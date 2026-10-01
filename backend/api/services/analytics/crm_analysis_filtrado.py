"""Mapa e ranking de medicos (tela /analises) com filtros de farmacia e de medico.

Com qualquer filtro alem de periodo e localizacao, o universo passa a ser o das
farmacias filtradas -- exatamente as mesmas de /estabelecimentos. Regra "no
periodo":

* entra o medico que prescreveu em pelo menos uma farmacia filtrada do
  territorio, em qualquer mes do periodo;
* mapa: ativos = esses medicos; alta intensidade = os que, alem disso, tiveram
  pelo menos um mes de alta intensidade no territorio no periodo (mesma
  marcacao do mapa sem filtro: taxa do mes acima do P95 nacional do mes, com
  todas as prescricoes do medico no territorio);
* ranking: os indicadores do medico sao os do escopo inteiro (mesmos numeros
  do ranking sem filtro); a coluna extra traz as prescricoes nas farmacias
  filtradas do escopo e a fatia delas no total do medico.

Filtros de medico (crm_filtros_medico) restringem esse universo: entram so os
medicos que tambem passam neles. Sem filtro de farmacia, o universo de
farmacias e o de todas as farmacias (mesmos numeros do mapa sem filtro).

Os conjuntos de medicos vem do indice de bitmaps (crm_indice_bitmaps), montado
na sincronizacao a partir dos modulos CRM.
"""

from datetime import date
from collections.abc import Mapping
from typing import Callable, Optional

import polars as pl
from fastapi import HTTPException
from pyroaring import BitMap

from crm_indice_bitmaps import IndiceBitmaps, IndiceDesatualizado, chave_territorio, obter_indice
from data_cache import (
    get_df_perfil_estabelecimento,
    get_localidades_df,
    scan_crm_farmacia_medico_ano,
    scan_crm_medico_dim,
    scan_crm_medico_estabelecimento_mes,
)
from . import crm_analysis as base
from .cache_geracao import CacheGeracao
from .crm_filtros_medico import FiltrosMedico, Recorte, chave_medicos, medicos_filtrados
from .indicadores import get_indicador_scope_base_cached
from .filtros_farmacia import CAMPOS_FILTROS_FARMACIA

# Filtros que definem as farmacias (os de localizacao ficam de fora: o recorte
# geografico e feito pelo territorio do mapa/ranking).
# Os mesmos campos do objeto de filtros (chave de cache e "filtro de farmacia ativo?").
FILTROS_FARMACIA = CAMPOS_FILTROS_FARMACIA

_COLUNA_TERRITORIO = {
    "uf": "uf",
    "regiao_saude": "id_regiao_saude",
    "municipio": "id_municipio",
}

_CACHE = CacheGeracao(max_itens=32)


def _chave_filtros(filtros: Mapping[str, object]) -> tuple[object, ...]:
    return tuple((nome, filtros.get(nome)) for nome in FILTROS_FARMACIA)


def _recorte(uf: Optional[str], regiao_id: Optional[int], id_ibge7: Optional[int]) -> Recorte:
    """Recorte da pagina normalizado (UF "Todos" = sem UF)."""
    return (uf if uf and uf != "Todos" else None, regiao_id, id_ibge7)


def filtro_farmacia_ativo(filtros: Mapping[str, object]) -> bool:
    """True quando algum filtro de farmacia (normalizado) esta ligado."""
    return any(filtros.get(nome) is not None and filtros.get(nome) is not False for nome in FILTROS_FARMACIA)


def _indice() -> IndiceBitmaps:
    try:
        return obter_indice()
    except IndiceDesatualizado as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


