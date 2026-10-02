from datetime import date

import polars as pl
import pytest
from fastapi import HTTPException

from api.services.analytics import dashboard
from api.services.analytics import matriz_risco_dinamica as dynamic_matrix


def _dashboard_frames():
    movimento = pl.DataFrame(
        {
            "id_cnpj": [1, 2],
            "periodo": [date(2020, 1, 1), date(2020, 1, 1)],
            "total_vendas": [100.0, 200.0],
            "total_sem_comprovacao": [20.0, 10.0],
            "total_qnt_caixas_vendidas": [10, 20],
            "total_qnt_caixas_sem_comprovacao": [2, 1],
        }
    )
    perfil = pl.DataFrame(
        {
            "id_cnpj": [1, 2],
            "cnpj": ["11111111000101", "22222222000102"],
            "uf": ["SP", "RJ"],
            "id_regiao_saude": ["10", "20"],
            "id_ibge7": [3550308, 3304557],
            "no_municipio": ["sao paulo", "rio de janeiro"],
            "razao_social": ["Farmacia Um", "Farmacia Dois"],
            "nome_fantasia": ["Um", "Dois"],
            "situacao_rf": ["ATIVA", "ATIVA"],
            "is_conexao_ativa": [True, True],
            "porte_empresa": ["ME", "ME"],
            "is_grande_rede": [False, False],
            "unidade_pf": ["Matriz", "Matriz"],
            "qtd_estabelecimentos_rede": [1, 1],
            "is_matriz": [True, True],
        }
    )
    return movimento, perfil


def _install_dynamic_matrix(monkeypatch, perfil):
    rows = []
    for identifier, pct in [(1, 20.0), (2, 5.0)]:
        row = {column: 0.0 for column in dynamic_matrix._MATRIX_COMPONENT_COLUMNS}
        row.update({"id_cnpj": identifier, "ano_base": 2020, "valor_total_vendas": 100.0, "valor_sem_comprovacao": pct})
        rows.append(row)
    monkeypatch.setattr(dynamic_matrix, "get_df_matriz_risco", lambda: pl.DataFrame(rows))
    monkeypatch.setattr(dynamic_matrix, "get_df_perfil_estabelecimento", lambda: perfil)
    monkeypatch.setattr(dynamic_matrix, "get_cache_generation", lambda: 991)
    monkeypatch.setattr(dynamic_matrix, "get_volume_atipico_aumento_minimo", lambda: 10000.0)
    dynamic_matrix._DYNAMIC_CACHE.clear()


def test_validar_secoes_dashboard_requires_safe_explicit_scope():
    assert dashboard.validar_secoes_dashboard(["ufs", "kpis"], None) == frozenset({"ufs", "kpis"})
    with pytest.raises(HTTPException) as empty:
        dashboard.validar_secoes_dashboard([], None)
    assert empty.value.status_code == 422
    with pytest.raises(HTTPException) as unknown:
        dashboard.validar_secoes_dashboard(["rede"], None)
    assert "rede" in unknown.value.detail
    with pytest.raises(HTTPException) as unscoped:
        dashboard.validar_secoes_dashboard(["cnpjs"], None)
    assert "exige o filtro cnpjs" in unscoped.value.detail


def test_dashboard_aggregates_only_requested_sections_and_applies_region_id(monkeypatch):
    movimento, perfil = _dashboard_frames()
    monkeypatch.setattr(dashboard, "get_df", lambda: movimento)
    monkeypatch.setattr(dashboard, "get_df_perfil_estabelecimento", lambda: perfil)

    result = dashboard.get_dashboard_data(
        db=None,
        data_inicio=date(2020, 1, 1),
        data_fim=date(2020, 1, 31),
        regiao_id=10,
        secoes={"kpis", "ufs", "municipios"},
    )

    assert result.kpis is not None
    assert {k.id: k.value for k in result.kpis}["total_cnpjs"] == "1"
    assert len(result.resultado_sentinela_uf) == 1
    assert result.resultado_sentinela_uf[0].uf == "SP"
    assert result.resultado_sentinela_uf[0].totalMov == 100.0
    assert result.resultado_municipios[0].municipio == "sao paulo"
    assert result.resultado_cnpjs is None


def test_dashboard_wraps_invalid_cache_as_service_unavailable(monkeypatch):
    monkeypatch.setattr(dashboard, "get_df", lambda: pl.DataFrame())
    monkeypatch.setattr(dashboard, "get_df_perfil_estabelecimento", lambda: pl.DataFrame())
    with pytest.raises(HTTPException) as error:
        dashboard.get_dashboard_data(db=None, secoes={"kpis"})
    assert error.value.status_code == 503
    assert "cache base invalido" in error.value.detail


