from datetime import date

import polars as pl
import pytest
from fastapi import HTTPException

from api.services.analytics import alertas_alvos, alertas_panorama
from api.services.analytics import volume_atipico
from api.services.analytics.filtros_farmacia import FiltrosFarmacia


def test_alerta_profile_filters_apply_scopes_and_fail_on_bad_population_range(monkeypatch):
    profile = pl.DataFrame(
        {
            "id_cnpj": [1, 2, 3], "id_ibge7": [100, 200, 300],
            "has_cadunico_direto": [True, False, False], "has_cadunico_n3": [False, True, False],
            "has_seguro_defeso_direto": [False, False, True], "has_seguro_defeso_n3": [False, False, False],
            "has_esocial_direto": [False, True, False], "has_esocial_n3": [False, False, True],
        }
    )
    assert alertas_alvos.apply_socio_beneficio_filter(profile, "direto")["id_cnpj"].to_list() == [1, 3]
    assert alertas_alvos.apply_socio_beneficio_filter(profile, "n3")["id_cnpj"].to_list() == [2]
    assert alertas_alvos.apply_socio_esocial_filter(profile, "direto_n3")["id_cnpj"].to_list() == [2, 3]

    monkeypatch.setattr(
        alertas_alvos,
        "get_localidades_df",
        lambda: pl.DataFrame({"id_ibge7": [100, 200, 300], "nu_populacao": [500, 1500, 2500]}),
    )
    filtered = alertas_alvos.apply_populacao_municipio_filter(profile, 1000, 2000)
    assert filtered["id_cnpj"].to_list() == [2]

    import pytest
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as error:
        alertas_alvos.apply_populacao_municipio_filter(profile, 10, 2)
    assert error.value.status_code == 422


def test_sequence_alert_filter_counts_unique_alert_days(monkeypatch):
    profile = pl.DataFrame({"id_cnpj": [1, 2, 3], "cnpj": ["a", "b", "c"]})
    source = pl.DataFrame(
        {
            "id_cnpj": [1, 1, 2, 2, 2, 2],
            "competencia": [209001, 209001, 209001, 209001, 209002, 209002],
            "dt_alerta": ["2090-01-01", "2090-01-02", "2090-01-01", "2090-01-02", "2090-02-01", "2090-02-02"],
            "id_severidade": [2, 2, 2, 2, 2, 2],
        }
    )
    monkeypatch.setattr(
        alertas_alvos,
        "TIPOS_SEQUENCIA",
        {"unico": (lambda: source.lazy(),), "multiplo": (lambda: source.lazy(),), "qualquer": (lambda: source.lazy(), lambda: source.lazy())},
    )
    result = alertas_alvos.apply_seq_filter(
        profile, "unico", 2, 2, 3, date(2090, 1, 1), date(2090, 2, 1)
    )
    assert result["id_cnpj"].to_list() == [1]


def test_alertas_panorama_aggregates_unique_cnpjs_and_counts_by_severity(monkeypatch):
    cnpjs = [f"{i:014d}" for i in range(1, 6)]
    profile = pl.DataFrame(
        {
            "id_cnpj": [1, 2, 3, 4, 5], "cnpj": cnpjs, "uf": ["SP"] * 5,
            "id_regiao_saude": [10] * 5, "id_ibge7": [100] * 5,
            "is_cnae_incompativel_farmaceutico": [False, True, False, False, False],
            "has_cadunico_direto": [False, False, False, True, False],
            "has_seguro_defeso_direto": [False] * 5,
            "has_esocial_direto": [False, False, False, True, False],
        }
    )
    socios = pl.DataFrame(
        {
            "cnpj": cnpjs, "indicador_socio": ["PF"] * 5,
            "data_exclusao_sociedade": [None] * 5,
            "is_falecido": [True, False, False, False, False],
            "data_nascimento_socio": [date(1980, 1, 1), date(1980, 1, 1), date(2005, 1, 1), date(1980, 1, 1), date(1980, 1, 1)],
        },
        schema_overrides={"data_exclusao_sociedade": pl.Date, "data_nascimento_socio": pl.Date},
    )
    volume_rows = pl.DataFrame(
        {
            "id_cnpj": [1], "chave_semestre": [202001], "status_semestre": [1],
            "aumento_valor_semestre": [20000.0], "taxa_crescimento_pct": [100.0],
        }
    )
    geografia = pl.DataFrame(
        {
            "id_cnpj": [3, 3], "uf_farmacia": ["SP", "SP"], "uf_paciente": ["MG", "AM"],
            "valor_autorizado": [1000.0, 200.0], "ano_base": [2020, 2020],
        }
    )
    par_teia = pl.DataFrame({"cnpj": cnpjs, "has_par_n2": [False, False, False, False, True]})
    monkeypatch.setattr(alertas_panorama, "get_df_perfil_estabelecimento", lambda: profile)
    monkeypatch.setattr(alertas_panorama, "get_df_dados_socios", lambda: socios)
    monkeypatch.setattr(alertas_panorama, "get_df_par_teia_alvos", lambda: par_teia)
    monkeypatch.setattr(alertas_panorama, "scan_geografico_origem_uf", lambda: geografia.lazy())
    monkeypatch.setattr(volume_atipico, "get_df_volume_atipico_semestral", lambda: volume_rows)
    monkeypatch.setattr(volume_atipico, "get_volume_atipico_aumento_minimo", lambda: 10000.0)
    monkeypatch.setattr(
        volume_atipico,
        "get_df_dados_farmacia",
        lambda: pl.DataFrame({"id_cnpj": [1], "cnpj": [cnpjs[0]]}),
    )

    result = alertas_panorama.get_alertas_panorama(
        uf="SP", data_inicio=date(2020, 1, 1), data_fim=date(2020, 12, 31), filtros=FiltrosFarmacia()
    )
    assert result.total_cnpjs_com_alerta == 5
    assert result.total_criticos == 2
    assert result.total_atencao == 6
    assert len(result.alertas) == 8


