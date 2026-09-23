from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import date
from database import get_db, engine
from ..schemas.analytics import (
    AnalyticsResponse, FatorRiscoResponseSchema,
    RedeEstabelecimentoSchema, EvolucaoFinanceiraResponse, IndicadoresResponse,
    ProducaoSemestralResponse,
    FalecidosResponse, MultiCnpjTimelineResponse, RegionalResponse, RegionalAnimationResponse,
    PrescritoresResponse, DadosFarmaciaSchema, CnpjAccessStatusSchema, MovimentacaoResponse, IndicadorAnaliseResponse,
    IndicadorCnpjPageResponse,
    PercentilesAnimationResponse, CrmTimelineDatasetResponse,
    CrmMedicoAlertasResponse, CrmRaioXResponse,
    EvolucaoMensalGtinResponse, GtinDetalhamentoMensalResponse, RepassesResponse,
    SociosResponse, IntegrityAlertsResponse, NetworkResponse,
    CnpjBootstrapResponse,
    GeograficoOrigemUfResponse,
    GeograficoBenchmarkResponse,
    IndicadorBenchmarkResponse,
    IndicadorEvolucaoBenchmarkResponse,
    ClinicoIncompatibilidadeResponse,
    AlertasPanoramaResponse,
    CrmPrescricoesAnaliseResponse,
    NotaTecnicaReadinessResponse,
    NotaTecnicaPrepareResponse,
)
from ..services.analytics import AnalyticsService
from fastapi.responses import StreamingResponse
from loguru import logger
from request_logging import FrontendPerformanceEvent, log_frontend_performance
import json
import time
import traceback
import urllib.parse

router = APIRouter()


@router.get("/crm-prescricoes-analise", response_model=CrmPrescricoesAnaliseResponse)
def get_crm_prescricoes_analise(
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    include_map: bool = Query(True),
    map_only: bool = Query(False),
    map_level: str = Query("uf", description="Nível do mapa: uf, municipio ou regiao."),
    data_inicio: Optional[date] = Query(None),
    data_fim: Optional[date] = Query(None),
    perc_min: Optional[float] = Query(None),
    perc_max: Optional[float] = Query(None),
    val_min: Optional[float] = Query(None),
    uf: Optional[str] = Query(None),
    regiao_id: Optional[int] = Query(None),
    id_ibge7: Optional[int] = Query(None),
    situacao_rf: Optional[str] = Query(None),
    conexao_ms: Optional[str] = Query(None),
    porte_empresa: Optional[str] = Query(None),
    grande_rede: Optional[str] = Query(None),
    cnpj_raiz: Optional[str] = Query(None),
    unidade_pf: Optional[str] = Query(None),
    razao_social: Optional[str] = Query(None),
    estabelecimento: Optional[str] = Query(None),
    par_teia: Optional[str] = Query(None),
    socio_beneficio: Optional[str] = Query(None),
    socio_esocial: Optional[str] = Query(None),
    cnae_incompativel: bool = Query(False),
    socio_idade_atipica: bool = Query(False),
    socio_falecido: bool = Query(False),
    volume_atipico: bool = Query(False),
    volume_atipico_limite: Optional[float] = Query(None),
    dispersao_uf_sem_fronteira: bool = Query(False),
    dispersao_uf_sem_fronteira_limite: Optional[float] = Query(None),
):
    """Retorna o percentual mensal de CRMs anômalos por UF/município e o ranking de médicos."""
    return AnalyticsService.get_crm_prescricoes_analise(
        page=page,
        page_size=page_size,
        include_map=include_map,
        map_only=map_only,
        map_level=map_level,
        data_inicio=data_inicio,
        data_fim=data_fim,
        perc_min=perc_min,
        perc_max=perc_max,
        val_min=val_min,
        uf=uf,
        regiao_id=regiao_id,
        id_ibge7=id_ibge7,
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
        volume_atipico_limite=volume_atipico_limite,
        dispersao_uf_sem_fronteira=dispersao_uf_sem_fronteira,
        dispersao_uf_sem_fronteira_limite=dispersao_uf_sem_fronteira_limite,
    )


def _parse_assinantes_tecnicos_param(value: Optional[str]) -> Optional[List[dict]]:
    if value is None or not value.strip():
        return None
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=422, detail="assinantes_tecnicos deve ser um JSON valido.") from exc
    if not isinstance(parsed, list):
        raise HTTPException(status_code=422, detail="assinantes_tecnicos deve ser uma lista.")
    if len(parsed) > 3:
        raise HTTPException(status_code=422, detail="Informe no maximo 3 assinaturas tecnicas.")

    normalized = []
    for item in parsed:
        if not isinstance(item, dict):
            raise HTTPException(status_code=422, detail="Cada assinatura tecnica deve ser um objeto.")
        nome = str(item.get("nome", "")).strip()
        cargo = str(item.get("cargo", "")).strip()
        if (nome and not cargo) or (cargo and not nome):
            raise HTTPException(
                status_code=422,
                detail="Cada assinatura tecnica deve conter nome e cargo.",
            )
        if nome and cargo:
            normalized.append({"nome": nome, "cargo": cargo})
    return normalized


@router.post("/client-perf")
def log_client_performance(event: FrontendPerformanceEvent):
    return log_frontend_performance(event)


@router.get("/cnpj/{cnpj}/bootstrap", response_model=CnpjBootstrapResponse)
def get_cnpj_bootstrap(
    cnpj: str,
    data_inicio: Optional[date] = Query(None),
    data_fim: Optional[date] = Query(None),
):
    """Retorna o pacote minimo para primeira renderizacao da tela de estabelecimento."""
    return AnalyticsService.get_cnpj_bootstrap(cnpj, data_inicio, data_fim)


