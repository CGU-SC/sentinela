from typing import Collection, List, Optional
from datetime import date
import calendar
import polars as pl
from sqlalchemy.orm import Session
from sqlalchemy import text
from fastapi import HTTPException
import os
import zlib
import json
import copy
from decimal import Decimal, ROUND_HALF_UP
from data_cache import get_df, get_rede_df, get_df_bench_crm_regiao, get_df_bench_crm_br, get_df_perfil_estabelecimento, get_cache_dir
from .alertas_alvos import build_perfil_filtrado
from .dispersao_uf import get_dispersao_uf_sem_fronteira_id_cnpjs_df
from .matriz_risco_dinamica import build_dynamic_matriz_risco

from ...utils.text_search import apply_token_search
from ...schemas.analytics import (
    AnalyticsKPISchema,
    ProducaoSemestralPointSchema,
    ProducaoSemestralResponse,
    ResultadoSentinelaUFSchema,
    AnalyticsResponse,
    ResultadoSentinelaMunicipioSchema,
    ResultadoSentinelaCnpjSchema,
    RedeEstabelecimentoSchema,
    FatorRiscoResponseSchema,
    FatorRiscoBucketSchema,
    EvolucaoSemestreSchema,
    EvolucaoFinanceiraResponse,
    IndicadorDataSchema,
    IndicadoresResponse,
    FalecidoTransactionSchema,
    FalecidosRankingSchema,
    FalecidosSummarySchema,
    FalecidosResponse,
    TimelineEventSchema,
    MultiCnpjTimelineResponse,
    RegionalMunicipioSchema,
    RegionalFarmaciaSchema,
    RegionalResponse,
    RegionalAnimationQuarterSchema,
    RegionalAnimationResponse,
    PrescritoresResponse,
    DadosFarmaciaSchema,
    MovimentacaoRowSchema,
    MovimentacaoSummarySchema,
    MovimentacaoResponse,
    IndicadorKpiSummarySchema,
    IndicadorCnpjRowSchema,
    IndicadorMunicipioRowSchema,
    IndicadorAnaliseResponse,
    MesMensalGtinItem,
    EvolucaoMensalGtinResponse,
    GtinDetalhamentoMensalResponse,
    GtinDetalhamentoMensalSummary,
    GtinDetalhamentoMensalItem,
)

DASHBOARD_SECOES = frozenset({"kpis", "ufs", "municipios", "cnpjs"})


def validar_secoes_dashboard(secoes: Collection[str], cnpjs: Optional[List[str]]) -> frozenset[str]:
    """Valida as secoes pedidas ao resumo do dashboard.

    Args:
        secoes: secoes solicitadas (kpis, ufs, municipios, cnpjs).
        cnpjs: filtro explicito de CNPJs da requisicao.

    Returns:
        Conjunto imutavel das secoes validas.

    Raises:
        HTTPException 422: sem secoes, secao desconhecida ou `cnpjs` sem o
            filtro de CNPJs (evita devolver a base inteira de estabelecimentos).
    """
    pedidas = frozenset(secoes or ())
    if not pedidas:
        raise HTTPException(status_code=422, detail="Informe ao menos uma secao: kpis, ufs, municipios ou cnpjs.")
    desconhecidas = pedidas - DASHBOARD_SECOES
    if desconhecidas:
        raise HTTPException(status_code=422, detail=f"Secoes invalidas no resumo: {', '.join(sorted(desconhecidas))}.")
    if "cnpjs" in pedidas and not cnpjs:
        raise HTTPException(status_code=422, detail="A secao cnpjs exige o filtro cnpjs com os estabelecimentos desejados.")
    return pedidas


