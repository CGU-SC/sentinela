"""Panorama agregado de alertas de integridade para o dashboard nacional."""

from __future__ import annotations

from datetime import date

import polars as pl

from data_cache import (
    get_df_perfil_estabelecimento,
    get_df_dados_socios,
    get_df_par_teia_alvos,
    scan_geografico_origem_uf,
)
from ...schemas.analytics import AlertaPanoramaItemSchema, AlertasPanoramaResponse
from .geografico import UF_VIZINHAS, UF_BRASILEIRAS, LIMIAR_ALERTA_UF_NAO_VIZINHA_PCT
from .dispersao_uf import get_dispersao_uf_sem_fronteira_id_cnpjs_df
from .volume_atipico import get_volume_atipico_id_cnpjs_df
from .alertas_alvos import build_perfil_filtrado
from .filtros_farmacia import SEM_FILTRO_FARMACIA, FiltrosFarmacia


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _filtrar_id_cnpjs_por_escopo(
    perfil_df: pl.DataFrame,
    uf: str | None,
    regiao_id: int | None,
    id_ibge7: int | None,
) -> pl.Series | None:
    """
    Retorna um Series de id_cnpj (Int32) restrito ao escopo geográfico
    informado e aos filtros de integridade já aplicados no `perfil_df` (que
    o call site deve passar via `build_perfil_filtrado`). Retorna None
    apenas quando o `perfil_df` está vazio, indicando que os filtros
    atuais não casaram com nenhum CNPJ.
    """
    if "id_cnpj" not in perfil_df.columns:
        raise RuntimeError(
            "perfil_estabelecimento sem coluna obrigatória para escopo: id_cnpj"
        )
    if perfil_df.is_empty():
        return None

    if not any([uf, regiao_id, id_ibge7]):
        return perfil_df.get_column("id_cnpj")

    required = {"id_cnpj", "uf", "id_regiao_saude", "id_ibge7"}
    missing = required - set(perfil_df.columns)
    if missing:
        raise RuntimeError(
            f"perfil_estabelecimento sem colunas obrigatórias para filtro geográfico: {missing}"
        )

    mask = pl.lit(True)
    if id_ibge7:
        mask = mask & (pl.col("id_ibge7") == id_ibge7)
    elif regiao_id:
        mask = mask & (pl.col("id_regiao_saude") == regiao_id)
    elif uf:
        mask = mask & (pl.col("uf") == uf)

    return perfil_df.filter(mask).get_column("id_cnpj")


def _intersect_id_cnpjs(
    left: pl.Series | None,
    right: pl.Series,
) -> pl.Series:
    right_df = pl.DataFrame({"id_cnpj": right.cast(pl.Int64)}).unique()
    if left is None:
        return right_df.get_column("id_cnpj")

    left_df = pl.DataFrame({"id_cnpj": left.cast(pl.Int64)}).unique()
    if left_df.is_empty() or right_df.is_empty():
        return _empty_id_cnpjs()
    return (
        left_df
        .join(right_df, on="id_cnpj", how="semi")
        .get_column("id_cnpj")
    )


def _empty_id_cnpjs() -> pl.Series:
    return pl.Series("id_cnpj", [], dtype=pl.Int64)


def _distinct_id_cnpjs(df: pl.DataFrame, col: str = "id_cnpj") -> pl.Series:
    if df.is_empty():
        return _empty_id_cnpjs()
    return df.select(pl.col(col).cast(pl.Int64).alias("id_cnpj")).unique().get_column("id_cnpj")


def _ids_por_cnpj(cnpjs: pl.Series) -> pl.Series:
    if cnpjs.is_empty():
        return _empty_id_cnpjs()

    perfil = get_df_perfil_estabelecimento()
    required = {"id_cnpj", "cnpj"}
    missing = required - set(perfil.columns)
    if missing:
        raise RuntimeError(f"perfil_estabelecimento sem colunas obrigatorias para mapear CNPJ: {missing}")

    return (
        perfil
        .filter(pl.col("cnpj").is_in(cnpjs))
        .select(pl.col("id_cnpj").cast(pl.Int64).alias("id_cnpj"))
        .unique()
        .get_column("id_cnpj")
    )


# ---------------------------------------------------------------------------
# Contadores por tipo de alerta
# ---------------------------------------------------------------------------

def _ids_volume_atipico(
    id_cnpjs: pl.Series | None,
    data_inicio: date | None,
    data_fim: date | None,
) -> pl.Series:
    df = get_volume_atipico_id_cnpjs_df(data_inicio, data_fim, 50.0)
    if id_cnpjs is not None:
        df = df.filter(pl.col("id_cnpj").is_in(id_cnpjs))

    return _distinct_id_cnpjs(df)


