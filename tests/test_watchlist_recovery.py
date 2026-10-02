"""Recuperação conjunta: arquivos temporários, sem tocar nas preferências reais."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.api.services.evidencias import EvidenciasService
from backend.api.services.preferences import PreferencesError, PreferencesService
from backend.api.services.watchlist_recovery import RemocaoIndisponivelError, WatchlistRecoveryService as Recovery


class WatchlistRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.original_dir = PreferencesService.BASE_DIR
        PreferencesService._set_base_dir(Path(self.temp.name))
        self.a = {"cnpj": "00000000000001", "observacao": "acompanhar"}
        self.b = {"cnpj": "00000000000002"}
        self.ea = self.evidence("a", self.a["cnpj"])
        self.eb = self.evidence("b", self.b["cnpj"])
        self.preferences = {**PreferencesService.default_preferences(), "watchlist": [self.a, self.b]}
        self.write(PreferencesService.FILE_PATH, self.preferences)
        self.write(EvidenciasService._file_path(), Recovery._evidence_document([self.ea, self.eb]))

    def tearDown(self):
        PreferencesService._set_base_dir(self.original_dir)
        self.temp.cleanup()

    @staticmethod
    def evidence(identifier, cnpj):
        return {"id": identifier, "cnpj": cnpj, "tipo": "dia", "dt_janela": "2026-09-01",
                "criado_em": "2026-09-02T10:00:00Z", "nota": "nota preservada",
                "snapshot": {"valor": 123.45}}

    @staticmethod
    def write(path, data):
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    def files(self):
        return {p.name: p.read_bytes() for p in PreferencesService.BASE_DIR.glob("*.json")}

    def test_remove_and_restore_exact_evidence_and_pharmacy(self):
        Recovery.update_watchlist([self.b])
        self.assertEqual(EvidenciasService.listar(), [self.eb])
        snapshot = Recovery._read_joint()
        self.assertEqual(snapshot, (self.preferences, [self.ea, self.eb]))
        recovered = Recovery.restore("backup", True)
        self.assertEqual(recovered, self.preferences)
        self.assertCountEqual(EvidenciasService.listar(), [self.ea, self.eb])
        self.assertEqual(len(list(PreferencesService.BASE_DIR.glob("*.pre-restore.*.json"))), 2)
        self.assertEqual(Recovery._read_joint(), snapshot)

    def test_restore_uses_most_recent_list_not_last_removal(self):
        """Cópia conjunta antiga não pode trazer de volta a farmácia removida nem apagar as novas."""
        c = {"cnpj": "00000000000003"}
        d = {"cnpj": "00000000000004"}
        Recovery.update_watchlist([self.b])            # remove a: cópia conjunta = [a, b]
        Recovery.update_watchlist([self.b, c])
        Recovery.update_watchlist([self.b, c, d])      # preferences.backup.json = [b, c]
        PreferencesService.FILE_PATH.write_text("{corrompido", encoding="utf-8")
        status = Recovery.recovery_status()["backup"]
        self.assertEqual((status["kind"], status["watchlist_count"]), ("separate", 2))
        restored = Recovery.restore("backup")
        self.assertEqual([i["cnpj"] for i in restored["watchlist"]], [self.b["cnpj"], c["cnpj"]])

    def test_separate_changes_cannot_overwrite_joint_snapshot(self):
        """A cópia da última remoção não muda com outras gravações e o Desfazer usa ela."""
        Recovery.update_watchlist([self.b])
        before = Recovery._backup_path().read_bytes()
        PreferencesService.update_filters({"uf": "SC"})
        PreferencesService.update_ui({"theme": "dark"})
        EvidenciasService.atualizar_nota("b", "nova nota")
        Recovery.update_watchlist([{**self.b, "observacao": "nova observação"}])
        self.assertEqual(Recovery._backup_path().read_bytes(), before)
        Recovery.undo_removal(self.a["cnpj"])
        self.assertCountEqual([i["id"] for i in EvidenciasService.listar()], ["a", "b"])

    def test_remove_without_evidence_still_has_complete_snapshot(self):
        self.write(EvidenciasService._file_path(), Recovery._evidence_document([self.eb]))
        Recovery.update_watchlist([self.b])
        self.assertEqual(Recovery._read_joint()[1], [self.eb])

    def test_full_preferences_write_also_coordinates_removal(self):
        Recovery.write_preferences({**self.preferences, "watchlist": [self.b]})
        self.assertEqual(EvidenciasService.listar(), [self.eb])
        self.assertEqual(Recovery._read_joint()[0], self.preferences)

    def test_failed_removal_rolls_back_every_json_file(self):
        before = self.files()
        original = PreferencesService._atomic_write

        def failing(path, data):
            if path == PreferencesService.FILE_PATH:
                raise OSError("disco indisponível")
            original(path, data)

        with patch.object(PreferencesService, "_atomic_write", side_effect=failing):
            with self.assertRaises(PreferencesError):
                Recovery.update_watchlist([self.b])
        self.assertEqual(self.files(), before)

    def test_failed_restore_preserves_current_files_and_snapshot(self):
        Recovery.update_watchlist([self.b])
        before = self.files()
        original = PreferencesService._atomic_write

        def failing(path, data):
            if path == PreferencesService.FILE_PATH:
                raise OSError("disco indisponível")
            original(path, data)

        with patch.object(PreferencesService, "_atomic_write", side_effect=failing):
            with self.assertRaises(PreferencesError):
                Recovery.restore("backup")
        after = self.files()
        for name, content in before.items():
            self.assertEqual(after[name], content)
        self.assertEqual(len(after), len(before) + 2)  # arquivos preservados antes da tentativa

    def test_invalid_joint_only_blocks_undo(self):
        """Cópia conjunta inválida: o Desfazer falha visível; a restauração usa a cópia da lista."""
        Recovery.update_watchlist([self.b])
        self.write(Recovery._backup_path(), {"schema_version": 1, "preferences": self.preferences})
        before = self.files()
        with self.assertRaises(PreferencesError):
            Recovery.last_removal()
        with self.assertRaises(PreferencesError):
            Recovery.undo_removal(self.a["cnpj"])
        self.assertEqual(self.files(), before)
        self.assertTrue(Recovery.recovery_status()["backup"]["valid"])
        self.assertEqual(Recovery.restore("backup", True), self.preferences)

    def test_validation_rejects_duplicate_pharmacies_or_unowned_duplicate_evidence(self):
        duplicate_preferences = {
            **self.preferences,
            "watchlist": [self.a, {"cnpj": self.a["cnpj"]}],
        }
        with self.assertRaisesRegex(ValueError, "farmácias duplicadas"):
            Recovery._validate(duplicate_preferences, [])

        with self.assertRaisesRegex(ValueError, "fora da lista"):
            Recovery._validate(
                {**self.preferences, "watchlist": [self.a]},
                [self.eb],
            )
        with self.assertRaisesRegex(ValueError, "evidências duplicadas"):
            Recovery._validate(self.preferences, [self.ea, self.ea])

    def test_readers_reject_unsupported_evidence_and_joint_snapshot_versions(self):
        evidence_path = EvidenciasService._file_path()
        self.write(evidence_path, {"schema_version": 999, "evidencias": []})
        with self.assertRaisesRegex(ValueError, "Versão do arquivo de evidências"):
            Recovery._read_evidence_path(evidence_path)

        joint_path = Recovery._backup_path()
        self.write(joint_path, {"schema_version": 999})
        with self.assertRaisesRegex(ValueError, "Versão da cópia conjunta"):
            Recovery._read_joint()

        self.write(
            joint_path,
            {
                "schema_version": Recovery.SCHEMA_VERSION,
                "preferences": {**self.preferences, "schema_version": 999},
                "evidencias": Recovery._evidence_document([]),
            },
        )
        with self.assertRaisesRegex(ValueError, "Versão das preferências"):
            Recovery._read_joint()

        self.write(
            joint_path,
            {
                "schema_version": Recovery.SCHEMA_VERSION,
                "preferences": self.preferences,
                "evidencias": {"schema_version": 999, "evidencias": []},
            },
        )
        with self.assertRaisesRegex(ValueError, "Versão das evidências"):
            Recovery._read_joint()

    def test_joint_commit_reports_failure_when_rollback_also_fails(self):
        first = PreferencesService.BASE_DIR / "first.json"
        second = PreferencesService.BASE_DIR / "second.json"
        first.write_bytes(b"first-original")
        second.write_bytes(b"second-original")

        def write_with_second_failure(path, data):
            if path == second:
                raise OSError("second write failed")
            path.write_text(json.dumps(data), encoding="utf-8")

        with patch.object(PreferencesService, "_atomic_write", side_effect=write_with_second_failure), patch.object(
            Recovery, "_atomic_bytes", side_effect=OSError("rollback failed")
        ):
            with self.assertRaisesRegex(PreferencesError, "gravação e na reversão"):
                Recovery._commit([(first, {"updated": True}), (second, {"updated": True})])

    def test_restore_rejects_evidence_outside_both_backup_and_current_lists(self):
        self.legacy([self.eb])
        only_a = {**self.preferences, "watchlist": [self.a]}
        self.write(PreferencesService.BACKUP_PATH, only_a)
        self.write(PreferencesService.FILE_PATH, only_a)

        with self.assertRaisesRegex(PreferencesError, "lista atual nem nesta cópia"):
            Recovery.restore("backup", True)

    def test_restore_rejects_same_evidence_id_with_different_record_content(self):
        self.legacy([self.ea])
        changed_a = {**self.ea, "dt_janela": "2026-09-03"}
        self.write(EvidenciasService._file_path(), Recovery._evidence_document([changed_a]))

        with self.assertRaisesRegex(PreferencesError, "identificador de evidência representa registros diferentes"):
            Recovery.restore("backup", True)

    def test_restore_rejects_unknown_source(self):
        with self.assertRaisesRegex(PreferencesError, "Fonte de recuperação inválida"):
            Recovery.restore("principal")

    def test_recovery_status_reports_invalid_evidence_backup_without_hiding_list_backup(self):
        self.write(PreferencesService.BACKUP_PATH, self.preferences)
        EvidenciasService._backup_path().write_text("{broken", encoding="utf-8")

        status = Recovery.recovery_status()["backup"]

        self.assertTrue(status["valid"])
        self.assertFalse(status["evidencias_backup_valid"])
        self.assertIn("evidencias_error", status)

    def legacy(self, current_items):
        self.write(PreferencesService.BACKUP_PATH, self.preferences)
        self.write(EvidenciasService._backup_path(), Recovery._evidence_document([self.ea, self.eb]))
        self.write(EvidenciasService._file_path(), Recovery._evidence_document(current_items))

    def test_legacy_requires_explicit_evidence_inclusion_and_keeps_current_notes(self):
        current_b = {**self.eb, "nota": "nota mais recente"}
        self.legacy([current_b])
        Recovery.restore("backup")
        self.assertEqual(EvidenciasService.listar(), [current_b])
        Recovery.restore("backup", True)
        self.assertCountEqual(EvidenciasService.listar(), [self.ea, current_b])

    def test_status_identifies_lost_evidence_when_pharmacy_already_restored(self):
        self.legacy([])
        status = Recovery.recovery_status()["backup"]
        self.assertEqual(status["kind"], "separate")
        self.assertEqual(status["missing_watchlist_count"], 0)
        self.assertEqual(status["missing_evidencias_count"], 2)
        self.assertEqual(status["evidencias_count"], 2)
        self.assertNotIn(self.a["cnpj"], json.dumps(status))

    def test_legacy_missing_or_corrupt_evidence_backup_fails_without_changes(self):
        self.legacy([])
        for content in (None, '{"evidencias":'):
            if content is None:
                EvidenciasService._backup_path().unlink()
            else:
                EvidenciasService._backup_path().write_text(content, encoding="utf-8")
            before = self.files()
            with self.assertRaises(PreferencesError):
                Recovery.restore("backup", True)
            self.assertEqual(self.files(), before)

    def test_legacy_does_not_import_evidence_outside_restored_list(self):
        self.legacy([])
        self.write(PreferencesService.BACKUP_PATH, {**self.preferences, "watchlist": [self.a]})
        Recovery.restore("backup", True)
        self.assertEqual(EvidenciasService.listar(), [self.ea])

    def test_legacy_explicit_restore_recovers_missing_main_evidence_file(self):
        self.legacy([])
        EvidenciasService._file_path().unlink()
        with self.assertRaises(PreferencesError):
            Recovery.restore("backup")
        self.assertFalse(EvidenciasService._file_path().exists())
        Recovery.restore("backup", True)
        self.assertEqual(EvidenciasService.listar(), [self.ea, self.eb])

    def test_duplicate_evidence_is_rejected_before_any_write(self):
        self.write(EvidenciasService._file_path(), Recovery._evidence_document([self.ea, self.ea]))
        before = self.files()
        with self.assertRaises(PreferencesError):
            Recovery.update_watchlist([self.b])
        self.assertEqual(self.files(), before)
        self.assertIn("evidencias_error", Recovery.recovery_status()["principal"])

    def test_legacy_keeps_pharmacies_with_current_evidence(self):
        """Evidência atual de farmácia fora da cópia: a farmácia continua na lista restaurada."""
        self.legacy([self.eb])
        self.write(PreferencesService.BACKUP_PATH, {**self.preferences, "watchlist": [self.a]})
        self.assertEqual(Recovery.recovery_status()["backup"]["farmacias_mantidas_count"], 1)
        restored = Recovery.restore("backup", True)
        self.assertEqual(restored["watchlist"], [self.a, self.b])  # registro de b vem da lista atual
        self.assertCountEqual(EvidenciasService.listar(), [self.ea, self.eb])

    def test_legacy_keep_fails_visibly_without_readable_current_list(self):
        self.legacy([self.eb])
        self.write(PreferencesService.BACKUP_PATH, {**self.preferences, "watchlist": [self.a]})
        PreferencesService.FILE_PATH.write_text("{", encoding="utf-8")
        before = self.files()
        with self.assertRaisesRegex(PreferencesError, "não estão nesta cópia"):
            Recovery.restore("backup")
        self.assertEqual(self.files(), before)

    def test_status_ignores_intentional_removal(self):
        """Remover de propósito não é perda: evidências da farmácia removida não contam."""
        Recovery.update_watchlist([self.b])
        status = Recovery.recovery_status()["backup"]
        self.assertEqual(status["kind"], "separate")
        self.assertEqual(status["missing_watchlist_count"], 1)
        self.assertEqual(status["missing_evidencias_count"], 0)
        self.assertEqual(status["farmacias_mantidas_count"], 0)

    def test_status_counts_lost_evidence_of_monitored_pharmacy(self):
        Recovery.update_watchlist([self.b])
        self.write(EvidenciasService._file_path(), Recovery._evidence_document([]))
        self.assertEqual(Recovery.recovery_status()["backup"]["missing_evidencias_count"], 1)

    def test_undo_restores_only_the_removed_pharmacy(self):
        """Mudanças depois da remoção sobrevivem ao Desfazer."""
        c = {"cnpj": "00000000000003", "razaoSocial": "Farmácia C"}
        self.assertEqual(Recovery.last_removal(), {"removido_em": None, "farmacias": []})
        Recovery.update_watchlist([self.b])
        Recovery.update_watchlist([self.b, c])
        ec = EvidenciasService.criar({"cnpj": c["cnpj"], "tipo": "dia", "dt_janela": "2026-09-03", "nota": ""})
        EvidenciasService.atualizar_nota("b", "nota nova")
        removal = Recovery.last_removal()
        self.assertIsNotNone(removal["removido_em"])
        self.assertEqual(removal["farmacias"], [{"cnpj": self.a["cnpj"], "razaoSocial": "", "evidencias_count": 1}])
        updated = Recovery.undo_removal(self.a["cnpj"])
        self.assertEqual(updated["watchlist"], [self.b, c, self.a])
        nota_b = {**self.eb, "nota": "nota nova"}
        current = {i["id"]: i for i in EvidenciasService.listar()}
        self.assertEqual(set(current), {"a", "b", ec["id"]})
        self.assertEqual(current["a"], self.ea)
        self.assertEqual(current["b"]["nota"], nota_b["nota"])
        self.assertEqual(Recovery.last_removal()["farmacias"], [])

    def test_undo_conflicts_change_nothing(self):
        with self.assertRaises(RemocaoIndisponivelError):
            Recovery.undo_removal(self.a["cnpj"])  # nenhuma remoção ainda
        Recovery.update_watchlist([self.b])
        before = self.files()
        for cnpj in (self.b["cnpj"], "00000000000009"):  # ainda na lista; fora da remoção
            with self.assertRaises(RemocaoIndisponivelError):
                Recovery.undo_removal(cnpj)
        self.assertEqual(self.files(), before)
        Recovery.undo_removal(self.a["cnpj"])
        with self.assertRaises(RemocaoIndisponivelError):
            Recovery.undo_removal(self.a["cnpj"])  # já desfeita

    def test_undo_rejects_evidence_id_reused_for_a_different_pharmacy(self):
        Recovery.update_watchlist([self.b])
        conflicting = self.evidence("a", self.b["cnpj"])
        self.write(EvidenciasService._file_path(), Recovery._evidence_document([conflicting]))
        before = self.files()

        with self.assertRaisesRegex(PreferencesError, "identificador de evidência representa registros diferentes"):
            Recovery.undo_removal(self.a["cnpj"])

        self.assertEqual(self.files(), before)

    def test_first_use_without_evidence_file_is_not_an_error(self):
        EvidenciasService._file_path().unlink()
        Recovery.update_watchlist([self.b])
        self.assertEqual(Recovery._read_joint()[1], [])

    def test_restore_can_recover_corrupt_main_evidence(self):
        Recovery.update_watchlist([self.b])
        EvidenciasService._file_path().write_text("corrompido", encoding="utf-8")
        with self.assertRaises(PreferencesError):
            Recovery.restore("backup")  # sem o backup de evidências não há como manter a cesta ilegível
        Recovery.restore("backup", True)
        self.assertEqual(EvidenciasService.listar(), [self.ea, self.eb])
        archives = list(PreferencesService.BASE_DIR.glob("evidencias.pre-restore.*.json"))
        self.assertEqual(archives[0].read_text(encoding="utf-8"), "corrompido")


if __name__ == "__main__":
    unittest.main()
