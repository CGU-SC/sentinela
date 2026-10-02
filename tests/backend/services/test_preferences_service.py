import json
from pathlib import Path

import pytest

from backend.api.services import preferences
from backend.api.services.preferences import PreferencesError, PreferencesService


@pytest.fixture
def preferences_dir(tmp_path, monkeypatch):
    for name in ("BASE_DIR", "FILE_PATH", "BACKUP_PATH", "CORRUPT_PATH"):
        monkeypatch.setattr(PreferencesService, name, getattr(PreferencesService, name))
    PreferencesService._set_base_dir(tmp_path)
    return tmp_path


def _valid(watchlist=None, **overrides):
    data = PreferencesService.default_preferences()
    data["watchlist"] = watchlist or []
    data.update(overrides)
    return data


def _write(path: Path, value):
    path.write_text(json.dumps(value), encoding="utf-8")


def test_preferences_directory_resolution_for_environment_and_frozen_app(monkeypatch, tmp_path):
    monkeypatch.setenv("SENTINELA_PREFERENCES_DIR", str(tmp_path / "custom"))
    assert preferences._preferences_dir() == tmp_path / "custom"

    monkeypatch.delenv("SENTINELA_PREFERENCES_DIR")
    monkeypatch.setattr(preferences.sys, "frozen", True, raising=False)
    monkeypatch.delenv("LOCALAPPDATA", raising=False)
    with pytest.raises(PreferencesError, match="LOCALAPPDATA não está definido"):
        preferences._preferences_dir()

    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    assert preferences._preferences_dir() == tmp_path / "local" / "Sentinela" / "preferences"

    monkeypatch.setattr(preferences.sys, "frozen", False, raising=False)
    expected = Path(preferences.__file__).resolve().parents[3] / "modules" / "user_preferences"
    assert preferences._preferences_dir() == expected


def test_default_preferences_and_normalization_enforce_watchlist_and_object_fields():
    assert PreferencesService.default_preferences() == {
        "schema_version": 1, "filters": {}, "watchlist": [], "ui": {}, "nota_tecnica": {}, "metodologia": {}
    }
    normalized = PreferencesService._normalize({"watchlist": [{"cnpj": "123"}], "schema_version": 0})
    assert normalized["schema_version"] == 1
    assert normalized["watchlist"] == [{"cnpj": "123"}]
    assert normalized["filters"] == normalized["ui"] == normalized["nota_tecnica"] == normalized["metodologia"] == {}

    for invalid in (None, [], {"watchlist": None}):
        with pytest.raises(ValueError, match="watchlist deve ser uma lista"):
            PreferencesService._normalize(invalid)
    for invalid_item in ([None], [{}], [{"cnpj": ""}], [{"cnpj": 123}]):
        with pytest.raises(ValueError, match="registro inválido"):
            PreferencesService._normalize({"watchlist": invalid_item})
    for key in ("filters", "ui", "nota_tecnica", "metodologia"):
        with pytest.raises(ValueError, match=f"campo {key} deve ser um objeto"):
            PreferencesService._normalize({"watchlist": [], key: []})
    with pytest.raises(ValueError):
        PreferencesService._normalize({"watchlist": [], "schema_version": "invalid"})


def test_read_creates_defaults_only_when_no_recovery_files_exist(preferences_dir):
    assert PreferencesService._read_unlocked() == PreferencesService.default_preferences()
    assert json.loads(PreferencesService.FILE_PATH.read_text(encoding="utf-8")) == PreferencesService.default_preferences()

    PreferencesService.FILE_PATH.unlink()
    PreferencesService.CORRUPT_PATH.write_text("preserve", encoding="utf-8")
    with pytest.raises(PreferencesError, match="Há cópias para recuperação"):
        PreferencesService._read_unlocked()
    assert not PreferencesService.FILE_PATH.exists()


@pytest.mark.parametrize("content", ["{bad", '{"watchlist": "bad"}', '{"watchlist": [], "ui": []}'])
def test_read_path_preserves_and_reports_invalid_preference_files(preferences_dir, content):
    PreferencesService.FILE_PATH.write_text(content, encoding="utf-8")
    with pytest.raises(PreferencesError, match="não puderam ser interpretadas"):
        PreferencesService._read_path(PreferencesService.FILE_PATH)
    assert PreferencesService.FILE_PATH.read_text(encoding="utf-8") == content


def test_read_path_retries_transient_os_errors_and_reports_persistent_failure(preferences_dir, monkeypatch):
    _write(PreferencesService.FILE_PATH, _valid())
    original_open = Path.open
    count = 0

    def flaky(path, *args, **kwargs):
        nonlocal count
        if path == PreferencesService.FILE_PATH:
            count += 1
            if count == 1:
                raise OSError("temporary lock")
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", flaky)
    monkeypatch.setattr(preferences.time, "sleep", lambda _seconds: None)
    assert PreferencesService._read_path(PreferencesService.FILE_PATH)["watchlist"] == []
    assert count == 2

    def broken(path, *args, **kwargs):
        if path == PreferencesService.FILE_PATH:
            raise OSError("sharing violation")
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", broken)
    with pytest.raises(PreferencesError, match="Não foi possível ler as preferências"):
        PreferencesService._read_path(PreferencesService.FILE_PATH)