@router.get("/cnpj/{cnpj}/status", response_model=CnpjAccessStatusSchema)
def get_cnpj_access_status(cnpj: str):
    """Valida se o identificador da rota e um CNPJ do Programa Farmacia Popular."""
    return AnalyticsService.get_cnpj_access_status(cnpj)


@router.get("/cnpj/{cnpj}/cadastro", response_model=DadosFarmaciaSchema)
def get_dados_farmacia(cnpj: str):
    """Retorna os dados cadastrais e geográficos (endereço, lat/lon) para um CNPJ."""
    return AnalyticsService.get_dados_farmacia(cnpj)

@router.get("/cnpj/{cnpj}/socios", response_model=SociosResponse)
def get_socios_farmacia(cnpj: str):
    """Retorna o quadro societário de um estabelecimento."""
    return AnalyticsService.get_socios_farmacia(cnpj)

@router.get("/alertas-panorama", response_model=AlertasPanoramaResponse)
def get_alertas_panorama(
    uf: Optional[str] = Query(None),
    regiao_id: Optional[int] = Query(None),
    id_ibge7: Optional[int] = Query(None),
    data_inicio: Optional[date] = Query(None),
    data_fim: Optional[date] = Query(None),
    par_teia: Optional[str] = Query(None),
    socio_beneficio: Optional[str] = Query(None),
    socio_esocial: Optional[str] = Query(None),
    cnae_incompativel: bool = Query(False),
    socio_idade_atipica: bool = Query(False),
    socio_falecido: bool = Query(False),
    volume_atipico: bool = Query(False),
    volume_atipico_limite: Optional[float] = Query(None),
    dispersao_uf_sem_fronteira: bool = Query(False),
    dispersao_uf_sem_fronteira_limite: Optional[float] = Query(None),
):
    """Panorama agregado de alertas de integridade para o dashboard, filtrado por escopo, filtros de integridade e período."""
    return AnalyticsService.get_alertas_panorama(
        uf=uf,
        regiao_id=regiao_id,
        id_ibge7=id_ibge7,
        data_inicio=data_inicio,
        data_fim=data_fim,
        par_teia=par_teia,
        socio_beneficio=socio_beneficio,
        socio_esocial=socio_esocial,
        cnae_incompativel=cnae_incompativel,
        socio_idade_atipica=socio_idade_atipica,
        socio_falecido=socio_falecido,
        volume_atipico=volume_atipico,
        volume_atipico_limite=volume_atipico_limite,
        dispersao_uf_sem_fronteira=dispersao_uf_sem_fronteira,
        dispersao_uf_sem_fronteira_limite=dispersao_uf_sem_fronteira_limite,
    )

@router.get("/cnpj/{cnpj}/alertas-integridade", response_model=IntegrityAlertsResponse)
def get_integrity_alerts(
    cnpj: str,
    data_inicio: Optional[date] = Query(None),
    data_fim: Optional[date] = Query(None),
    volume_atipico_limite: Optional[float] = Query(None),
):
    """Retorna alertas de integridade do estabelecimento e de seus vinculos diretos."""
    return AnalyticsService.get_integrity_alerts(
        cnpj,
        data_inicio=data_inicio,
        data_fim=data_fim,
        volume_atipico_limite=volume_atipico_limite,
    )

@router.get("/cnpj/{cnpj}/network", response_model=NetworkResponse)
def get_teia_grafo_nivel2(
    cnpj: str,
    data_inicio: Optional[date] = Query(None),
    data_fim: Optional[date] = Query(None),
):
    """Retorna a rede de relacionamentos societários (Teia) de um estabelecimento."""
    return AnalyticsService.get_teia_grafo_nivel2(
        cnpj,
        engine=None,
        data_inicio=data_inicio,
        data_fim=data_fim,
    )

@router.get("/cnpj/{cnpj}/network/expand/{target_id}", response_model=NetworkResponse)
def get_teia_network_expansion(
    cnpj: str,
    target_id: str,
    data_inicio: Optional[date] = Query(None),
    data_fim: Optional[date] = Query(None),
):
    """
    Retorna os dados de expansão para um nó da teia.
    - Se target_id for CNPJ (14 dígitos): expande para Sócios (Nível 3).
    - Se target_id for CPF (11 dígitos): expande para outras Empresas (Nível 4).
    """
    clean_id = target_id.replace(".", "").replace("/", "").replace("-", "")
    if len(clean_id) == 11:
        return AnalyticsService.get_teia_grafo_nivel4_expansao(
            cnpj_alvo=cnpj,
            cpf_para_expandir=clean_id,
            data_inicio=data_inicio,
            data_fim=data_fim,
        )
    else:
        return AnalyticsService.get_teia_grafo_nivel3_expansao(
            cnpj_alvo=cnpj,
            cnpj_para_expandir=clean_id,
            data_inicio=data_inicio,
            data_fim=data_fim,
        )

@router.get("/cnpj/{cnpj}/network/level/3", response_model=NetworkResponse)
def get_teia_batch_level3(
    cnpj: str,
    data_inicio: Optional[date] = Query(None),
    data_fim: Optional[date] = Query(None),
):
    """Retorna todos os sócios de nível 3 em lote."""
    return AnalyticsService.get_teia_grafo_nivel3_full(
        cnpj,
        data_inicio=data_inicio,
        data_fim=data_fim,
    )

