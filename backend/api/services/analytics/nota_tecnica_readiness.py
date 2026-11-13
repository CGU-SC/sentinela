"""Verificacao explicita dos caches necessarios para documentos do CNPJ."""

from __future__ import annotations

import os
from datetime import date
from typing import Any

import cache_files
import cache_registry
import cnpj_cache_versao
from data_cache import get_cache_dir, get_cnpj_cache_root


def _clean_cnpj(cnpj: str) -> str:
    clean = "".join(ch for ch in str(cnpj or "") if ch.isdigit())
    if len(clean) != 14:
        raise ValueError("CNPJ invalido para verificacao da Nota Tecnica.")
    return clean


def _module(
    key: str,
    label: str,
    files: list[tuple[str, str]],
    *,
    scope: str,
    required: bool = True,
    preparable: bool = False,
) -> dict[str, Any]:
    missing = [display for display, path in files if not os.path.exists(path)]
    return {
        "key": key,
        "label": label,
        "scope": scope,
        "required": required,
        "ready": not missing,
        "preparable": bool(preparable and missing),
        "missing_files": missing,
        "detail": None if not missing else f"{len(missing)} arquivo(s) ausente(s).",
    }


def _global_files(keys: list[str], global_files: dict[str, str], cache_dir: str) -> list[tuple[str, str]]:
    files: list[tuple[str, str]] = []
    for key in keys:
        filename = global_files.get(key)
        display = filename or f"cache global nao registrado: {key}"
        path = os.path.join(cache_dir, filename) if filename else ""
        files.append((display, path))
    return files


def _conferir_versao_cache_cnpj(cnpj: str, cnpj_cache_root: str) -> None:
    """Invalida os modulos locais do CNPJ gerados com outra versao da base global.

    Sem isso a prontidao contaria como pronto um arquivo que a geracao vai
    descartar ao abrir a pasta do CNPJ. Pasta inexistente nao tem o que conferir.
    """
    cnpj_dir = os.path.join(cnpj_cache_root, cnpj)
    if os.path.isdir(cnpj_dir):
        cnpj_cache_versao.garantir_cache_cnpj_atual(cnpj_dir)


def _cnpj_files(cnpj: str, filenames: list[str], cnpj_cache_root: str) -> list[tuple[str, str]]:
    return [
        (os.path.join("cnpjs", cnpj, filename), os.path.join(cnpj_cache_root, cnpj, filename))
        for filename in filenames
    ]


def _memoria_calculo_module(cnpj: str, global_files: dict[str, str], cache_dir: str, cnpj_cache_root: str) -> dict[str, Any]:
    local_display, local_path = _cnpj_files(
        cnpj,
        [cache_files.MEMORIA_CALCULO_PARQUET],
        cnpj_cache_root,
    )[0]
    if os.path.exists(local_path):
        return _module(
            "memoria_calculo",
            "Memoria de calculo do CNPJ",
            [(local_display, local_path)],
            scope="cnpj",
        )

    global_candidates = _global_files(
        ["memoria_calculo_global", "medicamentos"],
        global_files,
        cache_dir,
    )
    missing = [display for display, path in global_candidates if not os.path.exists(path)]
    return {
        "key": "memoria_calculo",
        "label": "Memoria de calculo do CNPJ",
        "scope": "cnpj",
        "required": True,
        "ready": not missing,
        "preparable": not missing,
        "missing_files": missing,
        "detail": (
            "Arquivo local ausente; sera derivado do modulo global."
            if not missing else f"{len(missing)} arquivo(s) ausente(s)."
        ),
    }


def _gtin_mensal_module(cnpj: str, global_files: dict[str, str], cache_dir: str, cnpj_cache_root: str) -> dict[str, Any]:
    local_display, local_path = _cnpj_files(
        cnpj,
        [cache_files.MOVIMENTACAO_MENSAL_GTIN_PARQUET],
        cnpj_cache_root,
    )[0]
    if os.path.exists(local_path):
        return _module(
            "gtin_mensal",
            "Movimentacao mensal por GTIN",
            [(local_display, local_path)] + _global_files(["medicamentos"], global_files, cache_dir),
            scope="cnpj",
        )

    global_candidates = _global_files(
        ["movimentacao_mensal_gtin_global", "medicamentos"],
        global_files,
        cache_dir,
    )
    missing = [display for display, path in global_candidates if not os.path.exists(path)]
    return {
        "key": "gtin_mensal",
        "label": "Movimentacao mensal por GTIN",
        "scope": "cnpj",
        "required": True,
        "ready": False,
        "preparable": not missing,
        "missing_files": [local_display] + missing,
        "detail": (
            "Arquivo local ausente; pode ser derivado do modulo global."
            if not missing else f"{len(missing)} arquivo(s) global(is) ausente(s)."
        ),
    }


