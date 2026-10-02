import json
from pathlib import Path

import polars as pl
import pytest
from pyroaring import BitMap

import data_cache as dc
from backend import crm_indice_bitmaps as index


def _sources():
    dim = pl.DataFrame(
        {"id_medico": ["A/SP", "B/RJ"], "id_medico_num": [0, 1]},
        schema_overrides={"id_medico_num": pl.Int32},
    )
    limiar = pl.DataFrame(
        {"competencia": [202401, 202402], "p95_taxa_dia": [2.0, 2.0]},
        schema_overrides={"competencia": pl.Int32},
    )
    farmacia_ano = pl.DataFrame(
        {"ano": [2024, 2024], "id_cnpj": [10, 20], "id_medico_num": [0, 1]},
        schema_overrides={"ano": pl.Int32, "id_cnpj": pl.Int32, "id_medico_num": pl.Int32},
    )
    territorio_ano = pl.DataFrame(
        {
            "ano": [2024], "nivel": ["uf"], "id_geografico": ["SP"],
            "qtd_meses_alta_intensidade": [1], "id_medico": ["A/SP"],
        }
    )
    farmacia_mes = pl.DataFrame(
        {
            "competencia": [202401, 202401, 202402],
            "id_cnpj": [10, 20, 20],
            "id_medico": ["A/SP", "B/RJ", "A/SP"],
        },
        schema_overrides={"competencia": pl.Int32, "id_cnpj": pl.Int32},
    )
    territorio_mes = pl.DataFrame(
        {
            "competencia": [202401, 202401, 202402],
            "nivel": ["uf", "uf", "municipio"],
            "id_geografico": ["SP", "SP", "3550308"],
            "nu_prescricoes_mes": [15, 10, 21],
            "qtd_dias_com_prescricao_mes": [5, 5, 7],
            "id_medico": ["A/SP", "B/RJ", "B/RJ"],
        },
        schema_overrides={"competencia": pl.Int32},
    )
    return dim, limiar, farmacia_ano, territorio_ano, farmacia_mes, territorio_mes


def _install_sources(monkeypatch, destination):
    dim, limiar, farmacia_ano, territorio_ano, farmacia_mes, territorio_mes = _sources()
    sources = {
        "scan_crm_medico_dim": dim,
        "scan_crm_limiar_p95_mes": limiar,
        "scan_crm_farmacia_medico_ano": farmacia_ano,
        "scan_crm_medico_territorio_ano": territorio_ano,
        "scan_crm_medico_estabelecimento_mes": farmacia_mes,
        "scan_crm_medico_territorio_mes": territorio_mes,
    }
    for name, frame in sources.items():
        monkeypatch.setattr(dc, name, lambda frame=frame: frame.lazy())
    monkeypatch.setattr(dc, "get_global_cache_signature", lambda name: (name, 123, 456))
    monkeypatch.setattr(dc, "_CRM_INDICE_BITMAPS_PATH", str(destination), raising=False)
    return dim


def test_serialization_and_dimension_join_enforce_complete_index_source():
    empty = index._serializar_grupos(pl.DataFrame(), "key", "value")
    assert empty.schema == {"chave": pl.Utf8, "bitmap": pl.Binary}
    assert empty.is_empty()

    groups = index._serializar_grupos(
        pl.DataFrame({"cnpj": [2, 1, 1, 2], "medico": [3, 2, 1, 0]}), "cnpj", "medico"
    )
    assert groups.get_column("chave").to_list() == ["1", "2"]
    assert [list(index.FrozenBitMap.deserialize(value)) for value in groups["bitmap"]] == [[1, 2], [0, 3]]

    dim = pl.DataFrame({"id_medico": ["A"], "id_medico_num": [0]})
    with pytest.raises(RuntimeError, match="medico fora de crm_medico_dim"):
        index._com_codigo(pl.DataFrame({"id_medico": ["unknown"]}).lazy(), dim, "fixture")


def test_build_index_writes_annual_monthly_bitmaps_and_loads_them(tmp_path, monkeypatch):
    destination = tmp_path / "crm_index.parquet"
    dim = _install_sources(monkeypatch, destination)
    progress = []
    index.construir_indice(str(destination), progress.append)

    assert destination.exists()
    assert progress == [31, 63, 95, 100]
    loaded = index.IndiceBitmaps(str(destination), dim.get_column("id_medico"), [202401, 202402])
    assert set(loaded.uniao_farmacias([10, 20], [2024], [202401])) == {0, 1}
    assert set(loaded.alta("uf:SP", [2024], [202401])) == {0}
    assert set(loaded.alta("municipio:3550308", [], [202402])) == {1}
    assert loaded.ids_medico(BitMap([0, 1])).to_list() == ["A/SP", "B/RJ"]
    assert loaded.ids_medico(BitMap()).to_list() == []

    # Consulta mensal move a chave usada para o final do LRU e a capacidade e respeitada.
    monkeypatch.setattr(index, "MESES_EM_MEMORIA", 2)
    loaded._mes(202401)
    loaded._mes(202402)
    loaded._mes(202401)
    loaded._mes(202403)
    assert list(loaded._meses) == [202401, 202403]
    assert index.chave_territorio("uf", "SP") == "uf:SP"


