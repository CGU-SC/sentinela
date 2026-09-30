"""Exportacao da aba Falecidos do CNPJ em CSV e Excel.

Os numeros vem do mesmo calculo da tela (carregar_falecidos). Com o filtro da
rede de coincidencia ativo na tela, o frontend envia o CNPJ da outra farmacia:
o arquivo traz so os CPFs que tambem compraram nela, e o filtro fica no
cabecalho.
"""

import csv
import io
from dataclasses import dataclass
from datetime import date, datetime
from typing import Iterator, Optional

import polars as pl
import xlsxwriter
import xlsxwriter.utility
from fastapi import HTTPException

from .crm_export import (
    _Farmacia,
    _csv_text,
    _format_cnpj,
    _formats,
    _load_farmacia,
    _setup_page,
    _title_case,
    _write_header,
    _write_total_row,
)
from .falecidos import carregar_falecidos, ranking_outras_farmacias

_SECAO = "Vendas para falecidos"
_TITULO = "Vendas para falecidos · Autorizações após o óbito"

# Mesmas faixas (e limites) das cores de "Dias após o óbito" na tela.
_FAIXAS_DIAS = (
    (7, "Até 7 dias"),
    (15, "8 a 15 dias"),
    (30, "16 a 30 dias"),
    (60, "31 a 60 dias"),
    (120, "61 a 120 dias"),
    (240, "121 a 240 dias"),
    (365, "241 dias a 1 ano"),
    (730, "1 a 2 anos"),
    (1095, "2 a 3 anos"),
)
_FAIXA_ACIMA = "Mais de 3 anos"
_LIMITE_DESTAQUE_DIAS = 365


def _faixa(dias: int) -> str:
    for limite, rotulo in _FAIXAS_DIAS:
        if dias <= limite:
            return rotulo
    return _FAIXA_ACIMA


def _format_cpf(cpf: str) -> str:
    c = str(cpf).zfill(11)
    return f"{c[:3]}.{c[3:6]}.{c[6:9]}-{c[9:]}"


# ── Dados ─────────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class _FalecidosExport:
    cnpj: str
    inicio: str  # ISO
    fim: str  # ISO
    transacoes: pl.DataFrame  # autorizacoes do arquivo (ordenadas por CPF e data)
    ranking: pl.DataFrame  # rede de coincidencia dos CPFs do arquivo
    faturamento: float
    filtro: Optional[str]
    total_cpfs_farmacia: int

    def filename(self, extensao: str) -> str:
        return f"falecidos_{self.cnpj}_{self.inicio[:7].replace('-', '')}-{self.fim[:7].replace('-', '')}.{extensao}"


def _preparar(
    cnpj: str,
    data_inicio: Optional[date],
    data_fim: Optional[date],
    outro_cnpj: Optional[str],
) -> _FalecidosExport:
    if data_inicio and data_fim and data_inicio > data_fim:
        raise HTTPException(status_code=422, detail="O início do período não pode ser posterior ao fim.")
    dados = carregar_falecidos(cnpj, data_inicio, data_fim)
    if dados.transacoes.is_empty():
        raise HTTPException(status_code=404, detail="Não há autorizações para falecidos nesta farmácia no período.")
    if dados.faturamento_periodo is None:
        raise HTTPException(status_code=500, detail="Faturamento do período não calculado para a exportação.")

    transacoes = dados.transacoes
    outras = dados.outras
    filtro = None
    if outro_cnpj is not None:
        alvo = "".join(ch for ch in outro_cnpj if ch.isdigit())
        linha = dados.ranking.filter(pl.col("cnpj") == alvo)
        if linha.is_empty():
            raise HTTPException(status_code=422, detail="A farmácia do filtro não está na rede de coincidência do período.")
        cpfs = outras.filter(pl.col("cnpj") == alvo).get_column("cpf").unique().implode()
        transacoes = transacoes.filter(pl.col("cpf").is_in(cpfs))
        outras = outras.filter(pl.col("cpf").is_in(cpfs))
        r = linha.row(0, named=True)
        filtro = (
            f"CPFs que também compraram em {_format_cnpj(alvo)} — "
            f"{_title_case(r['razao_social'])} ({r['municipio']}/{r['uf']})"
        )

    primeira, ultima = dados.transacoes.select([
        pl.col("data_autorizacao").min(), pl.col("data_autorizacao").max().alias("ultima"),
    ]).row(0)
    return _FalecidosExport(
        cnpj=dados.cnpj,
        inicio=(data_inicio or primeira).isoformat(),
        fim=(data_fim or ultima).isoformat(),
        transacoes=transacoes,
        ranking=ranking_outras_farmacias(outras),
        faturamento=dados.faturamento_periodo,
        filtro=filtro,
        total_cpfs_farmacia=dados.summary.cpfs_distintos,
    )


