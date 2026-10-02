from datetime import date

import polars as pl

from api.services.analytics import regional
from api.services.analytics import matriz_risco_dinamica as dynamic_matrix


def _install_dynamic_matrix(monkeypatch, profile, ids):
    rows = []
    for identifier in ids:
        row = {column: 0.0 for column in dynamic_matrix._MATRIX_COMPONENT_COLUMNS}
        row.update({"id_cnpj": identifier, "ano_base": 2020, "valor_total_vendas": 100.0, "valor_sem_comprovacao": 20.0})
        rows.append(row)
    monkeypatch.setattr(dynamic_matrix, "get_df_matriz_risco", lambda: pl.DataFrame(rows))
    monkeypatch.setattr(dynamic_matrix, "get_df_perfil_estabelecimento", lambda: profile)
    monkeypatch.setattr(dynamic_matrix, "get_cache_generation", lambda: 992)
    monkeypatch.setattr(dynamic_matrix, "get_volume_atipico_aumento_minimo", lambda: 10000.0)
    dynamic_matrix._DYNAMIC_CACHE.clear()


def test_regional_benchmarking_filters_by_region_id_and_builds_municipal_metrics(monkeypatch):
    movimento = pl.DataFrame(
        {
            "id_cnpj": [1, 1, 2],
            "periodo": [date(2020, 1, 1), date(2020, 2, 1), date(2020, 1, 1)],
            "total_vendas": [100.0, 50.0, 900.0],
            "total_sem_comprovacao": [10.0, 5.0, 90.0],
        }
    )
    perfil = pl.DataFrame(
        {
            "id_cnpj": [1, 2], "cnpj": ["11111111000101", "22222222000102"],
            "uf": ["SP", "SP"], "id_regiao_saude": ["10", "20"],
            "id_ibge7": [3550308, 3509502], "no_municipio": ["sao paulo", "campinas"],
            "razao_social": ["FARMACIA UM", "FARMACIA DOIS"], "is_conexao_ativa": [True, False],
        }
    )
    localidades = pl.DataFrame(
        {"id_ibge7": [3550308, 3509502], "nu_populacao": [1000, 2000], "id_regiao_saude": ["10", "20"], "no_regiao_saude": ["Regiao A", "Regiao B"]}
    )
    monkeypatch.setattr(regional, "get_df", lambda: movimento)
    monkeypatch.setattr(regional, "get_df_perfil_estabelecimento", lambda: perfil)
    monkeypatch.setattr(regional, "get_localidades_df", lambda: localidades)
    _install_dynamic_matrix(monkeypatch, perfil, [1, 2])

    result = regional.get_regional_benchmarking(uf="SP", data_inicio=date(2020, 1, 1), regiao_id=10)
    assert result.id_regiao == "10"
    assert len(result.farmacias) == 1
    assert result.farmacias[0].cnpj == "11111111000101"
    assert result.municipios[0].totalMov == 150.0
    assert result.municipios[0].populacao == 1000
    assert result.municipios[0].percValSemComp == 10.0


def test_metric_percentiles_scopes_and_clips_percentage_outliers(monkeypatch):
    source = pl.DataFrame(
        {
            "id_cnpj": [1, 2, 3], "uf": ["SP", "SP", "RJ"],
            "id_regiao_saude": ["10", "10", "20"],
            "score_risco_final": [1.0, 3.0, 99.0],
            "pct_sem_comprovacao": [5.0, 150.0, 80.0],
        }
    )
    monkeypatch.setattr(regional, "build_dynamic_matriz_risco", lambda **kwargs: source)

    scores = regional.get_metric_percentiles("uf", uf="SP")
    pct = regional.get_metric_percentiles("uf", uf="SP", metric="percentual_sem_comprovacao")
    assert len(scores) == len(pct) == 100
    assert scores[-1]["score"] == 3.0
    assert pct[-1]["score"] == 100.0
    assert regional.get_metric_percentiles("uf", uf="ZZ") == []


