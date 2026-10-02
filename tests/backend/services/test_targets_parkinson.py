"""Clinical-target calculations against complete, tiny Polars cache fixtures."""

from datetime import date

import polars as pl
import pytest
from fastapi import HTTPException

from api.services.targets import parkinson as targets
from api.services.analytics.indicator_rules import (
    DIABETES_PREVALENCIA_MENOR_20,
    IBGE_ANO_CENSO_DEMOGRAFIA,
    PARKINSON_PREVALENCIA_50_MAIS,
)


def _clinical(*, pathology="DOENCA DE PARKINSON", rule="IDADE_MENOR_50", rows=None):
    if rows is None:
        rows = [
        {"id_cnpj": 1, "id_ibge7": 4205407, "patologia": pathology, "regra_clinica": rule,
         "ano_base": 2024, "qtd_cpfs_incompativeis": 2, "qtd_autorizacoes_incompativeis": 3,
         "valor_incompativel_pago": 100.0},
        {"id_cnpj": 2, "id_ibge7": 4205407, "patologia": pathology, "regra_clinica": rule,
         "ano_base": 2024, "qtd_cpfs_incompativeis": 4, "qtd_autorizacoes_incompativeis": 5,
         "valor_incompativel_pago": 300.0},
    ]
    return pl.DataFrame(rows)


def _profile(rows=None):
    if rows is None:
        rows = [
        {"id_cnpj": 1, "cnpj": "00000000000001", "razao_social": "Farma A", "uf": "SC",
         "id_ibge7": 4205407, "id_regiao_saude": 4201, "no_municipio": "Florianópolis",
         "is_matriz": True, "is_conexao_ativa": False},
        {"id_cnpj": 2, "cnpj": "00000000000002", "razao_social": "Farma B", "uf": "SC",
         "id_ibge7": 4205407, "id_regiao_saude": 4201, "no_municipio": "Florianópolis",
         "is_matriz": False, "is_conexao_ativa": True},
    ]
    return pl.DataFrame(rows)


def _demography(ages=(49, 50), *, values=None, year=IBGE_ANO_CENSO_DEMOGRAFIA):
    values = values or {}
    rows = []
    for age in ages:
        for sex in ("F", "M"):
            rows.append({
                "id_ibge7": 4205407,
                "ano_censo": year,
                "idade_min": age,
                "nu_populacao": values.get((age, sex), 100 if age == 50 else 50),
                "sexo": sex,
            })
    return pl.DataFrame(rows)


def _install(monkeypatch, clinical=None, demography=None, profile=None):
    clinical = clinical if clinical is not None else _clinical()
    monkeypatch.setattr(targets, "scan_analise_gtin_inconsistencia_clinica", lambda: clinical.lazy())
    monkeypatch.setattr(targets, "get_df_dados_ibge_demografia", lambda: demography if demography is not None else _demography())
    monkeypatch.setattr(targets, "get_df_perfil_estabelecimento", lambda: profile if profile is not None else _profile())


def test_parkinson_target_aggregates_map_kpis_and_paginates(monkeypatch):
    _install(monkeypatch)

    response = targets.get_parkinson_menor_50(
        data_inicio=date(2024, 1, 1), data_fim=date(2024, 12, 31),
        uf="sc", regiao_id=4201, id_ibge7=4205407, page=2, page_size=1,
        sort_field="valor_incompativel", sort_order="desc",
    )

    assert response.total == 2
    assert response.page == 2
    assert response.page_size == 1
    assert response.items[0].cnpj == "00000000000001"
    assert response.items[0].casos_observados == 2
    assert response.items[0].casos_observados_municipio == 6
    assert response.items[0].casos_esperados == pytest.approx(200 * PARKINSON_PREVALENCIA_50_MAIS)
    assert response.items[0].populacao_referencia is None
    assert response.items[0].participacao_municipio == pytest.approx(0.25)
    assert {item.key: item.value for item in response.kpis} == {
        "farmacias": 2, "valor_incompativel": 400.0, "cpfs_envolvidos": 6,
        "municipios": 1, "ufs": 1,
    }
    assert response.mapa[0].total_farmacias == 2
    assert response.mapa[0].participacao_uf == pytest.approx(1.0)


