from collections import OrderedDict
from datetime import date

import polars as pl
import pytest
from fastapi import HTTPException

from backend.api.services.analytics import crm_analysis as crm
from backend.api.schemas.analytics import CrmPrescricoesMapaItemSchema


def test_cache_keys_generation_lru_and_helper_contracts(monkeypatch):
    generation = [7]
    monkeypatch.setattr(crm, "get_cache_generation", lambda: generation[0])
    key = crm._ranking_cache_key(geographic=True, inicio=date(2024, 1, 1), fim=date(2024, 1, 31), uf="SP")
    assert key == (7, "geografico", date(2024, 1, 1), date(2024, 1, 31), "SP", None, None)
    cache = OrderedDict()
    monkeypatch.setattr(crm, "_CRM_RANKING_CACHE", cache)
    monkeypatch.setattr(crm, "_CRM_RANKING_CACHE_MAX_ITEMS", 2)
    frame = pl.DataFrame({"id": [1]})
    crm._cache_ranking(key, frame)
    assert crm._get_cached_ranking(key).equals(frame)
    crm._cache_ranking((7, "second"), frame)
    crm._cache_ranking((7, "third"), frame)
    assert len(cache) == 2 and key not in cache
    crm._cache_ranking((8, "new-generation"), frame)
    assert list(cache) == [(8, "new-generation")]
    assert crm._get_cached_ranking((8, "missing")) is None

    crm._require_columns(pl.DataFrame({"id": [1]}), {"id"}, "fixture")
    with pytest.raises(HTTPException, match="fixture sem colunas obrigatorias: name"):
        crm._require_columns(pl.DataFrame({"id": [1]}), {"id", "name"}, "fixture")
    assert crm._competencia(date(2024, 8, 9)) == 202408
    assert crm._filtro_ativo(None) is False
    assert crm._filtro_ativo("  ") is False
    assert crm._filtro_ativo("Todos", neutral={"Todos"}) is False
    assert crm._filtro_ativo(0) is True


def test_period_and_percentage_helpers_enforce_full_months_and_safe_denominators():
    assert crm._period_bounds(date(2010, 1, 1), None) == (crm.MIN_DATA, crm.MAX_DATA)
    assert crm._period_bounds(date(2024, 1, 1), date(2024, 1, 31)) == (date(2024, 1, 1), date(2024, 1, 31))
    assert crm._period_bounds(date(2024, 12, 1), date(2024, 12, 31))[1] == date(2024, 12, 31)
    with pytest.raises(HTTPException, match="data_inicio posterior"):
        crm._period_bounds(date(2024, 2, 1), date(2024, 1, 31))
    with pytest.raises(HTTPException, match="meses completos"):
        crm._period_bounds(date(2024, 1, 2), date(2024, 1, 31))
    with pytest.raises(HTTPException, match="meses completos"):
        crm._period_bounds(date(2024, 1, 1), date(2024, 1, 30))

    result = pl.DataFrame(
        {"qtd_medicos_ativos": [10, 0], "qtd_medicos_alta_intensidade": [2, 0]}
    ).with_columns(crm._percentual_expr().alias("percentual"))
    assert result.get_column("percentual").to_list() == [20.0, None]
    assert crm._indice(None, 2.0) is None
    assert crm._indice(4.0, None) is None
    assert crm._indice(0.0, 0.0) == 0.0
    assert crm._indice(5.0, 0.0) is None
    assert crm._indice(10.0, 2.0) == 5.0
    assert crm._percentual_somado(pl.DataFrame({"qtd_medicos_ativos": [4, 6], "qtd_medicos_alta_intensidade": [1, 3]})) == 40.0
    assert crm._percentual_somado(pl.DataFrame({"qtd_medicos_ativos": [0], "qtd_medicos_alta_intensidade": [0]})) is None


