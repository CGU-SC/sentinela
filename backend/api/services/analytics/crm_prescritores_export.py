"""Exportação da lista "CRMs de interesse" (aba Perfil de CRMs do CNPJ) em CSV e Excel.

Os números vêm do mesmo cálculo da tela (get_crm_data), então o arquivo
reproduz exatamente a tabela. Com filtro ativo na tela, o frontend envia os
CRMs exibidos e a descrição do filtro, registrada no cabeçalho.
"""

import csv
import io
from dataclasses import dataclass
from datetime import date, datetime
from typing import Iterator, Optional

import xlsxwriter
import xlsxwriter.utility
from fastapi import HTTPException

from .crm import get_crm_data
from .crm_config import CRM_DAILY_RATE_ALERT_THRESHOLD
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

_SECAO = "Perfil de CRMs"
_TITULO = "Perfil de CRMs · CRMs de interesse"
_CRM_NAO_LOCALIZADO = "Não localizado na base do CFM"


# ── Dados ─────────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class _PerfilExport:
    cnpj: str
    inicio: str  # ISO (1º dia do mês inicial)
    fim: str  # ISO (último dia do mês final)
    crms: list[dict]
    serie_farmacia: dict[int, int]  # competência -> prescrições da farmácia
    filtro: Optional[str]
    total_crms_farmacia: int

    def filename(self, extensao: str) -> str:
        return f"crm_perfil_{self.cnpj}_{self.inicio[:7].replace('-', '')}-{self.fim[:7].replace('-', '')}.{extensao}"