def test_atomic_write_replaces_file_and_cleans_temporary_files_on_error(preferences_dir, monkeypatch):
    PreferencesService._atomic_write(PreferencesService.FILE_PATH, _valid())
    assert PreferencesService._read_path(PreferencesService.FILE_PATH) == _valid()

    monkeypatch.setattr(preferences.os, "replace", lambda *_args: (_ for _ in ()).throw(OSError("disk full")))
    with pytest.raises(OSError, match="disk full"):
        PreferencesService._atomic_write(PreferencesService.FILE_PATH, _valid())
    assert not list(preferences_dir.glob(".preferences.json.*.tmp"))


def test_lock_reports_unavailable_directory_and_releases_the_native_lock(preferences_dir, monkeypatch):
    base_file = preferences_dir / "not-a-directory"
    base_file.write_text("file", encoding="utf-8")
    monkeypatch.setattr(PreferencesService, "BASE_DIR", base_file)
    with pytest.raises(PreferencesError, match="acessar as preferências"):
        with PreferencesService._locked():
            pytest.fail("lock should fail when the configured base path is a file")


def test_lock_retries_until_timeout_when_another_process_holds_it(preferences_dir, monkeypatch):
    import msvcrt

    attempts = []

    def busy_lock(_fd, mode, _count):
        attempts.append(mode)
        raise OSError("locked")

    ticks = iter((10.0, 15.0))
    monkeypatch.setattr(msvcrt, "locking", busy_lock)
    monkeypatch.setattr(preferences.time, "monotonic", lambda: next(ticks))
    monkeypatch.setattr(preferences.time, "sleep", lambda _seconds: None)
    with pytest.raises(PreferencesError, match="ocupadas por outra instância"):
        with PreferencesService._locked():
            pytest.fail("lock acquisition should time out")
    assert len(attempts) == 1


def test_lock_retries_transient_contention_and_releases_lock(preferences_dir, monkeypatch):
    import msvcrt

    modes = []

    def transient_lock(_fd, mode, _count):
        modes.append(mode)
        if mode == msvcrt.LK_NBLCK and modes.count(msvcrt.LK_NBLCK) == 1:
            raise OSError("temporarily busy")

    ticks = iter((0.0, 1.0))
    sleeps = []
    monkeypatch.setattr(msvcrt, "locking", transient_lock)
    monkeypatch.setattr(preferences.time, "monotonic", lambda: next(ticks))
    monkeypatch.setattr(preferences.time, "sleep", lambda seconds: sleeps.append(seconds))
    with PreferencesService._locked():
        assert modes == [msvcrt.LK_NBLCK, msvcrt.LK_NBLCK]
    assert sleeps == [0.05]
    assert modes[-1] == msvcrt.LK_UNLCK


def test_lock_uses_posix_flock_contract_when_running_on_posix(preferences_dir, monkeypatch):
    class FakeFcntl:
        LOCK_EX = 1
        LOCK_UN = 2
        calls = []

        @classmethod
        def flock(cls, _fd, operation):
            cls.calls.append(operation)

    monkeypatch.setitem(__import__("sys").modules, "fcntl", FakeFcntl)
    monkeypatch.setattr(preferences.os, "name", "posix")
    with PreferencesService._locked():
        assert FakeFcntl.calls == [FakeFcntl.LOCK_EX]
    assert FakeFcntl.calls == [FakeFcntl.LOCK_EX, FakeFcntl.LOCK_UN]


def test_read_and_write_services_translate_filesystem_failures(preferences_dir, monkeypatch):
    with PreferencesService._locked():
        pass
    monkeypatch.setattr(PreferencesService, "_read_unlocked", classmethod(lambda _cls: (_ for _ in ()).throw(OSError("read error"))))
    with pytest.raises(PreferencesError, match="acessar as preferências"):
        PreferencesService.read()
    with pytest.raises(PreferencesError, match="salvar as preferências"):
        PreferencesService.write(_valid())


def test_write_unlocked_preserves_last_nonempty_backup_and_rotates_ordinary_backups(preferences_dir):
    old = _valid(watchlist=[{"cnpj": "old"}])
    new = _valid(watchlist=[])
    _write(PreferencesService.FILE_PATH, old)
    _write(PreferencesService.BACKUP_PATH, old)

    result = PreferencesService._write_unlocked(new, _valid())
    assert result == new
    assert json.loads(PreferencesService.BACKUP_PATH.read_text(encoding="utf-8")) == old
    assert PreferencesService._read_path(PreferencesService.FILE_PATH) == new

    current = _valid(watchlist=[{"cnpj": "current"}])
    PreferencesService._write_unlocked(current, new)
    assert json.loads(PreferencesService.BACKUP_PATH.read_text(encoding="utf-8")) == old
    assert PreferencesService._read_path(PreferencesService.FILE_PATH) == current


