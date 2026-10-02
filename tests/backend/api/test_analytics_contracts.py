"""HTTP contracts for analytics endpoints, isolated from SQL Server and app startup."""

from datetime import date
from unittest.mock import Mock

import polars as pl
import pytest


pytestmark = [pytest.mark.backend, pytest.mark.contract]


def test_summary_requires_sections_and_forwards_id_based_territory(
    analytics_api,
    isolated_db_session,
    mock_analytics_service,
):
    response_payload = {
        "kpis": [
            {
                "id": "valor_total",
                "label": "Valor total",
                "value": "R$ 100,00",
                "color": "blue",
                "icon": "pi pi-chart-bar",
            }
        ],
        "resultado_sentinela_uf": [{"uf": "SP", "cnpjs": 1}],
    }
    service_mock = mock_analytics_service("get_dashboard_data", response_payload)

    response = analytics_api.get(
        "/api/v1/analytics/resumo",
        params=[
            ("secoes", "kpis"),
            ("secoes", "ufs"),
            ("data_inicio", "2025-01-01"),
            ("uf", "SP"),
            ("regiao_id", "1234"),
            ("id_ibge7", "3509502"),
        ],
    )

    assert response.status_code == 200
    assert response.json()["kpis"][0]["id"] == "valor_total"
    assert response.json()["resultado_sentinela_uf"][0]["uf"] == "SP"

    service_mock.assert_called_once()
    args, kwargs = service_mock.call_args
    assert args[0] is isolated_db_session
    assert args[1] == date(2025, 1, 1)
    assert args[3] == "SP"
    assert kwargs["regiao_id"] == 1234
    assert kwargs["id_ibge7"] == 3509502
    assert kwargs["secoes"] == ["kpis", "ufs"]
    assert kwargs["filtros"].perc_min is None


def test_summary_rejects_textual_region_or_municipality_filters(
    analytics_api,
    mock_analytics_service,
):
    service_mock = mock_analytics_service("get_dashboard_data", {})

    for legacy_filter in ("regiao_saude=Regiao+de+Saude", "municipio=Campinas"):
        response = analytics_api.get(
            f"/api/v1/analytics/resumo?secoes=kpis&{legacy_filter}"
        )
        assert response.status_code == 400

    service_mock.assert_not_called()


def test_summary_requires_secoes(analytics_api, mock_analytics_service):
    service_mock = mock_analytics_service("get_dashboard_data", {})

    response = analytics_api.get("/api/v1/analytics/resumo")

    assert response.status_code == 422
    service_mock.assert_not_called()


def test_summary_rejects_non_numeric_id_ibge7(
    analytics_api,
    mock_analytics_service,
):
    service_mock = mock_analytics_service("get_dashboard_data", {})

    response = analytics_api.get(
        "/api/v1/analytics/resumo?secoes=kpis&id_ibge7=Campinas"
    )

    assert response.status_code == 422
    service_mock.assert_not_called()


def test_regional_benchmarking_forwards_region_id(
    analytics_api,
    mock_analytics_service,
):
    response_payload = {
        "nome_regiao": "Regiao de Saude",
        "id_regiao": "1234",
        "municipios": [{"uf": "SP", "municipio": "Campinas", "id_ibge7": 3509502}],
        "farmacias": [],
    }
    service_mock = mock_analytics_service("get_regional_benchmarking", response_payload)

    response = analytics_api.get(
        "/api/v1/analytics/regional-benchmarking",
        params={"uf": "SP", "regiao_id": 1234},
    )

    assert response.status_code == 200
    assert response.json()["id_regiao"] == "1234"
    assert response.json()["municipios"][0]["id_ibge7"] == 3509502
    service_mock.assert_called_once_with(
        uf="SP",
        data_inicio=None,
        data_fim=None,
        regiao_id=1234,
    )


def test_indicadores_analise_forwards_id_based_territory(
    analytics_api,
    mock_analytics_service,
):
    response_payload = {
        "indicador": "teto",
        "kpis": {"total_critico": 1},
        "municipios": [{"municipio": "Campinas", "uf": "SP", "id_ibge7": 3509502}],
    }
    service_mock = mock_analytics_service("get_indicadores_analise", response_payload)

    response = analytics_api.get(
        "/api/v1/analytics/indicadores-analise",
        params={"indicador": "teto", "regiao_id": 1234, "id_ibge7": 3509502},
    )

    assert response.status_code == 200
    assert response.json()["indicador"] == "teto"
    assert response.json()["kpis"]["total_critico"] == 1
    assert response.json()["municipios"][0]["id_ibge7"] == 3509502

    args, kwargs = service_mock.call_args
    assert args[0] == "teto"
    assert kwargs["regiao_id"] == 1234
    assert kwargs["id_ibge7"] == 3509502


