from datetime import date, datetime
from decimal import Decimal
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory

import polars as pl
import pytest
from fastapi import HTTPException

from backend.api.services.analytics import crm
from backend.cache_producers.types import CacheLoadResult


@pytest.fixture
def temp_dir():
    with TemporaryDirectory(prefix="sentinela-crm-tests-", dir=Path.cwd()) as directory:
        yield Path(directory)


def test_crm_timing_formatter_and_enabled_log_writer(temp_dir, monkeypatch):
    assert crm._format_timing_ms(999.94) == "999.9ms"
    assert crm._format_timing_ms(1000) == "1.000s"
    disabled = crm._CrmTiming("1", None, None)
    disabled.mark("ignored")
    disabled.detail("x", 1)
    disabled.write()
    assert disabled.steps == [] and disabled.details == {}

    fake_module = temp_dir / "backend/api/services/analytics/crm.py"
    fake_module.parent.mkdir(parents=True)
    monkeypatch.setattr(crm, "__file__", str(fake_module))
    timing = crm._CrmTiming("123", "2024-01", None, enabled=True)
    timing.mark("loaded cache")
    timing.detail("rows", 4)
    timing.write("ERROR", "diagnostic")
    log = temp_dir / "logs/crm_timing.log"
    content = log.read_text(encoding="utf-8")
    assert "inicio-aberto" not in content and "2024-01 a fim-aberto" in content
    assert "loaded cache" in content and "rows: 4" in content and "Erro: diagnostic" in content


def test_crm_scalar_normalizers_cover_python_numeric_text_and_invalid_inputs():
    assert crm._to_float(None, 2.5) == 2.5
    assert crm._to_float(True) == 1.0
    assert crm._to_float(Decimal("1.25")) == 1.25
    assert crm._to_float(b"1,5") == 1.5
    assert crm._to_float("  ", 7) == 7
    assert crm._to_float("bad", 8) == 8
    assert crm._to_float(object(), 9) == 9
    assert crm._to_optional_float(None) is None
    assert crm._to_optional_float(False) == 0.0
    assert crm._to_optional_float(Decimal("2.5")) == 2.5
    assert crm._to_optional_float("nan") is None
    assert crm._to_optional_float(b"bad") is None
    assert crm._to_optional_float("") is None
    assert crm._to_optional_float(object()) is None
    assert crm._to_int(None, 4) == 4
    assert crm._to_int(True) == 1
    assert crm._to_int(5) == 5
    assert crm._to_int(Decimal("5.8")) == 5
    assert crm._to_int(b"6,8") == 6
    assert crm._to_int(" ", 7) == 7
    assert crm._to_int("bad", 8) == 8
    assert crm._to_int(object(), 9) == 9


def test_crm_cache_errors_competencia_filter_and_row_count_helpers():
    with pytest.raises(HTTPException) as unavailable:
        crm._raise_cache_unavailable("CRM", None)
    assert unavailable.value.status_code == 503 and "falha ao sincronizar" in unavailable.value.detail
    with pytest.raises(HTTPException) as detailed:
        crm._raise_cache_unavailable("CRM", "offline")
    assert "offline" in detailed.value.detail
    assert crm._to_comp("2024-09-01") == 202409
    assert crm._filter_competencia(None, None, None) is None
    empty = pl.DataFrame(schema={"competencia": pl.Int32})
    assert crm._filter_competencia(empty, 202401, 202412).is_empty()
    data = pl.DataFrame({"competencia": [202312, 202401, 202406, 202501], "id_medico": ["a", "a", "b", "b"]})
    assert crm._filter_competencia(data, 202401, 202406).get_column("competencia").to_list() == [202401, 202406]
    assert crm._count_rows_by_medico(None) == {}
    assert crm._count_rows_by_medico(pl.DataFrame({"other": [1]})) == {}
    assert crm._count_rows_by_medico(data) == {"a": 2, "b": 2}


def test_crm_unico_alertas_group_by_medico_and_empty_input():
    assert crm._build_crm_unico_alertas_por_medico(pl.DataFrame()) == {}
    alerts = pl.DataFrame(
        {
            "id_medico": ["A", "A", "B"], "dt_alerta": ["2024-01-01", "2024-01-02", "2024-01-01"],
            "nu_prescricoes_dia": [10, 11, 12], "nu_minutos_dia": [2, 3, 4],
            "nu_minutos_intervalo": [1, None, 2], "taxa_hora": ["300.0", "bad", "180.0"],
            "dt_ini_hora": [None, "x", "y"], "dt_fim_hora": [None, "z", "q"], "id_severidade": ["1", "2", "3"],
        }
    )
    output = crm._build_crm_unico_alertas_por_medico(alerts)
    assert len(output["A"]) == 2 and len(output["B"]) == 1
    assert output["A"][0]["dt_ini_hora"] == "" and output["A"][0]["taxa_hora"] == 300.0
    assert output["A"][1]["taxa_hora"] == 0.0 and output["A"][1]["id_severidade"] == 2


def test_crm_rhythm_concentration_and_alert_type_maps():
    assert crm._best_crm_rhythm_from_row({"nu_5min": 2, "nu_10min": 8}, (5, 10)) == (48.0, 8, 10)
    assert crm._best_crm_rhythm_from_row({"nu_5min": None}, (5,)) == (0.0, None, None)
    assert crm._build_crm_rhythm_map(pl.DataFrame(), "date", (5,)) == {}
    rhythm = pl.DataFrame(
        {
            "day": ["2024-01-01", "2024-01-01", "2024-01-02", ""],
            "nu_prescricoes": [10, 1, 0, 2], "nu_minutos_span": [5, 5, 0, 1],
            "nu_5min": [None, None, 0, 1], "id_medico": ["A", "B", "C", "D"], "nu_crms": [2, 1, None, 1],
        }
    )
    rhythm_map = crm._build_crm_rhythm_map(rhythm, "day", (5,), id_col="id_medico", crms_col="nu_crms")
    assert rhythm_map["2024-01-01"]["id_medico"] == "A"
    assert rhythm_map["2024-01-01"]["nu_crms"] == 2
    assert "2024-01-02" not in rhythm_map and "" not in rhythm_map

    assert crm._build_crm_unico_concentration_map(pl.DataFrame()) == {}
    concentration = crm._build_crm_unico_concentration_map(
        pl.DataFrame(
            {
                "nu_prescricoes_dia": [10, 1, 20], "nu_minutos_dia": [5, 0, 4],
                "dt_alerta": ["2024-01-01", "2024-01-01", "2024-01-02"], "id_medico": ["A", "B", "C"],
            }
        )
    )
    assert concentration["2024-01-01"]["id_medico"] == "A"
    assert concentration["2024-01-02"]["score"] == 300.0
    assert crm._crm_hour_alert_types({"is_volume_horario_anomalo": "1", "is_crm_unico": 1, "is_crm_multiplo": True}) == [
        "volume_horario", "crm_unico", "crm_multiplo"
    ]
    assert crm._crm_hour_alert_types({}) == []


