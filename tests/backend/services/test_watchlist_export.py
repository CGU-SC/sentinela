import csv
from datetime import date
from io import BytesIO, StringIO
from types import SimpleNamespace
from zipfile import ZipFile

import pytest
from fastapi import HTTPException

from backend.api.services import watchlist_export as export

_INICIO, _FIM = date(2024, 1, 1), date(2024, 6, 30)


def _item(cnpj, razao="Farmacia", adicionado="2026-10-02T14:33:04.423Z", observacao=""):
    return {"cnpj": cnpj, "razaoSocial": razao, "adicionadoEm": adicionado, "observacao": observacao}


def _dados(cnpj, val_sem_comp, total_mov, **extra):
    campos = {
        "cnpj": cnpj, "razao_social": "RAZAO DA BASE", "municipio": "São Paulo", "uf": "SP",
        "score_risco_final": 88.5, "classificacao_risco": "CRÍTICO",
        "percValSemComp": val_sem_comp / total_mov * 100, "valSemComp": val_sem_comp, "totalMov": total_mov,
    }
    campos.update(extra)
    return SimpleNamespace(**campos)


def _instalar(monkeypatch, *, lista, dados, evidencias=()):
    chamadas = []
    monkeypatch.setattr(export.PreferencesService, "read", classmethod(lambda _cls: {"watchlist": lista}))
    monkeypatch.setattr(export.EvidenciasService, "resumo_por_cnpj", classmethod(lambda _cls: list(evidencias)))

    def resumo(db, data_inicio, data_fim, *, cnpjs, secoes):
        chamadas.append((db, data_inicio, data_fim, cnpjs, secoes))
        return SimpleNamespace(resultado_cnpjs=dados)

    monkeypatch.setattr(export, "get_dashboard_data", resumo)
    return chamadas


def _lista_padrao():
    """Três farmácias: a menor primeiro na lista, a maior depois e uma sem dados no período."""
    lista = [
        _item("11111111000111", "Farmacia Menor", observacao="=cmd|' /C calc'!A0"),
        _item("22222222000122", "", adicionado=None),
        _item("33333333000133", "Farmacia Sem Dados"),
    ]
    dados = [_dados("11111111000111", 100.0, 400.0), _dados("22222222000122", 300.0, 600.0)]
    evidencias = [{"cnpj": "11111111000111", "quantidade": 2, "ultima_em": "2026-10-01T10:00:00+00:00"}]
    return lista, dados, evidencias


def test_list_export_orders_by_unverified_value_keeps_pharmacies_without_data_and_sums_only_the_rest(monkeypatch):
    lista, dados, evidencias = _lista_padrao()
    chamadas = _instalar(monkeypatch, lista=lista, dados=dados, evidencias=evidencias)
    db = object()
    resultado = export._preparar(db, _INICIO, _FIM)

    assert chamadas == [(db, _INICIO, _FIM, ["11111111000111", "22222222000122", "33333333000133"], ["cnpjs"])]
    assert [linha.cnpj for linha in resultado.linhas] == ["22222222000122", "11111111000111", "33333333000133"]
    maior, menor, sem_dados = resultado.linhas
    # Sem razão social na lista vale a da base; sem data de inclusão a célula fica vazia.
    assert maior.razao_social == "RAZAO DA BASE" and maior.adicionado_em is None
    assert maior.perc_sem_comp == pytest.approx(0.5) and maior.qtd_evidencias == 0 and maior.ultima_evidencia is None
    assert menor.qtd_evidencias == 2 and menor.ultima_evidencia == date(2026, 10, 1)
    assert menor.adicionado_em == date(2026, 10, 2)
    assert sem_dados.com_dados is False and sem_dados.total_mov is None and sem_dados.municipio is None
    assert resultado.total_mov == 1000.0 and resultado.val_sem_comp == 400.0
    assert resultado.perc_sem_comp == pytest.approx(0.4)
    assert resultado.filename("xlsx") == "farmacias_monitoradas_202401-202406.xlsx"


def test_list_export_csv_uses_brazilian_formats_and_neutralizes_formula_text(monkeypatch):
    lista, dados, evidencias = _lista_padrao()
    _instalar(monkeypatch, lista=lista, dados=dados, evidencias=evidencias)
    nome, partes = export.export_watchlist_csv(object(), _INICIO, _FIM)
    conteudo = b"".join(partes)

    assert nome == "farmacias_monitoradas_202401-202406.csv"
    assert conteudo.startswith(b"\xef\xbb\xbf")
    linhas = list(csv.reader(StringIO(conteudo.decode("utf-8-sig")), delimiter=";"))
    cabecalho, primeira, segunda, terceira = linhas
    assert cabecalho[:3] == ["Posição", "CNPJ", "Razão social"] and cabecalho[-1] == "Observação"
    coluna = {nome: idx for idx, nome in enumerate(cabecalho)}
    assert primeira[coluna["Posição"]] == "1" and primeira[coluna["CNPJ"]] == '="22.222.222/0001-22"'
    assert primeira[coluna["% sem comprovação"]] == "50" and primeira[coluna["Valor sem comprovação"]] == "300"
    assert primeira[coluna["Score de risco"]] == "88,5" and primeira[coluna["Adicionada em"]] == ""
    assert segunda[coluna["Última evidência"]] == "01/10/2026" and segunda[coluna["Evidências"]] == "2"
    # Observação que começa com "=" sai como texto, não como fórmula.
    assert segunda[coluna["Observação"]].startswith("'=cmd")
    assert terceira[coluna["Situação no período"]] == "Sem dados no período"
    assert terceira[coluna["Total movimentado"]] == "" and terceira[coluna["Município"]] == ""