@router.get("/cnpj/{cnpj}/network/level/4", response_model=NetworkResponse)
def get_teia_batch_level4(
    cnpj: str,
    data_inicio: Optional[date] = Query(None),
    data_fim: Optional[date] = Query(None),
):
    """Retorna todas as participações de nível 4 em lote."""
    return AnalyticsService.get_teia_grafo_nivel4_full(
        cnpj,
        data_inicio=data_inicio,
        data_fim=data_fim,
    )



@router.get("/resumo", response_model=AnalyticsResponse)
def get_analytics_summary(
    data_inicio: Optional[date] = Query(None),
    data_fim: Optional[date] = Query(None),
    perc_min: Optional[float] = Query(None),
    perc_max: Optional[float] = Query(None),
    val_min: Optional[float] = Query(None),
    uf: Optional[str] = Query(None),
    regiao_saude: Optional[str] = Query(None),
    municipio: Optional[str] = Query(None),
    id_ibge7: Optional[int] = Query(None),
    situacao_rf: Optional[str] = Query(None),
    conexao_ms: Optional[str] = Query(None),
    porte_empresa: Optional[str] = Query(None),
    grande_rede: Optional[str] = Query(None),
    cnpj_raiz: Optional[str] = Query(None),
    unidade_pf: Optional[str] = Query(None),
    razao_social: Optional[str] = Query(None),
    estabelecimento: Optional[str] = Query(None),
    cnpjs: Optional[List[str]] = Query(None),
    regiao_id: Optional[int] = Query(None),
    volume_atipico: bool = Query(False),
    volume_atipico_limite: Optional[float] = Query(None),
    dispersao_uf_sem_fronteira: bool = Query(False),
    dispersao_uf_sem_fronteira_limite: Optional[float] = Query(None),
    par_teia: Optional[str] = Query(None),
    socio_beneficio: Optional[str] = Query(None),
    socio_esocial: Optional[str] = Query(None),
    cnae_incompativel: bool = Query(False),
    socio_idade_atipica: bool = Query(False),
    socio_falecido: bool = Query(False),
    db: Session = Depends(get_db)
):
    if regiao_saude and regiao_saude != "Todos":
        raise HTTPException(status_code=400, detail="Use regiao_id para filtros regionais; regiao_saude textual e apenas label.")
    if municipio and municipio != "Todos":
        raise HTTPException(status_code=400, detail="Use id_ibge7 para filtros municipais; municipio textual e apenas label.")
    return AnalyticsService.get_dashboard_data(db, data_inicio, data_fim, perc_min, perc_max, val_min, uf, regiao_saude, municipio, situacao_rf, conexao_ms, porte_empresa, grande_rede, cnpj_raiz, unidade_pf, razao_social, cnpjs, regiao_id=regiao_id, id_ibge7=id_ibge7, volume_atipico=volume_atipico, volume_atipico_limite=volume_atipico_limite, dispersao_uf_sem_fronteira=dispersao_uf_sem_fronteira, dispersao_uf_sem_fronteira_limite=dispersao_uf_sem_fronteira_limite, par_teia=par_teia, socio_beneficio=socio_beneficio, socio_esocial=socio_esocial, cnae_incompativel=cnae_incompativel, socio_idade_atipica=socio_idade_atipica, socio_falecido=socio_falecido, estabelecimento=estabelecimento)


@router.get("/producao-semestral", response_model=ProducaoSemestralResponse)
def get_producao_semestral(
    data_inicio: Optional[date] = Query(None),
    data_fim: Optional[date] = Query(None),
    perc_min: Optional[float] = Query(None),
    perc_max: Optional[float] = Query(None),
    val_min: Optional[float] = Query(None),
    uf: Optional[str] = Query(None),
    regiao_saude: Optional[str] = Query(None),
    municipio: Optional[str] = Query(None),
    id_ibge7: Optional[int] = Query(None),
    situacao_rf: Optional[str] = Query(None),
    conexao_ms: Optional[str] = Query(None),
    porte_empresa: Optional[str] = Query(None),
    grande_rede: Optional[str] = Query(None),
    cnpj_raiz: Optional[str] = Query(None),
    unidade_pf: Optional[str] = Query(None),
    razao_social: Optional[str] = Query(None),
    estabelecimento: Optional[str] = Query(None),
    cnpjs: Optional[List[str]] = Query(None),
    regiao_id: Optional[int] = Query(None),
    volume_atipico: bool = Query(False),
    volume_atipico_limite: Optional[float] = Query(None),
    dispersao_uf_sem_fronteira: bool = Query(False),
    dispersao_uf_sem_fronteira_limite: Optional[float] = Query(None),
    par_teia: Optional[str] = Query(None),
    socio_beneficio: Optional[str] = Query(None),
    socio_esocial: Optional[str] = Query(None),
    cnae_incompativel: bool = Query(False),
    socio_idade_atipica: bool = Query(False),
    socio_falecido: bool = Query(False),
    db: Session = Depends(get_db)
):
    """Retorna valor de producao semestral e acumulado para o dashboard Home."""
    if regiao_saude and regiao_saude != "Todos":
        raise HTTPException(status_code=400, detail="Use regiao_id para filtros regionais; regiao_saude textual e apenas label.")
    if municipio and municipio != "Todos":
        raise HTTPException(status_code=400, detail="Use id_ibge7 para filtros municipais; municipio textual e apenas label.")
    return AnalyticsService.get_producao_semestral_data(
        db,
        data_inicio,
        data_fim,
        perc_min,
        perc_max,
        val_min,
        uf,
        situacao_rf,
        conexao_ms,
        porte_empresa,
        grande_rede,
        cnpj_raiz,
        unidade_pf,
        razao_social,
        cnpjs,
        regiao_id=regiao_id,
        id_ibge7=id_ibge7,
        volume_atipico=volume_atipico,
        volume_atipico_limite=volume_atipico_limite,
        dispersao_uf_sem_fronteira=dispersao_uf_sem_fronteira,
        dispersao_uf_sem_fronteira_limite=dispersao_uf_sem_fronteira_limite,
        par_teia=par_teia,
        socio_beneficio=socio_beneficio,
        socio_esocial=socio_esocial,
        cnae_incompativel=cnae_incompativel,
        socio_idade_atipica=socio_idade_atipica,
        estabelecimento=estabelecimento,
    )

