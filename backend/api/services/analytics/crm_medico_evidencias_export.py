"""Excel das evidencias de um CRM (painel "Evidencias" do historico em /analises).

Tres abas, uma por tipo de evidencia, com o mesmo visual das planilhas CRM
(crm_export): cabecalho do medico, tabela com filtros e linha de total.
"""

import io
from datetime import date, datetime
from typing import Optional

import polars as pl
import xlsxwriter

from .crm_analysis import _period_bounds
from .crm_export import _format_cnpj, _formats, _setup_page, _title_case, _write_total_row
from .crm_medico_evidencias import evidencias_do_medico, nome_do_medico

SEVERIDADE_ROTULO = {1: "Alta", 2: "Grave", 3: "Crítica", 4: "Extrema"}
_LINHA_TABELA = 7  # cabecalho da planilha nas linhas 0 a 5, tabela a partir da 7


def _cabecalho(ws, f: dict, titulo: str, medico: str, filtro: str, inicio: date, fim: date,
               gerado_em: datetime, ultima_coluna: int) -> None:
    ws.set_row(0, 6)
    ws.merge_range(0, 0, 0, ultima_coluna, "", f["faixa"])
    ws.set_row(1, 30)
    ws.merge_range(1, 0, 1, ultima_coluna, titulo, f["titulo"])
    ws.merge_range(2, 0, 2, ultima_coluna, medico, f["subtitulo"])
    ws.merge_range(3, 0, 3, ultima_coluna, filtro, f["meta"])
    ws.merge_range(4, 0, 4, ultima_coluna,
                   f"Período: {inicio:%d/%m/%Y} a {fim:%d/%m/%Y}  ·  Gerado em {gerado_em:%d/%m/%Y %H:%M} pelo Sentinela",
                   f["meta"])


def _tabela(ws, f: dict, colunas: list[tuple[str, int, str]], linhas: list[list], total: list) -> None:
    """colunas: (titulo, largura, formato). Escreve cabecalho, linhas, filtro e total."""
    for c, (titulo, largura, _fmt) in enumerate(colunas):
        ws.set_column(c, c, largura)
        ws.write_string(_LINHA_TABELA, c, titulo, f["cabecalho_num"] if _fmt in ("inteiro", "moeda", "decimal") else f["cabecalho"])
    ws.set_row(_LINHA_TABELA, 30)
    for r, valores in enumerate(linhas, start=_LINHA_TABELA + 1):
        for c, valor in enumerate(valores):
            fmt = f[colunas[c][2]]
            if valor is None:
                ws.write_blank(r, c, None, fmt)
            elif isinstance(valor, datetime):
                ws.write_datetime(r, c, valor, fmt)
            elif isinstance(valor, date):
                ws.write_datetime(r, c, datetime(valor.year, valor.month, valor.day), fmt)
            elif isinstance(valor, (int, float)):
                ws.write_number(r, c, valor, fmt)
            else:
                ws.write_string(r, c, str(valor), fmt)
    ultima = _LINHA_TABELA + max(len(linhas), 1)
    ws.autofilter(_LINHA_TABELA, 0, ultima, len(colunas) - 1)
    ws.freeze_panes(_LINHA_TABELA + 1, 0)
    if linhas:
        _write_total_row(ws, f, ultima + 1, _LINHA_TABELA + 1, ultima, total)
    else:
        ws.write_string(_LINHA_TABELA + 1, 0, "Nenhuma evidência no período.", f["nota"])


def _soma(df: pl.DataFrame, coluna: str) -> float:
    return float(df.get_column(coluna).sum() or 0) if df.height else 0.0


def _data(valor: str) -> date:
    return date.fromisoformat(str(valor)[:10])