def test_crm_rhythm_maps_handle_numeric_corruption_and_duplicate_days():
    invalid_number = Decimal("NaN")
    assert crm._best_crm_rhythm_from_row({"nu_5min": invalid_number}, (5,)) == (0.0, None, None)

    malformed_rhythm = pl.DataFrame([
        pl.Series("day", ["2024-01-01"]),
        pl.Series("nu_prescricoes", [invalid_number], dtype=pl.Object),
        pl.Series("nu_minutos_span", [invalid_number], dtype=pl.Object),
        pl.Series("nu_5min", [invalid_number], dtype=pl.Object),
    ])
    assert crm._build_crm_rhythm_map(malformed_rhythm, "day", (5,)) == {}

    malformed_crm_count = pl.DataFrame([
        pl.Series("day", ["2024-01-01"]),
        pl.Series("nu_prescricoes", [10]),
        pl.Series("nu_minutos_span", [5]),
        pl.Series("nu_crms", [invalid_number], dtype=pl.Object),
        pl.Series("id_medico", ["CRM-A"]),
    ])
    rhythm = crm._build_crm_rhythm_map(
        malformed_crm_count, "day", (5,), id_col="id_medico", crms_col="nu_crms"
    )
    assert rhythm["2024-01-01"]["nu_crms"] is None

    concentration = crm._build_crm_unico_concentration_map(pl.DataFrame([
        pl.Series("nu_prescricoes_dia", [invalid_number, 10, 5, 1], dtype=pl.Object),
        pl.Series("nu_minutos_dia", [5, 5, 5, 1]),
        pl.Series("dt_alerta", ["2024-01-03", "2024-01-01", "2024-01-01", ""]),
        pl.Series("id_medico", ["X", "A", "B", "C"]),
    ]))
    assert concentration["2024-01-01"]["id_medico"] == "A"
    assert "" not in concentration


def test_timeline_filters_aggregates_and_orders_events_by_date():
    empty = pl.DataFrame(schema={"dt_janela": pl.String})
    assert crm._filter_crm_date_range(empty, "dt_janela", "2024-01", "2024-02").is_empty()
    activity = pl.DataFrame(
        {
            "dt_janela": ["2024-02-01 00:00:00", "2024-01-01 09:00:00"],
            "hr_janela": [0, 9], "nu_prescricoes": [5, 8], "nu_crms_diferentes": [2, 3],
            "mediana_hora": [2.0, 3.0], "is_volume_horario_anomalo": [0, 1],
            "is_crm_unico": [0, 0], "is_crm_multiplo": [1, 0],
        }
    )
    filtered = crm._filter_crm_date_range(activity, "dt_janela", "2024-01", "2024-01")
    assert filtered.height == 1
    hours = crm._build_timeline_hours_by_date(filtered)
    assert list(hours) == ["2024-01-01"] and len(hours["2024-01-01"]) == 24
    assert hours["2024-01-01"][9]["alert_types"] == ["volume_horario"]
    assert hours["2024-01-01"][0]["is_hora_com_alerta"] == 0
    assert crm._sum_timing(None, None) is None
    assert crm._sum_timing(2, None, 3.5) == 5.5

    assert crm._build_timeline_events_by_date(pl.DataFrame()) == {}
    events = pl.DataFrame(
        {
            "dt_janela": ["2024-01-01 08:00:00", "2024-01-01 08:00:00"],
            "tipo": ["b", "a"], "hora_inicio": ["08:02", "08:01"], "hora_fim": ["08:03", "08:02"],
            "minuto_inicio": [2, 1], "minuto_fim": [3, 2], "severidade": [1, 2],
            "id_medico": ["B", "A"], "nu_crms_distintos": [2, 1],
        }
    )
    output = crm._build_timeline_events_by_date(events)
    assert [event["minuto_inicio"] for event in output["2024-01-01"]] == [1, 2]


def test_crm_alert_time_and_hour_overlap_helpers():
    assert crm._format_alert_time(None) is None
    assert crm._format_alert_time(datetime(2024, 1, 1, 9, 30)) == "09:30"
    assert crm._format_alert_time("2024-01-01 09:35:00") == "09:35"
    assert crm._extract_alert_hour(None) is None
    assert crm._extract_alert_hour(datetime(2024, 1, 1, 9, 30)) == 9
    assert crm._extract_alert_hour("2024-01-01 09:35:00") == 9
    assert crm._extract_alert_hour("invalid") is None
    assert crm._alert_overlaps_hour("invalid", "invalid", None) is True
    assert crm._alert_overlaps_hour("invalid", "invalid", 8) is False
    assert crm._alert_overlaps_hour(None, "2024-01-01 11:00", 11) is True
    assert crm._alert_overlaps_hour("2024-01-01 22:00", None, 22) is True
    assert crm._alert_overlaps_hour("2024-01-01 22:00", "2024-01-01 02:00", 1) is True
    assert crm._alert_overlaps_hour("2024-01-01 09:00", "2024-01-01 12:00", 11) is True
    assert crm._alert_overlaps_hour("2024-01-01 09:00", "2024-01-01 12:00", 13) is False


def test_crm_alert_cache_loaders_expose_error_and_empty_contract(monkeypatch):
    monkeypatch.setattr(crm, "load_or_sync_crm_unico_alertas", lambda _: CacheLoadResult(None, False, error="unico indisponivel"))
    with pytest.raises(HTTPException) as unico_error:
        crm._load_crm_unico_alertas("1", "unused")
    assert unico_error.value.status_code == 503
    monkeypatch.setattr(crm, "load_or_sync_crm_unico_alertas", lambda _: CacheLoadResult(None, False))
    assert crm._load_crm_unico_alertas("1", "unused").is_empty()
    frame = pl.DataFrame({"x": [1]})
    monkeypatch.setattr(crm, "load_or_sync_crm_multi_alertas", lambda _: CacheLoadResult(frame, True))
    assert crm._load_crm_multi_alertas("1", "unused").equals(frame)
    monkeypatch.setattr(crm, "load_or_sync_crm_multi_alertas", lambda _: CacheLoadResult(None, False, error="multi unavailable"))
    with pytest.raises(HTTPException, match="multi unavailable"):
        crm._load_crm_multi_alertas("1", "unused")


