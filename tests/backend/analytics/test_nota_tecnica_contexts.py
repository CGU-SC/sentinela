from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

import polars as pl
import pytest

from backend.api.services.analytics import nota_tecnica_contexts as contexts


@pytest.fixture
def temp_dir():
    with TemporaryDirectory(prefix="sentinela-nt-contexts-", dir=Path.cwd()) as directory:
        yield Path(directory)


def test_regional_context_validates_required_id_and_locality_contract(monkeypatch):
    with pytest.raises(RuntimeError, match="id_ibge7 e obrigatorio"):
        contexts._resolve_regional_context({})
    monkeypatch.setattr(contexts, "get_localidades_df", lambda: pl.DataFrame({"wrong": [1]}))
    with pytest.raises(RuntimeError, match="colunas obrigatorias"):
        contexts._resolve_regional_context({"id_ibge7": 1})
    monkeypatch.setattr(
        contexts,
        "get_localidades_df",
        lambda: pl.DataFrame({"id_ibge7": [2], "id_regiao_saude": [5], "sg_uf": ["SP"]}),
    )
    with pytest.raises(RuntimeError, match="nao encontrado"):
        contexts._resolve_regional_context({"id_ibge7": 1})
    monkeypatch.setattr(
        contexts,
        "get_localidades_df",
        lambda: pl.DataFrame({"id_ibge7": [1], "id_regiao_saude": [None], "sg_uf": ["SP"]}),
    )
    with pytest.raises(RuntimeError, match="sem id_regiao_saude/UF"):
        contexts._resolve_regional_context({"id_ibge7": 1})
    monkeypatch.setattr(
        contexts,
        "get_localidades_df",
        lambda: pl.DataFrame({"id_ibge7": [1], "id_regiao_saude": [5], "sg_uf": ["SP"]}),
    )
    assert contexts._resolve_regional_context({"id_ibge7": "1"}) == {
        "id_regiao_saude": 5,
        "uf": "SP",
        "nome_regiao": "ID 5",
    }
    for empty_id in (None, "", "None"):
        with pytest.raises(RuntimeError, match="id_ibge7 e obrigatorio"):
            contexts._resolve_regional_context({"id_ibge7": empty_id})


def test_scope_percentual_comparison_filters_geography_period_and_validates_data(monkeypatch):
    movimentacao = pl.DataFrame(
        {
            "id_cnpj": [1, 1, 2, 3],
            "periodo": [date(2024, 1, 1), date(2024, 2, 1), date(2024, 1, 1), date(2024, 1, 1)],
            "total_vendas": [100.0, 100.0, 100.0, 0.0],
            "total_sem_comprovacao": [20.0, 20.0, 40.0, 0.0],
        }
    )
    perfil = pl.DataFrame({"id_cnpj": [1, 2, 3], "uf": ["SP", "RJ", "SP"]})
    monkeypatch.setattr(contexts, "get_df", lambda: movimentacao)
    monkeypatch.setattr(contexts, "get_df_perfil_estabelecimento", lambda: perfil)
    result = contexts._build_scope_percentual_comparison(
        {"percValSemComp": 25.0}, date(2024, 1, 1), date(2024, 12, 31), uf="SP"
    )
    assert result == {"mediana": 20.0, "multiplicador": 1.25}
    all_scope = contexts._build_scope_percentual_comparison({"percValSemComp": 25.0}, None, None)
    assert all_scope["mediana"] == 30.0
    with pytest.raises(RuntimeError, match="percValSemComp e obrigatorio"):
        contexts._build_scope_percentual_comparison({}, None, None)
    with pytest.raises(RuntimeError, match="Sem movimentacao.*UF XX"):
        contexts._build_scope_percentual_comparison(
            {"percValSemComp": 10}, date(2024, 1, 1), date(2024, 12, 31), uf="XX"
        )
    zero_sales = pl.DataFrame(
        {"id_cnpj": [1], "periodo": [date(2024, 1, 1)], "total_vendas": [0.0], "total_sem_comprovacao": [0.0]}
    )
    monkeypatch.setattr(contexts, "get_df", lambda: zero_sales)
    with pytest.raises(RuntimeError, match="Percentuais ausentes"):
        contexts._build_scope_percentual_comparison({"percValSemComp": 10}, date(2024, 1, 1), date(2024, 12, 31))
    zeros = pl.DataFrame(
        {"id_cnpj": [1, 2], "periodo": [date(2024, 1, 1)] * 2, "total_vendas": [100.0, 100.0], "total_sem_comprovacao": [0.0, 0.0]}
    )
    monkeypatch.setattr(contexts, "get_df", lambda: zeros)
    with pytest.raises(RuntimeError, match="Mediana.*maior que zero"):
        contexts._build_scope_percentual_comparison({"percValSemComp": 10}, date(2024, 1, 1), date(2024, 12, 31))


