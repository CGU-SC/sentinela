import os
import time

import pandas as pd
import polars as pl
from sqlalchemy import text

from cache_files import (
    CRM_CONCENTRACAO_MULTIPLO_ALERTAS_PARQUET,
    CRM_CONCENTRACAO_UNICO_ALERTAS_PARQUET,
    CRM_RAIOX_TX_CACHE_VERSION,
    CRM_PRESCRITORES_CACHE_VERSION,
    CRM_RAIOX_TX_GLOBAL_PARQUET,
    CRM_RAIOX_TX_PARQUET,
    CRM_TIMELINE_DIA_PARQUET,
    CRM_TIMELINE_EVENTOS_PARQUET,
    CRM_TIMELINE_HORA_PARQUET,
    CRM_PRESCRITORES_GLOBAL_PARQUET,
    CRM_PRESCRITORES_PARQUET,
    GEOGRAFICO_PARQUET,
    GEOGRAFICO_GLOBAL_PARQUET,
    CRM_CONCENTRACAO_UNICO_ALERTAS_GLOBAL_PARQUET,
    CRM_CONCENTRACAO_MULTIPLO_ALERTAS_GLOBAL_PARQUET,
    CRM_TIMELINE_DIA_GLOBAL_PARQUET,
    CRM_TIMELINE_HORA_GLOBAL_PARQUET,
    CRM_TIMELINE_EVENTOS_GLOBAL_PARQUET,
)
from cache_producers.types import CacheLoadResult

_CRM_ALERTS_CACHE_VERSION = 4
_CRM_PRESCRITORES_CACHE_VERSION = CRM_PRESCRITORES_CACHE_VERSION
_CRM_UNICO_RHYTHM_WINDOWS = (5, 10, 15, 20, 25, 30, 60)
_CRM_MULTIPLO_RHYTHM_WINDOWS = (5, 10, 15, 20, 25, 30, 60)


def _get_cnpj_cache_dir(cnpj: str) -> str:
    from data_cache import get_cnpj_cache_root

    cnpj_dir = os.path.join(get_cnpj_cache_root(), cnpj)
    os.makedirs(cnpj_dir, exist_ok=True)
    return cnpj_dir


def _engine_or_default(engine=None):
    if engine is not None:
        return engine
    from database import engine as default_engine

    return default_engine


def _to_int(value, default: int = 0) -> int:
    if value is None:
        return default
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _path(cnpj: str, filename: str) -> str:
    return os.path.join(_get_cnpj_cache_dir(cnpj), filename)


def _read_parquet(path: str) -> tuple[pl.DataFrame | None, float | None]:
    if not os.path.exists(path):
        return None, None
    try:
        t0 = time.perf_counter()
        df = pl.read_parquet(path)
        return df, round((time.perf_counter() - t0) * 1000, 1)
    except Exception as exc:
        print(f"[ CACHE ] erro de leitura ({exc})")
        return None, None


def _empty_schema(filename: str) -> dict:
    import cache_registry

    schemas = cache_registry.get_cnpj_parquet_schemas()
    return schemas[filename]


