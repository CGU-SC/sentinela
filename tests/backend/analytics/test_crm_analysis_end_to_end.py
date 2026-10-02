from datetime import date

import polars as pl
import pytest
from fastapi import HTTPException

from api.services.analytics import crm_analysis as analysis
from api.services.analytics import crm_analysis_filtrado as filtered_analysis
from api.services.analytics.crm_filtros_medico import FiltrosMedico
from api.services.analytics.filtros_farmacia import FiltrosFarmacia


INICIO = date(2024, 1, 1)
FIM = date(2024, 1, 31)


def _manager_frame():
    return pl.DataFrame(
        {
            "nivel": ["municipio", "municipio", "regiao_saude", "regiao_saude", "uf"],
            "id_geografico": ["100", "200", "1", "2", "SP"],
            "competencia_inicio": [202401] * 5,
            "competencia_fim": [202401] * 5,
            "qtd_medicos_ativos": [40, 60, 40, 60, 100],
            "qtd_medicos_alta_intensidade": [8, 9, 8, 9, 17],
        }
    )


def _localities():
    return pl.DataFrame(
        {
            "id_ibge7": [100, 200],
            "sg_uf": ["SP", "SP"],
            "id_regiao_saude": ["1", "2"],
            "no_regiao_saude": ["Regiao Um", "Regiao Dois"],
            "no_municipio": ["Municipio Um", "Municipio Dois"],
        }
    )


def _install_manager(monkeypatch, manager=None, localities=None):
    manager = _manager_frame() if manager is None else manager
    localities = _localities() if localities is None else localities
    monkeypatch.setattr(analysis, "scan_crm_mapa_municipio_regiao_periodo", lambda: manager.lazy())
    monkeypatch.setattr(analysis, "get_localidades_df", lambda: localities)


def test_geographic_manager_map_builds_municipality_region_and_reference_metrics(monkeypatch):
    _install_manager(monkeypatch)
    items, count, references = analysis._build_manager_map(
        map_level="municipio", inicio=INICIO, fim=FIM, uf="SP", regiao_id=1, id_ibge7=100,
    )
    assert count == 40
    assert len(items) == 1
    assert items[0].identificador == "100"
    assert items[0].nome == "Municipio Um"
    assert items[0].percentual_alta_intensidade == 20.0
    assert items[0].percentual_referencia_regiao == 20.0
    assert references == {
        "percentual_referencia_brasil": 17.0,
        "percentual_referencia_uf": 17.0,
        "percentual_referencia_regiao": 20.0,
    }


def _national_uf_frame():
    rows = [{"nivel": "brasil", "id_geografico": "BR", "qtd_medicos_ativos": 1000, "qtd_medicos_alta_intensidade": 200}]
    rows.extend(
        {"nivel": "uf", "id_geografico": uf, "qtd_medicos_ativos": 100, "qtd_medicos_alta_intensidade": 20}
        for uf in sorted(analysis._UFS_CRM)
    )
    return pl.DataFrame(rows).with_columns(
        pl.lit(202401).alias("competencia_inicio"), pl.lit(202401).alias("competencia_fim")
    )


def test_manager_map_supports_region_and_national_uf_scopes(monkeypatch):
    _install_manager(monkeypatch)
    region_items, region_count, _ = analysis._build_manager_map(
        map_level="regiao", inicio=INICIO, fim=FIM, uf="SP", regiao_id=1, id_ibge7=None,
    )
    assert region_count == 40
    assert [item.identificador for item in region_items] == ["100"]

    monkeypatch.setattr(analysis, "scan_crm_mapa_uf_periodo", lambda: _national_uf_frame().lazy())
    uf_items, uf_count, references = analysis._build_manager_map(
        map_level="uf", inicio=INICIO, fim=FIM, uf="SP", regiao_id=None, id_ibge7=None,
    )
    assert uf_count == 100
    assert [item.identificador for item in uf_items] == ["SP"]
    assert references["percentual_referencia_brasil"] == 20.0


