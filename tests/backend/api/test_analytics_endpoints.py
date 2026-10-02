import inspect
import json
from datetime import date, datetime

import pytest
from fastapi import HTTPException
from fastapi.params import Depends, Query
from fastapi.responses import Response, StreamingResponse
from pydantic_core import PydanticUndefined

from api.endpoints import analytics as endpoints
from api.schemas.analytics import CrmPerfilExportRequest, ListaInteresseExportRequest
from api.services.analytics.crm_filtros_medico import FiltrosMedico
from api.services.analytics.filtros_farmacia import FiltrosFarmacia


_CNPJ = "12345678000190"


def _invoke(name, **overrides):
    """Call an endpoint directly with HTTP-resolved defaults and explicit required inputs."""
    function = getattr(endpoints, name)
    values = {}
    for parameter in inspect.signature(function).parameters.values():
        if parameter.name in overrides:
            values[parameter.name] = overrides[parameter.name]
            continue
        default = parameter.default
        if isinstance(default, Query):
            value = default.default
            if value is PydanticUndefined:
                raise AssertionError(f"Required endpoint argument was not supplied: {parameter.name}")
            values[parameter.name] = value
        elif isinstance(default, Depends):
            if parameter.name == "filtros":
                values[parameter.name] = FiltrosFarmacia()
            elif parameter.name == "filtros_medico":
                values[parameter.name] = FiltrosMedico()
            else:
                values[parameter.name] = None
        elif default is inspect.Parameter.empty:
            raise AssertionError(f"Required endpoint argument was not supplied: {parameter.name}")
        else:
            values[parameter.name] = default
    return function(**values)


@pytest.mark.parametrize(
    ("endpoint", "service", "required"),
    [
        ("get_crm_prescricoes_analise", "get_crm_prescricoes_analise", {}),
        ("get_crm_prescricoes_mensal", "get_crm_prescricoes_mensal", {}),
        ("get_crm_prescricoes_serie_mensal", "get_crm_prescricoes_serie_mensal", {"ids": "1/SP"}),
        ("get_crm_prescricoes_alertas", "get_crm_medicos_alertas", {"ids": "1/SP"}),
        ("get_crm_medico_evidencias", "get_crm_medico_evidencias", {"id_medico": "1/SP", "tipo": "unico"}),
        ("get_crm_evidencia_autorizacoes", "get_crm_evidencia_autorizacoes", {
            "id_cnpj": 1, "id_medico": "1/SP", "inicio": datetime(2024, 1, 1), "fim": datetime(2024, 1, 1, 1),
        }),
        ("get_crm_medico_historico", "get_crm_medico_historico", {"id_medico": "1/SP"}),
        ("get_cnpj_bootstrap", "get_cnpj_bootstrap", {"cnpj": _CNPJ}),
        ("get_dados_farmacia", "get_dados_farmacia", {"cnpj": _CNPJ}),
        ("get_socios_farmacia", "get_socios_farmacia", {"cnpj": _CNPJ}),
        ("get_alertas_panorama", "get_alertas_panorama", {}),
        ("get_integrity_alerts", "get_integrity_alerts", {"cnpj": _CNPJ}),
        ("get_teia_grafo_nivel2", "get_teia_grafo_nivel2", {"cnpj": _CNPJ}),
        ("get_teia_batch_level3", "get_teia_grafo_nivel3_full", {"cnpj": _CNPJ}),
        ("get_teia_batch_level4", "get_teia_grafo_nivel4_full", {"cnpj": _CNPJ}),
        ("get_analytics_summary", "get_dashboard_data", {"secoes": ["kpis"], "db": object()}),
        ("get_producao_semestral", "get_producao_semestral_data", {"db": object()}),
        ("get_resultado_faixas_risco", "get_fator_risco_data", {"db": object()}),
        ("get_evolucao_financeira", "get_evolucao_financeira", {"cnpj": _CNPJ}),
        ("get_evolucao_mensal_gtin", "get_evolucao_mensal_gtin", {"cnpj": _CNPJ}),
        ("get_cnpj_repasses", "get_cnpj_repasses", {"cnpj": _CNPJ}),
        ("get_gtin_ranking", "get_gtin_ranking_periodo", {"cnpj": _CNPJ, "periodo": "2024-S1"}),
        ("get_indicadores", "get_indicadores", {"cnpj": _CNPJ}),
        ("get_indicador_benchmark_local", "get_indicador_benchmark_local", {"cnpj": _CNPJ, "indicador": "teto"}),
        ("get_indicador_evolucao_benchmark", "get_indicador_evolucao_benchmark", {"cnpj": _CNPJ, "indicador": "teto"}),
        ("get_geografico_origem_uf", "get_geografico_origem_uf", {"cnpj": _CNPJ}),
        ("get_geografico_benchmark_local", "get_geografico_benchmark_local", {"cnpj": _CNPJ}),
        ("get_incompatibilidade_patologica", "get_incompatibilidade_patologica_data", {"cnpj": _CNPJ}),
        ("get_falecidos", "get_falecidos_data", {"cnpj": _CNPJ}),
        ("get_rede_estabelecimentos", "get_rede_por_cnpj_raiz", {"cnpj_raiz": "12.345.678/"}),
        ("get_cpf_timeline", "get_timeline_cpf", {"cpf": "123", "cnpj": _CNPJ}),
        ("get_regional_benchmarking_animation", "get_regional_benchmarking_animation", {}),
        ("get_crm_data_endpoint", "get_crm_data", {"cnpj": _CNPJ}),
        ("get_crm_medico_atuacao", "get_crm_medico_atuacao", {"cnpj": _CNPJ, "id_medico": "1/SP"}),
        ("get_crm_timeline_dataset", "get_crm_timeline_dataset", {"cnpj": _CNPJ}),
        ("get_crm_raio_x", "get_crm_raio_x", {"cnpj": _CNPJ, "date_str": "2024-01-01"}),
        ("get_indicadores_analise_cnpjs", "get_indicadores_analise_cnpjs", {"indicador": "teto"}),
        ("get_movimentacao", "get_movimentacao_data", {"cnpj": _CNPJ}),
        ("get_cnpj_lookup", "get_cnpj_lookup", {}),
        ("get_metric_percentiles_animation", "get_metric_percentiles_animation", {"scope": "brasil"}),
        ("get_metric_percentiles", "get_metric_percentiles", {"scope": "brasil"}),
        ("get_nota_tecnica_regionais", "list_nota_tecnica_regionais", {}),
    ],
)
def test_analytics_endpoint_delegates_to_service(monkeypatch, endpoint, service, required):
    sentinel = object()
    calls = []

    def delegate(*args, **kwargs):
        calls.append((args, kwargs))
        return sentinel

    monkeypatch.setattr(endpoints.AnalyticsService, service, delegate)
    assert _invoke(endpoint, **required) is sentinel
    assert len(calls) == 1