def test_build_index_skips_empty_annual_groups(tmp_path, monkeypatch):
    destination = tmp_path / "empty_annual_index.parquet"
    _install_sources(monkeypatch, destination)
    monkeypatch.setattr(
        dc,
        "scan_crm_farmacia_medico_ano",
        lambda: pl.DataFrame(schema={"ano": pl.Int32, "id_cnpj": pl.Int32, "id_medico_num": pl.Int32}).lazy(),
    )
    monkeypatch.setattr(
        dc,
        "scan_crm_medico_territorio_ano",
        lambda: pl.DataFrame(
            schema={
                "ano": pl.Int32, "nivel": pl.Utf8, "id_geografico": pl.Utf8,
                "qtd_meses_alta_intensidade": pl.Int32, "id_medico": pl.Utf8,
            }
        ).lazy(),
    )

    index.construir_indice(str(destination))
    loaded = pl.read_parquet(destination)
    assert not loaded.filter(pl.col("granularidade") == "ano").height
    assert loaded.filter(pl.col("granularidade") == "mes").height > 0


def test_build_index_rejects_empty_duplicate_or_unmatched_doctor_dimension(tmp_path, monkeypatch):
    destination = tmp_path / "crm_index.parquet"
    dim, limiar, farmacia_ano, territorio_ano, farmacia_mes, territorio_mes = _sources()
    _install_sources(monkeypatch, destination)
    monkeypatch.setattr(dc, "scan_crm_medico_dim", lambda: dim.clear().lazy())
    with pytest.raises(RuntimeError, match="dim vazia ou com codigos repetidos"):
        index.construir_indice(str(destination))

    duplicate_code = pl.concat([dim, dim.head(1).with_columns(pl.lit("C/SP").alias("id_medico"))])
    monkeypatch.setattr(dc, "scan_crm_medico_dim", lambda: duplicate_code.lazy())
    with pytest.raises(RuntimeError, match="dim vazia ou com codigos repetidos"):
        index.construir_indice(str(destination))

    duplicate_id = pl.concat([dim, dim.head(1).with_columns(pl.lit(2).alias("id_medico_num"))])
    monkeypatch.setattr(dc, "scan_crm_medico_dim", lambda: duplicate_id.lazy())
    with pytest.raises(RuntimeError, match="id_medico repetido"):
        index.construir_indice(str(destination))

    _install_sources(monkeypatch, destination)
    unmatched = territorio_mes.with_columns(pl.lit("MISSING").alias("id_medico"))
    monkeypatch.setattr(dc, "scan_crm_medico_territorio_mes", lambda: unmatched.lazy())
    with pytest.raises(RuntimeError, match="medico fora de crm_medico_dim"):
        index.construir_indice(str(destination))


def test_obter_indice_validates_signatures_metadata_dimension_and_reuses_instance(tmp_path, monkeypatch):
    destination = tmp_path / "crm_index.parquet"
    dim = _install_sources(monkeypatch, destination)
    index.construir_indice(str(destination))
    monkeypatch.setattr(index, "_INDICE", None)
    monkeypatch.setattr(index, "_INDICE_CHAVE", None)

    loaded = index.obter_indice()
    assert loaded.ids_medico(BitMap([1])).to_list() == ["B/RJ"]
    assert index.obter_indice() is loaded

    changed_key = lambda name: (name, 999, 456)
    monkeypatch.setattr(dc, "get_global_cache_signature", changed_key)
    with pytest.raises(index.IndiceDesatualizado, match="desatualizado"):
        index.obter_indice()

    monkeypatch.setattr(dc, "get_global_cache_signature", lambda _name: (_ for _ in ()).throw(FileNotFoundError("missing")))
    with pytest.raises(index.IndiceDesatualizado, match="Modulo CRM ausente"):
        index.obter_indice()


def test_obter_indice_rejects_absent_metadata_and_dimension_mismatch(tmp_path, monkeypatch):
    destination = tmp_path / "crm_index.parquet"
    dim = _install_sources(monkeypatch, destination)
    index.construir_indice(str(destination))
    monkeypatch.setattr(index, "_INDICE", None)
    monkeypatch.setattr(index, "_INDICE_CHAVE", None)

    original = pl.read_parquet(destination)
    original.filter(pl.col("tipo") != "meta").write_parquet(destination)
    with pytest.raises(index.IndiceDesatualizado, match="sem assinatura"):
        index.obter_indice()

    info = {
        "versao": index.CRM_INDICE_BITMAPS_VERSION,
        "fontes": {name: [123, 456] for name in index.FONTES},
        "medicos": 1,
        "meses": [202401, 202402],
    }
    meta = pl.DataFrame(
        {
            "tipo": ["meta"], "granularidade": ["-"], "periodo": [0],
            "chave": ["assinatura"], "bitmap": [json.dumps(info).encode("utf-8")],
        },
        schema_overrides={"periodo": pl.Int32, "bitmap": pl.Binary},
    )
    rows = pl.concat([meta, original.filter(pl.col("tipo") != "meta")], how="diagonal_relaxed")
    rows.write_parquet(destination)
    with pytest.raises(index.IndiceDesatualizado, match="nao corresponde ao indice"):
        index.obter_indice()
