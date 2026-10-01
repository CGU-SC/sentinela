"""
Remoção e recuperação coordenadas de farmácias e suas evidências.

Cópias:
* preferences.backup.json: lista anterior a cada gravação (a mais recente).
  É a fonte de "Restaurar backup".
* evidencias.backup.json: cesta anterior a cada gravação de evidências.
* watchlist.backup.json (cópia conjunta): lista e evidências antes da última
  remoção. Serve só ao "Desfazer remoção"; não é usada para restaurar a lista,
  porque só é regravada em remoções e pode estar muito desatualizada.
"""

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

from .evidencias import EvidenciasError, EvidenciasService, _chave
from .preferences import PreferencesError, PreferencesService


class RemocaoIndisponivelError(PreferencesError):
    """Não há remoção a desfazer para a farmácia pedida (HTTP 409)."""


class WatchlistRecoveryService:
    SCHEMA_VERSION = 1
    BACKUP_NAME = "watchlist.backup.json"

    @classmethod
    def _backup_path(cls):
        return PreferencesService.BASE_DIR / cls.BACKUP_NAME

    @staticmethod
    def _evidence_document(items):
        return {"schema_version": EvidenciasService.SCHEMA_VERSION, "evidencias": items}

    @staticmethod
    def _validate(preferences, items):
        cnpjs = [item["cnpj"] for item in preferences["watchlist"]]
        if len(cnpjs) != len(set(cnpjs)):
            raise ValueError("A lista contém farmácias duplicadas.")
        cnpjs = set(cnpjs)
        EvidenciasService._validar_arquivo(WatchlistRecoveryService._evidence_document(items))
        ids, keys = set(), set()
        for item in items:
            if item["cnpj"] not in cnpjs:
                raise ValueError("Há evidências de farmácias fora da lista. Corrija a associação antes de continuar.")
            key = _chave(item)
            if item["id"] in ids or key in keys:
                raise ValueError("A cesta contém evidências duplicadas.")
            ids.add(item["id"])
            keys.add(key)

    @classmethod
    def _read_evidence_path(cls, path):
        document = json.loads(path.read_text(encoding="utf-8"))
        if document["schema_version"] != EvidenciasService.SCHEMA_VERSION:
            raise ValueError("Versão do arquivo de evidências não suportada.")
        return EvidenciasService._validar_arquivo(document)

    @classmethod
    def _read_joint(cls):
        document = json.loads(cls._backup_path().read_text(encoding="utf-8"))
        if document["schema_version"] != cls.SCHEMA_VERSION:
            raise ValueError("Versão da cópia conjunta não suportada.")
        preferences = PreferencesService._normalize(document["preferences"])
        if document["preferences"]["schema_version"] != PreferencesService.SCHEMA_VERSION:
            raise ValueError("Versão das preferências da cópia não suportada.")
        evidence = document["evidencias"]
        if evidence["schema_version"] != EvidenciasService.SCHEMA_VERSION:
            raise ValueError("Versão das evidências da cópia não suportada.")
        items = EvidenciasService._validar_arquivo(evidence)
        cls._validate(preferences, items)
        return preferences, items

    @classmethod
    def _current_items(cls):
        path = EvidenciasService._file_path()
        return cls._read_evidence_path(path) if path.exists() else EvidenciasService._ler_unlocked()

    @staticmethod
    def _atomic_bytes(path: Path, content: bytes):
        temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
        try:
            with temporary.open("wb") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)

    @classmethod
    def _commit(cls, writes):
        """O bloqueio comum impede leituras intermediárias; falhas revertem os arquivos."""
        originals = {path: path.read_bytes() if path.exists() else None for path, _ in writes}
        attempted = []
        try:
            for path, document in writes:
                attempted.append(path)
                PreferencesService._atomic_write(path, document)
        except OSError as exc:
            try:
                for path in reversed(attempted):
                    content = originals[path]
                    if content is None:
                        path.unlink(missing_ok=True)
                    else:
                        cls._atomic_bytes(path, content)
            except OSError as rollback_error:
                raise PreferencesError(
                    "Falha na gravação e na reversão. Use a cópia de recuperação antes de continuar."
                ) from rollback_error
            raise PreferencesError("Não foi possível salvar a lista e as evidências. Os arquivos anteriores foram preservados.") from exc

    @staticmethod
    def _preferences_backup_writes(previous):
        """Cópia da lista anterior; uma lista vazia não apaga backup que ainda tem favoritos."""
        preserve = (not previous["watchlist"] and PreferencesService.BACKUP_PATH.exists()
                    and bool(PreferencesService._read_path(PreferencesService.BACKUP_PATH)["watchlist"]))
        return [] if preserve else [(PreferencesService.BACKUP_PATH, previous)]

    @classmethod
    def _save_unlocked(cls, previous, updated):
        updated = PreferencesService._normalize(updated)
        items = cls._current_items()
        cls._validate(previous, items)
        removed = {i["cnpj"] for i in previous["watchlist"]} - {i["cnpj"] for i in updated["watchlist"]}
        remaining = [item for item in items if item["cnpj"] not in removed]
        cls._validate(updated, remaining)
        writes = []
        if removed:
            writes.append((cls._backup_path(), {
                "schema_version": cls.SCHEMA_VERSION,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "preferences": previous,
                "evidencias": cls._evidence_document(items),
            }))
        writes.extend(cls._preferences_backup_writes(previous))
        if remaining != items:
            writes.extend([
                (EvidenciasService._backup_path(), cls._evidence_document(items)),
                (EvidenciasService._file_path(), cls._evidence_document(remaining)),
            ])
        writes.append((PreferencesService.FILE_PATH, updated))
        cls._commit(writes)
        return updated

    @classmethod
    def _operation(cls, operation):
        try:
            with PreferencesService._locked():
                return operation()
        except PreferencesError:
            raise
        except (OSError, ValueError, TypeError, KeyError, EvidenciasError) as exc:
            raise PreferencesError(f"Lista e evidências não puderam ser processadas: {exc}") from exc

    @classmethod
    def update_watchlist(cls, watchlist):
        def operation():
            previous = PreferencesService._read_unlocked()
            return cls._save_unlocked(previous, {**previous, "watchlist": watchlist})
        return cls._operation(operation)

    @classmethod
    def write_preferences(cls, preferences):
        return cls._operation(lambda: cls._save_unlocked(PreferencesService._read_unlocked(), preferences))

    @staticmethod
    def _missing_evidence_pharmacies(preferences, items):
        """CNPJs com evidências atuais que não estão na lista da cópia."""
        cnpjs = {i["cnpj"] for i in preferences["watchlist"]}
        return sorted({i["cnpj"] for i in items} - cnpjs)

    @classmethod
    def _keep_evidence_pharmacies(cls, preferences, items):
        """
        Farmácias com evidências atuais e fora da cópia continuam na lista
        restaurada, com o registro (nome, observação, datas) da lista atual.
        Sem lista atual legível não há de onde tirar o registro: falha visível.
        """
        missing = cls._missing_evidence_pharmacies(preferences, items)
        if not missing:
            return preferences
        try:
            current = PreferencesService._read_path(PreferencesService.FILE_PATH)
        except PreferencesError as exc:
            raise ValueError(
                f"{len(missing)} farmácia(s) têm evidências atuais e não estão nesta cópia, "
                "e a lista atual não pôde ser lida para mantê-las."
            ) from exc
        entries = {i["cnpj"]: i for i in current["watchlist"]}
        absent = [cnpj for cnpj in missing if cnpj not in entries]
        if absent:
            raise ValueError(
                f"{len(absent)} farmácia(s) têm evidências atuais, mas não estão na lista atual nem nesta cópia."
            )
        return {**preferences, "watchlist": [*preferences["watchlist"], *(entries[c] for c in missing)]}

    @classmethod
    def _restored_evidence(cls, preferences, include_backup):
        """
        Retorna (lista restaurada, evidências) para a cópia da lista escolhida.

        As evidências atuais são mantidas. Com include_backup (escolha explícita do
        usuário), as evidências ausentes das farmácias da cópia voltam do backup de
        evidências; se a cesta atual estiver ilegível, ela é substituída por esse
        backup (o arquivo atual é preservado em pre-restore antes da gravação).
        """
        if include_backup:
            backup = cls._read_evidence_path(EvidenciasService._backup_path())
            cnpjs = {i["cnpj"] for i in preferences["watchlist"]}
            selected = [i for i in backup if i["cnpj"] in cnpjs]
            cls._validate(preferences, selected)
            if not EvidenciasService._file_path().exists():
                # Recriação solicitada explicitamente a partir da cópia validada.
                return preferences, selected
            try:
                current = cls._current_items()
            except (ValueError, TypeError, KeyError):
                # Cesta atual ilegível: a restauração confirmada usa o backup de evidências.
                return preferences, selected
            ids = {i["id"]: _chave(i) for i in current}
            keys = {_chave(i) for i in current}
            if any(i["id"] in ids and ids[i["id"]] != _chave(i) for i in selected):
                raise ValueError("Um identificador de evidência representa registros diferentes nas cópias.")
            current = [*current, *(i for i in selected if _chave(i) not in keys)]
        else:
            current = cls._current_items()
        preferences = cls._keep_evidence_pharmacies(preferences, current)
        cls._validate(preferences, current)
        return preferences, current

    @classmethod
    def restore(cls, source, include_evidence_backup=False):
        if source not in ("backup", "corrupt"):
            raise PreferencesError("Fonte de recuperação inválida.")

        def operation():
            path = PreferencesService.BACKUP_PATH if source == "backup" else PreferencesService.CORRUPT_PATH
            preferences, items = cls._restored_evidence(PreferencesService._read_path(path), include_evidence_backup)
            # Preserva ambos os arquivos atuais, inclusive se estiverem corrompidos.
            archive_id = uuid.uuid4().hex
            for path in (PreferencesService.FILE_PATH, EvidenciasService._file_path()):
                if path.exists():
                    archive = path.with_name(f"{path.stem}.pre-restore.{archive_id}.json")
                    cls._atomic_bytes(archive, path.read_bytes())
            cls._commit([
                (EvidenciasService._file_path(), cls._evidence_document(items)),
                (PreferencesService.FILE_PATH, preferences),
            ])
            return preferences
        return cls._operation(operation)

    @classmethod
    def recovery_status(cls):
        def operation():
            result = {}
            current_preferences, current_items = None, None
            current_error = None
            try:
                current_preferences = PreferencesService._read_path(PreferencesService.FILE_PATH)
                current_items = cls._current_items()
                cls._validate(current_preferences, current_items)
            except (PreferencesError, EvidenciasError, OSError, ValueError, TypeError, KeyError) as exc:
                current_items = None
                current_error = str(exc)
            for source, path in (("principal", PreferencesService.FILE_PATH),
                                 ("backup", PreferencesService.BACKUP_PATH),
                                 ("corrupt", PreferencesService.CORRUPT_PATH)):
                metadata = {"exists": path.exists(), "valid": False,
                            "kind": "separate", "watchlist_count": None,
                            "evidencias_count": None, "evidencias_backup_valid": False,
                            "missing_watchlist_count": None, "missing_evidencias_count": None,
                            "farmacias_mantidas_count": None}
                result[source] = metadata
                if source == "principal" and current_error:
                    metadata["evidencias_error"] = current_error
                if not path.exists():
                    continue
                try:
                    preferences = PreferencesService._read_path(path)
                    items = None
                    if source != "principal" and EvidenciasService._backup_path().exists():
                        try:
                            backup = cls._read_evidence_path(EvidenciasService._backup_path())
                            cnpjs = {i["cnpj"] for i in preferences["watchlist"]}
                            items = [i for i in backup if i["cnpj"] in cnpjs]
                            cls._validate(preferences, items)
                            metadata["evidencias_backup_valid"] = True
                            metadata["evidencias_count"] = len(items)
                        except (OSError, ValueError, TypeError, KeyError) as exc:
                            metadata["evidencias_error"] = str(exc)
                    metadata.update(valid=True, watchlist_count=len(preferences["watchlist"]))
                    if current_preferences is not None:
                        cnpjs = {i["cnpj"] for i in current_preferences["watchlist"]}
                        metadata["missing_watchlist_count"] = sum(i["cnpj"] not in cnpjs for i in preferences["watchlist"])
                    if current_items is not None and source != "principal":
                        # A restauração separada mantém essas farmácias na lista (_keep_evidence_pharmacies).
                        metadata["farmacias_mantidas_count"] = len(
                            cls._missing_evidence_pharmacies(preferences, current_items)
                        )
                    if items is not None and current_items is not None:
                        # Só conta como perdida a evidência de farmácia ainda monitorada:
                        # a da farmácia removida pelo usuário saiu junto, de propósito.
                        keys = {_chave(i) for i in current_items}
                        monitoradas = {i["cnpj"] for i in current_preferences["watchlist"]}
                        metadata["missing_evidencias_count"] = sum(
                            _chave(i) not in keys and i["cnpj"] in monitoradas for i in items
                        )
                except (PreferencesError, OSError, ValueError, TypeError, KeyError) as exc:
                    metadata["error"] = str(exc)
            return result
        return cls._operation(operation)

    @classmethod
    def last_removal(cls):
        """
        Farmácias da última remoção que continuam fora da lista, para o "Desfazer".
        A cópia conjunta é regravada a cada remoção, então só a última conta.
        """
        def operation():
            if not cls._backup_path().exists():
                return {"removido_em": None, "farmacias": []}
            created_at = json.loads(cls._backup_path().read_text(encoding="utf-8"))["created_at"]
            snapshot, items = cls._read_joint()
            current = {i["cnpj"] for i in PreferencesService._read_unlocked()["watchlist"]}
            farmacias = [
                {"cnpj": entry["cnpj"], "razaoSocial": entry.get("razaoSocial") or "",
                 "evidencias_count": sum(i["cnpj"] == entry["cnpj"] for i in items)}
                for entry in snapshot["watchlist"] if entry["cnpj"] not in current
            ]
            return {"removido_em": created_at if farmacias else None, "farmacias": farmacias}
        return cls._operation(operation)

    @classmethod
    def undo_removal(cls, cnpj):
        """
        Devolve à lista só a farmácia pedida, com o registro e as evidências da
        cópia da última remoção. O resto da lista e das evidências não muda.
        """
        def operation():
            if not cls._backup_path().exists():
                raise RemocaoIndisponivelError("Não há remoção para desfazer.")
            snapshot, snapshot_items = cls._read_joint()
            entry = next((i for i in snapshot["watchlist"] if i["cnpj"] == cnpj), None)
            if entry is None:
                raise RemocaoIndisponivelError("Esta farmácia não faz parte da última remoção.")
            previous = PreferencesService._read_unlocked()
            if any(i["cnpj"] == cnpj for i in previous["watchlist"]):
                raise RemocaoIndisponivelError("Esta farmácia já está nas Farmácias Monitoradas.")
            items = cls._current_items()
            cls._validate(previous, items)
            ids = {i["id"] for i in items}
            keys = {_chave(i) for i in items}
            restored = [i for i in snapshot_items if i["cnpj"] == cnpj and _chave(i) not in keys]
            if any(i["id"] in ids for i in restored):
                raise ValueError("Um identificador de evidência representa registros diferentes nas cópias.")
            updated = {**previous, "watchlist": [*previous["watchlist"], entry]}
            new_items = [*items, *restored]
            cls._validate(updated, new_items)
            writes = cls._preferences_backup_writes(previous)
            if restored:
                writes.extend([
                    (EvidenciasService._backup_path(), cls._evidence_document(items)),
                    (EvidenciasService._file_path(), cls._evidence_document(new_items)),
                ])
            writes.append((PreferencesService.FILE_PATH, updated))
            cls._commit(writes)
            return updated
        return cls._operation(operation)