def test_regional_comparison_positioning_and_percentile_contexts(monkeypatch):
    locality = pl.DataFrame({"id_ibge7": [1], "id_regiao_saude": [100], "sg_uf": ["SP"]})
    monkeypatch.setattr(contexts, "get_localidades_df", lambda: locality)
    farms = [
        SimpleNamespace(cnpj="12.345.678/0001-90", razao_social="Farmacia A", municipio="X", totalMov=100.0, percValSemComp=80.0, score_risco=3.0),
        SimpleNamespace(cnpj="", razao_social=None, municipio=None, totalMov=None, percValSemComp=150.0, score_risco=None),
    ]
    regional = SimpleNamespace(farmacias=farms, municipios=[SimpleNamespace(municipio="X"), SimpleNamespace(municipio="")])
    monkeypatch.setattr(contexts, "get_regional_benchmarking", lambda **kwargs: regional)
    monkeypatch.setattr(
        contexts,
        "_build_scope_percentual_comparison",
        lambda data, start, end, **kwargs: {"mediana": 20.0, "multiplicador": data["percValSemComp"] / 20.0},
    )
    comparison = contexts._build_regional_comparison_context({"percValSemComp": 40.0}, {"id_ibge7": 1}, None, None)
    assert comparison["id_regiao_saude"] == 100
    assert comparison["multiplicador"] == pytest.approx(40.0 / 115.0)
    assert comparison["multiplicador_uf"] == 2.0

    positioned = contexts._build_posicionamento_regional_context("12.345.678/0001-90", {"id_ibge7": 1}, None, None)
    assert positioned["current"]["is_current"] is True
    assert positioned["rows"][1]["pct_sem_comprovacao"] == 100.0
    assert positioned["rows"][1]["razao_social"] == ""
    with pytest.raises(RuntimeError, match="CNPJ analisado nao encontrado"):
        contexts._build_posicionamento_regional_context("999", {"id_ibge7": 1}, None, None)

    monkeypatch.setattr(contexts, "get_metric_percentiles", lambda **kwargs: [{"score": 20, "percentile": 25}, {"score": 40, "percentile": 50}])
    percentil = contexts._build_percentil_risco_context({"percValSemComp": 30}, {"id_ibge7": 1}, None, None)
    assert percentil["current_value"] == 30.0 and percentil["percentile_rank"] == 50
    monkeypatch.setattr(contexts, "get_metric_percentiles", lambda **kwargs: [])
    with pytest.raises(RuntimeError, match="Percentis regionais indisponiveis"):
        contexts._build_percentil_risco_context({}, {"id_ibge7": 1}, None, None)

    monkeypatch.setattr(contexts, "get_regional_benchmarking", lambda **kwargs: SimpleNamespace(farmacias=[], municipios=[]))
    with pytest.raises(RuntimeError, match="sem farmacias"):
        contexts._build_regional_comparison_context({"percValSemComp": 10}, {"id_ibge7": 1}, None, None)
    with pytest.raises(RuntimeError, match="sem farmacias"):
        contexts._build_posicionamento_regional_context("1", {"id_ibge7": 1}, None, None)


def test_regional_comparison_rejects_missing_percentages_and_nonpositive_medians(monkeypatch):
    monkeypatch.setattr(contexts, "get_localidades_df", lambda: pl.DataFrame({"id_ibge7": [1], "id_regiao_saude": [2], "sg_uf": ["SP"]}))
    farms = [SimpleNamespace(percValSemComp=None), SimpleNamespace(percValSemComp=None)]
    monkeypatch.setattr(contexts, "get_regional_benchmarking", lambda **kwargs: SimpleNamespace(farmacias=farms, municipios=[SimpleNamespace(municipio="X")]))
    with pytest.raises(RuntimeError, match="percValSemComp e obrigatorio"):
        contexts._build_regional_comparison_context({}, {"id_ibge7": 1}, None, None)
    with pytest.raises(RuntimeError, match="Percentuais regionais obrigatorios"):
        contexts._build_regional_comparison_context({"percValSemComp": 10}, {"id_ibge7": 1}, None, None)
    farms[0].percValSemComp = 0.0
    farms[1].percValSemComp = 0.0
    farms[0].percValSemComp = 0.0
    with pytest.raises(RuntimeError, match="Mediana regional deve ser maior"):
        contexts._build_regional_comparison_context({"percValSemComp": 10}, {"id_ibge7": 1}, None, None)
    farms[0].percValSemComp = 1.0
    monkeypatch.setattr(contexts, "_build_scope_percentual_comparison", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("mediana zero")))
    with pytest.raises(RuntimeError, match="mediana zero"):
        contexts._build_regional_comparison_context({"percValSemComp": 10}, {"id_ibge7": 1}, None, None)
    monkeypatch.setattr(contexts, "get_regional_benchmarking", lambda **kwargs: SimpleNamespace(farmacias=[SimpleNamespace(percValSemComp=1)], municipios=[]))
    with pytest.raises(RuntimeError, match="Municipios regionais obrigatorios"):
        contexts._build_regional_comparison_context({"percValSemComp": 10}, {"id_ibge7": 1}, None, None)


def test_gtin_normalization_and_medicine_lookup_contract(monkeypatch):
    assert contexts._normalize_gtin(" 000123.0 ") == "000123"
    assert contexts._normalize_gtin(123) == "123"
    with pytest.raises(RuntimeError, match="colunas obrigatorias"):
        monkeypatch.setattr(contexts, "get_medicamentos_df", lambda: pl.DataFrame({"codigo_barra": ["1"]}))
        contexts._build_medicamentos_lookup()
    monkeypatch.setattr(
        contexts,
        "get_medicamentos_df",
        lambda: pl.DataFrame(
            {
                "codigo_barra": [None, "", "0001.0", "0002", "0003"],
                "patologia": [None, None, " diabetes ", None, "None"],
                "principio_ativo": [None, None, "Substancia", None, ""],
                "produto": [None, None, "Outro", "Produto", ""],
                "descricao": [None, None, "Descricao", "Final", ""],
            }
        ),
    )
    lookup = contexts._build_medicamentos_lookup()
    assert lookup == {
        "0001": {"descricao": "Substancia", "patologia": "diabetes"},
        "0002": {"descricao": "Produto", "patologia": None},
    }
    monkeypatch.setattr(contexts, "get_medicamentos_df", lambda: pl.DataFrame({"codigo_barra": [None], "patologia": [None]}))
    with pytest.raises(RuntimeError, match="sem descricoes validas"):
        contexts._build_medicamentos_lookup()


