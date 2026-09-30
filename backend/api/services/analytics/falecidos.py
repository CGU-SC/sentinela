"""Vendas para falecidos (aba Falecidos do CNPJ).

Fonte: cache global `falecidos` (uma linha por autorizacao feita apos o obito
do beneficiario). O cadastro das farmacias vem do perfil de estabelecimentos e
o faturamento, da movimentacao mensal. Dado ausente ou inconsistente responde
503 em vez de virar zero ou lista vazia.
"""

from dataclasses import dataclass
from datetime import date
from typing import Optional

import polars as pl
from fastapi import HTTPException

from data_cache import get_df, get_df_falecidos, get_df_perfil_estabelecimento
from ...schemas.analytics import (
    FalecidoTransactionSchema,
    FalecidosRankingSchema,
    FalecidosResponse,
    FalecidosSummarySchema,
    MultiCnpjTimelineResponse,
    TimelineEventSchema,
)

# Quantas farmacias da rede de coincidencia aparecem na tela (o arquivo
# exportado traz todas).
RANKING_TELA = 20

_COLUNAS = {
    "cnpj", "cpf", "nome_falecido", "municipio_falecido", "uf_falecido", "dt_nascimento",
    "dt_obito", "fonte_obito", "num_autorizacao", "data_autorizacao",
    "qtd_itens_na_autorizacao", "valor_total_autorizacao", "dias_apos_obito",
}
# Campos sem os quais a autorizacao nao pode ser exibida nem somada.
_OBRIGATORIOS = (
    "cpf", "num_autorizacao", "data_autorizacao", "dt_obito",
    "qtd_itens_na_autorizacao", "valor_total_autorizacao", "dias_apos_obito",
)


def _indisponivel(detalhe: str) -> HTTPException:
    return HTTPException(status_code=503, detail=detalhe)


def _base_falecidos() -> pl.DataFrame:
    try:
        df = get_df_falecidos()
    except RuntimeError as exc:
        raise _indisponivel(f"Base de obitos indisponivel: {exc}") from exc
    faltando = _COLUNAS - set(df.columns)
    if faltando:
        raise _indisponivel(f"Base de obitos sem colunas obrigatorias: {', '.join(sorted(faltando))}.")
    return df


def _sem_nulos(df: pl.DataFrame, contexto: str) -> None:
    nulos = [c for c in _OBRIGATORIOS if df.get_column(c).null_count()]
    if nulos:
        raise _indisponivel(f"Autorizacoes de falecidos ({contexto}) sem {', '.join(nulos)}.")


def _cadastro(cnpjs: list[str]) -> pl.DataFrame:
    """cnpj, id_cnpj, razao_social, municipio e uf das farmacias pedidas (todas, sem duplicidade)."""
    cadastro = (
        get_df_perfil_estabelecimento()
        .select([
            pl.col("cnpj").cast(pl.Utf8),
            pl.col("id_cnpj").cast(pl.Int32),
            pl.col("razao_social").cast(pl.Utf8),
            pl.col("no_municipio").cast(pl.Utf8).alias("municipio"),
            pl.col("uf").cast(pl.Utf8),
        ])
        .filter(pl.col("cnpj").is_in(cnpjs))
    )
    duplicados = cadastro.filter(pl.col("cnpj").is_duplicated()).get_column("cnpj").unique().sort().to_list()
    if duplicados:
        raise _indisponivel(f"Perfil de estabelecimentos com mais de uma linha para: {', '.join(duplicados[:5])}.")
    ausentes = sorted(set(cnpjs) - set(cadastro.get_column("cnpj").to_list()))
    if ausentes:
        raise _indisponivel(f"Farmacias sem cadastro no perfil de estabelecimentos: {', '.join(ausentes[:5])}.")
    incompletos = cadastro.filter(
        pl.any_horizontal([pl.col(c).is_null() | (pl.col(c).str.strip_chars() == "") for c in ("razao_social", "municipio", "uf")])
    ).get_column("cnpj").to_list()
    if incompletos:
        raise _indisponivel(f"Farmacias sem razao social, municipio ou UF no perfil: {', '.join(sorted(incompletos)[:5])}.")
    return cadastro


def _faturamento(id_cnpj: int, data_inicio: Optional[date], data_fim: Optional[date]) -> float:
    """Faturamento PFPB da farmacia no mesmo periodo das autorizacoes."""
    mov = get_df().filter(pl.col("id_cnpj") == id_cnpj)
    if data_inicio:
        mov = mov.filter(pl.col("periodo") >= data_inicio.replace(day=1))
    if data_fim:
        mov = mov.filter(pl.col("periodo") <= data_fim)
    return float(mov.select(pl.col("total_vendas").sum()).item() or 0.0)