def export_crm_medico_evidencias_xlsx(
    id_medico: str,
    data_inicio: Optional[date] = None,
    data_fim: Optional[date] = None,
    id_cnpj: Optional[int] = None,
) -> tuple[str, bytes]:
    """Pasta de trabalho com as tres evidencias do CRM no periodo (e farmacia)."""
    id_medico = id_medico.strip()
    inicio, fim = _period_bounds(data_inicio, data_fim)
    ev = evidencias_do_medico(id_medico, inicio, fim, id_cnpj)
    nome = nome_do_medico(id_medico)
    medico = f"{_title_case(nome) if nome else 'Médico não localizado no CFM'}  ·  CRM {id_medico}"
    if id_cnpj is None:
        filtro = "Todas as farmácias do médico"
    else:
        cad = ev.unico.vstack(ev.multiplos.select(ev.unico.columns)) if ev.multiplos.height else ev.unico
        linha = cad.filter(pl.col("id_cnpj") == id_cnpj).head(1)
        filtro = (f"Farmácia: {linha.item(0, 'razao_social')} · CNPJ {_format_cnpj(linha.item(0, 'cnpj'))}"
                  if linha.height else f"Farmácia filtrada (id {id_cnpj})")
    gerado_em = datetime.now()

    buffer = io.BytesIO()
    wb = xlsxwriter.Workbook(buffer, {
        "in_memory": True, "strings_to_formulas": False, "strings_to_numbers": False, "strings_to_urls": False,
    })
    wb.set_properties({
        "title": "Evidências do CRM",
        "subject": medico,
        "author": "Sentinela · CGU",
        "company": "Controladoria-Geral da União",
        "comments": f"Período {inicio} a {fim}",
    })
    f = _formats(wb)
    f["decimal"] = wb.add_format({"font_name": "Calibri", "font_size": 10, "num_format": "#,##0.0"})
    f["datahora"] = wb.add_format({"font_name": "Calibri", "font_size": 10, "num_format": "hh:mm", "align": "left"})

    abas = (
        ("Sequências único CRM", "Autorizações em sequência · único CRM", ev.unico.sort(["dt_ini_hora", "id_cnpj"]), [
            ("Data", 12, "data"), ("Início", 9, "datahora"), ("Fim", 9, "datahora"), ("Farmácia", 40, "texto"),
            ("CNPJ", 20, "texto"), ("Município/UF", 26, "texto"), ("Autorizações", 13, "inteiro"),
            ("Janela (min)", 12, "inteiro"), ("Taxa/hora", 11, "decimal"), ("Severidade", 12, "texto"),
        ], lambda r: [
            _data(r["dt"]), r["dt_ini_hora"], r["dt_fim_hora"], r["razao_social"], _format_cnpj(r["cnpj"]),
            f"{r['municipio']}/{r['uf']}", r["nu_autorizacoes"], r["nu_minutos"], r["taxa_hora"],
            SEVERIDADE_ROTULO[r["id_severidade"]],
        ], lambda d: [("label", "Total"), ("contagem", d.height, "total_inteiro"), ("vazio",), ("vazio",), ("vazio",),
                      ("vazio",), ("soma", _soma(d, "nu_autorizacoes"), "total_inteiro"), ("vazio",), ("vazio",), ("vazio",)]),
        ("Sequências múltiplos CRMs", "Autorizações em sequência · múltiplos CRMs", ev.multiplos.sort(["dt_ini_hora", "id_cnpj"]), [
            ("Data", 12, "data"), ("Início", 9, "datahora"), ("Fim", 9, "datahora"), ("Farmácia", 40, "texto"),
            ("CNPJ", 20, "texto"), ("Município/UF", 26, "texto"), ("Autorizações do CRM", 13, "inteiro"),
            ("Autorizações na janela", 13, "inteiro"), ("CRMs na janela", 10, "inteiro"),
            ("Janela (min)", 12, "inteiro"), ("Taxa/hora", 11, "decimal"), ("Severidade", 12, "texto"),
        ], lambda r: [
            _data(r["dt"]), r["dt_ini_hora"], r["dt_fim_hora"], r["razao_social"], _format_cnpj(r["cnpj"]),
            f"{r['municipio']}/{r['uf']}", r["nu_autorizacoes_crm"], r["nu_autorizacoes_total"], r["nu_crms"],
            r["nu_minutos"], r["taxa_hora"], SEVERIDADE_ROTULO[r["id_severidade"]],
        ], lambda d: [("label", "Total"), ("contagem", d.height, "total_inteiro"), ("vazio",), ("vazio",), ("vazio",),
                      ("vazio",), ("soma", _soma(d, "nu_autorizacoes_crm"), "total_inteiro"),
                      ("soma", _soma(d, "nu_autorizacoes_total"), "total_inteiro"), ("vazio",), ("vazio",), ("vazio",),
                      ("vazio",)]),
        ("Farmácias distantes", "Farmácias distantes no mesmo mês", ev.distancia.sort(["distancia_km", "competencia"], descending=[True, False]), [
            ("Mês", 9, "texto"), ("Farmácia A", 36, "texto"), ("CNPJ A", 20, "texto"), ("Município/UF A", 24, "texto"),
            ("Prescrições A", 12, "inteiro"), ("Farmácia B", 36, "texto"), ("CNPJ B", 20, "texto"),
            ("Município/UF B", 24, "texto"), ("Prescrições B", 12, "inteiro"), ("Distância (km)", 13, "inteiro"),
            ("Valor autorizado", 16, "moeda"),
        ], lambda r: [
            f"{r['competencia'] % 100:02d}/{r['competencia'] // 100}", r["razao_social_a"], _format_cnpj(r["cnpj_a"]),
            f"{r['no_municipio_a']}/{r['sg_uf_a']}", r["nu_prescricoes_a"], r["razao_social_b"], _format_cnpj(r["cnpj_b"]),
            f"{r['no_municipio_b']}/{r['sg_uf_b']}", r["nu_prescricoes_b"], round(r["distancia_km"]),
            r["vl_autorizacoes_total"],
        ], lambda d: [("label", "Total"), ("contagem", d.height, "total_inteiro"), ("vazio",), ("vazio",),
                      ("soma", _soma(d, "nu_prescricoes_a"), "total_inteiro"), ("vazio",), ("vazio",), ("vazio",),
                      ("soma", _soma(d, "nu_prescricoes_b"), "total_inteiro"), ("vazio",),
                      ("soma", _soma(d, "vl_autorizacoes_total"), "total_moeda")]),
    )
    for nome_aba, titulo, df, colunas, linha_de, total in abas:
        ws = wb.add_worksheet(nome_aba)
        _setup_page(ws, id_medico, _LINHA_TABELA, secao="Evidências do CRM", rodape=titulo)
        _cabecalho(ws, f, titulo, medico, filtro, inicio, fim, gerado_em, len(colunas) - 1)
        _tabela(ws, f, colunas, [linha_de(r) for r in df.iter_rows(named=True)], total(df))
    wb.close()
    arquivo = f"crm_evidencias_{id_medico.replace('/', '_')}_{inicio:%Y%m}_{fim:%Y%m}.xlsx"
    return arquivo, buffer.getvalue()
