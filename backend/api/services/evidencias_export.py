"""Exportação em Excel da cesta de evidências de uma farmácia."""

import io
from datetime import date, datetime
from typing import Any, Dict, List

import xlsxwriter
from fastapi import HTTPException

from .analytics.crm_export import _format_cnpj, _formats, _load_farmacia
from .evidencias import EvidenciasService

TIPO_LABEL = {"dia": "Dia", "hora": "Hora", "autorizacao": "Autorização"}

_COLUNAS = [
    # (cabeçalho, largura, formato da célula, formato do cabeçalho)
    ("Tipo", 13, "texto", "cabecalho"),
    ("Data", 12, "data", "cabecalho"),
    ("Horário", 12, "texto", "cabecalho"),
    ("Nº da autorização", 20, "texto", "cabecalho"),
    ("CRM/UF", 13, "texto", "cabecalho"),
    ("Nome do médico", 32, "texto", "cabecalho"),
    ("Valor pago", 14, "moeda", "cabecalho_num"),
    ("Autorizações na janela", 14, "inteiro", "cabecalho_num"),
    ("Alertas", 34, "quebra", "cabecalho"),
    ("Nota do auditor", 50, "quebra", "cabecalho"),
    ("Marcada em", 17, "data_hora", "cabecalho"),
]


def _ordem(ev: Dict[str, Any]):
    return (ev["dt_janela"], -1 if ev.get("hora") is None else ev["hora"], (ev.get("snapshot") or {}).get("horario") or "")


def _marcada_em(iso: str) -> datetime:
    # Gravado em UTC; o auditor lê no fuso local da máquina.
    return datetime.fromisoformat(iso).astimezone().replace(tzinfo=None)


def _horario(ev: Dict[str, Any]) -> str:
    if ev["tipo"] == "dia":
        return "Dia todo"
    if ev["tipo"] == "hora":
        return f"{ev['hora']:02d}h às {ev['hora']:02d}h59"
    horario = (ev.get("snapshot") or {}).get("horario")
    if not horario:
        raise HTTPException(status_code=500, detail=f"Evidência {ev['id']} sem horário da autorização.")
    return str(horario)


def _linha(ev: Dict[str, Any]) -> List[Any]:
    s = ev.get("snapshot") or {}
    autorizacao = ev["tipo"] == "autorizacao"
    return [
        TIPO_LABEL[ev["tipo"]],
        date.fromisoformat(ev["dt_janela"]),
        _horario(ev),
        ev.get("num_autorizacao") or "",
        (s.get("crm") or "") if autorizacao else "",
        (s.get("medico") or "") if autorizacao else "",
        float(s["valor"]) if autorizacao and s.get("valor") is not None else None,
        int(s["qtd"]) if not autorizacao and s.get("qtd") is not None else None,
        ", ".join(s.get("alertas") or []),
        ev.get("nota") or "",
        _marcada_em(ev["criado_em"]),
    ]


