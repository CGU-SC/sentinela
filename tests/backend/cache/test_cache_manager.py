from pathlib import Path
from types import SimpleNamespace

import pytest

import cache_manager
import cache_registry


def test_load_callable_resolves_registered_import_path():
    producer = cache_manager._load_callable(
        "cache_producers.financeiro.load_or_sync_movimentacao_mensal_gtin"
    )

    assert producer.__name__ == "load_or_sync_movimentacao_mensal_gtin"
    assert producer.__module__ == "cache_producers.financeiro"


def test_sync_cnpj_cache_returns_result_and_surfaces_producer_errors(monkeypatch):
    calls = []

    def producer(cnpj, engine):
        calls.append((cnpj, engine))
        return SimpleNamespace(error=None, rows=3)

    monkeypatch.setattr(
        cache_registry,
        "get_cnpj_cache_definition",
        lambda key: SimpleNamespace(producer="cache_producers.fake.build"),
    )
    monkeypatch.setattr(cache_manager, "_load_callable", lambda path: producer)
    sentinel_engine = object()

    result = cache_manager.sync_cnpj_cache("crm_prescritores", "123", sentinel_engine)

    assert result.rows == 3
    assert calls == [("123", sentinel_engine)]

    monkeypatch.setattr(
        cache_manager,
        "_load_callable",
        lambda path: lambda cnpj, engine: SimpleNamespace(error="fonte inválida"),
    )
    with pytest.raises(RuntimeError, match="crm_prescritores: fonte inválida"):
        cache_manager.sync_cnpj_cache("crm_prescritores", "123", sentinel_engine)


def test_sync_cnpj_cache_requires_registered_producer(monkeypatch):
    monkeypatch.setattr(
        cache_registry,
        "get_cnpj_cache_definition",
        lambda key: SimpleNamespace(producer=None),
    )

    with pytest.raises(RuntimeError, match="Cache CNPJ sem produtor registrado: sem_produtor"):
        cache_manager.sync_cnpj_cache("sem_produtor", "123", object())


def test_sync_cnpj_producers_runs_each_distinct_producer_once_and_stops_on_error(monkeypatch):
    definitions = (
        SimpleNamespace(key="network_n2", producer="module.network.sync"),
        SimpleNamespace(key="network_n3", producer="module.network.sync"),
        SimpleNamespace(key="financeiro", producer="module.financeiro.sync"),
        SimpleNamespace(key="sem_produtor", producer=None),
    )
    monkeypatch.setattr(cache_registry, "CNPJ_CACHE_DEFINITIONS", definitions)
    calls = []

    def resolve(path):
        def producer(cnpj, engine):
            calls.append((path, cnpj, engine))
            return SimpleNamespace(error=None)

        return producer

    monkeypatch.setattr(cache_manager, "_load_callable", resolve)
    engine = object()

    synced = cache_manager.sync_cnpj_producers("456", engine)

    assert synced == ["network_n2", "financeiro"]
    assert calls == [
        ("module.network.sync", "456", engine),
        ("module.financeiro.sync", "456", engine),
    ]

    monkeypatch.setattr(
        cache_manager,
        "_load_callable",
        lambda path: lambda cnpj, engine: SimpleNamespace(error="falhou"),
    )
    with pytest.raises(RuntimeError, match="network_n2: falhou"):
        cache_manager.sync_cnpj_producers("456", engine)


def test_list_missing_cnpj_modules_reports_only_absent_registered_files(tmp_path, monkeypatch):
    monkeypatch.setattr(
        cache_registry,
        "get_cnpj_parquet_files",
        lambda: ("presente.smod", "ausente.smod"),
    )
    monkeypatch.setattr(
        "data_cache.get_cnpj_cache_root",
        lambda: str(tmp_path),
    )
    cnpj_dir = tmp_path / "12345678000195"
    cnpj_dir.mkdir()
    (cnpj_dir / "presente.smod").write_bytes(b"parquet-fixture")

    assert cache_manager.list_missing_cnpj_modules("12345678000195") == ["ausente.smod"]
    assert (cnpj_dir / "presente.smod").read_bytes() == b"parquet-fixture"


def test_sync_cnpj_caches_trims_inputs_and_reports_progress(monkeypatch):
    calls = []
    progress = []
    monkeypatch.setattr(
        cache_manager,
        "sync_cnpj_producers",
        lambda cnpj, engine: calls.append(cnpj) or [],
    )
    monkeypatch.setattr(cache_manager, "list_missing_cnpj_modules", lambda cnpj: [])

    cache_manager.sync_cnpj_caches(
        object(),
        [" 111 ", "", " 222"],
        progress.append,
    )

    assert calls == ["111", "222"]
    assert progress == [50, 100, 100]


def test_sync_cnpj_caches_empty_input_finishes_without_producer_calls(monkeypatch):
    calls = []
    progress = []
    monkeypatch.setattr(
        cache_manager,
        "sync_cnpj_producers",
        lambda *args: calls.append(args),
    )

    cache_manager.sync_cnpj_caches(object(), [" ", ""], progress.append)

    assert calls == []
    assert progress == [100]


def test_sync_cnpj_caches_reports_modules_that_remain_missing(monkeypatch, capsys):
    monkeypatch.setattr(cache_manager, "sync_cnpj_producers", lambda *_args: [])
    monkeypatch.setattr(cache_manager, "list_missing_cnpj_modules", lambda _cnpj: ["parquet-a.smod"])
    progress = []

    cache_manager.sync_cnpj_caches(object(), ["123"], progress.append)

    assert "Aviso: modulos faltantes: parquet-a.smod" in capsys.readouterr().out
    assert progress == [100, 100]