def _qtd_outras(outros: Optional[str]) -> int:
    return len(outros.split("; ")) if outros else 0


# ── Colunas da aba Autorizações (CSV usa as mesmas) ──────────────────────────
def _colunas() -> list[tuple[str, int, str, bool]]:
    """(cabeçalho, largura, chave do formato, é número)."""
    return [
        ("CPF", 16, "texto", False),
        ("Nome do falecido", 34, "texto", False),
        ("Nascimento", 12, "data", False),
        ("Óbito", 12, "data", False),
        ("Fonte do óbito", 18, "texto", False),
        ("Município do falecido", 22, "texto", False),
        ("UF", 6, "texto", False),
        ("Nº da autorização", 18, "texto", False),
        ("Data da venda", 12, "data", False),
        ("Itens", 8, "inteiro", True),
        ("Valor autorizado", 15, "moeda", True),
        ("Dias após o óbito", 11, "inteiro", True),
        ("Faixa de dias", 16, "texto", False),
        ("Outras farmácias do CPF", 12, "inteiro", True),
        ("Outras farmácias (CNPJ | município/UF)", 60, "texto_quebra", False),
    ]


def _linha(r: dict) -> list:
    return [
        _format_cpf(r["cpf"]),
        _title_case(r["nome_falecido"]) if r["nome_falecido"] else "",
        r["dt_nascimento"],
        r["dt_obito"],
        r["fonte_obito"] or "",
        _title_case(r["municipio_falecido"]) if r["municipio_falecido"] else "",
        r["uf_falecido"] or "",
        str(r["num_autorizacao"]),
        r["data_autorizacao"],
        int(r["qtd_itens_na_autorizacao"]),
        float(r["valor_total_autorizacao"]),
        int(r["dias_apos_obito"]),
        _faixa(int(r["dias_apos_obito"])),
        _qtd_outras(r["outros"]),
        r["outros"] or "",
    ]


# ── CSV ───────────────────────────────────────────────────────────────────────
def _csv_valor(valor, formato: str) -> str:
    if valor is None:
        return ""
    if formato == "data":
        return f"{valor:%d/%m/%Y}"
    if isinstance(valor, float):
        return f"{valor:.2f}".replace(".", ",")
    if isinstance(valor, int):
        return str(valor)
    return _csv_text(str(valor))


def export_falecidos_csv(
    cnpj: str,
    data_inicio: Optional[date] = None,
    data_fim: Optional[date] = None,
    outro_cnpj: Optional[str] = None,
) -> tuple[str, Iterator[bytes]]:
    export = _preparar(cnpj, data_inicio, data_fim, outro_cnpj)

    def gerar() -> Iterator[bytes]:
        colunas = _colunas()
        formatos = [formato for _, _, formato, _ in colunas]
        cnpj_formatado = _format_cnpj(export.cnpj)
        buffer = io.StringIO(newline="")
        writer = csv.writer(buffer, delimiter=";", lineterminator="\r\n")
        writer.writerow(["CNPJ da farmácia", *(nome for nome, *_ in colunas)])
        yield b"\xef\xbb\xbf" + buffer.getvalue().encode("utf-8")
        for bloco in export.transacoes.iter_slices(5_000):
            buffer = io.StringIO(newline="")
            writer = csv.writer(buffer, delimiter=";", lineterminator="\r\n")
            for r in bloco.iter_rows(named=True):
                writer.writerow([cnpj_formatado, *(_csv_valor(v, f) for v, f in zip(_linha(r), formatos))])
            yield buffer.getvalue().encode("utf-8")

    return export.filename("csv"), gerar()