def test_crm_multiple_alerts_join_transactions_inside_alert_windows(temp_dir):
    transactions = pl.DataFrame(
        {
            "dt_janela": ["2024-01-15", "2024-01-15", "2024-02-15"],
            "data_hora": ["2024-01-15 09:05:00", "2024-01-15 09:45:00", "2024-02-15 09:10:00"],
            "id_medico": ["CRM-A", "CRM-B", "CRM-A"],
            "num_autorizacao": ["A1", "B1", "A2"],
        }
    )
    transactions.write_parquet(temp_dir / crm.CRM_RAIOX_TX_PARQUET)
    alerts = pl.DataFrame(
        {
            "dt_alerta": ["2024-01-15", "2024-02-15"], "competencia": [202401, 202402],
            "dt_ini_concentracao": ["2024-01-15 09:00:00", "2024-02-15 09:00:00"],
            "dt_fim_concentracao": ["2024-01-15 09:30:00", "2024-02-15 09:30:00"],
            "hr_janela": [9, 9], "nu_prescricoes": [6, 3], "nu_crms": [2, 1],
            "nu_crms_distintos": [2, 1], "nu_minutos_intervalo": [30, 15], "nu_minutos_span": [30, 15],
            "taxa_hora": [12.0, 12.0], "id_severidade": [2, 1], "severidade": ["ALTO", "MODERADO"],
            "criterio_pior_ritmo": ["5min", "10min"],
        }
    )
    timing = crm._CrmTiming("1", None, None, enabled=True)

    grouped = crm._build_alertas_crm_multiplos_por_medico(
        str(temp_dir), alerts, 202401, 202401, timing
    )

    assert list(grouped) == ["CRM-A"]
    assert grouped["CRM-A"][0]["nu_presc_crm"] == 1
    assert grouped["CRM-A"][0]["nu_presc_total"] == 6
    assert grouped["CRM-A"][0]["nu_crms_total"] == 2
    assert grouped["CRM-A"][0]["descricao"] == "6 autorizacoes entre 09:00 e 09:30, envolvendo 2 CRMs (ALTO)"
    assert timing.details["cruzamento_join_linhas"] == 1


def test_crm_multiple_alerts_join_handles_empty_or_unmatched_inputs(temp_dir):
    assert crm._build_alertas_crm_multiplos_por_medico(
        str(temp_dir), pl.DataFrame(), None, None
    ) == {}


def test_crm_multiple_alerts_handles_empty_filtered_and_invalid_cache_inputs(temp_dir):
    cache_path = temp_dir / crm.CRM_RAIOX_TX_PARQUET
    empty_transactions = pl.DataFrame(
        schema={"dt_janela": pl.String, "data_hora": pl.String, "id_medico": pl.String, "num_autorizacao": pl.String}
    )
    empty_transactions.write_parquet(cache_path)
    alerts = pl.DataFrame({"competencia": [202401]})
    assert crm._build_alertas_crm_multiplos_por_medico(str(temp_dir), alerts, None, None) == {}

    pl.DataFrame(
        {
            "dt_janela": ["2024-01-15"], "data_hora": ["2024-01-15 09:05:00"],
            "id_medico": ["CRM-A"], "num_autorizacao": ["A1"],
        }
    ).write_parquet(cache_path)
    assert crm._build_alertas_crm_multiplos_por_medico(str(temp_dir), alerts, 202402, 202402) == {}

    timing = crm._CrmTiming("1", None, None, enabled=True)
    result = crm._build_alertas_crm_multiplos_por_medico(
        str(temp_dir), pl.DataFrame({"dt_alerta": ["2024-01-15"]}), None, None, timing
    )
    assert result == {}
    assert "cruzamento_erro" in timing.details


def test_crm_multiple_alerts_accept_date_and_datetime_columns(temp_dir):
    (pl.DataFrame(
        {
            "dt_janela": [date(2024, 1, 15)],
            "data_hora": [datetime(2024, 1, 15, 9, 5)],
            "id_medico": ["CRM-A"],
            "num_autorizacao": ["A1"],
        }
    )).write_parquet(temp_dir / crm.CRM_RAIOX_TX_PARQUET)
    alerts = pl.DataFrame(
        {
            "dt_alerta": [date(2024, 1, 15)], "competencia": [202401],
            "dt_ini_concentracao": [datetime(2024, 1, 15, 9, 0)],
            "dt_fim_concentracao": [datetime(2024, 1, 15, 9, 30)],
            "hr_janela": [9], "nu_prescricoes": [1], "nu_crms": [1],
            "nu_crms_distintos": [1], "nu_minutos_intervalo": [30], "nu_minutos_span": [30],
            "taxa_hora": [2.0], "id_severidade": [1], "severidade": ["BAIXO"],
            "criterio_pior_ritmo": ["30min"],
        }
    )
    result = crm._build_alertas_crm_multiplos_por_medico(str(temp_dir), alerts, None, None)
    assert result["CRM-A"][0]["dt"] == "2024-01-15"
    assert result["CRM-A"][0]["dt_ini_hora"].startswith("2024-01-15 09:00")
    cache_path = temp_dir / crm.CRM_RAIOX_TX_PARQUET
    pl.DataFrame(
        {
            "dt_janela": ["2024-01-15"], "data_hora": ["2024-01-15 10:00:00"],
            "id_medico": ["CRM-A"], "num_autorizacao": ["A1"],
        }
    ).write_parquet(cache_path)
    alerts = pl.DataFrame(
        {
            "dt_alerta": ["2024-01-15"], "competencia": [202401],
            "dt_ini_concentracao": ["2024-01-15 09:00:00"],
            "dt_fim_concentracao": ["2024-01-15 09:30:00"],
            "hr_janela": [9], "nu_prescricoes": [6], "nu_crms": [2],
            "nu_crms_distintos": [2], "nu_minutos_intervalo": [30], "nu_minutos_span": [30],
            "taxa_hora": [12.0], "id_severidade": [2], "severidade": ["ALTO"],
            "criterio_pior_ritmo": ["5min"],
        }
    )
    timing = crm._CrmTiming("1", None, None, enabled=True)

    assert crm._build_alertas_crm_multiplos_por_medico(
        str(temp_dir), alerts, 202401, 202401, timing
    ) == {}
    assert timing.details["cruzamento_join_linhas"] == 0
    assert crm._build_alertas_crm_multiplos_por_medico(
        str(temp_dir), pl.DataFrame(), None, None
    ) == {}


def test_crm_multiple_alerts_cast_date_typed_transaction_and_window_columns(temp_dir):
    pl.DataFrame({
        "dt_janela": [date(2024, 1, 15)],
        "data_hora": [date(2024, 1, 15)],
        "id_medico": ["CRM-A"],
        "num_autorizacao": ["A1"],
    }).write_parquet(temp_dir / crm.CRM_RAIOX_TX_PARQUET)
    alerts = pl.DataFrame({
        "dt_alerta": [date(2024, 1, 15)],
        "competencia": [202401],
        "dt_ini_concentracao": [date(2024, 1, 15)],
        "dt_fim_concentracao": [date(2024, 1, 15)],
        "hr_janela": [0],
        "nu_prescricoes": [1],
        "nu_crms": [1],
        "nu_crms_distintos": [1],
        "nu_minutos_intervalo": [0],
        "nu_minutos_span": [0],
        "taxa_hora": [1.0],
        "id_severidade": [1],
        "severidade": ["BAIXO"],
        "criterio_pior_ritmo": ["instantâneo"],
    })

    result = crm._build_alertas_crm_multiplos_por_medico(str(temp_dir), alerts, None, None)

    assert len(result["CRM-A"]) == 1
    assert result["CRM-A"][0]["nu_presc_total"] == 1