def export_evidencias_xlsx(cnpj: str) -> tuple[str, bytes]:
    """Planilha com uma linha por item marcado na cesta de evidências do CNPJ."""
    evidencias = sorted(EvidenciasService.listar(cnpj), key=_ordem)
    if not evidencias:
        raise HTTPException(status_code=404, detail="Nenhuma evidência marcada para esta farmácia.")
    farmacia = _load_farmacia(cnpj)
    gerado_em = datetime.now()
    cnpj_fmt = _format_cnpj(cnpj)

    buffer = io.BytesIO()
    # strings_to_*: notas e nomes nunca viram fórmula, número ou link.
    wb = xlsxwriter.Workbook(buffer, {
        "in_memory": True,
        "strings_to_formulas": False,
        "strings_to_numbers": False,
        "strings_to_urls": False,
    })
    wb.set_properties({
        "title": "Cesta de evidências",
        "subject": f"CNPJ {cnpj_fmt} · {farmacia.razao_social}",
        "author": "Sentinela · CGU",
        "company": "Controladoria-Geral da União",
    })
    f = _formats(wb)
    f["quebra"] = wb.add_format({"font_name": "Calibri", "font_size": 10, "font_color": "#1E293B",
                                 "valign": "top", "text_wrap": True, "indent": 1})
    f["data_hora"] = wb.add_format({"font_name": "Calibri", "font_size": 10, "font_color": "#1E293B",
                                    "valign": "vcenter", "num_format": "dd/mm/yyyy hh:mm", "align": "left",
                                    "indent": 1})

    ws = wb.add_worksheet("Evidências")
    ultima = len(_COLUNAS) - 1
    for idx, (_, largura, _, _) in enumerate(_COLUNAS):
        ws.set_column(idx, idx, largura)

    # Cabeçalho
    ws.set_row(0, 6)
    ws.merge_range(0, 0, 0, ultima, "", f["faixa"])
    ws.set_row(1, 30)
    ws.merge_range(1, 0, 1, ultima, "Cesta de evidências", f["titulo"])
    ws.merge_range(2, 0, 2, ultima, farmacia.razao_social, f["subtitulo"])
    ws.merge_range(3, 0, 3, ultima, f"CNPJ {cnpj_fmt}  ·  {farmacia.municipio}/{farmacia.uf}", f["meta"])
    ws.merge_range(4, 0, 4, ultima, f"Gerado em {gerado_em:%d/%m/%Y %H:%M} pelo Sentinela", f["meta"])

    # Indicadores
    contagem = {tipo: sum(1 for ev in evidencias if ev["tipo"] == tipo) for tipo in TIPO_LABEL}
    kpis = [
        (0, 1, "EVIDÊNCIAS", len(evidencias)),
        (2, 2, "DIAS", contagem["dia"]),
        (3, 4, "HORAS", contagem["hora"]),
        (5, 5, "AUTORIZAÇÕES", contagem["autorizacao"]),
    ]
    ws.set_row(6, 26)
    ws.set_row(7, 30)
    for c1, c2, label, valor in kpis:
        if c1 == c2:
            ws.write_string(6, c1, label, f["kpi_label"])
            ws.write_number(7, c1, valor, f["kpi_valor"])
        else:
            ws.merge_range(6, c1, 6, c2, label, f["kpi_label"])
            ws.merge_range(7, c1, 7, c2, valor, f["kpi_valor"])

    # Tabela
    header_row = 9
    ws.set_row(header_row, 30)
    dados = [_linha(ev) for ev in evidencias]
    ultima_linha = header_row + len(dados)
    ws.add_table(header_row, 0, ultima_linha, ultima, {
        "name": "Evidencias",
        "style": "Table Style Light 1",
        "data": dados,
        "columns": [
            {"header": nome, "format": f[fmt], "header_format": f[fmt_cab]}
            for nome, _, fmt, fmt_cab in _COLUNAS
        ],
    })
    ws.freeze_panes(header_row + 1, 0)

    ws.set_row(ultima_linha + 2, 30)
    ws.merge_range(
        ultima_linha + 2, 0, ultima_linha + 2, ultima,
        "Itens marcados pelo auditor na Cronologia do Sentinela. Quantidades, valores e alertas refletem "
        "os dados no momento da marcação.",
        f["nota"],
    )

    ws.hide_gridlines(2)
    ws.set_landscape()
    ws.set_paper(9)  # A4
    ws.fit_to_pages(1, 0)
    ws.set_margins(left=0.4, right=0.4, top=0.6, bottom=0.6)
    ws.repeat_rows(header_row)
    ws.set_header(f"&L&8Sentinela · Cesta de evidências&R&8CNPJ {cnpj_fmt}")
    ws.set_footer("&L&8Evidências marcadas pelo auditor&R&8Página &P de &N")

    wb.close()
    return f"evidencias_{cnpj}.xlsx", buffer.getvalue()
