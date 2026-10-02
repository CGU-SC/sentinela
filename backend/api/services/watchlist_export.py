"""Exportação das Farmácias Monitoradas (tela /listas) em Excel e CSV.

O arquivo reproduz a tabela da tela no período de análise: a lista vem das
preferências do usuário (lista de interesse), os números de cada farmácia do
mesmo cálculo da tela (get_dashboard_data, seção cnpjs) e a contagem de
evidências da cesta de evidências. As linhas saem ordenadas pelo valor sem
comprovação, do maior para o menor (a ordem padrão da tela).

Farmácia da lista sem movimentação no período continua no arquivo, com os
números em branco e a situação "Sem dados no período"; ela não entra nos totais
e o cabeçalho informa quantas ficaram nessa situação.
"""

import csv
import io
from dataclasses import dataclass
from datetime import date, datetime
from typing import Iterator, Optional

import xlsxwriter
import xlsxwriter.utility
from fastapi import HTTPException
from sqlalchemy.orm import Session

from .analytics.crm_export import (
    _csv_literal_text,
    _csv_text,
    _format_cnpj,
    _formats,
    _write_total_row,
)
from .analytics.dashboard import get_dashboard_data
from .evidencias import EvidenciasError, EvidenciasService
from .preferences import PreferencesError, PreferencesService

_TITULO = "Farmácias monitoradas"
_SECAO = "Lista de interesse"
_SEM_DADOS = "Sem dados no período"
_COM_DADOS = "Com dados no período"
_CAMPOS_ANALITICOS = ("totalMov", "valSemComp", "percValSemComp")


# ── Dados ─────────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class _Linha:
    """Uma farmácia da lista; os campos analíticos são None sem dados no período."""

    cnpj: str
    razao_social: str
    municipio: Optional[str]
    uf: Optional[str]
    score_risco: Optional[float]
    classificacao_risco: Optional[str]
    perc_sem_comp: Optional[float]  # fração (0,25 = 25%)
    val_sem_comp: Optional[float]
    total_mov: Optional[float]
    qtd_evidencias: int
    ultima_evidencia: Optional[date]
    adicionado_em: Optional[date]
    observacao: str

    @property
    def com_dados(self) -> bool:
        return self.total_mov is not None


@dataclass(frozen=True)
class _ListaExport:
    inicio: date
    fim: date
    linhas: list[_Linha]

    @property
    def com_dados(self) -> list[_Linha]:
        return [linha for linha in self.linhas if linha.com_dados]

    @property
    def total_mov(self) -> float:
        return sum(linha.total_mov for linha in self.com_dados)

    @property
    def val_sem_comp(self) -> float:
        return sum(linha.val_sem_comp for linha in self.com_dados)

    @property
    def perc_sem_comp(self) -> Optional[float]:
        """Valor sem comprovação somado ÷ total movimentado somado (None sem movimentação)."""
        return self.val_sem_comp / self.total_mov if self.total_mov > 0 else None

    def filename(self, extensao: str) -> str:
        return f"farmacias_monitoradas_{self.inicio:%Y%m}-{self.fim:%Y%m}.{extensao}"


def _data_do_iso(valor: object, campo: str, cnpj: str) -> Optional[date]:
    """Data (dia) de um carimbo ISO gravado pelo sistema; vazio = None; inválido = 503."""
    if valor in (None, ""):
        return None
    try:
        return datetime.fromisoformat(str(valor).replace("Z", "+00:00")).date()
    except ValueError as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Data inválida em {campo} da farmácia {cnpj} na lista de interesse.",
        ) from exc