def _gtin_frame():
    return pl.DataFrame(
        {
            "codigo_barra": ["0001", "0001", "0002"],
            "periodo": [date(2024, 1, 1), date(2024, 2, 1), date(2024, 1, 1)],
            "qnt_caixas_sem_comprovacao": [2, 3, 4],
            "valor_vendas": [100.0, 100.0, 50.0],
            "valor_sem_comprovacao": [20.0, 30.0, 10.0],
        }
    )


def _set_medicine_lookup(monkeypatch, rows=None):
    rows = rows or {"codigo_barra": ["0001", "0002"], "patologia": ["P1", "P2"], "produto": ["A", "B"]}
    monkeypatch.setattr(contexts, "get_medicamentos_df", lambda: pl.DataFrame(rows))


def _write_gtin_parquet(temp_dir, monkeypatch, frame=None):
    path = temp_dir / "gtin.parquet"
    (frame if frame is not None else _gtin_frame()).write_parquet(path)
    monkeypatch.setattr(contexts, "_get_cnpj_cache_dir", lambda cnpj: str(temp_dir))
    monkeypatch.setattr(contexts, "MOVIMENTACAO_MENSAL_GTIN_PARQUET", path.name)
    monkeypatch.setattr(contexts, "get_evolucao_mensal_gtin", lambda *args: None)
    return path


def test_gtin_sem_comprovacao_context_aggregates_enriches_and_counts_concentration(temp_dir, monkeypatch):
    _write_gtin_parquet(temp_dir, monkeypatch)
    _set_medicine_lookup(monkeypatch)
    result = contexts._build_gtin_sem_comprovacao_context("123", date(2024, 1, 1), date(2024, 2, 28), concentration_target=0.5)
    assert result["total_gtins"] == 2
    assert result["total_qtd"] == 9
    assert result["total_valor"] == 60.0
    assert result["representativos_count"] == 1
    assert result["rows"][0]["gtin"] == "0001"
    assert result["rows"][0]["pct_sem_comprovacao"] == 25.0


def test_gtin_concentration_reports_zero_percent_when_sales_denominator_is_zero(temp_dir, monkeypatch):
    _write_gtin_parquet(
        temp_dir,
        monkeypatch,
        pl.DataFrame(
            {
                "codigo_barra": ["0001"],
                "periodo": [date(2024, 1, 1)],
                "qnt_caixas_sem_comprovacao": [1],
                "valor_vendas": [0.0],
                "valor_sem_comprovacao": [25.0],
            }
        ),
    )
    _set_medicine_lookup(monkeypatch, {"codigo_barra": ["0001"], "patologia": ["P1"], "produto": ["Medicamento"]})
    result = contexts._build_gtin_sem_comprovacao_context("x", None, None)
    assert result["rows"][0]["pct_sem_comprovacao"] == 0.0
    assert result["total_pct_sem_comprovacao"] == 0.0


def test_gtin_sem_comprovacao_context_fails_for_missing_invalid_and_unenriched_data(temp_dir, monkeypatch):
    monkeypatch.setattr(contexts, "get_evolucao_mensal_gtin", lambda *args: None)
    monkeypatch.setattr(contexts, "_get_cnpj_cache_dir", lambda _: str(temp_dir))
    monkeypatch.setattr(contexts, "MOVIMENTACAO_MENSAL_GTIN_PARQUET", "absent.parquet")
    with pytest.raises(RuntimeError, match="nao encontrado"):
        contexts._build_gtin_sem_comprovacao_context("x", None, None)

    path = temp_dir / "gtin.parquet"
    monkeypatch.setattr(contexts, "MOVIMENTACAO_MENSAL_GTIN_PARQUET", path.name)
    pl.DataFrame({"wrong": [1]}).write_parquet(path)
    with pytest.raises(RuntimeError, match="sem colunas obrigatorias"):
        contexts._build_gtin_sem_comprovacao_context("x", None, None)
    _write_gtin_parquet(temp_dir, monkeypatch)
    with pytest.raises(RuntimeError, match="Movimentacao mensal por GTIN vazia"):
        contexts._build_gtin_sem_comprovacao_context("x", date(2025, 1, 1), date(2025, 12, 31))
    _write_gtin_parquet(temp_dir, monkeypatch, pl.DataFrame({
        "codigo_barra": ["1"], "periodo": [date(2024, 1, 1)], "qnt_caixas_sem_comprovacao": [1],
        "valor_vendas": [0.0], "valor_sem_comprovacao": [0.0],
    }))
    with pytest.raises(RuntimeError, match="Nenhum GTIN"):
        contexts._build_gtin_sem_comprovacao_context("x", None, None)
    _write_gtin_parquet(temp_dir, monkeypatch)
    _set_medicine_lookup(monkeypatch, {"codigo_barra": ["different"], "patologia": ["P"], "produto": ["Desc"]})
    with pytest.raises(RuntimeError, match="Descricao obrigatoria ausente"):
        contexts._build_gtin_sem_comprovacao_context("x", None, None)
    _set_medicine_lookup(monkeypatch, {"codigo_barra": ["0001"], "patologia": [None], "produto": ["Desc"]})
    with pytest.raises(RuntimeError, match="Patologia obrigatoria ausente"):
        contexts._build_gtin_sem_comprovacao_context("x", None, None)