def _ids_cnae_incompativel(id_cnpjs: pl.Series | None) -> pl.Series:
    perfil = get_df_perfil_estabelecimento()
    if "is_cnae_incompativel_farmaceutico" not in perfil.columns:
        return _empty_id_cnpjs()

    df = perfil.filter(pl.col("is_cnae_incompativel_farmaceutico") == True)  # noqa: E712
    if id_cnpjs is not None:
        df = df.filter(pl.col("id_cnpj").is_in(id_cnpjs))

    return _distinct_id_cnpjs(df)


def _ids_dispersao_uf_nao_vizinha(
    id_cnpjs: pl.Series | None,
    uf_farmacia_filtro: str | None,
    ano_base_min: int | None,
    ano_base_max: int | None,
) -> pl.Series:
    """
    Conta CNPJs onde vendas para UFs não-vizinhas superam o limiar de 5%.
    Usa scan lazy do geografico_origem_uf com filtro de ano_base.
    """
    required_cols = {"id_cnpj", "uf_farmacia", "uf_paciente", "valor_autorizado"}
    scan = scan_geografico_origem_uf()
    schema_cols = set(scan.collect_schema().names())
    missing = required_cols - schema_cols
    if missing:
        raise RuntimeError(f"geografico_origem_uf sem colunas: {missing}")

    lazy = scan
    if ano_base_min and "ano_base" in schema_cols:
        lazy = lazy.filter(pl.col("ano_base") >= ano_base_min)
    if ano_base_max and "ano_base" in schema_cols:
        lazy = lazy.filter(pl.col("ano_base") <= ano_base_max)
    if id_cnpjs is not None:
        lazy = lazy.filter(pl.col("id_cnpj").is_in(id_cnpjs))
    if uf_farmacia_filtro:
        lazy = lazy.filter(pl.col("uf_farmacia") == uf_farmacia_filtro)

    df = lazy.select(["id_cnpj", "uf_farmacia", "uf_paciente", "valor_autorizado"]).collect()
    if df.is_empty():
        return _empty_id_cnpjs()

    # Para cada (id_cnpj, uf_farmacia): calcula % de vendas para UFs não-vizinhas
    totais = (
        df.group_by(["id_cnpj", "uf_farmacia"])
        .agg(pl.col("valor_autorizado").sum().alias("total"))
    )

    # UFs não-vizinhas: uf_paciente não está em UF_VIZINHAS[uf_farmacia] ∪ {uf_farmacia}
    df_norm = df.with_columns(
        pl.col("uf_paciente").str.strip_chars().str.to_uppercase().alias("uf_pac_norm"),
        pl.col("uf_farmacia").str.strip_chars().str.to_uppercase().alias("uf_farm_norm"),
    )

    # Pré-computa pares de vizinhas para join vetorizado
    vizinhancas = []
    for uf_orig, vizs in UF_VIZINHAS.items():
        for uf_dest in (vizs | {uf_orig}):
            vizinhancas.append({"uf_farm_norm": uf_orig, "uf_pac_norm": uf_dest, "is_vizinha": True})
    df_vizinhancas = pl.DataFrame(vizinhancas)

    df_norm = df_norm.join(
        df_vizinhancas,
        on=["uf_farm_norm", "uf_pac_norm"],
        how="left",
    ).with_columns(
        (pl.col("is_vizinha").is_null() & pl.col("uf_pac_norm").is_in(list(UF_BRASILEIRAS))).alias("is_nao_vizinha")
    )

    distantes = (
        df_norm.filter(pl.col("is_nao_vizinha"))
        .group_by(["id_cnpj", "uf_farm_norm"])
        .agg(pl.col("valor_autorizado").sum().alias("valor_distante"))
    )

    joined = distantes.join(
        totais.rename({"uf_farmacia": "uf_farm_norm"}),
        on=["id_cnpj", "uf_farm_norm"],
        how="left",
    ).with_columns(
        (pl.col("valor_distante") / pl.col("total") * 100).alias("pct_distante")
    )

    alertas_df = joined.filter(pl.col("pct_distante") > LIMIAR_ALERTA_UF_NAO_VIZINHA_PCT)
    return _distinct_id_cnpjs(alertas_df)


