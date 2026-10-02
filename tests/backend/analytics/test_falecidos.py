from datetime import date

import polars as pl
import pytest
from fastapi import HTTPException

from api.services.analytics import falecidos


CNPJ_A = "12345678000190"
CNPJ_B = "98765432000110"


def _source_frames():
    falecidos_df = pl.DataFrame(
        {
            "cnpj": [CNPJ_A, CNPJ_A, CNPJ_B], "cpf": ["123", "456", "123"],
            "nome_falecido": ["Pessoa A", "Pessoa B", "Pessoa A"],
            "municipio_falecido": ["Brasilia"] * 3, "uf_falecido": ["DF"] * 3,
            "dt_nascimento": [date(1940, 1, 1)] * 3, "dt_obito": [date(2020, 1, 1)] * 3,
            "fonte_obito": ["base"] * 3, "num_autorizacao": ["a1", "a2", "a3"],
            "data_autorizacao": [date(2020, 1, 2), date(2020, 2, 2), date(2020, 1, 3)],
            "qtd_itens_na_autorizacao": [1, 2, 1], "valor_total_autorizacao": [10.0, 30.0, 15.0],
            "dias_apos_obito": [1, 32, 2],
        }
    )
    perfil = pl.DataFrame(
        {
            "cnpj": [CNPJ_A, CNPJ_B], "id_cnpj": [1, 2],
            "razao_social": ["Farmacia A", "Farmacia B"],
            "no_municipio": ["Brasilia", "Goiania"], "uf": ["DF", "GO"],
        }
    )
    movimento = pl.DataFrame(
        {"id_cnpj": [1, 2], "periodo": [date(2020, 1, 1), date(2020, 1, 1)], "total_vendas": [1000.0, 2000.0]}
    )
    return falecidos_df, perfil, movimento


def test_get_falecidos_returns_summary_other_pharmacy_and_sorted_timeline(monkeypatch):
    deaths, profile, movement = _source_frames()
    monkeypatch.setattr(falecidos, "get_df_falecidos", lambda: deaths)
    monkeypatch.setattr(falecidos, "get_df_perfil_estabelecimento", lambda: profile)
    monkeypatch.setattr(falecidos, "get_df", lambda: movement)

    response = falecidos.get_falecidos_data(CNPJ_A)
    assert response.tem_historico is True
    assert response.summary.total_autorizacoes == 2
    assert response.summary.valor_total == 40.0
    assert response.summary.pct_faturamento == 0.04
    assert response.transacoes[0].outros_estabelecimentos == f"{CNPJ_B} | Goiania/GO"
    timeline = falecidos.get_timeline_cpf(CNPJ_A, "123")
    assert timeline.cnpjs_envolvidos == [CNPJ_A, CNPJ_B]
    assert [event.is_this_cnpj for event in timeline.events] == [True, False]


def test_falecidos_fails_visibly_for_missing_required_columns(monkeypatch):
    monkeypatch.setattr(falecidos, "get_df_falecidos", lambda: pl.DataFrame({"cnpj": [CNPJ_A]}))
    with pytest.raises(HTTPException) as error:
        falecidos.carregar_falecidos(CNPJ_A)
    assert error.value.status_code == 503
    assert "colunas obrigatorias" in error.value.detail


def test_falecidos_cache_runtime_error_is_reported_as_service_unavailable(monkeypatch):
    def cache_indisponivel():
        raise RuntimeError("cache ainda nao carregado")

    monkeypatch.setattr(falecidos, "get_df_falecidos", cache_indisponivel)
    with pytest.raises(HTTPException) as error:
        falecidos._base_falecidos()

    assert error.value.status_code == 503
    assert "cache ainda nao carregado" in error.value.detail


def test_authorization_with_required_null_value_fails_visibly(monkeypatch):
    deaths, _, _ = _source_frames()
    deaths = deaths.with_columns(pl.when(pl.col("cnpj") == CNPJ_A).then(None).otherwise(pl.col("cpf")).alias("cpf"))
    monkeypatch.setattr(falecidos, "get_df_falecidos", lambda: deaths)

    with pytest.raises(HTTPException, match="sem cpf") as error:
        falecidos.carregar_falecidos(CNPJ_A)

    assert error.value.status_code == 503