def test_atypical_medicine_context_handles_no_data_and_contributing_gtins(temp_dir, monkeypatch):
    _write_gtin_parquet(temp_dir, monkeypatch)
    _set_medicine_lookup(monkeypatch)
    assert contexts._build_medicamentos_aumento_atipico_context("x", None, None, []) == []
    result = contexts._build_medicamentos_aumento_atipico_context(
        "x",
        date(2024, 1, 1),
        date(2024, 12, 31),
        [{"chave_semestre": 202401, "chave_semestre_anterior": 202302, "semestre": "1S/2024"}],
    )
    assert len(result) == 2
    assert {row["gtin"] for row in result} == {"0001", "0002"}
    assert all(row["aumento_relativo_pct"] is None for row in result)


def test_atypical_medicine_context_covers_empty_cache_period_and_bad_descriptions(temp_dir, monkeypatch):
    _set_medicine_lookup(monkeypatch)
    monkeypatch.setattr(contexts, "get_evolucao_mensal_gtin", lambda *args: None)
    monkeypatch.setattr(contexts, "_get_cnpj_cache_dir", lambda _: str(temp_dir))
    monkeypatch.setattr(contexts, "MOVIMENTACAO_MENSAL_GTIN_PARQUET", "missing.parquet")
    semesters = [{"chave_semestre": 202401, "chave_semestre_anterior": 202302}]
    assert contexts._build_medicamentos_aumento_atipico_context("x", None, None, semesters) == []

    path = temp_dir / "gtin.parquet"
    monkeypatch.setattr(contexts, "MOVIMENTACAO_MENSAL_GTIN_PARQUET", path.name)
    pl.DataFrame({"wrong": [1]}).write_parquet(path)
    assert contexts._build_medicamentos_aumento_atipico_context("x", None, None, semesters) == []
    _write_gtin_parquet(temp_dir, monkeypatch, pl.DataFrame({
        "codigo_barra": ["0001"], "periodo": [date(2020, 1, 1)], "valor_vendas": [10.0], "valor_sem_comprovacao": [1.0]
    }))
    assert contexts._build_medicamentos_aumento_atipico_context("x", date(2024, 1, 1), date(2024, 12, 31), semesters) == []
    _write_gtin_parquet(temp_dir, monkeypatch, pl.DataFrame({
        "codigo_barra": ["0001"], "periodo": [date(2024, 1, 1)], "valor_vendas": [0.0], "valor_sem_comprovacao": [1.0]
    }))
    assert contexts._build_medicamentos_aumento_atipico_context("x", None, None, [{"semestre": "incompleto"}]) == []
    assert contexts._build_medicamentos_aumento_atipico_context(
        "x", None, None, [{"chave_semestre": 202402, "chave_semestre_anterior": 202303}]
    ) == []
    assert contexts._build_medicamentos_aumento_atipico_context("x", None, None, [{"chave_semestre": 202401}]) == []
    assert contexts._build_medicamentos_aumento_atipico_context("x", None, None, semesters) == []

    growth = pl.DataFrame(
        {
            "codigo_barra": ["0001", "0002", "0001", "0002", "0003"],
            "periodo": [date(2023, 7, 1), date(2023, 7, 1), date(2024, 1, 1), date(2024, 1, 1), date(2024, 1, 1)],
            "valor_vendas": [1000.0, 1000.0, 1500.0, 1010.0, 5.0],
            "valor_sem_comprovacao": [10.0, 20.0, 100.0, 30.0, 1.0],
        }
    )
    _write_gtin_parquet(temp_dir, monkeypatch, growth)
    _set_medicine_lookup(monkeypatch, {
        "codigo_barra": ["0001", "0002", "0003"], "patologia": ["P1", "P2", "P3"], "produto": ["A", "B", "C"]
    })
    semestres = [{"chave_semestre": 202401, "chave_semestre_anterior": 202302, "semestre": "1S/2024"}]
    selected = contexts._build_medicamentos_aumento_atipico_context("x", None, None, semestres, max_por_semestre=1)
    assert len(selected) == 1
    assert selected[0]["gtin"] == "0001" and selected[0]["aumento_relativo_pct"] == 50.0
    assert "semestre_fmt" in selected[0] and selected[0]["semestre_anterior_fmt"]
    summarized = contexts._build_medicamentos_aumento_atipico_context("x", None, None, semestres, participacao_minima_pct=100)
    assert len(summarized) == 1 and summarized[0]["gtin"] == "3 GTINs" and summarized[0]["is_demais"]
    _set_medicine_lookup(monkeypatch, {"codigo_barra": ["not-present"], "patologia": ["P"], "produto": ["Desc"]})
    with pytest.raises(RuntimeError, match="Descricao obrigatoria ausente.*tabela de aumento"):
        contexts._build_medicamentos_aumento_atipico_context("x", None, None, semestres)


def test_atypical_medicine_context_skips_semesters_without_positive_gtin_growth(temp_dir, monkeypatch):
    data = pl.DataFrame(
        {
            "codigo_barra": ["0001", "0001"],
            "periodo": [date(2023, 7, 1), date(2024, 1, 1)],
            "valor_vendas": [100.0, 80.0],
            "valor_sem_comprovacao": [10.0, 8.0],
        }
    )
    _write_gtin_parquet(temp_dir, monkeypatch, data)
    _set_medicine_lookup(monkeypatch)
    semesters = [{"chave_semestre": 202401, "chave_semestre_anterior": 202302, "semestre": "1S/2024"}]
    assert contexts._build_medicamentos_aumento_atipico_context("x", None, None, semesters) == []


