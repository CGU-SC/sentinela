import { describe, expect, it, vi } from 'vitest'
import { reactive } from 'vue'

import { API_ENDPOINTS } from '@/config/api'
import { APP_RUNTIME, APP_VERSION, getAppRuntimeLabel, getAppVersionLabel } from '@/config/appInfo'
import { useChartTheme } from '@/config/chartTheme'
import { CRM_FAIXAS, crmFaixasDoGrupo } from '@/config/crmFiltrosMedico'
import {
  CRM_ATUACAO_TETO_P95,
  CRM_LINHA_TEMPO_TETO_P95,
  analysisTooltip,
  crmMaisMedicosTooltip,
  crmAlertasTooltip,
  crmAlturaAtuacao,
  crmFaixaP95,
  crmFaixaPorTaxa,
  crmMedicoNomeTooltip,
  crmMesTooltip,
  maisMedicosPerfilRotulo,
  siglaRegistroMedico,
} from '@/config/analysisTooltipConfig'
import { cnpjHeroTextTooltip, cnpjHeroTooltip } from '@/config/cnpjHeroTooltipConfig'
import { establishmentRiskTooltip, establishmentTableTooltip } from '@/config/establishmentTableTooltipConfig'
import { filterActionTooltip, filterTooltip } from '@/config/filterTooltipConfig'
import { FINANCIAL_MOVEMENT_TOOLTIP_COPY, financialMovementTooltip } from '@/config/financialMovementTooltipConfig'
import { homeTooltip } from '@/config/homeTooltipConfig'
import {
  INTEGRITY_ALERT_TOOLTIP_COPY,
  integrityAlertTooltip,
  panoramaAlertTooltip,
} from '@/config/integrityAlertTooltipConfig'
import { navbarTooltip } from '@/config/navbarTooltipConfig'
import { SURFACE_COLORS } from '@/config/themeConfig'

const mocks = vi.hoisted(() => ({ themeStore: null }))
vi.mock('@/stores/theme', () => ({ useThemeStore: () => mocks.themeStore }))

const ANALYSIS_KEYS = [
  'crmFiltrosMedico', 'crmFiltroBusca', 'crmFiltroSituacaoCfm', 'crmFiltroUfCrm',
  'crmFiltroTaxaDia', 'crmFiltroPrescricoes', 'crmFiltroExclusividade', 'crmFiltroFarmacias',
  'crmFiltroMunicipios', 'crmFiltroSequencia', 'crmMap', 'listaInteresse', 'crmRanking',
  'crmRankingMensal', 'crmRankingLinhaTempo', 'crmHistorico', 'crmHistoricoAtuacao',
  'crmRankingAlertas', 'crmHistoricoFiltros', 'crmHistoricoAtencao', 'crmHistoricoEvidencias',
  'crmEvidenciasUnico', 'crmEvidenciasMultiplos', 'crmEvidenciasDistancia',
]
const HERO_KEYS = [
  'back', 'copyCnpj', 'cadastro', 'nomeFantasia', 'razaoSocial', 'rede', 'ministerioSaude',
  'receitaFederal', 'rankRegiao', 'rankMunicipio', 'pdf', 'notaTecnica', 'listaInteresse',
  'evidencias', 'observacao',
]
const TABLE_KEYS = [
  'nameColumn', 'riskColumn', 'clearRegion', 'clearMunicipality', 'matrix', 'branch',
  'pharmacyName', 'cnpjValue', 'stateValue', 'copyCnpj', 'municipality', 'indicatorColumn',
  'totalSales', 'totalSalesFooter', 'unverifiedSales', 'unverifiedSalesFooter',
  'largeNetworkFilter', 'networkEstablishments', 'ministryConnectionFilter', 'indicatorDetails',
  'favoriteAdd', 'favoriteRemove', 'observationAdd', 'observationEdit',
]
const FILTER_KEYS = [
  'uf', 'regiao', 'municipio', 'unidadePf', 'situacao', 'ms', 'porte', 'grandeRede',
  'estabelecimento', 'parTeia', 'cnaeIncompativel', 'socioIdadeAtipica', 'socioFalecido',
  'socioBeneficio', 'socioEsocial', 'dispersaoUfSemFronteira', 'seq', 'volumeAtipico',
  'percentual', 'periodo', 'populacaoMunicipio', 'valorMin',
]
const NAVBAR_KEYS = [
  'comingSoon', 'recentCnpj', 'clearRecentCnpj', 'documentation', 'lightTheme',
  'darkTheme', 'settings', 'monitoredPharmacies',
]

