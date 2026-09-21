"""Dados agregados para a análise geográfica de prescrições por médico."""

from datetime import date, timedelta
from typing import Optional

import polars as pl
from fastapi import HTTPException

from data_cache import (
    get_localidades_df,
    scan_crm_prescricoes_gerencial,
    scan_crm_prescricoes_medico_municipio_mes,
    scan_dados_medico,
)
from ...schemas.analytics import (
    CrmPrescricoesAnaliseResponse,
    CrmPrescricoesMapaItemSchema,
    CrmPrescricoesRankingItemSchema,
)
MIN_DATA = date(2015, 7, 1)
MAX_DATA = date(2024, 12, 31)
CRM_PRESCRICOES_ANOMALIA_LIMITE = 22.0
CRM_ANALYSIS_REQUIRED_MANAGER_COLUMNS = {
    "nivel",
    "id_geografico",
    "competencia",
    "nu_prescricoes_total",
    "qtd_crms_ativos",
    "qtd_crms_anomalos",
    "percentual_crms_anomalos",
    "media_prescricoes_dia",
}
CRM_ANALYSIS_REQUIRED_LOCALIDADES_COLUMNS = {
    "id_ibge7",
    "sg_uf",
    "id_regiao_saude",
    "no_municipio",
}
CRM_ANALYSIS_REQUIRED_MEDICO_MUNICIPIO_COLUMNS = {
    "id_medico",
    "competencia",
    "id_ibge7",
    "nu_prescricoes_mes",
}
CRM_ANALYSIS_REQUIRED_MEDICO_COLUMNS = {
    "id_medico",
    "nu_crm",
    "sg_uf",
    "no_medico",
}


def _require_columns(df: pl.DataFrame, required: set[str], source: str) -> None:
    missing = sorted(required.difference(df.columns))
    if missing:
        raise HTTPException(
            status_code=503,
            detail=f"{source} sem colunas obrigatorias: {', '.join(missing)}.",
        )


def _period_bounds(data_inicio: Optional[date], data_fim: Optional[date]) -> tuple[date, date]:
    inicio = data_inicio if data_inicio and data_inicio >= MIN_DATA else MIN_DATA
    fim = data_fim or MAX_DATA
    if inicio > fim:
        raise HTTPException(status_code=422, detail="Período inválido: data_inicio posterior à data_fim.")
    proximo_mes = (
        date(fim.year + 1, 1, 1)
        if fim.month == 12
        else date(fim.year, fim.month + 1, 1)
    )
    ultimo_dia_mes = proximo_mes - timedelta(days=1)
    if inicio.day != 1 or fim != ultimo_dia_mes:
        raise HTTPException(
            status_code=422,
            detail="A análise de prescrições CRM exige meses completos.",
        )
    return inicio, fim


def _competencia(value: date) -> int:
    return value.year * 100 + value.month


def _dias_do_mes_expr() -> pl.Expr:
    ano = pl.col("competencia") // 100
    mes = pl.col("competencia") % 100
    prox_ano = pl.when(mes == 12).then(ano + 1).otherwise(ano)
    prox_mes = pl.when(mes == 12).then(pl.lit(1)).otherwise(mes + 1)
    return (pl.date(prox_ano, prox_mes, pl.lit(1)) - pl.duration(days=1)).dt.day()


def _filtro_ativo(value: object, *, neutral: set[object] | None = None) -> bool:
    if value is None:
        return False
    if isinstance(value, str) and not value.strip():
        return False
    return value not in (neutral or set())