def test_ultimo_mes_sav_context_validates_and_selects_latest_month(monkeypatch):
    monkeypatch.setattr(contexts, "get_evolucao_financeira", lambda *args: SimpleNamespace(semestres=None))
    with pytest.raises(RuntimeError, match="sem campo semestres"):
        contexts._build_ultimo_mes_sav_context("x", None, None)
    monkeypatch.setattr(contexts, "get_evolucao_financeira", lambda *args: SimpleNamespace(semestres=[{"meses": []}]))
    with pytest.raises(RuntimeError, match="mensal obrigatoria vazia"):
        contexts._build_ultimo_mes_sav_context("x", None, None)
    monkeypatch.setattr(
        contexts,
        "get_evolucao_financeira",
        lambda *args: SimpleNamespace(semestres=[{"meses": [{"mes": "2024-01", "total": 12.5}]}, {"meses": [{"mes": "2024-11", "total": 20.125}]}]),
    )
    result = contexts._build_ultimo_mes_sav_context("x", None, None)
    assert result["mes"] == "2024-11" and result["total"] == 20.12


def test_evolucao_financeira_context_maps_rows_and_growth_flags(monkeypatch):
    monkeypatch.setattr(contexts, "get_evolucao_mensal_gtin", lambda *args: None)
    monkeypatch.setattr(contexts, "get_volume_atipico_aumento_minimo", lambda: 25.0)
    monkeypatch.setattr(contexts, "_build_medicamentos_aumento_atipico_context", lambda *args: [{"gtin": "1"}])
    with pytest.raises(RuntimeError, match="sem campo semestres"):
        monkeypatch.setattr(contexts, "get_evolucao_financeira", lambda *args: SimpleNamespace(semestres=None))
        contexts._build_evolucao_financeira_context("x", None, None)
    with pytest.raises(RuntimeError, match="obrigatoria vazia"):
        monkeypatch.setattr(contexts, "get_evolucao_financeira", lambda *args: SimpleNamespace(semestres=[]))
        contexts._build_evolucao_financeira_context("x", None, None)
    complete = {"semestre": "1S/2024", "total": 200.0, "regular": 100.0, "irregular": 100.0, "pct_irregular": 50.0}
    with pytest.raises(RuntimeError, match="coluna obrigatoria.*regular"):
        monkeypatch.setattr(contexts, "get_evolucao_financeira", lambda *args: SimpleNamespace(semestres=[{"semestre": "1S/2024", "total": 1}]))
        contexts._build_evolucao_financeira_context("x", None, None)
    monkeypatch.setattr(contexts, "get_evolucao_financeira", lambda *args: SimpleNamespace(semestres=iter(())))
    with pytest.raises(RuntimeError, match="sem linhas validas"):
        contexts._build_evolucao_financeira_context("x", None, None)

    first = {**complete, "volume_atipico": True, "taxa_crescimento_pct": 70, "aumento_valor_semestre": 50,
             "chave_semestre": 202401, "chave_semestre_anterior": 202302, "limite_volume_atipico_pct": 60,
             "mes_inicio": "2024-01", "mes_fim": "2024-06"}
    second = {**complete, "semestre": "2S/2024", "total": 50, "regular": 45, "irregular": 5,
              "pct_irregular": 10, "volume_atipico": False, "taxa_crescimento_pct": None,
              "aumento_valor_semestre": None, "chave_semestre": None, "chave_semestre_anterior": None,
              "limite_volume_atipico_pct": None, "mes_inicio": "2024-07", "mes_fim": "2024-12"}
    monkeypatch.setattr(contexts, "get_evolucao_financeira", lambda *args: SimpleNamespace(semestres=[first, second]))
    result = contexts._build_evolucao_financeira_context("x", None, None, growth_threshold_pct=55)
    assert result["total"] == 250.0 and result["irregular"] == 105.0
    assert result["growth_threshold_pct"] == 60
    assert result["periodo_meses"]
    assert result["medicamentos_aumento_atipico"] == [{"gtin": "1"}]
    assert result["top_irregulares"][0]["semestre"] == "1S/2024"

    monkeypatch.setattr(contexts, "_build_medicamentos_aumento_atipico_context", lambda *args: [])
    monkeypatch.setattr(contexts, "get_evolucao_financeira", lambda *args: SimpleNamespace(semestres=[complete]))
    one = contexts._build_evolucao_financeira_context("x", None, None)
    assert one["periodo_meses"] == one["rows"][0]["semestre_fmt"]
    assert one["growth_threshold_pct"] == 50.0


def test_model_and_esocial_format_helpers_cover_input_types():
    assert contexts._model_to_dict({"x": 1}) == {"x": 1}
    assert contexts._model_to_dict(SimpleNamespace(model_dump=lambda: {"x": 2})) == {"x": 2}
    assert contexts._model_to_dict(SimpleNamespace(dict=lambda: {"x": 3})) == {"x": 3}
    with pytest.raises(TypeError, match="Objeto semestral inesperado"):
        contexts._model_to_dict(object())
    assert contexts._semestre_fmt_from_key(202401) == "1º Semestre/2024"
    assert contexts._format_competencia_esocial(None) == "—"
    assert contexts._format_competencia_esocial(202405) == "05/2024"
    assert contexts._format_competencia_esocial("x") == "x"
    assert contexts._format_competencia_esocial(202413) == "202413"
    assert contexts._format_cbo_label("bad", "title") == "CBO não informado"
    assert contexts._format_cbo_label(123, " Médico ") == "Médico (CBO 000123)"
    assert contexts._format_cbo_label(2235, "") == "CBO 002235 sem título válido"
    assert contexts._format_date_iso(None) == "—"
    assert contexts._format_date_iso(date(2024, 1, 2)) == "2024-01-02"
    assert contexts._format_date_iso("2024-01-02") == "2024-01-02"


