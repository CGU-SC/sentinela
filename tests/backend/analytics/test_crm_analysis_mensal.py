from collections import OrderedDict
from datetime import date

import polars as pl
import pytest
from fastapi import HTTPException

from backend.api.services.analytics import crm_analysis_mensal as mensal
from backend.api.services.analytics.crm_filtros_medico import FiltrosMedico
from backend.api.services.analytics.filtros_farmacia import FiltrosFarmacia


def _monthly_rows():
    return pl.DataFrame(
        {
            "id_medico": ["M1", "M2"], "competencia": [202401, 202401],
            "nu_prescricoes": [20, 10], "qtd_dias_com_prescricao": [10, 10],
        }
    )


def _doctor_cache():
    return pl.DataFrame(
        {
            "id_medico": ["M1", "M2"], "nu_crm": [123, None],
            "sg_uf": ["SP", None], "no_medico": ["Ana", "Medico nao localizado"],
        }
    )


class _ImmediateCache:
    def obter(self, _key, calculate):
        return calculate()


def _install_monthly(monkeypatch, *, rows=None, ids=None, doctors=None, pharmacy_filter=False):
    base = mensal.base
    monkeypatch.setattr(base, "_period_bounds", lambda start, end: (date(2024, 1, 1), date(2024, 1, 31)))
    monkeypatch.setattr(base, "montar_filtros_farmacia", lambda _: (pharmacy_filter, {"situacao_rf": "Ativa"} if pharmacy_filter else {}))
    monkeypatch.setattr(base, "escopo_territorial", lambda *args: ("brasil", None))
    monkeypatch.setattr(base, "_scope_label", lambda **kwargs: "Brasil")
    monkeypatch.setattr(base, "_normalizar_busca_medico", lambda query: query.strip().lower())
    monkeypatch.setattr(base, "ids_busca_medico", lambda query: ids)
    monkeypatch.setattr(base, "_limiares_do_periodo", lambda *_: pl.DataFrame({"competencia": [202401], "p95_taxa_dia": [1.5]}))
    monkeypatch.setattr(mensal, "_meses_brutos", lambda *args: (rows if rows is not None else _monthly_rows()).lazy())
    monkeypatch.setattr(mensal, "get_dados_medico_df", lambda: doctors if doctors is not None else _doctor_cache())
    monkeypatch.setattr(mensal.filtrado, "_CACHE", _ImmediateCache())
    monkeypatch.setattr(mensal.filtrado, "_chave_filtros", lambda filters: tuple(sorted(filters.items())))
    monkeypatch.setattr(mensal.filtrado, "ids_medicos_filtrados", lambda **kwargs: pl.Series("id_medico", ["M1"]))
    monkeypatch.setattr(mensal, "get_cache_generation", lambda: 1)
    monkeypatch.setattr(mensal, "_SELECIONADAS", OrderedDict())


def test_selected_rows_cache_uses_generation_lru_and_row_limit(monkeypatch):
    generation = [1]
    monkeypatch.setattr(mensal, "get_cache_generation", lambda: generation[0])
    monkeypatch.setattr(mensal, "_SELECIONADAS", OrderedDict())
    monkeypatch.setattr(mensal, "_SELECIONADAS_MAX_ITENS", 2)
    monkeypatch.setattr(mensal, "_SELECIONADAS_MAX_LINHAS", 2)
    frame = pl.DataFrame({"x": [1]})
    calls = []

    def reader():
        calls.append("read")
        return frame

    assert mensal._linhas_selecionadas(("a",), reader).equals(frame)
    mensal._linhas_selecionadas(("a",), reader)
    mensal._linhas_selecionadas(("b",), reader)
    mensal._linhas_selecionadas(("c",), reader)
    assert len(calls) == 3 and len(mensal._SELECIONADAS) == 2
    mensal._linhas_selecionadas(("a",), reader)
    assert len(calls) == 4

    generation[0] = 2
    mensal._linhas_selecionadas(("d",), reader)
    assert all(key[0] == 2 for key in mensal._SELECIONADAS)

    monkeypatch.setattr(mensal, "_SELECIONADAS_MAX_LINHAS", 0)
    mensal._linhas_selecionadas(("too-large",), lambda: frame)
    assert not any(key[-1] == "too-large" for key in mensal._SELECIONADAS)