def get_dashboard_data(db: Session, data_inicio=None, data_fim=None, perc_min=None, perc_max=None, val_min=None, uf=None, regiao_saude=None, municipio=None, situacao_rf=None, conexao_ms=None, porte_empresa=None, grande_rede=None, cnpj_raiz=None, unidade_pf=None, cnpjs: Optional[List[str]] = None, regiao_id: Optional[int] = None, id_ibge7: Optional[int] = None, volume_atipico: bool = False, volume_atipico_limite: Optional[float] = None, dispersao_uf_sem_fronteira: bool = False, dispersao_uf_sem_fronteira_limite: Optional[float] = None, par_teia: Optional[str] = None, socio_beneficio: Optional[str] = None, socio_esocial: Optional[str] = None, cnae_incompativel: bool = False, socio_idade_atipica: bool = False, socio_falecido: bool = False, estabelecimento: Optional[str] = None, *, secoes: Collection[str]) -> AnalyticsResponse:
    """
    Versão Unificada (Motor Polars): Calcula KPIs e análise por UF em tempo real.
    Garante consistência total entre as telas e alta performance via processamento em memória.

    Só calcula as seções pedidas em `secoes` (kpis, ufs, municipios, cnpjs); as
    demais voltam como None. A seção cnpjs exige o filtro `cnpjs`.
    """
    secoes = validar_secoes_dashboard(secoes, cnpjs)
    print(f'DEBUG get_dashboard_data - cnae_incompativel: {cnae_incompativel}')
    try:
        def human_format(num):
            if num is None: return "0"
            num = float(num)
            if num >= 1_000_000_000:
                return f"R$ {num/1_000_000_000:.2f} Bi".replace('.', ',')
            if num >= 1_000_000:
                return f"R$ {num/1_000_000:.2f} Mi".replace('.', ',')
            if num >= 1_000:
                return f"R$ {num/1_000:.0f} K"
            return f"R$ {num:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')

        def human_format_qty(num):
            if num is None: return "0"
            num = float(num)
            if num >= 1_000_000_000:
                return f"{num/1_000_000_000:.2f} Bi".replace('.', ',')
            if num >= 1_000_000:
                return f"{num/1_000_000:.2f} Mi".replace('.', ',')
            if num >= 1_000:
                return f"{num/1_000:.0f} K"
            return f"{num:.0f}"

        def build_kpis(cnpjs, total_vendas, val_sem_comp, perc_sem_comp, total_meds, qtd_municipios):
            return [
                AnalyticsKPISchema(id='total_municipios', label='Municípios', value=f"{(qtd_municipios or 0):,}".replace(',', '.'), color='#06b6d4', icon='pi pi-map-marker'),
                AnalyticsKPISchema(id='total_cnpjs', label='CNPJs', value=f"{(cnpjs or 0):,}".replace(',', '.'), color='#3b82f6', icon='pi pi-id-card'),
                AnalyticsKPISchema(id='valor_vendas', label='Valor Total de Vendas', value=human_format(total_vendas), color='#10b981', icon='pi pi-dollar'),
                AnalyticsKPISchema(id='perc_valor', label='% sem comprovação', value=f"{(perc_sem_comp or 0):.2f}%".replace('.', ','), color='#f59e0b', icon='pi pi-percentage'),
                AnalyticsKPISchema(id='valor_nao_comp', label='Valor sem Comprovação', value=human_format(val_sem_comp), color='#ef4444', icon='pi pi-dollar'),
                AnalyticsKPISchema(id='total_meds', label='Qtde de Medicamentos', value=human_format_qty(total_meds), color='#8b5cf6', icon='pi pi-box'),
            ]

        # 1. Parâmetros e DataFrame Base
        MIN_DATA = date(2015, 7, 1)
        MAX_DATA = date(2024, 12, 31)
        p_min = perc_min if perc_min is not None else 0.0
        p_max = perc_max if perc_max is not None else 100.0
        v_min = float(val_min) if val_min is not None and val_min > 0 else None
        
        inicio = (data_inicio if data_inicio and data_inicio >= MIN_DATA else MIN_DATA) if data_inicio else MIN_DATA
        fim = data_fim if data_fim else MAX_DATA

        df = get_df()
        perfil_df = get_df_perfil_estabelecimento()

        # 2. Filtros cadastrais/geograficos no perfil; periodo na tabela fato.
        mov_mask = pl.col("periodo").is_between(inicio, fim)
        perfil_mask = pl.lit(True)
        if uf and uf != 'Todos':                      perfil_mask = perfil_mask & (pl.col("uf") == uf)
        if regiao_id is not None:                     perfil_mask = perfil_mask & (pl.col("id_regiao_saude") == str(regiao_id))
        if id_ibge7 is not None:                      perfil_mask = perfil_mask & (pl.col("id_ibge7") == id_ibge7)
        if situacao_rf and situacao_rf != 'Todos':    perfil_mask = perfil_mask & (pl.col("situacao_rf") == situacao_rf)
        if conexao_ms and conexao_ms != 'Todos':
            perfil_mask = perfil_mask & (pl.col("is_conexao_ativa") == (conexao_ms == 'Ativa'))
        if porte_empresa and porte_empresa != 'Todos': perfil_mask = perfil_mask & (pl.col("porte_empresa") == porte_empresa)
        if grande_rede and grande_rede != 'Todos':
            perfil_mask = perfil_mask & (pl.col("is_grande_rede") == (grande_rede == 'Sim'))
        if unidade_pf and unidade_pf != 'Todos':
            perfil_mask = perfil_mask & (pl.col("unidade_pf") == unidade_pf)
        if cnpj_raiz:
            if len(cnpj_raiz) == 14:
                perfil_mask = perfil_mask & (pl.col("cnpj") == cnpj_raiz)
            else:
                perfil_mask = perfil_mask & (pl.col("cnpj").str.slice(0, 8) == cnpj_raiz)
        if cnpjs:
            perfil_mask = perfil_mask & (pl.col("cnpj").is_in(cnpjs))

        estabelecimento_query = estabelecimento
        perfil_filtrado = apply_token_search(
            perfil_df.filter(perfil_mask),
            estabelecimento_query,
            ("cnpj", "razao_social", "nome_fantasia"),
        )
        perfil_filtrado = build_perfil_filtrado(
            perfil_filtrado,
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
        period_df = (
            df.filter(mov_mask)
            .join(perfil_filtrado.select("id_cnpj"), on="id_cnpj", how="semi")
        )
        if dispersao_uf_sem_fronteira:
            id_cnpjs_dispersao_df = get_dispersao_uf_sem_fronteira_id_cnpjs_df(
                inicio,
                fim,
                dispersao_uf_sem_fronteira_limite,
            )
            period_df = period_df.join(id_cnpjs_dispersao_df.select("id_cnpj"), on="id_cnpj", how="semi")

        # 3. Agregação Granular (CNPJ) para aplicação de filtros de Risco (% e Valor)
        cnpj_agg = period_df.group_by("id_cnpj").agg([
            pl.sum("total_vendas").alias("tv"),
            pl.sum("total_sem_comprovacao").alias("tsc"),
            pl.col("total_qnt_caixas_vendidas").cast(pl.Int64).sum().alias("tqv"),
            pl.col("total_qnt_caixas_sem_comprovacao").cast(pl.Int64).sum().alias("tqsc"),
        ]).with_columns([
            (pl.col("tsc") / pl.when(pl.col("tv") > 0).then(pl.col("tv")).otherwise(None) * 100).fill_null(0).alias("pct")
        ])

        # Aplicação dos filtros de corte
        cnpj_ok = cnpj_agg.filter((pl.col("pct") >= p_min) & (pl.col("pct") <= p_max))
        if v_min is not None:
            cnpj_ok = cnpj_ok.filter(pl.col("tsc") >= v_min)

        perfil_ok = perfil_filtrado.join(cnpj_ok.select("id_cnpj"), on="id_cnpj", how="inner")

        # 4. Cálculo dos KPIs Globais
        kpis = None
        if "kpis" in secoes:
            tv  = float(cnpj_ok["tv"].sum() or 0)
            tsc = float(cnpj_ok["tsc"].sum() or 0)
            tqv = float(cnpj_ok["tqv"].sum() or 0)
            pct = (tsc / tv * 100) if tv else 0.0
            qtd_mun = int(perfil_ok.select(pl.n_unique("no_municipio")).item() or 0)
            kpis = build_kpis(cnpj_ok.height, tv, tsc, pct, tqv, qtd_mun)

        period_enriched = (
            period_df.join(perfil_ok, on="id_cnpj", how="inner")
            if secoes & {"ufs", "municipios", "cnpjs"} else None
        )

        # 5. Detalhamento por UF (Breakdown)
        resultado_sentinela_uf = None
        if "ufs" in secoes:
            uf_df = (
                period_enriched
                .group_by("uf")
                .agg([
                    pl.n_unique("id_cnpj").alias("cnpjs"),
                    pl.sum("total_vendas").alias("totalMov"),
                    pl.sum("total_sem_comprovacao").alias("valSemComp"),
                    pl.col("total_qnt_caixas_vendidas").cast(pl.Int64).sum().alias("totalQtde"),
                    pl.col("total_qnt_caixas_sem_comprovacao").cast(pl.Int64).sum().alias("qtdeSemComp"),
                ])
                .with_columns([
                    (pl.col("valSemComp") / pl.when(pl.col("totalMov") > 0).then(pl.col("totalMov")).otherwise(None) * 100).alias("percValSemComp"),
                    (pl.col("qtdeSemComp") / pl.when(pl.col("totalQtde") > 0).then(pl.col("totalQtde")).otherwise(None) * 100).alias("percQtdeSemComp"),
                ])
                .sort("percValSemComp", descending=True, nulls_last=True)
            )

            resultado_sentinela_uf = [
                ResultadoSentinelaUFSchema(**r)
                for r in uf_df.iter_rows(named=True)
            ]

        # 6. Agregação por Município
        resultado_municipios = None
        if "municipios" in secoes:
            muni_df = (
                period_enriched
                .group_by(["uf", "no_municipio", "id_ibge7"])
                .agg([
                    pl.n_unique("id_cnpj").alias("cnpjs"),
                    pl.sum("total_vendas").alias("totalMov"),
                    pl.sum("total_sem_comprovacao").alias("valSemComp"),
                    pl.col("total_qnt_caixas_vendidas").cast(pl.Int64).sum().alias("totalQtde"),
                    pl.col("total_qnt_caixas_sem_comprovacao").cast(pl.Int64).sum().alias("qtdeSemComp"),
                ])
                .with_columns([
                    (pl.col("valSemComp") / pl.when(pl.col("totalMov") > 0).then(pl.col("totalMov")).otherwise(None) * 100).alias("percValSemComp"),
                    (pl.col("qtdeSemComp") / pl.when(pl.col("totalQtde") > 0).then(pl.col("totalQtde")).otherwise(None) * 100).alias("percQtdeSemComp"),
                ])
                # id_ibge7 desempata: group_by nao garante ordem e a tabela de
                # /municipios mantem a ordem recebida entre valores iguais.
                .sort(["percValSemComp", "id_ibge7"], descending=[True, False], nulls_last=True)
            )

            resultado_municipios = [
                ResultadoSentinelaMunicipioSchema(municipio=r["no_municipio"], **r)
                for r in muni_df.iter_rows(named=True)
            ]

        # 7. Detalhamento por CNPJ (somente com filtro explícito de CNPJs)
        resultado_cnpjs = None
        if "cnpjs" in secoes:
            cnpj_df = (
                period_enriched
                .group_by("id_cnpj")
                .agg([
                    pl.col("cnpj").first().alias("cnpj"),
                    pl.col("no_municipio").first().alias("municipio"),
                    pl.col("id_ibge7").first().alias("id_ibge7"),
                    pl.col("uf").first().alias("uf"),
                    pl.col("razao_social").first().alias("razao_social"),
                    pl.sum("total_vendas").alias("totalMov"),
                    pl.sum("total_sem_comprovacao").alias("valSemComp"),
                    pl.col("total_qnt_caixas_vendidas").cast(pl.Int64).sum().alias("totalQtde"),
                    pl.col("total_qnt_caixas_sem_comprovacao").cast(pl.Int64).sum().alias("qtdeSemComp"),
                    pl.col("is_grande_rede").first().alias("is_grande_rede"),
                    pl.col("qtd_estabelecimentos_rede").first().alias("qtd_estabelecimentos_rede"),
                    pl.col("situacao_rf").first().alias("situacao_rf"),
                    pl.col("porte_empresa").first().alias("porte_empresa"),
                    pl.col("is_conexao_ativa").first().alias("is_conexao_ativa"),
                    pl.col("is_matriz").first().fill_null(False).alias("is_matriz"),
                ])
                .with_columns([
                    (pl.col("valSemComp") / pl.when(pl.col("totalMov") > 0).then(pl.col("totalMov")).otherwise(None) * 100).alias("percValSemComp"),
                    (pl.col("qtdeSemComp") / pl.when(pl.col("totalQtde") > 0).then(pl.col("totalQtde")).otherwise(None) * 100).alias("percQtdeSemComp"),
                    (pl.col("municipio") + " / " + pl.col("uf")).alias("municipio_uf"),
                ])
                .sort("percValSemComp", descending=True, nulls_last=True)
            )
            risco_cols = [
                "id_cnpj",
                "score_risco_final",
                "classificacao_risco",
                "rank_nacional",
                "total_nacional",
                "rank_uf",
                "total_uf",
                "rank_regiao_saude",
                "total_regiao_saude",
                "rank_municipio",
                "total_municipio",
            ]
            risco_df = build_dynamic_matriz_risco(
                data_inicio=inicio,
                data_fim=fim,
            ).select(risco_cols)
            cnpj_df = cnpj_df.join(risco_df, on="id_cnpj", how="left")

            resultado_cnpjs = [
                ResultadoSentinelaCnpjSchema(**r)
                for r in cnpj_df.iter_rows(named=True)
            ]

        return AnalyticsResponse(
            kpis=kpis, 
            resultado_sentinela_uf=resultado_sentinela_uf,
            resultado_municipios=resultado_municipios,
            resultado_cnpjs=resultado_cnpjs
        )

    except HTTPException:
        raise
    except Exception as e:
        import traceback
        print(f"❌ ERRO NO MOTOR POLARS (Analytics): {e}")
        print(traceback.format_exc())
        raise HTTPException(status_code=503, detail="Resumo analitico indisponivel: matriz dinamica de risco ou cache base invalido.") from e


def get_producao_semestral_data(db: Session, data_inicio=None, data_fim=None, perc_min=None, perc_max=None, val_min=None, uf=None, situacao_rf=None, conexao_ms=None, porte_empresa=None, grande_rede=None, cnpj_raiz=None, unidade_pf=None, cnpjs: Optional[List[str]] = None, regiao_id: Optional[int] = None, id_ibge7: Optional[int] = None, volume_atipico: bool = False, volume_atipico_limite: Optional[float] = None, dispersao_uf_sem_fronteira: bool = False, dispersao_uf_sem_fronteira_limite: Optional[float] = None, par_teia: Optional[str] = None, socio_beneficio: Optional[str] = None, socio_esocial: Optional[str] = None, cnae_incompativel: bool = False, socio_idade_atipica: bool = False, socio_falecido: bool = False, estabelecimento: Optional[str] = None) -> ProducaoSemestralResponse:
    """Retorna a producao acumulada por semestre para a Home, respeitando os filtros globais."""
    try:
        MIN_DATA = date(2015, 7, 1)
        MAX_DATA = date(2024, 12, 31)
        p_min = perc_min if perc_min is not None else 0.0
        p_max = perc_max if perc_max is not None else 100.0
        v_min = float(val_min) if val_min is not None and val_min > 0 else None

        inicio = (data_inicio if data_inicio and data_inicio >= MIN_DATA else MIN_DATA) if data_inicio else MIN_DATA
        fim = data_fim if data_fim else MAX_DATA

        df = get_df()
        perfil_df = get_df_perfil_estabelecimento()

        mov_mask = pl.col("periodo").is_between(inicio, fim)
        perfil_mask = pl.lit(True)
        if uf and uf != 'Todos':                       perfil_mask = perfil_mask & (pl.col("uf") == uf)
        if regiao_id is not None:                      perfil_mask = perfil_mask & (pl.col("id_regiao_saude") == str(regiao_id))
        if id_ibge7 is not None:                       perfil_mask = perfil_mask & (pl.col("id_ibge7") == id_ibge7)
        if situacao_rf and situacao_rf != 'Todos':     perfil_mask = perfil_mask & (pl.col("situacao_rf") == situacao_rf)
        if conexao_ms and conexao_ms != 'Todos':       perfil_mask = perfil_mask & (pl.col("is_conexao_ativa") == (conexao_ms == 'Ativa'))
        if porte_empresa and porte_empresa != 'Todos': perfil_mask = perfil_mask & (pl.col("porte_empresa") == porte_empresa)
        if grande_rede and grande_rede != 'Todos':     perfil_mask = perfil_mask & (pl.col("is_grande_rede") == (grande_rede == 'Sim'))
        if unidade_pf and unidade_pf != 'Todos':       perfil_mask = perfil_mask & (pl.col("unidade_pf") == unidade_pf)
        if cnpj_raiz:
            if len(cnpj_raiz) == 14:
                perfil_mask = perfil_mask & (pl.col("cnpj") == cnpj_raiz)
            else:
                perfil_mask = perfil_mask & (pl.col("cnpj").str.slice(0, 8) == cnpj_raiz)
        if cnpjs:
            perfil_mask = perfil_mask & (pl.col("cnpj").is_in(cnpjs))

        estabelecimento_query = estabelecimento
        perfil_filtrado = apply_token_search(
            perfil_df.filter(perfil_mask),
            estabelecimento_query,
            ("cnpj", "razao_social", "nome_fantasia"),
        )
        perfil_filtrado = build_perfil_filtrado(
            perfil_filtrado,
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

        period_df = (
            df.filter(mov_mask)
            .join(perfil_filtrado.select("id_cnpj"), on="id_cnpj", how="semi")
        )
        if dispersao_uf_sem_fronteira:
            id_cnpjs_dispersao_df = get_dispersao_uf_sem_fronteira_id_cnpjs_df(
                inicio,
                fim,
                dispersao_uf_sem_fronteira_limite,
            )
            period_df = period_df.join(id_cnpjs_dispersao_df.select("id_cnpj"), on="id_cnpj", how="semi")

        if period_df.is_empty():
            return ProducaoSemestralResponse(pontos=[])

        cnpj_agg = (
            period_df
            .group_by("id_cnpj")
            .agg([
                pl.sum("total_vendas").alias("tv"),
                pl.sum("total_sem_comprovacao").alias("tsc"),
            ])
            .with_columns([
                (pl.col("tsc") / pl.when(pl.col("tv") > 0).then(pl.col("tv")).otherwise(None) * 100)
                .fill_null(0)
                .alias("pct")
            ])
        )
        cnpj_ok = cnpj_agg.filter((pl.col("pct") >= p_min) & (pl.col("pct") <= p_max))
        if v_min is not None:
            cnpj_ok = cnpj_ok.filter(pl.col("tsc") >= v_min)

        filtered_period = period_df.join(cnpj_ok.select("id_cnpj"), on="id_cnpj", how="inner")
        if filtered_period.is_empty():
            return ProducaoSemestralResponse(pontos=[])

        semestral_df = (
            filtered_period
            .with_columns([
                pl.col("periodo").dt.year().alias("ano"),
                pl.when(pl.col("periodo").dt.month() <= 6).then(1).otherwise(2).alias("semestre_num"),
            ])
            .with_columns([
                (pl.col("ano") * 100 + pl.col("semestre_num")).cast(pl.Int32).alias("chave_semestre"),
            ])
            .group_by(["ano", "semestre_num", "chave_semestre"])
            .agg([
                pl.sum("total_vendas").alias("valor_producao"),
                pl.sum("total_sem_comprovacao").alias("valor_sem_comprovacao"),
                pl.n_unique("id_cnpj").alias("cnpjs"),
            ])
            .sort("chave_semestre")
            .with_columns([
                pl.format("{}-S{}", pl.col("ano"), pl.col("semestre_num")).alias("semestre"),
                (pl.col("valor_producao") - pl.col("valor_sem_comprovacao")).clip(0, None).alias("valor_regular"),
                (
                    pl.col("valor_sem_comprovacao")
                    / pl.when(pl.col("valor_producao") > 0).then(pl.col("valor_producao")).otherwise(None)
                    * 100
                ).fill_null(0).alias("pct_sem_comprovacao"),
            ])
            .select(["semestre", "chave_semestre", "valor_producao", "valor_regular", "valor_sem_comprovacao", "pct_sem_comprovacao", "cnpjs"])
        )

        return ProducaoSemestralResponse(
            pontos=[ProducaoSemestralPointSchema(**row) for row in semestral_df.iter_rows(named=True)]
        )

    except Exception as e:
        import traceback
        print(f"ERRO AO BUSCAR PRODUCAO SEMESTRAL: {e}")
        print(traceback.format_exc())
        return ProducaoSemestralResponse(pontos=[])


def get_rede_por_cnpj_raiz(cnpj_raiz: str) -> List[RedeEstabelecimentoSchema]:
    """Retorna todos os estabelecimentos de uma rede dado o CNPJ raiz (8 dígitos)."""
    try:
        df = get_rede_df()
        result = df.filter(pl.col("cnpj_raiz") == cnpj_raiz).sort("is_matriz", descending=True)
        return [RedeEstabelecimentoSchema(**r) for r in result.iter_rows(named=True)]
    except Exception as e:
        import traceback
        print(f"❌ ERRO AO BUSCAR REDE: {e}")
        print(traceback.format_exc())
        return []

