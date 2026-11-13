"""Orquestracao central dos caches por CNPJ."""

from collections.abc import Callable, Iterable
import importlib
import os
from typing import Any

import cache_registry
import cnpj_cache_versao


CacheProducer = Callable[[str, Any], Any]


def _load_callable(path: str) -> CacheProducer:
    module_name, function_name = path.rsplit(".", 1)
    module = importlib.import_module(module_name)
    return getattr(module, function_name)


def _get_cnpj_cache_dir(cnpj: str) -> str:
    return cnpj_cache_versao.get_cnpj_cache_dir(cnpj)


def sync_cnpj_cache(key: str, cnpj: str, engine) -> Any:
    definition = cache_registry.get_cnpj_cache_definition(key)
    if not definition.producer:
        raise RuntimeError(f"Cache CNPJ sem produtor registrado: {key}")
    result = _load_callable(definition.producer)(cnpj, engine)
    result_error = getattr(result, "error", None)
    if result_error:
        raise RuntimeError(f"{key}: {result_error}")
    return result


def sync_cnpj_producers(cnpj: str, engine) -> list[str]:
    synced: list[str] = []
    seen_producers: set[str] = set()

    for definition in cache_registry.CNPJ_CACHE_DEFINITIONS:
        producer = definition.producer
        if not producer or producer in seen_producers:
            continue

        seen_producers.add(producer)
        print(f"    - {definition.key}...", end="", flush=True)
        result = _load_callable(producer)(cnpj, engine)
        result_error = getattr(result, "error", None)
        if result_error:
            print(f" erro: {result_error}")
            raise RuntimeError(f"{definition.key}: {result_error}")

        print(" ok")
        synced.append(definition.key)

    return synced


def list_missing_cnpj_modules(cnpj: str) -> list[str]:
    cnpj_dir = _get_cnpj_cache_dir(cnpj)
    expected_files = cache_registry.get_cnpj_parquet_files()
    return [
        filename for filename in expected_files
        if not os.path.exists(os.path.join(cnpj_dir, filename))
    ]


def sync_cnpj_caches(engine, cnpjs: Iterable[str], progress_callback=None) -> None:
    cnpjs = [cnpj.strip() for cnpj in cnpjs if cnpj.strip()]
    total = len(cnpjs)
    print(f"Sincronizando todos os modulos por CNPJ para {total} estabelecimento(s)...")

    if total == 0:
        if progress_callback:
            progress_callback(100)
        return

    for index, cnpj in enumerate(cnpjs, 1):
        print(f"\n  [{index}/{total}] CNPJ {cnpj}")

        sync_cnpj_producers(cnpj, engine)
        still_missing = list_missing_cnpj_modules(cnpj)
        if still_missing:
            print(f"    Aviso: modulos faltantes: {', '.join(still_missing)}")

        if progress_callback:
            progress_callback(int((index / total) * 100))

    if progress_callback:
        progress_callback(100)