def _preparar(db: Session, data_inicio: date, data_fim: date) -> _ListaExport:
    if data_inicio > data_fim:
        raise HTTPException(status_code=422, detail="O início do período não pode ser posterior ao fim.")
    try:
        lista = PreferencesService.read()["watchlist"]
    except PreferencesError as exc:
        raise HTTPException(status_code=503, detail=f"Lista de interesse indisponível: {exc}") from exc
    if not lista:
        raise HTTPException(status_code=404, detail="Não há farmácias na lista de interesse para exportar.")
    cnpjs = [str(item["cnpj"]) for item in lista]
    if len(set(cnpjs)) != len(cnpjs):
        raise HTTPException(status_code=503, detail="Lista de interesse com CNPJ repetido.")

    try:
        evidencias = {r["cnpj"]: r for r in EvidenciasService.resumo_por_cnpj()}
    except EvidenciasError as exc:
        raise HTTPException(status_code=503, detail=f"Cesta de evidências indisponível: {exc}") from exc

    resumo = get_dashboard_data(db, data_inicio, data_fim, cnpjs=cnpjs, secoes=["cnpjs"])
    if resumo.resultado_cnpjs is None:
        raise HTTPException(status_code=503, detail="Resumo das farmácias da lista sem a seção de CNPJs.")
    por_cnpj = {r.cnpj: r for r in resumo.resultado_cnpjs}

    linhas = []
    for item in lista:
        cnpj = str(item["cnpj"])
        dados = por_cnpj.get(cnpj)
        if dados is not None and any(getattr(dados, campo) is None for campo in _CAMPOS_ANALITICOS):
            raise HTTPException(status_code=503, detail=f"Farmácia {cnpj} com indicadores incompletos no período.")
        evidencia = evidencias.get(cnpj)
        linhas.append(_Linha(
            cnpj=cnpj,
            razao_social=str(item.get("razaoSocial") or (dados.razao_social if dados else "") or ""),
            municipio=dados.municipio if dados else None,
            uf=dados.uf if dados else None,
            score_risco=dados.score_risco_final if dados else None,
            classificacao_risco=dados.classificacao_risco if dados else None,
            perc_sem_comp=float(dados.percValSemComp) / 100 if dados else None,
            val_sem_comp=float(dados.valSemComp) if dados else None,
            total_mov=float(dados.totalMov) if dados else None,
            qtd_evidencias=int(evidencia["quantidade"]) if evidencia else 0,
            ultima_evidencia=_data_do_iso(evidencia["ultima_em"], "última evidência", cnpj) if evidencia else None,
            adicionado_em=_data_do_iso(item.get("adicionadoEm"), "adicionadoEm", cnpj),
            observacao=str(item.get("observacao") or ""),
        ))
    # Maior valor sem comprovação primeiro; sem dados no fim; a ordem da lista desempata.
    linhas.sort(key=lambda linha: (not linha.com_dados, -(linha.val_sem_comp or 0.0)))
    return _ListaExport(inicio=data_inicio, fim=data_fim, linhas=linhas)


# ── Colunas (Excel e CSV usam as mesmas) ─────────────────────────────────────
def _colunas() -> list[tuple[str, int, str, bool]]:
    """(cabeçalho, largura, chave do formato, é número) — mesma ordem de _valores."""
    return [
        ("Posição", 9, "inteiro", True),
        ("CNPJ", 20, "texto", False),
        ("Razão social", 42, "texto", False),
        ("Município", 26, "texto", False),
        ("UF", 6, "texto", False),
        ("Situação no período", 20, "texto", False),
        ("Score de risco", 12, "decimal", True),
        ("Classificação de risco", 15, "texto", False),
        ("% sem comprovação", 13, "pct", True),
        ("Valor sem comprovação", 20, "moeda", True),
        ("Total movimentado", 20, "moeda", True),
        ("Evidências", 11, "inteiro", True),
        ("Última evidência", 13, "data", False),
        ("Adicionada em", 13, "data", False),
        ("Observação", 50, "texto_quebra", False),
    ]


def _valores(posicao: int, linha: _Linha) -> list:
    return [
        posicao,
        _format_cnpj(linha.cnpj),
        linha.razao_social,
        linha.municipio,
        linha.uf,
        _COM_DADOS if linha.com_dados else _SEM_DADOS,
        linha.score_risco,
        linha.classificacao_risco,
        linha.perc_sem_comp,
        linha.val_sem_comp,
        linha.total_mov,
        linha.qtd_evidencias,
        linha.ultima_evidencia,
        linha.adicionado_em,
        linha.observacao,
    ]


