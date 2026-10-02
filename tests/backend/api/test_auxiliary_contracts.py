"""HTTP contracts for supporting API routers, isolated from production services."""

from datetime import date
from unittest.mock import Mock

from fastapi import FastAPI
from fastapi.testclient import TestClient

import database
from api.endpoints import cache as cache_endpoints
from api.endpoints import geo as geo_endpoints
from api.endpoints import preferences as preferences_endpoints
from api.endpoints import system as system_endpoints
from api.endpoints import targets as targets_endpoints
from api.router import api_router
from api.schemas.geo import LocalidadesResponseSchema
from api.schemas.preferences import PreferencesSchema
from api.schemas.system_update import UpdateStatusResponse
from api.schemas.targets import ClinicalTargetResponse
from api.services.preferences import PreferencesError
from api.services.watchlist_recovery import RemocaoIndisponivelError


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(api_router, prefix="/api/v1")
    app.dependency_overrides[database.get_db] = lambda: object()
    return TestClient(app)


def _preferences() -> dict:
    return {
        "schema_version": 1,
        "filters": {},
        "watchlist": [],
        "ui": {},
        "nota_tecnica": {},
        "metodologia": {},
    }


def _update_status(**overrides) -> UpdateStatusResponse:
    data = {
        "current_version": "2.0.0",
        "latest_version": None,
        "minimum_supported_version": None,
        "status": "verification_unavailable",
        "checked_at": None,
        "source": "none",
        "download_url": None,
        "release_notes_url": None,
        "message": "Sem verificação disponível.",
        "block_title": None,
        "block_message": None,
        "blocked_since": None,
    }
    data.update(overrides)
    return UpdateStatusResponse.model_validate(data)


def _empty_target(**overrides) -> ClinicalTargetResponse:
    data = {
        "kpis": [],
        "mapa": [],
        "items": [],
        "total": 0,
        "page": 1,
        "page_size": 20,
        "sort_field": "valor_incompativel",
        "sort_order": "desc",
    }
    data.update(overrides)
    return ClinicalTargetResponse.model_validate(data)


def test_router_registers_auxiliary_routes_and_cache_refresh(monkeypatch):
    client = _client()
    cache_status = {"status": "ready", "message": "Cache disponível"}
    refresh = Mock()
    monkeypatch.setattr(cache_endpoints, "get_cache_status", lambda: cache_status)
    monkeypatch.setattr(cache_endpoints, "refresh_cache", refresh)

    status = client.get("/api/v1/cache/status")
    started = client.post("/api/v1/cache/refresh")

    assert status.status_code == 200
    assert status.json() == cache_status
    assert started.status_code == 200
    assert started.json() == {
        "status": "started",
        "message": "Sincronização iniciada em segundo plano.",
    }
    refresh.assert_called_once_with(cache_endpoints.engine)


def test_geo_endpoints_serialize_responses_and_forward_date_filters(monkeypatch):
    client = _client()
    localidades = LocalidadesResponseSchema(localidades=[{
        "sg_uf": "SC",
        "no_regiao_saude": "Vale",
        "id_regiao_saude": 4201,
        "no_municipio": "Florianópolis",
        "id_ibge7": 4205407,
        "nu_populacao": 537211,
        "unidade_pf": "Regional Sul",
    }])
    geo_result = {"estabelecimentos": []}
    get_localidades = Mock(return_value=localidades)
    get_estabelecimentos = Mock(return_value=geo_result)
    monkeypatch.setattr(geo_endpoints.GeoService, "get_localidades", get_localidades)
    monkeypatch.setattr(geo_endpoints.GeoService, "get_estabelecimentos_geo", get_estabelecimentos)

    response_localidades = client.get("/api/v1/geo/localidades")
    response_geo = client.get(
        "/api/v1/geo/estabelecimentos",
        params={"data_inicio": "2025-01-01", "data_fim": "2025-06-30"},
    )

    assert response_localidades.status_code == 200
    assert response_localidades.json()["localidades"][0]["id_regiao_saude"] == 4201
    get_localidades.assert_called_once()
    assert response_geo.status_code == 200
    assert response_geo.json() == geo_result
    get_estabelecimentos.assert_called_once_with(
        data_inicio=date(2025, 1, 1), data_fim=date(2025, 6, 30)
    )

    invalid = client.get("/api/v1/geo/estabelecimentos", params={"data_inicio": "ontem"})
    assert invalid.status_code == 422
    assert "data_inicio" in invalid.text


