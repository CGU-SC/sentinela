from pydantic import BaseModel, Field
from typing import Dict, List, Literal, Optional
from datetime import date, datetime

class AnalyticsKPISchema(BaseModel):
    id: str
    label: str
    value: str
    color: str
    icon: str

class ResultadoSentinelaUFSchema(BaseModel):
    uf: Optional[str] = "ND"
    cnpjs: Optional[int] = 0
    percValSemComp: Optional[float] = 0.0
    valSemComp: Optional[float] = 0.0
    totalMov: Optional[float] = 0.0
    percQtdeSemComp: Optional[float] = 0.0
    qtdeSemComp: Optional[int] = 0
    totalQtde: Optional[int] = 0

class ResultadoSentinelaMunicipioSchema(BaseModel):
    uf: Optional[str] = "ND"
    municipio: Optional[str] = "ND"
    id_ibge7: Optional[int] = None
    cnpjs: Optional[int] = 0
    percValSemComp: Optional[float] = 0.0
    valSemComp: Optional[float] = 0.0
    totalMov: Optional[float] = 0.0
    percQtdeSemComp: Optional[float] = 0.0
    qtdeSemComp: Optional[int] = 0
    totalQtde: Optional[int] = 0
    populacao: Optional[int] = 0
    densidade: Optional[float] = 0.0


class ResultadoSentinelaCnpjSchema(BaseModel):
    municipio_uf: str
    cnpj: str
    razao_social: Optional[str] = None
    nome_fantasia: Optional[str] = None
    totalMov: float = 0.0
    valSemComp: float = 0.0
    percValSemComp: Optional[float] = 0.0
    totalQtde: Optional[int] = 0
    qtdeSemComp: Optional[int] = 0
    percQtdeSemComp: Optional[float] = 0.0
    is_grande_rede: Optional[bool] = False
    qtd_estabelecimentos_rede: Optional[int] = 0
    situacao_rf: Optional[str] = "ND"
    porte_empresa: Optional[str] = "ND"
    is_conexao_ativa: Optional[bool] = False
    is_matriz: Optional[bool] = False
    id_ibge7: Optional[int] = None
    score_risco_final: Optional[float] = None
    classificacao_risco: Optional[str] = None
    data_ultima_venda: Optional[date] = None
    municipio: Optional[str] = None
    uf: Optional[str] = None
    rank_nacional: Optional[int] = None
    total_nacional: Optional[int] = None
    rank_uf: Optional[int] = None
    total_uf: Optional[int] = None
    rank_regiao_saude: Optional[int] = None
    total_regiao_saude: Optional[int] = None
    rank_municipio: Optional[int] = None
    total_municipio: Optional[int] = None

class RedeEstabelecimentoSchema(BaseModel):
    cnpj_raiz: str
    cnpj: str
    razao_social: Optional[str] = None
    uf: Optional[str] = None
    municipio: Optional[str] = None
    is_matriz: Optional[bool] = False
    qtd_estabelecimentos_rede: Optional[int] = 0
    is_grande_rede: Optional[bool] = False

class AnalyticsResponse(BaseModel):
    # Cada secao so vem preenchida quando pedida em `secoes`; as demais sao None.
    kpis: Optional[List[AnalyticsKPISchema]] = None
    resultado_sentinela_uf: Optional[List[ResultadoSentinelaUFSchema]] = None
    resultado_municipios: Optional[List[ResultadoSentinelaMunicipioSchema]] = None
    resultado_cnpjs: Optional[List[ResultadoSentinelaCnpjSchema]] = None


class ProducaoSemestralPointSchema(BaseModel):
    semestre: str
    chave_semestre: int
    valor_producao: float = 0.0
    valor_regular: float = 0.0
    valor_sem_comprovacao: float = 0.0
    pct_sem_comprovacao: float = 0.0
    cnpjs: int = 0


class ProducaoSemestralResponse(BaseModel):
    pontos: List[ProducaoSemestralPointSchema]


class RegionalMunicipioSchema(BaseModel):
    """Resumo de um município dentro da Região de Saúde selecionada."""
    uf: Optional[str] = "ND"
    municipio: Optional[str] = "ND"
    id_ibge7: Optional[int] = None
    populacao: Optional[int] = 0
    qtd_farmacias: Optional[int] = 0
    densidade: Optional[float] = 0.0
    totalMov: Optional[float] = 0.0
    valSemComp: Optional[float] = 0.0
    percValSemComp: Optional[float] = 0.0


class RegionalFarmaciaSchema(BaseModel):
    """Dados de uma farmácia no ranking regional de risco."""
    cnpj: str
    razao_social: Optional[str] = None
    municipio: Optional[str] = None
    id_ibge7: Optional[int] = None
    uf: Optional[str] = None
    score_risco: Optional[float] = None
    classificacao_risco: Optional[str] = None
    valSemComp: Optional[float] = 0.0
    totalMov: Optional[float] = 0.0
    percValSemComp: Optional[float] = 0.0
    is_conexao_ativa: Optional[bool] = False
    data_ultima_venda: Optional[date] = None
    rank: Optional[int] = None


class RegionalResponse(BaseModel):
    """Payload completo da aba Região de Saúde."""
    nome_regiao: str
    id_regiao: Optional[str] = None
    municipios: List[RegionalMunicipioSchema]
    farmacias: List[RegionalFarmaciaSchema]


class RegionalAnimationQuarterSchema(BaseModel):
    """Dados de uma janela móvel trimestral para animação do scatter regional."""
    trimestre: str          # mantido por compatibilidade; representa o mês inicial da janela
    inicio: date
    fim: date
    farmacias: List[RegionalFarmaciaSchema]


class RegionalAnimationResponse(BaseModel):
    """Payload completo para animação — todas as janelas móveis em uma única chamada."""
    nome_regiao: str
    quarters: List[RegionalAnimationQuarterSchema]


class PercentilesPointSchema(BaseModel):
    percentile: int
    score: float

class PercentilesQuarterSchema(BaseModel):
    """Dados de percentis de uma janela móvel trimestral para animação da curva de risco."""
    inicio: date
    fim: date
    percentiles: List[PercentilesPointSchema]

class PercentilesAnimationResponse(BaseModel):
    """Payload completo de percentis por período — todos os períodos em uma única chamada."""
    quarters: List[PercentilesQuarterSchema]

class EvolucaoMesSchema(BaseModel):
    mes: str
    total: float
    regular: float
    irregular: float
    pct_irregular: float

class EvolucaoSemestreSchema(BaseModel):
    semestre: str
    total: float
    regular: float
    irregular: float
    pct_irregular: float
    mes_inicio: Optional[str] = None  # "YYYY-MM" — mês mais antigo no grupo (pode ser parcial)
    mes_fim: Optional[str] = None     # "YYYY-MM" — mês mais recente no grupo
    chave_semestre: Optional[int] = None
    volume_atipico: bool = False
    taxa_crescimento_pct: Optional[float] = None
    chave_semestre_anterior: Optional[int] = None
    aumento_valor_semestre: Optional[float] = None
    status_semestre: Optional[int] = None
    qtd_meses_presentes: Optional[int] = None
    limite_volume_atipico_pct: Optional[float] = None
    limite_aumento_volume_atipico: Optional[float] = None
    meses: List[EvolucaoMesSchema] = []