def test_municipality_map_for_uf_uses_national_uf_count(monkeypatch):
    _install_manager(monkeypatch)
    monkeypatch.setattr(analysis, "_read_uf_brasil_period", lambda *_: (
        pl.DataFrame({
            "nivel": ["uf"], "id_geografico": ["SP"],
            "qtd_medicos_ativos": [100], "qtd_medicos_alta_intensidade": [20],
        }),
        pl.DataFrame({
            "nivel": ["brasil"], "id_geografico": ["BR"],
            "qtd_medicos_ativos": [1000], "qtd_medicos_alta_intensidade": [200],
        }),
    ))
    items, count, references = analysis._build_manager_map(
        map_level="municipio", inicio=INICIO, fim=FIM, uf="SP", regiao_id=None, id_ibge7=None,
    )
    assert count == 100
    assert {item.identificador for item in items} == {"100", "200"}
    assert references["percentual_referencia_uf"] == 17.0


def test_municipality_map_rejects_uf_missing_from_national_reference(monkeypatch):
    _install_manager(monkeypatch)
    monkeypatch.setattr(analysis, "_read_uf_brasil_period", lambda *_: (
        pl.DataFrame(schema={
            "nivel": pl.Utf8, "id_geografico": pl.Utf8,
            "qtd_medicos_ativos": pl.Int64, "qtd_medicos_alta_intensidade": pl.Int64,
        }),
        pl.DataFrame(),
    ))
    with pytest.raises(HTTPException, match="Cache do mapa Brasil sem a UF SP") as error:
        analysis._build_manager_map(
            map_level="municipio", inicio=INICIO, fim=FIM, uf="SP", regiao_id=None, id_ibge7=None,
        )
    assert error.value.status_code == 503


def test_geographic_manager_map_reports_missing_requested_region(monkeypatch):
    manager = _manager_frame().filter(~((pl.col("nivel") == "regiao_saude") & (pl.col("id_geografico") == "1")))
    _install_manager(monkeypatch, manager=manager)
    with pytest.raises(HTTPException, match="territorio regiao_saude/1") as error:
        analysis._build_manager_map(
            map_level="regiao", inicio=INICIO, fim=FIM, uf="SP", regiao_id=1, id_ibge7=None,
        )
    assert error.value.status_code == 503


def test_national_manager_map_requires_expected_territory_rows(monkeypatch):
    rows = _national_uf_frame().with_columns(
        pl.when(pl.col("nivel") == "brasil").then(pl.lit("uf")).otherwise(pl.col("nivel")).alias("nivel"),
        pl.when(pl.col("id_geografico") == "BR").then(pl.lit("ZZ")).otherwise(pl.col("id_geografico")).alias("id_geografico"),
    )
    monkeypatch.setattr(analysis, "scan_crm_mapa_uf_periodo", lambda: rows.lazy())
    with pytest.raises(HTTPException, match="territorios ausentes ou duplicados") as error:
        analysis._read_uf_brasil_period(INICIO, FIM)
    assert error.value.status_code == 503


