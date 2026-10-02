from datetime import date

import polars as pl
import pytest

from api.services.analytics import alertas_panorama as panorama
from api.services.analytics.filtros_farmacia import FiltrosFarmacia


def _profile():
    return pl.DataFrame(
        {
            "id_cnpj": [1, 2, 3],
            "cnpj": ["11111111000101", "22222222000102", "33333333000103"],
            "uf": ["SP", "RJ", "SP"],
            "id_regiao_saude": [10, 20, 10],
            "id_ibge7": [100, 200, 100],
        }
    )


def test_geographic_scope_validates_schema_and_applies_most_specific_scope():
    profile = _profile()
    assert panorama._filtrar_id_cnpjs_por_escopo(profile, None, None, None).to_list() == [1, 2, 3]
    assert panorama._filtrar_id_cnpjs_por_escopo(profile, "RJ", 10, 100).to_list() == [1, 3]
    assert panorama._filtrar_id_cnpjs_por_escopo(profile, None, 20, None).to_list() == [2]
    assert panorama._filtrar_id_cnpjs_por_escopo(profile, "SP", None, None).to_list() == [1, 3]
    assert panorama._filtrar_id_cnpjs_por_escopo(profile.clear(), None, None, None) is None

    with pytest.raises(RuntimeError, match="coluna obrigatória.*id_cnpj"):
        panorama._filtrar_id_cnpjs_por_escopo(pl.DataFrame({"uf": ["SP"]}), None, None, None)
    with pytest.raises(RuntimeError, match="colunas obrigatórias para filtro geográfico"):
        panorama._filtrar_id_cnpjs_por_escopo(pl.DataFrame({"id_cnpj": [1], "uf": ["SP"]}), "SP", None, None)


def test_id_intersection_and_distinct_helpers_preserve_empty_and_unique_semantics():
    left = pl.Series("id_cnpj", [1, 1, 2], dtype=pl.Int32)
    right = pl.Series("id_cnpj", [2, 2, 3], dtype=pl.Int64)

    assert set(panorama._intersect_id_cnpjs(None, right).to_list()) == {2, 3}
    assert panorama._intersect_id_cnpjs(left, right).to_list() == [2]
    assert panorama._intersect_id_cnpjs(left, pl.Series([], dtype=pl.Int64)).is_empty()
    assert panorama._intersect_id_cnpjs(pl.Series([], dtype=pl.Int32), right).is_empty()
    assert panorama._distinct_id_cnpjs(pl.DataFrame()).is_empty()
    assert set(panorama._distinct_id_cnpjs(pl.DataFrame({"id_cnpj": [1, 1, 2]})).to_list()) == {1, 2}


def test_cnpj_mapping_handles_empty_input_and_requires_identity_columns(monkeypatch):
    monkeypatch.setattr(panorama, "get_df_perfil_estabelecimento", lambda: pytest.fail("empty IDs need no lookup"))
    assert panorama._ids_por_cnpj(pl.Series([], dtype=pl.String)).is_empty()

    monkeypatch.setattr(panorama, "get_df_perfil_estabelecimento", lambda: pl.DataFrame({"cnpj": ["x"]}))
    with pytest.raises(RuntimeError, match="colunas obrigatorias para mapear CNPJ"):
        panorama._ids_por_cnpj(pl.Series(["x"]))

    profile = _profile()
    monkeypatch.setattr(panorama, "get_df_perfil_estabelecimento", lambda: profile)
    assert panorama._ids_por_cnpj(pl.Series(["22222222000102"])).to_list() == [2]


def test_volume_and_cnae_id_helpers_apply_optional_scope(monkeypatch):
    ids = pl.Series("id_cnpj", [1, 2], dtype=pl.Int64)
    calls = []
    monkeypatch.setattr(
        panorama, "get_volume_atipico_id_cnpjs_df",
        lambda start, end, limit: calls.append((start, end, limit))
        or pl.DataFrame({"id_cnpj": [1, 1, 2]}),
    )
    result = panorama._ids_volume_atipico(ids, date(2020, 1, 1), date(2020, 12, 31))
    assert set(result.to_list()) == {1, 2}
    assert calls == [(date(2020, 1, 1), date(2020, 12, 31), 50.0)]

    profile = _profile().with_columns(pl.Series("is_cnae_incompativel_farmaceutico", [True, False, True]))
    monkeypatch.setattr(panorama, "get_df_perfil_estabelecimento", lambda: profile)
    assert panorama._ids_cnae_incompativel(ids).to_list() == [1]
    assert set(panorama._ids_cnae_incompativel(None).to_list()) == {1, 3}
    assert panorama._ids_cnae_incompativel(pl.Series("id_cnpj", [2], dtype=pl.Int64)).is_empty()

    monkeypatch.setattr(panorama, "get_df_perfil_estabelecimento", lambda: _profile())
    assert panorama._ids_cnae_incompativel(None).is_empty()