describe('configurações de tooltip do frontend', () => {
  it('renderiza todos os textos cadastrados na página de análises', () => {
    for (const key of ANALYSIS_KEYS) {
      const tooltip = analysisTooltip(key)
      expect(tooltip.value).toContain('analysis-tooltip-content')
      expect(tooltip.escape).toBe(false)
    }
    expect(analysisTooltip('crmMap', { extraSections: [{ label: '<regra>', text: 'A & B' }] }).value)
      .toContain('&lt;regra&gt;')
    expect(() => analysisTooltip('crmMap', { extraSections: [{ label: 'sem texto' }] })).toThrow()
  })

  it('escapa conteúdo dinâmico e cobre faixas de taxa diária dos CRMs', () => {
    expect(() => analysisTooltip('ausente')).toThrow('Tooltip da página de análises não encontrado: ausente')
    const ratios = [
      [7, 'extrema'], [6, 'muito-forte'], [5, 'forte'], [4, 'media-forte'],
      [3, 'media'], [2, 'leve'], [1, null],
    ]
    for (const [razao_p95, chave] of ratios) {
      expect(crmFaixaP95({ taxa_elevada: true, razao_p95 }).chave).toBe(chave)
    }
    expect(crmFaixaP95({ taxa_elevada: false, razao_p95: 8 })).toBeNull()
    expect(crmAlturaAtuacao(2)).toEqual({ fracao: 2 / CRM_ATUACAO_TETO_P95, cortada: false })
    expect(crmAlturaAtuacao(6)).toEqual({ fracao: 1, cortada: true })
    expect(() => crmAlturaAtuacao(-1)).toThrow('×P95 inválido: -1.')
    expect(() => crmAlturaAtuacao(1, 0)).toThrow('Teto de ×P95 inválido: 0.')
    expect(CRM_LINHA_TEMPO_TETO_P95).toBe(10)
    expect(() => crmFaixaPorTaxa(4, 0)).toThrow('P95 do mês inválido: 0.')
    expect(crmFaixaPorTaxa(10, 5).chave).toBe('leve')

    expect(() => crmMedicoNomeTooltip('', 'CRM 123/SC')).toThrow('Tooltip de médico sem nome.')
    expect(crmMedicoNomeTooltip('<João>', 'CRM & 123').value).toContain('&lt;João&gt;')
    const single = crmMesTooltip({ competencia: 202401, qtd_dias_com_prescricao: 1, taxa_prescricoes_dia: 2.5, razao_p95: 2, nu_prescricoes: 2, taxa_elevada: true }, 1)
    expect(single.value).toContain('1 dia')
    expect(single.value).toContain('Taxa elevada')
    const plural = crmMesTooltip({ competencia: 202402, qtd_dias_com_prescricao: 3, taxa_prescricoes_dia: 2.5, razao_p95: 1, nu_prescricoes: 8, taxa_elevada: false }, 2)
    expect(plural.value).toContain('3 dias')
    expect(plural.value).not.toContain('Taxa elevada')
  })

  it('valida e escapa alertas de médicos, incluindo marcação do mês correspondente', () => {
    expect(() => crmAlertasTooltip([], { periodo: '2024' })).toThrow('Tooltip de alertas de CRM sem pontos de atenção.')
    expect(() => crmAlertasTooltip([{ codigo: 'invalido', titulo: 'x', detalhe: 'y' }], { periodo: '2024' }))
      .toThrow('Ponto de atenção sem ícone: invalido')
    const point = { codigo: 'distancia', titulo: '<distância>', detalhe: 'A & B', competencias: [202401] }
    const one = crmAlertasTooltip([point], { periodo: '2024', competencia: 202401 }).value
    expect(one).toContain('1 ponto de atenção')
    expect(one).toContain('is-mes')
    expect(one).toContain('&lt;distância&gt;')
    expect(one).toContain('A &amp; B')
    const many = crmAlertasTooltip([point, { ...point, competencias: [] }], { periodo: '<ano>', competencia: 202402 }).value
    expect(many).toContain('2 pontos de atenção')
    expect(many).toContain('&lt;ano&gt;')
    expect(many.match(/is-mes/g)).toBeNull()
    const missingCompetencies = crmAlertasTooltip(
      [{ ...point, competencias: undefined }],
      { periodo: '2024', competencia: 202401 },
    ).value
    expect(missingCompetencies).not.toContain('is-mes')
  })

  it('renderiza tooltips do Mais Médicos e valida perfis, nacionalidade e data', () => {
    const profiles = {
      INTERCAMBISTA: 'Intercambista',
      'CRM BRASIL': 'CRM Brasil',
      'MFC CELETISTA': 'MFC celetista',
      TUTOR: 'Tutor',
      BOLSISTA: 'Bolsista',
    }
    for (const [key, label] of Object.entries(profiles)) {
      expect(maisMedicosPerfilRotulo(key)).toBe(label)
    }
    expect(() => maisMedicosPerfilRotulo('DESCONHECIDO')).toThrow('Perfil do Mais Médicos desconhecido: DESCONHECIDO')
    expect(() => crmMaisMedicosTooltip(null)).toThrow('Tooltip do Mais Médicos sem dados.')

    const tooltip = crmMaisMedicosTooltip({
      tp_perfil: 'INTERCAMBISTA',
      no_nacionalidade: '<BRASILEIRA>',
      dt_atualizacao: '2025-07-09',
    }).value
    expect(tooltip).toContain('Intercambista')
    expect(tooltip).toContain('&lt;brasileira&gt;')
    expect(tooltip).toContain('09/07/2025')
    expect(crmMaisMedicosTooltip({
      tp_perfil: 'TUTOR',
      no_nacionalidade: null,
      dt_atualizacao: '2025-07-09',
    }).value).toContain('Não informada')
    expect(crmMaisMedicosTooltip({
      tp_perfil: 'TUTOR',
      no_nacionalidade: 'NAO INFORMADO',
      dt_atualizacao: '2025-07-09',
    }).value).toContain('Não informada')
    expect(() => crmMaisMedicosTooltip({
      tp_perfil: 'TUTOR',
      no_nacionalidade: null,
      dt_atualizacao: '2025/07/09',
    })).toThrow('Data inválida do Mais Médicos: 2025/07/09')

    expect(siglaRegistroMedico({ mais_medicos: { tp_perfil: 'INTERCAMBISTA' } })).toBe('RMS')
    expect(siglaRegistroMedico({ mais_medicos: { tp_perfil: 'TUTOR' } })).toBe('CRM')
    expect(siglaRegistroMedico({})).toBe('CRM')
    expect(siglaRegistroMedico(null)).toBe('CRM')
  })

  it('renderiza ferramentas da hero e tabela do estabelecimento em todos os formatos', () => {
    for (const key of HERO_KEYS) {
      expect(cnpjHeroTooltip(key).value).toContain('cnpj-hero-tooltip-content')
    }
    expect(() => cnpjHeroTooltip('missing')).toThrow('Texto de tooltip da hero do CNPJ não encontrado: missing')
    expect(() => cnpjHeroTooltip('back', { title: '', body: '' })).toThrow('Texto de tooltip da hero do CNPJ incompleto.')
    expect(cnpjHeroTooltip('copyCnpj', { title: '<CNPJ>', detail: 'A & B', detailLabel: '' }).value).toContain('&lt;CNPJ&gt;')
    expect(cnpjHeroTooltip('back', { icon: '' }).value).toContain('pi-info-circle')
    expect(cnpjHeroTextTooltip('PDF', 'Criar relatório', '').value).not.toContain('cnpj-hero-tooltip-detail')
    expect(cnpjHeroTextTooltip('PDF', 'Criar relatório', 'Pronto').value).toContain('<strong>Valor</strong>')

    for (const key of TABLE_KEYS) {
      expect(establishmentTableTooltip(key).value).toContain('establishment-table-tooltip-content')
    }
    expect(() => establishmentTableTooltip('missing')).toThrow('Tooltip da tabela de estabelecimentos não encontrado: missing')
    expect(establishmentTableTooltip('cnpjValue', '<123>').value).toContain('&lt;123&gt;')
    expect(establishmentTableTooltip('nameColumn', '<nome>').value).toContain('<strong>Detalhe</strong>')
    expect(establishmentRiskTooltip({ indicator: '<risco>', value: '10', median: '5', scope: 'UF', ratio: 2, status: 'ALTO' }).value)
      .toContain('2.0x')
    expect(establishmentRiskTooltip({ indicator: 'Risco', value: '—', median: '—', scope: 'Brasil', ratio: null, status: 'SEM DADOS' }).value)
      .toContain('região de saúde')
    expect(establishmentRiskTooltip({ indicator: 'Risco', value: '1', median: '0', scope: 'UF', ratio: undefined, status: 'NORMAL' }).value)
      .toContain('Multiplicador indisponível')
  })

  it('renderiza filtros, ações, textos da Home, financeiro e navbar, rejeitando chaves inválidas', () => {
    for (const key of FILTER_KEYS) {
      expect(filterTooltip(key).value).toContain('filter-tooltip-content')
    }
    expect(() => filterTooltip('missing')).toThrow('Texto de tooltip de filtro não encontrado: missing')
    expect(() => filterActionTooltip('', 'body')).toThrow('Tooltip de ação de filtro incompleto.')
    expect(() => filterActionTooltip('title', '')).toThrow('Tooltip de ação de filtro incompleto.')
    expect(filterActionTooltip('<Ação>', 'A & B').value).toContain('pi-info-circle')
    expect(filterActionTooltip('Ação', 'Corpo', '<ícone>').value).toContain('&lt;ícone&gt;')

    for (const key of ['updateStatus', 'refreshUpdates', 'riskDistribution']) {
      expect(homeTooltip(key).value).toContain('home-tooltip-content')
    }
    expect(() => homeTooltip('missing')).toThrow('Texto de tooltip da página inicial não encontrado: missing')
    expect(() => homeTooltip('riskDistribution', { title: '' })).toThrow('Texto de tooltip da página inicial incompleto.')
    expect(homeTooltip('updateStatus', { detail: '<pronto>', detailLabel: '' }).value).toContain('&lt;pronto&gt;')
    expect(homeTooltip('refreshUpdates', { icon: '' }).value).toContain('pi-info-circle')
    expect(() => homeTooltip('refreshUpdates', { sections: [{ label: '', text: 'quebrado' }] })).toThrow()

    for (const key of Object.keys(FINANCIAL_MOVEMENT_TOOLTIP_COPY)) {
      expect(financialMovementTooltip(key).value).toContain('financial-tooltip-content')
    }
    expect(() => financialMovementTooltip('missing')).toThrow('Texto de tooltip financeiro não encontrado: missing')
    for (const key of NAVBAR_KEYS) expect(navbarTooltip(key).value).toContain('navbar-tooltip-content')
    expect(() => navbarTooltip('missing')).toThrow('Tooltip da navbar não encontrado: missing')
    expect(navbarTooltip('recentCnpj', '<CNJP>').value).toContain('&lt;CNJP&gt;')
    expect(navbarTooltip('comingSoon', '<detalhe>').value).toContain('<strong>Detalhe</strong>')
  })

  it('renderiza alertas de integridade e cobre regras de quantidade e aumento mínimo do panorama', () => {
    for (const tipo of Object.keys(INTEGRITY_ALERT_TOOLTIP_COPY)) {
      expect(integrityAlertTooltip({ tipo }).value).toContain('integrity-tooltip-content')
    }
    expect(() => integrityAlertTooltip({ tipo: 'missing' })).toThrow('Texto de tooltip de alerta não encontrado: missing')
    expect(panoramaAlertTooltip({ tipo: 'volume_atipico', qtd_cnpjs: 1 }, { aumentoMinimo: 'R$ 20,00' }).value)
      .toContain('R$ 20,00')
    expect(panoramaAlertTooltip({ tipo: 'cnpj_dispersao_uf_nao_vizinha', qtd_cnpjs: 2 }).value)
      .toContain('2 estabelecimentos apresentam')
    expect(() => panoramaAlertTooltip({ tipo: 'missing', qtd_cnpjs: 0 })).toThrow('Texto de tooltip do panorama não encontrado: missing')
    expect(() => panoramaAlertTooltip({ tipo: 'volume_atipico', qtd_cnpjs: 0 })).toThrow('Valor mínimo de aumento não informado para o alerta de volume atípico.')
    expect(() => panoramaAlertTooltip({ tipo: 'volume_atipico', qtd_cnpjs: -1 }, { aumentoMinimo: 'R$ 1' }))
      .toThrow('Quantidade de estabelecimentos inválida no alerta: volume_atipico')
    expect(() => panoramaAlertTooltip({ tipo: 'volume_atipico', qtd_cnpjs: NaN }, { aumentoMinimo: 'R$ 1' }))
      .toThrow('Quantidade de estabelecimentos inválida no alerta: volume_atipico')
    expect(() => panoramaAlertTooltip({ tipo: 'volume_atipico', qtd_cnpjs: 0 }, { aumentoMinimo: 'R$ 1' }))
      .not.toThrow()
    expect(panoramaAlertTooltip({ tipo: 'cnpj_dispersao_uf_nao_vizinha', qtd_cnpjs: 0 }).value)
      .toContain('0 estabelecimentos apresentam')
  })

  it('valida conteúdo financeiro incompleto sem deixar a configuração modificada', () => {
    const copy = FINANCIAL_MOVEMENT_TOOLTIP_COPY.totalVendas
    const original = structuredClone(copy)
    try {
      copy.title = ''
      expect(() => financialMovementTooltip('totalVendas')).toThrow('Texto de tooltip financeiro incompleto.')
      copy.title = original.title
      copy.body = ''
      expect(() => financialMovementTooltip('totalVendas')).toThrow('Texto de tooltip financeiro incompleto.')
      copy.body = original.body
      copy.sections = null
      expect(() => financialMovementTooltip('totalVendas')).toThrow('Texto de tooltip financeiro incompleto.')
      copy.sections = []
      expect(() => financialMovementTooltip('totalVendas')).toThrow('Texto de tooltip financeiro incompleto.')
      copy.sections = [{ text: 'sem rótulo' }]
      expect(() => financialMovementTooltip('totalVendas')).toThrow('Seção de tooltip financeiro incompleta.')
      copy.sections = [{ label: 'Cálculo' }]
      expect(() => financialMovementTooltip('totalVendas')).toThrow('Seção de tooltip financeiro incompleta.')
    } finally {
      Object.assign(copy, original)
    }
  })

  it('escapa todos os caracteres HTML do conteúdo financeiro antes de renderizar', () => {
    const copy = FINANCIAL_MOVEMENT_TOOLTIP_COPY.totalVendas
    const original = structuredClone(copy)
    try {
      copy.title = `Título & < > " '`
      copy.body = `Corpo & < > " '`
      copy.sections = [{ label: `Seção & < > " '`, text: `Texto & < > " '` }]

      const tooltip = financialMovementTooltip('totalVendas').value
      expect(tooltip).toContain('Título &amp; &lt; &gt; &quot; &#39;')
      expect(tooltip).toContain('Corpo &amp; &lt; &gt; &quot; &#39;')
      expect(tooltip).toContain('Seção &amp; &lt; &gt; &quot; &#39;')
      expect(tooltip).toContain('Texto &amp; &lt; &gt; &quot; &#39;')
    } finally {
      Object.assign(copy, original)
    }
  })

  it('valida conteúdo de alerta incompleto sem deixar a configuração modificada', () => {
    const copy = INTEGRITY_ALERT_TOOLTIP_COPY.volume_atipico
    const original = structuredClone(copy)
    try {
      copy.title = ''
      expect(() => integrityAlertTooltip({ tipo: 'volume_atipico' })).toThrow('Texto de tooltip de alerta incompleto.')
      copy.title = original.title
      copy.intro = ''
      expect(() => integrityAlertTooltip({ tipo: 'volume_atipico' })).toThrow('Texto de tooltip de alerta incompleto.')
      copy.intro = original.intro
      copy.sections = null
      expect(() => integrityAlertTooltip({ tipo: 'volume_atipico' })).toThrow('Texto de tooltip de alerta incompleto.')
      copy.sections = []
      expect(() => integrityAlertTooltip({ tipo: 'volume_atipico' })).toThrow('Texto de tooltip de alerta incompleto.')
      copy.sections = [{ text: 'sem título' }]
      expect(() => integrityAlertTooltip({ tipo: 'volume_atipico' })).toThrow('Seção de tooltip de alerta sem título.')
      copy.sections = [{ label: 'Cálculo' }]
      expect(() => integrityAlertTooltip({ tipo: 'volume_atipico' })).toThrow('Seção de tooltip de alerta incompleta: Cálculo')
    } finally {
      Object.assign(copy, original)
    }
  })

  it('renderiza e escapa listas de itens nos alertas de integridade', () => {
    const copy = INTEGRITY_ALERT_TOOLTIP_COPY.volume_atipico
    const original = structuredClone(copy)
    try {
      copy.sections = [{ label: 'Itens', items: ['<risco> & "alto"'] }]

      const tooltip = integrityAlertTooltip({ tipo: 'volume_atipico' }).value
      expect(tooltip).toContain('<ul><li>&lt;risco&gt; &amp; &quot;alto&quot;</li></ul>')
    } finally {
      Object.assign(copy, original)
    }
  })

  it('rejeita chaves herdadas e seções de filtro inválidas', () => {
    expect(() => filterTooltip('__proto__')).toThrow('Texto de tooltip de filtro incompleto.')
    expect(() => filterTooltip('constructor')).toThrow('Texto de tooltip de filtro incompleto.')

    const originalDescriptor = Object.getOwnPropertyDescriptor(Object.prototype, 'sections')
    try {
      Object.defineProperty(Object.prototype, 'sections', {
        configurable: true,
        value: [null],
      })
      expect(() => filterTooltip('uf')).toThrow('Seção de tooltip de filtro sem título.')

      Object.defineProperty(Object.prototype, 'sections', {
        configurable: true,
        value: [{ label: 'Sem conteúdo' }],
      })
      expect(() => filterTooltip('uf')).toThrow('Seção de tooltip de filtro incompleta: Sem conteúdo')
    } finally {
      if (originalDescriptor) {
        Object.defineProperty(Object.prototype, 'sections', originalDescriptor)
      } else {
        delete Object.prototype.sections
      }
    }
  })
})