@dataclass(frozen=True)
class FalecidosDados:
    """Tudo o que a aba e a exportacao usam, calculado uma unica vez."""
    cnpj: str
    tem_historico: bool
    summary: FalecidosSummarySchema
    # Autorizacoes desta farmacia, ordenadas por CPF e data, com a coluna
    # "outros" (outras farmacias do CPF: "cnpj | municipio/UF; ...").
    transacoes: pl.DataFrame
    # Autorizacoes desses CPFs em outras farmacias, com o cadastro delas.
    outras: pl.DataFrame
    # Rede de coincidencia completa: cnpj, razao_social, municipio, uf,
    # qtd_cpfs, pct_total, estabelecimento; ordenada por qtd_cpfs.
    ranking: pl.DataFrame
    faturamento_periodo: Optional[float]


def _resumo_vazio() -> FalecidosSummarySchema:
    return FalecidosSummarySchema(
        cpfs_distintos=0, total_autorizacoes=0, valor_total=0.0, media_dias=0.0,
        max_dias=0, pct_faturamento=0.0, cpfs_multi_cnpj=0, pct_multi_cnpj=0.0,
    )


_RANKING_VAZIO = pl.DataFrame(schema={
    "cnpj": pl.Utf8, "razao_social": pl.Utf8, "municipio": pl.Utf8, "uf": pl.Utf8,
    "qtd_cpfs": pl.UInt32, "pct_total": pl.Float64, "estabelecimento": pl.Utf8,
})


def ranking_outras_farmacias(outras: pl.DataFrame) -> pl.DataFrame:
    """Rede de coincidencia: CPFs em comum por farmacia (pct sobre a soma das coincidencias)."""
    if outras.is_empty():
        return _RANKING_VAZIO
    return (
        outras.group_by(["cnpj", "razao_social", "municipio", "uf"])
        .agg(pl.col("cpf").n_unique().alias("qtd_cpfs"))
        .with_columns((pl.col("qtd_cpfs") / pl.col("qtd_cpfs").sum()).alias("pct_total"))
        .with_columns(pl.format("{} - {} | {}/{}", "cnpj", "razao_social", "municipio", "uf").alias("estabelecimento"))
        .sort(["qtd_cpfs", "cnpj"], descending=[True, False])
    )


def carregar_falecidos(cnpj: str, data_inicio: Optional[date] = None, data_fim: Optional[date] = None) -> FalecidosDados:
    cnpj_norm = "".join(ch for ch in str(cnpj or "") if ch.isdigit())
    if len(cnpj_norm) != 14:
        raise HTTPException(status_code=422, detail="CNPJ invalido.")
    base = _base_falecidos()
    tem_historico = not base.filter(pl.col("cnpj") == cnpj_norm).is_empty()

    periodo = base
    if data_inicio:
        periodo = periodo.filter(pl.col("data_autorizacao") >= data_inicio)
    if data_fim:
        periodo = periodo.filter(pl.col("data_autorizacao") <= data_fim)

    alvo = periodo.filter(pl.col("cnpj") == cnpj_norm)
    if alvo.is_empty():
        return FalecidosDados(
            cnpj=cnpj_norm, tem_historico=tem_historico, summary=_resumo_vazio(),
            transacoes=alvo.with_columns(pl.lit(None, dtype=pl.Utf8).alias("outros")),
            outras=alvo.clear().with_columns([pl.lit(None, dtype=pl.Utf8).alias(c) for c in ("razao_social", "municipio", "uf")]),
            ranking=_RANKING_VAZIO, faturamento_periodo=None,
        )
    _sem_nulos(alvo, "desta farmacia")

    # Mesmos CPFs em outras farmacias, no mesmo periodo.
    outras = periodo.filter(
        (pl.col("cnpj") != cnpj_norm) & pl.col("cpf").is_in(alvo.get_column("cpf").unique().implode())
    )
    cadastro = _cadastro(sorted({cnpj_norm, *outras.get_column("cnpj").unique().to_list()}))
    outras = outras.join(cadastro.drop("id_cnpj"), on="cnpj", how="inner", validate="m:1")

    total_cpfs_outras = outras.get_column("cpf").n_unique()

    outros_por_cpf = (
        outras.select(["cpf", pl.format("{} | {}/{}", "cnpj", "municipio", "uf").alias("info")])
        .unique()
        .sort(["cpf", "info"])
        .group_by("cpf", maintain_order=True)
        .agg(pl.col("info").str.join("; ").alias("outros"))
    )
    transacoes = (
        alvo.join(outros_por_cpf, on="cpf", how="left", validate="m:1")
        .sort(["cpf", "data_autorizacao", "num_autorizacao"])
    )

    id_cnpj = cadastro.filter(pl.col("cnpj") == cnpj_norm).item(0, "id_cnpj")
    valor_total = float(alvo.get_column("valor_total_autorizacao").sum())
    faturamento = _faturamento(id_cnpj, data_inicio, data_fim)
    if faturamento <= 0:
        raise _indisponivel(
            "Farmacia com autorizacoes para falecidos, mas sem faturamento na movimentacao do periodo."
        )
    cpfs_distintos = alvo.get_column("cpf").n_unique()
    summary = FalecidosSummarySchema(
        cpfs_distintos=cpfs_distintos,
        total_autorizacoes=alvo.height,
        valor_total=valor_total,
        media_dias=float(alvo.select(pl.col("dias_apos_obito").mean()).item()),
        max_dias=int(alvo.select(pl.col("dias_apos_obito").max()).item()),
        pct_faturamento=valor_total / faturamento,
        cpfs_multi_cnpj=total_cpfs_outras,
        pct_multi_cnpj=total_cpfs_outras / cpfs_distintos,
    )
    return FalecidosDados(
        cnpj=cnpj_norm, tem_historico=tem_historico, summary=summary,
        transacoes=transacoes, outras=outras, ranking=ranking_outras_farmacias(outras),
        faturamento_periodo=faturamento,
    )