# ── CSV ───────────────────────────────────────────────────────────────────────
def _csv_valor(valor, formato: str, coluna: str) -> str:
    """Valor da célula no CSV (pt-BR); percentuais em pontos percentuais (12,5 = 12,5%)."""
    if valor is None:
        return ""
    if coluna == "CNPJ":
        return _csv_literal_text(valor)
    if formato == "data":
        return f"{valor:%d/%m/%Y}"
    if formato == "pct":
        valor = valor * 100
    if isinstance(valor, float):
        return f"{valor:.4f}".rstrip("0").rstrip(".").replace(".", ",")
    if isinstance(valor, int):
        return str(valor)
    return _csv_text(str(valor))


def export_watchlist_csv(db: Session, data_inicio: date, data_fim: date) -> tuple[str, Iterator[bytes]]:
    """CSV (separador `;`, UTF-8 com BOM) das farmácias monitoradas no período."""
    export = _preparar(db, data_inicio, data_fim)

    def gerar() -> Iterator[bytes]:
        buffer = io.StringIO(newline="")
        writer = csv.writer(buffer, delimiter=";", lineterminator="\r\n")
        colunas = _colunas()
        writer.writerow([nome for nome, *_ in colunas])
        for posicao, linha in enumerate(export.linhas, start=1):
            writer.writerow([
                _csv_valor(valor, formato, nome)
                for valor, (nome, _, formato, _) in zip(_valores(posicao, linha), colunas)
            ])
        yield b"\xef\xbb\xbf" + buffer.getvalue().encode("utf-8")

    return export.filename("csv"), gerar()


# ── Excel ─────────────────────────────────────────────────────────────────────
def _formatos(wb: xlsxwriter.Workbook) -> dict:
    f = _formats(wb)
    base = {"font_name": "Calibri", "font_size": 10, "font_color": "#1E293B", "valign": "vcenter"}
    f["decimal"] = wb.add_format({**base, "num_format": "#,##0.00"})
    f["texto_quebra"] = wb.add_format({**base, "text_wrap": True, "valign": "top", "indent": 1})
    f["kpi_pct"] = wb.add_format({
        **base, "font_size": 16, "bold": True, "font_color": "#0F172A", "bg_color": "#F1F5F9",
        "num_format": "0.0%", "indent": 1, "align": "left",
    })
    f["kpi_moeda_alerta"] = wb.add_format({
        **base, "font_size": 16, "bold": True, "font_color": "#9B1C1C", "bg_color": "#F1F5F9",
        "num_format": '"R$" #,##0.00', "indent": 1, "align": "left",
    })
    f["kpi_texto"] = wb.add_format({
        **base, "font_size": 16, "bold": True, "font_color": "#0F172A", "bg_color": "#F1F5F9",
        "indent": 1, "align": "left",
    })
    return f


def _cabecalho(ws, f: dict, titulo: str, export: _ListaExport, gerado_em: datetime, ultima: int) -> None:
    """Cabeçalho das abas (linhas 0 a 4): faixa, título, composição da lista e período."""
    total = len(export.linhas)
    sem_dados = total - len(export.com_dados)
    composicao = f"{_SECAO}  ·  {total} {'farmácia' if total == 1 else 'farmácias'}"
    if sem_dados:
        composicao += f"  ·  {sem_dados} sem dados no período (fora dos totais)"
    ws.set_row(0, 6)
    ws.merge_range(0, 0, 0, ultima, "", f["faixa"])
    ws.set_row(1, 30)
    ws.merge_range(1, 0, 1, ultima, titulo, f["titulo"])
    ws.merge_range(2, 0, 2, ultima, composicao, f["subtitulo"])
    ws.merge_range(3, 0, 3, ultima,
                   f"Período de análise: {export.inicio:%d/%m/%Y} a {export.fim:%d/%m/%Y}", f["meta"])
    ws.merge_range(4, 0, 4, ultima, f"Gerado em {gerado_em:%d/%m/%Y %H:%M} pelo Sentinela", f["meta"])


