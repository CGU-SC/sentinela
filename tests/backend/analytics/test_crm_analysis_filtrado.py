from datetime import date

import polars as pl
import pytest
from fastapi import HTTPException
from pyroaring import BitMap

from api.services.analytics import crm_analysis as base
from api.services.analytics import crm_analysis_filtrado as filtrado
from api.services.analytics.crm_filtros_medico import FiltrosMedico
from crm_indice_bitmaps import IndiceDesatualizado, chave_territorio


INICIO = date(2024, 1, 1)
FIM = date(2024, 1, 31)


class _MemoCache:
    def __init__(self):
        self.values = {}

    def obter(self, key, calculate):
        if key not in self.values:
            self.values[key] = calculate()
        return self.values[key]


class _Index:
    def __init__(self):
        self.by_pharmacy = {
            10: BitMap([1, 2]),
            20: BitMap([2, 3]),
            30: BitMap([4]),
        }
        self.high_intensity = {
            chave_territorio("uf", "SP"): BitMap([2]),
            chave_territorio("uf", "RJ"): BitMap([4]),
            chave_territorio("municipio", "100"): BitMap([1]),
            chave_territorio("municipio", "200"): BitMap([4]),
        }
        self.labels = {1: "M1", 2: "M2", 3: "M3", 4: "M4"}

    def uniao_farmacias(self, cnpjs, _anos, _meses):
        return BitMap().union(*(self.by_pharmacy.get(int(cnpj), BitMap()) for cnpj in cnpjs))

    def alta(self, territory, _anos, _meses):
        return self.high_intensity.get(territory, BitMap())

    def ids_medico(self, bitmap):
        return pl.Series("id_medico", [self.labels[value] for value in bitmap], dtype=pl.Utf8)


def _profile():
    return pl.DataFrame(
        {
            "id_cnpj": [10, 20, 30],
            "uf": ["SP", "SP", "RJ"],
            "id_regiao_saude": ["1", "1", "2"],
            "id_ibge7": [100, 100, 200],
        }
    )


def _install_index(monkeypatch, profile=None):
    monkeypatch.setattr(filtrado, "_CACHE", _MemoCache())
    monkeypatch.setattr(filtrado, "_indice", lambda: _Index())
    monkeypatch.setattr(base, "_dividir_periodo_ranking", lambda *_args: ([2024], [202401]))
    if profile is not None:
        monkeypatch.setattr(filtrado, "get_df_perfil_estabelecimento", lambda: profile)


def test_filter_keys_active_detection_and_geographic_recorte_normalization():
    neutral = {name: None for name in filtrado.FILTROS_FARMACIA}
    assert filtrado._chave_filtros({}) == tuple((name, None) for name in filtrado.FILTROS_FARMACIA)
    assert filtrado.filtro_farmacia_ativo(neutral) is False
    assert filtrado.filtro_farmacia_ativo({**neutral, "cnae_incompativel": False}) is False
    assert filtrado.filtro_farmacia_ativo({**neutral, "situacao_rf": "Ativa"}) is True
    assert filtrado.filtro_farmacia_ativo({**neutral, "val_min": 0}) is True
    assert filtrado._recorte("Todos", 5, 500) == (None, 5, 500)
    assert filtrado._recorte("SP", None, None) == ("SP", None, None)


def test_pharmacy_universe_uses_profile_or_shared_filtered_scope_and_validates_contract(
    monkeypatch,
):
    profile = _profile()
    _install_index(monkeypatch, profile)
    assert filtrado._farmacias({}, INICIO, FIM).sort("id_cnpj").to_dicts() == [
        {"id_cnpj": 10, "uf": "SP", "id_regiao_saude": "1", "id_municipio": "100"},
        {"id_cnpj": 20, "uf": "SP", "id_regiao_saude": "1", "id_municipio": "100"},
        {"id_cnpj": 30, "uf": "RJ", "id_regiao_saude": "2", "id_municipio": "200"},
    ]

    calls = []
    monkeypatch.setattr(
        filtrado,
        "get_indicador_scope_base_cached",
        lambda **kwargs: (calls.append(kwargs), profile)[1],
    )
    selected = filtrado._farmacias({"situacao_rf": "ATIVA"}, INICIO, FIM)
    assert selected.height == 3
    assert calls == [{"data_inicio": INICIO, "data_fim": FIM, "situacao_rf": "ATIVA"}]

    monkeypatch.setattr(
        filtrado,
        "get_df_perfil_estabelecimento",
        lambda: pl.DataFrame({"id_cnpj": [1], "uf": ["SP"]}),
    )
    monkeypatch.setattr(filtrado, "_CACHE", _MemoCache())
    with pytest.raises(HTTPException, match="Perfil dos estabelecimentos sem colunas"):
        filtrado._farmacias({}, INICIO, FIM)


