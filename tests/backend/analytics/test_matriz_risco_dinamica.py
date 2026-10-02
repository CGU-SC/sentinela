from datetime import date

import polars as pl
import pytest

from api.services.analytics import matriz_risco_dinamica as matriz


def _matrix_frame():
    rows = []
    for entity, pct in [(1, 20.0), (2, 5.0)]:
        row = {col: 0.0 for col in matriz._MATRIX_COMPONENT_COLUMNS}
        row.update(
            {
                "id_cnpj": entity,
                "ano_base": 2020,
                "valor_total_vendas": 100.0,
                "valor_sem_comprovacao": pct,
                "total_caixas": 10.0,
                "total_caixas_sem_comprovacao": 1.0,
                "total_autorizacoes": 10.0,
                "ticket_total_autorizacoes": 10.0,
            }
        )
        rows.append(row)
    return pl.DataFrame(rows)


def test_dynamic_matrix_aggregates_by_cnpj_classifies_and_ranks(monkeypatch):
    profile = pl.DataFrame(
        {
            "id_cnpj": [1, 2], "cnpj": ["11111111000101", "22222222000102"],
            "uf": ["SP", "SP"], "id_regiao_saude": ["10", "10"], "id_ibge7": [1, 1],
        }
    )
    monkeypatch.setattr(matriz, "get_df_matriz_risco", lambda: _matrix_frame())
    monkeypatch.setattr(matriz, "get_volume_atipico_aumento_minimo", lambda: 10000.0)

    result = matriz._compute_dynamic_matriz_risco(
        data_inicio=date(2020, 1, 1), data_fim=date(2020, 12, 31), perfil_df=profile
    ).sort("id_cnpj")
    assert result["pct_sem_comprovacao"].to_list() == [20.0, 5.0]
    assert result["classificacao_risco"].to_list()[0] == "CRÍTICO"
    assert result["classificacao_risco"].to_list()[1] == "ATENÇÃO"
    assert result["rank_nacional"].to_list() == [1, 2]
    assert result["total_nacional"].to_list() == [2, 2]


def test_dynamic_matrix_rejects_missing_required_source_columns(monkeypatch):
    monkeypatch.setattr(matriz, "get_df_matriz_risco", lambda: pl.DataFrame({"id_cnpj": [1], "ano_base": [2020]}))
    monkeypatch.setattr(matriz, "get_volume_atipico_aumento_minimo", lambda: 10000.0)
    with pytest.raises(RuntimeError, match="colunas obrigatorias"):
        matriz._compute_dynamic_matriz_risco(perfil_df=pl.DataFrame())


def test_dynamic_matrix_rejects_incomplete_profile_schema(monkeypatch):
    monkeypatch.setattr(matriz, "get_df_matriz_risco", lambda: _matrix_frame())
    monkeypatch.setattr(matriz, "get_volume_atipico_aumento_minimo", lambda: 10000.0)

    with pytest.raises(RuntimeError, match="perfil_estabelecimento.*matriz dinamica"):
        matriz._compute_dynamic_matriz_risco(perfil_df=pl.DataFrame({"id_cnpj": [1]}))


def test_period_bounds_keep_year_scope_explicit():
    assert matriz._period_year_bounds(date(2020, 3, 1), date(2021, 2, 1)) == (2020, 2021)
    assert matriz._period_year_bounds(None, None) == (None, None)


def test_annual_matrix_adds_per_year_benchmarks(monkeypatch):
    profile = pl.DataFrame(
        {
            "id_cnpj": [1, 2], "cnpj": ["11111111000101", "22222222000102"],
            "uf": ["SP", "SP"], "id_regiao_saude": ["10", "10"],
        }
    )
    monkeypatch.setattr(matriz, "get_df_matriz_risco", lambda: _matrix_frame())
    result = matriz.build_annual_indicator_benchmark_matriz(perfil_df=profile).sort("id_cnpj")
    assert result["pct_sem_comprovacao"].to_list() == [20.0, 5.0]
    assert result["med_sem_comprovacao_reg"].to_list() == [12.5, 12.5]
    assert result["_total_regiao_benchmark"].to_list() == [2, 2]


@pytest.mark.parametrize("factor", [True, None, "1.5"])
def test_aggregation_factor_rejects_non_numeric_configuration(factor):
    with pytest.raises(RuntimeError, match="factor invalido"):
        matriz._aggregation_factor({"factor": factor})


def test_aggregation_factor_accepts_numeric_configuration():
    assert matriz._aggregation_factor({"factor": 2}) == 2.0


def test_dynamic_matrix_returns_empty_when_year_filter_has_no_rows(monkeypatch):
    monkeypatch.setattr(matriz, "get_df_matriz_risco", lambda: _matrix_frame())

    result = matriz._compute_dynamic_matriz_risco(data_inicio=date(2022, 1, 1))

    assert result.is_empty()


def test_annual_benchmark_returns_empty_for_empty_source(monkeypatch):
    monkeypatch.setattr(matriz, "get_df_matriz_risco", lambda: pl.DataFrame())

    assert matriz.build_annual_indicator_benchmark_matriz(perfil_df=pl.DataFrame()).is_empty()


