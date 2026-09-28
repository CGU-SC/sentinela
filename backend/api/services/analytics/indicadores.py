from typing import Any, List, Literal, Optional, TypeVar
from datetime import date
import calendar
from collections import OrderedDict
from threading import RLock
import polars as pl
from sqlalchemy.orm import Session
from sqlalchemy import text
from fastapi import HTTPException
import os
import zlib
import json
import copy
from decimal import Decimal, ROUND_HALF_UP
from data_cache import get_df, get_rede_df, get_df_bench_crm_regiao, get_df_bench_crm_br, get_df_dados_farmacia, get_df_perfil_estabelecimento, get_cache_dir, get_cache_generation, scan_geografico_origem_uf
from .indicator_config import (
    INDICATOR_MAPPING,
    INDICATOR_FLAGS as _INDICATOR_FLAGS,
    INDICATOR_AGGREGATIONS,
)
from .matriz_risco_dinamica import (
    MIN_REGIAO_BENCHMARK,
    build_annual_indicator_benchmark_matriz,
    build_dynamic_matriz_risco as _build_dynamic_matriz_risco,
)
from .indicator_rules import CLINICA_VALOR_MINIMO_DETALHAMENTO, get_volume_atipico_aumento_minimo
from .alertas_alvos import build_perfil_filtrado
from .dispersao_uf import get_dispersao_uf_sem_fronteira_id_cnpjs_df
from .geografico import UF_VIZINHAS, UF_BRASILEIRAS
from ...utils.text_search import apply_token_search
from ...schemas.analytics import (
    AnalyticsKPISchema,
    ResultadoSentinelaUFSchema,
    AnalyticsResponse,
    ResultadoSentinelaMunicipioSchema,
    ResultadoSentinelaCnpjSchema,
    RedeEstabelecimentoSchema,
    FatorRiscoResponseSchema,
    FatorRiscoBucketSchema,
    EvolucaoSemestreSchema,
    EvolucaoFinanceiraResponse,
    IndicadorDataSchema,
    IndicadoresResponse,
    FalecidoTransactionSchema,
    FalecidosRankingSchema,
    FalecidosSummarySchema,
    FalecidosResponse,
    TimelineEventSchema,
    MultiCnpjTimelineResponse,
    RegionalMunicipioSchema,
    RegionalFarmaciaSchema,
    RegionalResponse,
    RegionalAnimationQuarterSchema,
    RegionalAnimationResponse,
    PrescritoresResponse,
    DadosFarmaciaSchema,
    MovimentacaoRowSchema,
    MovimentacaoSummarySchema,
    MovimentacaoResponse,
    IndicadorKpiSummarySchema,
    IndicadorCnpjRowSchema,
    IndicadorMunicipioRowSchema,
    IndicadorAnaliseResponse,
    IndicadorCnpjPageResponse,
    IndicadorBenchmarkKpiSchema,
    IndicadorBenchmarkRowSchema,
    IndicadorBenchmarkScopeSchema,
    IndicadorBenchmarkResponse,
    IndicadorEvolucaoBenchmarkPointSchema,
    IndicadorEvolucaoBenchmarkPeriodoSchema,
    IndicadorEvolucaoBenchmarkResponse,
    MesMensalGtinItem,
    EvolucaoMensalGtinResponse,
    GtinDetalhamentoMensalResponse,
    GtinDetalhamentoMensalSummary,
    GtinDetalhamentoMensalItem,
)

def _optional_float(value: object) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float, Decimal)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None


def _apply_estabelecimento_search(df: pl.DataFrame, estabelecimento: str | None) -> pl.DataFrame:
    return apply_token_search(df, estabelecimento, ("cnpj", "razao_social", "nome_fantasia"))


# Caches em memoria da analise de indicadores. Os modulos so mudam na
# sincronizacao, e a chave inclui get_cache_generation() e o limite de volume
# atipico das configuracoes: nao ha prazo de validade. O limite de itens controla
# a memoria e descarta o item usado ha mais tempo (LRU).
_INDICADOR_CACHE_MAX_ENTRIES = 64
_INDICADOR_CACHE_LOCK = RLock()

_INDICADOR_VALOR_FINANCEIRO_COLS = {
    "percentual_nao_comprovacao": "valor_sem_comprovacao",
    "falecidos": "falecidos_valor",
    "incompatibilidade_patologica": "clinico_valor_suspeito",
    "teto": "teto_valor",
    "polimedicamento": "polimedicamento_valor",
    "alto_custo": "alto_custo_valor",
    "vendas_rapidas": "vendas_rapidas_valor",
    "recorrencia_sistemica": "recorrencia_valor_sistemico",
    "dias_pico": "pico_valor_top3_dias",
    "dispersao_geografica": "geografico_valor_outra_uf",
    "volume_atipico": "volume_atipico_valor_aumento_atipico",
    "hhi_crm": "hhi_valor_total",
    "crms_irregulares": "crms_irregulares_valor",
}

_INDICADOR_DISPLAY_VALUE_COLS = {
    "volume_atipico": "volume_atipico_valor_aumento_atipico",
}

_INDICADOR_EXTRA_COLS: dict[str, list[str]] = {
    "volume_atipico": ["volume_atipico_maior_taxa_crescimento_pct"],
    "dispersao_geografica": ["pct_dispersao_uf_nao_vizinha"],
}

_INDICADOR_BENCHMARK_LOCAL_KEYS = {
    "falecidos",
    "incompatibilidade_patologica",
    "percentual_nao_comprovacao",
    "teto",
    "polimedicamento",
    "ticket_medio",
    "receita_paciente",
    "per_capita",
    "alto_custo",
    "vendas_rapidas",
    "volume_atipico",
    "recorrencia_sistemica",
    "dias_pico",
    "hhi_crm",
    "crms_irregulares",
}

_INDICADOR_BENCHMARK_FORMATOS = {
    "falecidos": "pct3",
    "incompatibilidade_patologica": "pct",
    "percentual_nao_comprovacao": "pct",
    "teto": "pct",
    "polimedicamento": "pct",
    "ticket_medio": "val",
    "receita_paciente": "val",
    "per_capita": "val",
    "alto_custo": "pct",
    "vendas_rapidas": "pct",
    "volume_atipico": "val",
    "recorrencia_sistemica": "pct",
    "dias_pico": "pct",
    "hhi_crm": "dec",
    "crms_irregulares": "pct",
}

_INDICADOR_SCOPE_BASE_CACHE: "OrderedDict[tuple[object, ...], tuple[pl.DataFrame, pl.DataFrame]]" = OrderedDict()

_INDICADOR_DATASET_CACHE: "OrderedDict[tuple[object, ...], tuple[pl.DataFrame, pl.DataFrame, pl.DataFrame, str, str, str | None, str]]" = OrderedDict()

_IndicadorCachePayload = TypeVar("_IndicadorCachePayload")


def _normalize_cache_text(value: object) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    if not normalized or normalized == "Todos":
        return None
    return normalized


def _normalize_cache_int(value: object) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        raise TypeError("Valor booleano invalido para filtro numerico inteiro.")
    if isinstance(value, (int, str)):
        return int(value)
    if isinstance(value, Decimal):
        return int(value)
    if isinstance(value, float):
        if not value.is_integer():
            raise TypeError("Valor decimal invalido para filtro numerico inteiro.")
        return int(value)
    raise TypeError(f"Tipo invalido para filtro numerico inteiro: {type(value).__name__}.")


