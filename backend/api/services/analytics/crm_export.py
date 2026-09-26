"""Exportação das autorizações disponíveis no Raio-X CRM por CNPJ (CSV e Excel)."""

import csv
import io
import re
from dataclasses import dataclass
from datetime import date, datetime
from typing import Iterator

import polars as pl
import xlsxwriter
import xlsxwriter.utility
from fastapi import HTTPException

from cache_producers.crm import sync_crm_raiox_tx
from data_cache import get_df_perfil_estabelecimento, scan_dados_medico


CSV_COLUMNS = (
    "CNPJ",
    "Data",
    "Hora",
    "Número da autorização",
    "CRM/UF",
    "Nome do médico",
    "Situação do CRM",
    "Valor pago (R$)",
)
CRM_LOCALIZADO = "Localizado"
CRM_NAO_LOCALIZADO = "Não localizado na base do CFM"

SOURCE_COLUMNS = (
    "dt_janela",
    "data_hora",
    "num_autorizacao",
    "id_medico",
    "valor_pago",
)
# Caracteres que o Excel/LibreOffice interpretam como início de fórmula (OWASP CSV Injection).
_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")
_DATA_HORA_PATTERN = r"^\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}"
_CHUNK_ROWS = 1000


def _data_inconsistente(detail: str) -> HTTPException:
    """Falha de integridade do cache: 500 com mensagem legível para o usuário."""
    return HTTPException(status_code=500, detail=detail)


_TITLE_CASE_BOUNDARY = re.compile(r"(^|\s|-|/)(\S)")


def _title_case(value: str | None) -> str | None:
    """Converte nomes em caixa alta para TitleCase, com a mesma regra do
    `formatTitleCase` do frontend (maiúscula após início, espaço, hífen ou barra)."""
    if value is None:
        return None
    return _TITLE_CASE_BOUNDARY.sub(lambda m: m.group(1) + m.group(2).upper(), str(value).lower())


def _csv_text(value: str | None) -> str:
    """Evita que texto vindo da base seja interpretado como fórmula ao abrir o CSV."""
    text = "" if value is None else str(value)
    if text.startswith(_FORMULA_PREFIXES) or text.lstrip().startswith(_FORMULA_PREFIXES[:4]):
        return "'" + text
    return text


def _csv_literal_text(value: str) -> str:
    """Força o Excel a tratar o valor como texto literal (preserva zeros à esquerda
    e dígitos de números longos). A fórmula gerada é sempre uma constante de string
    com aspas escapadas, portanto não executa conteúdo vindo da base."""
    return '="' + str(value).replace('"', '""') + '"'


def _format_data_br(iso_date: str) -> str:
    return f"{iso_date[8:10]}/{iso_date[5:7]}/{iso_date[0:4]}"


def _format_cnpj(cnpj: str) -> str:
    return f"{cnpj[:2]}.{cnpj[2:5]}.{cnpj[5:8]}/{cnpj[8:12]}-{cnpj[12:]}"


def _csv_chunks(rows: pl.DataFrame, cnpj: str, doctors: dict[str, str | None]) -> Iterator[bytes]:
    """Serializa linhas já validadas por `export_crm_raiox_csv`."""
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, delimiter=";", lineterminator="\r\n")

    def flush() -> bytes:
        payload = buffer.getvalue().encode("utf-8")
        buffer.seek(0)
        buffer.truncate(0)
        return payload

    yield b"\xef\xbb\xbf"
    writer.writerow(CSV_COLUMNS)
    yield flush()

    cnpj_formatado = _format_cnpj(cnpj)
    for index, row in enumerate(rows.iter_rows(named=True), start=1):
        data_hora = str(row["data_hora"])
        id_medico = str(row["id_medico"])
        localizado = id_medico in doctors
        writer.writerow((
            cnpj_formatado,
            _format_data_br(str(row["dt_janela"])[:10]),
            data_hora[11:19],
            _csv_literal_text(row["num_autorizacao"]),
            _csv_text(id_medico),
            _csv_text(_title_case(doctors.get(id_medico))),
            CRM_LOCALIZADO if localizado else CRM_NAO_LOCALIZADO,
            f"{float(row['valor_pago']):.2f}".replace(".", ","),
        ))
        if index % _CHUNK_ROWS == 0:
            yield flush()
    if buffer.tell():
        yield flush()