def _ids_socio_falecido(id_cnpjs: pl.Series | None) -> pl.Series:
    socios = get_df_dados_socios()
    required = {"cnpj", "is_falecido", "indicador_socio", "data_exclusao_sociedade"}
    missing = required - set(socios.columns)
    if missing:
        return _empty_id_cnpjs()

    df = socios.filter(
        (pl.col("indicador_socio") == "PF")
        & pl.col("data_exclusao_sociedade").is_null()
        & (pl.col("is_falecido") == True)  # noqa: E712
    )

    if id_cnpjs is not None:
        # socios usa cnpj (string) — precisamos do mapeamento cnpj -> id_cnpj
        # via perfil_estabelecimento
        perfil = get_df_perfil_estabelecimento()
        if "cnpj" not in perfil.columns:
            raise RuntimeError("perfil_estabelecimento sem coluna 'cnpj'.")
        cnpjs_validos = (
            perfil.filter(pl.col("id_cnpj").is_in(id_cnpjs))
            .get_column("cnpj")
        )
        df = df.filter(pl.col("cnpj").is_in(cnpjs_validos))

    return _ids_por_cnpj(df.get_column("cnpj").unique())


def _ids_socio_beneficio_social(id_cnpjs: pl.Series | None) -> pl.Series:
    """Conta CNPJs com sócio inscrito no CadÚnico OU beneficiário do Seguro Defeso."""
    perfil = get_df_perfil_estabelecimento()
    tem_cadunico = "has_cadunico_direto" in perfil.columns
    tem_seguro = "has_seguro_defeso_direto" in perfil.columns
    if not tem_cadunico and not tem_seguro:
        return _empty_id_cnpjs()

    if tem_cadunico and tem_seguro:
        mask = (pl.col("has_cadunico_direto") == True) | (pl.col("has_seguro_defeso_direto") == True)  # noqa: E712
    elif tem_cadunico:
        mask = pl.col("has_cadunico_direto") == True  # noqa: E712
    else:
        mask = pl.col("has_seguro_defeso_direto") == True  # noqa: E712

    df = perfil.filter(mask)
    if id_cnpjs is not None:
        df = df.filter(pl.col("id_cnpj").is_in(id_cnpjs))

    return _distinct_id_cnpjs(df)


def _ids_socio_esocial(id_cnpjs: pl.Series | None) -> pl.Series:
    """Conta CNPJs com sócio com vínculo trabalhista em outro CNPJ (eSocial)."""
    perfil = get_df_perfil_estabelecimento()
    if "has_esocial_direto" not in perfil.columns:
        return _empty_id_cnpjs()

    df = perfil.filter(pl.col("has_esocial_direto") == True)  # noqa: E712
    if id_cnpjs is not None:
        df = df.filter(pl.col("id_cnpj").is_in(id_cnpjs))

    return _distinct_id_cnpjs(df)


def _ids_par_teia_n2(id_cnpjs: pl.Series | None) -> pl.Series:
    """Conta CNPJs alvo com ao menos um CNPJ no nivel 2 da teia com PAR."""
    par_teia = get_df_par_teia_alvos()
    required = {"cnpj", "has_par_n2"}
    missing = required - set(par_teia.columns)
    if missing:
        raise RuntimeError(
            "par_teia_alvos sem colunas obrigatorias para alerta PAR N2: "
            + ", ".join(sorted(missing))
        )

    cnpjs_par_n2 = (
        par_teia
        .filter(pl.col("has_par_n2") == True)  # noqa: E712
        .select("cnpj")
        .unique()
        .get_column("cnpj")
    )
    ids_par_n2 = _ids_por_cnpj(cnpjs_par_n2)
    return _intersect_id_cnpjs(id_cnpjs, ids_par_n2)


def _ids_socio_idade_atipica(
    id_cnpjs: pl.Series | None,
    data_referencia: date,
) -> pl.Series:
    """
    Conta CNPJs com ao menos um sócio ativo PF com idade < 21 ou > 80 anos.
    """
    socios = get_df_dados_socios()
    required = {"cnpj", "indicador_socio", "data_exclusao_sociedade", "data_nascimento_socio"}
    if not required.issubset(set(socios.columns)):
        return _empty_id_cnpjs()

    df = socios.filter(
        (pl.col("indicador_socio") == "PF")
        & pl.col("data_exclusao_sociedade").is_null()
        & pl.col("data_nascimento_socio").is_not_null()
    )

    if df.is_empty():
        return _empty_id_cnpjs()

    ref = pl.lit(data_referencia)
    df = df.with_columns(
        (
            (ref - pl.col("data_nascimento_socio")).dt.total_days() / 365.25
        ).alias("idade_anos")
    )

    df = df.filter(
        (pl.col("idade_anos") < 21) | (pl.col("idade_anos") > 80)
    )

    if id_cnpjs is not None:
        perfil = get_df_perfil_estabelecimento()
        if "cnpj" not in perfil.columns:
            raise RuntimeError("perfil_estabelecimento sem coluna 'cnpj'.")
        cnpjs_validos = (
            perfil.filter(pl.col("id_cnpj").is_in(id_cnpjs))
            .get_column("cnpj")
        )
        df = df.filter(pl.col("cnpj").is_in(cnpjs_validos))

    return _ids_por_cnpj(df.get_column("cnpj").unique())