@router.get("/faixas-risco", response_model=FatorRiscoResponseSchema)
def get_resultado_faixas_risco(
    data_inicio: Optional[date] = Query(None),
    data_fim: Optional[date] = Query(None),
    perc_min: Optional[float] = Query(None),
    perc_max: Optional[float] = Query(None),
    val_min: Optional[float] = Query(None),
    uf: Optional[str] = Query(None),
    regiao_saude: Optional[str] = Query(None),
    municipio: Optional[str] = Query(None),
    id_ibge7: Optional[int] = Query(None),
    situacao_rf: Optional[str] = Query(None),
    conexao_ms: Optional[str] = Query(None),
    porte_empresa: Optional[str] = Query(None),
    grande_rede: Optional[str] = Query(None),
    cnpj_raiz: Optional[str] = Query(None),
    unidade_pf: Optional[str] = Query(None),
    razao_social: Optional[str] = Query(None),
    estabelecimento: Optional[str] = Query(None),
    regiao_id: Optional[int] = Query(None),
    volume_atipico: bool = Query(False),
    volume_atipico_limite: Optional[float] = Query(None),
    dispersao_uf_sem_fronteira: bool = Query(False),
    dispersao_uf_sem_fronteira_limite: Optional[float] = Query(None),
    par_teia: Optional[str] = Query(None),
    socio_beneficio: Optional[str] = Query(None),
    socio_esocial: Optional[str] = Query(None),
    cnae_incompativel: bool = Query(False),
    socio_idade_atipica: bool = Query(False),
    socio_falecido: bool = Query(False),
    db: Session = Depends(get_db)
):
    if regiao_saude and regiao_saude != "Todos":
        raise HTTPException(status_code=400, detail="Use regiao_id para filtros regionais; regiao_saude textual e apenas label.")
    if municipio and municipio != "Todos":
        raise HTTPException(status_code=400, detail="Use id_ibge7 para filtros municipais; municipio textual e apenas label.")
    return AnalyticsService.get_fator_risco_data(db, data_inicio, data_fim, perc_min, perc_max, val_min, uf, regiao_saude, municipio, situacao_rf, conexao_ms, porte_empresa, grande_rede, cnpj_raiz, unidade_pf, razao_social, regiao_id=regiao_id, id_ibge7=id_ibge7, volume_atipico=volume_atipico, volume_atipico_limite=volume_atipico_limite, dispersao_uf_sem_fronteira=dispersao_uf_sem_fronteira, dispersao_uf_sem_fronteira_limite=dispersao_uf_sem_fronteira_limite, par_teia=par_teia, socio_beneficio=socio_beneficio, socio_esocial=socio_esocial, cnae_incompativel=cnae_incompativel, socio_idade_atipica=socio_idade_atipica, socio_falecido=socio_falecido, estabelecimento=estabelecimento)

@router.get("/cnpj/{cnpj}/evolucao", response_model=EvolucaoFinanceiraResponse)
def get_evolucao_financeira(
    cnpj: str,
    data_inicio: Optional[date] = Query(None),
    data_fim: Optional[date] = Query(None),
    volume_atipico_limite: Optional[float] = Query(None),
):
    """Retorna a série semestral de valores financeiros para um CNPJ, com recorte temporal opcional."""
    return AnalyticsService.get_evolucao_financeira(cnpj, data_inicio, data_fim, volume_atipico_limite)

@router.get("/cnpj/{cnpj}/evolucao-mensal-gtin", response_model=EvolucaoMensalGtinResponse)
def get_evolucao_mensal_gtin(
    cnpj: str,
    data_inicio: Optional[date] = Query(None),
    data_fim: Optional[date] = Query(None),
):
    """Retorna a série mensal de quantidades e valores (agregados por GTIN) para um CNPJ."""
    return AnalyticsService.get_evolucao_mensal_gtin(cnpj, data_inicio, data_fim)

@router.get("/cnpj/{cnpj}/repasses", response_model=RepassesResponse)
def get_cnpj_repasses(
    cnpj: str,
    data_inicio: Optional[date] = Query(None),
    data_fim: Optional[date] = Query(None),
):
    """Retorna repasses consolidados do Programa Farmacia Popular para um CNPJ."""
    return AnalyticsService.get_cnpj_repasses(cnpj, data_inicio, data_fim)

@router.get("/cnpj/{cnpj}/gtin-detalhamento-mensal", response_model=GtinDetalhamentoMensalResponse)
def get_gtin_ranking(
    cnpj: str,
    periodo: str = Query(..., description="Período no formato 'YYYY-MM' ou 'YYYY-S1'")
):
    """Retorna o ranking de GTINs infratores para um período específico (Raio-X Mensal)."""
    return AnalyticsService.get_gtin_ranking_periodo(cnpj, periodo)