def _validate_rows(rows: pl.DataFrame) -> None:
    """Valida todo o recorte antes do streaming começar, para que falhas virem
    resposta HTTP com mensagem e nunca um CSV truncado."""
    null_counts = rows.select(pl.col(field).null_count() for field in SOURCE_COLUMNS).row(0)
    if any(null_counts):
        raise _data_inconsistente("Raio-X CRM contém autorização sem campo obrigatório para exportação.")
    if rows.filter(~pl.col("valor_pago").cast(pl.Float64).is_finite()).height:
        raise _data_inconsistente("Raio-X CRM contém valor pago inválido para exportação.")
    if rows.filter(~pl.col("data_hora").cast(pl.Utf8).str.contains(_DATA_HORA_PATTERN)).height:
        raise _data_inconsistente("Raio-X CRM contém data/hora inválida para exportação.")
    if rows.filter(~pl.col("dt_janela").cast(pl.Utf8).str.contains(r"^\d{4}-\d{2}-\d{2}")).height:
        raise _data_inconsistente("Raio-X CRM contém data inválida para exportação.")


def _load_doctor_names(ids_medicos: list[str]) -> dict[str, str | None]:
    medico_df = (
        scan_dados_medico()
        .filter(pl.col("id_medico").cast(pl.Utf8).is_in(ids_medicos))
        .select(["id_medico", "no_medico"])
        .collect()
    )
    doctors: dict[str, str | None] = {}
    for medico in medico_df.iter_rows(named=True):
        medico_id = str(medico["id_medico"])
        nome = medico["no_medico"]
        if medico_id in doctors and doctors[medico_id] != nome:
            raise _data_inconsistente(f"Cadastro médico inconsistente para CRM {medico_id}.")
        doctors[medico_id] = nome
    return doctors


@dataclass(frozen=True)
class _RaioxExport:
    cnpj: str
    rows: pl.DataFrame
    doctors: dict[str, str | None]
    inicio: str
    fim: str

    def filename(self, extensao: str) -> str:
        return f"crm_raiox_dias_alertados_{self.cnpj}_{self.inicio}_{self.fim}.{extensao}"


def _prepare_export(cnpj: str, data_inicio: date | None, data_fim: date | None) -> _RaioxExport:
    """Carrega, filtra e valida as autorizações do Raio-X; comum a CSV e Excel."""
    cnpj_limpo = "".join(ch for ch in cnpj if ch.isdigit())
    if len(cnpj_limpo) != 14:
        raise HTTPException(status_code=422, detail="CNPJ inválido para exportação.")
    if data_inicio and data_fim and data_inicio > data_fim:
        raise HTTPException(status_code=422, detail="O início do período não pode ser posterior ao fim.")

    result = sync_crm_raiox_tx(cnpj_limpo)
    if result.error:
        raise HTTPException(status_code=503, detail=f"Raio-X CRM indisponível: {result.error}")
    if result.df is None:
        raise HTTPException(status_code=503, detail="Cache do Raio-X CRM indisponível para exportação.")
    missing = set(SOURCE_COLUMNS) - set(result.df.columns)
    if missing:
        raise HTTPException(
            status_code=503,
            detail=f"Cache do Raio-X CRM sem colunas obrigatórias: {', '.join(sorted(missing))}. Sincronize o cache.",
        )

    rows = result.df
    if data_inicio:
        rows = rows.filter(pl.col("dt_janela") >= data_inicio.isoformat())
    if data_fim:
        rows = rows.filter(pl.col("dt_janela") <= data_fim.isoformat())
    if rows.is_empty():
        raise HTTPException(status_code=404, detail="Não há autorizações no Raio-X nos dias alertados deste período.")
    _validate_rows(rows)
    rows = rows.sort(["dt_janela", "data_hora", "num_autorizacao", "id_medico"])

    return _RaioxExport(
        cnpj=cnpj_limpo,
        rows=rows,
        doctors=_load_doctor_names(rows["id_medico"].cast(pl.Utf8).unique().to_list()),
        inicio=data_inicio.isoformat() if data_inicio else str(rows["dt_janela"].min())[:10],
        fim=data_fim.isoformat() if data_fim else str(rows["dt_janela"].max())[:10],
    )


