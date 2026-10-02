from datetime import date
from types import SimpleNamespace

import polars as pl
import pytest
from fastapi import HTTPException

from backend.api.services.analytics import crm_medico_historico as historico


def _install_history_sources(monkeypatch):
    pharmacy_rows = []
    brazil_rows = []
    municipality_rows = []
    for competence, pharmacy_a, pharmacy_b, days_a, days_b in (
        (202401, 6, 4, 3, 2),
        (202402, 12, 8, 4, 3),
        (202403, 6, 4, 3, 2),
    ):
        pharmacy_rows.extend(
            [
                {"id_medico": "M1", "id_cnpj": 1, "competencia": competence,
                 "nu_prescricoes_mes": pharmacy_a, "qtd_dias_com_prescricao_mes": days_a},
                {"id_medico": "M1", "id_cnpj": 2, "competencia": competence,
                 "nu_prescricoes_mes": pharmacy_b, "qtd_dias_com_prescricao_mes": days_b},
            ]
        )
        brazil_rows.append(
            {
                "id_medico": "M1", "competencia": competence,
                "nu_prescricoes_mes": pharmacy_a + pharmacy_b,
                "qtd_dias_com_prescricao_mes": 4,
            }
        )
        municipality_rows.append(
            {
                "nivel": "municipio", "id_geografico": "3550308", "id_medico": "M1",
                "competencia": competence, "nu_prescricoes_mes": pharmacy_a,
                "qtd_dias_com_prescricao_mes": days_a,
            }
        )

    monkeypatch.setattr(
        historico, "scan_crm_medico_estabelecimento_mes",
        lambda: pl.DataFrame(pharmacy_rows).lazy(),
    )
    monkeypatch.setattr(
        historico, "scan_crm_medico_brasil_mes",
        lambda: pl.DataFrame(brazil_rows).lazy(),
    )
    monkeypatch.setattr(
        historico, "scan_crm_medico_territorio_mes",
        lambda: pl.DataFrame(municipality_rows).lazy(),
    )
    monkeypatch.setattr(
        historico, "scan_crm_limiar_p95_mes",
        lambda: pl.DataFrame(
            {"competencia": [202401, 202402, 202403], "p95_taxa_dia": [2.0, 2.0, 2.0]}
        ).lazy(),
    )
    monkeypatch.setattr(
        historico,
        "scan_crm_concentracao_unico_alertas_global",
        lambda: pl.DataFrame(
            {
                "id_medico": ["M1"], "id_cnpj": [1], "competencia": [202401],
                "dt_alerta": ["2024-01-15"], "id_severidade": [4],
            }
        ).lazy(),
    )
    monkeypatch.setattr(
        historico,
        "scan_geografico_global",
        lambda: pl.DataFrame(
            {
                "id_medico": ["M1"], "competencia": [202401],
                "no_municipio_a": ["Sao Paulo"], "sg_uf_a": ["SP"],
                "no_municipio_b": ["Rio"], "sg_uf_b": ["RJ"], "distancia_km": [1500.2],
            }
        ).lazy(),
    )
    monkeypatch.setattr(
        historico,
        "get_df_perfil_estabelecimento",
        lambda: pl.DataFrame(
            {
                "id_cnpj": [1, 2], "cnpj": ["11111111000111", "22222222000122"],
                "razao_social": ["Farmacia A", "Farmacia B"],
                "id_ibge7": [3550308, 3304557],
                "no_municipio": ["Sao Paulo", "Rio de Janeiro"],
                "uf": ["SP", "RJ"], "situacao_rf": ["ATIVA", "ATIVA"],
                "is_conexao_ativa": [True, False],
            }
        ),
    )
    monkeypatch.setattr(
        historico,
        "get_dados_medico_df",
        lambda: pl.DataFrame(
            {
                "id_medico": ["M1"], "nu_crm": ["12345"], "sg_uf": ["SP"],
                "no_medico": ["Doutor Um"],
                "dt_primeira_inscricao_uf": [date(2024, 2, 15)],
            }
        ),
    )
    empty = pl.DataFrame([])
    monkeypatch.setattr(
        historico,
        "evidencias_do_medico",
        lambda *_args: SimpleNamespace(unico=empty, multiplos=empty, distancia=empty),
    )


