import pytest

from api.services.analytics import indicator_rules


@pytest.mark.parametrize(
    ("normalizer", "default", "valid"),
    [
        (indicator_rules.normalize_volume_atipico_aumento_minimo, 10000.0, "250.5"),
        (indicator_rules.normalize_audit_high_value, 150000.0, "250.5"),
    ],
)
def test_indicator_rules_normalize_defaults_and_numeric_values(normalizer, default, valid):
    assert normalizer(None) == default
    assert normalizer("") == default
    assert normalizer(valid) == 250.5


@pytest.mark.parametrize(
    ("normalizer", "invalid"),
    [
        (indicator_rules.normalize_volume_atipico_aumento_minimo, "abc"),
        (indicator_rules.normalize_volume_atipico_aumento_minimo, -1),
        (indicator_rules.normalize_volume_atipico_aumento_minimo, 1_000_000_001),
        (indicator_rules.normalize_audit_high_value, "abc"),
        (indicator_rules.normalize_audit_high_value, -1),
        (indicator_rules.normalize_audit_high_value, 1_000_000_001),
    ],
)
def test_indicator_rules_reject_invalid_or_out_of_range_values(normalizer, invalid):
    with pytest.raises(RuntimeError):
        normalizer(invalid)


def test_indicator_rule_getters_validate_saved_methodology(monkeypatch):
    monkeypatch.setattr(indicator_rules.PreferencesService, "read", lambda: {"metodologia": {"audit_high_value": 0}})
    assert indicator_rules.get_audit_high_value() == 0
    monkeypatch.setattr(indicator_rules.PreferencesService, "read", lambda: {"metodologia": "invalid"})
    with pytest.raises(RuntimeError, match="objeto"):
        indicator_rules.get_volume_atipico_aumento_minimo()


def test_indicator_rule_getters_use_defaults_for_missing_methodology_and_validate_both_types(monkeypatch):
    monkeypatch.setattr(indicator_rules.PreferencesService, "read", lambda: {"metodologia": None})
    assert indicator_rules.get_volume_atipico_aumento_minimo() == indicator_rules.DEFAULT_VOLUME_ATIPICO_AUMENTO_MINIMO
    assert indicator_rules.get_audit_high_value() == indicator_rules.DEFAULT_AUDIT_HIGH_VALUE

    monkeypatch.setattr(indicator_rules.PreferencesService, "read", lambda: {"metodologia": []})
    with pytest.raises(RuntimeError, match="objeto"):
        indicator_rules.get_audit_high_value()