def load_or_sync_crm_data(cnpj: str, engine=None) -> CacheLoadResult:
    parquet_path = _path(cnpj, CRM_PRESCRITORES_PARQUET)
    from data_cache import get_cache_dir

    global_path = os.path.join(get_cache_dir(), CRM_PRESCRITORES_GLOBAL_PARQUET)
    schema = _empty_schema(CRM_PRESCRITORES_PARQUET)
    required_columns = set(schema)

    df, read_time_ms = _read_parquet(parquet_path)
    if df is not None:
        missing_cols = sorted(required_columns - set(df.columns))
        version_ok = (
            "_crm_prescritores_cache_version" in df.columns
            and (df.height == 0 or _to_int(df["_crm_prescritores_cache_version"].max()) >= _CRM_PRESCRITORES_CACHE_VERSION)
        )
        global_is_newer = (
            os.path.exists(global_path)
            and os.path.getmtime(global_path) > os.path.getmtime(parquet_path)
        )
        if not missing_cols and version_ok and not global_is_newer:
            return CacheLoadResult(df, from_cache=True, read_time_ms=read_time_ms)
        motivo = f"cache sem {', '.join(missing_cols)}" if missing_cols else "versao de cache defasada"
        print(f"[ CACHE ] {cnpj} - CRM - {motivo}; regenerando parquet.")

    def write_final(df_final: pl.DataFrame) -> float:
        missing_columns = sorted(required_columns - set(df_final.columns))
        if missing_columns:
            raise RuntimeError(
                f"Contrato invalido de {CRM_PRESCRITORES_PARQUET}: "
                f"colunas ausentes {', '.join(missing_columns)}."
            )
        df_final = df_final.select(list(schema.keys()))
        tmp_final_path = parquet_path + ".tmp"
        started_at = time.perf_counter()
        df_final.write_parquet(tmp_final_path, compression="zstd")
        os.replace(tmp_final_path, parquet_path)
        return round((time.perf_counter() - started_at) * 1000, 1)

    if os.path.exists(global_path):
        try:
            from data_cache import get_df_perfil_estabelecimento, scan_crm_prescritores_global

            global_version = pl.read_parquet(
                global_path,
                columns=["_crm_prescritores_cache_version"],
                n_rows=1,
            )
            if global_version.is_empty():
                raise RuntimeError("o modulo global esta vazio")
            if (
                _to_int(global_version["_crm_prescritores_cache_version"].max())
                < _CRM_PRESCRITORES_CACHE_VERSION
            ):
                raise RuntimeError(
                    "versao do modulo global inferior a "
                    f"{_CRM_PRESCRITORES_CACHE_VERSION}"
                )

            perfil = get_df_perfil_estabelecimento()
            required_profile = {"id_cnpj", "cnpj"}
            missing_profile = sorted(required_profile - set(perfil.columns))
            if missing_profile:
                raise RuntimeError(
                    "perfil_estabelecimento sem colunas obrigatorias para derivar CRM prescritores: "
                    + ", ".join(missing_profile)
                )

            perfil_cnpj = (
                perfil
                .filter(pl.col("cnpj").cast(pl.Utf8) == cnpj)
                .select("id_cnpj")
                .unique()
            )
            if perfil_cnpj.height != 1:
                raise RuntimeError(
                    f"CNPJ {cnpj} sem mapeamento unico de id_cnpj no perfil_estabelecimento."
                )
            id_cnpj = int(perfil_cnpj.item(0, "id_cnpj"))

            started_at = time.perf_counter()
            df_global_base = (
                scan_crm_prescritores_global()
                .filter(pl.col("id_cnpj") == id_cnpj)
                .drop("id_cnpj")
                .collect()
                .sort(["competencia", "id_medico"])
            )
            if df_global_base.is_empty():
                df_global = pl.DataFrame(schema=schema)
            else:
                from data_cache import scan_dados_medico

                id_medicos = df_global_base["id_medico"].cast(pl.Utf8).unique().to_list()
                df_medicos = (
                    scan_dados_medico()
                    .filter(pl.col("id_medico").is_in(id_medicos))
                    .select(["id_medico", "no_medico"])
                    .collect()
                    .with_columns(pl.col("id_medico").cast(pl.Utf8))
                    .unique("id_medico")
                )
                df_global = (
                    df_global_base
                    .with_columns(pl.col("id_medico").cast(pl.Utf8))
                    .join(df_medicos, on="id_medico", how="left")
                    .select(list(schema.keys()))
                )
            source_time_ms = round((time.perf_counter() - started_at) * 1000, 1)
            save_time_ms = write_final(df_global)
            print(
                f"[ CACHE ] {cnpj} - {CRM_PRESCRITORES_PARQUET} "
                f"derivado de {CRM_PRESCRITORES_GLOBAL_PARQUET}."
            )
            return CacheLoadResult(
                df_global,
                from_cache=False,
                read_time_ms=source_time_ms,
                save_time_ms=save_time_ms,
            )
        except Exception as exc:
            print(
                f"[ ANALYTICS ] {cnpj} - {CRM_PRESCRITORES_GLOBAL_PARQUET} "
                f"invalido: {exc}"
            )
            return CacheLoadResult(
                pl.DataFrame(schema=schema),
                from_cache=False,
                error=(
                    f"Modulo global {CRM_PRESCRITORES_GLOBAL_PARQUET} existente, "
                    f"mas invalido: {exc}"
                ),
            )

    query_time_ms: float | None = None
    save_time_ms: float | None = None
    try:
        engine = _engine_or_default(engine)
        with engine.connect() as conn:
            t0 = time.perf_counter()
            pdf = pd.read_sql(
                text("SELECT E.id_medico, E.competencia, E.vl_total_prescricoes, "
                     "E.nu_prescricoes_mes, E.nu_prescricoes_total_brasil, "
                     "E.flag_crm_invalido, "
                     "E.flag_prescricao_antes_registro, E.alerta_concentracao_multiplos_crms, "
                     "E.flag_concentracao_mesmo_crm, E.flag_distancia_geografica, "
                     "E.dt_inscricao_crm, "
                     "E.nu_estabelecimentos"
                     " FROM temp_CGUSC.fp.app_crm_export E"
                     " INNER JOIN temp_CGUSC.fp.dados_farmacia F ON F.id = E.id_cnpj"
                     " WHERE F.cnpj = :cnpj"),
                conn,
                params={"cnpj": cnpj},
            )
            query_time_ms = round((time.perf_counter() - t0) * 1000, 1)

        df = pl.from_pandas(pdf) if not pdf.empty else pl.DataFrame(schema=schema)
        if not df.is_empty():
            from data_cache import scan_dados_medico

            id_medicos = df["id_medico"].cast(pl.Utf8).unique().to_list()
            df_medicos = (
                scan_dados_medico()
                .filter(pl.col("id_medico").is_in(id_medicos))
                .select(["id_medico", "no_medico"])
                .collect()
            )
            df = df.with_columns(pl.col("id_medico").cast(pl.Utf8)).join(
                df_medicos,
                on="id_medico",
                how="left",
            )

        missing_after_build = [col for col in ["no_medico", "dt_inscricao_crm"] if col not in df.columns]
        if missing_after_build:
            raise RuntimeError(
                f"Contrato invalido ao gerar {CRM_PRESCRITORES_PARQUET}: colunas ausentes {', '.join(missing_after_build)}."
            )

        df = df.with_columns([
            pl.col("no_medico").cast(pl.Utf8),
            pl.col("nu_prescricoes_mes").cast(pl.Int32),
            pl.col("nu_prescricoes_total_brasil").cast(pl.Int32),
            pl.col("dt_inscricao_crm").cast(pl.Date),
            pl.col("nu_estabelecimentos").cast(pl.Int32),
        ])
        for col in [
            "flag_crm_invalido",
            "flag_prescricao_antes_registro",
            "alerta_concentracao_multiplos_crms",
            "flag_concentracao_mesmo_crm",
            "flag_distancia_geografica",
        ]:
            if col in df.columns:
                df = df.with_columns(pl.col(col).cast(pl.Int8))
        df = df.with_columns(pl.lit(_CRM_PRESCRITORES_CACHE_VERSION).alias("_crm_prescritores_cache_version"))

        save_time_ms = write_final(df)
        return CacheLoadResult(df, from_cache=False, query_time_ms=query_time_ms, save_time_ms=save_time_ms)
    except Exception:
        print(f"[ ANALYTICS ] {cnpj} - CRM - indisponivel (sem cache e banco offline)")
        return CacheLoadResult(pl.DataFrame(), from_cache=False, error="Arquivo Parquet local nao encontrado e Banco Offline.")