def test_month_helpers_format_and_find_longest_calendar_sequence():
    assert historico._fmt_comp(202401) == "01/2024"
    assert historico._indice_mes(202401) + 1 == historico._indice_mes(202402)
    assert historico._maior_sequencia([]) == []
    assert historico._maior_sequencia([202312, 202401, 202403, 202404, 202405]) == [202403, 202404, 202405]
    assert historico._maior_sequencia([202401, 202403, 202402]) == [202401]


def test_cadastro_farmacias_returns_one_complete_record_per_requested_id(monkeypatch):
    perfil = pl.DataFrame(
        {
            "id_cnpj": [1, 2], "cnpj": ["111", "222"], "razao_social": ["A", "B"],
            "id_ibge7": [3550308, 3304557], "no_municipio": ["São Paulo", "Rio"],
            "uf": ["SP", "RJ"], "situacao_rf": ["ATIVA", "ATIVA"], "is_conexao_ativa": [True, False],
        }
    )
    monkeypatch.setattr(historico, "get_df_perfil_estabelecimento", lambda: perfil)
    result = historico._cadastro_farmacias(pl.Series("ids", [1, 1], dtype=pl.Int32))
    assert result.get_column("id_cnpj").to_list() == [1]
    assert result.get_column("municipio").to_list() == ["São Paulo"]
    assert result.get_column("conexao_ativa").to_list() == [True]

    with pytest.raises(HTTPException) as missing:
        historico._cadastro_farmacias(pl.Series("ids", [3], dtype=pl.Int32))
    assert missing.value.status_code == 503 and "sem cadastro" in missing.value.detail
    duplicate = pl.concat([perfil, perfil.head(1)])
    monkeypatch.setattr(historico, "get_df_perfil_estabelecimento", lambda: duplicate)
    with pytest.raises(HTTPException) as duplicated:
        historico._cadastro_farmacias(pl.Series("ids", [1], dtype=pl.Int32))
    assert duplicated.value.status_code == 503 and "mais de uma linha" in duplicated.value.detail

    incomplete = perfil.with_columns(pl.when(pl.col("id_cnpj") == 1).then(pl.lit("")).otherwise(pl.col("uf")).alias("uf"))
    monkeypatch.setattr(historico, "get_df_perfil_estabelecimento", lambda: incomplete)
    with pytest.raises(HTTPException) as no_locality:
        historico._cadastro_farmacias(pl.Series("ids", [1], dtype=pl.Int32))
    assert no_locality.value.status_code == 503 and "sem UF ou municipio" in no_locality.value.detail


def test_points_of_attention_builds_temporal_concentration_burst_and_distance_alerts():
    months = pl.DataFrame(
        {"competencia": [202301, 202302, 202303, 202304], "alta": [True, True, True, False]}
    )
    bursts = pl.DataFrame(
        {
            "id_cnpj": [1, 1, 2], "competencia": [202301, 202302, 202302],
            "dt_alerta": ["2023-01-01", "2023-02-01", "2023-02-01"], "id_severidade": [1, 2, 3],
        }
    )
    distant = pl.DataFrame(
        {
            "competencia": [202301, 202302], "distancia_km": [999.8, 1500.2],
            "no_municipio_a": ["A", "A"], "sg_uf_a": ["SP", "SP"],
            "no_municipio_b": ["B", "B"], "sg_uf_b": ["RJ", "RJ"],
        }
    )
    points = historico.pontos_de_atencao(
        dt_inscricao=date(2023, 3, 15),
        meses_periodo=months,
        principal=(52.6, "Farmácia A"),
        rajadas=bursts,
        pares_distantes=distant,
        avaliar_farmacias=True,
    )
    by_code = {point.codigo: point for point in points}
    assert set(by_code) == {"antes_inscricao", "rajadas_unico", "distancia", "sequencia_alta", "concentracao"}
    assert by_code["antes_inscricao"].competencias == [202301, 202302]
    assert "2 dias" in by_code["rajadas_unico"].detalhe and "crítica" in by_code["rajadas_unico"].detalhe
    assert "1.500 km" in by_code["distancia"].detalhe
    assert by_code["sequencia_alta"].competencias == [202301, 202302, 202303]
    assert "52,6%" in by_code["concentracao"].detalhe