def _normalize_cache_float(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        raise TypeError("Valor booleano invalido para filtro numerico decimal.")
    if isinstance(value, (int, float, Decimal, str)):
        return float(value)
    raise TypeError(f"Tipo invalido para filtro numerico decimal: {type(value).__name__}.")


def _normalize_cache_bool(value: object) -> bool:
    return bool(value)


def _normalize_cache_date(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


def _normalize_cache_cnpj(value: object) -> str | None:
    normalized = _normalize_cache_text(value)
    if normalized is None:
        return None
    return normalized.replace(".", "").replace("/", "").replace("-", "")


_INDICADOR_SCOPE_FILTER_FIELDS = (
    ("data_inicio", _normalize_cache_date),
    ("data_fim", _normalize_cache_date),
    ("uf", _normalize_cache_text),
    ("regiao_id", _normalize_cache_int),
    ("id_ibge7", _normalize_cache_int),
    ("situacao_rf", _normalize_cache_text),
    ("conexao_ms", _normalize_cache_text),
    ("porte_empresa", _normalize_cache_text),
    ("grande_rede", _normalize_cache_text),
    ("cnpj_raiz", _normalize_cache_cnpj),
    ("estabelecimento", _normalize_cache_text),
    ("unidade_pf", _normalize_cache_text),
    ("par_teia", _normalize_cache_text),
    ("socio_beneficio", _normalize_cache_text),
    ("socio_esocial", _normalize_cache_text),
    ("cnae_incompativel", _normalize_cache_bool),
    ("socio_idade_atipica", _normalize_cache_bool),
    ("socio_falecido", _normalize_cache_bool),
    ("dispersao_uf_sem_fronteira", _normalize_cache_bool),
    ("dispersao_uf_sem_fronteira_limite", _normalize_cache_float),
    ("perc_min", _normalize_cache_float),
    ("perc_max", _normalize_cache_float),
    ("val_min", _normalize_cache_float),
    ("volume_atipico", _normalize_cache_bool),
    ("volume_atipico_limite", _normalize_cache_float),
)


def _make_indicador_scope_base_cache_key(
    *,
    filters: dict[str, object],
) -> tuple[object, ...]:
    return (
        get_cache_generation(),
        get_volume_atipico_aumento_minimo(),
        *(
            normalizer(filters.get(field_name))
            for field_name, normalizer in _INDICADOR_SCOPE_FILTER_FIELDS
        ),
    )


def _make_indicador_dataset_cache_key(
    *,
    indicador: str,
    filters: dict[str, object],
) -> tuple[object, ...]:
    return (
        get_cache_generation(),
        get_volume_atipico_aumento_minimo(),
        indicador,
        *(
            normalizer(filters.get(field_name))
            for field_name, normalizer in _INDICADOR_SCOPE_FILTER_FIELDS
        ),
    )


def _prune_indicador_cache(
    cache: "OrderedDict[tuple[object, ...], _IndicadorCachePayload]",
    generation: int,
) -> None:
    """Remove itens de geracoes anteriores e os usados ha mais tempo (chamar com o lock)."""
    for key in [key for key in cache if key[0] != generation]:
        del cache[key]
    while len(cache) > _INDICADOR_CACHE_MAX_ENTRIES:
        cache.popitem(last=False)


def _get_indicador_cache(
    cache: "OrderedDict[tuple[object, ...], _IndicadorCachePayload]",
    key: tuple[object, ...],
) -> _IndicadorCachePayload | None:
    """Le um item e renova a posicao dele (chamar com o lock)."""
    value = cache.get(key)
    if value is not None:
        cache.move_to_end(key)
    return value


def _put_indicador_cache(
    cache: "OrderedDict[tuple[object, ...], _IndicadorCachePayload]",
    key: tuple[object, ...],
    value: _IndicadorCachePayload,
    generation: int,
) -> None:
    """Grava um item como o mais recente e aplica o limite (chamar com o lock)."""
    cache[key] = value
    cache.move_to_end(key)
    _prune_indicador_cache(cache, generation)


def _cache_generation_from_key(cache_key: tuple[object, ...]) -> int:
    generation = cache_key[0]
    if isinstance(generation, bool) or not isinstance(generation, int):
        raise RuntimeError("Chave de cache de indicadores possui geracao invalida.")
    return generation


def _benchmark_escopo_expr() -> pl.Expr:
    return (
        pl.when(pl.col("_total_regiao_benchmark") >= MIN_REGIAO_BENCHMARK)
        .then(pl.lit("REGIÃO"))
        .otherwise(pl.lit("UF"))
        .alias("benchmark_escopo")
    )


def _benchmark_escopo_from_row(row: dict) -> str:
    total_regiao = row.get("_total_regiao_benchmark")
    return "REGIÃO" if total_regiao is not None and int(total_regiao) >= MIN_REGIAO_BENCHMARK else "UF"


def _valor_financeiro_indicador(row: dict, key: str) -> float | None:
    col = _INDICADOR_VALOR_FINANCEIRO_COLS.get(key)
    if col is None:
        return None
    if col not in row:
        raise RuntimeError(f"Indicador {key} sem coluna financeira obrigatoria na matriz dinamica: {col}")
    return _optional_float(row.get(col))


def _pode_detalhar_indicador(row: dict, key: str) -> bool:
    if key != "incompatibilidade_patologica":
        return False
    valor_financeiro = _valor_financeiro_indicador(row, key)
    return valor_financeiro is not None and valor_financeiro >= CLINICA_VALOR_MINIMO_DETALHAMENTO


def _require_columns(df: pl.DataFrame, columns: list[str], source: str) -> None:
    missing = [col for col in columns if col not in df.columns]
    if missing:
        raise RuntimeError(
            f"Colunas obrigatorias ausentes em {source}: " + ", ".join(missing)
        )


def _status_indicador_benchmark(row: dict, *, value_col: str, atencao_col: str, critico_col: str) -> str:
    if row.get(value_col) is None:
        return "SEM DADOS"
    if int(row.get(critico_col) or 0) == 1:
        return "CRITICO"
    if int(row.get(atencao_col) or 0) == 1:
        return "ATENCAO"
    return "NORMAL"


def _indicador_benchmark_row_schema(
    row: dict,
    *,
    cnpj_alvo: str,
    indicador: str,
    value_col: str,
    med_reg_col: str,
    med_uf_col: str,
    risco_reg_col: str,
    risco_uf_col: str,
    atencao_col: str,
    critico_col: str,
    status_value_col: str | None = None,
) -> IndicadorBenchmarkRowSchema:
    valor_financeiro_col = _INDICADOR_VALOR_FINANCEIRO_COLS.get(indicador)
    valor_financeiro = None
    if valor_financeiro_col is not None:
        if valor_financeiro_col not in row:
            raise RuntimeError(
                f"Indicador {indicador} sem coluna financeira obrigatoria no benchmark local: "
                f"{valor_financeiro_col}"
            )
        valor_financeiro = _optional_float(row.get(valor_financeiro_col))

    if row.get("is_conexao_ativa") is None:
        raise RuntimeError("Campo obrigatorio is_conexao_ativa ausente no benchmark local.")
    if row.get("is_matriz") is None:
        raise RuntimeError("Campo obrigatorio is_matriz ausente no benchmark local.")

    valor_movimentado = _optional_float(row.get("valor_total_vendas"))
    valor_sem_comprovacao = _optional_float(row.get("valor_sem_comprovacao"))
    percentual_nao_comprovacao = (
        round((valor_sem_comprovacao / valor_movimentado) * 100, 2)
        if valor_movimentado is not None
        and valor_sem_comprovacao is not None
        and valor_movimentado > 0
        else None
    )

    agg_spec = INDICATOR_AGGREGATIONS.get(indicador)
    valor_numerador = None
    valor_denominador = None
    if agg_spec:
        num_col = str(agg_spec["numerator"])
        den_col = str(agg_spec["denominator"])
        if num_col in row:
            valor_numerador = _optional_float(row.get(num_col))
        if den_col in row:
            valor_denominador = _optional_float(row.get(den_col))
    if indicador == "volume_atipico":
        valor_numerador = _optional_float(row.get("volume_atipico_valor_aumento_atipico"))
        valor_denominador = None

    return IndicadorBenchmarkRowSchema(
        cnpj=str(row["cnpj"]),
        razao_social=row.get("razao_social"),
        municipio=row.get("no_municipio"),
        uf=row.get("uf"),
        is_conexao_ativa=bool(row["is_conexao_ativa"]),
        is_matriz=bool(row["is_matriz"]),
        valor=_optional_float(row.get(value_col)),
        valor_financeiro=valor_financeiro,
        valor_movimentado=valor_movimentado,
        valor_sem_comprovacao=valor_sem_comprovacao,
        percentual_nao_comprovacao=percentual_nao_comprovacao,
        mediana_regiao=_optional_float(row.get(med_reg_col)),
        mediana_uf=_optional_float(row.get(med_uf_col)),
        risco_regiao=_optional_float(row.get(risco_reg_col)),
        risco_uf=_optional_float(row.get(risco_uf_col)),
        status=_status_indicador_benchmark(
            row,
            value_col=status_value_col or value_col,
            atencao_col=atencao_col,
            critico_col=critico_col,
        ),
        is_alvo=str(row["cnpj"]) == cnpj_alvo,
        valor_numerador=valor_numerador,
        valor_denominador=valor_denominador,
    )


def _indicador_benchmark_scope_schema(
    *,
    escopo: Literal["municipio", "regiao_saude"],
    label: str,
    rows_df: pl.DataFrame,
    cnpj_alvo: str,
    indicador: str,
    value_col: str,
    med_reg_col: str,
    med_uf_col: str,
    risco_reg_col: str,
    risco_uf_col: str,
    atencao_col: str,
    critico_col: str,
    status_value_col: str | None = None,
) -> IndicadorBenchmarkScopeSchema:
    rows = [
        _indicador_benchmark_row_schema(
            row,
            cnpj_alvo=cnpj_alvo,
            indicador=indicador,
            value_col=value_col,
            med_reg_col=med_reg_col,
            med_uf_col=med_uf_col,
            risco_reg_col=risco_reg_col,
            risco_uf_col=risco_uf_col,
            atencao_col=atencao_col,
            critico_col=critico_col,
            status_value_col=status_value_col,
        )
        for row in rows_df.iter_rows(named=True)
    ]
    return IndicadorBenchmarkScopeSchema(
        escopo=escopo,
        label=label,
        total_estabelecimentos=len(rows),
        rows=rows,
    )


def _indicador_benchmark_kpis(
    target: dict,
    *,
    indicador: str,
    value_col: str,
    med_reg_col: str,
    med_uf_col: str,
    risco_reg_col: str,
    risco_uf_col: str,
) -> list[IndicadorBenchmarkKpiSchema]:
    formato = _INDICADOR_BENCHMARK_FORMATOS[indicador]
    return [
        IndicadorBenchmarkKpiSchema(label="Farmacia", value=_optional_float(target.get(value_col)), formato=formato),
        IndicadorBenchmarkKpiSchema(label="Mediana Regiao", value=_optional_float(target.get(med_reg_col)), formato=formato),
        IndicadorBenchmarkKpiSchema(label="Mediana UF", value=_optional_float(target.get(med_uf_col)), formato=formato),
        IndicadorBenchmarkKpiSchema(label="Risco Regiao", value=_optional_float(target.get(risco_reg_col)), formato="risco"),
        IndicadorBenchmarkKpiSchema(label="Risco UF", value=_optional_float(target.get(risco_uf_col)), formato="risco"),
    ]


def get_indicadores(
    cnpj: str,
    data_inicio: date | None = None,
    data_fim: date | None = None,
) -> IndicadoresResponse:
    """Retorna os indicadores de risco para um CNPJ calculados a partir da matriz anual."""
    try:
        perfil_df = get_df_perfil_estabelecimento()
        cnpj_limpo = "".join(ch for ch in str(cnpj) if ch.isdigit()).zfill(14)
        target = perfil_df.filter(pl.col("cnpj") == cnpj_limpo)
        if target.is_empty():
            return IndicadoresResponse(cnpj=cnpj, indicadores={})

        df = _build_dynamic_matriz_risco(data_inicio=data_inicio, data_fim=data_fim)
        rows = df.filter(pl.col("cnpj") == cnpj_limpo)
        if rows.is_empty():
            return IndicadoresResponse(cnpj=cnpj, indicadores={})
        row = rows.row(0, named=True)

        def indicador_status(key: str, value_col: str) -> str:
            if row.get(value_col) is None:
                return "SEM DADOS"
            c_aten, c_crit = _INDICATOR_FLAGS[key]
            if int(row.get(c_crit) or 0) == 1:
                return "CRÍTICO"
            if int(row.get(c_aten) or 0) == 1:
                return "ATENÇÃO"
            return "NORMAL"

        benchmark_escopo = _benchmark_escopo_from_row(row)
        indicadores = {
            key: IndicadorDataSchema(
                valor=_optional_float(row.get(c_val)),
                valor_aumento_atipico=_optional_float(row.get("volume_atipico_valor_aumento_atipico")) if key == "volume_atipico" else None,
                valor_financeiro=_valor_financeiro_indicador(row, key),
                pode_detalhar=_pode_detalhar_indicador(row, key),
                med_reg=_optional_float(row.get(c_mr)),
                med_uf=_optional_float(row.get(c_mu)),
                med_br=_optional_float(row.get(c_mb)),
                med_benchmark=_optional_float(row.get(c_mr) if benchmark_escopo == "REGIÃO" else row.get(c_mu)),
                benchmark_escopo=benchmark_escopo,
                risco_reg=_optional_float(row.get(c_rr)),
                risco_uf=_optional_float(row.get(c_ru)),
                risco_br=_optional_float(row.get(c_rb)),
                risco_benchmark=_optional_float(row.get(c_rr) if benchmark_escopo == "REGIÃO" else row.get(c_ru)),
                status=indicador_status(key, c_val),
            )
            for key, (c_val, c_mr, c_mu, c_mb, c_rr, c_ru, c_rb) in INDICATOR_MAPPING.items()
        }
        return IndicadoresResponse(cnpj=cnpj_limpo, indicadores=indicadores)
    except HTTPException:
        raise
    except Exception as exc:
        print(f"[ ANALYTICS ] {cnpj} ● INDICADORES ● ❌ INDISPONÍVEL: {exc}")
        raise HTTPException(status_code=503, detail="Indicadores indisponiveis: matriz anual de risco nao carregada ou invalida.")

def _build_indicador_scope_base(
    data_inicio: date | None = None,
    data_fim: date | None = None,
    uf: str | None = None,
    situacao_rf: str | None = None,
    conexao_ms: str | None = None,
    porte_empresa: str | None = None,
    grande_rede: str | None = None,
    cnpj_raiz: str | None = None,
    estabelecimento: str | None = None,
    unidade_pf: str | None = None,
    perc_min: float | None = None,
    perc_max: float | None = None,
    val_min: float | None = None,
    regiao_id: int | None = None,
    id_ibge7: int | None = None,
    par_teia: str | None = None,
    socio_beneficio: str | None = None,
    socio_esocial: str | None = None,
    cnae_incompativel: bool = False,
    socio_idade_atipica: bool = False,
    socio_falecido: bool = False,
    dispersao_uf_sem_fronteira: bool = False,
    dispersao_uf_sem_fronteira_limite: float | None = None,
    volume_atipico: bool = False,
    volume_atipico_limite: float | None = None,
) -> tuple[pl.DataFrame, pl.DataFrame]:
    min_data = date(2015, 7, 1)
    max_data = date(2199, 12, 31)
    inicio = max(data_inicio, min_data) if data_inicio else min_data
    fim = data_fim if data_fim else max_data

    df_mov = get_df()
    perfil_df = get_df_perfil_estabelecimento()
    period_df = df_mov.filter(pl.col("periodo").is_between(inicio, fim))
    if dispersao_uf_sem_fronteira:
        id_cnpjs_dispersao_df = get_dispersao_uf_sem_fronteira_id_cnpjs_df(
            inicio,
            fim,
            dispersao_uf_sem_fronteira_limite,
        )
        period_df = period_df.join(id_cnpjs_dispersao_df.select("id_cnpj"), on="id_cnpj", how="semi")

    scope_base = period_df.group_by("id_cnpj").agg([
        pl.col("total_vendas").sum().alias("total_vendas"),
        pl.col("total_sem_comprovacao").sum().alias("total_sem_comprovacao"),
    ]).join(perfil_df, on="id_cnpj", how="inner").with_columns([
        pl.when(pl.col("total_vendas") > 0)
          .then((pl.col("total_sem_comprovacao") / pl.col("total_vendas") * 100).round(2))
          .otherwise(pl.lit(None))
          .alias("perc_val_sem_comp")
    ])

    mask = pl.lit(True)
    if uf and uf != 'Todos':
        mask = mask & (pl.col("uf") == uf)
    if regiao_id is not None:
        mask = mask & (pl.col("id_regiao_saude") == str(regiao_id))
    if id_ibge7 is not None:
        mask = mask & (pl.col("id_ibge7") == id_ibge7)
    if situacao_rf and situacao_rf != 'Todos':
        mask = mask & (pl.col("situacao_rf") == situacao_rf)
    if conexao_ms and conexao_ms != 'Todos':
        mask = mask & (pl.col("is_conexao_ativa") == (conexao_ms == 'Ativa'))
    if porte_empresa and porte_empresa != 'Todos':
        mask = mask & (pl.col("porte_empresa") == porte_empresa)
    if grande_rede and grande_rede != 'Todos':
        mask = mask & (pl.col("is_grande_rede") == (grande_rede == 'Sim'))
    if unidade_pf and unidade_pf != 'Todos':
        mask = mask & (pl.col("unidade_pf") == unidade_pf)
    if cnpj_raiz:
        cnpj_raiz_clean = cnpj_raiz.replace(".", "").replace("/", "").replace("-", "")
        if len(cnpj_raiz_clean) == 14:
            mask = mask & (pl.col("cnpj") == cnpj_raiz_clean)
        elif len(cnpj_raiz_clean) >= 8:
            mask = mask & (pl.col("cnpj").str.slice(0, 8) == cnpj_raiz_clean[:8])

    scope_base = _apply_estabelecimento_search(scope_base.filter(mask), estabelecimento)
    scope_base = build_perfil_filtrado(
        scope_base,
        par_teia=par_teia,
        socio_beneficio=socio_beneficio,
        socio_esocial=socio_esocial,
        socio_falecido=socio_falecido,
        cnae_incompativel=cnae_incompativel,
        socio_idade_atipica=socio_idade_atipica,
        data_referencia=fim,
        volume_atipico=volume_atipico,
        volume_atipico_inicio=inicio,
        volume_atipico_fim=fim,
        volume_atipico_limite=volume_atipico_limite,
    )
    if perc_min is not None:
        scope_base = scope_base.filter(pl.col("perc_val_sem_comp") >= perc_min)
    if perc_max is not None:
        scope_base = scope_base.filter(pl.col("perc_val_sem_comp") <= perc_max)
    if val_min is not None:
        scope_base = scope_base.filter(pl.col("total_sem_comprovacao") >= val_min)

    return scope_base, perfil_df


def _get_pct_dispersao_uf_nao_vizinha_df(data_inicio: date | None = None, data_fim: date | None = None) -> pl.DataFrame:
    rows = []
    for uf1 in UF_BRASILEIRAS:
        for uf2 in UF_BRASILEIRAS:
            is_vizinho = (uf2 == uf1) or (uf2 in UF_VIZINHAS.get(uf1, set()))
            rows.append({"uf_farmacia": uf1, "uf_paciente": uf2, "is_vizinho": is_vizinho})
    df_vizinhanca = pl.DataFrame(rows)

    origem_scan = scan_geografico_origem_uf()

    if data_inicio:
        origem_scan = origem_scan.filter(pl.col("ano_base") >= int(data_inicio.year))
    if data_fim:
        origem_scan = origem_scan.filter(pl.col("ano_base") <= int(data_fim.year))

    df_agg = (
        origem_scan
        .join(df_vizinhanca.lazy(), on=["uf_farmacia", "uf_paciente"], how="inner")
        .group_by("id_cnpj")
        .agg([
            pl.col("valor_autorizado").sum().alias("_total_valor"),
            pl.col("valor_autorizado").filter(~pl.col("is_vizinho")).sum().alias("_valor_nao_vizinho")
        ])
        .with_columns(
            pl.when(pl.col("_total_valor") > 0)
            .then(pl.col("_valor_nao_vizinho") / pl.col("_total_valor") * 100)
            .otherwise(0.0)
            .alias("pct_dispersao_uf_nao_vizinha")
        )
        .select(["id_cnpj", "pct_dispersao_uf_nao_vizinha"])
        .collect()
    )
    return df_agg


def _build_indicador_dataset(
    indicador: str,
    scope_base: pl.DataFrame,
    perfil_df: pl.DataFrame,
    data_inicio: date | None = None,
    data_fim: date | None = None,
) -> tuple[pl.DataFrame, pl.DataFrame, pl.DataFrame, str, str, str | None, str]:
    if indicador not in INDICATOR_MAPPING:
        raise HTTPException(
            status_code=400,
            detail=f"Indicador '{indicador}' inválido. Valores aceitos: {sorted(INDICATOR_MAPPING.keys())}"
        )

    c_val, c_mr, c_mu, _c_mb, c_rr, c_ru, _c_rb = INDICATOR_MAPPING[indicador]
    c_aten, c_crit = _INDICATOR_FLAGS[indicador]
    score_col = "score_risco_final"

    if scope_base.is_empty():
        return scope_base, perfil_df, pl.DataFrame(), c_val, c_mr, None, score_col

    df_risco = _build_dynamic_matriz_risco(
        data_inicio=data_inicio,
        data_fim=data_fim,
    )

    if indicador == "dispersao_geografica":
        df_nao_vizinha = _get_pct_dispersao_uf_nao_vizinha_df(data_inicio, data_fim)
        df_risco = df_risco.join(df_nao_vizinha, on="id_cnpj", how="left").with_columns(
            pl.col("pct_dispersao_uf_nao_vizinha").fill_null(0.0)
        )
    risco_cols = ["id_cnpj", "_total_regiao_benchmark", c_val, c_mr, c_mu, c_rr, c_ru, c_aten, c_crit, score_col]
    # Para volume_atipico, inclui a coluna monetária de aumento para exibição na tabela
    display_col = _INDICADOR_DISPLAY_VALUE_COLS.get(indicador)
    if display_col and display_col not in risco_cols:
        risco_cols.append(display_col)

    extra_cols = _INDICADOR_EXTRA_COLS.get(indicador, [])
    for extra_col in extra_cols:
        if extra_col not in risco_cols:
            risco_cols.append(extra_col)
    missing_cols = [col for col in risco_cols if col not in df_risco.columns]
    if missing_cols:
        raise RuntimeError(
            f"Colunas dinamicas obrigatorias ausentes para indicador '{indicador}': "
            + ", ".join(missing_cols)
        )
    indicador_dataset = scope_base.join(df_risco.select(risco_cols), on="id_cnpj", how="inner")
    if indicador_dataset.is_empty():
        return indicador_dataset, perfil_df, df_risco, c_val, c_mr, None, score_col

    rr_col = c_rr if c_rr in indicador_dataset.columns else None
    has_flags = c_crit in indicador_dataset.columns and c_aten in indicador_dataset.columns
    if has_flags:
        indicador_dataset = (
            indicador_dataset
            .with_columns([
                _benchmark_escopo_expr(),
                pl.when(pl.col("_total_regiao_benchmark") >= MIN_REGIAO_BENCHMARK)
                  .then(pl.col(c_mr))
                  .otherwise(pl.col(c_mu))
                  .alias("med_benchmark"),
                pl.when(pl.col("_total_regiao_benchmark") >= MIN_REGIAO_BENCHMARK)
                  .then(pl.col(c_rr))
                  .otherwise(pl.col(c_ru))
                  .alias("risco_benchmark"),
            ])
            .with_columns([
                pl.when(pl.col(c_val).is_null())
                  .then(pl.lit("SEM DADOS"))
                  .when(pl.col(c_crit).cast(pl.Int32) == 1)
                  .then(pl.lit("CRÍTICO"))
                  .when(pl.col(c_aten).cast(pl.Int32) == 1)
                  .then(pl.lit("ATENÇÃO"))
                  .otherwise(pl.lit("NORMAL"))
                  .alias("status")
            ])
        )
    else:
        indicador_dataset = indicador_dataset.with_columns(pl.lit("SEM DADOS").alias("status"))

    return indicador_dataset, perfil_df, df_risco, c_val, c_mr, rr_col, score_col


def _build_indicador_dataset_cached(
    indicador: str,
    data_inicio: date | None = None,
    data_fim: date | None = None,
    uf: str | None = None,
    situacao_rf: str | None = None,
    conexao_ms: str | None = None,
    porte_empresa: str | None = None,
    grande_rede: str | None = None,
    cnpj_raiz: str | None = None,
    estabelecimento: str | None = None,
    unidade_pf: str | None = None,
    perc_min: float | None = None,
    perc_max: float | None = None,
    val_min: float | None = None,
    regiao_id: int | None = None,
    id_ibge7: int | None = None,
    par_teia: str | None = None,
    socio_beneficio: str | None = None,
    socio_esocial: str | None = None,
    cnae_incompativel: bool = False,
    socio_idade_atipica: bool = False,
    socio_falecido: bool = False,
    dispersao_uf_sem_fronteira: bool = False,
    dispersao_uf_sem_fronteira_limite: float | None = None,
    volume_atipico: bool = False,
    volume_atipico_limite: float | None = None,
) -> tuple[pl.DataFrame, pl.DataFrame, pl.DataFrame, str, str, str | None, str]:
    raw_values = locals()
    filters = {
        field_name: raw_values[field_name]
        for field_name, _normalizer in _INDICADOR_SCOPE_FILTER_FIELDS
    }
    scope_cache_key = _make_indicador_scope_base_cache_key(filters=filters)
    dataset_cache_key = _make_indicador_dataset_cache_key(
        indicador=indicador,
        filters=filters,
    )
    generation = _cache_generation_from_key(dataset_cache_key)

    with _INDICADOR_CACHE_LOCK:
        _prune_indicador_cache(_INDICADOR_SCOPE_BASE_CACHE, generation)
        _prune_indicador_cache(_INDICADOR_DATASET_CACHE, generation)

        cached_dataset = _get_indicador_cache(_INDICADOR_DATASET_CACHE, dataset_cache_key)
        if cached_dataset is not None:
            return cached_dataset

        cached_scope = _get_indicador_cache(_INDICADOR_SCOPE_BASE_CACHE, scope_cache_key)

    if cached_scope is not None:
        scope_base, perfil_df = cached_scope
    else:
        scope_base, perfil_df = _build_indicador_scope_base(**filters)
        with _INDICADOR_CACHE_LOCK:
            _put_indicador_cache(
                _INDICADOR_SCOPE_BASE_CACHE,
                scope_cache_key,
                (scope_base, perfil_df),
                generation,
            )

    result = _build_indicador_dataset(
        indicador,
        scope_base,
        perfil_df,
        data_inicio=data_inicio,
        data_fim=data_fim,
    )

    with _INDICADOR_CACHE_LOCK:
        _put_indicador_cache(_INDICADOR_DATASET_CACHE, dataset_cache_key, result, generation)

    return result


def _build_indicador_cnpj_rows(
    df: pl.DataFrame,
    c_val: str,
    c_mr: str,
    rr_col: str | None,
    score_col: str,
    indicador: str | None = None,
) -> list[IndicadorCnpjRowSchema]:
    rows: list[IndicadorCnpjRowSchema] = []
    for row in df.iter_rows(named=True):
        is_matriz = row["is_matriz"]
        if is_matriz is None:
            raise ValueError("Campo obrigatorio is_matriz ausente para CNPJ em indicadores.")

        rows.append(IndicadorCnpjRowSchema(
            cnpj=str(row["cnpj"]),
            razao_social=row.get("razao_social"),
            municipio=str(row["no_municipio"]).title() if row.get("no_municipio") else None,
            uf=row.get("uf"),
            id_ibge7=int(row["id_ibge7"]) if row.get("id_ibge7") is not None else None,
            valor=_optional_float(row.get(c_val)),
            med_reg=_optional_float(row.get(c_mr)),
            med_benchmark=_optional_float(row.get("med_benchmark")),
            benchmark_escopo=row.get("benchmark_escopo"),
            risco_reg=_optional_float(row.get(rr_col)) if rr_col else None,
            risco_benchmark=_optional_float(row.get("risco_benchmark")),
            status=row.get("status", "SEM DADOS"),
            is_matriz=bool(is_matriz),
            is_grande_rede=bool(row.get("is_grande_rede", False)),
            qtd_estabelecimentos_rede=int(row["qtd_estabelecimentos_rede"]),
            situacao_rf=row.get("situacao_rf"),
            is_conexao_ativa=bool(row.get("is_conexao_ativa", False)),
            score_risco_final=_optional_float(row.get(score_col)) if score_col in df.columns else None,
            valor_movimentado=_optional_float(row.get("total_vendas")),
            val_sem_comp=_optional_float(row.get("total_sem_comprovacao")),
            perc_val_sem_comp=_optional_float(row.get("perc_val_sem_comp")),
            detalhes_extras={
                k: row.get(k)
                for k in _INDICADOR_EXTRA_COLS.get(indicador, [])
            } if indicador else None,
        ))
    return rows


def _build_status_kpis(df: pl.DataFrame) -> IndicadorKpiSummarySchema:
    if df.is_empty():
        return IndicadorKpiSummarySchema()
    status_counts = df["status"].value_counts().to_dicts()
    counts = {r["status"]: r["count"] for r in status_counts}
    total_mov = _optional_float(df.select(pl.col("total_vendas").sum()).item()) or 0.0
    total_sem_comprovacao = _optional_float(df.select(pl.col("total_sem_comprovacao").sum()).item()) or 0.0
    perc_sem_comprovacao = (
        round((total_sem_comprovacao / total_mov) * 100, 2)
        if total_mov > 0
        else None
    )
    total_com_dados = counts.get("CRÍTICO", 0) + counts.get("ATENÇÃO", 0) + counts.get("NORMAL", 0)
    pct_acima_limiar = (
        (counts.get("CRÍTICO", 0) + counts.get("ATENÇÃO", 0)) / total_com_dados * 100
        if total_com_dados > 0 else None
    )
    return IndicadorKpiSummarySchema(
        total_critico=counts.get("CRÍTICO", 0),
        total_atencao=counts.get("ATENÇÃO", 0),
        total_normal=counts.get("NORMAL", 0),
        total_sem_dados=counts.get("SEM DADOS", 0),
        total_mov=total_mov,
        total_sem_comprovacao=total_sem_comprovacao,
        perc_sem_comprovacao=perc_sem_comprovacao,
        pct_acima_limiar=round(pct_acima_limiar, 2) if pct_acima_limiar is not None else None,
    )


def get_indicador_benchmark_local(
    cnpj: str,
    indicador: str,
    data_inicio: date | None = None,
    data_fim: date | None = None,
) -> IndicadorBenchmarkResponse:
    clean_cnpj = str(cnpj or "").replace(".", "").replace("/", "").replace("-", "")
    if len(clean_cnpj) != 14:
        raise HTTPException(status_code=422, detail="CNPJ deve conter 14 digitos.")
    if indicador not in _INDICADOR_BENCHMARK_LOCAL_KEYS:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Indicador '{indicador}' nao possui benchmark local generico. "
                f"Valores aceitos: {sorted(_INDICADOR_BENCHMARK_LOCAL_KEYS)}"
            ),
        )

    value_col, med_reg_col, med_uf_col, _med_br_col, risco_reg_col, risco_uf_col, _risco_br_col = INDICATOR_MAPPING[indicador]
    display_value_col = _INDICADOR_DISPLAY_VALUE_COLS.get(indicador, value_col)
    display_med_reg_col = "_display_med_regiao" if display_value_col != value_col else med_reg_col
    display_med_uf_col = "_display_med_uf" if display_value_col != value_col else med_uf_col
    atencao_col, critico_col = _INDICATOR_FLAGS[indicador]
    valor_financeiro_col = _INDICADOR_VALOR_FINANCEIRO_COLS.get(indicador)

    perfil = get_df_perfil_estabelecimento()
    perfil_required = [
        "id_cnpj",
        "cnpj",
        "razao_social",
        "no_municipio",
        "uf",
        "id_ibge7",
        "id_regiao_saude",
        "is_conexao_ativa",
        "is_matriz",
    ]
    _require_columns(perfil, perfil_required, "perfil_estabelecimento")

    perfil_target = perfil.filter(pl.col("cnpj") == clean_cnpj).select(perfil_required)
    if perfil_target.is_empty():
        raise HTTPException(status_code=404, detail="CNPJ nao encontrado no perfil de estabelecimentos.")

    target_perfil = perfil_target.row(0, named=True)
    if target_perfil.get("id_ibge7") is None or target_perfil.get("id_regiao_saude") is None:
        raise RuntimeError("Perfil do CNPJ alvo sem id_ibge7/id_regiao_saude obrigatorios.")

    matriz = _build_dynamic_matriz_risco(data_inicio=data_inicio, data_fim=data_fim)
    matriz_required = [
        "id_cnpj",
        "valor_total_vendas",
        "valor_sem_comprovacao",
        value_col,
        med_reg_col,
        med_uf_col,
        risco_reg_col,
        risco_uf_col,
        atencao_col,
        critico_col,
    ]
    if display_value_col not in matriz_required:
        matriz_required.append(display_value_col)
    if valor_financeiro_col is not None and valor_financeiro_col not in matriz_required:
        matriz_required.append(valor_financeiro_col)

    agg_spec = INDICATOR_AGGREGATIONS.get(indicador)
    if agg_spec:
        num_col = str(agg_spec["numerator"])
        den_col = str(agg_spec["denominator"])
        if num_col not in matriz_required:
            matriz_required.append(num_col)
        if den_col not in matriz_required:
            matriz_required.append(den_col)

    _require_columns(matriz, matriz_required, "matriz_risco_dinamica")

    cast_exprs = [
        pl.col("id_regiao_saude").cast(pl.Utf8),
        pl.col("id_ibge7").cast(pl.Int64),
        pl.col(value_col).cast(pl.Float64),
        pl.col(risco_reg_col).cast(pl.Float64),
    ]
    if display_value_col != value_col:
        cast_exprs.append(pl.col(display_value_col).cast(pl.Float64))

    base = (
        matriz.select(matriz_required)
        .join(perfil.select(perfil_required), on="id_cnpj", how="inner")
        .with_columns(cast_exprs)
        .with_columns([
            pl.col(display_value_col).median().over("id_regiao_saude").alias(display_med_reg_col),
            pl.col(display_value_col).median().over("uf").alias(display_med_uf_col),
        ] if display_value_col != value_col else [])
        .sort(
            [display_value_col, risco_reg_col, "cnpj"],
            descending=[True, True, False],
            nulls_last=True,
        )
    )

    target_df = base.filter(pl.col("cnpj") == clean_cnpj)
    if target_df.is_empty():
        raise RuntimeError("Matriz dinamica nao retornou o CNPJ alvo para o benchmark local.")
    target = target_df.row(0, named=True)

    id_ibge7 = int(target["id_ibge7"])
    id_regiao_saude = str(target["id_regiao_saude"])
    municipio_label = f'{target["no_municipio"]}/{target["uf"]}'
    regiao_label = f'Regiao de Saude {id_regiao_saude}/{target["uf"]}'

    municipio_df = base.filter(pl.col("id_ibge7") == id_ibge7)
    regiao_df = base.filter(pl.col("id_regiao_saude") == id_regiao_saude)

    return IndicadorBenchmarkResponse(
        cnpj=clean_cnpj,
        indicador=indicador,
        periodo_inicio=data_inicio,
        periodo_fim=data_fim,
        kpis=_indicador_benchmark_kpis(
            target,
            indicador=indicador,
            value_col=display_value_col,
            med_reg_col=display_med_reg_col,
            med_uf_col=display_med_uf_col,
            risco_reg_col=risco_reg_col,
            risco_uf_col=risco_uf_col,
        ),
        municipio=_indicador_benchmark_scope_schema(
            escopo="municipio",
            label=municipio_label,
            rows_df=municipio_df,
            cnpj_alvo=clean_cnpj,
            indicador=indicador,
            value_col=display_value_col,
            med_reg_col=display_med_reg_col,
            med_uf_col=display_med_uf_col,
            risco_reg_col=risco_reg_col,
            risco_uf_col=risco_uf_col,
            atencao_col=atencao_col,
            critico_col=critico_col,
            status_value_col=value_col,
        ),
        regiao_saude=_indicador_benchmark_scope_schema(
            escopo="regiao_saude",
            label=regiao_label,
            rows_df=regiao_df,
            cnpj_alvo=clean_cnpj,
            indicador=indicador,
            value_col=display_value_col,
            med_reg_col=display_med_reg_col,
            med_uf_col=display_med_uf_col,
            risco_reg_col=risco_reg_col,
            risco_uf_col=risco_uf_col,
            atencao_col=atencao_col,
            critico_col=critico_col,
            status_value_col=value_col,
        ),
    )


