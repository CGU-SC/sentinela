"""Mapa e ranking de medicos (tela /analises) com filtros de farmacia.

Com qualquer filtro alem de periodo e localizacao, o universo passa a ser o das
farmacias filtradas -- exatamente as mesmas de /estabelecimentos. Regra "no
periodo":

* entra o medico que prescreveu em pelo menos uma farmacia filtrada do
  territorio, em qualquer mes do periodo;
* mapa: ativos = esses medicos; alta intensidade = os que, alem disso, tiveram
  pelo menos um mes de alta intensidade no territorio no periodo (mesma
  marcacao do mapa sem filtro: taxa do mes acima do P95 nacional do mes, com
  todas as prescricoes do medico no territorio);
* ranking: os indicadores do medico sao os do escopo inteiro (mesmos numeros
  do ranking sem filtro); a coluna extra traz as prescricoes nas farmacias
  filtradas do escopo e a fatia delas no total do medico.

Os conjuntos de medicos vem do indice de bitmaps (crm_indice_bitmaps), montado
na sincronizacao a partir dos modulos CRM.
"""

import threading
from collections import OrderedDict
from datetime import date
from collections.abc import Mapping
from typing import Callable, Optional, TypeVar, cast

import polars as pl
from fastapi import HTTPException
from pyroaring import BitMap

from crm_indice_bitmaps import IndiceBitmaps, IndiceDesatualizado, chave_territorio, obter_indice
from data_cache import (
    get_cache_generation,
    get_localidades_df,
    scan_crm_farmacia_medico_ano,
    scan_crm_medico_dim,
    scan_crm_medico_estabelecimento_mes,
)
from . import crm_analysis as base
from .indicadores import get_indicador_scope_base_cached

# Filtros que definem as farmacias (os de localizacao ficam de fora: o recorte
# geografico e feito pelo territorio do mapa/ranking).
FILTROS_FARMACIA = (
    "situacao_rf", "conexao_ms", "porte_empresa", "grande_rede", "cnpj_raiz",
    "estabelecimento", "unidade_pf", "par_teia", "socio_beneficio", "socio_esocial",
    "cnae_incompativel", "socio_idade_atipica", "socio_falecido",
    "dispersao_uf_sem_fronteira", "dispersao_uf_sem_fronteira_limite",
    "perc_min", "perc_max", "val_min", "volume_atipico", "volume_atipico_limite",
)

_COLUNA_TERRITORIO = {
    "uf": "uf",
    "regiao_saude": "id_regiao_saude",
    "municipio": "id_municipio",
}

_T = TypeVar("_T")

_CACHE_MAX_ITENS = 32
_CACHE: "OrderedDict[tuple[object, ...], object]" = OrderedDict()
_CACHE_LOCK = threading.Lock()


def _em_cache(chave: tuple[object, ...], calcular: Callable[[], _T]) -> _T:
    """Cache LRU por geracao dos modulos (descarta geracoes antigas)."""
    geracao = get_cache_generation()
    chave = (geracao, *chave)
    with _CACHE_LOCK:
        for antiga in [k for k in _CACHE if k[0] != geracao]:
            del _CACHE[antiga]
        if chave in _CACHE:
            _CACHE.move_to_end(chave)
            return cast(_T, _CACHE[chave])
    valor = calcular()
    with _CACHE_LOCK:
        _CACHE[chave] = valor
        _CACHE.move_to_end(chave)
        while len(_CACHE) > _CACHE_MAX_ITENS:
            _CACHE.popitem(last=False)
    return valor


def _chave_filtros(filtros: Mapping[str, object]) -> tuple[object, ...]:
    return tuple((nome, filtros.get(nome)) for nome in FILTROS_FARMACIA)


def _indice() -> IndiceBitmaps:
    try:
        return obter_indice()
    except IndiceDesatualizado as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


