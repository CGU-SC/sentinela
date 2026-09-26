"""Testes de persistência e recuperação das preferências locais."""

import json
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

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


if __name__ == "__main__":
    unittest.main()