def test_points_of_attention_skip_filtered_alerts_and_reject_unknown_severity():
    months = pl.DataFrame({"competencia": [202401, 202402], "alta": [True, False]})
    empty_bursts = pl.DataFrame(
        schema={"id_cnpj": pl.Int32, "competencia": pl.Int32, "dt_alerta": pl.String, "id_severidade": pl.Int32}
    )
    pairs = pl.DataFrame(
        schema={"competencia": pl.Int32, "distancia_km": pl.Float64, "no_municipio_a": pl.String,
                "sg_uf_a": pl.String, "no_municipio_b": pl.String, "sg_uf_b": pl.String}
    )
    points = historico.pontos_de_atencao(
        dt_inscricao="nao localizada", meses_periodo=months, principal=(80.0, "Farmácia"),
        rajadas=empty_bursts, pares_distantes=pairs, avaliar_farmacias=False,
    )
    assert points == []  # one high month is not a consecutive sequence and filtered farms are not evaluated

    invalid = pl.DataFrame(
        {"id_cnpj": [1], "competencia": [202401], "dt_alerta": ["2024-01-01"], "id_severidade": [9]}
    )
    with pytest.raises(HTTPException) as error:
        historico.pontos_de_atencao(
            dt_inscricao=None, meses_periodo=months, principal=None,
            rajadas=invalid, pares_distantes=pairs, avaliar_farmacias=False,
        )
    assert error.value.status_code == 503 and "Severidade de rajada desconhecida" in error.value.detail


def _run_history(**kwargs):
    return historico.get_crm_medico_historico(
        " M1 ", date(2024, 1, 1), date(2024, 3, 31), **kwargs
    )


def test_history_returns_complete_national_timeline_kpis_and_alerts(monkeypatch):
    _install_history_sources(monkeypatch)
    evidence = SimpleNamespace(
        unico=pl.DataFrame({"id": [1]}),
        multiplos=pl.DataFrame([]),
        distancia=pl.DataFrame([]),
    )
    monkeypatch.setattr(historico, "evidencias_do_medico", lambda *_args: evidence)

    result = _run_history()

    assert result.id_medico == "M1"
    assert result.localizado_cfm is True
    assert result.sg_uf == "SP"
    assert result.kpis.nu_prescricoes == 40
    assert result.kpis.qtd_dias_com_prescricao == 12
    assert result.kpis.qtd_meses_ativos == 3
    assert result.kpis.qtd_meses_alta_intensidade == 3
    assert result.kpis.qtd_farmacias == 2
    assert result.kpis.qtd_municipios == 2
    assert result.kpis.qtd_ufs == 2
    assert result.kpis.percentual_farmacia_principal == 60.0
    assert result.kpis.percentual_top3_farmacias == 100.0
    assert result.kpis.pior_mes_competencia == 202402
    assert len(result.meses) == len(result.p95_meses) == 3
    assert len(result.farmacia_mes) == 6
    assert result.farmacias[0].id_cnpj == 1
    assert result.farmacias[0].fora_uf_crm is False
    assert result.farmacias[1].fora_uf_crm is True
    assert result.tem_evidencias is True
    assert {item.codigo for item in result.pontos_atencao} == {
        "antes_inscricao", "rajadas_unico", "distancia", "sequencia_alta", "concentracao"
    }


def test_history_filter_by_pharmacy_keeps_full_pharmacy_table_and_limits_alerts(monkeypatch):
    _install_history_sources(monkeypatch)
    result = _run_history(id_cnpj=1)

    assert result.id_cnpj_filtro == 1
    assert result.kpis.nu_prescricoes == 24
    assert result.kpis.qtd_dias_com_prescricao == 10
    assert result.kpis.qtd_farmacias == 1
    assert result.kpis.percentual_farmacia_principal == 60.0
    assert result.kpis.percentual_top3_farmacias is None
    assert len(result.farmacias) == 2
    assert len(result.farmacia_mes) == 6
    assert "distancia" not in {item.codigo for item in result.pontos_atencao}
    assert "concentracao" not in {item.codigo for item in result.pontos_atencao}
    assert result.tem_evidencias is False


def test_history_filter_by_municipality_uses_distinct_city_days_and_scoped_alerts(monkeypatch):
    _install_history_sources(monkeypatch)
    result = _run_history(id_ibge7=3550308)

    assert result.id_ibge7_filtro == 3550308
    assert result.kpis.nu_prescricoes == 24
    assert result.kpis.qtd_dias_com_prescricao == 10
    assert result.kpis.qtd_farmacias == 1
    assert result.kpis.qtd_ufs == 1
    assert result.kpis.percentual_farmacia_principal == 60.0
    assert result.kpis.percentual_top3_farmacias is None
    assert all(month.qtd_farmacias == 1 for month in result.meses)
    assert "concentracao" not in {item.codigo for item in result.pontos_atencao}