def test_load_crm_prescription_days_uses_local_and_brazil_monthly_sources(monkeypatch):
    cnpj = "00123456000199"
    monkeypatch.setattr(
        crm, "get_df_perfil_estabelecimento",
        lambda: pl.DataFrame({"cnpj": [cnpj], "id_cnpj": [7]}),
    )
    local = pl.DataFrame(
        {
            "id_cnpj": [7], "id_medico": ["CRM-A"], "competencia": [202402],
            "nu_prescricoes_mes": [28], "qtd_dias_com_prescricao_mes": [14],
        }
    )
    brasil = pl.DataFrame(
        {
            "id_medico": ["CRM-A"], "competencia": [202402],
            "nu_prescricoes_mes": [56], "qtd_dias_com_prescricao_mes": [20],
        }
    )
    monkeypatch.setattr(crm, "scan_crm_medico_estabelecimento_mes", lambda: local.lazy())
    monkeypatch.setattr(crm, "scan_crm_medico_brasil_mes", lambda: brasil.lazy())
    profile = pl.DataFrame(
        {
            "id_medico": ["CRM-A"], "competencia": [202402],
            "nu_prescricoes_mes": [28], "nu_prescricoes_total_brasil": [56],
        }
    )

    result = crm._load_crm_prescription_days(cnpj, profile)

    assert result["_dias_ativos"].to_list() == [14]
    assert result["_dias_ativos_brasil"].to_list() == [20]
    assert result["nu_prescricoes_mes"].to_list() == [28]
    assert result["nu_prescricoes_total_brasil"].to_list() == [56]


def test_load_crm_prescription_days_rejects_duplicate_and_inconsistent_sources(monkeypatch):
    cnpj = "00123456000199"
    monkeypatch.setattr(
        crm, "get_df_perfil_estabelecimento",
        lambda: pl.DataFrame({"cnpj": [cnpj], "id_cnpj": [7]}),
    )
    profile = pl.DataFrame(
        {
            "id_medico": ["CRM-A"], "competencia": [202401],
            "nu_prescricoes_mes": [10], "nu_prescricoes_total_brasil": [20],
        }
    )
    local = pl.DataFrame(
        {
            "id_cnpj": [7, 7], "id_medico": ["CRM-A", "CRM-A"], "competencia": [202401, 202401],
            "nu_prescricoes_mes": [10, 10], "qtd_dias_com_prescricao_mes": [5, 5],
        }
    )
    brasil = pl.DataFrame(
        {
            "id_medico": ["CRM-A"], "competencia": [202401],
            "nu_prescricoes_mes": [20], "qtd_dias_com_prescricao_mes": [10],
        }
    )
    monkeypatch.setattr(crm, "scan_crm_medico_estabelecimento_mes", lambda: local.lazy())
    monkeypatch.setattr(crm, "scan_crm_medico_brasil_mes", lambda: brasil.lazy())
    with pytest.raises(HTTPException, match="registros mensais duplicados"):
        crm._load_crm_prescription_days(cnpj, pl.concat([profile, profile]))
    with pytest.raises(HTTPException, match="registros mensais duplicados"):
        crm._load_crm_prescription_days(cnpj, profile)

    local = local.head(1).with_columns(pl.lit(9).alias("nu_prescricoes_mes"))
    monkeypatch.setattr(crm, "scan_crm_medico_estabelecimento_mes", lambda: local.lazy())
    with pytest.raises(HTTPException, match="Bases CRM local incompatíveis"):
        crm._load_crm_prescription_days(cnpj, profile)


def test_load_crm_prescription_days_rejects_bad_schema_and_brazil_scope(monkeypatch):
    cnpj = "00123456000199"
    profile = pl.DataFrame(
        {"id_medico": ["CRM-A"], "competencia": [202401], "nu_prescricoes_mes": [10], "nu_prescricoes_total_brasil": [20]}
    )
    monkeypatch.setattr(
        crm, "get_df_perfil_estabelecimento",
        lambda: pl.DataFrame({"cnpj": [cnpj], "id_cnpj": [7]}),
    )
    local = pl.DataFrame(
        {"id_cnpj": [7], "id_medico": ["CRM-A"], "competencia": [202401], "nu_prescricoes_mes": [10], "qtd_dias_com_prescricao_mes": [5]}
    )
    monkeypatch.setattr(crm, "scan_crm_medico_estabelecimento_mes", lambda: local.lazy())
    monkeypatch.setattr(crm, "scan_crm_medico_brasil_mes", lambda: pl.DataFrame({"id_medico": ["CRM-A"]}).lazy())
    with pytest.raises(HTTPException, match="sem colunas obrigatórias"):
        crm._load_crm_prescription_days(cnpj, profile)

    brasil = pl.DataFrame(
        {"id_medico": ["CRM-A"], "competencia": [202401], "nu_prescricoes_mes": [20], "qtd_dias_com_prescricao_mes": [3]}
    )
    monkeypatch.setattr(crm, "scan_crm_medico_brasil_mes", lambda: brasil.lazy())
    with pytest.raises(HTTPException, match="Brasil com prescrições/dias inferiores"):
        crm._load_crm_prescription_days(cnpj, profile)

    monkeypatch.setattr(
        crm,
        "scan_crm_medico_estabelecimento_mes",
        lambda: (_ for _ in ()).throw(HTTPException(status_code=418, detail="source contract error")),
    )
    with pytest.raises(HTTPException) as original_http_error:
        crm._load_crm_prescription_days(cnpj, profile)
    assert original_http_error.value.status_code == 418


def test_crm_identifier_resolution_and_month_aggregation_fail_on_invalid_scope(monkeypatch):
    monkeypatch.setattr(crm, "get_df_perfil_estabelecimento", lambda: pl.DataFrame({"cnpj": ["x"]}))
    with pytest.raises(HTTPException, match="sem cnpj/id_cnpj"):
        crm._resolve_crm_id_cnpj("x")

    monkeypatch.setattr(
        crm, "get_df_perfil_estabelecimento",
        lambda: pl.DataFrame({"cnpj": ["x", "x"], "id_cnpj": [1, 2]}),
    )
    with pytest.raises(HTTPException, match="sem id_cnpj único"):
        crm._resolve_crm_id_cnpj("x")

    monthly = pl.DataFrame(
        {
            "id_medico": ["CRM-A"], "competencia": [202401], "vl_total_prescricoes": [100.0],
            "nu_prescricoes_mes": [10], "nu_prescricoes_total_brasil": [20], "_dias_ativos": [5],
            "_dias_ativos_brasil": [10], "no_medico": ["Exemplo"], "flag_crm_invalido": [0],
            "flag_prescricao_antes_registro": [0], "alerta_concentracao_multiplos_crms": [0],
            "flag_concentracao_mesmo_crm": [1], "flag_distancia_geografica": [0],
            "dt_inscricao_crm": [date(2010, 1, 1)], "nu_estabelecimentos": [1],
        }
    )
    aggregated = crm._aggregate_crm_medico_mes(monthly)
    assert aggregated["nu_prescricoes_dia"].to_list() == [2.0]
    assert aggregated["alerta_concentracao_unico_crm"].to_list() == [1]
    with pytest.raises(RuntimeError, match="sem cobertura Brasil"):
        crm._aggregate_crm_medico_mes(monthly.with_columns(pl.lit(0).alias("nu_prescricoes_total_brasil")))