def test_map_rows_format_uf_and_municipal_fields_and_small_sample_flag():
    uf_rows = pl.DataFrame(
        {
            "uf": ["SP"], "qtd_medicos_ativos": [30], "qtd_medicos_alta_intensidade": [6],
            "percentual_alta_intensidade": [20.0],
        }
    )
    uf_items = crm._map_items_from_summary(uf_rows, "uf", percentual_brasil=10.0)
    assert uf_items[0].identificador == "SP" and uf_items[0].indice_brasil == 2.0
    assert uf_items[0].amostra_pequena is False

    municipality = pl.DataFrame(
        {
            "id_ibge7": [3550308], "uf": ["SP"], "no_municipio": ["Sao Paulo"],
            "id_regiao_saude": ["100"], "no_regiao_saude": ["Capital"],
            "qtd_medicos_ativos": [12], "qtd_medicos_alta_intensidade": [3],
            "percentual_alta_intensidade": [25.0], "percentual_referencia_regiao": [20.0],
        }
    )
    items = crm._map_items_from_summary(municipality, "municipio", percentual_brasil=5.0, percentual_uf=10.0)
    assert items[0].identificador == "3550308" and items[0].id_regiao_saude == "100"
    assert items[0].indice_regiao == 1.25 and items[0].indice_uf == 2.5
    assert items[0].amostra_pequena is True
    assert crm._percentual_da_linha(uf_rows.with_columns(pl.lit(10).alias("qtd_medicos_ativos"), pl.lit(2).alias("qtd_medicos_alta_intensidade"))) == 20.0


def _national_map_rows():
    ufs = sorted(crm._UFS_CRM)
    rows = [
        {"nivel": "brasil", "id_geografico": "BR", "qtd_medicos_ativos": 1000, "qtd_medicos_alta_intensidade": 100}
    ]
    rows.extend(
        {"nivel": "uf", "id_geografico": uf, "qtd_medicos_ativos": 100, "qtd_medicos_alta_intensidade": index}
        for index, uf in enumerate(ufs, 1)
    )
    return pl.DataFrame(rows).with_columns(
        pl.lit(202401).alias("competencia_inicio"), pl.lit(202401).alias("competencia_fim")
    )


def test_national_map_cache_validates_territories_and_builds_reference(monkeypatch):
    monkeypatch.setattr(crm, "scan_crm_mapa_uf_periodo", lambda: _national_map_rows().lazy())
    ufs, brazil = crm._read_uf_brasil_period(date(2024, 1, 1), date(2024, 1, 31))
    assert ufs.height == 27 and brazil.height == 1
    items, count, references = crm._build_national_manager_map(
        inicio=date(2024, 1, 1), fim=date(2024, 1, 31), uf="SP"
    )
    assert len(items) == 1 and items[0].identificador == "SP"
    assert count == 100 and references["percentual_referencia_brasil"] is not None
    with pytest.raises(HTTPException, match="sem a UF XX"):
        crm._build_national_manager_map(inicio=date(2024, 1, 1), fim=date(2024, 1, 31), uf="XX")

    monkeypatch.setattr(crm, "scan_crm_mapa_uf_periodo", lambda: pl.DataFrame({"bad": [1]}).lazy())
    with pytest.raises(HTTPException, match="sem colunas obrigatorias"):
        crm._read_uf_brasil_period(date(2024, 1, 1), date(2024, 1, 31))


def test_national_map_rejects_short_invalid_duplicate_and_bad_identifier_caches(monkeypatch):
    monkeypatch.setattr(crm, "scan_crm_mapa_uf_periodo", lambda: _national_map_rows().head(27).lazy())
    with pytest.raises(HTTPException, match="sem as 28 linhas"):
        crm._read_uf_brasil_period(date(2024, 1, 1), date(2024, 1, 31))

    invalid = _national_map_rows().with_columns(
        pl.when(pl.col("id_geografico") == "AC").then(pl.lit(-1)).otherwise(pl.col("qtd_medicos_ativos")).alias("qtd_medicos_ativos")
    )
    monkeypatch.setattr(crm, "scan_crm_mapa_uf_periodo", lambda: invalid.lazy())
    with pytest.raises(HTTPException, match="contagens invalidas"):
        crm._read_uf_brasil_period(date(2024, 1, 1), date(2024, 1, 31))

    duplicate = pl.concat([_national_map_rows(), _national_map_rows().filter(pl.col("id_geografico") == "AC")])
    monkeypatch.setattr(crm, "scan_crm_mapa_uf_periodo", lambda: duplicate.lazy())
    with pytest.raises(HTTPException, match="sem as 28 linhas"):
        crm._read_uf_brasil_period(date(2024, 1, 1), date(2024, 1, 31))

    invalid_code = _national_map_rows().with_columns(
        pl.when(pl.col("id_geografico") == "AC").then(pl.lit("BR")).otherwise(pl.col("id_geografico")).alias("id_geografico")
    )
    monkeypatch.setattr(crm, "scan_crm_mapa_uf_periodo", lambda: invalid_code.lazy())
    with pytest.raises(HTTPException, match="identificador de UF invalido"):
        crm._read_uf_brasil_period(date(2024, 1, 1), date(2024, 1, 31))