def _pagina(ws, header_row: int, rodape: str) -> None:
    ws.hide_gridlines(2)
    ws.set_landscape()
    ws.set_paper(9)  # A4
    ws.fit_to_pages(1, 0)
    ws.set_margins(left=0.4, right=0.4, top=0.6, bottom=0.6)
    ws.repeat_rows(header_row)
    ws.set_header(f"&L&8Sentinela · {_SECAO}&R&8{_TITULO}")
    ws.set_footer(f"&L&8{rodape}&R&8Página &P de &N")


def _aba_farmacias(wb, f: dict, export: _ListaExport, gerado_em: datetime) -> None:
    ws = wb.add_worksheet("Farmácias")
    colunas = _colunas()
    ultima = len(colunas) - 1
    for idx, (_, largura, _, _) in enumerate(colunas):
        ws.set_column(idx, idx, largura)
    _cabecalho(ws, f, _TITULO, export, gerado_em, ultima)

    perc = export.perc_sem_comp
    kpis = [
        (0, 1, "FARMÁCIAS", len(export.linhas), f["kpi_valor"]),
        (2, 3, "TOTAL MOVIMENTADO", export.total_mov, f["kpi_moeda"]),
        (4, 7, "VALOR SEM COMPROVAÇÃO", export.val_sem_comp, f["kpi_moeda_alerta"]),
        (8, 9, "% SEM COMPROVAÇÃO", perc if perc is not None else "—", f["kpi_pct"] if perc is not None else f["kpi_texto"]),
        (10, 11, "EVIDÊNCIAS", sum(linha.qtd_evidencias for linha in export.linhas), f["kpi_valor"]),
    ]
    ws.set_row(6, 26)
    ws.set_row(7, 30)
    for c1, c2, rotulo, valor, fmt_valor in kpis:
        ws.merge_range(6, c1, 6, c2, rotulo, f["kpi_label"])
        ws.merge_range(7, c1, 7, c2, valor, fmt_valor)

    header_row = 9
    ws.set_row(header_row, 32)
    dados = [_valores(posicao, linha) for posicao, linha in enumerate(export.linhas, start=1)]
    ultima_linha = header_row + len(dados)
    ws.add_table(header_row, 0, ultima_linha, ultima, {
        "name": "Farmacias",
        "style": "Table Style Light 1",
        "data": dados,
        "columns": [
            {"header": nome, "format": f[formato], "header_format": f["cabecalho_num"] if numero else f["cabecalho"]}
            for nome, _, formato, numero in colunas
        ],
    })
    indice = {nome: idx for idx, (nome, *_) in enumerate(colunas)}
    totais: list[tuple] = [("label", "Total")] + [("vazio",)] * ultima
    totais[indice["Valor sem comprovação"]] = ("soma", export.val_sem_comp, "total_moeda")
    totais[indice["Total movimentado"]] = ("soma", export.total_mov, "total_moeda")
    totais[indice["Evidências"]] = ("soma", float(sum(linha.qtd_evidencias for linha in export.linhas)), "total_inteiro")
    _write_total_row(ws, f, ultima_linha + 1, header_row + 1, ultima_linha, totais)
    # Percentual do conjunto na linha de total: soma sem comprovação ÷ soma movimentada
    # (recalcula com os filtros da tabela; o valor gravado serve a quem não recalcula).
    col_pct = xlsxwriter.utility.xl_col_to_name(indice["% sem comprovação"])
    col_sem = xlsxwriter.utility.xl_col_to_name(indice["Valor sem comprovação"])
    col_mov = xlsxwriter.utility.xl_col_to_name(indice["Total movimentado"])
    linha_total = ultima_linha + 2  # numeração do Excel (base 1)
    ws.write_formula(
        f"{col_pct}{linha_total}",
        f'=IF({col_mov}{linha_total}>0,{col_sem}{linha_total}/{col_mov}{linha_total},"")',
        f["total_pct"], perc if perc is not None else "",
    )
    # Farmácias sem dados no período em destaque.
    col_situacao = xlsxwriter.utility.xl_col_to_name(indice["Situação no período"])
    ws.conditional_format(header_row + 1, 0, ultima_linha, ultima, {
        "type": "formula",
        "criteria": f'=${col_situacao}{header_row + 2}="{_SEM_DADOS}"',
        "format": f["alerta"],
    })
    ws.freeze_panes(header_row + 1, 3)
    ws.set_row(ultima_linha + 3, 30)
    ws.merge_range(ultima_linha + 3, 0, ultima_linha + 3, ultima,
                   "Mesmos números da tela Farmácias Monitoradas do Sentinela no período de análise, ordenados pelo "
                   "valor sem comprovação. Linhas destacadas não têm movimentação no período e ficam fora dos "
                   "totais. Significado de cada coluna na aba Critérios.",
                   f["nota"])
    _pagina(ws, header_row, _TITULO)


