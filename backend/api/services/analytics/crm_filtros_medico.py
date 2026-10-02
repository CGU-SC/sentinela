"""Filtros de medico da tela /analises (grupos "Cadastro CFM", "Producao" e
"Atuacao nas farmacias").

Cada combinacao de filtros vira o conjunto de medicos (codigos id_medico_num do
indice de bitmaps) que passam nela. crm_analysis_filtrado cruza esse conjunto
com o universo das farmacias do recorte para montar mapa, ranking e visao
mensal.

Regras (sempre no periodo da pagina):

* situacao no CFM: localizado = id_medico presente no cadastro de medicos;
* UF do CRM: UF do proprio id_medico ("123/SP"), valida tambem para os nao
  localizados (para os localizados ela coincide com sg_uf do cadastro);
* prescreveu antes da 1a inscricao: algum mes com prescricao no periodo
  anterior ao mes da 1a inscricao no CFM (mesma regra do modal do historico,
  crm_medico_historico.pontos_de_atencao). Medicos sem data de inscricao nao
  podem ser avaliados e nao entram;
* taxa diaria e total de prescricoes (faixas mín/máx, inclusivas): valem
  para o numero exibido em cada linha. No mapa, no Resumo e na Linha do tempo,
  a linha e o medico: numeros do periodo no RECORTE da pagina (Brasil, UF,
  regiao ou municipio), os das colunas TAXA / DIA e PRODUCAO do ranking; por
  isso o conjunto depende do recorte. Na aba Por mes, a linha e o medico x
  mes: a faixa filtra os meses (crm_analysis_mensal), e so os demais filtros
  escolhem os medicos (FiltrosMedico.sem_faixas). A taxa e comparada
  arredondada a 2 casas, como e exibida (expressao_faixas);
* exclusividade na farmacia principal (faixa mín/máx em %, inclusiva):
  prescricoes do medico na farmacia onde ele mais prescreveu / total dele no
  Brasil, no periodo -- a coluna Exclusividade da aba CRMs do estabelecimento,
  na farmacia principal. Nacional (todas as farmacias do medico), independe do
  recorte e dos filtros de farmacia; escolhe medicos em todas as abas;
* no de farmacias onde atuou (faixa mín/máx, inclusiva): farmacias distintas
  com prescricao do medico no periodo, no Brasil. Mesma regra e mesmo calculo
  da exclusividade (_atuacao_por_medico) -- o KPI "farmacias" do modal do
  historico;
* no de municipios onde atuou (faixa mín/máx, inclusiva): municipios distintos
  (id_ibge7 da farmacia) com prescricao do medico no periodo, no Brasil. Mesma
  regra dos demais filtros de atuacao, calculo proprio (_municipios_por_medico)
  -- o KPI "municipios" do modal do historico;
* autorizacoes em sequencia: dias com sequencia do medico no periodo, todas as
  farmacias, so os de severidade >= a minima escolhida (1 alta, 2 grave, 3
  critica, 4 extrema). Faixa de dias inclusiva; medico sem nenhum dia de
  sequencia tem 0 dias (ausencia na tabela = nenhuma sequencia). Severidade
  sem faixa de dias = pelo menos 1 dia. O tipo escolhe a origem dos dias:
    - unico (padrao): sequencias do proprio CRM
      (crm_concentracao_unico_alertas_global) -- mesma regra do ponto de
      atencao "rajadas_unico" do modal do historico;
    - multiplo: janelas de varios CRMs na farmacia em que o medico tem pelo
      menos SEQUENCIA_MULTIPLO_MIN_AUTORIZACOES autorizacoes
      (crm_concentracao_multiplo_medico_global, a ponte medico x janela
      derivada do Raio-X). A participacao minima existe porque a janela e um
      evento da farmacia: a mediana e 1 autorizacao do medico por janela, e
      sem o minimo o filtro alcancaria ~40% dos medicos;
    - qualquer: dias distintos de um tipo ou de outro.
"""

from dataclasses import dataclass, replace
from datetime import date
from typing import Optional

import numpy as np
import polars as pl
from fastapi import HTTPException
from pyroaring import BitMap

from data_cache import (
    conferir_crm_concentracao_multiplo_medico_global,
    get_dados_medico_df,
    get_df_perfil_estabelecimento,
    scan_crm_concentracao_multiplo_medico_global,
    scan_crm_concentracao_unico_alertas_global,
    scan_crm_farmacia_medico_ano,
    scan_crm_medico_dim,
    scan_crm_medico_estabelecimento_mes,
)

from .alertas_alvos import SEVERIDADES_SEQUENCIA
from .cache_geracao import CacheGeracao

