from datetime import date

import polars as pl
import pytest
from fastapi import HTTPException

from backend.api.schemas.analytics import ClinicoEvolucaoAnualSchema
from backend.api.services.analytics import clinico


CNPJ = "11111111000111"
CITY_ID = "3550308"


def _clinical_row(id_cnpj, pathology, rule, year, **overrides):
    row = {
        "id_cnpj": id_cnpj,
        "id_ibge7": int(CITY_ID),
        "patologia": pathology,
        "regra_clinica": rule,
        "ano_base": year,
        "qtd_cpfs_distintos": 30,
        "qtd_cpfs_incompativeis": 10,
        "qtd_autorizacoes": 50,
        "qtd_autorizacoes_incompativeis": 12,
        "valor_total_pago": 5000.0,
        "valor_incompativel_pago": 1500.0,
        "percentual_cpfs_incompativeis": 33.333,
        "rank_regional_qtd_cpfs_incompativeis": 8,
        "percentil_regional_qtd_cpfs_incompativeis": 0.9,
        "participacao_cpfs_incompativeis_regiao": 0.2,
        "percentual_regional_cpfs_incompativeis": 12.5,
        "razao_percentual_vs_regiao": 2.66,
        "cpfs_incompativeis_esperados_regiao": 4.0,
        "excesso_cpfs_incompativeis_vs_regiao": 6.0,
    }
    row.update(overrides)
    return row


def _install_clinical_sources(monkeypatch):
    key_list = [
        ("DOENCA DE PARKINSON", "IDADE_MENOR_50"),
        ("OSTEOPOROSE", "SEXO_MASCULINO"),
        ("DIABETES", "IDADE_MENOR_20"),
        ("HIPERTENSAO", "IDADE_MENOR_20"),
    ]
    rows = []
    for pathology, rule in key_list:
        rows.extend([
            _clinical_row(1, pathology, rule, 2021, qtd_cpfs_distintos=12, qtd_cpfs_incompativeis=4,
                          valor_total_pago=2400.0, valor_incompativel_pago=1100.0),
            _clinical_row(1, pathology, rule, 2022, qtd_cpfs_distintos=20, qtd_cpfs_incompativeis=8,
                          valor_total_pago=5000.0, valor_incompativel_pago=1600.0),
            _clinical_row(2, pathology, rule, 2022, qtd_cpfs_distintos=40, qtd_cpfs_incompativeis=5,
                          qtd_autorizacoes=80, qtd_autorizacoes_incompativeis=10,
                          valor_total_pago=12000.0, valor_incompativel_pago=3000.0),
        ])
    profile = pl.DataFrame({
        "id_cnpj": [1, 2],
        "cnpj": ["11.111.111/0001-11", "22.222.222/0001-22"],
        "id_ibge7": [int(CITY_ID), int(CITY_ID)],
        "no_municipio": ["São Paulo", "São Paulo"],
        "uf": ["sp", "SP"],
        "razao_social": ["Farmácia Alvo", "Farmácia Comparadora"],
    })
    demographic = pl.DataFrame({
        "id_ibge7": [CITY_ID, CITY_ID, CITY_ID, CITY_ID, "3304557"],
        "ano_censo": [2022, 2022, 2022, 2022, 2022],
        "idade_min": [0, 40, 50, 80, 50],
        "nu_populacao": [100, 50, 200, 50, 999],
    })
    monkeypatch.setattr(clinico, "get_df_perfil_estabelecimento", lambda: profile)
    monkeypatch.setattr(clinico, "scan_analise_gtin_inconsistencia_clinica", lambda: pl.DataFrame(rows).lazy())
    monkeypatch.setattr(clinico, "get_df_dados_ibge_demografia", lambda: demographic)
    return pl.DataFrame(rows), profile, demographic


def test_clinical_normalizers_ratios_sums_and_period_labels():
    assert clinico._clean_cnpj("11.111.111/0001-11") == CNPJ
    assert clinico._normalize_ascii_upper("  Doença_de   PARKINSON ") == "DOENCA DE PARKINSON"
    assert clinico._clinica_meta_key("diabetes", "idade menor 20") == ("DIABETES", "IDADE_MENOR_20")
    assert clinico._clinica_raw_key_value("A", "B") == "A\x1fB"
    assert clinico._ratio(2, 4) == 0.5
    assert clinico._ratio(2, 0) is None
    assert clinico._sum_numeric([{"amount": 2}, {"amount": None}, {}], "amount") == 2.0
    assert clinico._periodo_label(date(2024, 1, 1), date(2024, 12, 31)) == "2024"
    assert clinico._periodo_label(date(2021, 1, 1), date(2022, 12, 31)) == "2021 a 2022"
    assert clinico._periodo_label(None, date(2022, 12, 31)) == "período analisado"


