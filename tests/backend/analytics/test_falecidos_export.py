import csv
import io
import zipfile
from datetime import date
from xml.etree import ElementTree

import polars as pl
import pytest
from fastapi import HTTPException

from api.schemas.analytics import FalecidosSummarySchema
from api.services.analytics import falecidos_export as export_module
from api.services.analytics.falecidos import FalecidosDados
from api.services.analytics.crm_export import _Farmacia


CNPJ_ALVO = "12345678000190"
CNPJ_OUTRA_A = "98765432000110"
CNPJ_OUTRA_B = "11222333000181"


def _transacoes():
    return pl.DataFrame(
        {
            "cpf": ["00000000123", "00000000456"],
            "nome_falecido": ["MARIA DA SILVA", "=1+1"],
            "dt_nascimento": [date(1940, 2, 3), date(1945, 4, 5)],
            "dt_obito": [date(2020, 1, 1), date(2020, 2, 1)],
            "fonte_obito": ["SISOBI", None],
            "municipio_falecido": ["SAO PAULO", None],
            "uf_falecido": ["SP", None],
            "num_autorizacao": ["000000000001", "A-2"],
            "data_autorizacao": [date(2020, 1, 8), date(2021, 2, 1)],
            "qtd_itens_na_autorizacao": [2, 1],
            "valor_total_autorizacao": [125.50, 75.25],
            "dias_apos_obito": [7, 366],
            "outros": [
                f"{CNPJ_OUTRA_A} | Goiania/GO; {CNPJ_OUTRA_B} | Rio de Janeiro/RJ",
                f"{CNPJ_OUTRA_B} | Rio de Janeiro/RJ",
            ],
        }
    )


def _outras():
    return pl.DataFrame(
        {
            "cpf": ["00000000123", "00000000456"],
            "cnpj": [CNPJ_OUTRA_A, CNPJ_OUTRA_B],
            "razao_social": ["FARMACIA GOIANIA", "REDE RIO"],
            "municipio": ["Goiania", "Rio de Janeiro"],
            "uf": ["GO", "RJ"],
        }
    )


def _dados(transacoes=None, outras=None, faturamento=1000.0):
    transacoes = _transacoes() if transacoes is None else transacoes
    outras = _outras() if outras is None else outras
    return FalecidosDados(
        cnpj=CNPJ_ALVO,
        tem_historico=True,
        summary=FalecidosSummarySchema(
            cpfs_distintos=2,
            total_autorizacoes=2,
            valor_total=200.75,
            media_dias=186.5,
            max_dias=366,
            pct_faturamento=0.20075,
            cpfs_multi_cnpj=2,
            pct_multi_cnpj=1.0,
        ),
        transacoes=transacoes,
        outras=outras,
        ranking=export_module.ranking_outras_farmacias(outras),
        faturamento_periodo=faturamento,
    )


@pytest.fixture
def setup_export(monkeypatch):
    dados = _dados()
    monkeypatch.setattr(export_module, "carregar_falecidos", lambda *args: dados)
    monkeypatch.setattr(
        export_module,
        "_load_farmacia",
        lambda cnpj: _Farmacia("Farmacia Alvo", "Sao Paulo", "SP"),
    )
    return dados


@pytest.mark.parametrize(
    ("dias", "esperado"),
    [
        (0, "Até 7 dias"),
        (7, "Até 7 dias"),
        (8, "8 a 15 dias"),
        (15, "8 a 15 dias"),
        (16, "16 a 30 dias"),
        (30, "16 a 30 dias"),
        (31, "31 a 60 dias"),
        (60, "31 a 60 dias"),
        (61, "61 a 120 dias"),
        (120, "61 a 120 dias"),
        (121, "121 a 240 dias"),
        (240, "121 a 240 dias"),
        (241, "241 dias a 1 ano"),
        (365, "241 dias a 1 ano"),
        (366, "1 a 2 anos"),
        (730, "1 a 2 anos"),
        (731, "2 a 3 anos"),
        (1095, "2 a 3 anos"),
        (1096, "Mais de 3 anos"),
    ],
)
def test_faixa_uses_inclusive_day_boundaries(dias, esperado):
    assert export_module._faixa(dias) == esperado


def test_format_cpf_qtd_outras_and_line_normalization():
    assert export_module._format_cpf("123") == "000.000.001-23"
    assert export_module._qtd_outras(None) == 0
    assert export_module._qtd_outras("") == 0
    assert export_module._qtd_outras("farmacia A; farmacia B") == 2
    linha = export_module._linha(_transacoes().row(0, named=True))
    assert linha[0] == "000.000.001-23"
    assert linha[1] == "Maria Da Silva"
    assert linha[7] == "000000000001"
    assert linha[12] == "Até 7 dias"
    assert linha[13] == 2
    assert linha[14].startswith(CNPJ_OUTRA_A)


def test_line_keeps_optional_missing_text_fields_empty():
    row = _transacoes().row(1, named=True)
    linha = export_module._linha(row)
    assert linha[1] == "=1+1"
    assert linha[4] == ""
    assert linha[5] == ""
    assert linha[6] == ""
    assert linha[13] == 1


def test_csv_value_formats_dates_numbers_and_formula_safe_text():
    assert export_module._csv_valor(None, "texto") == ""
    assert export_module._csv_valor(date(2024, 3, 9), "data") == "09/03/2024"
    assert export_module._csv_valor(12.5, "moeda") == "12,50"
    assert export_module._csv_valor(12, "inteiro") == "12"
    assert export_module._csv_valor("=1+1", "texto") == "'=1+1"