def test_regional_animation_builds_two_month_windows_and_scoped_rankings(monkeypatch):
    movement = pl.DataFrame(
        {
            "id_cnpj": [1, 1], "periodo": [date(2020, 1, 1), date(2020, 3, 1)],
            "total_vendas": [100.0, 200.0], "total_sem_comprovacao": [5.0, 40.0],
        }
    )
    profile = pl.DataFrame(
        {
            "id_cnpj": [1], "cnpj": ["12345678000190"], "uf": ["SP"], "id_regiao_saude": ["10"],
            "id_ibge7": [1], "no_municipio": ["sao paulo"], "razao_social": ["FARMACIA A"], "is_conexao_ativa": [True],
        }
    )
    monkeypatch.setattr(regional, "get_df", lambda: movement)
    monkeypatch.setattr(regional, "get_df_perfil_estabelecimento", lambda: profile)
    monkeypatch.setattr(regional, "get_localidades_df", lambda: pl.DataFrame())
    _install_dynamic_matrix(monkeypatch, profile, [1])

    result = regional.get_regional_benchmarking_animation(
        uf="SP", data_inicio=date(2020, 1, 1), data_fim=date(2020, 4, 30)
    )
    assert [q.trimestre for q in result.quarters] == ["2020-01", "2020-03"]
    assert [q.farmacias[0].rank for q in result.quarters] == [1, 1]
    assert [q.farmacias[0].valSemComp for q in result.quarters] == [5.0, 40.0]


def test_percentile_animation_returns_one_window_per_month(monkeypatch):
    movement = pl.DataFrame(
        {"id_cnpj": [1], "periodo": [date(2020, 1, 1)], "total_vendas": [100.0], "total_sem_comprovacao": [25.0]}
    )
    profile = pl.DataFrame({"id_cnpj": [1], "uf": ["SP"], "id_regiao_saude": ["10"]})
    monkeypatch.setattr(regional, "get_df", lambda: movement)
    monkeypatch.setattr(regional, "get_df_perfil_estabelecimento", lambda: profile)

    result = regional.get_metric_percentiles_animation(
        scope="uf", uf="SP", metric="percentual_sem_comprovacao",
        data_inicio=date(2020, 1, 1), data_fim=date(2020, 2, 29),
    )
    assert len(result["quarters"]) == 2
    assert result["quarters"][0]["percentiles"][-1]["score"] == 25.0

    brasil = regional.get_metric_percentiles_animation(
        scope="brasil", metric="percentual_sem_comprovacao",
        data_inicio=date(2020, 1, 1), data_fim=date(2020, 1, 31),
    )
    assert len(brasil["quarters"]) == 1
    assert brasil["quarters"][0]["percentiles"][-1]["score"] == 25.0


def test_cnpj_lookup_returns_slim_unique_records(monkeypatch):
    monkeypatch.setattr(
        regional, "get_rede_df",
        lambda: pl.DataFrame(
            {"cnpj": ["2", "1", "1"], "razao_social": ["B", "A", "A"], "municipio": ["Y", "X", "X"], "uf": ["RJ", "SP", "SP"]}
        ),
    )
    assert regional.get_cnpj_lookup() == [
        {"cnpj": "1", "razao_social": "A", "municipio": "X", "uf": "SP"},
        {"cnpj": "2", "razao_social": "B", "municipio": "Y", "uf": "RJ"},
    ]


def test_regional_benchmarking_returns_empty_scope_when_period_has_no_movements(monkeypatch):
    monkeypatch.setattr(
        regional, "get_df",
        lambda: pl.DataFrame(
            {"id_cnpj": [1], "periodo": [date(2020, 1, 1)], "total_vendas": [10.0],
             "total_sem_comprovacao": [1.0]}
        ),
    )
    monkeypatch.setattr(regional, "get_df_perfil_estabelecimento", lambda: pl.DataFrame({"id_cnpj": [1], "uf": ["SP"]}))
    monkeypatch.setattr(regional, "get_localidades_df", lambda: pl.DataFrame())

    result = regional.get_regional_benchmarking(uf="SP", data_inicio=date(2021, 1, 1), data_fim=date(2021, 12, 31))

    assert result.nome_regiao == "SP"
    assert result.municipios == []
    assert result.farmacias == []


