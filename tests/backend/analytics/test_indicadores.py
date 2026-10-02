from datetime import date
from decimal import Decimal

import polars as pl
import pytest
from fastapi import HTTPException

from api.services.analytics import indicadores
from api.services.analytics import matriz_risco_dinamica as dynamic_matrix


def test_scope_base_uses_region_id_and_exact_percent_cut(monkeypatch):
    movimento = pl.DataFrame(
        {
            "id_cnpj": [1, 2, 3],
            "periodo": [date(2020, 1, 1)] * 3,
            "total_vendas": [1000.0, 1000.0, 1000.0],
            "total_sem_comprovacao": [49.988, 50.0, 80.0],
        }
    )
    perfil = pl.DataFrame(
        {
            "id_cnpj": [1, 2, 3], "cnpj": ["11111111000101", "22222222000102", "33333333000103"],
            "uf": ["SP", "SP", "RJ"], "id_regiao_saude": ["10", "10", "20"],
            "id_ibge7": [1, 1, 2], "situacao_rf": ["ATIVA"] * 3,
            "is_conexao_ativa": [True] * 3, "porte_empresa": ["ME"] * 3,
            "is_grande_rede": [False] * 3, "unidade_pf": ["Matriz"] * 3,
            "no_municipio": ["A", "A", "B"], "razao_social": ["A", "B", "C"],
            "nome_fantasia": ["A", "B", "C"],
        }
    )
    monkeypatch.setattr(indicadores, "get_df", lambda: movimento)
    monkeypatch.setattr(indicadores, "get_df_perfil_estabelecimento", lambda: perfil)

    scope, _ = indicadores._build_indicador_scope_base(
        data_inicio=date(2020, 1, 1), data_fim=date(2020, 1, 31),
        regiao_id=10, perc_min=5.0, perc_max=10.0,
    )
    assert scope["id_cnpj"].to_list() == [2]
    assert scope["perc_val_sem_comp"].to_list() == [5.0]

    exact_cnpj, _ = indicadores._build_indicador_scope_base(
        data_inicio=date(2020, 1, 1),
        data_fim=date(2020, 1, 31),
        cnpj_raiz="11111111000101",
    )
    assert exact_cnpj["id_cnpj"].to_list() == [1]


def test_indicadores_analise_rejects_unknown_indicator_before_cache_access():
    with pytest.raises(HTTPException) as error:
        indicadores.get_indicadores_analise("nao_existe")
    assert error.value.status_code == 400


def test_status_kpis_count_statuses_and_financial_totals():
    result = indicadores._build_status_kpis(
        pl.DataFrame(
            {
                "status": ["CRÍTICO", "ATENÇÃO", "NORMAL", "SEM DADOS"],
                "total_vendas": [100.0, 200.0, 300.0, 400.0],
                "total_sem_comprovacao": [20.0, 10.0, 0.0, 40.0],
            }
        )
    )
    assert (result.total_critico, result.total_atencao, result.total_normal, result.total_sem_dados) == (1, 1, 1, 1)
    assert result.total_mov == 1000.0
    assert result.total_sem_comprovacao == 70.0
    assert result.perc_sem_comprovacao == 7.0


def test_status_kpis_empty_input_returns_zero_summary():
    empty = pl.DataFrame(
        schema={
            "status": pl.String,
            "total_vendas": pl.Float64,
            "total_sem_comprovacao": pl.Float64,
        }
    )
    result = indicadores._build_status_kpis(empty)
    assert result.total_critico == 0
    assert result.total_atencao == 0
    assert result.total_mov == 0.0


def test_get_indicadores_maps_matrix_values_status_and_financial_context(monkeypatch):
    cnpj = "12345678000190"
    profile = pl.DataFrame(
        {"id_cnpj": [1], "cnpj": [cnpj], "uf": ["SP"], "id_regiao_saude": ["10"], "id_ibge7": [1]}
    )
    monkeypatch.setattr(
        indicadores,
        "get_df_perfil_estabelecimento",
        lambda: profile,
    )
    row = {column: 0.0 for column in dynamic_matrix._MATRIX_COMPONENT_COLUMNS}
    row.update({"id_cnpj": 1, "ano_base": 2020, "valor_total_vendas": 100.0, "valor_sem_comprovacao": 20.0, "total_autorizacoes": 10.0, "ticket_total_autorizacoes": 10.0})
    monkeypatch.setattr(dynamic_matrix, "get_df_matriz_risco", lambda: pl.DataFrame([row]))
    monkeypatch.setattr(dynamic_matrix, "get_df_perfil_estabelecimento", lambda: profile)
    monkeypatch.setattr(dynamic_matrix, "get_cache_generation", lambda: 993)
    monkeypatch.setattr(dynamic_matrix, "get_volume_atipico_aumento_minimo", lambda: 10000.0)
    dynamic_matrix._DYNAMIC_CACHE.clear()

    result = indicadores.get_indicadores("12.345.678/0001-90")
    assert result.cnpj == cnpj
    assert result.indicadores["percentual_nao_comprovacao"].status == "CRÍTICO"
    assert result.indicadores["percentual_nao_comprovacao"].valor_financeiro == 20.0
    assert result.indicadores["ticket_medio"].status == "NORMAL"


def test_get_indicadores_returns_empty_rows_and_attention_status(monkeypatch):
    cnpj = "12345678000190"
    monkeypatch.setattr(
        indicadores,
        "get_df_perfil_estabelecimento",
        lambda: pl.DataFrame({"cnpj": [cnpj]}),
    )
    monkeypatch.setattr(
        indicadores,
        "_build_dynamic_matriz_risco",
        lambda **kwargs: pl.DataFrame(schema={"cnpj": pl.String}),
    )
    no_rows = indicadores.get_indicadores(cnpj)
    assert no_rows.indicadores == {}

    attention_col, critical_col = indicadores._INDICATOR_FLAGS["falecidos"]
    value_col = indicadores.INDICATOR_MAPPING["falecidos"][0]
    matrix_row = {
        "cnpj": cnpj,
        "_total_regiao_benchmark": None,
        **{column: 0.0 for column in indicadores._INDICADOR_VALOR_FINANCEIRO_COLS.values()},
    }
    for attention_flag, critical_flag in indicadores._INDICATOR_FLAGS.values():
        matrix_row[attention_flag] = 0
        matrix_row[critical_flag] = 0
    matrix_row[value_col] = 4.0
    matrix_row[attention_col] = 1
    matrix_row[critical_col] = 0
    monkeypatch.setattr(
        indicadores,
        "_build_dynamic_matriz_risco",
        lambda **kwargs: pl.DataFrame([matrix_row]),
    )
    attention = indicadores.get_indicadores(cnpj)
    assert attention.indicadores["falecidos"].status.startswith("ATEN")
    assert attention.indicadores["falecidos"].benchmark_escopo == "UF"