@pytest.mark.parametrize("endpoint", ["get_analytics_summary", "get_producao_semestral", "get_resultado_faixas_risco"])
@pytest.mark.parametrize(
    ("scope_field", "value", "message"),
    [("regiao_saude", "Nordeste", "Use regiao_id"), ("municipio", "Recife", "Use id_ibge7")],
)
def test_summary_endpoints_reject_display_labels_as_filter_ids(endpoint, scope_field, value, message):
    with pytest.raises(HTTPException, match=message) as error:
        _invoke(endpoint, **{scope_field: value, **({"secoes": ["kpis"]} if endpoint == "get_analytics_summary" else {})})
    assert error.value.status_code == 400


@pytest.mark.parametrize("endpoint", ["get_indicadores_analise", "get_indicadores_analise_cnpjs"])
@pytest.mark.parametrize(
    ("scope_field", "value", "message"),
    [("regiao_saude", "Nordeste", "Use regiao_id"), ("municipio", "Recife", "Use id_ibge7")],
)
def test_indicator_endpoints_reject_display_labels_as_filter_ids(endpoint, scope_field, value, message, monkeypatch):
    monkeypatch.setattr(endpoints.AnalyticsService, "get_indicadores_analise", lambda *a, **k: pytest.fail("service não deveria ser chamado"))
    monkeypatch.setattr(endpoints.AnalyticsService, "get_indicadores_analise_cnpjs", lambda *a, **k: pytest.fail("service não deveria ser chamado"))
    with pytest.raises(HTTPException, match=message) as error:
        _invoke(endpoint, indicador="teto", **{scope_field: value})
    assert error.value.status_code == 400