SITUACOES_CFM = frozenset({"localizado", "nao_localizado"})
UFS_CRM = frozenset({
    "AC", "AL", "AM", "AP", "BA", "CE", "DF", "ES", "GO", "MA", "MG", "MS", "MT", "PA",
    "PB", "PE", "PI", "PR", "RJ", "RN", "RO", "RR", "RS", "SC", "SE", "SP", "TO",
})
TIPOS_SEQUENCIA = frozenset({"unico", "multiplo", "qualquer"})
TIPO_SEQUENCIA_PADRAO = "unico"
# Janela de multiplos CRMs so conta para o medico com pelo menos N autorizacoes nela.
# Com 3 o filtro alcancava ~107 mil medicos (qualquer severidade, >= 1 dia); com 5,
# ~45 mil (-58%), perto do filtro de unico CRM (~59 mil). Tirar a severidade "alta"
# cortaria so 29%: o ruido vem do medico de passagem na janela, nao da severidade.
# O modulo guarda o numero por janela, entao mudar este valor nao exige sincronizar.
SEQUENCIA_MULTIPLO_MIN_AUTORIZACOES = 5
_ID_MEDICO_RE = r"^\d+/[A-Z]{2}$"
# Chave unica medico x farmacia (medico * 2^31 + id_cnpj; id_cnpj e Int32 >= 0):
# agrupar por uma coluna Int64 foi ~40% mais rapido que por duas (benchmark).
_FATOR_CHAVE_FARMACIA = 2 ** 31

# Bases por periodo (dim, atuacao, municipios, sequencia...: segundos para
# calcular) e combinacoes de filtro (baratas, muitas) em caches separados, para
# que as combinacoes nao expulsem as bases.
_CACHE_BASES = CacheGeracao(max_itens=16)
_CACHE_MEDICOS = CacheGeracao(max_itens=32)


@dataclass(frozen=True)
class FiltrosMedico:
    """Filtros de medico normalizados (None/vazio/False = filtro desligado)."""
    situacao_cfm: Optional[str] = None
    ufs_crm: tuple[str, ...] = ()
    taxa_dia_min: Optional[float] = None
    taxa_dia_max: Optional[float] = None
    prescricoes_min: Optional[int] = None
    prescricoes_max: Optional[int] = None
    exclusividade_min: Optional[float] = None
    exclusividade_max: Optional[float] = None
    farmacias_min: Optional[int] = None
    farmacias_max: Optional[int] = None
    municipios_min: Optional[int] = None
    municipios_max: Optional[int] = None
    sequencia_severidade_min: Optional[int] = None
    sequencia_dias_min: Optional[int] = None
    sequencia_dias_max: Optional[int] = None
    # Origem dos dias de sequencia; so vale com severidade ou faixa de dias.
    sequencia_tipo: str = TIPO_SEQUENCIA_PADRAO

    @property
    def usa_sequencia(self) -> bool:
        return any(
            v is not None
            for v in (self.sequencia_severidade_min, self.sequencia_dias_min, self.sequencia_dias_max)
        )

    @property
    def usa_municipios(self) -> bool:
        return self.municipios_min is not None or self.municipios_max is not None

    @property
    def usa_atuacao(self) -> bool:
        """Filtros de atuacao nas farmacias (exclusividade e no de farmacias)."""
        return any(
            v is not None
            for v in (self.exclusividade_min, self.exclusividade_max, self.farmacias_min, self.farmacias_max)
        )

    def expressao_atuacao(self) -> Optional[pl.Expr]:
        """Condicao dos filtros de atuacao sobre _atuacao_por_medico (None sem filtro)."""
        if not self.usa_atuacao:
            return None
        exclusividade = pl.col("exclusividade").round(2)  # como a coluna Exclusividade exibe
        condicoes = []
        if self.exclusividade_min is not None:
            condicoes.append(exclusividade >= self.exclusividade_min)
        if self.exclusividade_max is not None:
            condicoes.append(exclusividade <= self.exclusividade_max)
        if self.farmacias_min is not None:
            condicoes.append(pl.col("qtd_farmacias") >= self.farmacias_min)
        if self.farmacias_max is not None:
            condicoes.append(pl.col("qtd_farmacias") <= self.farmacias_max)
        return pl.all_horizontal(condicoes)

    @property
    def usa_recorte(self) -> bool:
        """Filtros de faixa: dependem dos numeros do medico no recorte da pagina."""
        return any(v is not None for v in (self.taxa_dia_min, self.taxa_dia_max, self.prescricoes_min, self.prescricoes_max))

    @property
    def ativo(self) -> bool:
        return (
            self.situacao_cfm is not None or bool(self.ufs_crm)
            or self.usa_recorte or self.usa_atuacao or self.usa_municipios or self.usa_sequencia
        )

    @property
    def chave(self) -> tuple[object, ...]:
        return (
            self.situacao_cfm, self.ufs_crm,
            self.taxa_dia_min, self.taxa_dia_max, self.prescricoes_min, self.prescricoes_max,
            self.exclusividade_min, self.exclusividade_max, self.farmacias_min, self.farmacias_max,
            self.municipios_min, self.municipios_max,
            self.sequencia_severidade_min, self.sequencia_dias_min, self.sequencia_dias_max,
            self.sequencia_tipo,
        )

    def sem_faixas(self) -> "FiltrosMedico":
        """Os mesmos filtros sem as faixas de producao (so os que escolhem medicos).

        Os filtros de atuacao ficam: sao do medico no periodo, nao de cada mes.
        """
        return replace(self, taxa_dia_min=None, taxa_dia_max=None, prescricoes_min=None, prescricoes_max=None)

    def expressao_faixas(self, *, taxa: pl.Expr, prescricoes: pl.Expr) -> Optional[pl.Expr]:
        """Condicao das faixas sobre as colunas de uma linha (None sem faixa).

        Regra unica das faixas para medico (periodo) e medico x mes.

        Args:
            taxa: taxa diaria da linha (prescricoes / dias com prescricao).
            prescricoes: total de prescricoes da linha.
        """
        if not self.usa_recorte:
            return None
        taxa_exibida = taxa.round(2)  # compara com o valor exibido na tela
        condicoes = []
        if self.taxa_dia_min is not None:
            condicoes.append(taxa_exibida >= self.taxa_dia_min)
        if self.taxa_dia_max is not None:
            condicoes.append(taxa_exibida <= self.taxa_dia_max)
        if self.prescricoes_min is not None:
            condicoes.append(prescricoes >= self.prescricoes_min)
        if self.prescricoes_max is not None:
            condicoes.append(prescricoes <= self.prescricoes_max)
        return pl.all_horizontal(condicoes)