def test_regional_benchmarking_resolves_region_label_and_returns_rank(monkeypatch):
    movement = pl.DataFrame(
        {
            "id_cnpj": [1], "periodo": [date(2020, 1, 1)], "total_vendas": [100.0],
            "total_sem_comprovacao": [10.0],
        }
    )
    profile = pl.DataFrame(
        {
            "id_cnpj": [1], "cnpj": ["11111111000101"], "uf": ["SP"], "id_regiao_saude": ["10"],
            "id_ibge7": [3550308],
            "no_municipio": ["sao paulo"], "razao_social": ["FARMACIA UM"], "is_conexao_ativa": [True],
        }
    )
    localities = pl.DataFrame(
        {
            "id_regiao_saude": [10], "id_ibge7": [3550308], "nu_populacao": [1000],
            "no_regiao_saude": ["Regiao A"], "sg_uf": ["SP"],
        }
    )
    monkeypatch.setattr(regional, "get_df", lambda: movement)
    monkeypatch.setattr(regional, "get_df_perfil_estabelecimento", lambda: profile)
    monkeypatch.setattr(regional, "get_localidades_df", lambda: localities)
    monkeypatch.setattr(
        regional, "build_dynamic_matriz_risco",
        lambda **_kwargs: pl.DataFrame({"id_cnpj": [1], "score_risco_final": [55.0], "classificacao_risco": ["CRÍTICO"]}),
    )

    result = regional.get_regional_benchmarking(
        uf="Todos", regiao_id=10, data_inicio=date(2020, 1, 1), data_fim=date(2020, 1, 31)
    )

    assert result.nome_regiao == "Regiao A"
    assert result.id_regiao == "10"
    assert result.municipios[0].id_ibge7 == 3550308
    assert result.municipios[0].densidade == 1000.0
    assert result.farmacias[0].rank == 1
    assert result.farmacias[0].score_risco == 55.0


def test_regional_benchmarking_joins_municipality_id_when_movement_lacks_it(monkeypatch):
    movement = pl.DataFrame(
        {
            "id_cnpj": [1], "periodo": [date(2020, 1, 1)],
            "total_vendas": [100.0], "total_sem_comprovacao": [10.0],
        }
    )
    profile_without_municipality_id = pl.DataFrame(
        {
            "id_cnpj": [1], "cnpj": ["11111111000101"], "uf": ["SP"],
            "id_regiao_saude": ["10"], "no_municipio": ["sao paulo"],
            "razao_social": ["FARMACIA UM"], "is_conexao_ativa": [True],
        }
    )
    profile_with_municipality_id = pl.DataFrame(
        {"id_cnpj": [1], "id_ibge7": [3550308]}
    )
    localities = pl.DataFrame(
        {
            "id_ibge7": [3550308], "nu_populacao": [1000],
            "id_regiao_saude": ["10"],
        }
    )
    profile_calls = iter(
        [profile_without_municipality_id, profile_with_municipality_id]
    )
    monkeypatch.setattr(regional, "get_df", lambda: movement)
    monkeypatch.setattr(
        regional,
        "get_df_perfil_estabelecimento",
        lambda: next(profile_calls),
    )
    monkeypatch.setattr(regional, "get_localidades_df", lambda: localities)
    monkeypatch.setattr(
        regional,
        "build_dynamic_matriz_risco",
        lambda **_kwargs: pl.DataFrame(
            {"id_cnpj": [1], "score_risco_final": [55.0], "classificacao_risco": ["CRÍTICO"]}
        ),
    )

    result = regional.get_regional_benchmarking(
        uf="SP", data_inicio=date(2020, 1, 1), data_fim=date(2020, 1, 31)
    )

    assert result.municipios[0].id_ibge7 == 3550308
    assert result.farmacias[0].id_ibge7 == 3550308


def test_regional_benchmarking_converts_dependency_failure_to_empty_payload(monkeypatch):
    monkeypatch.setattr(regional, "get_df", lambda: (_ for _ in ()).throw(RuntimeError("cache unavailable")))

    result = regional.get_regional_benchmarking(uf="RJ")

    assert result.nome_regiao == "RJ"
    assert result.municipios == []
    assert result.farmacias == []


def test_regional_animation_resolves_region_and_returns_empty_for_no_match(monkeypatch):
    movement = pl.DataFrame(
        {"id_cnpj": [1], "periodo": [date(2020, 1, 1)], "total_vendas": [10.0], "total_sem_comprovacao": [1.0]}
    )
    profile = pl.DataFrame({"id_cnpj": [1], "uf": ["SP"], "id_regiao_saude": ["10"]})
    localities = pl.DataFrame(
        {"id_regiao_saude": [10], "no_regiao_saude": ["Regiao A"], "sg_uf": ["SP"]}
    )
    monkeypatch.setattr(regional, "get_df", lambda: movement)
    monkeypatch.setattr(regional, "get_df_perfil_estabelecimento", lambda: profile)
    monkeypatch.setattr(regional, "get_localidades_df", lambda: localities)

    result = regional.get_regional_benchmarking_animation(
        uf="Todos", regiao_id=10, data_inicio=date(2021, 1, 1), data_fim=date(2021, 3, 31)
    )

    assert result.nome_regiao == "Regiao A"
    assert result.quarters == []