class EvolucaoFinanceiraResponse(BaseModel):
    cnpj: str
    semestres: List[EvolucaoSemestreSchema]

class FatorRiscoBucketSchema(BaseModel):
    faixa: str
    qtd: int
    valor: str
    valor_raw: float

class FatorRiscoResponseSchema(BaseModel):
    periodo_formatado: str
    buckets: List[FatorRiscoBucketSchema]

class FalecidoTransactionSchema(BaseModel):
    cpf: str
    nome_falecido: Optional[str] = None
    municipio_falecido: Optional[str] = None
    uf_falecido: Optional[str] = None
    dt_nascimento: Optional[date] = None
    dt_obito: Optional[date] = None
    fonte_obito: Optional[str] = None
    num_autorizacao: Optional[str] = None
    data_autorizacao: Optional[date] = None
    qtd_itens_na_autorizacao: int = 0
    valor_total_autorizacao: float = 0.0
    dias_apos_obito: int = 0
    outros_estabelecimentos: Optional[str] = None

class FalecidosRankingSchema(BaseModel):
    # Cadastro estruturado da farmacia (perfil de estabelecimentos, obrigatorio).
    cnpj: str
    razao_social: str
    municipio: str
    uf: str
    # Rotulo "cnpj - razao | municipio/UF" (exportacoes e PDF).
    estabelecimento: str
    qtd_cpfs: int
    pct_total: float

class FalecidosSummarySchema(BaseModel):
    cpfs_distintos: int
    total_autorizacoes: int
    valor_total: float
    media_dias: float
    max_dias: int
    pct_faturamento: float
    cpfs_multi_cnpj: int
    pct_multi_cnpj: float

class FalecidosResponse(BaseModel):
    cnpj: str
    summary: FalecidosSummarySchema
    ranking: List[FalecidosRankingSchema]
    transacoes: List[FalecidoTransactionSchema]
    from_cache: bool = False
    tem_historico: bool = False
    query_time_ms: Optional[float] = None
    save_time_ms: Optional[float] = None
    read_time_ms: Optional[float] = None

class IndicadorDataSchema(BaseModel):
    valor: Optional[float] = None
    valor_aumento_atipico: Optional[float] = None
    valor_financeiro: Optional[float] = None
    pode_detalhar: bool = False
    med_reg: Optional[float] = None
    med_uf: Optional[float] = None
    med_br: Optional[float] = None
    med_benchmark: Optional[float] = None
    benchmark_escopo: Optional[str] = None
    risco_reg: Optional[float] = None
    risco_uf: Optional[float] = None
    risco_br: Optional[float] = None
    risco_benchmark: Optional[float] = None
    status: str = "SEM DADOS"

class IndicadoresResponse(BaseModel):
    cnpj: str
    indicadores: Dict[str, IndicadorDataSchema]

# ── Multi-CNPJ Timeline (Audit History) ──────────────────
class GeograficoOrigemUfRowSchema(BaseModel):
    uf_farmacia: str
    uf_paciente: str
    is_outra_uf: bool
    qtd_autorizacoes: int
    valor_autorizado: float
    percentual_sobre_total: float
    percentual_sobre_outra_uf: Optional[float] = None

class GeograficoOrigemUfResponse(BaseModel):
    cnpj: str
    uf_farmacia: str
    periodo_inicio: Optional[date] = None
    periodo_fim: Optional[date] = None
    total_valor_origem: float
    total_valor_outra_uf: float
    total_autorizacoes_origem: int
    total_autorizacoes_outra_uf: int
    percentual_financeiro_outra_uf: float
    principal_uf_externa: Optional[GeograficoOrigemUfRowSchema] = None
    rows: List[GeograficoOrigemUfRowSchema]


class GeograficoBenchmarkRowSchema(BaseModel):
    cnpj: str
    razao_social: Optional[str] = None
    nome_fantasia: Optional[str] = None
    municipio: Optional[str] = None
    uf: Optional[str] = None
    percentual_outra_uf: Optional[float] = None
    valor_total: float
    valor_outra_uf: float
    qtd_vendas_outra_uf: int
    mediana_regiao: Optional[float] = None
    mediana_uf: Optional[float] = None
    risco_regiao: Optional[float] = None
    risco_uf: Optional[float] = None
    status: str
    is_alvo: bool = False


class GeograficoBenchmarkScopeSchema(BaseModel):
    escopo: Literal["municipio", "regiao_saude"]
    label: str
    total_estabelecimentos: int
    rows: List[GeograficoBenchmarkRowSchema]


class GeograficoBenchmarkResponse(BaseModel):
    cnpj: str
    periodo_inicio: Optional[date] = None
    periodo_fim: Optional[date] = None
    municipio: GeograficoBenchmarkScopeSchema
    regiao_saude: GeograficoBenchmarkScopeSchema


class IndicadorBenchmarkKpiSchema(BaseModel):
    label: str
    value: Optional[float] = None
    formato: str


class IndicadorBenchmarkRowSchema(BaseModel):
    cnpj: str
    razao_social: Optional[str] = None
    municipio: Optional[str] = None
    uf: Optional[str] = None
    is_conexao_ativa: bool
    is_matriz: bool
    valor: Optional[float] = None
    valor_financeiro: Optional[float] = None
    valor_movimentado: Optional[float] = None
    valor_sem_comprovacao: Optional[float] = None
    percentual_nao_comprovacao: Optional[float] = None
    mediana_regiao: Optional[float] = None
    mediana_uf: Optional[float] = None
    risco_regiao: Optional[float] = None
    risco_uf: Optional[float] = None
    status: str
    is_alvo: bool = False
    valor_numerador: Optional[float] = None
    valor_denominador: Optional[float] = None


class IndicadorBenchmarkScopeSchema(BaseModel):
    escopo: Literal["municipio", "regiao_saude"]
    label: str
    total_estabelecimentos: int
    rows: List[IndicadorBenchmarkRowSchema]


class IndicadorBenchmarkResponse(BaseModel):
    cnpj: str
    indicador: str
    periodo_inicio: Optional[date] = None
    periodo_fim: Optional[date] = None
    kpis: List[IndicadorBenchmarkKpiSchema]
    municipio: IndicadorBenchmarkScopeSchema
    regiao_saude: IndicadorBenchmarkScopeSchema


