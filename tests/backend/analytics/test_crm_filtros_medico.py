from datetime import date
from types import SimpleNamespace

import polars as pl
import pytest
from fastapi import HTTPException

from backend.api.services.analytics import crm_filtros_medico as medico


class _ImmediateCache:
    def obter(self, _key, calculate):
        return calculate()


def test_filter_object_properties_keys_expressions_and_recorte_cache_key():
    empty = medico.FiltrosMedico()
    assert empty.ativo is False
    assert empty.usa_recorte is False and empty.usa_atuacao is False
    assert empty.usa_municipios is False and empty.usa_sequencia is False
    assert empty.expressao_faixas(taxa=pl.col("taxa"), prescricoes=pl.col("qtd")) is None
    assert empty.expressao_atuacao() is None
    assert medico.chave_medicos(empty, ("SP", None, None)) == (empty.chave, None)

    filters = medico.FiltrosMedico(
        situacao_cfm="localizado", ufs_crm=("SP",), taxa_dia_min=2.0, prescricoes_max=30,
        exclusividade_min=50, farmacias_min=2, municipios_max=3, sequencia_dias_min=1,
    )
    assert filters.ativo and filters.usa_recorte and filters.usa_atuacao
    assert filters.usa_municipios and filters.usa_sequencia
    assert filters.sem_faixas().taxa_dia_min is None
    assert filters.sem_faixas().situacao_cfm == "localizado"
    assert medico.chave_medicos(filters, ("SP", None, None))[1] == ("SP", None, None)

    expression = filters.expressao_faixas(taxa=pl.col("taxa"), prescricoes=pl.col("qtd"))
    rows = pl.DataFrame({"taxa": [2.004, 1.996, 2.0], "qtd": [30, 30, 31]}).filter(expression)
    # A taxa e arredondada a 2 casas antes da comparacao; 1.996 e 2.004
    # aparecem ambos como 2.00 e devem atender ao minimo inclusivo.
    assert rows.to_dicts() == [{"taxa": 2.004, "qtd": 30}, {"taxa": 1.996, "qtd": 30}]
    activity = pl.DataFrame(
        {"exclusividade": [50.001, 49.999, 75.0], "qtd_farmacias": [2, 2, 4]}
    ).filter(filters.expressao_atuacao())
    # A exclusividade tambem e avaliada em percentual arredondado; 49.999
    # torna-se 50.00, e a quantidade minima de farmacias e inclusiva.
    assert activity.to_dicts() == [
        {"exclusividade": 50.001, "qtd_farmacias": 2},
        {"exclusividade": 49.999, "qtd_farmacias": 2},
        {"exclusividade": 75.0, "qtd_farmacias": 4},
    ]

    upper_bounds = medico.FiltrosMedico(
        taxa_dia_max=2.0, prescricoes_min=10, exclusividade_max=60, farmacias_max=2
    )
    ranged_rows = pl.DataFrame(
        {"taxa": [2.0, 2.01, 1.5], "qtd": [10, 10, 9]}
    ).filter(
        upper_bounds.expressao_faixas(
            taxa=pl.col("taxa"), prescricoes=pl.col("qtd")
        )
    )
    assert ranged_rows.to_dicts() == [{"taxa": 2.0, "qtd": 10}]
    upper_activity = pl.DataFrame(
        {"exclusividade": [60.0, 60.01], "qtd_farmacias": [2, 1]}
    ).filter(upper_bounds.expressao_atuacao())
    assert upper_activity.to_dicts() == [{"exclusividade": 60.0, "qtd_farmacias": 2}]