def _esocial_frames(*, years=True, workers=True, alert=False):
    year_schema = {
        "id_cnpj": pl.Int32, "ano_base": pl.Int32, "competencia_base": pl.Int32, "qtd_trabalhadores": pl.Int32,
        "qtd_farmaceuticos": pl.Int32, "qtd_registros_vinculo_ano": pl.Int32,
        "qtd_trabalhadores_vinculo_ano": pl.Int32, "qtd_farmaceuticos_vinculo_ano": pl.Int32,
        "qtd_trabalhadores_cbo_sem_titulo_vinculo_ano": pl.Int32, "has_cbo_sem_titulo": pl.Boolean,
        "is_um_trabalhador": pl.Boolean, "is_um_trabalhador_sem_farmaceutico": pl.Boolean,
        "is_um_trabalhador_cbo_sem_titulo": pl.Boolean, "cbo_unico_trabalhador": pl.Int32,
        "titulo_cbo_unico_trabalhador": pl.String, "dt_carga_fonte": pl.Date,
    }
    year_rows = [
        {"id_cnpj": 1, "ano_base": 2024, "competencia_base": 202405, "qtd_trabalhadores": 1, "qtd_farmaceuticos": 0,
         "qtd_registros_vinculo_ano": 1, "qtd_trabalhadores_vinculo_ano": 1, "qtd_farmaceuticos_vinculo_ano": 0,
         "qtd_trabalhadores_cbo_sem_titulo_vinculo_ano": 1, "has_cbo_sem_titulo": True, "is_um_trabalhador": True,
         "is_um_trabalhador_sem_farmaceutico": True, "is_um_trabalhador_cbo_sem_titulo": True,
         "cbo_unico_trabalhador": 2235, "titulo_cbo_unico_trabalhador": "Medico", "dt_carga_fonte": date(2025, 1, 1)}
    ] if years else []
    worker_schema = {
        "id_cnpj": pl.Int32, "ano_base": pl.Int32, "cpf_trabalhador": pl.String, "cbo": pl.Int32,
        "titulo_cbo": pl.String, "dt_admissao": pl.Date, "dt_rescisao": pl.Date, "is_cbo_sem_titulo": pl.Boolean,
    }
    worker_rows = [{"id_cnpj": 1, "ano_base": 2024, "cpf_trabalhador": "0001", "cbo": 2235,
                    "titulo_cbo": "Medico", "dt_admissao": date(2024, 2, 1), "dt_rescisao": None,
                    "is_cbo_sem_titulo": False}] if workers else []
    ultima_schema = {
        "id_cnpj": pl.Int32, "ano_ultima_movimentacao": pl.Int32, "ano_esocial_referencia_ultima_movimentacao": pl.Int32,
        "is_sem_esocial_no_ano_ultima_movimentacao": pl.Boolean, "ultimo_periodo_movimentacao": pl.Date,
        "dt_referencia_ultima_movimentacao": pl.Date, "valor_pfpb_ultimo_mes": pl.Float64,
        "qtd_autorizacoes_ultimo_mes": pl.Int32, "qtd_trabalhadores_ativos_ultima_movimentacao": pl.Int32,
        "qtd_farmaceuticos_ativos_ultima_movimentacao": pl.Int32, "dt_ultima_rescisao_antes_ultima_movimentacao": pl.Date,
        "dt_ultimo_trabalhador_ativo": pl.Date, "ultimo_mes_trabalhador_ativo": pl.Date,
        "dt_inicio_periodo_sem_funcionario": pl.Date, "qtd_dias_sem_funcionario_ate_ultima_movimentacao": pl.Int32,
        "valor_pfpb_periodo_sem_funcionario": pl.Float64, "qtd_autorizacoes_periodo_sem_funcionario": pl.Int32,
        "has_movimentacao_sem_funcionario_ativo": pl.Boolean,
    }
    ultima_rows = [{
        "id_cnpj": 1, "ano_ultima_movimentacao": 2024, "ano_esocial_referencia_ultima_movimentacao": 2023,
        "is_sem_esocial_no_ano_ultima_movimentacao": True, "ultimo_periodo_movimentacao": date(2024, 8, 1),
        "dt_referencia_ultima_movimentacao": date(2024, 9, 1), "valor_pfpb_ultimo_mes": 100.0,
        "qtd_autorizacoes_ultimo_mes": 2, "qtd_trabalhadores_ativos_ultima_movimentacao": 0,
        "qtd_farmaceuticos_ativos_ultima_movimentacao": 0, "dt_ultima_rescisao_antes_ultima_movimentacao": None,
        "dt_ultimo_trabalhador_ativo": date(2024, 1, 1), "ultimo_mes_trabalhador_ativo": date(2024, 1, 1),
        "dt_inicio_periodo_sem_funcionario": date(2024, 2, 1), "qtd_dias_sem_funcionario_ate_ultima_movimentacao": 182,
        "valor_pfpb_periodo_sem_funcionario": 500.0, "qtd_autorizacoes_periodo_sem_funcionario": 9,
        "has_movimentacao_sem_funcionario_ativo": alert,
    }]
    metadados = pl.DataFrame({"nome_base": ["esocial"], "nome_artefato": ["esocial_cnpj_ano"], "dt_referencia_max": [date(2025, 1, 1)]})
    return (
        pl.DataFrame(year_rows, schema=year_schema),
        pl.DataFrame(worker_rows, schema=worker_schema),
        pl.DataFrame(ultima_rows, schema=ultima_schema),
        metadados,
    )