def load_or_sync_geografico(cnpj: str, engine=None) -> CacheLoadResult:
    schema = _empty_schema(GEOGRAFICO_PARQUET)
    required = set(schema)
    parquet_path = _path(cnpj, GEOGRAFICO_PARQUET)
    from data_cache import get_cache_dir
    global_path = os.path.join(get_cache_dir(), GEOGRAFICO_GLOBAL_PARQUET)
    
    df, read_time_ms = _read_parquet(parquet_path)
    if df is not None:
        missing_cols = sorted(required - set(df.columns))
        global_is_newer = os.path.exists(global_path) and os.path.getmtime(global_path) > os.path.getmtime(parquet_path)
        if not missing_cols and not global_is_newer:
            return CacheLoadResult(df, from_cache=True, read_time_ms=read_time_ms)
        print(f"[ CACHE ] {cnpj} - geografico - cache defasado; regenerando parquet.")

    if os.path.exists(global_path):
        try:
            from data_cache import scan_geografico_global
            started_at = time.perf_counter()
            df_global = (
                scan_geografico_global()
                .filter((pl.col("cnpj_a") == cnpj) | (pl.col("cnpj_b") == cnpj))
                .collect()
            )
            df_global = df_global.select(list(schema.keys()))
            source_time_ms = round((time.perf_counter() - started_at) * 1000, 1)
            
            t1 = time.perf_counter()
            df_global.write_parquet(parquet_path, compression="zstd")
            save_time_ms = round((time.perf_counter() - t1) * 1000, 1)
            print(f"[ CACHE ] {cnpj} - {GEOGRAFICO_PARQUET} derivado do global.")
            return CacheLoadResult(df_global, from_cache=False, read_time_ms=source_time_ms, save_time_ms=save_time_ms)
        except Exception as exc:
            print(f"[ ANALYTICS ] {cnpj} - geografico global invalido: {exc}")

    result = _load_or_sync_sql_cache(
        cnpj,
        GEOGRAFICO_PARQUET,
        text("SELECT * FROM temp_CGUSC.fp.app_alertas_crm_geografico WHERE cnpj_a = :cnpj OR cnpj_b = :cnpj"),
        {"cnpj": cnpj},
        engine,
        read_existing=False,
        required_columns=required,
    )
    return result


def load_or_sync_crm_timeline_dia(cnpj: str, engine=None) -> CacheLoadResult:
    schema = _empty_schema(CRM_TIMELINE_DIA_PARQUET)
    required = set(schema)
    parquet_path = _path(cnpj, CRM_TIMELINE_DIA_PARQUET)
    from data_cache import get_cache_dir
    global_path = os.path.join(get_cache_dir(), CRM_TIMELINE_DIA_GLOBAL_PARQUET)

    df, read_time_ms = _read_parquet(parquet_path)
    if df is not None:
        missing_cols = sorted(required - set(df.columns))
        global_is_newer = (
            os.path.exists(global_path)
            and os.path.getmtime(global_path) > os.path.getmtime(parquet_path)
        )
        if not missing_cols and not global_is_newer:
            return CacheLoadResult(df, from_cache=True, read_time_ms=read_time_ms)
        print(f"[ CACHE ] {cnpj} - timeline dia - cache defasado; regenerando parquet.")

    if os.path.exists(global_path):
        try:
            from data_cache import get_df_perfil_estabelecimento, scan_crm_timeline_dia_global
            perfil = get_df_perfil_estabelecimento()
            perfil_cnpj = perfil.filter(pl.col("cnpj").cast(pl.Utf8) == cnpj).select("id_cnpj").unique()
            if perfil_cnpj.height == 1:
                id_cnpj = int(perfil_cnpj.item(0, "id_cnpj"))
                started_at = time.perf_counter()
                df_global = (
                    scan_crm_timeline_dia_global()
                    .filter(pl.col("id_cnpj") == id_cnpj)
                    .drop("id_cnpj")
                    .collect()
                )
                df_global = df_global.select(list(schema.keys()))
                source_time_ms = round((time.perf_counter() - started_at) * 1000, 1)
                t1 = time.perf_counter()
                df_global.write_parquet(parquet_path, compression="zstd")
                save_time_ms = round((time.perf_counter() - t1) * 1000, 1)
                print(f"[ CACHE ] {cnpj} - {CRM_TIMELINE_DIA_PARQUET} derivado do global.")
                return CacheLoadResult(df_global, from_cache=False, read_time_ms=source_time_ms, save_time_ms=save_time_ms)
        except Exception as exc:
            print(f"[ ANALYTICS ] {cnpj} - {CRM_TIMELINE_DIA_GLOBAL_PARQUET} invalido: {exc}")

    return _load_or_sync_sql_cache(
        cnpj,
        CRM_TIMELINE_DIA_PARQUET,
        text(
            "SELECT CONVERT(VARCHAR(10), P.dt_janela, 23) AS dt_janela,"
            " P.competencia, P.nu_prescricoes_dia, P.nu_crms_distintos, P.mediana_diaria,"
            " P.is_dia_com_volume_horario_anomalo, P.is_anomalo_unico, P.is_crm_multiplo,"
            " P.score_crm_unico_hora, P.score_crm_unico_qtd, P.score_crm_unico_minutos,"
            " P.score_crm_unico_medico, P.score_crm_multiplo_hora, P.score_crm_multiplo_qtd,"
            " P.score_crm_multiplo_minutos, P.score_crm_multiplo_crms"
            " FROM temp_CGUSC.fp.app_crm_timeline_dia P"
            " INNER JOIN temp_CGUSC.fp.dados_farmacia F ON F.id = P.id_cnpj"
            " WHERE F.cnpj = :cnpj"
            " ORDER BY P.dt_janela"
        ),
        {"cnpj": cnpj},
        engine,
        read_existing=False,
    )


