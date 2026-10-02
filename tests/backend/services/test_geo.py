"""Small Polars fixtures for the geospatial cache transformations."""

from datetime import date
from unittest.mock import Mock

import polars as pl
import pytest
from fastapi import HTTPException

from api.services import geo
from api.services.geo import GeoService


def test_localidades_maps_all_contract_fields(monkeypatch):
    source = pl.DataFrame({
        "sg_uf": ["SC"],
        "no_regiao_saude": ["Grande Florianópolis"],
        "id_regiao_saude": [4201],
        "no_municipio": ["Florianópolis"],
        "id_ibge7": [4205407],
        "nu_populacao": [537211],
        "unidade_pf": ["Regional Sul"],
    })
    monkeypatch.setattr(geo, "get_localidades_df", lambda: source)

    response = GeoService.get_localidades(object())

    assert len(response.localidades) == 1
    row = response.localidades[0]
    assert row.model_dump() == {
        "sg_uf": "SC",
        "no_regiao_saude": "Grande Florianópolis",
        "id_regiao_saude": 4201,
        "no_municipio": "Florianópolis",
        "id_ibge7": 4205407,
        "nu_populacao": 537211,
        "unidade_pf": "Regional Sul",
    }


def test_localidades_reports_missing_cache_contract_as_503(monkeypatch):
    monkeypatch.setattr(geo, "get_localidades_df", lambda: pl.DataFrame({"sg_uf": ["SC"]}))

    with pytest.raises(HTTPException) as error:
        GeoService.get_localidades(object())

    assert error.value.status_code == 503
    assert "cache de localidades" in error.value.detail


def test_estabelecimentos_geo_filters_dates_joins_risk_and_excludes_unmapped(monkeypatch):
    pharmacies = pl.DataFrame({
        "id_cnpj": [1, 2, 3],
        "cnpj": ["00000000000001", "00000000000002", "00000000000003"],
        "razao_social": ["Farma A", "Farma B", "Sem Coordenadas"],
        "latitude": [None, -27.59, -27.60],
        "longitude": [None, -48.55, -48.56],
        "id_ibge7": ["4205407", "4205407", "4205407"],
        "uf": ["SC", "SC", "SC"],
        "municipio": ["Florianópolis", "Florianópolis", "Florianópolis"],
    })
    risk = pl.DataFrame({
        "id_cnpj": [1, 2],
        "score_risco_final": [8.5, 2.25],
        "classificacao_risco": ["crítico", "baixo"],
    })
    movement = pl.DataFrame({
        "id_cnpj": [2, 2, 2, 2, 3],
        "periodo": [date(2025, 1, 1), date(2025, 2, 1), date(2025, 3, 1), date(2025, 4, 1), date(2025, 2, 1)],
        "total_vendas": [100.0, 200.0, 200.0, 100.0, 0.0],
        "total_sem_comprovacao": [20.0, 100.0, 0.0, 10.0, 0.0],
    })
    matrix = Mock(return_value=risk)
    monkeypatch.setattr(geo, "get_df_dados_farmacia", lambda: pharmacies)
    monkeypatch.setattr(geo, "build_dynamic_matriz_risco", matrix)
    monkeypatch.setattr(geo, "get_df", lambda: movement)

    response = GeoService.get_estabelecimentos_geo(date(2025, 2, 1), date(2025, 3, 31))

    assert len(response.estabelecimentos) == 2
    mapped = next(item for item in response.estabelecimentos if item.cnpj.endswith("02"))
    assert mapped.lat == -27.59
    assert mapped.lon == -48.55
    assert mapped.score_risco == 2.25
    assert mapped.classificacao_risco == "baixo"
    assert mapped.totalMov == 400.0
    assert mapped.valSemComp == 100.0
    assert mapped.percValSemComp == 25.0
    no_risk = next(item for item in response.estabelecimentos if item.cnpj.endswith("03"))
    assert no_risk.score_risco is None
    assert no_risk.totalMov == 0.0
    assert no_risk.valSemComp == 0.0
    assert no_risk.percValSemComp is None
    matrix.assert_called_once_with(data_inicio=date(2025, 2, 1), data_fim=date(2025, 3, 31))


def test_estabelecimentos_geo_returns_503_when_required_source_column_is_missing(monkeypatch):
    pharmacies = pl.DataFrame({"id_cnpj": [1], "cnpj": ["00000000000001"], "latitude": [1.0]})
    risk = pl.DataFrame({"id_cnpj": [1], "score_risco_final": [1.0], "classificacao_risco": ["baixo"]})
    movement = pl.DataFrame({
        "id_cnpj": [1], "periodo": [date(2025, 1, 1)],
        "total_vendas": [100.0], "total_sem_comprovacao": [0.0],
    })
    monkeypatch.setattr(geo, "get_df_dados_farmacia", lambda: pharmacies)
    monkeypatch.setattr(geo, "build_dynamic_matriz_risco", lambda **_kwargs: risk)
    monkeypatch.setattr(geo, "get_df", lambda: movement)

    with pytest.raises(HTTPException) as error:
        GeoService.get_estabelecimentos_geo()

    assert error.value.status_code == 503
    assert "matriz dinamica de risco" in error.value.detail