@pytest.mark.parametrize(
    ("manager_factory", "locality_factory", "scope", "message"),
    [
        (lambda: pl.DataFrame({"unrelated": [1]}), _localities, {"uf": "SP", "regiao_id": 1, "id_ibge7": 100}, "sem colunas obrigatorias"),
        (lambda: _manager_frame().filter(pl.col("competencia_inicio") == 202402), _localities, {"uf": "SP", "regiao_id": 1, "id_ibge7": 100}, "sem o periodo solicitado"),
        (lambda: _manager_frame().with_columns(pl.when(pl.col("id_geografico") == "100").then(-1).otherwise(pl.col("qtd_medicos_ativos")).alias("qtd_medicos_ativos")), _localities, {"uf": "SP", "regiao_id": 1, "id_ibge7": 100}, "contagens invalidas"),
        (lambda: pl.concat([_manager_frame(), _manager_frame().head(1)]), _localities, {"uf": "SP", "regiao_id": 1, "id_ibge7": 100}, "territorios duplicados"),
        (_manager_frame, _localities, {"uf": None, "regiao_id": None, "id_ibge7": None}, "exige UF"),
        (lambda: _manager_frame().filter(pl.col("nivel") != "municipio"), _localities, {"uf": "SP", "regiao_id": 1, "id_ibge7": 100}, "sem municipios no periodo"),
        (_manager_frame, lambda: pl.DataFrame({"id_ibge7": [100]}), {"uf": "SP", "regiao_id": 1, "id_ibge7": 100}, "Localidades sem colunas obrigatorias"),
        (_manager_frame, lambda: _localities().with_columns(pl.lit(None, dtype=pl.Int64).alias("id_ibge7")), {"uf": "SP", "regiao_id": 1, "id_ibge7": 100}, "id_ibge7 nulo"),
        (_manager_frame, lambda: pl.concat([_localities(), _localities().head(1)]), {"uf": "SP", "regiao_id": 1, "id_ibge7": 100}, "mais de uma linha"),
        (_manager_frame, lambda: _localities().filter(pl.col("id_ibge7") == 200), {"uf": "SP", "regiao_id": 1, "id_ibge7": 100}, "municipios ausentes no cache de localidades"),
    ],
)
def test_geographic_manager_map_rejects_inconsistent_materialized_inputs(
    monkeypatch, manager_factory, locality_factory, scope, message
):
    _install_manager(monkeypatch, manager_factory(), locality_factory())
    with pytest.raises(HTTPException, match=message) as error:
        analysis._build_manager_map(map_level="municipio", inicio=INICIO, fim=FIM, **scope)
    assert error.value.status_code in {422, 503}


def test_manager_map_requires_a_real_geographic_scope(monkeypatch):
    _install_manager(monkeypatch)
    with pytest.raises(HTTPException, match="exige UF") as error:
        analysis._build_manager_map(
            map_level="regiao", inicio=INICIO, fim=FIM,
            uf=None, regiao_id=None, id_ibge7=None,
        )
    assert error.value.status_code == 422


def test_get_crm_analysis_returns_paged_ranking_without_map(monkeypatch):
    ranking = pl.DataFrame(
        {
            "id_medico": ["1/SP"], "taxa_prescricoes_dia": [5.0], "nu_prescricoes": [50],
            "qtd_dias_com_prescricao": [10], "qtd_meses_ativos": [2],
            "qtd_meses_alta_intensidade": [1], "percentual_meses_alta_intensidade": [50.0],
        }
    )
    doctors = pl.DataFrame({"id_medico": ["1/SP"], "nu_crm": [1], "sg_uf": ["SP"], "no_medico": ["Ana" ]})
    counts = pl.DataFrame({"id_medico": ["1/SP"], "qtd_farmacias": [2], "qtd_municipios": [1]})
    monkeypatch.setattr(analysis, "ranking_agregado_escopo", lambda **kwargs: ranking)
    monkeypatch.setattr(analysis, "ids_busca_medico", lambda query: None)
    monkeypatch.setattr(analysis, "get_dados_medico_df", lambda: doctors)
    monkeypatch.setattr(analysis, "farmacias_dos_medicos", lambda *args: counts)

    result = analysis.get_crm_prescricoes_analise(
        include_map=False, data_inicio=INICIO, data_fim=FIM, page=1, page_size=10,
    )
    assert result.qtd_medicos == 1
    assert result.escopo == "Brasil"
    assert result.mapa == []
    assert result.ranking[0].id_medico == "1/SP"
    assert result.ranking[0].localizado_cfm is True
    assert result.ranking[0].qtd_farmacias == 2


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"page": 0}, "page deve ser maior"),
        ({"page_size": 0}, "page_size deve estar"),
        ({"page_size": 101}, "page_size deve estar"),
        ({"sort_field": "bad"}, "Coluna de ordenacao invalida"),
        ({"sort_order": "up"}, "sort_order deve ser"),
        ({"map_level": "estado"}, "map_level deve ser"),
        ({"map_level": "municipio", "uf": "Todos"}, "mapa municipal exige"),
        ({"map_level": "regiao"}, "mapa da região exige regiao_id"),
    ],
)
def test_get_crm_analysis_validates_pagination_sorting_and_map_scope(kwargs, message):
    with pytest.raises(HTTPException, match=message) as error:
        analysis.get_crm_prescricoes_analise(**kwargs)
    assert error.value.status_code == 422


