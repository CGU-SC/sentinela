import json

import polars as pl
import pytest

import data_cache as dc
from backend import crm_multiplo_medico as ponte


def _alertas(**overrides):
    dados = {
        "id_cnpj": [10, 10],
        "competencia": [202401, 202401],
        "dt_alerta": ["2024-01-05 10:00:00.000000", "2024-01-05 15:00:00.000000"],
        "hr_janela": [10, 15],
        "dt_ini_concentracao": ["2024-01-05 10:00:00.000000", "2024-01-05 15:00:00.000000"],
        "dt_fim_concentracao": ["2024-01-05 10:30:00.000000", "2024-01-05 15:20:00.000000"],
        "id_severidade": [3, 1],
    }
    dados.update(overrides)
    return pl.DataFrame(dados, schema_overrides={"id_cnpj": pl.Int32, "competencia": pl.Int32})


def _autorizacoes(linhas=None):
    linhas = linhas if linhas is not None else [
        (10, "2024-01-05", "2024-01-05 10:05:00.000000", "a1", "A/SP"),
        (10, "2024-01-05", "2024-01-05 10:10:00.000000", "a2", "A/SP"),
        # A mesma autorizacao repetida conta uma vez.
        (10, "2024-01-05", "2024-01-05 10:10:00.000000", "a2", "A/SP"),
        # Um minuto depois do fim da janela: fica de fora.
        (10, "2024-01-05", "2024-01-05 10:31:00.000000", "a3", "A/SP"),
        (10, "2024-01-05", "2024-01-05 10:20:00.000000", "a4", "B/RJ"),
        (10, "2024-01-05", "2024-01-05 15:10:00.000000", "a5", "B/RJ"),
        # Outra farmacia, sem alerta: nao entra.
        (20, "2024-01-05", "2024-01-05 10:05:00.000000", "a6", "A/SP"),
    ]
    return pl.DataFrame(
        linhas,
        schema={"id_cnpj": pl.Int32, "dt_janela": pl.Utf8, "data_hora": pl.Utf8,
                "num_autorizacao": pl.Utf8, "id_medico": pl.Utf8},
        orient="row",
    )


def _instalar(monkeypatch, *, alertas=None, autorizacoes=None, assinatura=(123, 456)):
    alertas = alertas if alertas is not None else _alertas()
    autorizacoes = autorizacoes if autorizacoes is not None else _autorizacoes()
    monkeypatch.setattr(dc, "scan_crm_concentracao_multiplo_alertas_global", lambda: alertas.lazy())
    monkeypatch.setattr(dc, "scan_crm_raiox_tx_global", lambda: autorizacoes.lazy())
    monkeypatch.setattr(dc, "get_global_cache_signature", lambda nome: (nome, *assinatura))


def test_build_writes_one_row_per_doctor_and_window_with_source_signature(tmp_path, monkeypatch):
    destino = tmp_path / "ponte.smod"
    _instalar(monkeypatch)
    progresso = []
    ponte.construir(str(destino), progresso.append)

    assert progresso == [5, 80, 100]
    assert not (tmp_path / "ponte.smod.tmp").exists()
    gravado = pl.read_parquet(destino)
    assert dict(gravado.schema) == {
        "id_medico": pl.Utf8, "id_cnpj": pl.Int32, "competencia": pl.Int32, "dt_alerta": pl.Utf8,
        "hr_janela": pl.Int32, "dt_ini_concentracao": pl.Datetime, "nu_autorizacoes_crm": pl.Int32,
        "id_severidade": pl.Int32, ponte.COLUNA_VERSAO: pl.Int32,
    }
    assert gravado.select(["id_medico", "dt_alerta", "hr_janela", "nu_autorizacoes_crm", "id_severidade"]).to_dicts() == [
        {"id_medico": "A/SP", "dt_alerta": "2024-01-05", "hr_janela": 10, "nu_autorizacoes_crm": 2, "id_severidade": 3},
        {"id_medico": "B/RJ", "dt_alerta": "2024-01-05", "hr_janela": 10, "nu_autorizacoes_crm": 1, "id_severidade": 3},
        {"id_medico": "B/RJ", "dt_alerta": "2024-01-05", "hr_janela": 15, "nu_autorizacoes_crm": 1, "id_severidade": 1},
    ]
    assert set(gravado.get_column("id_cnpj").to_list()) == {10}
    assert set(gravado.get_column(ponte.COLUNA_VERSAO).to_list()) == {ponte.CRM_CONCENTRACAO_MULTIPLO_MEDICO_CACHE_VERSION}
    meta = json.loads(pl.read_parquet_metadata(destino)[ponte.META_CHAVE])
    assert meta == {
        "versao": ponte.CRM_CONCENTRACAO_MULTIPLO_MEDICO_CACHE_VERSION,
        "fontes": {nome: [123, 456] for nome in ponte.FONTES},
    }

    # Mesmas fontes: o modulo vale; sem progresso informado a montagem tambem funciona.
    ponte.conferir_fontes(str(destino))
    ponte.construir(str(destino))
    ponte.conferir_fontes(str(destino))


