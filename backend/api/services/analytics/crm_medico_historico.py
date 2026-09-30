"""Historico completo de um CRM (modal do ranking em /analises).

Fontes (todas ja sincronizadas; nenhuma consulta ao banco):
* crm_medico_estabelecimento_mes: prescricoes por farmacia e mes (ordenado por
  medico: a leitura de um CRM e rapida);
* crm_medico_brasil_mes: total e dias com prescricao do medico no Brasil por
  mes (dias nao se somam entre farmacias, por isso vem dai);
* crm_limiar_p95_mes: P95 nacional do mes (mesma regra de alta intensidade do
  mapa e do ranking);
* perfil_estabelecimento e dados_medico: cadastro da farmacia e do medico;
* crm_concentracao_unico_alertas_global: dias com rajada de prescricoes do
  CRM numa farmacia (ponto "rajadas");
* geografico_global: pares de farmacias distantes com prescricao do CRM no
  mesmo mes (ponto "distancia").

As duas tabelas por medico tem de bater mes a mes (mesma execucao da etapa 1);
se nao baterem, responde 503 em vez de mostrar numeros incoerentes.

Filtro de farmacia (id_cnpj): meses, indicadores e pontos de atencao passam a
ser os da farmacia (prescricoes e dias dela no mes, exatos). So uma farmacia
por vez: os dias de farmacias diferentes nao se somam (o mesmo dia pode ter
prescricao nas duas). A marcacao de taxa elevada continua sendo a do total do
medico no mes (o P95 e calculado sobre o total). A lista de farmacias e a
serie farmacia x mes continuam completas (tabela e coluna de atuacao), com a
participacao de cada farmacia no total do medico.
"""

from datetime import date
from typing import Optional

import polars as pl
from fastapi import HTTPException

from data_cache import (
    get_dados_medico_df,
    get_df_perfil_estabelecimento,
    scan_crm_concentracao_unico_alertas_global,
    scan_crm_limiar_p95_mes,
    scan_crm_medico_brasil_mes,
    scan_crm_medico_estabelecimento_mes,
    scan_geografico_global,
)
from ...schemas.analytics import (
    CrmHistoricoAtencaoSchema,
    CrmRankingAlertasMedicoSchema,
    CrmRankingAlertasResponse,
    CrmHistoricoFarmaciaMesSchema,
    CrmHistoricoFarmaciaSchema,
    CrmHistoricoKpisSchema,
    CrmHistoricoMesSchema,
    CrmMedicoHistoricoResponse,
)
from .crm_analysis import _competencia, _period_bounds

# Farmacia com esta fatia (ou mais) das prescricoes do medico no periodo vira
# ponto de atencao.
LIMITE_CONCENTRACAO_PERCENTUAL = 50.0
# Pontos de atencao de uma pagina do ranking: no maximo este numero de CRMs.
ALERTAS_MAX_MEDICOS = 100


def _fmt_comp(competencia: int) -> str:
    return f"{competencia % 100:02d}/{competencia // 100}"


