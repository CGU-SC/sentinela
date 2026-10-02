from io import BytesIO
from zipfile import ZipFile

import pytest
from fastapi import HTTPException

from backend.api.services import evidencias_export


def test_evidence_export_formats_each_schedule_type_and_rejects_missing_snapshot_time():
    assert evidencias_export._horario({"id": "dia-1", "tipo": "dia"}) == "Dia todo"
    assert evidencias_export._horario({"id": "hora-1", "tipo": "hora", "hora": 9}) == "09h às 09h59"
    assert evidencias_export._horario(
        {"id": "autorizacao-1", "tipo": "autorizacao", "snapshot": {"horario": "08:00-10:00"}}
    ) == "08:00-10:00"

    with pytest.raises(HTTPException, match="sem horário da autorização"):
        evidencias_export._horario({"id": "autorizacao-2", "tipo": "autorizacao", "snapshot": {}})


def test_evidence_export_renders_sorted_records_and_workbook_metadata(monkeypatch):
    cnpj = "12345678000190"
    records = [
        {
            "id": "auth", "cnpj": cnpj, "tipo": "autorizacao", "dt_janela": "2024-01-02",
            "num_autorizacao": "000123", "nota": "=HYPERLINK(\"https://example.invalid\")",
            "criado_em": "2024-01-02T12:00:00+00:00",
            "snapshot": {"horario": "08:10:00", "crm": "CRM/SP", "medico": "João Médico", "valor": 12.5,
                         "qtd": 4, "alertas": ["Sequência", "Volume"]},
        },
        {
            "id": "hour", "cnpj": cnpj, "tipo": "hora", "dt_janela": "2024-01-01",
            "hora": 9, "nota": "Nota hora", "criado_em": "2024-01-01T12:00:00+00:00",
            "snapshot": {"qtd": 7, "alertas": []},
        },
        {
            "id": "day", "cnpj": cnpj, "tipo": "dia", "dt_janela": "2024-01-01",
            "nota": "Nota dia", "criado_em": "2024-01-01T10:00:00+00:00",
            "snapshot": {"qtd": 10, "alertas": ["Falecidos"]},
        },
    ]
    monkeypatch.setattr(evidencias_export.EvidenciasService, "listar", classmethod(lambda _cls, _cnpj: records))
    monkeypatch.setattr(
        evidencias_export, "_load_farmacia",
        lambda _cnpj: type("Farmacia", (), {"razao_social": "FARMÁCIA CENTRAL", "municipio": "São Paulo", "uf": "sp"})(),
    )

    filename, content = evidencias_export.export_evidencias_xlsx(cnpj)

    assert filename == f"evidencias_{cnpj}.xlsx"
    assert content[:2] == b"PK"
    with ZipFile(BytesIO(content)) as workbook:
        names = workbook.namelist()
        assert "xl/worksheets/sheet1.xml" in names
        shared_strings = workbook.read("xl/sharedStrings.xml").decode("utf-8")
        sheet = workbook.read("xl/worksheets/sheet1.xml").decode("utf-8")
        assert "Cesta de evidências" in shared_strings
        assert "FARMÁCIA CENTRAL" in shared_strings
        assert "Autorização" in shared_strings and "Dia" in shared_strings and "Hora" in shared_strings
        assert "CRM/SP" in shared_strings and "João Médico" in shared_strings
        assert "Sequência, Volume" in shared_strings
        assert "Nota do auditor" in shared_strings and "=HYPERLINK" in shared_strings
        assert sheet.count("<row") >= 12


def test_evidence_export_rejects_empty_list_before_loading_pharmacy(monkeypatch):
    monkeypatch.setattr(evidencias_export.EvidenciasService, "listar", classmethod(lambda _cls, _cnpj: []))
    monkeypatch.setattr(
        evidencias_export, "_load_farmacia",
        lambda _cnpj: pytest.fail("farmacia should not be loaded for an empty evidence list"),
    )
    with pytest.raises(HTTPException) as error:
        evidencias_export.export_evidencias_xlsx("12345678000190")
    assert error.value.status_code == 404


def test_evidence_export_maps_missing_authorization_time_to_http_500(monkeypatch):
    record = {
        "id": "authorization", "cnpj": "12345678000190", "tipo": "autorizacao",
        "dt_janela": "2024-01-01", "num_autorizacao": "A", "criado_em": "2024-01-01T00:00:00+00:00",
        "snapshot": {},
    }
    monkeypatch.setattr(evidencias_export.EvidenciasService, "listar", classmethod(lambda _cls, _cnpj: [record]))
    monkeypatch.setattr(
        evidencias_export, "_load_farmacia",
        lambda _cnpj: type("Farmacia", (), {"razao_social": "Farmacia", "municipio": "Cidade", "uf": "SP"})(),
    )
    with pytest.raises(HTTPException) as error:
        evidencias_export.export_evidencias_xlsx("12345678000190")
    assert error.value.status_code == 500
    assert "sem horário da autorização" in error.value.detail