def test_list_export_workbook_has_totals_criteria_and_marks_pharmacies_without_data(monkeypatch):
    lista, dados, evidencias = _lista_padrao()
    _instalar(monkeypatch, lista=lista, dados=dados, evidencias=evidencias)
    nome, conteudo = export.export_watchlist_xlsx(object(), _INICIO, _FIM)

    assert nome == "farmacias_monitoradas_202401-202406.xlsx" and conteudo[:2] == b"PK"
    with ZipFile(BytesIO(conteudo)) as pasta:
        textos = pasta.read("xl/sharedStrings.xml").decode("utf-8")
        farmacias = pasta.read("xl/worksheets/sheet1.xml").decode("utf-8")
        planilha = pasta.read("xl/workbook.xml").decode("utf-8")
        assert "xl/worksheets/sheet2.xml" in pasta.namelist()
    assert 'name="Farmácias"' in planilha and 'name="Critérios"' in planilha
    assert "Farmácias monitoradas" in textos and "Lista de interesse  ·  3 farmácias  ·  1 sem dados no período" in textos
    assert "Período de análise: 01/01/2024 a 30/06/2024" in textos
    assert "VALOR SEM COMPROVAÇÃO" in textos and "% SEM COMPROVAÇÃO" in textos
    assert "22.222.222/0001-22" in textos and "Farmacia Sem Dados" in textos and "Sem dados no período" in textos
    # Texto da lista nunca vira fórmula; os totais usam SUBTOTAL e o percentual do conjunto.
    assert "=cmd|" in textos
    assert "SUBTOTAL(109,J11:J13)" in farmacias and "SUBTOTAL(109,K11:K13)" in farmacias
    assert 'IF(K14&gt;0,J14/K14,"")' in farmacias


def test_list_export_without_any_movement_shows_dash_instead_of_percentage(monkeypatch):
    _instalar(monkeypatch, lista=[_item("33333333000133", "Farmacia Sem Dados")], dados=[])
    resultado = export._preparar(object(), _INICIO, _FIM)
    assert resultado.total_mov == 0 and resultado.perc_sem_comp is None

    _, conteudo = export.export_watchlist_xlsx(object(), _INICIO, _FIM)
    with ZipFile(BytesIO(conteudo)) as pasta:
        textos = pasta.read("xl/sharedStrings.xml").decode("utf-8")
    assert "Lista de interesse  ·  1 farmácia  ·  1 sem dados no período" in textos
    assert "<t>—</t>" in textos


def test_list_export_fails_visibly_on_invalid_requests_and_sources(monkeypatch):
    lista, dados, _ = _lista_padrao()

    def erro(**instalacao):
        _instalar(monkeypatch, **{"lista": lista, "dados": dados, **instalacao})
        with pytest.raises(HTTPException) as capturado:
            export._preparar(object(), _INICIO, _FIM)
        return capturado.value

    _instalar(monkeypatch, lista=lista, dados=dados)
    with pytest.raises(HTTPException, match="não pode ser posterior") as invertido:
        export._preparar(object(), _FIM, _INICIO)
    assert invertido.value.status_code == 422

    vazia = erro(lista=[])
    assert vazia.status_code == 404 and "Não há farmácias" in vazia.detail
    repetida = erro(lista=[_item("11111111000111"), _item("11111111000111")])
    assert repetida.status_code == 503 and "repetido" in repetida.detail
    sem_secao = erro(dados=None)
    assert sem_secao.status_code == 503 and "sem a seção de CNPJs" in sem_secao.detail
    incompleta = erro(dados=[_dados("11111111000111", 100.0, 400.0, percValSemComp=None)])
    assert incompleta.status_code == 503 and "indicadores incompletos" in incompleta.detail
    data_ruim = erro(lista=[_item("11111111000111", adicionado="ontem")])
    assert data_ruim.status_code == 503 and "Data inválida em adicionadoEm" in data_ruim.detail

    _instalar(monkeypatch, lista=lista, dados=dados)

    def preferencias_fora(_cls):
        raise export.PreferencesError("arquivo ilegível")

    monkeypatch.setattr(export.PreferencesService, "read", classmethod(preferencias_fora))
    with pytest.raises(HTTPException, match="Lista de interesse indisponível: arquivo ilegível") as preferencias:
        export._preparar(object(), _INICIO, _FIM)
    assert preferencias.value.status_code == 503

    _instalar(monkeypatch, lista=lista, dados=dados)

    def evidencias_fora(_cls):
        raise export.EvidenciasError("cesta ilegível")

    monkeypatch.setattr(export.EvidenciasService, "resumo_por_cnpj", classmethod(evidencias_fora))
    with pytest.raises(HTTPException, match="Cesta de evidências indisponível: cesta ilegível") as cesta:
        export._preparar(object(), _INICIO, _FIM)
    assert cesta.value.status_code == 503