# ── Excel ─────────────────────────────────────────────────────────────────────
def _formatos(wb: xlsxwriter.Workbook) -> dict:
    f = _formats(wb)
    base = {"font_name": "Calibri", "font_size": 10, "font_color": "#1E293B", "valign": "vcenter"}
    f["texto_quebra"] = wb.add_format({**base, "text_wrap": True, "valign": "top", "indent": 1})
    f["kpi_dias"] = wb.add_format({**base, "font_size": 16, "bold": True, "font_color": "#0F172A",
                                   "bg_color": "#F1F5F9", "num_format": '#,##0 "dias"', "indent": 1, "align": "left"})
    f["kpi_pct"] = wb.add_format({**base, "font_size": 16, "bold": True, "font_color": "#0F172A",
                                  "bg_color": "#F1F5F9", "num_format": "0.000%", "indent": 1, "align": "left"})
    return f


def _linha_filtro(ws, f: dict, export: _FalecidosExport, ultima: int) -> None:
    cpfs = export.transacoes.get_column("cpf").n_unique()
    texto = (
        f"Filtro aplicado na tela: {export.filtro} — {cpfs} de {export.total_cpfs_farmacia} CPFs"
        if export.filtro
        else f"Todos os {export.total_cpfs_farmacia} CPFs com autorização após o óbito na farmácia no período"
    )
    ws.merge_range(5, 0, 5, ultima, texto, f["meta"])


def _tabela(ws, f: dict, header_row: int, nome: str, colunas: list, dados: list) -> int:
    ws.set_row(header_row, 32)
    ultima_linha = header_row + len(dados)
    ws.add_table(header_row, 0, ultima_linha, len(colunas) - 1, {
        "name": nome,
        "style": "Table Style Light 1",
        "data": dados,
        "columns": [
            {"header": nome_col, "format": f[formato], "header_format": f["cabecalho_num"] if numero else f["cabecalho"]}
            for nome_col, _, formato, numero in colunas
        ],
    })
    return ultima_linha


def _larguras(ws, colunas: list) -> None:
    for idx, (_, largura, _, _) in enumerate(colunas):
        ws.set_column(idx, idx, largura)


def _aba_autorizacoes(wb, f, export: _FalecidosExport, farmacia: _Farmacia, gerado_em: datetime) -> None:
    ws = wb.add_worksheet("Autorizações")
    colunas = _colunas()
    ultima = len(colunas) - 1
    _larguras(ws, colunas)
    _write_header(ws, f, _TITULO, farmacia, export.cnpj, export.inicio, export.fim, gerado_em, ultima)
    _linha_filtro(ws, f, export, ultima)

    t = export.transacoes
    valor = float(t.get_column("valor_total_autorizacao").sum())
    kpis = [
        ((0, 1), "CPFS DISTINTOS", t.get_column("cpf").n_unique(), f["kpi_alerta"]),
        ((2, 3), "AUTORIZAÇÕES", t.height, f["kpi_valor"]),
        ((4, 6), "PREJUÍZO ESTIMADO", valor, f["kpi_moeda"]),
        ((7, 9), "MÁXIMO APÓS O ÓBITO", int(t.select(pl.col("dias_apos_obito").max()).item()), f["kpi_dias"]),
        ((10, 12), "% DO FATURAMENTO NO PERÍODO", valor / export.faturamento, f["kpi_pct"]),
    ]
    ws.set_row(7, 26)
    ws.set_row(8, 30)
    for (c1, c2), rotulo, v, fmt in kpis:
        ws.merge_range(7, c1, 7, c2, rotulo, f["kpi_label"])
        ws.merge_range(8, c1, 8, c2, v, fmt)

    header_row = 10
    dados = [_linha(r) for r in t.iter_rows(named=True)]
    ultima_linha = _tabela(ws, f, header_row, "Autorizacoes", colunas, dados)
    indice = {nome: i for i, (nome, *_) in enumerate(colunas)}
    totais: list[tuple] = [("label", "Total")] + [("vazio",)] * ultima
    totais[indice["Itens"]] = ("soma", float(t.get_column("qtd_itens_na_autorizacao").sum()), "total_inteiro")
    totais[indice["Valor autorizado"]] = ("soma", valor, "total_moeda")
    _write_total_row(ws, f, ultima_linha + 1, header_row + 1, ultima_linha, totais)

    col_dias = xlsxwriter.utility.xl_col_to_name(indice["Dias após o óbito"])
    ws.conditional_format(header_row + 1, 0, ultima_linha, ultima, {
        "type": "formula",
        "criteria": f"=${col_dias}{header_row + 2}>{_LIMITE_DESTAQUE_DIAS}",
        "format": f["alerta"],
    })
    ws.freeze_panes(header_row + 1, 2)
    ws.set_row(ultima_linha + 3, 30)
    ws.merge_range(ultima_linha + 3, 0, ultima_linha + 3, ultima,
                   "Uma linha por autorização de venda feita após a data do óbito do beneficiário. Linhas destacadas: "
                   f"venda mais de {_LIMITE_DESTAQUE_DIAS} dias após o óbito. Significado de cada coluna na aba Critérios.",
                   f["nota"])
    _setup_page(ws, _format_cnpj(export.cnpj), header_row, secao=_SECAO, rodape="Autorizações após o óbito")