def test_get_indicadores_preserves_http_errors(monkeypatch):
    expected = HTTPException(status_code=409, detail="matrix conflict")
    monkeypatch.setattr(
        indicadores,
        "get_df_perfil_estabelecimento",
        lambda: pl.DataFrame({"cnpj": ["12345678000190"]}),
    )
    monkeypatch.setattr(
        indicadores,
        "_build_dynamic_matriz_risco",
        lambda **kwargs: (_ for _ in ()).throw(expected),
    )
    with pytest.raises(HTTPException) as error:
        indicadores.get_indicadores("12345678000190")
    assert error.value is expected


def test_indicador_dataset_rejects_unknown_indicator():
    with pytest.raises(HTTPException) as error:
        indicadores._build_indicador_dataset("desconhecido", pl.DataFrame(), pl.DataFrame())
    assert error.value.status_code == 400


def _indicador_risco_frame(indicador, *, ids=(1,), values=None):
    c_val, c_mr, c_mu, _c_mb, c_rr, c_ru, _c_rb = indicadores.INDICATOR_MAPPING[indicador]
    c_aten, c_crit = indicadores._INDICATOR_FLAGS[indicador]
    values = values or [1.0 for _ in ids]
    rows = []
    for index, (cnpj_id, value) in enumerate(zip(ids, values)):
        row = {
            "id_cnpj": cnpj_id,
            "_total_regiao_benchmark": indicadores.MIN_REGIAO_BENCHMARK + 1,
            c_val: value,
            c_mr: 0.8,
            c_mu: 0.7,
            c_rr: 1.2,
            c_ru: 1.1,
            c_aten: 0,
            c_crit: 0,
            "score_risco_final": 50.0 + index,
        }
        if indicador == "volume_atipico":
            row.update(
                {
                    "volume_atipico_valor_aumento_atipico": 500.0 + index,
                    "volume_atipico_maior_taxa_crescimento_pct": 0.6 + index,
                }
            )
        rows.append(row)
    return pl.DataFrame(rows)


def test_build_indicador_dataset_empty_scope_avoids_matrix_access(monkeypatch):
    empty_scope = pl.DataFrame(schema={"id_cnpj": pl.Int32})
    monkeypatch.setattr(
        indicadores,
        "_build_dynamic_matriz_risco",
        lambda **kwargs: pytest.fail("escopo vazio nao deve consultar a matriz"),
    )

    result = indicadores._build_indicador_dataset(
        "percentual_nao_comprovacao", empty_scope, pl.DataFrame()
    )

    assert result[0].is_empty()
    assert result[2].is_empty()
    assert result[3] == "pct_sem_comprovacao"


def test_build_indicador_dataset_returns_empty_when_matrix_has_no_scope_match(monkeypatch):
    scope = pl.DataFrame({"id_cnpj": [1]})
    risk = _indicador_risco_frame("percentual_nao_comprovacao", ids=(2,))
    monkeypatch.setattr(indicadores, "_build_dynamic_matriz_risco", lambda **kwargs: risk)

    result = indicadores._build_indicador_dataset(
        "percentual_nao_comprovacao", scope, pl.DataFrame()
    )

    assert result[0].is_empty()
    assert result[2].height == 1
    assert result[5] is None


def test_build_indicador_dataset_adds_dispersal_data_and_status_fields(monkeypatch):
    scope = pl.DataFrame({"id_cnpj": [1, 2]})
    risk = _indicador_risco_frame("dispersao_geografica", ids=(1, 2), values=(None, 2.0))
    monkeypatch.setattr(indicadores, "_build_dynamic_matriz_risco", lambda **kwargs: risk)
    monkeypatch.setattr(
        indicadores,
        "_get_pct_dispersao_uf_nao_vizinha_df",
        lambda *args: pl.DataFrame({"id_cnpj": [1, 2], "pct_dispersao_uf_nao_vizinha": [0.0, 0.4]}),
    )

    result = indicadores._build_indicador_dataset(
        "dispersao_geografica", scope, pl.DataFrame()
    )

    dataset = result[0].sort("id_cnpj")
    assert dataset["status"].to_list() == ["SEM DADOS", "NORMAL"]
    assert dataset["benchmark_escopo"].to_list() == ["REGI\u00c3O", "REGI\u00c3O"]
    assert dataset["pct_dispersao_uf_nao_vizinha"].to_list() == [0.0, 0.4]


def test_build_indicador_dataset_preserves_volume_display_columns(monkeypatch):
    scope = pl.DataFrame({"id_cnpj": [1]})
    risk = _indicador_risco_frame("volume_atipico")
    monkeypatch.setattr(indicadores, "_build_dynamic_matriz_risco", lambda **kwargs: risk)

    dataset, _profile, _risk, c_val, _median, _regional_risk, score_col = (
        indicadores._build_indicador_dataset("volume_atipico", scope, pl.DataFrame())
    )

    assert c_val == "val_volume_atipico"
    assert "volume_atipico_valor_aumento_atipico" in dataset.columns
    assert "volume_atipico_maior_taxa_crescimento_pct" in dataset.columns
    assert score_col == "score_risco_final"


def test_build_indicador_dataset_rejects_missing_required_matrix_column(monkeypatch):
    scope = pl.DataFrame({"id_cnpj": [1]})
    risk = _indicador_risco_frame("percentual_nao_comprovacao").drop(
        "flag_percentual_sem_comprovacao_critico"
    )
    monkeypatch.setattr(indicadores, "_build_dynamic_matriz_risco", lambda **kwargs: risk)

    with pytest.raises(RuntimeError, match="Colunas dinamicas obrigatorias ausentes"):
        indicadores._build_indicador_dataset(
            "percentual_nao_comprovacao", scope, pl.DataFrame()
        )


