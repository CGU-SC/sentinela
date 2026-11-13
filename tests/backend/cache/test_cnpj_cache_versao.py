"""Versao da base global nos caches por CNPJ (``backend/cnpj_cache_versao.py``).

O ``conftest`` desliga a conferencia por padrao; aqui as funcoes originais sao
capturadas na importacao (antes das fixtures autouse) e exercitadas direto.
"""

import json
import os
from types import SimpleNamespace

import pytest

import cnpj_cache_versao as ccv
import data_cache

_GARANTIR = ccv.garantir_cache_cnpj_atual
_REGISTRAR = ccv.registrar_base_carregada


def _definicoes(*chaves):
    return tuple(SimpleNamespace(key=chave) for chave in chaves)


def _ler_manifesto(cnpj_dir):
    with open(os.path.join(cnpj_dir, ccv.MANIFESTO_FILENAME), encoding="utf-8") as arquivo:
        return json.load(arquivo)


def _gravar_manifesto(cnpj_dir, conteudo):
    with open(os.path.join(cnpj_dir, ccv.MANIFESTO_FILENAME), "w", encoding="utf-8") as arquivo:
        arquivo.write(conteudo)


def test_assinaturas_globais_marca_modulo_ausente_como_none(monkeypatch):
    monkeypatch.setattr(ccv.cache_registry, "GLOBAL_CACHE_DEFINITIONS", _definicoes("socios", "teia"))

    def assinatura(chave):
        if chave == "teia":
            raise FileNotFoundError(chave)
        return (123, "abc")

    monkeypatch.setattr(data_cache, "get_global_content_signature", assinatura)

    assert ccv.assinaturas_globais() == {"socios": [123, "abc"], "teia": None}


def test_assinaturas_globais_propaga_parquet_invalido(monkeypatch):
    monkeypatch.setattr(ccv.cache_registry, "GLOBAL_CACHE_DEFINITIONS", _definicoes("socios"))

    def assinatura(chave):
        raise ValueError("nao e parquet")

    monkeypatch.setattr(data_cache, "get_global_content_signature", assinatura)

    with pytest.raises(ValueError, match="nao e parquet"):
        ccv.assinaturas_globais()


def test_calcular_versao_base_muda_quando_um_global_muda(monkeypatch):
    disco = {"socios": [1, "a"], "teia": None}
    monkeypatch.setattr(ccv, "assinaturas_globais", lambda: dict(disco))

    primeira = ccv.calcular_versao_base()
    assert ccv.calcular_versao_base() == primeira

    disco["socios"] = [2, "b"]
    assert ccv.calcular_versao_base() != primeira


def test_sem_carga_a_versao_segue_o_disco_e_apos_carga_fica_fixa(monkeypatch):
    disco = {"socios": [1, "a"]}
    monkeypatch.setattr(ccv, "assinaturas_globais", lambda: dict(disco))

    antes = ccv.versao_base_atual()
    disco["socios"] = [2, "b"]
    assert ccv.versao_base_atual() != antes

    _REGISTRAR()
    na_carga = ccv.versao_base_atual()

    # Global reescrito com o backend rodando: so vale na proxima carga.
    disco["socios"] = [3, "c"]
    assert ccv.versao_base_atual() == na_carga

    _REGISTRAR()
    assert ccv.versao_base_atual() != na_carga


def test_pasta_sem_manifesto_apaga_somente_smod_e_grava_versao(tmp_path, monkeypatch, capsys):
    cnpj_dir = tmp_path / "11222333000181"
    cnpj_dir.mkdir()
    (cnpj_dir / "teia_grafo_nivel2_nodes.smod").write_bytes(b"x")
    (cnpj_dir / "crm_prescritores.smod").write_bytes(b"x")
    (cnpj_dir / "anotacao.txt").write_text("fica")
    (cnpj_dir / "subpasta.smod").mkdir()
    monkeypatch.setattr(ccv, "versao_base_atual", lambda: "v1")

    _GARANTIR(str(cnpj_dir))

    assert sorted(os.listdir(cnpj_dir)) == ["anotacao.txt", ccv.MANIFESTO_FILENAME, "subpasta.smod"]
    assert _ler_manifesto(cnpj_dir) == {"formato": ccv.MANIFESTO_FORMATO, "versao_base": "v1"}
    assert ccv._PASTAS_CONFERIDAS == {str(cnpj_dir): "v1"}
    assert "2 modulo(s) do CNPJ serao regenerados" in capsys.readouterr().out


def test_pasta_com_mesma_versao_nao_apaga_nada(tmp_path, monkeypatch, capsys):
    cnpj_dir = tmp_path / "11222333000181"
    cnpj_dir.mkdir()
    (cnpj_dir / "crm_prescritores.smod").write_bytes(b"x")
    _gravar_manifesto(cnpj_dir, json.dumps({"formato": ccv.MANIFESTO_FORMATO, "versao_base": "v1"}))
    monkeypatch.setattr(ccv, "versao_base_atual", lambda: "v1")

    _GARANTIR(str(cnpj_dir))

    assert (cnpj_dir / "crm_prescritores.smod").exists()
    assert capsys.readouterr().out == ""


