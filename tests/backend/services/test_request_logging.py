"""Request logging tests capture structured events without writing to the repo."""

from urllib.parse import parse_qsl, urlsplit
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from loguru import logger
from pydantic import ValidationError
from starlette.requests import Request

import request_logging


def _request(url: str) -> Request:
    parsed = urlsplit(url)
    path = parsed.path or "/"
    query = "&".join(f"{key}={value}" for key, value in parse_qsl(parsed.query))
    return Request({
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": path,
        "raw_path": path.encode(),
        "query_string": query.encode(),
        "headers": [],
        "client": ("testclient", 1234),
        "server": ("testserver", 80),
        "root_path": "",
    })


def test_request_logging_helpers_only_select_detail_and_root_cnpj_calls():
    assert request_logging._project_root() == Path(request_logging.__file__).resolve().parent.parent
    detail = _request("/api/v1/analytics/cnpj/00112233000144/status?uf=SC&regiao_id=42")
    root = _request("/api/v1/analytics/resumo?cnpj_raiz=00112233&data_inicio=2024-01-01&ignored=x")
    summary = _request("/api/v1/analytics/resumo?uf=SC")

    assert request_logging._should_log_request(detail)
    assert request_logging._extract_cnpj(detail) == "00112233000144"
    assert request_logging._query_params(detail) == {"uf": "SC", "regiao_id": "42"}
    assert request_logging._should_log_request(root)
    assert request_logging._extract_cnpj(root) == "00112233"
    assert request_logging._query_params(root) == {"data_inicio": "2024-01-01", "cnpj_raiz": "00112233"}
    assert not request_logging._should_log_request(summary)
    assert request_logging._extract_cnpj(summary) == "-"


def test_request_middleware_logs_success_errors_and_skips_unrelated_routes(monkeypatch, tmp_path):
    original_root = request_logging._project_root
    original_sink = request_logging._REQUEST_SINK_ID
    request_logging._project_root = lambda: tmp_path
    request_logging._REQUEST_SINK_ID = None
    events = []
    capture_id = logger.add(
        lambda message: events.append(str(message)),
        filter=lambda record: record["extra"].get("sentinela_log") == "request_timing",
    )
    configured_sink = None
    try:
        app = FastAPI()
        request_logging.configure_request_timing_logger(app)

        @app.get("/api/v1/analytics/cnpj/{cnpj}/status")
        def cnpj_status(cnpj: str):
            return {"cnpj": cnpj}

        @app.get("/api/v1/analytics/resumo")
        def summary(cnpj_raiz: str | None = None):
            if cnpj_raiz == "falha":
                raise RuntimeError("falha analítica controlada")
            return {"cnpj_raiz": cnpj_raiz}

        @app.get("/health")
        def health():
            return {"status": "ok"}

        configured_sink = request_logging._REQUEST_SINK_ID
        with TestClient(app, raise_server_exceptions=False) as client:
            good = client.get(
                "/api/v1/analytics/cnpj/00112233000144/status",
                params={"scope": "regiao", "metric": "risco", "ignored": "secret"},
            )
            skipped = client.get("/health")
            failed = client.get("/api/v1/analytics/resumo", params={"cnpj_raiz": "falha", "uf": "SC"})

        assert good.status_code == 200
        assert skipped.status_code == 200
        assert failed.status_code == 500
        assert len(events) == 2
        assert "cnpj=00112233000144" in events[0]
        assert "status=200" in events[0]
        assert "'scope': 'regiao'" in events[0]
        assert "ignored" not in events[0]
        assert "cnpj=falha" in events[1]
        assert "status=500" in events[1]
        assert "RuntimeError: falha analítica controlada" in events[1]
        assert (tmp_path / "logs" / "cnpj_detail_requests.log").exists()
    finally:
        logger.remove(capture_id)
        if configured_sink is not None:
            logger.remove(configured_sink)
        request_logging._REQUEST_SINK_ID = original_sink
        request_logging._project_root = original_root


def test_frontend_performance_event_validates_and_writes_structured_log(monkeypatch, tmp_path):
    original_root = request_logging._project_root
    original_sink = request_logging._FRONTEND_SINK_ID
    request_logging._project_root = lambda: tmp_path
    request_logging._FRONTEND_SINK_ID = None
    events = []
    capture_id = logger.add(
        lambda message: events.append(str(message)),
        filter=lambda record: record["extra"].get("sentinela_log") == "frontend_perf",
    )
    configured_sink = None
    try:
        event = request_logging.FrontendPerformanceEvent(
            cnpj="00112233000144",
            event="aba_diagnostico",
            elapsed_ms=127.35,
            session_id="sessao-1",
            detail={"tab": "risk", "attempt": 2},
        )
        result = request_logging.log_frontend_performance(event)
        configured_sink = request_logging._FRONTEND_SINK_ID

        assert result == {"ok": True}
        assert len(events) == 1
        assert "session=sessao-1" in events[0]
        assert "cnpj=00112233000144" in events[0]
        assert "evento=aba_diagnostico" in events[0]
        assert "tempo_ms=127.35" in events[0]
        assert (tmp_path / "logs" / "cnpj_detail_frontend.log").exists()

        with pytest.raises(ValidationError):
            request_logging.FrontendPerformanceEvent(
                cnpj="", event="", elapsed_ms=-1, session_id="", detail={},
            )
    finally:
        logger.remove(capture_id)
        if configured_sink is not None:
            logger.remove(configured_sink)
        request_logging._FRONTEND_SINK_ID = original_sink
        request_logging._project_root = original_root
