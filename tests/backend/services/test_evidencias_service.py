import json
from contextlib import contextmanager
from pathlib import Path

import pytest

from backend.api.services.evidencias import (
    EvidenciaDuplicadaError,
    EvidenciaForaDaListaError,
    EvidenciaNaoEncontradaError,
    EvidenciasError,
    EvidenciasService,
    TIPOS_EVIDENCIA,
    _chave,
)
from backend.api.services.preferences import PreferencesError, PreferencesService


@pytest.fixture
def evidence_store(tmp_path, monkeypatch):
    monkeypatch.setattr(PreferencesService, "BASE_DIR", tmp_path)
    monkeypatch.setattr(PreferencesService, "FILE_PATH", tmp_path / "preferences.json")
    monkeypatch.setattr(PreferencesService, "BACKUP_PATH", tmp_path / "preferences.backup.json")
    monkeypatch.setattr(PreferencesService, "CORRUPT_PATH", tmp_path / "preferences.corrupt.json")
    tmp_path.mkdir(exist_ok=True)
    return tmp_path


def _seed_preferences(directory: Path, *, watchlist=None):
    PreferencesService._atomic_write(
        directory / "preferences.json",
        {"schema_version": 1, "filters": {}, "watchlist": watchlist or [], "ui": {},
         "nota_tecnica": {}, "metodologia": {}},
    )


def _payload(tipo="dia", **overrides):
    data = {"cnpj": "12345678000190", "tipo": tipo, "dt_janela": "2024-01-15", "nota": "  revisar  "}
    if tipo == "hora":
        data["hora"] = 9
    elif tipo == "autorizacao":
        data["num_autorizacao"] = "AUTH-1"
    data.update(overrides)
    return data


def _write_evidence(directory: Path, records):
    (directory / EvidenciasService.FILE_NAME).write_text(
        json.dumps({"schema_version": 1, "evidencias": records}), encoding="utf-8"
    )


def test_path_helpers_and_evidence_identity_for_all_supported_kinds(evidence_store):
    assert EvidenciasService._file_path() == evidence_store / "evidencias.json"
    assert EvidenciasService._backup_path() == evidence_store / "evidencias.backup.json"
    assert _chave({"cnpj": "1", "tipo": "dia", "dt_janela": "2024-01-01"}) == (
        "1", "dia", "2024-01-01"
    )
    assert _chave(
        {"cnpj": "1", "tipo": "hora", "dt_janela": "2024-01-01", "hora": 8}
    ) == ("1", "hora", "2024-01-01", 8)
    assert _chave(
        {"cnpj": "1", "tipo": "autorizacao", "num_autorizacao": "A"}
    ) == ("1", "autorizacao", "A")


@pytest.mark.parametrize(
    ("data", "message"),
    [
        ([], "evidencias deve ser uma lista"),
        ({"evidencias": "not a list"}, "evidencias deve ser uma lista"),
        ({"evidencias": ["not a record"]}, "registro incompleto"),
        ({"evidencias": [{"id": "1", "cnpj": "1", "tipo": "dia", "dt_janela": "2024-01-01"}]},
         "registro incompleto"),
        ({"evidencias": [{"id": "1", "cnpj": "1", "tipo": "unknown", "dt_janela": "2024-01-01", "criado_em": "now"}]},
         "Tipo de evidência desconhecido"),
    ],
)
def test_file_validator_rejects_invalid_container_records_and_types(data, message):
    with pytest.raises(ValueError, match=message):
        EvidenciasService._validar_arquivo(data)


def test_file_validator_accepts_complete_supported_records():
    records = [{"id": "1", "cnpj": "123", "tipo": tipo, "dt_janela": "2024-01-01", "criado_em": "now"}
               for tipo in TIPOS_EVIDENCIA]
    assert EvidenciasService._validar_arquivo({"evidencias": records}) is records


def test_read_missing_file_is_empty_but_backup_only_requires_explicit_recovery(evidence_store):
    assert EvidenciasService._ler_unlocked() == []
    (evidence_store / EvidenciasService.BACKUP_NAME).write_text("backup", encoding="utf-8")
    with pytest.raises(EvidenciasError, match="restaure a cópia"):
        EvidenciasService._ler_unlocked()