def test_get_crm_timeline_dataset_combines_daily_hourly_events_and_timings(monkeypatch):
    daily = pl.DataFrame(
        {
            "dt_janela": ["2024-01-10", "2024-02-10"], "competencia": [202401, 202402],
            "nu_prescricoes_dia": [10, 4], "nu_crms_distintos": [2, 1], "mediana_diaria": [5.0, 3.0],
            "is_dia_com_volume_horario_anomalo": [1, 0], "is_anomalo_unico": [0, 1],
            "is_crm_multiplo": [0, 0], "score_crm_unico_hora": [100.0, 200.0],
            "score_crm_unico_qtd": [10, 4], "score_crm_unico_minutos": [6, 2],
            "score_crm_unico_medico": ["A", "B"], "score_crm_multiplo_hora": [None, None],
            "score_crm_multiplo_qtd": [None, None], "score_crm_multiplo_minutos": [None, None],
            "score_crm_multiplo_crms": [None, None],
        }
    )
    hourly = pl.DataFrame(
        {
            "dt_janela": ["2024-01-10 09:00:00"], "hr_janela": [9], "nu_prescricoes": [5],
            "nu_crms_diferentes": [2], "mediana_hora": [2.0], "is_volume_horario_anomalo": [1],
            "is_crm_unico": [0], "is_crm_multiplo": [0],
        }
    )
    events = pl.DataFrame(
        {
            "dt_janela": ["2024-01-10 09:00:00"], "tipo": ["crm_unico"], "hora_inicio": ["09:00"],
            "hora_fim": ["09:05"], "minuto_inicio": [0], "minuto_fim": [5], "severidade": ["2"],
            "id_medico": ["CRM-A"], "nu_crms_distintos": [1],
        }
    )
    monkeypatch.setattr(crm, "load_or_sync_crm_timeline_dia", lambda _: CacheLoadResult(daily, True, 1, 2, 3))
    monkeypatch.setattr(crm, "load_or_sync_crm_timeline_hora", lambda _: CacheLoadResult(hourly, True, 4, 5, 6))
    monkeypatch.setattr(crm, "load_or_sync_crm_timeline_eventos", lambda _: CacheLoadResult(events, False, 7, 8, 9))
    monkeypatch.setattr(crm, "sync_crm_raiox_tx", lambda _: CacheLoadResult(None, True, 10, 11, 12))

    result = crm.get_crm_timeline_dataset("123", "2024-01", "2024-01")

    assert len(result.days) == 1
    assert result.days[0].is_anomalo == 1
    assert result.days[0].hours[9].alert_types == ["volume_horario"]
    assert result.days[0].events[0].id_medico == "CRM-A"
    assert result.from_cache is False and result.daily_from_cache is True and result.hourly_from_cache is True
    assert (result.read_time_ms, result.query_time_ms, result.save_time_ms) == (22, 26, 30)


def test_get_crm_timeline_dataset_surfaces_each_cache_error(monkeypatch):
    monkeypatch.setattr(
        crm, "load_or_sync_crm_timeline_dia",
        lambda _: CacheLoadResult(None, False, error="daily unavailable"),
    )
    with pytest.raises(HTTPException, match="daily unavailable"):
        crm.get_crm_timeline_dataset("123")

    monkeypatch.setattr(crm, "load_or_sync_crm_timeline_dia", lambda _: CacheLoadResult(pl.DataFrame(), False))
    monkeypatch.setattr(
        crm, "load_or_sync_crm_timeline_hora",
        lambda _: CacheLoadResult(None, False, error="hourly unavailable"),
    )
    with pytest.raises(HTTPException, match="hourly unavailable"):
        crm.get_crm_timeline_dataset("123")

    monkeypatch.setattr(crm, "load_or_sync_crm_timeline_hora", lambda _: CacheLoadResult(pl.DataFrame(), False))
    monkeypatch.setattr(
        crm, "load_or_sync_crm_timeline_eventos",
        lambda _: CacheLoadResult(None, False, error="events unavailable"),
    )
    with pytest.raises(HTTPException, match="events unavailable"):
        crm.get_crm_timeline_dataset("123")

    monkeypatch.setattr(crm, "load_or_sync_crm_timeline_hora", lambda _: CacheLoadResult(pl.DataFrame(), False))
    monkeypatch.setattr(crm, "load_or_sync_crm_timeline_eventos", lambda _: CacheLoadResult(pl.DataFrame(), False))
    monkeypatch.setattr(crm, "sync_crm_raiox_tx", lambda _: CacheLoadResult(None, False, error="raio-x unavailable"))
    with pytest.raises(HTTPException, match="raio-x unavailable"):
        crm.get_crm_timeline_dataset("123")


def test_get_crm_data_returns_empty_period_and_rejects_unavailable_cache(monkeypatch):
    monkeypatch.setattr(crm, "_get_cnpj_cache_dir", lambda _: "unused")
    monkeypatch.setattr(
        crm, "load_or_sync_crm_data",
        lambda _: CacheLoadResult(None, False, error="source offline"),
    )
    with pytest.raises(HTTPException) as unavailable:
        crm.get_crm_data("123")
    assert unavailable.value.status_code == 503 and "source offline" in unavailable.value.detail

    monkeypatch.setattr(crm, "load_or_sync_crm_data", lambda _: CacheLoadResult(None, True))
    with pytest.raises(HTTPException, match="Sem cache local"):
        crm.get_crm_data("123")

    monkeypatch.setattr(
        crm, "load_or_sync_crm_data",
        lambda _: CacheLoadResult(pl.DataFrame(schema={"competencia": pl.Int32}), True),
    )
    empty_result = crm.get_crm_data("123")
    assert empty_result.tem_historico is False and empty_result.crms_interesse == []

    historical = pl.DataFrame(
        {"competencia": [202401], "id_medico": ["CRM-A"], "vl_total_prescricoes": [100.0]}
    )
    monkeypatch.setattr(
        crm, "load_or_sync_crm_data",
        lambda _: CacheLoadResult(historical, True, read_time_ms=1.0),
    )
    result = crm.get_crm_data("123", data_inicio="2025-01")
    assert result.tem_historico is True and result.crms_interesse == []
    assert result.from_cache is True