def test_history_with_pharmacy_and_municipality_checks_that_they_match(monkeypatch):
    _install_history_sources(monkeypatch)
    checked = []
    monkeypatch.setattr(
        historico, "conferir_farmacia_no_municipio",
        lambda pharmacy, city: checked.append((pharmacy, city)),
    )

    result = _run_history(id_cnpj=1, id_ibge7=3550308)

    assert checked == [(1, 3550308)]
    assert result.kpis.nu_prescricoes == 24


@pytest.mark.parametrize(
    ("id_medico", "inicio", "fim", "status", "detail"),
    [
        ("   ", date(2024, 1, 1), date(2024, 3, 31), 422, "id_medico obrigatorio"),
        ("M1", date(2024, 1, 2), date(2024, 3, 31), 422, "meses completos"),
        ("M1", date(2024, 4, 1), date(2024, 3, 31), 422, "Período inválido"),
    ],
)
def test_history_validates_medical_id_and_full_month_period(id_medico, inicio, fim, status, detail):
    with pytest.raises(HTTPException) as error:
        historico.get_crm_medico_historico(id_medico, inicio, fim)
    assert error.value.status_code == status
    assert detail in error.value.detail


def test_history_translates_cache_failures_but_preserves_http_errors(monkeypatch):
    monkeypatch.setattr(historico, "scan_crm_medico_estabelecimento_mes", lambda: (_ for _ in ()).throw(RuntimeError("disk")))
    with pytest.raises(HTTPException) as unavailable:
        _run_history()
    assert unavailable.value.status_code == 503
    assert "Cache de prescricoes por medico indisponivel: disk" in unavailable.value.detail

    expected = HTTPException(status_code=409, detail="cache blocked")
    monkeypatch.setattr(historico, "scan_crm_medico_estabelecimento_mes", lambda: (_ for _ in ()).throw(expected))
    with pytest.raises(HTTPException) as preserved:
        _run_history()
    assert preserved.value is expected


def test_history_reports_missing_pharmacy_rows_and_unrequested_pharmacy(monkeypatch):
    _install_history_sources(monkeypatch)
    monkeypatch.setattr(
        historico,
        "scan_crm_medico_estabelecimento_mes",
        lambda: pl.DataFrame(
            schema={
                "id_medico": pl.String, "id_cnpj": pl.Int32, "competencia": pl.Int32,
                "nu_prescricoes_mes": pl.Int64, "qtd_dias_com_prescricao_mes": pl.Int64,
            }
        ).lazy(),
    )
    with pytest.raises(HTTPException) as empty:
        _run_history()
    assert empty.value.status_code == 404
    assert "sem prescricoes registradas" in empty.value.detail

    _install_history_sources(monkeypatch)
    with pytest.raises(HTTPException) as missing:
        _run_history(id_cnpj=3)
    assert missing.value.status_code == 404
    assert "sem prescricoes na farmacia 3" in missing.value.detail


def test_history_rejects_monthly_mismatch_between_pharmacies_and_brazil(monkeypatch):
    _install_history_sources(monkeypatch)
    brazil = pl.DataFrame(
        {
            "id_medico": ["M1", "M1", "M1"],
            "competencia": [202401, 202402, 202403],
            "nu_prescricoes_mes": [11, 20, 10],
            "qtd_dias_com_prescricao_mes": [4, 4, 4],
        }
    )
    monkeypatch.setattr(historico, "scan_crm_medico_brasil_mes", lambda: brazil.lazy())
    with pytest.raises(HTTPException) as mismatch:
        _run_history()
    assert mismatch.value.status_code == 503
    assert "nao batem com o total mensal do Brasil" in mismatch.value.detail


def test_history_rejects_pharmacy_without_complete_profile(monkeypatch):
    _install_history_sources(monkeypatch)
    monkeypatch.setattr(
        historico,
        "get_df_perfil_estabelecimento",
        lambda: pl.DataFrame(
            {
                "id_cnpj": [1], "cnpj": ["111"], "razao_social": ["A"],
                "id_ibge7": [3550308], "no_municipio": ["São Paulo"],
                "uf": ["SP"], "situacao_rf": ["ATIVA"], "is_conexao_ativa": [True],
            }
        ),
    )
    with pytest.raises(HTTPException) as missing:
        _run_history()
    assert missing.value.status_code == 503
    assert "sem cadastro no perfil" in missing.value.detail


