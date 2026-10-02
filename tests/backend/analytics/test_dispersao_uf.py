from datetime import date

import polars as pl
import pytest
from fastapi import HTTPException

from backend.api.services.analytics import dispersao_uf


def test_percentual_and_date_normalization():
    assert dispersao_uf._normalize_date(None) is None
    assert dispersao_uf._normalize_date(date(2024, 2, 3)) == "2024-02-03"
    assert dispersao_uf._normalize_percentual(None) == 5.0
    assert dispersao_uf._normalize_percentual(25.123456) == 25.1235
    for invalid in (-0.01, 100.01):
        with pytest.raises(HTTPException) as error:
            dispersao_uf._normalize_percentual(invalid)
        assert error.value.status_code == 400


def test_neighbor_matrix_marks_same_and_neighbor_states_only():
    matrix = dispersao_uf._vizinhanca_df()
    assert matrix.height == len(dispersao_uf.UF_BRASILEIRAS) ** 2
    assert matrix.filter((pl.col("uf_farmacia") == "SP") & (pl.col("uf_paciente") == "SP"))[0, "is_fronteira_ou_mesma_uf"]
    assert matrix.filter((pl.col("uf_farmacia") == "SP") & (pl.col("uf_paciente") == "MG"))[0, "is_fronteira_ou_mesma_uf"]
    assert not matrix.filter((pl.col("uf_farmacia") == "SP") & (pl.col("uf_paciente") == "AC"))[0, "is_fronteira_ou_mesma_uf"]


def test_dispersao_requires_the_complete_source_contract(monkeypatch):
    monkeypatch.setattr(dispersao_uf, "scan_geografico_origem_uf", lambda: pl.DataFrame({"id_cnpj": [1]}).lazy())
    with pytest.raises(HTTPException) as error:
        dispersao_uf._build_dispersao_df(None, None, 0)
    assert error.value.status_code == 500
    assert "ano_base" in error.value.detail and "uf_farmacia" in error.value.detail


def test_dispersao_aggregates_cross_state_sales_and_applies_year_and_threshold(monkeypatch):
    origin = pl.DataFrame(
        {
            "id_cnpj": [1, 1, 1, 2, 2, 3, 1],
            "ano_base": [2024, 2024, 2024, 2024, 2024, 2024, 2023],
            "uf_farmacia": [" sp ", "SP", "SP", "SP", "SP", "SP", "SP"],
            "uf_paciente": ["SP", "MG", "AC", "AC", "SP", "AC", "AC"],
            "valor_autorizado": [60.0, 30.0, 10.0, 100.0, 0.0, 0.0, 1000.0],
        }
    )
    monkeypatch.setattr(dispersao_uf, "scan_geografico_origem_uf", lambda: origin.lazy())
    result = dispersao_uf._build_dispersao_df(date(2024, 1, 1), date(2024, 12, 31), 10.0)
    rows = {row["id_cnpj"]: row for row in result.to_dicts()}
    assert set(rows) == {1, 2}
    assert rows[1]["pct_dispersao_uf_sem_fronteira"] == 10.0
    assert rows[1]["valor_dispersao_uf_sem_fronteira"] == 10.0
    assert rows[2]["pct_dispersao_uf_sem_fronteira"] == 100.0

    no_minimums = dispersao_uf._build_dispersao_df(None, None, 0.0)
    assert no_minimums.filter(pl.col("id_cnpj") == 1).height == 1
    assert no_minimums.filter(pl.col("id_cnpj") == 3).get_column("pct_dispersao_uf_sem_fronteira").item() == 0.0


def test_public_dispersao_uses_normalized_parameters_and_cache(monkeypatch):
    calls = []
    result = pl.DataFrame({"id_cnpj": [1], "pct_dispersao_uf_sem_fronteira": [10.0], "valor_dispersao_uf_sem_fronteira": [5.0]})

    def build(start, end, limit):
        calls.append((start, end, limit))
        return result

    monkeypatch.setattr(dispersao_uf, "_build_dispersao_df", build)
    first = dispersao_uf.get_dispersao_uf_sem_fronteira_id_cnpjs_df(date(2024, 1, 1), date(2024, 12, 31), 5)
    second = dispersao_uf.get_dispersao_uf_sem_fronteira_id_cnpjs_df(date(2024, 1, 1), date(2024, 12, 31), 5.00001)
    assert first.equals(result) and second.equals(result)
    assert len(calls) == 1
