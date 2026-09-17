"""Dados agregados para a análise geográfica de prescrições por médico."""

from datetime import date
from typing import Optional

import polars as pl
from fastapi import HTTPException

from data_cache import (
    get_df,
    get_df_perfil_estabelecimento,
    scan_crm_prescricoes_gerencial_mes,
    scan_crm_prescricoes_estabelecimento_mes,
    scan_dados_medico,
)
from ...schemas.analytics import (
    CrmPrescricoesAnaliseResponse,
    CrmPrescricoesMapaItemSchema,
    CrmPrescricoesRankingItemSchema,
)
from ...utils.text_search import apply_token_search
from .alertas_alvos import build_perfil_filtrado
from .dispersao_uf import get_dispersao_uf_sem_fronteira_id_cnpjs_df


MIN_DATA = date(2015, 7, 1)
MAX_DATA = date(2024, 12, 31)
CRM_ANALYSIS_REQUIRED_PROFILE_COLUMNS = {
    "id_cnpj",
    "cnpj",
    "uf",
    "id_regiao_saude",
    "id_ibge7",
    "no_municipio",
    "situacao_rf",
    "is_conexao_ativa",
    "porte_empresa",
    "is_grande_rede",
    "unidade_pf",
}
CRM_ANALYSIS_REQUIRED_MOV_COLUMNS = {
    "id_cnpj",
    "periodo",
    "total_vendas",
    "total_sem_comprovacao",
    "total_qnt_caixas_vendidas",
}
CRM_ANALYSIS_REQUIRED_MONTHLY_COLUMNS = {
    "id_cnpj",
    "id_medico",
    "competencia",
    "nu_prescricoes_mes",
    "uf",
    "id_regiao_saude",
    "id_ibge7",
    "no_municipio",
}
CRM_ANALYSIS_REQUIRED_MANAGER_COLUMNS = {
    "id_medico",
    "competencia",
    "uf",
    "id_regiao_saude",
    "id_ibge7",
    "no_municipio",
    "nu_prescricoes_mes",
    "nu_estabelecimentos_mes",
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


def _build_response(
    *,
    map_level: str,
    escopo: str,
    inicio: date,
    fim: date,
    monthly: pl.DataFrame | pl.LazyFrame,
) -> CrmPrescricoesAnaliseResponse:
    monthly_lf = monthly if isinstance(monthly, pl.LazyFrame) else monthly.lazy()
    monthly_columns = set(monthly_lf.collect_schema().names())
    if "id_cnpj" in monthly_columns:
        _require_columns(
            monthly_lf.limit(0).collect(),
            CRM_ANALYSIS_REQUIRED_MONTHLY_COLUMNS,
            "Prescricoes mensais",
        )
    else:
        missing_manager = sorted(CRM_ANALYSIS_REQUIRED_MANAGER_COLUMNS.difference(monthly_columns))
        if missing_manager:
            raise HTTPException(
                status_code=503,
                detail=(
                    "Cache gerencial de prescricoes sem colunas obrigatorias: "
                    + ", ".join(missing_manager)
                    + "."
                ),
            )

    if map_level == "uf":
        location_keys = ["uf"]
    else:
        location_keys = ["uf", "id_regiao_saude", "id_ibge7", "no_municipio"]

    location_key_columns = location_keys + ["id_medico", "competencia"]
    if "id_cnpj" in monthly_columns:
        qtd_estab_expr = pl.n_unique("id_cnpj").alias("qtd_estabelecimentos_mes")
    else:
        qtd_estab_expr = pl.sum("nu_estabelecimentos_mes").alias("qtd_estabelecimentos_mes")

    doctor_month = (
        monthly_lf.group_by(location_key_columns)
        .agg([
            pl.sum("nu_prescricoes_mes").cast(pl.Int64).alias("nu_prescricoes_mes"),
            qtd_estab_expr,
        ])
        .filter(pl.col("nu_prescricoes_mes") > 0)
        .with_columns(_dias_do_mes_expr().cast(pl.Int64).alias("dias_mes"))
        .collect()
    )
    if doctor_month.is_empty():
        return CrmPrescricoesAnaliseResponse(
            map_level=map_level,
            escopo=escopo,
            periodo_inicio=inicio,
            periodo_fim=fim,
            qtd_medicos=0,
            mapa=[],
            ranking=[],
        )
    doctor_scope = (
        doctor_month.group_by(location_keys + ["id_medico"])
        .agg([
            pl.sum("nu_prescricoes_mes").alias("nu_prescricoes"),
            pl.sum("dias_mes").alias("dias_calendario"),
        ])
        .with_columns(
            (
                pl.col("nu_prescricoes").cast(pl.Float64)
                / pl.col("dias_calendario").cast(pl.Float64)
            ).alias("taxa_prescricoes_dia")
        )
    )

    if "id_cnpj" in monthly_columns:
        qtd_estab = (
            monthly_lf.group_by(location_keys + ["id_medico"])
            .agg(pl.n_unique("id_cnpj").alias("qtd_estabelecimentos"))
            .collect()
        )
    else:
        qtd_estab = (
            doctor_month
            .group_by(location_keys + ["id_medico", "competencia"])
            .agg(pl.sum("qtd_estabelecimentos_mes").alias("qtd_estabelecimentos_mes"))
            .group_by(location_keys + ["id_medico"])
            .agg(pl.max("qtd_estabelecimentos_mes").alias("qtd_estabelecimentos"))
        )
    doctor_scope = doctor_scope.join(qtd_estab, on=location_keys + ["id_medico"], how="left")

    map_summary = (
        doctor_scope.group_by(location_keys)
        .agg([
            pl.col("taxa_prescricoes_dia").quantile(0.95, interpolation="linear").alias("p95_prescricoes_dia"),
            pl.col("taxa_prescricoes_dia").median().alias("mediana_prescricoes_dia"),
            pl.col("taxa_prescricoes_dia").max().alias("maior_prescricoes_dia"),
            pl.n_unique("id_medico").alias("qtd_medicos"),
        ])
        .sort("p95_prescricoes_dia", descending=True)
    )

    if map_level == "uf":
        mapa = [
            CrmPrescricoesMapaItemSchema(
                nivel="uf",
                identificador=str(row["uf"]),
                nome=str(row["uf"]),
                uf=str(row["uf"]),
                p95_prescricoes_dia=float(row["p95_prescricoes_dia"]),
                mediana_prescricoes_dia=float(row["mediana_prescricoes_dia"]),
                maior_prescricoes_dia=float(row["maior_prescricoes_dia"]),
                qtd_medicos=int(row["qtd_medicos"]),
            )
            for row in map_summary.iter_rows(named=True)
        ]
    else:
        mapa = [
            CrmPrescricoesMapaItemSchema(
                nivel="municipio",
                identificador=str(row["id_ibge7"]),
                nome=str(row["no_municipio"]),
                uf=str(row["uf"]),
                id_ibge7=int(row["id_ibge7"]),
                id_regiao_saude=str(row["id_regiao_saude"]),
                p95_prescricoes_dia=float(row["p95_prescricoes_dia"]),
                mediana_prescricoes_dia=float(row["mediana_prescricoes_dia"]),
                maior_prescricoes_dia=float(row["maior_prescricoes_dia"]),
                qtd_medicos=int(row["qtd_medicos"]),
            )
            for row in map_summary.iter_rows(named=True)
        ]

    if "id_cnpj" in monthly_columns:
        ranking_scope = (
            monthly_lf.group_by(["id_medico", "competencia"])
            .agg(pl.sum("nu_prescricoes_mes").cast(pl.Int64).alias("nu_prescricoes_mes"))
            .filter(pl.col("nu_prescricoes_mes") > 0)
            .with_columns(_dias_do_mes_expr().cast(pl.Int64).alias("dias_mes"))
            .group_by("id_medico")
            .agg([
                pl.sum("nu_prescricoes_mes").alias("nu_prescricoes"),
                pl.sum("dias_mes").alias("dias_calendario"),
            ])
            .with_columns(
                (
                    pl.col("nu_prescricoes").cast(pl.Float64)
                    / pl.col("dias_calendario").cast(pl.Float64)
                ).alias("taxa_prescricoes_dia")
            )
            .sort(["taxa_prescricoes_dia", "nu_prescricoes"], descending=[True, True])
            .head(100)
            .with_row_index("rank")
            .with_columns((pl.col("rank") + 1).cast(pl.Int64))
            .collect()
        )
        ranking_qtd_estab = (
            monthly_lf
            .group_by("id_medico")
            .agg(pl.n_unique("id_cnpj").alias("qtd_estabelecimentos"))
            .collect()
        )
    else:
        ranking_scope = (
            doctor_month
            .group_by(["id_medico", "competencia"])
            .agg([
                pl.sum("nu_prescricoes_mes").cast(pl.Int64).alias("nu_prescricoes_mes"),
                pl.sum("qtd_estabelecimentos_mes").alias("qtd_estabelecimentos_mes"),
                pl.first("dias_mes").alias("dias_mes"),
            ])
            .filter(pl.col("nu_prescricoes_mes") > 0)
            .group_by("id_medico")
            .agg([
                pl.sum("nu_prescricoes_mes").alias("nu_prescricoes"),
                pl.sum("dias_mes").alias("dias_calendario"),
                pl.max("qtd_estabelecimentos_mes").alias("qtd_estabelecimentos"),
            ])
            .with_columns(
                (
                    pl.col("nu_prescricoes").cast(pl.Float64)
                    / pl.col("dias_calendario").cast(pl.Float64)
                ).alias("taxa_prescricoes_dia")
            )
            .sort(["taxa_prescricoes_dia", "nu_prescricoes"], descending=[True, True])
            .head(100)
            .with_row_index("rank")
            .with_columns((pl.col("rank") + 1).cast(pl.Int64))
        )
        ranking_qtd_estab = (
            ranking_scope.select(["id_medico", "qtd_estabelecimentos"])
        )
    if "id_cnpj" in monthly_columns:
        ranking_scope = ranking_scope.join(ranking_qtd_estab, on="id_medico", how="left")

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
            qtd_estabelecimentos=int(row["qtd_estabelecimentos"]),
        )
        for row in ranking_scope.iter_rows(named=True)
    ]
    return CrmPrescricoesAnaliseResponse(
        map_level=map_level,
        escopo=escopo,
        periodo_inicio=inicio,
        periodo_fim=fim,
        qtd_medicos=doctor_scope.select(pl.n_unique("id_medico")).item(),
        mapa=mapa,
        ranking=ranking,
    )