def test_indicator_scope_cache_normalizes_filters_and_reuses_result(monkeypatch):
    indicadores._INDICADOR_SCOPE_BASE_CACHE.clear()
    monkeypatch.setattr(indicadores, "get_cache_generation", lambda: 17)
    monkeypatch.setattr(indicadores, "get_volume_atipico_aumento_minimo", lambda: 100.0)
    scope = pl.DataFrame({"id_cnpj": [1]})
    profile = pl.DataFrame({"cnpj": ["123"]})
    calls = []

    def build_scope(**filters):
        calls.append(filters)
        return scope, profile

    monkeypatch.setattr(indicadores, "_build_indicador_scope_base", build_scope)
    first = indicadores.get_indicador_scope_base_cached(uf=" sp ")
    second = indicadores.get_indicador_scope_base_cached(uf="sp")

    assert first.equals(scope)
    assert second.equals(scope)
    assert len(calls) == 1
    assert calls[0]["uf"] == " sp "
    with pytest.raises(ValueError, match="Filtros desconhecidos"):
        indicadores.get_indicador_scope_base_cached(not_a_filter=True)


def test_indicator_dataset_cache_reuses_scope_and_dataset(monkeypatch):
    indicadores._INDICADOR_SCOPE_BASE_CACHE.clear()
    indicadores._INDICADOR_DATASET_CACHE.clear()
    monkeypatch.setattr(indicadores, "get_cache_generation", lambda: 18)
    monkeypatch.setattr(indicadores, "get_volume_atipico_aumento_minimo", lambda: 100.0)
    scope = pl.DataFrame({"id_cnpj": [1]})
    profile = pl.DataFrame({"cnpj": ["123"]})
    cached_payload = (scope, profile, pl.DataFrame(), "v", "m", None, "score")
    build_scope_calls = []
    build_dataset_calls = []

    def build_scope(**filters):
        build_scope_calls.append(filters)
        return scope, profile

    def build_dataset(*args, **kwargs):
        build_dataset_calls.append((args, kwargs))
        return cached_payload

    monkeypatch.setattr(indicadores, "_build_indicador_scope_base", build_scope)
    monkeypatch.setattr(indicadores, "_build_indicador_dataset", build_dataset)
    first = indicadores._build_indicador_dataset_cached("percentual_nao_comprovacao", uf="SP")
    second = indicadores._build_indicador_dataset_cached("percentual_nao_comprovacao", uf="SP")

    assert first == cached_payload
    assert second == cached_payload
    assert len(build_scope_calls) == 1
    assert len(build_dataset_calls) == 1


def test_indicator_dataset_cache_reuses_scope_before_building_dataset(monkeypatch):
    indicadores._INDICADOR_SCOPE_BASE_CACHE.clear()
    indicadores._INDICADOR_DATASET_CACHE.clear()
    monkeypatch.setattr(indicadores, "get_cache_generation", lambda: 19)
    monkeypatch.setattr(indicadores, "get_volume_atipico_aumento_minimo", lambda: 100.0)
    scope = pl.DataFrame({"id_cnpj": [1]})
    profile = pl.DataFrame({"cnpj": ["123"]})
    raw_filters = {
        name: (False if normalizer is indicadores._normalize_cache_bool else None)
        for name, normalizer in indicadores._INDICADOR_SCOPE_FILTER_FIELDS
    }
    raw_filters["uf"] = "SP"
    key = indicadores._make_indicador_scope_base_cache_key(filters=raw_filters)
    indicadores._put_indicador_cache(
        indicadores._INDICADOR_SCOPE_BASE_CACHE, key, (scope, profile), 19
    )
    payload = (scope, profile, pl.DataFrame(), "v", "m", None, "score")
    monkeypatch.setattr(
        indicadores,
        "_build_indicador_scope_base",
        lambda **kwargs: pytest.fail("base ja esta no cache"),
    )
    monkeypatch.setattr(indicadores, "_build_indicador_dataset", lambda *a, **k: payload)

    result = indicadores._build_indicador_dataset_cached(
        "percentual_nao_comprovacao", uf="SP"
    )

    assert result == payload


def _analysis_dataset(indicador="percentual_nao_comprovacao"):
    c_val, c_mr, c_mu, _c_mb, c_rr, _c_ru, _c_rb = indicadores.INDICATOR_MAPPING[indicador]
    joined = pl.DataFrame(
        {
            "id_cnpj": [1, 2],
            "no_municipio": ["sao paulo", "campinas"],
            "uf": ["SP", "SP"],
            "id_ibge7": [3550308, 3509502],
            "id_regiao_saude": ["10", "10"],
            "status": ["CR\u00cdTICO", "ATEN\u00c7\u00c3O"],
            c_val: [4.0, 2.0],
            c_mr: [1.0, 0.8],
            c_mu: [0.9, 0.7],
            c_rr: [1.5, 0.8],
        }
    )
    profile = joined.select("id_cnpj", "uf", "id_regiao_saude")
    risk = joined.select("id_cnpj", c_val, c_rr)
    return joined, profile, risk, c_val, c_mr, c_rr, "score_risco_final"


def test_indicator_analysis_aggregates_municipalities_and_context(monkeypatch):
    payload = _analysis_dataset()
    monkeypatch.setattr(indicadores, "_build_indicador_dataset_cached", lambda *a, **k: payload)

    result = indicadores.get_indicadores_analise(
        "percentual_nao_comprovacao", uf="SP", id_ibge7=3550308
    )

    assert result.kpis.total_critico == 1
    assert result.kpis.total_atencao == 1
    assert result.kpis.pct_acima_limiar == 100.0
    assert result.kpis.mediana_reg == 3.0
    assert result.kpis.mad_reg == 0.35
    assert [row.municipio for row in result.municipios] == ["Sao Paulo", "Campinas"]
    assert result.municipios[0].pct_critico == 100.0


def test_indicator_analysis_returns_empty_response_and_surfaces_missing_risk_column(monkeypatch):
    empty = pl.DataFrame(schema={"id_cnpj": pl.Int32})
    monkeypatch.setattr(
        indicadores,
        "_build_indicador_dataset_cached",
        lambda *a, **k: (empty, pl.DataFrame(), pl.DataFrame(), "v", "m", "r", "score"),
    )
    response = indicadores.get_indicadores_analise("percentual_nao_comprovacao")
    assert response.municipios == []
    assert response.kpis.total_critico == 0

    joined = pl.DataFrame({"id_cnpj": [1]})
    monkeypatch.setattr(
        indicadores,
        "_build_indicador_dataset_cached",
        lambda *a, **k: (joined, pl.DataFrame(), pl.DataFrame(), "v", "m", None, "score"),
    )
    with pytest.raises(HTTPException) as error:
        indicadores.get_indicadores_analise("percentual_nao_comprovacao")
    assert error.value.status_code == 500


