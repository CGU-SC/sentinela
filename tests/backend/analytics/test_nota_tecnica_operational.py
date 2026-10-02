from datetime import date
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

import polars as pl
import pytest
from fastapi import HTTPException

from backend.api.services.analytics import (
    nota_tecnica_prepare as prepare,
    nota_tecnica_readiness as readiness,
    nota_tecnica_regionais as regionais,
    par_teia,
    socios as socios_service,
)
from backend.cache_producers.types import CacheLoadResult


@pytest.fixture
def temp_dir():
    with TemporaryDirectory(prefix="sentinela-nt-operational-", dir=Path.cwd()) as directory:
        yield Path(directory)


def test_regional_directory_and_resolution_are_normalized_and_detached():
    items = regionais.list_nota_tecnica_regionais()
    assert len(items) == len(regionais._REGIONAIS)
    assert len({item["codigo"] for item in items}) == len(items)
    assert all(item["linha_endereco"].endswith(item["cep"]) for item in items)
    assert all(item["linha_contato"].startswith("Tel. ") for item in items)
    items[0]["estado"] = "mutado"
    assert regionais.list_nota_tecnica_regionais()[0]["estado"] != "mutado"
    assert regionais.resolve_nota_tecnica_regional(" sp ")["codigo"] == "SP"
    with pytest.raises(RuntimeError, match="obrigatória"):
        regionais.resolve_nota_tecnica_regional(None)
    with pytest.raises(RuntimeError, match="inválida.*XX"):
        regionais.resolve_nota_tecnica_regional(" xx ")


@pytest.mark.parametrize(
    ("scope", "expected"),
    [
        ("alvo", ["1"]),
        ("N2", ["2"]),
        ("n4", ["3"]),
        (" QUALQUER ", ["1", "3"]),
    ],
)
def test_par_teia_filters_each_supported_scope(scope, expected, monkeypatch):
    targets = pl.DataFrame({"cnpj": ["1", "2", "3", "4"], "name": ["a", "b", "c", "d"]})
    memberships = pl.DataFrame(
        {
            "cnpj": ["1", "2", "3", "4"],
            "has_par_alvo": [True, False, False, False],
            "has_par_n2": [False, True, False, False],
            "has_par_n4": [False, False, True, False],
            "has_par_qualquer": [True, False, True, False],
        }
    )
    monkeypatch.setattr(par_teia, "get_df_par_teia_alvos", lambda: memberships)
    result = par_teia.apply_par_teia_filter(targets, scope)
    assert result.get_column("cnpj").to_list() == expected


def test_par_teia_filter_bypasses_empty_or_all_and_rejects_bad_contracts(monkeypatch):
    targets = pl.DataFrame({"cnpj": ["1"]})
    assert par_teia.apply_par_teia_filter(targets, None) is targets
    assert par_teia.apply_par_teia_filter(targets, "Todos") is targets
    with pytest.raises(HTTPException) as invalid:
        par_teia.apply_par_teia_filter(targets, "semelhante")
    assert invalid.value.status_code == 400
    with pytest.raises(HTTPException) as missing_column:
        par_teia.apply_par_teia_filter(pl.DataFrame({"other": [1]}), "alvo")
    assert missing_column.value.status_code == 500
    monkeypatch.setattr(par_teia, "get_df_par_teia_alvos", lambda: (_ for _ in ()).throw(RuntimeError("cache ausente")))
    with pytest.raises(HTTPException) as unavailable:
        par_teia.apply_par_teia_filter(targets, "alvo")
    assert unavailable.value.status_code == 503
    assert unavailable.value.detail == "cache ausente"
    assert isinstance(unavailable.value.__cause__, RuntimeError)