def _pode_usar_cache_gerencial(
    *,
    perc_min: Optional[float],
    perc_max: Optional[float],
    val_min: Optional[float],
    situacao_rf: Optional[str],
    conexao_ms: Optional[str],
    porte_empresa: Optional[str],
    grande_rede: Optional[str],
    cnpj_raiz: Optional[str],
    unidade_pf: Optional[str],
    razao_social: Optional[str],
    estabelecimento: Optional[str],
    par_teia: Optional[str],
    socio_beneficio: Optional[str],
    socio_esocial: Optional[str],
    cnae_incompativel: bool,
    socio_idade_atipica: bool,
    socio_falecido: bool,
    volume_atipico: bool,
    dispersao_uf_sem_fronteira: bool,
) -> bool:
    """Indica se o agregado gerencial preserva a semantica dos filtros recebidos."""
    return not any([
        perc_min is not None and float(perc_min) != 0,
        perc_max is not None and float(perc_max) != 100,
        val_min is not None and float(val_min) > 0,
        _filtro_ativo(situacao_rf, neutral={"Todos"}),
        _filtro_ativo(conexao_ms, neutral={"Todos"}),
        _filtro_ativo(porte_empresa, neutral={"Todos"}),
        _filtro_ativo(grande_rede, neutral={"Todos"}),
        _filtro_ativo(cnpj_raiz),
        _filtro_ativo(unidade_pf, neutral={"Todos"}),
        _filtro_ativo(razao_social),
        _filtro_ativo(estabelecimento),
        _filtro_ativo(par_teia),
        _filtro_ativo(socio_beneficio),
        _filtro_ativo(socio_esocial),
        cnae_incompativel,
        socio_idade_atipica,
        socio_falecido,
        volume_atipico,
        dispersao_uf_sem_fronteira,
    ])


def _perfil_filtrado(
    *,
    inicio: date,
    fim: date,
    perc_min: Optional[float],
    perc_max: Optional[float],
    val_min: Optional[float],
    uf: Optional[str],
    regiao_id: Optional[int],
    id_ibge7: Optional[int],
    situacao_rf: Optional[str],
    conexao_ms: Optional[str],
    porte_empresa: Optional[str],
    grande_rede: Optional[str],
    cnpj_raiz: Optional[str],
    unidade_pf: Optional[str],
    razao_social: Optional[str],
    estabelecimento: Optional[str],
    par_teia: Optional[str],
    socio_beneficio: Optional[str],
    socio_esocial: Optional[str],
    cnae_incompativel: bool,
    socio_idade_atipica: bool,
    socio_falecido: bool,
    volume_atipico: bool,
    volume_atipico_limite: Optional[float],
    dispersao_uf_sem_fronteira: bool,
    dispersao_uf_sem_fronteira_limite: Optional[float],
) -> pl.DataFrame:
    perfil_df = get_df_perfil_estabelecimento()
    _require_columns(perfil_df, CRM_ANALYSIS_REQUIRED_PROFILE_COLUMNS, "Perfil de estabelecimentos")

    mask = pl.lit(True)
    if uf and uf != "Todos":
        mask = mask & (pl.col("uf") == uf)
    if regiao_id is not None:
        mask = mask & (pl.col("id_regiao_saude") == str(regiao_id))
    if id_ibge7 is not None:
        mask = mask & (pl.col("id_ibge7") == id_ibge7)
    if situacao_rf and situacao_rf != "Todos":
        mask = mask & (pl.col("situacao_rf") == situacao_rf)
    if conexao_ms and conexao_ms != "Todos":
        mask = mask & (pl.col("is_conexao_ativa") == (conexao_ms == "Ativa"))
    if porte_empresa and porte_empresa != "Todos":
        mask = mask & (pl.col("porte_empresa") == porte_empresa)
    if grande_rede and grande_rede != "Todos":
        mask = mask & (pl.col("is_grande_rede") == (grande_rede == "Sim"))
    if unidade_pf and unidade_pf != "Todos":
        mask = mask & (pl.col("unidade_pf") == unidade_pf)
    if cnpj_raiz:
        if len(cnpj_raiz) == 14:
            mask = mask & (pl.col("cnpj") == cnpj_raiz)
        else:
            mask = mask & (pl.col("cnpj").str.slice(0, 8) == cnpj_raiz[:8])

    perfil = apply_token_search(
        perfil_df.filter(mask),
        estabelecimento or razao_social,
        ("cnpj", "razao_social", "nome_fantasia"),
    )
    perfil = build_perfil_filtrado(
        perfil,
        par_teia=par_teia,
        socio_beneficio=socio_beneficio,
        socio_esocial=socio_esocial,
        socio_falecido=socio_falecido,
        cnae_incompativel=cnae_incompativel,
        socio_idade_atipica=socio_idade_atipica,
        data_referencia=fim,
        volume_atipico=volume_atipico,
        volume_atipico_inicio=inicio,
        volume_atipico_fim=fim,
        volume_atipico_limite=volume_atipico_limite,
    )

    if dispersao_uf_sem_fronteira:
        ids_dispersao = get_dispersao_uf_sem_fronteira_id_cnpjs_df(
            inicio,
            fim,
            dispersao_uf_sem_fronteira_limite,
        ).select(pl.col("id_cnpj").cast(pl.Int64))
        perfil = perfil.join(ids_dispersao, on="id_cnpj", how="semi")

    mov_df = get_df()
    _require_columns(mov_df, CRM_ANALYSIS_REQUIRED_MOV_COLUMNS, "Movimentação")
    mov_periodo = (
        mov_df
        .filter(pl.col("periodo").is_between(inicio, fim))
        .join(perfil.select("id_cnpj"), on="id_cnpj", how="semi")
    )
    cnpj_agg = mov_periodo.group_by("id_cnpj").agg([
        pl.sum("total_vendas").alias("total_vendas"),
        pl.sum("total_sem_comprovacao").alias("total_sem_comprovacao"),
    ]).with_columns(
        (
            pl.col("total_sem_comprovacao")
            / pl.when(pl.col("total_vendas") > 0).then(pl.col("total_vendas")).otherwise(None)
            * 100
        ).fill_null(0).alias("percentual_sem_comprovacao")
    )
    p_min = float(perc_min) if perc_min is not None else 0.0
    p_max = float(perc_max) if perc_max is not None else 100.0
    cnpj_ok = cnpj_agg.filter(
        (pl.col("percentual_sem_comprovacao") >= p_min)
        & (pl.col("percentual_sem_comprovacao") <= p_max)
    )
    if val_min is not None and val_min > 0:
        cnpj_ok = cnpj_ok.filter(pl.col("total_sem_comprovacao") >= float(val_min))
    return perfil.join(cnpj_ok.select("id_cnpj"), on="id_cnpj", how="inner")


