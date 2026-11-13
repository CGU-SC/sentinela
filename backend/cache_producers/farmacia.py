from decimal import Decimal, ROUND_HALF_UP
import copy
import json
import os
import time as _time
import traceback
import zlib

import polars as pl
from sqlalchemy import text
from sqlalchemy.exc import InterfaceError as SQLAInterfaceError

import cnpj_cache_versao
from cache_files import (
    MEMORIA_CALCULO_CACHE_VERSION,
    MEMORIA_CALCULO_GLOBAL_PARQUET,
    MEMORIA_CALCULO_PARQUET,
)
from cache_producers.types import CacheLoadResult


def _cache_path(cnpj: str) -> str:
    return os.path.join(_get_cnpj_cache_dir(cnpj), MEMORIA_CALCULO_PARQUET)


def _global_cache_path() -> str:
    from data_cache import get_cache_dir

    return os.path.join(get_cache_dir(), MEMORIA_CALCULO_GLOBAL_PARQUET)


def _get_cnpj_cache_dir(cnpj: str) -> str:
    return cnpj_cache_versao.get_cnpj_cache_dir(cnpj)


def _parse_memory_date(value):
    if not value:
        return None
    if hasattr(value, "strftime"):
        return value
    try:
        from datetime import datetime as _dt

        text_value = str(value)
        if "T" in text_value:
            return _dt.fromisoformat(text_value).date()
        return _dt.strptime(text_value[:10], "%Y-%m-%d").date()
    except Exception:
        return None


def _fmt_memory_date(value) -> str:
    parsed = _parse_memory_date(value)
    return parsed.strftime("%d/%m/%Y") if parsed else "-"


def _as_decimal(value) -> Decimal:
    return Decimal(str(value or 0))


def _as_int(value) -> int:
    return int(_as_decimal(value))


def _formatar_notas_estoque_inicial(estoque_inicial: dict) -> str:
    quantidade = _as_int(estoque_inicial.get("quantidade"))
    data_ref = _fmt_memory_date(estoque_inicial.get("data_referencia"))
    partes = [f"Estoque Inicial Estimado: {quantidade} - {data_ref}"]
    for nota in estoque_inicial.get("notas") or []:
        numero = nota.get("numero_nfe") or ""
        data = _fmt_memory_date(nota.get("data"))
        qtd = _as_int(nota.get("quantidade"))
        partes.append(f"NF Estoque Inicial: {numero} - {data} | Qtde: {qtd}")
    return "; ".join(partes)


def _build_medicamentos_map_from_rows(rows) -> dict[str | float, str]:
    medicamentos_map: dict[str | float, str] = {}
    for row in rows:
        codigo_raw = row[0] if not isinstance(row, dict) else row.get("codigo_barra")
        principio_raw = row[1] if not isinstance(row, dict) else row.get("principio_ativo")
        if not codigo_raw:
            continue
        codigo = str(codigo_raw).strip()
        principio_ativo = str(principio_raw or "DESCONHECIDO")
        medicamentos_map[codigo] = principio_ativo
        try:
            medicamentos_map[float(codigo)] = principio_ativo
        except (TypeError, ValueError):
            pass
    return medicamentos_map


def _load_medicamentos_map_from_cache() -> dict[str | float, str]:
    from data_cache import get_medicamentos_df

    medicamentos = get_medicamentos_df()
    required = {"codigo_barra", "principio_ativo"}
    missing = required - set(medicamentos.columns)
    if missing:
        raise RuntimeError(
            "Cache de medicamentos sem colunas obrigatorias para memoria de calculo: "
            + ", ".join(sorted(missing))
        )
    rows = (
        medicamentos
        .select(["codigo_barra", "principio_ativo"])
        .iter_rows()
    )
    return _build_medicamentos_map_from_rows(rows)


def _formatar_referencia_v2(referencia: dict, estoque_inicial: dict) -> str:
    tipo = referencia.get("tipo")
    if tipo == "estoque_inicial":
        return _formatar_notas_estoque_inicial(estoque_inicial)

    numero = referencia.get("numero_nfe") or ""
    data = _fmt_memory_date(referencia.get("data"))
    qtd = _as_int(referencia.get("quantidade"))
    if tipo == "saida_estoque":
        return f"NF Transferencia: {numero} - {data} | Qtde: {qtd}"
    return f"NF Aquisicao: {numero} - {data} | Qtde: {qtd}"