def test_filter_constructor_normalizes_and_rejects_invalid_ranges():
    normalized = medico.montar_filtros_medico(
        situacao_cfm="localizado", uf_crm=[" sp ", "SP", "rj"], taxa_dia_min=0, taxa_dia_max=2,
        prescricoes_min=1, prescricoes_max=9, exclusividade_min=0, exclusividade_max=100,
        farmacias_min=1, farmacias_max=4, municipios_min=0, municipios_max=5,
        sequencia_severidade_min=4, sequencia_dias_min=0, sequencia_dias_max=8,
    )
    assert normalized.ufs_crm == ("RJ", "SP")
    assert normalized.situacao_cfm == "localizado"
    assert normalized.sequencia_severidade_min == 4
    # Sem tipo informado vale o padrao (unico CRM); com filtro de sequencia o tipo e mantido.
    assert normalized.sequencia_tipo == "unico"
    multiple = medico.montar_filtros_medico(
        situacao_cfm=None, uf_crm=None, sequencia_severidade_min=2, sequencia_tipo="multiplo",
    )
    assert multiple.sequencia_tipo == "multiplo" and multiple.chave != normalized.chave
    # Tipo sem severidade nem faixa de dias nao filtra nada: volta ao padrao e o filtro fica inativo.
    type_only = medico.montar_filtros_medico(situacao_cfm=None, uf_crm=None, sequencia_tipo="qualquer")
    assert type_only.sequencia_tipo == "unico" and type_only.ativo is False

    invalid = (
        ({"situacao_cfm": "qualquer"}, "situacao_cfm"),
        ({"uf_crm": ["XX"]}, "UF do CRM invalida"),
        ({"taxa_dia_min": -1}, "Faixa de taxa_dia nao pode ser negativa"),
        ({"taxa_dia_min": 4, "taxa_dia_max": 2}, "Faixa de taxa_dia: minimo maior"),
        ({"prescricoes_max": -1}, "Faixa de prescricoes nao pode ser negativa"),
        ({"prescricoes_min": 9, "prescricoes_max": 2}, "Faixa de prescricoes: minimo maior"),
        ({"farmacias_min": -1}, "Faixa de farmacias nao pode ser negativa"),
        ({"farmacias_min": 4, "farmacias_max": 2}, "Faixa de farmacias: minimo maior"),
        ({"municipios_max": -1}, "Faixa de municipios nao pode ser negativa"),
        ({"municipios_min": 3, "municipios_max": 2}, "Faixa de municipios: minimo maior"),
        ({"sequencia_dias_min": -1}, "Faixa de dias com sequencia nao pode ser negativa"),
        ({"sequencia_dias_min": 4, "sequencia_dias_max": 2}, "Faixa de dias com sequencia: minimo maior"),
        ({"sequencia_severidade_min": 5}, "sequencia_severidade_min deve ser"),
        ({"sequencia_tipo": "duplo"}, "sequencia_tipo deve ser"),
        ({"exclusividade_min": -1}, "exclusividade deve estar entre"),
        ({"exclusividade_max": 101}, "exclusividade deve estar entre"),
        ({"exclusividade_min": 75, "exclusividade_max": 20}, "exclusividade: minimo maior"),
    )
    for overrides, message in invalid:
        params = {"situacao_cfm": None, "uf_crm": None}
        params.update(overrides)
        with pytest.raises(HTTPException, match=message):
            medico.montar_filtros_medico(**params)


def test_dimension_and_doctor_catalog_contracts_cache_and_normalize(monkeypatch):
    monkeypatch.setattr(medico, "_CACHE_BASES", _ImmediateCache())
    dim = pl.DataFrame({"id_medico_num": [1, 2], "id_medico": ["123/SP", "456/RJ"]})
    monkeypatch.setattr(medico, "scan_crm_medico_dim", lambda: dim.lazy())
    result = medico._dim()
    assert result.get_column("uf_crm").to_list() == ["SP", "RJ"]

    bad_dim = pl.DataFrame({"id_medico_num": [1], "id_medico": ["bad"]})
    monkeypatch.setattr(medico, "scan_crm_medico_dim", lambda: bad_dim.lazy())
    with pytest.raises(HTTPException, match="fora do formato numero/UF"):
        medico._dim()

    doctors = pl.DataFrame({"id_medico": ["123/SP"], "dt_primeira_inscricao_uf": [date(2015, 1, 1)]})
    monkeypatch.setattr(medico, "get_dados_medico_df", lambda: doctors)
    assert medico._cadastro().columns == ["id_medico", "dt_primeira_inscricao_uf"]
    monkeypatch.setattr(medico, "get_dados_medico_df", lambda: pl.DataFrame({"id_medico": ["123/SP"]}))
    with pytest.raises(HTTPException, match="sem colunas"):
        medico._cadastro()
    monkeypatch.setattr(medico, "get_dados_medico_df", lambda: (_ for _ in ()).throw(RuntimeError("offline")))
    with pytest.raises(HTTPException, match="indisponivel: offline"):
        medico._cadastro()