def test_versao_nova_regenera_e_pasta_vazia_nao_imprime(tmp_path, monkeypatch, capsys):
    cnpj_dir = tmp_path / "11222333000181"
    cnpj_dir.mkdir()
    _gravar_manifesto(cnpj_dir, json.dumps({"formato": ccv.MANIFESTO_FORMATO, "versao_base": "v1"}))
    monkeypatch.setattr(ccv, "versao_base_atual", lambda: "v2")

    _GARANTIR(str(cnpj_dir))

    assert _ler_manifesto(cnpj_dir)["versao_base"] == "v2"
    assert not (cnpj_dir / f"{ccv.MANIFESTO_FILENAME}.tmp").exists()
    assert capsys.readouterr().out == ""


def test_pasta_ja_conferida_nao_relê_manifesto(tmp_path, monkeypatch):
    cnpj_dir = str(tmp_path)
    monkeypatch.setattr(ccv, "versao_base_atual", lambda: "v1")
    monkeypatch.setattr(ccv, "_PASTAS_CONFERIDAS", {cnpj_dir: "v1"})

    def nao_deve_ler(_):
        raise AssertionError("manifesto relido")

    monkeypatch.setattr(ccv, "_ler_versao_gravada", nao_deve_ler)

    _GARANTIR(cnpj_dir)


def test_pasta_conferida_por_outra_thread_enquanto_esperava_o_lock(tmp_path, monkeypatch):
    cnpj_dir = str(tmp_path)
    monkeypatch.setattr(ccv, "versao_base_atual", lambda: "v1")

    class LockQueOutraThreadLiberou:
        def __enter__(self):
            ccv._PASTAS_CONFERIDAS[cnpj_dir] = "v1"

        def __exit__(self, *exc):
            return False

    monkeypatch.setattr(ccv, "_LOCK", LockQueOutraThreadLiberou())

    def nao_deve_ler(_):
        raise AssertionError("manifesto relido")

    monkeypatch.setattr(ccv, "_ler_versao_gravada", nao_deve_ler)

    _GARANTIR(cnpj_dir)


@pytest.mark.parametrize(
    "conteudo",
    [
        "{nao e json",
        json.dumps(["lista"]),
        json.dumps({"formato": 999, "versao_base": "v1"}),
        json.dumps({"formato": ccv.MANIFESTO_FORMATO, "versao_base": 7}),
    ],
)
def test_manifesto_ilegivel_vale_como_versao_desconhecida(tmp_path, conteudo):
    _gravar_manifesto(tmp_path, conteudo)

    assert ccv._ler_versao_gravada(str(tmp_path)) is None


def test_manifesto_ausente_e_valido(tmp_path):
    assert ccv._ler_versao_gravada(str(tmp_path)) is None

    _gravar_manifesto(tmp_path, json.dumps({"formato": ccv.MANIFESTO_FORMATO, "versao_base": "v9"}))

    assert ccv._ler_versao_gravada(str(tmp_path)) == "v9"


def test_falha_ao_apagar_modulo_sobe_visivel(tmp_path, monkeypatch):
    (tmp_path / "crm_prescritores.smod").write_bytes(b"x")

    def remove_bloqueado(caminho):
        raise PermissionError("arquivo em uso")

    monkeypatch.setattr(ccv.os, "remove", remove_bloqueado)

    with pytest.raises(RuntimeError, match="nao foi possivel apagar .*crm_prescritores.smod"):
        ccv._apagar_modulos(str(tmp_path))


def test_get_cnpj_cache_dir_cria_a_pasta_e_confere_a_versao(tmp_path, monkeypatch):
    monkeypatch.setattr(data_cache, "get_cnpj_cache_root", lambda: str(tmp_path))
    monkeypatch.setattr(ccv, "garantir_cache_cnpj_atual", _GARANTIR)
    monkeypatch.setattr(ccv, "versao_base_atual", lambda: "v1")

    cnpj_dir = ccv.get_cnpj_cache_dir("11222333000181")

    assert cnpj_dir == str(tmp_path / "11222333000181")
    assert _ler_manifesto(cnpj_dir)["versao_base"] == "v1"


def test_prontidao_confere_versao_somente_de_pasta_existente(tmp_path, monkeypatch):
    from api.services.analytics import nota_tecnica_readiness as readiness

    conferidas = []
    monkeypatch.setattr(ccv, "garantir_cache_cnpj_atual", conferidas.append)
    (tmp_path / "11222333000181").mkdir()

    readiness._conferir_versao_cache_cnpj("11222333000181", str(tmp_path))
    readiness._conferir_versao_cache_cnpj("99888777000166", str(tmp_path))

    assert conferidas == [str(tmp_path / "11222333000181")]
