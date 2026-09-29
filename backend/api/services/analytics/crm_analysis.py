"""Dados agregados para a análise geográfica de prescrições por médico."""

import threading
from collections import OrderedDict
from datetime import date, timedelta
from typing import Callable, Literal, Optional, cast

import polars as pl
from fastapi import HTTPException

from data_cache import (
    get_localidades_df,
    get_cache_generation,
    scan_crm_mapa_uf_periodo,
    scan_crm_mapa_municipio_regiao_periodo,
    scan_crm_limiar_p95_mes,
    scan_crm_medico_brasil_ano,
    scan_crm_medico_brasil_mes,
    scan_crm_medico_territorio_ano,
    scan_crm_medico_territorio_mes,
    get_dados_medico_df,
)
from ...schemas.analytics import (
    CrmPrescricoesAnaliseResponse,
    CrmPrescricoesMapaItemSchema,
    CrmPrescricoesRankingItemSchema,
)
MIN_DATA = date(2015, 7, 1)
MAX_DATA = date(2024, 12, 31)
# Abaixo deste numero de medicos ativos no periodo, o municipio aparece como
# "amostra pequena" no mapa (sem cor de risco): o percentual oscila demais.
CRM_MAPA_MIN_MEDICOS_ATIVOS_MUNICIPIO = 20
MapLevel = Literal["uf", "municipio", "regiao"]
CRM_ANALYSIS_REQUIRED_LIMIAR_COLUMNS = {
    "competencia",
    "qtd_medicos_ativos",
    "p95_taxa_dia",
}
CRM_ANALYSIS_REQUIRED_MANAGER_COLUMNS = {
    "nivel",
    "id_geografico",
    "competencia_inicio",
    "competencia_fim",
    "qtd_medicos_ativos",
    "qtd_medicos_alta_intensidade",
}
CRM_ANALYSIS_REQUIRED_NATIONAL_MAP_COLUMNS = {
    "nivel",
    "id_geografico",
    "competencia_inicio",
    "competencia_fim",
    "qtd_medicos_ativos",
    "qtd_medicos_alta_intensidade",
}
CRM_ANALYSIS_REQUIRED_LOCALIDADES_COLUMNS = {
    "id_ibge7",
    "sg_uf",
    "id_regiao_saude",
    "no_regiao_saude",
    "no_municipio",
}
CRM_ANALYSIS_REQUIRED_MEDICO_TERRITORIO_COLUMNS = {
    "nivel",
    "id_geografico",
    "id_medico",
    "competencia",
    "nu_prescricoes_mes",
    "qtd_dias_com_prescricao_mes",
}
CRM_ANALYSIS_REQUIRED_MEDICO_MES_COLUMNS = {
    "id_medico",
    "competencia",
    "nu_prescricoes_mes",
    "qtd_dias_com_prescricao_mes",
}
CRM_ANALYSIS_REQUIRED_MEDICO_ANO_COLUMNS = {
    "id_medico",
    "ano",
    "nu_prescricoes",
    "qtd_dias_com_prescricao",
    "qtd_meses_ativos",
    "qtd_meses_alta_intensidade",
}
CRM_ANALYSIS_REQUIRED_MEDICO_COLUMNS = {
    "id_medico",
    "nu_crm",
    "sg_uf",
    "no_medico",
}
# Ranking agregado (1 linha por medico) por periodo/escopo. Os modulos so mudam
# na sincronizacao, e a chave inclui get_cache_generation(): nao ha prazo de
# validade. O limite de itens controla a memoria (o ranking do Brasil no periodo
# inteiro ocupa dezenas de MB) e descarta o item usado ha mais tempo (LRU).
_CRM_RANKING_CACHE_MAX_ITEMS = 8
_CRM_RANKING_CACHE_LOCK = threading.Lock()
_CRM_RANKING_CACHE: "OrderedDict[tuple[object, ...], pl.DataFrame]" = OrderedDict()


def _ranking_cache_key(
    *,
    geographic: bool,
    inicio: date,
    fim: date,
    uf: Optional[str] = None,
    regiao_id: Optional[int] = None,
    id_ibge7: Optional[int] = None,
) -> tuple[object, ...]:
    return (
        get_cache_generation(),
        "geografico" if geographic else "brasil",
        inicio,
        fim,
        uf,
        regiao_id,
        id_ibge7,
    )


def _descartar_geracoes_antigas(generation: object) -> None:
    """Remove rankings de uma geracao de cache anterior (chamar com o lock)."""
    for cache_key in [key for key in _CRM_RANKING_CACHE if key[0] != generation]:
        del _CRM_RANKING_CACHE[cache_key]


def _get_cached_ranking(key: tuple[object, ...]) -> pl.DataFrame | None:
    with _CRM_RANKING_CACHE_LOCK:
        _descartar_geracoes_antigas(key[0])
        cached = _CRM_RANKING_CACHE.get(key)
        if cached is not None:
            # Consulta renova a posicao: sai primeiro quem esta parado ha mais tempo.
            _CRM_RANKING_CACHE.move_to_end(key)
        return cached


def _cache_ranking(key: tuple[object, ...], value: pl.DataFrame) -> None:
    with _CRM_RANKING_CACHE_LOCK:
        _descartar_geracoes_antigas(key[0])
        _CRM_RANKING_CACHE[key] = value
        _CRM_RANKING_CACHE.move_to_end(key)
        while len(_CRM_RANKING_CACHE) > _CRM_RANKING_CACHE_MAX_ITEMS:
            _CRM_RANKING_CACHE.popitem(last=False)


def _require_columns(df: pl.DataFrame, required: set[str], source: str) -> None:
    missing = sorted(required.difference(df.columns))
    if missing:
        raise HTTPException(
            status_code=503,
            detail=f"{source} sem colunas obrigatorias: {', '.join(missing)}.",
        )