def test_production_range_filter_requires_aggregate_contract_and_filters_rows(monkeypatch):
    from backend.api.services.analytics import crm_analysis

    ranking = pl.DataFrame(
        {"id_medico": ["M1", "M2"], "taxa_prescricoes_dia": [2.5, 1.5], "nu_prescricoes": [25, 15]}
    )
    monkeypatch.setattr(crm_analysis, "ranking_agregado_escopo", lambda **kwargs: ranking)
    filters = medico.FiltrosMedico(taxa_dia_min=2.0, prescricoes_max=30)
    result = medico._ids_por_faixa(filters, date(2024, 1, 1), date(2024, 1, 31), ("SP", None, None))
    assert result.get_column("id_medico").to_list() == ["M1"]
    with pytest.raises(ValueError, match="sem faixa de producao"):
        medico._ids_por_faixa(medico.FiltrosMedico(), date(2024, 1, 1), date(2024, 1, 31), (None, None, None))

    monkeypatch.setattr(crm_analysis, "ranking_agregado_escopo", lambda **kwargs: pl.DataFrame({"id_medico": ["M1"]}))
    with pytest.raises(HTTPException, match="Ranking agregado sem colunas"):
        medico._ids_por_faixa(filters, date(2024, 1, 1), date(2024, 1, 31), (None, None, None))


def test_filtered_doctor_bitmaps_combine_registration_geography_ranges_and_alert_days(monkeypatch):
    dim = pl.DataFrame(
        {"id_medico_num": [1, 2, 3], "id_medico": ["123/SP", "456/RJ", "789/SP"], "uf_crm": ["SP", "RJ", "SP"]}
    )
    cadastro = pl.DataFrame({"id_medico": ["123/SP", "789/SP"], "dt_primeira_inscricao_uf": [date(2000, 1, 1)] * 2})
    activity = pl.DataFrame(
        {"id_medico_num": [1, 2, 3], "exclusividade": [80.0, 40.0, 70.0], "qtd_farmacias": [3, 1, 2]}
    )
    municipalities = pl.DataFrame({"id_medico_num": [1, 2, 3], "qtd_municipios": [2, 1, 4]})
    sequences = pl.DataFrame({"id_medico": ["123/SP"], "dias": [2]})
    monkeypatch.setattr(medico, "_CACHE_MEDICOS", _ImmediateCache())
    monkeypatch.setattr(medico, "_dim", lambda: dim)
    monkeypatch.setattr(medico, "_cadastro", lambda: cadastro)
    monkeypatch.setattr(medico, "_ids_por_faixa", lambda *args: pl.DataFrame({"id_medico": ["123/SP", "456/RJ"]}))
    monkeypatch.setattr(medico, "_atuacao_por_medico", lambda *args: activity)
    monkeypatch.setattr(medico, "_municipios_por_medico", lambda *args: municipalities)
    monkeypatch.setattr(medico, "_sequencia_por_medico", lambda *args: sequences)

    filters = medico.FiltrosMedico(
        situacao_cfm="localizado", ufs_crm=("SP", "RJ"), taxa_dia_min=1.0,
        exclusividade_min=50, farmacias_min=2, municipios_max=3, sequencia_severidade_min=2,
    )
    assert list(medico.medicos_filtrados(filters, date(2024, 1, 1), date(2024, 1, 31), (None, None, None))) == [1]

    not_located = medico.FiltrosMedico(situacao_cfm="nao_localizado")
    assert list(medico.medicos_filtrados(not_located, date(2024, 1, 1), date(2024, 1, 31), (None, None, None))) == [2]

    sequence_max_only = medico.FiltrosMedico(sequencia_dias_max=0)
    assert list(medico.medicos_filtrados(sequence_max_only, date(2024, 1, 1), date(2024, 1, 31), (None, None, None))) == [2, 3]
    with pytest.raises(ValueError, match="sem filtro de medico ativo"):
        medico.medicos_filtrados(medico.FiltrosMedico(), date(2024, 1, 1), date(2024, 1, 31), (None, None, None))