def test_get_crm_data_builds_summary_and_alert_counts(monkeypatch):
    cnpj = "00123456000199"
    raw = pl.DataFrame(
        {
            "competencia": [202401], "id_medico": ["CRM-A"], "vl_total_prescricoes": [100.0],
            "nu_prescricoes_mes": [10], "flag_concentracao_mesmo_crm": [1],
        }
    )
    med_month = pl.DataFrame(
        {
            "id_medico": ["CRM-A"], "competencia": [202401], "vl_total_prescricoes": [100.0],
            "nu_prescricoes": [10], "nu_prescricoes_total_brasil": [20], "_dias_ativos": [5],
            "_dias_ativos_brasil": [10], "no_medico": ["Dra. Exemplo"], "flag_crm_invalido": [1],
            "flag_prescricao_antes_registro": [0], "alerta_concentracao_multiplos_crms": [1],
            "alerta_concentracao_unico_crm": [1], "alerta_distancia_geografica": [0],
            "alerta5_geografico": [0], "dt_inscricao_crm": ["2010-01-01"], "nu_estabelecimentos": [1],
            "nu_prescricoes_dia": [2.0], "prescricoes_dia_total_brasil": [2.0],
        }
    )
    monkeypatch.setattr(crm, "_get_cnpj_cache_dir", lambda _: "unused")
    monkeypatch.setattr(
        crm, "load_or_sync_crm_data", lambda _: CacheLoadResult(raw, True, 1.0, 2.0, 3.0)
    )
    monkeypatch.setattr(crm, "_load_crm_prescription_days", lambda _cnpj, frame: frame)
    monkeypatch.setattr(crm, "_aggregate_crm_medico_mes", lambda _frame: med_month)
    monkeypatch.setattr(
        crm, "_build_crm_medico_atuacao",
        lambda _frame: pl.DataFrame({"id_medico": ["CRM-A"], "competencia_inicio_atuacao": [202401]}),
    )
    monkeypatch.setattr(crm, "get_df_perfil_estabelecimento", lambda: pl.DataFrame(
        {"cnpj": [cnpj], "razao_social": ["Farmácia Exemplo"], "no_municipio": ["São Paulo"], "uf": ["SP"]}
    ))
    monkeypatch.setattr(crm, "_load_crm_unico_alertas", lambda *_: pl.DataFrame(
        {
            "competencia": [202401], "id_medico": ["CRM-A"], "dt_alerta": ["2024-01-05"],
            "hr_janela": [9], "nu_prescricoes_dia": [10],
        }
    ))
    monkeypatch.setattr(crm, "load_or_sync_geografico", lambda _: CacheLoadResult(pl.DataFrame(
        {"competencia": [202401], "id_medico": ["CRM-A"]}
    ), True))
    monkeypatch.setattr(crm, "_load_crm_multi_alertas", lambda *_: pl.DataFrame(
        {
            "competencia": [202401], "dt_alerta": ["2024-01-05"], "taxa_hora": [120.0],
            "nu_prescricoes": [8],
        }
    ))
    monkeypatch.setattr(crm, "sync_crm_raiox_tx", lambda _: CacheLoadResult(None, True))
    monkeypatch.setattr(crm, "load_or_sync_crm_timeline_hora", lambda _: CacheLoadResult(pl.DataFrame(
        {"dt_janela": ["2024-01-05 09:00:00"], "is_volume_horario_anomalo": [1]}
    ), True))
    monkeypatch.setattr(crm, "_build_alertas_crm_multiplos_por_medico", lambda *_: {"CRM-A": [{"hr": 9}]})

    result = crm.get_crm_data(cnpj, data_inicio="2024-01", data_fim="2024-01")

    assert result.tem_historico and result.from_cache
    assert result.summary["pct_concentracao_top1"] == 100.0
    assert result.summary["qtd_prescritores_robos"] == 0
    assert result.summary["qtd_crm_invalido"] == 1
    assert result.summary["qtd_alertas_volume_horario"] == 1
    assert result.summary["qtd_alertas_cnpj_unico"] == 1
    assert result.summary["qtd_alertas_cnpj_multiplo"] == 1
    assert result.summary["qtd_dias_alertas_cnpj_multiplo"] == 1
    assert result.summary["razaoSocial"] == "Farmácia Exemplo"
    assert result.crms_interesse[0]["qtd_alertas_crm_unico"] == 1
    assert result.crms_interesse[0]["qtd_alertas_geograficos"] == 1
    assert result.crms_interesse[0]["qtd_alertas_crm_multiplos"] == 1
    assert result.crms_interesse[0]["alerta_concentracao_multiplos_crms"] == 1

    monkeypatch.setattr(
        crm,
        "get_df_perfil_estabelecimento",
        lambda: (_ for _ in ()).throw(RuntimeError("profile cache unavailable")),
    )
    without_optional_profile = crm.get_crm_data(cnpj, data_inicio="2024-01", data_fim="2024-01")
    assert without_optional_profile.summary["razaoSocial"] is None

    monkeypatch.setattr(crm, "get_df_perfil_estabelecimento", lambda: pl.DataFrame(
        {"cnpj": [cnpj], "razao_social": ["Farmácia Exemplo"], "no_municipio": ["São Paulo"], "uf": ["SP"]}
    ))
    monkeypatch.setattr(crm, "_build_crm_medico_atuacao", lambda _frame: pl.DataFrame(
        {"id_medico": ["CRM-A"], "competencia_inicio_atuacao": [None]},
        schema={"id_medico": pl.String, "competencia_inicio_atuacao": pl.Int32},
    ))
    with pytest.raises(RuntimeError, match="sem competencia com prescricao no periodo"):
        crm.get_crm_data(cnpj, data_inicio="2024-01", data_fim="2024-01")

    monkeypatch.setattr(crm, "_build_crm_medico_atuacao", lambda _frame: pl.DataFrame(
        {"id_medico": ["CRM-A"], "competencia_inicio_atuacao": [202401]}
    ))
    monkeypatch.setattr(
        crm,
        "load_or_sync_crm_timeline_hora",
        lambda _: CacheLoadResult(None, False, error="hourly source offline"),
    )
    with pytest.raises(HTTPException, match="hourly source offline"):
        crm.get_crm_data(cnpj, data_inicio="2024-01", data_fim="2024-01")


