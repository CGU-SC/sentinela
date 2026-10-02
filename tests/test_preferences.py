"""Testes de persistência e recuperação das preferências locais."""

import json
import sys
import tempfile
import types
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from backend.api.services import preferences as preferences_module
from backend.api.services.preferences import PreferencesError, PreferencesService


class PreferencesServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.original_dir = PreferencesService.BASE_DIR
        PreferencesService._set_base_dir(Path(self.temp.name))

    def tearDown(self):
        PreferencesService._set_base_dir(self.original_dir)
        self.temp.cleanup()

    @staticmethod
    def items(count):
        return [{"cnpj": f"{number:014d}", "razaoSocial": "Farmácia"} for number in range(count)]

    def test_preferences_directory_uses_override_and_frozen_app_location(self):
        with patch.dict(
            preferences_module.os.environ,
            {"SENTINELA_PREFERENCES_DIR": str(Path(self.temp.name) / "custom")},
            clear=True,
        ):
            self.assertEqual(
                preferences_module._preferences_dir(),
                Path(self.temp.name) / "custom",
            )

        with patch.dict(
            preferences_module.os.environ,
            {"SENTINELA_PREFERENCES_DIR": "", "LOCALAPPDATA": self.temp.name},
            clear=True,
        ), patch.object(preferences_module.sys, "frozen", True, create=True):
            self.assertEqual(
                preferences_module._preferences_dir(),
                Path(self.temp.name) / "Sentinela" / "preferences",
            )

        with patch.dict(
            preferences_module.os.environ,
            {"SENTINELA_PREFERENCES_DIR": ""},
            clear=True,
        ), patch.object(preferences_module.sys, "frozen", True, create=True):
            with self.assertRaisesRegex(PreferencesError, "LOCALAPPDATA não está definido"):
                preferences_module._preferences_dir()

    def test_normalization_rejects_invalid_required_watchlist_and_object_fields(self):
        with self.assertRaisesRegex(ValueError, "watchlist deve ser uma lista"):
            PreferencesService._normalize({})
        with self.assertRaisesRegex(ValueError, "registro inválido"):
            PreferencesService._normalize({"watchlist": [{"cnpj": ""}]})
        for field in ("filters", "ui", "nota_tecnica", "metodologia"):
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, f"{field} deve ser um objeto"):
                PreferencesService._normalize({"watchlist": [], field: []})

    def test_lock_errors_are_reported_and_windows_lock_retries_then_times_out(self):
        original_open = Path.open

        def fail_lock_file(path, *args, **kwargs):
            if path.name == ".preferences.lock":
                raise OSError("lock file unavailable")
            return original_open(path, *args, **kwargs)

        with patch.object(Path, "open", fail_lock_file):
            with self.assertRaisesRegex(PreferencesError, "acessar as preferências"):
                PreferencesService.read()

        attempts = []

        def lock_then_succeed(_fd, operation, _length):
            attempts.append(operation)
            if operation == 1 and attempts.count(1) == 1:
                raise OSError("busy")

        fake_msvcrt = types.SimpleNamespace(LK_NBLCK=1, LK_UNLCK=2, locking=lock_then_succeed)
        with patch.object(preferences_module, "os", types.SimpleNamespace(name="nt")), patch.dict(
            sys.modules, {"msvcrt": fake_msvcrt}
        ), patch.object(preferences_module.time, "monotonic", side_effect=[0.0, 0.0]), patch.object(
            preferences_module.time, "sleep"
        ):
            with PreferencesService._locked():
                pass
        self.assertEqual(attempts, [1, 1, 2])

        def always_busy(_fd, _operation, _length):
            raise OSError("still busy")

        fake_msvcrt.locking = always_busy
        with patch.object(preferences_module, "os", types.SimpleNamespace(name="nt")), patch.dict(
            sys.modules, {"msvcrt": fake_msvcrt}
        ), patch.object(preferences_module.time, "monotonic", side_effect=[0.0, 6.0]), patch.object(
            preferences_module.time, "sleep"
        ):
            with self.assertRaisesRegex(PreferencesError, "ocupadas por outra instância"):
                with PreferencesService._locked():
                    self.fail("lock contention must time out before entering the critical section")

    def test_posix_lock_acquires_and_releases_file_lock(self):
        operations = []
        fake_fcntl = types.SimpleNamespace(
            LOCK_EX=1,
            LOCK_UN=2,
            flock=lambda _fd, operation: operations.append(operation),
        )
        with patch.object(preferences_module, "os", types.SimpleNamespace(name="posix")), patch.dict(
            sys.modules, {"fcntl": fake_fcntl}
        ):
            with PreferencesService._locked():
                self.assertEqual(operations, [fake_fcntl.LOCK_EX])
        self.assertEqual(operations, [fake_fcntl.LOCK_EX, fake_fcntl.LOCK_UN])

    def test_first_use_creates_empty_preferences(self):
        self.assertEqual(PreferencesService.read()["watchlist"], [])
        self.assertTrue(PreferencesService.FILE_PATH.exists())

    def test_invalid_json_does_not_reset_or_overwrite_backup(self):
        PreferencesService.BACKUP_PATH.write_text(
            json.dumps({**PreferencesService.default_preferences(), "watchlist": self.items(2)}),
            encoding="utf-8",
        )
        PreferencesService.FILE_PATH.write_text('{"watchlist":', encoding="utf-8")
        backup_before = PreferencesService.BACKUP_PATH.read_bytes()
        with self.assertRaises(PreferencesError):
            PreferencesService.read()
        with self.assertRaises(PreferencesError):
            PreferencesService.update_watchlist([])
        self.assertEqual(PreferencesService.FILE_PATH.read_text(encoding="utf-8"), '{"watchlist":')
        self.assertEqual(PreferencesService.BACKUP_PATH.read_bytes(), backup_before)

    def test_missing_main_with_backup_requires_explicit_recovery(self):
        PreferencesService.BACKUP_PATH.write_text(
            json.dumps({**PreferencesService.default_preferences(), "watchlist": self.items(2)}),
            encoding="utf-8",
        )
        with self.assertRaises(PreferencesError):
            PreferencesService.read()
        self.assertFalse(PreferencesService.FILE_PATH.exists())

    def test_empty_main_does_not_replace_backup_with_favorites(self):
        PreferencesService.read()
        PreferencesService.BACKUP_PATH.write_text(
            json.dumps({**PreferencesService.default_preferences(), "watchlist": self.items(2)}),
            encoding="utf-8",
        )
        PreferencesService.update_filters({"x": 1})
        self.assertEqual(len(PreferencesService._read_path(PreferencesService.BACKUP_PATH)["watchlist"]), 2)

    def test_temporary_read_error_is_retried(self):
        PreferencesService.update_watchlist(self.items(3))
        original_open = Path.open
        failures = 0

        def flaky_open(path, *args, **kwargs):
            nonlocal failures
            if path == PreferencesService.FILE_PATH and failures < 2:
                failures += 1
                raise PermissionError("temporarily locked")
            return original_open(path, *args, **kwargs)

        with patch.object(Path, "open", flaky_open):
            self.assertEqual(len(PreferencesService.read()["watchlist"]), 3)
        self.assertEqual(failures, 2)

    def test_persistent_read_error_preserves_files(self):
        PreferencesService.update_watchlist(self.items(3))
        before = PreferencesService.FILE_PATH.read_bytes()
        backup_before = PreferencesService.BACKUP_PATH.read_bytes()
        original_open = Path.open

        def blocked_open(path, *args, **kwargs):
            if path == PreferencesService.FILE_PATH:
                raise PermissionError("locked")
            return original_open(path, *args, **kwargs)

        with patch.object(Path, "open", blocked_open):
            with self.assertRaises(PreferencesError):
                PreferencesService.read()
        self.assertEqual(PreferencesService.FILE_PATH.read_bytes(), before)
        self.assertEqual(PreferencesService.BACKUP_PATH.read_bytes(), backup_before)

    def test_read_wraps_initialization_oserror_and_write_reports_rejected_data(self):
        with patch.object(PreferencesService, "_read_unlocked", side_effect=PermissionError("locked")):
            with self.assertRaisesRegex(PreferencesError, "acessar as preferências"):
                PreferencesService.read()

        with patch.object(PreferencesService, "_write_unlocked", side_effect=ValueError("invalid")):
            with self.assertRaisesRegex(PreferencesError, "salvar as preferências"):
                PreferencesService.write(PreferencesService.default_preferences())

    def test_recovery_status_reports_absent_and_invalid_files(self):
        absent = PreferencesService.recovery_status()
        self.assertTrue(all(not record["exists"] and not record["valid"] for record in absent.values()))

        PreferencesService.CORRUPT_PATH.write_text("not-json", encoding="utf-8")
        status = PreferencesService.recovery_status()
        self.assertEqual(
            status["corrupt"],
            {"exists": True, "valid": False, "watchlist_count": None},
        )

    def test_restore_rejects_unknown_source_and_reports_failed_atomic_write(self):
        with self.assertRaisesRegex(PreferencesError, "Fonte de recuperação inválida"):
            PreferencesService.restore("primary")

        PreferencesService.CORRUPT_PATH.write_text(
            json.dumps({**PreferencesService.default_preferences(), "watchlist": self.items(1)}),
            encoding="utf-8",
        )
        with patch.object(PreferencesService, "_atomic_write", side_effect=OSError("disk full")):
            with self.assertRaisesRegex(PreferencesError, "restaurar as preferências"):
                PreferencesService.restore("corrupt")

    def test_write_error_is_not_reported_as_success(self):
        PreferencesService.update_watchlist(self.items(3))
        before = PreferencesService.FILE_PATH.read_bytes()
        original_write = PreferencesService._atomic_write.__func__

        def failed_write(cls, path, data):
            if path == cls.FILE_PATH:
                raise PermissionError("disk full")
            return original_write(cls, path, data)

        with patch.object(PreferencesService, "_atomic_write", classmethod(failed_write)):
            with self.assertRaises(PreferencesError):
                PreferencesService.update_watchlist([])
        self.assertEqual(PreferencesService.FILE_PATH.read_bytes(), before)

    def test_explicit_restore_preserves_previous_main_and_backup(self):
        PreferencesService.update_watchlist([])
        PreferencesService.CORRUPT_PATH.write_text(
            json.dumps({**PreferencesService.default_preferences(), "watchlist": self.items(17)}),
            encoding="utf-8",
        )
        main_before = PreferencesService.FILE_PATH.read_bytes()
        backup_before = PreferencesService.BACKUP_PATH.read_bytes()
        status = PreferencesService.recovery_status()
        self.assertEqual(status["corrupt"]["watchlist_count"], 17)
        self.assertEqual(len(PreferencesService.restore("corrupt")["watchlist"]), 17)
        self.assertEqual(PreferencesService.BACKUP_PATH.read_bytes(), backup_before)
        archived = list(PreferencesService.BASE_DIR.glob("preferences.pre-restore.*.json"))
        self.assertEqual(len(archived), 1)
        self.assertEqual(archived[0].read_bytes(), main_before)

    def test_updates_from_threads_do_not_lose_fields(self):
        PreferencesService.read()
        with ThreadPoolExecutor(max_workers=8) as executor:
            list(executor.map(lambda i: PreferencesService.update_ui({f"field_{i}": i}), range(20)))
        self.assertEqual(len(PreferencesService.read()["ui"]), 20)

    def test_note_and_methodology_preferences_are_persisted_with_expected_merge_behavior(self):
        PreferencesService.read()
        PreferencesService.update_nota_tecnica({"periodo": "2024-S1"})
        PreferencesService.update_nota_tecnica({"include_appendix": True})
        PreferencesService.update_metodologia({"version": 1})
        PreferencesService.update_metodologia({"source": "official"})

        saved = PreferencesService.read()
        self.assertEqual(saved["nota_tecnica"], {"include_appendix": True})
        self.assertEqual(saved["metodologia"], {"version": 1, "source": "official"})


if __name__ == "__main__":
    unittest.main()