Recorte = tuple[Optional[str], Optional[int], Optional[int]]  # (uf, regiao_id, id_ibge7)


def chave_medicos(filtros: "FiltrosMedico", recorte: Recorte) -> tuple[object, ...]:
    """Chave de cache do conjunto de medicos (o recorte so entra com filtro de faixa)."""
    return (filtros.chave, recorte if filtros.usa_recorte else None)


SEM_FILTRO_MEDICO = FiltrosMedico()


def montar_filtros_medico(
    *,
    situacao_cfm: Optional[str],
    uf_crm: Optional[list[str]],
    taxa_dia_min: Optional[float] = None,
    taxa_dia_max: Optional[float] = None,
    prescricoes_min: Optional[int] = None,
    prescricoes_max: Optional[int] = None,
    exclusividade_min: Optional[float] = None,
    exclusividade_max: Optional[float] = None,
    farmacias_min: Optional[int] = None,
    farmacias_max: Optional[int] = None,
    municipios_min: Optional[int] = None,
    municipios_max: Optional[int] = None,
    sequencia_severidade_min: Optional[int] = None,
    sequencia_dias_min: Optional[int] = None,
    sequencia_dias_max: Optional[int] = None,
    sequencia_tipo: Optional[str] = None,
) -> FiltrosMedico:
    """Valida e normaliza os filtros de medico recebidos pela API.

    Args:
        situacao_cfm: "localizado", "nao_localizado" ou None (todos).
        uf_crm: siglas das UFs do CRM (vazio/None = todas).
        taxa_dia_min / taxa_dia_max: faixa da taxa diaria no recorte (inclusiva).
        prescricoes_min / prescricoes_max: faixa do total de prescricoes no recorte.
        exclusividade_min / exclusividade_max: faixa (0 a 100%) da exclusividade
            na farmacia principal.
        farmacias_min / farmacias_max: faixa do no de farmacias onde atuou.
        municipios_min / municipios_max: faixa do no de municipios onde atuou.
        sequencia_severidade_min: severidade minima (1..4) dos dias de
            sequencia que contam.
        sequencia_dias_min / sequencia_dias_max: faixa de dias com sequencia.
        sequencia_tipo: "unico" (padrao), "multiplo" ou "qualquer"; so tem
            efeito com severidade ou faixa de dias (sem elas vira o padrao).

    Returns:
        FiltrosMedico com UFs ordenadas e sem repeticao.

    Raises:
        HTTPException 422: situacao, UF ou tipo de sequencia invalido ou faixa
            invalida (negativa, exclusividade acima de 100% ou minimo maior que maximo).
    """
    if situacao_cfm is not None and situacao_cfm not in SITUACOES_CFM:
        raise HTTPException(status_code=422, detail="situacao_cfm deve ser localizado ou nao_localizado.")
    ufs = tuple(sorted({str(uf).strip().upper() for uf in (uf_crm or [])}))
    invalidas = [uf for uf in ufs if uf not in UFS_CRM]
    if invalidas:
        raise HTTPException(status_code=422, detail=f"UF do CRM invalida: {', '.join(invalidas)}.")
    for nome, minimo, maximo in (
        ("taxa_dia", taxa_dia_min, taxa_dia_max),
        ("prescricoes", prescricoes_min, prescricoes_max),
        ("farmacias", farmacias_min, farmacias_max),
        ("municipios", municipios_min, municipios_max),
        ("dias com sequencia", sequencia_dias_min, sequencia_dias_max),
    ):
        if (minimo is not None and minimo < 0) or (maximo is not None and maximo < 0):
            raise HTTPException(status_code=422, detail=f"Faixa de {nome} nao pode ser negativa.")
        if minimo is not None and maximo is not None and minimo > maximo:
            raise HTTPException(status_code=422, detail=f"Faixa de {nome}: minimo maior que maximo.")
    if sequencia_severidade_min is not None and sequencia_severidade_min not in SEVERIDADES_SEQUENCIA:
        raise HTTPException(status_code=422, detail="sequencia_severidade_min deve ser 1 (alta), 2 (grave), 3 (critica) ou 4 (extrema).")
    if sequencia_tipo is not None and sequencia_tipo not in TIPOS_SEQUENCIA:
        raise HTTPException(status_code=422, detail="sequencia_tipo deve ser unico, multiplo ou qualquer.")
    usa_sequencia = any(v is not None for v in (sequencia_severidade_min, sequencia_dias_min, sequencia_dias_max))
    if any(v is not None and not 0 <= v <= 100 for v in (exclusividade_min, exclusividade_max)):
        raise HTTPException(status_code=422, detail="Faixa de exclusividade deve estar entre 0 e 100%.")
    if exclusividade_min is not None and exclusividade_max is not None and exclusividade_min > exclusividade_max:
        raise HTTPException(status_code=422, detail="Faixa de exclusividade: minimo maior que maximo.")
    return FiltrosMedico(
        situacao_cfm=situacao_cfm,
        ufs_crm=ufs,
        taxa_dia_min=taxa_dia_min,
        taxa_dia_max=taxa_dia_max,
        prescricoes_min=prescricoes_min,
        prescricoes_max=prescricoes_max,
        exclusividade_min=exclusividade_min,
        exclusividade_max=exclusividade_max,
        farmacias_min=farmacias_min,
        farmacias_max=farmacias_max,
        municipios_min=municipios_min,
        municipios_max=municipios_max,
        sequencia_severidade_min=sequencia_severidade_min,
        sequencia_dias_min=sequencia_dias_min,
        sequencia_dias_max=sequencia_dias_max,
        # Sem filtro de sequencia o tipo nao escolhe nada: fica o padrao (mesma chave de cache).
        sequencia_tipo=(sequencia_tipo or TIPO_SEQUENCIA_PADRAO) if usa_sequencia else TIPO_SEQUENCIA_PADRAO,
    )


