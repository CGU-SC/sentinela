import pytest

import cache_files
import cache_registry


def test_global_registry_is_keyed_and_uses_canonical_module_names():
    files = cache_registry.get_global_parquet_files_by_key()

    assert files["movimentacao"] == cache_files.MOVIMENTACAO_PARQUET
    assert files["perfil_estabelecimento"] == cache_files.PERFIL_ESTABELECIMENTO_PARQUET
    assert files["crm_raiox_tx_global"] == cache_files.CRM_RAIOX_TX_GLOBAL_PARQUET
    assert len(files) == len(cache_registry.GLOBAL_CACHE_DEFINITIONS)
    assert len(set(files.values())) == len(files)


def test_cnpj_registry_exposes_unique_files_and_complete_schemas():
    definitions = cache_registry.CNPJ_CACHE_DEFINITIONS
    files = cache_registry.get_cnpj_parquet_files()
    schemas = cache_registry.get_cnpj_parquet_schemas()

    assert len(files) == len(definitions)
    assert len(set(files)) == len(files)
    assert set(schemas) == set(files)
    assert all(definition.scope == "cnpj" for definition in definitions)
    assert all(definition.producer for definition in definitions)
    assert schemas[cache_files.MOVIMENTACAO_MENSAL_GTIN_PARQUET]["periodo"].__name__ == "Date"


def test_registry_lookup_returns_definition_and_rejects_unknown_key():
    definition = cache_registry.get_cnpj_cache_definition("crm_raiox_tx")

    assert definition.filename == cache_files.CRM_RAIOX_TX_PARQUET
    assert definition.producer == "cache_producers.crm.sync_crm_raiox_tx"
    with pytest.raises(KeyError, match="Cache CNPJ nao registrado: ausente"):
        cache_registry.get_cnpj_cache_definition("ausente")


def test_schema_catalog_fails_visibly_if_a_cache_has_no_schema(monkeypatch):
    definitions = list(cache_registry.CNPJ_CACHE_DEFINITIONS)
    definitions[0] = cache_registry.CacheDefinition(
        key=definitions[0].key,
        filename=definitions[0].filename,
        scope=definitions[0].scope,
        schema=None,
        producer=definitions[0].producer,
    )
    monkeypatch.setattr(cache_registry, "CNPJ_CACHE_DEFINITIONS", tuple(definitions))

    with pytest.raises(RuntimeError, match=f"Cache CNPJ sem schema registrado: {definitions[0].key}"):
        cache_registry.get_cnpj_parquet_schemas()