def test_get_crm_analysis_map_only_uses_map_and_period_thresholds(monkeypatch):
    mapa = []
    reference = {"percentual_referencia_brasil": 10.0, "percentual_referencia_uf": 8.0}
    monkeypatch.setattr(analysis, "_build_manager_map", lambda **kwargs: (mapa, 25, reference))
    monkeypatch.setattr(analysis, "_limiares_do_periodo", lambda *_: pl.DataFrame({"p95_taxa_dia": [2.0, 5.0]}))
    response = analysis.get_crm_prescricoes_analise(map_only=True, uf="SP", data_inicio=INICIO, data_fim=FIM)
    assert response.qtd_medicos == 25
    assert response.ranking == []
    assert response.percentual_referencia_brasil == 10.0
    assert response.limiar_p95_min == 2.0
    assert response.limiar_p95_max == 5.0


def test_get_crm_analysis_converts_unexpected_map_cache_errors_to_service_unavailable(monkeypatch):
    monkeypatch.setattr(analysis, "_build_manager_map", lambda **kwargs: (_ for _ in ()).throw(RuntimeError("offline")))
    with pytest.raises(HTTPException, match="Cache gerencial de prescricoes indisponivel: offline") as error:
        analysis.get_crm_prescricoes_analise()
    assert error.value.status_code == 503


def _monthly_rows(*, territorial=False):
    values = {
        "id_medico": ["1/SP", "2/SP"],
        "competencia": [202401, 202402],
        "nu_prescricoes_mes": [10, 20],
        "qtd_dias_com_prescricao_mes": [2, 4],
    }
    if territorial:
        values["nivel"] = ["uf", "uf"]
        values["id_geografico"] = ["SP", "RJ"]
    return pl.DataFrame(values)


def _year_rows(*, territorial=False):
    values = {
        "id_medico": ["1/SP"], "ano": [2024], "nu_prescricoes": [100],
        "qtd_dias_com_prescricao": [50], "qtd_meses_ativos": [6],
        "qtd_meses_alta_intensidade": [2],
    }
    if territorial:
        values["nivel"] = ["uf"]
        values["id_geografico"] = ["SP"]
    return pl.DataFrame(values)


def test_scope_ranking_uses_generation_cache_and_materialized_national_sources(monkeypatch):
    cached = pl.DataFrame({"id_medico": ["cached"]})
    monkeypatch.setattr(analysis, "_ranking_cache_key", lambda **kwargs: ("national",))
    monkeypatch.setattr(analysis, "_get_cached_ranking", lambda key: None)
    monkeypatch.setattr(analysis, "scan_crm_medico_brasil_mes", lambda: _monthly_rows().lazy())
    monkeypatch.setattr(analysis, "scan_crm_medico_brasil_ano", lambda: _year_rows().lazy())
    monkeypatch.setattr(analysis, "_require_columns", lambda *args: None)
    captured = {}

    def aggregate(monthly, inicio, fim, yearly):
        captured["monthly"] = monthly.collect()
        captured["yearly"] = yearly.collect()
        captured["period"] = (inicio, fim)
        return cached

    monkeypatch.setattr(analysis, "_agregar_ranking", aggregate)
    writes = []
    monkeypatch.setattr(analysis, "_cache_ranking", lambda key, result: writes.append((key, result)))
    result = analysis.ranking_agregado_escopo(
        inicio=INICIO, fim=FIM, uf=None, regiao_id=None, id_ibge7=None,
    )
    assert result is cached
    assert captured["monthly"].get_column("competencia").to_list() == [202401]
    assert captured["period"] == (INICIO, FIM)
    assert writes == [(("national",), cached)]

    monkeypatch.setattr(analysis, "_get_cached_ranking", lambda key: cached)
    monkeypatch.setattr(analysis, "scan_crm_medico_brasil_mes", lambda: pytest.fail("deve usar cache"))
    assert analysis.ranking_agregado_escopo(
        inicio=INICIO, fim=FIM, uf=None, regiao_id=None, id_ibge7=None,
    ) is cached


