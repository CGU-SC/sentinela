"""Indice de bitmaps (Roaring) dos filtros de farmacia da tela de analises.

Os dados vem do SQL (etapa 1) ja sincronizados nos .smod CRM; este modulo so os
reorganiza para consulta rapida -- nao calcula regra de negocio nova:

* farmacia x ano / farmacia x mes: medicos (id_medico_num) com prescricao na
  farmacia no periodo (crm_farmacia_medico_ano / crm_medico_estabelecimento_mes);
* alta x ano / alta x mes: medicos com mes de alta intensidade no territorio
  (UF e municipio), igual as tabelas do ranking (crm_medico_territorio_ano /
  _mes com o P95 de crm_limiar_p95_mes).

Com um filtro de farmacia, a uniao dos bitmaps das farmacias filtradas de um
territorio da, em milissegundos, os medicos que prescreveram nelas; a
intersecao com o bitmap de alta do territorio da os de alta intensidade.

O arquivo guarda a assinatura (tamanho e data) dos .smod de origem; se algum
for sincronizado de novo sem remontar o indice, a consulta responde 503.
"""

from __future__ import annotations

import array
import json
import os
import shutil
import threading
import time
from collections import OrderedDict
from pathlib import Path
from typing import Callable, Iterable, Optional

import numpy as np
import polars as pl
from pyroaring import BitMap, FrozenBitMap

from cache_files import CRM_INDICE_BITMAPS_VERSION

FONTES = (
    "crm_medico_dim",
    "crm_farmacia_medico_ano",
    "crm_medico_estabelecimento_mes",
    "crm_medico_territorio_ano",
    "crm_medico_territorio_mes",
    "crm_limiar_p95_mes",
)
NIVEIS_ALTA = ("uf", "municipio")
MESES_EM_MEMORIA = 24


class IndiceDesatualizado(RuntimeError):
    """O indice nao corresponde aos .smod carregados (ou nao existe)."""


def chave_territorio(nivel: str, id_geografico: str) -> str:
    return f"{nivel}:{id_geografico}"


# ── Montagem (sincronizacao) ─────────────────────────────────────────────────
def _serializar_grupos(df: pl.DataFrame, chave: str, valor: str) -> pl.DataFrame:
    """Um bitmap serializado por valor de `chave` (valores de `valor` como uint32)."""
    if df.is_empty():
        return pl.DataFrame(schema={"chave": pl.Utf8, "bitmap": pl.Binary})
    df = df.sort([chave, valor])
    contagens = df.group_by(chave, maintain_order=True).agg(pl.len().alias("n"))
    valores = df.get_column(valor).cast(pl.UInt32).to_numpy()
    fins = contagens.get_column("n").cum_sum().to_numpy()
    inicios = fins - contagens.get_column("n").to_numpy()
    bitmaps = [
        BitMap(array.array("I", valores[a:b].tobytes())).serialize()
        for a, b in zip(inicios, fins)
    ]
    return pl.DataFrame({
        "chave": contagens.get_column(chave).cast(pl.Utf8),
        "bitmap": pl.Series(bitmaps, dtype=pl.Binary),
    })


def _com_codigo(df: pl.LazyFrame, dim: pl.DataFrame, origem: str) -> pl.DataFrame:
    """Troca id_medico pelo codigo inteiro; medico fora da dimensao e erro."""
    base = df.collect(engine="streaming")
    com = base.join(dim, on="id_medico", how="inner")
    if com.height != base.height:
        raise RuntimeError(
            f"{base.height - com.height} linhas de {origem} com medico fora de crm_medico_dim."
        )
    return com