def test_indicator_endpoints_delegate_with_id_based_scopes(monkeypatch):
    sentinel = object()
    calls = []

    def delegate(*args, **kwargs):
        calls.append((args, kwargs))
        return sentinel

    monkeypatch.setattr(endpoints.AnalyticsService, "get_indicadores_analise", delegate)
    monkeypatch.setattr(endpoints.AnalyticsService, "get_indicadores_analise_cnpjs", delegate)
    assert _invoke("get_indicadores_analise", indicador="teto", regiao_saude="Todos", municipio="Todos", regiao_id=7, id_ibge7=1234567) is sentinel
    assert _invoke("get_indicadores_analise_cnpjs", indicador="teto", regiao_saude="Todos", municipio="Todos", regiao_id=7, id_ibge7=1234567) is sentinel
    assert len(calls) == 2


def test_crm_filter_dependency_builds_a_typed_filter(monkeypatch):
    expected = object()
    captured = {}

    def build(**kwargs):
        captured.update(kwargs)
        return expected

    monkeypatch.setattr(endpoints, "montar_filtros_medico", build)
    result = endpoints._crm_filtros_medico(
        situacao_cfm="localizado", uf_crm=["SP"], taxa_dia_min=2.5, prescricoes_max=20,
        exclusividade_min=50, farmacias_min=2, municipios_max=3,
        sequencia_severidade_min=2, sequencia_dias_min=1, sequencia_dias_max=5,
    )
    assert result is expected
    assert captured["situacao_cfm"] == "localizado"
    assert captured["uf_crm"] == ["SP"]
    assert captured["prescricoes_max"] == 20


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, None),
        ("  ", None),
        ('[{"nome":" Ana ","cargo":" Auditora "}]', [{"nome": "Ana", "cargo": "Auditora"}]),
        ('[{"nome":" ","cargo":" "}]', []),
    ],
)
def test_technical_signers_parameter_parses_and_normalizes(value, expected):
    assert endpoints._parse_assinantes_tecnicos_param(value) == expected


@pytest.mark.parametrize(
    ("value", "message"),
    [
        ("{", "JSON valido"),
        ('{"nome":"Ana"}', "deve ser uma lista"),
        (json.dumps([{}, {}, {}, {}]), "no maximo 3"),
        ("[1]", "Cada assinatura tecnica deve ser um objeto"),
        ('[{"nome":"Ana"}]', "conter nome e cargo"),
        ('[{"cargo":"Auditora"}]', "conter nome e cargo"),
    ],
)
def test_technical_signers_parameter_rejects_invalid_inputs(value, message):
    with pytest.raises(HTTPException, match=message) as error:
        endpoints._parse_assinantes_tecnicos_param(value)
    assert error.value.status_code == 422


def test_client_performance_event_is_forwarded(monkeypatch):
    event = object()
    monkeypatch.setattr(endpoints, "log_frontend_performance", lambda received: ("logged", received))
    assert endpoints.log_client_performance(event) == ("logged", event)


@pytest.mark.parametrize(
    ("endpoint", "service", "error_type"),
    [
        ("get_nota_tecnica_readiness", "get_nota_tecnica_readiness", ValueError),
        ("get_relatorio_pdf_readiness", "get_relatorio_pdf_readiness", ValueError),
        ("prepare_nota_tecnica", "prepare_nota_tecnica_cnpj", ValueError),
        ("prepare_nota_tecnica", "prepare_nota_tecnica_cnpj", RuntimeError),
        ("prepare_relatorio_pdf", "prepare_relatorio_pdf_cnpj", ValueError),
        ("prepare_relatorio_pdf", "prepare_relatorio_pdf_cnpj", RuntimeError),
    ],
)
def test_document_preparation_endpoints_translate_service_errors(monkeypatch, endpoint, service, error_type):
    def fail(*args, **kwargs):
        raise error_type("cache indisponível")

    monkeypatch.setattr(endpoints.AnalyticsService, service, fail)
    with pytest.raises(HTTPException, match="cache indisponível") as error:
        _invoke(endpoint, cnpj=_CNPJ)
    assert error.value.status_code == 422


