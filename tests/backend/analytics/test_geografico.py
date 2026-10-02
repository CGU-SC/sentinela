from datetime import date

import polars as pl
import pytest
from fastapi import HTTPException

from api.services.analytics import geografico


CNPJ = "12345678000190"


def _perfil_base():
    return pl.DataFrame(
        {
            "id_cnpj": [1, 2, 3],
            "cnpj": [CNPJ, "12345678000270", "98765432000110"],
            "razao_social": ["Alvo Ltda", "Vizinha Ltda", "Regional Ltda"],
            "no_municipio": ["Sao Paulo", "Sao Paulo", "Campinas"],
            "uf": ["SP", "SP", "SP"],
            "id_ibge7": [3550308, 3550308, 3509502],
            "id_regiao_saude": ["10", "10", "10"],
        }
    )


def _matriz_base():
    return pl.DataFrame(
        {
            "id_cnpj": [1, 2, 3],
            "pct_geografico": [30.0, 20.0, None],
            "med_geografico_reg": [10.0, 10.0, 10.0],
            "med_geografico_uf": [5.0, 5.0, 5.0],
            "risco_geografico_reg": [50.0, 25.0, None],
            "risco_geografico_uf": [55.0, 20.0, None],
            "geografico_valor_total": [1000.0, 900.0, 0.0],
            "geografico_valor_outra_uf": [300.0, 180.0, 0.0],
            "geografico_qtd_vendas_outra_uf": [3, 2, 0],
            "flag_dispersao_geografica_atencao": [0, 1, 0],
            "flag_dispersao_geografica_critico": [1, 0, 0],
        }
    )


def _origem_uf():
    return pl.DataFrame(
        {
            "id_cnpj": [1, 1, 1],
            "ano_base": [2020, 2020, 2021],
            "uf_farmacia": ["SP", "SP", "SP"],
            "uf_paciente": ["SP", "RJ", "RJ"],
            "is_outra_uf": [False, True, True],
            "qtd_autorizacoes": [6, 3, 2],
            "valor_autorizado": [60.0, 30.0, 10.0],
        }
    )


def test_calculate_distant_uf_alert_applies_year_range_and_strict_threshold(monkeypatch):
    origins = pl.DataFrame(
        {
            "id_cnpj": [1, 1, 1, 1],
            "ano_base": [2020, 2020, 2021, 2022],
            "uf_paciente": ["mg", "BA", "BA", "AC"],
            "valor_autorizado": [90.0, 10.0, 50.0, 100.0],
        }
    )
    monkeypatch.setattr(geografico, "scan_geografico_origem_uf", lambda: origins.lazy())

    # Em 2020, BA esta fora das vizinhas de SP: 10/100 e nao supera 10%.
    exactly_threshold = geografico.calcular_alerta_uf_nao_vizinha(
        1, " sp ", date(2020, 1, 1), date(2020, 12, 31)
    )
    assert exactly_threshold == {
        "is_dispersao_uf_nao_vizinha": False,
        "pct_dispersao_uf_nao_vizinha": 10.0,
        "valor_dispersao_uf_nao_vizinha": 10.0,
    }

    beyond_threshold = geografico.calcular_alerta_uf_nao_vizinha(1, "SP", date(2020, 1, 1), date(2021, 12, 31))
    assert beyond_threshold["is_dispersao_uf_nao_vizinha"] is True
    assert beyond_threshold["valor_dispersao_uf_nao_vizinha"] == 60.0
    assert beyond_threshold["pct_dispersao_uf_nao_vizinha"] == pytest.approx(40.0)


