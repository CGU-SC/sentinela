"""Application startup, static serving, health checks, and DB session cleanup."""

import importlib
import json
import runpy
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import uvicorn
from fastapi import HTTPException
from fastapi.testclient import TestClient
from loguru import logger

import database
import request_logging
from api.endpoints import cache as cache_endpoints


@pytest.fixture(scope="module")
def main_module(tmp_path_factory):
    """Import the real app while directing its request log sink to a temp tree."""
    original_root = request_logging._project_root
    original_sink = request_logging._REQUEST_SINK_ID
    log_root = tmp_path_factory.mktemp("sentinela-app-logs")
    request_logging._REQUEST_SINK_ID = None
    request_logging._project_root = lambda: log_root
    main = importlib.import_module("main")
    configured_sink = request_logging._REQUEST_SINK_ID
    try:
        yield main
    finally:
        if configured_sink is not None:
            logger.remove(configured_sink)
        request_logging._REQUEST_SINK_ID = original_sink
        request_logging._project_root = original_root


def _started_client(main, monkeypatch, *, db_session=None):
    load_cache = Mock()
    initialize = Mock()
    scheduled = []

    class Loop:
        def run_in_executor(self, executor, callback):
            scheduled.append((executor, callback))
            return None

    monkeypatch.setattr(main, "load_cache", load_cache)
    monkeypatch.setattr(main, "initialize_update_check", initialize)
    monkeypatch.setattr(main, "asyncio", SimpleNamespace(get_event_loop=lambda: Loop()))
    if db_session is None:
        db_session = SimpleNamespace(
            execute=lambda _statement: SimpleNamespace(fetchone=lambda: (1,))
        )
    main.app.dependency_overrides[database.get_db] = lambda: db_session
    client = TestClient(main.app)
    return client, load_cache, initialize, scheduled


def test_product_version_reads_dev_and_frozen_locations_and_fails_to_visible_default(main_module, monkeypatch, tmp_path):
    main = main_module
    project_version = json.loads((Path(main.__file__).parent.parent / "version.json").read_text(encoding="utf-8"))["version"]
    assert main._read_product_version() == project_version

    bundle = tmp_path / "bundle"
    bundle.mkdir()
    (bundle / "version.json").write_text('{"version": "9.8.7"}', encoding="utf-8")
    monkeypatch.setattr(main.sys, "frozen", True, raising=False)
    monkeypatch.setattr(main.sys, "_MEIPASS", str(bundle), raising=False)
    assert main._read_product_version() == "9.8.7"

    monkeypatch.setattr(main.json, "loads", lambda _raw: (_ for _ in ()).throw(ValueError("bad json")))
    assert main._read_product_version() == "0.0.0"


def test_lifespan_preloads_cache_and_schedules_remote_check_without_waiting(main_module, monkeypatch):
    main = main_module
    monkeypatch.setattr(cache_endpoints, "get_cache_status", lambda: {"status": "ready"})
    client, load_cache, initialize, scheduled = _started_client(main, monkeypatch)
    with client:
        response = client.get("/api/v1/cache/status")

    assert response.status_code == 200
    assert response.json() == {"status": "ready"}
    load_cache.assert_called_once_with(main.engine)
    initialize.assert_called_once_with()
    assert len(scheduled) == 1
    executor, callback = scheduled[0]
    assert executor is None
    assert callback is main.check_for_updates


def test_health_endpoint_reports_database_result_and_failure(main_module, monkeypatch):
    main = main_module
    session = Mock()
    session.execute.return_value.fetchone.return_value = (1,)
    response = main.testar_conexao(session)
    assert response == {"status": "Database OK", "timestamp": "Conexão está ativa"}
    session.execute.assert_called_once()
    assert str(session.execute.call_args.args[0]) == "SELECT 1"

    broken_session = Mock()
    broken_session.execute.side_effect = OSError("SQL Server indisponível")
    with pytest.raises(HTTPException) as error:
        main.testar_conexao(broken_session)
    assert error.value.status_code == 500
    assert error.value.detail == "Erro de conexão: SQL Server indisponível"


def test_frontend_root_file_and_history_fallback(main_module, monkeypatch):
    main = main_module
    client, *_ = _started_client(main, monkeypatch)
    with client:
        root = client.get("/")
        existing_file = client.get("/index.html")
        history_route = client.get("/estabelecimentos/00000000000001")

    assert root.status_code == 200
    assert "<html" in root.text.lower()
    assert existing_file.status_code == 200
    assert existing_file.content == root.content
    assert history_route.status_code == 200
    assert history_route.content == root.content


def test_database_session_dependency_closes_after_success_and_exception(monkeypatch):
    session = Mock()
    monkeypatch.setattr(database, "SessionLocal", Mock(return_value=session))

    generator = database.get_db()
    assert next(generator) is session
    with pytest.raises(StopIteration):
        next(generator)
    session.close.assert_called_once_with()

    failed_session = Mock()
    monkeypatch.setattr(database, "SessionLocal", Mock(return_value=failed_session))
    generator = database.get_db()
    assert next(generator) is failed_session
    with pytest.raises(RuntimeError, match="request failed"):
        generator.throw(RuntimeError("request failed"))
    failed_session.close.assert_called_once_with()


def test_frozen_import_without_frontend_reports_missing_build(main_module, monkeypatch, tmp_path, capsys):
    main = main_module
    monkeypatch.setattr(main.sys, "frozen", True, raising=False)
    monkeypatch.setattr(main.sys, "_MEIPASS", str(tmp_path), raising=False)

    importlib.reload(main)
    output = capsys.readouterr().out

    assert main.BASE_DIR == str(tmp_path)
    assert main.FRONTEND_PATH == str(tmp_path / "frontend" / "dist")
    assert "Pasta frontend/dist nao encontrada" in output
    assert not (tmp_path / "frontend" / "dist").exists()


def test_script_entrypoint_passes_api_to_uvicorn_without_starting_server(main_module, monkeypatch):
    run_server = Mock()
    monkeypatch.setattr(uvicorn, "run", run_server)

    namespace = runpy.run_path(str(Path(main_module.__file__)), run_name="__main__")

    run_server.assert_called_once_with(namespace["app"], host="127.0.0.1", port=8002)