def test_dashboard_cnpj_section_uses_explicit_cnpj_list_and_risk_snapshot(monkeypatch):
    movimento, perfil = _dashboard_frames()
    monkeypatch.setattr(dashboard, "get_df", lambda: movimento)
    monkeypatch.setattr(dashboard, "get_df_perfil_estabelecimento", lambda: perfil)
    _install_dynamic_matrix(monkeypatch, perfil)
    result = dashboard.get_dashboard_data(
        db=None, cnpjs=["11111111000101"], secoes={"cnpjs"}
    )
    assert result.kpis is None
    assert len(result.resultado_cnpjs) == 1
    assert result.resultado_cnpjs[0].classificacao_risco == "CRÍTICO"
    assert result.resultado_cnpjs[0].score_risco_final is not None
    assert result.resultado_cnpjs[0].totalMov == 100.0


def test_producao_semestral_aggregates_and_respects_risk_filters(monkeypatch):
    from api.services.analytics.filtros_farmacia import FiltrosFarmacia

    movimento, perfil = _dashboard_frames()
    monkeypatch.setattr(dashboard, "get_df", lambda: movimento)
    monkeypatch.setattr(dashboard, "get_df_perfil_estabelecimento", lambda: perfil)
    result = dashboard.get_producao_semestral_data(
        db=None,
        data_inicio=date(2020, 1, 1),
        data_fim=date(2020, 12, 31),
        filtros=FiltrosFarmacia(perc_min=15, perc_max=25, val_min=15),
    )
    assert len(result.pontos) == 1
    assert result.pontos[0].semestre == "2020-S1"
    assert result.pontos[0].valor_producao == 100.0
    assert result.pontos[0].valor_regular == 80.0


@pytest.mark.parametrize(
    ("amount", "quantity", "expected_sales", "expected_quantity"),
    [
        (1_500_000_000.0, 1_500_000_000, "R$ 1,50 Bi", "1,50 Bi"),
        (1_500_000.0, 1_500_000, "R$ 1,50 Mi", "1,50 Mi"),
        (1_500.0, 1_500, "R$ 2 K", "2 K"),
        (500.0, 500, "R$ 500,00", "500"),
    ],
)
def test_dashboard_kpis_format_values_across_magnitude_bands(
    monkeypatch, amount, quantity, expected_sales, expected_quantity
):
    from api.services.analytics.filtros_farmacia import FiltrosFarmacia

    movimento, perfil = _dashboard_frames()
    movimento = movimento.with_columns(
        pl.when(pl.col("id_cnpj") == 1).then(amount).otherwise(0.0).alias("total_vendas"),
        pl.when(pl.col("id_cnpj") == 1).then(amount / 10).otherwise(0.0).alias("total_sem_comprovacao"),
        pl.when(pl.col("id_cnpj") == 1).then(quantity).otherwise(0).alias("total_qnt_caixas_vendidas"),
    )
    monkeypatch.setattr(dashboard, "get_df", lambda: movimento)
    monkeypatch.setattr(dashboard, "get_df_perfil_estabelecimento", lambda: perfil)
    monkeypatch.setattr(dashboard, "build_perfil_filtrado", lambda frame, **_kwargs: frame)

    result = dashboard.get_dashboard_data(
        db=None, data_inicio=date(2020, 1, 1), data_fim=date(2020, 12, 31),
        filtros=FiltrosFarmacia(cnpj_raiz="11111111"), secoes={"kpis"},
    )
    values = {item.id: item.value for item in result.kpis}

    assert values["valor_vendas"] == expected_sales
    assert values["total_meds"] == expected_quantity


def test_dashboard_applies_full_and_root_cnpj_filters_with_cadastral_filters(monkeypatch):
    from api.services.analytics.filtros_farmacia import FiltrosFarmacia

    movimento, perfil = _dashboard_frames()
    monkeypatch.setattr(dashboard, "get_df", lambda: movimento)
    monkeypatch.setattr(dashboard, "get_df_perfil_estabelecimento", lambda: perfil)
    monkeypatch.setattr(dashboard, "build_perfil_filtrado", lambda frame, **_kwargs: frame)

    filters = FiltrosFarmacia(
        situacao_rf="ATIVA", conexao_ms="Ativa", porte_empresa="ME", grande_rede="Nao",
        unidade_pf="Matriz", cnpj_raiz="11111111", val_min=15,
    )
    result = dashboard.get_dashboard_data(
        db=None, uf="SP", regiao_id=10, id_ibge7=3550308, filtros=filters, secoes={"kpis"},
    )
    assert {item.id: item.value for item in result.kpis}["total_cnpjs"] == "1"

    exact = dashboard.get_dashboard_data(
        db=None, filtros=FiltrosFarmacia(cnpj_raiz="11111111000101"), secoes={"kpis"},
    )
    assert {item.id: item.value for item in exact.kpis}["total_cnpjs"] == "1"