def test_scope_ranking_filters_territorial_sources_by_requested_uf(monkeypatch):
    monkeypatch.setattr(analysis, "_ranking_cache_key", lambda **kwargs: ("regional", kwargs["uf"]))
    monkeypatch.setattr(analysis, "_get_cached_ranking", lambda key: None)
    monkeypatch.setattr(analysis, "scan_crm_medico_territorio_mes", lambda: _monthly_rows(territorial=True).lazy())
    monkeypatch.setattr(analysis, "scan_crm_medico_territorio_ano", lambda: _year_rows(territorial=True).lazy())
    monkeypatch.setattr(analysis, "_require_columns", lambda *args: None)
    captured = {}

    def aggregate(monthly, inicio, fim, yearly):
        captured["monthly"] = monthly.collect()
        captured["yearly"] = yearly.collect()
        return pl.DataFrame({"id_medico": ["1/SP"]})

    monkeypatch.setattr(analysis, "_agregar_ranking", aggregate)
    monkeypatch.setattr(analysis, "_cache_ranking", lambda *args: None)
    result = analysis.ranking_agregado_escopo(
        inicio=INICIO, fim=FIM, uf="SP", regiao_id=None, id_ibge7=None,
    )
    assert result.get_column("id_medico").to_list() == ["1/SP"]
    assert captured["monthly"].get_column("id_medico").to_list() == ["1/SP"]
    assert captured["yearly"].get_column("id_medico").to_list() == ["1/SP"]


@pytest.mark.parametrize("http_error", [False, True])
def test_scope_ranking_reports_scan_errors_without_hiding_http_errors(monkeypatch, http_error):
    monkeypatch.setattr(analysis, "_ranking_cache_key", lambda **kwargs: ("scan-error",))
    monkeypatch.setattr(analysis, "_get_cached_ranking", lambda _: None)

    def fail():
        if http_error:
            raise HTTPException(status_code=409, detail="cache lock")
        raise RuntimeError("offline")

    monkeypatch.setattr(analysis, "scan_crm_medico_brasil_mes", fail)
    with pytest.raises(HTTPException) as error:
        analysis.ranking_agregado_escopo(
            inicio=INICIO, fim=FIM, uf=None, regiao_id=None, id_ibge7=None,
        )
    assert error.value.status_code == (409 if http_error else 503)
    assert ("cache lock" if http_error else "offline") in error.value.detail


def test_crm_name_index_reuses_the_current_cache_entry(monkeypatch):
    signature = ("fresh", 2, 3)
    cached = pl.DataFrame({"id_medico": ["1/SP"], "nome_busca": ["ana"]})
    monkeypatch.setattr(analysis, "_CRM_MEDICO_NAME_INDEX", (signature, cached))
    monkeypatch.setattr(analysis, "get_global_cache_signature", lambda *_: pytest.fail("cached index should return directly"))
    assert analysis._get_medico_name_index(pl.DataFrame(), signature) is cached


def test_crm_name_index_rechecks_cache_after_entering_lock(monkeypatch):
    signature = ("fresh", 2, 3)
    cached = pl.DataFrame({"id_medico": ["1/SP"], "nome_busca": ["ana"]})

    class CachePopulatedUnderLock:
        def __enter__(self):
            monkeypatch.setattr(analysis, "_CRM_MEDICO_NAME_INDEX", (signature, cached))

        def __exit__(self, *_args):
            return False

    monkeypatch.setattr(analysis, "_CRM_MEDICO_NAME_INDEX", None)
    monkeypatch.setattr(analysis, "_CRM_MEDICO_NAME_INDEX_LOCK", CachePopulatedUnderLock())
    assert analysis._get_medico_name_index(pl.DataFrame(), signature) is cached


