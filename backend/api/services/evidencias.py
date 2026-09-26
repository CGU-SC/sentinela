"""Cesta de evidências: marcações do auditor persistidas localmente.

Fica ao lado do ``preferences.json`` (mesma pasta e mesmo bloqueio entre
processos), mas em arquivo próprio, porque cresce com o uso e não deve
arriscar a lista de Farmácias Monitoradas.
"""

import json
import logging
import os
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .preferences import PreferencesError, PreferencesService

logger = logging.getLogger(__name__)

TIPOS_EVIDENCIA = ("dia", "hora", "autorizacao")
_CAMPOS_OBRIGATORIOS = ("id", "cnpj", "tipo", "dt_janela", "criado_em")


class EvidenciasError(RuntimeError):
    """Falha de armazenamento que deve aparecer para o usuário (HTTP 503)."""


class EvidenciaNaoEncontradaError(LookupError):
    """A evidência pedida não existe mais (HTTP 404)."""


class EvidenciaDuplicadaError(ValueError):
    """O mesmo item já foi marcado para este CNPJ (HTTP 409)."""


def _agora() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _chave(item: Dict[str, Any]) -> Tuple[Any, ...]:
    """Identidade do item marcado: o mesmo dia/hora/autorização só entra uma vez."""
    tipo = item["tipo"]
    if tipo == "dia":
        return (item["cnpj"], tipo, item["dt_janela"])
    if tipo == "hora":
        return (item["cnpj"], tipo, item["dt_janela"], item["hora"])
    return (item["cnpj"], tipo, item["num_autorizacao"])