def test_sequence_filter_validates_alert_severity_and_reports_source_failures(monkeypatch):
    monkeypatch.setattr(medico, "_CACHE_BASES", _ImmediateCache())
    alerts = pl.DataFrame(
        {"competencia": [202401, 202401], "id_medico": ["123/SP", "123/SP"],
         "dt_alerta": ["2024-01-01", "2024-01-01"], "id_severidade": [1, 3]}
    )
    monkeypatch.setattr(medico, "scan_crm_concentracao_unico_alertas_global", lambda: alerts.lazy())
    assert medico._sequencia_por_medico(date(2024, 1, 1), date(2024, 1, 31), 2).to_dicts() == [
        {"id_medico": "123/SP", "dias": 1}
    ]
    unknown = alerts.with_columns(pl.lit(9).alias("id_severidade"))
    monkeypatch.setattr(medico, "scan_crm_concentracao_unico_alertas_global", lambda: unknown.lazy())
    with pytest.raises(HTTPException, match="Severidade de sequencia desconhecida"):
        medico._sequencia_por_medico(date(2024, 1, 1), date(2024, 1, 31), 1)
    monkeypatch.setattr(medico, "scan_crm_concentracao_unico_alertas_global", lambda: (_ for _ in ()).throw(RuntimeError("offline")))
    with pytest.raises(HTTPException, match="Alertas de sequencia.*offline"):
        medico._sequencia_por_medico(date(2024, 1, 1), date(2024, 1, 31), 1)
    with pytest.raises(ValueError, match="Tipo de sequencia invalido"):
        medico._sequencia_por_medico(date(2024, 1, 1), date(2024, 1, 31), 1, "duplo")


def test_sequence_filter_counts_multi_crm_windows_with_minimum_participation(monkeypatch):
    monkeypatch.setattr(medico, "_CACHE_BASES", _ImmediateCache())
    single = pl.DataFrame(
        {"competencia": [202401, 202401], "id_medico": ["123/SP", "789/SP"],
         "dt_alerta": ["2024-01-02", "2024-01-09"], "id_severidade": [3, 3]}
    )
    windows = pl.DataFrame(
        {
            "competencia": [202401, 202401, 202401, 202401, 202402, 202401],
            "id_medico": ["123/SP", "123/SP", "123/SP", "456/RJ", "456/RJ", "456/RJ"],
            # 123/SP: duas janelas no mesmo dia (1 dia) e uma abaixo do minimo de autorizacoes.
            "dt_alerta": ["2024-01-02", "2024-01-02", "2024-01-03", "2024-01-04", "2024-02-01", "2024-01-05"],
            "nu_autorizacoes_crm": [5, 8, 4, 6, 9, 5],
            "id_severidade": [3, 4, 4, 3, 4, 1],
        }
    )
    checks = []
    monkeypatch.setattr(medico, "scan_crm_concentracao_unico_alertas_global", lambda: single.lazy())
    monkeypatch.setattr(medico, "scan_crm_concentracao_multiplo_medico_global", lambda: windows.lazy())
    monkeypatch.setattr(medico, "conferir_crm_concentracao_multiplo_medico_global", lambda: checks.append("ok"))
    period = (date(2024, 1, 1), date(2024, 1, 31))

    def days(tipo, severity=3):
        rows = medico._sequencia_por_medico(*period, severity, tipo).sort("id_medico")
        return dict(zip(rows.get_column("id_medico").to_list(), rows.get_column("dias").to_list()))

    assert medico.SEQUENCIA_MULTIPLO_MIN_AUTORIZACOES == 5
    assert days("multiplo") == {"123/SP": 1, "456/RJ": 1}
    # Severidade 1 inclui a janela de 2024-01-05 do 456/RJ; fevereiro fica fora do periodo.
    assert days("multiplo", severity=1) == {"123/SP": 1, "456/RJ": 2}
    assert days("unico") == {"123/SP": 1, "789/SP": 1}
    # Qualquer: dias distintos dos dois tipos (o dia 02 do 123/SP e o mesmo nos dois).
    assert days("qualquer") == {"123/SP": 1, "456/RJ": 1, "789/SP": 1}
    assert checks  # a ponte e conferida contra as fontes antes de cada leitura

    unknown = windows.with_columns(pl.lit(9).alias("id_severidade"))
    monkeypatch.setattr(medico, "scan_crm_concentracao_multiplo_medico_global", lambda: unknown.lazy())
    with pytest.raises(HTTPException, match="Severidade de sequencia desconhecida"):
        medico._sequencia_por_medico(*period, 1, "multiplo")

    def stale():
        raise RuntimeError("modulo desatualizado")

    monkeypatch.setattr(medico, "conferir_crm_concentracao_multiplo_medico_global", stale)
    with pytest.raises(HTTPException, match="multiplos CRMs por medico indisponiveis: modulo desatualizado") as error:
        medico._sequencia_por_medico(*period, 1, "multiplo")
    assert error.value.status_code == 503