@pytest.mark.parametrize("contents", ["{invalid", "{}", '{"evidencias": [{"tipo": "bad"}]}'])
def test_read_rejects_corrupt_json_and_invalid_evidence_without_overwriting(evidence_store, contents):
    path = evidence_store / EvidenciasService.FILE_NAME
    path.write_text(contents, encoding="utf-8")
    with pytest.raises(EvidenciasError, match="não pôde ser interpretada"):
        EvidenciasService._ler_unlocked()
    assert path.read_text(encoding="utf-8") == contents


def test_read_retries_transient_os_errors_then_succeeds(evidence_store, monkeypatch):
    _write_evidence(evidence_store, [])
    original_open = Path.open
    attempts = 0

    def flaky_open(path, *args, **kwargs):
        nonlocal attempts
        if path == evidence_store / EvidenciasService.FILE_NAME:
            attempts += 1
            if attempts < 3:
                raise OSError("temporary sharing violation")
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", flaky_open)
    monkeypatch.setattr("backend.api.services.evidencias.time.sleep", lambda _seconds: None)
    assert EvidenciasService._ler_unlocked() == []
    assert attempts == 3


def test_read_reports_persistent_os_failure_after_retries(evidence_store, monkeypatch):
    path = evidence_store / EvidenciasService.FILE_NAME
    path.write_text('{"evidencias": []}', encoding="utf-8")
    original_open = Path.open
    attempts = 0

    def failing_open(candidate, *args, **kwargs):
        nonlocal attempts
        if candidate == path:
            attempts += 1
            raise OSError("sharing violation")
        return original_open(candidate, *args, **kwargs)

    monkeypatch.setattr(Path, "open", failing_open)
    monkeypatch.setattr("backend.api.services.evidencias.time.sleep", lambda _seconds: None)
    with pytest.raises(EvidenciasError, match="Não foi possível ler"):
        EvidenciasService._ler_unlocked()
    assert attempts == 3


def test_create_persists_clean_note_and_backups_previous_version(evidence_store):
    _seed_preferences(
        evidence_store,
        watchlist=[{"cnpj": "12345678000190"}, {"cnpj": "12345678000191"}],
    )
    first = EvidenciasService.criar(_payload())
    assert first["nota"] == "revisar"
    assert first["id"] and first["criado_em"] == first["atualizado_em"]
    assert EvidenciasService._ler_unlocked() == [first]

    second = EvidenciasService.criar(_payload("hora", dt_janela="2024-01-15", hora=10))
    backup = json.loads((evidence_store / EvidenciasService.BACKUP_NAME).read_text(encoding="utf-8"))
    assert backup["evidencias"] == [first]
    assert EvidenciasService._ler_unlocked() == [first, second]


def test_create_requires_watchlist_membership_and_prevents_duplicate_days_hours_and_authorizations(evidence_store):
    _seed_preferences(evidence_store, watchlist=[{"cnpj": "12345678000190"}])
    with pytest.raises(EvidenciaForaDaListaError, match="não está nas Farmácias Monitoradas"):
        EvidenciasService.criar(_payload(cnpj="99999999000199"))

    for tipo in TIPOS_EVIDENCIA:
        evidence = EvidenciasService.criar(_payload(tipo))
        with pytest.raises(EvidenciaDuplicadaError, match="já está na cesta"):
            EvidenciasService.criar(_payload(tipo))
        assert evidence["tipo"] == tipo
        if tipo == "autorizacao":
            # Autorização é identificada pelo número no mesmo CNPJ, mesmo se a data divergir.
            with pytest.raises(EvidenciaDuplicadaError):
                EvidenciasService.criar(_payload(tipo, dt_janela="2024-01-16"))


