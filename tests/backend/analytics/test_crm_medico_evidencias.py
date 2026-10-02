from datetime import date, datetime

import polars as pl
import pytest
from fastapi import HTTPException

from backend.api.services.analytics import crm_medico_evidencias as evidencias


@pytest.fixture
def perfil():
    return pl.DataFrame(
        {
            "id_cnpj": [1, 2],
            "cnpj": ["11111111000111", "22222222000122"],
            "razao_social": ["Farmacia Um", "Farmacia Dois"],
            "id_ibge7": [3550308, 3304557],
            "no_municipio": ["Sao Paulo", "Rio de Janeiro"],
            "uf": ["SP", "RJ"],
        }
    )


def _unico_scan():
    return pl.DataFrame(
        {
            "id_medico": ["123/SP", "123/SP"],
            "competencia": [202401, 202401],
            "id_cnpj": [1, 2],
            "dt_alerta": ["2024-01-01", "2024-01-02"],
            "hr_janela": [9, 10],
            "dt_ini_hora": [datetime(2024, 1, 1, 9), datetime(2024, 1, 2, 10)],
            "dt_fim_hora": [datetime(2024, 1, 1, 10), datetime(2024, 1, 2, 11)],
            "nu_prescricoes_dia": [8, 12],
            "nu_minutos_dia": [20, 30],
            "taxa_hora": [24.0, 24.0],
            "id_severidade": [1, 3],
        }
    ).lazy()


def _raiox_scan():
    return pl.DataFrame(
        {
            "id_medico": ["123/SP", "999/RJ", "123/SP"],
            "id_cnpj": [1, 1, 1],
            "dt_janela": ["2024-01-03 00:00:00"] * 3,
            "data_hora": ["2024-01-03 09:10:00", "2024-01-03 09:20:00", "2024-01-03 12:00:00"],
            "num_autorizacao": ["A", "B", "C"],
            "valor_pago": [10.0, 20.0, 30.0],
        }
    ).lazy()


def _multi_alerts_scan():
    return pl.DataFrame(
        {
            "id_cnpj": [1],
            "competencia": [202401],
            "dt_alerta": ["2024-01-03"],
            "hr_janela": [9],
            "dt_ini_concentracao": ["2024-01-03 09:00:00"],
            "dt_fim_concentracao": ["2024-01-03 10:00:00"],
            "nu_prescricoes": [2],
            "nu_crms": [2],
            "nu_crms_distintos": [None],
            "nu_minutos_intervalo": [10],
            "nu_minutos_span": [20],
            "taxa_hora": [2.0],
            "id_severidade": [2],
        }
    ).lazy()


def _ponte_scan():
    """Ponte medico x janela: 123/SP e 999/RJ na janela das 09:00 da farmacia 1."""
    return pl.DataFrame(
        {
            "id_medico": ["123/SP", "999/RJ"],
            "id_cnpj": [1, 1],
            "competencia": [202401, 202401],
            "dt_ini_concentracao": [datetime(2024, 1, 3, 9), datetime(2024, 1, 3, 9)],
            "nu_autorizacoes_crm": [1, 1],
        },
        schema_overrides={"id_cnpj": pl.Int32, "competencia": pl.Int32, "nu_autorizacoes_crm": pl.Int32},
    ).lazy()


def _geografico_scan():
    return pl.DataFrame(
        {
            "competencia": [202401], "id_medico": ["123/SP"],
            "cnpj_a": ["11111111000111"], "no_municipio_a": ["Sao Paulo"], "sg_uf_a": ["SP"],
            "dt_ini_a": ["2024-01-01"], "dt_fim_a": ["2024-01-31"], "nu_prescricoes_a": [5],
            "vl_autorizacoes_a": [50.0], "cnpj_b": ["22222222000122"],
            "no_municipio_b": ["Rio de Janeiro"], "sg_uf_b": ["RJ"], "dt_ini_b": ["2024-01-01"],
            "dt_fim_b": ["2024-01-31"], "nu_prescricoes_b": [6], "vl_autorizacoes_b": [60.0],
            "vl_autorizacoes_total": [110.0], "distancia_km": [360.5],
        }
    ).lazy()


