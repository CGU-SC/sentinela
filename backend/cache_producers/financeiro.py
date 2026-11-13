import os
import time

import pandas as pd
import polars as pl
from sqlalchemy import text

import cnpj_cache_versao
from cache_files import MOVIMENTACAO_MENSAL_GTIN_PARQUET
from cache_producers.types import CacheLoadResult


def _get_cnpj_cache_dir(cnpj: str) -> str:
    return cnpj_cache_versao.get_cnpj_cache_dir(cnpj)


def _cache_path(cnpj: str) -> str:
    return os.path.join(_get_cnpj_cache_dir(cnpj), MOVIMENTACAO_MENSAL_GTIN_PARQUET)


def _load_from_global(cnpj: str) -> tuple[pl.DataFrame, float] | None:
    from data_cache import get_df_perfil_estabelecimento, scan_movimentacao_mensal_gtin_global

    perfil = get_df_perfil_estabelecimento()
    row = (
        perfil
        .lazy()
        .filter(pl.col("cnpj").cast(pl.Utf8) == cnpj)
        .select("id_cnpj")
        .collect()
    )
    if row.height != 1:
        raise RuntimeError(f"Perfil estabelecimento sem id_cnpj unico para CNPJ {cnpj}.")

    id_cnpj = int(row.item(0, "id_cnpj"))
    t0 = time.perf_counter()
    df = (
        scan_movimentacao_mensal_gtin_global()
        .filter(pl.col("id_cnpj") == id_cnpj)
        .select([
            "codigo_barra",
            "periodo",
            "qnt_caixas_vendidas",
            "qnt_caixas_sem_comprovacao",
            "num_autorizacoes",
            "valor_vendas",
            "valor_sem_comprovacao",
        ])
        .collect()
    )
    read_time_ms = round((time.perf_counter() - t0) * 1000, 1)
    return df, read_time_ms


def load_or_sync_movimentacao_mensal_gtin(cnpj: str, engine=None) -> CacheLoadResult:
    parquet_path = _cache_path(cnpj)
    df: pl.DataFrame | None = None
    from_cache = False
    read_time_ms: float | None = None

    if os.path.exists(parquet_path):
        try:
            t0 = time.perf_counter()
            df = pl.read_parquet(parquet_path)
            read_time_ms = round((time.perf_counter() - t0) * 1000, 1)
            from_cache = True
        except Exception as exc:
            print(f"[ CACHE ] {cnpj} - GTIN - erro de leitura ({exc})")

    if df is not None:
        return CacheLoadResult(df=df, from_cache=from_cache, read_time_ms=read_time_ms)

    query_time_ms: float | None = None
    save_time_ms: float | None = None

    try:
        try:
            global_result = _load_from_global(cnpj)
        except FileNotFoundError as exc:
            global_error = str(exc)
            global_result = None

        if global_result is not None:
            df, read_time_ms = global_result
            t1 = time.perf_counter()
            df.write_parquet(parquet_path, compression="zstd")
            save_time_ms = round((time.perf_counter() - t1) * 1000, 1)
            print(f"GTIN {cnpj}: global {read_time_ms}ms | parquet {save_time_ms}ms")
            return CacheLoadResult(
                df=df,
                from_cache=False,
                read_time_ms=read_time_ms,
                save_time_ms=save_time_ms,
            )

        if engine is None:
            from database import engine as engine

        with engine.connect() as conn:
            t0 = time.perf_counter()
            pdf = pd.read_sql(
                text("""
                    SELECT gtin.codigo_barra, m.periodo,
                           m.qnt_caixas_vendidas, m.qnt_caixas_sem_comprovacao,
                           m.num_autorizacoes,
                           CAST(m.valor_vendas AS FLOAT) AS valor_vendas,
                           CAST(m.valor_sem_comprovacao AS FLOAT) AS valor_sem_comprovacao
                    FROM [temp_CGUSC].[fp].[movimentacao_mensal_gtin] m
                    INNER JOIN [temp_CGUSC].[fp].[processamento] p ON p.id = m.id_processamento
                    INNER JOIN [temp_CGUSC].[fp].[medicamentos_patologia_chave] gtin ON gtin.id = m.id_gtin
                    WHERE p.cnpj = :cnpj AND p.situacao = 1
                """),
                conn,
                params={"cnpj": cnpj},
            )
            query_time_ms = round((time.perf_counter() - t0) * 1000, 1)

        df = pl.from_pandas(pdf).with_columns([
            pl.col("codigo_barra").cast(pl.String),
            pl.col("periodo").cast(pl.Date),
            pl.col("qnt_caixas_vendidas").cast(pl.Int64),
            pl.col("qnt_caixas_sem_comprovacao").cast(pl.Int64),
            pl.col("num_autorizacoes").cast(pl.Int64),
            pl.col("valor_vendas").cast(pl.Float64),
            pl.col("valor_sem_comprovacao").cast(pl.Float64),
        ])

        t1 = time.perf_counter()
        df.write_parquet(parquet_path, compression="zstd")
        save_time_ms = round((time.perf_counter() - t1) * 1000, 1)
        print(f"GTIN {cnpj}: SQL {query_time_ms}ms | parquet {save_time_ms}ms")

        return CacheLoadResult(
            df=df,
            from_cache=False,
            query_time_ms=query_time_ms,
            save_time_ms=save_time_ms,
        )
    except Exception:
        print(f"[ ANALYTICS ] {cnpj} - GTIN - indisponivel (sem cache local, global indisponivel e banco offline)")
        detail = (
            "Movimentacao mensal por GTIN indisponivel para este CNPJ. "
            "O arquivo local ainda nao existe, o modulo global nao pode ser usado "
            "e o SQL Server nao respondeu para materializar o cache por CNPJ."
        )
        if "global_error" in locals() and global_error:
            detail += f" Detalhe do modulo global: {global_error}"
        return CacheLoadResult(
            df=pl.DataFrame(),
            from_cache=False,
            query_time_ms=query_time_ms,
            save_time_ms=save_time_ms,
            error=detail,
        )
