"""Visoes mensais do ranking de medicos (tela /analises).

* Aba "Por mes": uma linha por medico e mes, ordenavel (padrao: taxa do mes
  / P95 nacional do mes, da maior para a menor). Mesmo universo do ranking:
  medicos com prescricao no escopo e no periodo; com filtro de farmacia, so os
  medicos das farmacias filtradas (os numeros continuam os do escopo inteiro).
* Aba "Linha do tempo": serie mensal dos medicos de uma pagina do ranking.

Mesmas regras do ranking: taxa = prescricoes / dias com prescricao no mes, no
escopo; mes com taxa elevada = taxa arredondada a 6 casas acima do P95 nacional
do mes.
"""

import threading
from collections import OrderedDict
from datetime import date
from typing import Callable, Optional

import polars as pl
from fastapi import HTTPException

from data_cache import (
    get_cache_generation,
    get_dados_medico_df,
    scan_crm_medico_brasil_mes,
    scan_crm_medico_territorio_mes,
)
from ...schemas.analytics import (
    CrmPrescricoesMensalItemSchema,
    CrmPrescricoesMensalResponse,
    CrmPrescricoesSerieMensalResponse,
    CrmSerieMensalMedicoSchema,
    CrmSerieMensalMesSchema,
    CrmSerieMensalPontoSchema,
)
from . import crm_analysis as base
from . import crm_analysis_filtrado as filtrado

# Coluna escolhida + desempates fixos (para a paginacao ser estavel).
MENSAL_SORT_COLUMNS: dict[str, list[tuple[str, bool]]] = {
    "razao_p95": [("nu_prescricoes", True), ("id_medico", False), ("competencia", False)],
    "taxa_prescricoes_dia": [("nu_prescricoes", True), ("id_medico", False), ("competencia", False)],
    "nu_prescricoes": [("qtd_dias_com_prescricao", True), ("id_medico", False), ("competencia", False)],
    "competencia": [("razao_p95", True), ("id_medico", False)],
}
SERIE_MENSAL_MAX_MEDICOS = 100

# Com busca ou filtro de farmacia, as linhas selecionadas (so id, mes,
# prescricoes e dias; ~25 bytes/linha) ficam em memoria: o arquivo mensal e
# lido uma vez por recorte e total, paginas e ordenacoes saem da memoria.
# Recortes maiores que o limite nao sao guardados (seguem lendo do disco).
_SELECIONADAS_MAX_LINHAS = 2_000_000
_SELECIONADAS_MAX_ITENS = 4
_SELECIONADAS_LOCK = threading.Lock()
_SELECIONADAS: "OrderedDict[tuple[object, ...], pl.DataFrame]" = OrderedDict()


def _linhas_selecionadas(chave: tuple[object, ...], ler: Callable[[], pl.DataFrame]) -> pl.DataFrame:
    """Cache LRU das linhas de uma busca/filtro, por geracao dos modulos."""
    geracao = get_cache_generation()
    chave = (geracao, *chave)
    with _SELECIONADAS_LOCK:
        for antiga in [k for k in _SELECIONADAS if k[0] != geracao]:
            del _SELECIONADAS[antiga]
        if chave in _SELECIONADAS:
            _SELECIONADAS.move_to_end(chave)
            return _SELECIONADAS[chave]
    linhas = ler()
    if linhas.height <= _SELECIONADAS_MAX_LINHAS:
        with _SELECIONADAS_LOCK:
            _SELECIONADAS[chave] = linhas
            _SELECIONADAS.move_to_end(chave)
            while len(_SELECIONADAS) > _SELECIONADAS_MAX_ITENS:
                _SELECIONADAS.popitem(last=False)
    return linhas