def test_diabetes_target_calculates_under_twenty_population_fields(monkeypatch):
    clinical = _clinical(pathology="DIABETES", rule="IDADE_MENOR_20")
    demography = _demography(
        ages=(0, 19, 20, 50),
        values={(0, "F"): 10, (0, "M"): 20, (19, "F"): 30, (19, "M"): 40,
                (20, "F"): 60, (20, "M"): 70, (50, "F"): 80, (50, "M"): 90},
    )
    _install(monkeypatch, clinical=clinical, demography=demography)

    response = targets.get_diabetes_menor_20(
        sort_field="razao_observado_esperado", sort_order="asc"
    )

    assert response.total == 2
    assert response.items[0].casos_esperados == pytest.approx(100 * DIABETES_PREVALENCIA_MENOR_20)
    assert response.items[0].populacao_referencia == 100
    assert response.items[0].razao_observado_esperado == pytest.approx(2 / (100 * DIABETES_PREVALENCIA_MENOR_20))
    assert response.items[0].percentual_observado_populacao == pytest.approx(2 / 100)


def test_target_returns_empty_for_period_without_observations_and_keeps_requested_page(monkeypatch):
    _install(monkeypatch)

    response = targets.get_parkinson_menor_50(
        data_inicio=date(2025, 1, 1), data_fim=date(2025, 12, 31), page=3, page_size=7,
    )

    assert response.total == 0
    assert response.items == []
    assert response.mapa == []
    assert response.page == 3
    assert response.page_size == 7
    assert {item.value for item in response.kpis} == {0, 0.0}


def test_target_keeps_filtered_map_when_id_filter_has_no_matching_pharmacy(monkeypatch):
    _install(monkeypatch)

    response = targets.get_parkinson_menor_50(uf="SC", id_ibge7=9999999)

    assert response.total == 0
    assert response.items == []
    assert len(response.mapa) == 1
    assert response.mapa[0].id_ibge7 == 4205407
    assert response.mapa[0].valor_incompativel == 400.0


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"page": 0}, "page deve ser maior ou igual"),
        ({"page_size": 201}, "page_size deve estar entre"),
        ({"data_inicio": date(2025, 1, 1), "data_fim": date(2024, 1, 1)}, "data_inicio nao pode ser maior"),
    ],
)
def test_target_rejects_invalid_page_and_period_before_reading_sources(monkeypatch, kwargs, message):
    scan = lambda: pytest.fail("cache não deve ser consultado antes de validar os parâmetros")
    monkeypatch.setattr(targets, "scan_analise_gtin_inconsistencia_clinica", scan)

    with pytest.raises(HTTPException) as error:
        targets.get_parkinson_menor_50(**kwargs)

    assert error.value.status_code == 422
    assert message in error.value.detail


def test_target_fails_visibly_for_missing_clinical_and_profile_columns(monkeypatch):
    monkeypatch.setattr(targets, "scan_analise_gtin_inconsistencia_clinica", lambda: pl.DataFrame({"id_cnpj": [1]}).lazy())
    with pytest.raises(HTTPException, match="Colunas ausentes") as clinical_error:
        targets.get_parkinson_menor_50()
    assert clinical_error.value.status_code == 500

    _install(monkeypatch, profile=pl.DataFrame({"id_cnpj": [1]}))
    with pytest.raises(HTTPException, match="Colunas ausentes") as profile_error:
        targets.get_parkinson_menor_50()
    assert "perfil_estabelecimento" in profile_error.value.detail


def test_target_rejects_unknown_ids_and_missing_profile_rows(monkeypatch):
    bad_ids = _clinical(rows=[{
        "id_cnpj": None, "id_ibge7": 4205407, "patologia": "DOENCA DE PARKINSON",
        "regra_clinica": "IDADE_MENOR_50", "ano_base": 2024,
        "qtd_cpfs_incompativeis": 2, "qtd_autorizacoes_incompativeis": 3,
        "valor_incompativel_pago": 100.0,
    }])
    _install(monkeypatch, clinical=bad_ids)
    with pytest.raises(HTTPException, match="id_cnpj/id_ibge7/ano_base invalido"):
        targets.get_parkinson_menor_50()

    absent_profile = _profile().filter(pl.col("id_cnpj") == 99)
    _install(monkeypatch, profile=absent_profile)
    with pytest.raises(HTTPException, match="Perfil ausente para alvo"):
        targets.get_parkinson_menor_50()


def test_target_rejects_null_expected_case_calculation(monkeypatch):
    _install(monkeypatch)
    monkeypatch.setattr(
        targets,
        "_add_parkinson_municipal_expected",
        lambda frame: frame.with_columns(pl.lit(None, dtype=pl.Float64).alias("casos_esperados")),
    )
    with pytest.raises(HTTPException, match="casos_esperados nulo"):
        targets.get_parkinson_menor_50()


