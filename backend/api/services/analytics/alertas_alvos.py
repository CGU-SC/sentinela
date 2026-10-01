from datetime import date
from typing import Optional

import polars as pl
from fastapi import HTTPException

from data_cache import (
    get_df_dados_socios,
    get_localidades_df,
    scan_crm_concentracao_multiplo_alertas_global,
    scan_crm_concentracao_unico_alertas_global,
)
from .cache_geracao import CacheGeracao
from .filtros_farmacia import FiltrosFarmacia
from .par_teia import apply_par_teia_filter as _apply_par_teia_filter
from .volume_atipico import get_volume_atipico_id_cnpjs_df


SOCIO_BENEFICIO_SCOPES = {
    "direto",
    "n3",
    "direto_n3",
}


SOCIO_BENEFICIO_REQUIRED_COLUMNS = {
    "has_cadunico_direto",
    "has_cadunico_n3",
    "has_seguro_defeso_direto",
    "has_seguro_defeso_n3",
}

SOCIO_ESOCIAL_SCOPES = {
    "direto",
    "n3",
    "direto_n3",
}

SOCIO_ESOCIAL_REQUIRED_COLUMNS = {
    "has_esocial_direto",
    "has_esocial_n3",
}


def _socio_beneficio_scope_expr(scope: str) -> pl.Expr:
    if scope == "direto":
        return pl.col("has_cadunico_direto") | pl.col("has_seguro_defeso_direto")
    if scope == "n3":
        return pl.col("has_cadunico_n3") | pl.col("has_seguro_defeso_n3")
    if scope == "direto_n3":
        return (
            pl.col("has_cadunico_direto")
            | pl.col("has_seguro_defeso_direto")
            | pl.col("has_cadunico_n3")
            | pl.col("has_seguro_defeso_n3")
        )
    raise HTTPException(
        status_code=400,
        detail=(
            f"Filtro socio_beneficio invalido: {scope}. "
            f"Valores aceitos: {sorted(SOCIO_BENEFICIO_SCOPES)}"
        ),
    )


def _socio_esocial_scope_expr(scope: str) -> pl.Expr:
    if scope == "direto":
        return pl.col("has_esocial_direto")
    if scope == "n3":
        return pl.col("has_esocial_n3")
    if scope == "direto_n3":
        return pl.col("has_esocial_direto") | pl.col("has_esocial_n3")
    raise HTTPException(
        status_code=400,
        detail=(
            f"Filtro socio_esocial invalido: {scope}. "
            f"Valores aceitos: {sorted(SOCIO_ESOCIAL_SCOPES)}"
        ),
    )


def apply_socio_beneficio_filter(
    df: pl.DataFrame,
    socio_beneficio: Optional[str],
) -> pl.DataFrame:
    if not socio_beneficio or socio_beneficio == "Todos":
        return df

    missing_columns = SOCIO_BENEFICIO_REQUIRED_COLUMNS - set(df.columns)
    if missing_columns:
        raise HTTPException(
            status_code=500,
            detail=(
                "Filtro socio_beneficio exige colunas no perfil do estabelecimento: "
                + ", ".join(sorted(missing_columns))
            ),
        )

    scope = socio_beneficio.strip().lower()
    filter_expr = _socio_beneficio_scope_expr(scope)
    return df.filter(filter_expr)


def apply_cnae_incompativel_filter(
    df: pl.DataFrame,
    cnae_incompativel: bool,
) -> pl.DataFrame:
    if not cnae_incompativel:
        return df
    if "is_cnae_incompativel_farmaceutico" not in df.columns:
        raise HTTPException(
            status_code=500,
            detail="Filtro cnae_incompativel exige coluna is_cnae_incompativel_farmaceutico no perfil do estabelecimento.",
        )
    return df.filter(pl.col("is_cnae_incompativel_farmaceutico") != 0)