def test_month_scan_validates_source_and_applies_territory_and_period(monkeypatch):
    base = mensal.base
    frame = pl.DataFrame(
        {
            "nivel": ["uf", "regiao_saude"], "id_geografico": ["SP", "7"],
            "id_medico": ["M1", "M2"], "competencia": [202401, 202312],
            "nu_prescricoes_mes": [20, 30], "qtd_dias_com_prescricao_mes": [10, 12],
        }
    )
    monkeypatch.setattr(base, "escopo_territorial", lambda *args: ("uf", "SP"))
    monkeypatch.setattr(mensal, "scan_crm_medico_territorio_mes", lambda: frame.lazy())
    result = mensal._meses_brutos(date(2024, 1, 1), date(2024, 1, 31), "SP", None, None).collect()
    assert result.to_dicts() == [{"id_medico": "M1", "competencia": 202401, "nu_prescricoes": 20, "qtd_dias_com_prescricao": 10}]

    monkeypatch.setattr(base, "escopo_territorial", lambda *args: ("brasil", None))
    national = pl.DataFrame(
        {
            "id_medico": ["M1", "M2"], "competencia": [202401, 202401],
            "nu_prescricoes_mes": [20, 10], "qtd_dias_com_prescricao_mes": [10, 10],
        }
    )
    monkeypatch.setattr(mensal, "scan_crm_medico_brasil_mes", lambda: national.lazy())
    assert mensal._meses_brutos(date(2024, 1, 1), date(2024, 1, 31), None, None, None).collect().height == 2

    monkeypatch.setattr(base, "escopo_territorial", lambda *args: ("uf", "SP"))
    monkeypatch.setattr(mensal, "scan_crm_medico_territorio_mes", lambda: pl.DataFrame({"id_medico": ["M1"]}).lazy())
    with pytest.raises(HTTPException, match="sem colunas obrigatorias"):
        mensal._meses_brutos(date(2024, 1, 1), date(2024, 1, 31), "SP", None, None)
    monkeypatch.setattr(mensal, "scan_crm_medico_territorio_mes", lambda: (_ for _ in ()).throw(ValueError("offline")))
    with pytest.raises(HTTPException, match="indisponivel: offline"):
        mensal._meses_brutos(date(2024, 1, 1), date(2024, 1, 31), "SP", None, None)
    monkeypatch.setattr(
        mensal,
        "scan_crm_medico_territorio_mes",
        lambda: (_ for _ in ()).throw(HTTPException(status_code=503, detail="upstream contract error")),
    )
    with pytest.raises(HTTPException, match="upstream contract error"):
        mensal._meses_brutos(date(2024, 1, 1), date(2024, 1, 31), "SP", None, None)


def test_monthly_rate_calculation_joins_p95_and_marks_high_rates():
    rows = _monthly_rows().lazy()
    calculated = mensal._com_taxa(
        rows, pl.DataFrame({"competencia": [202401], "p95_taxa_dia": [1.5]})
    ).collect().sort("id_medico")
    assert calculated.get_column("taxa_prescricoes_dia").to_list() == [2.0, 1.0]
    assert calculated.get_column("taxa_elevada").to_list() == [True, False]
    assert calculated.get_column("razao_p95").to_list() == [pytest.approx(2 / 1.5), pytest.approx(1 / 1.5)]


def test_monthly_view_returns_sorted_rows_and_handles_search_and_empty_page(monkeypatch):
    _install_monthly(monkeypatch, doctors=_doctor_cache().head(1))
    result = mensal.get_crm_prescricoes_mensal(page=1, page_size=10)
    assert result.qtd_linhas == 2 and result.escopo == "Brasil"
    assert [row.id_medico for row in result.linhas] == ["M1", "M2"]
    assert result.linhas[0].taxa_elevada is True
    assert result.linhas[1].localizado_cfm is False

    _install_monthly(monkeypatch, ids=pl.Series("id_medico", ["M2"]))
    searched = mensal.get_crm_prescricoes_mensal(medico_query="Bia")
    assert [row.id_medico for row in searched.linhas] == ["M2"]

    _install_monthly(monkeypatch)
    empty = mensal.get_crm_prescricoes_mensal(page=9, page_size=1)
    assert empty.qtd_linhas == 2 and empty.linhas == []