@router.get("/cnpj/{cnpj}/indicadores", response_model=IndicadoresResponse)
def get_indicadores(
    cnpj: str,
    data_inicio: Optional[date] = Query(None),
    data_fim: Optional[date] = Query(None),
):
    """Retorna os indicadores detalhados para um CNPJ."""
    return AnalyticsService.get_indicadores(cnpj, data_inicio=data_inicio, data_fim=data_fim)

@router.get("/cnpj/{cnpj}/indicadores/{indicador}/benchmark-local", response_model=IndicadorBenchmarkResponse)
def get_indicador_benchmark_local(
    cnpj: str,
    indicador: str,
    data_inicio: Optional[date] = Query(None),
    data_fim: Optional[date] = Query(None),
):
    """Retorna comparação municipal e regional para indicadores com detalhamento generico."""
    return AnalyticsService.get_indicador_benchmark_local(
        cnpj,
        indicador,
        data_inicio=data_inicio,
        data_fim=data_fim,
    )

@router.get("/cnpj/{cnpj}/indicadores/{indicador}/evolucao-benchmark", response_model=IndicadorEvolucaoBenchmarkResponse)
def get_indicador_evolucao_benchmark(
    cnpj: str,
    indicador: str,
    data_inicio: Optional[date] = Query(None),
    data_fim: Optional[date] = Query(None),
):
    """Retorna evolucao anual da farmacia contra regiao, UF e Brasil."""
    return AnalyticsService.get_indicador_evolucao_benchmark(
        cnpj,
        indicador,
        data_inicio=data_inicio,
        data_fim=data_fim,
    )

@router.get("/cnpj/{cnpj}/geografico/origem-uf", response_model=GeograficoOrigemUfResponse)
def get_geografico_origem_uf(
    cnpj: str,
    data_inicio: Optional[date] = Query(None),
    data_fim: Optional[date] = Query(None),
):
    """Retorna a distribuicao financeira por UF de residencia do beneficiario."""
    return AnalyticsService.get_geografico_origem_uf(cnpj, data_inicio=data_inicio, data_fim=data_fim)

@router.get("/cnpj/{cnpj}/geografico/benchmark-local", response_model=GeograficoBenchmarkResponse)
def get_geografico_benchmark_local(
    cnpj: str,
    data_inicio: Optional[date] = Query(None),
    data_fim: Optional[date] = Query(None),
):
    """Retorna comparação municipal e regional do indicador de dispersao interestadual."""
    return AnalyticsService.get_geografico_benchmark_local(
        cnpj,
        data_inicio=data_inicio,
        data_fim=data_fim,
    )

@router.get("/cnpj/{cnpj}/clinico/incompatibilidades", response_model=ClinicoIncompatibilidadeResponse)
def get_incompatibilidade_patologica(
    cnpj: str,
    data_inicio: Optional[date] = Query(None),
    data_fim: Optional[date] = Query(None),
    ranking_municipal_limite: int = Query(10, ge=0),
):
    """Retorna o detalhamento clinico/patologico por recorte monitorado."""
    return AnalyticsService.get_incompatibilidade_patologica_data(
        cnpj,
        data_inicio=data_inicio,
        data_fim=data_fim,
        ranking_municipal_limite=ranking_municipal_limite,
    )

@router.get("/cnpj/{cnpj}/falecidos", response_model=FalecidosResponse)
def get_falecidos(
    cnpj: str,
    data_inicio: Optional[date] = Query(None),
    data_fim:    Optional[date] = Query(None),
):
    """Retorna os dados detalhados de vendas para falecidos de um CNPJ."""
    return AnalyticsService.get_falecidos_data(cnpj, data_inicio, data_fim)

@router.get("/rede/{cnpj_raiz}", response_model=List[RedeEstabelecimentoSchema])
def get_rede_estabelecimentos(cnpj_raiz: str):
    """Retorna todos os estabelecimentos de uma rede dado o CNPJ raiz (8 dígitos)."""
    raiz = cnpj_raiz.replace(".", "").replace("/", "").replace("-", "")[:8]
    return AnalyticsService.get_rede_por_cnpj_raiz(raiz)

@router.get("/cpf/{cpf}/timeline", response_model=MultiCnpjTimelineResponse)
def get_cpf_timeline(
    cpf: str,
    cnpj: str = Query(..., description="CNPJ de referência (estabelecimento de origem)")
):
    """
    Retorna todas as transações reais de um CPF falecido em todos os estabelecimentos
    detectados. Usado no Mapa de Trilhas Temporais (Audit History).
    """
    return AnalyticsService.get_timeline_cpf(cnpj_referencia=cnpj, cpf=cpf)

@router.get("/regional-benchmarking", response_model=RegionalResponse)
def get_regional_benchmarking(
    uf: Optional[str] = Query(None, description="Sigla do Estado (ex: 'SC')"),
    data_inicio: Optional[date] = Query(None),
    data_fim: Optional[date] = Query(None),
    regiao_id: Optional[int] = Query(None),
):
    """
    Retorna o resumo municipal e o ranking de farmácias por risco (Benchmarking Regional).
    - Com regiao_id: filtra pela região de saúde.
    - Sem regiao_id: filtra por UF inteiro (escopo estadual).
    """
    return AnalyticsService.get_regional_benchmarking(
        uf=uf, 
        data_inicio=data_inicio, 
        data_fim=data_fim, 
        regiao_id=regiao_id
    )