def _period_bounds(data_inicio: Optional[date], data_fim: Optional[date]) -> tuple[date, date]:
    inicio = data_inicio if data_inicio and data_inicio >= MIN_DATA else MIN_DATA
    fim = data_fim or MAX_DATA
    if inicio > fim:
        raise HTTPException(status_code=422, detail="Período inválido: data_inicio posterior à data_fim.")
    proximo_mes = (
        date(fim.year + 1, 1, 1)
        if fim.month == 12
        else date(fim.year, fim.month + 1, 1)
    )
    ultimo_dia_mes = proximo_mes - timedelta(days=1)
    if inicio.day != 1 or fim != ultimo_dia_mes:
        raise HTTPException(
            status_code=422,
            detail="A análise de prescrições CRM exige meses completos.",
        )
    return inicio, fim


def _competencia(value: date) -> int:
    return value.year * 100 + value.month


def _filtro_ativo(value: object, *, neutral: set[object] | None = None) -> bool:
    if value is None:
        return False
    if isinstance(value, str) and not value.strip():
        return False
    return value not in (neutral or set())


def _pode_usar_cache_gerencial(
    *,
    perc_min: Optional[float],
    perc_max: Optional[float],
    val_min: Optional[float],
    situacao_rf: Optional[str],
    conexao_ms: Optional[str],
    porte_empresa: Optional[str],
    grande_rede: Optional[str],
    cnpj_raiz: Optional[str],
    unidade_pf: Optional[str],
    razao_social: Optional[str],
    estabelecimento: Optional[str],
    par_teia: Optional[str],
    socio_beneficio: Optional[str],
    socio_esocial: Optional[str],
    cnae_incompativel: bool,
    socio_idade_atipica: bool,
    socio_falecido: bool,
    volume_atipico: bool,
    dispersao_uf_sem_fronteira: bool,
) -> bool:
    """Indica se o agregado gerencial preserva a semantica dos filtros recebidos."""
    return not any([
        perc_min is not None and float(perc_min) != 0,
        perc_max is not None and float(perc_max) != 100,
        val_min is not None and float(val_min) > 0,
        _filtro_ativo(situacao_rf, neutral={"Todos"}),
        _filtro_ativo(conexao_ms, neutral={"Todos"}),
        _filtro_ativo(porte_empresa, neutral={"Todos"}),
        _filtro_ativo(grande_rede, neutral={"Todos"}),
        _filtro_ativo(cnpj_raiz),
        _filtro_ativo(unidade_pf, neutral={"Todos"}),
        _filtro_ativo(razao_social),
        _filtro_ativo(estabelecimento),
        _filtro_ativo(par_teia),
        _filtro_ativo(socio_beneficio),
        _filtro_ativo(socio_esocial),
        cnae_incompativel,
        socio_idade_atipica,
        socio_falecido,
        volume_atipico,
        dispersao_uf_sem_fronteira,
    ])


def _percentual_expr() -> pl.Expr:
    return (
        pl.when(pl.col("qtd_medicos_ativos") > 0)
        .then(pl.col("qtd_medicos_alta_intensidade") / pl.col("qtd_medicos_ativos") * 100)
        .otherwise(None)
    )


def _indice(percentual: Optional[float], referencia: Optional[float]) -> Optional[float]:
    """Multiplo da concentracao de referencia (ex.: 2,0 = o dobro da media)."""
    if percentual is None or referencia is None:
        return None
    if referencia <= 0:
        # Referencia somada zerada: nenhum territorio dela tem medico de alta
        # intensidade, entao o territorio comparado tambem tem 0%.
        return 0.0 if percentual == 0 else None
    return percentual / referencia


def _percentual_somado(rows: pl.DataFrame) -> Optional[float]:
    """Referencia na mesma unidade dos territorios comparados.

    Um medico conta como ativo em cada territorio onde teve prescricao, entao a
    soma dos ativos dos territorios e maior que o total de medicos distintos
    (a linha agregada conta cada medico uma vez). Comparar o territorio com a
    linha agregada deixaria todos abaixo da referencia; por isso a referencia
    e soma do alta / soma dos ativos dos proprios territorios.
    """
    ativos = int(rows.get_column("qtd_medicos_ativos").sum())
    if ativos <= 0:
        return None
    return int(rows.get_column("qtd_medicos_alta_intensidade").sum()) / ativos * 100


def _map_items_from_summary(
    summary: pl.DataFrame,
    map_level: str,
    *,
    percentual_brasil: Optional[float],
    percentual_uf: Optional[float] = None,
) -> list[CrmPrescricoesMapaItemSchema]:
    """Converte o resumo de medicos (ativos e de alta intensidade) no contrato do mapa."""
    items = []
    for row in summary.iter_rows(named=True):
        percentual = row["percentual_alta_intensidade"]
        percentual = float(percentual) if percentual is not None else None
        ativos = int(row["qtd_medicos_ativos"])
        comuns = dict(
            qtd_medicos_ativos=ativos,
            qtd_medicos_alta_intensidade=int(row["qtd_medicos_alta_intensidade"]),
            percentual_alta_intensidade=percentual,
            indice_brasil=_indice(percentual, percentual_brasil),
        )
        if map_level == "uf":
            uf = str(row["uf"])
            items.append(CrmPrescricoesMapaItemSchema(
                nivel="uf", identificador=uf, nome=uf, uf=uf,
                amostra_pequena=False,
                **comuns,
            ))
        else:
            percentual_regiao = row["percentual_referencia_regiao"]
            percentual_regiao = float(percentual_regiao) if percentual_regiao is not None else None
            items.append(CrmPrescricoesMapaItemSchema(
                nivel="municipio",
                identificador=str(row["id_ibge7"]),
                nome=str(row["no_municipio"]),
                uf=str(row["uf"]),
                id_ibge7=int(row["id_ibge7"]),
                id_regiao_saude=str(row["id_regiao_saude"]),
                no_regiao_saude=row["no_regiao_saude"],
                indice_uf=_indice(percentual, percentual_uf),
                indice_regiao=_indice(percentual, percentual_regiao),
                percentual_referencia_regiao=percentual_regiao,
                amostra_pequena=ativos < CRM_MAPA_MIN_MEDICOS_ATIVOS_MUNICIPIO,
                **comuns,
            ))
    return items