class IndicadorEvolucaoBenchmarkPointSchema(BaseModel):
    ano_base: int
    farmacia: Optional[float] = None
    regiao_saude: Optional[float] = None
    uf: Optional[float] = None
    valor_numerador: Optional[float] = None
    valor_denominador: Optional[float] = None
    valor_movimentado: Optional[float] = None
    valor_sem_comprovacao: Optional[float] = None
    percentual_nao_comprovacao: Optional[float] = None


class IndicadorEvolucaoBenchmarkPeriodoSchema(BaseModel):
    ano_inicio: Optional[int] = None
    ano_fim: Optional[int] = None
    anos: List[int]


class IndicadorEvolucaoBenchmarkResponse(BaseModel):
    cnpj: str
    indicador: str
    formato: str
    periodo_inicio: Optional[date] = None
    periodo_fim: Optional[date] = None
    periodo_marcado: IndicadorEvolucaoBenchmarkPeriodoSchema
    series: List[IndicadorEvolucaoBenchmarkPointSchema]


class ClinicoEvolucaoAnualSchema(BaseModel):
    ano_base: int
    qtd_cpfs_distintos: int
    qtd_cpfs_incompativeis: int
    qtd_autorizacoes: int
    qtd_autorizacoes_incompativeis: int
    valor_total_pago: float
    valor_incompativel_pago: float
    percentual_cpfs_incompativeis: float
    percentual_autorizacoes_incompativeis: Optional[float] = None


class ClinicoMunicipalResumoRowSchema(BaseModel):
    grupo: str
    qtd_farmacias: int
    qtd_cpfs_distintos: int
    qtd_cpfs_incompativeis: int
    qtd_autorizacoes_incompativeis: int
    valor_incompativel_pago: float
    participacao_valor_municipal: Optional[float] = None


class ClinicoMunicipalRankingRowSchema(BaseModel):
    posicao: int
    id_cnpj: int
    cnpj: str
    razao_social: str
    is_alvo: bool
    qtd_autorizacoes: int
    qtd_autorizacoes_incompativeis: int
    valor_total_pago: float
    valor_incompativel_pago: float
    participacao_municipal: Optional[float] = None


class ClinicoFaixaEtariaSchema(BaseModel):
    faixa: str
    faixa_inicio: int
    populacao: int
    percentual: float
    destacar_50_mais: bool


class ClinicoParkinsonDemografiaSchema(BaseModel):
    municipio: str
    uf: str
    ano_censo: int
    ano_observado: int
    prevalencia_50_mais: float
    populacao_total: int
    populacao_50_mais: int
    casos_esperados: float
    cpfs_observados: int
    razao_observado_esperado: Optional[float] = None
    faixas_etarias: List[ClinicoFaixaEtariaSchema]


class ClinicoPatologiaSchema(BaseModel):
    patologia: str
    regra_clinica: str
    titulo: str
    objeto: str
    criterio: str
    descricao: str
    ano_inicio: int
    ano_fim: int
    qtd_cpfs_distintos: int
    qtd_cpfs_incompativeis: int
    qtd_autorizacoes: int
    qtd_autorizacoes_incompativeis: int
    valor_total_pago: float
    valor_incompativel_pago: float
    percentual_medio_cpfs_incompativeis: float
    percentual_medio_regional_cpfs_incompativeis: Optional[float] = None
    razao_media_percentual_vs_regiao: Optional[float] = None
    excesso_cpfs_incompativeis_vs_regiao: Optional[float] = None
    melhor_rank_regional_qtd_cpfs_incompativeis: Optional[int] = None
    maior_percentil_regional_qtd_cpfs_incompativeis: Optional[float] = None
    maior_participacao_cpfs_incompativeis_regiao: Optional[float] = None
    evolucao_anual: List[ClinicoEvolucaoAnualSchema]
    municipal_resumo: List[ClinicoMunicipalResumoRowSchema]
    ranking_municipal: List[ClinicoMunicipalRankingRowSchema]
    demografia_parkinson: Optional[ClinicoParkinsonDemografiaSchema] = None


class ClinicoIncompatibilidadeSummarySchema(BaseModel):
    qtd_cpfs_distintos: int
    qtd_cpfs_incompativeis: int
    qtd_autorizacoes: int
    qtd_autorizacoes_incompativeis: int
    valor_total_pago: float
    valor_incompativel_pago: float
    percentual_valor_incompativel: Optional[float] = None


class ClinicoIncompatibilidadeResponse(BaseModel):
    cnpj: str
    razao_social: str
    municipio: str
    uf: str
    periodo_inicio: Optional[date] = None
    periodo_fim: Optional[date] = None
    periodo_label: str
    summary: ClinicoIncompatibilidadeSummarySchema
    patologias: List[ClinicoPatologiaSchema]

class TimelineEventSchema(BaseModel):
    cnpj: str
    razao_social: Optional[str] = None
    municipio: Optional[str] = None
    uf: Optional[str] = None
    data_autorizacao: Optional[date] = None
    valor_total_autorizacao: float = 0.0
    num_autorizacao: Optional[str] = None
    is_this_cnpj: bool = False

class MultiCnpjTimelineResponse(BaseModel):
    cpf: str
    nome_falecido: Optional[str] = None
    dt_obito: Optional[date] = None
    events: List[TimelineEventSchema]
    cnpjs_envolvidos: List[str]

# ── Análise CRMs (Prescritores) ─────────────────────────
class CrmPrescricoesMapaItemSchema(BaseModel):
    nivel: Literal["uf", "municipio"]
    identificador: str
    nome: str
    uf: str
    id_ibge7: Optional[int] = None
    id_regiao_saude: Optional[str] = None
    no_regiao_saude: Optional[str] = None
    qtd_medicos_ativos: int
    # Medicos com pelo menos um mes acima do P95 nacional do mes
    qtd_medicos_alta_intensidade: int
    percentual_alta_intensidade: Optional[float] = None
    # Multiplo da referencia (1,0 = igual a media). A referencia soma os
    # territorios do mesmo nivel: UFs do Brasil no mapa nacional; municipios do
    # Brasil, da UF e da regiao de saude no mapa municipal.
    indice_brasil: Optional[float] = None
    indice_uf: Optional[float] = None
    indice_regiao: Optional[float] = None
    percentual_referencia_regiao: Optional[float] = None
    # Municipio com poucos medicos ativos: sem cor de risco no mapa
    amostra_pequena: bool = False


class CrmPrescricoesRankingItemSchema(BaseModel):
    id_medico: str
    nu_crm: Optional[int] = None
    sg_uf: Optional[str] = None
    no_medico: Optional[str] = None
    # True quando o id_medico consta no cadastro do CFM (dados dos medicos).
    localizado_cfm: bool
    # prescricoes / dias com prescricao no periodo e no escopo consultado
    taxa_prescricoes_dia: float
    nu_prescricoes: int
    qtd_dias_com_prescricao: int
    qtd_meses_ativos: int
    qtd_meses_alta_intensidade: int
    percentual_meses_alta_intensidade: float
    # Farmacias e municipios distintos onde o medico atuou no periodo (Brasil,
    # nao so no recorte): os mesmos numeros dos filtros de atuacao.
    qtd_farmacias: int
    qtd_municipios: int
    # Somente com filtro de farmacia: prescricoes do medico nas farmacias
    # filtradas (mesmos meses e escopo) e a fatia do total dele.
    nu_prescricoes_farmacias_filtradas: Optional[int] = None
    percentual_prescricoes_farmacias_filtradas: Optional[float] = None