@router.get("/regional-benchmarking-animation", response_model=RegionalAnimationResponse)
def get_regional_benchmarking_animation(
    uf: Optional[str] = Query(None, description="Sigla do Estado (ex: 'SC')"),
    data_inicio: Optional[date] = Query(None),
    data_fim: Optional[date] = Query(None),
    regiao_id: Optional[int] = Query(None),
):
    """
    Retorna todos os trimestres do período em uma única chamada.
    Usado pela animação do scatter de posicionamento regional — evita N round-trips.
    """
    return AnalyticsService.get_regional_benchmarking_animation(
        uf=uf, 
        data_inicio=data_inicio, 
        data_fim=data_fim, 
        regiao_id=regiao_id
    )


@router.get("/cnpj/{cnpj}/crm-data", response_model=PrescritoresResponse)
def get_crm_data_endpoint(
    cnpj: str,
    data_inicio: Optional[str] = Query(None, description="Início do período (YYYY-MM)"),
    data_fim:    Optional[str] = Query(None, description="Fim do período (YYYY-MM)"),
):
    """Retorna KPIs e top prescritores (CRMs) de um CNPJ, com filtro opcional de período."""
    return AnalyticsService.get_crm_data(cnpj, data_inicio=data_inicio, data_fim=data_fim)


@router.get("/cnpj/{cnpj}/crm/medico-alertas/{id_medico:path}", response_model=CrmMedicoAlertasResponse)
def get_crm_medico_alertas(
    cnpj: str,
    id_medico: str,
    data_inicio: Optional[str] = Query(None, description="Início do período (YYYY-MM)"),
    data_fim:    Optional[str] = Query(None, description="Fim do período (YYYY-MM)"),
):
    """Retorna alertas detalhados de um CRM especifico sob demanda."""
    return AnalyticsService.get_crm_medico_alertas(cnpj, id_medico, data_inicio=data_inicio, data_fim=data_fim)

@router.get("/cnpj/{cnpj}/crm/timeline-dataset", response_model=CrmTimelineDatasetResponse)
def get_crm_timeline_dataset(
    cnpj: str,
    data_inicio: Optional[str] = Query(None, description="Inicio do periodo (YYYY-MM-DD ou YYYY-MM)"),
    data_fim:    Optional[str] = Query(None, description="Fim do periodo (YYYY-MM-DD ou YYYY-MM)"),
):
    """Retorna o dataset semantico da linha do tempo CRM, agrupado por dia."""
    return AnalyticsService.get_crm_timeline_dataset(cnpj, data_inicio=data_inicio, data_fim=data_fim)


@router.get("/cnpj/{cnpj}/crm/raio-x", response_model=CrmRaioXResponse)
def get_crm_raio_x(
    cnpj: str,
    date_str: str = Query(..., description="Data da janela de auditoria (YYYY-MM-DD)"),
    hour: Optional[int] = Query(None, description="Hora da anomalia (0-23)")
):
    """Retorna o raio-x (transação literal) de uma hora específica ou do dia inteiro se a hora for omitida."""
    return AnalyticsService.get_crm_raio_x(cnpj, date_str, hour)


@router.get("/indicadores-analise", response_model=IndicadorAnaliseResponse)
def get_indicadores_analise(
    indicador: str = Query(..., description="Chave do indicador (ex: 'auditado', 'teto', 'vendas_rapidas')"),
    data_inicio: Optional[date] = Query(None),
    data_fim: Optional[date] = Query(None),
    uf: Optional[str] = Query(None),
    regiao_saude: Optional[str] = Query(None),
    municipio: Optional[str] = Query(None),
    id_ibge7: Optional[int] = Query(None),
    situacao_rf: Optional[str] = Query(None),
    conexao_ms: Optional[str] = Query(None),
    porte_empresa: Optional[str] = Query(None),
    grande_rede: Optional[str] = Query(None),
    cnpj_raiz: Optional[str] = Query(None),
    estabelecimento: Optional[str] = Query(None),
    unidade_pf: Optional[str] = Query(None),
    perc_min: Optional[float] = Query(None),
    perc_max: Optional[float] = Query(None),
    val_min: Optional[float] = Query(None),
    regiao_id: Optional[int] = Query(None),
    par_teia: Optional[str] = Query(None),
    socio_beneficio: Optional[str] = Query(None),
    socio_esocial: Optional[str] = Query(None),
    cnae_incompativel: bool = Query(False),
    socio_idade_atipica: bool = Query(False),
    socio_falecido: bool = Query(False),
    dispersao_uf_sem_fronteira: bool = Query(False),
    dispersao_uf_sem_fronteira_limite: Optional[float] = Query(None),
    volume_atipico: bool = Query(False),
    volume_atipico_limite: Optional[float] = Query(None)
):
    """
    Análise cruzada de um indicador: retorna KPIs, mapa municipal e CNPJs ranqueados.
    Aplica filtros cadastrais/geográficos, período, aumento semestral atípico e limites de valor/percentual.
    """
    if regiao_saude and regiao_saude != "Todos":
        raise HTTPException(status_code=400, detail="Use regiao_id para filtros regionais; regiao_saude textual e apenas label.")
    if municipio and municipio != "Todos":
        raise HTTPException(status_code=400, detail="Use id_ibge7 para filtros municipais; municipio textual e apenas label.")
    return AnalyticsService.get_indicadores_analise(
        indicador, data_inicio, data_fim, uf, regiao_saude, municipio,
        situacao_rf, conexao_ms, porte_empresa, grande_rede, cnpj_raiz, estabelecimento, unidade_pf,
        perc_min=perc_min, perc_max=perc_max, val_min=val_min, regiao_id=regiao_id, id_ibge7=id_ibge7, par_teia=par_teia,
        socio_beneficio=socio_beneficio, socio_esocial=socio_esocial, cnae_incompativel=cnae_incompativel, socio_idade_atipica=socio_idade_atipica, socio_falecido=socio_falecido,
        dispersao_uf_sem_fronteira=dispersao_uf_sem_fronteira,
        dispersao_uf_sem_fronteira_limite=dispersao_uf_sem_fronteira_limite,
        volume_atipico=volume_atipico, volume_atipico_limite=volume_atipico_limite
    )