@pytest.mark.parametrize(
    ("origins", "uf", "expected"),
    [
        (pl.DataFrame(schema={"id_cnpj": pl.Int64, "ano_base": pl.Int32, "uf_paciente": pl.Utf8, "valor_autorizado": pl.Float64}), "SP", False),
        (pl.DataFrame({"id_cnpj": [1], "ano_base": [2020], "uf_paciente": ["BA"], "valor_autorizado": [0.0]}), "SP", False),
        (pl.DataFrame({"id_cnpj": [1], "ano_base": [2020], "uf_paciente": ["SP"], "valor_autorizado": [100.0]}), "SP", False),
    ],
)
def test_calculate_distant_uf_alert_returns_no_alert_for_empty_zero_or_only_near_origins(monkeypatch, origins, uf, expected):
    monkeypatch.setattr(geografico, "scan_geografico_origem_uf", lambda: origins.lazy())
    result = geografico.calcular_alerta_uf_nao_vizinha(1, uf)
    assert result["is_dispersao_uf_nao_vizinha"] is expected
    if origins.is_empty() or origins["valor_autorizado"].sum() == 0:
        assert result["pct_dispersao_uf_nao_vizinha"] == 0.0


def test_geographic_alert_rejects_invalid_uf_and_cache_contract(monkeypatch):
    monkeypatch.setattr(geografico, "scan_geografico_origem_uf", lambda: _origem_uf().lazy())
    with pytest.raises(HTTPException, match="UF de farmacia invalida"):
        geografico.calcular_alerta_uf_nao_vizinha(1, "XX")

    monkeypatch.setattr(
        geografico,
        "scan_geografico_origem_uf",
        lambda: pl.DataFrame({"id_cnpj": [1], "ano_base": [2020]}).lazy(),
    )
    with pytest.raises(HTTPException, match="Contrato de cache invalido em geografico_origem_uf"):
        geografico.calcular_alerta_uf_nao_vizinha(1, "SP")


def test_origin_uf_details_aggregates_period_and_external_uf_shares(monkeypatch):
    monkeypatch.setattr(geografico, "get_df_perfil_estabelecimento", _perfil_base)
    monkeypatch.setattr(geografico, "scan_geografico_origem_uf", lambda: _origem_uf().lazy())

    result = geografico.get_geografico_origem_uf(CNPJ, date(2020, 1, 1), date(2020, 12, 31))
    assert result.uf_farmacia == "SP"
    assert result.total_valor_origem == 90.0
    assert result.total_autorizacoes_origem == 9
    assert result.total_valor_outra_uf == 30.0
    assert result.total_autorizacoes_outra_uf == 3
    assert result.percentual_financeiro_outra_uf == pytest.approx(100 / 3)
    assert result.principal_uf_externa.uf_paciente == "RJ"
    assert [row.percentual_sobre_total for row in result.rows] == pytest.approx([200 / 3, 100 / 3])
    assert result.rows[0].percentual_sobre_outra_uf is None
    assert result.rows[1].percentual_sobre_outra_uf == 100.0


def test_origin_uf_details_handles_cnpj_and_data_contract_errors(monkeypatch):
    with pytest.raises(HTTPException, match="CNPJ deve conter 14 digitos"):
        geografico.get_geografico_origem_uf("123")

    monkeypatch.setattr(geografico, "get_df_perfil_estabelecimento", lambda: pl.DataFrame({"cnpj": [CNPJ]}))
    with pytest.raises(HTTPException, match="Contrato de cache invalido em perfil_estabelecimento"):
        geografico.get_geografico_origem_uf(CNPJ)

    monkeypatch.setattr(geografico, "get_df_perfil_estabelecimento", _perfil_base)
    with pytest.raises(HTTPException) as not_found:
        geografico.get_geografico_origem_uf("00000000000000")
    assert not_found.value.status_code == 404

    monkeypatch.setattr(
        geografico,
        "scan_geografico_origem_uf",
        lambda: pl.DataFrame({"id_cnpj": [1]}).lazy(),
    )
    with pytest.raises(HTTPException, match="Contrato de cache invalido em geografico_origem_uf"):
        geografico.get_geografico_origem_uf(CNPJ)

    monkeypatch.setattr(
        geografico,
        "scan_geografico_origem_uf",
        lambda: _origem_uf().filter(pl.col("ano_base") == 2021).lazy(),
    )
    with pytest.raises(HTTPException, match="sem detalhamento geografico por UF"):
        geografico.get_geografico_origem_uf(CNPJ, date(2020, 1, 1), date(2020, 12, 31))

    no_value = _origem_uf().with_columns(pl.lit(0.0).alias("valor_autorizado"))
    monkeypatch.setattr(geografico, "scan_geografico_origem_uf", lambda: no_value.lazy())
    with pytest.raises(HTTPException, match="sem valor autorizado positivo"):
        geografico.get_geografico_origem_uf(CNPJ)