class CrmPrescricoesAnaliseResponse(BaseModel):
    map_level: Literal["uf", "municipio", "regiao"]
    escopo: str
    periodo_inicio: date
    periodo_fim: date
    qtd_medicos: int
    ranking_page: int
    ranking_page_size: int
    mapa: List[CrmPrescricoesMapaItemSchema]
    ranking: List[CrmPrescricoesRankingItemSchema]
    # Somente nas respostas do mapa (map_only)
    percentual_referencia_brasil: Optional[float] = None
    percentual_referencia_uf: Optional[float] = None
    percentual_referencia_regiao: Optional[float] = None
    limiar_p95_min: Optional[float] = None
    limiar_p95_max: Optional[float] = None
    min_medicos_amostra_municipio: Optional[int] = None
    # True quando algum filtro de farmacia (alem de periodo e localizacao) esta ativo.
    filtro_farmacias_ativo: bool = False
    # True quando algum filtro de medico (Cadastro CFM) esta ativo.
    filtro_medicos_ativo: bool = False


class CrmPrescricoesMensalItemSchema(BaseModel):
    """Um medico em um mes (aba "Por mes" do ranking de /analises)."""
    id_medico: str
    nu_crm: Optional[int] = None
    sg_uf: Optional[str] = None
    no_medico: Optional[str] = None
    # True quando o id_medico consta no cadastro do CFM (dados dos medicos).
    localizado_cfm: bool
    competencia: int
    nu_prescricoes: int
    qtd_dias_com_prescricao: int
    # prescricoes / dias com prescricao no mes, no escopo consultado
    taxa_prescricoes_dia: float
    # P95 nacional do mes e taxa do mes / P95
    p95_taxa_dia: float
    razao_p95: float
    # Mesma regra do ranking: taxa arredondada a 6 casas acima do P95 do mes.
    taxa_elevada: bool


class CrmPrescricoesMensalResponse(BaseModel):
    escopo: str
    periodo_inicio: date
    periodo_fim: date
    # Total de linhas medico x mes no recorte (com a busca aplicada).
    qtd_linhas: int
    page: int
    page_size: int
    linhas: List[CrmPrescricoesMensalItemSchema]
    filtro_farmacias_ativo: bool = False
    filtro_medicos_ativo: bool = False


class CrmSerieMensalMesSchema(BaseModel):
    competencia: int
    p95_taxa_dia: float


class CrmSerieMensalPontoSchema(BaseModel):
    competencia: int
    nu_prescricoes: int
    qtd_dias_com_prescricao: int
    taxa_prescricoes_dia: float
    razao_p95: float
    taxa_elevada: bool


class CrmSerieMensalMedicoSchema(BaseModel):
    id_medico: str
    # Somente os meses com prescricao no escopo e no periodo.
    meses: List[CrmSerieMensalPontoSchema]


class CrmPrescricoesSerieMensalResponse(BaseModel):
    """Serie mensal dos medicos de uma pagina do ranking (aba "Linha do tempo")."""
    escopo: str
    periodo_inicio: date
    periodo_fim: date
    # Eixo comum: todos os meses do periodo, com o P95 nacional de cada um.
    meses: List[CrmSerieMensalMesSchema]
    medicos: List[CrmSerieMensalMedicoSchema]


class CrmHistoricoMesSchema(BaseModel):
    """Um mes do medico no Brasil (todas as farmacias).

    Com filtro de farmacia: prescricoes, dias e taxa sao os da farmacia;
    alta_intensidade continua sendo a do total do medico no mes.
    """
    competencia: int
    nu_prescricoes: int
    qtd_dias_com_prescricao: int
    taxa_prescricoes_dia: float
    p95_taxa_dia: float
    alta_intensidade: bool
    qtd_farmacias: int
    qtd_ufs: int
    no_periodo: bool


class CrmHistoricoFarmaciaSchema(BaseModel):
    """Farmacia onde o medico prescreveu, com totais no periodo filtrado."""
    id_cnpj: int
    cnpj: Optional[str] = None
    razao_social: Optional[str] = None
    # Codigo IBGE do municipio: valor do filtro de municipio da tabela (o nome e so rotulo).
    id_ibge7: int
    municipio: Optional[str] = None
    uf: Optional[str] = None
    situacao_rf: Optional[str] = None
    conexao_ativa: Optional[bool] = None
    nu_prescricoes: int
    percentual_prescricoes: float
    qtd_meses: int
    primeira_competencia: int
    ultima_competencia: int
    fora_uf_crm: bool


class CrmHistoricoFarmaciaMesSchema(BaseModel):
    id_cnpj: int
    # Municipio da farmacia (o filtro de municipio do modal separa as series por ele).
    id_ibge7: int
    competencia: int
    nu_prescricoes: int
    # Dias com prescricao do medico nesta farmacia no mes (taxa do mapa de calor).
    qtd_dias_com_prescricao: int


class CrmHistoricoP95MesSchema(BaseModel):
    competencia: int
    p95_taxa_dia: float


class CrmHistoricoKpisSchema(BaseModel):
    nu_prescricoes: int
    qtd_dias_com_prescricao: int
    taxa_prescricoes_dia: Optional[float] = None
    qtd_meses_ativos: int
    qtd_meses_alta_intensidade: int
    percentual_meses_alta_intensidade: Optional[float] = None
    qtd_farmacias: int
    qtd_municipios: int
    qtd_ufs: int
    percentual_farmacia_principal: Optional[float] = None
    percentual_top3_farmacias: Optional[float] = None
    # Pior mes do periodo: maior taxa diaria (prescricoes / dias com prescricao).
    pior_mes_competencia: Optional[int] = None
    pior_mes_taxa_prescricoes_dia: Optional[float] = None
    pior_mes_prescricoes: Optional[int] = None
    pior_mes_p95_taxa_dia: Optional[float] = None


class CrmHistoricoAtencaoSchema(BaseModel):
    """Fato calculado que merece atencao do auditor (sem juizo de valor)."""
    codigo: Literal[
        "antes_inscricao", "rajadas_unico", "distancia",
        "sequencia_alta", "concentracao",
    ]
    titulo: str
    detalhe: str
    competencias: List[int] = []


class CrmRankingAlertasMedicoSchema(BaseModel):
    id_medico: str
    # Mesmos pontos de atencao do modal do historico (periodo, sem filtro de farmacia).
    pontos_atencao: List[CrmHistoricoAtencaoSchema]