def _indicador_periodo_marcado(
    data_inicio: date | None,
    data_fim: date | None,
) -> IndicadorEvolucaoBenchmarkPeriodoSchema:
    ano_inicio = data_inicio.year if data_inicio else None
    ano_fim = data_fim.year if data_fim else None
    if ano_inicio is not None and ano_fim is not None and ano_inicio > ano_fim:
        ano_inicio, ano_fim = ano_fim, ano_inicio

    anos: list[int] = []
    if ano_inicio is not None and ano_fim is not None:
        anos = list(range(ano_inicio, ano_fim + 1))
    elif ano_inicio is not None:
        anos = [ano_inicio]
        ano_fim = ano_inicio
    elif ano_fim is not None:
        anos = [ano_fim]
        ano_inicio = ano_fim

    return IndicadorEvolucaoBenchmarkPeriodoSchema(
        ano_inicio=ano_inicio,
        ano_fim=ano_fim,
        anos=anos,
    )


def get_indicador_evolucao_benchmark(
    cnpj: str,
    indicador: str,
    data_inicio: date | None = None,
    data_fim: date | None = None,
) -> IndicadorEvolucaoBenchmarkResponse:
    clean_cnpj = str(cnpj or "").replace(".", "").replace("/", "").replace("-", "")
    if len(clean_cnpj) != 14:
        raise HTTPException(status_code=422, detail="CNPJ deve conter 14 digitos.")
    if indicador not in _INDICADOR_BENCHMARK_LOCAL_KEYS:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Indicador '{indicador}' nao possui evolucao anual generica. "
                f"Valores aceitos: {sorted(_INDICADOR_BENCHMARK_LOCAL_KEYS)}"
            ),
        )

    value_col, med_reg_col, med_uf_col, med_br_col, risco_reg_col, risco_uf_col = INDICATOR_MAPPING[indicador][:6]
    display_value_col = _INDICADOR_DISPLAY_VALUE_COLS.get(indicador, value_col)
    display_med_reg_col = "_display_med_regiao" if display_value_col != value_col else med_reg_col
    display_med_uf_col = "_display_med_uf" if display_value_col != value_col else med_uf_col
    formato = _INDICADOR_BENCHMARK_FORMATOS[indicador]

    perfil = get_df_perfil_estabelecimento()
    perfil_required = ["id_cnpj", "cnpj", "uf", "id_regiao_saude"]
    _require_columns(perfil, perfil_required, "perfil_estabelecimento")

    target_perfil = perfil.filter(pl.col("cnpj") == clean_cnpj).select(perfil_required)
    if target_perfil.is_empty():
        raise HTTPException(status_code=404, detail="CNPJ nao encontrado no perfil de estabelecimentos.")

    id_cnpj_value = target_perfil.row(0, named=True).get("id_cnpj")
    if id_cnpj_value is None:
        raise RuntimeError("Perfil do CNPJ alvo sem id_cnpj obrigatorio.")

    matriz = build_annual_indicator_benchmark_matriz()
    matriz_required = [
        "id_cnpj",
        "ano_base",
        value_col,
        med_reg_col,
        med_uf_col,
        "valor_total_vendas",
        "valor_sem_comprovacao",
    ]
    if display_value_col not in matriz_required:
        matriz_required.append(display_value_col)
    if display_value_col != value_col:
        for context_col in ("id_regiao_saude", "uf"):
            if context_col not in matriz_required:
                matriz_required.append(context_col)
    
    agg_spec = INDICATOR_AGGREGATIONS.get(indicador)
    num_col = None
    den_col = None
    if agg_spec:
        num_col = str(agg_spec["numerator"])
        den_col = str(agg_spec["denominator"])
        if num_col not in matriz_required:
            matriz_required.append(num_col)
        if den_col not in matriz_required:
            matriz_required.append(den_col)
    if indicador == "volume_atipico":
        num_col = "volume_atipico_valor_aumento_atipico"
        den_col = None
        if num_col not in matriz_required:
            matriz_required.append(num_col)

    _require_columns(matriz, matriz_required, "matriz_risco_anual")

    target_info = target_perfil.row(0, named=True)
    target_uf = target_info.get("uf")
    target_regiao = target_info.get("id_regiao_saude")
    if display_value_col != value_col and (target_uf is None or target_regiao is None):
        raise RuntimeError("Perfil do CNPJ alvo sem uf/id_regiao_saude para evolucao anual.")

    matriz_base = matriz
    if display_value_col != value_col:
        matriz_base = matriz_base.with_columns([
            pl.col("id_regiao_saude").cast(pl.Utf8),
            pl.col("uf").cast(pl.Utf8),
            pl.col(display_value_col).cast(pl.Float64),
        ]).with_columns([
            pl.col(display_value_col).median().over(["ano_base", "id_regiao_saude"]).alias(display_med_reg_col),
            pl.col(display_value_col).median().over(["ano_base", "uf"]).alias(display_med_uf_col),
        ])
        if display_med_reg_col not in matriz_required:
            matriz_required.append(display_med_reg_col)
        if display_med_uf_col not in matriz_required:
            matriz_required.append(display_med_uf_col)

    serie_df = (
        matriz_base
        .filter(pl.col("id_cnpj") == int(id_cnpj_value))
        .select(matriz_required)
        .with_columns([
            pl.col("ano_base").cast(pl.Int64),
            pl.col(display_value_col).cast(pl.Float64),
            pl.col(display_med_reg_col).cast(pl.Float64),
            pl.col(display_med_uf_col).cast(pl.Float64),
        ])
        .sort("ano_base")
    )

    if serie_df.is_empty():
        raise RuntimeError("Matriz de risco anual nao possui serie para o CNPJ alvo.")

    series = [
        IndicadorEvolucaoBenchmarkPointSchema(
            ano_base=int(row["ano_base"]),
            farmacia=_optional_float(row.get(display_value_col)),
            regiao_saude=_optional_float(row.get(display_med_reg_col)),
            uf=_optional_float(row.get(display_med_uf_col)),
            valor_numerador=_optional_float(row.get(num_col)) if num_col and num_col in row else None,
            valor_denominador=_optional_float(row.get(den_col)) if den_col and den_col in row else None,
            valor_movimentado=_optional_float(row.get("valor_total_vendas")),
            valor_sem_comprovacao=_optional_float(row.get("valor_sem_comprovacao")),
            percentual_nao_comprovacao=(
                round((float(row["valor_sem_comprovacao"]) / float(row["valor_total_vendas"])) * 100, 2)
                if row.get("valor_total_vendas") is not None
                and row.get("valor_sem_comprovacao") is not None
                and float(row["valor_total_vendas"]) > 0
                else None
            ),
        )
        for row in serie_df.to_dicts()
    ]

    return IndicadorEvolucaoBenchmarkResponse(
        cnpj=clean_cnpj,
        indicador=indicador,
        formato=formato,
        periodo_inicio=data_inicio,
        periodo_fim=data_fim,
        periodo_marcado=_indicador_periodo_marcado(data_inicio, data_fim),
        series=series,
    )


