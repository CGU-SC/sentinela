from fastapi import APIRouter, HTTPException
from typing import Any

from ..schemas.preferences import (
    FiltersPayload,
    MetodologiaPayload,
    NotaTecnicaPayload,
    PreferencesSchema,
    PreferencesRecoveryPayload,
    UiPayload,
    WatchlistPayload,
)
from ..services.preferences import PreferencesError, PreferencesService
from ..services.analytics.indicator_rules import (
    DEFAULT_AUDIT_HIGH_VALUE,
    DEFAULT_VOLUME_ATIPICO_AUMENTO_MINIMO,
    MAX_AUDIT_HIGH_VALUE,
    MAX_VOLUME_ATIPICO_AUMENTO_MINIMO,
    MIN_AUDIT_HIGH_VALUE,
    MIN_VOLUME_ATIPICO_AUMENTO_MINIMO,
    get_audit_high_value,
    get_volume_atipico_aumento_minimo,
    normalize_audit_high_value,
    normalize_volume_atipico_aumento_minimo,
)
from ..services.analytics.nota_tecnica_regionais import resolve_nota_tecnica_regional

router = APIRouter()


def _preferences_call(operation, *args):
    try:
        return operation(*args)
    except PreferencesError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


def _validate_assinantes_tecnicos(value: Any) -> list[dict[str, str]]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise HTTPException(status_code=422, detail="assinantes_tecnicos deve ser uma lista.")
    if len(value) > 3:
        raise HTTPException(status_code=422, detail="Informe no maximo 3 assinaturas tecnicas.")

    normalized: list[dict[str, str]] = []
    for item in value:
        if not isinstance(item, dict):
            raise HTTPException(status_code=422, detail="Cada assinatura tecnica deve ser um objeto.")
        nome = str(item.get("nome", "")).strip()
        cargo = str(item.get("cargo", "")).strip()
        if (nome and not cargo) or (cargo and not nome):
            raise HTTPException(
                status_code=422,
                detail="Cada assinatura tecnica deve conter nome e cargo.",
            )
        if nome and cargo:
            normalized.append({"nome": nome, "cargo": cargo})
    return normalized


def _validate_gerar_pdf_visualizacao(value: Any) -> bool:
    if value is None:
        return False
    if not isinstance(value, bool):
        raise HTTPException(status_code=422, detail="gerar_pdf_visualizacao deve ser booleano.")
    return value


@router.get("", response_model=PreferencesSchema)
def get_preferences():
    return _preferences_call(PreferencesService.read)


@router.put("", response_model=PreferencesSchema)
def save_preferences(payload: PreferencesSchema):
    return _preferences_call(PreferencesService.write, payload.model_dump())


@router.put("/filters", response_model=PreferencesSchema)
def save_filters(payload: FiltersPayload):
    return _preferences_call(PreferencesService.update_filters, payload.filters)


@router.put("/watchlist", response_model=PreferencesSchema)
def save_watchlist(payload: WatchlistPayload):
    return _preferences_call(PreferencesService.update_watchlist,
        [item.model_dump() for item in payload.interesse]
    )


@router.put("/ui", response_model=PreferencesSchema)
def save_ui(payload: UiPayload):
    return _preferences_call(PreferencesService.update_ui, payload.ui)


@router.put("/nota-tecnica", response_model=PreferencesSchema)
def save_nota_tecnica(payload: NotaTecnicaPayload):
    try:
        resolve_nota_tecnica_regional(payload.nota_tecnica.get("regional_codigo"))
    except RuntimeError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    payload.nota_tecnica["assinantes_tecnicos"] = _validate_assinantes_tecnicos(
        payload.nota_tecnica.get("assinantes_tecnicos")
    )
    payload.nota_tecnica["gerar_pdf_visualizacao"] = _validate_gerar_pdf_visualizacao(
        payload.nota_tecnica.get("gerar_pdf_visualizacao")
    )
    return _preferences_call(PreferencesService.update_nota_tecnica, payload.nota_tecnica)


@router.get("/recovery/status")
def preferences_recovery_status():
    """Expõe apenas existência, validade e contagem, sem CNPJs."""
    return _preferences_call(PreferencesService.recovery_status)


@router.post("/recovery", response_model=PreferencesSchema)
def restore_preferences(payload: PreferencesRecoveryPayload):
    """Restauração explícita; preserva o arquivo principal anterior."""
    return _preferences_call(PreferencesService.restore, payload.source)


def _metodologia_response() -> dict[str, Any]:
    return {
        "audit_high_value": get_audit_high_value(),
        "volume_atipico_aumento_minimo": get_volume_atipico_aumento_minimo(),
        "defaults": {
            "audit_high_value": DEFAULT_AUDIT_HIGH_VALUE,
            "volume_atipico_aumento_minimo": DEFAULT_VOLUME_ATIPICO_AUMENTO_MINIMO,
        },
        "limits": {
            "audit_high_value": {
                "min": MIN_AUDIT_HIGH_VALUE,
                "max": MAX_AUDIT_HIGH_VALUE,
            },
            "volume_atipico_aumento_minimo": {
                "min": MIN_VOLUME_ATIPICO_AUMENTO_MINIMO,
                "max": MAX_VOLUME_ATIPICO_AUMENTO_MINIMO,
            },
        },
    }


@router.get("/metodologia")
def get_metodologia():
    return _metodologia_response()


@router.put("/metodologia")
def save_metodologia(payload: MetodologiaPayload):
    required_fields = {"audit_high_value", "volume_atipico_aumento_minimo"}
    missing_fields = required_fields - set(payload.metodologia.keys())
    if missing_fields:
        raise HTTPException(
            status_code=422,
            detail="Configuracao metodologica incompleta: " + ", ".join(sorted(missing_fields)),
        )

    try:
        volume_atipico_aumento_minimo = normalize_volume_atipico_aumento_minimo(
            payload.metodologia.get("volume_atipico_aumento_minimo")
        )
        audit_high_value = normalize_audit_high_value(
            payload.metodologia.get("audit_high_value")
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    _preferences_call(PreferencesService.update_metodologia, {
        "audit_high_value": audit_high_value,
        "volume_atipico_aumento_minimo": volume_atipico_aumento_minimo,
    })
    return _metodologia_response()