def test_history_uses_crm_suffix_when_cfm_record_is_missing(monkeypatch):
    _install_history_sources(monkeypatch)
    for name in (
        "scan_crm_medico_estabelecimento_mes", "scan_crm_medico_brasil_mes",
        "scan_crm_medico_territorio_mes", "scan_crm_concentracao_unico_alertas_global",
        "scan_geografico_global",
    ):
        scan = getattr(historico, name)
        frame = scan().collect().with_columns(pl.lit("M1/RJ").alias("id_medico"))
        monkeypatch.setattr(historico, name, lambda frame=frame: frame.lazy())
    monkeypatch.setattr(historico, "get_dados_medico_df", lambda: pl.DataFrame(schema={"id_medico": pl.String}))

    result = historico.get_crm_medico_historico("M1/RJ", date(2024, 1, 1), date(2024, 3, 31))

    assert result.localizado_cfm is False
    assert result.sg_uf == "RJ"
    assert result.no_medico is None
    assert result.dt_primeira_inscricao is None
    assert "antes_inscricao" not in {item.codigo for item in result.pontos_atencao}


def test_history_rejects_missing_p95_threshold(monkeypatch):
    _install_history_sources(monkeypatch)
    monkeypatch.setattr(
        historico,
        "scan_crm_limiar_p95_mes",
        lambda: pl.DataFrame({"competencia": [202401], "p95_taxa_dia": [2.0]}).lazy(),
    )
    with pytest.raises(HTTPException) as unavailable:
        _run_history()
    assert unavailable.value.status_code == 503
    assert "Limiar P95 ausente" in unavailable.value.detail


def test_history_rejects_missing_municipality_data_and_mismatched_city_totals(monkeypatch):
    _install_history_sources(monkeypatch)
    with pytest.raises(HTTPException) as no_city:
        _run_history(id_ibge7=4106902)
    assert no_city.value.status_code == 404
    assert "sem prescricoes no municipio" in no_city.value.detail

    _install_history_sources(monkeypatch)
    incorrect_city = pl.DataFrame(
        {
            "nivel": ["municipio"], "id_geografico": ["3550308"], "id_medico": ["M1"],
            "competencia": [202401], "nu_prescricoes_mes": [99],
            "qtd_dias_com_prescricao_mes": [0],
        }
    )
    monkeypatch.setattr(historico, "scan_crm_medico_territorio_mes", lambda: incorrect_city.lazy())
    with pytest.raises(HTTPException) as mismatch:
        _run_history(id_ibge7=3550308)
    assert mismatch.value.status_code == 503
    assert "no municipio nao batem" in mismatch.value.detail


def test_history_translates_municipality_cache_scan_error(monkeypatch):
    _install_history_sources(monkeypatch)
    monkeypatch.setattr(
        historico, "scan_crm_medico_territorio_mes",
        lambda: (_ for _ in ()).throw(RuntimeError("territory parquet")),
    )
    with pytest.raises(HTTPException) as unavailable:
        _run_history(id_ibge7=3550308)
    assert unavailable.value.status_code == 503
    assert "Cache de prescricoes por medico e municipio indisponivel" in unavailable.value.detail


def test_ranking_alerts_builds_alerts_and_validates_ids_and_source_consistency(monkeypatch):
    _install_history_sources(monkeypatch)
    result = historico.get_crm_medicos_alertas(" M1 ", date(2024, 1, 1), date(2024, 3, 31))
    assert len(result.medicos) == 1
    assert result.medicos[0].id_medico == "M1"
    assert {item.codigo for item in result.medicos[0].pontos_atencao} == {
        "antes_inscricao", "rajadas_unico", "distancia", "sequencia_alta", "concentracao"
    }

    for ids, detail in [(" , ", "Informe ao menos"), ("M1,M1", "repetido")]:
        with pytest.raises(HTTPException) as invalid:
            historico.get_crm_medicos_alertas(ids, date(2024, 1, 1), date(2024, 3, 31))
        assert invalid.value.status_code == 422
        assert detail in invalid.value.detail
    too_many = ",".join(f"M{i}" for i in range(historico.ALERTAS_MAX_MEDICOS + 1))
    with pytest.raises(HTTPException) as excessive:
        historico.get_crm_medicos_alertas(too_many, date(2024, 1, 1), date(2024, 3, 31))
    assert excessive.value.status_code == 422
    assert "No maximo" in excessive.value.detail


