"""Medicos nas janelas de sequencia de multiplos CRMs (modulo derivado, sem banco).

A tabela de alertas de multiplos CRMs (crm_concentracao_multiplo_alertas_global)
descreve a janela na farmacia, mas nao diz quais medicos estavam nela. O Raio-X
(crm_raiox_tx_global) tem cada autorizacao com o medico. Este modulo cruza os
dois uma vez, na sincronizacao, e grava a ponte medico x janela:

* uma linha por medico em cada janela em que ele tem ao menos uma autorizacao;
* a autorizacao entra na janela quando e da mesma farmacia, do mesmo dia e a
  data/hora cai entre o inicio e o fim da janela (mesma regra do painel
  "Evidencias" do historico do CRM, crm_medico_evidencias._multiplos);
* nu_autorizacoes_crm = autorizacoes distintas do medico dentro da janela.

Nao calcula regra de negocio nova: quem consulta decide a participacao minima
(ver crm_filtros_medico). A janela e identificada por (id_cnpj,
dt_ini_concentracao), chave unica da tabela de alertas.

O arquivo guarda, nos metadados, a assinatura (data e tamanho) dos .smod de
origem; se algum for sincronizado de novo sem refazer este modulo, a consulta
responde 503 (ModuloDesatualizado) em vez de usar a ponte antiga.
"""

from __future__ import annotations

import json
import os
import time
from typing import Callable, Optional

import polars as pl

from cache_files import CRM_CONCENTRACAO_MULTIPLO_MEDICO_CACHE_VERSION

NOME = "crm_concentracao_multiplo_medico_global"
FONTES = ("crm_raiox_tx_global", "crm_concentracao_multiplo_alertas_global")
META_CHAVE = "sentinela_crm_multiplo_medico"
COLUNA_VERSAO = "_crm_multiplo_medico_cache_version"
_FORMATO_DATA_HORA = "%Y-%m-%d %H:%M:%S%.f"


class ModuloDesatualizado(RuntimeError):
    """O modulo nao corresponde aos .smod de origem carregados (ou a versao mudou)."""


def _assinatura_fontes() -> dict[str, list[int]]:
    import data_cache as dc

    return {nome: list(dc.get_global_cache_signature(nome)[1:]) for nome in FONTES}