def _read_uf_brasil_period(inicio: date, fim: date) -> tuple[pl.DataFrame, pl.DataFrame]:
    """Linhas das 27 UFs e do Brasil para o intervalo exato, validadas."""
    national = scan_crm_mapa_uf_periodo()
    national_columns = set(national.collect_schema().names())
    missing = sorted(CRM_ANALYSIS_REQUIRED_NATIONAL_MAP_COLUMNS.difference(national_columns))
    if missing:
        raise HTTPException(
            status_code=503,
            detail="Cache do mapa Brasil sem colunas obrigatorias: " + ", ".join(missing) + ".",
        )

    competencia_inicio = _competencia(inicio)
    competencia_fim = _competencia(fim)
    period_rows = national.filter(
        (pl.col("competencia_inicio") == competencia_inicio)
        & (pl.col("competencia_fim") == competencia_fim)
    ).select([
        pl.col("nivel").cast(pl.Utf8),
        pl.col("id_geografico").cast(pl.Utf8),
        pl.col("qtd_medicos_ativos").cast(pl.Int64),
        pl.col("qtd_medicos_alta_intensidade").cast(pl.Int64),
    ]).collect()
    if period_rows.height != 28:
        raise HTTPException(
            status_code=503,
            detail=f"Cache do mapa Brasil sem as 28 linhas exigidas para {competencia_inicio}-{competencia_fim}.",
        )
    if period_rows.filter(
        (pl.col("qtd_medicos_ativos") < 0)
        | (pl.col("qtd_medicos_alta_intensidade") < 0)
        | (pl.col("qtd_medicos_alta_intensidade") > pl.col("qtd_medicos_ativos"))
    ).height:
        raise HTTPException(status_code=503, detail="Cache do mapa Brasil possui contagens invalidas.")
    brasil = period_rows.filter(
        (pl.col("nivel") == "brasil") & (pl.col("id_geografico") == "BR")
    )
    ufs = period_rows.filter(pl.col("nivel") == "uf")
    if brasil.height != 1 or ufs.height != 27 or ufs.get_column("id_geografico").n_unique() != 27:
        raise HTTPException(status_code=503, detail="Cache do mapa Brasil possui territorios ausentes ou duplicados.")
    if ufs.filter(
        (pl.col("id_geografico") == "BR")
        | (pl.col("id_geografico").str.len_chars() != 2)
    ).height:
        raise HTTPException(status_code=503, detail="Cache do mapa Brasil possui identificador de UF invalido.")
    return ufs, brasil


def _percentual_da_linha(rows: pl.DataFrame) -> Optional[float]:
    valor = rows.with_columns(_percentual_expr().alias("p")).item(0, "p")
    return float(valor) if valor is not None else None


def _build_national_manager_map(
    *,
    inicio: date,
    fim: date,
    uf: Optional[str],
) -> tuple[list[CrmPrescricoesMapaItemSchema], int, dict]:
    """Mapa Brasil: le as contagens por UF ja materializadas para o intervalo exato.

    Referencia da cor: soma das 27 UFs (ver _percentual_somado), nao a linha BR.
    """
    ufs, brasil = _read_uf_brasil_period(inicio, fim)
    percentual_brasil = _percentual_somado(ufs)
    if uf and uf != "Todos":
        ufs = ufs.filter(pl.col("id_geografico") == uf)
        if ufs.is_empty():
            raise HTTPException(status_code=503, detail=f"Cache do mapa Brasil sem a UF {uf}.")

    summary = (
        ufs.rename({"id_geografico": "uf"})
        .with_columns(_percentual_expr().alias("percentual_alta_intensidade"))
        .sort("percentual_alta_intensidade", descending=True, nulls_last=True)
    )
    referencia = {"percentual_referencia_brasil": percentual_brasil}
    if uf and uf != "Todos":
        referencia["percentual_referencia_uf"] = _percentual_da_linha(summary)
    return (
        _map_items_from_summary(summary, "uf", percentual_brasil=percentual_brasil),
        int(summary.item(0, "qtd_medicos_ativos")) if uf and uf != "Todos"
        else int(brasil.item(0, "qtd_medicos_ativos")),
        referencia,
    )


