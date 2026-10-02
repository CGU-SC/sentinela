from datetime import date

import polars as pl
import pytest
from fastapi import HTTPException

from api.services.analytics import crm_mais_medicos as cmm


def _lista():
    return pl.DataFrame({
        "id_medico": ["1405609/RR", "56650/MG"],
        "no_medico": ["KEIVISSON DA GAMA E SILVA", "MONICA"],
        "tp_perfil": ["INTERCAMBISTA", "CRM BRASIL"],
        "no_nacionalidade": ["BRASILEIRA", None],
        "dt_atualizacao": [date(2026, 9, 11), date(2026, 9, 11)],
    })


def test_devolve_so_os_medicos_da_lista(monkeypatch):
    monkeypatch.setattr(cmm, "get_mais_medicos_df", _lista)
    encontrados = cmm.mais_medicos_por_id(["1405609/RR", "999/SP", "1405609/RR"])
    assert list(encontrados) == ["1405609/RR"]
    assert encontrados["1405609/RR"].model_dump() == {
        "no_medico": "KEIVISSON DA GAMA E SILVA",
        "tp_perfil": "INTERCAMBISTA",
        "no_nacionalidade": "BRASILEIRA",
        "dt_atualizacao": date(2026, 9, 11),
    }


def test_sem_ids_nao_le_o_modulo(monkeypatch):
    monkeypatch.setattr(cmm, "get_mais_medicos_df", lambda: pytest.fail("nao deveria ler o modulo"))
    assert cmm.mais_medicos_por_id([]) == {}


def test_modulo_ausente_responde_503(monkeypatch):
    monkeypatch.setattr(cmm, "get_mais_medicos_df", lambda: (_ for _ in ()).throw(FileNotFoundError("sem arquivo")))
    with pytest.raises(HTTPException) as erro:
        cmm.mais_medicos_por_id(["1/RR"])
    assert erro.value.status_code == 503
    assert "sincronize o item 56" in erro.value.detail


def test_modulo_sem_colunas_responde_503(monkeypatch):
    monkeypatch.setattr(cmm, "get_mais_medicos_df", lambda: _lista().drop("tp_perfil"))
    with pytest.raises(HTTPException) as erro:
        cmm.mais_medicos_por_id(["1/RR"])
    assert erro.value.status_code == 503
    assert "tp_perfil" in erro.value.detail