def test_pharmacy_universe_rejects_missing_territory_values_and_filters_ids(monkeypatch):
    incomplete = pl.DataFrame(
        {
            "id_cnpj": [10], "uf": ["SP"], "id_regiao_saude": ["1"],
            "id_ibge7": [None],
        },
        schema_overrides={"id_ibge7": pl.Int64},
    )
    _install_index(monkeypatch, incomplete)
    with pytest.raises(HTTPException, match="sem UF, regiao ou municipio"):
        filtrado._farmacias({}, INICIO, FIM)

    pharmacies = pl.DataFrame(
        {
            "id_cnpj": [10, 20, 30], "uf": ["SP", "SP", "RJ"],
            "id_regiao_saude": ["1", "1", "2"], "id_municipio": ["100", "100", "200"],
        }
    )
    assert filtrado._cnpjs(pharmacies, "brasil", None) == [10, 20, 30]
    assert filtrado._cnpjs(pharmacies, "uf", "SP") == [10, 20]
    assert filtrado._cnpjs(pharmacies, "regiao_saude", "2") == [30]
    assert filtrado._cnpjs(pharmacies, "municipio", "200") == [30]


def test_index_staleness_becomes_service_unavailable(monkeypatch):
    monkeypatch.setattr(
        filtrado,
        "obter_indice",
        lambda: (_ for _ in ()).throw(IndiceDesatualizado("indice precisa ser reconstruido")),
    )

    with pytest.raises(HTTPException, match="indice precisa ser reconstruido") as error:
        filtrado._indice()

    assert error.value.status_code == 503


def test_medico_bitmap_filters_are_intersected_by_territory(monkeypatch):
    _install_index(monkeypatch)
    raw = {"SP": BitMap([1, 2]), "RJ": BitMap([2, 3])}
    monkeypatch.setattr(filtrado, "_medicos_farmacias_por_territorio", lambda *_args: raw)
    filters = FiltrosMedico(situacao_cfm="localizado")
    monkeypatch.setattr(filtrado, "medicos_filtrados", lambda *_args: BitMap([2, 4]))

    result = filtrado._medicos_por_territorio({}, filters, (None, None, None), "uf", INICIO, FIM)

    assert {territory: list(bitmap) for territory, bitmap in result.items()} == {
        "SP": [2], "RJ": [2]
    }
    assert filtrado._medicos_por_territorio(
        {}, FiltrosMedico(), (None, None, None), "uf", INICIO, FIM
    ) is raw


def test_territory_and_brazil_scopes_union_bitmaps_and_reject_missing_territory(monkeypatch):
    _install_index(monkeypatch)
    territories = {"SP": BitMap([1, 2]), "RJ": BitMap([3])}
    monkeypatch.setattr(filtrado, "_medicos_por_territorio", lambda *_args: territories)

    national = filtrado._medicos_escopo(
        {}, FiltrosMedico(), (None, None, None), "brasil", None, INICIO, FIM
    )
    assert list(national) == [1, 2, 3]
    assert list(
        filtrado._medicos_escopo(
            {}, FiltrosMedico(), (None, None, None), "uf", "SP", INICIO, FIM
        )
    ) == [1, 2]
    assert not filtrado._medicos_escopo(
        {}, FiltrosMedico(), (None, None, None), "uf", "XX", INICIO, FIM
    )
    with pytest.raises(ValueError, match="sem territorio"):
        filtrado._medicos_escopo(
            {}, FiltrosMedico(), (None, None, None), "municipio", None, INICIO, FIM
        )


def test_counts_include_only_active_doctors_and_intersect_high_intensity(monkeypatch):
    _install_index(monkeypatch)
    monkeypatch.setattr(
        filtrado,
        "_medicos_por_territorio",
        lambda *_args: {"SP": BitMap([1, 2, 3]), "RJ": BitMap([4]), "XX": BitMap()},
    )

    result = filtrado._contagens(
        {}, FiltrosMedico(), (None, None, None), "uf", INICIO, FIM
    ).sort("id_geografico")

    assert result.to_dicts() == [
        {"id_geografico": "RJ", "qtd_medicos_ativos": 1, "qtd_medicos_alta_intensidade": 1},
        {"id_geografico": "SP", "qtd_medicos_ativos": 3, "qtd_medicos_alta_intensidade": 1},
    ]


