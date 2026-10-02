from datetime import date
from decimal import Decimal

import polars as pl
import pytest
from fastapi import HTTPException

from backend.api.services.analytics import bootstrap


CNPJ = "12345678000190"


def _profile():
    return pl.DataFrame(
        {
            "id_cnpj": [1], "cnpj": [CNPJ], "no_municipio": ["Sao Paulo"], "id_ibge7": [3550308],
            "id_regiao_saude": [10], "uf": ["SP"], "razao_social": ["Farmacia Alvo"],
            "is_grande_rede": [True], "qtd_estabelecimentos_rede": [4], "situacao_rf": ["ATIVA"],
            "porte_empresa": ["ME"], "is_conexao_ativa": [True], "is_matriz": [False],
            "is_cnae_incompativel_farmaceutico": [True],
        }
    )


def test_cnpj_bootstrap_composes_status_cadastro_period_risk_and_geo(monkeypatch):
    farmacia = pl.DataFrame(
        {
            "cnpj": [CNPJ], "razao_social": ["Farmacia Alvo"], "nome_fantasia": ["Alvo"],
            "municipio": ["Sao Paulo"], "uf": ["SP"],
        }
    )
    movement = pl.DataFrame(
        {
            "id_cnpj": [1, 1], "periodo": [date(2024, 1, 1), date(2024, 2, 1)],
            "total_vendas": [100.0, 200.0], "total_sem_comprovacao": [10.0, 20.0],
            "total_qnt_caixas_vendidas": [10, 20], "total_qnt_caixas_sem_comprovacao": [1, 2],
        }
    )
    matrix = pl.DataFrame(
        {
            "cnpj": [CNPJ], "score_risco_final": [3.5], "classificacao_risco": ["ALTO"],
            "rank_nacional": [1], "total_nacional": [10], "rank_uf": [1], "total_uf": [5],
            "rank_regiao_saude": [1], "total_regiao_saude": [3], "rank_municipio": [1],
            "total_municipio": [2], "uf": ["SP"], "id_regiao_saude": [10], "id_ibge7": [3550308],
        }
    )
    localidades = pl.DataFrame(
        {
            "sg_uf": ["SP", "SP"], "no_regiao_saude": ["Regiao 10", "Regiao 10"],
            "id_regiao_saude": [10, 10], "no_municipio": ["Sao Paulo", "Osasco"],
            "id_ibge7": [3550308, 3534401], "nu_populacao": [1000, 2000], "unidade_pf": ["Farmacia", "Farmacia"],
        }
    )
    monkeypatch.setattr(bootstrap, "get_df_dados_farmacia", lambda: farmacia)
    monkeypatch.setattr(bootstrap, "get_df_perfil_estabelecimento", _profile)
    monkeypatch.setattr(bootstrap, "get_df", lambda: movement)
    monkeypatch.setattr(bootstrap, "build_dynamic_matriz_risco", lambda **_kwargs: matrix)
    monkeypatch.setattr(bootstrap, "get_localidades_df", lambda: localidades)
    monkeypatch.setattr(bootstrap, "get_cnaes_secundarios_farmacia", lambda _cnpj: [{"id_cnae": "123"}])
    monkeypatch.setattr(
        bootstrap,
        "calcular_alerta_uf_nao_vizinha",
        lambda **_kwargs: {
            "is_dispersao_uf_nao_vizinha": True,
            "pct_dispersao_uf_nao_vizinha": 20.0,
            "valor_dispersao_uf_nao_vizinha": 60.0,
        },
    )

    result = bootstrap.get_cnpj_bootstrap("12.345.678/0001-90", date(2024, 1, 1), date(2024, 2, 28))

    assert result.status.status == "valid" and result.status.in_program is True
    assert result.status.cnpj == CNPJ and result.status.nome_fantasia == "Alvo"
    assert result.cadastro.cnpj == CNPJ
    assert result.cadastro.is_cnae_incompativel_farmaceutico is True
    assert result.cadastro.is_cnae_farmacia_ausente is True
    assert result.cadastro.is_dispersao_uf_nao_vizinha is True
    assert [item.id_cnae for item in result.cadastro.cnaes_secundarios] == [123]
    assert result.cnpj_data.totalMov == 300.0 and result.cnpj_data.valSemComp == 30.0
    assert result.cnpj_data.score_risco_final == 3.5 and result.cnpj_data.rank_uf == 1
    assert result.period_summary.percValSemComp == 10.0
    assert result.geo_data.id_regiao_saude == 10 and result.qtd_municipios_regiao == 2


