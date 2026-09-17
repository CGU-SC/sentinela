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
    kpis: List[AnalyticsKPISchema]
    resultado_sentinela_uf: List[ResultadoSentinelaUFSchema]
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
    p95_prescricoes_dia: float
    mediana_prescricoes_dia: float
    maior_prescricoes_dia: float
    qtd_medicos: int


class CrmPrescricoesRankingItemSchema(BaseModel):
    rank: int
    id_medico: str
    nu_crm: Optional[int] = None
    sg_uf: Optional[str] = None
    no_medico: Optional[str] = None
    taxa_prescricoes_dia: float
    nu_prescricoes: int
    dias_calendario: int
    qtd_estabelecimentos: int


class CrmPrescricoesAnaliseResponse(BaseModel):
    map_level: Literal["uf", "municipio", "regiao"]
    escopo: str
    periodo_inicio: date
    periodo_fim: date
    qtd_medicos: int
    mapa: List[CrmPrescricoesMapaItemSchema]
    ranking: List[CrmPrescricoesRankingItemSchema]


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

class CrmMedicoAlertasResponse(BaseModel):
    cnpj: str
    id_medico: str
    alertas_crm_unico: List[dict]
    alertas_geograficos: List[dict]
    alertas_crm_multiplos: List[dict]

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

