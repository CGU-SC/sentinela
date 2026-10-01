"""Evidencias de um CRM no Brasil (painel "Evidencias" do historico em /analises).

Mesmos alertas do painel do CRM na aba Autorizacoes do estabelecimento, mas em
todas as farmacias do medico, uma linha por janela de sequencia:

* unico: crm_concentracao_unico_alertas_global (sequencias do proprio CRM);
* multiplos: crm_concentracao_multiplo_alertas_global cruzada com as
  autorizacoes do medico no Raio-X (crm_raiox_tx_global). A tabela de alertas
  nao identifica o medico: ele entra na janela quando tem ao menos uma
  autorizacao dentro dela (mesma regra de crm._build_alertas_crm_multiplos_por_medico);
* distancia: geografico_global (pares de farmacias distantes no mesmo mes).

Periodo por competencia (como o historico e a aba do estabelecimento). Com
filtro de farmacia (id_cnpj): sequencias so dela e pares que a envolvem.
"""

from dataclasses import dataclass
from datetime import date, datetime
from typing import Optional

import polars as pl
from fastapi import HTTPException

from data_cache import (
    get_dados_medico_df,
    get_df_perfil_estabelecimento,
    scan_crm_concentracao_multiplo_alertas_global,
    scan_crm_concentracao_unico_alertas_global,
    scan_crm_raiox_tx_global,
    scan_geografico_global,
)

from ...schemas.analytics import (
    CrmEvidenciaAutorizacaoSchema,
    CrmEvidenciaAutorizacoesResponse,
    CrmEvidenciaDistanciaSchema,
    CrmEvidenciaMultiplosSchema,
    CrmEvidenciaUnicoSchema,
    CrmEvidenciasResponse,
    CrmEvidenciasResumoDistanciaSchema,
    CrmEvidenciasResumoSequenciaSchema,
)
from .alertas_alvos import SEVERIDADES_SEQUENCIA
from .cache_geracao import CacheGeracao
from .crm_analysis import _competencia, _period_bounds

TIPOS_EVIDENCIA = ("unico", "multiplos", "distancia")
# Ordenacoes aceitas por tipo: campo da API -> coluna do DataFrame.
ORDENACOES = {
    "unico": {"data": "dt_ini_hora", "severidade": "id_severidade", "taxa_hora": "taxa_hora",
              "autorizacoes": "nu_autorizacoes"},
    "multiplos": {"data": "dt_ini_hora", "severidade": "id_severidade", "taxa_hora": "taxa_hora",
                  "autorizacoes": "nu_autorizacoes_crm"},
    "distancia": {"data": "competencia", "distancia": "distancia_km"},
}
ORDENACAO_PADRAO = {"unico": "data", "multiplos": "data", "distancia": "distancia"}

_CACHE = CacheGeracao(max_itens=32)


@dataclass(frozen=True)
class EvidenciasMedico:
    """As tres tabelas de evidencias de um medico num periodo (e farmacia)."""

    unico: pl.DataFrame
    multiplos: pl.DataFrame
    distancia: pl.DataFrame


def _cadastro(id_cnpjs: list[int]) -> pl.DataFrame:
    """Farmacia (id_cnpj -> cnpj, razao social, municipio, UF); ausente responde 503."""
    if not id_cnpjs:
        return pl.DataFrame(schema={"id_cnpj": pl.Int32, "cnpj": pl.Utf8, "razao_social": pl.Utf8,
                                    "municipio": pl.Utf8, "uf": pl.Utf8})
    cadastro = (
        get_df_perfil_estabelecimento()
        .select([
            pl.col("id_cnpj").cast(pl.Int32),
            pl.col("cnpj").cast(pl.Utf8),
            pl.col("razao_social").cast(pl.Utf8),
            pl.col("no_municipio").cast(pl.Utf8).alias("municipio"),
            pl.col("uf").cast(pl.Utf8),
        ])
        .filter(pl.col("id_cnpj").is_in(id_cnpjs))
        .unique("id_cnpj", keep="first")
    )
    ausentes = sorted(set(id_cnpjs) - set(cadastro.get_column("id_cnpj").to_list()))
    if ausentes:
        raise HTTPException(
            status_code=503,
            detail=f"Farmacias com alerta do CRM sem cadastro no perfil de estabelecimentos: {ausentes[:5]}.",
        )
    return cadastro