# ── Farmacias e medicos delas ────────────────────────────────────────────────
def _farmacias(filtros: Mapping[str, object], inicio: date, fim: date) -> pl.DataFrame:
    """
    id_cnpj e territorio das farmacias do universo.

    Com filtro de farmacia: as filtradas (mesma base de /estabelecimentos).
    So com filtro de medico: todas as farmacias do cadastro, o mesmo universo da
    analise sem filtros. A base de /estabelecimentos corta farmacias sem venda ou
    sem movimento no periodo, e ligar um filtro de medico nao pode mudar a base.
    """
    def calcular() -> pl.DataFrame:
        if filtro_farmacia_ativo(filtros):
            scope = get_indicador_scope_base_cached(data_inicio=inicio, data_fim=fim, **filtros)
            origem = "Base de farmacias filtradas"
        else:
            scope = get_df_perfil_estabelecimento()
            origem = "Perfil dos estabelecimentos"
        base._require_columns(scope, {"id_cnpj", "uf", "id_regiao_saude", "id_ibge7"}, origem)
        farmacias = scope.select([
            pl.col("id_cnpj").cast(pl.Int32),
            pl.col("uf").cast(pl.Utf8),
            pl.col("id_regiao_saude").cast(pl.Utf8),
            pl.col("id_ibge7").cast(pl.Int64).cast(pl.Utf8).alias("id_municipio"),
        ]).unique("id_cnpj")
        if farmacias.select(pl.any_horizontal(pl.all().is_null()).any()).item():
            raise HTTPException(status_code=503, detail="Farmacias filtradas sem UF, regiao ou municipio.")
        return farmacias
    return _CACHE.obter(("farmacias", _chave_filtros(filtros), inicio, fim), calcular)


def _cnpjs(farmacias: pl.DataFrame, nivel: str, territorio: Optional[str]) -> list[int]:
    if nivel == "brasil":
        return farmacias.get_column("id_cnpj").to_list()
    return farmacias.filter(pl.col(_COLUNA_TERRITORIO[nivel]) == territorio).get_column("id_cnpj").to_list()


def _medicos_por_territorio(
    filtros, medicos: FiltrosMedico, recorte: Recorte, nivel: str, inicio: date, fim: date,
) -> dict[str, BitMap]:
    """Por territorio do nivel: medicos das farmacias filtradas dele que passam nos filtros de medico."""
    por_territorio = _medicos_farmacias_por_territorio(filtros, nivel, inicio, fim)
    if not medicos.ativo:
        return por_territorio

    def calcular() -> dict[str, BitMap]:
        selecionados = medicos_filtrados(medicos, inicio, fim, recorte)
        return {territorio: bitmap & selecionados for territorio, bitmap in por_territorio.items()}

    return _CACHE.obter(("medicos_filtrados", nivel, _chave_filtros(filtros), chave_medicos(medicos, recorte), inicio, fim), calcular)


def _medicos_farmacias_por_territorio(filtros, nivel: str, inicio: date, fim: date) -> dict[str, BitMap]:
    """Por territorio do nivel: medicos com prescricao nas farmacias filtradas dele."""
    def calcular() -> dict[str, BitMap]:
        indice = _indice()
        anos, meses = base._dividir_periodo_ranking(inicio, fim)
        grupos = (
            _farmacias(filtros, inicio, fim)
            .group_by(_COLUNA_TERRITORIO[nivel])
            .agg(pl.col("id_cnpj"))
        )
        return {
            territorio: indice.uniao_farmacias(cnpjs, anos, meses)
            for territorio, cnpjs in grupos.iter_rows()
        }
    return _CACHE.obter(("medicos", nivel, _chave_filtros(filtros), inicio, fim), calcular)


def _medicos_escopo(
    filtros, medicos: FiltrosMedico, recorte: Recorte, nivel: str, territorio: Optional[str], inicio: date, fim: date,
) -> BitMap:
    """Medicos do universo filtrado no escopo (nivel de base.escopo_territorial)."""
    if nivel == "brasil":
        por_uf = _medicos_por_territorio(filtros, medicos, recorte, "uf", inicio, fim)
        return _CACHE.obter(
            ("medicos_brasil", _chave_filtros(filtros), chave_medicos(medicos, recorte), inicio, fim),
            lambda: BitMap().union(*por_uf.values()),
        )
    if territorio is None:
        raise ValueError(f"Escopo {nivel} sem territorio.")
    return _medicos_por_territorio(filtros, medicos, recorte, nivel, inicio, fim).get(territorio, BitMap())