class CrmPerfilExportRequest(BaseModel):
    """Pedido de exportação da lista "CRMs de interesse" (aba Perfil de CRMs)."""
    formato: Literal["csv", "xlsx"]
    data_inicio: Optional[date] = None
    data_fim: Optional[date] = None
    ids: Optional[List[str]] = Field(None, max_length=20000, description="CRMs exibidos na tela (id_medico); ausente = todos.")
    filtro: Optional[str] = Field(None, max_length=300, description="Descrição do filtro da tela; obrigatória com ids.")


class ListaInteresseExportRequest(BaseModel):
    """Pedido de exportação das Farmácias Monitoradas (tela /listas) no período de análise."""
    formato: Literal["csv", "xlsx"]
    data_inicio: date
    data_fim: date


class CrmRankingAlertasResponse(BaseModel):
    """Pontos de atencao dos CRMs de uma pagina do ranking de /analises."""
    periodo_inicio: date
    periodo_fim: date
    medicos: List[CrmRankingAlertasMedicoSchema]


class CrmMedicoHistoricoResponse(BaseModel):
    id_medico: str
    nu_crm: Optional[int] = None
    sg_uf: Optional[str] = None
    no_medico: Optional[str] = None
    dt_primeira_inscricao: Optional[date] = None
    localizado_cfm: bool
    periodo_inicio: date
    periodo_fim: date
    # Farmacia filtrada (None = todas as farmacias).
    id_cnpj_filtro: Optional[int] = None
    # Municipio filtrado (id_ibge7; None = todos os municipios).
    id_ibge7_filtro: Optional[int] = None
    kpis: CrmHistoricoKpisSchema
    # Historico completo (todas as competencias com prescricao), para o grafico.
    meses: List[CrmHistoricoMesSchema]
    # Farmacias com prescricao no periodo filtrado, da maior para a menor.
    farmacias: List[CrmHistoricoFarmaciaSchema]
    # Farmacia x mes no historico completo (para empilhar e o mapa de calor).
    farmacia_mes: List[CrmHistoricoFarmaciaMesSchema]
    # P95 nacional de todos os meses do medico (mesmo com farmacia filtrada, quando
    # `meses` traz so os meses dela): a coluna de atuacao desenha todas as farmacias.
    p95_meses: List[CrmHistoricoP95MesSchema]
    # Ha alguma evidencia no periodo (sequencia de unico CRM, de multiplos CRMs
    # ou farmacias distantes)? O painel "Evidencias" so e montado quando houver.
    tem_evidencias: bool
    pontos_atencao: List[CrmHistoricoAtencaoSchema]
    limite_concentracao_percentual: float


# ── Evidencias do CRM (painel do historico em /analises) ─────────────────────
class _CrmEvidenciaFarmaciaSchema(BaseModel):
    id_cnpj: int
    cnpj: str
    razao_social: Optional[str] = None
    municipio: str
    uf: str


class CrmEvidenciaUnicoSchema(_CrmEvidenciaFarmaciaSchema):
    """Uma janela de autorizacoes em sequencia do proprio CRM numa farmacia."""
    dt: str
    hr_janela: Optional[int] = None
    dt_ini_hora: Optional[datetime] = None
    dt_fim_hora: Optional[datetime] = None
    nu_autorizacoes: int
    nu_minutos: Optional[int] = None
    taxa_hora: Optional[float] = None
    id_severidade: int


class CrmEvidenciaMultiplosSchema(_CrmEvidenciaFarmaciaSchema):
    """Janela de autorizacoes em sequencia com varios CRMs em que o medico autorizou."""
    dt: str
    hr_janela: Optional[int] = None
    dt_ini_hora: datetime
    dt_fim_hora: datetime
    nu_autorizacoes_crm: int
    nu_autorizacoes_total: int
    nu_crms: Optional[int] = None
    nu_minutos: Optional[int] = None
    taxa_hora: Optional[float] = None
    id_severidade: int


class CrmEvidenciaDistanciaSchema(BaseModel):
    """Par de farmacias distantes com prescricao do CRM no mesmo mes."""
    competencia: int
    cnpj_a: str
    razao_social_a: Optional[str] = None
    no_municipio_a: str
    sg_uf_a: str
    dt_ini_a: Optional[str] = None
    dt_fim_a: Optional[str] = None
    nu_prescricoes_a: Optional[int] = None
    vl_autorizacoes_a: Optional[float] = None
    cnpj_b: str
    razao_social_b: Optional[str] = None
    no_municipio_b: str
    sg_uf_b: str
    dt_ini_b: Optional[str] = None
    dt_fim_b: Optional[str] = None
    nu_prescricoes_b: Optional[int] = None
    vl_autorizacoes_b: Optional[float] = None
    vl_autorizacoes_total: Optional[float] = None
    distancia_km: float


class CrmEvidenciasResumoSequenciaSchema(BaseModel):
    qtd_alertas: int
    qtd_dias: int
    qtd_farmacias: int
    pior_severidade: Optional[int] = None
    # id_severidade ("1".."4") -> numero de janelas
    por_severidade: Dict[str, int]


class CrmEvidenciasResumoDistanciaSchema(BaseModel):
    qtd_pares: int
    qtd_meses: int
    maior_distancia_km: Optional[float] = None


class CrmEvidenciasResponse(BaseModel):
    id_medico: str
    periodo_inicio: date
    periodo_fim: date
    id_cnpj: Optional[int] = None
    id_ibge7: Optional[int] = None
    tipo: Literal["unico", "multiplos", "distancia"]
    # Resumos das tres abas (contadores das abas e chips de severidade).
    resumo_unico: CrmEvidenciasResumoSequenciaSchema
    resumo_multiplos: CrmEvidenciasResumoSequenciaSchema
    resumo_distancia: CrmEvidenciasResumoDistanciaSchema
    # Linhas da aba pedida, depois do filtro de severidade (total) e paginadas.
    total: int
    page: int
    page_size: int
    linhas_unico: List[CrmEvidenciaUnicoSchema] = []
    linhas_multiplos: List[CrmEvidenciaMultiplosSchema] = []
    linhas_distancia: List[CrmEvidenciaDistanciaSchema] = []


class CrmEvidenciaAutorizacaoSchema(BaseModel):
    data_hora: datetime
    num_autorizacao: str
    id_medico: str
    no_medico: Optional[str] = None
    valor_pago: Optional[float] = None
    # Autorizacao do CRM consultado (as demais sao de outros CRMs na janela).
    do_crm: bool


class CrmEvidenciaAutorizacoesResponse(BaseModel):
    """Autorizacoes de uma janela de sequencia numa farmacia (Raio-X)."""
    id_cnpj: int
    cnpj: str
    razao_social: Optional[str] = None
    municipio: str
    uf: str
    id_medico: str
    inicio: datetime
    fim: datetime
    qtd_autorizacoes: int
    qtd_autorizacoes_crm: int
    qtd_crms: int
    valor_total: float
    autorizacoes: List[CrmEvidenciaAutorizacaoSchema]