def get_crm_prescricoes_analise(
    *,
    map_level: str = "uf",
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
    if map_level not in {"uf", "municipio", "regiao"}:
        raise HTTPException(status_code=422, detail="map_level deve ser uf, municipio ou regiao.")
    if map_level == "municipio" and not uf:
        raise HTTPException(status_code=422, detail="O mapa municipal exige uma UF selecionada.")
    if map_level == "regiao" and regiao_id is None:
        raise HTTPException(status_code=422, detail="O mapa da região exige regiao_id.")

    inicio, fim = _period_bounds(data_inicio, data_fim)
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

    if use_manager:
        try:
            manager_filters = [
                pl.col("competencia").is_between(_competencia(inicio), _competencia(fim)),
            ]
            if uf and uf != "Todos":
                manager_filters.append(pl.col("uf") == uf)
            if regiao_id is not None:
                manager_filters.append(pl.col("id_regiao_saude") == str(regiao_id))
            if id_ibge7 is not None:
                manager_filters.append(pl.col("id_ibge7") == id_ibge7)

            monthly = (
                scan_crm_prescricoes_gerencial_mes()
                .filter(pl.all_horizontal(manager_filters))
                .select([
                    "id_medico",
                    "competencia",
                    "uf",
                    "id_regiao_saude",
                    "id_ibge7",
                    "no_municipio",
                    "nu_prescricoes_mes",
                    "nu_estabelecimentos_mes",
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
                scan_crm_prescricoes_estabelecimento_mes()
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

    escopo = "Brasil" if map_level == "uf" and not uf else f"UF {uf}"
    if map_level == "regiao":
        escopo = f"Região de Saúde {regiao_id}"
    return _build_response(
        map_level=map_level,
        escopo=escopo,
        inicio=inicio,
        fim=fim,
        monthly=monthly,
    )
