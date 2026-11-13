"""Controle de versao da base para os caches por CNPJ (``modules/cnpjs/{cnpj}/``).

Todo arquivo da pasta de um CNPJ e derivado dos modulos globais
(``modules/global``). Quando uma sincronizacao reescreve um global com conteudo
diferente, os derivados do CNPJ ficam desatualizados e precisam ser refeitos.

A *versao da base* e o hash das assinaturas de conteudo (tamanho e hash do
rodape do parquet, ver ``data_cache.get_global_content_signature``) de todos os
modulos globais de ``cache_registry.GLOBAL_CACHE_DEFINITIONS``. Ela nao depende
do ``mtime``: copiar a pasta ``modules`` para outra maquina nao a altera, e uma
sincronizacao que traga dados diferentes a muda.

Cada pasta de CNPJ guarda em ``cache_manifesto.json`` a versao da base com que
seus arquivos foram gerados. Ao abrir a pasta (``get_cnpj_cache_dir``), se a
versao gravada for diferente da atual, os ``.smod`` da pasta sao apagados e os
produtores os regeneram sob demanda. Pasta sem manifesto (criada antes deste
controle) ou com manifesto ilegivel tem versao desconhecida e e tratada como
desatualizada: a consequencia e so regenerar, nunca servir dado antigo.

Qual versao vale como "atual":

* O backend calcula a versao uma vez, quando ``data_cache.load_cache`` carrega a
  base (boot, inclusive em modo degradado, ou sincronizacao concluida pela
  interface), via ``registrar_base_carregada``. Depois disso nao ha conferencia
  de arquivo global por consulta.
* Processo que nao carregou a base (``sincronizar_cache.py``, que sincroniza
  globais e CNPJs no mesmo processo) calcula a versao do disco a cada abertura.

Limite aceito: a base e distribuida pronta e os usuarios nao sincronizam. Se um
global for reescrito por outro processo com o backend rodando, os caches por
CNPJ so passam a refletir a mudanca quando o backend reiniciar.
"""

from __future__ import annotations

import hashlib
import json
import os
import threading

import cache_registry
from cache_files import MODULE_EXT

MANIFESTO_FILENAME = "cache_manifesto.json"
MANIFESTO_FORMATO = 1

_LOCK = threading.Lock()
# Pasta de CNPJ -> versao da base ja conferida neste processo (evita reler o manifesto).
_PASTAS_CONFERIDAS: dict[str, str] = {}
# Versao da base fixada quando este processo carregou a base; None sem carga.
_VERSAO_CARREGADA: str | None = None


def assinaturas_globais() -> dict[str, list | None]:
    """Assinatura de conteudo de cada modulo global registrado.

    Modulo global ausente entra como ``None``: e um estado valido (varios globais
    sao gerados sob demanda) e a versao muda quando ele passar a existir.

    Returns:
        Mapa ``chave do modulo -> [tamanho em bytes, hash do rodape]`` ou ``None``.

    Raises:
        ValueError: modulo global presente que nao e um parquet valido.
    """
    import data_cache

    assinaturas: dict[str, list | None] = {}
    for definition in cache_registry.GLOBAL_CACHE_DEFINITIONS:
        try:
            tamanho, hash_rodape = data_cache.get_global_content_signature(definition.key)
        except FileNotFoundError:
            assinaturas[definition.key] = None
            continue
        assinaturas[definition.key] = [tamanho, hash_rodape]
    return assinaturas


def calcular_versao_base() -> str:
    """Hash das assinaturas de todos os modulos globais, lidas do disco agora."""
    conteudo = json.dumps(assinaturas_globais(), sort_keys=True, separators=(",", ":"))
    return hashlib.blake2b(conteudo.encode("utf-8"), digest_size=16).hexdigest()


def registrar_base_carregada() -> None:
    """Fixa a versao da base que este processo acabou de carregar.

    Chamado por ``data_cache.load_cache`` ao fim do boot (completo ou degradado)
    e de uma sincronizacao concluida.
    """
    global _VERSAO_CARREGADA
    _VERSAO_CARREGADA = calcular_versao_base()


