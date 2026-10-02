"""Fixtures for backend API tests without the production application lifespan."""

from __future__ import annotations

import sys
from pathlib import Path
from collections.abc import Iterator
from unittest.mock import Mock

import polars as pl
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


PROJECT_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = PROJECT_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


@pytest.fixture(autouse=True)
def lista_mais_medicos_vazia(monkeypatch: pytest.MonkeyPatch) -> None:
    """O cruzamento com o Mais Medicos le um modulo baixado da API do Ministerio
    da Saude; a suite nao depende dele (testes que precisam o substituem)."""
    import mais_medicos

    monkeypatch.setattr(
        "api.services.analytics.crm_mais_medicos.get_mais_medicos_df",
        lambda: pl.DataFrame(schema=mais_medicos.SCHEMA),
    )


@pytest.fixture
def isolated_db_session() -> Mock:
    """A sentinel session object; no SQLAlchemy engine or database is used."""
    return Mock(name="isolated_db_session")


@pytest.fixture
def analytics_api(isolated_db_session: Mock) -> Iterator[TestClient]:
    """Mount only analytics routes in an app with no production lifespan."""
    from api.endpoints.analytics import router as analytics_router
    from database import get_db

    app = FastAPI()
    app.include_router(analytics_router, prefix="/api/v1/analytics")
    app.dependency_overrides[get_db] = lambda: isolated_db_session

    with TestClient(app) as client:
        yield client


@pytest.fixture
def mock_analytics_service(monkeypatch: pytest.MonkeyPatch):
    """Replace a named AnalyticsService operation with an explicit response mock."""
    from api.services.analytics import AnalyticsService

    def install(method_name: str, response: object) -> Mock:
        service_mock = Mock(name=f"AnalyticsService.{method_name}", return_value=response)
        monkeypatch.setattr(AnalyticsService, method_name, service_mock)
        return service_mock

    return install