def test_search_rejects_lowercase_unknown_state_and_mid_query_cache_changes(monkeypatch):
    assert analysis._parse_busca_crm("800/xx") is None
    doctors = pl.DataFrame(
        {"id_medico": ["800/SC"], "nu_crm": [800], "sg_uf": ["SC"], "no_medico": ["Ana Silva"]}
    )
    signatures = iter([("old", 1, 1), ("new", 1, 2)])
    monkeypatch.setattr(analysis, "get_global_cache_signature", lambda *_: next(signatures))
    monkeypatch.setattr(analysis, "get_dados_medico_df", lambda: doctors)
    with pytest.raises(HTTPException, match="atualizado durante a busca") as error:
        analysis.ids_busca_medico("Ana")
    assert error.value.status_code == 503


def test_farmacia_count_join_fails_when_ranking_and_count_modules_diverge(monkeypatch):
    ranking = pl.DataFrame({"id_medico": ["1/SP"]})
    monkeypatch.setattr(analysis, "farmacias_dos_medicos", lambda *args: pl.DataFrame(
        {"id_medico": ["another"], "qtd_farmacias": [1], "qtd_municipios": [1]}
    ))
    with pytest.raises(HTTPException, match="sem farmacias no modulo medico x farmacia") as error:
        analysis._com_farmacias(ranking, INICIO, FIM, todos=False)
    assert error.value.status_code == 503


def _ranking_frame():
    return pl.DataFrame(
        {
            "id_medico": ["1/SP", "2/SP"], "taxa_prescricoes_dia": [5.0, 2.0],
            "nu_prescricoes": [50, 20], "qtd_dias_com_prescricao": [10, 10],
            "qtd_meses_ativos": [2, 1], "qtd_meses_alta_intensidade": [1, 0],
            "percentual_meses_alta_intensidade": [50.0, 0.0],
        }
    )


def _doctor_frame():
    return pl.DataFrame(
        {"id_medico": ["1/SP"], "nu_crm": [1], "sg_uf": ["SP"], "no_medico": ["Ana"]}
    )


def _pharmacy_counts():
    return pl.DataFrame(
        {"id_medico": ["1/SP", "2/SP"], "qtd_farmacias": [2, 1], "qtd_municipios": [1, 1]}
    )


def _ranking_kwargs(**overrides):
    return {
        "map_level": "uf", "escopo": "Brasil", "inicio": INICIO, "fim": FIM,
        "page": 1, "page_size": 2, "medico_query": None,
        "sort_field": "taxa_prescricoes_dia", "sort_order": "desc", "manager_map": None,
        **overrides,
    }


def test_ranking_response_sorts_by_all_medicinal_counts_and_name(monkeypatch):
    ranking = _ranking_frame()
    monkeypatch.setattr(analysis, "ids_busca_medico", lambda _: None)
    monkeypatch.setattr(analysis, "get_dados_medico_df", lambda: _doctor_frame())
    monkeypatch.setattr(analysis, "farmacias_dos_medicos", lambda *args: _pharmacy_counts())
    monkeypatch.setattr(analysis, "farmacias_por_medico", lambda *args: _pharmacy_counts())

    by_pharmacies = analysis._montar_resposta_ranking(
        ranking, **_ranking_kwargs(sort_field="qtd_farmacias", sort_order="asc")
    )
    assert [item.id_medico for item in by_pharmacies.ranking] == ["2/SP", "1/SP"]

    by_name = analysis._montar_resposta_ranking(
        ranking, **_ranking_kwargs(sort_field="no_medico", sort_order="asc")
    )
    assert by_name.ranking[0].id_medico == "1/SP"
    assert by_name.ranking[0].no_medico == "Ana"