def _cnpj_da_farmacia(id_cnpj: int) -> str:
    linha = get_df_perfil_estabelecimento().filter(pl.col("id_cnpj").cast(pl.Int32) == id_cnpj)
    if linha.height != 1:
        raise HTTPException(status_code=422, detail=f"Farmacia {id_cnpj} nao encontrada no perfil de estabelecimentos.")
    return str(linha.item(0, "cnpj"))


def _conferir_severidades(df: pl.DataFrame, origem: str) -> None:
    desconhecidas = set(df.get_column("id_severidade").unique().to_list()) - SEVERIDADES_SEQUENCIA
    if desconhecidas:
        raise HTTPException(status_code=503, detail=f"Severidade desconhecida em {origem}: {sorted(desconhecidas)}.")


# Nos filtros dos scans as colunas sao comparadas sem cast (id_medico e texto,
# id_cnpj e Int32 nos modulos): com cast o Polars nao usa as estatisticas do
# Parquet e le o arquivo inteiro (o Raio-X tem 145 mi de linhas).
def _unico(id_medico: str, comp_ini: int, comp_fim: int, id_cnpj: Optional[int]) -> pl.DataFrame:
    filtro = (pl.col("id_medico") == id_medico) & pl.col("competencia").is_between(comp_ini, comp_fim)
    if id_cnpj is not None:
        filtro &= pl.col("id_cnpj") == id_cnpj
    df = (
        scan_crm_concentracao_unico_alertas_global()
        .filter(filtro)
        .select([
            pl.col("id_cnpj").cast(pl.Int32),
            pl.col("dt_alerta").cast(pl.Utf8).str.slice(0, 10).alias("dt"),
            pl.col("hr_janela").cast(pl.Int32),
            pl.col("dt_ini_hora").cast(pl.Datetime),
            pl.col("dt_fim_hora").cast(pl.Datetime),
            pl.col("nu_prescricoes_dia").cast(pl.Int64).alias("nu_autorizacoes"),
            pl.col("nu_minutos_dia").cast(pl.Int64).alias("nu_minutos"),
            pl.col("taxa_hora").cast(pl.Float64),
            pl.col("id_severidade").cast(pl.Int32),
        ])
        .collect()
    )
    _conferir_severidades(df, "sequencias de unico CRM")
    return df