def load_or_sync_crm_timeline_hora(cnpj: str, engine=None) -> CacheLoadResult:
    schema = _empty_schema(CRM_TIMELINE_HORA_PARQUET)
    required = set(schema)
    parquet_path = _path(cnpj, CRM_TIMELINE_HORA_PARQUET)
    from data_cache import get_cache_dir
    global_path = os.path.join(get_cache_dir(), CRM_TIMELINE_HORA_GLOBAL_PARQUET)

    df, read_time_ms = _read_parquet(parquet_path)
    if df is not None:
        missing_cols = sorted(required - set(df.columns))
        global_is_newer = (
            os.path.exists(global_path)
            and os.path.getmtime(global_path) > os.path.getmtime(parquet_path)
        )
        if not missing_cols and not global_is_newer:
            return CacheLoadResult(df, from_cache=True, read_time_ms=read_time_ms)
        print(f"[ CACHE ] {cnpj} - timeline hora - cache defasado; regenerando parquet.")

    if os.path.exists(global_path):
        try:
            from data_cache import get_df_perfil_estabelecimento, scan_crm_timeline_hora_global
            perfil = get_df_perfil_estabelecimento()
            perfil_cnpj = perfil.filter(pl.col("cnpj").cast(pl.Utf8) == cnpj).select("id_cnpj").unique()
            if perfil_cnpj.height == 1:
                id_cnpj = int(perfil_cnpj.item(0, "id_cnpj"))
                started_at = time.perf_counter()
                df_global = (
                    scan_crm_timeline_hora_global()
                    .filter(pl.col("id_cnpj") == id_cnpj)
                    .drop("id_cnpj")
                    .collect()
                )
                df_global = df_global.select(list(schema.keys()))
                source_time_ms = round((time.perf_counter() - started_at) * 1000, 1)
                t1 = time.perf_counter()
                df_global.write_parquet(parquet_path, compression="zstd")
                save_time_ms = round((time.perf_counter() - t1) * 1000, 1)
                print(f"[ CACHE ] {cnpj} - {CRM_TIMELINE_HORA_PARQUET} derivado do global.")
                return CacheLoadResult(df_global, from_cache=False, read_time_ms=source_time_ms, save_time_ms=save_time_ms)
        except Exception as exc:
            print(f"[ ANALYTICS ] {cnpj} - {CRM_TIMELINE_HORA_GLOBAL_PARQUET} invalido: {exc}")

    return _load_or_sync_sql_cache(
        cnpj,
        CRM_TIMELINE_HORA_PARQUET,
        text(
            "SELECT CONVERT(VARCHAR(10), P.dt_janela, 23) AS dt_janela,"
            " P.hr_janela, P.nu_prescricoes, P.nu_crms_diferentes, P.mediana_hora,"
            " P.mad_hora, P.is_hora_com_alerta, P.is_volume_horario_anomalo,"
            " P.is_crm_unico, P.is_crm_multiplo"
            " FROM temp_CGUSC.fp.app_crm_timeline_hora P"
            " INNER JOIN temp_CGUSC.fp.dados_farmacia F ON F.id = P.id_cnpj"
            " WHERE F.cnpj = :cnpj"
            " ORDER BY P.dt_janela, P.hr_janela"
        ),
        {"cnpj": cnpj},
        engine,
        read_existing=False,
    )