def test_filtered_map_builds_uf_and_municipality_summaries(monkeypatch):
    _install_index(monkeypatch, _profile())
    localities = pl.DataFrame(
        {
            "id_ibge7": [100, 200], "sg_uf": ["SP", "RJ"],
            "id_regiao_saude": ["1", "2"], "no_regiao_saude": ["Regiao Um", "Regiao Dois"],
            "no_municipio": ["Municipio Um", "Municipio Dois"],
        }
    )
    monkeypatch.setattr(filtrado, "get_localidades_df", lambda: localities)

    uf_items, uf_count, uf_reference = filtrado.mapa_filtrado(
        filtros={}, medicos=FiltrosMedico(), map_level="uf", inicio=INICIO, fim=FIM,
        uf="Todos", regiao_id=None, id_ibge7=None,
    )
    assert {item.identificador for item in uf_items} == {"SP", "RJ"}
    assert uf_count == 4
    assert uf_reference["percentual_referencia_brasil"] is not None

    sp_items, sp_count, _ = filtrado.mapa_filtrado(
        filtros={}, medicos=FiltrosMedico(), map_level="uf", inicio=INICIO, fim=FIM,
        uf="SP", regiao_id=None, id_ibge7=None,
    )
    assert [item.identificador for item in sp_items] == ["SP"]
    assert sp_count == 3

    municipal_items, count, reference = filtrado.mapa_filtrado(
        filtros={}, medicos=FiltrosMedico(), map_level="municipio", inicio=INICIO, fim=FIM,
        uf="SP", regiao_id=1, id_ibge7=100,
    )
    assert [item.identificador for item in municipal_items] == ["100"]
    assert count == 3
    assert reference["percentual_referencia_regiao"] is not None


def test_filtered_map_rejects_missing_localities_and_unscoped_geographic_map(monkeypatch):
    _install_index(monkeypatch, _profile())
    monkeypatch.setattr(
        filtrado,
        "get_localidades_df",
        lambda: pl.DataFrame({"id_ibge7": [100]}),
    )
    with pytest.raises(HTTPException, match="Localidades sem colunas obrigatorias"):
        filtrado.mapa_filtrado(
            filtros={}, medicos=FiltrosMedico(), map_level="municipio", inicio=INICIO,
            fim=FIM, uf="SP", regiao_id=None, id_ibge7=100,
        )

    monkeypatch.setattr(
        filtrado,
        "get_localidades_df",
        lambda: pl.DataFrame(
            {
                "id_ibge7": [100, 200], "sg_uf": ["SP", "RJ"],
                "id_regiao_saude": ["1", "2"],
                "no_regiao_saude": ["Regiao Um", "Regiao Dois"],
                "no_municipio": ["Municipio Um", "Municipio Dois"],
            }
        ),
    )
    with pytest.raises(HTTPException, match="exige UF"):
        filtrado.mapa_filtrado(
            filtros={}, medicos=FiltrosMedico(), map_level="municipio", inicio=INICIO,
            fim=FIM, uf="Todos", regiao_id=None, id_ibge7=None,
        )


def test_filtered_map_rejects_municipality_without_locality_record(monkeypatch):
    _install_index(monkeypatch, _profile())
    monkeypatch.setattr(
        filtrado,
        "get_localidades_df",
        lambda: pl.DataFrame(
            {
                "id_ibge7": [200], "sg_uf": ["RJ"], "id_regiao_saude": ["2"],
                "no_regiao_saude": ["Regiao Dois"], "no_municipio": ["Municipio Dois"],
            }
        ),
    )

    with pytest.raises(HTTPException, match="ausentes no cache de localidades"):
        filtrado.mapa_filtrado(
            filtros={}, medicos=FiltrosMedico(), map_level="municipio", inicio=INICIO,
            fim=FIM, uf="SP", regiao_id=None, id_ibge7=100,
        )


