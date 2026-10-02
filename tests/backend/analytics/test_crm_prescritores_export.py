import csv
import io
import zipfile
from datetime import date
from types import SimpleNamespace
from xml.etree import ElementTree

import pytest
from fastapi import HTTPException

from api.services.analytics import crm_prescritores_export as export_module
from api.services.analytics.crm_export import _Farmacia


CNPJ = "12345678000190"


def _crm(id_medico="CRM-123-SP", ranking=1, **overrides):
    medico = {
        "id_medico": id_medico,
        "no_medico": "MEDICO UM",
        "dt_inscricao_crm": date(2000, 1, 2),
        "ranking": ranking,
        "nu_prescricoes": 20,
        "vl_total_prescricoes": 600.0,
        "nu_prescricoes_dia": 10.0,
        "prescricoes_dia_total_brasil": 12.0,
        "pct_participacao": 25.0,
        "pct_acumulado": 25.0,
        "pct_volume_aqui_vs_total": 75.0,
        "nu_estabelecimentos": 3,
        "competencia_inicio_atuacao": 202401,
        "competencia_fim_atuacao": 202402,
        "qtd_meses_atuacao": 2,
        "serie_mensal_atuacao": [
            {"competencia": 202401, "qtd": 10, "qtd_brasil": 20, "valor": 300.0},
            {"competencia": 202402, "qtd": 15, "qtd_brasil": 30, "valor": 300.0},
        ],
        "flag_crm_invalido": False,
        "flag_prescricao_antes_registro": False,
        "flag_robo": False,
        "flag_robo_oculto": False,
        "flag_crm_exclusivo": False,
        "alerta_concentracao_unico_crm": False,
        "alerta_concentracao_multiplos_crms": False,
        "alerta5_geografico": False,
        "qtd_alertas_crm_unico": 0,
        "qtd_alertas_crm_multiplos": 0,
        "qtd_alertas_geograficos": 0,
    }
    medico.update(overrides)
    return medico


def _response(crms=None, summary=None):
    return SimpleNamespace(
        crms_interesse=[_crm()] if crms is None else crms,
        summary={
            "competencia_inicio_periodo": 202401,
            "competencia_fim_periodo": 202402,
            "serie_mensal_farmacia": [
                {"competencia": 202401, "qtd": 40},
                {"competencia": 202402, "qtd": 50},
            ],
        } if summary is None else summary,
    )


@pytest.fixture
def setup_export(monkeypatch):
    response = _response()
    calls = []

    def get_crm_data(cnpj, **kwargs):
        calls.append((cnpj, kwargs))
        return response

    monkeypatch.setattr(export_module, "get_crm_data", get_crm_data)
    monkeypatch.setattr(
        export_module,
        "_load_farmacia",
        lambda cnpj: _Farmacia("Farmacia Alvo", "Sao Paulo", "SP"),
    )
    return response, calls


def test_competencia_date_and_month_end_boundaries():
    assert export_module._comp_para_data(202402) == date(2024, 2, 1)
    assert export_module._fim_do_mes(202402) == date(2024, 2, 29)
    assert export_module._fim_do_mes(202412) == date(2024, 12, 31)


def test_alert_labels_include_all_flags_and_counts():
    medico = _crm(
        flag_crm_invalido=True,
        flag_prescricao_antes_registro=True,
        flag_robo=True,
        flag_robo_oculto=True,
        alerta_concentracao_unico_crm=True,
        qtd_alertas_crm_unico=3,
        alerta_concentracao_multiplos_crms=True,
        qtd_alertas_crm_multiplos=4,
        alerta5_geografico=True,
        qtd_alertas_geograficos=5,
        flag_crm_exclusivo=True,
    )
    alertas = export_module._alertas(medico)
    assert [item[0] for item in alertas] == [
        "crm_invalido", "crm_irregular", "taxa_local", "seq_unico",
        "seq_multiplos", "distancia", "exclusivo",
    ]
    texto = export_module._texto_alertas(medico)
    assert "CRM não localizado" in texto
    assert "Autorizações em sequência · único CRM (3×)" in texto
    assert "Autorizações em sequência · múltiplos CRMs (4×)" in texto
    assert "Distância > 400 km (5×)" in texto
    assert "taxa_brasil" not in texto


def test_hidden_national_rate_alert_only_appears_without_local_rate():
    medico = _crm(flag_robo_oculto=True)
    assert [item[0] for item in export_module._alertas(medico)] == ["taxa_brasil"]
    limite = export_module.CRM_DAILY_RATE_ALERT_THRESHOLD
    assert export_module._texto_alertas(medico) == f"Mais de {limite} presc./dia (Brasil)"