def load_or_sync_crm_timeline_eventos(cnpj: str, engine=None) -> CacheLoadResult:
    schema = _empty_schema(CRM_TIMELINE_EVENTOS_PARQUET)
    required = set(schema)
    parquet_path = _path(cnpj, CRM_TIMELINE_EVENTOS_PARQUET)
    from data_cache import get_cache_dir
    global_path = os.path.join(get_cache_dir(), CRM_TIMELINE_EVENTOS_GLOBAL_PARQUET)

    df, read_time_ms = _read_parquet(parquet_path)
    if df is not None:
        missing_cols = sorted(required - set(df.columns))
        global_is_newer = (
            os.path.exists(global_path)
            and os.path.getmtime(global_path) > os.path.getmtime(parquet_path)
        )
        if not missing_cols and not global_is_newer:
            return CacheLoadResult(df, from_cache=True, read_time_ms=read_time_ms)
        print(f"[ CACHE ] {cnpj} - timeline eventos - cache defasado; regenerando parquet.")

    if os.path.exists(global_path):
        try:
            from data_cache import get_df_perfil_estabelecimento, scan_crm_timeline_eventos_global
            perfil = get_df_perfil_estabelecimento()
            perfil_cnpj = perfil.filter(pl.col("cnpj").cast(pl.Utf8) == cnpj).select("id_cnpj").unique()
            if perfil_cnpj.height == 1:
                id_cnpj = int(perfil_cnpj.item(0, "id_cnpj"))
                started_at = time.perf_counter()
                df_global = (
                    scan_crm_timeline_eventos_global()
                    .filter(pl.col("id_cnpj") == id_cnpj)
                    .drop("id_cnpj")
                    .collect()
                )
                df_global = df_global.select(list(schema.keys()))
                source_time_ms = round((time.perf_counter() - started_at) * 1000, 1)
                t1 = time.perf_counter()
                df_global.write_parquet(parquet_path, compression="zstd")
                save_time_ms = round((time.perf_counter() - t1) * 1000, 1)
                print(f"[ CACHE ] {cnpj} - {CRM_TIMELINE_EVENTOS_PARQUET} derivado do global.")
                return CacheLoadResult(df_global, from_cache=False, read_time_ms=source_time_ms, save_time_ms=save_time_ms)
        except Exception as exc:
            print(f"[ ANALYTICS ] {cnpj} - {CRM_TIMELINE_EVENTOS_GLOBAL_PARQUET} invalido: {exc}")

    return _load_or_sync_sql_cache(
        cnpj,
        CRM_TIMELINE_EVENTOS_PARQUET,
        text(
            "SELECT CONVERT(VARCHAR(10), P.dt_janela, 23) AS dt_janela,"
            " P.tipo, P.hora_inicio, P.hora_fim, P.minuto_inicio, P.minuto_fim,"
            " P.severidade, P.id_medico, P.nu_crms_distintos"
            " FROM temp_CGUSC.fp.app_crm_timeline_eventos P"
            " INNER JOIN temp_CGUSC.fp.dados_farmacia F ON F.id = P.id_cnpj"
            " WHERE F.cnpj = :cnpj"
            " ORDER BY P.dt_janela, P.minuto_inicio, P.tipo"
        ),
        {"cnpj": cnpj},
        engine,
        read_existing=False,
    )



def load_or_sync_crm_unico_alertas(cnpj: str, engine=None) -> CacheLoadResult:
    schema = _empty_schema(CRM_CONCENTRACAO_UNICO_ALERTAS_PARQUET)
    required = set(schema)
    parquet_path = _path(cnpj, CRM_CONCENTRACAO_UNICO_ALERTAS_PARQUET)
    from data_cache import get_cache_dir
    global_path = os.path.join(get_cache_dir(), CRM_CONCENTRACAO_UNICO_ALERTAS_GLOBAL_PARQUET)

    df, read_time_ms = _read_parquet(parquet_path)
    if df is not None:
        version_ok = "_crm_alerts_cache_version" in df.columns and (
            df.height == 0 or _to_int(df["_crm_alerts_cache_version"].max()) >= _CRM_ALERTS_CACHE_VERSION
        )
        global_is_newer = (
            os.path.exists(global_path)
            and os.path.getmtime(global_path) > os.path.getmtime(parquet_path)
        )
        if required.issubset(df.columns) and version_ok and not global_is_newer:
            return CacheLoadResult(df, from_cache=True, read_time_ms=read_time_ms)
        print(f"[ CACHE ] {cnpj} - unico alertas - cache defasado; regenerando parquet.")

    if os.path.exists(global_path):
        try:
            from data_cache import get_df_perfil_estabelecimento, scan_crm_concentracao_unico_alertas_global
            perfil = get_df_perfil_estabelecimento()
            perfil_cnpj = perfil.filter(pl.col("cnpj").cast(pl.Utf8) == cnpj).select("id_cnpj").unique()
            if perfil_cnpj.height == 1:
                id_cnpj = int(perfil_cnpj.item(0, "id_cnpj"))
                started_at = time.perf_counter()
                df_global = (
                    scan_crm_concentracao_unico_alertas_global()
                    .filter(pl.col("id_cnpj") == id_cnpj)
                    .drop("id_cnpj")
                    .collect()
                )
                df_global = df_global.with_columns(
                    pl.lit(_CRM_ALERTS_CACHE_VERSION).alias("_crm_alerts_cache_version")
                )
                df_global = df_global.select(list(schema.keys()))
                source_time_ms = round((time.perf_counter() - started_at) * 1000, 1)
                t1 = time.perf_counter()
                df_global.write_parquet(parquet_path, compression="zstd")
                save_time_ms = round((time.perf_counter() - t1) * 1000, 1)
                print(f"[ CACHE ] {cnpj} - {CRM_CONCENTRACAO_UNICO_ALERTAS_PARQUET} derivado do global.")
                return CacheLoadResult(df_global, from_cache=False, read_time_ms=source_time_ms, save_time_ms=save_time_ms)
        except Exception as exc:
            print(f"[ ANALYTICS ] {cnpj} - {CRM_CONCENTRACAO_UNICO_ALERTAS_GLOBAL_PARQUET} invalido: {exc}")

    query = text("""
        SELECT A.id_medico, YEAR(A.dt_dia) * 100 + MONTH(A.dt_dia) AS competencia,
               A.dt_dia AS dt_alerta, DATEPART(HOUR, A.dt_ini_concentracao) AS hr_janela,
               A.nu_autorizacoes_pior_ritmo AS nu_prescricoes_dia,
               A.janela_pior_ritmo_minutos AS nu_minutos_dia,
               A.nu_minutos_span AS nu_minutos_intervalo,
               A.taxa_hora_pior_ritmo AS taxa_hora,
               A.dt_ini_concentracao AS dt_ini_hora,
               A.dt_fim_concentracao AS dt_fim_hora,
               A.id_severidade,
               CASE A.id_severidade WHEN 4 THEN 'EXTREMO' WHEN 3 THEN 'CRITICO'
                    WHEN 2 THEN 'GRAVE' WHEN 1 THEN 'ALTO' ELSE 'ALERTA' END AS severidade,
               A.criterio_pior_ritmo, A.nu_5min, A.nu_10min, A.nu_15min,
               A.nu_20min, A.nu_25min, A.nu_30min, A.nu_60min
        FROM temp_CGUSC.fp.app_crm_concentracao_unico_alertas A
        INNER JOIN temp_CGUSC.fp.dados_farmacia F ON F.id = A.id_cnpj
        WHERE F.cnpj = :cnpj
        ORDER BY A.dt_dia, A.id_medico, A.dt_ini_concentracao
    """)
    result = _load_or_sync_sql_cache(cnpj, CRM_CONCENTRACAO_UNICO_ALERTAS_PARQUET, query, {"cnpj": cnpj}, engine, read_existing=False)
    if result.error or result.df is None:
        return result

    df = result.df.with_columns(pl.lit(_CRM_ALERTS_CACHE_VERSION).alias("_crm_alerts_cache_version"))
    df.write_parquet(parquet_path, compression="zstd")
    return CacheLoadResult(df, result.from_cache, result.read_time_ms, result.query_time_ms, result.save_time_ms, result.error)