def _build_manager_map(
    *,
    map_level: str,
    inicio: date,
    fim: date,
    uf: Optional[str],
    regiao_id: Optional[int],
    id_ibge7: Optional[int],
) -> tuple[list[CrmPrescricoesMapaItemSchema], int, dict]:
    """Le contagens distintas precomputadas para o intervalo exato do mapa."""
    if map_level == "uf":
        return _build_national_manager_map(inicio=inicio, fim=fim, uf=uf)

    manager_scan = scan_crm_mapa_municipio_regiao_periodo()
    manager_columns = set(manager_scan.collect_schema().names())
    missing = sorted(CRM_ANALYSIS_REQUIRED_MANAGER_COLUMNS.difference(manager_columns))
    if missing:
        raise HTTPException(
            status_code=503,
            detail="Cache do mapa por municipio/regiao sem colunas obrigatorias: " + ", ".join(missing) + ".",
        )

    manager = manager_scan.filter(
        (pl.col("competencia_inicio") == _competencia(inicio))
        & (pl.col("competencia_fim") == _competencia(fim))
    ).select([
        pl.col("nivel").cast(pl.Utf8),
        pl.col("id_geografico").cast(pl.Utf8),
        pl.col("qtd_medicos_ativos").cast(pl.Int64),
        pl.col("qtd_medicos_alta_intensidade").cast(pl.Int64),
    ]).collect()
    if manager.is_empty():
        raise HTTPException(status_code=503, detail="Cache de municipio/regiao sem o periodo solicitado.")
    if manager.filter(
        (pl.col("qtd_medicos_ativos") < 0)
        | (pl.col("qtd_medicos_alta_intensidade") < 0)
        | (pl.col("qtd_medicos_alta_intensidade") > pl.col("qtd_medicos_ativos"))
    ).height:
        raise HTTPException(status_code=503, detail="Cache de municipio/regiao possui contagens invalidas.")
    if manager.group_by(["nivel", "id_geografico"]).len().filter(pl.col("len") > 1).height:
        raise HTTPException(status_code=503, detail="Cache de municipio/regiao possui territorios duplicados.")

    localidades = get_localidades_df()
    _require_columns(localidades, CRM_ANALYSIS_REQUIRED_LOCALIDADES_COLUMNS, "Localidades")
    geo = (
        localidades
        .select(["id_ibge7", "sg_uf", "id_regiao_saude", "no_regiao_saude", "no_municipio"])
        .with_columns([
            pl.col("id_ibge7").cast(pl.Int64),
            pl.col("sg_uf").cast(pl.Utf8).alias("uf"),
            pl.col("id_regiao_saude").cast(pl.Utf8),
            pl.col("no_regiao_saude").cast(pl.Utf8),
            pl.col("no_municipio").cast(pl.Utf8),
        ])
        .select(["id_ibge7", "uf", "id_regiao_saude", "no_regiao_saude", "no_municipio"])
    )
    if geo.filter(pl.col("id_ibge7").is_null()).height:
        raise HTTPException(
            status_code=503,
            detail="Cache de localidades possui id_ibge7 nulo para a analise de CRMs.",
        )
    duplicate_geo = geo.group_by("id_ibge7").len().filter(pl.col("len") > 1)
    if duplicate_geo.height:
        raise HTTPException(
            status_code=503,
            detail="Cache de localidades possui mais de uma linha para o mesmo id_ibge7.",
        )
    geo_scope = geo
    if uf and uf != "Todos":
        geo_scope = geo_scope.filter(pl.col("uf") == uf)
    if regiao_id is not None:
        geo_scope = geo_scope.filter(pl.col("id_regiao_saude") == str(regiao_id))
    if id_ibge7 is not None:
        geo_scope = geo_scope.filter(pl.col("id_ibge7") == id_ibge7)

    if id_ibge7 is not None:
        scope_level = "municipio"
        scope_identifier = str(id_ibge7)
    elif regiao_id is not None:
        scope_level = "regiao_saude"
        scope_identifier = str(regiao_id)
    elif uf and uf != "Todos":
        scope_level = "uf"
        scope_identifier = uf
    else:
        raise HTTPException(
            status_code=422,
            detail="O mapa geografico exige UF, regiao de saude ou municipio.",
        )

    # Referencias da cor, na mesma unidade dos municipios (medico x municipio):
    # soma dos municipios do Brasil, da UF e de cada regiao de saude
    # (ver _percentual_somado).
    municipality_counts = (
        manager.filter(pl.col("nivel") == "municipio")
        .with_columns(pl.col("id_geografico").cast(pl.Int64).alias("id_ibge7"))
        .select(["id_ibge7", "qtd_medicos_ativos", "qtd_medicos_alta_intensidade"])
    )
    if municipality_counts.is_empty():
        raise HTTPException(status_code=503, detail="Cache de municipio/regiao sem municipios no periodo solicitado.")
    municipios_geo = municipality_counts.join(
        geo.select(["id_ibge7", "uf", "id_regiao_saude"]),
        on="id_ibge7",
        how="left",
    )
    if municipios_geo.filter(pl.col("uf").is_null()).height:
        raise HTTPException(
            status_code=503,
            detail="Cache de municipio/regiao possui municipios ausentes no cache de localidades.",
        )

    percentual_brasil = _percentual_somado(municipios_geo)
    uf_referencia = uf if uf and uf != "Todos" else None
    percentual_uf = (
        _percentual_somado(municipios_geo.filter(pl.col("uf") == uf_referencia))
        if uf_referencia is not None
        else None
    )
    referencia_regioes = (
        municipios_geo
        .group_by("id_regiao_saude")
        .agg([
            pl.sum("qtd_medicos_ativos").alias("qtd_medicos_ativos"),
            pl.sum("qtd_medicos_alta_intensidade").alias("qtd_medicos_alta_intensidade"),
        ])
        .with_columns(_percentual_expr().alias("percentual_referencia_regiao"))
        .select(["id_regiao_saude", "percentual_referencia_regiao"])
    )

    if scope_level == "uf":
        ufs, _ = _read_uf_brasil_period(inicio, fim)
        linha_uf = ufs.filter(pl.col("id_geografico") == uf)
        if linha_uf.height != 1:
            raise HTTPException(status_code=503, detail=f"Cache do mapa Brasil sem a UF {uf}.")
        qtd_medicos_escopo = int(linha_uf.item(0, "qtd_medicos_ativos"))
    else:
        scope_rows = manager.filter(
            (pl.col("nivel") == scope_level)
            & (pl.col("id_geografico") == scope_identifier)
        )
        if scope_rows.height != 1:
            raise HTTPException(status_code=503, detail=f"Cache sem o territorio {scope_level}/{scope_identifier} no periodo.")
        qtd_medicos_escopo = int(scope_rows.item(0, "qtd_medicos_ativos"))

    summary = (
        geo_scope.select(["id_ibge7", "uf", "id_regiao_saude", "no_regiao_saude", "no_municipio"])
        .unique("id_ibge7")
        .join(municipality_counts, on="id_ibge7", how="left")
        .join(referencia_regioes, on="id_regiao_saude", how="left")
        .with_columns([
            pl.col("qtd_medicos_ativos").fill_null(0).cast(pl.Int64),
            pl.col("qtd_medicos_alta_intensidade").fill_null(0).cast(pl.Int64),
        ])
        .with_columns(_percentual_expr().alias("percentual_alta_intensidade"))
        .sort("percentual_alta_intensidade", descending=True, nulls_last=True)
    )
    referencia = {
        "percentual_referencia_brasil": percentual_brasil,
        "percentual_referencia_uf": percentual_uf,
    }
    if regiao_id is not None:
        linha_regiao = referencia_regioes.filter(pl.col("id_regiao_saude") == str(regiao_id))
        referencia["percentual_referencia_regiao"] = (
            linha_regiao.item(0, "percentual_referencia_regiao") if linha_regiao.height == 1 else None
        )
    return (
        _map_items_from_summary(
            summary, map_level,
            percentual_brasil=percentual_brasil,
            percentual_uf=percentual_uf,
        ),
        qtd_medicos_escopo,
        referencia,
    )