def _crm_module(cnpj: str, global_files: dict[str, str], cache_dir: str, cnpj_cache_root: str) -> dict[str, Any]:
    required_global_keys = [
        "bench_crm_uf",
        "bench_crm_regiao",
        "bench_crm_br",
        "crm_prescricoes_brasil_semestre",
        "dados_medico",
        "perfil_estabelecimento",
    ]
    derivable_global_keys = [
        "crm_prescritores_global",
        "geografico_global",
        "crm_raiox_tx_global",
        "crm_concentracao_unico_alertas_global",
        "crm_concentracao_multiplo_alertas_global",
        "crm_timeline_dia_global",
        "crm_timeline_hora_global",
        "crm_timeline_eventos_global",
    ]
    local_filenames = [
        cache_files.CRM_PRESCRITORES_PARQUET,
        cache_files.GEOGRAFICO_PARQUET,
        cache_files.CRM_RAIOX_TX_PARQUET,
        cache_files.CRM_CONCENTRACAO_UNICO_ALERTAS_PARQUET,
        cache_files.CRM_CONCENTRACAO_MULTIPLO_ALERTAS_PARQUET,
        cache_files.CRM_TIMELINE_DIA_PARQUET,
        cache_files.CRM_TIMELINE_HORA_PARQUET,
        cache_files.CRM_TIMELINE_EVENTOS_PARQUET,
    ]
    global_files_required = _global_files(required_global_keys, global_files, cache_dir)
    local_files = _cnpj_files(cnpj, local_filenames, cnpj_cache_root)
    missing_global = [display for display, path in global_files_required if not os.path.exists(path)]
    missing_local = [display for display, path in local_files if not os.path.exists(path)]
    if not missing_global and not missing_local:
        return _module(
            "crm",
            "Evidencias e indicadores de CRM",
            global_files_required + local_files,
            scope="cnpj",
        )

    missing_derivable_global = [
        display
        for display, path in _global_files(derivable_global_keys, global_files, cache_dir)
        if not os.path.exists(path)
    ]
    return {
        "key": "crm",
        "label": "Evidencias e indicadores de CRM",
        "scope": "cnpj",
        "required": True,
        "ready": False,
        "preparable": bool(missing_local) and not missing_global and not missing_derivable_global,
        "missing_files": missing_global + missing_local + missing_derivable_global,
        "detail": (
            "Arquivos locais de CRM ausentes; podem ser preparados sob demanda para este CNPJ."
            if missing_local and not missing_global and not missing_derivable_global
            else f"{len(missing_global) + len(missing_local) + len(missing_derivable_global)} arquivo(s) ausente(s)."
        ),
    }


def _document_base_modules() -> list[dict[str, Any]]:
    cache_dir = get_cache_dir()
    global_files = cache_registry.get_global_parquet_files_by_key()

    return [
        _module(
            "base_cadastral",
            "Base cadastral do estabelecimento",
            _global_files(
                ["dados_farmacia", "perfil_estabelecimento", "localidades"],
                global_files,
                cache_dir,
            ),
            scope="global",
        ),
        _module(
            "movimentacao_matriz",
            "Movimentacao e matriz de risco",
            _global_files(
                [
                    "movimentacao",
                    "matriz_risco",
                    "volume_atipico_semestral",
                    "geografico_origem_uf",
                ],
                global_files,
                cache_dir,
            ),
            scope="global",
        ),
    ]