class PrescritoresResponse(BaseModel):
    cnpj: str
    summary: dict
    crms_interesse: list
    cnpj_alerts: List[dict] = []
    from_cache: bool = False
    tem_historico: bool = False
    read_time_ms: Optional[float] = None
    query_time_ms: Optional[float] = None
    save_time_ms: Optional[float] = None

class CrmMedicoAtuacaoResponse(BaseModel):
    """Atuação de um CRM numa farmácia (mesmo contrato da tabela de CRMs do CNPJ)."""
    cnpj: str
    # Item do médico em crms_interesse de /cnpj/{cnpj}/crm-data.
    medico: dict
    # Eixo comum da farmácia no período (competências YYYYMM).
    competencia_inicio_periodo: int
    competencia_fim_periodo: int
    serie_mensal_farmacia: list

class CrmDailyProfileItem(BaseModel):
    dt_janela: str
    competencia: int
    nu_prescricoes_dia: int
    nu_crms_distintos: int
    mediana_diaria: float
    is_dia_com_volume_horario_anomalo: int
    is_anomalo_unico: int
    is_crm_multiplo: int
    score_crm_unico_hora: Optional[float] = None
    score_crm_unico_qtd: Optional[int] = None
    score_crm_unico_minutos: Optional[int] = None
    score_crm_unico_medico: Optional[str] = None
    score_crm_multiplo_hora: Optional[float] = None
    score_crm_multiplo_qtd: Optional[int] = None
    score_crm_multiplo_minutos: Optional[int] = None
    score_crm_multiplo_crms: Optional[int] = None

class CrmHourlyEventSchema(BaseModel):
    dt_janela: date
    tipo: str
    hora_inicio: str
    hora_fim: str
    minuto_inicio: int
    minuto_fim: int
    severidade: Optional[str] = None
    id_medico: Optional[str] = None
    nu_crms_distintos: Optional[int] = None

# ── Dataset semantico da Linha do Tempo CRM ─────────────────────
class CrmTimelineHourSchema(BaseModel):
    dt_janela: date
    hr_janela: int
    nu_prescricoes: int
    nu_crms_diferentes: int
    mediana_hora: float
    is_hora_com_alerta: int = 0
    is_volume_horario_anomalo: int = 0
    is_crm_unico: int = 0
    is_crm_multiplo: int = 0
    alert_types: List[str] = Field(default_factory=list)

class CrmTimelineDaySchema(CrmDailyProfileItem):
    is_volume_horario_anomalo: int = 0
    is_crm_unico: int = 0
    is_anomalo: int = 0
    hours: List[CrmTimelineHourSchema]
    events: List[CrmHourlyEventSchema] = Field(default_factory=list)

class CrmTimelineDatasetResponse(BaseModel):
    cnpj: str
    days: List[CrmTimelineDaySchema]
    from_cache: bool = False
    daily_from_cache: bool = False
    hourly_from_cache: bool = False
    read_time_ms: Optional[float] = None
    query_time_ms: Optional[float] = None
    save_time_ms: Optional[float] = None

# ── Dados Cadastrais e Geográficos ─────────────────────
class CnaeSecundarioSchema(BaseModel):
    id_cnae: int
    descricao: Optional[str] = None


class DadosFarmaciaSchema(BaseModel):
    cnpj: str
    razao_social: Optional[str] = None
    nome_fantasia: Optional[str] = None
    is_matriz: Optional[bool] = False
    tipo_logradouro: Optional[str] = None
    logradouro: Optional[str] = None
    numero: Optional[str] = None
    complemento: Optional[str] = None
    bairro: Optional[str] = None
    cep: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    id_ibge7: Optional[str] = None
    id_cnae_principal: Optional[str] = None
    cnae_principal: Optional[str] = None
    cnaes_secundarios: List[CnaeSecundarioSchema]
    is_cnae_incompativel_farmaceutico: bool
    is_cnae_farmacia_ausente: bool
    is_dispersao_uf_nao_vizinha: bool
    pct_dispersao_uf_nao_vizinha: float
    valor_dispersao_uf_nao_vizinha: float
    data_abertura: Optional[datetime] = None
    data_processamento: Optional[datetime] = None
    natureza_juridica: Optional[str] = None
    capital_social: Optional[float] = 0.0
    # Dados adicionais de identidade para o Quadro 01 da Nota Técnica
    telefone_1: Optional[str] = None
    telefone_2: Optional[str] = None
    email: Optional[str] = None
    # UF e Município (conveniência para o objeto de cadastro)
    uf: Optional[str] = None
    municipio: Optional[str] = None
    situacao_rf: Optional[str] = None
    porte_empresa: Optional[str] = None

class CnpjAccessStatusSchema(BaseModel):
    cnpj: str
    status: str
    in_program: bool
    razao_social: Optional[str] = None
    nome_fantasia: Optional[str] = None
    municipio: Optional[str] = None
    uf: Optional[str] = None

class CnpjPeriodSummarySchema(BaseModel):
    totalMov: float = 0.0
    valSemComp: float = 0.0
    percValSemComp: float = 0.0
    totalQtde: int = 0
    qtdeSemComp: int = 0
    percQtdeSemComp: float = 0.0

class CnpjGeoDataSchema(BaseModel):
    sg_uf: str
    no_regiao_saude: str
    id_regiao_saude: int
    no_municipio: str
    id_ibge7: int
    nu_populacao: Optional[int] = None
    unidade_pf: Optional[str] = None

class CnpjBootstrapResponse(BaseModel):
    status: CnpjAccessStatusSchema
    cadastro: DadosFarmaciaSchema
    cnpj_data: ResultadoSentinelaCnpjSchema
    geo_data: CnpjGeoDataSchema
    qtd_municipios_regiao: int
    period_summary: CnpjPeriodSummarySchema

class SocioSchema(BaseModel):
    cnpj: str
    cpf_cnpj_socio: str
    nome_socio: Optional[str] = None
    indicador_socio: Optional[str] = None
    municipio: Optional[str] = None
    uf: Optional[str] = None
    descricao_qualificacao: Optional[str] = None
    data_entrada_sociedade: Optional[date] = None
    data_exclusao_sociedade: Optional[date] = None
    percentual_qualificacao: Optional[float] = 0.0
    # Representante Legal
    cpf_representante: Optional[str] = None
    id_qualificacao_representante: Optional[int] = None
    nome_representante: Optional[str] = None
    descricao_qualificacao_representante: Optional[str] = None
    # Datas de Nascimento (Novidade)
    data_nascimento_socio: Optional[date] = None
    data_nascimento_representante: Optional[date] = None
    is_falecido: Optional[bool] = False
    is_cadunico: bool
    is_esocial: bool
    is_seguro_defeso: bool