def apply_socio_idade_atipica_filter(
    df: pl.DataFrame,
    socio_idade_atipica: bool,
    data_referencia: Optional[date] = None,
) -> pl.DataFrame:
    """
    Filtra o perfil para CNPJs com ao menos um sócio PF ativo (sem data de
    exclusao) cuja idade na `data_referencia` esteja fora de [21, 80] anos.

    A idade e calculada on-demand a partir de `dados_socios` para evitar
    inconsistência quando um socio cruza a fronteira dos 21 ou 80 anos
    depois que o Parquet foi gerado.
    """
    if not socio_idade_atipica:
        return df
    if "cnpj" not in df.columns:
        raise HTTPException(
            status_code=500,
            detail="Filtro socio_idade_atipica exige coluna 'cnpj' no perfil do estabelecimento.",
        )

    socios = get_df_dados_socios()
    required = {"cnpj", "indicador_socio", "data_exclusao_sociedade", "data_nascimento_socio"}
    if not required.issubset(set(socios.columns)):
        raise HTTPException(
            status_code=500,
            detail=(
                "Filtro socio_idade_atipica exige colunas em dados_socios: "
                + ", ".join(sorted(required - set(socios.columns)))
            ),
        )

    ref = data_referencia or date.today()
    idade_expr = (pl.lit(ref) - pl.col("data_nascimento_socio")).dt.total_days() / 365.25

    cnpjs_idade_atipica = (
        socios
        .filter(
            (pl.col("indicador_socio") == "PF")
            & pl.col("data_exclusao_sociedade").is_null()
            & pl.col("data_nascimento_socio").is_not_null()
        )
        .with_columns(idade_expr.alias("idade_anos"))
        .filter((pl.col("idade_anos") < 21) | (pl.col("idade_anos") > 80))
        .select("cnpj")
        .unique()
    )
    return df.join(cnpjs_idade_atipica, on="cnpj", how="semi")


def apply_populacao_municipio_filter(
    df: pl.DataFrame,
    populacao_min: Optional[int],
    populacao_max: Optional[int],
) -> pl.DataFrame:
    """
    Filtra o perfil para farmacias de municipios com populacao na faixa
    [populacao_min, populacao_max] (inclusiva; None = sem limite). A populacao
    vem do cadastro de localidades (IBGE, `dados_ibge.nu_populacao`), pelo
    `id_ibge7` da farmacia.

    Raises:
        HTTPException 422: faixa negativa ou minimo maior que maximo.
        HTTPException 503: localidades sem populacao, ou farmacia em municipio
            ausente do cadastro de localidades (o filtro nao pode avaliar).
    """
    if populacao_min is None and populacao_max is None:
        return df
    if any(v is not None and v < 0 for v in (populacao_min, populacao_max)):
        raise HTTPException(status_code=422, detail="Faixa de populacao do municipio nao pode ser negativa.")
    if populacao_min is not None and populacao_max is not None and populacao_min > populacao_max:
        raise HTTPException(status_code=422, detail="Faixa de populacao do municipio: minimo maior que maximo.")
    if "id_ibge7" not in df.columns:
        raise HTTPException(
            status_code=500,
            detail="Filtro de populacao exige coluna 'id_ibge7' no perfil do estabelecimento.",
        )

    localidades = get_localidades_df()
    faltando = {"id_ibge7", "nu_populacao"} - set(localidades.columns)
    if faltando:
        raise HTTPException(
            status_code=503,
            detail=f"Localidades sem colunas para o filtro de populacao: {', '.join(sorted(faltando))}.",
        )
    populacao = localidades.select([
        pl.col("id_ibge7").cast(pl.Int64),
        pl.col("nu_populacao").cast(pl.Int64),
    ]).unique("id_ibge7")
    if populacao.get_column("nu_populacao").null_count():
        raise HTTPException(status_code=503, detail="Localidades com municipio sem populacao (nu_populacao nulo).")

    farmacias = df.select(pl.col("id_ibge7").cast(pl.Int64)).unique()
    sem_cadastro = farmacias.join(populacao, on="id_ibge7", how="anti")
    if sem_cadastro.height:
        raise HTTPException(
            status_code=503,
            detail=(
                "Farmacias em municipios ausentes do cadastro de localidades (id_ibge7: "
                + ", ".join(str(v) for v in sem_cadastro.get_column("id_ibge7").head(5).to_list())
                + "). Sincronize localidades."
            ),
        )

    condicao = pl.lit(True)
    if populacao_min is not None:
        condicao &= pl.col("nu_populacao") >= populacao_min
    if populacao_max is not None:
        condicao &= pl.col("nu_populacao") <= populacao_max
    municipios = populacao.filter(condicao).select("id_ibge7")
    return df.filter(pl.col("id_ibge7").cast(pl.Int64).is_in(municipios.get_column("id_ibge7")))


