from datetime import date

import polars as pl
import pytest

from backend.api.services.analytics import volume_atipico as volume


def _volume_rows():
    return pl.DataFrame(
        {
            "id_cnpj": [1, 1, 1, 2, 3],
            "chave_semestre": [202301, 202302, 202401, 202401, 202402],
            "status_semestre": [1, 1, 1, 0, 1],
            "aumento_valor_semestre": [100.0, 250.0, 50.0, 1000.0, 500.0],
            "taxa_crescimento_pct": [60.0, 80.0, 30.0, 150.0, None],
        }
    )


def test_volume_limit_dates_and_material_growth_rule(monkeypatch):
    monkeypatch.setattr(volume, "get_volume_atipico_aumento_minimo", lambda: 100.0)
    assert volume.normalize_volume_atipico_limite(None) == 50.0
    assert volume.normalize_volume_atipico_limite(10) == 40.0
    assert volume.normalize_volume_atipico_limite("75.5") == 75.5
    assert volume.normalize_volume_atipico_limite(5000) == 2000.0
    assert volume._date_to_semester_key(date(2024, 6, 30)) == 202401
    assert volume._date_to_semester_key(date(2024, 7, 1)) == 202402
    assert volume._period_to_semester_keys(None, date(2024, 7, 1)) == (None, 202402)
    assert volume._period_to_semester_keys(date(2024, 1, 1), None) == (202401, None)

    assert volume.is_volume_atipico_relevante(50.01, 100.0, 50.0)
    assert not volume.is_volume_atipico_relevante(50.0, 1000.0, 50.0)
    assert not volume.is_volume_atipico_relevante(None, 1000.0, 50.0)
    assert not volume.is_volume_atipico_relevante(80.0, None, 50.0)
    expression = pl.DataFrame(
        {"taxa_crescimento_pct": [50.0, 50.01, 90.0, None], "aumento_valor_semestre": [1000.0, 99.0, 100.0, 1000.0]}
    ).select(volume.volume_atipico_flag_expr(50.0).alias("flag"))
    assert expression.get_column("flag").to_list() == [False, False, True, False]


def test_volume_cache_contract_and_cnpj_lookup_validation(monkeypatch):
    incomplete = pl.DataFrame({"id_cnpj": [1], "status_semestre": [1]})
    monkeypatch.setattr(volume, "get_df_volume_atipico_semestral", lambda: incomplete)
    with pytest.raises(RuntimeError, match="Cache de Volume Atipico Semestral sem colunas obrigatorias"):
        volume._volume_df_for_period(None, None)

    monkeypatch.setattr(volume, "get_df_dados_farmacia", lambda: pl.DataFrame({"id_cnpj": [1]}))
    with pytest.raises(RuntimeError, match="Cache de Dados das Farmacias sem colunas obrigatorias"):
        volume._cnpj_lookup_df()

    monkeypatch.setattr(
        volume,
        "get_df_dados_farmacia",
        lambda: pl.DataFrame({"id_cnpj": [1, 1, 2], "cnpj": ["001", "ignored duplicate", "002"]}),
    )
    lookup = volume._cnpj_lookup_df()
    assert lookup.sort("id_cnpj").to_dicts() == [
        {"id_cnpj": 1, "cnpj": "001"},
        {"id_cnpj": 2, "cnpj": "002"},
    ]


def test_period_metrics_include_only_comparable_semesters_and_calculate_risks(monkeypatch):
    monkeypatch.setattr(volume, "get_df_volume_atipico_semestral", _volume_rows)
    monkeypatch.setattr(volume, "get_volume_atipico_aumento_minimo", lambda: 100.0)
    monkeypatch.setattr(
        volume,
        "get_df_dados_farmacia",
        lambda: pl.DataFrame({"id_cnpj": [1, 2, 3], "cnpj": ["1", "2", "3"]}),
    )

    metrics = volume.get_volume_atipico_period_metrics(date(2023, 7, 1), date(2024, 6, 30), 50.0)
    row = metrics.filter(pl.col("id_cnpj") == 1).row(0, named=True)
    assert row["qtd_comparacoes_volume_atipico"] == 2
    assert row["qtd_semestres_atipicos"] == 1
    assert row["maior_crescimento_pct"] == 80.0
    assert row["soma_excesso_volume_atipico"] == 30.0
    assert row["risco_final_volume_atipico"] == 15.0
    assert row["risco_magnitude_volume_atipico"] == 30.0
    assert row["risco_frequencia_volume_atipico"] == 0.5
    assert metrics.filter(pl.col("id_cnpj") == 2).is_empty()

    monkeypatch.setattr(volume, "get_df_volume_atipico_semestral", lambda: _volume_rows().clear())
    assert volume.get_volume_atipico_period_metrics(None, None).is_empty()


def test_atypical_volume_cnpj_ids_cache_filter_and_cache_eviction(monkeypatch):
    source = _volume_rows()
    volume._VOLUME_ATIPICO_ID_CNPJS_CACHE.clear()
    monkeypatch.setattr(volume, "get_df_volume_atipico_semestral", lambda: source)
    monkeypatch.setattr(volume, "get_volume_atipico_aumento_minimo", lambda: 100.0)
    original_period = volume._volume_df_for_period
    period_calls = []
    monkeypatch.setattr(
        volume,
        "_volume_df_for_period",
        lambda start, end: period_calls.append((start, end)) or original_period(start, end),
    )

    first = volume.get_volume_atipico_id_cnpjs_df(date(2023, 7, 1), date(2024, 6, 30), 50.0)
    second = volume.get_volume_atipico_id_cnpjs_df(date(2023, 7, 1), date(2024, 6, 30), 50.0)
    assert first.get_column("id_cnpj").to_list() == [1]
    assert second.equals(first)
    assert len(period_calls) == 1

    empty_source = source.clear()
    monkeypatch.setattr(volume, "get_df_volume_atipico_semestral", lambda: empty_source)
    assert volume.get_volume_atipico_id_cnpjs_df(None, None).schema == {"id_cnpj": pl.Int32}

    volume._VOLUME_ATIPICO_ID_CNPJS_CACHE.clear()
    volume._VOLUME_ATIPICO_ID_CNPJS_CACHE.update({(index, None, None, 50.0, 100.0): pl.DataFrame() for index in range(64)})
    monkeypatch.setattr(volume, "get_df_volume_atipico_semestral", lambda: source)
    volume.get_volume_atipico_id_cnpjs_df(date(2023, 7, 1), date(2024, 6, 30), 60.0)
    assert len(volume._VOLUME_ATIPICO_ID_CNPJS_CACHE) == 1


def test_volume_metrics_fail_explicitly_for_missing_pharmacy_contract(monkeypatch):
    monkeypatch.setattr(volume, "get_df_volume_atipico_semestral", _volume_rows)
    monkeypatch.setattr(volume, "get_volume_atipico_aumento_minimo", lambda: 100.0)
    monkeypatch.setattr(volume, "get_df_dados_farmacia", lambda: pl.DataFrame({"id_cnpj": [1]}))
    with pytest.raises(RuntimeError, match="Cache de Dados das Farmacias sem colunas obrigatorias"):
        volume.get_volume_atipico_period_metrics(None, None)