def load_or_sync_crm_multi_alertas(cnpj: str, engine=None) -> CacheLoadResult:
    schema = _empty_schema(CRM_CONCENTRACAO_MULTIPLO_ALERTAS_PARQUET)
    required = set(schema)
    parquet_path = _path(cnpj, CRM_CONCENTRACAO_MULTIPLO_ALERTAS_PARQUET)
    df, read_time_ms = _read_parquet(parquet_path)
    if df is not None:
        version_ok = "_crm_alerts_cache_version" in df.columns and (
            df.height == 0 or _to_int(df["_crm_alerts_cache_version"].max()) >= _CRM_ALERTS_CACHE_VERSION
        )
        if required.issubset(df.columns) and version_ok:
            return CacheLoadResult(df, from_cache=True, read_time_ms=read_time_ms)

    
    from data_cache import get_cache_dir
    global_path = os.path.join(get_cache_dir(), CRM_CONCENTRACAO_MULTIPLO_ALERTAS_GLOBAL_PARQUET)
    if df is not None:
        global_is_newer = os.path.exists(global_path) and os.path.getmtime(global_path) > os.path.getmtime(parquet_path)
        
        version_ok = "_crm_alerts_cache_version" in df.columns and (
            df.height == 0 or _to_int(df["_crm_alerts_cache_version"].max()) >= _CRM_ALERTS_CACHE_VERSION
        )
        if not version_ok: global_is_newer = True

        if global_is_newer:
            df = None # force re-generation

    if df is None and os.path.exists(global_path):
        try:
            from data_cache import get_df_perfil_estabelecimento, scan_crm_concentracao_multiplo_alertas_global
            perfil = get_df_perfil_estabelecimento()
            perfil_cnpj = perfil.filter(pl.col("cnpj").cast(pl.Utf8) == cnpj).select("id_cnpj").unique()
            if perfil_cnpj.height == 1:
                id_cnpj = int(perfil_cnpj.item(0, "id_cnpj"))
                started_at = time.perf_counter()
                df_global = (
                    scan_crm_concentracao_multiplo_alertas_global()
                    .filter(pl.col("id_cnpj") == id_cnpj)
                    
                    .collect()
                )
                df_global = df_global.with_columns(pl.lit(_CRM_ALERTS_CACHE_VERSION).alias("_crm_alerts_cache_version"))
                df_global = df_global.select(list(schema.keys()))
                source_time_ms = round((time.perf_counter() - started_at) * 1000, 1)
                
                t1 = time.perf_counter()
                df_global.write_parquet(parquet_path, compression="zstd")
                save_time_ms = round((time.perf_counter() - t1) * 1000, 1)
                print(f"[ CACHE ] {cnpj} - {CRM_CONCENTRACAO_MULTIPLO_ALERTAS_PARQUET} derivado do global.")
                return CacheLoadResult(df_global, from_cache=False, read_time_ms=source_time_ms, save_time_ms=save_time_ms)
        except Exception as exc:
            print(f"[ ANALYTICS ] {cnpj} - CRM_CONCENTRACAO_MULTIPLO_ALERTAS_GLOBAL_PARQUET invalido: {exc}")

    query = text("""
        SELECT A.id_cnpj, YEAR(A.dt_dia) * 100 + MONTH(A.dt_dia) AS competencia,
               A.dt_dia, A.dt_ini_concentracao AS dt_alerta,
               DATEPART(HOUR, A.dt_ini_concentracao) AS hr_janela,
               A.dt_ini_concentracao, A.dt_fim_concentracao,
               A.nu_autorizacoes_pior_ritmo AS nu_prescricoes,
               A.nu_crms_distintos AS nu_crms, A.nu_60min,
               A.nu_minutos_span AS nu_minutos_intervalo,
               A.janela_pior_ritmo_minutos AS nu_minutos_span,
               A.taxa_hora_pior_ritmo AS taxa_hora,
               A.id_severidade,
               A.nu_crms_distintos,
               CASE A.id_severidade WHEN 4 THEN 'EXTREMO' WHEN 3 THEN 'CRITICO'
                    WHEN 2 THEN 'GRAVE' WHEN 1 THEN 'ALTO' ELSE 'ALERTA' END AS severidade,
               A.criterio_pior_ritmo, A.nu_5min, A.nu_10min, A.nu_15min,
               A.nu_20min, A.nu_25min, A.nu_30min
        FROM temp_CGUSC.fp.app_crm_concentracao_multiplo_alertas A
        INNER JOIN temp_CGUSC.fp.dados_farmacia F ON F.id = A.id_cnpj
        WHERE F.cnpj = :cnpj
    """)
    result = _load_or_sync_sql_cache(cnpj, CRM_CONCENTRACAO_MULTIPLO_ALERTAS_PARQUET, query, {"cnpj": cnpj}, engine, read_existing=False)
    if result.error or result.df is None:
        return result

    df = result.df.with_columns(pl.lit(_CRM_ALERTS_CACHE_VERSION).alias("_crm_alerts_cache_version"))
    df.write_parquet(parquet_path, compression="zstd")
    return CacheLoadResult(df, result.from_cache, result.read_time_ms, result.query_time_ms, result.save_time_ms, result.error)