def _scope_label(
    *,
    uf: Optional[str],
    regiao_id: Optional[int],
    id_ibge7: Optional[int],
) -> str:
    """Descreve o filtro geografico mais especifico aplicado a resposta."""
    if id_ibge7 is not None:
        localidades = get_localidades_df()
        _require_columns(localidades, CRM_ANALYSIS_REQUIRED_LOCALIDADES_COLUMNS, "Localidades")
        municipio = (
            localidades
            .filter(pl.col("id_ibge7").cast(pl.Int64) == id_ibge7)
            .select(pl.col("no_municipio").cast(pl.Utf8))
            .unique()
        )
        if municipio.height != 1:
            raise HTTPException(
                status_code=422,
                detail=f"Municipio IBGE {id_ibge7} nao encontrado de forma univoca.",
            )
        return f"Município {municipio.item(0, 'no_municipio')}"
    if regiao_id is not None:
        return f"Região de Saúde {regiao_id}"
    if uf and uf != "Todos":
        return f"UF {uf}"
    return "Brasil"


def _limiares_do_periodo(inicio: date, fim: date) -> pl.DataFrame:
    """P95 nacional de cada mes do periodo; falha se faltar algum mes."""
    try:
        limiar = scan_crm_limiar_p95_mes().collect()
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Cache de limiares do P95 indisponivel: {exc}",
        ) from exc
    _require_columns(limiar, CRM_ANALYSIS_REQUIRED_LIMIAR_COLUMNS, "Limiares do P95")
    competencia_inicio, competencia_fim = _competencia(inicio), _competencia(fim)
    periodo = limiar.filter(
        pl.col("competencia").is_between(competencia_inicio, competencia_fim)
    ).select([
        pl.col("competencia").cast(pl.Int32),
        pl.col("p95_taxa_dia").cast(pl.Float64),
    ])
    meses_esperados = (
        (competencia_fim // 100 - competencia_inicio // 100) * 12
        + (competencia_fim % 100 - competencia_inicio % 100)
        + 1
    )
    if (
        periodo.height != meses_esperados
        or periodo.get_column("competencia").n_unique() != meses_esperados
        or periodo.filter(pl.col("p95_taxa_dia").is_null() | (pl.col("p95_taxa_dia") < 1)).height
    ):
        raise HTTPException(
            status_code=503,
            detail=(
                "Cache de limiares do P95 incompleto para "
                f"{competencia_inicio}-{competencia_fim}."
            ),
        )
    return periodo


def _dividir_periodo_ranking(inicio: date, fim: date) -> tuple[list[int], list[int]]:
    """Anos inteiros (lidos da tabela anual) e meses soltos (da mensal).

    Um ano e inteiro quando todos os meses dele que existem nos dados (os meses
    com P95 em crm_limiar_p95_mes) estao dentro do periodo; ex.: 2015 comeca em
    julho, entao 07/2015 a 12/2015 ja e o ano inteiro.
    """
    competencia_inicio, competencia_fim = _competencia(inicio), _competencia(fim)
    meses_dados = sorted(
        scan_crm_limiar_p95_mes()
        .select(pl.col("competencia").cast(pl.Int32))
        .collect()
        .get_column("competencia")
        .to_list()
    )
    no_periodo = [m for m in meses_dados if competencia_inicio <= m <= competencia_fim]
    anos = [
        ano
        for ano in sorted({m // 100 for m in no_periodo})
        if all(competencia_inicio <= m <= competencia_fim for m in meses_dados if m // 100 == ano)
    ]
    soltos = [m for m in no_periodo if m // 100 not in anos]
    return anos, soltos


def _agregar_ranking(
    doctor_month: pl.LazyFrame,
    inicio: date,
    fim: date,
    doctor_year: pl.LazyFrame,
) -> pl.DataFrame:
    """Agrega o ranking com a mesma regra do mapa:

    * taxa = prescricoes / dias com prescricao no periodo (e no escopo);
    * mes de alta intensidade = taxa do mes acima do P95 nacional do mes, com
      qualquer quantidade de dias (taxa arredondada a 6 casas, como o
      DECIMAL(19,6) do SQL);
    * entram no ranking todos os medicos com prescricao no periodo.

    Anos inteiros do periodo vem da tabela anual (somas ja prontas, inclusive
    os meses de alta intensidade); meses soltos vem da mensal. Todas as colunas
    sao somas, entao o resultado e identico a somar so a mensal.
    """
    limiares = _limiares_do_periodo(inicio, fim)
    anos, meses_soltos = _dividir_periodo_ranking(inicio, fim)
    colunas = [
        pl.col("id_medico").cast(pl.Utf8),
        pl.col("nu_prescricoes").cast(pl.Int64),
        pl.col("qtd_dias_com_prescricao").cast(pl.Int64),
        pl.col("qtd_meses_ativos").cast(pl.Int64),
        pl.col("qtd_meses_alta_intensidade").cast(pl.Int64),
    ]
    partes = []
    if anos:
        partes.append(
            doctor_year
            .filter(pl.col("ano").cast(pl.Int32).is_in(anos))
            .select(colunas)
        )
    if meses_soltos:
        partes.append(
            doctor_month
            .select([
                pl.col("id_medico").cast(pl.Utf8),
                pl.col("competencia").cast(pl.Int32),
                pl.col("nu_prescricoes_mes").cast(pl.Int64),
                pl.col("qtd_dias_com_prescricao_mes").cast(pl.Int64),
            ])
            .filter(
                pl.col("competencia").is_in(meses_soltos)
                & (pl.col("nu_prescricoes_mes") > 0)
                & (pl.col("qtd_dias_com_prescricao_mes") > 0)
            )
            .join(limiares.lazy(), on="competencia", how="inner")
            .select([
                pl.col("id_medico"),
                pl.col("nu_prescricoes_mes").alias("nu_prescricoes"),
                pl.col("qtd_dias_com_prescricao_mes").alias("qtd_dias_com_prescricao"),
                pl.lit(1, dtype=pl.Int64).alias("qtd_meses_ativos"),
                (
                    (pl.col("nu_prescricoes_mes") / pl.col("qtd_dias_com_prescricao_mes")).round(6)
                    > pl.col("p95_taxa_dia")
                ).cast(pl.Int64).alias("qtd_meses_alta_intensidade"),
            ])
        )
    if not partes:
        raise HTTPException(status_code=422, detail="Periodo sem meses com dados para o ranking.")
    return (
        pl.concat(partes)
        .group_by("id_medico")
        .agg([
            pl.col("nu_prescricoes").sum().cast(pl.Int64),
            pl.col("qtd_dias_com_prescricao").sum().cast(pl.Int64),
            pl.col("qtd_meses_ativos").sum().cast(pl.Int64),
            pl.col("qtd_meses_alta_intensidade").sum().cast(pl.Int64),
        ])
        .with_columns([
            (
                pl.col("nu_prescricoes").cast(pl.Float64)
                / pl.col("qtd_dias_com_prescricao").cast(pl.Float64)
            ).alias("taxa_prescricoes_dia"),
            (
                pl.col("qtd_meses_alta_intensidade") / pl.col("qtd_meses_ativos") * 100
            ).alias("percentual_meses_alta_intensidade"),
        ])
        .collect(engine="streaming")
    )


def _montar_resposta_ranking(
    ranking_aggregated: pl.DataFrame,
    *,
    map_level: MapLevel,
    escopo: str,
    inicio: date,
    fim: date,
    page: int,
    page_size: int,
    manager_map: Optional[list[CrmPrescricoesMapaItemSchema]],
    prescricoes_filtradas: Optional[Callable[[list[str]], pl.DataFrame]] = None,
) -> CrmPrescricoesAnaliseResponse:
    """Pagina o ranking agregado (1 linha por medico) e completa nome/CRM da pagina.

    Com filtro de farmacia, `prescricoes_filtradas` recebe os id_medico da
    pagina e devolve (id_medico, nu_prescricoes_farmacias_filtradas): so os 25
    medicos exibidos precisam dessa soma.
    """
    farmacias_filtradas = prescricoes_filtradas is not None
    ranking_total = ranking_aggregated.height
    if ranking_total == 0:
        return CrmPrescricoesAnaliseResponse(
            map_level=map_level,
            escopo=escopo,
            periodo_inicio=inicio,
            periodo_fim=fim,
            qtd_medicos=0,
            ranking_page=page,
            ranking_page_size=page_size,
            mapa=manager_map or [],
            ranking=[],
            filtro_farmacias_ativo=farmacias_filtradas,
        )

    ranking_offset = (page - 1) * page_size
    ranking_limit = min(ranking_offset + page_size, ranking_total)
    ranking_scope = (
        ranking_aggregated
        .top_k(
            ranking_limit,
            by=["taxa_prescricoes_dia", "nu_prescricoes", "id_medico"],
            reverse=[False, False, True],
        )
        .sort(
            ["taxa_prescricoes_dia", "nu_prescricoes", "id_medico"],
            descending=[True, True, False],
        )
        .slice(ranking_offset, page_size)
        .with_row_index("rank")
        .with_columns((pl.col("rank") + ranking_offset + 1).cast(pl.Int64))
    )
    if ranking_scope.is_empty():
        return CrmPrescricoesAnaliseResponse(
            map_level=map_level,
            escopo=escopo,
            periodo_inicio=inicio,
            periodo_fim=fim,
            qtd_medicos=ranking_total,
            ranking_page=page,
            ranking_page_size=page_size,
            mapa=manager_map or [],
            ranking=[],
            filtro_farmacias_ativo=farmacias_filtradas,
        )

    medico_ids = ranking_scope.select("id_medico")
    try:
        medico_df = get_dados_medico_df().lazy().filter(
            pl.col("id_medico").is_in(medico_ids.get_column("id_medico"))
        ).collect()
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Cache de dados dos medicos indisponivel: {exc}") from exc
    _require_columns(medico_df, CRM_ANALYSIS_REQUIRED_MEDICO_COLUMNS, "Dados dos medicos")
    medico_df = medico_df.unique(subset=["id_medico"], keep="first")
    ranking_scope = ranking_scope.join(medico_df, on="id_medico", how="left")
    if prescricoes_filtradas is not None:
        filtradas = prescricoes_filtradas(ranking_scope.get_column("id_medico").to_list())
        ranking_scope = ranking_scope.join(filtradas, on="id_medico", how="left")
        if ranking_scope.get_column("nu_prescricoes_farmacias_filtradas").null_count():
            raise HTTPException(
                status_code=503,
                detail="Medico do ranking sem prescricoes nas farmacias filtradas (indice CRM inconsistente).",
            )
        ranking_scope = ranking_scope.with_columns(
            (pl.col("nu_prescricoes_farmacias_filtradas") / pl.col("nu_prescricoes") * 100)
            .alias("percentual_prescricoes_farmacias_filtradas")
        )
    ranking = [
        CrmPrescricoesRankingItemSchema(
            rank=int(row["rank"]),
            id_medico=str(row["id_medico"]),
            nu_crm=int(row["nu_crm"]) if row["nu_crm"] is not None else None,
            sg_uf=str(row["sg_uf"]) if row["sg_uf"] is not None else None,
            no_medico=str(row["no_medico"]) if row["no_medico"] is not None else None,
            taxa_prescricoes_dia=float(row["taxa_prescricoes_dia"]),
            nu_prescricoes=int(row["nu_prescricoes"]),
            qtd_dias_com_prescricao=int(row["qtd_dias_com_prescricao"]),
            qtd_meses_ativos=int(row["qtd_meses_ativos"]),
            qtd_meses_alta_intensidade=int(row["qtd_meses_alta_intensidade"]),
            percentual_meses_alta_intensidade=float(row["percentual_meses_alta_intensidade"]),
            nu_prescricoes_farmacias_filtradas=(
                int(row["nu_prescricoes_farmacias_filtradas"])
                if farmacias_filtradas else None
            ),
            percentual_prescricoes_farmacias_filtradas=(
                float(row["percentual_prescricoes_farmacias_filtradas"])
                if farmacias_filtradas else None
            ),
        )
        for row in ranking_scope.iter_rows(named=True)
    ]
    return CrmPrescricoesAnaliseResponse(
        map_level=map_level,
        escopo=escopo,
        periodo_inicio=inicio,
        periodo_fim=fim,
        qtd_medicos=ranking_total,
        ranking_page=page,
        ranking_page_size=page_size,
        mapa=manager_map or [],
        ranking=ranking,
        filtro_farmacias_ativo=farmacias_filtradas,
    )



def ranking_agregado_escopo(
    *,
    inicio: date,
    fim: date,
    uf: Optional[str],
    regiao_id: Optional[int],
    id_ibge7: Optional[int],
) -> pl.DataFrame:
    """Ranking agregado (1 linha por medico) do escopo mais especifico, com cache.

    Sem UF/regiao/municipio: modulos nacionais (medico x mes/ano). Com escopo:
    modulos por territorio, filtrados no nivel e id do escopo (o modulo ja traz
    cada nivel agregado).
    """
    if id_ibge7 is not None:
        scope_level, scope_identifier = "municipio", str(id_ibge7)
    elif regiao_id is not None:
        scope_level, scope_identifier = "regiao_saude", str(regiao_id)
    elif uf and uf != "Todos":
        scope_level, scope_identifier = "uf", uf
    else:
        scope_level, scope_identifier = "brasil", None
    nacional = scope_level == "brasil"

    ranking_cache_key = _ranking_cache_key(
        geographic=not nacional,
        inicio=inicio,
        fim=fim,
        uf=None if nacional else uf,
        regiao_id=regiao_id,
        id_ibge7=id_ibge7,
    )
    ranking_aggregated = _get_cached_ranking(ranking_cache_key)
    if ranking_aggregated is not None:
        return ranking_aggregated

    try:
        monthly_full = scan_crm_medico_brasil_mes() if nacional else scan_crm_medico_territorio_mes()
        yearly = scan_crm_medico_brasil_ano() if nacional else scan_crm_medico_territorio_ano()
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=(
                (
                    "Cache de prescricoes nacionais por medico (mes/ano) indisponivel: "
                    if nacional
                    else "Cache de prescricoes por medico/territorio (mes/ano) indisponivel: "
                )
                + f"{exc}"
            ),
        ) from exc

    periodo = pl.col("competencia").is_between(_competencia(inicio), _competencia(fim))
    if nacional:
        _require_columns(
            monthly_full.limit(0).collect(),
            CRM_ANALYSIS_REQUIRED_MEDICO_MES_COLUMNS,
            "Prescricoes nacionais por medico/mes",
        )
        _require_columns(
            yearly.limit(0).collect(),
            CRM_ANALYSIS_REQUIRED_MEDICO_ANO_COLUMNS,
            "Prescricoes nacionais por medico/ano",
        )
        # O modulo nacional ja tem uma linha por id_medico e competencia.
        ranking_aggregated = _agregar_ranking(monthly_full.filter(periodo), inicio, fim, yearly)
    else:
        _require_columns(
            monthly_full.limit(0).collect(),
            CRM_ANALYSIS_REQUIRED_MEDICO_TERRITORIO_COLUMNS,
            "Prescricoes por medico/territorio/mes",
        )
        _require_columns(
            yearly.limit(0).collect(),
            {"nivel", "id_geografico", *CRM_ANALYSIS_REQUIRED_MEDICO_ANO_COLUMNS},
            "Prescricoes por medico/territorio/ano",
        )
        escopo_territorio = (pl.col("nivel") == scope_level) & (pl.col("id_geografico") == scope_identifier)
        scoped_monthly = (
            monthly_full
            .filter(escopo_territorio & periodo)
            .select(["id_medico", "competencia", "nu_prescricoes_mes", "qtd_dias_com_prescricao_mes"])
        )
        ranking_aggregated = _agregar_ranking(scoped_monthly, inicio, fim, yearly.filter(escopo_territorio))
    _cache_ranking(ranking_cache_key, ranking_aggregated)
    return ranking_aggregated


def get_crm_prescricoes_analise(
    *,
    map_level: str = "uf",
    page: int = 1,
    page_size: int = 25,
    include_map: bool = True,
    map_only: bool = False,
    data_inicio: Optional[date] = None,
    data_fim: Optional[date] = None,
    perc_min: Optional[float] = None,
    perc_max: Optional[float] = None,
    val_min: Optional[float] = None,
    uf: Optional[str] = None,
    regiao_id: Optional[int] = None,
    id_ibge7: Optional[int] = None,
    situacao_rf: Optional[str] = None,
    conexao_ms: Optional[str] = None,
    porte_empresa: Optional[str] = None,
    grande_rede: Optional[str] = None,
    cnpj_raiz: Optional[str] = None,
    unidade_pf: Optional[str] = None,
    razao_social: Optional[str] = None,
    estabelecimento: Optional[str] = None,
    par_teia: Optional[str] = None,
    socio_beneficio: Optional[str] = None,
    socio_esocial: Optional[str] = None,
    cnae_incompativel: bool = False,
    socio_idade_atipica: bool = False,
    socio_falecido: bool = False,
    volume_atipico: bool = False,
    volume_atipico_limite: Optional[float] = None,
    dispersao_uf_sem_fronteira: bool = False,
    dispersao_uf_sem_fronteira_limite: Optional[float] = None,
) -> CrmPrescricoesAnaliseResponse:
    if page < 1:
        raise HTTPException(status_code=422, detail="page deve ser maior ou igual a 1.")
    if page_size < 1 or page_size > 100:
        raise HTTPException(status_code=422, detail="page_size deve estar entre 1 e 100.")

    if map_level not in {"uf", "municipio", "regiao"}:
        raise HTTPException(status_code=422, detail="map_level deve ser uf, municipio ou regiao.")
    nivel_mapa = cast(MapLevel, map_level)  # validado acima
    if map_level == "municipio" and (not uf or uf == "Todos"):
        raise HTTPException(status_code=422, detail="O mapa municipal exige uma UF selecionada.")
    if map_level == "regiao" and regiao_id is None:
        raise HTTPException(status_code=422, detail="O mapa da região exige regiao_id.")

    inicio, fim = _period_bounds(data_inicio, data_fim)
    if not _pode_usar_cache_gerencial(
        perc_min=perc_min,
        perc_max=perc_max,
        val_min=val_min,
        situacao_rf=situacao_rf,
        conexao_ms=conexao_ms,
        porte_empresa=porte_empresa,
        grande_rede=grande_rede,
        cnpj_raiz=cnpj_raiz,
        unidade_pf=unidade_pf,
        razao_social=razao_social,
        estabelecimento=estabelecimento,
        par_teia=par_teia,
        socio_beneficio=socio_beneficio,
        socio_esocial=socio_esocial,
        cnae_incompativel=cnae_incompativel,
        socio_idade_atipica=socio_idade_atipica,
        socio_falecido=socio_falecido,
        volume_atipico=volume_atipico,
        dispersao_uf_sem_fronteira=dispersao_uf_sem_fronteira,
    ):
        filtro_farmacias_ativo = True
    else:
        filtro_farmacias_ativo = False
    if _filtro_ativo(razao_social):
        raise HTTPException(
            status_code=422,
            detail="Filtro razao_social nao e usado na analise de CRMs; use 'estabelecimento'.",
        )
    # Com filtro de farmacia, o universo e o das farmacias filtradas (as mesmas de
    # /estabelecimentos): ver crm_analysis_filtrado. Valores neutros viram None.
    filtros_farmacia = {
        "situacao_rf": situacao_rf if _filtro_ativo(situacao_rf, neutral={"Todos"}) else None,
        "conexao_ms": conexao_ms if _filtro_ativo(conexao_ms, neutral={"Todos"}) else None,
        "porte_empresa": porte_empresa if _filtro_ativo(porte_empresa, neutral={"Todos"}) else None,
        "grande_rede": grande_rede if _filtro_ativo(grande_rede, neutral={"Todos"}) else None,
        "cnpj_raiz": cnpj_raiz if _filtro_ativo(cnpj_raiz) else None,
        "estabelecimento": estabelecimento if _filtro_ativo(estabelecimento) else None,
        "unidade_pf": unidade_pf if _filtro_ativo(unidade_pf, neutral={"Todos"}) else None,
        "par_teia": par_teia if _filtro_ativo(par_teia) else None,
        "socio_beneficio": socio_beneficio if _filtro_ativo(socio_beneficio) else None,
        "socio_esocial": socio_esocial if _filtro_ativo(socio_esocial) else None,
        "cnae_incompativel": cnae_incompativel,
        "socio_idade_atipica": socio_idade_atipica,
        "socio_falecido": socio_falecido,
        "dispersao_uf_sem_fronteira": dispersao_uf_sem_fronteira,
        "dispersao_uf_sem_fronteira_limite": dispersao_uf_sem_fronteira_limite if dispersao_uf_sem_fronteira else None,
        "perc_min": perc_min if perc_min is not None and float(perc_min) != 0 else None,
        "perc_max": perc_max if perc_max is not None and float(perc_max) != 100 else None,
        "val_min": val_min if val_min is not None and float(val_min) > 0 else None,
        "volume_atipico": volume_atipico,
        "volume_atipico_limite": volume_atipico_limite if volume_atipico else None,
    }

    try:
        if (include_map or map_only) and filtro_farmacias_ativo:
            from .crm_analysis_filtrado import mapa_filtrado
            manager_map, map_qtd_medicos, map_referencia = mapa_filtrado(
                filtros=filtros_farmacia,
                map_level=nivel_mapa,
                inicio=inicio,
                fim=fim,
                uf=uf,
                regiao_id=regiao_id,
                id_ibge7=id_ibge7,
            )
        elif include_map or map_only:
            manager_map, map_qtd_medicos, map_referencia = _build_manager_map(
                map_level=nivel_mapa,
                inicio=inicio,
                fim=fim,
                uf=uf,
                regiao_id=regiao_id,
                id_ibge7=id_ibge7,
            )
        else:
            manager_map = None
            map_qtd_medicos = 0
            map_referencia = {}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=(
                "Cache gerencial de prescricoes indisponivel: "
                f"{exc}"
            ),
        ) from exc

    escopo = _scope_label(uf=uf, regiao_id=regiao_id, id_ibge7=id_ibge7)
    if map_only:
        # Legenda: faixa do corte P95 nos meses do periodo.
        limiares = _limiares_do_periodo(inicio, fim)
        return CrmPrescricoesAnaliseResponse(
            map_level=nivel_mapa,
            escopo=escopo,
            periodo_inicio=inicio,
            periodo_fim=fim,
            qtd_medicos=map_qtd_medicos,
            ranking_page=page,
            ranking_page_size=page_size,
            mapa=manager_map or [],
            ranking=[],
            percentual_referencia_brasil=map_referencia.get("percentual_referencia_brasil"),
            percentual_referencia_uf=map_referencia.get("percentual_referencia_uf"),
            percentual_referencia_regiao=map_referencia.get("percentual_referencia_regiao"),
            limiar_p95_min=float(limiares.select(pl.col("p95_taxa_dia").min()).item()),
            limiar_p95_max=float(limiares.select(pl.col("p95_taxa_dia").max()).item()),
            min_medicos_amostra_municipio=CRM_MAPA_MIN_MEDICOS_ATIVOS_MUNICIPIO,
            filtro_farmacias_ativo=filtro_farmacias_ativo,
        )

    if filtro_farmacias_ativo:
        from .crm_analysis_filtrado import ranking_filtrado
        if page < 1 or page_size < 1 or page_size > 100:
            raise HTTPException(status_code=422, detail="Pagina ou tamanho de pagina invalido.")
        try:
            ranking_aggregated, prescricoes_filtradas = ranking_filtrado(
                filtros=filtros_farmacia,
                inicio=inicio,
                fim=fim,
                uf=uf,
                regiao_id=regiao_id,
                id_ibge7=id_ibge7,
            )
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(
                status_code=503,
                detail=f"Indice CRM de farmacias indisponivel: {exc}",
            ) from exc
        return _montar_resposta_ranking(
            ranking_aggregated,
            map_level=nivel_mapa,
            escopo=escopo,
            inicio=inicio,
            fim=fim,
            page=page,
            page_size=page_size,
            manager_map=manager_map,
            prescricoes_filtradas=prescricoes_filtradas,
        )

    try:
        ranking_aggregated = ranking_agregado_escopo(
            inicio=inicio, fim=fim, uf=uf, regiao_id=regiao_id, id_ibge7=id_ibge7,
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Cache de prescricoes por medico (mes/ano) indisponivel: {exc}",
        ) from exc
    return _montar_resposta_ranking(
        ranking_aggregated,
        map_level=nivel_mapa,
        escopo=escopo,
        inicio=inicio,
        fim=fim,
        page=page,
        page_size=page_size,
        manager_map=manager_map,
    )