def _multiplos(id_medico: str, comp_ini: int, comp_fim: int, id_cnpj: Optional[int]) -> pl.DataFrame:
    competencia_tx = (
        pl.col("dt_janela").cast(pl.Utf8).str.slice(0, 4).cast(pl.Int32) * 100
        + pl.col("dt_janela").cast(pl.Utf8).str.slice(5, 2).cast(pl.Int32)
    )
    filtro_tx = (pl.col("id_medico") == id_medico) & competencia_tx.is_between(comp_ini, comp_fim)
    if id_cnpj is not None:
        filtro_tx &= pl.col("id_cnpj") == id_cnpj
    tx = (
        scan_crm_raiox_tx_global()
        .filter(filtro_tx)
        .select([
            pl.col("id_cnpj").cast(pl.Int32),
            pl.col("dt_janela").cast(pl.Utf8).str.slice(0, 10).alias("dt"),
            pl.col("data_hora").cast(pl.Utf8).str.strptime(pl.Datetime, strict=False).alias("data_hora"),
            pl.col("num_autorizacao").cast(pl.Utf8),
        ])
        .collect()
    )
    vazio = pl.DataFrame(schema={
        "id_cnpj": pl.Int32, "dt": pl.Utf8, "hr_janela": pl.Int32, "dt_ini_hora": pl.Datetime,
        "dt_fim_hora": pl.Datetime, "nu_autorizacoes_crm": pl.Int64, "nu_autorizacoes_total": pl.Int64,
        "nu_crms": pl.Int64, "nu_minutos": pl.Int64, "taxa_hora": pl.Float64, "id_severidade": pl.Int32,
    })
    if tx.is_empty():
        return vazio
    if tx.get_column("data_hora").null_count():
        raise HTTPException(status_code=503, detail="Autorizacoes do Raio-X sem data/hora valida.")
    farmacias = tx.get_column("id_cnpj").unique().to_list()
    dias = tx.get_column("dt").unique().to_list()
    alertas = (
        scan_crm_concentracao_multiplo_alertas_global()
        .filter(
            pl.col("id_cnpj").is_in(farmacias)
            & pl.col("competencia").is_between(comp_ini, comp_fim)
            & pl.col("dt_alerta").cast(pl.Utf8).str.slice(0, 10).is_in(dias)
        )
        .select([
            pl.col("id_cnpj").cast(pl.Int32),
            pl.col("dt_alerta").cast(pl.Utf8).str.slice(0, 10).alias("dt"),
            pl.col("hr_janela").cast(pl.Int32),
            pl.col("dt_ini_concentracao").cast(pl.Utf8).str.strptime(pl.Datetime, strict=False).alias("dt_ini_hora"),
            pl.col("dt_fim_concentracao").cast(pl.Utf8).str.strptime(pl.Datetime, strict=False).alias("dt_fim_hora"),
            pl.col("nu_prescricoes").cast(pl.Int64).alias("nu_autorizacoes_total"),
            # mesmas escolhas do painel do estabelecimento (nu_crms, senao distintos)
            pl.coalesce(pl.col("nu_crms"), pl.col("nu_crms_distintos")).cast(pl.Int64).alias("nu_crms"),
            pl.coalesce(pl.col("nu_minutos_intervalo"), pl.col("nu_minutos_span")).cast(pl.Int64).alias("nu_minutos"),
            pl.col("taxa_hora").cast(pl.Float64),
            pl.col("id_severidade").cast(pl.Int32),
        ])
        .collect()
        .with_row_index("_alerta")
    )
    if alertas.is_empty():
        return vazio
    if alertas.select(pl.col("dt_ini_hora").is_null() | pl.col("dt_fim_hora").is_null()).to_series().any():
        raise HTTPException(status_code=503, detail="Alerta de multiplos CRMs sem inicio/fim da janela.")
    _conferir_severidades(alertas, "sequencias de multiplos CRMs")
    cruzado = (
        tx.join(alertas, on=["id_cnpj", "dt"], how="inner")
        .filter(pl.col("data_hora").is_between(pl.col("dt_ini_hora"), pl.col("dt_fim_hora")))
        .group_by("_alerta")
        .agg([
            pl.col("num_autorizacao").n_unique().cast(pl.Int64).alias("nu_autorizacoes_crm"),
            *(pl.col(c).first() for c in vazio.columns if c != "nu_autorizacoes_crm"),
        ])
        .select(vazio.columns)
    )
    return cruzado