def test_preferences_routes_validate_inputs_and_map_service_errors(monkeypatch):
    client = _client()
    prefs = _preferences()
    monkeypatch.setattr(preferences_endpoints.PreferencesService, "read", lambda: prefs)
    monkeypatch.setattr(preferences_endpoints.PreferencesService, "update_filters", lambda value: {**prefs, "filters": value})
    monkeypatch.setattr(preferences_endpoints.PreferencesService, "update_ui", lambda value: {**prefs, "ui": value})
    monkeypatch.setattr(preferences_endpoints.PreferencesService, "update_nota_tecnica", lambda value: {**prefs, "nota_tecnica": value})
    monkeypatch.setattr(preferences_endpoints.WatchlistRecoveryService, "write_preferences", lambda value: value)
    monkeypatch.setattr(preferences_endpoints.WatchlistRecoveryService, "update_watchlist", lambda value: {**prefs, "watchlist": value})
    monkeypatch.setattr(preferences_endpoints.WatchlistRecoveryService, "last_removal", lambda: {"cnpj": "00000000000001"})
    monkeypatch.setattr(preferences_endpoints.WatchlistRecoveryService, "undo_removal", lambda cnpj: {**prefs, "watchlist": [{"cnpj": cnpj}]})
    monkeypatch.setattr(preferences_endpoints.WatchlistRecoveryService, "recovery_status", lambda: {"principal": {"valid": True}})
    monkeypatch.setattr(preferences_endpoints.WatchlistRecoveryService, "restore", lambda source, include: prefs)
    monkeypatch.setattr(preferences_endpoints, "resolve_nota_tecnica_regional", lambda code: code or "nacional")
    monkeypatch.setattr(preferences_endpoints, "get_audit_high_value", lambda: 100_000.0)
    monkeypatch.setattr(preferences_endpoints, "get_volume_atipico_aumento_minimo", lambda: 0.5)

    assert client.get("/api/v1/preferences").json()["schema_version"] == 1
    assert client.put("/api/v1/preferences/filters", json={"filters": {"uf": "SC"}}).json()["filters"] == {"uf": "SC"}
    assert client.put("/api/v1/preferences/ui", json={"ui": {"theme": "dark"}}).json()["ui"] == {"theme": "dark"}
    assert client.put("/api/v1/preferences/watchlist", json={"interesse": [{"cnpj": "00000000000001"}]}).json()["watchlist"][0]["cnpj"] == "00000000000001"
    assert client.get("/api/v1/preferences/watchlist/ultima-remocao").json() == {"cnpj": "00000000000001"}
    assert client.post("/api/v1/preferences/watchlist/desfazer-remocao", json={"cnpj": "00000000000001"}).status_code == 200
    assert client.get("/api/v1/preferences/recovery/status").json() == {"principal": {"valid": True}}
    assert client.post("/api/v1/preferences/recovery?incluir_evidencias_backup=true", json={"source": "backup"}).status_code == 200

    note_response = client.put("/api/v1/preferences/nota-tecnica", json={"nota_tecnica": {
        "regional_codigo": "sul",
        "assinantes_tecnicos": [{"nome": " Ana ", "cargo": " Auditora "}, {"nome": " ", "cargo": " "}],
        "gerar_pdf_visualizacao": True,
    }})
    assert note_response.status_code == 200
    assert note_response.json()["nota_tecnica"] == {
        "regional_codigo": "sul",
        "assinantes_tecnicos": [{"nome": "Ana", "cargo": "Auditora"}],
        "gerar_pdf_visualizacao": True,
    }

    incomplete_signer = client.put("/api/v1/preferences/nota-tecnica", json={"nota_tecnica": {
        "assinantes_tecnicos": [{"nome": "Ana"}],
    }})
    assert incomplete_signer.status_code == 422
    assert "nome e cargo" in incomplete_signer.json()["detail"]
    invalid_pdf_flag = client.put("/api/v1/preferences/nota-tecnica", json={"nota_tecnica": {
        "gerar_pdf_visualizacao": "true",
    }})
    assert invalid_pdf_flag.status_code == 422

    method_status = client.get("/api/v1/preferences/metodologia")
    assert method_status.status_code == 200
    assert method_status.json()["audit_high_value"] == 100_000.0
    assert set(method_status.json()["limits"]) == {"audit_high_value", "volume_atipico_aumento_minimo"}

    invalid_undo = client.post("/api/v1/preferences/watchlist/desfazer-remocao", json={"cnpj": "123"})
    assert invalid_undo.status_code == 422
    monkeypatch.setattr(preferences_endpoints.PreferencesService, "read", lambda: (_ for _ in ()).throw(PreferencesError("arquivo indisponível")))
    failed_read = client.get("/api/v1/preferences")
    assert failed_read.status_code == 503
    assert failed_read.json()["detail"] == "arquivo indisponível"
    monkeypatch.setattr(preferences_endpoints.WatchlistRecoveryService, "undo_removal", lambda _cnpj: (_ for _ in ()).throw(RemocaoIndisponivelError("recuperação indisponível")))
    failed_undo = client.post("/api/v1/preferences/watchlist/desfazer-remocao", json={"cnpj": "00000000000001"})
    assert failed_undo.status_code == 409
    assert failed_undo.json()["detail"] == "recuperação indisponível"