def test_get_crm_data_rejects_invalid_multiple_alert_and_downstream_cache_errors(monkeypatch):
    cnpj = "00123456000199"
    raw = pl.DataFrame(
        {
            "competencia": [202401], "id_medico": ["CRM-A"], "vl_total_prescricoes": [100.0],
            "nu_prescricoes_mes": [10], "flag_concentracao_mesmo_crm": [0],
        }
    )
    med_month = pl.DataFrame(
        {
            "id_medico": ["CRM-A"], "competencia": [202401], "vl_total_prescricoes": [100.0],
            "nu_prescricoes": [10], "nu_prescricoes_total_brasil": [20], "_dias_ativos": [5],
            "_dias_ativos_brasil": [10], "no_medico": ["Dra. Exemplo"], "flag_crm_invalido": [0],
            "flag_prescricao_antes_registro": [0], "alerta_concentracao_multiplos_crms": [0],
            "alerta_concentracao_unico_crm": [0], "alerta_distancia_geografica": [0],
            "alerta5_geografico": [0], "dt_inscricao_crm": ["2010-01-01"], "nu_estabelecimentos": [2],
            "nu_prescricoes_dia": [2.0], "prescricoes_dia_total_brasil": [2.0],
        }
    )
    monkeypatch.setattr(crm, "_get_cnpj_cache_dir", lambda _: "unused")
    monkeypatch.setattr(crm, "load_or_sync_crm_data", lambda _: CacheLoadResult(raw, True))
    monkeypatch.setattr(crm, "_load_crm_prescription_days", lambda _cnpj, frame: frame)
    monkeypatch.setattr(crm, "_aggregate_crm_medico_mes", lambda _frame: med_month)
    monkeypatch.setattr(
        crm, "_build_crm_medico_atuacao",
        lambda _frame: pl.DataFrame({"id_medico": ["CRM-A"], "competencia_inicio_atuacao": [202401]}),
    )
    monkeypatch.setattr(crm, "get_df_perfil_estabelecimento", lambda: pl.DataFrame(schema={"cnpj": pl.String}))
    monkeypatch.setattr(crm, "_load_crm_unico_alertas", lambda *_: pl.DataFrame())
    monkeypatch.setattr(crm, "load_or_sync_geografico", lambda _: CacheLoadResult(pl.DataFrame(), True))
    monkeypatch.setattr(crm, "_load_crm_multi_alertas", lambda *_: pl.DataFrame(
        {"competencia": [202401], "dt_alerta": ["2024-01-05"], "taxa_hora": [0.0]}
    ))
    monkeypatch.setattr(crm, "sync_crm_raiox_tx", lambda _: CacheLoadResult(None, True))
    monkeypatch.setattr(crm, "load_or_sync_crm_timeline_hora", lambda _: CacheLoadResult(pl.DataFrame(), True))

    with pytest.raises(HTTPException) as invalid_alert:
        crm.get_crm_data(cnpj)
    assert invalid_alert.value.status_code == 500 and "taxa_hora" in invalid_alert.value.detail

    monkeypatch.setattr(crm, "_load_crm_multi_alertas", lambda *_: pl.DataFrame())
    monkeypatch.setattr(
        crm, "load_or_sync_geografico",
        lambda _: CacheLoadResult(None, False, error="geo source offline"),
    )
    with pytest.raises(HTTPException, match="geo source offline"):
        crm.get_crm_data(cnpj)

    monkeypatch.setattr(crm, "load_or_sync_geografico", lambda _: CacheLoadResult(pl.DataFrame(), True))
    monkeypatch.setattr(
        crm, "sync_crm_raiox_tx", lambda _: CacheLoadResult(None, False, error="raio-x offline")
    )
    with pytest.raises(HTTPException, match="raio-x offline"):
        crm.get_crm_data(cnpj)


def test_get_crm_raio_x_filters_hour_and_enriches_transactions(temp_dir, monkeypatch):
    cnpj = "00123456000199"
    transactions = pl.DataFrame(
        {
            "dt_janela": ["2024-01-10 09:00:00", "2024-01-10 10:00:00"],
            "hr_janela": [9, 10], "data_hora": ["2024-01-10 09:05:00", "2024-01-10 10:05:00"],
            "num_autorizacao": ["A1", "A2"], "id_medico": ["CRM-A", "CRM-B"], "valor_pago": [12.5, 4.0],
        }
    )
    transactions.write_parquet(temp_dir / crm.CRM_RAIOX_TX_PARQUET)
    monkeypatch.setattr(crm, "_get_cnpj_cache_dir", lambda _: str(temp_dir))
    monkeypatch.setattr(crm, "sync_crm_raiox_tx", lambda _: CacheLoadResult(None, True, 2.0))
    monkeypatch.setattr(crm, "_load_crm_unico_alertas", lambda *_: pl.DataFrame(
        {
            "dt_alerta": ["2024-01-10", "2024-01-10"], "id_medico": ["CRM-A", "CRM-B"],
            "hr_janela": [9, 10], "nu_prescricoes_dia": [10, 12], "nu_minutos_dia": [5, 6],
            "nu_minutos_intervalo": [5, 6], "taxa_hora": [120.0, 120.0],
            "severidade": ["ALTO", "ALTO"], "criterio_pior_ritmo": ["5min", "5min"],
            "dt_ini_hora": ["2024-01-10 09:00:00", "2024-01-10 10:00:00"],
            "dt_fim_hora": ["2024-01-10 09:30:00", "2024-01-10 10:30:00"],
        }
    ))
    monkeypatch.setattr(crm, "_load_crm_multi_alertas", lambda *_: pl.DataFrame(
        {
            "dt_dia": ["2024-01-10", "2024-01-10"],
            "dt_ini_concentracao": ["2024-01-10 09:10:00", "2024-01-10 10:10:00"],
            "dt_fim_concentracao": ["2024-01-10 09:30:00", "2024-01-10 10:30:00"],
            "nu_prescricoes": [6, 4], "nu_crms_distintos": [2, 2], "nu_minutos_span": [20, 20],
            "severidade": ["ALTO", "ALTO"], "criterio_pior_ritmo": ["5min", "5min"],
        }
    ))
    import data_cache
    monkeypatch.setattr(
        data_cache, "get_dados_medico_df",
        lambda: pl.DataFrame({"id_medico": ["CRM-A", "CRM-B"], "no_medico": ["Ana", "Bruno"]}),
    )

    result = crm.get_crm_raio_x(cnpj, "2024-01-10", hour=9)

    assert result.from_cache is True
    assert [row.num_autorizacao for row in result.transactions] == ["A1"]
    assert result.transactions[0].no_medico == "Ana"
    assert result.transactions[0].valor_pago == 12.5
    assert [alert.id_medico for alert in result.alertas_unico] == ["CRM-A"]
    assert result.alertas_unico[0].ritmo_hora == 120.0
    assert len(result.alertas_multi) == 1
    assert result.alertas_multi[0].ritmo_hora == 18.0
    assert result.alertas_multi[0].hr_janela == 9


def test_get_crm_raio_x_propagates_cache_and_required_rate_errors(temp_dir, monkeypatch):
    import data_cache

    cnpj = "00123456000199"
    monkeypatch.setattr(
        data_cache,
        "get_dados_medico_df",
        lambda: pl.DataFrame({"id_medico": ["CRM-A"], "no_medico": ["Ana"]}),
    )
    pl.DataFrame(
        {
            "dt_janela": ["2024-01-10 09:00:00"], "hr_janela": [9],
            "data_hora": ["2024-01-10 09:05:00"], "num_autorizacao": ["A1"],
            "id_medico": ["CRM-A"], "valor_pago": [12.5],
        }
    ).write_parquet(temp_dir / crm.CRM_RAIOX_TX_PARQUET)
    monkeypatch.setattr(crm, "_get_cnpj_cache_dir", lambda _: str(temp_dir))
    monkeypatch.setattr(
        crm, "sync_crm_raiox_tx", lambda _: CacheLoadResult(None, False, error="Raio-X indisponível")
    )
    with pytest.raises(HTTPException, match="Raio-X indisponível"):
        crm.get_crm_raio_x(cnpj, "2024-01-10", hour=9)

    monkeypatch.setattr(crm, "sync_crm_raiox_tx", lambda _: CacheLoadResult(None, True))
    monkeypatch.setattr(crm, "_load_crm_unico_alertas", lambda *_: pl.DataFrame(
        {
            "dt_alerta": ["2024-01-10"], "id_medico": ["CRM-A"], "hr_janela": [9],
            "nu_prescricoes_dia": [10], "nu_minutos_dia": [5], "nu_minutos_intervalo": [5],
            "taxa_hora": [0.0], "dt_ini_hora": ["2024-01-10 09:00:00"],
            "dt_fim_hora": ["2024-01-10 09:30:00"],
        }
    ))
    with pytest.raises(HTTPException) as invalid_rate:
        crm.get_crm_raio_x(cnpj, "2024-01-10", hour=9)
    assert invalid_rate.value.status_code == 500 and "taxa_hora" in invalid_rate.value.detail

    monkeypatch.setattr(
        crm,
        "_load_crm_unico_alertas",
        lambda *_: (_ for _ in ()).throw(ValueError("malformed alert cache")),
    )
    with pytest.raises(HTTPException) as unexpected_error:
        crm.get_crm_raio_x(cnpj, "2024-01-10", hour=9)
    assert unexpected_error.value.status_code == 500
    assert "malformed alert cache" in unexpected_error.value.detail