def _distancia(id_medico: str, comp_ini: int, comp_fim: int, id_cnpj: Optional[int]) -> pl.DataFrame:
    filtro = (pl.col("id_medico") == id_medico) & pl.col("competencia").is_between(comp_ini, comp_fim)
    if id_cnpj is not None:
        cnpj = _cnpj_da_farmacia(id_cnpj)
        filtro &= (pl.col("cnpj_a") == cnpj) | (pl.col("cnpj_b") == cnpj)
    df = (
        scan_geografico_global()
        .filter(filtro)
        .select([
            pl.col("competencia").cast(pl.Int32),
            *(pl.col(f"{c}_{lado}").cast(t).alias(f"{c}_{lado}")
              for lado in ("a", "b")
              for c, t in (("cnpj", pl.Utf8), ("no_municipio", pl.Utf8), ("sg_uf", pl.Utf8),
                           ("dt_ini", pl.Utf8), ("dt_fim", pl.Utf8), ("nu_prescricoes", pl.Int64),
                           ("vl_autorizacoes", pl.Float64))),
            pl.col("vl_autorizacoes_total").cast(pl.Float64),
            pl.col("distancia_km").cast(pl.Float64),
        ])
        .collect()
    )
    if df.select(pl.col("distancia_km").is_null().any()).item():
        raise HTTPException(status_code=503, detail="Par de farmacias distantes sem distancia calculada.")
    # Razao social das duas farmacias (o par traz so CNPJ, municipio e UF).
    cnpjs = sorted(set(df.get_column("cnpj_a").to_list()) | set(df.get_column("cnpj_b").to_list()))
    nomes = (
        get_df_perfil_estabelecimento()
        .select([pl.col("cnpj").cast(pl.Utf8), pl.col("razao_social").cast(pl.Utf8)])
        .filter(pl.col("cnpj").is_in(cnpjs))
        .unique("cnpj", keep="first")
    )
    ausentes = sorted(set(cnpjs) - set(nomes.get_column("cnpj").to_list()))
    if ausentes:
        raise HTTPException(
            status_code=503,
            detail=f"Farmacias de pares distantes sem cadastro no perfil de estabelecimentos: {ausentes[:5]}.",
        )
    for lado in ("a", "b"):
        df = df.join(nomes.rename({"cnpj": f"cnpj_{lado}", "razao_social": f"razao_social_{lado}"}),
                     on=f"cnpj_{lado}", how="left")
    return df


def evidencias_do_medico(
    id_medico: str, inicio: date, fim: date, id_cnpj: Optional[int]
) -> EvidenciasMedico:
    """As tres tabelas, com a farmacia (cadastro) nas sequencias; em cache por geracao."""
    comp_ini, comp_fim = _competencia(inicio), _competencia(fim)

    def calcular() -> EvidenciasMedico:
        try:
            unico = _unico(id_medico, comp_ini, comp_fim, id_cnpj)
            multiplos = _multiplos(id_medico, comp_ini, comp_fim, id_cnpj)
            distancia = _distancia(id_medico, comp_ini, comp_fim, id_cnpj)
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(status_code=503, detail=f"Alertas do CRM indisponiveis: {exc}") from exc
        farmacias = sorted(set(unico.get_column("id_cnpj").to_list()) | set(multiplos.get_column("id_cnpj").to_list()))
        cadastro = _cadastro(farmacias)
        return EvidenciasMedico(
            unico=unico.join(cadastro, on="id_cnpj", how="left"),
            multiplos=multiplos.join(cadastro, on="id_cnpj", how="left"),
            distancia=distancia,
        )

    return _CACHE.obter(("evidencias", id_medico, comp_ini, comp_fim, id_cnpj), calcular)


def _resumo_sequencia(df: pl.DataFrame) -> CrmEvidenciasResumoSequenciaSchema:
    contagem = dict(df.group_by("id_severidade").len().iter_rows()) if df.height else {}
    return CrmEvidenciasResumoSequenciaSchema(
        qtd_alertas=df.height,
        qtd_dias=df.get_column("dt").n_unique() if df.height else 0,
        qtd_farmacias=df.get_column("id_cnpj").n_unique() if df.height else 0,
        pior_severidade=max(contagem) if contagem else None,
        por_severidade={str(s): int(contagem.get(s, 0)) for s in sorted(SEVERIDADES_SEQUENCIA)},
    )


def _resumo_distancia(df: pl.DataFrame) -> CrmEvidenciasResumoDistanciaSchema:
    return CrmEvidenciasResumoDistanciaSchema(
        qtd_pares=df.height,
        qtd_meses=df.get_column("competencia").n_unique() if df.height else 0,
        maior_distancia_km=float(df.get_column("distancia_km").max()) if df.height else None,
    )