def test_list_and_summary_filter_by_cnpj_and_sort_latest_first(evidence_store):
    _seed_preferences(evidence_store, watchlist=[])
    records = [
        {"id": "a", "cnpj": "2", "tipo": "dia", "dt_janela": "2024-01-01", "criado_em": "2024-01-01"},
        {"id": "b", "cnpj": "1", "tipo": "hora", "dt_janela": "2024-01-02", "criado_em": "2024-02-01"},
        {"id": "c", "cnpj": "2", "tipo": "autorizacao", "dt_janela": "2024-01-03", "criado_em": "2024-03-01"},
    ]
    _write_evidence(evidence_store, records)

    assert [item["id"] for item in EvidenciasService.listar()] == ["c", "b", "a"]
    assert [item["id"] for item in EvidenciasService.listar("2")] == ["c", "a"]
    assert EvidenciasService.resumo_por_cnpj() == [
        {"cnpj": "1", "quantidade": 1, "ultima_em": "2024-02-01"},
        {"cnpj": "2", "quantidade": 2, "ultima_em": "2024-03-01"},
    ]


def test_update_note_trims_text_and_missing_ids_raise(evidence_store):
    _seed_preferences(evidence_store, watchlist=[{"cnpj": "12345678000190"}])
    created = EvidenciasService.criar(_payload())
    updated = EvidenciasService.atualizar_nota(created["id"], "  validado  ")
    assert updated["nota"] == "validado"
    assert updated["atualizado_em"] >= created["atualizado_em"]
    with pytest.raises(EvidenciaNaoEncontradaError):
        EvidenciasService.atualizar_nota("missing", "nota")


def test_remove_item_and_remove_all_items_for_pharmacy(evidence_store):
    _seed_preferences(
        evidence_store,
        watchlist=[{"cnpj": "12345678000190"}, {"cnpj": "12345678000191"}],
    )
    first = EvidenciasService.criar(_payload())
    second = EvidenciasService.criar(_payload("hora", hora=10))
    other = EvidenciasService.criar(_payload(cnpj="12345678000191"))

    EvidenciasService.remover(first["id"])
    with pytest.raises(EvidenciaNaoEncontradaError):
        EvidenciasService.remover(first["id"])
    assert EvidenciasService.remover_por_cnpj("12345678000190") == 1
    assert EvidenciasService.remover_por_cnpj("12345678000190") == 0
    assert EvidenciasService.listar() == [other]
    assert second["id"] != other["id"]


def test_transaction_converts_preferences_lock_failures_to_visible_storage_error(evidence_store, monkeypatch):
    @contextmanager
    def locked():
        raise PreferencesError("locked by another process")
        yield

    monkeypatch.setattr(PreferencesService, "_locked", locked)
    with pytest.raises(EvidenciasError, match="locked by another process"):
        EvidenciasService.listar()


def test_write_failure_preserves_error_and_cleans_temporary_backup(evidence_store, monkeypatch):
    _seed_preferences(evidence_store, watchlist=[{"cnpj": "12345678000190"}])
    (evidence_store / EvidenciasService.FILE_NAME).write_text(
        '{"schema_version": 1, "evidencias": []}', encoding="utf-8"
    )
    original_replace = __import__("backend.api.services.evidencias", fromlist=["os"]).os.replace
    backup_path = evidence_store / EvidenciasService.BACKUP_NAME

    def fail_backup_replace(source, destination):
        if Path(destination) == backup_path:
            raise OSError("disk full")
        return original_replace(source, destination)

    monkeypatch.setattr("backend.api.services.evidencias.os.replace", fail_backup_replace)
    with pytest.raises(EvidenciasError, match="Não foi possível salvar"):
        EvidenciasService._gravar_unlocked([])
    assert not list(evidence_store.glob(f".{EvidenciasService.BACKUP_NAME}.*.tmp"))


def test_write_failure_during_primary_atomic_replace_is_reported(evidence_store, monkeypatch):
    _seed_preferences(evidence_store, watchlist=[])
    monkeypatch.setattr(
        PreferencesService,
        "_atomic_write",
        classmethod(lambda _cls, _path, _data: (_ for _ in ()).throw(OSError("disk full"))),
    )
    with pytest.raises(EvidenciasError, match="Não foi possível salvar"):
        EvidenciasService._gravar_unlocked([])