def _patch_esocial(monkeypatch, perfil=None, frames=None, metadata=None):
    anos, trabalhadores, ultima, metadados = frames or _esocial_frames()
    monkeypatch.setattr(
        contexts,
        "get_df_perfil_estabelecimento",
        lambda: perfil if perfil is not None else pl.DataFrame({"id_cnpj": [1], "cnpj": ["12345678000190"]}),
    )
    monkeypatch.setattr(contexts, "scan_esocial_cnpj_ano", lambda: anos.lazy())
    monkeypatch.setattr(contexts, "scan_esocial_cnpj_trabalhador_ano", lambda: trabalhadores.lazy())
    monkeypatch.setattr(contexts, "scan_esocial_cnpj_ultima_movimentacao", lambda: ultima.lazy())
    monkeypatch.setattr(contexts, "get_df_sentinela_metadados_base", lambda: metadata if metadata is not None else metadados)


def test_esocial_context_rejects_invalid_cnpj_and_missing_profile(monkeypatch):
    with pytest.raises(RuntimeError, match="CNPJ invalido"):
        contexts._build_esocial_context("x", None, None)
    monkeypatch.setattr(contexts, "get_df_perfil_estabelecimento", lambda: pl.DataFrame({"cnpj": ["12345678000190"]}))
    with pytest.raises(RuntimeError, match="colunas obrigatorias"):
        contexts._build_esocial_context("12345678000190", None, None)
    monkeypatch.setattr(contexts, "get_df_perfil_estabelecimento", lambda: pl.DataFrame({"id_cnpj": [1], "cnpj": ["99999999000100"]}))
    with pytest.raises(RuntimeError, match="nao encontrado"):
        contexts._build_esocial_context("12345678000190", None, None)


def test_esocial_context_handles_empty_years_and_builds_worker_and_alert_detail(monkeypatch):
    frames = _esocial_frames(years=False)
    _patch_esocial(monkeypatch, frames=frames)
    empty = contexts._build_esocial_context("12.345.678/0001-90", None, None)
    assert empty["has_data"] is False and empty["trabalhador_detalhe_modo"] == "sem_dados"

    frames = _esocial_frames(alert=True)
    _patch_esocial(monkeypatch, frames=frames)
    result = contexts._build_esocial_context("12345678000190", date(2024, 1, 1), date(2024, 12, 31))
    assert result["has_data"] is True
    assert result["anos_sem_farmaceutico"] == [result["rows"][0]]
    assert result["trabalhador_detalhe_modo"] == "lista_completa"
    assert result["rows"][0]["trabalhador_unico_cbo_txt"] == "Medico (CBO 002235)"
    assert result["movimentacao_sem_funcionario_alerta"]["ultimo_periodo_movimentacao_txt"]
    assert result["movimentacao_sem_funcionario_alerta"]["qtd_autorizacoes_periodo_sem_funcionario"] == 9


def test_esocial_large_worker_detail_keeps_only_critical_years_or_omits_all(monkeypatch):
    years, workers, ultima, metadata = _esocial_frames(alert=True)
    many_workers = pl.concat(
        [workers.with_columns(pl.lit(f"{index:04d}").alias("cpf_trabalhador")) for index in range(16)]
    )

    _patch_esocial(monkeypatch, frames=(years, many_workers, ultima, metadata))
    critical = contexts._build_esocial_context("12345678000190", None, None)
    assert critical["trabalhador_detalhe_total_cpfs"] == 16
    assert critical["trabalhador_detalhe_modo"] == "anos_criticos"
    assert len(critical["trabalhador_detalhe_rows"]) == 16

    noncritical_years = years.with_columns(
        pl.lit(1).cast(pl.Int32).alias("qtd_farmaceuticos"),
        pl.lit(1).cast(pl.Int32).alias("qtd_farmaceuticos_vinculo_ano"),
        pl.lit(0).cast(pl.Int32).alias("qtd_trabalhadores_cbo_sem_titulo_vinculo_ano"),
        pl.lit(False).alias("has_cbo_sem_titulo"),
        pl.lit(False).alias("is_um_trabalhador"),
        pl.lit(False).alias("is_um_trabalhador_sem_farmaceutico"),
        pl.lit(False).alias("is_um_trabalhador_cbo_sem_titulo"),
    )
    _patch_esocial(monkeypatch, frames=(noncritical_years, many_workers, ultima, metadata))
    omitted = contexts._build_esocial_context("12345678000190", None, None)
    assert omitted["trabalhador_detalhe_total_cpfs"] == 16
    assert omitted["trabalhador_detalhe_modo"] == "omitido"
    assert omitted["trabalhador_detalhe_rows"] == []


def test_esocial_context_validates_metadata_and_required_alert_fields(monkeypatch):
    frames = _esocial_frames()
    _patch_esocial(monkeypatch, frames=frames, metadata=pl.DataFrame({"nome_base": ["other"], "nome_artefato": ["other"], "dt_referencia_max": [date(2025, 1, 1)]}))
    with pytest.raises(RuntimeError, match="sem registro para esocial_cnpj_ano"):
        contexts._build_esocial_context("12345678000190", None, None)
    _patch_esocial(monkeypatch, frames=frames, metadata=pl.DataFrame({"nome_base": ["esocial"], "nome_artefato": ["esocial_cnpj_ano"], "dt_referencia_max": [None]}))
    with pytest.raises(RuntimeError, match="sem dt_referencia_max"):
        contexts._build_esocial_context("12345678000190", None, None)

    years, workers, ultima, meta = _esocial_frames(alert=True)
    ultima = ultima.with_columns(pl.lit(None, dtype=pl.Date).alias("dt_referencia_ultima_movimentacao"))
    _patch_esocial(monkeypatch, frames=(years, workers, ultima, meta))
    with pytest.raises(RuntimeError, match="campos obrigatorios"):
        contexts._build_esocial_context("12345678000190", None, None)