class SociosResponse(BaseModel):
    cnpj: str
    socios: List[SocioSchema]
    data_processamento: Optional[date] = None
    from_cache: bool = False


class IntegrityAlertSchema(BaseModel):
    tipo: str
    escopo: Literal["cnpj", "socio", "representante"]
    entidade_id: str
    entidade_nome: str
    severidade: Literal["critico", "atencao"]
    titulo: str
    fonte: str
    data_referencia: Optional[date] = None
    aba_destino: str


class IntegrityAlertsResponse(BaseModel):
    cnpj: str
    total: int
    total_criticos: int
    total_atencao: int
    alertas: List[IntegrityAlertSchema]
    data_processamento: Optional[date] = None

# ── Panorama de Alertas (Dashboard) ───────────────────────────
class AlertaPanoramaItemSchema(BaseModel):
    tipo: str
    titulo: str
    severidade: Literal["critico", "atencao"]
    qtd_cnpjs: int


class AlertasPanoramaResponse(BaseModel):
    total_cnpjs_com_alerta: int
    total_criticos: int
    total_atencao: int
    alertas: List[AlertaPanoramaItemSchema]


# ── Teia Societária (Grafos) ───────────────────────────
class NetworkNodeSchema(BaseModel):
    id: str
    label: str
    type: str                 # 'PF' | 'PJ_ALVO' | 'PJ_FARMACIA_POPULAR' | 'PJ_OUTRAS_FARMACIAS' | 'PJ_DEMAIS_EMPRESAS'
    network_level: Optional[str] = None
    percentual_nao_comprovacao: Optional[float] = None
    criticidade_nao_comprovacao: Optional[str] = None
    conexao_ms: Optional[str] = None
    razao_social: Optional[str] = None
    nome_socio: Optional[str] = None
    nome_fantasia: Optional[str] = None
    id_cnae_principal: Optional[int] = None
    cnae_principal: Optional[str] = None
    cnaes_secundarios: List[CnaeSecundarioSchema]
    municipio: Optional[str] = None
    uf: Optional[str] = None
    situacao_rf: Optional[str] = None
    is_falecido: Optional[bool] = False
    is_cadunico: bool
    is_esocial: bool
    is_seguro_defeso: bool
    is_cnae_farmacia_ausente: bool
    is_par: Optional[bool] = False
    qtd_processos_par: Optional[int] = 0
    par_situacoes: Optional[str] = None
    par_primeira_instauracao: Optional[date] = None
    par_ultima_instauracao: Optional[date] = None
    par_ultima_conclusao: Optional[date] = None

class NetworkEdgeSchema(BaseModel):
    id: str
    source: str               # ID do nó de origem
    target: str               # ID do nó de destino
    label: Optional[str] = None # Ex: '10.00%'
    type: str = "socio"       # 'socio' | 'representante'
    network_level: Optional[str] = None
    is_ativo: bool = True
    data_entrada_sociedade: Optional[date] = None
    data_exclusao_sociedade: Optional[date] = None

class NetworkLevelSummarySchema(BaseModel):
    label: str
    entities: int = 0
    links: int = 0

class NetworkSummarySchema(BaseModel):
    total_entities: int = 0
    total_links: int = 0
    levels: Dict[str, NetworkLevelSummarySchema] = Field(default_factory=dict)

class NetworkResponse(BaseModel):
    cnpj: str
    nodes: List[NetworkNodeSchema]
    edges: List[NetworkEdgeSchema]
    summary: Optional[NetworkSummarySchema] = None
    query_time_ms: Optional[float] = None


# ── Memória de Cálculo — Movimentação por GTIN ──────────
class MovimentacaoRowSchema(BaseModel):
    """
    Representa uma linha processada da Memória de Cálculo.
    O campo `tipo_linha` define como a linha deve ser renderizada no frontend:
      - 'header_medicamento'  : Cabeçalho do GTIN (fundo cinza escuro)
      - 'header_colunas'      : Sub-cabeçalho de colunas (fundo cinza claro)
      - 'venda_normal'        : Venda com comprovação total (fundo verde claro)
      - 'venda_irregular'     : Venda SEM comprovação (fundo vermelho claro)
      - 'resumo_parcial'      : Linha de subtotal do GTIN (negrito)
      - 'total_geral'         : Linha de total geral do CNPJ (azul escuro)
    """
    tipo_linha: str
    gtin: Optional[str] = None
    medicamento: Optional[str] = None
    periodo_inicial: Optional[str] = None
    periodo_inicio_irregular: Optional[str] = None
    periodo_final: Optional[str] = None
    estoque_inicial: Optional[int] = None
    estoque_final: Optional[int] = None
    vendas: Optional[int] = None
    vendas_irregular: Optional[int] = None
    valor: Optional[float] = None
    valor_irregular: Optional[float] = None
    notas: Optional[str] = None


class MovimentacaoSummarySchema(BaseModel):
    """Totalizadores do processamento da Memória de Cálculo."""
    total_vendas: int = 0
    total_vendas_irregular: int = 0
    valor_total: float = 0.0
    valor_irregular: float = 0.0
    pct_irregular: float = 0.0
    from_cache: bool = False  # True se foi carregado do cache Parquet local


class MovimentacaoResponse(BaseModel):
    """Payload completo da aba Movimentação."""
    cnpj: str
    summary: MovimentacaoSummarySchema
    rows: List[MovimentacaoRowSchema]
    from_cache: bool = False
    read_time_ms: Optional[float] = None
    query_time_ms: Optional[float] = None
    save_time_ms: Optional[float] = None


# ── Análise de Indicadores (Vista /indicadores) ──────────────────────────────

class IndicadorKpiSummarySchema(BaseModel):
    """Contadores de status para um indicador no escopo atual."""
    total_critico: int = 0
    total_atencao: int = 0
    total_normal: int = 0
    total_sem_dados: int = 0
    total_mov: float = 0.0
    total_sem_comprovacao: float = 0.0
    perc_sem_comprovacao: Optional[float] = None
    mediana_reg: Optional[float] = None
    mad_reg: Optional[float] = None
    pct_acima_limiar: Optional[float] = None
    limiar_atencao: Optional[float] = None
    limiar_critico: Optional[float] = None


class IndicadorCnpjRowSchema(BaseModel):
    """Uma linha na tabela ranqueada de CNPJs por indicador."""
    cnpj: str
    razao_social: Optional[str] = None
    municipio: Optional[str] = None
    uf: Optional[str] = None
    id_ibge7: Optional[int] = None
    valor: Optional[float] = None
    med_reg: Optional[float] = None
    med_benchmark: Optional[float] = None
    benchmark_escopo: Optional[str] = None
    risco_reg: Optional[float] = None
    risco_benchmark: Optional[float] = None
    status: str = "SEM DADOS"          # "CRÍTICO" | "ATENÇÃO" | "NORMAL" | "SEM DADOS"
    is_matriz: bool
    is_grande_rede: Optional[bool] = False
    qtd_estabelecimentos_rede: int
    situacao_rf: Optional[str] = None
    is_conexao_ativa: Optional[bool] = False
    score_risco_final: Optional[float] = None
    valor_movimentado: Optional[float] = None
    val_sem_comp: Optional[float] = None
    perc_val_sem_comp: Optional[float] = None
    detalhes_extras: Optional[Dict[str, float | str | None]] = None