def test_activity_aggregates_annual_and_monthly_pharmacy_pairs_and_validates_period(monkeypatch):
    from backend.api.services.analytics import crm_analysis

    monkeypatch.setattr(medico, "_CACHE_BASES", _ImmediateCache())
    monkeypatch.setattr(crm_analysis, "_dividir_periodo_ranking", lambda *_args: ([2024], [202401]))
    monkeypatch.setattr(
        medico,
        "scan_crm_farmacia_medico_ano",
        lambda: pl.DataFrame(
            {"ano": [2024], "id_medico_num": [1], "id_cnpj": [100], "nu_prescricoes": [7]}
        ).lazy(),
    )
    monkeypatch.setattr(
        medico,
        "scan_crm_medico_estabelecimento_mes",
        lambda: pl.DataFrame(
            {"competencia": [202401, 202401], "id_medico": ["123/SP", "123/SP"], "id_cnpj": [100, 200], "nu_prescricoes_mes": [3, 10]}
        ).lazy(),
    )
    monkeypatch.setattr(
        medico,
        "_dim",
        lambda: pl.DataFrame(
            {"id_medico": ["123/SP"], "id_medico_num": [1]},
            schema_overrides={"id_medico_num": pl.Int32},
        ),
    )

    result = medico._atuacao_por_medico(date(2024, 1, 1), date(2024, 1, 31))
    assert result.to_dicts() == [{"id_medico_num": 1, "exclusividade": 50.0, "qtd_farmacias": 2}]

    monkeypatch.setattr(crm_analysis, "_dividir_periodo_ranking", lambda *_args: ([], []))
    with pytest.raises(HTTPException, match="Periodo sem meses"):
        medico._atuacao_por_medico(date(2024, 1, 1), date(2024, 1, 31))

    monkeypatch.setattr(crm_analysis, "_dividir_periodo_ranking", lambda *_args: ([2024], []))
    monkeypatch.setattr(
        medico,
        "scan_crm_farmacia_medico_ano",
        lambda: pl.DataFrame(
            {"ano": [2024], "id_medico_num": [1], "id_cnpj": [100], "nu_prescricoes": [0]}
        ).lazy(),
    )
    with pytest.raises(HTTPException, match="total de prescricoes nao positivo"):
        medico._atuacao_por_medico(date(2024, 1, 1), date(2024, 12, 31))