def test_esocial_context_rejects_missing_required_cache_columns(monkeypatch):
    anos, trabalhadores, ultima, meta = _esocial_frames()
    _patch_esocial(monkeypatch, frames=(pl.DataFrame({"id_cnpj": [1]}), trabalhadores, ultima, meta))
    with pytest.raises(RuntimeError, match="CNPJ/ano sem colunas"):
        contexts._build_esocial_context("12345678000190", None, None)
    _patch_esocial(monkeypatch, frames=(anos, pl.DataFrame({"id_cnpj": [1]}), ultima, meta))
    with pytest.raises(RuntimeError, match="trabalhador/ano sem colunas"):
        contexts._build_esocial_context("12345678000190", None, None)
    _patch_esocial(monkeypatch, frames=(anos, trabalhadores, pl.DataFrame({"id_cnpj": [1]}), meta))
    with pytest.raises(RuntimeError, match="ultima movimentacao sem colunas"):
        contexts._build_esocial_context("12345678000190", None, None)
    _patch_esocial(monkeypatch, frames=(anos, trabalhadores, ultima, pl.DataFrame({"nome_base": ["esocial"]})))
    with pytest.raises(RuntimeError, match="metadados das bases sem colunas"):
        contexts._build_esocial_context("12345678000190", None, None)


def test_socios_volume_atipico_context_matches_semesters_and_sorts():
    socios = [
        SimpleNamespace(data_entrada_sociedade=date(2024, 1, 15), nome_socio="B"),
        SimpleNamespace(data_entrada_sociedade=None, nome_socio="ignored"),
        SimpleNamespace(data_entrada_sociedade=date(2023, 7, 1), nome_socio=None),
        SimpleNamespace(data_entrada_sociedade=date(2020, 1, 1), nome_socio="old"),
    ]
    evolucao = {
        "semestres_atipicos": [
            {"chave_semestre": 202401, "semestre": "1S/2024", "taxa_crescimento_pct": 60},
            {"semestre": "2S/2023", "semestre_fmt": "2º sem 2023", "taxa_crescimento_pct": 80},
            {},
        ]
    }
    matches = contexts._build_socios_volume_atipico_context(socios, evolucao)
    assert len(matches) == 3
    assert matches[0]["nome_socio"] == "socio nao identificado"
    assert matches[0]["distancia_semestres"] == 0
    assert matches[1]["distancia_semestres"] == 1
    assert matches[2]["nome_socio"] == "B"
    assert matches[2]["distancia_semestres"] == 0
    assert contexts._build_socios_volume_atipico_context([], {}) == []


def test_repasses_context_no_results_formats_each_period_and_errors(monkeypatch):
    profile = pl.DataFrame({"cnpj": ["12345678000190"], "id_cnpj": [1]})
    monkeypatch.setattr(contexts, "get_df_perfil_estabelecimento", lambda: profile)
    empty = pl.DataFrame(schema={"id_cnpj": pl.Int32, "data_pagamento": pl.String, "valor_pago": pl.Float64})
    monkeypatch.setattr(contexts, "scan_pagamentos_consolidados_farmacia_popular", lambda: empty.lazy())
    result = contexts._build_repasses_anuais_context("12345678000190", None, None)
    assert result == {"rows": [], "total": 0.0, "periodo_fmt": "período analisado", "sem_repasses": True}
    assert contexts._build_repasses_anuais_context("12345678000190", date(2024, 1, 1), None)["periodo_fmt"] == "a partir de 2024"
    assert contexts._build_repasses_anuais_context("12345678000190", None, date(2024, 12, 31))["periodo_fmt"] == "até 2024"
    assert contexts._build_repasses_anuais_context("12345678000190", date(2024, 1, 1), date(2024, 12, 31))["periodo_fmt"] == "2024"
    monkeypatch.setattr(contexts, "get_df_perfil_estabelecimento", lambda: profile.head(0))
    with pytest.raises(RuntimeError, match="perfil para contexto"):
        contexts._build_repasses_anuais_context("missing", None, None)


def test_repasses_context_fills_zero_years_and_sums_values(monkeypatch):
    profile = pl.DataFrame({"cnpj": ["12345678000190"], "id_cnpj": [1]})
    payments = pl.DataFrame(
        {"id_cnpj": [1, 1], "data_pagamento": ["2023-06-01", "2025-06-01"], "valor_pago": [10.5, 20.25]}
    )
    monkeypatch.setattr(contexts, "get_df_perfil_estabelecimento", lambda: profile)
    monkeypatch.setattr(contexts, "scan_pagamentos_consolidados_farmacia_popular", lambda: payments.lazy())
    result = contexts._build_repasses_anuais_context("12345678000190", date(2023, 1, 1), date(2025, 12, 31))
    assert result["rows"] == [{"ano": 2023, "valor": 10.5}, {"ano": 2024, "valor": 0.0}, {"ano": 2025, "valor": 20.25}]
    assert result["total"] == 30.75 and result["periodo_fmt"] == "2023 a 2025"