def test_indicadores_analise_rejects_textual_region_or_municipality_filters(
    analytics_api,
    mock_analytics_service,
):
    service_mock = mock_analytics_service("get_indicadores_analise", {})

    for legacy_filter in ("regiao_saude=Regiao+de+Saude", "municipio=Campinas"):
        response = analytics_api.get(
            f"/api/v1/analytics/indicadores-analise?indicador=teto&{legacy_filter}"
        )
        assert response.status_code == 400

    service_mock.assert_not_called()


def test_cnpj_status_validates_using_mocked_cache(
    analytics_api,
    monkeypatch,
):
    from api.services.analytics import AnalyticsService
    from api.services.analytics import farmacia as farmacia_service

    cached_pharmacies = pl.DataFrame(
        {
            "cnpj": ["11222333000181"],
            "razao_social": ["Farmacia Exemplo Ltda"],
            "nome_fantasia": ["Farmacia Exemplo"],
            "municipio": ["Campinas"],
            "uf": ["SP"],
        }
    )
    cache_mock = Mock(name="get_df_dados_farmacia", return_value=cached_pharmacies)
    monkeypatch.setattr(farmacia_service, "get_df_dados_farmacia", cache_mock)

    actual_service = AnalyticsService.get_cnpj_access_status
    service_spy = Mock(name="AnalyticsService.get_cnpj_access_status", wraps=actual_service)
    monkeypatch.setattr(AnalyticsService, "get_cnpj_access_status", service_spy)

    response = analytics_api.get("/api/v1/analytics/cnpj/11222333000181/status")

    assert response.status_code == 200
    assert response.json() == {
        "cnpj": "11222333000181",
        "status": "valid",
        "in_program": True,
        "razao_social": "Farmacia Exemplo Ltda",
        "nome_fantasia": "Farmacia Exemplo",
        "municipio": "Campinas",
        "uf": "SP",
    }
    service_spy.assert_called_once_with("11222333000181")
    cache_mock.assert_called_once_with()


def test_cnpj_status_rejects_invalid_format_before_reading_cache(
    analytics_api,
    monkeypatch,
):
    from api.services.analytics import AnalyticsService
    from api.services.analytics import farmacia as farmacia_service

    cache_mock = Mock(name="get_df_dados_farmacia")
    monkeypatch.setattr(farmacia_service, "get_df_dados_farmacia", cache_mock)
    actual_service = AnalyticsService.get_cnpj_access_status
    service_spy = Mock(name="AnalyticsService.get_cnpj_access_status", wraps=actual_service)
    monkeypatch.setattr(AnalyticsService, "get_cnpj_access_status", service_spy)

    response = analytics_api.get("/api/v1/analytics/cnpj/123/status")

    assert response.status_code == 422
    assert response.json()["detail"]["status"] == "invalid_format"
    service_spy.assert_called_once_with("123")
    cache_mock.assert_not_called()


def test_cnpj_status_returns_not_found_for_valid_format_missing_from_cache(
    analytics_api,
    monkeypatch,
):
    from api.services.analytics import AnalyticsService
    from api.services.analytics import farmacia as farmacia_service

    cached_pharmacies = pl.DataFrame(schema={"cnpj": pl.String})
    cache_mock = Mock(name="get_df_dados_farmacia", return_value=cached_pharmacies)
    monkeypatch.setattr(farmacia_service, "get_df_dados_farmacia", cache_mock)
    actual_service = AnalyticsService.get_cnpj_access_status
    service_spy = Mock(name="AnalyticsService.get_cnpj_access_status", wraps=actual_service)
    monkeypatch.setattr(AnalyticsService, "get_cnpj_access_status", service_spy)

    response = analytics_api.get("/api/v1/analytics/cnpj/00000000000000/status")

    assert response.status_code == 404
    assert response.json()["detail"]["status"] == "not_in_program"
    service_spy.assert_called_once_with("00000000000000")
    cache_mock.assert_called_once_with()