def _competencia(value: date) -> int:
    return value.year * 100 + value.month


def _dim() -> pl.DataFrame:
    """id_medico_num / id_medico de todos os medicos com prescricao (codigos do indice)."""
    def calcular() -> pl.DataFrame:
        dim = scan_crm_medico_dim().select([
            pl.col("id_medico_num").cast(pl.Int32),
            pl.col("id_medico").cast(pl.Utf8),
        ]).collect()
        invalidos = dim.filter(~pl.col("id_medico").str.contains(_ID_MEDICO_RE))
        if invalidos.height:
            amostra = ", ".join(invalidos.get_column("id_medico").head(5).to_list())
            raise HTTPException(status_code=503, detail=f"id_medico fora do formato numero/UF no indice CRM: {amostra}.")
        return dim.with_columns(pl.col("id_medico").str.slice(-2).alias("uf_crm"))
    return _CACHE_BASES.obter(("dim",), calcular)


def _cadastro() -> pl.DataFrame:
    """id_medico e data da 1a inscricao dos medicos localizados no CFM."""
    try:
        medicos = get_dados_medico_df()
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Cache de dados dos medicos indisponivel: {exc}") from exc
    faltando = {"id_medico", "dt_primeira_inscricao_uf"} - set(medicos.columns)
    if faltando:
        raise HTTPException(status_code=503, detail=f"Dados dos medicos sem colunas: {', '.join(sorted(faltando))}.")
    return medicos.select([pl.col("id_medico").cast(pl.Utf8), pl.col("dt_primeira_inscricao_uf")])


def _ids_por_faixa(filtros: FiltrosMedico, inicio: date, fim: date, recorte: Recorte) -> pl.DataFrame:
    """id_medico cujos numeros no recorte (colunas do ranking) estao nas faixas."""
    from . import crm_analysis as base  # import tardio: crm_analysis importa este modulo

    uf, regiao_id, id_ibge7 = recorte
    agregado = base.ranking_agregado_escopo(inicio=inicio, fim=fim, uf=uf, regiao_id=regiao_id, id_ibge7=id_ibge7)
    faltando = {"id_medico", "taxa_prescricoes_dia", "nu_prescricoes"} - set(agregado.columns)
    if faltando:
        raise HTTPException(status_code=503, detail=f"Ranking agregado sem colunas: {', '.join(sorted(faltando))}.")
    condicao = filtros.expressao_faixas(taxa=pl.col("taxa_prescricoes_dia"), prescricoes=pl.col("nu_prescricoes"))
    if condicao is None:
        raise ValueError("_ids_por_faixa chamado sem faixa de producao.")
    return agregado.filter(condicao).select(pl.col("id_medico").cast(pl.Utf8))