def _meses_brutos(
    inicio: date,
    fim: date,
    uf: Optional[str],
    regiao_id: Optional[int],
    id_ibge7: Optional[int],
) -> pl.LazyFrame:
    """Medico x mes do escopo no periodo (id, competencia, prescricoes, dias)."""
    nivel, identificador = base.escopo_territorial(uf, regiao_id, id_ibge7)
    nacional = nivel == "brasil"
    try:
        scan = scan_crm_medico_brasil_mes() if nacional else scan_crm_medico_territorio_mes()
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Cache de prescricoes por medico/mes indisponivel: {exc}",
        ) from exc
    base._require_columns(
        scan.limit(0).collect(),
        base.CRM_ANALYSIS_REQUIRED_MEDICO_MES_COLUMNS if nacional
        else base.CRM_ANALYSIS_REQUIRED_MEDICO_TERRITORIO_COLUMNS,
        "Prescricoes por medico/mes" if nacional else "Prescricoes por medico/territorio/mes",
    )
    if not nacional:
        scan = scan.filter((pl.col("nivel") == nivel) & (pl.col("id_geografico") == identificador))
    return (
        scan
        .filter(pl.col("competencia").is_between(base._competencia(inicio), base._competencia(fim)))
        .select([
            pl.col("id_medico").cast(pl.Utf8),
            pl.col("competencia").cast(pl.Int32),
            pl.col("nu_prescricoes_mes").alias("nu_prescricoes"),
            pl.col("qtd_dias_com_prescricao_mes").alias("qtd_dias_com_prescricao"),
        ])
        .filter((pl.col("nu_prescricoes") > 0) & (pl.col("qtd_dias_com_prescricao") > 0))
    )


def _com_taxa(linhas: pl.LazyFrame, limiares: pl.DataFrame) -> pl.LazyFrame:
    """Acrescenta P95 do mes, taxa diaria, razao e a marcacao de taxa elevada."""
    taxa = pl.col("nu_prescricoes").cast(pl.Float64) / pl.col("qtd_dias_com_prescricao").cast(pl.Float64)
    return (
        linhas
        .join(limiares.lazy(), on="competencia", how="inner")
        .with_columns(taxa.alias("taxa_prescricoes_dia"))
        .with_columns([
            (pl.col("taxa_prescricoes_dia") / pl.col("p95_taxa_dia")).alias("razao_p95"),
            (pl.col("taxa_prescricoes_dia").round(6) > pl.col("p95_taxa_dia")).alias("taxa_elevada"),
        ])
    )


