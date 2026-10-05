import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, disposePinia, setActivePinia } from 'pinia'
import axios from 'axios'

import { API_ENDPOINTS } from '@/config/api'
import { CRM_RANKING_DEFAULT_PAGE_SIZE } from '@/config/constants'
import { DEFAULT_TARGET_KEY } from '@/config/targetConfig'
import { useAnalyticsStore, buildAnalyticsParams, requestResumo } from '@/stores/analytics'
import { useCnpjDetailStore } from '@/stores/cnpjDetail'
import { useCnpjNavStore } from '@/stores/cnpjNav'
import { useCrmFiltrosMedicoStore, formatarValorFaixa, validarFaixa } from '@/stores/crmFiltrosMedico'
import { useCrmPrescricoesAnalysisStore } from '@/stores/crmPrescricoesAnalysis'
import { useCrmPrescricoesMensalStore } from '@/stores/crmPrescricoesMensal'
import { useEvidenciasStore, chaveEvidencia } from '@/stores/evidencias'
import { useFarmaciaListsStore } from '@/stores/farmaciaLists'
import { useGeoStore } from '@/stores/geo'
import { useMetodologiaConfigStore } from '@/stores/metodologiaConfig'
import { useNotaTecnicaConfigStore } from '@/stores/notaTecnicaConfig'
import { useRecentCnpjStore } from '@/stores/recentCnpj'
import { useRiskIndicatorsStore } from '@/stores/riskIndicators'
import { useSystemUpdateStore } from '@/stores/systemUpdate'
import { useTargetsStore } from '@/stores/targets'
import { useThemeStore } from '@/stores/theme'

vi.mock('axios', () => ({
  default: {
    get: vi.fn(),
    put: vi.fn(),
    post: vi.fn(),
    patch: vi.fn(),
    delete: vi.fn(),
    isCancel: vi.fn(() => false),
  },
}))

const RECOVERY_STATUS = {
  backup: {
    exists: false, valid: false, kind: 'joint', evidencias_backup_valid: false,
    watchlist_count: null, evidencias_count: null, missing_watchlist_count: null,
    missing_evidencias_count: null, farmacias_mantidas_count: null,
  },
  corrupt: {
    exists: false, valid: false, kind: 'joint', evidencias_backup_valid: false,
    watchlist_count: null, evidencias_count: null, missing_watchlist_count: null,
    missing_evidencias_count: null, farmacias_mantidas_count: null,
  },
}

const METODOLOGIA = {
  audit_high_value: 10000,
  volume_atipico_aumento_minimo: 0.5,
  defaults: { audit_high_value: 10000, volume_atipico_aumento_minimo: 0.5 },
  limits: {
    audit_high_value: { min: 100, max: 1000000 },
    volume_atipico_aumento_minimo: { min: 0.1, max: 5 },
  },
}

function response(data) {
  return { data }
}

function validMap() {
  return {
    mapa: [],
    qtd_medicos: 0,
    map_level: 'regiao',
    escopo: 'Região',
    periodo_inicio: '2025-01',
    periodo_fim: '2025-12',
  }
}

function validRanking(page = 1, pageSize = CRM_RANKING_DEFAULT_PAGE_SIZE) {
  return { ranking: [], qtd_medicos: 0, ranking_page: page, ranking_page_size: pageSize }
}

