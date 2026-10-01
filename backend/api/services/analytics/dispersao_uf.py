from __future__ import annotations

from datetime import date
from typing import Optional

import polars as pl
from fastapi import HTTPException

from data_cache import scan_geografico_origem_uf

from .cache_geracao import CacheGeracao
from .geografico import UF_BRASILEIRAS, UF_VIZINHAS


_DISPERSAO_CACHE = CacheGeracao(max_itens=32, ttl_segundos=300)


def _normalize_date(value: date | None) -> str | None:
    return value.isoformat() if value else None


def _normalize_percentual(value: float | None) -> float:
    percentual = float(value if value is not None else 5.0)
    if percentual < 0 or percentual > 100:
        raise HTTPException(
            status_code=400,
            detail="Filtro dispersao_uf_sem_fronteira_limite deve estar entre 0 e 100.",
        )
    return round(percentual, 4)


def _vizinhanca_df() -> pl.DataFrame:
    rows: list[dict[str, object]] = []
    for uf_farmacia in UF_BRASILEIRAS:
        for uf_paciente in UF_BRASILEIRAS:
            rows.append({
                "uf_farmacia": uf_farmacia,
                "uf_paciente": uf_paciente,
                "is_fronteira_ou_mesma_uf": uf_paciente == uf_farmacia
                or uf_paciente in UF_VIZINHAS.get(uf_farmacia, set()),
            })
    return pl.DataFrame(rows)


def _build_dispersao_df(
    data_inicio: date | None,
    data_fim: date | None,
    percentual_minimo: float,
) -> pl.DataFrame:
    required = {
        "id_cnpj",
        "ano_base",
        "uf_farmacia",
        "uf_paciente",
        "valor_autorizado",
    }
    origem_scan = scan_geografico_origem_uf()
    schema_cols = set(origem_scan.collect_schema().names())
    missing = required - schema_cols
    if missing:
        raise HTTPException(
            status_code=500,
            detail=(
                "Contrato de cache invalido em geografico_origem_uf. "
                "Colunas ausentes: " + ", ".join(sorted(missing))
            ),
        )

    if data_inicio:
        origem_scan = origem_scan.filter(pl.col("ano_base") >= int(data_inicio.year))
    if data_fim:
        origem_scan = origem_scan.filter(pl.col("ano_base") <= int(data_fim.year))

    df_vizinhanca = _vizinhanca_df().lazy()
    return (
        origem_scan
        .select([
            pl.col("id_cnpj").cast(pl.Int64),
            pl.col("uf_farmacia").cast(pl.Utf8).str.strip_chars().str.to_uppercase(),
            pl.col("uf_paciente").cast(pl.Utf8).str.strip_chars().str.to_uppercase(),
            pl.col("valor_autorizado").cast(pl.Float64),
        ])
        .join(df_vizinhanca, on=["uf_farmacia", "uf_paciente"], how="inner")
        .group_by("id_cnpj")
        .agg([
            pl.col("valor_autorizado").sum().alias("_valor_total"),
            pl.col("valor_autorizado")
            .filter(~pl.col("is_fronteira_ou_mesma_uf"))
            .sum()
            .alias("valor_dispersao_uf_sem_fronteira"),
        ])
        .with_columns(
            pl.when(pl.col("_valor_total") > 0)
            .then(pl.col("valor_dispersao_uf_sem_fronteira") / pl.col("_valor_total") * 100)
            .otherwise(0.0)
            .alias("pct_dispersao_uf_sem_fronteira")
        )
        .filter(pl.col("pct_dispersao_uf_sem_fronteira") >= percentual_minimo)
        .select([
            pl.col("id_cnpj").cast(pl.Int64),
            pl.col("pct_dispersao_uf_sem_fronteira").cast(pl.Float64),
            pl.col("valor_dispersao_uf_sem_fronteira").cast(pl.Float64),
        ])
        .collect()
    )


def get_dispersao_uf_sem_fronteira_id_cnpjs_df(
    data_inicio: date | None = None,
    data_fim: date | None = None,
    percentual_minimo: Optional[float] = None,
) -> pl.DataFrame:
    limite = _normalize_percentual(percentual_minimo)
    return _DISPERSAO_CACHE.obter(
        (_normalize_date(data_inicio), _normalize_date(data_fim), limite),
        lambda: _build_dispersao_df(data_inicio, data_fim, limite),
    )