def test_activity_wraps_unexpected_source_errors_as_service_unavailable(monkeypatch):
    from backend.api.services.analytics import crm_analysis

    monkeypatch.setattr(medico, "_CACHE_BASES", _ImmediateCache())
    monkeypatch.setattr(crm_analysis, "_dividir_periodo_ranking", lambda *_args: ([], [202401]))
    monkeypatch.setattr(
        medico,
        "scan_crm_medico_estabelecimento_mes",
        lambda: (_ for _ in ()).throw(RuntimeError("broken monthly source")),
    )

    with pytest.raises(HTTPException, match="medico x farmacia indisponiveis: broken monthly source") as error:
        medico._atuacao_por_medico(date(2024, 1, 1), date(2024, 1, 31))
    assert error.value.status_code == 503


def test_municipality_counts_join_annual_and_monthly_pairs_and_validate_required_profile(monkeypatch):
    from backend.api.services.analytics import crm_analysis

    monkeypatch.setattr(medico, "_CACHE_BASES", _ImmediateCache())
    monkeypatch.setattr(crm_analysis, "_dividir_periodo_ranking", lambda *_args: ([2024], [202401]))
    monkeypatch.setattr(
        medico,
        "get_df_perfil_estabelecimento",
        lambda: pl.DataFrame({"id_cnpj": [100, 200], "id_ibge7": [3550308, 3534401]}),
    )
    monkeypatch.setattr(
        medico,
        "scan_crm_farmacia_medico_ano",
        lambda: pl.DataFrame({"ano": [2024], "id_medico_num": [1], "id_cnpj": [100]}).lazy(),
    )
    monkeypatch.setattr(
        medico,
        "scan_crm_medico_estabelecimento_mes",
        lambda: pl.DataFrame(
            {"competencia": [202401], "id_medico": ["123/SP"], "id_cnpj": [200]}
        ).lazy(),
    )
    monkeypatch.setattr(
        medico,
        "_dim",
        lambda: pl.DataFrame(
            {"id_medico": ["123/SP"], "id_medico_num": [1]},
            schema_overrides={"id_medico_num": pl.Int32},
        ),
    )

    result = medico._municipios_por_medico(date(2024, 1, 1), date(2024, 1, 31))
    assert result.to_dicts() == [{"id_medico_num": 1, "qtd_municipios": 2}]

    monkeypatch.setattr(crm_analysis, "_dividir_periodo_ranking", lambda *_args: ([], []))
    with pytest.raises(HTTPException, match="Periodo sem meses"):
        medico._municipios_por_medico(date(2024, 1, 1), date(2024, 1, 31))

    monkeypatch.setattr(crm_analysis, "_dividir_periodo_ranking", lambda *_args: ([2024], []))
    monkeypatch.setattr(medico, "get_df_perfil_estabelecimento", lambda: pl.DataFrame({"id_cnpj": [100]}))
    with pytest.raises(HTTPException, match="sem colunas"):
        medico._municipios_por_medico(date(2024, 1, 1), date(2024, 12, 31))

    monkeypatch.setattr(
        medico,
        "get_df_perfil_estabelecimento",
        lambda: pl.DataFrame({"id_cnpj": [100], "id_ibge7": [None]}, schema_overrides={"id_ibge7": pl.Int64}),
    )
    with pytest.raises(HTTPException, match="sem id_ibge7"):
        medico._municipios_por_medico(date(2024, 1, 1), date(2024, 12, 31))

    monkeypatch.setattr(medico, "get_df_perfil_estabelecimento", lambda: (_ for _ in ()).throw(RuntimeError("offline")))
    with pytest.raises(HTTPException, match="Perfil de estabelecimentos indisponivel"):
        medico._municipios_por_medico(date(2024, 1, 1), date(2024, 12, 31))