def _legacy_rows_from_memoria_v2(memoria_v2: dict) -> list[dict]:
    rows: list[dict] = []
    for gtin_info in memoria_v2.get("gtins") or []:
        gtin = str(gtin_info.get("gtin") or "").strip()
        if not gtin:
            continue

        estoque_inicial = gtin_info.get("estoque_inicial") or {}
        estoque_qtd = _as_decimal(estoque_inicial.get("quantidade"))
        data_estoque = _parse_memory_date(estoque_inicial.get("data_referencia"))

        rows.append({
            "tipo": "h",
            "codigo_barra": gtin,
            "estoque_inicial": estoque_qtd,
            "vendas_periodo": 0,
            "vendas_sem_comprovacao": 0,
            "qnt_aquis_dev": 0,
            "data_aquis_dev_estoq": None,
            "numero_nfe": None,
        })
        rows.append({
            "tipo": "e",
            "codigo_barra": gtin,
            "estoque_inicial": estoque_qtd,
            "data_estoque_inicial": data_estoque,
            "data_aquis_dev_estoq": data_estoque,
            "qnt_aquis_dev": 0,
            "numero_nfe": None,
            "notas_estoque_inicial": estoque_inicial.get("notas") or [],
        })

        for evento in gtin_info.get("eventos") or []:
            tipo_evento = evento.get("tipo")
            if tipo_evento == "estoque_inicial":
                continue
            if tipo_evento in ("aquisicao", "saida_estoque"):
                rows.append({
                    "tipo": "c" if tipo_evento == "aquisicao" else "d",
                    "codigo_barra": gtin,
                    "estoque_inicial": _as_decimal(evento.get("estoque_inicial")),
                    "estoque_final": _as_decimal(evento.get("estoque_final")),
                    "data_aquis_dev_estoq": _parse_memory_date(evento.get("data")),
                    "qnt_aquis_dev": _as_decimal(evento.get("quantidade")),
                    "numero_nfe": evento.get("numero_nfe"),
                })
            elif tipo_evento == "venda":
                referencias = evento.get("notas_referencia") or [{"tipo": "estoque_inicial"}]
                notas = "; ".join(
                    _formatar_referencia_v2(ref, estoque_inicial)
                    for ref in referencias
                )
                rows.append({
                    "tipo": "v",
                    "codigo_barra": gtin,
                    "periodo_inicial": _parse_memory_date(evento.get("periodo_inicial")),
                    "periodo_final": _parse_memory_date(evento.get("periodo_final")),
                    "periodo_inicial_nao_comprovacao": _parse_memory_date(evento.get("periodo_inicio_irregular")),
                    "estoque_inicial": _as_decimal(evento.get("estoque_inicial")),
                    "estoque_final": _as_decimal(evento.get("estoque_final")),
                    "vendas_periodo": _as_decimal(evento.get("vendas")),
                    "vendas_sem_comprovacao": _as_decimal(evento.get("vendas_sem_comprovacao")),
                    "valor_movimentado": _as_decimal(evento.get("valor")),
                    "valor_sem_comprovacao": _as_decimal(evento.get("valor_sem_comprovacao")),
                    "data_aquis_dev_estoq": None,
                    "qnt_aquis_dev": 0,
                    "numero_nfe": None,
                    "notas": notas,
                })

        resumo = gtin_info.get("summary") or {}
        rows.append({
            "tipo": "s",
            "codigo_barra": gtin,
            "vendas_periodo": _as_decimal(resumo.get("vendas")),
            "vendas_sem_comprovacao": _as_decimal(resumo.get("vendas_sem_comprovacao")),
            "valor_movimentado": _as_decimal(resumo.get("valor")),
            "valor_sem_comprovacao": _as_decimal(resumo.get("valor_sem_comprovacao")),
            "qnt_aquis_dev": 0,
            "data_aquis_dev_estoq": None,
            "numero_nfe": None,
        })
    return rows


def _payload_to_bytes(payload) -> bytes:
    if isinstance(payload, bytes):
        return payload
    if isinstance(payload, bytearray):
        return bytes(payload)
    if isinstance(payload, memoryview):
        return payload.tobytes()
    return bytes(payload)