def test_indicator_analysis_rethrows_http_errors_from_dataset(monkeypatch):
    expected = HTTPException(status_code=409, detail="cache conflict")
    monkeypatch.setattr(
        indicadores,
        "_build_indicador_dataset_cached",
        lambda *a, **k: (_ for _ in ()).throw(expected),
    )
    with pytest.raises(HTTPException) as error:
        indicadores.get_indicadores_analise("percentual_nao_comprovacao")
    assert error.value is expected


def _cnpj_analysis_rows(indicador="percentual_nao_comprovacao"):
    c_val, c_mr, _c_mu, _c_mb, c_rr, _c_ru, _c_rb = indicadores.INDICATOR_MAPPING[indicador]
    rows = []
    for index, (cnpj, status, value) in enumerate(
        [("11111111000101", "NORMAL", 2.0), ("22222222000102", "CR\u00cdTICO", 5.0)]
    ):
        rows.append(
            {
                "id_cnpj": index + 1,
                "cnpj": cnpj,
                "razao_social": f"Farmacia {index + 1}",
                "no_municipio": "sao paulo",
                "uf": "SP",
                "id_ibge7": 3550308,
                "is_matriz": index == 0,
                "is_grande_rede": False,
                "qtd_estabelecimentos_rede": 1,
                "situacao_rf": "ATIVA",
                "is_conexao_ativa": True,
                "status": status,
                c_val: value,
                c_mr: 2.5,
                "med_benchmark": 2.5,
                "benchmark_escopo": "REGI\u00c3O",
                c_rr: 1.2,
                "risco_benchmark": 1.2,
                "score_risco_final": 75.0,
                "total_vendas": 100.0,
                "total_sem_comprovacao": 5.0,
                "perc_val_sem_comp": 5.0,
            }
        )
    return pl.DataFrame(rows)


def test_indicator_cnpj_page_sorts_paginates_and_normalizes_bounds(monkeypatch):
    joined = _cnpj_analysis_rows()
    payload = (joined, pl.DataFrame(), pl.DataFrame(), "pct_sem_comprovacao", "med_sem_comprovacao_reg", "risco_sem_comprovacao_reg", "score_risco_final")
    monkeypatch.setattr(indicadores, "_build_indicador_dataset_cached", lambda *a, **k: payload)

    result = indicadores.get_indicadores_analise_cnpjs(
        "percentual_nao_comprovacao", page=0, page_size=0, sort_field="valor", sort_order="asc"
    )

    assert result.page == 1
    assert result.page_size == 20
    assert result.sort_order == "asc"
    assert result.total == 2
    assert len(result.items) == 2
    assert result.items[0].cnpj == "11111111000101"
    assert result.items[0].municipio == "Sao Paulo"
    assert result.kpis.total_normal == 1


def test_indicator_cnpj_page_empty_result_and_required_row_contract(monkeypatch):
    empty = pl.DataFrame(schema={"id_cnpj": pl.Int32})
    monkeypatch.setattr(
        indicadores,
        "_build_indicador_dataset_cached",
        lambda *a, **k: (empty, pl.DataFrame(), pl.DataFrame(), "v", "m", None, "score"),
    )
    result = indicadores.get_indicadores_analise_cnpjs("percentual_nao_comprovacao", page=0, page_size=500)
    assert result.items == []
    assert result.page == 1 and result.page_size == 200

    incomplete = _cnpj_analysis_rows().with_columns(
        pl.lit(None, dtype=pl.Boolean).alias("is_matriz")
    )
    monkeypatch.setattr(
        indicadores,
        "_build_indicador_dataset_cached",
        lambda *a, **k: (incomplete, pl.DataFrame(), pl.DataFrame(), "pct_sem_comprovacao", "med_sem_comprovacao_reg", "risco_sem_comprovacao_reg", "score_risco_final"),
    )
    with pytest.raises(HTTPException) as error:
        indicadores.get_indicadores_analise_cnpjs("percentual_nao_comprovacao")
    assert error.value.status_code == 500


def test_indicator_cnpj_page_rejects_missing_sort_and_display_columns(monkeypatch):
    joined = pl.DataFrame({"cnpj": ["11111111000101"]})
    monkeypatch.setattr(
        indicadores,
        "_build_indicador_dataset_cached",
        lambda *a, **k: (
            joined,
            pl.DataFrame(),
            pl.DataFrame(),
            "pct_sem_comprovacao",
            "med_sem_comprovacao_reg",
            "risco_sem_comprovacao_reg",
            "score_risco_final",
        ),
    )
    with pytest.raises(HTTPException) as missing_sort:
        indicadores.get_indicadores_analise_cnpjs(
            "percentual_nao_comprovacao", sort_field="valor"
        )
    assert missing_sort.value.status_code == 400

    monkeypatch.setattr(
        indicadores,
        "_build_indicador_dataset_cached",
        lambda *a, **k: (
            joined,
            pl.DataFrame(),
            pl.DataFrame(),
            "val_volume_atipico",
            "med_volume_atipico_reg",
            "risco_volume_atipico_reg",
            "score_risco_final",
        ),
    )
    with pytest.raises(HTTPException) as missing_display:
        indicadores.get_indicadores_analise_cnpjs("volume_atipico", sort_field="cnpj")
    assert missing_display.value.status_code == 500


@pytest.mark.parametrize(
    ("value", "expected"),
    [(None, None), (True, None), (12, 12.0), (1.25, 1.25), ("3.5", 3.5), ("bad", None), (object(), None)],
)
def test_optional_float_normalizes_supported_values(value, expected):
    assert indicadores._optional_float(value) == expected