def test_non_neighbor_helper_rejects_bad_schema_and_returns_empty_for_no_matching_rows(monkeypatch):
    monkeypatch.setattr(panorama, "scan_geografico_origem_uf", lambda: pl.DataFrame({"id_cnpj": [1]}).lazy())
    with pytest.raises(RuntimeError, match="geografico_origem_uf sem colunas"):
        panorama._ids_dispersao_uf_nao_vizinha(None, None, None, None)

    empty = pl.DataFrame(
        schema={
            "id_cnpj": pl.Int64, "uf_farmacia": pl.String, "uf_paciente": pl.String,
            "valor_autorizado": pl.Float64, "ano_base": pl.Int32,
        }
    )
    monkeypatch.setattr(panorama, "scan_geografico_origem_uf", lambda: empty.lazy())
    assert panorama._ids_dispersao_uf_nao_vizinha(None, "SP", 2020, 2021).is_empty()


def test_deceased_partner_helper_handles_missing_schema_scope_and_profile_contract(monkeypatch):
    monkeypatch.setattr(panorama, "get_df_dados_socios", lambda: pl.DataFrame({"cnpj": ["a"]}))
    assert panorama._ids_socio_falecido(None).is_empty()

    socios = pl.DataFrame(
        {
            "cnpj": ["a", "b", "c"], "indicador_socio": ["PF", "PF", "PJ"],
            "is_falecido": [True, True, True], "data_exclusao_sociedade": [None, date(2020, 1, 1), None],
        },
        schema_overrides={"data_exclusao_sociedade": pl.Date},
    )
    monkeypatch.setattr(panorama, "get_df_dados_socios", lambda: socios)
    monkeypatch.setattr(
        panorama, "get_df_perfil_estabelecimento",
        lambda: pl.DataFrame({"id_cnpj": [1, 2], "cnpj": ["a", "b"]}),
    )
    assert panorama._ids_socio_falecido(None).to_list() == [1]
    assert panorama._ids_socio_falecido(pl.Series("id_cnpj", [2], dtype=pl.Int64)).is_empty()

    monkeypatch.setattr(panorama, "get_df_perfil_estabelecimento", lambda: pl.DataFrame({"id_cnpj": [1]}))
    with pytest.raises(RuntimeError, match="sem coluna 'cnpj'"):
        panorama._ids_socio_falecido(pl.Series("id_cnpj", [1], dtype=pl.Int64))


@pytest.mark.parametrize(
    ("profile", "expected"),
    [
        (pl.DataFrame({"id_cnpj": [1]}), []),
        (pl.DataFrame({"id_cnpj": [1], "has_cadunico_direto": [True]}), [1]),
        (pl.DataFrame({"id_cnpj": [1], "has_seguro_defeso_direto": [True]}), [1]),
        (pl.DataFrame({"id_cnpj": [1], "has_cadunico_direto": [False], "has_seguro_defeso_direto": [True]}), [1]),
    ],
)
def test_social_benefit_helper_supports_available_profile_columns(monkeypatch, profile, expected):
    monkeypatch.setattr(panorama, "get_df_perfil_estabelecimento", lambda: profile)

    result = panorama._ids_socio_beneficio_social(pl.Series("id_cnpj", [1], dtype=pl.Int64))

    assert result.to_list() == expected


def test_esocial_helper_handles_missing_column_and_optional_scope(monkeypatch):
    monkeypatch.setattr(panorama, "get_df_perfil_estabelecimento", lambda: pl.DataFrame({"id_cnpj": [1]}))
    assert panorama._ids_socio_esocial(None).is_empty()

    profile = pl.DataFrame({"id_cnpj": [1, 2], "has_esocial_direto": [True, False]})
    monkeypatch.setattr(panorama, "get_df_perfil_estabelecimento", lambda: profile)
    assert panorama._ids_socio_esocial(None).to_list() == [1]
    assert panorama._ids_socio_esocial(pl.Series("id_cnpj", [2], dtype=pl.Int64)).is_empty()


def test_par_teia_helper_requires_schema_maps_and_intersects_ids(monkeypatch):
    monkeypatch.setattr(panorama, "get_df_par_teia_alvos", lambda: pl.DataFrame({"cnpj": ["a"]}))
    with pytest.raises(RuntimeError, match="colunas obrigatorias para alerta PAR N2"):
        panorama._ids_par_teia_n2(None)

    monkeypatch.setattr(
        panorama, "get_df_par_teia_alvos",
        lambda: pl.DataFrame({"cnpj": ["a", "b"], "has_par_n2": [True, False]}),
    )
    monkeypatch.setattr(
        panorama, "get_df_perfil_estabelecimento",
        lambda: pl.DataFrame({"cnpj": ["a", "b"], "id_cnpj": [1, 2]}),
    )
    assert panorama._ids_par_teia_n2(None).to_list() == [1]
    assert panorama._ids_par_teia_n2(pl.Series("id_cnpj", [2], dtype=pl.Int64)).is_empty()


