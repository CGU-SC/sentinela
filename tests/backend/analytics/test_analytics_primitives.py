from datetime import date

import polars as pl
import pytest
from fastapi import HTTPException

from api.services.analytics import indicadores
from api.services.analytics.filtros_farmacia import CAMPOS_FILTROS_FARMACIA, FiltrosFarmacia


def test_filter_value_object_round_trips_and_ignores_unknown_mapping_keys():
    values = dict.fromkeys(CAMPOS_FILTROS_FARMACIA)
    values.update({"perc_min": 5.0, "cnae_incompativel": False, "socio_falecido": False, "volume_atipico": False, "dispersao_uf_sem_fronteira": False})
    values["unexpected"] = "ignored"
    filtros = FiltrosFarmacia.de_mapeamento(values)
    assert filtros.perc_min == 5.0
    assert filtros.como_dict()["cnae_incompativel"] is False
    assert len(FiltrosFarmacia.como_dict(FiltrosFarmacia())) == len(FiltrosFarmacia.__dataclass_fields__)


def test_indicator_text_and_number_normalizers_are_explicit():
    assert indicadores._optional_float("1.5") == 1.5
    assert indicadores._optional_float(None) is None
    assert indicadores._normalize_cache_text("  Farmácia ") == "Farmácia"
    assert indicadores._normalize_cache_text(" ") is None
    assert indicadores._normalize_cache_int("12") == 12
    assert indicadores._normalize_cache_bool("true") is True
    assert indicadores._normalize_cache_bool("false") is True  # string truthiness is preserved by the cache normalizer
    assert indicadores._normalize_cache_date(date(2020, 1, 2)) == "2020-01-02"
    assert indicadores._normalize_cache_cnpj("12.345.678/0001-90") == "12345678000190"


def test_integrity_filters_require_the_declared_profile_contract():
    with pytest.raises(HTTPException) as benefit:
        from api.services.analytics.alertas_alvos import apply_socio_beneficio_filter
        apply_socio_beneficio_filter(pl.DataFrame({"id_cnpj": [1]}), "direto")
    assert benefit.value.status_code == 500

    with pytest.raises(HTTPException) as cnae:
        from api.services.analytics.alertas_alvos import apply_cnae_incompativel_filter
        apply_cnae_incompativel_filter(pl.DataFrame({"id_cnpj": [1]}), True)
    assert "is_cnae_incompativel_farmaceutico" in cnae.value.detail