def test_prepare_normalizes_and_sorts_crms_and_derives_full_month_period(setup_export):
    response, calls = setup_export
    response.crms_interesse = [_crm("2", 2), _crm("1", 1)]
    export = export_module._preparar(f"{CNPJ[:2]}.{CNPJ[2:5]}.{CNPJ[5:8]}/{CNPJ[8:12]}-{CNPJ[12:]}", None, None, None, None)
    assert export.cnpj == CNPJ
    assert [row["id_medico"] for row in export.crms] == ["1", "2"]
    assert export.inicio == "2024-01-01"
    assert export.fim == "2024-02-29"
    assert export.serie_farmacia == {202401: 40, 202402: 50}
    assert export.filtro is None
    assert export.total_crms_farmacia == 2
    assert calls == [(CNPJ, {"data_inicio": None, "data_fim": None})]


@pytest.mark.parametrize(
    ("cnpj", "inicio", "fim", "ids", "filtro", "status", "mensagem"),
    [
        ("123", None, None, None, None, 422, "CNPJ inválido"),
        (CNPJ, date(2024, 2, 1), date(2024, 1, 1), None, None, 422, "início do período"),
        (CNPJ, None, None, [], "Filtro", 422, "Nenhum CRM selecionado"),
        (CNPJ, None, None, ["1"], "   ", 422, "sem a descrição do filtro"),
    ],
)
def test_prepare_rejects_invalid_export_requests(setup_export, cnpj, inicio, fim, ids, filtro, status, mensagem):
    with pytest.raises(HTTPException, match=mensagem) as error:
        export_module._preparar(cnpj, inicio, fim, ids, filtro)
    assert error.value.status_code == status


def test_prepare_rejects_missing_crms_and_incomplete_required_contract(setup_export):
    response, _ = setup_export
    response.crms_interesse = []
    with pytest.raises(HTTPException, match="Não há CRMs") as error:
        export_module._preparar(CNPJ, None, None, None, None)
    assert error.value.status_code == 404

    response.crms_interesse = [{"ranking": 1}]
    with pytest.raises(HTTPException, match="campos obrigatórios") as error:
        export_module._preparar(CNPJ, None, None, None, None)
    assert error.value.status_code == 500
    assert "id_medico" in error.value.detail


@pytest.mark.parametrize(
    "summary",
    [
        {"competencia_inicio_periodo": None, "competencia_fim_periodo": 202402, "serie_mensal_farmacia": []},
        {"competencia_inicio_periodo": 202401, "competencia_fim_periodo": None, "serie_mensal_farmacia": []},
        {"competencia_inicio_periodo": 202401, "competencia_fim_periodo": 202402, "serie_mensal_farmacia": None},
    ],
)
def test_prepare_rejects_missing_monthly_summary_contract(setup_export, summary):
    response, _ = setup_export
    response.summary = summary
    with pytest.raises(HTTPException, match="Resumo CRM sem período") as error:
        export_module._preparar(CNPJ, None, None, None, None)
    assert error.value.status_code == 500


def test_prepare_applies_explicit_dates_and_valid_crm_filter(setup_export):
    response, calls = setup_export
    response.crms_interesse = [_crm("1", 1), _crm("2", 2)]
    export = export_module._preparar(
        CNPJ, date(2023, 8, 10), date(2024, 1, 20), ["2"], "  CRM de interesse  "
    )
    assert export.inicio == "2023-08-10"
    assert export.fim == "2024-01-20"
    assert [row["id_medico"] for row in export.crms] == ["2"]
    assert export.filtro == "CRM de interesse"
    assert export.total_crms_farmacia == 2
    assert calls == [(CNPJ, {"data_inicio": "2023-08-10", "data_fim": "2024-01-20"})]


def test_prepare_reports_unknown_crm_ids_with_bounded_message(setup_export):
    response, _ = setup_export
    response.crms_interesse = [_crm("known", 1)]
    unknown = [f"missing-{i}" for i in range(8)]
    with pytest.raises(HTTPException) as error:
        export_module._preparar(CNPJ, None, None, unknown, "Filtro")
    assert error.value.status_code == 422
    assert error.value.detail.endswith(", ".join(unknown[:5]) + ".")
    assert "missing-5" not in error.value.detail


@pytest.mark.parametrize(
    ("valor", "esperado"),
    [(None, None), ("", None), (date(2001, 2, 3), date(2001, 2, 3)), ("2001-02-03T12:00:00", date(2001, 2, 3))],
)
def test_inscription_date_normalization(valor, esperado):
    assert export_module._data_inscricao({"dt_inscricao_crm": valor}) == esperado