describe('configurações do app, dos endpoints e de gráficos', () => {
  it('seleciona o rótulo de runtime Web ou Desktop', () => {
    expect(APP_RUNTIME).toEqual({ WEB: 'Web', DESKTOP: 'Desktop' })
    expect(getAppRuntimeLabel()).toBe('Web')
    Object.defineProperty(window, 'pywebview', { configurable: true, value: { api: {} } })
    expect(getAppRuntimeLabel()).toBe('Desktop')
    expect(getAppVersionLabel()).toBe(`Desktop v${APP_VERSION}`)
    delete window.pywebview
    expect(getAppVersionLabel()).toBe(`Web v${APP_VERSION}`)
  })

  it('resolve endpoints estáticos e todos os builders de URL com e sem parâmetros opcionais', () => {
    const staticEndpoints = Object.entries(API_ENDPOINTS).filter(([, value]) => typeof value === 'string')
    expect(staticEndpoints.length).toBeGreaterThan(40)
    for (const [, url] of staticEndpoints) expect(url).toContain('/api/v1/')
    const base = new URL(API_ENDPOINTS.analyticsResumo).origin
    const calls = [
      ['analyticsRegionalBenchmarking', ['SP']],
      ['analyticsRegionalBenchmarking', ['SP', 355, '2024-01-01', '2024-12-31']],
      ['analyticsRegionalBenchmarkingAnimation', ['SP', '2024-01-01', '2024-12-31']],
      ['analyticsRegionalBenchmarkingAnimation', ['SP', '2024-01-01', '2024-12-31', 355]],
      ['analyticsCnpjBootstrap', ['123']], ['analyticsEvolucao', ['123']],
      ['analyticsEvolucaoMensalGtin', ['123']], ['analyticsRepasses', ['123']],
      ['analyticsGtinDetalhamentoMensal', ['123', '2024-01']], ['analyticsIndicadores', ['123']],
      ['analyticsIndicadorBenchmarkLocal', ['123', 'teto']], ['analyticsIndicadorEvolucaoBenchmark', ['123', 'teto']],
      ['analyticsGeograficoOrigemUf', ['123']], ['analyticsGeograficoBenchmarkLocal', ['123']],
      ['analyticsIncompatibilidadePatologica', ['123']], ['analyticsFalecidos', ['123']],
      ['analyticsFalecidosExport', ['123', '2024-01', '2024-12', 'csv', '321']],
      ['analyticsFalecidosExport', ['123', null, null, 'xlsx', null]], ['analyticsCrmData', ['123']],
      ['analyticsCrmMedicoEvidenciasExport', [{ crm: '123/DF', inicio: '2024-01' }]],
      ['analyticsCrmMedicoAtuacao', ['123', 'CRM 1/SC']], ['analyticsCrmTimelineDataset', ['123']],
      ['analyticsCrmRaioXExport', ['123', '2024-01-01', '2024-12-31', 'csv']],
      ['analyticsCrmRaioXExport', ['123', null, null, 'xlsx']], ['analyticsCrmPrescritoresExport', ['123']],
      ['analyticsCrmRaioX', ['123', '2024-01-01']], ['analyticsCrmRaioX', ['123', '2024-01-01', 0]],
      ['analyticsCnpjStatus', ['123']], ['analyticsCadastro', ['123']], ['analyticsSocios', ['123']],
      ['analyticsIntegrityAlerts', ['123']], ['analyticsNetwork', ['123']],
      ['analyticsNetworkExpand', ['123', '456']], ['analyticsNetworkLevel3', ['123']],
      ['analyticsNetworkLevel4', ['123']], ['analyticsMovimentacao', ['123']],
      ['analyticsMetricPercentilesAnimation', ['regiao']],
      ['analyticsMetricPercentilesAnimation', ['regiao', 'SP', '355', 'ticket', '2024-01', '2024-12']],
      ['analyticsCpfTimeline', ['123', '456']], ['analyticsNotaTecnica', ['123']],
      ['analyticsNotaTecnicaReadiness', ['123']], ['analyticsNotaTecnicaPrepare', ['123']],
      ['analyticsRelatorioPdfReadiness', ['123']], ['analyticsRelatorioPdfPrepare', ['123']],
      ['evidencia', ['id/seguro']], ['evidenciasDoCnpj', ['123']], ['evidenciasExportar', ['123']],
    ]
    for (const [key, args] of calls) expect(API_ENDPOINTS[key](...args)).toContain(`${base}/api/v1/`)
    expect(API_ENDPOINTS.analyticsRegionalBenchmarking('SP', 355, '2024-01-01', '2024-12-31'))
      .toContain('regiao_id=355')
    expect(API_ENDPOINTS.analyticsMetricPercentilesAnimation('brasil', null, null, null, null, null))
      .toContain('?scope=brasil')
    expect(API_ENDPOINTS.analyticsCrmRaioX('123', '2024-01-01', null)).not.toContain('&hour=')
  })

  it('escolhe a URL base local para o servidor de desenvolvimento', async () => {
    vi.stubEnv('VITE_API_URL', '')
    vi.stubGlobal('window', { location: { port: '5173' } })
    try {
      vi.resetModules()
      const { API_ENDPOINTS: devEndpoints } = await import('@/config/api')
      expect(devEndpoints.analyticsResumo).toContain('127.0.0.1:8002')
    } finally {
      vi.unstubAllGlobals()
      vi.unstubAllEnvs()
      vi.resetModules()
    }

    vi.stubEnv('VITE_API_URL', 'https://api.sentinela.test')
    vi.stubGlobal('window', { location: { port: '5173' } })
    try {
      vi.resetModules()
      const { API_ENDPOINTS: configuredEndpoints } = await import('@/config/api')
      expect(configuredEndpoints.analyticsResumo).toContain('https://api.sentinela.test/api/v1/')
    } finally {
      vi.unstubAllGlobals()
      vi.unstubAllEnvs()
      vi.resetModules()
    }
  })

  it('alterna o tema de gráfico, paleta conhecida e paleta desconhecida', () => {
    mocks.themeStore = reactive({
      isDark: true,
      currentPalette: 'carbon',
      tokens: { textColor: '#eee', mutedColor: '#aaa', borderColor: '#333' },
    })
    const theme = useChartTheme()
    expect(theme.chartTheme.value.tooltip).toContain('rgba(')
    expect(theme.chartTheme.value.tooltipText).toBe('#ffffff')
    expect(theme.chartDataColors.value).toEqual(expect.objectContaining({ green: expect.any(String), red: expect.any(String) }))
    expect(theme.chartRiskAccents.value).toBeDefined()
    expect(theme.chartUFAccents.value).toBeDefined()
    expect(theme.baseChartConfig.value.animationDuration).toBe(900)

    mocks.themeStore.isDark = false
    expect(theme.chartTheme.value.tooltip).toBe('rgba(255, 255, 255, 0.9)')
    expect(theme.chartTheme.value.tooltipText).toBe('#eee')
    expect(theme.chartTheme.value.tooltipSolid).toBe('#ffffff')
    expect(theme.chartDataColors.value).toBeDefined()
    expect(theme.chartRiskAccents.value).toBeDefined()
    expect(theme.chartUFAccents.value).toBeDefined()
    mocks.themeStore.currentPalette = 'azul_dark'
    mocks.themeStore.isDark = true
    expect(theme.chartTheme.value.tooltipSolid).toBeDefined()
    mocks.themeStore.currentPalette = 'desconhecida'
    expect(theme.chartTheme.value.tooltip).toContain('rgba(')

    const originalCardBg = SURFACE_COLORS.carbon.dark['card-bg']
    try {
      SURFACE_COLORS.carbon.dark['card-bg'] = ''
      mocks.themeStore.currentPalette = 'carbon'
      expect(theme.chartTheme.value.tooltip).toBe('rgba(255, 255, 255, 0.8)')
    } finally {
      SURFACE_COLORS.carbon.dark['card-bg'] = originalCardBg
    }
  })

  it('mantém os grupos de faixas de CRM separados por produção e sequência', () => {
    const production = crmFaixasDoGrupo('producao')
    const sequence = crmFaixasDoGrupo('sequencia')

    expect(production).toEqual(Object.keys(CRM_FAIXAS).filter((key) => CRM_FAIXAS[key].grupo === 'producao'))
    expect(sequence).toEqual(['sequenciaDias'])
    expect(crmFaixasDoGrupo('inexistente')).toEqual([])
  })
})