# Severidade dos alertas de sequencia (unico e multiplos CRMs): 1 alta, 2 grave,
# 3 critica, 4 extrema. Fonte unica (tambem usada pelos filtros de medico).
SEVERIDADES_SEQUENCIA = frozenset({1, 2, 3, 4})
# Tabelas de alertas por tipo de sequencia; "qualquer" une os dias das duas.
TIPOS_SEQUENCIA = {
    "unico": (scan_crm_concentracao_unico_alertas_global,),
    "multiplo": (scan_crm_concentracao_multiplo_alertas_global,),
    "qualquer": (scan_crm_concentracao_unico_alertas_global, scan_crm_concentracao_multiplo_alertas_global),
}


# Dias de sequencia por farmacia: so dependem de (tipo, severidade, meses do
# periodo) e da geracao dos dados. Uma mudanca de filtro dispara 4-5 endpoints em
# paralelo com a mesma chave; o cache calcula uma vez so.
_CACHE_SEQUENCIA = CacheGeracao(max_itens=16)


def _calcular_dias_seq(
    tipo: str, severidade_min: int, competencia_inicio: Optional[int], competencia_fim: Optional[int]
) -> pl.DataFrame:
    """Dias distintos com alerta de severidade >= severidade_min, por farmacia (id_cnpj, _dias_seq)."""
    periodo = pl.lit(True)
    if competencia_inicio is not None:
        periodo &= pl.col("competencia").cast(pl.Int32) >= competencia_inicio
    if competencia_fim is not None:
        periodo &= pl.col("competencia").cast(pl.Int32) <= competencia_fim
    try:
        alertas = pl.concat([
            scan()
            .filter(periodo)
            .select(
                pl.col("id_cnpj").cast(pl.Int64),
                pl.col("dt_alerta").cast(pl.Utf8).str.slice(0, 10).alias("dia"),
                pl.col("id_severidade").cast(pl.Int32),
            )
            .collect()
            for scan in TIPOS_SEQUENCIA[tipo]
        ])
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Alertas de sequencia ({tipo}) indisponiveis: {exc}") from exc
    desconhecidas = set(alertas.get_column("id_severidade").unique().to_list()) - SEVERIDADES_SEQUENCIA
    if desconhecidas:
        raise HTTPException(status_code=503, detail=f"Severidade desconhecida nos alertas de sequencia: {sorted(desconhecidas)}.")
    if alertas.get_column("dia").null_count():
        raise HTTPException(status_code=503, detail="Alerta de sequencia sem dt_alerta.")

    # n_unique dos dias: no tipo "qualquer", dia com alerta nos dois tipos conta uma vez.
    return (
        alertas.filter(pl.col("id_severidade") >= severidade_min)
        .group_by("id_cnpj")
        .agg(pl.col("dia").n_unique().alias("_dias_seq"))
    )


def _dias_seq_por_farmacia(
    tipo: str, severidade_min: int, competencia_inicio: Optional[int], competencia_fim: Optional[int]
) -> pl.DataFrame:
    """Versao em cache de _calcular_dias_seq; erros (422/503) nunca entram no cache."""
    return _CACHE_SEQUENCIA.obter(
        (tipo, severidade_min, competencia_inicio, competencia_fim),
        lambda: _calcular_dias_seq(tipo, severidade_min, competencia_inicio, competencia_fim),
    )