@pytest.mark.parametrize(
    ("normalizer", "value", "expected"),
    [
        (indicadores._normalize_cache_int, 3.0, 3),
        (indicadores._normalize_cache_int, Decimal("2.9"), 2),
        (indicadores._normalize_cache_int, "3", 3),
        (indicadores._normalize_cache_int, None, None),
        (indicadores._normalize_cache_float, "1.25", 1.25),
        (indicadores._normalize_cache_float, 2, 2.0),
        (indicadores._normalize_cache_float, None, None),
        (indicadores._normalize_cache_date, None, None),
        (indicadores._normalize_cache_date, date(2024, 1, 2), "2024-01-02"),
        (indicadores._normalize_cache_date, "2024-01-02", "2024-01-02"),
    ],
)
def test_indicator_cache_normalizers_handle_supported_inputs(normalizer, value, expected):
    assert normalizer(value) == expected


@pytest.mark.parametrize(
    ("normalizer", "value", "error_type"),
    [
        (indicadores._normalize_cache_int, "bad", ValueError),
        (indicadores._normalize_cache_int, True, TypeError),
        (indicadores._normalize_cache_int, 3.9, TypeError),
        (indicadores._normalize_cache_float, "bad", ValueError),
        (indicadores._normalize_cache_float, True, TypeError),
        (indicadores._normalize_cache_int, None, None),
    ],
)
def test_indicator_cache_normalizers_reject_invalid_inputs(normalizer, value, error_type):
    if error_type is None:
        assert normalizer(value) is None
    else:
        with pytest.raises(error_type):
            normalizer(value)


def test_indicator_cache_pruning_generation_and_required_column_guards(monkeypatch):
    cache = indicadores.OrderedDict(
        [((1, "old"), "old"), ((2, "recent"), "recent")]
    )
    indicadores._prune_indicador_cache(cache, 2)
    assert list(cache.items()) == [((2, "recent"), "recent")]
    cache[(2, "next")] = "next"
    indicadores._get_indicador_cache(cache, (2, "recent"))
    assert list(cache) == [(2, "next"), (2, "recent")]
    indicadores._put_indicador_cache(cache, (2, "final"), "final", 2)
    assert list(cache)[-1] == (2, "final")
    large_cache = indicadores.OrderedDict(
        [
            ((2, index), index)
            for index in range(indicadores._INDICADOR_CACHE_MAX_ENTRIES + 1)
        ]
    )
    indicadores._prune_indicador_cache(large_cache, 2)
    assert len(large_cache) == indicadores._INDICADOR_CACHE_MAX_ENTRIES
    assert (2, 0) not in large_cache
    with pytest.raises(RuntimeError, match="geracao invalida"):
        indicadores._cache_generation_from_key((True,))
    with pytest.raises(RuntimeError, match="Colunas obrigatorias ausentes"):
        indicadores._require_columns(pl.DataFrame({"present": [1]}), ["missing"], "teste")

    monkeypatch.setattr(indicadores, "CLINICA_VALOR_MINIMO_DETALHAMENTO", 100.0)
    assert indicadores._valor_financeiro_indicador(
        {"valor_sem_comprovacao": 50.0}, "percentual_nao_comprovacao"
    ) == 50.0
    with pytest.raises(RuntimeError, match="coluna financeira obrigatoria"):
        indicadores._valor_financeiro_indicador({}, "incompatibilidade_patologica")
    assert indicadores._pode_detalhar_indicador(
        {"clinico_valor_suspeito": 100.0}, "incompatibilidade_patologica"
    ) is True
    assert indicadores._pode_detalhar_indicador(
        {"clinico_valor_suspeito": 99.0}, "incompatibilidade_patologica"
    ) is False
    assert indicadores._pode_detalhar_indicador({}, "teto") is False


def test_indicator_cache_normalizers_reject_unsupported_types():
    with pytest.raises(TypeError, match="Tipo invalido"):
        indicadores._normalize_cache_int(object())
    with pytest.raises(TypeError, match="Tipo invalido"):
        indicadores._normalize_cache_float(object())


@pytest.mark.parametrize(
    ("row", "expected"),
    [
        ({"v": None}, "SEM DADOS"),
        ({"v": 1, "a": 1, "c": 0}, "ATENCAO"),
        ({"v": 1, "a": 0, "c": 1}, "CRITICO"),
        ({"v": 1, "a": 0, "c": 0}, "NORMAL"),
    ],
)
def test_indicator_benchmark_status_contract(row, expected):
    assert indicadores._status_indicador_benchmark(
        row, value_col="v", atencao_col="a", critico_col="c"
    ) == expected