describe('stores Pinia — contratos e fluxos', () => {
  let pinia

  beforeEach(() => {
    vi.clearAllMocks()
    localStorage.clear()
    axios.isCancel.mockReturnValue(false)
    axios.get.mockImplementation(async (url) => {
      if (url === API_ENDPOINTS.preferences) {
        return response({ filters: {}, ui: {}, watchlist: [] })
      }
      if (url === API_ENDPOINTS.evidencias) return response([])
      if (url === API_ENDPOINTS.preferencesRecoveryStatus) return response(RECOVERY_STATUS)
      if (url === API_ENDPOINTS.preferencesWatchlistUltimaRemocao) {
        return response({ farmacias: [], removido_em: null })
      }
      if (url === API_ENDPOINTS.analyticsNotaTecnicaRegionais) return response([])
      if (url === API_ENDPOINTS.preferencesMetodologia) return response(METODOLOGIA)
      return response({})
    })
    axios.put.mockImplementation(async (url, payload) => {
      if (url === API_ENDPOINTS.preferencesWatchlist) return response({ watchlist: payload.interesse })
      if (url === API_ENDPOINTS.preferencesMetodologia) return response(METODOLOGIA)
      return response({})
    })
    axios.post.mockResolvedValue(response({}))
    axios.patch.mockResolvedValue(response({}))
    axios.delete.mockResolvedValue(response({}))

    pinia = createPinia()
    setActivePinia(pinia)
  })

  afterEach(async () => {
    disposePinia(pinia)
    localStorage.clear()
  })

  it('analytics converte filtros territoriais em IDs e valida somente as seções pedidas', async () => {
    expect(buildAnalyticsParams({
      uf: 'RO', regiaoId: 1100001, idIbge7: 1100015,
      percMin: 0, percMax: 100, valMin: 0,
      volumeAtipicoEnabled: true, volumeAtipicoPercentual: 65,
    })).toEqual({
      uf: 'RO', regiao_id: 1100001, id_ibge7: 1100015,
      volume_atipico: true, volume_atipico_limite: 65,
    })

    await expect(requestResumo({}, ['ufs'], {})).rejects.toThrow(
      'Contrato inválido em analytics/resumo: seção ufs ausente.',
    )
    axios.get.mockResolvedValueOnce(response({ resultado_sentinela_uf: [] }))
    await expect(requestResumo({}, ['ufs'], {})).resolves.toEqual({ resultado_sentinela_uf: [] })
    expect(axios.get).toHaveBeenLastCalledWith(API_ENDPOINTS.analyticsResumo, expect.objectContaining({
      params: { secoes: ['ufs'] },
      paramsSerializer: { indexes: null },
    }))
  })

  it('analytics conserva seções não solicitadas e marca a chave da seção carregada', async () => {
    axios.get.mockResolvedValueOnce(response({ kpis: [{ id: 'vendas', value: 12 }] }))
    const store = useAnalyticsStore()
    await store.fetchDashboardSummary({ uf: 'RO' }, ['kpis'])

    expect(store.kpis).toEqual([{ id: 'vendas', value: 12 }])
    expect(store.resultadoMunicipios).toEqual([])
    expect(store.sectionKeys.kpis).toBe(JSON.stringify({ uf: 'RO' }))
    expect(store.isDashboardFresh(JSON.stringify({ uf: 'RO' }), ['kpis'])).toBe(true)
    expect(store.isDashboardFresh(JSON.stringify({ uf: 'RO' }), ['ufs'])).toBe(false)
  })

  it('geo deriva filtros territoriais por ID e cacheia estabelecimentos pelo período', async () => {
    const store = useGeoStore()
    store.localidades = [
      { id_ibge7: 1100015, id_regiao_saude: 1100001, sg_uf: 'RO', no_municipio: 'Alta Floresta', no_regiao_saude: 'Central', unidade_pf: 'RO-1' },
      { id_ibge7: 1100205, id_regiao_saude: 1100002, sg_uf: 'RO', no_municipio: 'Porto Velho', no_regiao_saude: 'Madeira', unidade_pf: 'RO-2' },
    ]

    expect(store.municipiosPorFiltro('RO', '1100001', 'Todos')).toEqual([
      { label: 'Todos', value: 'Todos' },
      { label: 'Alta Floresta', value: '1100015', nome: 'Alta Floresta', uf: 'RO' },
    ])
    expect(store.getRegiaoByIbge7('1100015')).toBe('1100001')
    expect(store.regioesPorUF('RO')).toEqual([
      { label: 'Todos', value: 'Todos' },
      { label: 'Central', value: '1100001' },
      { label: 'Madeira', value: '1100002' },
    ])

    axios.get.mockResolvedValue(response({ estabelecimentos: [{ id_ibge7: 1100015, cnpj: '1' }] }))
    await store.fetchEstabelecimentos('2025-01-01', '2025-12-31')
    await store.fetchEstabelecimentos('2025-01-01', '2025-12-31')
    expect(axios.get).toHaveBeenCalledTimes(1)
    expect(store.estabelecimentosPorIbge7.get(1100015)).toHaveLength(1)
    await store.fetchEstabelecimentos('2026-01-01', '2026-12-31')
    expect(axios.get).toHaveBeenCalledTimes(2)
  })

  it('CNPJ detail normaliza acesso, carrega indicadores uma vez por chave e limpa estado ao trocar de CNPJ', async () => {
    const store = useCnpjDetailStore()
    const cnpj = '12345678000195'
    axios.get.mockImplementation(async (url) => {
      if (url === API_ENDPOINTS.analyticsCnpjStatus(cnpj)) return response({ status: 'valid', cnpj })
      if (url === API_ENDPOINTS.analyticsIndicadores(cnpj)) return response({ risco: 'alto' })
      return response({})
    })

    const access = await store.validateCnpjAccess('12.345.678/0001-95')
    expect(access).toEqual({ status: 'valid', cnpj })
    expect(store.cnpjAccessStatus).toBe('valid')

    await store.fetchIndicadores(cnpj, '2025-01-01', '2025-12-31')
    await store.fetchIndicadores(cnpj, '2025-01-01', '2025-12-31')
    expect(store.indicadoresData).toEqual({ risco: 'alto' })
    expect(axios.get).toHaveBeenCalledTimes(2)

    store.navigateTimeline('2025-06-01', 9, 'A-123')
    expect(store.activeCrmViewMode).toBe('cronologia')
    expect(store.selectedTimelineEvent).toMatchObject({ date: '2025-06-01', hour: 9, autorizacao: 'A-123' })
    store.resetAll()
    expect(store.indicadoresData).toBeNull()
    expect(store.selectedTimelineEvent).toBeNull()
    expect(store.cnpjAccessStatus).toBe('idle')
  })

  it('CNPJ detail rejeita formato inválido sem fazer chamada HTTP', async () => {
    const store = useCnpjDetailStore()
    const result = await store.validateCnpjAccess('12.345')
    expect(result.status).toBe('invalid_format')
    expect(result.cnpj).toBe('12345')
    expect(axios.get).not.toHaveBeenCalled()
  })

  it('navegação do CNPJ consome a seleção pendente uma única vez e pode ser reiniciada', () => {
    const store = useCnpjNavStore()
    store.navigateToRegiao(1100015)
    expect(store.activeTabIndex).toBe(7)
    expect(store.consumePendingMunicipio()).toBe(1100015)
    expect(store.consumePendingMunicipio()).toBeNull()

    store.navigateToRegiao()
    expect(store.consumePendingMunicipio()).toBe('__RESET__')
    store.reset(3)
    expect(store.activeTabIndex).toBe(3)
    expect(store.pendingMunicipio).toBeNull()
  })

  it('CRM médico valida faixas e gera parâmetros ordenados só para filtros ativos', () => {
    const store = useCrmFiltrosMedicoStore()
    expect(store.apiParams).toEqual({})
    store.setUfsCrm(['SP', 'RO', 'SP'])
    store.setFaixa('exclusividade', { min: 10, max: 80 })
    expect(store.apiParams.uf_crm).toEqual(['RO', 'SP'])
    expect(store.apiParams).toHaveProperty('exclusividade_min', 10)
    expect(store.apiParams).toHaveProperty('exclusividade_max', 80)
    expect(formatarValorFaixa('exclusividade', 80)).toBe('80%')
    expect(validarFaixa('exclusividade', { min: 81, max: 80 })).toBe('O mínimo é maior que o máximo.')
    expect(() => store.setUfsCrm(['XX'])).toThrow('UF do CRM inválida: XX')
    expect(store.qtdAtivos).toBe(2)
    store.limpar()
    expect(store.apiParams).toEqual({})
    expect(store.qtdAtivos).toBe(0)
  })

  it('análise de prescrições exige versão de cache e valida mapa e ranking', async () => {
    const store = useCrmPrescricoesAnalysisStore()
    axios.get.mockImplementation(async (url, options = {}) => {
      if (url === API_ENDPOINTS.cacheStatus) return response({ cache_version: 'cache-v1', status: 'ready' })
      if (url === API_ENDPOINTS.analyticsCrmPrescricoesAnalise) {
        return response(options.params.include_map ? validMap() : validRanking())
      }
      return response({})
    })

    await store.activate({
      map_level: 'regiao', regiao_id: 1100001, id_ibge7: 1100015, ids_fixados: 'medico-1',
    })

    expect(store.cacheVersion).toBe('cache-v1')
    expect(store.mapResponse).toMatchObject(validMap())
    expect(store.rankingResponse).toMatchObject(validRanking())
    const requests = axios.get.mock.calls.filter(([url]) => url === API_ENDPOINTS.analyticsCrmPrescricoesAnalise)
    expect(requests).toHaveLength(2)
    const mapParams = requests.find(([, options]) => options.params.include_map)[1].params
    const rankingParams = requests.find(([, options]) => !options.params.include_map)[1].params
    expect(mapParams).not.toHaveProperty('id_ibge7')
    expect(mapParams).not.toHaveProperty('ids_fixados')
    expect(rankingParams).toHaveProperty('id_ibge7', 1100015)
    expect(rankingParams).toHaveProperty('ids_fixados', 'medico-1')
  })

  it('análise de prescrições falha visivelmente quando falta a versão do cache', async () => {
    axios.get.mockResolvedValue(response({ status: 'ready' }))
    const store = useCrmPrescricoesAnalysisStore()
    await store.activate({ uf: 'RO' })
    expect(store.mapError).toBe('Status do cache sem versão obrigatória.')
    expect(store.rankingError).toBe('Status do cache sem versão obrigatória.')
    expect(axios.get).toHaveBeenCalledTimes(1)
  })

  it('visão mensal de prescrições exclui map_level e exige paginação compatível', async () => {
    const store = useCrmPrescricoesMensalStore()
    const mensal = { linhas: [{ id_medico: 'm1', competencia: '2025-01' }], qtd_linhas: 1, page: 1, page_size: CRM_RANKING_DEFAULT_PAGE_SIZE, escopo: 'RO' }
    axios.get.mockResolvedValue(response(mensal))
    store.setTab('mes')
    await store.activateMensal({ map_level: 'uf', uf: 'RO', regiao_id: 1100001 }, '', 'cache-v1')

    expect(store.mensalResponse).toEqual(mensal)
    expect(store.mensalLoading).toBe(false)
    expect(axios.get).toHaveBeenCalledWith(API_ENDPOINTS.analyticsCrmPrescricoesMensal, expect.objectContaining({
      params: expect.objectContaining({ uf: 'RO', regiao_id: 1100001, page: 1, page_size: CRM_RANKING_DEFAULT_PAGE_SIZE }),
    }))
    expect(axios.get.mock.calls[0][1].params).not.toHaveProperty('map_level')

    await store.loadMensal({}, 'cache-v1', 1, 20, 'campo_nao_permitido', 'asc')
    expect(store.mensalError).toBe('Ordenação inválida para a visão mensal.')
    expect(axios.get).toHaveBeenCalledTimes(1)
  })

  it('evidências só marcam depois de carregar e monitorar a farmácia', async () => {
    const evidencias = useEvidenciasStore()
    const listas = useFarmaciaListsStore()
    await Promise.resolve()
    await Promise.resolve()
    expect(evidencias.loadState).toBe('ready')
    expect(listas.canEdit).toBe(true)

    const evidencia = {
      id: 7, cnpj: '12345678000195', tipo: 'dia', dt_janela: '2025-02-10',
      hora: null, criado_em: '2025-02-11T12:00:00Z',
    }
    axios.post.mockResolvedValue(response(evidencia))
    const resultado = await evidencias.marcar({
      cnpj: evidencia.cnpj, tipo: evidencia.tipo, dt_janela: evidencia.dt_janela,
    }, { razaoSocial: 'Farmácia Exemplo' })

    expect(resultado).toEqual({ evidencia, farmaciaAdicionada: true })
    expect(listas.isInteresse(evidencia.cnpj)).toBe(true)
    expect(evidencias.contar(evidencia.cnpj)).toBe(1)
    expect(evidencias.encontrar(evidencia)).toEqual(evidencia)
    expect(axios.put).toHaveBeenCalledWith(API_ENDPOINTS.preferencesWatchlist, {
      interesse: [expect.objectContaining({ cnpj: evidencia.cnpj, razaoSocial: 'Farmácia Exemplo' })],
    })
    expect(chaveEvidencia(evidencia)).toBe(evidencia.cnpj + '|dia|2025-02-10')
  })

  it('cesta de evidências rejeita alteração antes do carregamento e tipo desconhecido', async () => {
    const store = useEvidenciasStore()
    await expect(store.marcar({ cnpj: '12345678000195', tipo: 'dia', dt_janela: '2025-01-01' }))
      .rejects.toThrow('A cesta de evidências ainda não foi carregada.')
    expect(() => chaveEvidencia({ cnpj: '1', tipo: 'outro' })).toThrow('Tipo de evidência desconhecido: outro')
  })

  it('targets monta parâmetros de tabela e aplica a resposta paginada', async () => {
    const filters = await import('@/stores/filters')
    filters.useFilterStore()
    const store = useTargetsStore()
    store.page = 3
    store.rowsPerPage = 10
    store.sortField = 'valor_incompativel'
    store.sortOrder = 1
    axios.get.mockResolvedValue(response({
      kpis: [{ label: 'Farmácias', value: 1 }],
      mapa: [{ id_ibge7: 1100015, total: 1 }],
      items: [{ cnpj: '12345678000195' }],
      total: 21, page: 3, page_size: 10, sort_field: 'valor_incompativel', sort_order: 'asc',
    }))

    await store.loadCurrentTarget()
    expect(store.selectedTarget).toBe(DEFAULT_TARGET_KEY)
    expect(store.rows).toEqual([{ cnpj: '12345678000195' }])
    expect(store.totalRecords).toBe(21)
    expect(store.isLoading).toBe(false)
    expect(axios.get).toHaveBeenCalledWith(API_ENDPOINTS.targetParkinsonMenor50, expect.objectContaining({
      params: expect.objectContaining({ page: 3, page_size: 10, sort_order: 'asc' }),
    }))
  })

  it('indicadores de risco guarda resumo e mostra erro para contrato incompleto', async () => {
    const store = useRiskIndicatorsStore()
    axios.get.mockResolvedValueOnce(response({ municipios: [{ id_ibge7: 1100015 }], kpis: { total_critico: 1 } }))
    await store.fetchRiskIndicatorSummary('ticket_medio', { uf: 'RO', regiao_id: 1100001 })
    expect(store.selectedRiskIndicator).toBe('ticket_medio')
    expect(store.municipios).toEqual([{ id_ibge7: 1100015 }])
    expect(store.kpis).toEqual({ total_critico: 1 })

    axios.get.mockResolvedValueOnce(response({ municipios: [] }))
    await store.fetchRiskIndicatorSummary('ticket_medio', { uf: 'AC' })
    expect(store.summaryError).toBe('Nao foi possivel carregar a analise do indicador.')
    expect(store.summaryParamsKey).toBe(JSON.stringify({ indicador: 'ticket_medio', params: { uf: 'RO', regiao_id: 1100001 } }))
  })

  it('configuração metodológica aplica limites obrigatórios e envia a alteração completa', async () => {
    const store = useMetodologiaConfigStore()
    await store.ensureLoaded()
    expect(store.loaded).toBe(true)
    expect(store.auditHighValue).toBe(10000)
    expect(store.auditHighValueLimits).toEqual(METODOLOGIA.limits.audit_high_value)

    const saved = { ...METODOLOGIA, audit_high_value: 25000 }
    axios.put.mockResolvedValueOnce(response(saved))
    await store.saveAuditHighValue(25000)
    expect(axios.put).toHaveBeenCalledWith(API_ENDPOINTS.preferencesMetodologia, {
      metodologia: { audit_high_value: 25000, volume_atipico_aumento_minimo: 0.5 },
    })
    expect(store.auditHighValue).toBe(25000)

    disposePinia(pinia)
    pinia = createPinia()
    setActivePinia(pinia)
    const broken = useMetodologiaConfigStore()
    axios.get.mockResolvedValueOnce(response({ audit_high_value: 10000 }))
    await expect(broken.ensureLoaded()).rejects.toThrow('Configuração metodológica incompleta.')
    expect(broken.loaded).toBe(false)
    expect(broken.loading).toBe(false)
  })

  it('configuração da Nota Técnica carrega regionais, valida seleção e persiste assinantes normalizados', async () => {
    const store = useNotaTecnicaConfigStore()
    axios.get.mockImplementation(async (url) => {
      if (url === API_ENDPOINTS.analyticsNotaTecnicaRegionais) {
        return response([{ codigo: 'RO', estado: 'Rondônia' }])
      }
      if (url === API_ENDPOINTS.preferences) {
        return response({ nota_tecnica: { regional_codigo: 'RO', ultimo_numero_nota: 'NT-1' } })
      }
      return response({})
    })
    await store.ensureLoaded()
    expect(store.selectedRegionalLabel).toBe('RO - Rondônia')
    await expect(store.saveRegionalCodigo('XX')).rejects.toThrow('Regional emissora inválida: XX.')

    axios.put.mockResolvedValueOnce(response({ nota_tecnica: { regional_codigo: 'RO' } }))
    await store.saveNotaTecnicaConfig({
      regionalCodigo: ' ro ', numeroNota: ' NT-2 ', numeroProcesso: ' 123 ',
      assinantes: [{ nome: ' Ana ', cargo: ' Auditora ' }, { nome: '', cargo: '' }],
      gerarPdf: true,
    })
    expect(axios.put).toHaveBeenCalledWith(API_ENDPOINTS.preferencesNotaTecnica, {
      nota_tecnica: {
        regional_codigo: 'RO', ultimo_numero_nota: 'NT-2', ultimo_numero_processo: '123',
        assinantes_tecnicos: [{ nome: 'Ana', cargo: 'Auditora' }], gerar_pdf_visualizacao: true,
      },
    })
  })

  it('atualização do sistema expõe estado e impede fechar o diálogo durante download', async () => {
    const store = useSystemUpdateStore()
    axios.post.mockResolvedValueOnce(response({
      status: 'update_required', current_version: '1.0.0', latest_version: '2.0.0',
      minimum_supported_version: '1.5.0', download_url: 'https://example.invalid/app',
      release_notes_url: null, checked_at: '2026-10-02T12:00:00Z', source: 'remote',
      message: 'Atualização necessária', block_title: null, block_message: null, blocked_since: null,
    }))
    await store.forceCheckUpdate()
    expect(store.isBlocked).toBe(true)
    expect(store.statusLabel).toBe('Atualização obrigatória')
    expect(store.statusTone).toBe('critical')

    store.downloadStatus = 'downloading'
    store.openDownloadDialog()
    store.closeDownloadDialog()
    expect(store.downloadDialogVisible).toBe(true)
    expect(store.isDownloading).toBe(true)
  })

  it('tema inicial respeita modo salvo e mantém a paleta oficial', async () => {
    vi.useFakeTimers()
    const store = useThemeStore()
    axios.get.mockResolvedValueOnce(response({ ui: { themeMode: 'light', themePalette: 'azul_dark' } }))
    await store.initTheme()
    expect(store.isDark).toBe(false)
    expect(store.currentPalette).toBe('carbon')
    expect(store.tokens.bgColor).toBeTruthy()
    expect(document.documentElement.classList.contains('light-mode')).toBe(true)
    expect(axios.put).toHaveBeenCalledWith(API_ENDPOINTS.preferencesUi, {
      ui: { themeMode: 'light', themePalette: 'carbon' },
    })
    await vi.runAllTimersAsync()
    vi.useRealTimers()
  })

  it('último CNPJ persiste o par cadastral e limpa o armazenamento', () => {
    const store = useRecentCnpjStore()
    store.set('12345678000195', 'Farmácia Exemplo')
    expect(store.recent).toEqual({ cnpj: '12345678000195', razaoSocial: 'Farmácia Exemplo' })
    expect(JSON.parse(localStorage.getItem('sentinela_recent_cnpj'))).toEqual(store.recent)

    store.clear()
    expect(store.recent).toBeNull()
    expect(localStorage.getItem('sentinela_recent_cnpj')).toBeNull()
  })
})