def apply_seq_filter(
    df: pl.DataFrame,
    tipo: Optional[str],
    severidade_min: Optional[int],
    dias_min: Optional[int],
    dias_max: Optional[int],
    periodo_inicio: Optional[date],
    periodo_fim: Optional[date],
) -> pl.DataFrame:
    """
    Filtra o perfil pelas autorizacoes em sequencia da farmacia, no periodo.

    tipo: "unico" (mesmo CRM, crm_concentracao_unico_alertas_global),
    "multiplo" (varios CRMs, crm_concentracao_multiplo_alertas_global) ou
    "qualquer" (uniao dos dias das duas tabelas).
    Dias = datas distintas de dt_alerta, a mesma contagem da Cronologia da aba
    Autorizacoes do CNPJ (e, para multiplos, do KPI da aba).
    So contam os alertas de severidade >= severidade_min (1 alta, 2 grave,
    3 critica, 4 extrema; None = qualquer). Faixa de dias inclusiva; farmacia
    sem alerta tem 0 dias (ausencia na tabela = nenhuma sequencia).
    Severidade sem faixa de dias = pelo menos 1 dia.

    Raises:
        HTTPException 422: tipo ausente/invalido, severidade invalida ou faixa
            de dias invalida.
        HTTPException 503: alertas indisponiveis ou com severidade desconhecida.
    """
    if severidade_min is None and dias_min is None and dias_max is None:
        return df
    if tipo not in TIPOS_SEQUENCIA:
        raise HTTPException(status_code=422, detail="seq_tipo deve ser unico, multiplo ou qualquer quando o filtro de sequencia esta ativo.")
    if severidade_min is not None and severidade_min not in SEVERIDADES_SEQUENCIA:
        raise HTTPException(status_code=422, detail="seq_severidade_min deve ser 1 (alta), 2 (grave), 3 (critica) ou 4 (extrema).")
    if any(v is not None and v < 0 for v in (dias_min, dias_max)):
        raise HTTPException(status_code=422, detail="Faixa de dias de sequencia nao pode ser negativa.")
    if dias_min is not None and dias_max is not None and dias_min > dias_max:
        raise HTTPException(status_code=422, detail="Faixa de dias de sequencia: minimo maior que maximo.")
    if "id_cnpj" not in df.columns:
        raise HTTPException(status_code=500, detail="Filtro de sequencia exige coluna 'id_cnpj' no perfil.")

    competencia_inicio = periodo_inicio.year * 100 + periodo_inicio.month if periodo_inicio is not None else None
    competencia_fim = periodo_fim.year * 100 + periodo_fim.month if periodo_fim is not None else None
    dias_por_farmacia = _dias_seq_por_farmacia(
        tipo, severidade_min or min(SEVERIDADES_SEQUENCIA), competencia_inicio, competencia_fim
    )
    if dias_min is None and dias_max is None:
        dias_min = 1
    condicao = pl.lit(True)
    if dias_min is not None:
        condicao &= pl.col("_dias_seq") >= dias_min
    if dias_max is not None:
        condicao &= pl.col("_dias_seq") <= dias_max
    return (
        df.with_columns(pl.col("id_cnpj").cast(pl.Int64).alias("_id_cnpj_seq"))
        .join(dias_por_farmacia.rename({"id_cnpj": "_id_cnpj_seq"}), on="_id_cnpj_seq", how="left")
        .with_columns(pl.col("_dias_seq").fill_null(0))  # sem alerta = 0 dias
        .filter(condicao)
        .drop(["_id_cnpj_seq", "_dias_seq"])
    )


def apply_socio_falecido_filter(
    df: pl.DataFrame,
    socio_falecido: bool,
) -> pl.DataFrame:
    """
    Filtra o perfil para CNPJs com ao menos um socio PF ativo (sem data
    de exclusao) com `is_falecido == True` em `dados_socios`. A coluna
    `is_falecido` vem do SQL Server (cruza CPF do socio com base de
    obitos) e e espelhada no Parquet global de socios.
    """
    if not socio_falecido:
        return df
    if "cnpj" not in df.columns:
        raise HTTPException(
            status_code=500,
            detail="Filtro socio_falecido exige coluna 'cnpj' no perfil do estabelecimento.",
        )

    socios = get_df_dados_socios()
    required = {"cnpj", "indicador_socio", "data_exclusao_sociedade", "is_falecido"}
    if not required.issubset(set(socios.columns)):
        raise HTTPException(
            status_code=500,
            detail=(
                "Filtro socio_falecido exige colunas em dados_socios: "
                + ", ".join(sorted(required - set(socios.columns)))
            ),
        )

    cnpjs_socio_falecido = (
        socios
        .filter(
            (pl.col("indicador_socio") == "PF")
            & pl.col("data_exclusao_sociedade").is_null()
            & (pl.col("is_falecido") == True)  # noqa: E712
        )
        .select("cnpj")
        .unique()
    )
    return df.join(cnpjs_socio_falecido, on="cnpj", how="semi")