def test_required_column_validators_report_missing_cache_fields():
    with pytest.raises(HTTPException) as eager:
        clinico._require_columns(pl.DataFrame({"present": [1]}), ["present", "required"], "perfil")
    assert eager.value.status_code == 500
    assert "required" in eager.value.detail

    with pytest.raises(HTTPException) as lazy:
        clinico._require_lazy_columns(pl.DataFrame({"present": [1]}).lazy(), ["absent"], "cache")
    assert lazy.value.status_code == 500
    assert "absent" in lazy.value.detail


def test_municipal_context_summarizes_target_rest_and_ranks_by_incompatible_value(monkeypatch):
    rows, profile, _ = _install_clinical_sources(monkeypatch)
    item = {"patologia": "DIABETES", "regra_clinica": "IDADE_MENOR_20"}
    summary, ranking = clinico._build_municipal_context(item, rows, profile, 1, ranking_municipal_limite=2)

    assert [row.grupo for row in summary] == ["Farmácia analisada", "Demais farmácias do município", "Total do município"]
    assert [row.qtd_farmacias for row in summary] == [1, 1, 2]
    assert summary[0].valor_incompativel_pago == 2700.0
    assert summary[2].valor_incompativel_pago == 5700.0
    assert summary[0].participacao_valor_municipal == pytest.approx(2700 / 5700)
    assert [row.id_cnpj for row in ranking] == [2, 1]
    assert ranking[1].is_alvo is True
    assert ranking[0].cnpj == "22222222000122"
    assert ranking[0].participacao_municipal == pytest.approx(3000 / 5700)


def test_municipal_context_handles_zero_limit_and_rejects_invalid_or_incomplete_comparisons(monkeypatch):
    rows, profile, _ = _install_clinical_sources(monkeypatch)
    item = {"patologia": "DIABETES", "regra_clinica": "IDADE_MENOR_20"}

    summary, ranking = clinico._build_municipal_context(item, rows, profile, 1, ranking_municipal_limite=0)
    assert len(summary) == 3 and len(ranking) == 2
    with pytest.raises(HTTPException) as invalid_limit:
        clinico._build_municipal_context(item, rows, profile, 1, ranking_municipal_limite=-1)
    assert invalid_limit.value.status_code == 422

    with pytest.raises(HTTPException, match="sem linhas para recorte"):
        clinico._build_municipal_context({"patologia": "OUTRA", "regra_clinica": "REGRA"}, rows, profile, 1)
    with pytest.raises(HTTPException, match="sem CNPJ alvo"):
        clinico._build_municipal_context(item, rows.filter(pl.col("id_cnpj") == 2), profile, 1)
    with pytest.raises(HTTPException, match="Colunas ausentes: razao_social"):
        clinico._build_municipal_context(item, rows, profile.drop("razao_social"), 1)

    no_target_profile = profile.filter(pl.col("id_cnpj") == 1)
    no_target_profile = no_target_profile.with_columns(pl.when(pl.col("id_cnpj") == 2).then(pl.lit(None, dtype=pl.String)).otherwise(pl.col("cnpj")).alias("cnpj"))
    with pytest.raises(HTTPException, match="Perfil ausente para ranking clínico municipal|Perfil ausente para ranking clinico municipal"):
        clinico._build_municipal_context(item, rows, no_target_profile, 1)


def test_parkinson_demography_aggregates_age_bands_and_selects_most_observed_year(monkeypatch):
    _, _, demographic = _install_clinical_sources(monkeypatch)
    monkeypatch.setattr(clinico, "get_df_dados_ibge_demografia", lambda: demographic)
    evolution = [
        ClinicoEvolucaoAnualSchema(
            ano_base=2021, qtd_cpfs_distintos=12, qtd_cpfs_incompativeis=4,
            qtd_autorizacoes=20, qtd_autorizacoes_incompativeis=8,
            valor_total_pago=2000, valor_incompativel_pago=1000, percentual_cpfs_incompativeis=33.3,
        ),
        ClinicoEvolucaoAnualSchema(
            ano_base=2022, qtd_cpfs_distintos=20, qtd_cpfs_incompativeis=8,
            qtd_autorizacoes=50, qtd_autorizacoes_incompativeis=12,
            valor_total_pago=5000, valor_incompativel_pago=1600, percentual_cpfs_incompativeis=40.0,
        ),
    ]

    result = clinico._build_parkinson_demografia(
        {"id_ibge7": CITY_ID, "no_municipio": " São Paulo ", "uf": "sp"}, evolution
    )

    assert result.ano_observado == 2022
    assert result.cpfs_observados == 20
    assert result.populacao_total == 400
    assert result.populacao_50_mais == 250
    assert result.casos_esperados == pytest.approx(250 * 0.0086)
    assert result.razao_observado_esperado == pytest.approx(20 / (250 * 0.0086))
    assert [(item.faixa, item.populacao, item.destacar_50_mais) for item in result.faixas_etarias] == [
        ("0 a 9", 100, False), ("40 a 49", 50, False), ("50 a 59", 200, True), ("80+", 50, True)
    ]