def test_scope_limiter_and_month_period_split_contracts(monkeypatch):
    localidades = pl.DataFrame(
        {
            "id_ibge7": [3550308], "sg_uf": ["SP"], "id_regiao_saude": [100],
            "no_regiao_saude": ["Capital"], "no_municipio": ["Sao Paulo"],
        }
    )
    monkeypatch.setattr(crm, "get_localidades_df", lambda: localidades)
    assert crm._scope_label(uf=None, regiao_id=None, id_ibge7=None) == "Brasil"
    assert crm._scope_label(uf="SP", regiao_id=None, id_ibge7=None) == "UF SP"
    assert crm._scope_label(uf=None, regiao_id=100, id_ibge7=None) == "Região de Saúde 100"
    assert crm._scope_label(uf=None, regiao_id=None, id_ibge7=3550308) == "Município Sao Paulo"
    with pytest.raises(HTTPException, match="nao encontrado de forma univoca"):
        crm._scope_label(uf=None, regiao_id=None, id_ibge7=1)
    assert crm.escopo_territorial(None, None, 3550308) == ("municipio", "3550308")
    assert crm.escopo_territorial(None, 100, None) == ("regiao_saude", "100")
    assert crm.escopo_territorial("SP", None, None) == ("uf", "SP")
    assert crm.escopo_territorial("Todos", None, None) == ("brasil", None)

    all_months = pl.DataFrame({"competencia": list(range(202401, 202413))})
    monkeypatch.setattr(crm, "scan_crm_limiar_p95_mes", lambda: all_months.lazy())
    assert crm._dividir_periodo_ranking(date(2024, 1, 1), date(2024, 12, 31)) == ([2024], [])
    partial = pl.DataFrame({"competencia": [202401, 202402, 202404, 202405]})
    monkeypatch.setattr(crm, "scan_crm_limiar_p95_mes", lambda: partial.lazy())
    assert crm._dividir_periodo_ranking(date(2024, 1, 1), date(2024, 2, 29)) == ([], [202401, 202402])


def test_monthly_threshold_cache_requires_complete_valid_months(monkeypatch):
    valid = pl.DataFrame({"competencia": [202401, 202402], "qtd_medicos_ativos": [10, 12], "p95_taxa_dia": [2.0, 3.0]})
    monkeypatch.setattr(crm, "scan_crm_limiar_p95_mes", lambda: valid.lazy())
    result = crm._limiares_do_periodo(date(2024, 1, 1), date(2024, 2, 29))
    assert result.get_column("p95_taxa_dia").to_list() == [2.0, 3.0]

    monkeypatch.setattr(crm, "scan_crm_limiar_p95_mes", lambda: (_ for _ in ()).throw(HTTPException(409, "busy")))
    with pytest.raises(HTTPException) as original:
        crm._limiares_do_periodo(date(2024, 1, 1), date(2024, 1, 31))
    assert original.value.status_code == 409
    monkeypatch.setattr(crm, "scan_crm_limiar_p95_mes", lambda: (_ for _ in ()).throw(ValueError("offline")))
    with pytest.raises(HTTPException, match="indisponivel: offline"):
        crm._limiares_do_periodo(date(2024, 1, 1), date(2024, 1, 31))
    missing_columns = pl.DataFrame({"competencia": [202401], "p95_taxa_dia": [2.0]})
    monkeypatch.setattr(crm, "scan_crm_limiar_p95_mes", lambda: missing_columns.lazy())
    with pytest.raises(HTTPException, match="sem colunas obrigatorias"):
        crm._limiares_do_periodo(date(2024, 1, 1), date(2024, 1, 31))
    for broken in (
        pl.DataFrame({"competencia": [202401], "qtd_medicos_ativos": [10], "p95_taxa_dia": [None]}),
        pl.DataFrame({"competencia": [202401], "qtd_medicos_ativos": [10], "p95_taxa_dia": [0.5]}),
        pl.DataFrame({"competencia": [202401, 202401], "qtd_medicos_ativos": [10, 10], "p95_taxa_dia": [2.0, 2.0]}),
    ):
        monkeypatch.setattr(crm, "scan_crm_limiar_p95_mes", lambda broken=broken: broken.lazy())
        with pytest.raises(HTTPException, match="incompleto"):
            crm._limiares_do_periodo(date(2024, 1, 1), date(2024, 1, 31))


