from datetime import date

import polars as pl
import pytest
from fastapi import HTTPException

from api.services.analytics import fator_risco
from api.services.analytics.filtros_farmacia import FiltrosFarmacia


def test_fator_risco_buckets_filter_by_uf_and_percent_range(monkeypatch):
    movimento = pl.DataFrame(
        {
            "id_cnpj": [1, 2, 3],
            "periodo": [date(2020, 1, 1)] * 3,
            "total_vendas": [100.0, 100.0, 100.0],
            "total_sem_comprovacao": [10.0, 25.0, 85.0],
        }
    )
    perfil = pl.DataFrame(
        {"id_cnpj": [1, 2, 3], "uf": ["SP", "SP", "RJ"]}
    )
    monkeypatch.setattr(fator_risco, "get_df", lambda: movimento)
    monkeypatch.setattr(fator_risco, "get_df_perfil_estabelecimento", lambda: perfil)

    result = fator_risco.get_fator_risco_data(
        db=None,
        data_inicio=date(2020, 1, 1),
        data_fim=date(2020, 1, 31),
        uf="SP",
        filtros=FiltrosFarmacia(perc_min=20, perc_max=30),
    )

    assert result.periodo_formatado == "2020-01-01 a 2020-01-31"
    assert [(b.faixa, b.qtd, b.valor_raw) for b in result.buckets] == [("20% - 30%", 1, 25.0)]


def test_fator_risco_uses_historical_label_when_dates_not_both_provided(monkeypatch):
    movimento = pl.DataFrame(
        {"id_cnpj": [1], "periodo": [date(2020, 1, 1)], "total_vendas": [100.0], "total_sem_comprovacao": [0.0]}
    )
    perfil = pl.DataFrame({"id_cnpj": [1], "uf": ["SP"]})
    monkeypatch.setattr(fator_risco, "get_df", lambda: movimento)
    monkeypatch.setattr(fator_risco, "get_df_perfil_estabelecimento", lambda: perfil)

    result = fator_risco.get_fator_risco_data(db=None, data_inicio=date(2020, 1, 1))
    assert result.periodo_formatado == "Acumulado Historico"
    assert result.buckets[0].faixa == "00% - 10%"


def test_fator_risco_reports_failed_calculation_explicitly(monkeypatch):
    monkeypatch.setattr(fator_risco, "get_df", lambda: pl.DataFrame())
    monkeypatch.setattr(fator_risco, "get_df_perfil_estabelecimento", lambda: pl.DataFrame())
    result = fator_risco.get_fator_risco_data(db=None)
    assert result.periodo_formatado == "Erro ao calcular"
    assert result.buckets == []


def test_fator_risco_applies_full_establishment_scope_and_dispersal(monkeypatch):
    movimento = pl.DataFrame(
        {
            "id_cnpj": [1, 2, 3],
            "periodo": [date(2015, 7, 1), date(2015, 8, 1), date(2015, 8, 1)],
            "total_vendas": [100.0, 100.0, 100.0],
            "total_sem_comprovacao": [25.0, 30.0, 50.0],
        }
    )
    perfil = pl.DataFrame(
        {
            "id_cnpj": [1, 2, 3],
            "uf": ["SP", "SP", "RJ"],
            "id_regiao_saude": ["10", "10", "20"],
            "id_ibge7": [3550308, 3550308, 3304557],
            "situacao_rf": ["ATIVA", "ATIVA", "BAIXADA"],
            "is_conexao_ativa": [True, True, False],
            "porte_empresa": ["ME", "EPP", "ME"],
            "is_grande_rede": [True, False, True],
            "unidade_pf": ["Matriz", "Filial", "Matriz"],
            "cnpj": ["12345678000190", "12345678000270", "98765432000110"],
            "razao_social": ["Farmacia Central", "Farmacia Bairro", "Outra Farmacia"],
            "nome_fantasia": ["Central", "Bairro", "Outra"],
        }
    )
    monkeypatch.setattr(fator_risco, "get_df", lambda: movimento)
    monkeypatch.setattr(fator_risco, "get_df_perfil_estabelecimento", lambda: perfil)
    captured = {}

    def keep_profile(scope, **kwargs):
        captured.update(kwargs)
        return scope

    monkeypatch.setattr(fator_risco, "build_perfil_filtrado", keep_profile)
    monkeypatch.setattr(
        fator_risco,
        "get_dispersao_uf_sem_fronteira_id_cnpjs_df",
        lambda inicio, fim, limite: pl.DataFrame({"id_cnpj": [1]}),
    )
    filters = FiltrosFarmacia(
        perc_min=20,
        perc_max=30,
        val_min=20,
        situacao_rf="ATIVA",
        conexao_ms="Ativa",
        porte_empresa="ME",
        grande_rede="Sim",
        cnpj_raiz="12345678000190",
        unidade_pf="Matriz",
        estabelecimento="central",
        dispersao_uf_sem_fronteira=True,
        dispersao_uf_sem_fronteira_limite=10,
    )

    result = fator_risco.get_fator_risco_data(
        db=None,
        data_inicio=date(2015, 1, 1),
        data_fim=date(2015, 8, 31),
        uf="SP",
        regiao_id=10,
        id_ibge7=3550308,
        filtros=filters,
    )

    assert [(bucket.faixa, bucket.qtd, bucket.valor_raw) for bucket in result.buckets] == [
        ("20% - 30%", 1, 25.0)
    ]
    assert captured["periodo_inicio"] == date(2015, 7, 1)
    assert captured["data_referencia"] == date(2015, 8, 31)
    assert result.periodo_formatado == "2015-07-01 a 2015-08-31"


def test_fator_risco_supports_cnpj_root_and_preserves_http_errors(monkeypatch):
    movimento = pl.DataFrame(
        {"id_cnpj": [1], "periodo": [date(2020, 1, 1)], "total_vendas": [100.0], "total_sem_comprovacao": [50.0]}
    )
    perfil = pl.DataFrame(
        {
            "id_cnpj": [1],
            "uf": ["SP"],
            "cnpj": ["12345678000190"],
            "razao_social": ["Farmacia Central"],
            "nome_fantasia": ["Central"],
        }
    )
    monkeypatch.setattr(fator_risco, "get_df", lambda: movimento)
    monkeypatch.setattr(fator_risco, "get_df_perfil_estabelecimento", lambda: perfil)
    monkeypatch.setattr(fator_risco, "build_perfil_filtrado", lambda scope, **kwargs: scope)

    result = fator_risco.get_fator_risco_data(
        db=None, filtros=FiltrosFarmacia(cnpj_raiz="12345678", perc_min=50, perc_max=50)
    )
    assert [(bucket.faixa, bucket.qtd) for bucket in result.buckets] == [("40% - 50%", 1)]

    def raise_http(*_args, **_kwargs):
        raise HTTPException(status_code=503, detail="required source unavailable")

    monkeypatch.setattr(fator_risco, "build_perfil_filtrado", raise_http)
    with pytest.raises(HTTPException, match="required source unavailable"):
        fator_risco.get_fator_risco_data(db=None)