def test_bootstrap_normalizers_and_small_dataframe_helpers_validate_contracts():
    assert bootstrap._clean_cnpj("12.345.678/0001-90") == CNPJ
    assert bootstrap._first_row(pl.DataFrame({"x": [1]}), "sample") == {"x": 1}
    with pytest.raises(HTTPException, match="sample nao encontrado"):
        bootstrap._first_row(pl.DataFrame(), "sample")
    with pytest.raises(HTTPException, match="Contrato de cache invalido"):
        bootstrap._require_columns(pl.DataFrame({"present": [1]}), ["missing"], "sample")

    assert bootstrap._scope_total(pl.DataFrame(), None, None) is None
    assert bootstrap._scope_total(pl.DataFrame({"value": [1]}), None, None) is None
    risk = pl.DataFrame({"score_risco_final": [1.0, None, 3.0], "uf": ["SP", "SP", "RJ"]})
    assert bootstrap._scope_total(risk, None, None) == 2
    assert bootstrap._scope_total(risk, "uf", "SP") == 1
    assert bootstrap._scope_total(risk, "missing", "SP") is None
    assert bootstrap._scope_total(risk, "uf", None) is None

    assert bootstrap._optional_float(None, "f") is None
    assert bootstrap._optional_float(Decimal("1.25"), "f") == 1.25
    assert bootstrap._optional_float(" 2.5 ", "f") == 2.5
    for invalid in (True, "abc", object()):
        with pytest.raises(HTTPException, match="deve ser numerico"):
            bootstrap._optional_float(invalid, "f")

    assert bootstrap._optional_int(None, "n") is None
    assert bootstrap._optional_int(2, "n") == 2
    assert bootstrap._optional_int(2.0, "n") == 2
    assert bootstrap._optional_int(Decimal("3"), "n") == 3
    assert bootstrap._optional_int("4", "n") == 4
    for invalid in (True, 2.5, Decimal("2.5"), Decimal("sNaN"), "2.5", "sNaN", object()):
        with pytest.raises(HTTPException, match="deve ser inteiro"):
            bootstrap._optional_int(invalid, "n")
    assert bootstrap._optional_str(None, "s") is None
    assert bootstrap._optional_str("value", "s") == "value"
    with pytest.raises(HTTPException, match="deve ser texto"):
        bootstrap._optional_str(2, "s")


def test_period_summary_handles_empty_period_zero_denominators_and_missing_columns(monkeypatch):
    movement = pl.DataFrame(
        {
            "id_cnpj": [1], "periodo": [date(2020, 1, 1)], "total_vendas": [0.0],
            "total_sem_comprovacao": [4.0], "total_qnt_caixas_vendidas": [0],
            "total_qnt_caixas_sem_comprovacao": [2],
        }
    )
    monkeypatch.setattr(bootstrap, "get_df", lambda: movement)
    assert bootstrap._period_summary(1, date(2021, 1, 1), None).totalMov == 0
    summary = bootstrap._period_summary(1, None, None)
    assert summary.percValSemComp == 0.0 and summary.percQtdeSemComp == 0.0
    assert summary.totalQtde == 0 and summary.qtdeSemComp == 2

    monkeypatch.setattr(bootstrap, "get_df", lambda: pl.DataFrame({"id_cnpj": [1]}))
    with pytest.raises(HTTPException, match="movimentacao"):
        bootstrap._period_summary(1, None, None)