def test_monthly_view_applies_selection_filters_and_validates_requests(monkeypatch):
    _install_monthly(monkeypatch, ids=pl.Series("id_medico", ["M1"]), pharmacy_filter=True)
    filters = FiltrosMedico(situacao_cfm="localizado", taxa_dia_min=1.5)
    pharmacies = FiltrosFarmacia(situacao_rf="Ativa")
    result = mensal.get_crm_prescricoes_mensal(filtros_medico=filters, filtros_farmacia=pharmacies)
    assert result.qtd_linhas == 1
    assert result.filtro_farmacias_ativo is True and result.filtro_medicos_ativo is True

    _install_monthly(monkeypatch)
    invalid_calls = (
        ({"page": 0}, "page deve ser"),
        ({"page_size": 101}, "page_size deve estar"),
        ({"sort_field": "unknown"}, "Coluna de ordenacao invalida"),
        ({"sort_order": "sideways"}, "sort_order deve ser"),
    )
    for kwargs, message in invalid_calls:
        with pytest.raises(HTTPException, match=message):
            mensal.get_crm_prescricoes_mensal(**kwargs)


def test_monthly_view_restricts_to_pinned_doctors_on_top_of_other_filters(monkeypatch):
    _install_monthly(monkeypatch)
    pinned = mensal.get_crm_prescricoes_mensal(ids_fixados="M2")
    assert pinned.qtd_linhas == 1 and [row.id_medico for row in pinned.linhas] == ["M2"]

    # A busca devolve so M1: o fixado M2 fica fora do recorte.
    _install_monthly(monkeypatch, ids=pl.Series("id_medico", ["M1"]))
    outside = mensal.get_crm_prescricoes_mensal(medico_query="ana", ids_fixados="M2")
    assert outside.qtd_linhas == 0 and outside.linhas == []

    _install_monthly(monkeypatch)
    invalid_lists = (("", "ao menos um id_medico"), ("M1,,M2", "ao menos um id_medico"), ("M1,M1", "repetido"))
    for value, message in invalid_lists:
        with pytest.raises(HTTPException, match=message):
            mensal.get_crm_prescricoes_mensal(ids_fixados=value)
    too_many = ",".join(f"M{i}" for i in range(mensal.base.MEDICOS_FIXADOS_MAX + 1))
    with pytest.raises(HTTPException, match="No maximo"):
        mensal.get_crm_prescricoes_mensal(ids_fixados=too_many)


def test_monthly_view_reports_missing_or_unavailable_doctor_catalog(monkeypatch):
    _install_monthly(monkeypatch, doctors=pl.DataFrame({"id_medico": ["M1"]}))
    with pytest.raises(HTTPException, match="Dados dos medicos sem colunas obrigatorias"):
        mensal.get_crm_prescricoes_mensal()

    _install_monthly(monkeypatch)
    monkeypatch.setattr(mensal, "get_dados_medico_df", lambda: (_ for _ in ()).throw(RuntimeError("offline")))
    with pytest.raises(HTTPException, match="Cache de dados dos medicos indisponivel: offline"):
        mensal.get_crm_prescricoes_mensal()


def test_monthly_series_validates_ids_and_returns_ordered_medic_and_p95_series(monkeypatch):
    _install_monthly(monkeypatch)
    response = mensal.get_crm_prescricoes_serie_mensal(ids="M1, M2")
    assert response.escopo == "Brasil"
    assert [item.id_medico for item in response.medicos] == ["M1", "M2"]
    assert response.meses[0].p95_taxa_dia == 1.5

    for ids, message in (
        (" , ", "Informe ao menos um"),
        (("M," * (mensal.SERIE_MENSAL_MAX_MEDICOS + 1)), "No maximo"),
        ("M1,M1", "repetido"),
    ):
        with pytest.raises(HTTPException, match=message):
            mensal.get_crm_prescricoes_serie_mensal(ids=ids)

    with pytest.raises(HTTPException, match="sem meses com prescricao"):
        mensal.get_crm_prescricoes_serie_mensal(ids="M1,M3")


def test_monthly_series_rejects_duplicate_cache_rows(monkeypatch):
    duplicated = pl.concat([_monthly_rows(), _monthly_rows().head(1)])
    _install_monthly(monkeypatch, rows=duplicated)
    with pytest.raises(HTTPException, match="meses duplicados"):
        mensal.get_crm_prescricoes_serie_mensal(ids="M1,M2")