def _normalizar_sort_order(sort_order: str | int | None) -> tuple[str, bool]:
    raw = str(sort_order or "desc").lower()
    descending = raw in {"desc", "descending", "-1"}
    return ("desc" if descending else "asc"), descending


def get_indicadores_analise(
    indicador: str,
    data_inicio: date | None = None,
    data_fim: date | None = None,
    uf: str | None = None,
    regiao_saude: str | None = None,
    municipio: str | None = None,
    situacao_rf: str | None = None,
    conexao_ms: str | None = None,
    porte_empresa: str | None = None,
    grande_rede: str | None = None,
    cnpj_raiz: str | None = None,
    estabelecimento: str | None = None,
    unidade_pf: str | None = None,
    perc_min: float | None = None,
    perc_max: float | None = None,
    val_min: float | None = None,
    regiao_id: int | None = None,
    id_ibge7: int | None = None,
    par_teia: str | None = None,
    socio_beneficio: str | None = None,
    socio_esocial: str | None = None,
    dispersao_uf_sem_fronteira: bool = False,
    dispersao_uf_sem_fronteira_limite: float | None = None,
    volume_atipico: bool = False,
    volume_atipico_limite: float | None = None,
    cnae_incompativel: bool = False,
    socio_idade_atipica: bool = False,
    socio_falecido: bool = False,
) -> IndicadorAnaliseResponse:
    """
    Análise cruzada de um indicador de risco: retorna KPIs, mapa municipal
    filtrados pelo escopo geográfico.

    Operação 100% em memória (Polars) sobre df_matriz_risco + df_movimentacao.
    O período e o aumento semestral atípico filtram o universo de CNPJs da movimentação;
    a métrica do indicador vem da matriz_risco consolidada.

    Args:
        indicador: Chave do indicador (ex: 'auditado', 'teto'). Deve existir em INDICATOR_MAPPING.
        uf: Sigla da UF ou None.
        regiao_saude: Nome da Região de Saúde ou None.
        municipio: Nome do município ou None.
        situacao_rf: Situação na Receita Federal ou None.
        conexao_ms: 'Ativa' | 'Inativa' | None.
        porte_empresa: Porte CNPJ ou None.
        grande_rede: 'Sim' | 'Não' | None.
        cnpj_raiz: 8 ou 14 dígitos ou None.
        unidade_pf: Nome da Unidade PF ou None.
        perc_min: Limiar mínimo de não comprovação (%)
        perc_max: Limiar máximo de não comprovação (%)
        val_min: Valor bruto mínimo sem comprovação (R$)

    Returns:
        IndicadorAnaliseResponse com kpis e municipios.

    Raises:
        HTTPException 400 se a chave do indicador for inválida.
    """
    if indicador not in INDICATOR_MAPPING:
        raise HTTPException(
            status_code=400,
            detail=f"Indicador '{indicador}' inválido. Valores aceitos: {sorted(INDICATOR_MAPPING.keys())}"
        )

    try:
        df_joined, perfil_df, df_risco, c_val, _c_mr, rr_col, _score_col = _build_indicador_dataset_cached(
            indicador,
            data_inicio=data_inicio,
            data_fim=data_fim,
            uf=uf,
            situacao_rf=situacao_rf,
            conexao_ms=conexao_ms,
            porte_empresa=porte_empresa,
            grande_rede=grande_rede,
            cnpj_raiz=cnpj_raiz,
            estabelecimento=estabelecimento,
            unidade_pf=unidade_pf,
            perc_min=perc_min,
            perc_max=perc_max,
            val_min=val_min,
            regiao_id=regiao_id,
            id_ibge7=id_ibge7,
            par_teia=par_teia,
            socio_beneficio=socio_beneficio,
            socio_esocial=socio_esocial,
            cnae_incompativel=cnae_incompativel,
            socio_idade_atipica=socio_idade_atipica,
            socio_falecido=socio_falecido,
            dispersao_uf_sem_fronteira=dispersao_uf_sem_fronteira,
            dispersao_uf_sem_fronteira_limite=dispersao_uf_sem_fronteira_limite,
            volume_atipico=volume_atipico,
            volume_atipico_limite=volume_atipico_limite,
        )

        if df_joined.is_empty():
            empty_kpis = IndicadorKpiSummarySchema()
            return IndicadorAnaliseResponse(indicador=indicador, kpis=empty_kpis, municipios=[])

        if rr_col is None:
            raise RuntimeError(f"Coluna de risco regional obrigatoria ausente para indicador '{indicador}'.")

        # ── 6. Agregação por município para o mapa ──
        mun_agg = (
            df_joined
            .group_by(["no_municipio", "uf", "id_ibge7"])
            .agg([
                pl.len().alias("total_cnpjs"),
                (pl.col("status") == "CRÍTICO").sum().alias("total_critico"),
            ])
            .with_columns([
                (
                    pl.col("total_critico").cast(pl.Float64) /
                    pl.when(pl.col("total_cnpjs") > 0)
                    .then(pl.col("total_cnpjs").cast(pl.Float64))
                    .otherwise(pl.lit(1.0)) * 100
                ).round(2).alias("pct_critico")
            ])
            .sort("pct_critico", descending=True)
        )

        municipios_list: list[IndicadorMunicipioRowSchema] = []
        for row in mun_agg.iter_rows(named=True):
            municipios_list.append(IndicadorMunicipioRowSchema(
                municipio=str(row["no_municipio"]).title() if row.get("no_municipio") else "",
                uf=row.get("uf"),
                id_ibge7=int(row["id_ibge7"]) if row.get("id_ibge7") is not None else None,
                total_cnpjs=int(row["total_cnpjs"] or 0),
                total_critico=int(row["total_critico"] or 0),
                pct_critico=_optional_float(row.get("pct_critico")) or 0.0,
            ))

        # ── 7. KPIs de resumo com Contexto Regional de Benchmarking ──
        status_counts = df_joined["status"].value_counts().to_dicts()
        counts = {r["status"]: r["count"] for r in status_counts}

        total_com_dados = counts.get("CRÍTICO", 0) + counts.get("ATENÇÃO", 0) + counts.get("NORMAL", 0)
        pct_acima_limiar = (
            (counts.get("CRÍTICO", 0) + counts.get("ATENÇÃO", 0)) / total_com_dados * 100
            if total_com_dados > 0 else None
        )

        # Identifica a Região de Saúde de referência (mesmo se filtro for municipal)
        context_regiao_id = str(regiao_id) if regiao_id is not None else None
        if context_regiao_id is None and id_ibge7 is not None:
            sample = df_joined.select("id_regiao_saude").unique().limit(1)
            if not sample.is_empty():
                context_regiao_id = str(sample.item(0, 0))

        # Cálculo de Mediana/MAD sobre o CONTEXTO (UF + opcionalmente Região de Saúde)
        context_mask = pl.lit(True)
        if uf and uf != 'Todos':
            context_mask = context_mask & (pl.col("uf") == uf)
        if context_regiao_id is not None:
            context_mask = context_mask & (pl.col("id_regiao_saude") == context_regiao_id)

        # Buscamos a mediana e MAD do indicador para o contexto regional completo
        mediana_reg = None
        mad_reg = None
        # Perfil contém todos os CNPJs com geografia; filtramos os do contexto por id_cnpj.
        df_context_geo = perfil_df.select(["id_cnpj", "uf", "id_regiao_saude"]).filter(context_mask)
        
        df_context = df_context_geo.join(df_risco.select(["id_cnpj", c_val, rr_col]), on="id_cnpj", how="inner")
        
        if not df_context.is_empty():
            s_valores = df_context.select(c_val).drop_nulls().to_series().sort()
            s_riscos = df_context.select(rr_col).drop_nulls().to_series().sort()
            
            if not s_valores.is_empty():
                mediana_reg = _optional_float(s_valores.median()) or 0.0
            
            if not s_riscos.is_empty():
                # Para o MAD/Z-Score, usamos os scores (ratios) onde a mediana teórica é 1.0
                m_r = _optional_float(s_riscos.median()) or 1.0
                mad_reg = _optional_float((s_riscos - m_r).abs().median()) or 0.0001

        kpis = IndicadorKpiSummarySchema(
            total_critico=counts.get("CRÍTICO", 0),
            total_atencao=counts.get("ATENÇÃO", 0),
            total_normal=counts.get("NORMAL", 0),
            total_sem_dados=counts.get("SEM DADOS", 0),
            mediana_reg=mediana_reg,
            mad_reg=mad_reg,
            pct_acima_limiar=round(pct_acima_limiar, 2) if pct_acima_limiar is not None else None,
            limiar_atencao=None,
            limiar_critico=None
        )

        return IndicadorAnaliseResponse(
            indicador=indicador,
            kpis=kpis,
            municipios=municipios_list,
        )

    except HTTPException:
        raise
    except Exception as e:
        import traceback
        print(f"❌ ERRO EM get_indicadores_analise (indicador={indicador}): {e}")
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail="Erro interno ao processar análise de indicadores.")