def export_crm_raiox_csv(
    cnpj: str,
    data_inicio: date | None = None,
    data_fim: date | None = None,
) -> tuple[str, Iterator[bytes]]:
    """Exporta todas as autorizações guardadas no Raio-X (dias com alerta) em CSV."""
    export = _prepare_export(cnpj, data_inicio, data_fim)
    return export.filename("csv"), _csv_chunks(export.rows, export.cnpj, export.doctors)


# ─── Excel ──────────────────────────────────────────────────────────────────

_XLSX_MAX_ROWS = 1_000_000  # limite prático abaixo das 1.048.576 linhas do Excel

# Paleta institucional sóbria (azul-ardósia) usada em todas as abas.
_COR_TITULO = "#0F172A"
_COR_TEXTO = "#1E293B"
_COR_SUAVE = "#64748B"
_COR_CABECALHO = "#1E3A5F"
_COR_DESTAQUE = "#2563EB"
_COR_CARD = "#F1F5F9"
_COR_BORDA = "#CBD5E1"
_COR_ALERTA_FUNDO = "#FDECEC"
_COR_ALERTA_TEXTO = "#9B1C1C"
_FONTE = "Calibri"


@dataclass(frozen=True)
class _Farmacia:
    razao_social: str
    municipio: str
    uf: str


def _load_farmacia(cnpj: str) -> _Farmacia:
    perfil = get_df_perfil_estabelecimento()
    required = {"cnpj", "razao_social", "no_municipio", "uf"}
    missing = required - set(perfil.columns)
    if missing:
        raise _data_inconsistente(
            f"Perfil do estabelecimento sem colunas obrigatórias: {', '.join(sorted(missing))}."
        )
    linha = perfil.filter(pl.col("cnpj").cast(pl.Utf8) == cnpj).select(sorted(required))
    if linha.is_empty():
        raise HTTPException(status_code=404, detail="CNPJ não encontrado no perfil dos estabelecimentos.")
    dados = linha.row(0, named=True)
    if any(dados[campo] in (None, "") for campo in ("razao_social", "no_municipio", "uf")):
        raise _data_inconsistente("Perfil do estabelecimento sem razão social, município ou UF.")
    return _Farmacia(
        razao_social=_title_case(dados["razao_social"]),
        municipio=_title_case(dados["no_municipio"]),
        uf=str(dados["uf"]).upper(),
    )


def _iso_to_date(value: str) -> date:
    return date.fromisoformat(str(value)[:10])