def _aba_criterios(wb, f: dict, export: _ListaExport, gerado_em: datetime) -> None:
    ws = wb.add_worksheet("Critérios")
    ws.set_column(0, 0, 30)
    ws.set_column(1, 1, 104)
    _cabecalho(ws, f, f"{_TITULO} · Critérios e definições", export, gerado_em, 1)
    itens = [
        ("Posição", "Ordem da farmácia pelo valor sem comprovação no período (1 = maior valor). Farmácias sem dados no período ficam no fim."),
        ("Situação no período", f'"{_COM_DADOS}": a farmácia tem movimentação no período de análise. "{_SEM_DADOS}": não tem; os números ficam em branco e ela não entra nos totais.'),
        ("Score de risco", "Score final da matriz de risco da farmácia no período de análise."),
        ("Classificação de risco", "Faixa do score de risco (crítico, alto, médio ou baixo)."),
        ("% sem comprovação", "Valor sem comprovação ÷ total movimentado da farmácia no período. Na linha de total, soma do valor sem comprovação ÷ soma do total movimentado."),
        ("Valor sem comprovação", "Valor das vendas do Farmácia Popular sem comprovação de aquisição do medicamento, no período."),
        ("Total movimentado", "Valor total das vendas da farmácia pelo Farmácia Popular no período."),
        ("Evidências", "Quantidade de itens marcados pelo auditor na cesta de evidências da farmácia (não depende do período de análise)."),
        ("Última evidência", "Data da marcação mais recente na cesta de evidências da farmácia."),
        ("Adicionada em", "Data em que a farmácia entrou na lista de interesse."),
        ("Observação", "Anotação do auditor sobre a farmácia na lista de interesse."),
    ]
    header_row = 6
    ws.set_row(header_row, 22)
    ws.add_table(header_row, 0, header_row + len(itens), 1, {
        "name": "Criterios",
        "style": "Table Style Light 1",
        "data": [list(item) for item in itens],
        "columns": [
            {"header": "Coluna", "format": f["texto_forte"], "header_format": f["cabecalho"]},
            {"header": "Definição", "format": f["texto_quebra"], "header_format": f["cabecalho"]},
        ],
    })
    _pagina(ws, header_row, "Critérios e definições")


def export_watchlist_xlsx(db: Session, data_inicio: date, data_fim: date) -> tuple[str, bytes]:
    """Planilha formatada (abas Farmácias e Critérios) das farmácias monitoradas no período."""
    export = _preparar(db, data_inicio, data_fim)
    gerado_em = datetime.now()
    buffer = io.BytesIO()
    # strings_to_*: texto da lista (razão social, observação) nunca vira fórmula, número ou link.
    wb = xlsxwriter.Workbook(buffer, {
        "in_memory": True,
        "strings_to_formulas": False,
        "strings_to_numbers": False,
        "strings_to_urls": False,
    })
    wb.set_properties({
        "title": _TITULO,
        "subject": f"{_SECAO} · {len(export.linhas)} farmácias",
        "author": "Sentinela · CGU",
        "company": "Controladoria-Geral da União",
        "comments": f"Período {export.inicio.isoformat()} a {export.fim.isoformat()}",
    })
    f = _formatos(wb)
    _aba_farmacias(wb, f, export, gerado_em)
    _aba_criterios(wb, f, export, gerado_em)
    wb.close()
    return export.filename("xlsx"), buffer.getvalue()