def _pdf_modules(cnpj: str) -> list[dict[str, Any]]:
    cache_dir = get_cache_dir()
    cnpj_cache_root = get_cnpj_cache_root()
    _conferir_versao_cache_cnpj(cnpj, cnpj_cache_root)
    global_files = cache_registry.get_global_parquet_files_by_key()

    required_global_keys = [
        "bench_crm_uf",
        "bench_crm_regiao",
        "bench_crm_br",
        "crm_prescricoes_brasil_semestre",
        "dados_medico",
        "perfil_estabelecimento",
    ]
    derivable_global_keys = [
        "crm_prescritores_global",
        "geografico_global",
        "crm_concentracao_unico_alertas_global",
        "crm_concentracao_multiplo_alertas_global",
    ]
    local_crm_files = [
        cache_files.CRM_PRESCRITORES_PARQUET,
        cache_files.GEOGRAFICO_PARQUET,
        cache_files.CRM_CONCENTRACAO_UNICO_ALERTAS_PARQUET,
        cache_files.CRM_CONCENTRACAO_MULTIPLO_ALERTAS_PARQUET,
    ]
    global_files_required = _global_files(required_global_keys, global_files, cache_dir)
    local_files = _cnpj_files(cnpj, local_crm_files, cnpj_cache_root)
    missing_global = [display for display, path in global_files_required if not os.path.exists(path)]
    missing_local = [display for display, path in local_files if not os.path.exists(path)]
    missing_derivable_global = [
        display
        for display, path in _global_files(derivable_global_keys, global_files, cache_dir)
        if not os.path.exists(path)
    ]
    crm_module = {
        "key": "crm",
        "label": "Dados de CRM",
        "scope": "cnpj",
        "required": True,
        "ready": not missing_global and not missing_local,
        "preparable": bool(missing_local) and not missing_global and not missing_derivable_global,
        "missing_files": missing_global + missing_local + missing_derivable_global,
        "detail": (
            None if not missing_global and not missing_local
            else (
                "Arquivos locais de CRM ausentes; podem ser preparados sob demanda para este CNPJ."
                if missing_local and not missing_global and not missing_derivable_global
                else f"{len(missing_global) + len(missing_local) + len(missing_derivable_global)} arquivo(s) ausente(s)."
            )
        ),
    }

    return [
        *_document_base_modules(),
        crm_module,
        _module(
            "falecidos",
            "Vendas para pessoas falecidas",
            _global_files(["falecidos"], global_files, cache_dir),
            scope="global",
        ),
    ]


def _nota_tecnica_modules(cnpj: str) -> list[dict[str, Any]]:
    cache_dir = get_cache_dir()
    cnpj_cache_root = get_cnpj_cache_root()
    _conferir_versao_cache_cnpj(cnpj, cnpj_cache_root)
    global_files = cache_registry.get_global_parquet_files_by_key()

    return [
        *_document_base_modules(),
        _memoria_calculo_module(cnpj, global_files, cache_dir, cnpj_cache_root),
        _gtin_mensal_module(cnpj, global_files, cache_dir, cnpj_cache_root),
        _module(
            "falecidos",
            "Vendas para pessoas falecidas",
            _global_files(["falecidos"], global_files, cache_dir),
            scope="global",
        ),
        _module(
            "socios_esocial",
            "Socios e vinculos trabalhistas",
            _global_files(
                [
                    "dados_socios",
                    "esocial_cnpj_ano",
                    "esocial_cnpj_trabalhador_ano",
                    "esocial_cnpj_ultima_movimentacao",
                    "sentinela_metadados_base",
                ],
                global_files,
                cache_dir,
            ),
            scope="global",
        ),
        _module(
            "clinico",
            "Incompatibilidade clinica/patologica",
            _global_files(
                [
                    "analise_gtin_inconsistencia_clinica",
                    "analise_gtin_inconsistencia_clinica_municipio",
                    "analise_gtin_inconsistencia_clinica_regiao",
                    "dados_ibge_demografia",
                ],
                global_files,
                cache_dir,
            ),
            scope="global",
        ),
        _crm_module(cnpj, global_files, cache_dir, cnpj_cache_root),
    ]


def _build_readiness(
    cnpj: str,
    modules: list[dict[str, Any]],
    data_inicio: date | None = None,
    data_fim: date | None = None,
) -> dict[str, Any]:
    clean = _clean_cnpj(cnpj)
    missing_modules = [module for module in modules if module["required"] and not module["ready"]]
    preparable = bool(missing_modules) and all(module.get("preparable") for module in missing_modules)
    return {
        "cnpj": clean,
        "ready": not missing_modules,
        "preparable": preparable,
        "data_inicio": data_inicio,
        "data_fim": data_fim,
        "modules": modules,
        "missing_modules": missing_modules,
    }


def get_nota_tecnica_readiness(
    cnpj: str,
    data_inicio: date | None = None,
    data_fim: date | None = None,
) -> dict[str, Any]:
    """Retorna a prontidao dos caches obrigatorios da Nota Tecnica."""
    clean = _clean_cnpj(cnpj)
    return _build_readiness(clean, _nota_tecnica_modules(clean), data_inicio, data_fim)


def get_relatorio_pdf_readiness(
    cnpj: str,
    data_inicio: date | None = None,
    data_fim: date | None = None,
) -> dict[str, Any]:
    """Retorna a prontidao dos caches obrigatorios do relatorio PDF."""
    clean = _clean_cnpj(cnpj)
    return _build_readiness(clean, _pdf_modules(clean), data_inicio, data_fim)
