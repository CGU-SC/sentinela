from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory

import polars as pl
import pytest
from fastapi import HTTPException

from api.services.analytics import financeiro


def test_evolucao_financeira_aggregates_half_years_and_month_breakdown(monkeypatch):
    monkeypatch.setattr(financeiro, "get_volume_atipico_aumento_minimo", lambda: 10_000.0)
    monkeypatch.setattr(
        financeiro,
        "get_df_perfil_estabelecimento",
        lambda: pl.DataFrame({"cnpj": ["12345678000190"], "id_cnpj": [7]}),
    )
    monkeypatch.setattr(
        financeiro,
        "get_df",
        lambda: pl.DataFrame(
            {
                "id_cnpj": [7, 7, 8], "periodo": [date(2020, 1, 1), date(2020, 7, 1), date(2020, 1, 1)],
                "total_vendas": [100.0, 200.0, 900.0], "total_sem_comprovacao": [10.0, 50.0, 0.0],
            }
        ),
    )
    monkeypatch.setattr(
        financeiro,
        "get_df_volume_atipico_semestral",
        lambda: pl.DataFrame(
            {
                "id_cnpj": [7], "chave_semestre": [202002], "status_semestre": [1],
                "qtd_meses_presentes": [6], "chave_semestre_anterior": [202001],
                "aumento_valor_semestre": [100.0], "taxa_crescimento_pct": [50.0],
            }
        ),
    )

    result = financeiro.get_evolucao_financeira(
        "12345678000190", date(2020, 1, 1), date(2020, 12, 31)
    )
    assert [s.semestre for s in result.semestres] == ["1S/2020", "2S/2020"]
    assert result.semestres[0].total == 100.0
    assert result.semestres[0].pct_irregular == 10.0
    assert result.semestres[0].meses[0].mes == "2020-01"
    assert result.semestres[1].volume_atipico is False
    assert result.semestres[1].status_semestre == 1

    monkeypatch.setattr(
        financeiro,
        "get_df_volume_atipico_semestral",
        lambda: (_ for _ in ()).throw(RuntimeError("volume cache unavailable")),
    )
    without_volume = financeiro.get_evolucao_financeira("12345678000190")
    assert [item.semestre for item in without_volume.semestres] == ["1S/2020", "2S/2020"]


def test_mensal_gtin_aggregates_period_and_reports_missing_cache_error(monkeypatch):
    from types import SimpleNamespace

    base = pl.DataFrame(
        {
            "periodo": [date(2020, 1, 1), date(2020, 1, 1), date(2020, 2, 1)],
            "qnt_caixas_vendidas": [2, 3, 4], "qnt_caixas_sem_comprovacao": [1, 0, 2],
            "num_autorizacoes": [1, 2, 3], "valor_vendas": [100.0, 200.0, 400.0],
            "valor_sem_comprovacao": [10.0, 0.0, 80.0],
        }
    )
    monkeypatch.setattr(
        financeiro,
        "load_or_sync_movimentacao_mensal_gtin",
        lambda _cnpj: SimpleNamespace(df=base, error=None, from_cache=True, query_time_ms=2, save_time_ms=0, read_time_ms=1),
    )
    result = financeiro.get_evolucao_mensal_gtin("12345678000190", date(2020, 1, 1), date(2020, 1, 31))
    assert len(result.meses) == 1
    assert result.meses[0].mes == "2020-01"
    assert result.meses[0].valor_vendas == 300.0
    assert result.meses[0].pct_sem_comprovacao == 3.33

    monkeypatch.setattr(
        financeiro,
        "load_or_sync_movimentacao_mensal_gtin",
        lambda _cnpj: SimpleNamespace(df=None, error="offline", from_cache=False, query_time_ms=None, save_time_ms=None, read_time_ms=None),
    )
    from fastapi import HTTPException
    import pytest
    with pytest.raises(HTTPException) as error:
        financeiro.get_evolucao_mensal_gtin("12345678000190")
    assert error.value.status_code == 503


def test_repasses_summarize_paid_orders_and_period_filter(monkeypatch):
    monkeypatch.setattr(financeiro, "get_cache_dir", lambda: "cache")
    monkeypatch.setattr(financeiro.os.path, "exists", lambda _path: True)
    monkeypatch.setattr(financeiro, "get_df_perfil_estabelecimento", lambda: pl.DataFrame({"cnpj": ["12345678000190"], "id_cnpj": [7]}))
    payments = pl.DataFrame(
        {
            "id_cnpj": [7, 7, 7, 8], "data_pagamento": ["2020-01-02", "2020-01-20", "2020-02-02", "2020-01-02"],
            "programa_acao": ["  Acao  ", "Acao", "Outra", "Alheia"],
            "numero_ordem_bancaria": ["01", "02", "03", "04"], "valor_pago": [10.5, 25.0, 40.0, 999.0],
        }
    )
    monkeypatch.setattr(financeiro, "scan_pagamentos_consolidados_farmacia_popular", lambda: payments.lazy())

    result = financeiro.get_cnpj_repasses(
        "12345678000190", data_inicio=date(2020, 1, 1), data_fim=date(2020, 1, 31)
    )
    assert result.resumo.total_repassado == 35.5
    assert result.resumo.qtd_ordens == 2
    assert result.resumo.maior_repasse == 25.0
    assert result.resumo.ultimo_repasse_data == date(2020, 1, 20)
    assert [item.mes for item in result.mensal] == ["2020-01"]
    assert result.pagamentos[0].programa_acao == "Acao"