def _atuacao_por_medico(inicio: date, fim: date) -> pl.DataFrame:
    """Exclusividade (%) na farmacia principal e no de farmacias de cada medico no periodo.

    Estrategia escolhida por benchmark (mesmo resultado das alternativas):
    tabela anual medico x farmacia (crm_farmacia_medico_ano) nos anos inteiros
    + tabela mensal so nos meses das pontas, agrupando por uma chave Int64 unica
    medico x farmacia em streaming. 0,8 s (6 meses) a 4,4 s (historico inteiro)
    na primeira vez; depois vem do cache por periodo. O no de farmacias sai do
    mesmo agrupamento, sem custo extra.

    Returns:
        id_medico_num (Int32), exclusividade (Float64, 0 a 100) e
        qtd_farmacias (UInt32, farmacias distintas com prescricao).
    """
    from . import crm_analysis as base  # import tardio: crm_analysis importa este modulo

    def calcular() -> pl.DataFrame:
        anos, meses = base._dividir_periodo_ranking(inicio, fim)
        chave = pl.col("id_medico_num").cast(pl.Int64) * _FATOR_CHAVE_FARMACIA + pl.col("id_cnpj").cast(pl.Int64)
        partes = []
        try:
            if anos:
                partes.append(
                    scan_crm_farmacia_medico_ano()
                    .filter(pl.col("ano").cast(pl.Int32).is_in(anos))
                    .select(chave.alias("chave"), pl.col("nu_prescricoes").cast(pl.Int64).alias("nu"))
                )
            if meses:
                partes.append(
                    scan_crm_medico_estabelecimento_mes()
                    .filter(pl.col("competencia").cast(pl.Int32).is_in(meses))
                    .select(
                        pl.col("id_medico").cast(pl.Utf8),
                        pl.col("id_cnpj"),
                        pl.col("nu_prescricoes_mes").cast(pl.Int64).alias("nu"),
                    )
                    .join(_dim().lazy().select(["id_medico", "id_medico_num"]), on="id_medico", how="inner")
                    .select(chave.alias("chave"), "nu")
                )
            if not partes:
                raise HTTPException(status_code=422, detail="Periodo sem meses com prescricoes nos modulos CRM.")
            resultado = (
                pl.concat(partes)
                .group_by("chave").agg(pl.col("nu").sum())
                .group_by((pl.col("chave") // _FATOR_CHAVE_FARMACIA).cast(pl.Int32).alias("id_medico_num"))
                .agg([
                    pl.col("nu").max().alias("principal"),
                    pl.col("nu").sum().alias("total"),
                    pl.len().alias("qtd_farmacias"),
                ])
                .collect(engine="streaming")
            )
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(status_code=503, detail=f"Modulos CRM medico x farmacia indisponiveis: {exc}") from exc
        if resultado.filter(pl.col("total") <= 0).height:
            raise HTTPException(status_code=503, detail="Medico com total de prescricoes nao positivo no modulo medico x farmacia.")
        return resultado.select(
            "id_medico_num",
            (pl.col("principal").cast(pl.Float64) / pl.col("total").cast(pl.Float64) * 100).alias("exclusividade"),
            "qtd_farmacias",
        )

    return _CACHE_BASES.obter(("atuacao", inicio, fim), calcular)


def _municipios_por_medico(inicio: date, fim: date) -> pl.DataFrame:
    """No de municipios distintos (id_ibge7 da farmacia) de cada medico no periodo.

    Calculo proprio, escolhido por benchmark (mesmo resultado de junta-lo ao
    _atuacao_por_medico, porem 30-60% mais rapido e sem pesar nos demais
    filtros): pares medico x farmacia da tabela anual nos anos inteiros + da
    mensal nas pontas, ligados ao municipio pelo perfil das farmacias. 0,6 s
    (6 meses) a 4,7 s (historico inteiro) na primeira vez; depois, cache.

    Returns:
        id_medico_num (Int32) e qtd_municipios (UInt32).

    Raises:
        HTTPException 503: farmacia dos modulos CRM sem municipio no perfil.
    """
    from . import crm_analysis as base  # import tardio: crm_analysis importa este modulo

    def calcular() -> pl.DataFrame:
        anos, meses = base._dividir_periodo_ranking(inicio, fim)
        try:
            perfil = get_df_perfil_estabelecimento()
        except Exception as exc:
            raise HTTPException(status_code=503, detail=f"Perfil de estabelecimentos indisponivel: {exc}") from exc
        faltando = {"id_cnpj", "id_ibge7"} - set(perfil.columns)
        if faltando:
            raise HTTPException(status_code=503, detail=f"Perfil de estabelecimentos sem colunas: {', '.join(sorted(faltando))}.")
        municipio = perfil.select([pl.col("id_cnpj").cast(pl.Int64), pl.col("id_ibge7").cast(pl.Int64)])
        if municipio.get_column("id_ibge7").null_count():
            raise HTTPException(status_code=503, detail="Perfil de estabelecimentos com farmacia sem id_ibge7.")
        partes = []
        try:
            if anos:
                partes.append(
                    scan_crm_farmacia_medico_ano()
                    .filter(pl.col("ano").cast(pl.Int32).is_in(anos))
                    .select(pl.col("id_medico_num").cast(pl.Int32), pl.col("id_cnpj").cast(pl.Int64))
                )
            if meses:
                partes.append(
                    scan_crm_medico_estabelecimento_mes()
                    .filter(pl.col("competencia").cast(pl.Int32).is_in(meses))
                    .select(pl.col("id_medico").cast(pl.Utf8), pl.col("id_cnpj").cast(pl.Int64))
                    .join(_dim().lazy().select(["id_medico", "id_medico_num"]), on="id_medico", how="inner")
                    .select("id_medico_num", "id_cnpj")
                )
            if not partes:
                raise HTTPException(status_code=422, detail="Periodo sem meses com prescricoes nos modulos CRM.")
            pares = pl.concat(partes)
            sem_municipio = (
                pares.select("id_cnpj").unique()
                .join(municipio.lazy(), on="id_cnpj", how="anti")
                .collect(engine="streaming")
            )
            if sem_municipio.height:
                raise HTTPException(
                    status_code=503,
                    detail=(
                        "Farmacias dos modulos CRM sem municipio no perfil de estabelecimentos (id_cnpj: "
                        + ", ".join(str(v) for v in sem_municipio.get_column("id_cnpj").head(5).to_list())
                        + "). Sincronize o perfil e os modulos CRM da mesma execucao."
                    ),
                )
            return (
                pares.join(municipio.lazy(), on="id_cnpj", how="inner")
                .group_by("id_medico_num")
                .agg(pl.col("id_ibge7").n_unique().alias("qtd_municipios"))
                .collect(engine="streaming")
            )
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(status_code=503, detail=f"Modulos CRM medico x farmacia indisponiveis: {exc}") from exc

    return _CACHE_BASES.obter(("municipios", inicio, fim), calcular)


def farmacias_por_medico(inicio: date, fim: date) -> pl.DataFrame:
    """No de farmacias e de municipios onde cada medico atuou no periodo (Brasil).

    Os mesmos numeros dos filtros "No de farmacias" e "No de municipios" (e do
    mesmo cache por periodo), para a coluna "Farmacias" do ranking.

    Returns:
        id_medico (Utf8), qtd_farmacias (Int64) e qtd_municipios (Int64).
    """
    def calcular() -> pl.DataFrame:
        farmacias = _atuacao_por_medico(inicio, fim).select(["id_medico_num", "qtd_farmacias"])
        municipios = _municipios_por_medico(inicio, fim)
        juntos = farmacias.join(municipios, on="id_medico_num", how="full", coalesce=True)
        if juntos.filter(pl.col("qtd_farmacias").is_null() | pl.col("qtd_municipios").is_null()).height:
            raise HTTPException(
                status_code=503,
                detail="Contagens de farmacias e de municipios por medico divergentes (modulos CRM de execucoes diferentes).",
            )
        return (
            juntos.join(_dim().select(["id_medico_num", "id_medico"]), on="id_medico_num", how="inner")
            .select([
                "id_medico",
                pl.col("qtd_farmacias").cast(pl.Int64),
                pl.col("qtd_municipios").cast(pl.Int64),
            ])
        )

    return _CACHE_BASES.obter(("farmacias_por_medico", inicio, fim), calcular)


def farmacias_dos_medicos(id_medicos: list[str], inicio: date, fim: date) -> pl.DataFrame:
    """No de farmacias e de municipios so dos medicos pedidos (uma pagina do ranking).

    Mesma regra de farmacias_por_medico (tabela anual nos anos inteiros + mensal
    nas pontas, Brasil), mas lendo so esses medicos: ~0,08 s sem cache, contra
    2 a 9 s do calculo de todos os medicos, que so a ordenacao pela coluna exige.

    Returns:
        id_medico (Utf8), qtd_farmacias (Int64) e qtd_municipios (Int64).
    """
    from . import crm_analysis as base  # import tardio: crm_analysis importa este modulo

    if not id_medicos:
        return pl.DataFrame(schema={"id_medico": pl.Utf8, "qtd_farmacias": pl.Int64, "qtd_municipios": pl.Int64})
    dim = _dim().filter(pl.col("id_medico").is_in(id_medicos)).select(["id_medico_num", "id_medico"])
    anos, meses = base._dividir_periodo_ranking(inicio, fim)
    try:
        perfil = get_df_perfil_estabelecimento()
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Perfil de estabelecimentos indisponivel: {exc}") from exc
    municipio = perfil.select([pl.col("id_cnpj").cast(pl.Int64), pl.col("id_ibge7").cast(pl.Int64)])
    partes = []
    try:
        if anos:
            partes.append(
                scan_crm_farmacia_medico_ano()
                .filter(pl.col("id_medico_num").is_in(dim.get_column("id_medico_num").implode()) & pl.col("ano").is_in(anos))
                .select(pl.col("id_medico_num").cast(pl.Int32), pl.col("id_cnpj").cast(pl.Int64))
            )
        if meses:
            partes.append(
                scan_crm_medico_estabelecimento_mes()
                .filter(pl.col("id_medico").is_in(id_medicos) & pl.col("competencia").is_in(meses))
                .select(pl.col("id_medico").cast(pl.Utf8), pl.col("id_cnpj").cast(pl.Int64))
                .join(dim.lazy(), on="id_medico", how="inner")
                .select("id_medico_num", "id_cnpj")
            )
        if not partes:
            raise HTTPException(status_code=422, detail="Periodo sem meses com prescricoes nos modulos CRM.")
        pares = pl.concat(partes).unique().collect()
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Modulos CRM medico x farmacia indisponiveis: {exc}") from exc
    com_municipio = pares.join(municipio, on="id_cnpj", how="left")
    if com_municipio.get_column("id_ibge7").null_count():
        raise HTTPException(status_code=503, detail="Farmacia dos modulos CRM sem municipio no perfil de estabelecimentos.")
    return (
        com_municipio.group_by("id_medico_num")
        .agg([
            pl.col("id_cnpj").n_unique().cast(pl.Int64).alias("qtd_farmacias"),
            pl.col("id_ibge7").n_unique().cast(pl.Int64).alias("qtd_municipios"),
        ])
        .join(dim, on="id_medico_num", how="inner")
        .select(["id_medico", "qtd_farmacias", "qtd_municipios"])
    )


def _conferir_severidades_sequencia(linhas: pl.DataFrame) -> None:
    desconhecidas = set(linhas.get_column("id_severidade").unique().to_list()) - SEVERIDADES_SEQUENCIA
    if desconhecidas:
        raise HTTPException(status_code=503, detail=f"Severidade de sequencia desconhecida nos alertas: {sorted(desconhecidas)}.")


def _dias_sequencia_unico(inicio: date, fim: date, severidade_min: int) -> pl.DataFrame:
    """Medico x dia com sequencia do proprio CRM (id_medico, dt), severidade >= minima."""
    try:
        alertas = (
            scan_crm_concentracao_unico_alertas_global()
            .filter(pl.col("competencia").cast(pl.Int32).is_between(_competencia(inicio), _competencia(fim)))
            .select(
                pl.col("id_medico").cast(pl.Utf8),
                pl.col("dt_alerta").cast(pl.Utf8).str.slice(0, 10).alias("dt"),
                pl.col("id_severidade").cast(pl.Int32),
            )
            .collect()
        )
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Alertas de sequencia (unico CRM) indisponiveis: {exc}") from exc
    _conferir_severidades_sequencia(alertas)
    return alertas.filter(pl.col("id_severidade") >= severidade_min).select(["id_medico", "dt"]).unique()


def _dias_sequencia_multiplo(inicio: date, fim: date, severidade_min: int) -> pl.DataFrame:
    """Medico x dia em janela de multiplos CRMs (id_medico, dt), severidade >= minima.

    So as janelas em que o medico tem pelo menos
    SEQUENCIA_MULTIPLO_MIN_AUTORIZACOES autorizacoes. Competencia e no de
    autorizacoes sao comparados sem cast, para o Polars usar as estatisticas
    do arquivo (15 mi de linhas).
    """
    try:
        # Ponte montada com outro Raio-X/alertas: 503 em vez de numeros antigos.
        conferir_crm_concentracao_multiplo_medico_global()
        janelas = (
            scan_crm_concentracao_multiplo_medico_global()
            .filter(
                pl.col("competencia").is_between(_competencia(inicio), _competencia(fim))
                & (pl.col("nu_autorizacoes_crm") >= SEQUENCIA_MULTIPLO_MIN_AUTORIZACOES)
            )
            .select(
                pl.col("id_medico").cast(pl.Utf8),
                pl.col("dt_alerta").cast(pl.Utf8).alias("dt"),
                pl.col("id_severidade").cast(pl.Int32),
            )
            .collect()
        )
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Sequencias de multiplos CRMs por medico indisponiveis: {exc}",
        ) from exc
    _conferir_severidades_sequencia(janelas)
    return janelas.filter(pl.col("id_severidade") >= severidade_min).select(["id_medico", "dt"]).unique()


def _sequencia_por_medico(
    inicio: date, fim: date, severidade_min: int, tipo: str = TIPO_SEQUENCIA_PADRAO,
) -> pl.DataFrame:
    """Dias com sequencia de severidade >= severidade_min, por medico, no periodo.

    Args:
        inicio: inicio do periodo da pagina.
        fim: fim do periodo da pagina.
        severidade_min: severidade minima (1..4) dos dias que contam.
        tipo: "unico" (sequencias do proprio CRM; mesma contagem do ponto de
            atencao "rajadas_unico" do modal), "multiplo" (janelas de varios
            CRMs com participacao minima do medico) ou "qualquer" (dias
            distintos de um ou de outro).

    Returns:
        id_medico (Utf8) e dias (UInt32), so os medicos com pelo menos 1 dia.
    """
    if tipo not in TIPOS_SEQUENCIA:
        raise ValueError(f"Tipo de sequencia invalido: {tipo}")

    def calcular() -> pl.DataFrame:
        partes = []
        if tipo in ("unico", "qualquer"):
            partes.append(_dias_sequencia_unico(inicio, fim, severidade_min))
        if tipo in ("multiplo", "qualquer"):
            partes.append(_dias_sequencia_multiplo(inicio, fim, severidade_min))
        return (
            pl.concat(partes)
            .group_by("id_medico")
            .agg(pl.col("dt").n_unique().alias("dias"))
        )

    return _CACHE_BASES.obter(("sequencia", tipo, inicio, fim, severidade_min), calcular)


def medicos_filtrados(filtros: FiltrosMedico, inicio: date, fim: date, recorte: Recorte) -> BitMap:
    """Codigos (id_medico_num) dos medicos que passam nos filtros, no periodo.

    Args:
        filtros: filtros ativos (use apenas com filtros.ativo).
        inicio: inicio do periodo da pagina.
        fim: fim do periodo da pagina.
        recorte: (uf, regiao_id, id_ibge7) da pagina; usado pelos filtros de faixa.

    Returns:
        BitMap com os codigos do indice de bitmaps CRM.
    """
    if not filtros.ativo:
        raise ValueError("medicos_filtrados chamado sem filtro de medico ativo.")

    def calcular() -> BitMap:
        dim = _dim()
        if filtros.ufs_crm:
            dim = dim.filter(pl.col("uf_crm").is_in(list(filtros.ufs_crm)))
        if filtros.situacao_cfm is not None:
            cadastro = _cadastro()
            if filtros.situacao_cfm == "nao_localizado":
                dim = dim.join(cadastro.select("id_medico"), on="id_medico", how="anti")
            else:
                dim = dim.join(cadastro.select("id_medico"), on="id_medico", how="semi")
        if filtros.usa_recorte:
            dim = dim.join(_ids_por_faixa(filtros, inicio, fim, recorte), on="id_medico", how="semi")
        if filtros.usa_atuacao:
            selecionados = _atuacao_por_medico(inicio, fim).filter(filtros.expressao_atuacao())
            dim = dim.join(selecionados.select("id_medico_num"), on="id_medico_num", how="semi")
        if filtros.usa_municipios:
            condicoes = []
            if filtros.municipios_min is not None:
                condicoes.append(pl.col("qtd_municipios") >= filtros.municipios_min)
            if filtros.municipios_max is not None:
                condicoes.append(pl.col("qtd_municipios") <= filtros.municipios_max)
            selecionados = _municipios_por_medico(inicio, fim).filter(pl.all_horizontal(condicoes))
            dim = dim.join(selecionados.select("id_medico_num"), on="id_medico_num", how="semi")
        if filtros.usa_sequencia:
            severidade = filtros.sequencia_severidade_min or min(SEVERIDADES_SEQUENCIA)
            # Severidade sem faixa de dias = pelo menos 1 dia de sequencia nesse nivel.
            dias_min = filtros.sequencia_dias_min
            if dias_min is None and filtros.sequencia_dias_max is None:
                dias_min = 1
            # Medico fora da tabela de alertas tem 0 dias de sequencia (nao e dado ausente).
            dias = (
                dim.select("id_medico")
                .join(_sequencia_por_medico(inicio, fim, severidade, filtros.sequencia_tipo), on="id_medico", how="left")
                .with_columns(pl.col("dias").fill_null(0))
            )
            condicoes = []
            if dias_min is not None:
                condicoes.append(pl.col("dias") >= dias_min)
            if filtros.sequencia_dias_max is not None:
                condicoes.append(pl.col("dias") <= filtros.sequencia_dias_max)
            dim = dim.join(dias.filter(pl.all_horizontal(condicoes)).select("id_medico"), on="id_medico", how="semi")
        codigos = dim.get_column("id_medico_num").to_numpy().astype(np.uint32)
        return BitMap(codigos)

    # O periodo so importa para as faixas, a atuacao nas farmacias e as sequencias.
    periodo = (
        (inicio, fim)
        if filtros.usa_recorte or filtros.usa_atuacao or filtros.usa_municipios
        or filtros.usa_sequencia
        else None
    )
    return _CACHE_MEDICOS.obter(("medicos", chave_medicos(filtros, recorte), periodo), calcular)