def get_falecidos_data(
    cnpj: str,
    data_inicio: date | None = None,
    data_fim: date | None = None,
) -> FalecidosResponse:
    """Retorna os dados detalhados de vendas para falecidos de um CNPJ."""
    dados = carregar_falecidos(cnpj, data_inicio, data_fim)
    return FalecidosResponse(
        cnpj=dados.cnpj,
        summary=dados.summary,
        ranking=[
            FalecidosRankingSchema(
                cnpj=r["cnpj"], razao_social=r["razao_social"], municipio=r["municipio"], uf=r["uf"],
                estabelecimento=r["estabelecimento"], qtd_cpfs=r["qtd_cpfs"], pct_total=r["pct_total"],
            )
            for r in dados.ranking.head(RANKING_TELA).iter_rows(named=True)
        ],
        transacoes=[
            FalecidoTransactionSchema(
                cpf=str(r["cpf"]).zfill(11),
                nome_falecido=r["nome_falecido"],
                municipio_falecido=r["municipio_falecido"],
                uf_falecido=r["uf_falecido"],
                dt_nascimento=r["dt_nascimento"],
                dt_obito=r["dt_obito"],
                fonte_obito=r["fonte_obito"],
                num_autorizacao=str(r["num_autorizacao"]),
                data_autorizacao=r["data_autorizacao"],
                qtd_itens_na_autorizacao=int(r["qtd_itens_na_autorizacao"]),
                valor_total_autorizacao=float(r["valor_total_autorizacao"]),
                dias_apos_obito=int(r["dias_apos_obito"]),
                outros_estabelecimentos=r["outros"],
            )
            for r in dados.transacoes.iter_rows(named=True)
        ],
        from_cache=True,
        tem_historico=dados.tem_historico,
    )


def get_timeline_cpf(cnpj_referencia: str, cpf: str) -> MultiCnpjTimelineResponse:
    """Todas as autorizacoes de um CPF falecido, em todas as farmacias (Mapa de Trilhas Temporais).

    Args:
        cnpj_referencia: CNPJ que originou a consulta (marca `is_this_cnpj`).
        cpf: CPF do falecido.
    """
    cnpj_ref_norm = "".join(ch for ch in str(cnpj_referencia or "") if ch.isdigit())
    cpf_clean = "".join(ch for ch in str(cpf or "") if ch.isdigit()).zfill(11)
    if len(cpf_clean) != 11:
        raise HTTPException(status_code=422, detail="CPF invalido.")
    df_cpf = _base_falecidos().filter(pl.col("cpf").cast(pl.Utf8).str.zfill(11) == cpf_clean)
    if df_cpf.is_empty():
        return MultiCnpjTimelineResponse(cpf=cpf, nome_falecido=None, dt_obito=None, events=[], cnpjs_envolvidos=[])
    _sem_nulos(df_cpf, f"CPF {cpf_clean}")

    cnpjs = sorted(df_cpf.get_column("cnpj").unique().to_list())
    eventos = df_cpf.join(_cadastro(cnpjs).drop("id_cnpj"), on="cnpj", how="inner", validate="m:1")
    row0 = df_cpf.row(0, named=True)
    return MultiCnpjTimelineResponse(
        cpf=cpf,
        nome_falecido=row0["nome_falecido"],
        dt_obito=row0["dt_obito"],
        events=[
            TimelineEventSchema(
                cnpj=str(r["cnpj"]),
                razao_social=r["razao_social"],
                municipio=r["municipio"],
                uf=r["uf"],
                data_autorizacao=r["data_autorizacao"],
                valor_total_autorizacao=float(r["valor_total_autorizacao"]),
                num_autorizacao=str(r["num_autorizacao"]),
                is_this_cnpj=(str(r["cnpj"]) == cnpj_ref_norm),
            )
            for r in eventos.sort(["data_autorizacao", "num_autorizacao"]).iter_rows(named=True)
        ],
        cnpjs_envolvidos=cnpjs,
    )