class EvidenciasService:
    SCHEMA_VERSION = 1
    FILE_NAME = "evidencias.json"
    BACKUP_NAME = "evidencias.backup.json"

    # Os caminhos acompanham a pasta das preferências (inclusive nos testes).
    @classmethod
    def _file_path(cls) -> Path:
        return PreferencesService.BASE_DIR / cls.FILE_NAME

    @classmethod
    def _backup_path(cls) -> Path:
        return PreferencesService.BASE_DIR / cls.BACKUP_NAME

    @classmethod
    def _locked(cls):
        return PreferencesService._locked()

    # ── Leitura e escrita ─────────────────────────────────────────────────
    @classmethod
    def _validar_arquivo(cls, data: Any) -> List[Dict[str, Any]]:
        if not isinstance(data, dict) or not isinstance(data.get("evidencias"), list):
            raise ValueError("O campo obrigatório evidencias deve ser uma lista.")
        for item in data["evidencias"]:
            if not isinstance(item, dict) or any(not item.get(campo) for campo in _CAMPOS_OBRIGATORIOS):
                raise ValueError("A cesta de evidências contém um registro incompleto.")
            if item["tipo"] not in TIPOS_EVIDENCIA:
                raise ValueError(f"Tipo de evidência desconhecido: {item['tipo']}.")
        return data["evidencias"]

    @classmethod
    def _ler_unlocked(cls) -> List[Dict[str, Any]]:
        path = cls._file_path()
        if not path.exists():
            if cls._backup_path().exists():
                raise EvidenciasError(
                    "O arquivo de evidências não foi encontrado, mas há uma cópia de segurança. "
                    "Nenhuma cesta vazia foi criada; restaure a cópia antes de continuar."
                )
            return []
        for attempt in range(3):
            try:
                with path.open("r", encoding="utf-8") as file:
                    return cls._validar_arquivo(json.load(file))
            except OSError as exc:
                if attempt < 2:
                    time.sleep(0.1)
                    continue
                logger.exception("Falha de leitura em %s", path)
                raise EvidenciasError("Não foi possível ler a cesta de evidências. Nada foi alterado.") from exc
            except (json.JSONDecodeError, UnicodeError, ValueError, TypeError) as exc:
                logger.error("Cesta de evidências inválida em %s: %s", path, exc)
                raise EvidenciasError(
                    "A cesta de evidências não pôde ser interpretada. O arquivo foi preservado sem alterações."
                ) from exc
        raise AssertionError("inalcançável")

    @classmethod
    def _gravar_unlocked(cls, itens: List[Dict[str, Any]]) -> None:
        path = cls._file_path()
        try:
            if path.exists():
                # Backup da versão anterior antes de cada gravação (atômico, como o principal).
                backup = cls._backup_path()
                tmp = backup.with_name(f".{backup.name}.{uuid.uuid4().hex}.tmp")
                try:
                    tmp.write_bytes(path.read_bytes())
                    os.replace(tmp, backup)
                finally:
                    tmp.unlink(missing_ok=True)
            PreferencesService._atomic_write(path, {"schema_version": cls.SCHEMA_VERSION, "evidencias": itens})
        except OSError as exc:
            logger.exception("Falha ao gravar evidências em %s", path)
            raise EvidenciasError("Não foi possível salvar a cesta de evidências. A alteração não foi confirmada.") from exc

    @classmethod
    def _transacao(cls, operacao):
        try:
            with cls._locked():
                itens = cls._ler_unlocked()
                resultado, novos = operacao(list(itens))
                if novos is not None:
                    cls._gravar_unlocked(novos)
                return resultado
        except PreferencesError as exc:
            raise EvidenciasError(str(exc)) from exc

    # ── Operações públicas ────────────────────────────────────────────────
    @classmethod
    def listar(cls, cnpj: Optional[str] = None) -> List[Dict[str, Any]]:
        def op(itens):
            filtrados = [i for i in itens if cnpj is None or i["cnpj"] == cnpj]
            return sorted(filtrados, key=lambda i: i["criado_em"], reverse=True), None
        return cls._transacao(op)

    @classmethod
    def resumo_por_cnpj(cls) -> List[Dict[str, Any]]:
        def op(itens):
            resumo: Dict[str, Dict[str, Any]] = {}
            for item in itens:
                atual = resumo.setdefault(item["cnpj"], {"cnpj": item["cnpj"], "quantidade": 0, "ultima_em": item["criado_em"]})
                atual["quantidade"] += 1
                atual["ultima_em"] = max(atual["ultima_em"], item["criado_em"])
            return sorted(resumo.values(), key=lambda r: r["cnpj"]), None
        return cls._transacao(op)

    @classmethod
    def criar(cls, dados: Dict[str, Any]) -> Dict[str, Any]:
        agora = _agora()
        novo = {
            **dados,
            "id": uuid.uuid4().hex,
            "nota": (dados.get("nota") or "").strip(),
            "criado_em": agora,
            "atualizado_em": agora,
        }

        def op(itens):
            chave = _chave(novo)
            if any(_chave(item) == chave for item in itens):
                raise EvidenciaDuplicadaError("Este item já está na cesta de evidências.")
            return novo, [*itens, novo]
        return cls._transacao(op)

    @classmethod
    def atualizar_nota(cls, evidencia_id: str, nota: str) -> Dict[str, Any]:
        def op(itens):
            for index, item in enumerate(itens):
                if item["id"] == evidencia_id:
                    atualizado = {**item, "nota": nota.strip(), "atualizado_em": _agora()}
                    itens[index] = atualizado
                    return atualizado, itens
            raise EvidenciaNaoEncontradaError("Evidência não encontrada.")
        return cls._transacao(op)

    @classmethod
    def remover(cls, evidencia_id: str) -> None:
        def op(itens):
            restantes = [i for i in itens if i["id"] != evidencia_id]
            if len(restantes) == len(itens):
                raise EvidenciaNaoEncontradaError("Evidência não encontrada.")
            return None, restantes
        cls._transacao(op)

    @classmethod
    def remover_por_cnpj(cls, cnpj: str) -> int:
        def op(itens):
            restantes = [i for i in itens if i["cnpj"] != cnpj]
            removidas = len(itens) - len(restantes)
            return removidas, (restantes if removidas else None)
        return cls._transacao(op)