def _install_scans(monkeypatch, perfil, *, unico=None, raiox=None, multiplos=None, geografico=None, ponte=None):
    monkeypatch.setattr(evidencias, "get_df_perfil_estabelecimento", lambda: perfil)
    monkeypatch.setattr(evidencias, "scan_crm_concentracao_unico_alertas_global", lambda: unico if unico is not None else _unico_scan())
    monkeypatch.setattr(evidencias, "scan_crm_raiox_tx_global", lambda: raiox if raiox is not None else _raiox_scan())
    monkeypatch.setattr(evidencias, "scan_crm_concentracao_multiplo_alertas_global", lambda: multiplos if multiplos is not None else _multi_alerts_scan())
    monkeypatch.setattr(evidencias, "scan_geografico_global", lambda: geografico if geografico is not None else _geografico_scan())
    monkeypatch.setattr(evidencias, "scan_crm_concentracao_multiplo_medico_global", lambda: ponte if ponte is not None else _ponte_scan())
    monkeypatch.setattr(evidencias, "conferir_crm_concentracao_multiplo_medico_global", lambda: None)


def test_farmacia_and_municipality_helpers_require_unique_records(monkeypatch, perfil):
    _install_scans(monkeypatch, perfil)
    assert evidencias._cadastro([]).is_empty()
    assert evidencias._cadastro([1]).get_column("municipio").to_list() == ["Sao Paulo"]
    with pytest.raises(HTTPException) as missing:
        evidencias._cadastro([99])
    assert missing.value.status_code == 503
    assert evidencias._cnpj_da_farmacia(1) == "11111111000111"
    evidencias.conferir_farmacia_no_municipio(1, 3550308)
    assert evidencias.nome_do_municipio(3304557) == ("Rio de Janeiro", "RJ")
    with pytest.raises(HTTPException) as no_pharmacy:
        evidencias._cnpj_da_farmacia(99)
    assert no_pharmacy.value.status_code == 422
    with pytest.raises(HTTPException, match="nao encontrada no perfil"):
        evidencias.conferir_farmacia_no_municipio(99, 3550308)
    with pytest.raises(HTTPException, match="nao pertence ao municipio"):
        evidencias.conferir_farmacia_no_municipio(1, 3304557)
    with pytest.raises(HTTPException, match="sem farmacias"):
        evidencias.nome_do_municipio(999)


def test_single_crm_sequences_cast_fields_filter_pharmacy_and_reject_unknown_severity(monkeypatch, perfil):
    _install_scans(monkeypatch, perfil)
    full = evidencias._unico("123/SP", 202401, 202412, None)
    assert full.height == 2
    assert full.get_column("dt").to_list() == ["2024-01-01", "2024-01-02"]
    assert evidencias._unico("123/SP", 202401, 202412, 3).is_empty()
    assert evidencias._multiplos("123/SP", 202401, 202412, 2).is_empty()
    invalid = _unico_scan().with_columns(pl.lit(99).alias("id_severidade"))
    _install_scans(monkeypatch, perfil, unico=invalid)
    with pytest.raises(HTTPException) as error:
        evidencias._unico("123/SP", 202401, 202412, None)
    assert error.value.status_code == 503


def test_multiple_crm_sequences_read_bridge_and_reject_inconsistent_modules(monkeypatch, perfil):
    # Medico sem janela na ponte (ou fora da farmacia filtrada): nenhuma evidencia.
    _install_scans(monkeypatch, perfil, ponte=_ponte_scan().filter(pl.lit(False)))
    assert evidencias._multiplos("123/SP", 202401, 202412, None).is_empty()
    _install_scans(monkeypatch, perfil)
    assert evidencias._multiplos("123/SP", 202401, 202412, 2).is_empty()
    assert evidencias._multiplos("123/SP", 202402, 202412, None).is_empty()

    # Janela na ponte sem alerta correspondente: modulos de execucoes diferentes.
    empty_alerts = _multi_alerts_scan().filter(pl.lit(False))
    _install_scans(monkeypatch, perfil, multiplos=empty_alerts)
    with pytest.raises(HTTPException, match="sem alerta correspondente") as mismatch:
        evidencias._multiplos("123/SP", 202401, 202412, None)
    assert mismatch.value.status_code == 503

    missing_window = _multi_alerts_scan().with_columns(pl.lit(None, dtype=pl.String).alias("dt_ini_concentracao"))
    _install_scans(monkeypatch, perfil, multiplos=missing_window)
    with pytest.raises(HTTPException, match="sem inicio/fim"):
        evidencias._multiplos("123/SP", 202401, 202412, None)

    invalid_severity = _multi_alerts_scan().with_columns(pl.lit(7).alias("id_severidade"))
    _install_scans(monkeypatch, perfil, multiplos=invalid_severity)
    with pytest.raises(HTTPException, match="Severidade desconhecida"):
        evidencias._multiplos("123/SP", 202401, 202412, None)

    # Ponte montada com outras fontes: a conferencia falha antes de qualquer leitura.
    _install_scans(monkeypatch, perfil)

    def stale():
        raise RuntimeError("modulo desatualizado")

    monkeypatch.setattr(evidencias, "conferir_crm_concentracao_multiplo_medico_global", stale)
    with pytest.raises(RuntimeError, match="modulo desatualizado"):
        evidencias._multiplos("123/SP", 202401, 202412, None)

    _install_scans(monkeypatch, perfil)
    crossed = evidencias._multiplos("123/SP", 202401, 202412, None)
    assert crossed.height == 1
    assert crossed.item(0, "dt") == "2024-01-03" and crossed.item(0, "hr_janela") == 9
    assert crossed.item(0, "nu_autorizacoes_crm") == 1
    assert crossed.item(0, "nu_autorizacoes_total") == 2
    assert crossed.item(0, "nu_crms") == 2


