from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


class WatchlistItemSchema(BaseModel):
    cnpj: str
    razaoSocial: Optional[str] = ""
    adicionadoEm: Optional[str] = None
    observacao: Optional[str] = ""
    atualizadoEm: Optional[str] = None


class WatchlistPayload(BaseModel):
    interesse: List[WatchlistItemSchema] = Field(default_factory=list)


class PreferencesRecoveryPayload(BaseModel):
    source: Literal["backup", "corrupt"]


class FiltersPayload(BaseModel):
    filters: Dict[str, Any] = Field(default_factory=dict)


class UiPayload(BaseModel):
    ui: Dict[str, Any] = Field(default_factory=dict)


class NotaTecnicaPayload(BaseModel):
    nota_tecnica: Dict[str, Any] = Field(default_factory=dict)


class MetodologiaPayload(BaseModel):
    metodologia: Dict[str, Any] = Field(default_factory=dict)


class PreferencesSchema(BaseModel):
    schema_version: int = 1
    filters: Dict[str, Any] = Field(default_factory=dict)
    watchlist: List[WatchlistItemSchema] = Field(default_factory=list)
    ui: Dict[str, Any] = Field(default_factory=dict)
    nota_tecnica: Dict[str, Any] = Field(default_factory=dict)
    metodologia: Dict[str, Any] = Field(default_factory=dict)
