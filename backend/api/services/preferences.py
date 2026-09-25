"""Persistência segura das preferências locais do Sentinela."""

import json
import logging
import os
import sys
import threading
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


class PreferencesError(RuntimeError):
    """Falha de armazenamento que não deve ser ocultada pela API."""


def _preferences_dir() -> Path:
    override = os.getenv("SENTINELA_PREFERENCES_DIR")
    if override:
        return Path(override)
    if getattr(sys, "frozen", False):
        local_app_data = os.getenv("LOCALAPPDATA")
        if not local_app_data:
            raise PreferencesError("LOCALAPPDATA não está definido; preferências indisponíveis.")
        return Path(local_app_data) / "Sentinela" / "preferences"
    return Path(__file__).resolve().parents[3] / "modules" / "user_preferences"


class PreferencesService:
    SCHEMA_VERSION = 1
    BASE_DIR = _preferences_dir()
    FILE_PATH = BASE_DIR / "preferences.json"
    BACKUP_PATH = BASE_DIR / "preferences.backup.json"
    CORRUPT_PATH = BASE_DIR / "preferences.corrupt.json"
    _thread_lock = threading.RLock()

    @classmethod
    def _set_base_dir(cls, base_dir: Path) -> None:
        cls.BASE_DIR = base_dir
        cls.FILE_PATH = base_dir / "preferences.json"
        cls.BACKUP_PATH = base_dir / "preferences.backup.json"
        cls.CORRUPT_PATH = base_dir / "preferences.corrupt.json"

    @classmethod
    @contextmanager
    def _locked(cls):
        """Protege a transação inclusive entre dois processos Desktop."""
        with cls._thread_lock:
            try:
                cls.BASE_DIR.mkdir(parents=True, exist_ok=True)
                handle = (cls.BASE_DIR / ".preferences.lock").open("a+b")
            except OSError as exc:
                logger.exception("Falha ao abrir bloqueio em %s", cls.BASE_DIR)
                raise PreferencesError("Não foi possível acessar as preferências do usuário.") from exc
            try:
                if os.name == "nt":
                    import msvcrt
                    handle.seek(0)
                    if handle.read(1) != b"\0":
                        handle.seek(0)
                        handle.write(b"\0")
                        handle.flush()
                    deadline = time.monotonic() + 5
                    while True:
                        try:
                            handle.seek(0)
                            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                            break
                        except OSError as exc:
                            if time.monotonic() >= deadline:
                                raise PreferencesError("Preferências ocupadas por outra instância. Tente novamente.") from exc
                            time.sleep(0.05)
                else:
                    import fcntl
                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
                try:
                    yield
                finally:
                    if os.name == "nt":
                        handle.seek(0)
                        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                    else:
                        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            finally:
                handle.close()

    @classmethod
    def default_preferences(cls) -> Dict[str, Any]:
        return {"schema_version": cls.SCHEMA_VERSION, "filters": {}, "watchlist": [],
                "ui": {}, "nota_tecnica": {}, "metodologia": {}}

    @classmethod
    def _normalize(cls, data: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(data, dict) or not isinstance(data.get("watchlist"), list):
            raise ValueError("O campo obrigatório watchlist deve ser uma lista.")
        if any(not isinstance(item, dict) or not isinstance(item.get("cnpj"), str)
               or not item["cnpj"] for item in data["watchlist"]):
            raise ValueError("A lista de farmácias monitoradas contém um registro inválido.")
        normalized = cls.default_preferences()
        normalized["schema_version"] = int(data.get("schema_version") or cls.SCHEMA_VERSION)
        normalized["watchlist"] = data["watchlist"]
        for key in ("filters", "ui", "nota_tecnica", "metodologia"):
            value = data.get(key, {})
            if not isinstance(value, dict):
                raise ValueError(f"O campo {key} deve ser um objeto.")
            normalized[key] = value
        return normalized

    @classmethod
    def _read_path(cls, path: Path) -> Dict[str, Any]:
        for attempt in range(3):
            try:
                with path.open("r", encoding="utf-8") as file:
                    return cls._normalize(json.load(file))
            except OSError as exc:
                if attempt < 2:
                    time.sleep(0.1)
                    continue
                logger.exception("Falha de leitura em %s", path)
                raise PreferencesError("Não foi possível ler as preferências. Seus dados não foram alterados.") from exc
            except (json.JSONDecodeError, UnicodeError, ValueError, TypeError) as exc:
                logger.error("Preferências inválidas em %s: %s", path, exc)
                raise PreferencesError("As preferências não puderam ser interpretadas. Seus dados não foram alterados.") from exc

    @classmethod
    def _atomic_write(cls, path: Path, data: Dict[str, Any]) -> None:
        tmp_path = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
        try:
            with tmp_path.open("w", encoding="utf-8") as file:
                json.dump(data, file, ensure_ascii=False, indent=2)
                file.write("\n")
                file.flush()
                os.fsync(file.fileno())
            os.replace(tmp_path, path)
        finally:
            tmp_path.unlink(missing_ok=True)

    @classmethod
    def _read_unlocked(cls) -> Dict[str, Any]:
        if not cls.FILE_PATH.exists():
            if cls.BACKUP_PATH.exists() or cls.CORRUPT_PATH.exists():
                raise PreferencesError("Arquivo principal ausente. Há cópias para recuperação; nenhuma lista foi recriada.")
            data = cls.default_preferences()
            cls._atomic_write(cls.FILE_PATH, data)
            return data
        return cls._read_path(cls.FILE_PATH)

    @classmethod
    def _write_unlocked(cls, data: Dict[str, Any], previous: Dict[str, Any]) -> Dict[str, Any]:
        normalized = cls._normalize(data)
        if cls.FILE_PATH.exists():
            # Uma lista vazia após um incidente não pode apagar o último
            # backup que ainda contém favoritos durante uma gravação de filtros/UI.
            preserve_backup = False
            if not previous["watchlist"] and cls.BACKUP_PATH.exists():
                preserve_backup = bool(cls._read_path(cls.BACKUP_PATH)["watchlist"])
            if not preserve_backup:
                cls._atomic_write(cls.BACKUP_PATH, previous)
        cls._atomic_write(cls.FILE_PATH, normalized)
        return normalized

    @classmethod
    def read(cls) -> Dict[str, Any]:
        with cls._locked():
            try:
                return cls._read_unlocked()
            except OSError as exc:
                logger.exception("Falha ao iniciar preferências em %s", cls.FILE_PATH)
                raise PreferencesError("Não foi possível acessar as preferências do usuário.") from exc

    @classmethod
    def write(cls, data: Dict[str, Any]) -> Dict[str, Any]:
        with cls._locked():
            try:
                return cls._write_unlocked(data, cls._read_unlocked())
            except (OSError, ValueError, TypeError) as exc:
                logger.exception("Falha ao gravar preferências em %s", cls.FILE_PATH)
                raise PreferencesError("Não foi possível salvar as preferências. A alteração não foi confirmada.") from exc

    @classmethod
    def _update(cls, field: str, value: Any, merge: bool = False) -> Dict[str, Any]:
        with cls._locked():
            try:
                data = cls._read_unlocked()
                updated = dict(data)
                updated[field] = {**data[field], **value} if merge else value
                return cls._write_unlocked(updated, data)
            except (OSError, ValueError, TypeError) as exc:
                logger.exception("Falha ao atualizar %s em %s", field, cls.FILE_PATH)
                raise PreferencesError("Não foi possível salvar as preferências. A alteração não foi confirmada.") from exc

    @classmethod
    def recovery_status(cls) -> Dict[str, Any]:
        with cls._locked():
            result = {}
            for source, path in (("principal", cls.FILE_PATH), ("backup", cls.BACKUP_PATH), ("corrupt", cls.CORRUPT_PATH)):
                if not path.exists():
                    result[source] = {"exists": False, "valid": False, "watchlist_count": None}
                    continue
                try:
                    data = cls._read_path(path)
                    result[source] = {"exists": True, "valid": True, "watchlist_count": len(data["watchlist"])}
                except PreferencesError:
                    result[source] = {"exists": True, "valid": False, "watchlist_count": None}
            return result

    @classmethod
    def restore(cls, source: str) -> Dict[str, Any]:
        if source not in ("backup", "corrupt"):
            raise PreferencesError("Fonte de recuperação inválida.")
        with cls._locked():
            data = cls._read_path(cls.BACKUP_PATH if source == "backup" else cls.CORRUPT_PATH)
            try:
                if cls.FILE_PATH.exists():
                    archive = cls.BASE_DIR / f"preferences.pre-restore.{uuid.uuid4().hex}.json"
                    archive.write_bytes(cls.FILE_PATH.read_bytes())
                cls._atomic_write(cls.FILE_PATH, data)
                return data
            except OSError as exc:
                logger.exception("Falha ao restaurar preferências de %s", source)
                raise PreferencesError("Não foi possível restaurar as preferências. Os arquivos originais foram preservados.") from exc

    @classmethod
    def update_filters(cls, filters: Dict[str, Any]) -> Dict[str, Any]:
        return cls._update("filters", filters)

    @classmethod
    def update_watchlist(cls, watchlist: List[Dict[str, Any]]) -> Dict[str, Any]:
        return cls._update("watchlist", watchlist)

    @classmethod
    def update_ui(cls, ui: Dict[str, Any]) -> Dict[str, Any]:
        return cls._update("ui", ui, merge=True)

    @classmethod
    def update_nota_tecnica(cls, nota_tecnica: Dict[str, Any]) -> Dict[str, Any]:
        return cls._update("nota_tecnica", nota_tecnica)

    @classmethod
    def update_metodologia(cls, metodologia: Dict[str, Any]) -> Dict[str, Any]:
        return cls._update("metodologia", metodologia, merge=True)