def versao_base_atual() -> str:
    """Versao da base que vale para este processo (ver docstring do modulo)."""
    if _VERSAO_CARREGADA is not None:
        return _VERSAO_CARREGADA
    return calcular_versao_base()


def _ler_versao_gravada(cnpj_dir: str) -> str | None:
    """Versao gravada no manifesto da pasta; ``None`` quando desconhecida."""
    caminho = os.path.join(cnpj_dir, MANIFESTO_FILENAME)
    if not os.path.exists(caminho):
        return None
    try:
        with open(caminho, encoding="utf-8") as arquivo:
            manifesto = json.load(arquivo)
    except (OSError, ValueError):
        return None
    if not isinstance(manifesto, dict) or manifesto.get("formato") != MANIFESTO_FORMATO:
        return None
    versao = manifesto.get("versao_base")
    return versao if isinstance(versao, str) else None


def _apagar_modulos(cnpj_dir: str) -> list[str]:
    """Apaga os ``.smod`` da pasta do CNPJ e devolve os nomes apagados.

    Raises:
        RuntimeError: arquivo que nao pode ser apagado (por exemplo, aberto por
            outro processo); a pasta fica como estava e o erro sobe visivel.
    """
    apagados: list[str] = []
    for nome in sorted(os.listdir(cnpj_dir)):
        caminho = os.path.join(cnpj_dir, nome)
        if not nome.endswith(MODULE_EXT) or not os.path.isfile(caminho):
            continue
        try:
            os.remove(caminho)
        except OSError as exc:
            raise RuntimeError(
                f"Cache do CNPJ desatualizado e nao foi possivel apagar {caminho}: {exc}"
            ) from exc
        apagados.append(nome)
    return apagados


def _gravar_manifesto(cnpj_dir: str, versao: str) -> None:
    """Grava o manifesto de forma atomica (arquivo temporario + ``os.replace``)."""
    caminho = os.path.join(cnpj_dir, MANIFESTO_FILENAME)
    temporario = f"{caminho}.tmp"
    with open(temporario, "w", encoding="utf-8") as arquivo:
        json.dump({"formato": MANIFESTO_FORMATO, "versao_base": versao}, arquivo)
    os.replace(temporario, caminho)


def garantir_cache_cnpj_atual(cnpj_dir: str) -> None:
    """Invalida os modulos da pasta do CNPJ se foram gerados com outra versao da base.

    Args:
        cnpj_dir: pasta ``modules/cnpjs/{cnpj}`` (ja existente).
    """
    versao = versao_base_atual()
    if _PASTAS_CONFERIDAS.get(cnpj_dir) == versao:
        return
    with _LOCK:
        if _PASTAS_CONFERIDAS.get(cnpj_dir) == versao:
            return
        if _ler_versao_gravada(cnpj_dir) != versao:
            apagados = _apagar_modulos(cnpj_dir)
            if apagados:
                print(
                    f"[ CACHE ] {os.path.basename(cnpj_dir)} - base global mudou; "
                    f"{len(apagados)} modulo(s) do CNPJ serao regenerados sob demanda."
                )
            _gravar_manifesto(cnpj_dir, versao)
        _PASTAS_CONFERIDAS[cnpj_dir] = versao


def get_cnpj_cache_dir(cnpj: str) -> str:
    """Pasta ``modules/cnpjs/{cnpj}``, criada se preciso e conferida contra a base.

    Ponto unico de acesso aos caches por CNPJ: todo produtor e leitor deve abrir a
    pasta por aqui para nunca ler um modulo gerado com outra versao da base.
    """
    from data_cache import get_cnpj_cache_root

    cnpj_dir = os.path.join(get_cnpj_cache_root(), cnpj)
    os.makedirs(cnpj_dir, exist_ok=True)
    garantir_cache_cnpj_atual(cnpj_dir)
    return cnpj_dir