def test_annual_benchmark_rejects_incomplete_matrix_schema(monkeypatch):
    monkeypatch.setattr(matriz, "get_df_matriz_risco", lambda: pl.DataFrame({"id_cnpj": [1], "ano_base": [2020]}))

    with pytest.raises(RuntimeError, match="evolucao anual"):
        matriz.build_annual_indicator_benchmark_matriz(perfil_df=pl.DataFrame())


def test_annual_benchmark_rejects_incomplete_profile_schema(monkeypatch):
    monkeypatch.setattr(matriz, "get_df_matriz_risco", lambda: _matrix_frame())

    with pytest.raises(RuntimeError, match="perfil_estabelecimento.*evolucao anual"):
        matriz.build_annual_indicator_benchmark_matriz(perfil_df=pl.DataFrame({"id_cnpj": [1]}))


def test_annual_benchmark_caches_and_returns_independent_copies(monkeypatch):
    profile = pl.DataFrame(
        {
            "id_cnpj": [1, 2], "cnpj": ["11111111000101", "22222222000102"],
            "uf": ["SP", "SP"], "id_regiao_saude": ["10", "10"],
        }
    )
    monkeypatch.setattr(matriz, "_ANNUAL_BENCHMARK_CACHE", {})
    monkeypatch.setattr(matriz, "get_cache_generation", lambda: 42)
    monkeypatch.setattr(matriz, "get_df_matriz_risco", lambda: _matrix_frame())
    monkeypatch.setattr(matriz, "get_df_perfil_estabelecimento", lambda: profile)
    monkeypatch.setattr(matriz.time, "monotonic", lambda: 100.0)

    first = matriz.build_annual_indicator_benchmark_matriz()
    second = matriz.build_annual_indicator_benchmark_matriz()

    assert first.equals(second)
    assert first is not second
    assert len(matriz._ANNUAL_BENCHMARK_CACHE) == 1


def test_dynamic_builder_uses_explicit_profile_without_global_cache(monkeypatch):
    expected = pl.DataFrame({"id_cnpj": [9]})
    profile = pl.DataFrame({"id_cnpj": [9]})
    calls = []

    def compute(**kwargs):
        calls.append(kwargs)
        return expected

    monkeypatch.setattr(matriz, "_compute_dynamic_matriz_risco", compute)
    result = matriz.build_dynamic_matriz_risco(
        data_inicio=date(2020, 1, 1), data_fim=date(2020, 12, 31), perfil_df=profile
    )

    assert result is expected
    assert calls == [{"data_inicio": date(2020, 1, 1), "data_fim": date(2020, 12, 31), "perfil_df": profile}]


def test_dynamic_builder_caches_results_until_ttl_expires(monkeypatch):
    cache = {}
    calls = []
    instants = iter([100.0, 200.0, 401.0])

    def compute(**kwargs):
        calls.append(kwargs)
        return pl.DataFrame({"computed": [len(calls)]})

    monkeypatch.setattr(matriz, "_DYNAMIC_CACHE", cache)
    monkeypatch.setattr(matriz, "get_cache_generation", lambda: 8)
    monkeypatch.setattr(matriz, "get_volume_atipico_aumento_minimo", lambda: 10000.0)
    monkeypatch.setattr(matriz.time, "monotonic", lambda: next(instants))
    monkeypatch.setattr(matriz, "_compute_dynamic_matriz_risco", compute)

    first = matriz.build_dynamic_matriz_risco(data_inicio=date(2020, 1, 1))
    cached = matriz.build_dynamic_matriz_risco(data_inicio=date(2020, 7, 1))
    expired = matriz.build_dynamic_matriz_risco(data_inicio=date(2020, 7, 1))

    assert first is cached
    assert expired["computed"].to_list() == [2]
    assert len(calls) == 2


def test_dynamic_builder_evicts_oldest_entry_when_cache_is_full(monkeypatch):
    cache = {}
    calls = []
    instants = iter([10.0, 20.0, 30.0])

    def compute(**kwargs):
        calls.append(kwargs)
        return pl.DataFrame({"computed": [len(calls)]})

    monkeypatch.setattr(matriz, "_DYNAMIC_CACHE", cache)
    monkeypatch.setattr(matriz, "_DYNAMIC_CACHE_MAX_ENTRIES", 1)
    monkeypatch.setattr(matriz, "get_cache_generation", lambda: 9)
    monkeypatch.setattr(matriz, "get_volume_atipico_aumento_minimo", lambda: 10000.0)
    monkeypatch.setattr(matriz.time, "monotonic", lambda: next(instants))
    monkeypatch.setattr(matriz, "_compute_dynamic_matriz_risco", compute)

    matriz.build_dynamic_matriz_risco(data_inicio=date(2020, 1, 1))
    matriz.build_dynamic_matriz_risco(data_inicio=date(2021, 1, 1))
    matriz.build_dynamic_matriz_risco(data_inicio=date(2020, 1, 1))

    assert len(calls) == 3
    assert len(cache) == 1