def _contagens(filtros, medicos: FiltrosMedico, recorte: Recorte, nivel: str, inicio: date, fim: date) -> pl.DataFrame:
    """Por territorio (uf ou municipio): medicos ativos e de alta intensidade."""
    def calcular() -> pl.DataFrame:
        indice = _indice()
        anos, meses = base._dividir_periodo_ranking(inicio, fim)
        linhas = [
            (
                territorio,
                len(medicos_territorio),
                medicos_territorio.intersection_cardinality(indice.alta(chave_territorio(nivel, territorio), anos, meses)),
            )
            for territorio, medicos_territorio in _medicos_por_territorio(filtros, medicos, recorte, nivel, inicio, fim).items()
            if medicos_territorio
        ]
        return pl.DataFrame(
            linhas,
            schema={
                "id_geografico": pl.Utf8,
                "qtd_medicos_ativos": pl.Int64,
                "qtd_medicos_alta_intensidade": pl.Int64,
            },
            orient="row",
        )
    return _CACHE.obter(("contagens", nivel, _chave_filtros(filtros), chave_medicos(medicos, recorte), inicio, fim), calcular)


# ── Mapa ──────────────────────────────────────────────────────────────────────
def mapa_filtrado(
    *,
    filtros: Mapping[str, object],
    medicos: FiltrosMedico,
    map_level: str,
    inicio: date,
    fim: date,
    uf: Optional[str],
    regiao_id: Optional[int],
    id_ibge7: Optional[int],
):
    """Mesmo contrato de base._build_manager_map, com o universo filtrado (farmacias e medicos)."""
    recorte = _recorte(uf, regiao_id, id_ibge7)
    if map_level == "uf":
        contagens = _contagens(filtros, medicos, recorte, "uf", inicio, fim).rename({"id_geografico": "uf"})
        ufs = (
            get_localidades_df().select(pl.col("sg_uf").cast(pl.Utf8).alias("uf")).unique()
            .join(contagens, on="uf", how="left")
            .with_columns([
                pl.col("qtd_medicos_ativos").fill_null(0),
                pl.col("qtd_medicos_alta_intensidade").fill_null(0),
            ])
        )
        percentual_brasil = base._percentual_somado(ufs)
        if uf and uf != "Todos":
            ufs = ufs.filter(pl.col("uf") == uf)
        summary = (
            ufs.with_columns(base._percentual_expr().alias("percentual_alta_intensidade"))
            .sort("percentual_alta_intensidade", descending=True, nulls_last=True)
        )
        referencia = {"percentual_referencia_brasil": percentual_brasil}
        # Mapa por UF: escopo e a UF selecionada ou o Brasil.
        qtd = len(_medicos_escopo(filtros, medicos, recorte, *base.escopo_territorial(uf, None, None), inicio, fim))
        return base._map_items_from_summary(summary, "uf", percentual_brasil=percentual_brasil), qtd, referencia

    localidades = get_localidades_df()
    base._require_columns(localidades, base.CRM_ANALYSIS_REQUIRED_LOCALIDADES_COLUMNS, "Localidades")
    geo = localidades.select([
        pl.col("id_ibge7").cast(pl.Int64),
        pl.col("sg_uf").cast(pl.Utf8).alias("uf"),
        pl.col("id_regiao_saude").cast(pl.Utf8),
        pl.col("no_regiao_saude").cast(pl.Utf8),
        pl.col("no_municipio").cast(pl.Utf8),
    ]).unique("id_ibge7")
    contagens = (
        _contagens(filtros, medicos, recorte, "municipio", inicio, fim)
        .with_columns(pl.col("id_geografico").cast(pl.Int64).alias("id_ibge7"))
        .drop("id_geografico")
    )
    municipios_geo = contagens.join(geo.select(["id_ibge7", "uf", "id_regiao_saude"]), on="id_ibge7", how="left")
    if municipios_geo.filter(pl.col("uf").is_null()).height:
        raise HTTPException(status_code=503, detail="Municipios das farmacias filtradas ausentes no cache de localidades.")

    percentual_brasil = base._percentual_somado(municipios_geo) if municipios_geo.height else None
    uf_referencia = uf if uf and uf != "Todos" else None
    percentual_uf = (
        base._percentual_somado(municipios_geo.filter(pl.col("uf") == uf_referencia))
        if uf_referencia is not None else None
    )
    referencia_regioes = (
        municipios_geo.group_by("id_regiao_saude").agg([
            pl.sum("qtd_medicos_ativos").alias("qtd_medicos_ativos"),
            pl.sum("qtd_medicos_alta_intensidade").alias("qtd_medicos_alta_intensidade"),
        ])
        .with_columns(base._percentual_expr().alias("percentual_referencia_regiao"))
        .select(["id_regiao_saude", "percentual_referencia_regiao"])
    )

    geo_scope = geo
    if uf_referencia is not None:
        geo_scope = geo_scope.filter(pl.col("uf") == uf_referencia)
    if regiao_id is not None:
        geo_scope = geo_scope.filter(pl.col("id_regiao_saude") == str(regiao_id))
    if id_ibge7 is not None:
        geo_scope = geo_scope.filter(pl.col("id_ibge7") == id_ibge7)

    nivel_escopo, territorio_escopo = base.escopo_territorial(uf, regiao_id, id_ibge7)
    if nivel_escopo == "brasil":
        raise HTTPException(status_code=422, detail="O mapa geografico exige UF, regiao de saude ou municipio.")
    qtd = len(_medicos_escopo(filtros, medicos, recorte, nivel_escopo, territorio_escopo, inicio, fim))

    summary = (
        geo_scope
        .join(contagens, on="id_ibge7", how="left")
        .join(referencia_regioes, on="id_regiao_saude", how="left")
        .with_columns([
            pl.col("qtd_medicos_ativos").fill_null(0).cast(pl.Int64),
            pl.col("qtd_medicos_alta_intensidade").fill_null(0).cast(pl.Int64),
        ])
        .with_columns(base._percentual_expr().alias("percentual_alta_intensidade"))
        .sort("percentual_alta_intensidade", descending=True, nulls_last=True)
    )
    referencia = {
        "percentual_referencia_brasil": percentual_brasil,
        "percentual_referencia_uf": percentual_uf,
    }
    if regiao_id is not None:
        linha = referencia_regioes.filter(pl.col("id_regiao_saude") == str(regiao_id))
        referencia["percentual_referencia_regiao"] = linha.item(0, "percentual_referencia_regiao") if linha.height == 1 else None
    items = base._map_items_from_summary(
        summary, map_level, percentual_brasil=percentual_brasil, percentual_uf=percentual_uf,
    )
    return items, qtd, referencia