def test_document_readiness_success_is_returned(monkeypatch):
    readiness = {"ready": True, "missing_modules": []}
    monkeypatch.setattr(endpoints.AnalyticsService, "get_nota_tecnica_readiness", lambda *a: readiness)
    monkeypatch.setattr(endpoints.AnalyticsService, "get_relatorio_pdf_readiness", lambda *a: readiness)
    assert _invoke("get_nota_tecnica_readiness", cnpj=_CNPJ) is readiness
    assert _invoke("get_relatorio_pdf_readiness", cnpj=_CNPJ) is readiness


@pytest.mark.parametrize(
    ("endpoint", "service"),
    [("prepare_nota_tecnica", "prepare_nota_tecnica_cnpj"), ("prepare_relatorio_pdf", "prepare_relatorio_pdf_cnpj")],
)
def test_document_preparation_success_passes_shared_engine(monkeypatch, endpoint, service):
    result = object()
    calls = []

    def prepare(*args):
        calls.append(args)
        return result

    monkeypatch.setattr(endpoints.AnalyticsService, service, prepare)
    assert _invoke(endpoint, cnpj=_CNPJ, data_inicio=date(2024, 1, 1)) is result
    assert calls[0][0] == _CNPJ
    assert calls[0][1] is endpoints.engine
    assert calls[0][2] == date(2024, 1, 1)


def test_falecidos_export_returns_excel_and_streaming_csv_responses(monkeypatch):
    monkeypatch.setattr(endpoints.AnalyticsService, "export_falecidos_xlsx", lambda *a: ("deaths.xlsx", b"xlsx"))
    excel = _invoke("export_falecidos", cnpj=_CNPJ, formato="xlsx", outro_cnpj="999")
    assert isinstance(excel, Response)
    assert excel.body == b"xlsx"
    assert excel.headers["content-disposition"].endswith('deaths.xlsx"')

    monkeypatch.setattr(endpoints.AnalyticsService, "export_falecidos_csv", lambda *a: ("deaths.csv", iter([b"csv"])))
    csv_response = _invoke("export_falecidos", cnpj=_CNPJ, formato="csv")
    assert isinstance(csv_response, StreamingResponse)
    assert csv_response.headers["cache-control"] == "no-store"
    assert csv_response.headers["content-disposition"].endswith('deaths.csv"')


def test_network_expansion_selects_cpf_and_cnpj_handlers(monkeypatch):
    cpf_call = {}
    cnpj_call = {}
    cpf_result, cnpj_result = object(), object()

    def expand_cpf(**kwargs):
        cpf_call.update(kwargs)
        return cpf_result

    def expand_cnpj(**kwargs):
        cnpj_call.update(kwargs)
        return cnpj_result

    monkeypatch.setattr(endpoints.AnalyticsService, "get_teia_grafo_nivel4_expansao", expand_cpf)
    monkeypatch.setattr(endpoints.AnalyticsService, "get_teia_grafo_nivel3_expansao", expand_cnpj)
    assert _invoke("get_teia_network_expansion", cnpj=_CNPJ, target_id="123.456.789-01") is cpf_result
    assert cpf_call["cpf_para_expandir"] == "12345678901"
    assert _invoke("get_teia_network_expansion", cnpj=_CNPJ, target_id="98.765.432/0001-10") is cnpj_result
    assert cnpj_call["cnpj_para_expandir"] == "98765432000110"