def get_crm_prescricoes_mensal(
    *,
    page: int = 1,
    page_size: int = 15,
    medico_query: Optional[str] = None,
    sort_field: str = "razao_p95",
    sort_order: str = "desc",
    data_inicio: Optional[date] = None,
    data_fim: Optional[date] = None,
    uf: Optional[str] = None,
    regiao_id: Optional[int] = None,
    id_ibge7: Optional[int] = None,
    **filtros_farmacia_brutos,
) -> CrmPrescricoesMensalResponse:
    if page < 1:
        raise HTTPException(status_code=422, detail="page deve ser maior ou igual a 1.")
    if page_size < 1 or page_size > 100:
        raise HTTPException(status_code=422, detail="page_size deve estar entre 1 e 100.")
    if sort_field not in MENSAL_SORT_COLUMNS:
        raise HTTPException(status_code=422, detail="Coluna de ordenacao invalida para a visao mensal.")
    if sort_order not in {"asc", "desc"}:
        raise HTTPException(status_code=422, detail="sort_order deve ser asc ou desc.")

    inicio, fim = base._period_bounds(data_inicio, data_fim)
    filtro_ativo, filtros = base.montar_filtros_farmacia(**filtros_farmacia_brutos)
    nivel, identificador = base.escopo_territorial(uf, regiao_id, id_ibge7)
    escopo = base._scope_label(uf=uf, regiao_id=regiao_id, id_ibge7=id_ibge7)
    termo = base._normalizar_busca_medico(medico_query or "")

    ids: Optional[pl.Series] = None
    if filtro_ativo:
        ids = filtrado.ids_medicos_filtrados(
            filtros=filtros, inicio=inicio, fim=fim, uf=uf, regiao_id=regiao_id, id_ibge7=id_ibge7,
        )
    busca = base.ids_busca_medico(termo)
    if busca is not None:
        ids = busca if ids is None else ids.filter(ids.is_in(busca))

    limiares = base._limiares_do_periodo(inicio, fim)
    brutos = _meses_brutos(inicio, fim, uf, regiao_id, id_ibge7)
    chave_recorte = (
        "mensal", nivel, identificador, filtrado._chave_filtros(filtros) if filtro_ativo else None,
        termo, inicio, fim,
    )
    colunas = [sort_field, *(nome for nome, _ in MENSAL_SORT_COLUMNS[sort_field])]
    descendente = [sort_order == "desc", *(desc for _, desc in MENSAL_SORT_COLUMNS[sort_field])]

    def pagina_de(linhas: pl.LazyFrame, offset: int, limite: int) -> pl.DataFrame:
        return (
            linhas
            .top_k(limite, by=colunas, reverse=[not d for d in descendente])
            .collect(engine="streaming")
            .sort(colunas, descending=descendente)
            .slice(offset, page_size)
        )

    if ids is None:
        # Recorte inteiro (dezenas de milhoes de linhas no Brasil): le do disco
        # em streaming; total e paginas ja calculados ficam no cache.
        linhas = _com_taxa(brutos, limiares)
        total = filtrado._em_cache(
            (*chave_recorte, "total"),
            lambda: int(brutos.select(pl.len()).collect(engine="streaming").item()),
        )

        def obter_pagina(offset: int, limite: int) -> pl.DataFrame:
            return filtrado._em_cache(
                (*chave_recorte, "pagina", sort_field, sort_order, page, page_size),
                lambda: pagina_de(linhas, offset, limite),
            )
    else:
        selecionadas = _linhas_selecionadas(
            chave_recorte,
            lambda: brutos.filter(pl.col("id_medico").is_in(ids)).collect(engine="streaming"),
        )
        linhas = _com_taxa(selecionadas.lazy(), limiares)
        total = selecionadas.height

        def obter_pagina(offset: int, limite: int) -> pl.DataFrame:
            return pagina_de(linhas, offset, limite)

    def resposta(itens: list[CrmPrescricoesMensalItemSchema]) -> CrmPrescricoesMensalResponse:
        return CrmPrescricoesMensalResponse(
            escopo=escopo,
            periodo_inicio=inicio,
            periodo_fim=fim,
            qtd_linhas=total,
            page=page,
            page_size=page_size,
            linhas=itens,
            filtro_farmacias_ativo=filtro_ativo,
        )

    offset = (page - 1) * page_size
    if offset >= total:
        return resposta([])
    pagina = obter_pagina(offset, min(offset + page_size, total))
    try:
        medicos = get_dados_medico_df().lazy().filter(
            pl.col("id_medico").is_in(pagina.get_column("id_medico").unique())
        ).collect()
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Cache de dados dos medicos indisponivel: {exc}") from exc
    base._require_columns(medicos, base.CRM_ANALYSIS_REQUIRED_MEDICO_COLUMNS, "Dados dos medicos")
    # maintain_order="left": a pagina ja vem na ordem escolhida.
    # Marcador do left join: medico ausente do cadastro do CFM fica com null.
    pagina = pagina.join(
        medicos.select(["id_medico", "nu_crm", "sg_uf", "no_medico"])
        .unique(subset=["id_medico"], keep="first")
        .with_columns(pl.lit(True).alias("localizado_cfm")),
        on="id_medico", how="left", maintain_order="left",
    ).with_columns(pl.col("localizado_cfm").is_not_null())
    return resposta([
        CrmPrescricoesMensalItemSchema(
            id_medico=str(row["id_medico"]),
            nu_crm=int(row["nu_crm"]) if row["nu_crm"] is not None else None,
            sg_uf=str(row["sg_uf"]) if row["sg_uf"] is not None else None,
            no_medico=str(row["no_medico"]) if row["no_medico"] is not None else None,
            localizado_cfm=bool(row["localizado_cfm"]),
            competencia=int(row["competencia"]),
            nu_prescricoes=int(row["nu_prescricoes"]),
            qtd_dias_com_prescricao=int(row["qtd_dias_com_prescricao"]),
            taxa_prescricoes_dia=float(row["taxa_prescricoes_dia"]),
            p95_taxa_dia=float(row["p95_taxa_dia"]),
            razao_p95=float(row["razao_p95"]),
            taxa_elevada=bool(row["taxa_elevada"]),
        )
        for row in pagina.iter_rows(named=True)
    ])