def test_municipality_counts_reject_pairs_without_profile_and_wrap_source_errors(monkeypatch):
    from backend.api.services.analytics import crm_analysis

    monkeypatch.setattr(medico, "_CACHE_BASES", _ImmediateCache())
    monkeypatch.setattr(crm_analysis, "_dividir_periodo_ranking", lambda *_args: ([2024], []))
    monkeypatch.setattr(
        medico,
        "get_df_perfil_estabelecimento",
        lambda: pl.DataFrame({"id_cnpj": [100], "id_ibge7": [3550308]}),
    )
    monkeypatch.setattr(
        medico,
        "scan_crm_farmacia_medico_ano",
        lambda: pl.DataFrame(
            {"ano": [2024], "id_medico_num": [1], "id_cnpj": [999]}
        ).lazy(),
    )

    with pytest.raises(HTTPException, match="id_cnpj: 999") as missing:
        medico._municipios_por_medico(date(2024, 1, 1), date(2024, 12, 31))
    assert missing.value.status_code == 503

    monkeypatch.setattr(crm_analysis, "_dividir_periodo_ranking", lambda *_args: ([], [202401]))
    monkeypatch.setattr(
        medico,
        "scan_crm_medico_estabelecimento_mes",
        lambda: (_ for _ in ()).throw(RuntimeError("broken monthly source")),
    )
    with pytest.raises(HTTPException, match="medico x farmacia indisponiveis: broken monthly source") as error:
        medico._municipios_por_medico(date(2024, 1, 1), date(2024, 1, 31))
    assert error.value.status_code == 503


def test_pharmacy_counts_combine_sources_and_reject_inconsistent_or_unavailable_data(monkeypatch):
    monkeypatch.setattr(medico, "_CACHE_BASES", _ImmediateCache())
    monkeypatch.setattr(
        medico,
        "_atuacao_por_medico",
        lambda *_args: pl.DataFrame({"id_medico_num": [1], "qtd_farmacias": [2]}),
    )
    monkeypatch.setattr(
        medico,
        "_municipios_por_medico",
        lambda *_args: pl.DataFrame({"id_medico_num": [1], "qtd_municipios": [2]}),
    )
    monkeypatch.setattr(medico, "_dim", lambda: pl.DataFrame({"id_medico_num": [1], "id_medico": ["123/SP"]}))
    result = medico.farmacias_por_medico(date(2024, 1, 1), date(2024, 1, 31))
    assert result.to_dicts() == [{"id_medico": "123/SP", "qtd_farmacias": 2, "qtd_municipios": 2}]

    monkeypatch.setattr(
        medico,
        "_municipios_por_medico",
        lambda *_args: pl.DataFrame({"id_medico_num": [2], "qtd_municipios": [1]}),
    )
    with pytest.raises(HTTPException, match="divergentes"):
        medico.farmacias_por_medico(date(2024, 1, 1), date(2024, 1, 31))


def test_pharmacy_counts_for_selected_doctors_handle_empty_success_and_failures(monkeypatch):
    from backend.api.services.analytics import crm_analysis

    assert medico.farmacias_dos_medicos([], date(2024, 1, 1), date(2024, 1, 31)).schema == {
        "id_medico": pl.Utf8, "qtd_farmacias": pl.Int64, "qtd_municipios": pl.Int64,
    }
    monkeypatch.setattr(
        medico,
        "_dim",
        lambda: pl.DataFrame(
            {"id_medico_num": [1, 2], "id_medico": ["123/SP", "456/RJ"]},
            schema_overrides={"id_medico_num": pl.Int32},
        ),
    )
    monkeypatch.setattr(crm_analysis, "_dividir_periodo_ranking", lambda *_args: ([2024], [202401]))
    monkeypatch.setattr(medico, "get_df_perfil_estabelecimento", lambda: pl.DataFrame({"id_cnpj": [100, 200], "id_ibge7": [3550308, 3534401]}))
    monkeypatch.setattr(
        medico,
        "scan_crm_farmacia_medico_ano",
        lambda: pl.DataFrame({"ano": [2024, 2024], "id_medico_num": [1, 2], "id_cnpj": [100, 200]}).lazy(),
    )
    monkeypatch.setattr(
        medico,
        "scan_crm_medico_estabelecimento_mes",
        lambda: pl.DataFrame(
            {"competencia": [202401], "id_medico": ["123/SP"], "id_cnpj": [200]}
        ).lazy(),
    )
    result = medico.farmacias_dos_medicos(["123/SP"], date(2024, 1, 1), date(2024, 1, 31))
    assert result.to_dicts() == [{"id_medico": "123/SP", "qtd_farmacias": 2, "qtd_municipios": 2}]

    monkeypatch.setattr(crm_analysis, "_dividir_periodo_ranking", lambda *_args: ([], []))
    with pytest.raises(HTTPException, match="Periodo sem meses"):
        medico.farmacias_dos_medicos(["123/SP"], date(2024, 1, 1), date(2024, 1, 31))

    monkeypatch.setattr(crm_analysis, "_dividir_periodo_ranking", lambda *_args: ([2024], []))
    monkeypatch.setattr(medico, "get_df_perfil_estabelecimento", lambda: (_ for _ in ()).throw(RuntimeError("offline")))
    with pytest.raises(HTTPException, match="Perfil de estabelecimentos indisponivel"):
        medico.farmacias_dos_medicos(["123/SP"], date(2024, 1, 1), date(2024, 12, 31))