def test_other_export_routes_return_expected_response_types(monkeypatch):
    monkeypatch.setattr(endpoints.AnalyticsService, "export_crm_medico_evidencias_xlsx", lambda *a: ("evidence.xlsx", b"e"))
    evidence = _invoke("export_crm_medico_evidencias", id_medico="1/SP")
    assert isinstance(evidence, Response)
    assert evidence.body == b"e"

    monkeypatch.setattr(endpoints.AnalyticsService, "export_crm_raiox_xlsx", lambda *a: ("raiox.xlsx", b"x"))
    raiox_excel = _invoke("export_crm_raio_x", cnpj=_CNPJ, formato="xlsx")
    assert isinstance(raiox_excel, Response)
    assert raiox_excel.headers["cache-control"] == "no-store"
    monkeypatch.setattr(endpoints.AnalyticsService, "export_crm_raiox_csv", lambda *a: ("raiox.csv", iter([b"c"])))
    assert isinstance(_invoke("export_crm_raio_x", cnpj=_CNPJ, formato="csv"), StreamingResponse)

    body = CrmPerfilExportRequest(formato="xlsx", ids=["1/SP"], filtro="seleção")
    monkeypatch.setattr(endpoints.AnalyticsService, "export_crm_perfil_xlsx", lambda *a: ("perfil.xlsx", b"p"))
    perfil_excel = _invoke("export_crm_prescritores", cnpj=_CNPJ, body=body)
    assert isinstance(perfil_excel, Response)
    assert perfil_excel.body == b"p"

    body.formato = "csv"
    monkeypatch.setattr(endpoints.AnalyticsService, "export_crm_perfil_csv", lambda *a: ("perfil.csv", iter([b"p"])))
    perfil_csv = _invoke("export_crm_prescritores", cnpj=_CNPJ, body=body)
    assert isinstance(perfil_csv, StreamingResponse)
    assert perfil_csv.headers["content-disposition"].endswith('perfil.csv"')

    # Farmácias Monitoradas (/listas): mesmo par Excel/CSV, com a sessão do banco repassada.
    lista = ListaInteresseExportRequest(formato="xlsx", data_inicio=date(2024, 1, 1), data_fim=date(2024, 6, 30))
    pedidos = []
    monkeypatch.setattr(endpoints, "export_watchlist_xlsx", lambda *a: pedidos.append(a) or ("lista.xlsx", b"l"))
    lista_excel = _invoke("export_lista_interesse", body=lista, db="sessao")
    assert isinstance(lista_excel, Response) and lista_excel.body == b"l"
    assert pedidos == [("sessao", date(2024, 1, 1), date(2024, 6, 30))]

    lista.formato = "csv"
    monkeypatch.setattr(endpoints, "export_watchlist_csv", lambda *a: ("lista.csv", iter([b"l"])))
    lista_csv = _invoke("export_lista_interesse", body=lista, db="sessao")
    assert isinstance(lista_csv, StreamingResponse)
    assert lista_csv.headers["content-disposition"].endswith('lista.csv"')


def test_note_generation_translates_missing_readiness_to_unprocessable(monkeypatch):
    monkeypatch.setattr(
        endpoints.AnalyticsService,
        "get_nota_tecnica_readiness",
        lambda *a: {"ready": False, "missing_modules": [{"label": "memória de cálculo"}, {"label": "rede"}]},
    )
    with pytest.raises(HTTPException, match="memória de cálculo, rede") as error:
        _invoke("get_nota_tecnica", cnpj=_CNPJ, regional_codigo="SP")
    assert error.value.status_code == 422


def test_note_generation_streams_docx_and_accepts_signers(monkeypatch):
    calls = []
    monkeypatch.setattr(endpoints.AnalyticsService, "get_nota_tecnica_readiness", lambda *a: {"ready": True, "missing_modules": []})

    def generate(*args):
        calls.append(args)
        return iter([b"docx"])

    monkeypatch.setattr(endpoints.AnalyticsService, "generate_nota_tecnica", generate)
    response = _invoke(
        "get_nota_tecnica",
        cnpj=_CNPJ,
        regional_codigo="SP",
        numero_nota="NT-1",
        assinantes_tecnicos='[{"nome":"Ana","cargo":"Auditora"}]',
        db=object(),
    )
    assert isinstance(response, StreamingResponse)
    assert response.media_type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    assert "filename*=UTF-8''Nota_Tecnica_" in response.headers["content-disposition"]
    assert calls[0][0] is not None
    assert calls[0][-1] == [{"nome": "Ana", "cargo": "Auditora"}]


@pytest.mark.parametrize("exception, status", [(ValueError("input"), 422), (RuntimeError("business"), 422), (TypeError("unexpected"), 500)])
def test_note_generation_converts_document_errors_to_http_response(monkeypatch, exception, status):
    monkeypatch.setattr(endpoints.AnalyticsService, "get_nota_tecnica_readiness", lambda *a: {"ready": True, "missing_modules": []})

    def fail(*args):
        raise exception

    monkeypatch.setattr(endpoints.AnalyticsService, "generate_nota_tecnica", fail)
    with pytest.raises(HTTPException) as error:
        _invoke("get_nota_tecnica", cnpj=_CNPJ, regional_codigo="SP", db=None)
    assert error.value.status_code == status
    if status == 500:
        assert "Erro inesperado ao gerar Nota Tecnica" in error.value.detail