def test_ranking_response_returns_empty_when_page_offset_exceeds_population(monkeypatch):
    monkeypatch.setattr(analysis, "ids_busca_medico", lambda _: None)
    result = analysis._montar_resposta_ranking(
        _ranking_frame(), **_ranking_kwargs(page=5, page_size=2)
    )
    assert result.qtd_medicos == 2
    assert result.ranking == []


def test_filtered_sort_and_filtered_page_values_are_joined_and_percentages_calculated(monkeypatch):
    monkeypatch.setattr(analysis, "ids_busca_medico", lambda _: None)
    monkeypatch.setattr(analysis, "get_dados_medico_df", lambda: _doctor_frame())
    monkeypatch.setattr(analysis, "farmacias_dos_medicos", lambda *args: _pharmacy_counts())
    complete = lambda: pl.DataFrame(
        {"id_medico": ["1/SP", "2/SP"], "nu_prescricoes_farmacias_filtradas": [25, 10]}
    )
    ordered = analysis._montar_resposta_ranking(
        _ranking_frame(), **_ranking_kwargs(
            sort_field="nu_prescricoes_farmacias_filtradas",
            prescricoes_filtradas_completas=complete,
            prescricoes_filtradas=lambda ids: pl.DataFrame(
                {"id_medico": ids, "nu_prescricoes_farmacias_filtradas": [25 for _ in ids]}
            ),
        )
    )
    assert ordered.ranking[0].nu_prescricoes_farmacias_filtradas == 25
    assert ordered.ranking[0].percentual_prescricoes_farmacias_filtradas == 50.0

    monkeypatch.setattr(analysis, "ids_busca_medico", lambda _: None)
    page = analysis._montar_resposta_ranking(
        _ranking_frame(), **_ranking_kwargs(
            prescricoes_filtradas=lambda ids: pl.DataFrame(
                {"id_medico": ids, "nu_prescricoes_farmacias_filtradas": [20 for _ in ids]}
            ),
        )
    )
    assert page.ranking[0].nu_prescricoes_farmacias_filtradas == 20
    assert page.ranking[0].percentual_prescricoes_farmacias_filtradas == 40.0


def test_ranking_response_requires_counts_for_every_filtered_page_doctor(monkeypatch):
    monkeypatch.setattr(analysis, "ids_busca_medico", lambda _: None)
    monkeypatch.setattr(analysis, "get_dados_medico_df", lambda: _doctor_frame())
    monkeypatch.setattr(analysis, "farmacias_dos_medicos", lambda *args: _pharmacy_counts())
    missing = lambda ids: pl.DataFrame(
        {"id_medico": ["not-in-ranking"], "nu_prescricoes_farmacias_filtradas": [10]}
    )
    with pytest.raises(HTTPException, match="indice CRM inconsistente") as error:
        analysis._montar_resposta_ranking(
            _ranking_frame(), **_ranking_kwargs(prescricoes_filtradas=missing)
        )
    assert error.value.status_code == 503


@pytest.mark.parametrize("sort", ["qtd_farmacias", "no_medico", "ranking_page"])
def test_ranking_response_reports_missing_medico_cache_and_filter_counts(monkeypatch, sort):
    monkeypatch.setattr(analysis, "ids_busca_medico", lambda _: None)
    monkeypatch.setattr(analysis, "farmacias_por_medico", lambda *args: _pharmacy_counts())
    monkeypatch.setattr(analysis, "farmacias_dos_medicos", lambda *args: _pharmacy_counts())
    monkeypatch.setattr(analysis, "get_dados_medico_df", lambda: (_ for _ in ()).throw(RuntimeError("offline")))
    if sort == "ranking_page":
        # The cache read happens after pagination for a normal sort.
        sort_field = "taxa_prescricoes_dia"
        common = _ranking_kwargs(page=1, sort_field=sort_field)
    else:
        common = _ranking_kwargs(sort_field=sort)
    with pytest.raises(HTTPException, match="Cache de dados dos medicos indisponivel: offline") as error:
        analysis._montar_resposta_ranking(_ranking_frame(), **common)
    assert error.value.status_code == 503