def _map_items_from_summary(summary: pl.DataFrame, map_level: str) -> list[CrmPrescricoesMapaItemSchema]:
    """Converte o resumo mensal/gerencial no contrato consumido pelo mapa."""
    if summary.is_empty():
        return []

    items = []
    for row in summary.iter_rows(named=True):
        percentual = row.get("percentual_crms_anomalos")
        media = row.get("media_prescricoes_dia")
        if map_level == "uf":
            uf = str(row["uf"])
            items.append(
                CrmPrescricoesMapaItemSchema(
                    nivel="uf",
                    identificador=uf,
                    nome=uf,
                    uf=uf,
                    nu_prescricoes_total=int(row["nu_prescricoes_total"]),
                    qtd_crms_ativos=int(row["qtd_crms_ativos"]),
                    qtd_crms_anomalos=int(row["qtd_crms_anomalos"]),
                    percentual_crms_anomalos=float(percentual) if percentual is not None else None,
                    media_prescricoes_dia=float(media) if media is not None else None,
                )
            )
        else:
            items.append(
                CrmPrescricoesMapaItemSchema(
                    nivel="municipio",
                    identificador=str(row["id_ibge7"]),
                    nome=str(row["no_municipio"]),
                    uf=str(row["uf"]),
                    id_ibge7=int(row["id_ibge7"]),
                    id_regiao_saude=str(row["id_regiao_saude"]),
                    nu_prescricoes_total=int(row["nu_prescricoes_total"]),
                    qtd_crms_ativos=int(row["qtd_crms_ativos"]),
                    qtd_crms_anomalos=int(row["qtd_crms_anomalos"]),
                    percentual_crms_anomalos=float(percentual) if percentual is not None else None,
                    media_prescricoes_dia=float(media) if media is not None else None,
                )
            )
    return items