def _indice_mes(competencia: int) -> int:
    return (competencia // 100) * 12 + (competencia % 100) - 1


# Nome da severidade da rajada (id_severidade 1..4) no texto do alerta.
_SEVERIDADE_RAJADA = {1: "alta", 2: "grave", 3: "crítica", 4: "extrema"}


def _ler_rajadas(filtro: pl.Expr) -> pl.DataFrame:
    """Dias com rajada de prescricoes (CRM unico) que atendem ao filtro."""
    return (
        scan_crm_concentracao_unico_alertas_global()
        .filter(filtro)
        .select([
            pl.col("id_medico").cast(pl.Utf8),
            pl.col("id_cnpj").cast(pl.Int32),
            pl.col("competencia").cast(pl.Int32),
            pl.col("dt_alerta").cast(pl.Utf8),
            pl.col("id_severidade").cast(pl.Int32),
        ])
        .collect()
    )


def _ler_pares_distantes(filtro: pl.Expr) -> pl.DataFrame:
    """Pares de farmacias distantes (mesmo CRM, mesmo mes) que atendem ao filtro."""
    return (
        scan_geografico_global()
        .filter(filtro)
        .select([
            pl.col("id_medico").cast(pl.Utf8),
            pl.col("competencia").cast(pl.Int32),
            pl.col("no_municipio_a").cast(pl.Utf8),
            pl.col("sg_uf_a").cast(pl.Utf8),
            pl.col("no_municipio_b").cast(pl.Utf8),
            pl.col("sg_uf_b").cast(pl.Utf8),
            pl.col("distancia_km").cast(pl.Float64),
        ])
        .collect()
    )


def _maior_sequencia(competencias: list[int]) -> list[int]:
    """Maior trecho de meses consecutivos (calendario) da lista ordenada."""
    melhor: list[int] = []
    atual: list[int] = []
    for comp in competencias:
        if atual and _indice_mes(comp) == _indice_mes(atual[-1]) + 1:
            atual.append(comp)
        else:
            atual = [comp]
        if len(atual) > len(melhor):
            melhor = list(atual)
    return melhor


def pontos_de_atencao(
    *,
    id_medico: str,
    localizado_cfm: bool,
    dt_inscricao: object,
    meses_periodo: pl.DataFrame,
    principal: Optional[tuple[float, str]],
    rajadas: pl.DataFrame,
    pares_distantes: pl.DataFrame,
    avaliar_farmacias: bool,
) -> list[CrmHistoricoAtencaoSchema]:
    """Pontos de atencao de um CRM no periodo (regra unica: modal e ranking).

    meses_periodo: um mes por linha, com competencia, qtd_ufs (UFs distintas
    das farmacias no mes) e alta (taxa do mes acima do P95 do mes).
    principal: (% da farmacia principal no total do medico, nome dela).
    rajadas: dias com rajada do CRM no periodo (id_cnpj, competencia,
    dt_alerta, id_severidade); com filtro, so os da farmacia filtrada.
    pares_distantes: pares de farmacias distantes no periodo (competencia,
    municipios/UFs e distancia_km).
    avaliar_farmacias: False com filtro de farmacia (UFs, distancia e
    concentracao precisam de todas as farmacias).
    """
    pontos: list[CrmHistoricoAtencaoSchema] = []
    if not localizado_cfm:
        # Fato do CRM (nao do periodo): vem primeiro e vale com ou sem filtro.
        pontos.append(CrmHistoricoAtencaoSchema(
            codigo="nao_localizado_cfm",
            titulo="CRM não localizado no cadastro do CFM",
            detalhe=(
                f"O CRM {id_medico} não consta no cadastro do CFM. Sem a data de 1ª inscrição, "
                "não é possível conferir prescrições anteriores à inscrição."
            ),
        ))
    comps_periodo = meses_periodo.get_column("competencia").to_list()
    if isinstance(dt_inscricao, date):
        comp_inscricao = dt_inscricao.year * 100 + dt_inscricao.month
        antes = [c for c in comps_periodo if c < comp_inscricao]
        if antes:
            pontos.append(CrmHistoricoAtencaoSchema(
                codigo="antes_inscricao",
                titulo="Prescrições antes da inscrição no CFM",
                detalhe=(
                    f"{len(antes)} {'mês' if len(antes) == 1 else 'meses'} com prescrição antes da 1ª inscrição "
                    f"no CFM ({dt_inscricao:%d/%m/%Y}); primeiro em {_fmt_comp(antes[0])}."
                ),
                competencias=antes,
            ))
    if rajadas.height:
        dias = rajadas.get_column("dt_alerta").n_unique()
        farmacias_rajada = rajadas.get_column("id_cnpj").n_unique()
        pior = rajadas.select(pl.col("id_severidade").max()).item()
        if pior not in _SEVERIDADE_RAJADA:
            raise HTTPException(status_code=503, detail=f"Severidade de rajada desconhecida: {pior}.")
        pontos.append(CrmHistoricoAtencaoSchema(
            codigo="rajadas_unico",
            titulo="Rajadas de prescrição do mesmo CRM",
            detalhe=(
                f"{dias} {'dia' if dias == 1 else 'dias'} com muitas prescrições do CRM em poucos minutos, "
                f"em {farmacias_rajada} {'farmácia' if farmacias_rajada == 1 else 'farmácias'}; "
                f"pior severidade: {_SEVERIDADE_RAJADA[pior]}."
            ),
            competencias=sorted(rajadas.get_column("competencia").unique().to_list()),
        ))
    if avaliar_farmacias and pares_distantes.height:
        meses_distantes = sorted(pares_distantes.get_column("competencia").unique().to_list())
        maior = pares_distantes.sort(["distancia_km", "competencia"], descending=[True, False]).row(0, named=True)
        km = f"{maior['distancia_km']:,.0f}".replace(",", ".")
        pontos.append(CrmHistoricoAtencaoSchema(
            codigo="distancia",
            titulo="Farmácias distantes no mesmo mês",
            detalhe=(
                f"{len(meses_distantes)} {'mês' if len(meses_distantes) == 1 else 'meses'} com prescrição em farmácias "
                f"distantes entre si; maior distância: {km} km ({maior['no_municipio_a']}/{maior['sg_uf_a']} × "
                f"{maior['no_municipio_b']}/{maior['sg_uf_b']}, {_fmt_comp(maior['competencia'])})."
            ),
            competencias=meses_distantes,
        ))
    multi = meses_periodo.filter(pl.col("qtd_ufs") > 1).get_column("competencia").to_list()
    if multi and avaliar_farmacias:
        pontos.append(CrmHistoricoAtencaoSchema(
            codigo="multiplas_ufs",
            titulo="Prescrições em mais de uma UF no mesmo mês",
            detalhe=f"{len(multi)} {'mês' if len(multi) == 1 else 'meses'} com farmácias de UFs diferentes.",
            competencias=multi,
        ))
    sequencia = _maior_sequencia(meses_periodo.filter(pl.col("alta")).get_column("competencia").to_list())
    if len(sequencia) >= 2:
        pontos.append(CrmHistoricoAtencaoSchema(
            codigo="sequencia_alta",
            titulo="Meses consecutivos com taxa elevada",
            detalhe=(
                f"{len(sequencia)} meses seguidos com taxa elevada, de "
                f"{_fmt_comp(sequencia[0])} a {_fmt_comp(sequencia[-1])}."
            ),
            competencias=sequencia,
        ))
    if avaliar_farmacias and principal is not None and principal[0] >= LIMITE_CONCENTRACAO_PERCENTUAL:
        pontos.append(CrmHistoricoAtencaoSchema(
            codigo="concentracao",
            titulo="Concentração em uma farmácia",
            detalhe=f"{principal[0]:.1f}".replace(".", ",") + f"% das prescrições do período em {principal[1]}.",
        ))
    return pontos


def get_crm_medico_historico(
    id_medico: str,
    data_inicio: Optional[date] = None,
    data_fim: Optional[date] = None,
    id_cnpj: Optional[int] = None,
) -> CrmMedicoHistoricoResponse:
    id_medico = id_medico.strip()
    if not id_medico:
        raise HTTPException(status_code=422, detail="id_medico obrigatorio.")
    inicio, fim = _period_bounds(data_inicio, data_fim)
    comp_ini, comp_fim = _competencia(inicio), _competencia(fim)

    try:
        por_farmacia = (
            scan_crm_medico_estabelecimento_mes()
            .filter(pl.col("id_medico").cast(pl.Utf8) == id_medico)
            .select([
                pl.col("id_cnpj").cast(pl.Int32),
                pl.col("competencia").cast(pl.Int32),
                pl.col("nu_prescricoes_mes").cast(pl.Int64).alias("nu_prescricoes"),
                pl.col("qtd_dias_com_prescricao_mes").cast(pl.Int64).alias("qtd_dias"),
            ])
            .collect()
        )
        brasil = (
            scan_crm_medico_brasil_mes()
            .filter(pl.col("id_medico").cast(pl.Utf8) == id_medico)
            .select([
                pl.col("competencia").cast(pl.Int32),
                pl.col("nu_prescricoes_mes").cast(pl.Int64).alias("nu_prescricoes"),
                pl.col("qtd_dias_com_prescricao_mes").cast(pl.Int64).alias("qtd_dias"),
            ])
            .collect()
        )
        limiar = scan_crm_limiar_p95_mes().select([
            pl.col("competencia").cast(pl.Int32),
            pl.col("p95_taxa_dia").cast(pl.Float64),
        ]).collect()
        periodo_medico = (pl.col("id_medico").cast(pl.Utf8) == id_medico) & pl.col("competencia").is_between(comp_ini, comp_fim)
        rajadas = _ler_rajadas(periodo_medico)
        pares_distantes = _ler_pares_distantes(periodo_medico)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Cache de prescricoes por medico indisponivel: {exc}") from exc
    if id_cnpj is not None:
        rajadas = rajadas.filter(pl.col("id_cnpj") == id_cnpj)

    if por_farmacia.is_empty():
        raise HTTPException(status_code=404, detail=f"CRM {id_medico} sem prescricoes registradas.")
    if id_cnpj is not None and por_farmacia.filter(pl.col("id_cnpj") == id_cnpj).is_empty():
        raise HTTPException(status_code=404, detail=f"CRM {id_medico} sem prescricoes na farmacia {id_cnpj}.")

    # Conferencia: soma por farmacia = total Brasil, mes a mes.
    soma_farmacias = por_farmacia.group_by("competencia").agg(pl.col("nu_prescricoes").sum().alias("soma"))
    conferencia = soma_farmacias.join(brasil, on="competencia", how="full", coalesce=True)
    if conferencia.filter(
        pl.col("soma").is_null() | pl.col("nu_prescricoes").is_null() | (pl.col("soma") != pl.col("nu_prescricoes"))
    ).height:
        raise HTTPException(
            status_code=503,
            detail=(
                "Prescricoes do medico por farmacia nao batem com o total mensal do Brasil. "
                "Sincronize crm_medico_estabelecimento_mes e crm_medico_brasil_mes da mesma execucao."
            ),
        )

    # Cadastro das farmacias
    perfil = get_df_perfil_estabelecimento()
    cadastro = (
        perfil.select([
            pl.col("id_cnpj").cast(pl.Int32),
            pl.col("cnpj").cast(pl.Utf8),
            pl.col("razao_social").cast(pl.Utf8),
            pl.col("no_municipio").cast(pl.Utf8).alias("municipio"),
            pl.col("uf").cast(pl.Utf8),
            pl.col("situacao_rf").cast(pl.Utf8),
            pl.col("is_conexao_ativa").alias("conexao_ativa"),
        ])
        .filter(pl.col("id_cnpj").is_in(por_farmacia.get_column("id_cnpj").unique().implode()))
        .unique("id_cnpj", keep="first")
    )
    por_farmacia = por_farmacia.join(cadastro.select(["id_cnpj", "uf", "municipio"]), on="id_cnpj", how="left")
    por_farmacia_todas = por_farmacia

    # Cadastro do medico
    medico = (
        get_dados_medico_df().lazy()
        .filter(pl.col("id_medico").cast(pl.Utf8) == id_medico)
        .collect()
        .unique("id_medico", keep="first")
    )
    info = medico.row(0, named=True) if medico.height else {}
    dt_inscricao = info.get("dt_primeira_inscricao_uf")
    sg_uf = info.get("sg_uf") or (id_medico.split("/")[-1] if "/" in id_medico else None)

    # Meses (historico completo)
    ufs_mes = (
        por_farmacia.group_by("competencia")
        .agg([
            pl.col("id_cnpj").n_unique().alias("qtd_farmacias"),
            pl.col("uf").drop_nulls().n_unique().alias("qtd_ufs"),
        ])
    )
    meses_df = (
        brasil.join(limiar, on="competencia", how="left")
        .join(ufs_mes, on="competencia", how="left")
        .with_columns([
            (pl.col("nu_prescricoes") / pl.col("qtd_dias")).alias("taxa"),
        ])
        .with_columns([
            (pl.col("taxa").round(6) > pl.col("p95_taxa_dia")).fill_null(False).alias("alta"),
            pl.col("competencia").is_between(comp_ini, comp_fim).alias("no_periodo"),
        ])
        .sort("competencia")
    )
    if meses_df.filter(pl.col("p95_taxa_dia").is_null()).height:
        raise HTTPException(status_code=503, detail="Limiar P95 ausente para algum mes do historico do medico.")
    # Total do medico no periodo (base do % de cada farmacia na tabela).
    total_medico_periodo = int(meses_df.filter(pl.col("no_periodo")).get_column("nu_prescricoes").sum() or 0)
    if id_cnpj is not None:
        # Meses da farmacia: prescricoes, dias e taxa dela; taxa elevada do total.
        por_farmacia = por_farmacia.filter(pl.col("id_cnpj") == id_cnpj)
        meses_df = (
            por_farmacia.select(["competencia", "nu_prescricoes", "qtd_dias", "uf"])
            .join(
                meses_df.select(["competencia", "p95_taxa_dia", "alta", "no_periodo"]),
                on="competencia", how="left",
            )
            .with_columns([
                (pl.col("nu_prescricoes") / pl.col("qtd_dias")).alias("taxa"),
                pl.lit(1, dtype=pl.Int64).alias("qtd_farmacias"),
                pl.col("uf").is_not_null().cast(pl.Int64).alias("qtd_ufs"),
            ])
            .sort("competencia")
        )
        if meses_df.filter(pl.col("p95_taxa_dia").is_null()).height:
            raise HTTPException(status_code=503, detail="Farmacia com mes ausente no total mensal do medico.")
    meses = [
        CrmHistoricoMesSchema(
            competencia=int(r["competencia"]),
            nu_prescricoes=int(r["nu_prescricoes"]),
            qtd_dias_com_prescricao=int(r["qtd_dias"]),
            taxa_prescricoes_dia=float(r["taxa"]),
            p95_taxa_dia=float(r["p95_taxa_dia"]),
            alta_intensidade=bool(r["alta"]),
            qtd_farmacias=int(r["qtd_farmacias"] or 0),
            qtd_ufs=int(r["qtd_ufs"] or 0),
            no_periodo=bool(r["no_periodo"]),
        )
        for r in meses_df.iter_rows(named=True)
    ]

    # Periodo filtrado
    meses_periodo = meses_df.filter(pl.col("no_periodo"))
    farm_periodo = por_farmacia.filter(pl.col("competencia").is_between(comp_ini, comp_fim))
    total_periodo = int(meses_periodo.get_column("nu_prescricoes").sum() or 0)
    dias_periodo = int(meses_periodo.get_column("qtd_dias").sum() or 0)

    farm_todas = por_farmacia_todas.filter(pl.col("competencia").is_between(comp_ini, comp_fim))
    farmacias_df = (
        farm_todas.group_by("id_cnpj")
        .agg([
            pl.col("nu_prescricoes").sum().alias("nu_prescricoes"),
            pl.col("competencia").n_unique().alias("qtd_meses"),
            pl.col("competencia").min().alias("primeira"),
            pl.col("competencia").max().alias("ultima"),
        ])
        .join(cadastro, on="id_cnpj", how="left")
        .sort(["nu_prescricoes", "id_cnpj"], descending=[True, False])
    )
    farmacias = [
        CrmHistoricoFarmaciaSchema(
            id_cnpj=int(r["id_cnpj"]),
            cnpj=r["cnpj"],
            razao_social=r["razao_social"],
            municipio=r["municipio"],
            uf=r["uf"],
            situacao_rf=r["situacao_rf"],
            conexao_ativa=r["conexao_ativa"],
            nu_prescricoes=int(r["nu_prescricoes"]),
            percentual_prescricoes=(r["nu_prescricoes"] / total_medico_periodo * 100) if total_medico_periodo else 0.0,
            qtd_meses=int(r["qtd_meses"]),
            primeira_competencia=int(r["primeira"]),
            ultima_competencia=int(r["ultima"]),
            fora_uf_crm=bool(sg_uf and r["uf"] and r["uf"] != sg_uf),
        )
        for r in farmacias_df.iter_rows(named=True)
    ]

    # Pior mes: maior taxa diaria; empate -> mais prescricoes, depois o mais antigo.
    pior = meses_periodo.sort(["taxa", "nu_prescricoes", "competencia"], descending=[True, True, False]).head(1)
    qtd_alta = int(meses_periodo.get_column("alta").sum() or 0)
    if id_cnpj is not None:
        # Com filtro: "farmacia principal" = participacao da farmacia no total.
        selecionada = [f.percentual_prescricoes for f in farmacias if f.id_cnpj == id_cnpj]
        pcts = selecionada
    else:
        pcts = [f.percentual_prescricoes for f in farmacias]
    kpis = CrmHistoricoKpisSchema(
        nu_prescricoes=total_periodo,
        qtd_dias_com_prescricao=dias_periodo,
        taxa_prescricoes_dia=(total_periodo / dias_periodo) if dias_periodo else None,
        qtd_meses_ativos=meses_periodo.height,
        qtd_meses_alta_intensidade=qtd_alta,
        percentual_meses_alta_intensidade=(qtd_alta / meses_periodo.height * 100) if meses_periodo.height else None,
        qtd_farmacias=farm_periodo.get_column("id_cnpj").n_unique(),
        qtd_municipios=farm_periodo.select(pl.col("municipio").drop_nulls().n_unique()).item(),
        qtd_ufs=farm_periodo.select(pl.col("uf").drop_nulls().n_unique()).item(),
        percentual_farmacia_principal=pcts[0] if pcts else None,
        percentual_top3_farmacias=sum(pcts[:3]) if pcts and id_cnpj is None else None,
        pior_mes_competencia=int(pior.item(0, "competencia")) if pior.height else None,
        pior_mes_taxa_prescricoes_dia=float(pior.item(0, "taxa")) if pior.height else None,
        pior_mes_prescricoes=int(pior.item(0, "nu_prescricoes")) if pior.height else None,
        pior_mes_p95_taxa_dia=float(pior.item(0, "p95_taxa_dia")) if pior.height else None,
    )

    # Pontos de atencao (no periodo filtrado)
    principal = farmacias[0] if farmacias else None
    pontos = pontos_de_atencao(
        id_medico=id_medico,
        localizado_cfm=bool(info),
        dt_inscricao=dt_inscricao,
        meses_periodo=meses_periodo,
        principal=(
            (principal.percentual_prescricoes, str(principal.razao_social or principal.cnpj or principal.id_cnpj))
            if principal else None
        ),
        rajadas=rajadas,
        pares_distantes=pares_distantes,
        avaliar_farmacias=id_cnpj is None,
    )

    return CrmMedicoHistoricoResponse(
        id_medico=id_medico,
        nu_crm=info.get("nu_crm"),
        sg_uf=sg_uf,
        no_medico=info.get("no_medico"),
        dt_primeira_inscricao=dt_inscricao if isinstance(dt_inscricao, date) else None,
        localizado_cfm=bool(info),
        periodo_inicio=inicio,
        periodo_fim=fim,
        id_cnpj_filtro=id_cnpj,
        kpis=kpis,
        meses=meses,
        farmacias=farmacias,
        farmacia_mes=[
            CrmHistoricoFarmaciaMesSchema(
                id_cnpj=int(a), competencia=int(b), nu_prescricoes=int(c), qtd_dias_com_prescricao=int(e),
            )
            for a, b, c, e in por_farmacia_todas.select(["id_cnpj", "competencia", "nu_prescricoes", "qtd_dias"])
            .sort(["competencia", "id_cnpj"]).iter_rows()
        ],
        pontos_atencao=pontos,
        limite_concentracao_percentual=LIMITE_CONCENTRACAO_PERCENTUAL,
    )


def get_crm_medicos_alertas(
    ids: str,
    data_inicio: Optional[date] = None,
    data_fim: Optional[date] = None,
) -> CrmRankingAlertasResponse:
    """Pontos de atencao dos CRMs de uma pagina do ranking (/analises).

    Mesma regra do modal (pontos_de_atencao), sem filtro de farmacia, lendo
    so os medicos pedidos: prescricoes por farmacia, total Brasil por mes, P95
    e cadastros de farmacias e medicos.
    """
    id_medicos = [item.strip() for item in ids.split(",") if item.strip()]
    if not id_medicos:
        raise HTTPException(status_code=422, detail="Informe ao menos um id_medico.")
    if len(id_medicos) > ALERTAS_MAX_MEDICOS:
        raise HTTPException(status_code=422, detail=f"No maximo {ALERTAS_MAX_MEDICOS} medicos por consulta de alertas.")
    if len(set(id_medicos)) != len(id_medicos):
        raise HTTPException(status_code=422, detail="id_medico repetido na consulta de alertas.")
    inicio, fim = _period_bounds(data_inicio, data_fim)
    comp_ini, comp_fim = _competencia(inicio), _competencia(fim)
    no_periodo = pl.col("competencia").is_between(comp_ini, comp_fim)

    try:
        por_farmacia = (
            scan_crm_medico_estabelecimento_mes()
            .filter(pl.col("id_medico").cast(pl.Utf8).is_in(id_medicos) & no_periodo)
            .select([
                pl.col("id_medico").cast(pl.Utf8),
                pl.col("id_cnpj").cast(pl.Int32),
                pl.col("competencia").cast(pl.Int32),
                pl.col("nu_prescricoes_mes").cast(pl.Int64).alias("nu_prescricoes"),
            ])
            .collect()
        )
        brasil = (
            scan_crm_medico_brasil_mes()
            .filter(pl.col("id_medico").cast(pl.Utf8).is_in(id_medicos) & no_periodo)
            .select([
                pl.col("id_medico").cast(pl.Utf8),
                pl.col("competencia").cast(pl.Int32),
                pl.col("nu_prescricoes_mes").cast(pl.Int64).alias("nu_prescricoes"),
                pl.col("qtd_dias_com_prescricao_mes").cast(pl.Int64).alias("qtd_dias"),
            ])
            .collect()
        )
        limiar = scan_crm_limiar_p95_mes().select([
            pl.col("competencia").cast(pl.Int32),
            pl.col("p95_taxa_dia").cast(pl.Float64),
        ]).collect()
        dos_medicos = pl.col("id_medico").cast(pl.Utf8).is_in(id_medicos) & no_periodo
        rajadas = _ler_rajadas(dos_medicos)
        pares_distantes = _ler_pares_distantes(dos_medicos)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Cache de prescricoes por medico indisponivel: {exc}") from exc

    ausentes = sorted(set(id_medicos) - set(por_farmacia.get_column("id_medico").unique().to_list()))
    if ausentes:
        raise HTTPException(
            status_code=503,
            detail="CRMs do ranking sem prescricoes por farmacia no periodo: " + ", ".join(ausentes[:5]),
        )
    # Conferencia (mesma do modal): soma por farmacia = total Brasil, mes a mes.
    conferencia = (
        por_farmacia.group_by(["id_medico", "competencia"]).agg(pl.col("nu_prescricoes").sum().alias("soma"))
        .join(brasil, on=["id_medico", "competencia"], how="full", coalesce=True)
    )
    if conferencia.filter(
        pl.col("soma").is_null() | pl.col("nu_prescricoes").is_null() | (pl.col("soma") != pl.col("nu_prescricoes"))
    ).height:
        raise HTTPException(
            status_code=503,
            detail=(
                "Prescricoes dos medicos por farmacia nao batem com o total mensal do Brasil. "
                "Sincronize crm_medico_estabelecimento_mes e crm_medico_brasil_mes da mesma execucao."
            ),
        )

    cadastro = (
        get_df_perfil_estabelecimento()
        .select([
            pl.col("id_cnpj").cast(pl.Int32),
            pl.col("cnpj").cast(pl.Utf8),
            pl.col("razao_social").cast(pl.Utf8),
            pl.col("uf").cast(pl.Utf8),
        ])
        .filter(pl.col("id_cnpj").is_in(por_farmacia.get_column("id_cnpj").unique().implode()))
        .unique("id_cnpj", keep="first")
    )
    por_farmacia = por_farmacia.join(cadastro, on="id_cnpj", how="left")
    medicos = (
        get_dados_medico_df().lazy()
        .filter(pl.col("id_medico").cast(pl.Utf8).is_in(id_medicos))
        .collect()
        .unique("id_medico", keep="first")
    )
    cadastro_medico = {str(r["id_medico"]): r for r in medicos.iter_rows(named=True)}

    ufs_mes = por_farmacia.group_by(["id_medico", "competencia"]).agg(
        pl.col("uf").drop_nulls().n_unique().alias("qtd_ufs")
    )
    meses = (
        brasil.join(limiar, on="competencia", how="left")
        .join(ufs_mes, on=["id_medico", "competencia"], how="left")
        .with_columns((pl.col("nu_prescricoes") / pl.col("qtd_dias")).alias("taxa"))
        .with_columns((pl.col("taxa").round(6) > pl.col("p95_taxa_dia")).fill_null(False).alias("alta"))
        .sort(["id_medico", "competencia"])
    )
    if meses.filter(pl.col("p95_taxa_dia").is_null()).height:
        raise HTTPException(status_code=503, detail="Limiar P95 ausente para algum mes dos medicos consultados.")

    # Farmacia principal de cada medico (mesmo desempate da tabela do modal).
    totais = brasil.group_by("id_medico").agg(pl.col("nu_prescricoes").sum().alias("total"))
    principais = (
        por_farmacia.group_by(["id_medico", "id_cnpj"])
        .agg([
            pl.col("nu_prescricoes").sum(),
            pl.col("razao_social").first(),
            pl.col("cnpj").first(),
        ])
        .sort(["id_medico", "nu_prescricoes", "id_cnpj"], descending=[False, True, False])
        .unique("id_medico", keep="first", maintain_order=True)
        .join(totais, on="id_medico", how="left")
    )
    principal_por_medico = {
        str(r["id_medico"]): (
            (r["nu_prescricoes"] / r["total"] * 100) if r["total"] else 0.0,
            str(r["razao_social"] or r["cnpj"] or r["id_cnpj"]),
        )
        for r in principais.iter_rows(named=True)
    }
    meses_por_medico = meses.partition_by("id_medico", as_dict=True, include_key=True)
    rajadas_por_medico = rajadas.partition_by("id_medico", as_dict=True, include_key=True)
    pares_por_medico = pares_distantes.partition_by("id_medico", as_dict=True, include_key=True)

    resultado = []
    for id_medico in id_medicos:
        info = cadastro_medico.get(id_medico) or {}
        resultado.append(CrmRankingAlertasMedicoSchema(
            id_medico=id_medico,
            pontos_atencao=pontos_de_atencao(
                id_medico=id_medico,
                localizado_cfm=bool(info),
                dt_inscricao=info.get("dt_primeira_inscricao_uf"),
                meses_periodo=meses_por_medico[(id_medico,)].sort("competencia"),
                principal=principal_por_medico[id_medico],
                rajadas=rajadas_por_medico.get((id_medico,), rajadas.clear()),
                pares_distantes=pares_por_medico.get((id_medico,), pares_distantes.clear()),
                avaliar_farmacias=True,
            ),
        ))
    return CrmRankingAlertasResponse(periodo_inicio=inicio, periodo_fim=fim, medicos=resultado)