def test_filtered_ranking_exposes_filtered_prescription_callbacks_and_validates_index(
    monkeypatch,
):
    _install_index(monkeypatch, _profile())
    selected = BitMap([1, 2])
    monkeypatch.setattr(filtrado, "_medicos_escopo", lambda *_args: selected)
    monkeypatch.setattr(
        base,
        "ranking_agregado_escopo",
        lambda **_kwargs: pl.DataFrame(
            {"id_medico": ["M1", "M2", "M3"], "nu_prescricoes": [10, 20, 30]}
        ),
    )
    prescription_calls = []
    monkeypatch.setattr(
        filtrado,
        "_prescricoes_nas_farmacias",
        lambda ids, cnpjs, inicio, fim: (
            prescription_calls.append((ids, sorted(cnpjs), inicio, fim)),
            pl.DataFrame({"id_medico": ids, "nu_prescricoes_farmacias_filtradas": [5] * len(ids)}),
        )[1],
    )
    monkeypatch.setattr(
        filtrado,
        "get_indicador_scope_base_cached",
        lambda **_kwargs: _profile(),
    )
    filters = {"situacao_rf": "ATIVA"}

    aggregate, page_callback, full_callback = filtrado.ranking_filtrado(
        filtros=filters, medicos=FiltrosMedico(), inicio=INICIO, fim=FIM,
        uf="SP", regiao_id=None, id_ibge7=None,
    )
    assert aggregate.get_column("id_medico").to_list() == ["M1", "M2"]
    assert page_callback(["M1"]).get_column("nu_prescricoes_farmacias_filtradas").to_list() == [5]
    assert full_callback().height == 2
    assert full_callback().height == 2
    assert prescription_calls == [
        (["M1"], [10, 20], INICIO, FIM),
        (["M1", "M2"], [10, 20], INICIO, FIM),
    ]

    with pytest.raises(HTTPException, match="fora do ranking do escopo"):
        monkeypatch.setattr(filtrado, "_CACHE", _MemoCache())
        monkeypatch.setattr(filtrado, "_medicos_escopo", lambda *_args: BitMap([1, 2, 3, 4]))
        filtrado.ranking_filtrado(
            filtros={}, medicos=FiltrosMedico(), inicio=INICIO, fim=FIM,
            uf=None, regiao_id=None, id_ibge7=None,
        )


def test_unfiltered_ranking_has_no_filtered_pharmacy_callbacks(monkeypatch):
    _install_index(monkeypatch)
    monkeypatch.setattr(filtrado, "_medicos_escopo", lambda *_args: BitMap([1]))
    monkeypatch.setattr(
        base,
        "ranking_agregado_escopo",
        lambda **_kwargs: pl.DataFrame({"id_medico": ["M1"], "nu_prescricoes": [10]}),
    )

    ranking, page_callback, full_callback = filtrado.ranking_filtrado(
        filtros={}, medicos=FiltrosMedico(), inicio=INICIO, fim=FIM,
        uf=None, regiao_id=None, id_ibge7=None,
    )

    assert ranking.get_column("id_medico").to_list() == ["M1"]
    assert page_callback is None and full_callback is None


def test_filtered_ids_respect_geo_scope_and_reuse_the_index(monkeypatch):
    _install_index(monkeypatch, _profile())
    result = filtrado.ids_medicos_filtrados(
        filtros={}, medicos=FiltrosMedico(), inicio=INICIO, fim=FIM,
        uf="SP", regiao_id=None, id_ibge7=None,
    )

    assert result.name == "id_medico"
    assert result.to_list() == ["M1", "M2", "M3"]


def test_filtered_prescription_totals_join_annual_and_monthly_sources(monkeypatch):
    monkeypatch.setattr(base, "_dividir_periodo_ranking", lambda *_args: ([2023], [202401]))
    monkeypatch.setattr(
        filtrado,
        "scan_crm_medico_dim",
        lambda: pl.DataFrame({"id_medico": ["M1"], "id_medico_num": [1]}).lazy(),
    )
    monkeypatch.setattr(
        filtrado,
        "scan_crm_farmacia_medico_ano",
        lambda: pl.DataFrame(
            {"ano": [2023], "id_medico_num": [1], "id_cnpj": [10], "nu_prescricoes": [12]}
        ).lazy(),
    )
    monkeypatch.setattr(
        filtrado,
        "scan_crm_medico_estabelecimento_mes",
        lambda: pl.DataFrame(
            {"competencia": [202401], "id_medico": ["M1"], "id_cnpj": [10], "nu_prescricoes_mes": [3]}
        ).lazy(),
    )

    result = filtrado._prescricoes_nas_farmacias(["M1"], [10], INICIO, FIM)

    assert result.to_dicts() == [
        {"id_medico": "M1", "nu_prescricoes_farmacias_filtradas": 15}
    ]