def _decode_memoria_payload(payload) -> list[dict]:
    json_str_v2 = zlib.decompress(_payload_to_bytes(payload)).decode("utf-8")
    dados_v2 = json.loads(json_str_v2)
    dados = _legacy_rows_from_memoria_v2(dados_v2)

    for item in dados:
        for key in [
            "periodo_inicial",
            "periodo_final",
            "periodo_inicial_nao_comprovacao",
            "data_aquis_dev_estoq",
            "data_estoque_inicial",
            "data_aquisicao",
            "data_devolucao",
        ]:
            if key in item and item[key] and isinstance(item[key], str):
                try:
                    from datetime import datetime as _dt

                    if "T" in item[key]:
                        item[key] = _dt.fromisoformat(item[key]).date()
                    else:
                        item[key] = _dt.strptime(item[key], "%Y-%m-%d").date()
                except Exception:
                    pass

        for key in ["valor_movimentado", "valor_sem_comprovacao"]:
            if key in item and item[key] is not None:
                item[key] = Decimal(str(item[key]))

    return dados


def _load_memoria_sql(cnpj: str, engine) -> tuple[list[dict] | None, dict[str | float, str], float | None]:
    query_time_ms = None
    with engine.connect() as conn:
        _tq0 = _time.perf_counter()
        result = conn.execute(text("""
            SELECT TOP 1
                memoria_calculo_payload,
                schema_version,
                id_processamento
            FROM temp_CGUSC.fp.memoria_calculo_consolidada
            WHERE cnpj = :cnpj
            ORDER BY id_processamento DESC
        """), {"cnpj": cnpj}).fetchone()
        query_time_ms = round((_time.perf_counter() - _tq0) * 1000, 1)

        if not result or not result[0]:
            print(f"Aviso: nenhum dado no banco para CNPJ {cnpj}")
            return None, {}, query_time_ms

        memoria_calculo_payload = result[0]

        med_rows = conn.execute(text("""
            SELECT codigo_barra, principio_ativo
            FROM temp_CGUSC.fp.medicamentos_patologia
        """)).fetchall()
        medicamentos_map = _build_medicamentos_map_from_rows(med_rows)

    return _decode_memoria_payload(memoria_calculo_payload), medicamentos_map, query_time_ms