def test_panorama_scope_and_intersection_preserve_only_matching_ids():
    profile = pl.DataFrame(
        {"id_cnpj": [1, 2, 3], "uf": ["SP", "RJ", "SP"], "id_regiao_saude": [10, 20, 10], "id_ibge7": [100, 200, 100]}
    )
    ids = alertas_panorama._filtrar_id_cnpjs_por_escopo(profile, "SP", None, None)
    assert set(ids.to_list()) == {1, 3}
    assert set(alertas_panorama._intersect_id_cnpjs(ids, pl.Series([3, 4], dtype=pl.Int64)).to_list()) == {3}
    assert alertas_panorama._filtrar_id_cnpjs_por_escopo(profile.clear(), None, None, None) is None


def test_socio_age_and_deceased_filters_include_only_active_person_partners(monkeypatch):
    profile = pl.DataFrame({"cnpj": ["a", "b", "c"], "id_cnpj": [1, 2, 3]})
    socios = pl.DataFrame(
        {
            "cnpj": ["a", "b", "c"], "indicador_socio": ["PF", "PF", "PJ"],
            "data_exclusao_sociedade": [None, None, None], "is_falecido": [True, False, True],
            "data_nascimento_socio": [date(2005, 1, 1), date(1980, 1, 1), date(1930, 1, 1)],
        },
        schema_overrides={"data_exclusao_sociedade": pl.Date, "data_nascimento_socio": pl.Date},
    )
    monkeypatch.setattr(alertas_alvos, "get_df_dados_socios", lambda: socios)
    assert alertas_alvos.apply_socio_falecido_filter(profile, True)["cnpj"].to_list() == ["a"]
    assert alertas_alvos.apply_socio_idade_atipica_filter(
        profile, True, data_referencia=date(2020, 1, 1)
    )["cnpj"].to_list() == ["a"]


def test_panorama_non_neighbor_alert_uses_patient_uf_not_neighbor(monkeypatch):
    source = pl.DataFrame(
        {
            "id_cnpj": [1, 1], "uf_farmacia": ["SP", "SP"], "uf_paciente": ["MG", "AM"],
            "valor_autorizado": [1000.0, 200.0], "ano_base": [2020, 2020],
        }
    )
    monkeypatch.setattr(alertas_panorama, "scan_geografico_origem_uf", lambda: source.lazy())
    ids = alertas_panorama._ids_dispersao_uf_nao_vizinha(None, "SP", 2020, 2020)
    assert ids.to_list() == [1]