def test_crm_medico_atuacao_builds_monthly_series_and_requires_p95(monkeypatch):
    monthly = pl.DataFrame(
        {
            "id_medico": ["CRM-A", "CRM-A"], "competencia": [202401, 202402],
            "nu_prescricoes": [20, 10], "_dias_ativos": [10, 10],
            "vl_total_prescricoes": [200.0, 100.0], "nu_prescricoes_total_brasil": [40, 30],
            "alerta_concentracao_unico_crm": [1, 0], "alerta_concentracao_multiplos_crms": [0, 1],
            "alerta5_geografico": [0, 1],
        }
    )
    p95 = pl.DataFrame({"competencia": [202401, 202402], "p95_taxa_dia": [1.5, 2.0]})
    monkeypatch.setattr(crm, "scan_crm_limiar_p95_mes", lambda: p95.lazy())

    result = crm._build_crm_medico_atuacao(monthly).row(0, named=True)

    assert result["competencia_inicio_atuacao"] == 202401
    assert result["competencia_fim_atuacao"] == 202402
    assert result["qtd_meses_atuacao"] == 2
    assert result["serie_mensal_atuacao"][0]["taxa_elevada"] is True
    assert result["serie_mensal_atuacao"][0]["alerta_sequencia_unico"] is True
    assert result["serie_mensal_atuacao"][1]["alerta_sequencia_multiplos"] is True
    assert result["serie_mensal_atuacao"][1]["alerta_distancia"] is True

    monkeypatch.setattr(
        crm, "scan_crm_limiar_p95_mes",
        lambda: pl.DataFrame({"competencia": [202401], "p95_taxa_dia": [1.5]}).lazy(),
    )
    with pytest.raises(RuntimeError, match="Limiar P95 nacional ausente"):
        crm._build_crm_medico_atuacao(monthly)


def test_get_crm_medico_atuacao_returns_response_and_translates_errors(monkeypatch):
    cnpj = "00123456000199"
    global_rows = pl.DataFrame(
        {
            "id_cnpj": [7, 7], "id_medico": ["CRM-A", "CRM-A"], "competencia": [202401, 202402],
            "_crm_prescritores_cache_version": [crm.CRM_PRESCRITORES_CACHE_VERSION] * 2,
            "nu_prescricoes_mes": [20, 10], "vl_total_prescricoes": [200.0, 100.0],
        }
    )
    totals = global_rows.select(["competencia", "nu_prescricoes_mes", "vl_total_prescricoes"])
    medico_mes = pl.DataFrame(
        {
            "id_medico": ["CRM-A"], "no_medico": ["Dra. Exemplo"], "dt_inscricao_crm": ["2010-01-01"],
            "vl_total_prescricoes": [300.0],
        }
    )
    atuacao = pl.DataFrame(
        {
            "id_medico": ["CRM-A"], "competencia_inicio_atuacao": [202401],
            "competencia_fim_atuacao": [202402], "qtd_meses_atuacao": [2],
            "serie_mensal_atuacao": [[{"competencia": 202401}, {"competencia": 202402}]],
        }
    )
    monkeypatch.setattr(crm, "_resolve_crm_id_cnpj", lambda _: 7)
    monkeypatch.setattr(crm, "scan_crm_prescritores_global", lambda: global_rows.lazy())
    monkeypatch.setattr(crm, "scan_dados_medico", lambda: pl.DataFrame(
        {"id_medico": ["CRM-A"], "no_medico": ["Dra. Exemplo"]}
    ).lazy())
    monkeypatch.setattr(crm, "_load_crm_prescription_days", lambda _cnpj, frame: frame)
    monkeypatch.setattr(crm, "_aggregate_crm_medico_mes", lambda _frame: medico_mes)
    monkeypatch.setattr(crm, "_build_crm_medico_atuacao", lambda _frame: atuacao)

    result = crm.get_crm_medico_atuacao(cnpj, "CRM-A", "2024-01", "2024-02")

    assert result.cnpj == cnpj
    assert result.medico["no_medico"] == "Dra. Exemplo"
    assert result.competencia_inicio_periodo == 202401
    assert result.competencia_fim_periodo == 202402
    assert result.serie_mensal_farmacia == [
        {"competencia": 202401, "qtd": 20, "valor": 200.0},
        {"competencia": 202402, "qtd": 10, "valor": 100.0},
    ]

    with pytest.raises(HTTPException) as missing_id:
        crm.get_crm_medico_atuacao(cnpj, "")
    assert missing_id.value.status_code == 400

    monkeypatch.setattr(crm, "scan_crm_prescritores_global", lambda: global_rows.filter(pl.col("id_medico") == "OTHER").lazy())
    with pytest.raises(HTTPException) as not_found:
        crm.get_crm_medico_atuacao(cnpj, "CRM-A")
    assert not_found.value.status_code == 404

    monkeypatch.setattr(crm, "scan_crm_prescritores_global", lambda: global_rows.lazy())
    stale = global_rows.with_columns(pl.lit(0).alias("_crm_prescritores_cache_version"))
    monkeypatch.setattr(crm, "scan_crm_prescritores_global", lambda: stale.lazy())
    with pytest.raises(HTTPException) as stale_cache:
        crm.get_crm_medico_atuacao(cnpj, "CRM-A")
    assert stale_cache.value.status_code == 503 and "versão defasada" in stale_cache.value.detail


def test_crm_medico_atuacao_rejects_missing_farmacia_series_values():
    valid = pl.DataFrame(
        {"competencia": [202401], "nu_prescricoes_mes": [1], "vl_total_prescricoes": [10.0]}
    )
    assert crm._build_crm_farmacia_series(valid) == [
        {"competencia": 202401, "qtd": 1, "valor": 10.0}
    ]
    invalid = valid.with_columns(pl.lit(float("inf")).alias("vl_total_prescricoes"))
    with pytest.raises(RuntimeError, match="ausente/inválido"):
        crm._build_crm_farmacia_series(invalid)