def test_parkinson_demography_rejects_invalid_evolution_profile_and_population(monkeypatch):
    _, _, demographic = _install_clinical_sources(monkeypatch)
    valid_year = ClinicoEvolucaoAnualSchema(
        ano_base=2022, qtd_cpfs_distintos=1, qtd_cpfs_incompativeis=1,
        qtd_autorizacoes=1, qtd_autorizacoes_incompativeis=1,
        valor_total_pago=1, valor_incompativel_pago=1, percentual_cpfs_incompativeis=100,
    )
    pharmacy = {"id_ibge7": CITY_ID, "no_municipio": "Cidade", "uf": "SP"}
    with pytest.raises(HTTPException, match="Evolucao anual de Parkinson ausente"):
        clinico._build_parkinson_demografia(pharmacy, [])
    invalid_observed = valid_year.model_copy(update={"qtd_cpfs_distintos": 0})
    with pytest.raises(HTTPException, match="CPFs observados.*invalidos"):
        clinico._build_parkinson_demografia(pharmacy, [invalid_observed])
    for incomplete in ({"id_ibge7": CITY_ID, "no_municipio": "Cidade"},
                       {"id_ibge7": "", "no_municipio": "Cidade", "uf": "SP"}):
        with pytest.raises(HTTPException, match="Perfil sem no_municipio/UF/id_ibge7"):
            clinico._build_parkinson_demografia(incomplete, [valid_year])

    monkeypatch.setattr(clinico, "get_df_dados_ibge_demografia", lambda: demographic.drop("idade_min"))
    with pytest.raises(HTTPException, match="dados_ibge_demografia.*idade_min"):
        clinico._build_parkinson_demografia(pharmacy, [valid_year])
    monkeypatch.setattr(
        clinico,
        "get_df_dados_ibge_demografia",
        lambda: demographic.filter(pl.col("id_ibge7") == "3304557"),
    )
    with pytest.raises(HTTPException, match="Demografia IBGE ausente"):
        clinico._build_parkinson_demografia(pharmacy, [valid_year])
    for invalid_demo in (
        pl.DataFrame({"id_ibge7": [CITY_ID], "ano_censo": [2022], "idade_min": [50], "nu_populacao": [0]}),
        pl.DataFrame({"id_ibge7": [CITY_ID], "ano_censo": [2022], "idade_min": [0], "nu_populacao": [100]}),
        pl.DataFrame({"id_ibge7": [CITY_ID, CITY_ID], "ano_censo": [2022, 2022], "idade_min": [-1, 50], "nu_populacao": [1, 10]}),
        pl.DataFrame({"id_ibge7": [CITY_ID, CITY_ID], "ano_censo": [2022, 2022], "idade_min": [0, 50], "nu_populacao": [-1, 10]}),
    ):
        monkeypatch.setattr(clinico, "get_df_dados_ibge_demografia", lambda invalid_demo=invalid_demo: invalid_demo)
        with pytest.raises(HTTPException, match="Demografia IBGE invalida"):
            clinico._build_parkinson_demografia(pharmacy, [valid_year])


def test_clinical_service_aggregates_known_pathologies_and_applies_year_and_ranking_filters(monkeypatch):
    _install_clinical_sources(monkeypatch)
    result = clinico.get_incompatibilidade_patologica_data(
        "11.111.111/0001-11", date(2021, 1, 1), date(2022, 12, 31), ranking_municipal_limite=2
    )

    assert result.cnpj == CNPJ
    assert result.razao_social == "Farmácia Alvo"
    assert result.uf == "SP"
    assert result.periodo_label == "2021 a 2022"
    assert result.summary.qtd_cpfs_distintos == 128
    assert result.summary.qtd_cpfs_incompativeis == 48
    assert result.summary.percentual_valor_incompativel == pytest.approx(10800 / 29600 * 100)
    assert {item.patologia for item in result.patologias} == {
        "DOENCA DE PARKINSON", "OSTEOPOROSE", "DIABETES", "HIPERTENSAO"
    }
    parkinson = next(item for item in result.patologias if item.patologia == "DOENCA DE PARKINSON")
    assert [row.ano_base for row in parkinson.evolucao_anual] == [2021, 2022]
    assert parkinson.evolucao_anual[0].percentual_autorizacoes_incompativeis == pytest.approx(12 / 50)
    assert parkinson.demografia_parkinson.ano_observado == 2022
    assert all(len(item.ranking_municipal) == 2 for item in result.patologias)

    current_year = clinico.get_incompatibilidade_patologica_data(
        CNPJ, date(2022, 1, 1), date(2022, 12, 31), ranking_municipal_limite=0
    )
    assert current_year.periodo_label == "2022"
    assert all(len(item.evolucao_anual) == 1 and len(item.ranking_municipal) == 2 for item in current_year.patologias)