def test_distance_pairs_add_cadastral_ids_and_reject_missing_distance_or_pharmacy(monkeypatch, perfil):
    _install_scans(monkeypatch, perfil)
    pair = evidencias._distancia("123/SP", 202401, 202412, 1)
    assert pair.item(0, "razao_social_a") == "Farmacia Um"
    assert pair.item(0, "id_ibge7_b") == 3304557
    with pytest.raises(HTTPException) as missing_cnpj:
        evidencias._distancia("123/SP", 202401, 202412, 99)
    assert missing_cnpj.value.status_code == 422
    invalid_distance = _geografico_scan().with_columns(pl.lit(None, dtype=pl.Float64).alias("distancia_km"))
    _install_scans(monkeypatch, perfil, geografico=invalid_distance)
    with pytest.raises(HTTPException, match="sem distancia calculada"):
        evidencias._distancia("123/SP", 202401, 202412, None)
    _install_scans(monkeypatch, perfil.head(1))
    with pytest.raises(HTTPException, match="sem cadastro no perfil"):
        evidencias._distancia("123/SP", 202401, 202412, None)


def test_evidence_cache_municipality_cut_and_invalid_combined_filter(monkeypatch, perfil):
    _install_scans(monkeypatch, perfil)

    class ImmediateCache:
        def obter(self, _key, calculate):
            return calculate()

    monkeypatch.setattr(evidencias, "_CACHE", ImmediateCache())
    full = evidencias.evidencias_do_medico("123/SP", date(2024, 1, 1), date(2024, 12, 31), None)
    assert full.unico.height == 2 and full.multiplos.height == 1 and full.distancia.height == 1
    municipal = evidencias.evidencias_do_medico(
        "123/SP", date(2024, 1, 1), date(2024, 12, 31), None, 3550308
    )
    assert municipal.unico.get_column("id_cnpj").to_list() == [1]
    assert municipal.distancia.height == 1
    with pytest.raises(HTTPException, match="nao pertence ao municipio"):
        evidencias.evidencias_do_medico("123/SP", date(2024, 1, 1), date(2024, 12, 31), 1, 3304557)


def test_evidence_builder_passes_http_errors_and_wraps_unexpected_errors(monkeypatch, perfil):
    _install_scans(monkeypatch, perfil)

    class ImmediateCache:
        def obter(self, _key, calculate):
            return calculate()

    monkeypatch.setattr(evidencias, "_CACHE", ImmediateCache())
    monkeypatch.setattr(evidencias, "_unico", lambda *args: (_ for _ in ()).throw(HTTPException(418, "teapot")))
    with pytest.raises(HTTPException) as expected:
        evidencias.evidencias_do_medico("123/SP", date(2024, 1, 1), date(2024, 12, 31), None)
    assert expected.value.status_code == 418

    monkeypatch.setattr(evidencias, "_unico", lambda *args: (_ for _ in ()).throw(ValueError("broken source")))
    with pytest.raises(HTTPException, match="Alertas do CRM indisponiveis: broken source") as wrapped:
        evidencias.evidencias_do_medico("123/SP", date(2024, 1, 1), date(2024, 12, 31), None)
    assert wrapped.value.status_code == 503


