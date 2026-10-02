"""Medicos do Programa Mais Medicos entre os nao localizados no CFM.

O intercambista do programa prescreve com o registro do Ministerio da Saude
(RMS), que nao consta no cadastro do CFM. O modulo mais_medicos (lista oficial
dos ativos) identifica esses medicos pela mesma chave do CFM (id_medico).
"""

from __future__ import annotations

from typing import Iterable

import polars as pl
from fastapi import HTTPException

from data_cache import get_mais_medicos_df
from ...schemas.analytics import CrmMaisMedicosSchema

MAIS_MEDICOS_REQUIRED_COLUMNS = {
    "id_medico",
    "no_medico",
    "tp_perfil",
    "no_nacionalidade",
    "dt_atualizacao",
}


def mais_medicos_por_id(ids: Iterable[str]) -> dict[str, CrmMaisMedicosSchema]:
    """Dados do Mais Medicos dos medicos informados que constam na lista de ativos.

    Args:
        ids: id_medico ("{numero}/{UF}") dos medicos nao localizados no CFM.

    Returns:
        Dicionario id_medico -> dados do programa (so os encontrados na lista).

    Raises:
        HTTPException: 503 se o modulo nao foi sincronizado ou esta sem colunas.
    """
    ids = list(dict.fromkeys(ids))
    if not ids:
        return {}
    try:
        lista = get_mais_medicos_df()
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Modulo Mais Medicos indisponivel ({exc}); sincronize o item 56 do sincronizar_cache.",
        ) from exc
    faltantes = sorted(MAIS_MEDICOS_REQUIRED_COLUMNS.difference(lista.columns))
    if faltantes:
        raise HTTPException(
            status_code=503,
            detail=f"Modulo Mais Medicos sem colunas obrigatorias: {', '.join(faltantes)}.",
        )
    encontrados = lista.filter(pl.col("id_medico").is_in(ids))
    return {
        row["id_medico"]: CrmMaisMedicosSchema(
            no_medico=row["no_medico"],
            tp_perfil=row["tp_perfil"],
            no_nacionalidade=row["no_nacionalidade"],
            dt_atualizacao=row["dt_atualizacao"],
        )
        for row in encontrados.iter_rows(named=True)
    }