def _build_manager_map(
    *,
    map_level: str,
    inicio: date,
    fim: date,
    uf: Optional[str],
    regiao_id: Optional[int],
    id_ibge7: Optional[int],
) -> list[CrmPrescricoesMapaItemSchema]:
    """Agrega a tabela mensal gerencial para o período exibido no mapa."""
    manager = scan_crm_prescricoes_gerencial()
    manager_columns = set(manager.collect_schema().names())
    missing = sorted(CRM_ANALYSIS_REQUIRED_MANAGER_COLUMNS.difference(manager_columns))
    if missing:
        raise HTTPException(
            status_code=503,
            detail="Cache gerencial de prescricoes sem colunas obrigatorias: " + ", ".join(missing) + ".",
        )

    manager = (
        manager
        .filter(pl.col("competencia").is_between(_competencia(inicio), _competencia(fim)))
        .with_columns([
            pl.col("id_geografico").cast(pl.Utf8),
            pl.col("competencia").cast(pl.Int32),
            pl.col("nu_prescricoes_total").cast(pl.Int64),
            pl.col("qtd_crms_ativos").cast(pl.Int64),
            pl.col("qtd_crms_anomalos").cast(pl.Int64),
        ])
        .with_columns([
            _dias_do_mes_expr().cast(pl.Int64).alias("dias_mes"),
        ])
    )

    if map_level == "uf":
        if uf and uf != "Todos":
            manager = manager.filter(pl.col("id_geografico") == uf)
        summary = (
            manager
            .filter(pl.col("nivel") == "uf")
            .with_columns(pl.col("id_geografico").alias("uf"))
            .group_by("uf")
            .agg([
                pl.sum("nu_prescricoes_total").cast(pl.Int64).alias("nu_prescricoes_total"),
                pl.sum("qtd_crms_ativos").cast(pl.Int64).alias("qtd_crms_ativos"),
                pl.sum("qtd_crms_anomalos").cast(pl.Int64).alias("qtd_crms_anomalos"),
                (pl.col("qtd_crms_ativos") * pl.col("dias_mes"))
                .cast(pl.Int64)
                .sum()
                .alias("crm_dias"),
            ])
            .with_columns([
                pl.when(pl.col("qtd_crms_ativos") > 0)
                .then(pl.col("qtd_crms_anomalos") / pl.col("qtd_crms_ativos") * 100)
                .otherwise(None)
                .alias("percentual_crms_anomalos"),
                pl.when(pl.col("crm_dias") > 0)
                .then(pl.col("nu_prescricoes_total") / pl.col("crm_dias"))
                .otherwise(None)
                .alias("media_prescricoes_dia"),
            ])
            .sort("percentual_crms_anomalos", descending=True, nulls_last=True)
            .collect()
        )
        return _map_items_from_summary(summary, map_level)

    localidades = get_localidades_df()
    _require_columns(localidades, CRM_ANALYSIS_REQUIRED_LOCALIDADES_COLUMNS, "Localidades")
    geo = (
        localidades
        .select(["id_ibge7", "sg_uf", "id_regiao_saude", "no_municipio"])
        .with_columns([
            pl.col("id_ibge7").cast(pl.Int64),
            pl.col("sg_uf").cast(pl.Utf8).alias("uf"),
            pl.col("id_regiao_saude").cast(pl.Utf8),
            pl.col("no_municipio").cast(pl.Utf8),
        ])
        .select(["id_ibge7", "uf", "id_regiao_saude", "no_municipio"])
    )
    if geo.filter(pl.col("id_ibge7").is_null()).height:
        raise HTTPException(
            status_code=503,
            detail="Cache de localidades possui id_ibge7 nulo para a analise de CRMs.",
        )
    duplicate_geo = geo.group_by("id_ibge7").len().filter(pl.col("len") > 1)
    if duplicate_geo.height:
        raise HTTPException(
            status_code=503,
            detail="Cache de localidades possui mais de uma linha para o mesmo id_ibge7.",
        )
    scoped = (
        manager
        .filter(pl.col("nivel") == "municipio")
        .with_columns(pl.col("id_geografico").cast(pl.Int64).alias("id_ibge7"))
        .join(geo.lazy(), on="id_ibge7", how="inner")
    )
    if uf and uf != "Todos":
        scoped = scoped.filter(pl.col("uf") == uf)
    if regiao_id is not None:
        scoped = scoped.filter(pl.col("id_regiao_saude") == str(regiao_id))
    if id_ibge7 is not None:
        scoped = scoped.filter(pl.col("id_ibge7") == id_ibge7)

    summary = (
        scoped
        .group_by(["id_ibge7", "uf", "id_regiao_saude", "no_municipio"])
        .agg([
            pl.sum("nu_prescricoes_total").cast(pl.Int64).alias("nu_prescricoes_total"),
            pl.sum("qtd_crms_ativos").cast(pl.Int64).alias("qtd_crms_ativos"),
            pl.sum("qtd_crms_anomalos").cast(pl.Int64).alias("qtd_crms_anomalos"),
            (pl.col("qtd_crms_ativos") * pl.col("dias_mes"))
            .cast(pl.Int64)
            .sum()
            .alias("crm_dias"),
        ])
        .with_columns([
            pl.when(pl.col("qtd_crms_ativos") > 0)
            .then(pl.col("qtd_crms_anomalos") / pl.col("qtd_crms_ativos") * 100)
            .otherwise(None)
            .alias("percentual_crms_anomalos"),
            pl.when(pl.col("crm_dias") > 0)
            .then(pl.col("nu_prescricoes_total") / pl.col("crm_dias"))
            .otherwise(None)
            .alias("media_prescricoes_dia"),
        ])
        .sort("percentual_crms_anomalos", descending=True, nulls_last=True)
        .collect()
    )
    return _map_items_from_summary(summary, map_level)