@pytest.mark.parametrize(
    ("transform", "message"),
    [
        (lambda profile: pl.concat([profile, profile.filter(pl.col("cnpj") == CNPJ_A)]), "mais de uma linha"),
        (lambda profile: profile.filter(pl.col("cnpj") != CNPJ_A), "sem cadastro no perfil"),
        (lambda profile: profile.with_columns(pl.when(pl.col("cnpj") == CNPJ_A).then(pl.lit("")).otherwise(pl.col("razao_social")).alias("razao_social")), "sem razao social"),
    ],
)
def test_invalid_pharmacy_profile_is_rejected(monkeypatch, transform, message):
    _, profile, _ = _source_frames()
    monkeypatch.setattr(falecidos, "get_df_perfil_estabelecimento", lambda: transform(profile))

    with pytest.raises(HTTPException, match=message) as error:
        falecidos._cadastro([CNPJ_A])

    assert error.value.status_code == 503


def test_nonmatching_pharmacy_returns_empty_response_and_preserves_historical_flag(monkeypatch):
    deaths, _, _ = _source_frames()
    monkeypatch.setattr(falecidos, "get_df_falecidos", lambda: deaths)

    response = falecidos.get_falecidos_data("11111111000111")

    assert response.tem_historico is False
    assert response.summary.total_autorizacoes == 0
    assert response.transacoes == []
    assert response.ranking == []


def test_date_range_limits_authorizations_and_revenue_period(monkeypatch):
    deaths, profile, movement = _source_frames()
    movement = pl.DataFrame(
        {"id_cnpj": [1, 1, 2], "periodo": [date(2020, 1, 1), date(2020, 2, 1), date(2020, 1, 1)],
         "total_vendas": [1000.0, 500.0, 2000.0]}
    )
    monkeypatch.setattr(falecidos, "get_df_falecidos", lambda: deaths)
    monkeypatch.setattr(falecidos, "get_df_perfil_estabelecimento", lambda: profile)
    monkeypatch.setattr(falecidos, "get_df", lambda: movement)

    data = falecidos.carregar_falecidos(CNPJ_A, date(2020, 2, 1), date(2020, 2, 28))

    assert data.tem_historico is True
    assert data.summary.total_autorizacoes == 1
    assert data.transacoes.get_column("num_autorizacao").to_list() == ["a2"]
    assert data.faturamento_periodo == 500.0
    assert data.ranking.is_empty()


def test_matching_deceased_authorizations_without_positive_revenue_raise_503(monkeypatch):
    deaths, profile, movement = _source_frames()
    movement = movement.with_columns(pl.lit(0.0).alias("total_vendas"))
    monkeypatch.setattr(falecidos, "get_df_falecidos", lambda: deaths)
    monkeypatch.setattr(falecidos, "get_df_perfil_estabelecimento", lambda: profile)
    monkeypatch.setattr(falecidos, "get_df", lambda: movement)

    with pytest.raises(HTTPException, match="sem faturamento") as error:
        falecidos.carregar_falecidos(CNPJ_A)

    assert error.value.status_code == 503


@pytest.mark.parametrize("cnpj", ["", "123", "12.345.678/0001-90-1"])
def test_invalid_cnpj_is_rejected_before_reading_cache(monkeypatch, cnpj):
    monkeypatch.setattr(falecidos, "get_df_falecidos", lambda: pytest.fail("cache should not be read"))

    with pytest.raises(HTTPException) as error:
        falecidos.carregar_falecidos(cnpj)

    assert error.value.status_code == 422


def test_timeline_invalid_or_unknown_cpf_returns_validation_or_empty_result(monkeypatch):
    deaths, _, _ = _source_frames()
    monkeypatch.setattr(falecidos, "get_df_falecidos", lambda: deaths)

    with pytest.raises(HTTPException) as error:
        falecidos.get_timeline_cpf(CNPJ_A, "123456789012")
    assert error.value.status_code == 422

    timeline = falecidos.get_timeline_cpf(CNPJ_A, "999")
    assert timeline.events == []
    assert timeline.cnpjs_envolvidos == []


def test_timeline_authorizations_with_null_required_fields_fail(monkeypatch):
    deaths, _, _ = _source_frames()
    deaths = deaths.with_columns(
        pl.when(pl.col("cpf") == "123").then(pl.lit(None, dtype=pl.Utf8)).otherwise(pl.col("num_autorizacao")).alias("num_autorizacao")
    )
    monkeypatch.setattr(falecidos, "get_df_falecidos", lambda: deaths)

    with pytest.raises(HTTPException, match="sem num_autorizacao") as error:
        falecidos.get_timeline_cpf(CNPJ_A, "123")

    assert error.value.status_code == 503