def test_prepare_rejects_reversed_period_before_loading(monkeypatch):
    monkeypatch.setattr(export_module, "carregar_falecidos", lambda *args: pytest.fail("não deveria carregar"))
    with pytest.raises(HTTPException) as error:
        export_module._preparar(CNPJ_ALVO, date(2024, 2, 1), date(2024, 1, 1), None)
    assert error.value.status_code == 422


@pytest.mark.parametrize(
    ("transacoes", "faturamento", "status", "mensagem"),
    [
        (pl.DataFrame(), 100.0, 404, "Não há autorizações"),
        (_transacoes(), None, 500, "Faturamento do período não calculado"),
    ],
)
def test_prepare_rejects_empty_or_incomplete_export_data(
    monkeypatch, transacoes, faturamento, status, mensagem
):
    dados = _dados(transacoes=transacoes, faturamento=faturamento)
    monkeypatch.setattr(export_module, "carregar_falecidos", lambda *args: dados)
    with pytest.raises(HTTPException, match=mensagem) as error:
        export_module._preparar(CNPJ_ALVO, None, None, None)
    assert error.value.status_code == status


def test_prepare_rejects_filter_outside_coincidence_network(setup_export):
    with pytest.raises(HTTPException, match="não está na rede de coincidência") as error:
        export_module._preparar(CNPJ_ALVO, None, None, "00.000.000/0000-00")
    assert error.value.status_code == 422


def test_prepare_normalizes_cnpj_period_defaults_and_filters_matching_cpf(setup_export):
    export = export_module._preparar(CNPJ_ALVO, None, None, "98.765.432/0001-10")
    assert export.cnpj == CNPJ_ALVO
    assert export.inicio == "2020-01-08"
    assert export.fim == "2021-02-01"
    assert export.filtro == "CPFs que também compraram em 98.765.432/0001-10 — Farmacia Goiania (Goiania/GO)"
    assert export.transacoes.get_column("cpf").to_list() == ["00000000123"]
    assert export.ranking.get_column("cnpj").to_list() == [CNPJ_OUTRA_A]
    assert export.total_cpfs_farmacia == 2


def test_prepare_respects_explicit_dates_and_keeps_all_matching_rows(setup_export):
    export = export_module._preparar(CNPJ_ALVO, date(2020, 1, 1), date(2022, 1, 1), None)
    assert export.inicio == "2020-01-01"
    assert export.fim == "2022-01-01"
    assert export.filtro is None
    assert export.transacoes.height == 2
    assert export.ranking.height == 2


def test_csv_export_has_bom_headers_and_escaped_transaction_text(setup_export):
    filename, chunks = export_module.export_falecidos_csv(CNPJ_ALVO)
    content = b"".join(chunks)
    assert filename == "falecidos_12345678000190_202001-202102.csv"
    assert content.startswith(b"\xef\xbb\xbf")
    rows = list(csv.reader(io.StringIO(content.decode("utf-8-sig"), newline=""), delimiter=";"))
    assert rows[0][0] == "CNPJ da farmácia"
    assert rows[0][1] == "CPF"
    assert rows[1][0] == "12.345.678/0001-90"
    assert rows[1][1] == "000.000.001-23"
    assert rows[1][11] == "125,50"
    assert rows[2][2] == "'=1+1"


def _shared_text_values(workbook_bytes):
    with zipfile.ZipFile(io.BytesIO(workbook_bytes)) as archive:
        xml = ElementTree.fromstring(archive.read("xl/sharedStrings.xml"))
    ns = {"x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    return ["".join(node.itertext()) for node in xml.findall("x:si", ns)]


def test_xlsx_export_builds_four_sheets_and_keeps_database_text_literal(setup_export):
    filename, content = export_module.export_falecidos_xlsx(CNPJ_ALVO)
    assert filename == "falecidos_12345678000190_202001-202102.xlsx"
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        workbook_xml = ElementTree.fromstring(archive.read("xl/workbook.xml"))
    ns = {"x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    sheets = [node.attrib["name"] for node in workbook_xml.findall("x:sheets/x:sheet", ns)]
    assert sheets == ["Autorizações", "Resumo por CPF", "Outras farmácias", "Critérios"]
    assert "=1+1" in _shared_text_values(content)


def test_xlsx_export_renders_empty_other_pharmacy_ranking(monkeypatch):
    transacoes = _transacoes().head(1).with_columns(pl.lit(None, dtype=pl.Utf8).alias("outros"))
    dados = _dados(transacoes=transacoes, outras=pl.DataFrame())
    monkeypatch.setattr(export_module, "carregar_falecidos", lambda *args: dados)
    monkeypatch.setattr(
        export_module,
        "_load_farmacia",
        lambda cnpj: _Farmacia("Farmacia Alvo", "Sao Paulo", "SP"),
    )
    _, content = export_module.export_falecidos_xlsx(CNPJ_ALVO)
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        assert "xl/worksheets/sheet3.xml" in archive.namelist()
        sheet = ElementTree.fromstring(archive.read("xl/worksheets/sheet3.xml"))
    ns = {"x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    assert sheet.find(".//x:mergeCell", ns) is not None


def test_xlsx_export_records_applied_pharmacy_filter(setup_export):
    _, content = export_module.export_falecidos_xlsx(CNPJ_ALVO, outro_cnpj=CNPJ_OUTRA_A)
    shared_text = " ".join(_shared_text_values(content))
    assert "CPFs que também compraram em 98.765.432/0001-10" in shared_text
    assert "1 de 2 CPFs" in shared_text