def _build_response(
    *,
    map_level: str,
    escopo: str,
    inicio: date,
    fim: date,
    monthly: pl.DataFrame | pl.LazyFrame,
    page: int = 1,
    page_size: int = 25,
    uf: Optional[str] = None,
    regiao_id: Optional[int] = None,
    id_ibge7: Optional[int] = None,
    manager_map: Optional[list[CrmPrescricoesMapaItemSchema]] = None,
) -> CrmPrescricoesAnaliseResponse:
    if page < 1:
        raise HTTPException(status_code=422, detail="page deve ser maior ou igual a 1.")
    if page_size < 1 or page_size > 100:
        raise HTTPException(status_code=422, detail="page_size deve estar entre 1 e 100.")

    monthly_lf = monthly if isinstance(monthly, pl.LazyFrame) else monthly.lazy()
    _require_columns(
        monthly_lf.limit(0).collect(),
        CRM_ANALYSIS_REQUIRED_MEDICO_MUNICIPIO_COLUMNS,
        "Prescricoes por medico/municipio/mes",
    )

    localidades = get_localidades_df()
    _require_columns(localidades, CRM_ANALYSIS_REQUIRED_LOCALIDADES_COLUMNS, "Localidades")
    geo = (
        localidades
        .select(["id_ibge7", "sg_uf", "id_regiao_saude", "no_municipio"])
        .with_columns([
            pl.col("id_ibge7").cast(pl.Int64),
            pl.col("sg_uf").cast(pl.Utf8).alias("uf"),
            pl.col("id_regiao_saude").cast(pl.Utf8),
            pl.col("no_municipio").cast(pl.Utf8),
        ])
        .select(["id_ibge7", "uf", "id_regiao_saude", "no_municipio"])
    )
    if geo.filter(pl.col("id_ibge7").is_null()).height:
        raise HTTPException(
            status_code=503,
            detail="Cache de localidades possui id_ibge7 nulo para o ranking de CRMs.",
        )
    duplicate_geo = geo.group_by("id_ibge7").len().filter(pl.col("len") > 1)
    if duplicate_geo.height:
        raise HTTPException(
            status_code=503,
            detail="Cache de localidades possui mais de uma linha para o mesmo id_ibge7.",
        )

    scoped_monthly = (
        monthly_lf
        .filter(pl.col("competencia").is_between(_competencia(inicio), _competencia(fim)))
        .with_columns([
            pl.col("id_medico").cast(pl.Utf8),
            pl.col("id_ibge7").cast(pl.Int64),
            pl.col("nu_prescricoes_mes").cast(pl.Int64),
        ])
        .join(geo.lazy(), on="id_ibge7", how="inner")
    )
    if uf and uf != "Todos":
        scoped_monthly = scoped_monthly.filter(pl.col("uf") == uf)
    if regiao_id is not None:
        scoped_monthly = scoped_monthly.filter(pl.col("id_regiao_saude") == str(regiao_id))
    if id_ibge7 is not None:
        scoped_monthly = scoped_monthly.filter(pl.col("id_ibge7") == int(id_ibge7))

    doctor_month = (
        scoped_monthly
        .group_by(["id_medico", "competencia"])
        .agg(pl.sum("nu_prescricoes_mes").cast(pl.Int64).alias("nu_prescricoes_mes"))
        .filter(pl.col("nu_prescricoes_mes") > 0)
        .with_columns([
            _dias_do_mes_expr().cast(pl.Int64).alias("dias_mes"),
            (
                pl.col("nu_prescricoes_mes").cast(pl.Float64)
                / _dias_do_mes_expr().cast(pl.Float64)
            ).alias("taxa_mes_dia"),
        ])
    )
    dias_intervalo = (fim - inicio).days + 1
    ranking_all = (
        doctor_month
        .group_by("id_medico")
        .agg([
            pl.sum("nu_prescricoes_mes").cast(pl.Int64).alias("nu_prescricoes"),
            pl.len().cast(pl.Int64).alias("qtd_meses_ativos"),
            pl.when(pl.col("taxa_mes_dia") > CRM_PRESCRICOES_ANOMALIA_LIMITE)
            .then(1)
            .otherwise(0)
            .sum()
            .cast(pl.Int64)
            .alias("qtd_meses_anomalos"),
        ])
        .with_columns([
            pl.lit(dias_intervalo).cast(pl.Int64).alias("dias_calendario"),
            (
                pl.col("nu_prescricoes").cast(pl.Float64)
                / pl.lit(dias_intervalo).cast(pl.Float64)
            ).alias("taxa_prescricoes_dia"),
            pl.when(pl.col("qtd_meses_ativos") > 0)
            .then(pl.col("qtd_meses_anomalos") / pl.col("qtd_meses_ativos") * 100)
            .otherwise(None)
            .alias("percentual_meses_anomalos"),
        ])
        .sort(["taxa_prescricoes_dia", "nu_prescricoes"], descending=[True, True])
        .collect()
    )
    if ranking_all.is_empty():
        return CrmPrescricoesAnaliseResponse(
            map_level=map_level,
            escopo=escopo,
            periodo_inicio=inicio,
            periodo_fim=fim,
            qtd_medicos=0,
            ranking_page=page,
            ranking_page_size=page_size,
            mapa=manager_map or [],
            ranking=[],
        )
    ranking_offset = (page - 1) * page_size
    ranking_scope = (
        ranking_all.slice(ranking_offset, page_size)
        .with_row_index("rank")
        .with_columns((pl.col("rank") + ranking_offset + 1).cast(pl.Int64))
    )
    mapa = manager_map or []

    medico_ids = ranking_scope.select("id_medico")
    try:
        medico_df = scan_dados_medico().filter(
            pl.col("id_medico").is_in(medico_ids.get_column("id_medico"))
        ).collect()
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Cache de dados dos médicos indisponível: {exc}") from exc
    _require_columns(medico_df, CRM_ANALYSIS_REQUIRED_MEDICO_COLUMNS, "Dados dos médicos")
    medico_df = medico_df.unique(subset=["id_medico"], keep="first")
    ranking_scope = ranking_scope.join(medico_df, on="id_medico", how="left")
    ranking = [
        CrmPrescricoesRankingItemSchema(
            rank=int(row["rank"]),
            id_medico=str(row["id_medico"]),
            nu_crm=int(row["nu_crm"]) if row["nu_crm"] is not None else None,
            sg_uf=str(row["sg_uf"]) if row["sg_uf"] is not None else None,
            no_medico=str(row["no_medico"]) if row["no_medico"] is not None else None,
            taxa_prescricoes_dia=float(row["taxa_prescricoes_dia"]),
            nu_prescricoes=int(row["nu_prescricoes"]),
            dias_calendario=int(row["dias_calendario"]),
            qtd_meses_ativos=int(row["qtd_meses_ativos"]),
            qtd_meses_anomalos=int(row["qtd_meses_anomalos"]),
            percentual_meses_anomalos=(
                float(row["percentual_meses_anomalos"])
                if row["percentual_meses_anomalos"] is not None
                else None
            ),
        )
        for row in ranking_scope.iter_rows(named=True)
    ]
    return CrmPrescricoesAnaliseResponse(
        map_level=map_level,
        escopo=escopo,
        periodo_inicio=inicio,
        periodo_fim=fim,
        qtd_medicos=ranking_all.height,
        ranking_page=page,
        ranking_page_size=page_size,
        mapa=mapa,
        ranking=ranking,
    )