def test_preferences_full_save_and_methodology_validation(monkeypatch):
    client = _client()
    prefs = _preferences()
    saved = Mock(return_value=prefs)
    monkeypatch.setattr(preferences_endpoints.WatchlistRecoveryService, "write_preferences", saved)
    response = client.put("/api/v1/preferences", json=prefs)
    assert response.status_code == 200
    saved.assert_called_once()
    assert PreferencesSchema.model_validate(response.json()).schema_version == 1

    missing = client.put("/api/v1/preferences/metodologia", json={"metodologia": {"audit_high_value": 2}})
    assert missing.status_code == 422
    assert "volume_atipico_aumento_minimo" in missing.json()["detail"]
    invalid_value = client.put("/api/v1/preferences/metodologia", json={"metodologia": {
        "audit_high_value": -1,
        "volume_atipico_aumento_minimo": 0.5,
    }})
    assert invalid_value.status_code == 422

    monkeypatch.setattr(preferences_endpoints, "normalize_audit_high_value", lambda value: float(value))
    monkeypatch.setattr(preferences_endpoints, "normalize_volume_atipico_aumento_minimo", lambda value: float(value))
    monkeypatch.setattr(preferences_endpoints, "get_audit_high_value", lambda: 50_000.0)
    monkeypatch.setattr(preferences_endpoints, "get_volume_atipico_aumento_minimo", lambda: 0.75)
    update_methodology = Mock(return_value=prefs)
    monkeypatch.setattr(preferences_endpoints.PreferencesService, "update_metodologia", update_methodology)
    valid_methodology = client.put("/api/v1/preferences/metodologia", json={"metodologia": {
        "audit_high_value": "50000", "volume_atipico_aumento_minimo": "0.75",
    }})
    assert valid_methodology.status_code == 200
    assert valid_methodology.json()["audit_high_value"] == 50_000.0
    update_methodology.assert_called_once_with({
        "audit_high_value": 50_000.0, "volume_atipico_aumento_minimo": 0.75,
    })


def test_note_preference_validation_reports_bad_region_and_signer_shapes(monkeypatch):
    client = _client()
    prefs = _preferences()
    monkeypatch.setattr(preferences_endpoints.PreferencesService, "update_nota_tecnica", lambda value: {**prefs, "nota_tecnica": value})
    monkeypatch.setattr(
        preferences_endpoints,
        "resolve_nota_tecnica_regional",
        lambda code: (_ for _ in ()).throw(RuntimeError("regional desconhecida")) if code == "desconhecida" else code,
    )

    empty = client.put("/api/v1/preferences/nota-tecnica", json={"nota_tecnica": {}})
    assert empty.status_code == 200
    assert empty.json()["nota_tecnica"] == {"assinantes_tecnicos": [], "gerar_pdf_visualizacao": False}

    invalid_region = client.put("/api/v1/preferences/nota-tecnica", json={"nota_tecnica": {"regional_codigo": "desconhecida"}})
    assert invalid_region.status_code == 422
    assert invalid_region.json()["detail"] == "regional desconhecida"

    invalid_signers = [
        ("texto", "deve ser uma lista"),
        ([{"nome": "A", "cargo": "B"}] * 4, "no maximo 3"),
        (["Ana"], "Cada assinatura tecnica deve ser um objeto"),
        ([{"cargo": "Auditora"}], "deve conter nome e cargo"),
    ]
    for signers, message in invalid_signers:
        response = client.put("/api/v1/preferences/nota-tecnica", json={"nota_tecnica": {
            "assinantes_tecnicos": signers,
        }})
        assert response.status_code == 422
        assert message in response.json()["detail"]