def construir(destino: str, progress_callback: Optional[Callable[[int], None]] = None) -> None:
    """Cruza o Raio-X com os alertas de multiplos CRMs e grava a ponte medico x janela.

    Args:
        destino: caminho do .smod a gravar (substituido de forma atomica).
        progress_callback: recebe o percentual concluido (0 a 100).

    Raises:
        RuntimeError: fonte vazia, janela sem inicio/fim, chave de janela
            repetida, autorizacao sem data/hora valida ou cruzamento vazio.
    """
    import data_cache as dc

    t0 = time.perf_counter()
    print("Montando medicos por janela de multiplos CRMs...")
    assinatura = _assinatura_fontes()

    alertas = (
        dc.scan_crm_concentracao_multiplo_alertas_global()
        .select([
            pl.col("id_cnpj").cast(pl.Int32),
            pl.col("competencia").cast(pl.Int32),
            pl.col("dt_alerta").cast(pl.Utf8).str.slice(0, 10).alias("dt_alerta"),
            pl.col("hr_janela").cast(pl.Int32),
            pl.col("dt_ini_concentracao").cast(pl.Utf8)
            .str.strptime(pl.Datetime, _FORMATO_DATA_HORA, strict=False).alias("dt_ini_concentracao"),
            pl.col("dt_fim_concentracao").cast(pl.Utf8)
            .str.strptime(pl.Datetime, _FORMATO_DATA_HORA, strict=False).alias("_dt_fim"),
            pl.col("id_severidade").cast(pl.Int32),
        ])
        .collect()
        .with_row_index("_alerta")
    )
    if alertas.is_empty():
        raise RuntimeError("crm_concentracao_multiplo_alertas_global vazio: nada a cruzar com o Raio-X.")
    if alertas.select(pl.col("dt_ini_concentracao").is_null() | pl.col("_dt_fim").is_null()).to_series().any():
        raise RuntimeError("Alerta de multiplos CRMs sem inicio/fim de janela valido.")
    if alertas.select(pl.struct(["id_cnpj", "dt_ini_concentracao"]).is_duplicated().any()).item():
        raise RuntimeError("Alertas de multiplos CRMs com janela repetida (id_cnpj, dt_ini_concentracao).")
    if progress_callback:
        progress_callback(5)

    autorizacoes = dc.scan_crm_raiox_tx_global().select([
        pl.col("id_cnpj").cast(pl.Int32),
        pl.col("dt_janela").cast(pl.Utf8).str.slice(0, 10).alias("dt_alerta"),
        pl.col("data_hora").cast(pl.Utf8).str.strptime(pl.Datetime, _FORMATO_DATA_HORA, strict=False).alias("_data_hora"),
        pl.col("id_medico").cast(pl.Utf8),
        pl.col("num_autorizacao").cast(pl.Utf8),
    ])
    # A autorizacao sem data/hora valida fica no cruzamento (marcada) para a
    # montagem falhar em vez de deixa-la de fora em silencio.
    por_janela = (
        autorizacoes
        .join(
            alertas.lazy().select(["_alerta", "id_cnpj", "dt_alerta", "dt_ini_concentracao", "_dt_fim"]),
            on=["id_cnpj", "dt_alerta"], how="inner",
        )
        .filter(
            pl.col("_data_hora").is_null()
            | pl.col("_data_hora").is_between(pl.col("dt_ini_concentracao"), pl.col("_dt_fim"))
        )
        .group_by(["id_medico", "_alerta"])
        .agg([
            pl.col("num_autorizacao").n_unique().cast(pl.Int32).alias("nu_autorizacoes_crm"),
            pl.col("_data_hora").is_null().any().alias("_sem_data_hora"),
        ])
        .collect(engine="streaming")
    )
    if por_janela.get_column("_sem_data_hora").any():
        raise RuntimeError("Raio-X com autorizacao sem data/hora valida em dia de alerta de multiplos CRMs.")
    if por_janela.get_column("id_medico").null_count():
        raise RuntimeError("Raio-X com autorizacao sem medico em janela de multiplos CRMs.")
    if por_janela.is_empty():
        raise RuntimeError("Nenhuma autorizacao do Raio-X dentro das janelas de multiplos CRMs.")
    if progress_callback:
        progress_callback(80)

    # Ordenado por medico: a consulta de um medico le poucos row groups.
    resultado = (
        por_janela
        .join(alertas.drop("_dt_fim"), on="_alerta", how="inner")
        .select([
            "id_medico", "id_cnpj", "competencia", "dt_alerta", "hr_janela",
            "dt_ini_concentracao", "nu_autorizacoes_crm", "id_severidade",
            pl.lit(CRM_CONCENTRACAO_MULTIPLO_MEDICO_CACHE_VERSION, dtype=pl.Int32).alias(COLUNA_VERSAO),
        ])
        .sort(["id_medico", "dt_ini_concentracao", "id_cnpj"])
    )
    tmp = destino + ".tmp"
    resultado.write_parquet(
        tmp, compression="zstd", row_group_size=250_000,
        metadata={META_CHAVE: json.dumps({
            "versao": CRM_CONCENTRACAO_MULTIPLO_MEDICO_CACHE_VERSION,
            "fontes": assinatura,
        })},
    )
    os.replace(tmp, destino)
    if progress_callback:
        progress_callback(100)
    print(
        f"   {resultado.height:,} linhas medico x janela gravadas em "
        f"{time.perf_counter() - t0:.0f}s ({os.path.getsize(destino) / 1e6:,.0f} MB)."
    )


def conferir_fontes(caminho: str) -> None:
    """Confere que o modulo foi montado a partir dos .smod de origem atuais.

    Raises:
        ModuloDesatualizado: arquivo sem assinatura, de outra versao ou montado
            com fontes diferentes das carregadas.
    """
    bruto = pl.read_parquet_metadata(caminho).get(META_CHAVE)
    if bruto is None:
        raise ModuloDesatualizado(f"{NOME} sem assinatura das fontes; sincronize o modulo novamente.")
    meta = json.loads(bruto)
    if meta.get("versao") != CRM_CONCENTRACAO_MULTIPLO_MEDICO_CACHE_VERSION:
        raise ModuloDesatualizado(f"{NOME} de versao antiga; sincronize o modulo novamente.")
    if meta.get("fontes") != _assinatura_fontes():
        raise ModuloDesatualizado(
            f"{NOME} montado com outra versao de {' / '.join(FONTES)}; sincronize o modulo novamente."
        )