def get_crm_prescricoes_analise(
    *,
    map_level: str = "uf",
    page: int = 1,
    page_size: int = 25,
    include_map: bool = True,
    data_inicio: Optional[date] = None,
    data_fim: Optional[date] = None,
    perc_min: Optional[float] = None,
    perc_max: Optional[float] = None,
    val_min: Optional[float] = None,
    uf: Optional[str] = None,
    regiao_id: Optional[int] = None,
    id_ibge7: Optional[int] = None,
    situacao_rf: Optional[str] = None,
    conexao_ms: Optional[str] = None,
    porte_empresa: Optional[str] = None,
    grande_rede: Optional[str] = None,
    cnpj_raiz: Optional[str] = None,
    unidade_pf: Optional[str] = None,
    razao_social: Optional[str] = None,
    estabelecimento: Optional[str] = None,
    par_teia: Optional[str] = None,
    socio_beneficio: Optional[str] = None,
    socio_esocial: Optional[str] = None,
    cnae_incompativel: bool = False,
    socio_idade_atipica: bool = False,
    socio_falecido: bool = False,
    volume_atipico: bool = False,
    volume_atipico_limite: Optional[float] = None,
    dispersao_uf_sem_fronteira: bool = False,
    dispersao_uf_sem_fronteira_limite: Optional[float] = None,
) -> CrmPrescricoesAnaliseResponse:
    if page < 1:
        raise HTTPException(status_code=422, detail="page deve ser maior ou igual a 1.")
    if page_size < 1 or page_size > 100:
        raise HTTPException(status_code=422, detail="page_size deve estar entre 1 e 100.")

    if map_level not in {"uf", "municipio", "regiao"}:
        raise HTTPException(status_code=422, detail="map_level deve ser uf, municipio ou regiao.")
    if map_level == "municipio" and (not uf or uf == "Todos"):
        raise HTTPException(status_code=422, detail="O mapa municipal exige uma UF selecionada.")
    if map_level == "regiao" and regiao_id is None:
        raise HTTPException(status_code=422, detail="O mapa da região exige regiao_id.")

    inicio, fim = _period_bounds(data_inicio, data_fim)
    if not _pode_usar_cache_gerencial(
        perc_min=perc_min,
        perc_max=perc_max,
        val_min=val_min,
        situacao_rf=situacao_rf,
        conexao_ms=conexao_ms,
        porte_empresa=porte_empresa,
        grande_rede=grande_rede,
        cnpj_raiz=cnpj_raiz,
        unidade_pf=unidade_pf,
        razao_social=razao_social,
        estabelecimento=estabelecimento,
        par_teia=par_teia,
        socio_beneficio=socio_beneficio,
        socio_esocial=socio_esocial,
        cnae_incompativel=cnae_incompativel,
        socio_idade_atipica=socio_idade_atipica,
        socio_falecido=socio_falecido,
        volume_atipico=volume_atipico,
        dispersao_uf_sem_fronteira=dispersao_uf_sem_fronteira,
    ):
        raise HTTPException(
            status_code=422,
            detail=(
                "A analise gerencial de medicos aceita apenas periodo e filtros geograficos "
                "nesta etapa. Filtros de estabelecimento e indicadores serao disponibilizados "
                "no detalhamento do CRM."
            ),
        )

    try:
        manager_map = (
            _build_manager_map(
                map_level=map_level,
                inicio=inicio,
                fim=fim,
                uf=uf,
                regiao_id=regiao_id,
                id_ibge7=id_ibge7,
            )
            if include_map
            else None
        )
        monthly = scan_crm_prescricoes_medico_municipio_mes().filter(
            pl.col("competencia").is_between(_competencia(inicio), _competencia(fim))
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=(
                "Cache de prescricoes por medico/municipio/mes indisponivel: "
                f"{exc}"
            ),
        ) from exc

    escopo = "Brasil" if map_level == "uf" and (not uf or uf == "Todos") else f"UF {uf}"
    if map_level == "regiao":
        escopo = f"Regiao de Saude {regiao_id}"
    return _build_response(
        map_level=map_level,
        escopo=escopo,
        inicio=inicio,
        fim=fim,
        monthly=monthly,
        page=page,
        page_size=page_size,
        uf=uf,
        regiao_id=regiao_id,
        id_ibge7=id_ibge7,
        manager_map=manager_map,
    )

    use_manager = _pode_usar_cache_gerencial(
        perc_min=perc_min,
        perc_max=perc_max,
        val_min=val_min,
        situacao_rf=situacao_rf,
        conexao_ms=conexao_ms,
        porte_empresa=porte_empresa,
        grande_rede=grande_rede,
        cnpj_raiz=cnpj_raiz,
        unidade_pf=unidade_pf,
        razao_social=razao_social,
        estabelecimento=estabelecimento,
        par_teia=par_teia,
        socio_beneficio=socio_beneficio,
        socio_esocial=socio_esocial,
        cnae_incompativel=cnae_incompativel,
        socio_idade_atipica=socio_idade_atipica,
        socio_falecido=socio_falecido,
        volume_atipico=volume_atipico,
        dispersao_uf_sem_fronteira=dispersao_uf_sem_fronteira,
    )

    manager_map = None
    if use_manager:
        try:
            manager_map = _build_manager_map(
                map_level=map_level,
                inicio=inicio,
                fim=fim,
                uf=uf,
                regiao_id=regiao_id,
                id_ibge7=id_ibge7,
            )

            perfil_df = get_df_perfil_estabelecimento()
            _require_columns(perfil_df, CRM_ANALYSIS_REQUIRED_PROFILE_COLUMNS, "Perfil de estabelecimentos")
            perfil_mask = pl.lit(True)
            if uf and uf != "Todos":
                perfil_mask = perfil_mask & (pl.col("uf") == uf)
            if regiao_id is not None:
                perfil_mask = perfil_mask & (pl.col("id_regiao_saude") == str(regiao_id))
            if id_ibge7 is not None:
                perfil_mask = perfil_mask & (pl.col("id_ibge7") == id_ibge7)
            perfil = perfil_df.filter(perfil_mask)

            monthly = (
                scan_crm_prescricoes_medico_municipio_mes()
                .filter(pl.col("competencia").is_between(_competencia(inicio), _competencia(fim)))
                .join(
                    perfil.select([
                        "id_cnpj",
                        "uf",
                        "id_regiao_saude",
                        "id_ibge7",
                        "no_municipio",
                    ]).unique("id_cnpj").lazy(),
                    on="id_cnpj",
                    how="inner",
                )
                .select([
                    "id_cnpj",
                    "id_medico",
                    "competencia",
                    "nu_prescricoes_mes",
                    "uf",
                    "id_regiao_saude",
                    "id_ibge7",
                    "no_municipio",
                ])
            )
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(
                status_code=503,
                detail=f"Cache gerencial de prescrições indisponível: {exc}",
            ) from exc
    else:
        perfil = _perfil_filtrado(
            inicio=inicio,
            fim=fim,
            perc_min=perc_min,
            perc_max=perc_max,
            val_min=val_min,
            uf=uf,
            regiao_id=regiao_id,
            id_ibge7=id_ibge7,
            situacao_rf=situacao_rf,
            conexao_ms=conexao_ms,
            porte_empresa=porte_empresa,
            grande_rede=grande_rede,
            cnpj_raiz=cnpj_raiz,
            unidade_pf=unidade_pf,
            razao_social=razao_social,
            estabelecimento=estabelecimento,
            par_teia=par_teia,
            socio_beneficio=socio_beneficio,
            socio_esocial=socio_esocial,
            cnae_incompativel=cnae_incompativel,
            socio_idade_atipica=socio_idade_atipica,
            socio_falecido=socio_falecido,
            volume_atipico=volume_atipico,
            volume_atipico_limite=volume_atipico_limite,
            dispersao_uf_sem_fronteira=dispersao_uf_sem_fronteira,
            dispersao_uf_sem_fronteira_limite=dispersao_uf_sem_fronteira_limite,
        )

        try:
            monthly = (
                scan_crm_prescricoes_medico_municipio_mes()
                .filter(
                    pl.col("competencia").is_between(_competencia(inicio), _competencia(fim))
                )
                .join(
                    perfil.select([
                        "id_cnpj",
                        "uf",
                        "id_regiao_saude",
                        "id_ibge7",
                        "no_municipio",
                    ]).unique("id_cnpj").lazy(),
                    on="id_cnpj",
                    how="inner",
                )
                .select([
                    "id_cnpj",
                    "id_medico",
                    "competencia",
                    "nu_prescricoes_mes",
                    "uf",
                    "id_regiao_saude",
                    "id_ibge7",
                    "no_municipio",
                ])
            )
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(
                status_code=503,
                detail=f"Cache de prescrições por estabelecimento/mês indisponível: {exc}",
            ) from exc

    escopo = "Brasil" if map_level == "uf" and (not uf or uf == "Todos") else f"UF {uf}"
    if map_level == "regiao":
        escopo = f"Região de Saúde {regiao_id}"
    return _build_response(
        map_level=map_level,
        escopo=escopo,
        inicio=inicio,
        fim=fim,
        monthly=monthly,
        manager_map=manager_map,
    )