def test_clinical_service_returns_zero_summary_for_empty_cache_and_validates_input_contracts(monkeypatch):
    rows, profile, _ = _install_clinical_sources(monkeypatch)
    with pytest.raises(HTTPException) as invalid_limit:
        clinico.get_incompatibilidade_patologica_data(CNPJ, ranking_municipal_limite=-1)
    assert invalid_limit.value.status_code == 422
    for invalid_cnpj in ("123", "123.456", ""):
        with pytest.raises(HTTPException) as invalid:
            clinico.get_incompatibilidade_patologica_data(invalid_cnpj)
        assert invalid.value.status_code == 422

    monkeypatch.setattr(clinico, "get_df_perfil_estabelecimento", lambda: profile.drop("id_ibge7"))
    with pytest.raises(HTTPException) as profile_contract:
        clinico.get_incompatibilidade_patologica_data(CNPJ)
    assert profile_contract.value.status_code == 500

    monkeypatch.setattr(clinico, "get_df_perfil_estabelecimento", lambda: profile)
    with pytest.raises(HTTPException) as unknown:
        clinico.get_incompatibilidade_patologica_data("33333333000133")
    assert unknown.value.status_code == 404

    no_city = profile.with_columns(pl.when(pl.col("id_cnpj") == 1).then(pl.lit(None, dtype=pl.Int64)).otherwise(pl.col("id_ibge7")).alias("id_ibge7"))
    monkeypatch.setattr(clinico, "get_df_perfil_estabelecimento", lambda: no_city)
    with pytest.raises(HTTPException, match="sem id_ibge7"):
        clinico.get_incompatibilidade_patologica_data(CNPJ)

    monkeypatch.setattr(clinico, "get_df_perfil_estabelecimento", lambda: profile)
    empty = rows.clear()
    monkeypatch.setattr(clinico, "scan_analise_gtin_inconsistencia_clinica", lambda: empty.lazy())
    response = clinico.get_incompatibilidade_patologica_data(CNPJ)
    assert response.summary.qtd_cpfs_distintos == 0
    assert response.summary.percentual_valor_incompativel is None
    assert response.patologias == []


def test_clinical_service_rejects_bad_cache_contracts_unmapped_rules_and_missing_municipality_rows(monkeypatch):
    rows, profile, _ = _install_clinical_sources(monkeypatch)
    monkeypatch.setattr(clinico, "scan_analise_gtin_inconsistencia_clinica", lambda: pl.DataFrame({"id_cnpj": [1]}).lazy())
    with pytest.raises(HTTPException, match="Contrato de cache invalido.*Colunas ausentes"):
        clinico.get_incompatibilidade_patologica_data(CNPJ)

    unknown = rows.filter(pl.col("id_cnpj") == 1).with_columns(
        pl.lit("DOENCA DESCONHECIDA").alias("patologia"), pl.lit("REGRA_DESCONHECIDA").alias("regra_clinica")
    )
    monkeypatch.setattr(clinico, "scan_analise_gtin_inconsistencia_clinica", lambda: unknown.lazy())
    with pytest.raises(HTTPException, match="sem mapeamento textual"):
        clinico.get_incompatibilidade_patologica_data(CNPJ)

    target_only = rows.filter(pl.col("id_cnpj") == 1).with_columns(pl.lit(9999999).alias("id_ibge7"))
    monkeypatch.setattr(clinico, "scan_analise_gtin_inconsistencia_clinica", lambda: target_only.lazy())
    with pytest.raises(HTTPException, match="municipal sem linhas"):
        clinico.get_incompatibilidade_patologica_data(CNPJ)


def test_clinical_service_surfaces_missing_demographic_data_for_parkinson(monkeypatch):
    rows, profile, _ = _install_clinical_sources(monkeypatch)
    monkeypatch.setattr(clinico, "scan_analise_gtin_inconsistencia_clinica", lambda: rows.filter(pl.col("patologia") == "DOENCA DE PARKINSON").lazy())
    monkeypatch.setattr(clinico, "get_df_dados_ibge_demografia", lambda: pl.DataFrame({
        "id_ibge7": [CITY_ID], "ano_censo": [2022], "idade_min": [0], "nu_populacao": [1]
    }))
    with pytest.raises(HTTPException, match="Demografia IBGE invalida"):
        clinico.get_incompatibilidade_patologica_data(CNPJ)