@router.get("/indicadores-analise/cnpjs", response_model=IndicadorCnpjPageResponse)
def get_indicadores_analise_cnpjs(
    indicador: str = Query(..., description="Chave do indicador (ex: 'percentual_nao_comprovacao', 'teto')"),
    data_inicio: Optional[date] = Query(None),
    data_fim: Optional[date] = Query(None),
    uf: Optional[str] = Query(None),
    regiao_saude: Optional[str] = Query(None),
    municipio: Optional[str] = Query(None),
    id_ibge7: Optional[int] = Query(None),
    situacao_rf: Optional[str] = Query(None),
    conexao_ms: Optional[str] = Query(None),
    porte_empresa: Optional[str] = Query(None),
    grande_rede: Optional[str] = Query(None),
    cnpj_raiz: Optional[str] = Query(None),
    estabelecimento: Optional[str] = Query(None),
    unidade_pf: Optional[str] = Query(None),
    perc_min: Optional[float] = Query(None),
    perc_max: Optional[float] = Query(None),
    val_min: Optional[float] = Query(None),
    regiao_id: Optional[int] = Query(None),
    par_teia: Optional[str] = Query(None),
    socio_beneficio: Optional[str] = Query(None),
    socio_esocial: Optional[str] = Query(None),
    cnae_incompativel: bool = Query(False),
    socio_idade_atipica: bool = Query(False),
    socio_falecido: bool = Query(False),
    dispersao_uf_sem_fronteira: bool = Query(False),
    dispersao_uf_sem_fronteira_limite: Optional[float] = Query(None),
    volume_atipico: bool = Query(False),
    volume_atipico_limite: Optional[float] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    sort_field: str = Query("val_sem_comp"),
    sort_order: str = Query("desc"),
):
    """Retorna uma pagina server-side da tabela de CNPJs de /indicadores."""
    if regiao_saude and regiao_saude != "Todos":
        raise HTTPException(status_code=400, detail="Use regiao_id para filtros regionais; regiao_saude textual e apenas label.")
    if municipio and municipio != "Todos":
        raise HTTPException(status_code=400, detail="Use id_ibge7 para filtros municipais; municipio textual e apenas label.")
    return AnalyticsService.get_indicadores_analise_cnpjs(
        indicador, data_inicio, data_fim, uf, regiao_saude, municipio,
        situacao_rf, conexao_ms, porte_empresa, grande_rede, cnpj_raiz, estabelecimento, unidade_pf,
        perc_min=perc_min, perc_max=perc_max, val_min=val_min, regiao_id=regiao_id,
        id_ibge7=id_ibge7, par_teia=par_teia, socio_beneficio=socio_beneficio, socio_esocial=socio_esocial, cnae_incompativel=cnae_incompativel, socio_idade_atipica=socio_idade_atipica, socio_falecido=socio_falecido, dispersao_uf_sem_fronteira=dispersao_uf_sem_fronteira, dispersao_uf_sem_fronteira_limite=dispersao_uf_sem_fronteira_limite, page=page, page_size=page_size,
        sort_field=sort_field, sort_order=sort_order,
        volume_atipico=volume_atipico, volume_atipico_limite=volume_atipico_limite
    )


@router.get("/cnpj/{cnpj}/movimentacao", response_model=MovimentacaoResponse)
def get_movimentacao(
    cnpj: str,
    check_cache: bool = Query(False, description="Se True, retorna vazio caso não exista cache no servidor.")
):
    """
    Retorna a Memória de Cálculo processada (Movimentação por GTIN) de um CNPJ.

    - **Primeira chamada**: busca do SQL Server (`memoria_calculo_consolidada`),
      processa a lógica de linhas e salva cache Parquet.
    - **Chamadas subsequentes**: carrega do cache Parquet local (< 1s).
    - **Parâmetro check_cache**: permite carregar apenas se já existir cache, sem disparar processamento.
    """
    return AnalyticsService.get_movimentacao_data(cnpj, engine, check_cache=check_cache)
@router.get("/cnpj-lookup")
def get_cnpj_lookup():
    """Retorna lista slim [{cnpj, razao_social}] para autocomplete no frontend."""
    return AnalyticsService.get_cnpj_lookup()

@router.get("/metric-percentiles-animation", response_model=PercentilesAnimationResponse)
def get_metric_percentiles_animation(
    scope: str = Query(..., description="Escopo: 'regiao', 'uf' ou 'brasil'"),
    uf: Optional[str] = Query(None),
    regiao_id: Optional[str] = Query(None),
    metric: str = Query("score", description="Métrica: 'score' ou 'percentual_sem_comprovacao'"),
    data_inicio: Optional[date] = Query(None),
    data_fim: Optional[date] = Query(None),
):
    """Retorna percentis por janela de 2 meses para animação da curva de risco — uma única chamada."""
    return AnalyticsService.get_metric_percentiles_animation(scope, uf, regiao_id, metric, data_inicio, data_fim)