def _formats(wb: xlsxwriter.Workbook) -> dict:
    base = {"font_name": _FONTE, "font_size": 10, "font_color": _COR_TEXTO, "valign": "vcenter"}

    def fmt(**extra):
        return wb.add_format({**base, **extra})

    return {
        "titulo": fmt(font_size=18, bold=True, font_color=_COR_TITULO),
        "subtitulo": fmt(font_size=11, bold=True, font_color=_COR_TEXTO),
        "meta": fmt(font_size=9, font_color=_COR_SUAVE),
        "faixa": wb.add_format({"bg_color": _COR_DESTAQUE}),
        "kpi_label": fmt(font_size=8, bold=True, font_color=_COR_SUAVE, bg_color=_COR_CARD,
                         top=2, top_color=_COR_DESTAQUE, text_wrap=True, indent=1),
        "kpi_valor": fmt(font_size=16, bold=True, font_color=_COR_TITULO, bg_color=_COR_CARD,
                         num_format="#,##0", indent=1, align="left"),
        "kpi_moeda": fmt(font_size=16, bold=True, font_color=_COR_TITULO, bg_color=_COR_CARD,
                         num_format='"R$" #,##0.00', indent=1, align="left"),
        "kpi_alerta": fmt(font_size=16, bold=True, font_color=_COR_ALERTA_TEXTO, bg_color=_COR_CARD,
                          num_format="#,##0", indent=1, align="left"),
        "cabecalho": fmt(bold=True, font_color="#FFFFFF", bg_color=_COR_CABECALHO, text_wrap=True,
                         border=1, border_color=_COR_CABECALHO, align="left", indent=1),
        "cabecalho_num": fmt(bold=True, font_color="#FFFFFF", bg_color=_COR_CABECALHO, text_wrap=True,
                             border=1, border_color=_COR_CABECALHO, align="right"),
        "texto": fmt(indent=1),
        "texto_forte": fmt(bold=True, indent=1),
        "data": fmt(num_format="dd/mm/yyyy", align="left", indent=1),
        "hora": fmt(num_format="hh:mm:ss", align="left", indent=1),
        "inteiro": fmt(num_format="#,##0"),
        "moeda": fmt(num_format='"R$" #,##0.00'),
        "pct": fmt(num_format="0.0%"),
        "alerta": wb.add_format({"bg_color": _COR_ALERTA_FUNDO, "font_color": _COR_ALERTA_TEXTO}),
        "total_label": fmt(bold=True, top=2, top_color=_COR_CABECALHO, indent=1),
        "total_vazio": fmt(top=2, top_color=_COR_CABECALHO),
        "total_inteiro": fmt(bold=True, num_format="#,##0", top=2, top_color=_COR_CABECALHO),
        "total_moeda": fmt(bold=True, num_format='"R$" #,##0.00', top=2, top_color=_COR_CABECALHO),
        "total_pct": fmt(bold=True, num_format="0.0%", top=2, top_color=_COR_CABECALHO),
        "nota": fmt(font_size=8, italic=True, font_color=_COR_SUAVE, text_wrap=True, valign="top"),
    }


def _write_header(ws, f: dict, titulo: str, farmacia: _Farmacia, export: _RaioxExport,
                  gerado_em: datetime, ultima_coluna: int) -> None:
    ws.set_row(0, 6)
    ws.merge_range(0, 0, 0, ultima_coluna, "", f["faixa"])
    ws.set_row(1, 30)
    ws.merge_range(1, 0, 1, ultima_coluna, titulo, f["titulo"])
    ws.merge_range(2, 0, 2, ultima_coluna, farmacia.razao_social, f["subtitulo"])
    periodo = f"{_iso_to_date(export.inicio):%d/%m/%Y} a {_iso_to_date(export.fim):%d/%m/%Y}"
    ws.merge_range(3, 0, 3, ultima_coluna,
                   f"CNPJ {_format_cnpj(export.cnpj)}  ·  {farmacia.municipio}/{farmacia.uf}", f["meta"])
    ws.merge_range(4, 0, 4, ultima_coluna,
                   f"Período: {periodo}  ·  Gerado em {gerado_em:%d/%m/%Y %H:%M} pelo Sentinela", f["meta"])


def _write_total_row(ws, f: dict, row: int, first_data: int, last_data: int, specs: list) -> None:
    """Linha de total fora da tabela, com SUBTOTAL (respeita filtros) e valor já calculado,
    para que leitores sem recálculo (visualizadores, LibreOffice) exibam o total correto."""
    ws.set_row(row, 20)
    for col, spec in enumerate(specs):
        kind = spec[0]
        if kind == "label":
            ws.write_string(row, col, spec[1], f["total_label"])
        elif kind == "vazio":
            ws.write_blank(row, col, None, f["total_vazio"])
        else:
            funcao = {"soma": 109, "contagem": 103}[kind]
            coluna = xlsxwriter.utility.xl_col_to_name(col)
            ws.write_formula(
                row, col, f"=SUBTOTAL({funcao},{coluna}{first_data + 1}:{coluna}{last_data + 1})",
                f[spec[2]], spec[1],
            )


def _setup_page(ws, farmacia_cnpj: str, header_row: int) -> None:
    ws.hide_gridlines(2)
    ws.set_landscape()
    ws.set_paper(9)  # A4
    ws.fit_to_pages(1, 0)
    ws.set_margins(left=0.4, right=0.4, top=0.6, bottom=0.6)
    ws.repeat_rows(header_row)
    ws.set_header(f"&L&8Sentinela · Raio-X CRM&R&8CNPJ {farmacia_cnpj}")
    ws.set_footer("&L&8Autorizações dos dias alertados&R&8Página &P de &N")


