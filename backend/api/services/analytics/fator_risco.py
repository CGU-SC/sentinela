from datetime import date
from typing import Optional

import polars as pl
from fastapi import HTTPException
from sqlalchemy.orm import Session

from data_cache import get_df, get_df_perfil_estabelecimento

from ...schemas.analytics import FatorRiscoBucketSchema, FatorRiscoResponseSchema
from ...utils.text_search import apply_token_search
from .alertas_alvos import build_perfil_filtrado
from .dispersao_uf import get_dispersao_uf_sem_fronteira_id_cnpjs_df
from .volume_atipico import get_volume_atipico_id_cnpjs_df
from .filtros_farmacia import SEM_FILTRO_FARMACIA, FiltrosFarmacia


def get_fator_risco_data(
    db: Session,
    data_inicio=None,
    data_fim=None,
    uf=None,
    regiao_saude=None,
    municipio=None,
    regiao_id: Optional[int] = None,
    id_ibge7: Optional[int] = None,
    filtros: FiltrosFarmacia = SEM_FILTRO_FARMACIA,
) -> FatorRiscoResponseSchema:
    """
    Calcula as faixas de risco (buckets de 10%) via Polars.
    """
    try:
        MIN_DATA = date(2015, 7, 1)
        inicio = max(data_inicio, MIN_DATA) if data_inicio else MIN_DATA
        fim = data_fim if data_fim else date(2199, 12, 31)
        p_min = filtros.perc_min if filtros.perc_min is not None else 0.0
        p_max = filtros.perc_max if filtros.perc_max is not None else 100.0
        v_min = float(filtros.val_min) if filtros.val_min is not None and filtros.val_min > 0 else None

        df = get_df()
        perfil_df = get_df_perfil_estabelecimento()

        mov_mask = pl.col("periodo").is_between(inicio, fim)
        perfil_mask = pl.lit(True)
        if uf and uf != "Todos":
            perfil_mask = perfil_mask & (pl.col("uf") == uf)
        if regiao_id is not None:
            perfil_mask = perfil_mask & (pl.col("id_regiao_saude") == str(regiao_id))
        if id_ibge7 is not None:
            perfil_mask = perfil_mask & (pl.col("id_ibge7") == id_ibge7)
        if filtros.situacao_rf and filtros.situacao_rf != "Todos":
            perfil_mask = perfil_mask & (pl.col("situacao_rf") == filtros.situacao_rf)
        if filtros.conexao_ms and filtros.conexao_ms != "Todos":
            perfil_mask = perfil_mask & (pl.col("is_conexao_ativa") == (filtros.conexao_ms == "Ativa"))
        if filtros.porte_empresa and filtros.porte_empresa != "Todos":
            perfil_mask = perfil_mask & (pl.col("porte_empresa") == filtros.porte_empresa)
        if filtros.grande_rede and filtros.grande_rede != "Todos":
            perfil_mask = perfil_mask & (pl.col("is_grande_rede") == (filtros.grande_rede == "Sim"))
        if filtros.unidade_pf and filtros.unidade_pf != "Todos":
            perfil_mask = perfil_mask & (pl.col("unidade_pf") == filtros.unidade_pf)
        if filtros.cnpj_raiz:
            if len(filtros.cnpj_raiz) == 14:
                perfil_mask = perfil_mask & (pl.col("cnpj") == filtros.cnpj_raiz)
            else:
                perfil_mask = perfil_mask & (pl.col("cnpj").str.slice(0, 8) == filtros.cnpj_raiz)

        perfil_filtrado = apply_token_search(
            perfil_df.filter(perfil_mask),
            filtros.estabelecimento,
            ("cnpj", "razao_social", "nome_fantasia"),
        )
        perfil_filtrado = build_perfil_filtrado(
            perfil_filtrado,
            filtros=filtros,
            data_referencia=fim,
            periodo_inicio=inicio,
            volume_atipico_inicio=inicio,
            periodo_fim=fim,
            volume_atipico_fim=fim,
        )
        period_df = (
            df.filter(mov_mask)
            .join(perfil_filtrado.select("id_cnpj"), on="id_cnpj", how="semi")
        )
        if filtros.dispersao_uf_sem_fronteira:
            id_cnpjs_dispersao_df = get_dispersao_uf_sem_fronteira_id_cnpjs_df(
                inicio,
                fim,
                filtros.dispersao_uf_sem_fronteira_limite,
            )
            period_df = period_df.join(id_cnpjs_dispersao_df.select("id_cnpj"), on="id_cnpj", how="semi")

        cnpj_agg = (
            period_df
            .group_by("id_cnpj")
            .agg([
                pl.sum("total_vendas").alias("tv"),
                pl.sum("total_sem_comprovacao").alias("tsc"),
            ])
            .with_columns([
                (
                    pl.col("tsc") /
                    pl.when(pl.col("tv") > 0).then(pl.col("tv")).otherwise(None) *
                    100
                ).fill_null(0).alias("pct")
            ])
            .filter((pl.col("pct") >= p_min) & (pl.col("pct") <= p_max))
        )

        if v_min is not None:
            cnpj_agg = cnpj_agg.filter(pl.col("tsc") >= v_min)

        faixa_expr = (
            pl.when(pl.col("pct") <= 10).then(pl.lit("00% - 10%"))
            .when(pl.col("pct") <= 20).then(pl.lit("10% - 20%"))
            .when(pl.col("pct") <= 30).then(pl.lit("20% - 30%"))
            .when(pl.col("pct") <= 40).then(pl.lit("30% - 40%"))
            .when(pl.col("pct") <= 50).then(pl.lit("40% - 50%"))
            .when(pl.col("pct") <= 60).then(pl.lit("50% - 60%"))
            .when(pl.col("pct") <= 70).then(pl.lit("60% - 70%"))
            .when(pl.col("pct") <= 80).then(pl.lit("70% - 80%"))
            .when(pl.col("pct") <= 90).then(pl.lit("80% - 90%"))
            .otherwise(pl.lit("90% - 100%"))
        )
        ordem_expr = (
            pl.when(pl.col("pct") <= 10).then(1)
            .when(pl.col("pct") <= 20).then(2)
            .when(pl.col("pct") <= 30).then(3)
            .when(pl.col("pct") <= 40).then(4)
            .when(pl.col("pct") <= 50).then(5)
            .when(pl.col("pct") <= 60).then(6)
            .when(pl.col("pct") <= 70).then(7)
            .when(pl.col("pct") <= 80).then(8)
            .when(pl.col("pct") <= 90).then(9)
            .otherwise(10)
        )

        buckets_df = (
            cnpj_agg
            .with_columns([faixa_expr.alias("faixa"), ordem_expr.alias("ordem")])
            .group_by(["faixa", "ordem"])
            .agg([pl.len().alias("qtd"), pl.sum("tsc").alias("valor_raw")])
            .sort("ordem")
        )

        buckets = [
            FatorRiscoBucketSchema(
                faixa=r["faixa"],
                qtd=r["qtd"],
                valor=f"R$ {r['valor_raw']:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."),
                valor_raw=r["valor_raw"],
            )
            for r in buckets_df.iter_rows(named=True)
        ]

        return FatorRiscoResponseSchema(
            periodo_formatado=f"{inicio} a {fim}" if data_inicio and data_fim else "Acumulado Historico",
            buckets=buckets,
        )
    except HTTPException:
        raise
    except Exception:
        return FatorRiscoResponseSchema(periodo_formatado="Erro ao calcular", buckets=[])