def test_partner_benefit_and_esocial_scopes_cover_unions_and_reject_unknown_values():
    profile = pl.DataFrame(
        {
            "id_cnpj": [1, 2, 3],
            "has_cadunico_direto": [True, False, False],
            "has_cadunico_n3": [False, True, False],
            "has_seguro_defeso_direto": [False, False, True],
            "has_seguro_defeso_n3": [False, False, False],
            "has_esocial_direto": [True, False, False],
            "has_esocial_n3": [False, True, False],
        }
    )
    assert alertas_alvos.apply_socio_beneficio_filter(profile, " DIRETO_N3 ")["id_cnpj"].to_list() == [1, 2, 3]
    assert alertas_alvos.apply_socio_esocial_filter(profile, "direto")["id_cnpj"].to_list() == [1]
    assert alertas_alvos.apply_socio_esocial_filter(profile, "n3")["id_cnpj"].to_list() == [2]

    with pytest.raises(HTTPException) as benefit_error:
        alertas_alvos.apply_socio_beneficio_filter(profile, "rede")
    assert benefit_error.value.status_code == 400
    with pytest.raises(HTTPException) as esocial_error:
        alertas_alvos.apply_socio_esocial_filter(profile, "rede")
    assert esocial_error.value.status_code == 400


def test_cnae_and_age_filters_validate_required_source_contracts(monkeypatch):
    profile = pl.DataFrame({"cnpj": ["a", "b"], "is_cnae_incompativel_farmaceutico": [1, 0]})
    assert alertas_alvos.apply_cnae_incompativel_filter(profile, True)["cnpj"].to_list() == ["a"]
    with pytest.raises(HTTPException) as cnae_error:
        alertas_alvos.apply_cnae_incompativel_filter(pl.DataFrame({"cnpj": ["a"]}), True)
    assert cnae_error.value.status_code == 500

    with pytest.raises(HTTPException, match="exige coluna 'cnpj'"):
        alertas_alvos.apply_socio_idade_atipica_filter(pl.DataFrame({"id_cnpj": [1]}), True)
    monkeypatch.setattr(alertas_alvos, "get_df_dados_socios", lambda: pl.DataFrame({"cnpj": ["a"]}))
    with pytest.raises(HTTPException, match="exige colunas em dados_socios"):
        alertas_alvos.apply_socio_idade_atipica_filter(profile, True, date(2024, 1, 1))


@pytest.mark.parametrize(
    ("profile", "expected_detail"),
    [
        (pl.DataFrame({"id_ibge7": [1]}), "Localidades sem colunas"),
        (pl.DataFrame({"id_ibge7": [1], "nu_populacao": [None]}), "nu_populacao nulo"),
    ],
)
def test_population_filter_rejects_incomplete_or_null_locality_data(monkeypatch, profile, expected_detail):
    monkeypatch.setattr(alertas_alvos, "get_localidades_df", lambda: profile)
    pharmacies = pl.DataFrame({"id_ibge7": [1]})

    with pytest.raises(HTTPException, match=expected_detail) as error:
        alertas_alvos.apply_populacao_municipio_filter(pharmacies, 1, None)

    assert error.value.status_code == 503


def test_population_filter_requires_locality_for_every_pharmacy_municipality(monkeypatch):
    monkeypatch.setattr(
        alertas_alvos, "get_localidades_df",
        lambda: pl.DataFrame({"id_ibge7": [100], "nu_populacao": [1000]}),
    )

    with pytest.raises(HTTPException, match="ausentes do cadastro de localidades") as error:
        alertas_alvos.apply_populacao_municipio_filter(pl.DataFrame({"id_ibge7": [200]}), 1, None)

    assert error.value.status_code == 503
    with pytest.raises(HTTPException, match="exige coluna 'id_ibge7'"):
        alertas_alvos.apply_populacao_municipio_filter(pl.DataFrame({"cnpj": ["a"]}), 1, None)


def test_population_filter_rejects_negative_lower_or_upper_bound():
    for bounds in ((-1, None), (None, -1)):
        with pytest.raises(HTTPException, match="nao pode ser negativa") as error:
            alertas_alvos.apply_populacao_municipio_filter(pl.DataFrame({"id_ibge7": [1]}), *bounds)
        assert error.value.status_code == 422


def test_sequence_alert_aggregation_translates_source_failures_and_invalid_rows(monkeypatch):
    from fastapi import HTTPException

    monkeypatch.setattr(
        alertas_alvos, "TIPOS_SEQUENCIA",
        {"unico": (lambda: (_ for _ in ()).throw(OSError("source offline")),)},
    )
    with pytest.raises(HTTPException, match="indisponiveis") as unavailable:
        alertas_alvos._calcular_dias_seq("unico", 1, None, None)
    assert unavailable.value.status_code == 503

    unknown = pl.DataFrame(
        {"id_cnpj": [1], "competencia": [202401], "dt_alerta": ["2024-01-01"], "id_severidade": [5]}
    )
    monkeypatch.setattr(alertas_alvos, "TIPOS_SEQUENCIA", {"unico": (lambda: unknown.lazy(),)})
    with pytest.raises(HTTPException, match="Severidade desconhecida"):
        alertas_alvos._calcular_dias_seq("unico", 1, 202401, 202401)

    missing_date = unknown.with_columns(
        pl.lit(None, dtype=pl.String).alias("dt_alerta"), pl.lit(2).alias("id_severidade")
    )
    monkeypatch.setattr(alertas_alvos, "TIPOS_SEQUENCIA", {"unico": (lambda: missing_date.lazy(),)})
    with pytest.raises(HTTPException, match="sem dt_alerta"):
        alertas_alvos._calcular_dias_seq("unico", 1, None, None)