def _sheet_autorizacoes(wb, f, export: _RaioxExport, farmacia: _Farmacia, gerado_em: datetime) -> None:
    ws = wb.add_worksheet("Autorizações")
    colunas = [
        ("Data", 13, f["data"]),
        ("Hora", 11, f["hora"]),
        ("Nº da autorização", 24, f["texto"]),
        ("CRM/UF", 14, f["texto"]),
        ("Nome do médico", 42, f["texto"]),
        ("Situação do CRM", 30, f["texto"]),
        ("Valor pago", 16, f["moeda"]),
    ]
    ultima = len(colunas) - 1
    for idx, (_, largura, _) in enumerate(colunas):
        ws.set_column(idx, idx, largura)
    _write_header(ws, f, "Raio-X CRM · Autorizações dos dias alertados", farmacia, export, gerado_em, ultima)

    rows = export.rows
    ids = rows["id_medico"].cast(pl.Utf8)
    nao_localizados = sorted({i for i in ids.unique().to_list() if i not in export.doctors})
    kpis = [
        (0, 1, "AUTORIZAÇÕES", rows.height, f["kpi_valor"]),
        (2, 2, "DIAS ALERTADOS", rows["dt_janela"].n_unique(), f["kpi_valor"]),
        (3, 3, "MÉDICOS DISTINTOS", ids.n_unique(), f["kpi_valor"]),
        (4, 4, "CRMs NÃO LOCALIZADOS NA BASE DO CFM", len(nao_localizados),
         f["kpi_alerta"] if nao_localizados else f["kpi_valor"]),
        (5, 6, "VALOR TOTAL PAGO", float(rows["valor_pago"].sum()), f["kpi_moeda"]),
    ]
    ws.set_row(6, 26)
    ws.set_row(7, 30)
    for c1, c2, label, valor, fmt_valor in kpis:
        if c1 == c2:
            ws.write_string(6, c1, label, f["kpi_label"])
            ws.write_number(7, c1, valor, fmt_valor)
        else:
            ws.merge_range(6, c1, 6, c2, label, f["kpi_label"])
            ws.merge_range(7, c1, 7, c2, valor, fmt_valor)

    header_row = 9
    ws.set_row(header_row, 22)
    data = []
    for row in rows.iter_rows(named=True):
        id_medico = str(row["id_medico"])
        data_hora = datetime.fromisoformat(str(row["data_hora"])[:19].replace("T", " "))
        data.append([
            _iso_to_date(row["dt_janela"]),
            data_hora.time(),
            str(row["num_autorizacao"]),
            id_medico,
            _title_case(export.doctors.get(id_medico)) or "",
            CRM_LOCALIZADO if id_medico in export.doctors else CRM_NAO_LOCALIZADO,
            float(row["valor_pago"]),
        ])
    ultima_linha = header_row + len(data)
    ws.add_table(header_row, 0, ultima_linha, ultima, {
        "name": "Autorizacoes",
        "style": "Table Style Light 1",
        "data": data,
        "columns": [
            {"header": "Data", "format": f["data"], "header_format": f["cabecalho"]},
            {"header": "Hora", "format": f["hora"], "header_format": f["cabecalho"]},
            {"header": "Nº da autorização", "format": f["texto"], "header_format": f["cabecalho"]},
            {"header": "CRM/UF", "format": f["texto"], "header_format": f["cabecalho"]},
            {"header": "Nome do médico", "format": f["texto"], "header_format": f["cabecalho"]},
            {"header": "Situação do CRM", "format": f["texto"], "header_format": f["cabecalho"]},
            {"header": "Valor pago", "format": f["moeda"], "header_format": f["cabecalho_num"]},
        ],
    })
    _write_total_row(ws, f, ultima_linha + 1, header_row + 1, ultima_linha, [
        ("label", "Total"), ("vazio",), ("contagem", len(data), "total_inteiro"), ("vazio",), ("vazio",),
        ("vazio",), ("soma", float(rows["valor_pago"].sum()), "total_moeda"),
    ])
    ultima_linha += 1
    ws.conditional_format(header_row + 1, 0, ultima_linha - 1, ultima, {
        "type": "formula",
        "criteria": f'=$F{header_row + 2}="{CRM_NAO_LOCALIZADO}"',
        "format": f["alerta"],
    })
    ws.freeze_panes(header_row + 1, 0)
    ws.set_row(ultima_linha + 2, 30)
    ws.merge_range(ultima_linha + 2, 0, ultima_linha + 2, ultima,
                   "Inclui todas as autorizações dos dias com alerta de Volume Atípico ou de Autorizações em "
                   "Sequência (Único CRM / Múltiplos CRMs) guardadas no Raio-X do Sentinela. Linhas destacadas "
                   "indicam CRM não localizado na base do CFM.", f["nota"])
    _setup_page(ws, _format_cnpj(export.cnpj), header_row)


