from datetime import date, datetime

import pytest

from backend.api.services.analytics import nota_tecnica_formatters as formatters


@pytest.mark.unit
@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, "—"),
        ("", "—"),
        ("12345678901", "123.456.789-01"),
        ("11.222.333/0001-81", "11.222.333/0001-81"),
        ("123", "123"),
    ],
)
def test_format_cpf_cnpj(value, expected):
    assert formatters._format_cpf_cnpj(value) == expected


@pytest.mark.unit
def test_format_decimal_in_portuguese_locale():
    assert formatters._format_decimal_pt(1234567.891) == "1.234.567,89"
    assert formatters._format_decimal_pt(-1234.5, decimals=1) == "-1.234,5"
    assert formatters._format_decimal_pt(12, decimals=0) == "12"


@pytest.mark.unit
def test_format_date_supports_date_datetime_iso_and_unrecognized_text():
    assert formatters._format_date_pt(None) == "—"
    assert formatters._format_date_pt(date(2025, 3, 7)) == "07.03.2025"
    assert formatters._format_date_pt(datetime(2025, 3, 7, 9, 30)) == "07.03.2025"
    assert formatters._format_date_pt("2025-03-07") == "07.03.2025"
    assert formatters._format_date_pt("2025-03-07T09:30:00") == "07.03.2025"
    assert formatters._format_date_pt("data indisponível") == "data indisponível"


@pytest.mark.unit
def test_title_case_and_pathology_labels():
    assert formatters._title_case_pt(None) == "Não identificado"
    assert formatters._title_case_pt("   ") == "Não identificado"
    assert formatters._title_case_pt("  JOAO DA SILVA  ") == "Joao Da Silva"
    assert formatters._format_patologia_pt(None) == ""
    assert formatters._format_patologia_pt("doenca de parkinson") == "Doença De Parkinson"
    assert formatters._format_patologia_pt("diabetes mellitus") == "Diabetes Mellitus"


@pytest.mark.unit
@pytest.mark.parametrize(
    ("month_key", "expected"),
    [
        ("2025-03", "03/2025"),
        ("2025-3", "2025-3"),
        ("25-03", "25-03"),
        ("2025", "2025"),
        ("", "—"),
        (None, "—"),
    ],
)
def test_format_month_year(month_key, expected):
    assert formatters._format_month_year_pt(month_key) == expected


@pytest.mark.unit
@pytest.mark.parametrize(
    ("month_key", "expected"),
    [
        ("2025-01", "janeiro de 2025"),
        ("2025-02", "fevereiro de 2025"),
        ("2025-03", "março de 2025"),
        ("2025-04", "abril de 2025"),
        ("2025-05", "maio de 2025"),
        ("2025-06", "junho de 2025"),
        ("2025-07", "julho de 2025"),
        ("2025-08", "agosto de 2025"),
        ("2025-09", "setembro de 2025"),
        ("2025-10", "outubro de 2025"),
        ("2025-11", "novembro de 2025"),
        ("2025-12", "dezembro de 2025"),
        ("2025-13", "2025-13"),
        ("25-03", "25-03"),
        ("2025", "2025"),
        ("", "—"),
        (None, "—"),
    ],
)
def test_format_month_year_long(month_key, expected):
    assert formatters._format_month_year_long_pt(month_key) == expected


@pytest.mark.unit
def test_format_dates_as_long_month_and_semester_labels():
    reference = date(2024, 9, 12)
    assert formatters._format_date_month_year_long_pt(reference) == "setembro de 2024"
    assert formatters._format_full_date_long_pt(reference) == "12 de setembro de 2024"
    assert formatters._format_semestre_pt("1S/2024") == "1º Semestre/2024"
    assert formatters._format_semestre_pt(" 2s/2025 ") == "2º Semestre/2025"
    assert formatters._format_semestre_pt("2024-S1") == "2024-S1"
    assert formatters._format_semestre_pt("") == ""


@pytest.mark.unit
def test_semester_keys_and_distance():
    assert formatters._semester_key_from_date(date(2024, 1, 31)) == 202401
    assert formatters._semester_key_from_date(date(2024, 7, 1)) == 202402
    assert formatters._semester_key_from_label("1S/2024") == 202401
    assert formatters._semester_key_from_label("2s/2024") == 202402
    assert formatters._semester_key_from_label("2024-S1") == 202401
    assert formatters._semester_key_from_label("2024-S2-extra") == 202402
    assert formatters._semester_key_from_label("1S/invalid") is None
    assert formatters._semester_key_from_label("2024-Sx") is None
    assert formatters._semester_key_from_label("not-a-semester") is None
    assert formatters._semester_distance(202301, 202402) == 3
    assert formatters._semester_distance(202402, 202301) == -3


@pytest.mark.unit
def test_format_list_deduplicates_and_uses_portuguese_conjunction():
    with pytest.raises(
        RuntimeError,
        match="Lista de municipios obrigatoria para comparacao regional da Nota Tecnica",
    ):
        formatters._format_list_pt([])
    with pytest.raises(RuntimeError):
        formatters._format_list_pt(["", ""])

    assert formatters._format_list_pt(["Campinas"]) == "Campinas"
    assert formatters._format_list_pt(["Campinas", "Santos"]) == "Campinas e Santos"
    assert formatters._format_list_pt(
        ["Campinas", "Santos", "Campinas", "Ribeirão Preto", ""]
    ) == "Campinas, Santos e Ribeirão Preto"