def test_indicator_benchmark_row_scope_and_kpi_helpers_enforce_contracts():
    values = {
        "cnpj": "11111111000101",
        "razao_social": "Farmacia Alvo",
        "no_municipio": "Sao Paulo",
        "uf": "SP",
        "is_conexao_ativa": True,
        "is_matriz": True,
        "pct_sem_comprovacao": 8.0,
        "valor_sem_comprovacao": 80.0,
        "valor_total_vendas": 1000.0,
        "med_sem_comprovacao_reg": 6.0,
        "med_sem_comprovacao_uf": 5.0,
        "risco_sem_comprovacao_reg": 1.3,
        "risco_sem_comprovacao_uf": 1.1,
        "flag_percentual_sem_comprovacao_atencao": 0,
        "flag_percentual_sem_comprovacao_critico": 1,
    }
    row = indicadores._indicador_benchmark_row_schema(
        values,
        cnpj_alvo="11111111000101",
        indicador="percentual_nao_comprovacao",
        value_col="pct_sem_comprovacao",
        med_reg_col="med_sem_comprovacao_reg",
        med_uf_col="med_sem_comprovacao_uf",
        risco_reg_col="risco_sem_comprovacao_reg",
        risco_uf_col="risco_sem_comprovacao_uf",
        atencao_col="flag_percentual_sem_comprovacao_atencao",
        critico_col="flag_percentual_sem_comprovacao_critico",
    )
    assert row.is_alvo is True
    assert row.status == "CRITICO"
    assert row.percentual_nao_comprovacao == 8.0
    assert row.valor_financeiro == 80.0

    scope = indicadores._indicador_benchmark_scope_schema(
        escopo="municipio",
        label="Sao Paulo/SP",
        rows_df=pl.DataFrame([values]),
        cnpj_alvo="11111111000101",
        indicador="percentual_nao_comprovacao",
        value_col="pct_sem_comprovacao",
        med_reg_col="med_sem_comprovacao_reg",
        med_uf_col="med_sem_comprovacao_uf",
        risco_reg_col="risco_sem_comprovacao_reg",
        risco_uf_col="risco_sem_comprovacao_uf",
        atencao_col="flag_percentual_sem_comprovacao_atencao",
        critico_col="flag_percentual_sem_comprovacao_critico",
    )
    assert scope.total_estabelecimentos == 1
    assert scope.rows[0].cnpj == row.cnpj
    assert len(
        indicadores._indicador_benchmark_kpis(
            values,
            indicador="percentual_nao_comprovacao",
            value_col="pct_sem_comprovacao",
            med_reg_col="med_sem_comprovacao_reg",
            med_uf_col="med_sem_comprovacao_uf",
            risco_reg_col="risco_sem_comprovacao_reg",
            risco_uf_col="risco_sem_comprovacao_uf",
        )
    ) == 5

    with pytest.raises(RuntimeError, match="Campo obrigatorio is_matriz"):
        indicadores._indicador_benchmark_row_schema(
            {**values, "is_matriz": None},
            cnpj_alvo="11111111000101",
            indicador="percentual_nao_comprovacao",
            value_col="pct_sem_comprovacao",
            med_reg_col="med_sem_comprovacao_reg",
            med_uf_col="med_sem_comprovacao_uf",
            risco_reg_col="risco_sem_comprovacao_reg",
            risco_uf_col="risco_sem_comprovacao_uf",
            atencao_col="flag_percentual_sem_comprovacao_atencao",
            critico_col="flag_percentual_sem_comprovacao_critico",
        )
    row_arguments = {
        "cnpj_alvo": "11111111000101",
        "indicador": "percentual_nao_comprovacao",
        "value_col": "pct_sem_comprovacao",
        "med_reg_col": "med_sem_comprovacao_reg",
        "med_uf_col": "med_sem_comprovacao_uf",
        "risco_reg_col": "risco_sem_comprovacao_reg",
        "risco_uf_col": "risco_sem_comprovacao_uf",
        "atencao_col": "flag_percentual_sem_comprovacao_atencao",
        "critico_col": "flag_percentual_sem_comprovacao_critico",
    }
    with pytest.raises(RuntimeError, match="coluna financeira obrigatoria"):
        indicadores._indicador_benchmark_row_schema(
            {key: value for key, value in values.items() if key != "valor_sem_comprovacao"},
            **row_arguments,
        )
    with pytest.raises(RuntimeError, match="Campo obrigatorio is_conexao_ativa"):
        indicadores._indicador_benchmark_row_schema(
            {key: value for key, value in values.items() if key != "is_conexao_ativa"},
            **row_arguments,
        )


def test_period_marker_handles_reversed_partial_and_unbounded_years():
    reverse = indicadores._indicador_periodo_marcado(date(2024, 5, 1), date(2022, 6, 1))
    assert (reverse.ano_inicio, reverse.ano_fim, reverse.anos) == (2022, 2024, [2022, 2023, 2024])
    from_start = indicadores._indicador_periodo_marcado(date(2023, 1, 1), None)
    assert (from_start.ano_inicio, from_start.ano_fim, from_start.anos) == (2023, 2023, [2023])
    from_end = indicadores._indicador_periodo_marcado(None, date(2025, 2, 1))
    assert (from_end.ano_inicio, from_end.ano_fim, from_end.anos) == (2025, 2025, [2025])
    unbounded = indicadores._indicador_periodo_marcado(None, None)
    assert unbounded.anos == []


def test_build_indicador_scope_base_applies_catalog_filters_and_dispersion(monkeypatch):
    movimento = pl.DataFrame(
        {
            "id_cnpj": [1, 2],
            "periodo": [date(2024, 1, 1), date(2024, 1, 1)],
            "total_vendas": [1000.0, 1000.0],
            "total_sem_comprovacao": [80.0, 200.0],
        }
    )
    perfil = pl.DataFrame(
        {
            "id_cnpj": [1, 2],
            "cnpj": ["11111111000101", "22222222000102"],
            "uf": ["SP", "RJ"],
            "id_regiao_saude": ["10", "20"],
            "id_ibge7": [1, 2],
            "situacao_rf": ["ATIVA", "INAPTA"],
            "is_conexao_ativa": [True, False],
            "porte_empresa": ["ME", "EPP"],
            "is_grande_rede": [True, False],
            "unidade_pf": ["Matriz", "Filial"],
            "no_municipio": ["Sao Paulo", "Rio"],
            "razao_social": ["Farmacia Alvo", "Outra"],
            "nome_fantasia": ["Alvo", "Outra"],
        }
    )
    monkeypatch.setattr(indicadores, "get_df", lambda: movimento)
    monkeypatch.setattr(indicadores, "get_df_perfil_estabelecimento", lambda: perfil)
    monkeypatch.setattr(
        indicadores,
        "get_dispersao_uf_sem_fronteira_id_cnpjs_df",
        lambda *args: pl.DataFrame({"id_cnpj": [1]}),
    )
    monkeypatch.setattr(
        indicadores,
        "build_perfil_filtrado",
        lambda frame, **kwargs: frame,
    )

    scope, _ = indicadores._build_indicador_scope_base(
        data_inicio=date(2024, 1, 1),
        data_fim=date(2024, 1, 31),
        uf="SP",
        regiao_id=10,
        id_ibge7=1,
        situacao_rf="ATIVA",
        conexao_ms="Ativa",
        porte_empresa="ME",
        grande_rede="Sim",
        cnpj_raiz="11111111",
        estabelecimento="Alvo",
        unidade_pf="Matriz",
        perc_min=7.0,
        perc_max=9.0,
        val_min=50.0,
        dispersao_uf_sem_fronteira=True,
        dispersao_uf_sem_fronteira_limite=25.0,
    )

    assert scope["id_cnpj"].to_list() == [1]
    assert scope["perc_val_sem_comp"].to_list() == [8.0]


def test_dispersal_percentage_aggregates_neighbor_pairs_and_year_range(monkeypatch):
    monkeypatch.setattr(indicadores, "UF_BRASILEIRAS", ("SP", "AC"))
    monkeypatch.setattr(indicadores, "UF_VIZINHAS", {"SP": set(), "AC": set()})
    monkeypatch.setattr(
        indicadores,
        "scan_geografico_origem_uf",
        lambda: pl.DataFrame(
            {
                "id_cnpj": [1, 1, 1, 2],
                "ano_base": [2020, 2020, 2019, 2020],
                "uf_farmacia": ["SP", "SP", "SP", "AC"],
                "uf_paciente": ["SP", "AC", "AC", "AC"],
                "valor_autorizado": [70.0, 30.0, 100.0, 0.0],
            }
        ).lazy(),
    )

    result = indicadores._get_pct_dispersao_uf_nao_vizinha_df(
        date(2020, 1, 1), date(2020, 12, 31)
    ).sort("id_cnpj")

    assert result["pct_dispersao_uf_nao_vizinha"].to_list() == [30.0, 0.0]