def test_regional_animation_converts_dependency_failure_to_empty_payload(monkeypatch):
    monkeypatch.setattr(regional, "get_df", lambda: (_ for _ in ()).throw(RuntimeError("cache unavailable")))

    result = regional.get_regional_benchmarking_animation(uf="SP")

    assert result.nome_regiao == "SP"
    assert result.quarters == []


def test_dynamic_percentile_query_aggregates_percentages_for_region_and_date_scope(monkeypatch):
    movement = pl.DataFrame(
        {
            "id_cnpj": [1, 2], "periodo": [date(2020, 1, 1), date(2020, 1, 1)],
            "total_vendas": [100.0, 200.0], "total_sem_comprovacao": [150.0, 40.0],
        }
    )
    profile = pl.DataFrame(
        {
            "id_cnpj": [1, 2], "cnpj": ["a", "b"], "uf": ["SP", "RJ"],
            "id_regiao_saude": ["10", "20"], "no_municipio": ["x", "y"],
        }
    )
    monkeypatch.setattr(regional, "get_df", lambda: movement)
    monkeypatch.setattr(regional, "get_df_perfil_estabelecimento", lambda: profile)

    values = regional.get_metric_percentiles(
        "regiao", regiao_id="10", metric="percentual_sem_comprovacao",
        data_inicio=date(2020, 1, 1), data_fim=date(2020, 1, 31),
    )

    assert len(values) == 100
    assert values[-1]["score"] == 100.0


def test_percentiles_support_region_and_brazil_scopes_and_handle_invalid_matrix(monkeypatch):
    source = pl.DataFrame(
        {
            "id_cnpj": [1, 2], "uf": ["SP", "RJ"], "id_regiao_saude": ["10", "20"],
            "score_risco_final": [3.0, 9.0],
        }
    )
    monkeypatch.setattr(regional, "build_dynamic_matriz_risco", lambda **_kwargs: source)
    assert regional.get_metric_percentiles("regiao", regiao_id="10")[-1]["score"] == 3.0
    assert regional.get_metric_percentiles("brasil")[-1]["score"] == 9.0

    monkeypatch.setattr(regional, "build_dynamic_matriz_risco", lambda **_kwargs: pl.DataFrame())
    assert regional.get_metric_percentiles("brasil") == []


def test_metric_percentiles_returns_empty_and_logs_when_matrix_build_fails(monkeypatch, capsys):
    monkeypatch.setattr(
        regional,
        "build_dynamic_matriz_risco",
        lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("matriz indisponivel")),
    )

    assert regional.get_metric_percentiles("brasil") == []
    assert "matriz indisponivel" in capsys.readouterr().out


def test_percentile_animation_supports_region_empty_windows_and_score_windows(monkeypatch):
    movement = pl.DataFrame(
        {
            "id_cnpj": [1], "periodo": [date(2020, 1, 1)],
            "total_vendas": [100.0], "total_sem_comprovacao": [25.0],
        }
    )
    profile = pl.DataFrame({"id_cnpj": [1], "uf": ["SP"], "id_regiao_saude": ["10"]})
    monkeypatch.setattr(regional, "get_df", lambda: movement)
    monkeypatch.setattr(regional, "get_df_perfil_estabelecimento", lambda: profile)

    percentages = regional.get_metric_percentiles_animation(
        scope="regiao", regiao_id="10", metric="percentual_sem_comprovacao",
        data_inicio=date(2020, 1, 1), data_fim=date(2020, 4, 30),
    )
    assert len(percentages["quarters"]) == 4
    assert percentages["quarters"][0]["percentiles"][-1]["score"] == 25.0
    assert percentages["quarters"][-1]["percentiles"] == []

    calls = []
    monkeypatch.setattr(regional, "get_metric_percentiles", lambda *args: calls.append(args) or [{"percentile": 100, "score": 5.0}])
    scores = regional.get_metric_percentiles_animation(
        scope="uf", uf="SP", metric="score", data_inicio=date(2020, 1, 1), data_fim=date(2020, 2, 29)
    )
    assert len(scores["quarters"]) == 2
    assert len(calls) == 2
    assert calls[0][:4] == ("uf", "SP", None, "score")


def test_cnpj_lookup_returns_empty_when_cache_is_unavailable(monkeypatch):
    monkeypatch.setattr(regional, "get_rede_df", lambda: (_ for _ in ()).throw(RuntimeError("cache offline")))

    assert regional.get_cnpj_lookup() == []