# ---------------------------------------------------------------------------
# Função pública
# ---------------------------------------------------------------------------

def get_alertas_panorama(
    uf: str | None = None,
    regiao_id: int | None = None,
    id_ibge7: int | None = None,
    data_inicio: date | None = None,
    data_fim: date | None = None,
    filtros: FiltrosFarmacia = SEM_FILTRO_FARMACIA,
) -> AlertasPanoramaResponse:
    """
    Agrega contagens de alertas de integridade por tipo, filtradas pelo escopo
    geográfico, filtros de integridade e período informados. Processamento
    100% em memória via Polars.
    """
    ano_base_min = data_inicio.year if data_inicio else None
    ano_base_max = data_fim.year if data_fim else None
    data_ref = data_fim or date.today()

    perfil_df = get_df_perfil_estabelecimento()
    perfil_filtrado = build_perfil_filtrado(
        perfil_df,
        filtros=filtros,
        data_referencia=data_ref,
        periodo_inicio=data_inicio,
        volume_atipico_inicio=data_inicio,
        periodo_fim=data_fim,
        volume_atipico_fim=data_fim,
    )

    id_cnpjs = _filtrar_id_cnpjs_por_escopo(perfil_filtrado, uf, regiao_id, id_ibge7)
    if filtros.dispersao_uf_sem_fronteira:
        id_cnpjs_dispersao = (
            get_dispersao_uf_sem_fronteira_id_cnpjs_df(
                data_inicio,
                data_fim,
                filtros.dispersao_uf_sem_fronteira_limite,
            )
            .select(pl.col("id_cnpj").cast(pl.Int64))
            .unique()
            .get_column("id_cnpj")
        )
        id_cnpjs = _intersect_id_cnpjs(id_cnpjs, id_cnpjs_dispersao)

    ids_por_alerta = {
        "volume_atipico": _ids_volume_atipico(id_cnpjs, data_inicio, data_fim),
        "cnpj_cnae_farmacia_ausente": _ids_cnae_incompativel(id_cnpjs),
        "cnpj_dispersao_uf_nao_vizinha": _ids_dispersao_uf_nao_vizinha(
            id_cnpjs, uf, ano_base_min, ano_base_max
        ),
        "socio_falecido": _ids_socio_falecido(id_cnpjs),
        "socio_beneficio_social": _ids_socio_beneficio_social(id_cnpjs),
        "socio_idade_atipica": _ids_socio_idade_atipica(id_cnpjs, data_ref),
        "socio_esocial": _ids_socio_esocial(id_cnpjs),
        "par_teia_n2": _ids_par_teia_n2(id_cnpjs),
    }
    contagens = {
        tipo: ids.n_unique()
        for tipo, ids in ids_por_alerta.items()
    }

    DEFINICOES = [
        ("volume_atipico",                "Crescimento semestral atípico",                "critico"),
        ("cnpj_dispersao_uf_nao_vizinha", "Vendas para UFs sem fronteira",              "critico"),
        ("cnpj_cnae_farmacia_ausente",    "CNAE incompatível",                            "atencao"),
        ("socio_falecido",                "Sócio ativo falecido",                         "atencao"),
        ("socio_beneficio_social",        "Sócio inscrito no CadÚnico/Defeso",            "atencao"),
        ("socio_idade_atipica",           "Sócios < 21 ou > 80 anos",                    "atencao"),
        ("socio_esocial",                 "Sócio com vínculo eSocial",                  "atencao"),
        ("par_teia_n2",                    "CNPJ Nível 2 da Teia com PAR",               "atencao"),
    ]

    alertas = [
        AlertaPanoramaItemSchema(
            tipo=tipo,
            titulo=titulo,
            severidade=severidade,  # type: ignore[arg-type]
            qtd_cnpjs=contagens[tipo],
        )
        for tipo, titulo, severidade in DEFINICOES
    ]

    # CNPJs com pelo menos 1 alerta, sem dupla contagem entre tipos.
    total_com_alerta = (
        pl.concat(list(ids_por_alerta.values())).n_unique()
        if ids_por_alerta
        else 0
    )

    total_criticos = sum(
        a.qtd_cnpjs for a in alertas if a.severidade == "critico"
    )
    total_atencao = sum(
        a.qtd_cnpjs for a in alertas if a.severidade == "atencao"
    )

    return AlertasPanoramaResponse(
        total_cnpjs_com_alerta=total_com_alerta,
        total_criticos=total_criticos,
        total_atencao=total_atencao,
        alertas=alertas,
    )