def get_indicadores_analise_cnpjs(
    indicador: str,
    data_inicio: date | None = None,
    data_fim: date | None = None,
    uf: str | None = None,
    regiao_saude: str | None = None,
    municipio: str | None = None,
    situacao_rf: str | None = None,
    conexao_ms: str | None = None,
    porte_empresa: str | None = None,
    grande_rede: str | None = None,
    cnpj_raiz: str | None = None,
    estabelecimento: str | None = None,
    unidade_pf: str | None = None,
    perc_min: float | None = None,
    perc_max: float | None = None,
    val_min: float | None = None,
    regiao_id: int | None = None,
    id_ibge7: int | None = None,
    par_teia: str | None = None,
    socio_beneficio: str | None = None,
    socio_esocial: str | None = None,
    dispersao_uf_sem_fronteira: bool = False,
    dispersao_uf_sem_fronteira_limite: float | None = None,
    volume_atipico: bool = False,
    volume_atipico_limite: float | None = None,
    cnae_incompativel: bool = False,
    socio_idade_atipica: bool = False,
    socio_falecido: bool = False,
    page: int = 1,
    page_size: int = 20,
    sort_field: str = "val_sem_comp",
    sort_order: str | int | None = "desc",
) -> IndicadorCnpjPageResponse:
    try:
        df_joined, _perfil_df, _df_risco, c_val, c_mr, rr_col, score_col = _build_indicador_dataset_cached(
            indicador,
            data_inicio=data_inicio,
            data_fim=data_fim,
            uf=uf,
            situacao_rf=situacao_rf,
            conexao_ms=conexao_ms,
            porte_empresa=porte_empresa,
            grande_rede=grande_rede,
            cnpj_raiz=cnpj_raiz,
            estabelecimento=estabelecimento,
            unidade_pf=unidade_pf,
            perc_min=perc_min,
            perc_max=perc_max,
            val_min=val_min,
            regiao_id=regiao_id,
            id_ibge7=id_ibge7,
            par_teia=par_teia,
            socio_beneficio=socio_beneficio,
            socio_esocial=socio_esocial,
            cnae_incompativel=cnae_incompativel,
            socio_idade_atipica=socio_idade_atipica,
            socio_falecido=socio_falecido,
            dispersao_uf_sem_fronteira=dispersao_uf_sem_fronteira,
            dispersao_uf_sem_fronteira_limite=dispersao_uf_sem_fronteira_limite,
            volume_atipico=volume_atipico,
            volume_atipico_limite=volume_atipico_limite,
        )

        normalized_order, descending = _normalizar_sort_order(sort_order)
        page = max(1, int(page or 1))
        page_size = min(200, max(1, int(page_size or 20)))

        if df_joined.is_empty():
            return IndicadorCnpjPageResponse(
                indicador=indicador,
                items=[],
                kpis=IndicadorKpiSummarySchema(),
                total=0,
                page=page,
                page_size=page_size,
                sort_field=sort_field,
                sort_order=normalized_order,
            )

        # Para indicadores com coluna de exibição distinta (ex: volume_atipico usa valor monetário),
        # substituir c_val pelo display col na construção das rows e ordenação
        display_c_val = _INDICADOR_DISPLAY_VALUE_COLS.get(indicador, c_val)

        sort_columns = {
            "cnpj": "cnpj",
            "razao_social": "razao_social",
            "municipio": "no_municipio",
            "uf": "uf",
            "valor": display_c_val,
            "med_reg": c_mr,
            "risco_reg": "risco_benchmark",
            "risco_benchmark": "risco_benchmark",
            "status": "status",
            "is_matriz": "is_matriz",
            "is_conexao_ativa": "is_conexao_ativa",
            "situacao_rf": "situacao_rf",
            "score_risco_final": score_col,
            "valor_movimentado": "total_vendas",
            "val_sem_comp": "total_sem_comprovacao",
            "perc_val_sem_comp": "perc_val_sem_comp",
            "pct_dispersao_uf_nao_vizinha": "pct_dispersao_uf_nao_vizinha",
        }
        sort_col = sort_columns.get(sort_field) or rr_col or "cnpj"
        if sort_col not in df_joined.columns:
            raise HTTPException(status_code=400, detail=f"Campo de ordenacao invalido: {sort_field}")

        total = df_joined.height
        offset = (page - 1) * page_size
        df_page = (
            df_joined
            .sort(sort_col, descending=descending, nulls_last=True)
            .slice(offset, page_size)
        )

        if display_c_val != c_val and display_c_val not in df_page.columns:
            raise RuntimeError(
                f"Coluna de display obrigatoria ausente para indicador '{indicador}': {display_c_val}"
            )

        return IndicadorCnpjPageResponse(
            indicador=indicador,
            items=_build_indicador_cnpj_rows(df_page, display_c_val, c_mr, rr_col, score_col, indicador),
            kpis=_build_status_kpis(df_joined),
            total=total,
            page=page,
            page_size=page_size,
            sort_field=sort_field,
            sort_order=normalized_order,
        )

    except HTTPException:
        raise
    except Exception as e:
        import traceback
        print(f"ERRO EM get_indicadores_analise_cnpjs (indicador={indicador}): {e}")
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail="Erro interno ao paginar CNPJs do indicador.")