def test_local_geographic_benchmark_builds_sorted_scopes_and_statuses(monkeypatch):
    monkeypatch.setattr(geografico, "get_df_perfil_estabelecimento", _perfil_base)
    calls = []

    def matrix(**kwargs):
        calls.append(kwargs)
        return _matriz_base()

    monkeypatch.setattr(geografico, "build_dynamic_matriz_risco", matrix)
    start, end = date(2020, 1, 1), date(2020, 12, 31)
    result = geografico.get_geografico_benchmark_local("12.345.678/0001-90", start, end)

    assert result.cnpj == CNPJ
    assert calls == [{"data_inicio": start, "data_fim": end}]
    assert result.municipio.label == "Sao Paulo/SP"
    assert result.municipio.total_estabelecimentos == 2
    assert [row.cnpj for row in result.municipio.rows] == [CNPJ, "12345678000270"]
    assert [row.status for row in result.municipio.rows] == ["CRITICO", "ATENCAO"]
    assert [row.is_alvo for row in result.municipio.rows] == [True, False]
    assert result.regiao_saude.escopo == "regiao_saude"
    assert result.regiao_saude.total_estabelecimentos == 3
    assert result.regiao_saude.rows[-1].status == "SEM DADOS"
    assert result.regiao_saude.rows[-1].percentual_outra_uf is None


def test_local_geographic_benchmark_validates_cnpj_profile_target_and_matrix(monkeypatch):
    with pytest.raises(HTTPException, match="CNPJ deve conter 14 digitos"):
        geografico.get_geografico_benchmark_local("invalid")

    monkeypatch.setattr(geografico, "get_df_perfil_estabelecimento", lambda: pl.DataFrame({"cnpj": [CNPJ]}))
    with pytest.raises(HTTPException, match="Contrato de cache invalido em perfil_estabelecimento"):
        geografico.get_geografico_benchmark_local(CNPJ)

    monkeypatch.setattr(geografico, "get_df_perfil_estabelecimento", _perfil_base)
    with pytest.raises(HTTPException) as not_found:
        geografico.get_geografico_benchmark_local("00000000000000")
    assert not_found.value.status_code == 404

    monkeypatch.setattr(geografico, "build_dynamic_matriz_risco", lambda **kwargs: pl.DataFrame({"id_cnpj": [1]}))
    with pytest.raises(HTTPException, match="Contrato de cache invalido em matriz_risco_dinamica"):
        geografico.get_geografico_benchmark_local(CNPJ)


def test_geographic_schema_helpers_map_defaults_and_status_precedence():
    row = geografico._row_schema(
        {
            "uf_farmacia": "SP", "uf_paciente": "BA", "is_outra_uf": 1,
            "qtd_autorizacoes": None, "valor_autorizado": None,
            "percentual_sobre_total": None, "percentual_sobre_outra_uf": None,
        }
    )
    assert row.qtd_autorizacoes == 0 and row.valor_autorizado == 0
    assert row.percentual_sobre_total == 0 and row.percentual_sobre_outra_uf is None
    assert geografico._status_dispersao({"flag_dispersao_geografica_critico": 1, "flag_dispersao_geografica_atencao": 1}) == "CRITICO"
    assert geografico._status_dispersao({"flag_dispersao_geografica_atencao": 1}) == "ATENCAO"
    assert geografico._status_dispersao({"pct_geografico": None}) == "SEM DADOS"
    assert geografico._status_dispersao({"pct_geografico": 0}) == "NORMAL"
    assert geografico._clean_cnpj("12.345.678/0001-90") == CNPJ