def sync_crm_raiox_tx(cnpj: str, engine=None) -> CacheLoadResult:
    parquet_path = _path(cnpj, CRM_RAIOX_TX_PARQUET)
    from data_cache import get_cache_dir

    global_path = os.path.join(get_cache_dir(), CRM_RAIOX_TX_GLOBAL_PARQUET)
    schema = _empty_schema(CRM_RAIOX_TX_PARQUET)
    required_columns = set(schema)

    df, read_time_ms = _read_parquet(parquet_path)
    if df is not None:
        version_ok = "_crm_raiox_tx_cache_version" in df.columns and (
            df.height == 0 or _to_int(df["_crm_raiox_tx_cache_version"].max()) >= CRM_RAIOX_TX_CACHE_VERSION
        )
        global_is_newer = (
            os.path.exists(global_path)
            and os.path.getmtime(global_path) > os.path.getmtime(parquet_path)
        )
        if (
            required_columns.issubset(set(df.columns))
            and "codigo_barra" not in df.columns
            and version_ok
            and not global_is_newer
        ):
            return CacheLoadResult(df, from_cache=True, read_time_ms=read_time_ms)

    def write_final(df_final: pl.DataFrame) -> float:
        df_final = df_final.select(list(schema.keys()))
        tmp_final_path = parquet_path + ".tmp"
        started_at = time.perf_counter()
        df_final.write_parquet(tmp_final_path, compression="zstd")
        os.replace(tmp_final_path, parquet_path)
        return round((time.perf_counter() - started_at) * 1000, 1)

    if os.path.exists(global_path):
        try:
            from data_cache import get_df_perfil_estabelecimento, scan_crm_raiox_tx_global

            global_version = pl.read_parquet(
                global_path,
                columns=["_crm_raiox_tx_cache_version"],
                n_rows=1,
            )
            if global_version.is_empty():
                raise RuntimeError("o modulo global esta vazio")
            if (
                _to_int(global_version["_crm_raiox_tx_cache_version"].max())
                < CRM_RAIOX_TX_CACHE_VERSION
            ):
                raise RuntimeError(
                    "versao do modulo global inferior a "
                    f"{CRM_RAIOX_TX_CACHE_VERSION}"
                )

            perfil = get_df_perfil_estabelecimento()
            required_profile = {"id_cnpj", "cnpj"}
            missing_profile = sorted(required_profile - set(perfil.columns))
            if missing_profile:
                raise RuntimeError(
                    "perfil_estabelecimento sem colunas obrigatorias para derivar CRM Raio-X: "
                    + ", ".join(missing_profile)
                )

            perfil_cnpj = (
                perfil
                .filter(pl.col("cnpj").cast(pl.Utf8) == cnpj)
                .select("id_cnpj")
                .unique()
            )
            if perfil_cnpj.height != 1:
                raise RuntimeError(
                    f"CNPJ {cnpj} sem mapeamento unico de id_cnpj no perfil_estabelecimento."
                )
            id_cnpj = int(perfil_cnpj.item(0, "id_cnpj"))

            started_at = time.perf_counter()
            df_global = (
                scan_crm_raiox_tx_global()
                .filter(pl.col("id_cnpj") == id_cnpj)
                .drop("id_cnpj")
                .collect()
                .sort(["data_hora", "num_autorizacao"])
                .select(list(schema.keys()))
            )
            source_time_ms = round((time.perf_counter() - started_at) * 1000, 1)
            save_time_ms = write_final(df_global)
            print(
                f"[ CACHE ] {cnpj} - {CRM_RAIOX_TX_PARQUET} "
                f"derivado de {CRM_RAIOX_TX_GLOBAL_PARQUET}."
            )
            return CacheLoadResult(
                df_global,
                from_cache=False,
                read_time_ms=source_time_ms,
                save_time_ms=save_time_ms,
            )
        except Exception as exc:
            print(
                f"[ ANALYTICS ] {cnpj} - {CRM_RAIOX_TX_GLOBAL_PARQUET} "
                f"invalido: {exc}"
            )
            return CacheLoadResult(
                pl.DataFrame(schema=schema),
                from_cache=False,
                error=(
                    f"Modulo global {CRM_RAIOX_TX_GLOBAL_PARQUET} existente, "
                    f"mas invalido: {exc}"
                ),
            )

    try:
        engine = _engine_or_default(engine)
        query = text(
            "SELECT P.dt_janela, P.hr_janela, MIN(P.data_hora) AS data_hora, "
            "P.num_autorizacao, P.id_medico, SUM(P.valor_pago) AS valor_pago "
            "FROM temp_CGUSC.fp.app_crm_raiox_tx P "
            "INNER JOIN temp_CGUSC.fp.dados_farmacia F ON F.id = P.id_cnpj "
            "WHERE F.cnpj = :cnpj "
            "GROUP BY P.dt_janela, P.hr_janela, P.num_autorizacao, P.id_medico "
            "ORDER BY MIN(P.data_hora), P.num_autorizacao"
        )

        with engine.connect() as conn:
            started_at = time.perf_counter()
            pdf = pd.read_sql(query, conn, params={"cnpj": cnpj})
            query_time_ms = round((time.perf_counter() - started_at) * 1000, 1)

        if pdf.empty:
            df_final = pl.DataFrame(schema=schema)
        else:
            df_final = (
                pl.from_pandas(pdf)
                .with_columns([
                    pl.col("dt_janela").cast(pl.Utf8),
                    pl.col("hr_janela").cast(pl.Int32),
                    pl.col("data_hora").cast(pl.Utf8),
                    pl.col("num_autorizacao").cast(pl.Utf8),
                    pl.col("id_medico").cast(pl.Utf8),
                    pl.col("valor_pago").cast(pl.Float64),
                    pl.lit(CRM_RAIOX_TX_CACHE_VERSION)
                    .alias("_crm_raiox_tx_cache_version"),
                ])
                .sort(["data_hora", "num_autorizacao"])
            )
        save_time_ms = write_final(df_final)

        print(
            f"[ CACHE ] {cnpj} - {CRM_RAIOX_TX_PARQUET} "
            "gerado por consulta SQL direta."
        )
        return CacheLoadResult(
            df_final,
            from_cache=False,
            query_time_ms=query_time_ms,
            save_time_ms=save_time_ms,
        )
    except Exception as exc:
        print(
            f"[ ANALYTICS ] {cnpj} - {CRM_RAIOX_TX_PARQUET} - "
            f"erro ao consultar SQL Server: {exc}"
        )
        return CacheLoadResult(
            pl.DataFrame(schema=schema),
            from_cache=False,
            error=f"Erro ao gerar {CRM_RAIOX_TX_PARQUET} pelo SQL Server: {exc}",
        )