def get_crm_prescricoes_serie_mensal(
    *,
    ids: str,
    data_inicio: Optional[date] = None,
    data_fim: Optional[date] = None,
    uf: Optional[str] = None,
    regiao_id: Optional[int] = None,
    id_ibge7: Optional[int] = None,
) -> CrmPrescricoesSerieMensalResponse:
    """Meses com prescricao de cada medico solicitado, no escopo e no periodo."""
    id_medicos = [item.strip() for item in ids.split(",") if item.strip()]
    if not id_medicos:
        raise HTTPException(status_code=422, detail="Informe ao menos um id_medico.")
    if len(id_medicos) > SERIE_MENSAL_MAX_MEDICOS:
        raise HTTPException(
            status_code=422,
            detail=f"No maximo {SERIE_MENSAL_MAX_MEDICOS} medicos por consulta da serie mensal.",
        )
    if len(set(id_medicos)) != len(id_medicos):
        raise HTTPException(status_code=422, detail="id_medico repetido na consulta da serie mensal.")

    inicio, fim = base._period_bounds(data_inicio, data_fim)
    limiares = base._limiares_do_periodo(inicio, fim).sort("competencia")
    dados = (
        _com_taxa(
            _meses_brutos(inicio, fim, uf, regiao_id, id_ibge7).filter(pl.col("id_medico").is_in(id_medicos)),
            limiares,
        )
        .collect()
        .sort(["id_medico", "competencia"])
    )
    if dados.select(pl.struct(["id_medico", "competencia"]).is_duplicated().any()).item():
        raise HTTPException(status_code=503, detail="Cache de prescricoes por medico/mes com meses duplicados.")
    por_medico: dict[str, list[CrmSerieMensalPontoSchema]] = {}
    for row in dados.iter_rows(named=True):
        por_medico.setdefault(str(row["id_medico"]), []).append(CrmSerieMensalPontoSchema(
            competencia=int(row["competencia"]),
            nu_prescricoes=int(row["nu_prescricoes"]),
            qtd_dias_com_prescricao=int(row["qtd_dias_com_prescricao"]),
            taxa_prescricoes_dia=float(row["taxa_prescricoes_dia"]),
            razao_p95=float(row["razao_p95"]),
            taxa_elevada=bool(row["taxa_elevada"]),
        ))
    ausentes = [id_medico for id_medico in id_medicos if id_medico not in por_medico]
    if ausentes:
        raise HTTPException(
            status_code=503,
            detail=(
                "CRMs do ranking sem meses com prescricao no escopo e periodo: "
                + ", ".join(ausentes[:5]) + (" ..." if len(ausentes) > 5 else "")
            ),
        )
    return CrmPrescricoesSerieMensalResponse(
        escopo=base._scope_label(uf=uf, regiao_id=regiao_id, id_ibge7=id_ibge7),
        periodo_inicio=inicio,
        periodo_fim=fim,
        meses=[
            CrmSerieMensalMesSchema(competencia=int(row["competencia"]), p95_taxa_dia=float(row["p95_taxa_dia"]))
            for row in limiares.iter_rows(named=True)
        ],
        medicos=[CrmSerieMensalMedicoSchema(id_medico=id_medico, meses=por_medico[id_medico]) for id_medico in id_medicos],
    )