def _aba_cpfs(wb, f, export: _FalecidosExport, farmacia: _Farmacia, gerado_em: datetime) -> None:
    ws = wb.add_worksheet("Resumo por CPF")
    colunas = [
        ("CPF", 16, "texto", False),
        ("Nome do falecido", 34, "texto", False),
        ("Nascimento", 12, "data", False),
        ("Óbito", 12, "data", False),
        ("Fonte do óbito", 18, "texto", False),
        ("Autorizações", 12, "inteiro", True),
        ("Primeira venda", 12, "data", False),
        ("Última venda", 12, "data", False),
        ("Maior nº de dias após o óbito", 13, "inteiro", True),
        ("Valor autorizado", 15, "moeda", True),
        ("Outras farmácias do CPF", 12, "inteiro", True),
    ]
    ultima = len(colunas) - 1
    _larguras(ws, colunas)
    _write_header(ws, f, "Vendas para falecidos · Resumo por CPF", farmacia, export.cnpj,
                  export.inicio, export.fim, gerado_em, ultima)
    _linha_filtro(ws, f, export, ultima)

    resumo = (
        export.transacoes.group_by("cpf")
        .agg([
            pl.col("nome_falecido").first(),
            pl.col("dt_nascimento").first(),
            pl.col("dt_obito").first(),
            pl.col("fonte_obito").first(),
            pl.len().alias("autorizacoes"),
            pl.col("data_autorizacao").min().alias("primeira"),
            pl.col("data_autorizacao").max().alias("ultima"),
            pl.col("dias_apos_obito").max().alias("max_dias"),
            pl.col("valor_total_autorizacao").sum().alias("valor"),
            pl.col("outros").first(),
        ])
        .sort(["valor", "cpf"], descending=[True, False])
    )
    dados = [
        [
            _format_cpf(r["cpf"]),
            _title_case(r["nome_falecido"]) if r["nome_falecido"] else "",
            r["dt_nascimento"], r["dt_obito"], r["fonte_obito"] or "",
            int(r["autorizacoes"]), r["primeira"], r["ultima"], int(r["max_dias"]),
            float(r["valor"]), _qtd_outras(r["outros"]),
        ]
        for r in resumo.iter_rows(named=True)
    ]
    header_row = 7
    ultima_linha = _tabela(ws, f, header_row, "ResumoCPF", colunas, dados)
    totais: list[tuple] = [("label", "Total")] + [("vazio",)] * ultima
    totais[5] = ("soma", float(resumo.get_column("autorizacoes").sum()), "total_inteiro")
    totais[9] = ("soma", float(resumo.get_column("valor").sum()), "total_moeda")
    _write_total_row(ws, f, ultima_linha + 1, header_row + 1, ultima_linha, totais)
    ws.freeze_panes(header_row + 1, 2)
    _setup_page(ws, _format_cnpj(export.cnpj), header_row, secao=_SECAO, rodape="Resumo por CPF")