# ── Farmacias e medicos delas ────────────────────────────────────────────────
def _farmacias(filtros: Mapping[str, object], inicio: date, fim: date) -> pl.DataFrame:
    """id_cnpj e territorio das farmacias filtradas (mesma base de /estabelecimentos)."""
    def calcular() -> pl.DataFrame:
        scope = get_indicador_scope_base_cached(data_inicio=inicio, data_fim=fim, **filtros)
        base._require_columns(scope, {"id_cnpj", "uf", "id_regiao_saude", "id_ibge7"}, "Base de farmacias filtradas")
        farmacias = scope.select([
            pl.col("id_cnpj").cast(pl.Int32),
            pl.col("uf").cast(pl.Utf8),
            pl.col("id_regiao_saude").cast(pl.Utf8),
            pl.col("id_ibge7").cast(pl.Int64).cast(pl.Utf8).alias("id_municipio"),
        ]).unique("id_cnpj")
        if farmacias.select(pl.any_horizontal(pl.all().is_null()).any()).item():
            raise HTTPException(status_code=503, detail="Farmacias filtradas sem UF, regiao ou municipio.")
        return farmacias
    return _em_cache(("farmacias", _chave_filtros(filtros), inicio, fim), calcular)


def _cnpjs(farmacias: pl.DataFrame, nivel: Optional[str], territorio: Optional[str]) -> list[int]:
    if nivel is None:
        return farmacias.get_column("id_cnpj").to_list()
    return farmacias.filter(pl.col(_COLUNA_TERRITORIO[nivel]) == territorio).get_column("id_cnpj").to_list()


def _medicos_por_territorio(filtros, nivel: str, inicio: date, fim: date) -> dict[str, BitMap]:
    """Por territorio do nivel: medicos com prescricao nas farmacias filtradas dele."""
    def calcular() -> dict[str, BitMap]:
        indice = _indice()
        anos, meses = base._dividir_periodo_ranking(inicio, fim)
        grupos = (
            _farmacias(filtros, inicio, fim)
            .group_by(_COLUNA_TERRITORIO[nivel])
            .agg(pl.col("id_cnpj"))
        )
        return {
            territorio: indice.uniao_farmacias(cnpjs, anos, meses)
            for territorio, cnpjs in grupos.iter_rows()
        }
    return _em_cache(("medicos", nivel, _chave_filtros(filtros), inicio, fim), calcular)


def _medicos_escopo(filtros, nivel: Optional[str], territorio: Optional[str], inicio: date, fim: date) -> BitMap:
    """Medicos com prescricao nas farmacias filtradas do escopo (None = Brasil)."""
    if nivel == "brasil" or nivel is None:
        por_uf = _medicos_por_territorio(filtros, "uf", inicio, fim)
        return _em_cache(
            ("medicos_brasil", _chave_filtros(filtros), inicio, fim),
            lambda: BitMap().union(*por_uf.values()),
        )
    if territorio is None:
        raise ValueError(f"Escopo {nivel} sem territorio.")
    return _medicos_por_territorio(filtros, nivel, inicio, fim).get(territorio, BitMap())


def _contagens(filtros, nivel: str, inicio: date, fim: date) -> pl.DataFrame:
    """Por territorio (uf ou municipio): medicos ativos e de alta intensidade."""
    def calcular() -> pl.DataFrame:
        indice = _indice()
        anos, meses = base._dividir_periodo_ranking(inicio, fim)
        linhas = [
            (
                territorio,
                len(medicos),
                medicos.intersection_cardinality(indice.alta(chave_territorio(nivel, territorio), anos, meses)),
            )
            for territorio, medicos in _medicos_por_territorio(filtros, nivel, inicio, fim).items()
            if medicos
        ]
        return pl.DataFrame(
            linhas,
            schema={
                "id_geografico": pl.Utf8,
                "qtd_medicos_ativos": pl.Int64,
                "qtd_medicos_alta_intensidade": pl.Int64,
            },
            orient="row",
        )
    return _em_cache(("contagens", nivel, _chave_filtros(filtros), inicio, fim), calcular)