def test_ranking_aggregation_combines_complete_years_with_months(monkeypatch):
    monkeypatch.setattr(crm, "_limiares_do_periodo", lambda *_: pl.DataFrame({"competencia": [202101], "p95_taxa_dia": [3.0]}))
    monkeypatch.setattr(crm, "_dividir_periodo_ranking", lambda *_: ([2020], [202101]))
    year = pl.DataFrame(
        {
            "id_medico": ["M1"], "ano": [2020], "nu_prescricoes": [100],
            "qtd_dias_com_prescricao": [50], "qtd_meses_ativos": [6], "qtd_meses_alta_intensidade": [2],
        }
    ).lazy()
    month = pl.DataFrame(
        {
            "id_medico": ["M1", "M2", "M3"], "competencia": [202101, 202101, 202101],
            "nu_prescricoes_mes": [10, 20, 0], "qtd_dias_com_prescricao_mes": [2, 10, 0],
        }
    ).lazy()
    result = crm._agregar_ranking(month, date(2020, 1, 1), date(2021, 1, 31), year).sort("id_medico")
    assert result.select(["id_medico", "nu_prescricoes", "qtd_dias_com_prescricao", "qtd_meses_ativos", "qtd_meses_alta_intensidade"]).to_dicts() == [
        {"id_medico": "M1", "nu_prescricoes": 110, "qtd_dias_com_prescricao": 52, "qtd_meses_ativos": 7, "qtd_meses_alta_intensidade": 3},
        {"id_medico": "M2", "nu_prescricoes": 20, "qtd_dias_com_prescricao": 10, "qtd_meses_ativos": 1, "qtd_meses_alta_intensidade": 0},
    ]
    monkeypatch.setattr(crm, "_dividir_periodo_ranking", lambda *_: ([], []))
    with pytest.raises(HTTPException, match="Periodo sem meses com dados"):
        crm._agregar_ranking(month, date(2020, 1, 1), date(2021, 1, 31), year)


def test_search_crm_syntax_and_name_index_cache_and_errors(monkeypatch):
    assert crm._normalizar_busca_medico("  DRA. SÃO   JOSÉ ") == "dra. sao jose"
    assert crm._parse_busca_crm("800") == ("800", None)
    for term in ("crm 800", "800/sc", "800-sc", "800 sc", "sc/800", "crm-sc 800"):
        parsed = crm._parse_busca_crm(term)
        assert parsed is not None and parsed[0] == "800"
    assert crm._parse_busca_crm("800/XX") is None
    assert crm._parse_busca_crm("Joao Silva") is None
    doctors = pl.DataFrame(
        {"id_medico": ["800/SC", "800/SP", "801/SP"], "nu_crm": [800, 800, 801],
         "sg_uf": ["SC", "SP", "SP"], "no_medico": ["João Silva", "Maria Souza", "J. Silva"]}
    )
    monkeypatch.setattr(crm, "get_global_cache_signature", lambda _: ("sig", 1, 2))
    monkeypatch.setattr(crm, "get_dados_medico_df", lambda: doctors)
    monkeypatch.setattr(crm, "_CRM_MEDICO_NAME_INDEX", None)
    assert crm.ids_busca_medico(None) is None
    assert crm.ids_busca_medico("   ") is None
    assert crm.ids_busca_medico("crm 800/sc").to_list() == ["800/SC"]
    assert set(crm.ids_busca_medico("800").to_list()) == {"800/SC", "800/SP"}
    assert crm.ids_busca_medico("joao silva").to_list() == ["800/SC"]
    assert crm._get_medico_name_index(doctors, ("sig", 1, 2)).height == 3
    monkeypatch.setattr(crm, "get_global_cache_signature", lambda _: ("changed", 1, 3))
    monkeypatch.setattr(crm, "_CRM_MEDICO_NAME_INDEX", None)
    with pytest.raises(HTTPException, match="atualizado durante a busca"):
        crm._get_medico_name_index(doctors, ("sig", 1, 2))
    monkeypatch.setattr(crm, "get_dados_medico_df", lambda: (_ for _ in ()).throw(RuntimeError("offline")))
    with pytest.raises(HTTPException, match="indisponivel: offline"):
        crm.ids_busca_medico("joao")