def test_atypical_age_helper_handles_incomplete_empty_and_scoped_data(monkeypatch):
    monkeypatch.setattr(panorama, "get_df_dados_socios", lambda: pl.DataFrame({"cnpj": ["a"]}))
    assert panorama._ids_socio_idade_atipica(None, date(2024, 1, 1)).is_empty()

    socios = pl.DataFrame(
        {
            "cnpj": ["a", "b", "c"], "indicador_socio": ["PF", "PF", "PJ"],
            "data_exclusao_sociedade": [None, None, None],
            "data_nascimento_socio": [date(2005, 1, 1), date(1980, 1, 1), date(1900, 1, 1)],
        },
        schema_overrides={"data_exclusao_sociedade": pl.Date, "data_nascimento_socio": pl.Date},
    )
    monkeypatch.setattr(panorama, "get_df_dados_socios", lambda: socios)
    monkeypatch.setattr(
        panorama, "get_df_perfil_estabelecimento",
        lambda: pl.DataFrame({"id_cnpj": [1, 2, 3], "cnpj": ["a", "b", "c"]}),
    )
    assert panorama._ids_socio_idade_atipica(None, date(2024, 1, 1)).to_list() == [1]

    ordinary = socios.with_columns(pl.lit(date(1990, 1, 1)).alias("data_nascimento_socio"))
    monkeypatch.setattr(panorama, "get_df_dados_socios", lambda: ordinary)
    assert panorama._ids_socio_idade_atipica(None, date(2024, 1, 1)).is_empty()

    without_eligible_people = ordinary.with_columns(pl.lit("PJ").alias("indicador_socio"))
    monkeypatch.setattr(panorama, "get_df_dados_socios", lambda: without_eligible_people)
    assert panorama._ids_socio_idade_atipica(None, date(2024, 1, 1)).is_empty()

    monkeypatch.setattr(
        panorama, "get_df_perfil_estabelecimento",
        lambda: pl.DataFrame({"id_cnpj": [1], "cnpj": ["a"]}),
    )
    monkeypatch.setattr(panorama, "get_df_dados_socios", lambda: socios)
    assert panorama._ids_socio_idade_atipica(pl.Series("id_cnpj", [1], dtype=pl.Int64), date(2024, 1, 1)).to_list() == [1]
    monkeypatch.setattr(panorama, "get_df_perfil_estabelecimento", lambda: pl.DataFrame({"id_cnpj": [1]}))
    with pytest.raises(RuntimeError, match="sem coluna 'cnpj'"):
        panorama._ids_socio_idade_atipica(pl.Series("id_cnpj", [1], dtype=pl.Int64), date(2024, 1, 1))


def test_public_panorama_applies_dispersal_scope_and_deduplicates_total_alerted_cnpjs(monkeypatch):
    profile = _profile()
    monkeypatch.setattr(panorama, "get_df_perfil_estabelecimento", lambda: profile)
    monkeypatch.setattr(panorama, "build_perfil_filtrado", lambda frame, **_kwargs: frame)
    calls = []
    monkeypatch.setattr(
        panorama, "get_dispersao_uf_sem_fronteira_id_cnpjs_df",
        lambda start, end, limit: (
            calls.append((start, end, limit)), pl.DataFrame({"id_cnpj": [1, 2]})
        )[1],
    )

    def scoped_ids(ids, _start, _end):
        return pl.Series("id_cnpj", [1] if ids is not None and 1 in ids.to_list() else [], dtype=pl.Int64)

    monkeypatch.setattr(panorama, "_ids_volume_atipico", scoped_ids)
    monkeypatch.setattr(panorama, "_ids_cnae_incompativel", lambda ids: pl.Series("id_cnpj", [1, 2], dtype=pl.Int64))
    monkeypatch.setattr(panorama, "_ids_dispersao_uf_nao_vizinha", lambda ids, *_args: pl.Series("id_cnpj", [2], dtype=pl.Int64))
    monkeypatch.setattr(panorama, "_ids_socio_falecido", lambda ids: pl.Series("id_cnpj", [2], dtype=pl.Int64))
    monkeypatch.setattr(panorama, "_ids_socio_beneficio_social", lambda ids: pl.Series("id_cnpj", [1], dtype=pl.Int64))
    monkeypatch.setattr(panorama, "_ids_socio_idade_atipica", lambda ids, _ref: pl.Series("id_cnpj", [1], dtype=pl.Int64))
    monkeypatch.setattr(panorama, "_ids_socio_esocial", lambda ids: pl.Series("id_cnpj", [], dtype=pl.Int64))
    monkeypatch.setattr(panorama, "_ids_par_teia_n2", lambda ids: pl.Series("id_cnpj", [2], dtype=pl.Int64))

    response = panorama.get_alertas_panorama(
        uf="SP", data_inicio=date(2020, 1, 1), data_fim=date(2020, 12, 31),
        filtros=FiltrosFarmacia(dispersao_uf_sem_fronteira=True, dispersao_uf_sem_fronteira_limite=0.15),
    )

    assert response.total_cnpjs_com_alerta == 2
    assert response.total_criticos == 2
    assert response.total_atencao == 6
    assert calls == [(date(2020, 1, 1), date(2020, 12, 31), 0.15)]