def _benchmark_profile():
    return pl.DataFrame(
        {
            "id_cnpj": [1, 2, 3],
            "cnpj": ["11111111000101", "22222222000102", "33333333000103"],
            "razao_social": ["Farmacia Alvo", "Farmacia Dois", "Farmacia Tres"],
            "no_municipio": ["Sao Paulo", "Sao Paulo", "Campinas"],
            "uf": ["SP", "SP", "SP"],
            "id_ibge7": [3550308, 3550308, 3509502],
            "id_regiao_saude": ["10", "10", "10"],
            "is_conexao_ativa": [True, False, True],
            "is_matriz": [True, False, True],
        }
    )


def _local_benchmark_matrix(indicador="percentual_nao_comprovacao"):
    c_val, c_mr, c_mu, _c_mb, c_rr, c_ru, _c_rb = indicadores.INDICATOR_MAPPING[indicador]
    c_aten, c_crit = indicadores._INDICATOR_FLAGS[indicador]
    rows = []
    for index, cnpj_id in enumerate((1, 2, 3)):
        row = {
            "id_cnpj": cnpj_id,
            "valor_total_vendas": 1000.0,
            "valor_sem_comprovacao": 50.0 + index,
            c_val: 5.0 + index,
            c_mr: 6.0,
            c_mu: 7.0,
            c_rr: 1.2,
            c_ru: 1.3,
            c_aten: int(index == 1),
            c_crit: int(index == 0),
        }
        if indicador == "volume_atipico":
            row.update(
                {
                    "volume_atipico_valor_aumento_atipico": 500.0 + index,
                    "volume_atipico_soma_excesso_crescimento_pct": 20.0,
                    "volume_atipico_total_semestres_comparaveis": 2,
                }
            )
        if indicador == "falecidos":
            row["falecidos_valor"] = 125.0 + index
        rows.append(row)
    return pl.DataFrame(rows)


def test_get_indicador_benchmark_local_builds_scopes_kpis_and_rows(monkeypatch):
    monkeypatch.setattr(indicadores, "get_df_perfil_estabelecimento", _benchmark_profile)
    monkeypatch.setattr(
        indicadores,
        "_build_dynamic_matriz_risco",
        lambda **kwargs: _local_benchmark_matrix(),
    )

    result = indicadores.get_indicador_benchmark_local(
        "111.111.110/001-01", "percentual_nao_comprovacao", date(2024, 1, 1), date(2024, 12, 31)
    )

    assert result.cnpj == "11111111000101"
    assert result.kpis[0].value == 5.0
    assert result.municipio.total_estabelecimentos == 2
    assert result.regiao_saude.total_estabelecimentos == 3
    target_row = next(row for row in result.municipio.rows if row.is_alvo)
    assert target_row.status == "CRITICO"
    assert target_row.percentual_nao_comprovacao == 5.0


def test_get_indicador_benchmark_local_handles_volume_display_metric(monkeypatch):
    monkeypatch.setattr(indicadores, "get_df_perfil_estabelecimento", _benchmark_profile)
    monkeypatch.setattr(
        indicadores,
        "_build_dynamic_matriz_risco",
        lambda **kwargs: _local_benchmark_matrix("volume_atipico"),
    )

    result = indicadores.get_indicador_benchmark_local(
        "11111111000101", "volume_atipico"
    )

    target_row = next(row for row in result.municipio.rows if row.is_alvo)
    assert target_row.valor == 500.0
    assert target_row.valor_numerador == 500.0
    assert target_row.valor_denominador is None
    assert result.kpis[0].value == 500.0


def test_get_indicador_benchmark_local_requires_financial_metric_column(monkeypatch):
    monkeypatch.setattr(indicadores, "get_df_perfil_estabelecimento", _benchmark_profile)
    monkeypatch.setattr(
        indicadores,
        "_build_dynamic_matriz_risco",
        lambda **kwargs: _local_benchmark_matrix("falecidos"),
    )

    result = indicadores.get_indicador_benchmark_local(
        "11111111000101", "falecidos"
    )

    target_row = next(row for row in result.municipio.rows if row.is_alvo)
    assert target_row.valor_financeiro == 125.0


@pytest.mark.parametrize(
    ("profile", "matrix", "expected_error"),
    [
        (_benchmark_profile().filter(pl.col("id_cnpj") != 1), _local_benchmark_matrix(), "CNPJ nao encontrado"),
        (
            _benchmark_profile().with_columns(pl.lit(None, dtype=pl.Int64).alias("id_ibge7")),
            _local_benchmark_matrix(),
            "id_ibge7/id_regiao_saude obrigatorios",
        ),
        (
            _benchmark_profile(),
            _local_benchmark_matrix().filter(pl.col("id_cnpj") != 1),
            "nao retornou o CNPJ alvo",
        ),
    ],
    ids=["target-absent", "missing-geographic-ids", "target-absent-from-matrix"],
)
def test_get_indicador_benchmark_local_rejects_incomplete_scope(
    profile, matrix, expected_error, monkeypatch
):
    monkeypatch.setattr(indicadores, "get_df_perfil_estabelecimento", lambda: profile)
    monkeypatch.setattr(indicadores, "_build_dynamic_matriz_risco", lambda **kwargs: matrix)
    with pytest.raises((HTTPException, RuntimeError), match=expected_error):
        indicadores.get_indicador_benchmark_local(
            "11111111000101", "percentual_nao_comprovacao"
        )


@pytest.mark.parametrize(
    ("cnpj", "indicador", "status"),
    [
        ("123", "percentual_nao_comprovacao", 422),
        ("11111111000101", "nao_existe", 400),
    ],
)
def test_get_indicador_benchmark_local_rejects_invalid_request(cnpj, indicador, status):
    with pytest.raises(HTTPException) as error:
        indicadores.get_indicador_benchmark_local(cnpj, indicador)
    assert error.value.status_code == status