def test_get_crm_analysis_uses_filtered_map_and_ranking_service(monkeypatch):
    calls = []
    marker = object()
    monkeypatch.setattr(filtered_analysis, "mapa_filtrado", lambda **kwargs: ([], 1, {}))
    monkeypatch.setattr(
        filtered_analysis,
        "ranking_filtrado",
        lambda **kwargs: (_ranking_frame(), lambda ids: None, lambda: None),
    )
    monkeypatch.setattr(analysis, "_montar_resposta_ranking", lambda *args, **kwargs: calls.append(kwargs) or marker)
    response = analysis.get_crm_prescricoes_analise(
        filtros_medico=FiltrosMedico(taxa_dia_min=2),
        filtros=FiltrosFarmacia(),
        data_inicio=INICIO,
        data_fim=FIM,
    )
    assert response is marker
    assert calls[0]["filtro_medicos_ativo"] is True


def test_get_crm_analysis_translates_filtered_ranking_and_aggregate_failures(monkeypatch):
    monkeypatch.setattr(filtered_analysis, "mapa_filtrado", lambda **kwargs: ([], 1, {}))
    monkeypatch.setattr(filtered_analysis, "ranking_filtrado", lambda **kwargs: (_ for _ in ()).throw(RuntimeError("bitmap unavailable")))
    with pytest.raises(HTTPException, match="Indice CRM de farmacias/medicos indisponivel") as filtered_error:
        analysis.get_crm_prescricoes_analise(filtros_medico=FiltrosMedico(taxa_dia_min=2))
    assert filtered_error.value.status_code == 503

    monkeypatch.setattr(analysis, "ranking_agregado_escopo", lambda **kwargs: (_ for _ in ()).throw(RuntimeError("parquet unavailable")))
    with pytest.raises(HTTPException, match="Cache de prescricoes por medico") as aggregate_error:
        analysis.get_crm_prescricoes_analise(include_map=False)
    assert aggregate_error.value.status_code == 503


def test_get_crm_analysis_preserves_filtered_index_http_errors(monkeypatch):
    monkeypatch.setattr(filtered_analysis, "ranking_filtrado", lambda **kwargs: (_ for _ in ()).throw(HTTPException(409, "index conflict")))
    with pytest.raises(HTTPException, match="index conflict") as error:
        analysis.get_crm_prescricoes_analise(
            filtros_medico=FiltrosMedico(taxa_dia_min=2), include_map=False,
        )
    assert error.value.status_code == 409


def test_get_crm_analysis_rejects_invalid_filtered_pagination(monkeypatch):
    monkeypatch.setattr(filtered_analysis, "mapa_filtrado", lambda **kwargs: ([], 0, {}))
    with pytest.raises(HTTPException, match="page deve ser maior ou igual a 1") as error:
        analysis.get_crm_prescricoes_analise(
            filtros_medico=FiltrosMedico(taxa_dia_min=2),
            include_map=False,
            page=0,
        )
    assert error.value.status_code == 422


def test_get_crm_analysis_preserves_http_errors_from_map_and_ranking_sources(monkeypatch):
    monkeypatch.setattr(analysis, "_build_manager_map", lambda **kwargs: (_ for _ in ()).throw(HTTPException(409, "map conflict")))
    with pytest.raises(HTTPException, match="map conflict") as map_error:
        analysis.get_crm_prescricoes_analise()
    assert map_error.value.status_code == 409

    monkeypatch.setattr(analysis, "_build_manager_map", lambda **kwargs: ([], 0, {}))
    monkeypatch.setattr(analysis, "ranking_agregado_escopo", lambda **kwargs: (_ for _ in ()).throw(HTTPException(409, "rank conflict")))
    with pytest.raises(HTTPException, match="rank conflict") as rank_error:
        analysis.get_crm_prescricoes_analise()
    assert rank_error.value.status_code == 409