def _ordenar(df: pl.DataFrame, tipo: str, sort_field: str, descendente: bool) -> pl.DataFrame:
    coluna = ORDENACOES[tipo][sort_field]
    # desempate estavel: data/hora (ou mes) e farmacia, sempre no mesmo sentido
    desempate = ["competencia", "cnpj_a", "cnpj_b"] if tipo == "distancia" else ["dt_ini_hora", "id_cnpj"]
    colunas = [coluna, *(c for c in desempate if c != coluna)]
    return df.sort(colunas, descending=[descendente] + [False] * (len(colunas) - 1), nulls_last=True)


def validar_parametros(tipo: str, sort_field: Optional[str], severidade: Optional[int]) -> str:
    if tipo not in TIPOS_EVIDENCIA:
        raise HTTPException(status_code=422, detail="tipo deve ser unico, multiplos ou distancia.")
    campo = sort_field or ORDENACAO_PADRAO[tipo]
    if campo not in ORDENACOES[tipo]:
        raise HTTPException(status_code=422, detail=f"Ordenacao invalida para {tipo}: use {sorted(ORDENACOES[tipo])}.")
    if severidade is not None and (tipo == "distancia" or severidade not in SEVERIDADES_SEQUENCIA):
        raise HTTPException(status_code=422, detail="severidade vale so para sequencias: 1 alta, 2 grave, 3 critica, 4 extrema.")
    return campo


def get_crm_medico_evidencias(
    *,
    id_medico: str,
    tipo: str,
    data_inicio: Optional[date] = None,
    data_fim: Optional[date] = None,
    id_cnpj: Optional[int] = None,
    severidade: Optional[int] = None,
    sort_field: Optional[str] = None,
    sort_order: str = "desc",
    page: int = 1,
    page_size: int = 15,
) -> CrmEvidenciasResponse:
    """Resumo das tres evidencias e uma pagina da tabela pedida (tipo)."""
    id_medico = id_medico.strip()
    if not id_medico:
        raise HTTPException(status_code=422, detail="id_medico obrigatorio.")
    campo = validar_parametros(tipo, sort_field, severidade)
    if sort_order not in ("asc", "desc"):
        raise HTTPException(status_code=422, detail="sort_order deve ser asc ou desc.")
    inicio, fim = _period_bounds(data_inicio, data_fim)
    ev = evidencias_do_medico(id_medico, inicio, fim, id_cnpj)

    tabela = getattr(ev, tipo)
    if severidade is not None:
        tabela = tabela.filter(pl.col("id_severidade") == severidade)
    tabela = _ordenar(tabela, tipo, campo, sort_order == "desc")
    pagina = tabela.slice((page - 1) * page_size, page_size)

    resposta = dict(
        id_medico=id_medico,
        periodo_inicio=inicio,
        periodo_fim=fim,
        id_cnpj=id_cnpj,
        tipo=tipo,
        resumo_unico=_resumo_sequencia(ev.unico),
        resumo_multiplos=_resumo_sequencia(ev.multiplos),
        resumo_distancia=_resumo_distancia(ev.distancia),
        total=tabela.height,
        page=page,
        page_size=page_size,
    )
    if tipo == "unico":
        resposta["linhas_unico"] = [CrmEvidenciaUnicoSchema(**r) for r in pagina.iter_rows(named=True)]
    elif tipo == "multiplos":
        resposta["linhas_multiplos"] = [CrmEvidenciaMultiplosSchema(**r) for r in pagina.iter_rows(named=True)]
    else:
        resposta["linhas_distancia"] = [CrmEvidenciaDistanciaSchema(**r) for r in pagina.iter_rows(named=True)]
    return CrmEvidenciasResponse(**resposta)