def _build_memoria_calculo_df(dados: list[dict], medicamentos_map: dict[str | float, str]) -> pl.DataFrame:
    results = copy.deepcopy(dados)

    contador = 0
    for i, item in enumerate(results):
        if item["tipo"] in ("c", "d"):
            contador += 1
        if item["tipo"] in ("s", "h"):
            contador = 0
        if item["tipo"] == "v":
            if item.get("notas"):
                contador = 0
                continue
            lista_nfs = []
            for idx in range(1, contador + 1):
                item_ant = results[i - idx]
                if item_ant["tipo"] == "c":
                    dt = item_ant["data_aquis_dev_estoq"].strftime("%d/%m/%Y") if item_ant.get("data_aquis_dev_estoq") else ""
                    qtd = int(item_ant["qnt_aquis_dev"]) if item_ant.get("qnt_aquis_dev") else 0
                    lista_nfs.append(f"NF Aquisicao: {item_ant.get('numero_nfe', '')} - {dt} | Qtde: {qtd}")
                elif item_ant["tipo"] == "d":
                    dt = item_ant["data_aquis_dev_estoq"].strftime("%d/%m/%Y") if item_ant.get("data_aquis_dev_estoq") else ""
                    qtd = int(item_ant["qnt_aquis_dev"]) if item_ant.get("qnt_aquis_dev") else 0
                    lista_nfs.append(f"NF Transferencia: {item_ant.get('numero_nfe', '')} - {dt} | Qtde: {qtd}")
                elif item_ant["tipo"] == "e":
                    est = int(item_ant.get("estoque_inicial", 0))
                    lista_nfs.append(f"Estoque Inicial Estimado: {est} - 01/07/2015")
            if not lista_nfs:
                for idx in range(i - 1, -1, -1):
                    if results[idx]["tipo"] == "e":
                        est = int(results[idx].get("estoque_inicial", 0))
                        lista_nfs.append(f"Estoque Inicial Estimado: {est} - 01/07/2015")
                        break
                    if results[idx]["tipo"] == "h":
                        break
            results[i]["notas"] = "; ".join(lista_nfs)
            contador = 0

    fmt_date = lambda value: value.strftime("%d/%m/%Y") if value else "-"

    lista_linhas: list[dict] = []
    lista_parcial: list[dict] = []
    numero_vendas_gtin = 0
    ultimo_estoque_valido = 0
    gtin_atual: str | None = None
    medicamento_atual: str | None = None

    for item in results:
        tipo = item["tipo"]

        if tipo == "h":
            numero_vendas_gtin = 0
            codigo = int(item["codigo_barra"])
            gtin_atual = str(codigo)
            medicamento_atual = medicamentos_map.get(float(codigo), "DESCONHECIDO")
            estoque = item.get("estoque_inicial", 0) or 0
            ultimo_estoque_valido = estoque

            lista_parcial.append({
                "tipo_linha": "header_medicamento",
                "gtin": gtin_atual,
                "medicamento": f"{medicamento_atual} (Estoque Inicial: {int(estoque)} un.)",
            })
            lista_parcial.append({"tipo_linha": "header_colunas"})

        elif tipo == "e":
            ultimo_estoque_valido = item.get("estoque_inicial", 0) or 0

        elif tipo == "v":
            ultimo_estoque_valido = item.get("estoque_final", 0) or 0
            tem_irregular = (item.get("valor_sem_comprovacao") or Decimal(0)) > 0
            numero_vendas_gtin += 1

            dt_nc = item.get("periodo_inicial_nao_comprovacao")
            dt_nc_fmt = "-" if (dt_nc is None or str(dt_nc) == "9999-01-01") else fmt_date(dt_nc)

            lista_parcial.append({
                "tipo_linha": "venda_irregular" if tem_irregular else "venda_normal",
                "gtin": gtin_atual,
                "medicamento": medicamento_atual,
                "periodo_inicial": fmt_date(item.get("periodo_inicial")),
                "periodo_inicio_irregular": dt_nc_fmt,
                "periodo_final": fmt_date(item.get("periodo_final")),
                "estoque_inicial": int(item.get("estoque_inicial") or 0),
                "estoque_final": int(item.get("estoque_final") or 0),
                "vendas": int(item.get("vendas_periodo") or 0),
                "vendas_irregular": int(item.get("vendas_sem_comprovacao") or 0),
                "valor": float(Decimal(str(item.get("valor_movimentado") or 0)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)),
                "valor_irregular": float(Decimal(str(item.get("valor_sem_comprovacao") or 0)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)),
                "notas": item.get("notas", ""),
            })

        elif tipo in ("c", "d"):
            ultimo_estoque_valido = item.get("estoque_final", 0) or 0

        elif tipo == "s":
            estoque_visual = int(ultimo_estoque_valido)
            for item_rev in reversed(lista_parcial):
                if item_rev.get("estoque_final") is not None:
                    estoque_visual = item_rev["estoque_final"]
                    break

            lista_parcial.append({
                "tipo_linha": "resumo_parcial",
                "gtin": gtin_atual,
                "medicamento": medicamento_atual,
                "periodo_inicial": "Resumo Parcial",
                "estoque_final": estoque_visual,
                "vendas": int(item.get("vendas_periodo") or 0),
                "vendas_irregular": int(item.get("vendas_sem_comprovacao") or 0),
                "valor": float(Decimal(str(item.get("valor_movimentado") or 0)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)),
                "valor_irregular": float(Decimal(str(item.get("valor_sem_comprovacao") or 0)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)),
            })

            if numero_vendas_gtin > 0:
                lista_linhas.extend(copy.deepcopy(lista_parcial))

            lista_parcial.clear()
            numero_vendas_gtin = 0

    schema_cols = [
        "tipo_linha",
        "gtin",
        "medicamento",
        "periodo_inicial",
        "periodo_inicio_irregular",
        "periodo_final",
        "estoque_inicial",
        "estoque_final",
        "vendas",
        "vendas_irregular",
        "valor",
        "valor_irregular",
        "notas",
    ]

    for row in lista_linhas:
        for col in schema_cols:
            row.setdefault(col, None)

    if not lista_linhas:
        return pl.DataFrame([])

    return (
        pl.DataFrame(lista_linhas)
        .select(schema_cols)
        .with_columns([
            pl.col("estoque_inicial").cast(pl.Int64, strict=False),
            pl.col("estoque_final").cast(pl.Int64, strict=False),
            pl.col("vendas").cast(pl.Int64, strict=False),
            pl.col("vendas_irregular").cast(pl.Int64, strict=False),
            pl.col("valor").cast(pl.Float64, strict=False),
            pl.col("valor_irregular").cast(pl.Float64, strict=False),
        ])
    )