def test_socios_service_maps_load_errors_empty_results_and_sorted_records(monkeypatch):
    cnpj = "12345678000190"
    monkeypatch.setattr(socios_service, "load_socios", lambda _: CacheLoadResult(None, False, error="offline"))
    with pytest.raises(HTTPException) as load_error:
        socios_service.get_socios_farmacia(cnpj)
    assert load_error.value.status_code == 503
    assert "offline" in load_error.value.detail

    monkeypatch.setattr(socios_service, "load_socios", lambda _: CacheLoadResult(None, False))
    with pytest.raises(HTTPException) as no_frame:
        socios_service.get_socios_farmacia(cnpj)
    assert no_frame.value.status_code == 503

    empty = pl.DataFrame(schema={"cnpj": pl.String, "data_entrada_sociedade": pl.Date})
    monkeypatch.setattr(socios_service, "load_socios", lambda _: CacheLoadResult(empty, True))
    response = socios_service.get_socios_farmacia(cnpj)
    assert response.socios == [] and response.from_cache

    records = pl.DataFrame(
        {
            "cnpj": [cnpj, cnpj],
            "cpf_cnpj_socio": ["1", "2"],
            "data_entrada_sociedade": [date(2020, 1, 1), date(2024, 1, 1)],
            "data_processamento": [date(2025, 2, 1), date(2025, 2, 1)],
            "is_cadunico": [False, True],
            "is_esocial": [False, True],
            "is_seguro_defeso": [False, False],
        }
    )
    monkeypatch.setattr(socios_service, "load_socios", lambda _: CacheLoadResult(records, False))
    response = socios_service.get_socios_farmacia(cnpj)
    assert [s.cpf_cnpj_socio for s in response.socios] == ["2", "1"]
    assert response.data_processamento == date(2025, 2, 1)
    assert response.from_cache is False


def test_readiness_cnpj_validation_and_module_summary(temp_dir, monkeypatch):
    cnpj = "12345678000190"
    start, end = date(2024, 1, 1), date(2024, 12, 31)
    assert readiness._clean_cnpj("12.345.678/0001-90") == cnpj
    with pytest.raises(ValueError, match="CNPJ invalido"):
        readiness._clean_cnpj("123")
    module = readiness._module("optional", "Optional", [("x.parquet", str(temp_dir / "missing"))], scope="global", required=False)
    assert module["ready"] is False and module["preparable"] is False
    assert module["detail"] == "1 arquivo(s) ausente(s)."
    assert readiness._global_files(["known", "unknown"], {"known": "known.parquet"}, str(temp_dir)) == [
        ("known.parquet", str(temp_dir / "known.parquet")),
        ("cache global nao registrado: unknown", ""),
    ]
    assert readiness._cnpj_files(cnpj, ["local.parquet"], str(temp_dir)) == [
        (os.path.join("cnpjs", cnpj, "local.parquet"), str(temp_dir / cnpj / "local.parquet"))
    ]

    summary = readiness._build_readiness(cnpj, [module], start, end)
    assert summary["ready"] is True and summary["preparable"] is False
    assert summary["missing_modules"] == []
    prepared = readiness._build_readiness(
        cnpj,
        [{"required": True, "ready": False, "preparable": True}],
        start,
        end,
    )
    assert prepared["ready"] is False and prepared["preparable"] is True
    not_preparable = readiness._build_readiness(
        cnpj,
        [{"required": True, "ready": False, "preparable": False}],
    )
    assert not_preparable["preparable"] is False


def _global_keys_for_readiness():
    return {
        key: f"{key}.parquet"
        for key in (
            "dados_farmacia", "perfil_estabelecimento", "localidades", "movimentacao", "matriz_risco",
            "volume_atipico_semestral", "geografico_origem_uf", "memoria_calculo_global", "medicamentos",
            "movimentacao_mensal_gtin_global", "falecidos", "dados_socios", "esocial_cnpj_ano",
            "esocial_cnpj_trabalhador_ano", "esocial_cnpj_ultima_movimentacao", "sentinela_metadados_base",
            "analise_gtin_inconsistencia_clinica", "analise_gtin_inconsistencia_clinica_municipio",
            "analise_gtin_inconsistencia_clinica_regiao", "dados_ibge_demografia", "bench_crm_uf",
            "bench_crm_regiao", "bench_crm_br", "crm_prescricoes_brasil_semestre", "dados_medico",
            "crm_prescritores_global", "geografico_global", "crm_raiox_tx_global",
            "crm_concentracao_unico_alertas_global", "crm_concentracao_multiplo_alertas_global",
            "crm_timeline_dia_global", "crm_timeline_hora_global", "crm_timeline_eventos_global",
        )
    }