def test_sequence_filter_validates_parameters_and_defaults_severity_only_to_one_day(monkeypatch):
    profile = pl.DataFrame({"id_cnpj": [1, 2]})
    noop = alertas_alvos.apply_seq_filter(profile, None, None, None, None, None, None)
    assert noop.equals(profile)

    invalid_cases = [
        ((profile, None, None, 1, None, None, None), "seq_tipo"),
        ((profile, "unico", 5, 1, None, None, None), "seq_severidade_min"),
        ((profile, "unico", None, -1, None, None, None), "nao pode ser negativa"),
        ((profile, "unico", None, 3, 2, None, None), "minimo maior que maximo"),
        ((pl.DataFrame({"cnpj": ["a"]}), "unico", None, 1, None, None, None), "exige coluna 'id_cnpj'"),
    ]
    for args, message in invalid_cases:
        with pytest.raises(HTTPException, match=message):
            alertas_alvos.apply_seq_filter(*args)

    days = pl.DataFrame(
        {"id_cnpj": [1], "competencia": [202401], "dt_alerta": ["2024-01-01"], "id_severidade": [2]}
    )
    monkeypatch.setattr(alertas_alvos, "TIPOS_SEQUENCIA", {"unico": (lambda: days.lazy(),)})
    result = alertas_alvos.apply_seq_filter(
        pl.DataFrame({"id_cnpj": [1]}), "unico", 2, None, None, date(2024, 1, 1), None
    )
    assert result["id_cnpj"].to_list() == [1]
    assert "_dias_seq" not in result.columns


def test_deceased_and_esocial_filters_validate_contracts_and_filter_active_matches(monkeypatch):
    profile = pl.DataFrame({"cnpj": ["a", "b"]})
    with pytest.raises(HTTPException, match="exige coluna 'cnpj'"):
        alertas_alvos.apply_socio_falecido_filter(pl.DataFrame({"id_cnpj": [1]}), True)

    monkeypatch.setattr(alertas_alvos, "get_df_dados_socios", lambda: pl.DataFrame({"cnpj": ["a"]}))
    with pytest.raises(HTTPException, match="exige colunas em dados_socios"):
        alertas_alvos.apply_socio_falecido_filter(profile, True)

    socios = pl.DataFrame(
        {
            "cnpj": ["a", "a", "b"], "indicador_socio": ["PF", "PF", "PJ"],
            "data_exclusao_sociedade": [None, date(2020, 1, 1), None],
            "is_falecido": [True, True, True],
        },
        schema_overrides={"data_exclusao_sociedade": pl.Date},
    )
    monkeypatch.setattr(alertas_alvos, "get_df_dados_socios", lambda: socios)
    assert alertas_alvos.apply_socio_falecido_filter(profile, True)["cnpj"].to_list() == ["a"]

    with pytest.raises(HTTPException, match="exige colunas no perfil"):
        alertas_alvos.apply_socio_esocial_filter(pl.DataFrame({"id_cnpj": [1]}), "direto")


def test_volume_atypical_filter_is_noop_validates_and_joins_ids(monkeypatch):
    profile = pl.DataFrame({"id_cnpj": [1, 2]})
    assert alertas_alvos.apply_volume_atipico_filter(profile, False).equals(profile)
    with pytest.raises(HTTPException, match="exige coluna 'id_cnpj'"):
        alertas_alvos.apply_volume_atipico_filter(pl.DataFrame({"cnpj": ["a"]}), True)

    calls = []
    monkeypatch.setattr(
        alertas_alvos, "get_volume_atipico_id_cnpjs_df",
        lambda start, end, limit: (
            calls.append((start, end, limit)), pl.DataFrame({"id_cnpj": [2]})
        )[1],
    )
    result = alertas_alvos.apply_volume_atipico_filter(
        profile, True, date(2020, 1, 1), date(2020, 12, 31), 0.75
    )
    assert result["id_cnpj"].to_list() == [2]
    assert calls == [(date(2020, 1, 1), date(2020, 12, 31), 0.75)]