@router.get("/metric-percentiles")
def get_metric_percentiles(
    scope: str = Query(..., description="Escopo: 'regiao', 'uf' ou 'brasil'"),
    uf: Optional[str] = Query(None),
    regiao_id: Optional[str] = Query(None),
    metric: str = Query("score", description="Métrica: 'score' ou 'percentual_sem_comprovacao'"),
    data_inicio: Optional[date] = Query(None),
    data_fim: Optional[date] = Query(None),
):
    """Retorna os percentis de score de risco ou não comprovação para o escopo selecionado."""
    return AnalyticsService.get_metric_percentiles(scope, uf, regiao_id, metric, data_inicio, data_fim)


@router.get("/nota-tecnica/regionais")
def get_nota_tecnica_regionais():
    """Lista as regionais emissoras disponíveis para a Nota Técnica."""
    return AnalyticsService.list_nota_tecnica_regionais()


@router.get("/cnpj/{cnpj}/nota-tecnica/readiness", response_model=NotaTecnicaReadinessResponse)
def get_nota_tecnica_readiness(
    cnpj: str,
    data_inicio: Optional[date] = Query(None),
    data_fim: Optional[date] = Query(None),
):
    """Verifica se todos os modulos de cache obrigatorios para a Nota Tecnica estao prontos."""
    try:
        return AnalyticsService.get_nota_tecnica_readiness(cnpj, data_inicio, data_fim)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/cnpj/{cnpj}/nota-tecnica/prepare", response_model=NotaTecnicaPrepareResponse)
def prepare_nota_tecnica(
    cnpj: str,
    data_inicio: Optional[date] = Query(None),
    data_fim: Optional[date] = Query(None),
):
    """Materializa sob demanda os modulos por CNPJ exigidos pela Nota Tecnica."""
    try:
        return AnalyticsService.prepare_nota_tecnica_cnpj(cnpj, engine, data_inicio, data_fim)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/cnpj/{cnpj}/relatorio-pdf/readiness", response_model=NotaTecnicaReadinessResponse)
def get_relatorio_pdf_readiness(
    cnpj: str,
    data_inicio: Optional[date] = Query(None),
    data_fim: Optional[date] = Query(None),
):
    """Verifica se todos os modulos de cache obrigatorios para o relatorio PDF estao prontos."""
    try:
        return AnalyticsService.get_relatorio_pdf_readiness(cnpj, data_inicio, data_fim)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/cnpj/{cnpj}/relatorio-pdf/prepare", response_model=NotaTecnicaPrepareResponse)
def prepare_relatorio_pdf(
    cnpj: str,
    data_inicio: Optional[date] = Query(None),
    data_fim: Optional[date] = Query(None),
):
    """Materializa sob demanda os modulos por CNPJ exigidos pelo relatorio PDF."""
    try:
        return AnalyticsService.prepare_relatorio_pdf_cnpj(cnpj, engine, data_inicio, data_fim)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/cnpj/{cnpj}/nota-tecnica")
def get_nota_tecnica(
    cnpj: str,
    data_inicio: Optional[date] = Query(None),
    data_fim: Optional[date] = Query(None),
    regional_codigo: str = Query(...),
    numero_nota: Optional[str] = Query(None),
    numero_processo: Optional[str] = Query(None),
    assinantes_tecnicos: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    """Gera e retorna o download da Nota Técnica Preliminar (.docx)."""
    try:
        readiness = AnalyticsService.get_nota_tecnica_readiness(cnpj, data_inicio, data_fim)
        if not readiness["ready"]:
            missing = ", ".join(module["label"] for module in readiness["missing_modules"])
            raise RuntimeError(f"Nota Tecnica indisponivel. Modulos pendentes: {missing}.")

        docx_started = time.perf_counter()
        file_stream = AnalyticsService.generate_nota_tecnica(
            db,
            cnpj,
            data_inicio,
            data_fim,
            regional_codigo,
            numero_nota,
            numero_processo,
            _parse_assinantes_tecnicos_param(assinantes_tecnicos),
        )
        docx_elapsed_ms = round((time.perf_counter() - docx_started) * 1000, 2)
        logger.bind(sentinela_log="request_timing").info(
            "cnpj={} | nota_tecnica_docx | params={} | tempo_ms={}",
            cnpj,
            {
                "data_inicio": data_inicio.isoformat() if data_inicio else None,
                "data_fim": data_fim.isoformat() if data_fim else None,
                "regional_codigo": regional_codigo,
            },
            docx_elapsed_ms,
        )
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        tb_str = traceback.format_exc()
        logger.bind(sentinela_log="nota_tecnica_error").error(
            "cnpj={} | erro inesperado ao gerar Nota Tecnica\n{}",
            cnpj,
            tb_str,
        )
        last_frames = traceback.format_tb(exc.__traceback__)
        last_frame = last_frames[-1] if last_frames else ""
        detail = (
            f"Erro inesperado ao gerar Nota Tecnica: {exc}\n\n"
            f"Arquivo: {last_frame}"
        )
        raise HTTPException(status_code=500, detail=detail) from exc
    
    filename = f"Nota_Tecnica_{cnpj}_{date.today().isoformat()}.docx"
    # Encode filename for header
    safe_filename = urllib.parse.quote(filename)
    
    return StreamingResponse(
        file_stream,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{safe_filename}"}
    )