def test_target_rejects_invalid_sort_and_incomplete_profile_flags(monkeypatch):
    _install(monkeypatch)
    with pytest.raises(HTTPException, match="Campo de ordenacao invalido"):
        targets.get_parkinson_menor_50(sort_field="nome_inexistente")
    with pytest.raises(HTTPException, match="sort_order deve ser asc ou desc"):
        targets.get_parkinson_menor_50(sort_order="random")

    profile = _profile().with_columns(pl.lit(None, dtype=pl.Boolean).alias("is_matriz"))
    _install(monkeypatch, profile=profile)
    with pytest.raises(HTTPException, match="sem is_matriz/is_conexao_ativa"):
        targets.get_parkinson_menor_50()


def test_demography_rejects_incomplete_grid_invalid_sex_and_negative_population(monkeypatch):
    base = pl.DataFrame({"id_ibge7": [4205407]})

    incomplete = _demography().filter(~((pl.col("idade_min") == 50) & (pl.col("sexo") == "M")))
    monkeypatch.setattr(targets, "get_df_dados_ibge_demografia", lambda: incomplete)
    with pytest.raises(HTTPException, match="Grade demografica IBGE incompleta"):
        targets._get_target_demografia(base, "Parkinson")

    invalid_sex = _demography().with_columns(
        pl.when(pl.col("sexo") == "M").then(pl.lit("X")).otherwise(pl.col("sexo")).alias("sexo")
    )
    monkeypatch.setattr(targets, "get_df_dados_ibge_demografia", lambda: invalid_sex)
    with pytest.raises(HTTPException, match="sexo invalido"):
        targets._get_target_demografia(base, "Parkinson")

    negative = _demography(values={(50, "M"): -1})
    monkeypatch.setattr(targets, "get_df_dados_ibge_demografia", lambda: negative)
    with pytest.raises(HTTPException, match="populacao negativa"):
        targets._get_target_demografia(base, "Parkinson")

    null_age = _demography().with_columns(
        pl.when(pl.col("idade_min") == 50)
        .then(pl.lit(None).cast(pl.Int16))
        .otherwise(pl.col("idade_min"))
        .alias("idade_min")
    )
    monkeypatch.setattr(targets, "get_df_dados_ibge_demografia", lambda: null_age)
    with pytest.raises(HTTPException, match="municipio, idade ou sexo nulo"):
        targets._get_target_demografia(base, "Parkinson")


def test_demography_rejects_missing_target_population_and_zero_expected_population(monkeypatch):
    cnpj_base = pl.DataFrame({"id_ibge7": [4205407]})
    only_younger = _demography(ages=(20, 30))
    monkeypatch.setattr(targets, "get_df_dados_ibge_demografia", lambda: only_younger)
    with pytest.raises(HTTPException, match="ausente para municipios"):
        targets._add_parkinson_municipal_expected(cnpj_base)

    zero_older = _demography(values={(50, "F"): 0, (50, "M"): 0})
    monkeypatch.setattr(targets, "get_df_dados_ibge_demografia", lambda: zero_older)
    with pytest.raises(HTTPException, match="Demografia IBGE invalida"):
        targets._add_parkinson_municipal_expected(cnpj_base)


def test_target_rejects_demography_without_required_columns(monkeypatch):
    monkeypatch.setattr(targets, "get_df_dados_ibge_demografia", lambda: pl.DataFrame({"id_ibge7": [4205407]}))

    with pytest.raises(HTTPException, match="dados_ibge_demografia") as error:
        targets._get_target_demografia(pl.DataFrame({"id_ibge7": [4205407]}), "Parkinson")

    assert error.value.status_code == 500


def test_generic_regional_target_requires_and_aggregates_regional_expected_count(monkeypatch):
    config = targets.ClinicalTargetConfig(
        key="regional_test", label="Regional", patologia="DOENCA DE PARKINSON",
        regra_clinica="IDADE_MENOR_50",
    )
    regional_rows = _clinical().with_columns(pl.lit(1.5).alias("cpfs_incompativeis_esperados_regiao"))
    _install(monkeypatch, clinical=regional_rows)

    response = targets._get_clinical_target(config)

    assert response.items[0].casos_esperados == pytest.approx(1.5)
    assert response.items[1].casos_esperados == pytest.approx(1.5)
    assert response.items[0].populacao_referencia is None