# ── Ranking ───────────────────────────────────────────────────────────────────
def _prescricoes_nas_farmacias(
    id_medicos: list[str],
    cnpjs: list[int],
    inicio: date,
    fim: date,
) -> pl.DataFrame:
    """Soma das prescricoes dos medicos solicitados nas farmacias do escopo."""
    anos, meses = base._dividir_periodo_ranking(inicio, fim)
    dim = (
        scan_crm_medico_dim()
        .filter(pl.col("id_medico").cast(pl.Utf8).is_in(id_medicos))
        .select([pl.col("id_medico").cast(pl.Utf8), pl.col("id_medico_num").cast(pl.Int32)])
        .collect()
    )
    cnpjs_serie = pl.Series("id_cnpj", cnpjs, dtype=pl.Int32)
    partes = []
    if anos:
        partes.append(
            scan_crm_farmacia_medico_ano()
            .filter(
                pl.col("ano").cast(pl.Int32).is_in(anos)
                & pl.col("id_medico_num").cast(pl.Int32).is_in(dim.get_column("id_medico_num"))
                & pl.col("id_cnpj").cast(pl.Int32).is_in(cnpjs_serie)
            )
            .select([pl.col("id_medico_num").cast(pl.Int32), pl.col("nu_prescricoes").cast(pl.Int64)])
            .collect()
            .join(dim, on="id_medico_num", how="inner")
            .select(["id_medico", "nu_prescricoes"])
        )
    if meses:
        partes.append(
            scan_crm_medico_estabelecimento_mes()
            .filter(
                pl.col("competencia").cast(pl.Int32).is_in(meses)
                & pl.col("id_medico").cast(pl.Utf8).is_in(id_medicos)
                & pl.col("id_cnpj").cast(pl.Int32).is_in(cnpjs_serie)
            )
            .select([
                pl.col("id_medico").cast(pl.Utf8),
                pl.col("nu_prescricoes_mes").cast(pl.Int64).alias("nu_prescricoes"),
            ])
            .collect()
        )
    return (
        pl.concat(partes)
        .group_by("id_medico")
        .agg(pl.col("nu_prescricoes").sum().alias("nu_prescricoes_farmacias_filtradas"))
    )