def apply_socio_esocial_filter(
    df: pl.DataFrame,
    socio_esocial: Optional[str],
) -> pl.DataFrame:
    if not socio_esocial or socio_esocial == "Todos":
        return df

    missing_columns = SOCIO_ESOCIAL_REQUIRED_COLUMNS - set(df.columns)
    if missing_columns:
        raise HTTPException(
            status_code=500,
            detail=(
                "Filtro socio_esocial exige colunas no perfil do estabelecimento: "
                + ", ".join(sorted(missing_columns))
            ),
        )

    scope = socio_esocial.strip().lower()
    filter_expr = _socio_esocial_scope_expr(scope)
    return df.filter(filter_expr)


def apply_volume_atipico_filter(
    df: pl.DataFrame,
    volume_atipico: bool,
    data_inicio: Optional[date] = None,
    data_fim: Optional[date] = None,
    volume_atipico_limite: Optional[float] = None,
) -> pl.DataFrame:
    """
    Restringe o DataFrame a CNPJs com ao menos um semestre de crescimento
    atípico no período informado. Quando `volume_atipico` é False, não
    aplica nada.
    """
    if not volume_atipico:
        return df
    if "id_cnpj" not in df.columns:
        raise HTTPException(
            status_code=500,
            detail="Filtro volume_atipico exige coluna 'id_cnpj' no perfil do estabelecimento.",
        )
    id_cnpjs_volume = get_volume_atipico_id_cnpjs_df(
        data_inicio,
        data_fim,
        volume_atipico_limite,
    ).select(pl.col("id_cnpj").cast(pl.Int64))
    return df.join(id_cnpjs_volume, on="id_cnpj", how="semi")


def build_perfil_filtrado(
    perfil_df: pl.DataFrame,
    *,
    filtros: FiltrosFarmacia,
    periodo_inicio: Optional[date] = None,
    periodo_fim: Optional[date] = None,
    data_referencia: Optional[date] = None,
    volume_atipico_inicio: Optional[date] = None,
    volume_atipico_fim: Optional[date] = None,
) -> pl.DataFrame:
    """
    Aplica em sequência os filtros de integridade (par_teia, socio_*, cnae,
    socio_idade_atipica) e, opcionalmente, o filtro de volume atípico, sobre
    um `perfil_df` que já deve ter passado pela filtragem geográfica do
    call site (não centraliza UF/regiao/municipio/CNPJ porque cada
    endpoint tem suas particularidades).

    `data_referencia` é a data usada para calcular idade do sócio no
    filtro de idade atípica (tipicamente `data_fim` do período). O
    filtro de volume atípico usa `volume_atipico_inicio` e
    `volume_atipico_fim` (período do crescimento semestral).

    Ordem de aplicação: populacao do municipio (corte barato, primeiro) →
    par_teia → socio_beneficio → socio_esocial → socio_falecido →
    cnae_incompativel → socio_idade_atipica → volume_atipico → autorizacoes em
    sequencia (unico/multiplos CRMs, no periodo periodo_inicio..periodo_fim).
    Cada filtro é no-op quando o parâmetro correspondente é o default
    (None / False).
    """
    df = apply_populacao_municipio_filter(perfil_df, filtros.populacao_min, filtros.populacao_max)
    df = _apply_par_teia_filter(df, filtros.par_teia)
    df = apply_socio_beneficio_filter(df, filtros.socio_beneficio)
    df = apply_socio_esocial_filter(df, filtros.socio_esocial)
    df = apply_socio_falecido_filter(df, filtros.socio_falecido)
    df = apply_cnae_incompativel_filter(df, filtros.cnae_incompativel)
    df = apply_socio_idade_atipica_filter(df, filtros.socio_idade_atipica, data_referencia=data_referencia)
    df = apply_volume_atipico_filter(
        df,
        filtros.volume_atipico,
        data_inicio=volume_atipico_inicio,
        data_fim=volume_atipico_fim,
        volume_atipico_limite=filtros.volume_atipico_limite,
    )
    df = apply_seq_filter(
        df,
        filtros.seq_tipo,
        filtros.seq_severidade_min,
        filtros.seq_dias_min,
        filtros.seq_dias_max,
        periodo_inicio,
        periodo_fim,
    )
    return df