def construir_indice(destino: str, progress_callback: Optional[Callable[[int], None]] = None) -> None:
    import data_cache as dc

    t0 = time.perf_counter()
    print("Montando indice de bitmaps CRM (filtros de farmacia)...")
    assinatura = {nome: list(dc.get_global_cache_signature(nome)[1:]) for nome in FONTES}

    dim = dc.scan_crm_medico_dim().select([
        pl.col("id_medico").cast(pl.Utf8),
        pl.col("id_medico_num").cast(pl.Int32),
    ]).collect()
    if dim.height == 0 or dim.get_column("id_medico_num").n_unique() != dim.height:
        raise RuntimeError("crm_medico_dim vazia ou com codigos repetidos.")
    if dim.get_column("id_medico").n_unique() != dim.height:
        raise RuntimeError("crm_medico_dim com id_medico repetido.")

    limiar = dc.scan_crm_limiar_p95_mes().select([
        pl.col("competencia").cast(pl.Int32),
        pl.col("p95_taxa_dia").cast(pl.Float64),
    ]).collect()
    meses = sorted(limiar.get_column("competencia").to_list())
    anos = sorted({m // 100 for m in meses})

    partes_dir = Path(destino).parent / ".parts" / "crm_indice_bitmaps"
    shutil.rmtree(partes_dir, ignore_errors=True)
    partes_dir.mkdir(parents=True, exist_ok=True)
    partes: list[str] = []

    def gravar(tipo: str, granularidade: str, periodo: int, grupos: pl.DataFrame) -> None:
        if grupos.is_empty():
            return
        caminho = partes_dir / f"{granularidade}_{periodo}_{tipo}.parquet"
        grupos.select([
            pl.lit(tipo).alias("tipo"),
            pl.lit(granularidade).alias("granularidade"),
            pl.lit(periodo, dtype=pl.Int32).alias("periodo"),
            pl.col("chave"),
            pl.col("bitmap"),
        ]).write_parquet(caminho, compression="zstd", row_group_size=20_000)
        partes.append(str(caminho))

    total_passos = len(anos) + len(meses)
    passo = 0

    for ano in anos:
        fato = dc.scan_crm_farmacia_medico_ano().filter(pl.col("ano") == ano).select([
            pl.col("id_cnpj").cast(pl.Int32),
            pl.col("id_medico_num").cast(pl.Int32),
        ]).collect(engine="streaming")
        gravar("farmacia", "ano", ano, _serializar_grupos(fato, "id_cnpj", "id_medico_num"))

        alta = _com_codigo(
            dc.scan_crm_medico_territorio_ano()
            .filter(
                (pl.col("ano") == ano)
                & pl.col("nivel").is_in(NIVEIS_ALTA)
                & (pl.col("qtd_meses_alta_intensidade") > 0)
            )
            .select([
                (pl.col("nivel").cast(pl.Utf8) + ":" + pl.col("id_geografico").cast(pl.Utf8)).alias("chave"),
                pl.col("id_medico").cast(pl.Utf8),
            ]),
            dim, "crm_medico_territorio_ano",
        )
        gravar("alta", "ano", ano, _serializar_grupos(alta, "chave", "id_medico_num"))
        passo += 1
        print(f"   -> ano {ano}: {fato.height:,} pares farmacia-medico, {alta.height:,} medico-territorio de alta")
        if progress_callback:
            progress_callback(int(passo / total_passos * 95))

    p95 = dict(zip(limiar.get_column("competencia").to_list(), limiar.get_column("p95_taxa_dia").to_list()))
    for competencia in meses:
        farmacia = _com_codigo(
            dc.scan_crm_medico_estabelecimento_mes()
            .filter(pl.col("competencia") == competencia)
            .select([pl.col("id_cnpj").cast(pl.Int32), pl.col("id_medico").cast(pl.Utf8)]),
            dim, "crm_medico_estabelecimento_mes",
        )
        gravar("farmacia", "mes", competencia, _serializar_grupos(farmacia, "id_cnpj", "id_medico_num"))

        # Mesma regra do ranking: taxa do mes (6 casas) acima do P95 do mes.
        alta = _com_codigo(
            dc.scan_crm_medico_territorio_mes()
            .filter(
                (pl.col("competencia") == competencia)
                & pl.col("nivel").is_in(NIVEIS_ALTA)
                & (pl.col("nu_prescricoes_mes") > 0)
                & (pl.col("qtd_dias_com_prescricao_mes") > 0)
            )
            .filter(
                (
                    pl.col("nu_prescricoes_mes").cast(pl.Float64)
                    / pl.col("qtd_dias_com_prescricao_mes").cast(pl.Float64)
                ).round(6) > p95[competencia]
            )
            .select([
                (pl.col("nivel").cast(pl.Utf8) + ":" + pl.col("id_geografico").cast(pl.Utf8)).alias("chave"),
                pl.col("id_medico").cast(pl.Utf8),
            ]),
            dim, "crm_medico_territorio_mes",
        )
        gravar("alta", "mes", competencia, _serializar_grupos(alta, "chave", "id_medico_num"))
        passo += 1
        if progress_callback:
            progress_callback(int(passo / total_passos * 95))

    meta = pl.DataFrame({
        "tipo": ["meta"],
        "granularidade": ["-"],
        "periodo": pl.Series([0], dtype=pl.Int32),
        "chave": ["assinatura"],
        "bitmap": pl.Series([json.dumps({
            "versao": CRM_INDICE_BITMAPS_VERSION,
            "fontes": assinatura,
            "medicos": dim.height,
            "meses": meses,
        }).encode("utf-8")], dtype=pl.Binary),
    })
    caminho_meta = partes_dir / "meta.parquet"
    meta.write_parquet(caminho_meta)

    # Ordem por granularidade e periodo: a leitura de um mes le poucos row groups.
    tmp = destino + ".tmp"
    pl.concat([pl.scan_parquet(str(caminho_meta)), *[pl.scan_parquet(p) for p in partes]]).sink_parquet(
        tmp, compression="zstd", row_group_size=20_000,
    )
    os.replace(tmp, destino)
    shutil.rmtree(partes_dir, ignore_errors=True)
    if progress_callback:
        progress_callback(100)
    print(f"   Indice de bitmaps gravado em {time.perf_counter() - t0:.0f}s ({os.path.getsize(destino) / 1e6:,.0f} MB).")


# ── Consulta (backend) ────────────────────────────────────────────────────────
class IndiceBitmaps:
    """Bitmaps anuais em memoria; mensais carregados sob demanda (LRU)."""

    def __init__(self, caminho: str, dim_ids: pl.Series, meses: list[int]):
        self.caminho = caminho
        self.dim_ids = dim_ids
        self.meses_dados = meses
        self.farmacia_ano: dict[int, dict[int, FrozenBitMap]] = {}
        self.alta_ano: dict[int, dict[str, FrozenBitMap]] = {}
        self._meses: "OrderedDict[int, tuple[dict[int, FrozenBitMap], dict[str, FrozenBitMap]]]" = OrderedDict()
        self._lock = threading.Lock()
        linhas = (
            pl.scan_parquet(caminho)
            .filter(pl.col("granularidade") == "ano")
            .select(["tipo", "periodo", "chave", "bitmap"])
            .collect()
        )
        for tipo, periodo, chave, dados in linhas.iter_rows():
            bm = FrozenBitMap.deserialize(dados)
            if tipo == "farmacia":
                self.farmacia_ano.setdefault(periodo, {})[int(chave)] = bm
            else:
                self.alta_ano.setdefault(periodo, {})[chave] = bm

    def _mes(self, competencia: int):
        with self._lock:
            if competencia in self._meses:
                self._meses.move_to_end(competencia)
                return self._meses[competencia]
        linhas = (
            pl.scan_parquet(self.caminho)
            .filter((pl.col("granularidade") == "mes") & (pl.col("periodo") == competencia))
            .select(["tipo", "chave", "bitmap"])
            .collect()
        )
        farmacia: dict[int, FrozenBitMap] = {}
        alta: dict[str, FrozenBitMap] = {}
        for tipo, chave, dados in linhas.iter_rows():
            bm = FrozenBitMap.deserialize(dados)
            if tipo == "farmacia":
                farmacia[int(chave)] = bm
            else:
                alta[chave] = bm
        with self._lock:
            self._meses[competencia] = (farmacia, alta)
            while len(self._meses) > MESES_EM_MEMORIA:
                self._meses.popitem(last=False)
        return farmacia, alta

    def uniao_farmacias(self, cnpjs: Iterable[int], anos: list[int], meses: list[int]) -> BitMap:
        """Medicos com prescricao em alguma das farmacias nos anos/meses."""
        fontes = [self.farmacia_ano.get(ano, {}) for ano in anos]
        fontes += [self._mes(m)[0] for m in meses]
        partes = [bm for fonte in fontes for cnpj in cnpjs if (bm := fonte.get(cnpj)) is not None]
        return BitMap().union(*partes)

    def alta(self, chave: str, anos: list[int], meses: list[int]) -> BitMap:
        """Medicos com pelo menos um mes de alta intensidade no territorio."""
        partes = [bm for ano in anos if (bm := self.alta_ano.get(ano, {}).get(chave)) is not None]
        partes += [bm for m in meses if (bm := self._mes(m)[1].get(chave)) is not None]
        return BitMap().union(*partes)

    def ids_medico(self, medicos: BitMap) -> pl.Series:
        """id_medico (texto) dos codigos do bitmap, em ordem de codigo."""
        codigos = np.frombuffer(medicos.to_array(), dtype=np.uint32)
        return self.dim_ids.gather(codigos)


_INDICE: Optional[IndiceBitmaps] = None
_INDICE_CHAVE: Optional[tuple] = None
_INDICE_LOCK = threading.Lock()


def obter_indice() -> IndiceBitmaps:
    """Indice carregado e conferido contra os .smod atuais (carrega uma vez)."""
    import data_cache as dc

    global _INDICE, _INDICE_CHAVE
    try:
        chave = (
            dc.get_global_cache_signature("crm_indice_bitmaps"),
            *(dc.get_global_cache_signature(nome) for nome in FONTES),
        )
    except FileNotFoundError as exc:
        raise IndiceDesatualizado(f"Modulo CRM ausente: {exc}. Sincronize os modulos CRM e o indice de bitmaps.") from exc
    with _INDICE_LOCK:
        if _INDICE is not None and _INDICE_CHAVE == chave:
            return _INDICE
        caminho = dc._CRM_INDICE_BITMAPS_PATH
        meta = (
            pl.scan_parquet(caminho)
            .filter(pl.col("tipo") == "meta")
            .select("bitmap")
            .collect()
        )
        if meta.height != 1:
            raise IndiceDesatualizado("Indice de bitmaps CRM sem assinatura. Monte o indice de novo.")
        info = json.loads(meta.item(0, "bitmap").decode("utf-8"))
        atual = {nome: list(dc.get_global_cache_signature(nome)[1:]) for nome in FONTES}
        if info.get("versao") != CRM_INDICE_BITMAPS_VERSION or info.get("fontes") != atual:
            raise IndiceDesatualizado(
                "Indice de bitmaps CRM desatualizado em relacao aos modulos CRM sincronizados. "
                "Monte o indice de novo (sincronizar_cache.py, opcao 54)."
            )
        dim = dc.scan_crm_medico_dim().select([
            pl.col("id_medico_num").cast(pl.Int32),
            pl.col("id_medico").cast(pl.Utf8),
        ]).collect().sort("id_medico_num")
        if dim.height != info.get("medicos") or dim.item(dim.height - 1, "id_medico_num") != dim.height - 1:
            raise IndiceDesatualizado("crm_medico_dim nao corresponde ao indice de bitmaps.")
        _INDICE = IndiceBitmaps(caminho, dim.get_column("id_medico"), info["meses"])
        _INDICE_CHAVE = chave
        return _INDICE