def test_ranking_alerts_rejects_missing_ids_mismatched_totals_and_missing_p95(monkeypatch):
    _install_history_sources(monkeypatch)
    monkeypatch.setattr(
        historico, "scan_crm_medico_estabelecimento_mes",
        lambda: pl.DataFrame(schema={
            "id_medico": pl.String, "id_cnpj": pl.Int32, "competencia": pl.Int32,
            "nu_prescricoes_mes": pl.Int64,
        }).lazy(),
    )
    with pytest.raises(HTTPException) as absent:
        historico.get_crm_medicos_alertas("M1", date(2024, 1, 1), date(2024, 3, 31))
    assert absent.value.status_code == 503
    assert "sem prescricoes por farmacia" in absent.value.detail

    _install_history_sources(monkeypatch)
    monkeypatch.setattr(
        historico, "scan_crm_medico_brasil_mes",
        lambda: pl.DataFrame(
            {"id_medico": ["M1"], "competencia": [202401], "nu_prescricoes_mes": [999],
             "qtd_dias_com_prescricao_mes": [4]}
        ).lazy(),
    )
    with pytest.raises(HTTPException) as mismatch:
        historico.get_crm_medicos_alertas("M1", date(2024, 1, 1), date(2024, 3, 31))
    assert mismatch.value.status_code == 503
    assert "nao batem com o total mensal do Brasil" in mismatch.value.detail

    _install_history_sources(monkeypatch)
    monkeypatch.setattr(
        historico, "scan_crm_limiar_p95_mes",
        lambda: pl.DataFrame({"competencia": [202401], "p95_taxa_dia": [2.0]}).lazy(),
    )
    with pytest.raises(HTTPException) as no_p95:
        historico.get_crm_medicos_alertas("M1", date(2024, 1, 1), date(2024, 3, 31))
    assert no_p95.value.status_code == 503
    assert "Limiar P95 ausente" in no_p95.value.detail


def test_ranking_alerts_translates_cache_errors_and_handles_doctor_without_cfm(monkeypatch):
    _install_history_sources(monkeypatch)
    monkeypatch.setattr(
        historico, "scan_geografico_global",
        lambda: (_ for _ in ()).throw(RuntimeError("geo parquet")),
    )
    with pytest.raises(HTTPException) as unavailable:
        historico.get_crm_medicos_alertas("M1", date(2024, 1, 1), date(2024, 3, 31))
    assert unavailable.value.status_code == 503
    assert "Cache de prescricoes por medico indisponivel: geo parquet" in unavailable.value.detail

    _install_history_sources(monkeypatch)
    monkeypatch.setattr(historico, "get_dados_medico_df", lambda: pl.DataFrame(schema={"id_medico": pl.String}))
    result = historico.get_crm_medicos_alertas("M1", date(2024, 1, 1), date(2024, 3, 31))
    assert "antes_inscricao" not in {item.codigo for item in result.medicos[0].pontos_atencao}


def test_ranking_alerts_preserves_http_errors_from_cache_sources(monkeypatch):
    _install_history_sources(monkeypatch)
    expected = HTTPException(status_code=409, detail="cache blocked")
    monkeypatch.setattr(
        historico,
        "scan_crm_medico_estabelecimento_mes",
        lambda: (_ for _ in ()).throw(expected),
    )
    with pytest.raises(HTTPException) as preserved:
        historico.get_crm_medicos_alertas("M1", date(2024, 1, 1), date(2024, 3, 31))
    assert preserved.value is expected


def test_ranking_alerts_uses_empty_alert_frames_for_doctors_without_optional_events(monkeypatch):
    _install_history_sources(monkeypatch)
    monkeypatch.setattr(
        historico,
        "scan_crm_concentracao_unico_alertas_global",
        lambda: pl.DataFrame(
            schema={"id_medico": pl.String, "id_cnpj": pl.Int32, "competencia": pl.Int32,
                    "dt_alerta": pl.String, "id_severidade": pl.Int32}
        ).lazy(),
    )
    monkeypatch.setattr(
        historico,
        "scan_geografico_global",
        lambda: pl.DataFrame(
            schema={"id_medico": pl.String, "competencia": pl.Int32, "no_municipio_a": pl.String,
                    "sg_uf_a": pl.String, "no_municipio_b": pl.String, "sg_uf_b": pl.String,
                    "distancia_km": pl.Float64}
        ).lazy(),
    )
    result = historico.get_crm_medicos_alertas("M1", date(2024, 1, 1), date(2024, 3, 31))
    assert {item.codigo for item in result.medicos[0].pontos_atencao} == {"antes_inscricao", "sequencia_alta", "concentracao"}