def _sheet_por_dia(wb, f, export: _RaioxExport, farmacia: _Farmacia, gerado_em: datetime) -> None:
    ws = wb.add_worksheet("Por dia")
    larguras = [14, 16, 18, 18, 18]
    for idx, largura in enumerate(larguras):
        ws.set_column(idx, idx, largura)
    ultima = len(larguras) - 1
    _write_header(ws, f, "Resumo por dia alertado", farmacia, export, gerado_em, ultima)

    resumo = (
        export.rows
        .group_by("dt_janela")
        .agg([
            pl.len().alias("qtd"),
            pl.col("id_medico").n_unique().alias("medicos"),
            pl.col("valor_pago").sum().alias("valor"),
        ])
        .sort("dt_janela")
    )
    total_valor = float(export.rows["valor_pago"].sum())
    data = [
        [
            _iso_to_date(r["dt_janela"]),
            int(r["qtd"]),
            int(r["medicos"]),
            float(r["valor"]),
            (float(r["valor"]) / total_valor) if total_valor else 0.0,
        ]
        for r in resumo.iter_rows(named=True)
    ]
    header_row = 6
    ws.set_row(header_row, 22)
    ultima_linha = header_row + len(data)
    ws.add_table(header_row, 0, ultima_linha, ultima, {
        "name": "ResumoPorDia",
        "style": "Table Style Light 1",
        "data": data,
        "columns": [
            {"header": "Data", "format": f["data"], "header_format": f["cabecalho"]},
            {"header": "Autorizações", "format": f["inteiro"], "header_format": f["cabecalho_num"]},
            {"header": "Médicos distintos", "format": f["inteiro"], "header_format": f["cabecalho_num"]},
            {"header": "Valor pago", "format": f["moeda"], "header_format": f["cabecalho_num"]},
            {"header": "% do valor", "format": f["pct"], "header_format": f["cabecalho_num"]},
        ],
    })
    _write_total_row(ws, f, ultima_linha + 1, header_row + 1, ultima_linha, [
        ("label", "Total"), ("soma", export.rows.height, "total_inteiro"), ("vazio",),
        ("soma", total_valor, "total_moeda"), ("soma", 1.0 if total_valor else 0.0, "total_pct"),
    ])
    ws.conditional_format(header_row + 1, 3, ultima_linha, 3, {
        "type": "data_bar", "bar_color": "#BFDBFE", "bar_solid": True,
    })
    ws.freeze_panes(header_row + 1, 0)
    _setup_page(ws, _format_cnpj(export.cnpj), header_row)