def test_public_readiness_reports_missing_and_all_ready_cache_sets(temp_dir, monkeypatch):
    cnpj = "12345678000190"
    global_dir = temp_dir / "global"
    cnpj_root = temp_dir / "cnpjs"
    global_dir.mkdir()
    cnpj_dir = cnpj_root / cnpj
    cnpj_dir.mkdir(parents=True)
    monkeypatch.setattr(readiness, "get_cache_dir", lambda: str(global_dir))
    monkeypatch.setattr(readiness, "get_cnpj_cache_root", lambda: str(cnpj_root))
    mapping = _global_keys_for_readiness()
    monkeypatch.setattr(readiness.cache_registry, "get_global_parquet_files_by_key", lambda: mapping)

    missing = readiness.get_nota_tecnica_readiness(cnpj)
    assert missing["ready"] is False
    assert {m["key"] for m in missing["missing_modules"]} >= {"base_cadastral", "crm", "gtin_mensal"}
    assert readiness.get_relatorio_pdf_readiness(cnpj)["ready"] is False

    for filename in mapping.values():
        (global_dir / filename).write_text("fixture", encoding="utf-8")
    local_filenames = {
        readiness.cache_files.MEMORIA_CALCULO_PARQUET,
        readiness.cache_files.MOVIMENTACAO_MENSAL_GTIN_PARQUET,
        readiness.cache_files.CRM_PRESCRITORES_PARQUET,
        readiness.cache_files.GEOGRAFICO_PARQUET,
        readiness.cache_files.CRM_RAIOX_TX_PARQUET,
        readiness.cache_files.CRM_CONCENTRACAO_UNICO_ALERTAS_PARQUET,
        readiness.cache_files.CRM_CONCENTRACAO_MULTIPLO_ALERTAS_PARQUET,
        readiness.cache_files.CRM_TIMELINE_DIA_PARQUET,
        readiness.cache_files.CRM_TIMELINE_HORA_PARQUET,
        readiness.cache_files.CRM_TIMELINE_EVENTOS_PARQUET,
    }
    for filename in local_filenames:
        (cnpj_dir / filename).write_text("fixture", encoding="utf-8")

    ready = readiness.get_nota_tecnica_readiness(cnpj, date(2024, 1, 1), date(2024, 12, 31))
    assert ready["ready"] is True and ready["missing_modules"] == []
    assert readiness.get_relatorio_pdf_readiness(cnpj)["ready"] is True


@pytest.mark.parametrize(
    ("function", "keys_attribute", "readiness_name", "key"),
    [
        (prepare.prepare_nota_tecnica_cnpj, "_NOTA_TECNICA_CNPJ_CACHE_KEYS", "get_nota_tecnica_readiness", "memoria_calculo"),
        (prepare.prepare_relatorio_pdf_cnpj, "_RELATORIO_PDF_CNPJ_CACHE_KEYS", "get_relatorio_pdf_readiness", "crm_prescritores"),
    ],
)
def test_document_cache_preparation_existing_and_successful_paths(function, keys_attribute, readiness_name, key, temp_dir, monkeypatch):
    cnpj = "12345678000190"
    monkeypatch.setattr(prepare, keys_attribute, (key,))
    path = temp_dir / cnpj / f"{key}.parquet"
    monkeypatch.setattr(prepare, "_cnpj_cache_path", lambda _cnpj, _filename: str(path))
    monkeypatch.setattr(prepare.cache_registry, "get_cnpj_cache_definition", lambda _: SimpleNamespace(filename=path.name))
    readiness_fn = getattr(readiness, readiness_name)
    readiness_values = iter([{"ready": False, "preparable": True, "missing_modules": []}, {"ready": True, "missing_modules": []}])
    if readiness_name == "get_nota_tecnica_readiness":
        monkeypatch.setattr(prepare, readiness_name, lambda *args: next(readiness_values))
    else:
        monkeypatch.setattr(readiness, readiness_name, lambda *args: next(readiness_values))
    engine = object()

    path.parent.mkdir()
    path.write_text("present", encoding="utf-8")
    already = function(f"12.345.678/0001-90", engine)
    assert already["cnpj"] == cnpj
    assert already["prepared_modules"][0]["status"] == "already_ready"

    path.unlink()
    readiness_values = iter([{"ready": False, "preparable": True, "missing_modules": []}, {"ready": True, "missing_modules": []}])
    if readiness_name == "get_nota_tecnica_readiness":
        monkeypatch.setattr(prepare, readiness_name, lambda *args: next(readiness_values))
    else:
        monkeypatch.setattr(readiness, readiness_name, lambda *args: next(readiness_values))

    def sync(_key, _cnpj, _engine):
        assert (_key, _cnpj, _engine) == (key, cnpj, engine)
        path.write_text("generated", encoding="utf-8")

    monkeypatch.setattr(prepare.cache_manager, "sync_cnpj_cache", sync)
    created = function(cnpj, engine)
    assert created["prepared_modules"][0]["status"] == "prepared"