def test_farmacia_counts_and_ranking_response_main_branches(monkeypatch):
    ranking = pl.DataFrame(
        {
            "id_medico": ["M1", "M2"], "taxa_prescricoes_dia": [5.0, 2.0], "nu_prescricoes": [50, 20],
            "qtd_dias_com_prescricao": [10, 10], "qtd_meses_ativos": [2, 1],
            "qtd_meses_alta_intensidade": [1, 0], "percentual_meses_alta_intensidade": [50.0, 0.0],
        }
    )
    doctors = pl.DataFrame(
        {"id_medico": ["M1"], "nu_crm": [123], "sg_uf": ["SP"], "no_medico": ["Ana"]}
    )
    counts = pl.DataFrame({"id_medico": ["M1", "M2"], "qtd_farmacias": [2, 1], "qtd_municipios": [1, 1]})
    monkeypatch.setattr(crm, "ids_busca_medico", lambda _: None)
    monkeypatch.setattr(crm, "get_dados_medico_df", lambda: doctors)
    monkeypatch.setattr(crm, "mais_medicos_por_id", lambda _: {})
    monkeypatch.setattr(crm, "farmacias_dos_medicos", lambda *args: counts)
    monkeypatch.setattr(crm, "farmacias_por_medico", lambda *args: counts)
    enriched = crm._com_farmacias(ranking, date(2024, 1, 1), date(2024, 1, 31), todos=False)
    assert enriched.get_column("qtd_farmacias").to_list() == [2, 1]
    assert crm._com_farmacias(ranking, date(2024, 1, 1), date(2024, 1, 31), todos=True).height == 2

    response = crm._montar_resposta_ranking(
        ranking, map_level="uf", escopo="Brasil", inicio=date(2024, 1, 1), fim=date(2024, 1, 31),
        page=1, page_size=2, medico_query=None, sort_field="taxa_prescricoes_dia", sort_order="desc",
        manager_map=None,
    )
    assert response.qtd_medicos == 2 and [row.id_medico for row in response.ranking] == ["M1", "M2"]
    assert response.ranking[0].localizado_cfm is True and response.ranking[1].localizado_cfm is False
    assert response.ranking[0].qtd_farmacias == 2

    # Medicos fixados: so os que tambem estao no recorte (M9 nao esta).
    pinned = crm._montar_resposta_ranking(
        ranking, map_level="uf", escopo="Brasil", inicio=date(2024, 1, 1), fim=date(2024, 1, 31),
        page=1, page_size=2, medico_query=None, sort_field="taxa_prescricoes_dia", sort_order="desc",
        manager_map=None, ids_fixados=["M2", "M9"],
    )
    assert pinned.qtd_medicos == 1 and [row.id_medico for row in pinned.ranking] == ["M2"]
    assert crm.ids_medicos_fixados(None) is None and crm.ids_medicos_fixados(" M1 , M2 ") == ["M1", "M2"]

    monkeypatch.setattr(crm, "ids_busca_medico", lambda _: pl.Series("id_medico", [], dtype=pl.String))
    no_matches = crm._montar_resposta_ranking(
        ranking, map_level="uf", escopo="Brasil", inicio=date(2024, 1, 1), fim=date(2024, 1, 31),
        page=1, page_size=2, medico_query="missing", sort_field="nu_prescricoes", sort_order="desc",
        manager_map=None,
    )
    assert no_matches.qtd_medicos == 0 and no_matches.ranking == []


def test_ranking_response_filtered_sort_requires_complete_counts(monkeypatch):
    ranking = pl.DataFrame(
        {"id_medico": ["M1"], "taxa_prescricoes_dia": [5.0], "nu_prescricoes": [50],
         "qtd_dias_com_prescricao": [10], "qtd_meses_ativos": [2], "qtd_meses_alta_intensidade": [1],
         "percentual_meses_alta_intensidade": [50.0]}
    )
    common = dict(
        map_level="uf", escopo="Brasil", inicio=date(2024, 1, 1), fim=date(2024, 1, 31), page=1,
        page_size=10, medico_query=None, sort_field="nu_prescricoes_farmacias_filtradas", sort_order="desc", manager_map=None,
    )
    with pytest.raises(HTTPException, match="exige filtro de farmacia ativo"):
        crm._montar_resposta_ranking(ranking, **common)

    monkeypatch.setattr(crm, "ids_busca_medico", lambda _: None)
    with pytest.raises(HTTPException, match="sem prescricoes nas farmacias filtradas"):
        crm._montar_resposta_ranking(ranking, prescricoes_filtradas_completas=lambda: pl.DataFrame(
            {"id_medico": ["M1"], "nu_prescricoes_farmacias_filtradas": [None]}, schema_overrides={"nu_prescricoes_farmacias_filtradas": pl.Int64}
        ), **common)