def _load_memoria_from_global(cnpj: str) -> tuple[pl.DataFrame | None, float | None]:
    global_path = _global_cache_path()
    if not os.path.exists(global_path):
        return None, None

    from data_cache import scan_memoria_calculo_global

    t0 = _time.perf_counter()
    row_df = (
        scan_memoria_calculo_global()
        .filter(pl.col("cnpj") == cnpj)
        .select([
            "cnpj",
            "memoria_calculo_payload",
            "_memoria_calculo_cache_version",
        ])
        .collect()
    )
    read_time_ms = round((_time.perf_counter() - t0) * 1000, 1)

    if row_df.is_empty():
        return pl.DataFrame([]), read_time_ms

    version = int(row_df.item(0, "_memoria_calculo_cache_version") or 0)
    if version < MEMORIA_CALCULO_CACHE_VERSION:
        raise RuntimeError(
            f"{MEMORIA_CALCULO_GLOBAL_PARQUET} esta na versao {version}; "
            f"esperado {MEMORIA_CALCULO_CACHE_VERSION}."
        )

    payload = row_df.item(0, "memoria_calculo_payload")
    dados = _decode_memoria_payload(payload)
    medicamentos_map = _load_medicamentos_map_from_cache()
    return _build_memoria_calculo_df(dados, medicamentos_map), read_time_ms


def load_or_sync_memoria_calculo(cnpj: str, engine, check_cache: bool = False) -> CacheLoadResult:
    cache_path = _cache_path(cnpj)

    if os.path.exists(cache_path):
        try:
            t0 = _time.perf_counter()
            df_cached = pl.read_parquet(cache_path)
            read_time_ms = round((_time.perf_counter() - t0) * 1000, 1)
            return CacheLoadResult(df_cached, from_cache=True, read_time_ms=read_time_ms)
        except Exception as exc:
            print(f"[ CACHE ] {cnpj} - MOVIMENTACAO - erro de leitura ({exc})")

    if check_cache:
        return CacheLoadResult(pl.DataFrame([]), from_cache=False)

    try:
        df_global, read_time_ms = _load_memoria_from_global(cnpj)
        if df_global is not None:
            if not df_global.is_empty():
                save_time_ms = None
                try:
                    t1 = _time.perf_counter()
                    df_global.write_parquet(cache_path, compression="zstd")
                    save_time_ms = round((_time.perf_counter() - t1) * 1000, 1)
                    print(f"Cache Parquet salvo a partir do global: {cache_path}")
                except Exception as exc:
                    print(f"Erro ao salvar Parquet de memoria de calculo para {cnpj}: {exc}")
                    print(traceback.format_exc())
                return CacheLoadResult(
                    df_global,
                    from_cache=True,
                    read_time_ms=read_time_ms,
                    save_time_ms=save_time_ms,
                )
            print(f"Aviso: memoria_calculo_global sem registro para CNPJ {cnpj}")
            return CacheLoadResult(pl.DataFrame([]), from_cache=True, read_time_ms=read_time_ms)
    except FileNotFoundError:
        pass
    except Exception as exc:
        return CacheLoadResult(
            pl.DataFrame([]),
            from_cache=False,
            error=f"Modulo global {MEMORIA_CALCULO_GLOBAL_PARQUET} invalido: {exc}",
        )

    try:
        dados, medicamentos_map, query_time_ms = _load_memoria_sql(cnpj, engine)
    except (SQLAInterfaceError, Exception):
        print(f"[ ANALYTICS ] {cnpj} - MOVIMENTACAO - indisponivel (sem cache e banco offline)")
        return CacheLoadResult(
            pl.DataFrame([]),
            from_cache=False,
            error="Arquivo Parquet local nao encontrado e Banco Offline.",
        )

    if dados is None:
        return CacheLoadResult(pl.DataFrame([]), from_cache=False, query_time_ms=query_time_ms)

    df_result = _build_memoria_calculo_df(dados, medicamentos_map)
    save_time_ms = None

    if not df_result.is_empty():
        try:
            t1 = _time.perf_counter()
            df_result.write_parquet(cache_path, compression="zstd")
            save_time_ms = round((_time.perf_counter() - t1) * 1000, 1)
            print(f"Cache Parquet salvo: {cache_path}")
        except Exception as exc:
            print(f"Erro ao salvar Parquet de memoria de calculo para {cnpj}: {exc}")
            print(traceback.format_exc())

    return CacheLoadResult(
        df_result,
        from_cache=False,
        query_time_ms=query_time_ms,
        save_time_ms=save_time_ms,
    )
