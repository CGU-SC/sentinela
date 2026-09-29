"""Historico completo de um CRM (modal do ranking em /analises).

Fontes (todas ja sincronizadas; nenhuma consulta ao banco):
* crm_medico_estabelecimento_mes: prescricoes por farmacia e mes (ordenado por
  medico: a leitura de um CRM e rapida);
* crm_medico_brasil_mes: total e dias com prescricao do medico no Brasil por
  mes (dias nao se somam entre farmacias, por isso vem dai);
* crm_limiar_p95_mes: P95 nacional do mes (mesma regra de alta intensidade do
  mapa e do ranking);
* perfil_estabelecimento e dados_medico: cadastro da farmacia e do medico.

As duas tabelas por medico tem de bater mes a mes (mesma execucao da etapa 1);
se nao baterem, responde 503 em vez de mostrar numeros incoerentes.
"""

from datetime import date
from typing import Optional

import polars as pl
from fastapi import HTTPException

from data_cache import (
    get_dados_medico_df,
    get_df_perfil_estabelecimento,
    scan_crm_limiar_p95_mes,
    scan_crm_medico_brasil_mes,
    scan_crm_medico_estabelecimento_mes,
)
from ...schemas.analytics import (
    CrmHistoricoAtencaoSchema,
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


def _fmt_comp(competencia: int) -> str:
    return f"{competencia % 100:02d}/{competencia // 100}"


def _indice_mes(competencia: int) -> int:
    return (competencia // 100) * 12 + (competencia % 100) - 1


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


def get_crm_medico_historico(
    id_medico: str,
    data_inicio: Optional[date] = None,
    data_fim: Optional[date] = None,
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
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Cache de prescricoes por medico indisponivel: {exc}") from exc

    if por_farmacia.is_empty():
        raise HTTPException(status_code=404, detail=f"CRM {id_medico} sem prescricoes registradas.")

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

    farmacias_df = (
        farm_periodo.group_by("id_cnpj")
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
            percentual_prescricoes=(r["nu_prescricoes"] / total_periodo * 100) if total_periodo else 0.0,
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
    pcts = [f.percentual_prescricoes for f in farmacias]
    kpis = CrmHistoricoKpisSchema(
        nu_prescricoes=total_periodo,
        qtd_dias_com_prescricao=dias_periodo,
        taxa_prescricoes_dia=(total_periodo / dias_periodo) if dias_periodo else None,
        qtd_meses_ativos=meses_periodo.height,
        qtd_meses_alta_intensidade=qtd_alta,
        percentual_meses_alta_intensidade=(qtd_alta / meses_periodo.height * 100) if meses_periodo.height else None,
        qtd_farmacias=len(farmacias),
        qtd_municipios=farm_periodo.select(pl.col("municipio").drop_nulls().n_unique()).item(),
        qtd_ufs=farm_periodo.select(pl.col("uf").drop_nulls().n_unique()).item(),
        percentual_farmacia_principal=pcts[0] if pcts else None,
        percentual_top3_farmacias=sum(pcts[:3]) if pcts else None,
        pior_mes_competencia=int(pior.item(0, "competencia")) if pior.height else None,
        pior_mes_taxa_prescricoes_dia=float(pior.item(0, "taxa")) if pior.height else None,
        pior_mes_prescricoes=int(pior.item(0, "nu_prescricoes")) if pior.height else None,
        pior_mes_p95_taxa_dia=float(pior.item(0, "p95_taxa_dia")) if pior.height else None,
    )

    # Pontos de atencao (no periodo filtrado)
    pontos: list[CrmHistoricoAtencaoSchema] = []
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
    multi = meses_periodo.filter(pl.col("qtd_ufs") > 1).get_column("competencia").to_list()
    if multi:
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
    if farmacias and farmacias[0].percentual_prescricoes >= LIMITE_CONCENTRACAO_PERCENTUAL:
        principal = farmacias[0]
        pontos.append(CrmHistoricoAtencaoSchema(
            codigo="concentracao",
            titulo="Concentração em uma farmácia",
            detalhe=(
                f"{principal.percentual_prescricoes:.1f}".replace(".", ",")
                + f"% das prescrições do período em {principal.razao_social or principal.cnpj or principal.id_cnpj}."
            ),
        ))

    return CrmMedicoHistoricoResponse(
        id_medico=id_medico,
        nu_crm=info.get("nu_crm"),
        sg_uf=sg_uf,
        no_medico=info.get("no_medico"),
        dt_primeira_inscricao=dt_inscricao if isinstance(dt_inscricao, date) else None,
        localizado_cfm=bool(info),
        periodo_inicio=inicio,
        periodo_fim=fim,
        kpis=kpis,
        meses=meses,
        farmacias=farmacias,
        farmacia_mes=[
            CrmHistoricoFarmaciaMesSchema(
                id_cnpj=int(a), competencia=int(b), nu_prescricoes=int(c), qtd_dias_com_prescricao=int(e),
            )
            for a, b, c, e in por_farmacia.select(["id_cnpj", "competencia", "nu_prescricoes", "qtd_dias"])
            .sort(["competencia", "id_cnpj"]).iter_rows()
        ],
        pontos_atencao=pontos,
        limite_concentracao_percentual=LIMITE_CONCENTRACAO_PERCENTUAL,
    )