def ranking_filtrado(
    *,
    filtros: Mapping[str, object],
    medicos: FiltrosMedico,
    inicio: date,
    fim: date,
    uf: Optional[str],
    regiao_id: Optional[int],
    id_ibge7: Optional[int],
) -> tuple[
    pl.DataFrame,
    Optional[Callable[[list[str]], pl.DataFrame]],
    Optional[Callable[[], pl.DataFrame]],
]:
    """Ranking do escopo restrito ao universo filtrado (farmacias e medicos).

    Devolve o agregado e, so com filtro de farmacia, a soma dos medicos da
    pagina e a soma completa sob demanda (colunas "Farmacias filtradas").
    """
    nivel, territorio = base.escopo_territorial(uf, regiao_id, id_ibge7)
    recorte = _recorte(uf, regiao_id, id_ibge7)

    def calcular() -> pl.DataFrame:
        selecionados = _medicos_escopo(filtros, medicos, recorte, nivel, territorio, inicio, fim)
        ids = _indice().ids_medico(selecionados)
        completo = base.ranking_agregado_escopo(
            inicio=inicio, fim=fim, uf=uf, regiao_id=regiao_id, id_ibge7=id_ibge7,
        )
        agregado = completo.filter(pl.col("id_medico").is_in(ids))
        if agregado.height != len(selecionados):
            raise HTTPException(
                status_code=503,
                detail=(
                    f"{len(selecionados) - agregado.height} medicos do universo filtrado fora do ranking do escopo. "
                    "Sincronize os modulos CRM e o indice de bitmaps da mesma execucao."
                ),
            )
        return agregado

    agregado = _CACHE.obter(("ranking", nivel, territorio, _chave_filtros(filtros), chave_medicos(medicos, recorte), inicio, fim), calcular)
    if not filtro_farmacia_ativo(filtros):
        # So filtro de medico: sem colunas de farmacias filtradas.
        return agregado, None, None
    cnpjs = _cnpjs(_farmacias(filtros, inicio, fim), nivel, territorio)
    def prescricoes_pagina(id_medicos: list[str]) -> pl.DataFrame:
        return _prescricoes_nas_farmacias(id_medicos, cnpjs, inicio, fim)

    def prescricoes_completas() -> pl.DataFrame:
        return _CACHE.obter(
            ("ranking_prescricoes_completas", nivel, territorio, _chave_filtros(filtros), chave_medicos(medicos, recorte), inicio, fim),
            lambda: _prescricoes_nas_farmacias(
                agregado.get_column("id_medico").to_list(), cnpjs, inicio, fim,
            ),
        )

    return agregado, prescricoes_pagina, prescricoes_completas


def ids_medicos_filtrados(
    *,
    filtros: Mapping[str, object],
    medicos: FiltrosMedico,
    inicio: date,
    fim: date,
    uf: Optional[str],
    regiao_id: Optional[int],
    id_ibge7: Optional[int],
) -> pl.Series:
    """id_medico dos medicos do universo filtrado (farmacias e medicos) no escopo, no periodo."""
    nivel, territorio = base.escopo_territorial(uf, regiao_id, id_ibge7)
    recorte = _recorte(uf, regiao_id, id_ibge7)

    def calcular() -> pl.Series:
        selecionados = _medicos_escopo(filtros, medicos, recorte, nivel, territorio, inicio, fim)
        return _indice().ids_medico(selecionados).cast(pl.Utf8).alias("id_medico")

    return _CACHE.obter(("ids_medicos", nivel, territorio, _chave_filtros(filtros), chave_medicos(medicos, recorte), inicio, fim), calcular)
