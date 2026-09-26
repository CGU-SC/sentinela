from typing import List, Optional

from fastapi import APIRouter, HTTPException, Path, Query, Response

from ..schemas.evidencias import (
    EvidenciaCreate,
    EvidenciaNotaPayload,
    EvidenciaRemocaoCnpjSchema,
    EvidenciaResumoSchema,
    EvidenciaSchema,
)
from ..services.evidencias_export import export_evidencias_xlsx
from ..services.evidencias import (
    EvidenciaDuplicadaError,
    EvidenciaNaoEncontradaError,
    EvidenciasError,
    EvidenciasService,
)

router = APIRouter()

CNPJ_PATTERN = r"^\d{14}$"


def _chamar(operacao, *args):
    try:
        return operacao(*args)
    except EvidenciaDuplicadaError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except EvidenciaNaoEncontradaError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except EvidenciasError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("", response_model=List[EvidenciaSchema])
def listar_evidencias(cnpj: Optional[str] = Query(default=None, pattern=CNPJ_PATTERN)):
    return _chamar(EvidenciasService.listar, cnpj)


@router.get("/resumo", response_model=List[EvidenciaResumoSchema])
def resumo_evidencias():
    return _chamar(EvidenciasService.resumo_por_cnpj)


@router.post("", response_model=EvidenciaSchema, status_code=201)
def criar_evidencia(payload: EvidenciaCreate):
    return _chamar(EvidenciasService.criar, payload.model_dump())


@router.patch("/{evidencia_id}", response_model=EvidenciaSchema)
def atualizar_nota_evidencia(payload: EvidenciaNotaPayload, evidencia_id: str = Path(min_length=1)):
    return _chamar(EvidenciasService.atualizar_nota, evidencia_id, payload.nota)


@router.get("/cnpj/{cnpj}/exportar")
def exportar_evidencias_do_cnpj(cnpj: str = Path(pattern=CNPJ_PATTERN)):
    """Baixa a cesta de evidências da farmácia em Excel."""
    filename, content = _chamar(export_evidencias_xlsx, cnpj)
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-store",
        },
    )


@router.delete("/cnpj/{cnpj}", response_model=EvidenciaRemocaoCnpjSchema)
def remover_evidencias_do_cnpj(cnpj: str = Path(pattern=CNPJ_PATTERN)):
    return {"removidas": _chamar(EvidenciasService.remover_por_cnpj, cnpj)}


@router.delete("/{evidencia_id}", status_code=204)
def remover_evidencia(evidencia_id: str = Path(min_length=1)):
    _chamar(EvidenciasService.remover, evidencia_id)
    return Response(status_code=204)