def test_public_updates_replace_or_merge_their_fields(preferences_dir):
    assert PreferencesService.read() == PreferencesService.default_preferences()
    PreferencesService.update_filters({"uf": "SP"})
    PreferencesService.update_watchlist([{"cnpj": "123"}])
    PreferencesService.update_ui({"theme": "dark"})
    PreferencesService.update_ui({"sidebar": "collapsed"})
    PreferencesService.update_nota_tecnica({"fonte": "Arial"})
    PreferencesService.update_metodologia({"volume_atipico_aumento_minimo": 100})
    PreferencesService.update_metodologia({"audit_high_value": 500})
    result = PreferencesService.read()
    assert result["filters"] == {"uf": "SP"}
    assert result["watchlist"] == [{"cnpj": "123"}]
    assert result["ui"] == {"theme": "dark", "sidebar": "collapsed"}
    assert result["nota_tecnica"] == {"fonte": "Arial"}
    assert result["metodologia"] == {"volume_atipico_aumento_minimo": 100, "audit_high_value": 500}


def test_write_and_update_reject_invalid_data_as_preferences_errors(preferences_dir):
    with pytest.raises(PreferencesError, match="salvar as preferências"):
        PreferencesService.write({"watchlist": "invalid"})
    with pytest.raises(PreferencesError, match="salvar as preferências"):
        PreferencesService.update_watchlist([{"cnpj": ""}])


def test_write_unlocked_does_not_overwrite_backup_without_watchlist_when_previous_is_empty(preferences_dir):
    current = _valid()
    old_backup = _valid(watchlist=[])
    _write(PreferencesService.FILE_PATH, current)
    _write(PreferencesService.BACKUP_PATH, old_backup)
    result = PreferencesService._write_unlocked(_valid(ui={"mode": "compact"}), current)
    assert result["ui"] == {"mode": "compact"}
    assert json.loads(PreferencesService.BACKUP_PATH.read_text(encoding="utf-8")) == current


def test_recovery_status_reports_missing_valid_and_corrupt_sources(preferences_dir):
    status = PreferencesService.recovery_status()
    assert all(not value["exists"] and value["watchlist_count"] is None for value in status.values())

    _write(PreferencesService.FILE_PATH, _valid(watchlist=[{"cnpj": "1"}]))
    _write(PreferencesService.BACKUP_PATH, _valid())
    PreferencesService.CORRUPT_PATH.write_text("broken", encoding="utf-8")
    status = PreferencesService.recovery_status()
    assert status["principal"] == {"exists": True, "valid": True, "watchlist_count": 1}
    assert status["backup"] == {"exists": True, "valid": True, "watchlist_count": 0}
    assert status["corrupt"] == {"exists": True, "valid": False, "watchlist_count": None}


@pytest.mark.parametrize("source", ["backup", "corrupt"])
def test_restore_archives_current_preferences_and_restores_selected_copy(preferences_dir, source):
    previous = _valid(watchlist=[{"cnpj": "old"}])
    selected = _valid(watchlist=[{"cnpj": "restored"}], ui={"mode": "dark"})
    _write(PreferencesService.FILE_PATH, previous)
    source_path = PreferencesService.BACKUP_PATH if source == "backup" else PreferencesService.CORRUPT_PATH
    _write(source_path, selected)

    result = PreferencesService.restore(source)

    assert result == selected
    assert PreferencesService._read_path(PreferencesService.FILE_PATH) == selected
    archives = list(preferences_dir.glob("preferences.pre-restore.*.json"))
    assert len(archives) == 1
    assert json.loads(archives[0].read_text(encoding="utf-8")) == previous


def test_restore_rejects_unknown_source_and_reports_write_failure(preferences_dir, monkeypatch):
    with pytest.raises(PreferencesError, match="Fonte de recuperação inválida"):
        PreferencesService.restore("principal")

    _write(PreferencesService.BACKUP_PATH, _valid(watchlist=[{"cnpj": "backup"}]))
    _write(PreferencesService.FILE_PATH, _valid(watchlist=[{"cnpj": "current"}]))
    monkeypatch.setattr(
        PreferencesService,
        "_atomic_write",
        classmethod(lambda _cls, _path, _data: (_ for _ in ()).throw(OSError("disk full"))),
    )
    with pytest.raises(PreferencesError, match="Não foi possível restaurar"):
        PreferencesService.restore("backup")
    assert json.loads(PreferencesService.FILE_PATH.read_text(encoding="utf-8"))["watchlist"] == [{"cnpj": "current"}]


def test_restore_requires_valid_source_copy(preferences_dir):
    PreferencesService.BACKUP_PATH.write_text("invalid", encoding="utf-8")
    with pytest.raises(PreferencesError, match="não puderam ser interpretadas"):
        PreferencesService.restore("backup")