def test_line_maps_alerts_and_metrics_to_export_columns():
    medico = _crm(
        no_medico=None,
        dt_inscricao_crm="2000-01-02T00:00:00",
        flag_crm_invalido=True,
        flag_prescricao_antes_registro=True,
        flag_robo=True,
        alerta_concentracao_unico_crm=True,
        qtd_alertas_crm_unico=2,
        alerta5_geografico=True,
        qtd_alertas_geograficos=1,
    )
    linha = export_module._linha(medico)
    assert len(linha) == len(export_module._colunas()) == 24
    assert linha[2] == export_module._CRM_NAO_LOCALIZADO
    assert linha[3] == date(2000, 1, 2)
    assert "CRM não localizado" in linha[4]
    assert linha[5:9] == ["Sim", "Sim", "Sim", ""]
    assert linha[9:12] == [2, 0, 1]
    assert linha[12] == ""
    assert linha[13:15] == [date(2024, 1, 1), date(2024, 2, 1)]
    assert linha[20:23] == [0.25, 0.25, 0.75]


@pytest.mark.parametrize(
    ("valor", "formato", "esperado"),
    [
        (None, "texto", ""),
        (date(2024, 1, 5), "data", "05/01/2024"),
        (date(2024, 1, 5), "mes", "01/2024"),
        (0.125, "pct", "12,5"),
        (12.34567, "decimal", "12,3457"),
        (12, "inteiro", "12"),
        ("=SUM(A1:A2)", "texto", "'=SUM(A1:A2)"),
    ],
)
def test_csv_value_formats_pt_br_and_safe_text(valor, formato, esperado):
    assert export_module._csv_valor(valor, formato) == esperado


def test_csv_export_serializes_headers_alerts_percentages_and_safe_text(setup_export):
    response, _ = setup_export
    response.crms_interesse = [_crm(no_medico="=1+1", flag_robo=True)]
    filename, chunks = export_module.export_crm_perfil_csv(CNPJ)
    payload = b"".join(chunks)
    assert filename == "crm_perfil_12345678000190_202401-202402.csv"
    assert payload.startswith(b"\xef\xbb\xbf")
    rows = list(csv.reader(io.StringIO(payload.decode("utf-8-sig"), newline=""), delimiter=";"))
    assert rows[0][0:4] == ["CNPJ", "Posição", "CRM/UF", "Nome do médico"]
    assert rows[1][0] == "12.345.678/0001-90"
    assert rows[1][3] == "'=1+1"
    assert rows[1][4] == "02/01/2000"
    assert rows[1][8] == "Sim"
    assert rows[1][21] == "25"


def _shared_strings(content):
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        root = ElementTree.fromstring(archive.read("xl/sharedStrings.xml"))
    ns = {"x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    return ["".join(item.itertext()) for item in root.findall("x:si", ns)]


def test_xlsx_export_builds_crm_monthly_and_criteria_worksheets(setup_export):
    response, _ = setup_export
    response.crms_interesse = [_crm(no_medico="=2+2", flag_crm_exclusivo=True)]
    filename, content = export_module.export_crm_perfil_xlsx(CNPJ)
    assert filename == "crm_perfil_12345678000190_202401-202402.xlsx"
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        root = ElementTree.fromstring(archive.read("xl/workbook.xml"))
    ns = {"x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    assert [s.attrib["name"] for s in root.findall("x:sheets/x:sheet", ns)] == [
        "CRMs", "Atuação mensal", "Critérios"
    ]
    assert "=2+2" in _shared_strings(content)


def test_xlsx_export_shows_filter_summary_and_rejects_inconsistent_month_series(monkeypatch, setup_export):
    response, _ = setup_export
    _, filtered = export_module.export_crm_perfil_xlsx(CNPJ, ids=["CRM-123-SP"], filtro="Selecionado")
    texts = " ".join(_shared_strings(filtered))
    assert "Filtro aplicado na tela: Selecionado" in texts
    assert "1 de 1 CRMs" in texts

    response.crms_interesse = [_crm(serie_mensal_atuacao=[
        {"competencia": 202401, "qtd": 10, "qtd_brasil": 20, "valor": 300.0}
    ])]
    response.summary["serie_mensal_farmacia"] = [{"competencia": 202401, "qtd": 0}]
    with pytest.raises(HTTPException, match="Série mensal inconsistente") as error:
        export_module.export_crm_perfil_xlsx(CNPJ)
    assert error.value.status_code == 500