def _comp_para_data(comp: int) -> date:
    return date(comp // 100, comp % 100, 1)


def _fim_do_mes(comp: int) -> date:
    ano, mes = comp // 100, comp % 100
    proximo = date(ano + 1, 1, 1) if mes == 12 else date(ano, mes + 1, 1)
    return date.fromordinal(proximo.toordinal() - 1)


def _alertas(m: dict) -> list[tuple[str, str, Optional[int]]]:
    """(chave, rótulo, quantidade) na mesma ordem e com os mesmos nomes da tabela da tela."""
    itens: list[tuple[str, str, Optional[int]]] = []
    if m["flag_crm_invalido"]:
        itens.append(("crm_invalido", "CRM não localizado", None))
    if m["flag_prescricao_antes_registro"]:
        itens.append(("crm_irregular", "CRM irregular (prescrição antes da inscrição)", None))
    if m["flag_robo"]:
        itens.append(("taxa_local", f"Mais de {CRM_DAILY_RATE_ALERT_THRESHOLD} presc./dia (local)", None))
    if m["flag_robo_oculto"] and not m["flag_robo"]:
        itens.append(("taxa_brasil", f"Mais de {CRM_DAILY_RATE_ALERT_THRESHOLD} presc./dia (Brasil)", None))
    if m["alerta_concentracao_unico_crm"]:
        itens.append(("seq_unico", "Autorizações em sequência · único CRM", int(m["qtd_alertas_crm_unico"])))
    if m["alerta_concentracao_multiplos_crms"]:
        itens.append(("seq_multiplos", "Autorizações em sequência · múltiplos CRMs", int(m["qtd_alertas_crm_multiplos"])))
    if m["alerta5_geografico"]:
        itens.append(("distancia", "Distância > 400 km", int(m["qtd_alertas_geograficos"])))
    if m["flag_crm_exclusivo"]:
        itens.append(("exclusivo", "CRM exclusivo", None))
    return itens


def _texto_alertas(m: dict) -> str:
    return "; ".join(f"{rotulo} ({qtd}×)" if qtd else rotulo for _, rotulo, qtd in _alertas(m))


_CAMPOS_OBRIGATORIOS = {
    "id_medico", "no_medico", "dt_inscricao_crm", "ranking", "nu_prescricoes", "vl_total_prescricoes",
    "nu_prescricoes_dia", "prescricoes_dia_total_brasil", "pct_participacao", "pct_acumulado",
    "pct_volume_aqui_vs_total", "nu_estabelecimentos", "competencia_inicio_atuacao",
    "competencia_fim_atuacao", "qtd_meses_atuacao", "serie_mensal_atuacao", "flag_crm_invalido",
    "flag_prescricao_antes_registro", "flag_robo", "flag_robo_oculto", "flag_crm_exclusivo",
    "alerta_concentracao_unico_crm", "alerta_concentracao_multiplos_crms", "alerta5_geografico",
    "qtd_alertas_crm_unico", "qtd_alertas_crm_multiplos", "qtd_alertas_geograficos",
}


def _preparar(
    cnpj: str,
    data_inicio: Optional[date],
    data_fim: Optional[date],
    ids: Optional[list[str]],
    filtro: Optional[str],
) -> _PerfilExport:
    cnpj_limpo = "".join(ch for ch in cnpj if ch.isdigit())
    if len(cnpj_limpo) != 14:
        raise HTTPException(status_code=422, detail="CNPJ inválido para exportação.")
    if data_inicio and data_fim and data_inicio > data_fim:
        raise HTTPException(status_code=422, detail="O início do período não pode ser posterior ao fim.")
    if ids is not None and not ids:
        raise HTTPException(status_code=422, detail="Nenhum CRM selecionado para exportação.")
    if ids is not None and not (filtro or "").strip():
        raise HTTPException(status_code=422, detail="Exportação filtrada sem a descrição do filtro.")

    dados = get_crm_data(
        cnpj_limpo,
        data_inicio=data_inicio.isoformat() if data_inicio else None,
        data_fim=data_fim.isoformat() if data_fim else None,
    )
    todos = dados.crms_interesse
    if not todos:
        raise HTTPException(status_code=404, detail="Não há CRMs com prescrição nesta farmácia no período.")
    faltando = sorted(_CAMPOS_OBRIGATORIOS - set(todos[0].keys()))
    if faltando:
        raise HTTPException(status_code=500, detail=f"Lista de CRMs sem campos obrigatórios: {', '.join(faltando)}.")
    summary = dados.summary
    comp_ini = summary.get("competencia_inicio_periodo")
    comp_fim = summary.get("competencia_fim_periodo")
    serie = summary.get("serie_mensal_farmacia")
    if comp_ini is None or comp_fim is None or not isinstance(serie, list):
        raise HTTPException(status_code=500, detail="Resumo CRM sem período ou série mensal da farmácia.")

    crms = sorted(todos, key=lambda m: int(m["ranking"]))
    if ids is not None:
        por_id = {str(m["id_medico"]): m for m in crms}
        desconhecidos = [i for i in ids if i not in por_id]
        if desconhecidos:
            raise HTTPException(
                status_code=422,
                detail=f"CRMs fora da lista da farmácia no período: {', '.join(desconhecidos[:5])}.",
            )
        escolhidos = set(ids)
        crms = [m for m in crms if str(m["id_medico"]) in escolhidos]

    return _PerfilExport(
        cnpj=cnpj_limpo,
        inicio=(data_inicio or _comp_para_data(int(comp_ini))).isoformat(),
        fim=(data_fim or _fim_do_mes(int(comp_fim))).isoformat(),
        crms=crms,
        serie_farmacia={int(p["competencia"]): int(p["qtd"]) for p in serie},
        filtro=filtro.strip() if filtro else None,
        total_crms_farmacia=len(todos),
    )


def _data_inscricao(m: dict) -> Optional[date]:
    valor = m["dt_inscricao_crm"]
    if valor in (None, ""):
        return None
    return valor if isinstance(valor, date) else date.fromisoformat(str(valor)[:10])


# ── Colunas da aba principal (CSV usa as mesmas) ─────────────────────────────
def _linha(m: dict) -> list:
    alertas = {chave: qtd for chave, _, qtd in _alertas(m)}
    sim = lambda chave: "Sim" if chave in alertas else ""  # noqa: E731
    return [
        int(m["ranking"]),
        str(m["id_medico"]),
        _title_case(m["no_medico"]) if m["no_medico"] else _CRM_NAO_LOCALIZADO,
        _data_inscricao(m),
        _texto_alertas(m),
        sim("crm_invalido"),
        sim("crm_irregular"),
        sim("taxa_local"),
        sim("taxa_brasil"),
        alertas.get("seq_unico") or 0,
        alertas.get("seq_multiplos") or 0,
        alertas.get("distancia") or 0,
        sim("exclusivo"),
        _comp_para_data(int(m["competencia_inicio_atuacao"])),
        _comp_para_data(int(m["competencia_fim_atuacao"])),
        int(m["qtd_meses_atuacao"]),
        int(m["nu_prescricoes"]),
        float(m["nu_prescricoes_dia"]),
        float(m["prescricoes_dia_total_brasil"]),
        float(m["vl_total_prescricoes"]),
        float(m["pct_participacao"]) / 100,
        float(m["pct_acumulado"]) / 100,
        float(m["pct_volume_aqui_vs_total"]) / 100,
        int(m["nu_estabelecimentos"]),
    ]


def _colunas() -> list[tuple[str, int, str, bool]]:
    """(cabeçalho, largura, chave do formato, é número) — mesma ordem de _linha."""
    limite = CRM_DAILY_RATE_ALERT_THRESHOLD
    return [
        ("Posição", 9, "inteiro", True),
        ("CRM/UF", 13, "texto", False),
        ("Nome do médico", 36, "texto", False),
        ("1ª inscrição no CFM", 13, "data", False),
        ("Alertas", 48, "texto", False),
        ("CRM não localizado", 12, "texto", False),
        ("CRM irregular", 11, "texto", False),
        (f"> {limite} presc./dia (local)", 12, "texto", False),
        (f"> {limite} presc./dia (Brasil)", 12, "texto", False),
        ("Aut. em sequência · único CRM", 13, "inteiro", True),
        ("Aut. em sequência · múltiplos CRMs", 14, "inteiro", True),
        ("Distância > 400 km", 11, "inteiro", True),
        ("CRM exclusivo", 10, "texto", False),
        ("Início da atuação", 11, "mes", False),
        ("Fim da atuação", 11, "mes", False),
        ("Meses com prescrição", 11, "inteiro", True),
        ("Prescrições", 12, "inteiro", True),
        ("Prescrições/dia (unidade)", 12, "decimal", True),
        ("Prescrições/dia (Brasil)", 12, "decimal", True),
        ("Valor autorizado", 16, "moeda", True),
        ("Participação no valor", 12, "pct", True),
        ("Participação acumulada", 12, "pct", True),
        ("Exclusividade", 12, "pct", True),
        ("Nº de estabelecimentos", 13, "inteiro", True),
    ]


# ── CSV ───────────────────────────────────────────────────────────────────────
def _csv_valor(valor, formato: str) -> str:
    """Valor da célula no CSV (pt-BR); percentuais em pontos percentuais (12,5 = 12,5%)."""
    if valor is None:
        return ""
    if formato == "data":
        return f"{valor:%d/%m/%Y}"
    if formato == "mes":
        return f"{valor:%m/%Y}"
    if formato == "pct":
        valor = valor * 100
    if isinstance(valor, float):
        return f"{valor:.4f}".rstrip("0").rstrip(".").replace(".", ",")
    if isinstance(valor, int):
        return str(valor)
    return _csv_text(str(valor))


def export_crm_perfil_csv(
    cnpj: str,
    data_inicio: Optional[date] = None,
    data_fim: Optional[date] = None,
    ids: Optional[list[str]] = None,
    filtro: Optional[str] = None,
) -> tuple[str, Iterator[bytes]]:
    export = _preparar(cnpj, data_inicio, data_fim, ids, filtro)

    def gerar() -> Iterator[bytes]:
        buffer = io.StringIO(newline="")
        writer = csv.writer(buffer, delimiter=";", lineterminator="\r\n")
        colunas = _colunas()
        writer.writerow(["CNPJ", *(nome for nome, *_ in colunas)])
        cnpj_formatado = _format_cnpj(export.cnpj)
        for m in export.crms:
            valores = zip(_linha(m), (formato for _, _, formato, _ in colunas))
            writer.writerow([cnpj_formatado, *(_csv_valor(v, formato) for v, formato in valores)])
        yield b"\xef\xbb\xbf" + buffer.getvalue().encode("utf-8")

    return export.filename("csv"), gerar()


# ── Excel ─────────────────────────────────────────────────────────────────────
def _formatos(wb: xlsxwriter.Workbook) -> dict:
    f = _formats(wb)
    base = {"font_name": "Calibri", "font_size": 10, "font_color": "#1E293B", "valign": "vcenter"}
    f["mes"] = wb.add_format({**base, "num_format": "mm/yyyy", "align": "left", "indent": 1})
    f["decimal"] = wb.add_format({**base, "num_format": "#,##0.00"})
    f["texto_quebra"] = wb.add_format({**base, "text_wrap": True, "valign": "top", "indent": 1})
    return f


def _cabecalho_filtro(ws, f: dict, export: _PerfilExport, ultima: int) -> None:
    texto = (
        f"Filtro aplicado na tela: {export.filtro} — {len(export.crms)} de {export.total_crms_farmacia} CRMs"
        if export.filtro
        else f"Todos os {export.total_crms_farmacia} CRMs com prescrição na farmácia no período"
    )
    ws.merge_range(5, 0, 5, ultima, texto, f["meta"])


def _aba_crms(wb, f, export: _PerfilExport, farmacia: _Farmacia, gerado_em: datetime) -> None:
    ws = wb.add_worksheet("CRMs")
    colunas = _colunas()
    ultima = len(colunas) - 1
    for idx, (_, largura, _, _) in enumerate(colunas):
        ws.set_column(idx, idx, largura)
    _write_header(ws, f, _TITULO, farmacia, export.cnpj, export.inicio, export.fim, gerado_em, ultima)
    _cabecalho_filtro(ws, f, export, ultima)

    com_alerta = sum(1 for m in export.crms if any(k != "exclusivo" for k, _, _ in _alertas(m)))
    prescricoes = sum(int(m["nu_prescricoes"]) for m in export.crms)
    valor = sum(float(m["vl_total_prescricoes"]) for m in export.crms)
    kpis = [
        (0, 1, "CRMs NO ARQUIVO", len(export.crms), f["kpi_valor"]),
        (2, 3, "CRMs COM ALERTAS", com_alerta, f["kpi_alerta"] if com_alerta else f["kpi_valor"]),
        (4, 4, "PRESCRIÇÕES", prescricoes, f["kpi_valor"]),
        (5, 8, "VALOR AUTORIZADO", valor, f["kpi_moeda"]),
    ]
    ws.set_row(7, 26)
    ws.set_row(8, 30)
    for c1, c2, rotulo, v, fmt_valor in kpis:
        if c1 == c2:
            ws.write_string(7, c1, rotulo, f["kpi_label"])
            ws.write_number(8, c1, v, fmt_valor)
        else:
            ws.merge_range(7, c1, 7, c2, rotulo, f["kpi_label"])
            ws.merge_range(8, c1, 8, c2, v, fmt_valor)

    header_row = 10
    ws.set_row(header_row, 42)
    dados = [_linha(m) for m in export.crms]
    ultima_linha = header_row + len(dados)
    ws.add_table(header_row, 0, ultima_linha, ultima, {
        "name": "CRMs",
        "style": "Table Style Light 1",
        "data": dados,
        "columns": [
            {"header": nome, "format": f[formato], "header_format": f["cabecalho_num"] if numero else f["cabecalho"]}
            for nome, _, formato, numero in colunas
        ],
    })
    indice = {nome: idx for idx, (nome, *_) in enumerate(colunas)}
    totais: list[tuple] = [("label", "Total")] + [("vazio",)] * ultima
    totais[indice["Prescrições"]] = ("soma", float(prescricoes), "total_inteiro")
    totais[indice["Valor autorizado"]] = ("soma", valor, "total_moeda")
    _write_total_row(ws, f, ultima_linha + 1, header_row + 1, ultima_linha, totais)
    # Linhas com algum alerta (exceto só "CRM exclusivo") em destaque: colunas
    # "Sim" das marcações e contagens > 0 das sequências e da distância.
    linha_excel = header_row + 2
    marcacoes = [nome for nome, _, formato, _ in colunas[5:12] if formato == "texto"]
    contagens = [nome for nome, _, formato, _ in colunas[5:12] if formato == "inteiro"]
    celula = lambda nome: f"${xlsxwriter.utility.xl_col_to_name(indice[nome])}{linha_excel}"  # noqa: E731
    condicoes = [f'{celula(n)}="Sim"' for n in marcacoes] + [f"{celula(n)}>0" for n in contagens]
    ws.conditional_format(header_row + 1, 0, ultima_linha, ultima, {
        "type": "formula",
        "criteria": f"=OR({','.join(condicoes)})",
        "format": f["alerta"],
    })
    ws.freeze_panes(header_row + 1, 3)
    ws.set_row(ultima_linha + 3, 30)
    ws.merge_range(ultima_linha + 3, 0, ultima_linha + 3, ultima,
                   "Mesmos números da tabela \"CRMs de interesse - detalhamento\" do Sentinela, ordenados pelo valor "
                   "autorizado. Linhas destacadas têm ao menos um alerta. Significado de cada coluna na aba Critérios.",
                   f["nota"])
    _setup_page(ws, _format_cnpj(export.cnpj), header_row, secao=_SECAO, rodape="CRMs de interesse")


def _aba_atuacao(wb, f, export: _PerfilExport, farmacia: _Farmacia, gerado_em: datetime) -> None:
    ws = wb.add_worksheet("Atuação mensal")
    colunas = [
        ("CRM/UF", 13, f["texto"], False),
        ("Nome do médico", 36, f["texto"], False),
        ("Competência", 12, f["mes"], False),
        ("Prescrições na farmácia", 14, f["inteiro"], True),
        ("Valor na farmácia", 16, f["moeda"], True),
        ("Prescrições do médico no Brasil", 16, f["inteiro"], True),
        ("Fatia desta farmácia no total do médico", 17, f["pct"], True),
        ("Fatia do médico no mês da farmácia", 17, f["pct"], True),
    ]
    ultima = len(colunas) - 1
    for idx, (_, largura, _, _) in enumerate(colunas):
        ws.set_column(idx, idx, largura)
    _write_header(ws, f, "Perfil de CRMs · Atuação mensal na farmácia", farmacia, export.cnpj,
                  export.inicio, export.fim, gerado_em, ultima)
    _cabecalho_filtro(ws, f, export, ultima)

    dados = []
    for m in export.crms:
        nome = _title_case(m["no_medico"]) if m["no_medico"] else _CRM_NAO_LOCALIZADO
        for p in sorted(m["serie_mensal_atuacao"], key=lambda x: int(x["competencia"])):
            comp = int(p["competencia"])
            qtd = int(p["qtd"])
            qtd_brasil = int(p["qtd_brasil"])
            mes_farmacia = export.serie_farmacia.get(comp)
            if mes_farmacia is None or mes_farmacia <= 0 or qtd_brasil <= 0:
                raise HTTPException(
                    status_code=500,
                    detail=f"Série mensal inconsistente para {m['id_medico']} em {comp}.",
                )
            dados.append([
                str(m["id_medico"]), nome, _comp_para_data(comp), qtd, float(p["valor"]), qtd_brasil,
                qtd / qtd_brasil, qtd / mes_farmacia,
            ])
    header_row = 7
    ws.set_row(header_row, 32)
    ultima_linha = header_row + len(dados)
    ws.add_table(header_row, 0, ultima_linha, ultima, {
        "name": "AtuacaoMensal",
        "style": "Table Style Light 1",
        "data": dados,
        "columns": [
            {"header": nome, "format": fmt, "header_format": f["cabecalho_num"] if numero else f["cabecalho"]}
            for nome, _, fmt, numero in colunas
        ],
    })
    ws.freeze_panes(header_row + 1, 2)
    ws.set_row(ultima_linha + 2, 30)
    ws.merge_range(ultima_linha + 2, 0, ultima_linha + 2, ultima,
                   "Um registro por médico e mês com prescrição nesta farmácia (mesma série do gráfico "
                   "\"Atuação na farmácia\"). A fatia do médico no mês da farmácia compara as prescrições dele "
                   "com todas as prescrições da farmácia naquele mês.", f["nota"])
    _setup_page(ws, _format_cnpj(export.cnpj), header_row, secao=_SECAO, rodape="Atuação mensal dos CRMs")


def _aba_criterios(wb, f, export: _PerfilExport, farmacia: _Farmacia, gerado_em: datetime) -> None:
    ws = wb.add_worksheet("Critérios")
    ws.set_column(0, 0, 34)
    ws.set_column(1, 1, 100)
    _write_header(ws, f, "Perfil de CRMs · Critérios e definições", farmacia, export.cnpj,
                  export.inicio, export.fim, gerado_em, 1)
    limite = CRM_DAILY_RATE_ALERT_THRESHOLD
    itens = [
        ("Posição", "Ordem do CRM pelo valor autorizado nesta farmácia no período (1 = maior valor)."),
        ("1ª inscrição no CFM", "Data da primeira inscrição do médico na UF do CRM, segundo a base do CFM."),
        ("CRM não localizado", "O CRM não consta na base do CFM."),
        ("CRM irregular", "Há prescrição anterior à data da primeira inscrição do médico no CFM."),
        (f"> {limite} presc./dia (local)",
         f"Prescrições nesta farmácia ÷ dias em que o médico prescreveu nela, acima de {limite} (o limite em si não gera alerta)."),
        (f"> {limite} presc./dia (Brasil)",
         f"A taxa nacional do médico (prescrições no Brasil ÷ dias distintos com prescrição no país, nos mesmos meses) "
         f"passa de {limite}, mas a taxa nesta farmácia não."),
        ("Aut. em sequência · único CRM", "Quantidade de alertas em que o mesmo CRM teve muitas autorizações em poucos minutos nesta farmácia."),
        ("Aut. em sequência · múltiplos CRMs", "Quantidade de sequências de autorizações de vários CRMs em poucos minutos nesta farmácia das quais o CRM participou."),
        ("Distância > 400 km", "Quantidade de ocorrências de prescrição do mesmo CRM, no mesmo mês, em farmácias a mais de 400 km uma da outra."),
        ("CRM exclusivo", "O CRM prescreveu apenas nesta farmácia no período."),
        ("Prescrições/dia (unidade)", "Prescrições nesta farmácia ÷ dias com prescrição nela."),
        ("Prescrições/dia (Brasil)", "Prescrições do médico no Brasil ÷ dias distintos com prescrição no país, nos meses de atuação nesta farmácia."),
        ("Participação no valor", "Valor autorizado do CRM ÷ valor autorizado de todos os CRMs da farmácia no período."),
        ("Participação acumulada", "Soma das participações do 1º CRM até a linha (curva de concentração)."),
        ("Exclusividade", "Prescrições do CRM nesta farmácia ÷ prescrições do CRM no Brasil, nos mesmos meses."),
        ("Nº de estabelecimentos", "Maior número de farmácias em que o CRM prescreveu no Brasil em um mesmo mês, nos meses de atuação nesta farmácia."),
    ]
    header_row = 6
    ws.set_row(header_row, 22)
    ws.add_table(header_row, 0, header_row + len(itens), 1, {
        "name": "Criterios",
        "style": "Table Style Light 1",
        "data": [list(i) for i in itens],
        "columns": [
            {"header": "Coluna", "format": f["texto_forte"], "header_format": f["cabecalho"]},
            {"header": "Definição", "format": f["texto_quebra"], "header_format": f["cabecalho"]},
        ],
    })
    _setup_page(ws, _format_cnpj(export.cnpj), header_row, secao=_SECAO, rodape="Critérios e definições")


def export_crm_perfil_xlsx(
    cnpj: str,
    data_inicio: Optional[date] = None,
    data_fim: Optional[date] = None,
    ids: Optional[list[str]] = None,
    filtro: Optional[str] = None,
) -> tuple[str, bytes]:
    export = _preparar(cnpj, data_inicio, data_fim, ids, filtro)
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
    _aba_crms(wb, f, export, farmacia, gerado_em)
    _aba_atuacao(wb, f, export, farmacia, gerado_em)
    _aba_criterios(wb, f, export, farmacia, gerado_em)
    wb.close()
    return export.filename("xlsx"), buffer.getvalue()
