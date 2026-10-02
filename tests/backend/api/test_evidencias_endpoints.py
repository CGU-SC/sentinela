import pytest
from fastapi import HTTPException

from backend.api.endpoints import evidencias
from backend.api.schemas.evidencias import (
    EvidenciaCreate,
    EvidenciaNotaPayload,
    EvidenciaRemocaoCnpjSchema,
    EvidenciaResumoSchema,
    EvidenciaSchema,
)
from backend.api.services.evidencias import (
    EvidenciaDuplicadaError,
    EvidenciaForaDaListaError,
    EvidenciaNaoEncontradaError,
    EvidenciasError,
)


@pytest.mark.parametrize(
    ("exception", "status"),
    [
        (EvidenciaDuplicadaError("duplicate"), 409),
        (EvidenciaForaDaListaError("not watched"), 409),
        (EvidenciaNaoEncontradaError("missing"), 404),
        (EvidenciasError("storage unavailable"), 503),
    ],
)
def test_endpoint_error_adapter_maps_service_errors_and_keeps_causes(exception, status):
    def fail(*_args):
        raise exception

    with pytest.raises(HTTPException) as error:
        evidencias._chamar(fail, "arg")
    assert error.value.status_code == status
    assert error.value.detail == str(exception)
    assert error.value.__cause__ is exception


def test_list_and_summary_endpoints_delegate_to_service(monkeypatch):
    calls = []
    monkeypatch.setattr(evidencias.EvidenciasService, "listar", classmethod(lambda _cls, cnpj=None: calls.append(cnpj) or [{"id": "e1"}]))
    monkeypatch.setattr(evidencias.EvidenciasService, "resumo_por_cnpj", classmethod(lambda _cls: [{"cnpj": "1", "quantidade": 2}]))

    assert evidencias.listar_evidencias("12345678000190") == [{"id": "e1"}]
    assert evidencias.listar_evidencias(None) == [{"id": "e1"}]
    assert evidencias.resumo_evidencias() == [{"cnpj": "1", "quantidade": 2}]
    assert calls == ["12345678000190", None]


def test_create_and_update_endpoints_pass_validated_payload_fields(monkeypatch):
    create_calls = []
    update_calls = []
    monkeypatch.setattr(
        evidencias.EvidenciasService,
        "criar",
        classmethod(lambda _cls, payload: create_calls.append(payload) or {"id": "e1"}),
    )
    monkeypatch.setattr(
        evidencias.EvidenciasService,
        "atualizar_nota",
        classmethod(lambda _cls, item_id, note: update_calls.append((item_id, note)) or {"id": item_id, "nota": note}),
    )
    created = EvidenciaCreate(cnpj="12345678000190", tipo="hora", dt_janela="2024-02-01", hora=7, nota="analisar")
    updated = evidencias.atualizar_nota_evidencia(EvidenciaNotaPayload(nota="nota revisada"), "e1")

    assert evidencias.criar_evidencia(created) == {"id": "e1"}
    assert create_calls == [created.model_dump()]
    assert updated == {"id": "e1", "nota": "nota revisada"}
    assert update_calls == [("e1", "nota revisada")]


def test_export_delete_by_cnpj_and_delete_by_id_return_http_contracts(monkeypatch):
    monkeypatch.setattr(evidencias, "export_evidencias_xlsx", lambda _cnpj: ("audit.xlsx", b"excel-bytes"))
    monkeypatch.setattr(evidencias.EvidenciasService, "remover_por_cnpj", classmethod(lambda _cls, _cnpj: 3))
    removed_ids = []
    monkeypatch.setattr(evidencias.EvidenciasService, "remover", classmethod(lambda _cls, item_id: removed_ids.append(item_id)))

    response = evidencias.exportar_evidencias_do_cnpj("12345678000190")
    assert response.body == b"excel-bytes"
    assert response.media_type == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    assert response.headers["content-disposition"] == 'attachment; filename="audit.xlsx"'
    assert response.headers["cache-control"] == "no-store"
    assert evidencias.remover_evidencias_do_cnpj("12345678000190") == {"removidas": 3}
    deleted = evidencias.remover_evidencia("e1")
    assert deleted.status_code == 204
    assert removed_ids == ["e1"]


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ({"cnpj": "bad", "tipo": "dia", "dt_janela": "2024-01-01"}, "cnpj"),
        ({"cnpj": "12345678000190", "tipo": "unknown", "dt_janela": "2024-01-01"}, "tipo"),
        ({"cnpj": "12345678000190", "tipo": "dia", "dt_janela": "20240101"}, "dt_janela"),
        ({"cnpj": "12345678000190", "tipo": "dia", "dt_janela": "2024-01-01", "hora": 1}, "tipo dia"),
        ({"cnpj": "12345678000190", "tipo": "hora", "dt_janela": "2024-01-01"}, "exige a hora"),
        ({"cnpj": "12345678000190", "tipo": "hora", "dt_janela": "2024-01-01", "hora": 1, "num_autorizacao": "A"}, "não leva autorização"),
        ({"cnpj": "12345678000190", "tipo": "autorizacao", "dt_janela": "2024-01-01", "hora": 1}, "exige o número"),
        ({"cnpj": "12345678000190", "tipo": "autorizacao", "dt_janela": "2024-01-01", "hora": 1, "num_autorizacao": "A"}, None),
    ],
)
def test_create_schema_enforces_discriminator_fields_and_accepts_valid_authorization(payload, message):
    if message is None:
        assert EvidenciaCreate(**payload).tipo == "autorizacao"
    else:
        with pytest.raises(ValueError, match=message):
            EvidenciaCreate(**payload)


def test_note_payload_accepts_empty_note_and_response_date_types_are_valid():
    assert EvidenciaNotaPayload(nota="").nota == ""
    assert EvidenciaResumoSchema(cnpj="123", quantidade=2, ultima_em="2024-01-01").quantidade == 2
    assert EvidenciaRemocaoCnpjSchema(removidas=1).removidas == 1
    payload = EvidenciaSchema(
        cnpj="12345678000190", tipo="dia", dt_janela="2024-01-01", id="e1",
        criado_em="2024-01-01T00:00:00Z", atualizado_em="2024-01-01T00:00:00Z",
    )
    assert payload.id == "e1"