def _annual_benchmark_matrix(indicador="percentual_nao_comprovacao"):
    c_val, c_mr, c_mu, _c_mb, _c_rr, _c_ru, _c_rb = indicadores.INDICATOR_MAPPING[indicador]
    rows = []
    for year, value, sales, unverified in (
        (2020, 4.0, 100.0, 4.0),
        (2021, 6.0, 200.0, 12.0),
    ):
        row = {
            "id_cnpj": 1,
            "ano_base": year,
            c_val: value,
            c_mr: value + 1.0,
            c_mu: value + 2.0,
            "valor_total_vendas": sales,
            "valor_sem_comprovacao": unverified,
        }
        if indicador == "volume_atipico":
            row.update(
                {
                    "uf": "SP",
                    "id_regiao_saude": "10",
                    "volume_atipico_valor_aumento_atipico": 500.0 + year,
                    "volume_atipico_soma_excesso_crescimento_pct": 20.0,
                    "volume_atipico_total_semestres_comparaveis": 2,
                }
            )
        rows.append(row)
    return pl.DataFrame(rows)


@pytest.mark.parametrize(
    ("indicador", "expected_values", "expected_numerators"),
    [
        ("percentual_nao_comprovacao", [4.0, 6.0], [4.0, 12.0]),
        ("volume_atipico", [2520.0, 2521.0], [2520.0, 2521.0]),
    ],
)
def test_get_indicador_evolucao_benchmark_builds_annual_series(
    indicador, expected_values, expected_numerators, monkeypatch
):
    monkeypatch.setattr(
        indicadores,
        "get_df_perfil_estabelecimento",
        lambda: pl.DataFrame(
            {
                "id_cnpj": [1],
                "cnpj": ["11111111000101"],
                "uf": ["SP"],
                "id_regiao_saude": ["10"],
            }
        ),
    )
    monkeypatch.setattr(
        indicadores,
        "build_annual_indicator_benchmark_matriz",
        lambda: _annual_benchmark_matrix(indicador),
    )

    result = indicadores.get_indicador_evolucao_benchmark(
        "11111111000101", indicador, date(2020, 1, 1), date(2021, 12, 31)
    )

    assert result.periodo_marcado.anos == [2020, 2021]
    assert [point.farmacia for point in result.series] == expected_values
    assert [point.valor_numerador for point in result.series] == expected_numerators
    assert [point.percentual_nao_comprovacao for point in result.series] == [4.0, 6.0]


@pytest.mark.parametrize(
    ("cnpj", "indicador", "status"),
    [
        ("123", "percentual_nao_comprovacao", 422),
        ("11111111000101", "desconhecido", 400),
    ],
)
def test_get_indicador_evolucao_benchmark_rejects_invalid_request(cnpj, indicador, status):
    with pytest.raises(HTTPException) as error:
        indicadores.get_indicador_evolucao_benchmark(cnpj, indicador)
    assert error.value.status_code == status


def test_get_indicador_evolucao_benchmark_rejects_missing_profile_id_and_series(monkeypatch):
    profile = pl.DataFrame(
        {
            "id_cnpj": [1],
            "cnpj": ["11111111000101"],
            "uf": ["SP"],
            "id_regiao_saude": ["10"],
        }
    )
    monkeypatch.setattr(indicadores, "get_df_perfil_estabelecimento", lambda: profile)
    with pytest.raises(HTTPException) as missing:
        indicadores.get_indicador_evolucao_benchmark(
            "22222222000102", "percentual_nao_comprovacao"
        )
    assert missing.value.status_code == 404

    no_id = profile.with_columns(pl.lit(None, dtype=pl.Int64).alias("id_cnpj"))
    monkeypatch.setattr(indicadores, "get_df_perfil_estabelecimento", lambda: no_id)
    with pytest.raises(RuntimeError, match="id_cnpj obrigatorio"):
        indicadores.get_indicador_evolucao_benchmark(
            "11111111000101", "percentual_nao_comprovacao"
        )

    monkeypatch.setattr(indicadores, "get_df_perfil_estabelecimento", lambda: profile)
    no_target = _annual_benchmark_matrix().with_columns(pl.lit(2).alias("id_cnpj"))
    monkeypatch.setattr(
        indicadores, "build_annual_indicator_benchmark_matriz", lambda: no_target
    )
    with pytest.raises(RuntimeError, match="nao possui serie para o CNPJ alvo"):
        indicadores.get_indicador_evolucao_benchmark(
            "11111111000101", "percentual_nao_comprovacao"
        )


def test_volume_evolution_requires_target_geographic_context(monkeypatch):
    profile = pl.DataFrame(
        {
            "id_cnpj": [1],
            "cnpj": ["11111111000101"],
            "uf": [None],
            "id_regiao_saude": ["10"],
        }
    )
    monkeypatch.setattr(indicadores, "get_df_perfil_estabelecimento", lambda: profile)
    monkeypatch.setattr(
        indicadores,
        "build_annual_indicator_benchmark_matriz",
        lambda: _annual_benchmark_matrix("volume_atipico"),
    )

    with pytest.raises(RuntimeError, match="uf/id_regiao_saude"):
        indicadores.get_indicador_evolucao_benchmark("11111111000101", "volume_atipico")


def test_get_indicadores_returns_empty_for_missing_target_and_wraps_unexpected_error(monkeypatch):
    monkeypatch.setattr(
        indicadores,
        "get_df_perfil_estabelecimento",
        lambda: pl.DataFrame({"cnpj": ["22222222000102"]}),
    )
    monkeypatch.setattr(
        indicadores,
        "_build_dynamic_matriz_risco",
        lambda **kwargs: pytest.fail("CNPJ inexistente deve retornar antes de calcular a matriz"),
    )
    missing = indicadores.get_indicadores("11111111000101")
    assert missing.indicadores == {}

    monkeypatch.setattr(
        indicadores,
        "get_df_perfil_estabelecimento",
        lambda: pl.DataFrame({"cnpj": ["11111111000101"]}),
    )
    monkeypatch.setattr(
        indicadores,
        "_build_dynamic_matriz_risco",
        lambda **kwargs: (_ for _ in ()).throw(RuntimeError("matriz indisponivel")),
    )
    with pytest.raises(HTTPException) as error:
        indicadores.get_indicadores("11111111000101")
    assert error.value.status_code == 503