def _load_or_sync_sql_cache(
    cnpj: str,
    filename: str,
    query,
    params: dict,
    engine=None,
    read_existing: bool = True,
    required_columns: set[str] | None = None,
) -> CacheLoadResult:
    parquet_path = _path(cnpj, filename)
    if read_existing:
        df, read_time_ms = _read_parquet(parquet_path)
        if df is not None:
            return CacheLoadResult(df, from_cache=True, read_time_ms=read_time_ms)

    query_time_ms: float | None = None
    save_time_ms: float | None = None
    try:
        engine = _engine_or_default(engine)
        with engine.connect() as conn:
            t0 = time.perf_counter()
            pdf = pd.read_sql(query, conn, params=params)
            query_time_ms = round((time.perf_counter() - t0) * 1000, 1)

        if required_columns and not pdf.empty:
            missing_columns = sorted(required_columns - set(pdf.columns))
            if missing_columns:
                return CacheLoadResult(
                    None,
                    from_cache=False,
                    query_time_ms=query_time_ms,
                    error=(
                        f"Contrato invalido de {filename}: colunas ausentes "
                        f"{', '.join(missing_columns)}."
                    ),
                )

        df = pl.from_pandas(pdf) if not pdf.empty else pl.DataFrame(schema=_empty_schema(filename))
        t1 = time.perf_counter()
        df.write_parquet(parquet_path, compression="zstd")
        save_time_ms = round((time.perf_counter() - t1) * 1000, 1)
        return CacheLoadResult(df, from_cache=False, query_time_ms=query_time_ms, save_time_ms=save_time_ms)
    except Exception:
        print(f"[ ANALYTICS ] {cnpj} - {filename} - indisponivel (sem cache e banco offline)")
        return CacheLoadResult(pl.DataFrame(schema=_empty_schema(filename)), from_cache=False, error="Banco Offline.")