def test_risk_row_and_geo_row_return_scoped_counts_and_validate_required_ids(monkeypatch):
    risk = pl.DataFrame(
        {
            "cnpj": ["00000000000001", CNPJ], "score_risco_final": [2.0, 3.0],
            "classificacao_risco": ["MEDIO", "ALTO"], "rank_nacional": [1, 2], "total_nacional": [2, 2],
            "rank_uf": [1, 1], "total_uf": [1, 1], "rank_regiao_saude": [1, 1], "total_regiao_saude": [1, 1],
            "rank_municipio": [1, 1], "total_municipio": [1, 1], "uf": ["SP", "SP"],
            "id_regiao_saude": [10, 10], "id_ibge7": [3550308, 3550308],
        }
    )
    monkeypatch.setattr(bootstrap, "build_dynamic_matriz_risco", lambda **_kwargs: risk)
    assert bootstrap._risk_row(CNPJ, "SP", 10, 3550308, None, None)["classificacao_risco"] == "ALTO"
    missing = bootstrap._risk_row("missing", "SP", 10, 3550308, None, None)
    assert missing["total_nacional"] == 2 and missing["total_uf"] == 2
    assert missing["total_regiao_saude"] == 2 and missing["total_municipio"] == 2

    with pytest.raises(HTTPException, match="matriz_risco_dinamica"):
        monkeypatch.setattr(bootstrap, "build_dynamic_matriz_risco", lambda **_kwargs: pl.DataFrame({"cnpj": [CNPJ]}))
        bootstrap._risk_row(CNPJ, "SP", 10, 3550308, None, None)

    profile_row = {"id_ibge7": 3550308}
    localities = pl.DataFrame(
        {
            "sg_uf": ["SP"], "no_regiao_saude": ["Regiao"], "id_regiao_saude": [10],
            "no_municipio": ["Sao Paulo"], "id_ibge7": [3550308], "nu_populacao": [None], "unidade_pf": [None],
        }
    )
    monkeypatch.setattr(bootstrap, "get_localidades_df", lambda: localities)
    geo, municipality_count = bootstrap._geo_row(profile_row)
    assert geo.nu_populacao is None and geo.unidade_pf is None
    assert municipality_count == 1
    with pytest.raises(HTTPException, match="sem id_ibge7"):
        bootstrap._geo_row({})
    with pytest.raises(HTTPException, match="localidades"):
        monkeypatch.setattr(bootstrap, "get_localidades_df", lambda: pl.DataFrame({"id_ibge7": [1]}))
        bootstrap._geo_row(profile_row)

    monkeypatch.setattr(bootstrap, "get_localidades_df", lambda: localities.with_columns(pl.lit(None).cast(pl.Int64).alias("id_regiao_saude")))
    with pytest.raises(HTTPException, match="sem id_regiao_saude"):
        bootstrap._geo_row(profile_row)


def test_bootstrap_rejects_bad_cnpj_and_missing_program_or_profile_records(monkeypatch):
    with pytest.raises(HTTPException) as invalid:
        bootstrap.get_cnpj_bootstrap("bad")
    assert invalid.value.status_code == 422

    monkeypatch.setattr(
        bootstrap,
        "get_df_dados_farmacia",
        lambda: pl.DataFrame({"cnpj": [CNPJ], "razao_social": ["F"], "nome_fantasia": ["F"], "municipio": ["M"], "uf": ["SP"]}),
    )
    monkeypatch.setattr(bootstrap, "get_df_perfil_estabelecimento", lambda: _profile())
    with pytest.raises(HTTPException) as missing:
        bootstrap.get_cnpj_bootstrap("00000000000000")
    assert missing.value.status_code == 404

    monkeypatch.setattr(bootstrap, "get_df_dados_farmacia", lambda: pl.DataFrame({"cnpj": [CNPJ]}))
    with pytest.raises(HTTPException, match="dados_farmacia"):
        bootstrap.get_cnpj_bootstrap(CNPJ)

    monkeypatch.setattr(
        bootstrap,
        "get_df_dados_farmacia",
        lambda: pl.DataFrame({"cnpj": [CNPJ], "razao_social": ["F"], "nome_fantasia": ["F"], "municipio": ["M"], "uf": ["SP"]}),
    )
    monkeypatch.setattr(bootstrap, "get_df_perfil_estabelecimento", lambda: pl.DataFrame({"cnpj": [CNPJ]}))
    with pytest.raises(HTTPException, match="perfil_estabelecimento"):
        bootstrap.get_cnpj_bootstrap(CNPJ)

    monkeypatch.setattr(bootstrap, "get_df_perfil_estabelecimento", lambda: _profile().head(0))
    with pytest.raises(HTTPException, match="Perfil do CNPJ nao encontrado"):
        bootstrap.get_cnpj_bootstrap(CNPJ)
