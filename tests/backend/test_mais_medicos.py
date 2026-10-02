import io
from datetime import date
from types import SimpleNamespace
from urllib.error import HTTPError, URLError

import polars as pl
import pytest

import data_cache as dc
import mais_medicos as mm

HEADER = ["crm", "perfil", "uf", "inicio_atividade", "dt_atualizacao", "nacionalidade", "no_profissional", "ciclo"]


def _linha(crm="1405609", perfil="INTERCAMBISTA", uf="RR", inicio="2025-10-20", atualizacao="2026-09-11",
           nacionalidade="BRASILEIRA", nome="KEIVISSON DA GAMA E SILVA", ciclo="31"):
    return [crm, perfil, uf, inicio, atualizacao, nacionalidade, nome, ciclo]


def _csv(header, rows):
    return ";".join(header) + "\n" + "".join(";".join(r) + "\n" for r in rows)


class _Resposta:
    def __init__(self, body, content_type="text/csv"):
        self._body = body if isinstance(body, bytes) else body.encode("utf-8")
        self.headers = SimpleNamespace(get_content_type=lambda: content_type)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self):
        return self._body


def _urlopen(respostas, chamadas):
    def abrir(request, timeout):
        chamadas.append(request.full_url)
        resposta = respostas.pop(0)
        if isinstance(resposta, Exception):
            raise resposta
        return resposta
    return abrir


# ── montar ──────────────────────────────────────────────────────────────────

def test_montar_gera_uma_linha_por_medico_com_a_atividade_mais_recente():
    registros = [
        _linha(),
        # Mesmo medico em outro municipio, atividade mais antiga: fica de fora.
        _linha(inicio="2024-01-01", perfil="CRM BRASIL"),
        _linha(crm="0056650", uf="mg", perfil="CRM BRASIL", nome="MONICA", nacionalidade=""),
        # Sem CRM: descartado e contado.
        _linha(crm="", nome="SEM REGISTRO"),
        _linha(crm="  ", nome="SEM REGISTRO 2"),
    ]
    modulo, sem_crm = mm.montar(HEADER, registros)
    assert sem_crm == 2
    assert modulo.schema == pl.Schema(mm.SCHEMA)
    assert modulo.sort("id_medico").to_dicts() == [
        {"id_medico": "1405609/RR", "nu_crm": 1405609, "sg_uf": "RR", "no_medico": "KEIVISSON DA GAMA E SILVA",
         "tp_perfil": "INTERCAMBISTA", "no_nacionalidade": "BRASILEIRA",
         "dt_atualizacao": date(2026, 9, 11)},
        {"id_medico": "56650/MG", "nu_crm": 56650, "sg_uf": "MG", "no_medico": "MONICA",
         "tp_perfil": "CRM BRASIL", "no_nacionalidade": None,
         "dt_atualizacao": date(2026, 9, 11)},
    ]


@pytest.mark.parametrize(
    ("registros", "mensagem"),
    [
        ([_linha(crm="")], "nenhum registro com numero de CRM"),
        ([_linha(crm="12A45")], "caracteres nao numericos"),
        ([_linha(uf="")], "sem 'uf'"),
        ([_linha(nome="")], "sem 'no_profissional'"),
        ([_linha(inicio="20/10/2025")], "data invalida em '_inicio_atividade'"),
        ([_linha(atualizacao="2026-13-01")], "data invalida em 'dt_atualizacao'"),
    ],
)
def test_montar_falha_com_dado_obrigatorio_invalido(registros, mensagem):
    with pytest.raises(RuntimeError, match=mensagem):
        mm.montar(HEADER, registros)


# ── download ────────────────────────────────────────────────────────────────

def test_baixar_percorre_as_paginas_ate_a_ultima_incompleta(monkeypatch):
    monkeypatch.setattr(mm, "PAGE_SIZE", 2)
    chamadas, progresso = [], []
    respostas = [
        _Resposta("﻿" + _csv(HEADER, [_linha(), _linha(crm="2")])),
        _Resposta(_csv(HEADER, [_linha(crm="3")])),
    ]
    monkeypatch.setattr(mm, "urlopen", _urlopen(respostas, chamadas))
    header, registros, paginas = mm.baixar({"uf": "RR", "sexo": ""}, progress_callback=progresso.append)
    assert header == HEADER
    assert [r[0] for r in registros] == ["1405609", "2", "3"]
    assert paginas == 2
    assert progresso == [3, 6]
    assert "offset=0" in chamadas[0] and "offset=2" in chamadas[1]
    assert "uf=RR" in chamadas[0] and "sexo" not in chamadas[0]


def test_baixar_sem_filtros_nem_progresso(monkeypatch):
    monkeypatch.setattr(mm, "urlopen", _urlopen([_Resposta(_csv(HEADER, [_linha()]))], []))
    assert mm.baixar()[2] == 1