def _sheet_por_medico(wb, f, export: _RaioxExport, farmacia: _Farmacia, gerado_em: datetime) -> None:
    ws = wb.add_worksheet("Por médico")
    larguras = [14, 40, 30, 14, 15, 18, 13]
    for idx, largura in enumerate(larguras):
        ws.set_column(idx, idx, largura)
    ultima = len(larguras) - 1
    _write_header(ws, f, "Resumo por médico prescritor", farmacia, export, gerado_em, ultima)

    resumo = (
        export.rows
        .with_columns(pl.col("id_medico").cast(pl.Utf8))
        .group_by("id_medico")
        .agg([
            pl.col("dt_janela").n_unique().alias("dias"),
            pl.len().alias("qtd"),
            pl.col("valor_pago").sum().alias("valor"),
        ])
        .sort(["valor", "id_medico"], descending=[True, False])
    )
    total_valor = float(export.rows["valor_pago"].sum())
    data = []
    for r in resumo.iter_rows(named=True):
        id_medico = r["id_medico"]
        data.append([
            id_medico,
            _title_case(export.doctors.get(id_medico)) or "",
            CRM_LOCALIZADO if id_medico in export.doctors else CRM_NAO_LOCALIZADO,
            int(r["dias"]),
            int(r["qtd"]),
            float(r["valor"]),
            (float(r["valor"]) / total_valor) if total_valor else 0.0,
        ])
    header_row = 6
    ws.set_row(header_row, 22)
    ultima_linha = header_row + len(data)
    ws.add_table(header_row, 0, ultima_linha, ultima, {
        "name": "ResumoPorMedico",
        "style": "Table Style Light 1",
        "data": data,
        "columns": [
            {"header": "CRM/UF", "format": f["texto_forte"], "header_format": f["cabecalho"]},
            {"header": "Nome do médico", "format": f["texto"], "header_format": f["cabecalho"]},
            {"header": "Situação do CRM", "format": f["texto"], "header_format": f["cabecalho"]},
            {"header": "Dias", "format": f["inteiro"], "header_format": f["cabecalho_num"]},
            {"header": "Autorizações", "format": f["inteiro"], "header_format": f["cabecalho_num"]},
            {"header": "Valor pago", "format": f["moeda"], "header_format": f["cabecalho_num"]},
            {"header": "% do valor", "format": f["pct"], "header_format": f["cabecalho_num"]},
        ],
    })
    _write_total_row(ws, f, ultima_linha + 1, header_row + 1, ultima_linha, [
        ("label", "Total"), ("vazio",), ("vazio",), ("vazio",),
        ("soma", export.rows.height, "total_inteiro"), ("soma", total_valor, "total_moeda"),
        ("soma", 1.0 if total_valor else 0.0, "total_pct"),
    ])
    ws.conditional_format(header_row + 1, 0, ultima_linha, ultima, {
        "type": "formula",
        "criteria": f'=$C{header_row + 2}="{CRM_NAO_LOCALIZADO}"',
        "format": f["alerta"],
    })
    ws.conditional_format(header_row + 1, 5, ultima_linha, 5, {
        "type": "data_bar", "bar_color": "#BFDBFE", "bar_solid": True,
    })
    ws.freeze_panes(header_row + 1, 0)
    _setup_page(ws, _format_cnpj(export.cnpj), header_row)


def export_crm_raiox_xlsx(
    cnpj: str,
    data_inicio: date | None = None,
    data_fim: date | None = None,
) -> tuple[str, bytes]:
    """Exporta as autorizações do Raio-X em uma pasta de trabalho Excel formatada,
    com abas de detalhe, resumo por dia e resumo por médico."""
    export = _prepare_export(cnpj, data_inicio, data_fim)
    if export.rows.height > _XLSX_MAX_ROWS:
        raise HTTPException(
            status_code=413,
            detail="O período tem autorizações demais para o Excel; reduza o período ou exporte em CSV.",
        )
    farmacia = _load_farmacia(export.cnpj)
    gerado_em = datetime.now()

    buffer = io.BytesIO()
    # strings_to_*: texto vindo da base nunca vira fórmula, número ou link.
    wb = xlsxwriter.Workbook(buffer, {
        "in_memory": True,
        "strings_to_formulas": False,
        "strings_to_numbers": False,
        "strings_to_urls": False,
    })
    wb.set_properties({
        "title": "Raio-X CRM · Autorizações dos dias alertados",
        "subject": f"CNPJ {_format_cnpj(export.cnpj)} · {farmacia.razao_social}",
        "author": "Sentinela · CGU",
        "company": "Controladoria-Geral da União",
        "comments": f"Período {export.inicio} a {export.fim}",
    })
    f = _formats(wb)
    _sheet_autorizacoes(wb, f, export, farmacia, gerado_em)
    _sheet_por_dia(wb, f, export, farmacia, gerado_em)
    _sheet_por_medico(wb, f, export, farmacia, gerado_em)
    wb.close()
    return export.filename("xlsx"), buffer.getvalue()
