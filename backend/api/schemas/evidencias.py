from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, model_validator

TipoEvidencia = Literal["dia", "hora", "autorizacao"]


class EvidenciaCreate(BaseModel):
    cnpj: str = Field(pattern=r"^\d{14}$")
    tipo: TipoEvidencia
    dt_janela: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    hora: Optional[int] = Field(default=None, ge=0, le=23)
    num_autorizacao: Optional[str] = Field(default=None, min_length=1, max_length=64)
    snapshot: Dict[str, Any] = Field(default_factory=dict)
    nota: str = Field(default="", max_length=2000)

    @model_validator(mode="after")
    def _campos_por_tipo(self):
        if self.tipo == "dia" and (self.hora is not None or self.num_autorizacao):
            raise ValueError("Evidência do tipo dia não leva hora nem autorização.")
        if self.tipo == "hora" and (self.hora is None or self.num_autorizacao):
            raise ValueError("Evidência do tipo hora exige a hora e não leva autorização.")
        if self.tipo == "autorizacao" and (self.hora is None or not self.num_autorizacao):
            raise ValueError("Evidência do tipo autorização exige o número e a hora da autorização.")
        return self


class EvidenciaNotaPayload(BaseModel):
    nota: str = Field(max_length=2000)


class EvidenciaSchema(EvidenciaCreate):
    id: str
    criado_em: str
    atualizado_em: str


class EvidenciaResumoSchema(BaseModel):
    cnpj: str
    quantidade: int
    ultima_em: str


class EvidenciaRemocaoCnpjSchema(BaseModel):
    removidas: int


EvidenciasLista = List[EvidenciaSchema]