# ── Mapa ──────────────────────────────────────────────────────────────────────
def mapa_filtrado(
    *,
    filtros: Mapping[str, object],
    map_level: str,
    inicio: date,
    fim: date,
    uf: Optional[str],
    regiao_id: Optional[int],
    id_ibge7: Optional[int],
):
    """Mesmo contrato de base._build_manager_map, com o universo das farmacias filtradas."""
    if map_level == "uf":
        contagens = _contagens(filtros, "uf", inicio, fim).rename({"id_geografico": "uf"})
        ufs = (
            get_localidades_df().select(pl.col("sg_uf").cast(pl.Utf8).alias("uf")).unique()
            .join(contagens, on="uf", how="left")
            .with_columns([
                pl.col("qtd_medicos_ativos").fill_null(0),
                pl.col("qtd_medicos_alta_intensidade").fill_null(0),
            ])
        )
        percentual_brasil = base._percentual_somado(ufs)
        if uf and uf != "Todos":
            ufs = ufs.filter(pl.col("uf") == uf)
        summary = (
            ufs.with_columns(base._percentual_expr().alias("percentual_alta_intensidade"))
            .sort("percentual_alta_intensidade", descending=True, nulls_last=True)
        )
        referencia = {"percentual_referencia_brasil": percentual_brasil}
        qtd = len(
            _medicos_escopo(filtros, "uf", uf, inicio, fim) if uf and uf != "Todos"
            else _medicos_escopo(filtros, None, None, inicio, fim)
        )
        return base._map_items_from_summary(summary, "uf", percentual_brasil=percentual_brasil), qtd, referencia

    localidades = get_localidades_df()
    base._require_columns(localidades, base.CRM_ANALYSIS_REQUIRED_LOCALIDADES_COLUMNS, "Localidades")
    geo = localidades.select([
        pl.col("id_ibge7").cast(pl.Int64),
        pl.col("sg_uf").cast(pl.Utf8).alias("uf"),
        pl.col("id_regiao_saude").cast(pl.Utf8),
        pl.col("no_regiao_saude").cast(pl.Utf8),
        pl.col("no_municipio").cast(pl.Utf8),
    ]).unique("id_ibge7")
    contagens = (
        _contagens(filtros, "municipio", inicio, fim)
        .with_columns(pl.col("id_geografico").cast(pl.Int64).alias("id_ibge7"))
        .drop("id_geografico")
    )
    municipios_geo = contagens.join(geo.select(["id_ibge7", "uf", "id_regiao_saude"]), on="id_ibge7", how="left")
    if municipios_geo.filter(pl.col("uf").is_null()).height:
        raise HTTPException(status_code=503, detail="Municipios das farmacias filtradas ausentes no cache de localidades.")

    percentual_brasil = base._percentual_somado(municipios_geo) if municipios_geo.height else None
    uf_referencia = uf if uf and uf != "Todos" else None
    percentual_uf = (
        base._percentual_somado(municipios_geo.filter(pl.col("uf") == uf_referencia))
        if uf_referencia is not None else None
    )
    referencia_regioes = (
        municipios_geo.group_by("id_regiao_saude").agg([
            pl.sum("qtd_medicos_ativos").alias("qtd_medicos_ativos"),
            pl.sum("qtd_medicos_alta_intensidade").alias("qtd_medicos_alta_intensidade"),
        ])
        .with_columns(base._percentual_expr().alias("percentual_referencia_regiao"))
        .select(["id_regiao_saude", "percentual_referencia_regiao"])
    )

    geo_scope = geo
    if uf_referencia is not None:
        geo_scope = geo_scope.filter(pl.col("uf") == uf_referencia)
    if regiao_id is not None:
        geo_scope = geo_scope.filter(pl.col("id_regiao_saude") == str(regiao_id))
    if id_ibge7 is not None:
        geo_scope = geo_scope.filter(pl.col("id_ibge7") == id_ibge7)

    if id_ibge7 is not None:
        qtd = len(_medicos_escopo(filtros, "municipio", str(id_ibge7), inicio, fim))
    elif regiao_id is not None:
        qtd = len(_medicos_escopo(filtros, "regiao_saude", str(regiao_id), inicio, fim))
    elif uf_referencia is not None:
        qtd = len(_medicos_escopo(filtros, "uf", uf_referencia, inicio, fim))
    else:
        raise HTTPException(status_code=422, detail="O mapa geografico exige UF, regiao de saude ou municipio.")

    summary = (
        geo_scope
        .join(contagens, on="id_ibge7", how="left")
        .join(referencia_regioes, on="id_regiao_saude", how="left")
        .with_columns([
            pl.col("qtd_medicos_ativos").fill_null(0).cast(pl.Int64),
            pl.col("qtd_medicos_alta_intensidade").fill_null(0).cast(pl.Int64),
        ])
        .with_columns(base._percentual_expr().alias("percentual_alta_intensidade"))
        .sort("percentual_alta_intensidade", descending=True, nulls_last=True)
    )
    referencia = {
        "percentual_referencia_brasil": percentual_brasil,
        "percentual_referencia_uf": percentual_uf,
    }
    if regiao_id is not None:
        linha = referencia_regioes.filter(pl.col("id_regiao_saude") == str(regiao_id))
        referencia["percentual_referencia_regiao"] = linha.item(0, "percentual_referencia_regiao") if linha.height == 1 else None
    items = base._map_items_from_summary(
        summary, map_level, percentual_brasil=percentual_brasil, percentual_uf=percentual_uf,
    )
    return items, qtd, referencia