def test_source_check_rejects_missing_signature_old_version_and_changed_sources(tmp_path, monkeypatch):
    destino = tmp_path / "ponte.smod"
    _instalar(monkeypatch)
    ponte.construir(str(destino))

    # Raio-X ou alertas sincronizados de novo: a ponte antiga nao vale mais.
    monkeypatch.setattr(dc, "get_global_cache_signature", lambda nome: (nome, 999, 456))
    with pytest.raises(ponte.ModuloDesatualizado, match="montado com outra versao"):
        ponte.conferir_fontes(str(destino))

    monkeypatch.setattr(dc, "get_global_cache_signature", lambda nome: (nome, 123, 456))
    monkeypatch.setattr(ponte, "CRM_CONCENTRACAO_MULTIPLO_MEDICO_CACHE_VERSION", 99)
    with pytest.raises(ponte.ModuloDesatualizado, match="versao antiga"):
        ponte.conferir_fontes(str(destino))

    sem_assinatura = tmp_path / "sem_assinatura.smod"
    pl.DataFrame({"id_medico": ["A/SP"]}).write_parquet(sem_assinatura)
    with pytest.raises(ponte.ModuloDesatualizado, match="sem assinatura"):
        ponte.conferir_fontes(str(sem_assinatura))


def test_build_fails_visibly_on_invalid_sources(tmp_path, monkeypatch):
    destino = str(tmp_path / "ponte.smod")

    _instalar(monkeypatch, alertas=_alertas().clear())
    with pytest.raises(RuntimeError, match="vazio"):
        ponte.construir(destino)

    _instalar(monkeypatch, alertas=_alertas(dt_fim_concentracao=["sem data", "2024-01-05 15:20:00.000000"]))
    with pytest.raises(RuntimeError, match="sem inicio/fim"):
        ponte.construir(destino)

    repetida = "2024-01-05 10:00:00.000000"
    _instalar(monkeypatch, alertas=_alertas(dt_alerta=[repetida, repetida], dt_ini_concentracao=[repetida, repetida]))
    with pytest.raises(RuntimeError, match="janela repetida"):
        ponte.construir(destino)

    _instalar(monkeypatch, autorizacoes=_autorizacoes([(10, "2024-01-05", "hora invalida", "a1", "A/SP")]))
    with pytest.raises(RuntimeError, match="sem data/hora valida"):
        ponte.construir(destino)

    _instalar(monkeypatch, autorizacoes=_autorizacoes([(10, "2024-01-05", "2024-01-05 10:05:00.000000", "a1", None)]))
    with pytest.raises(RuntimeError, match="sem medico"):
        ponte.construir(destino)

    _instalar(monkeypatch, autorizacoes=_autorizacoes([(10, "2024-01-05", "2024-01-05 12:00:00.000000", "a1", "A/SP")]))
    with pytest.raises(RuntimeError, match="Nenhuma autorizacao"):
        ponte.construir(destino)
    assert not (tmp_path / "ponte.smod").exists()