def test_system_endpoints_cover_cached_remote_error_and_update_actions(monkeypatch):
    client = _client()
    cached = _update_status(download_url="https://example.test/Sentinela.exe")
    monkeypatch.setattr(system_endpoints, "get_cached_status", lambda: cached)
    check = Mock(return_value=_update_status(status="current", message="Sistema atualizado."))
    monkeypatch.setattr(system_endpoints, "check_for_updates", check)

    assert client.get("/api/v1/system/update-status").json()["download_url"] == cached.download_url
    monkeypatch.setattr(system_endpoints, "get_cached_status", lambda: None)
    computed = client.get("/api/v1/system/update-status")
    assert computed.status_code == 200
    assert computed.json()["status"] == "current"
    check.assert_called_once_with()
    forced = client.post("/api/v1/system/check-update")
    assert forced.status_code == 200
    assert check.call_args_list[-1].kwargs == {"force_remote": True}

    unavailable = client.post("/api/v1/system/download-update", json={})
    assert unavailable.status_code == 409
    assert "URL de download" in unavailable.json()["detail"]
    monkeypatch.setattr(system_endpoints, "get_cached_status", lambda: cached)
    download = Mock()
    monkeypatch.setattr(system_endpoints, "download_and_apply_update", download)
    started = client.post("/api/v1/system/download-update")
    assert started.status_code == 200
    download.assert_called_once_with(cached.download_url)
    override = client.post("/api/v1/system/download-update", json={"download_url": "https://example.test/override.exe"})
    assert override.status_code == 200
    download.assert_called_with("https://example.test/override.exe")

    monkeypatch.setattr(system_endpoints, "download_and_apply_update", Mock(side_effect=RuntimeError("somente Desktop")))
    monkeypatch.setattr(system_endpoints.sys, "frozen", False, raising=False)
    rejected = client.post("/api/v1/system/download-update", json={"download_url": "https://example.test/a.exe"})
    assert rejected.status_code == 400
    assert rejected.json()["detail"] == "somente Desktop"

    progress = {"status": "downloading", "progress": 0.5, "error": None}
    monkeypatch.setattr(system_endpoints, "get_download_state", lambda: progress)
    assert client.get("/api/v1/system/download-progress").json() == progress
    apply = Mock(side_effect=RuntimeError("sem arquivo"))
    monkeypatch.setattr(system_endpoints, "apply_update", apply)
    assert client.post("/api/v1/system/apply-update").status_code == 409
    apply.side_effect = None
    assert client.post("/api/v1/system/apply-update").json() == {"ok": True}
    cancel = Mock()
    monkeypatch.setattr(system_endpoints, "cancel_update", cancel)
    assert client.post("/api/v1/system/cancel-update").json() == {"ok": True}
    cancel.assert_called_once_with()


def test_target_endpoints_forward_id_based_filters_and_reject_bad_paging(monkeypatch):
    client = _client()
    result = _empty_target(page=2, page_size=5, sort_field="valor_incompativel", sort_order="asc")
    parkinson = Mock(return_value=result)
    diabetes = Mock(return_value=_empty_target())
    monkeypatch.setattr(targets_endpoints, "get_parkinson_menor_50", parkinson)
    monkeypatch.setattr(targets_endpoints, "get_diabetes_menor_20", diabetes)

    response = client.get("/api/v1/targets/parkinson-menor-50", params={
        "data_inicio": "2024-01-01", "data_fim": "2025-01-01", "uf": "SC",
        "regiao_id": 4201, "id_ibge7": 4205407, "page": 2, "page_size": 5,
        "sort_field": "valor_incompativel", "sort_order": "asc",
    })
    assert response.status_code == 200
    assert response.json()["page"] == 2
    parkinson.assert_called_once_with(
        data_inicio=date(2024, 1, 1), data_fim=date(2025, 1, 1), uf="SC",
        regiao_id=4201, id_ibge7=4205407, page=2, page_size=5,
        sort_field="valor_incompativel", sort_order="asc",
    )

    assert client.get("/api/v1/targets/diabetes-menor-20").status_code == 200
    diabetes.assert_called_once()
    assert client.get("/api/v1/targets/parkinson-menor-50", params={"page": 0}).status_code == 422
    assert client.get("/api/v1/targets/diabetes-menor-20", params={"sort_order": "sideways"}).status_code == 422
    assert client.get("/api/v1/targets/parkinson-menor-50", params={"uf": "SANTA"}).status_code == 422