# ── Ranking ───────────────────────────────────────────────────────────────────
def _prescricoes_nas_farmacias(
    id_medicos: list[str],
    cnpjs: list[int],
    inicio: date,
    fim: date,
) -> pl.DataFrame:
    """Soma das prescricoes dos medicos (so os da pagina) nas farmacias do escopo."""
    anos, meses = base._dividir_periodo_ranking(inicio, fim)
    dim = (
        scan_crm_medico_dim()
        .filter(pl.col("id_medico").cast(pl.Utf8).is_in(id_medicos))
        .select([pl.col("id_medico").cast(pl.Utf8), pl.col("id_medico_num").cast(pl.Int32)])
        .collect()
    )
    cnpjs_serie = pl.Series("id_cnpj", cnpjs, dtype=pl.Int32)
    partes = []
    if anos:
        partes.append(
            scan_crm_farmacia_medico_ano()
            .filter(
                pl.col("ano").cast(pl.Int32).is_in(anos)
                & pl.col("id_medico_num").cast(pl.Int32).is_in(dim.get_column("id_medico_num"))
                & pl.col("id_cnpj").cast(pl.Int32).is_in(cnpjs_serie)
            )
            .select([pl.col("id_medico_num").cast(pl.Int32), pl.col("nu_prescricoes").cast(pl.Int64)])
            .collect()
            .join(dim, on="id_medico_num", how="inner")
            .select(["id_medico", "nu_prescricoes"])
        )
    if meses:
        partes.append(
            scan_crm_medico_estabelecimento_mes()
            .filter(
                pl.col("competencia").cast(pl.Int32).is_in(meses)
                & pl.col("id_medico").cast(pl.Utf8).is_in(id_medicos)
                & pl.col("id_cnpj").cast(pl.Int32).is_in(cnpjs_serie)
            )
            .select([
                pl.col("id_medico").cast(pl.Utf8),
                pl.col("nu_prescricoes_mes").cast(pl.Int64).alias("nu_prescricoes"),
            ])
            .collect()
        )
    return (
        pl.concat(partes)
        .group_by("id_medico")
        .agg(pl.col("nu_prescricoes").sum().alias("nu_prescricoes_farmacias_filtradas"))
    )


def ranking_filtrado(
    *,
    filtros: Mapping[str, object],
    inicio: date,
    fim: date,
    uf: Optional[str],
    regiao_id: Optional[int],
    id_ibge7: Optional[int],
) -> tuple[pl.DataFrame, Callable[[list[str]], pl.DataFrame]]:
    """Ranking do escopo restrito aos medicos das farmacias filtradas.

    Devolve o agregado (mesmas colunas do ranking sem filtro) e a funcao que
    soma, para os medicos da pagina, as prescricoes nas farmacias filtradas.
    """
    if id_ibge7 is not None:
        nivel, territorio = "municipio", str(id_ibge7)
    elif regiao_id is not None:
        nivel, territorio = "regiao_saude", str(regiao_id)
    elif uf and uf != "Todos":
        nivel, territorio = "uf", uf
    else:
        nivel, territorio = None, None

    def calcular() -> pl.DataFrame:
        medicos = _medicos_escopo(filtros, nivel, territorio, inicio, fim)
        ids = _indice().ids_medico(medicos)
        completo = base.ranking_agregado_escopo(
            inicio=inicio, fim=fim, uf=uf, regiao_id=regiao_id, id_ibge7=id_ibge7,
        )
        agregado = completo.filter(pl.col("id_medico").is_in(ids))
        if agregado.height != len(medicos):
            raise HTTPException(
                status_code=503,
                detail=(
                    f"{len(medicos) - agregado.height} medicos das farmacias filtradas fora do ranking do escopo. "
                    "Sincronize os modulos CRM e o indice de bitmaps da mesma execucao."
                ),
            )
        return agregado

    agregado = _em_cache(("ranking", nivel, territorio, _chave_filtros(filtros), inicio, fim), calcular)
    cnpjs = _cnpjs(_farmacias(filtros, inicio, fim), nivel, territorio)
    return agregado, lambda id_medicos: _prescricoes_nas_farmacias(id_medicos, cnpjs, inicio, fim)