def test_repasses_fail_when_global_cache_is_missing(monkeypatch):
    from fastapi import HTTPException

    monkeypatch.setattr(financeiro, "get_cache_dir", lambda: "cache")
    monkeypatch.setattr(financeiro.os.path, "exists", lambda _path: False)
    with pytest.raises(HTTPException) as error:
        financeiro.get_cnpj_repasses("12345678000190")
    assert error.value.status_code == 503


def test_finance_evolution_handles_absent_profile_data_and_failed_required_cache(monkeypatch):
    monkeypatch.setattr(financeiro, "get_df_perfil_estabelecimento", lambda: pl.DataFrame({"cnpj": [], "id_cnpj": []}))
    assert financeiro.get_evolucao_financeira("12345678000190").semestres == []

    monkeypatch.setattr(financeiro, "get_df_perfil_estabelecimento", lambda: pl.DataFrame({"cnpj": ["12345678000190"], "id_cnpj": [7]}))
    monkeypatch.setattr(financeiro, "get_df", lambda: pl.DataFrame({"id_cnpj": [], "periodo": [], "total_vendas": [], "total_sem_comprovacao": []}, schema_overrides={"id_cnpj": pl.Int64, "periodo": pl.Date, "total_vendas": pl.Float64, "total_sem_comprovacao": pl.Float64}))
    assert financeiro.get_evolucao_financeira("12345678000190").semestres == []

    monkeypatch.setattr(financeiro, "get_df", lambda: (_ for _ in ()).throw(RuntimeError("cache indisponivel")))
    failed = financeiro.get_evolucao_financeira("12345678000190")
    assert failed.semestres == []


def test_monthly_gtin_handles_missing_dataframe_empty_and_period_without_rows(monkeypatch):
    from types import SimpleNamespace

    with pytest.raises(HTTPException, match="sem DataFrame carregado"):
        monkeypatch.setattr(
            financeiro, "load_or_sync_movimentacao_mensal_gtin",
            lambda _: SimpleNamespace(df=None, error=None, from_cache=False, query_time_ms=1, save_time_ms=0, read_time_ms=0),
        )
        financeiro.get_evolucao_mensal_gtin("12345678000190")

    empty = pl.DataFrame(
        schema={
            "periodo": pl.Date, "qnt_caixas_vendidas": pl.Int64, "qnt_caixas_sem_comprovacao": pl.Int64,
            "num_autorizacoes": pl.Int64, "valor_vendas": pl.Float64, "valor_sem_comprovacao": pl.Float64,
        }
    )
    monkeypatch.setattr(financeiro, "load_or_sync_movimentacao_mensal_gtin", lambda _: SimpleNamespace(
        df=empty, error=None, from_cache=False, query_time_ms=1, save_time_ms=2, read_time_ms=3,
    ))
    result = financeiro.get_evolucao_mensal_gtin("12345678000190")
    assert result.meses == [] and result.query_time_ms == 1 and result.from_cache is False

    outside = pl.DataFrame(
        {
            "periodo": [date(2020, 1, 1)], "qnt_caixas_vendidas": [1], "qnt_caixas_sem_comprovacao": [1],
            "num_autorizacoes": [1], "valor_vendas": [100.0], "valor_sem_comprovacao": [150.0],
        }
    )
    monkeypatch.setattr(financeiro, "load_or_sync_movimentacao_mensal_gtin", lambda _: SimpleNamespace(
        df=outside, error=None, from_cache=True, query_time_ms=0, save_time_ms=0, read_time_ms=0,
    ))
    no_period = financeiro.get_evolucao_mensal_gtin("12345678000190", date(2021, 1, 1), None)
    assert no_period.meses == []