def test_public_evidence_validation_pagination_summaries_and_types(monkeypatch, perfil):
    _install_scans(monkeypatch, perfil)

    class ImmediateCache:
        def obter(self, _key, calculate):
            return calculate()

    monkeypatch.setattr(evidencias, "_CACHE", ImmediateCache())
    response = evidencias.get_crm_medico_evidencias(
        id_medico=" 123/SP ", tipo="unico", severidade=1, page=1, page_size=1
    )
    assert response.id_medico == "123/SP"
    assert response.total == 1 and response.resumo_unico.qtd_alertas == 2
    assert response.resumo_unico.por_severidade["1"] == 1
    assert response.linhas_unico[0].cnpj == "11111111000111"
    assert evidencias.get_crm_medico_evidencias(id_medico="123/SP", tipo="distancia").resumo_distancia.maior_distancia_km == 360.5
    assert evidencias.get_crm_medico_evidencias(id_medico="123/SP", tipo="multiplos").linhas_multiplos[0].nu_autorizacoes_crm == 1
    for kwargs, message in (
        ({"id_medico": " ", "tipo": "unico"}, "id_medico obrigatorio"),
        ({"id_medico": "1", "tipo": "bad"}, "tipo deve ser"),
        ({"id_medico": "1", "tipo": "unico", "sort_field": "bad"}, "Ordenacao invalida"),
        ({"id_medico": "1", "tipo": "distancia", "severidade": 1}, "severidade vale so"),
        ({"id_medico": "1", "tipo": "unico", "severidade": 9}, "severidade vale so"),
        ({"id_medico": "1", "tipo": "unico", "sort_order": "bad"}, "sort_order deve ser"),
    ):
        with pytest.raises(HTTPException, match=message):
            evidencias.get_crm_medico_evidencias(**kwargs)


def test_doctor_lookup_handles_missing_unique_and_duplicate_records(monkeypatch):
    monkeypatch.setattr(evidencias, "get_dados_medico_df", lambda: pl.DataFrame({"id_medico": ["1", "2"], "no_medico": ["Ana", "Bia"]}))
    assert evidencias.nome_do_medico("1") == "Ana"
    assert evidencias.nome_do_medico("3") is None
    monkeypatch.setattr(evidencias, "get_dados_medico_df", lambda: pl.DataFrame({"id_medico": ["1", "1"], "no_medico": ["Ana", "Outra"]}))
    with pytest.raises(HTTPException) as duplicate:
        evidencias.nome_do_medico("1")
    assert duplicate.value.status_code == 503


def test_authorization_window_validation_and_success(monkeypatch, perfil):
    _install_scans(monkeypatch, perfil)
    medico_data = pl.DataFrame({"id_medico": ["123/SP", "999/RJ"], "no_medico": ["Dra Ana", "Dr Bia"]})
    monkeypatch.setattr(evidencias, "get_dados_medico_df", lambda: medico_data)
    start, end = datetime(2024, 1, 3, 9), datetime(2024, 1, 3, 10)
    response = evidencias.get_crm_evidencia_autorizacoes(
        id_cnpj=1, id_medico="123/SP", inicio=start, fim=end
    )
    assert response.qtd_autorizacoes == 2
    assert response.qtd_autorizacoes_crm == 1
    assert response.qtd_crms == 2 and response.valor_total == 30.0
    assert response.autorizacoes[0].do_crm is True
    for medico, begin, finish, message in (
        (" ", start, end, "id_medico obrigatorio"),
        ("1", end, start, "A janela deve"),
        ("1", start, datetime(2024, 1, 4, 10), "A janela deve"),
        ("1", start, datetime(2024, 1, 3, 16, 1), "Janela maior que"),
    ):
        with pytest.raises(HTTPException, match=message):
            evidencias.get_crm_evidencia_autorizacoes(id_cnpj=1, id_medico=medico, inicio=begin, fim=finish)


def test_authorization_window_reports_bad_cache_contracts(monkeypatch, perfil):
    _install_scans(monkeypatch, perfil)
    monkeypatch.setattr(evidencias, "get_dados_medico_df", lambda: pl.DataFrame({"id_medico": [], "no_medico": []}, schema_overrides={"id_medico": pl.String, "no_medico": pl.String}))
    start, end = datetime(2024, 1, 3, 9), datetime(2024, 1, 3, 10)
    broken = _raiox_scan().with_columns(pl.lit(None, dtype=pl.String).alias("data_hora"))
    _install_scans(monkeypatch, perfil, raiox=broken)
    with pytest.raises(HTTPException, match="sem data/hora valida"):
        evidencias.get_crm_evidencia_autorizacoes(id_cnpj=1, id_medico="123/SP", inicio=start, fim=end)

    _install_scans(monkeypatch, perfil, raiox=pl.DataFrame({"id_cnpj": [], "dt_janela": []}).lazy())
    with pytest.raises(HTTPException, match="indisponivel"):
        evidencias.get_crm_evidencia_autorizacoes(id_cnpj=1, id_medico="123/SP", inicio=start, fim=end)
    broken = _raiox_scan().with_columns(pl.lit(None, dtype=pl.String).alias("data_hora"))
    _install_scans(monkeypatch, perfil, raiox=broken)
    with pytest.raises(HTTPException, match="sem data/hora valida"):
        evidencias.get_crm_evidencia_autorizacoes(id_cnpj=1, id_medico="123/SP", inicio=start, fim=end)