def test_dashboard_applies_cnpj_allowlist_and_dispersal_scope(monkeypatch):
    from api.services.analytics.filtros_farmacia import FiltrosFarmacia

    movimento, perfil = _dashboard_frames()
    monkeypatch.setattr(dashboard, "get_df", lambda: movimento)
    monkeypatch.setattr(dashboard, "get_df_perfil_estabelecimento", lambda: perfil)
    monkeypatch.setattr(dashboard, "build_perfil_filtrado", lambda frame, **_kwargs: frame)
    calls = []
    monkeypatch.setattr(
        dashboard, "get_dispersao_uf_sem_fronteira_id_cnpjs_df",
        lambda start, end, threshold: (
            calls.append((start, end, threshold)), pl.DataFrame({"id_cnpj": [1]})
        )[1],
    )

    result = dashboard.get_dashboard_data(
        db=None, cnpjs=["11111111000101", "22222222000102"],
        filtros=FiltrosFarmacia(dispersao_uf_sem_fronteira=True, dispersao_uf_sem_fronteira_limite=0.2),
        secoes={"kpis"},
    )

    assert {item.id: item.value for item in result.kpis}["total_cnpjs"] == "1"
    assert calls == [(date(2015, 7, 1), date(2024, 12, 31), 0.2)]


def test_dashboard_preserves_http_errors_from_cache_or_dependencies(monkeypatch):
    def unavailable():
        raise HTTPException(status_code=409, detail="dependency validation")

    monkeypatch.setattr(dashboard, "get_df", unavailable)

    with pytest.raises(HTTPException) as error:
        dashboard.get_dashboard_data(db=None, secoes={"kpis"})

    assert error.value.status_code == 409
    assert error.value.detail == "dependency validation"


def test_production_returns_empty_for_no_period_rows_and_for_excluded_risk(monkeypatch):
    from api.services.analytics.filtros_farmacia import FiltrosFarmacia

    movimento, perfil = _dashboard_frames()
    monkeypatch.setattr(dashboard, "get_df", lambda: movimento)
    monkeypatch.setattr(dashboard, "get_df_perfil_estabelecimento", lambda: perfil)
    monkeypatch.setattr(dashboard, "build_perfil_filtrado", lambda frame, **_kwargs: frame)

    no_period = dashboard.get_producao_semestral_data(
        db=None, data_inicio=date(2022, 1, 1), data_fim=date(2022, 12, 31)
    )
    assert no_period.pontos == []

    excluded = dashboard.get_producao_semestral_data(
        db=None, data_inicio=date(2020, 1, 1), data_fim=date(2020, 12, 31),
        filtros=FiltrosFarmacia(perc_min=50),
    )
    assert excluded.pontos == []


def test_production_applies_cadastral_cnpj_and_dispersal_filters(monkeypatch):
    from api.services.analytics.filtros_farmacia import FiltrosFarmacia

    movimento, perfil = _dashboard_frames()
    monkeypatch.setattr(dashboard, "get_df", lambda: movimento)
    monkeypatch.setattr(dashboard, "get_df_perfil_estabelecimento", lambda: perfil)
    monkeypatch.setattr(dashboard, "build_perfil_filtrado", lambda frame, **_kwargs: frame)
    calls = []
    monkeypatch.setattr(
        dashboard, "get_dispersao_uf_sem_fronteira_id_cnpjs_df",
        lambda start, end, threshold: (calls.append(threshold), pl.DataFrame({"id_cnpj": [1]}))[1],
    )

    result = dashboard.get_producao_semestral_data(
        db=None, uf="SP", regiao_id=10, id_ibge7=3550308, cnpjs=["11111111000101"],
        filtros=FiltrosFarmacia(
            situacao_rf="ATIVA", conexao_ms="Ativa", porte_empresa="ME", grande_rede="Nao",
            unidade_pf="Matriz", cnpj_raiz="11111111000101", val_min=15,
            dispersao_uf_sem_fronteira=True, dispersao_uf_sem_fronteira_limite=0.1,
        ),
    )

    assert [point.semestre for point in result.pontos] == ["2020-S1"]
    assert calls == [0.1]

    root_result = dashboard.get_producao_semestral_data(
        db=None,
        data_inicio=date(2020, 1, 1),
        data_fim=date(2020, 12, 31),
        filtros=FiltrosFarmacia(cnpj_raiz="11111111"),
    )
    assert [point.semestre for point in root_result.pontos] == ["2020-S1"]
    assert calls == [0.1]


def test_network_lookup_returns_sorted_rows_and_empty_on_dependency_failure(monkeypatch):
    network = pl.DataFrame(
        {
            "cnpj_raiz": ["12345678", "12345678"], "cnpj": ["12345678000190", "12345678000108"],
            "razao_social": ["Filial", "Matriz"], "uf": ["SC", "SC"],
            "municipio": ["A", "B"], "is_matriz": [False, True],
        }
    )
    monkeypatch.setattr(dashboard, "get_rede_df", lambda: network)

    result = dashboard.get_rede_por_cnpj_raiz("12345678")

    assert [item.is_matriz for item in result] == [True, False]
    monkeypatch.setattr(dashboard, "get_rede_df", lambda: (_ for _ in ()).throw(RuntimeError("cache offline")))
    assert dashboard.get_rede_por_cnpj_raiz("12345678") == []