def nome_do_medico(id_medico: str) -> Optional[str]:
    """Nome do medico no cadastro (None se nao localizado no CFM)."""
    medico = (
        get_dados_medico_df().lazy()
        .filter(pl.col("id_medico").cast(pl.Utf8) == id_medico)
        .select("no_medico")
        .collect()
        .unique()
    )
    if medico.height > 1:
        raise HTTPException(status_code=503, detail=f"Cadastro medico inconsistente para CRM {id_medico}.")
    return medico.item(0, 0) if medico.height else None


# Janela mais longa aceita (as sequencias tem minutos; protege a leitura).
JANELA_MAXIMA_HORAS = 6


def get_crm_evidencia_autorizacoes(
    *, id_cnpj: int, id_medico: str, inicio: datetime, fim: datetime
) -> CrmEvidenciaAutorizacoesResponse:
    """Autorizacoes de uma janela de sequencia numa farmacia (todas os CRMs), do Raio-X.

    As do CRM consultado vem marcadas (do_crm). Mesma fonte da Cronologia do
    estabelecimento (crm_raiox_tx_global).
    """
    id_medico = id_medico.strip()
    if not id_medico:
        raise HTTPException(status_code=422, detail="id_medico obrigatorio.")
    if fim < inicio or inicio.date() != fim.date():
        raise HTTPException(status_code=422, detail="A janela deve comecar e terminar no mesmo dia, com inicio antes do fim.")
    if (fim - inicio).total_seconds() > JANELA_MAXIMA_HORAS * 3600:
        raise HTTPException(status_code=422, detail=f"Janela maior que {JANELA_MAXIMA_HORAS} horas.")
    farmacia = _cadastro([id_cnpj]).row(0, named=True)
    try:
        tx = (
            scan_crm_raiox_tx_global()
            .filter(
                (pl.col("id_cnpj") == id_cnpj)
                & (pl.col("dt_janela").cast(pl.Utf8).str.slice(0, 10) == inicio.date().isoformat())
            )
            .select([
                pl.col("data_hora").cast(pl.Utf8).str.strptime(pl.Datetime, strict=False).alias("data_hora"),
                pl.col("num_autorizacao").cast(pl.Utf8),
                pl.col("id_medico").cast(pl.Utf8),
                pl.col("valor_pago").cast(pl.Float64),
            ])
            .collect()
        )
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Raio-X de autorizacoes indisponivel: {exc}") from exc
    if tx.get_column("data_hora").null_count():
        raise HTTPException(status_code=503, detail="Autorizacoes do Raio-X sem data/hora valida.")
    tx = tx.filter(pl.col("data_hora").is_between(inicio, fim)).sort(["data_hora", "num_autorizacao"])
    nomes = (
        get_dados_medico_df().lazy()
        .filter(pl.col("id_medico").cast(pl.Utf8).is_in(tx.get_column("id_medico").unique().to_list()))
        .select([pl.col("id_medico").cast(pl.Utf8), pl.col("no_medico").cast(pl.Utf8)])
        .collect()
        .unique("id_medico", keep="first")
    )
    tx = tx.join(nomes, on="id_medico", how="left").with_columns((pl.col("id_medico") == id_medico).alias("do_crm"))
    return CrmEvidenciaAutorizacoesResponse(
        id_cnpj=id_cnpj,
        cnpj=farmacia["cnpj"],
        razao_social=farmacia["razao_social"],
        municipio=farmacia["municipio"],
        uf=farmacia["uf"],
        id_medico=id_medico,
        inicio=inicio,
        fim=fim,
        qtd_autorizacoes=tx.height,
        qtd_autorizacoes_crm=int(tx.get_column("do_crm").sum()) if tx.height else 0,
        qtd_crms=tx.get_column("id_medico").n_unique() if tx.height else 0,
        valor_total=float(tx.get_column("valor_pago").sum() or 0) if tx.height else 0.0,
        autorizacoes=[CrmEvidenciaAutorizacaoSchema(**r) for r in tx.iter_rows(named=True)],
    )