def test_baixar_falha_se_o_cabecalho_muda_entre_paginas(monkeypatch):
    monkeypatch.setattr(mm, "PAGE_SIZE", 1)
    respostas = [_Resposta(_csv(HEADER, [_linha()])), _Resposta(_csv(HEADER[::-1], [_linha()[::-1]]))]
    monkeypatch.setattr(mm, "urlopen", _urlopen(respostas, []))
    with pytest.raises(mm.DownloadError, match="cabecalho da API mudou"):
        mm.baixar()


def test_baixar_falha_sem_nenhum_profissional(monkeypatch):
    monkeypatch.setattr(mm, "urlopen", _urlopen([_Resposta(_csv(HEADER, []))], []))
    with pytest.raises(mm.DownloadError, match="nenhum profissional ativo"):
        mm.baixar()


@pytest.mark.parametrize(
    ("resposta", "mensagem"),
    [
        (_Resposta("{}", content_type="application/json"), "Content-Type inesperado"),
        (HTTPError("u", 500, "erro", {}, io.BytesIO(b"falhou")), "HTTP 500: falhou"),
        (URLError("sem rede"), "Nao foi possivel acessar a API: sem rede"),
        (_Resposta(b"\xff\xfe\x00"), "nao esta codificada em UTF-8"),
        (_Resposta(""), "CSV vazio"),
        (_Resposta("crm;;uf\n"), "cabecalho retornado pela API esta vazio"),
        (_Resposta("crm;uf\n1;RR\n"), "colunas obrigatorias: dt_atualizacao, inicio_atividade"),
        (_Resposta(_csv(HEADER, [["1", "2"]])), "linha 2 tem 2 campos"),
    ],
)
def test_pagina_invalida_falha_de_forma_visivel(monkeypatch, resposta, mensagem):
    monkeypatch.setattr(mm, "urlopen", _urlopen([resposta], []))
    with pytest.raises(mm.DownloadError, match=mensagem):
        mm.baixar()


# ── construir e cache ───────────────────────────────────────────────────────

def test_construir_grava_o_modulo_de_forma_atomica(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(mm, "baixar", lambda progress_callback=None: (HEADER, [_linha(), _linha(crm="")], 1))
    destino = tmp_path / "mais_medicos.smod"
    progresso = []
    mm.construir(str(destino), progress_callback=progresso.append)
    assert pl.read_parquet(destino).get_column("id_medico").to_list() == ["1405609/RR"]
    assert not (tmp_path / "mais_medicos.smod.tmp").exists()
    assert progresso == [90, 100]
    assert "1 sem CRM descartados; 1 medicos gravados" in capsys.readouterr().out
    mm.construir(str(destino))


def test_sync_e_leitura_do_modulo_no_cache(monkeypatch, tmp_path):
    monkeypatch.setattr(dc, "_CACHE_DIR", str(tmp_path))
    caminho = str(tmp_path / "mais_medicos.smod")
    monkeypatch.setattr(dc, "_MAIS_MEDICOS_PARQUET_PATH", caminho)
    monkeypatch.setattr(dc, "_ON_DEMAND_GLOBAL_CACHE_READY", set())
    monkeypatch.setattr(dc, "_MAIS_MEDICOS_MEMORIA", None)
    monkeypatch.setattr(mm, "baixar", lambda progress_callback=None: (HEADER, [_linha()], 1))

    dc._sync_mais_medicos(progress_callback=None)
    assert "mais_medicos" in dc._ON_DEMAND_GLOBAL_CACHE_READY
    primeiro = dc.get_mais_medicos_df()
    assert primeiro.get_column("id_medico").to_list() == ["1405609/RR"]
    assert dc.get_mais_medicos_df() is primeiro

    # Arquivo sincronizado de novo: a leitura em memoria e refeita.
    monkeypatch.setattr(mm, "baixar", lambda progress_callback=None: (HEADER, [_linha(), _linha(crm="7")], 1))
    dc._sync_mais_medicos()
    assert dc.get_mais_medicos_df().height == 2


def test_leitura_em_memoria_confere_de_novo_dentro_da_trava(monkeypatch, tmp_path):
    monkeypatch.setattr(dc, "_CACHE_DIR", str(tmp_path))
    caminho = str(tmp_path / "mais_medicos.smod")
    monkeypatch.setattr(dc, "_MAIS_MEDICOS_PARQUET_PATH", caminho)
    monkeypatch.setattr(dc, "_ON_DEMAND_GLOBAL_CACHE_READY", set())
    mm.montar(HEADER, [_linha()])[0].write_parquet(caminho)
    pronto = pl.DataFrame({"id_medico": ["x"]})

    class _Trava:
        # Outra requisicao carregou o modulo enquanto esta esperava a trava.
        def __enter__(self):
            dc._MAIS_MEDICOS_MEMORIA = (dc.get_global_cache_signature("mais_medicos"), pronto)

        def __exit__(self, *exc):
            return False

    monkeypatch.setattr(dc, "_MAIS_MEDICOS_MEMORIA", None)
    monkeypatch.setattr(dc, "_MAIS_MEDICOS_MEMORIA_LOCK", _Trava())
    assert dc.get_mais_medicos_df() is pronto