def test_gtin_ranking_reads_month_and_semester_and_enriches_products(monkeypatch):
    import data_cache

    with TemporaryDirectory(prefix="sentinela-gtin-ranking-", dir=Path.cwd()) as directory:
        root = Path(directory)
        filename = "gtin.parquet"
        path = root / filename
        frame = pl.DataFrame(
            {
                "codigo_barra": ["0001.0", "0002", "0003"],
                "periodo": [date(2024, 1, 10), date(2024, 7, 10), date(2024, 7, 11)],
                "qnt_caixas_vendidas": [5, 4, 0], "qnt_caixas_sem_comprovacao": [2, 0, 0],
                "num_autorizacoes": [3, 2, 1], "valor_vendas": [50.0, 40.0, 30.0],
                "valor_sem_comprovacao": [20.0, 0.0, 0.0],
            }
        )
        frame.write_parquet(path)
        monkeypatch.setattr(financeiro, "_get_cnpj_cache_dir", lambda _: directory)
        monkeypatch.setattr(financeiro, "MOVIMENTACAO_MENSAL_GTIN_PARQUET", filename)
        monkeypatch.setattr(data_cache, "get_medicamentos_df", lambda: pl.DataFrame(
            {
                "codigo_barra": ["0001", "0002", None], "principio_ativo": ["Ativo A", None, None],
                "produto": ["Produto A", "Produto B", "ignorado"], "laboratorio": ["Lab", "Lab 2", "X"],
            }
        ))
        month = financeiro.get_gtin_ranking_periodo("12345678000190", "2024-01")
        assert month.summary.total_gtins == 1 and month.summary.gtins_irregulares == 1
        assert month.ranking[0].gtin == "0001" and month.ranking[0].medicamento == "Ativo A"
        semester = financeiro.get_gtin_ranking_periodo("12345678000190", "2024-S2")
        assert semester.summary.total_gtins == 1
        assert semester.ranking[0].gtin == "0002" and semester.ranking[0].medicamento == "Produto B"


def test_gtin_ranking_handles_lazy_creation_empty_period_and_missing_product_catalog(monkeypatch):
    with TemporaryDirectory(prefix="sentinela-gtin-ranking-empty-", dir=Path.cwd()) as directory:
        path = Path(directory) / "gtin.parquet"
        monkeypatch.setattr(financeiro, "_get_cnpj_cache_dir", lambda _: directory)
        monkeypatch.setattr(financeiro, "MOVIMENTACAO_MENSAL_GTIN_PARQUET", path.name)
        calls = []

        def no_create(_cnpj):
            calls.append(_cnpj)

        monkeypatch.setattr(financeiro, "get_evolucao_mensal_gtin", no_create)
        missing = financeiro.get_gtin_ranking_periodo("12345678000190", "2024-01")
        assert missing.ranking == [] and calls == ["12345678000190"]

        pl.DataFrame(
            {
                "codigo_barra": ["1", "2"], "periodo": [date(2024, 1, 1), date(2024, 7, 1)],
                "qnt_caixas_vendidas": [0, 1], "qnt_caixas_sem_comprovacao": [0, 1], "num_autorizacoes": [0, 1],
                "valor_vendas": [0.0, 10.0], "valor_sem_comprovacao": [0.0, 20.0],
            }
        ).write_parquet(path)
        empty = financeiro.get_gtin_ranking_periodo("12345678000190", "2024-02")
        assert empty.ranking == []

        import data_cache
        monkeypatch.setattr(data_cache, "get_medicamentos_df", lambda: (_ for _ in ()).throw(RuntimeError("catalog offline")))
        ranking = financeiro.get_gtin_ranking_periodo("12345678000190", "2024-S2")
        assert ranking.summary.total_gtins == 1
        assert ranking.ranking[0].medicamento == "Substância Não Identificada"


def test_repasses_returns_empty_results_for_unknown_farmacy_or_empty_period(monkeypatch):
    monkeypatch.setattr(financeiro, "get_cache_dir", lambda: "cache")
    monkeypatch.setattr(financeiro.os.path, "exists", lambda _path: True)
    monkeypatch.setattr(financeiro, "get_df_perfil_estabelecimento", lambda: pl.DataFrame({"cnpj": [], "id_cnpj": []}))
    unknown = financeiro.get_cnpj_repasses("00000000000000")
    assert unknown.resumo.qtd_ordens == 0 and unknown.pagamentos == []

    monkeypatch.setattr(financeiro, "get_df_perfil_estabelecimento", lambda: pl.DataFrame({"cnpj": ["12345678000190"], "id_cnpj": [7]}))
    empty_cache = pl.DataFrame(
        schema={
            "id_cnpj": pl.Int64,
            "data_pagamento": pl.String,
            "programa_acao": pl.String,
            "numero_ordem_bancaria": pl.String,
            "valor_pago": pl.Float64,
        }
    )
    monkeypatch.setattr(financeiro, "scan_pagamentos_consolidados_farmacia_popular", lambda: empty_cache.lazy())
    no_payments = financeiro.get_cnpj_repasses("12345678000190")
    assert no_payments.resumo.qtd_ordens == 0 and no_payments.pagamentos == []

    monkeypatch.setattr(
        financeiro,
        "scan_pagamentos_consolidados_farmacia_popular",
        lambda: pl.DataFrame(
            {
                "id_cnpj": [7], "data_pagamento": ["2020-01-02"], "programa_acao": ["A"],
                "numero_ordem_bancaria": ["1"], "valor_pago": [10.0],
            }
        ).lazy(),
    )
    empty = financeiro.get_cnpj_repasses("12345678000190", data_inicio=date(2021, 1, 1))
    assert empty.resumo.total_repassado == 0 and empty.mensal == []