def _aba_outras(wb, f, export: _FalecidosExport, farmacia: _Farmacia, gerado_em: datetime) -> None:
    ws = wb.add_worksheet("Outras farmácias")
    colunas = [
        ("Posição", 9, "inteiro", True),
        ("CNPJ", 20, "texto", False),
        ("Razão social", 42, "texto", False),
        ("Município", 24, "texto", False),
        ("UF", 6, "texto", False),
        ("CPFs em comum", 12, "inteiro", True),
        ("Participação nas coincidências", 14, "pct", True),
    ]
    ultima = len(colunas) - 1
    _larguras(ws, colunas)
    _write_header(ws, f, "Vendas para falecidos · Rede de coincidência", farmacia, export.cnpj,
                  export.inicio, export.fim, gerado_em, ultima)
    _linha_filtro(ws, f, export, ultima)
    header_row = 7
    if export.ranking.is_empty():
        ws.merge_range(header_row, 0, header_row, ultima,
                       "Nenhum CPF desta farmácia teve autorização após o óbito em outra farmácia no período.",
                       f["texto"])
    else:
        dados = [
            [i, _format_cnpj(r["cnpj"]), _title_case(r["razao_social"]), r["municipio"], r["uf"],
             int(r["qtd_cpfs"]), float(r["pct_total"])]
            for i, r in enumerate(export.ranking.iter_rows(named=True), start=1)
        ]
        ultima_linha = _tabela(ws, f, header_row, "OutrasFarmacias", colunas, dados)
        ws.freeze_panes(header_row + 1, 3)
        ws.set_row(ultima_linha + 2, 30)
        ws.merge_range(ultima_linha + 2, 0, ultima_linha + 2, ultima,
                       "Farmácias onde os mesmos CPFs falecidos também tiveram autorização após o óbito, no mesmo "
                       "período (lista completa; a tela mostra as 20 primeiras).", f["nota"])
    _setup_page(ws, _format_cnpj(export.cnpj), header_row, secao=_SECAO, rodape="Rede de coincidência")


def _aba_criterios(wb, f, export: _FalecidosExport, farmacia: _Farmacia, gerado_em: datetime) -> None:
    ws = wb.add_worksheet("Critérios")
    ws.set_column(0, 0, 34)
    ws.set_column(1, 1, 100)
    _write_header(ws, f, "Vendas para falecidos · Critérios e definições", farmacia, export.cnpj,
                  export.inicio, export.fim, gerado_em, 1)
    faixas = "; ".join([r for _, r in _FAIXAS_DIAS] + [_FAIXA_ACIMA])
    itens = [
        ("Autorização após o óbito", "Autorização de venda do Farmácia Popular registrada em data posterior à data de óbito do beneficiário (CPF), segundo a base de óbitos."),
        ("Fonte do óbito", "Base de óbitos de onde veio a data de falecimento do CPF."),
        ("Itens", "Quantidade de itens registrados na autorização."),
        ("Valor autorizado", "Valor pago registrado na autorização. A soma é o prejuízo estimado."),
        ("Dias após o óbito", "Dias entre a data do óbito e a data da venda."),
        ("Faixa de dias", f"Mesmas faixas das cores da tela: {faixas}."),
        ("Outras farmácias do CPF", "Quantidade de outras farmácias em que o mesmo CPF teve autorização após o óbito no período."),
        ("% do faturamento no período", "Valor autorizado após o óbito ÷ faturamento do Farmácia Popular da farmácia no mesmo período."),
        ("CPFs em comum", "Na aba Outras farmácias: quantos CPFs deste arquivo também tiveram autorização após o óbito naquela farmácia."),
        ("Participação nas coincidências", "CPFs em comum da farmácia ÷ soma dos CPFs em comum de todas as farmácias da lista."),
    ]
    header_row = 6
    ws.set_row(header_row, 22)
    ws.add_table(header_row, 0, header_row + len(itens), 1, {
        "name": "Criterios",
        "style": "Table Style Light 1",
        "data": [list(i) for i in itens],
        "columns": [
            {"header": "Termo", "format": f["texto_forte"], "header_format": f["cabecalho"]},
            {"header": "Definição", "format": f["texto_quebra"], "header_format": f["cabecalho"]},
        ],
    })
    _setup_page(ws, _format_cnpj(export.cnpj), header_row, secao=_SECAO, rodape="Critérios e definições")


def export_falecidos_xlsx(
    cnpj: str,
    data_inicio: Optional[date] = None,
    data_fim: Optional[date] = None,
    outro_cnpj: Optional[str] = None,
) -> tuple[str, bytes]:
    export = _preparar(cnpj, data_inicio, data_fim, outro_cnpj)
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
        "title": _TITULO,
        "subject": f"CNPJ {_format_cnpj(export.cnpj)} · {farmacia.razao_social}",
        "author": "Sentinela · CGU",
        "company": "Controladoria-Geral da União",
        "comments": f"Período {export.inicio} a {export.fim}",
    })
    f = _formatos(wb)
    _aba_autorizacoes(wb, f, export, farmacia, gerado_em)
    _aba_cpfs(wb, f, export, farmacia, gerado_em)
    _aba_outras(wb, f, export, farmacia, gerado_em)
    _aba_criterios(wb, f, export, farmacia, gerado_em)
    wb.close()
    return export.filename("xlsx"), buffer.getvalue()