@pytest.mark.parametrize(
    ("function", "keys_attribute", "readiness_name", "key"),
    [
        (prepare.prepare_nota_tecnica_cnpj, "_NOTA_TECNICA_CNPJ_CACHE_KEYS", "get_nota_tecnica_readiness", "memoria_calculo"),
        (prepare.prepare_relatorio_pdf_cnpj, "_RELATORIO_PDF_CNPJ_CACHE_KEYS", "get_relatorio_pdf_readiness", "crm_prescritores"),
    ],
)
def test_document_cache_preparation_failures_are_reported(function, keys_attribute, readiness_name, key, temp_dir, monkeypatch):
    cnpj = "12345678000190"
    monkeypatch.setattr(prepare, keys_attribute, (key,))
    path = temp_dir / cnpj / f"{key}.parquet"
    monkeypatch.setattr(prepare, "_cnpj_cache_path", lambda _cnpj, _filename: str(path))
    monkeypatch.setattr(prepare.cache_registry, "get_cnpj_cache_definition", lambda _: SimpleNamespace(filename=path.name))
    if readiness_name == "get_nota_tecnica_readiness":
        setter = lambda callback: monkeypatch.setattr(prepare, readiness_name, callback)
    else:
        setter = lambda callback: monkeypatch.setattr(readiness, readiness_name, callback)

    setter(lambda *args: {"ready": False, "preparable": False, "missing_modules": [{"label": "base"}]})
    with pytest.raises(RuntimeError, match="modulos globais pendentes"):
        function(cnpj, object())

    setter(lambda *args: {"ready": False, "preparable": True, "missing_modules": []})
    monkeypatch.setattr(prepare.cache_manager, "sync_cnpj_cache", lambda *args: (_ for _ in ()).throw(ValueError("falha producer")))
    with pytest.raises(RuntimeError, match="Detalhe tecnico: falha producer"):
        function(cnpj, object())

    monkeypatch.setattr(prepare.cache_manager, "sync_cnpj_cache", lambda *args: None)
    with pytest.raises(RuntimeError, match="sem criar o arquivo obrigatorio"):
        function(cnpj, object())

    path.parent.mkdir(exist_ok=True)
    path.write_text("produced", encoding="utf-8")
    calls = iter([{"ready": False, "preparable": True, "missing_modules": []}, {"ready": False, "missing_modules": [{"label": "still missing"}]}])
    setter(lambda *args: next(calls))
    with pytest.raises(RuntimeError, match="ainda possui pendencias"):
        function(cnpj, object())


def test_prepare_failure_message_uses_key_label_hint_and_exception_detail():
    message = prepare._prepare_failure_message("memoria_calculo", RuntimeError("SQL unavailable"))
    assert "Memoria de calculo do CNPJ" in message
    assert "SQL Server" in message
    assert "Detalhe tecnico: SQL unavailable" in message
    assert prepare._prepare_failure_message("unknown", RuntimeError(" ")) == (
        "Nao foi possivel preparar o modulo unknown para a Nota Tecnica."
    )


def test_cnpj_cache_path_uses_the_configured_cache_root(monkeypatch, temp_dir):
    monkeypatch.setattr(prepare, "get_cnpj_cache_root", lambda: str(temp_dir))
    assert prepare._cnpj_cache_path("12345678000190", "memoria.parquet") == os.path.join(
        str(temp_dir), "12345678000190", "memoria.parquet"
    )