def test_selected_doctor_pharmacy_counts_reject_missing_municipality_and_wrap_source_errors(monkeypatch):
    from backend.api.services.analytics import crm_analysis

    monkeypatch.setattr(medico, "_CACHE_BASES", _ImmediateCache())
    monkeypatch.setattr(
        medico,
        "_dim",
        lambda: pl.DataFrame(
            {"id_medico_num": [1], "id_medico": ["123/SP"]},
            schema_overrides={"id_medico_num": pl.Int32},
        ),
    )
    monkeypatch.setattr(crm_analysis, "_dividir_periodo_ranking", lambda *_args: ([], [202401]))
    monkeypatch.setattr(
        medico,
        "get_df_perfil_estabelecimento",
        lambda: pl.DataFrame({"id_cnpj": [100], "id_ibge7": [3550308]}),
    )
    monkeypatch.setattr(
        medico,
        "scan_crm_medico_estabelecimento_mes",
        lambda: (_ for _ in ()).throw(RuntimeError("broken monthly source")),
    )
    with pytest.raises(HTTPException, match="medico x farmacia indisponiveis: broken monthly source") as source_error:
        medico.farmacias_dos_medicos(["123/SP"], date(2024, 1, 1), date(2024, 1, 31))
    assert source_error.value.status_code == 503

    monkeypatch.setattr(crm_analysis, "_dividir_periodo_ranking", lambda *_args: ([2024], []))
    monkeypatch.setattr(
        medico,
        "scan_crm_farmacia_medico_ano",
        lambda: pl.DataFrame(
            {"ano": [2024], "id_medico_num": [1], "id_cnpj": [999]},
            schema_overrides={"id_medico_num": pl.Int32},
        ).lazy(),
    )
    with pytest.raises(HTTPException, match="sem municipio no perfil de estabelecimentos") as missing:
        medico.farmacias_dos_medicos(["123/SP"], date(2024, 1, 1), date(2024, 12, 31))
    assert missing.value.status_code == 503


def test_filtered_doctors_apply_lower_municipality_bound(monkeypatch):
    dim = pl.DataFrame(
        {"id_medico_num": [1, 2], "id_medico": ["123/SP", "456/RJ"]},
        schema_overrides={"id_medico_num": pl.Int32},
    )
    municipalities = pl.DataFrame(
        {"id_medico_num": [1, 2], "qtd_municipios": [2, 1]},
        schema_overrides={"id_medico_num": pl.Int32},
    )
    monkeypatch.setattr(medico, "_CACHE_MEDICOS", _ImmediateCache())
    monkeypatch.setattr(medico, "_dim", lambda: dim)
    monkeypatch.setattr(medico, "_municipios_por_medico", lambda *_args: municipalities)

    selected = medico.medicos_filtrados(
        medico.FiltrosMedico(municipios_min=2),
        date(2024, 1, 1),
        date(2024, 1, 31),
        (None, None, None),
    )
    assert list(selected) == [1]