class IndicadorMunicipioRowSchema(BaseModel):
    """Agregação municipal para o mapa coroplético de um indicador."""
    municipio: str
    uf: Optional[str] = None
    id_ibge7: Optional[int] = None
    total_cnpjs: int = 0
    total_critico: int = 0
    pct_critico: float = 0.0           # campo usado para colorir o mapa


class IndicadorAnaliseResponse(BaseModel):
    """Payload de resumo da análise cruzada de um indicador."""
    indicador: str
    kpis: IndicadorKpiSummarySchema
    municipios: List[IndicadorMunicipioRowSchema]


class IndicadorCnpjPageResponse(BaseModel):
    """Paginacao server-side da tabela de CNPJs da vista /indicadores."""
    indicador: str
    items: List[IndicadorCnpjRowSchema]
    kpis: Optional[IndicadorKpiSummarySchema] = None
    total: int = 0
    page: int = 1
    page_size: int = 20
    sort_field: str = "val_sem_comp"
    sort_order: str = "desc"


# ── Drill-down da Análise Horária (Raio-X de Transações) ─────────────────────────

class CrmHourlyTransactionSchema(BaseModel):
    """Uma prescrição real capturada no Data Mart de anomalias horárias."""
    data_hora: str
    num_autorizacao: str
    id_medico: str
    no_medico: Optional[str] = None
    valor_pago: float


class CrmUnicoAlertaSchema(BaseModel):
    """Médico que disparou alerta de concentração num dia específico."""
    id_medico: str
    hr_janela: int
    nu_prescricoes_dia: int
    nu_minutos_dia: int
    taxa_hora: float
    ritmo_hora: float
    ritmo_qtd: int
    ritmo_minutos: int
    severidade: Optional[str] = None
    criterio_pior_ritmo: Optional[str] = None
    dt_ini_hora: Optional[str] = None
    dt_fim_hora: Optional[str] = None


# ── Evolução Mensal por GTIN ─────────────────────────────────────────────────

class CrmMultiploAlertaSchema(BaseModel):
    """Alerta coordenado de prescricoes envolvendo multiplos CRMs num intervalo."""
    dt_janela: str
    hr_janela: Optional[int] = None
    nu_prescricoes: int = 0
    nu_crms: int = 0
    ritmo_hora: float = 0
    ritmo_qtd: int = 0
    ritmo_minutos: int = 0
    severidade: Optional[str] = None
    criterio_pior_ritmo: Optional[str] = None
    dt_ini_hora: Optional[str] = None
    dt_fim_hora: Optional[str] = None

class CrmRaioXResponse(BaseModel):
    """Contrato unificado do Raio-X de auditoria CRM."""
    cnpj: str
    dt_janela: str
    hour: Optional[int] = None
    transactions: List[CrmHourlyTransactionSchema]
    alertas_unico: List[CrmUnicoAlertaSchema] = Field(default_factory=list)
    alertas_multi: List[CrmMultiploAlertaSchema] = Field(default_factory=list)
    from_cache: bool = False
    read_time_ms: Optional[float] = None


class MesMensalGtinItem(BaseModel):
    mes: str                          # "YYYY-MM"
    qnt_caixas_vendidas: int
    qnt_caixas_sem_comprovacao: int
    num_autorizacoes: int = 0
    valor_vendas: float
    valor_sem_comprovacao: float
    pct_sem_comprovacao: float        # 0–100

class EvolucaoMensalGtinResponse(BaseModel):
    meses: List[MesMensalGtinItem]
    from_cache: bool = False
    query_time_ms: Optional[float] = None
    save_time_ms: Optional[float] = None
    read_time_ms: Optional[float] = None


class RepassesResumoSchema(BaseModel):
    total_repassado: float
    qtd_ordens: int
    maior_repasse: float
    ultimo_repasse_data: Optional[date] = None
    ultimo_repasse_valor: Optional[float] = None


class RepasseMensalItemSchema(BaseModel):
    mes: str
    valor_repassado: float
    qtd_ordens: int


class RepassePagamentoItemSchema(BaseModel):
    data_pagamento: date
    programa_acao: str
    numero_ordem_bancaria: str
    valor_pago: float


class RepassesResponse(BaseModel):
    cnpj: str
    resumo: RepassesResumoSchema
    mensal: List[RepasseMensalItemSchema]
    pagamentos: List[RepassePagamentoItemSchema]


# ── Detalhamento Mensal de GTINs (Raio-X Mensal) ─────────────────────────────
class GtinDetalhamentoMensalItem(BaseModel):
    gtin: str
    medicamento: Optional[str] = None
    principio_ativo: Optional[str] = None
    produto: Optional[str] = None
    laboratorio: Optional[str] = None
    qnt_caixas_vendidas: int = 0
    qnt_caixas_sem_comprovacao: int = 0
    num_autorizacoes: int = 0
    valor_vendas: float = 0.0
    valor_sem_comprovacao: float = 0.0
    pct_sem_comprovacao: float = 0.0

class GtinDetalhamentoMensalSummary(BaseModel):
    total_gtins: int = 0
    gtins_irregulares: int = 0
    gtins_regulares: int = 0

class GtinDetalhamentoMensalResponse(BaseModel):
    cnpj: str
    periodo: str
    summary: GtinDetalhamentoMensalSummary
    ranking: List[GtinDetalhamentoMensalItem]
    from_cache: bool = False
    read_time_ms: Optional[float] = None


class NotaTecnicaReadinessModuleSchema(BaseModel):
    key: str
    label: str
    scope: Literal["global", "cnpj"]
    required: bool
    ready: bool
    preparable: bool = False
    missing_files: List[str] = Field(default_factory=list)
    detail: Optional[str] = None


class NotaTecnicaReadinessResponse(BaseModel):
    cnpj: str
    ready: bool
    preparable: bool = False
    data_inicio: Optional[date] = None
    data_fim: Optional[date] = None
    modules: List[NotaTecnicaReadinessModuleSchema]
    missing_modules: List[NotaTecnicaReadinessModuleSchema] = Field(default_factory=list)


class NotaTecnicaPrepareModuleSchema(BaseModel):
    key: str
    label: str
    status: Literal["already_ready", "prepared"]
    file: str


class NotaTecnicaPrepareResponse(BaseModel):
    cnpj: str
    prepared_modules: List[NotaTecnicaPrepareModuleSchema] = Field(default_factory=list)
    readiness: NotaTecnicaReadinessResponse

