import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, disposePinia, setActivePinia } from 'pinia'
import axios from 'axios'

import { API_ENDPOINTS } from '@/config/api'
import { CRM_RANKING_DEFAULT_PAGE_SIZE } from '@/config/constants'
import { useCrmPrescricoesAnalysisStore } from '@/stores/crmPrescricoesAnalysis'
import { useCrmPrescricoesMensalStore } from '@/stores/crmPrescricoesMensal'

vi.mock('axios', () => ({ default: { get: vi.fn() } }))

const response = (data) => ({ data })

function mapPayload(overrides = {}) {
  return {
    mapa: [], qtd_medicos: 0, map_level: 'regiao', escopo: 'Região',
    periodo_inicio: '2025-01', periodo_fim: '2025-12', ...overrides,
  }
}

function rankingPayload(page = 1, pageSize = CRM_RANKING_DEFAULT_PAGE_SIZE, overrides = {}) {
  return { ranking: [], qtd_medicos: 0, ranking_page: page, ranking_page_size: pageSize, ...overrides }
}

function mensalPayload(page = 1, pageSize = CRM_RANKING_DEFAULT_PAGE_SIZE, overrides = {}) {
  return { linhas: [], qtd_linhas: 0, page, page_size: pageSize, escopo: 'Brasil', ...overrides }
}

function deferred() {
  let resolve
  let reject
  const promise = new Promise((res, rej) => { resolve = res; reject = rej })
  return { promise, resolve, reject }
}

describe('cobertura das stores de análise de prescrições', () => {
  let pinia

  beforeEach(() => {
    vi.clearAllMocks()
    axios.get.mockResolvedValue(response({}))
    pinia = createPinia()
    setActivePinia(pinia)
  })

  afterEach(() => disposePinia(pinia))

  it('mantém as entradas de cache LRU e valida respostas individuais de mapa e ranking', async () => {
    const store = useCrmPrescricoesAnalysisStore()
    for (let index = 0; index < 9; index += 1) store.touchEntry(`filtro-${index}`)
    expect(store.cacheOrder).toHaveLength(8)
    expect(store.cacheEntries['filtro-0']).toBeUndefined()
    store.resetCachedResponses()
    expect(store.cacheEntries).toEqual({})
    expect(store.cacheOrder).toEqual([])
    expect(store.rankingPage).toBe(1)

    store.cacheVersion = 'v-map'
    axios.get.mockResolvedValueOnce(response(mapPayload()))
    const map = await store.requestMap('map-key', {
      map_level: 'regiao', id_ibge7: 1100015, ids_fixados: 'm1', uf: 'RO',
    }, 'v-map')
    expect(map.map_level).toBe('regiao')
    expect(axios.get).toHaveBeenLastCalledWith(API_ENDPOINTS.analyticsCrmPrescricoesAnalise, expect.objectContaining({
      params: expect.objectContaining({ uf: 'RO', include_map: true, map_only: true }),
    }))
    expect(axios.get.mock.calls.at(-1)[1].params).not.toHaveProperty('id_ibge7')
    expect(axios.get.mock.calls.at(-1)[1].params).not.toHaveProperty('ids_fixados')

    axios.get.mockResolvedValueOnce(response(rankingPayload(2, 5)))
    await expect(store.requestRanking('ranking-key', { ids_fixados: 'm1' }, 'v-map', 2, 5, 'no_medico', 'asc', '  Ana '))
      .resolves.toMatchObject({ ranking_page: 2 })
    expect(axios.get.mock.calls.at(-1)[1].params).toMatchObject({
      ids_fixados: 'm1', page: 2, page_size: 5, sort_field: 'no_medico', sort_order: 'asc', medico_query: '  Ana ', include_map: false,
    })

    await expect(store.requestMap('bad-map', {}, 'v-map')).rejects.toThrow('sem mapa')
    axios.get.mockResolvedValueOnce(response(mapPayload({ escopo: '' })))
    await expect(store.requestMap('bad-meta', {}, 'v-map')).rejects.toThrow('metadados obrigatórios')
    axios.get.mockResolvedValueOnce(response({ ranking: [], qtd_medicos: 0, ranking_page: 1 }))
    await expect(store.requestRanking('bad-ranking', {}, 'v-map', 1, 20, 'no_medico', 'asc', '')).rejects.toThrow('contrato completo')
    axios.get.mockResolvedValueOnce(response(rankingPayload(3, 20)))
    await expect(store.requestRanking('bad-page', {}, 'v-map', 2, 20, 'no_medico', 'asc', '')).rejects.toThrow('paginação divergente')
  })

  it('ativa mapa e ranking, reaproveita cache e invalida dados quando a versão muda', async () => {
    const store = useCrmPrescricoesAnalysisStore()
    const params = { map_level: 'regiao', regiao_id: 1100001, id_ibge7: 1100015, ids_fixados: 'medico-1' }
    axios.get.mockImplementation(async (url, options = {}) => {
      if (url === API_ENDPOINTS.cacheStatus) return response({ cache_version: 'v-activate', status: 'ready' })
      if (options.params?.include_map) return response(mapPayload())
      return response(rankingPayload(options.params.page, options.params.page_size))
    })
    await store.activate(params)
    expect(store.mapResponse).toMatchObject(mapPayload())
    expect(store.rankingResponse).toMatchObject(rankingPayload())
    const consultadas = axios.get.mock.calls.filter(([url]) => url === API_ENDPOINTS.analyticsCrmPrescricoesAnalise).length
    await store.activate(params)
    expect(axios.get.mock.calls.filter(([url]) => url === API_ENDPOINTS.analyticsCrmPrescricoesAnalise)).toHaveLength(consultadas)

    store.rankingSortField = 'nu_prescricoes_farmacias_filtradas'
    await store.activate({ ...params, uf: 'RO' })
    expect(store.rankingSortField).toBe('taxa_prescricoes_dia')

    axios.get.mockImplementation(async (url, options = {}) => {
      if (url === API_ENDPOINTS.cacheStatus) return response({ cache_version: 'v-activate-2', status: 'ready' })
      if (options.params?.include_map) return response(mapPayload({ escopo: 'versão nova' }))
      return response(rankingPayload(options.params.page, options.params.page_size, { qtd_medicos: 3 }))
    })
    await store.activate({ ...params, uf: 'AC' })
    expect(store.cacheVersion).toBe('v-activate-2')
    expect(store.mapResponse.escopo).toBe('versão nova')
    expect(store.rankingResponse.qtd_medicos).toBe(3)
  })

  it('descarta ativações obsoletas quando a consulta de versão conclui ou falha', async () => {
    const store = useCrmPrescricoesAnalysisStore()
    const obsoleteStatus = deferred()
    const currentStatus = deferred()
    const statuses = [obsoleteStatus, currentStatus]
    axios.get.mockImplementation((url, options = {}) => {
      if (url === API_ENDPOINTS.cacheStatus) return statuses.shift().promise
      return Promise.resolve(response(options.params?.include_map
        ? mapPayload({ escopo: options.params.uf })
        : rankingPayload(options.params.page, options.params.page_size)))
    })

    const obsoleteActivation = store.activate({ uf: 'RO' })
    const currentActivation = store.activate({ uf: 'AC' })
    currentStatus.resolve(response({ cache_version: 'v-race-success', status: 'ready' }))
    await currentActivation
    const currentMap = store.mapResponse
    obsoleteStatus.resolve(response({ cache_version: 'v-race-success', status: 'ready' }))
    await obsoleteActivation
    expect(store.activeParams).toEqual({ uf: 'AC' })
    expect(store.mapResponse).toBe(currentMap)

    const obsoleteFailure = deferred()
    const latestStatus = deferred()
    statuses.push(obsoleteFailure, latestStatus)
    const staleFailureActivation = store.activate({ uf: 'SP' })
    const latestActivation = store.activate({ uf: 'BA' })
    latestStatus.resolve(response({ cache_version: 'v-race-failure', status: 'ready' }))
    await latestActivation
    const latestMap = store.mapResponse
    obsoleteFailure.reject(new Error('resposta de ativação obsoleta'))
    await staleFailureActivation
    expect(store.activeParams).toEqual({ uf: 'BA' })
    expect(store.mapResponse).toBe(latestMap)
    expect(store.mapError).toBeNull()
    expect(store.rankingError).toBeNull()
  })

  it('mostra erros apropriados para versão ausente, sincronização e falhas HTTP do ranking', async () => {
    const store = useCrmPrescricoesAnalysisStore()
    axios.get.mockResolvedValueOnce(response({ status: 'ready' }))
    await store.activate({ uf: 'RO' })
    expect(store.mapError).toBe('Status do cache sem versão obrigatória.')
    expect(store.rankingError).toBe('Status do cache sem versão obrigatória.')
    axios.get.mockResolvedValueOnce(response({ cache_version: 'v-fetch', status: 'fetching' }))
    await store.activate({ uf: 'AC' })
    expect(store.mapError).toContain('sincronização')

    axios.get.mockResolvedValueOnce(response({ cache_version: 'v-processing', status: 'processing' }))
    await store.activate({ uf: 'SP' })
    expect(store.rankingError).toContain('sincronização')

    const log = vi.spyOn(console, 'error').mockImplementation(() => {})
    axios.get.mockRejectedValueOnce(new Error('offline'))
    await store.activate({ uf: 'BA' })
    expect(store.mapError).toContain('verificar a versão')
    expect(store.rankingError).toBe(store.mapError)

    store.cacheVersion = 'v-errors'
    store.activeKey = 'key'
    store.activationId = 7
    store.rankingRequestId = 9
    store.activeParams = {}
    axios.get.mockRejectedValueOnce({ response: { status: 503 } })
    await store.loadMap('key', {}, 'v-errors', 7)
    expect(store.mapError).toContain('dados gerenciais')
    axios.get.mockRejectedValueOnce({ response: { status: 422, data: { detail: 'filtro inválido' } } })
    await store.loadRanking('key', {}, 'v-errors', 7, 9, 1, 20, 'no_medico', 'desc', '', false)
    expect(store.rankingError).toBe('filtro inválido')
    axios.get.mockRejectedValueOnce({ response: { status: 422, data: {} } })
    await store.loadRanking('key', {}, 'v-errors', 7, 9, 1, 20, 'no_medico', 'desc', '', true)
    expect(store.rankingPageError).toContain('parâmetros')

    axios.get.mockResolvedValueOnce(response({}))
    await store.loadMap('map-contract', {}, 'v-errors', 7)
    expect(store.mapError).toBe('Resposta da análise de CRMs sem mapa.')
    axios.get.mockRejectedValueOnce(new Error('rede indisponível'))
    await store.loadMap('map-offline', {}, 'v-errors', 7)
    expect(store.mapError).toContain('Não foi possível carregar os dados do mapa')
    expect(log).not.toHaveBeenCalled()
  })

  it('valida busca e paginação do ranking, aceita cache e distingue erro de página', async () => {
    const store = useCrmPrescricoesAnalysisStore()
    store.setRankingSearch('  Ana  ')
    expect(store.rankingSearch).toBe('Ana')
    expect(store.setRankingSearch('x'.repeat(121))).toBe(false)
    expect(store.rankingPageError).toContain('120 caracteres')

    await store.fetchRankingPage(1)
    expect(store.rankingPageError).toContain('ainda não foi carregado')
    store.activeKey = 'ranking-key'
    store.activeParams = { uf: 'RO' }
    store.cacheVersion = 'v-page'
    store.activationId = 4
    store.rankingRequestId = 3
    store.rankingResponseKey = 'ranking-key'
    store.rankingResponse = rankingPayload(1, 20, { filtro_farmacias_ativo: false })
    await store.fetchRankingPage(0)
    expect(store.rankingPageError).toContain('página solicitada')
    await store.fetchRankingPage(2, 0)
    expect(store.rankingPageError).toContain('tamanho solicitado')
    await store.fetchRankingPage(2, 20, 'campo-invalido', 'asc')
    expect(store.rankingPageError).toContain('ordenação solicitada')
    await store.fetchRankingPage(2, 20, 'nu_prescricoes_farmacias_filtradas', 'asc')
    expect(store.rankingPageError).toContain('exige um filtro')
    await store.fetchRankingPage(2, 20, 'no_medico', 'asc', 'x'.repeat(121))
    expect(store.rankingPageError).toContain('120 caracteres')

    axios.get.mockResolvedValueOnce(response(rankingPayload(2, 10, { filtro_farmacias_ativo: true })))
    await store.fetchRankingPage(2, 10, 'no_medico', 'asc', ' Bia ')
    expect(store.rankingResponse.ranking_page).toBe(2)
    expect(store.rankingResponseSearch).toBe('Bia')
    const count = axios.get.mock.calls.length
    await store.fetchRankingPage(2, 10, 'no_medico', 'asc', 'Bia')
    expect(axios.get).toHaveBeenCalledTimes(count)

    store.rankingRequestId += 1
    store.rankingRequestId -= 1
    axios.get.mockRejectedValueOnce({ response: { status: 503 } })
    await store.fetchRankingPage(3, 10, 'no_medico', 'desc', '')
    expect(store.rankingPageError).toContain('dados gerenciais')
  })

  it('descarta páginas antigas do ranking por meio da paginação pública', async () => {
    const store = useCrmPrescricoesAnalysisStore()
    store.activeKey = 'ranking-lru-public'
    store.activeParams = { uf: 'RO' }
    store.cacheVersion = 'v-ranking-lru-public'
    store.activationId = 1
    store.rankingRequestId = 1
    store.rankingResponseKey = store.activeKey
    store.rankingResponse = rankingPayload(1, 20)

    for (let page = 2; page <= 8; page += 1) {
      axios.get.mockResolvedValueOnce(response(rankingPayload(page, 20)))
      await store.fetchRankingPage(page, 20, 'no_medico', 'asc', '')
    }
    const calls = axios.get.mock.calls.length
    expect(store.cacheEntries[store.activeKey].pageOrder).toHaveLength(6)

    axios.get.mockResolvedValueOnce(response(rankingPayload(2, 20)))
    await store.fetchRankingPage(2, 20, 'no_medico', 'asc', '')
    expect(axios.get).toHaveBeenCalledTimes(calls + 1)
    const afterRefetch = axios.get.mock.calls.length
    await store.fetchRankingPage(2, 20, 'no_medico', 'asc', '')
    expect(axios.get).toHaveBeenCalledTimes(afterRefetch)
  })

  it('valida a visão mensal, reaproveita cache e lida com respostas atrasadas e erros', async () => {
    const store = useCrmPrescricoesMensalStore()
    expect(() => store.setTab('invalida')).toThrow('Aba do ranking de CRMs inválida: invalida')
    store.setTab('mes')
    expect(store.tab).toBe('mes')
    await store.loadMensal({}, 'v-invalid', 0, 20, 'no_medico', 'asc')
    expect(store.mensalError).toBe('Página inválida para a visão mensal.')
    await store.loadMensal({}, 'v-invalid', 1, 101, 'no_medico', 'asc')
    expect(store.mensalError).toBe('Página inválida para a visão mensal.')
    await store.loadMensal({}, 'v-invalid', 1, 20, 'no_medico', 'asc')
    expect(store.mensalError).toBe('Ordenação inválida para a visão mensal.')

    const params = { map_level: 'uf', uf: 'RO', data_inicio: '2025-01', data_fim: '2025-12' }
    axios.get.mockResolvedValueOnce(response(mensalPayload(1, CRM_RANKING_DEFAULT_PAGE_SIZE)))
    await store.activateMensal(params, 'Ana', 'v-mensal')
    expect(axios.get).toHaveBeenCalledWith(API_ENDPOINTS.analyticsCrmPrescricoesMensal, expect.objectContaining({
      params: expect.objectContaining({ uf: 'RO', medico_query: 'Ana' }),
    }))
    expect(axios.get.mock.calls.at(-1)[1].params).not.toHaveProperty('map_level')
    expect(store.mensalResponse).toEqual(mensalPayload(1, CRM_RANKING_DEFAULT_PAGE_SIZE))
    expect(store.mensalError).toBeNull()
    const firstCount = axios.get.mock.calls.length
    await store.activateMensal(params, 'Ana', 'v-mensal')
    expect(axios.get).toHaveBeenCalledTimes(firstCount)
    store.mensalResponse = null
    store.mensalPage = 2
    axios.get.mockResolvedValueOnce(response(mensalPayload(2, CRM_RANKING_DEFAULT_PAGE_SIZE)))
    await store.activateMensal(params, 'Ana', 'v-mensal')
    expect(axios.get.mock.calls.at(-1)[1].params.page).toBe(2)
    expect(store.mensalResponse.page).toBe(2)
    axios.get.mockResolvedValueOnce(response(mensalPayload(1, 20)))
    await store.loadMensal({ uf: 'RO' }, 'v-mensal', 1, 20, 'taxa_prescricoes_dia', 'desc')
    expect(store.mensalResponse).toEqual(mensalPayload(1, 20))

    axios.get.mockResolvedValueOnce(response({ linhas: [], qtd_linhas: 0, page: 1, page_size: 20 }))
    await store.loadMensal({ uf: 'AC' }, 'v-invalid-contract', 1, 20, 'competencia', 'asc')
    expect(store.mensalError).toContain('contrato completo')
    axios.get.mockRejectedValueOnce({ response: { status: 422, data: { detail: 'consulta inválida' } } })
    await store.loadMensal({ uf: 'AC' }, 'v-422', 1, 20, 'nu_prescricoes', 'asc')
    expect(store.mensalError).toBe('consulta inválida')
    axios.get.mockRejectedValueOnce({ response: { status: 503, data: { detail: 'módulo indisponível' } } })
    await store.loadMensal({ uf: 'AC' }, 'v-503', 1, 20, 'nu_prescricoes', 'asc')
    expect(store.mensalError).toBe('módulo indisponível')
    axios.get.mockRejectedValueOnce(new Error('offline'))
    await store.loadMensal({ uf: 'AC' }, 'v-generic', 1, 20, 'nu_prescricoes', 'asc')
    expect(store.mensalError).toContain('visão mensal')

    const slow = deferred()
    const fast = deferred()
    axios.get.mockImplementationOnce(() => slow.promise).mockImplementationOnce(() => fast.promise)
    const old = store.loadMensal({ uf: 'AM' }, 'v-race', 1, 20, 'competencia', 'asc')
    const current = store.loadMensal({ uf: 'PA' }, 'v-race', 1, 20, 'competencia', 'asc')
    fast.resolve(response(mensalPayload(1, 20, { escopo: 'PA' })))
    await current
    slow.resolve(response(mensalPayload(1, 20, { escopo: 'AM' })))
    await old
    expect(store.mensalResponse.escopo).toBe('PA')

    const staleFailure = deferred()
    const latestSuccess = deferred()
    axios.get.mockImplementationOnce(() => staleFailure.promise).mockImplementationOnce(() => latestSuccess.promise)
    const staleLoad = store.loadMensal({ uf: 'RR' }, 'v-stale-error', 1, 20, 'competencia', 'asc')
    const latestLoad = store.loadMensal({ uf: 'AP' }, 'v-stale-error', 1, 20, 'competencia', 'asc')
    latestSuccess.resolve(response(mensalPayload(1, 20, { escopo: 'AP' })))
    await latestLoad
    staleFailure.reject(new Error('falha antiga'))
    await staleLoad
    expect(store.mensalResponse.escopo).toBe('AP')
    expect(store.mensalError).toBeNull()

    const pageCacheParams = { uf: 'AC', data_inicio: '2097-01' }
    axios.get.mockImplementation(async (_url, options) => response(mensalPayload(
      options.params.page, options.params.page_size,
    )))
    await store.loadMensal(pageCacheParams, 'v-mensal-page-lru', 1, 20, 'competencia', 'asc')
    const pageCacheCount = axios.get.mock.calls.length
    await store.loadMensal(pageCacheParams, 'v-mensal-page-lru', 1, 20, 'competencia', 'asc')
    expect(axios.get).toHaveBeenCalledTimes(pageCacheCount)
    for (let page = 2; page <= 25; page += 1) {
      await store.loadMensal(pageCacheParams, 'v-mensal-page-lru', page, 20, 'competencia', 'asc')
    }
    const afterFill = axios.get.mock.calls.length
    await store.loadMensal(pageCacheParams, 'v-mensal-page-lru', 1, 20, 'competencia', 'asc')
    expect(axios.get).toHaveBeenCalledTimes(afterFill + 1)
    const afterOldRefetch = axios.get.mock.calls.length
    await store.loadMensal(pageCacheParams, 'v-mensal-page-lru', 25, 20, 'competencia', 'asc')
    expect(axios.get).toHaveBeenCalledTimes(afterOldRefetch)
  })

  it('acumula alertas por período, ignora duplicatas e valida os médicos recebidos', async () => {
    const store = useCrmPrescricoesMensalStore()
    const params = { data_inicio: '2025-01', data_fim: '2025-12', map_level: 'regiao', uf: 'RO' }
    const alerts = { periodo_inicio: '2025-01', periodo_fim: '2025-12', medicos: [
      { id_medico: 'm1', pontos_atencao: ['a'] }, { id_medico: 'm2', pontos_atencao: [] },
    ] }
    axios.get.mockResolvedValueOnce(response(alerts))
    await store.loadAlertas(params, ['m1', 'm1', 'm2'], 'v-alert')
    expect(store.alertas).toEqual({ m1: ['a'], m2: [] })
    expect(store.alertasPeriodo).toEqual({ inicio: '2025-01', fim: '2025-12' })
    const calls = axios.get.mock.calls.length
    await store.loadAlertas(params, ['m1', 'm2'], 'v-alert')
    expect(axios.get).toHaveBeenCalledTimes(calls)

    const pending = deferred()
    axios.get.mockImplementationOnce(() => pending.promise)
    const first = store.loadAlertas({ data_inicio: '2026-01' }, ['m3'], 'v-pending')
    const duplicate = store.loadAlertas({ data_inicio: '2026-01' }, ['m3'], 'v-pending')
    expect(axios.get).toHaveBeenCalledTimes(calls + 1)
    pending.resolve(response({ periodo_inicio: '2026-01', periodo_fim: '2026-12', medicos: [
      { id_medico: 'm3', pontos_atencao: [] },
    ] }))
    await Promise.all([first, duplicate])

    axios.get.mockResolvedValueOnce(response({ periodo_inicio: 'x', periodo_fim: 'y', medicos: [] }))
    await store.loadAlertas(params, ['missing'], 'v-bad')
    expect(store.alertasErro).toContain('médicos diferentes')
    axios.get.mockResolvedValueOnce(response(null))
    await store.loadAlertas(params, ['missing-response'], 'v-null-response')
    expect(store.alertasErro).toContain('médicos diferentes')
    axios.get.mockRejectedValueOnce({ response: { status: 422, data: { detail: 'período inválido' } } })
    await store.loadAlertas(params, ['m4'], 'v-422')
    expect(store.alertasErro).toBe('período inválido')
    axios.get.mockRejectedValueOnce(new Error('offline'))
    await store.loadAlertas(params, ['m5'], 'v-generic')
    expect(store.alertasErro).toContain('alertas dos médicos')

    axios.get.mockResolvedValueOnce(response({ periodo_inicio: 'x', periodo_fim: 'y', medicos: [
      { id_medico: 'm6', pontos_atencao: null },
    ] }))
    await store.loadAlertas(params, ['m6'], 'v-invalid-points')
    expect(store.alertasErro).toContain('médicos diferentes')

    const staleResponse = deferred()
    const currentAlert = { periodo_inicio: '2099-01', periodo_fim: '2099-12', medicos: [
      { id_medico: 'current', pontos_atencao: ['atual'] },
    ] }
    axios.get.mockImplementationOnce(() => staleResponse.promise)
    const staleAlerts = store.loadAlertas({ data_inicio: '2098-01' }, ['stale'], 'v-alert-stale-success')
    axios.get.mockResolvedValueOnce(response(currentAlert))
    await store.loadAlertas({ data_inicio: '2099-01' }, ['current'], 'v-alert-stale-success')
    staleResponse.resolve(response({ periodo_inicio: '2098-01', periodo_fim: '2098-12', medicos: [
      { id_medico: 'stale', pontos_atencao: ['antigo'] },
    ] }))
    await staleAlerts
    expect(store.alertas).toEqual({ current: ['atual'] })

    const staleFailure = deferred()
    axios.get.mockImplementationOnce(() => staleFailure.promise)
    const staleAlertFailure = store.loadAlertas({ data_inicio: '2100-01' }, ['old-error'], 'v-alert-stale-error')
    axios.get.mockResolvedValueOnce(response({ periodo_inicio: '2101-01', periodo_fim: '2101-12', medicos: [
      { id_medico: 'new', pontos_atencao: [] },
    ] }))
    await store.loadAlertas({ data_inicio: '2101-01' }, ['new'], 'v-alert-stale-error')
    staleFailure.reject(new Error('falha obsoleta'))
    await staleAlertFailure
    expect(store.alertas).toEqual({ new: [] })
    expect(store.alertasErro).toBeNull()
  })

  it('valida série mensal, guarda no cache e ignora respostas de período antigo', async () => {
    const store = useCrmPrescricoesMensalStore()
    const params = { data_inicio: '2025-01', data_fim: '2025-12', uf: 'RO', regiao_id: 1100001, id_ibge7: 1100015, page: 4 }
    const serie = { meses: ['2025-01'], medicos: [{ id_medico: 'm1', valores: [1] }] }
    axios.get.mockResolvedValueOnce(response(serie))
    await store.loadSerie(params, ['m1'], 'v-serie')
    expect(store.serieResponse).toEqual(serie)
    expect(axios.get).toHaveBeenLastCalledWith(API_ENDPOINTS.analyticsCrmPrescricoesSerieMensal, {
      params: { data_inicio: '2025-01', data_fim: '2025-12', uf: 'RO', regiao_id: 1100001, id_ibge7: 1100015, ids: 'm1' },
    })
    const count = axios.get.mock.calls.length
    await store.loadSerie(params, ['m1'], 'v-serie')
    expect(axios.get).toHaveBeenCalledTimes(count)

    disposePinia(pinia)
    pinia = createPinia()
    setActivePinia(pinia)
    const cached = useCrmPrescricoesMensalStore()
    await cached.loadSerie(params, ['m1'], 'v-serie')
    expect(cached.serieResponse).toEqual(serie)
    expect(axios.get).toHaveBeenCalledTimes(count)

    axios.get.mockResolvedValueOnce(response({ meses: [], medicos: [] }))
    await store.loadSerie({ uf: 'AC' }, ['m2'], 'v-empty')
    expect(store.serieError).toContain('eixo de meses')
    axios.get.mockResolvedValueOnce(response({ meses: ['2025-01'], medicos: [{ id_medico: 'outro' }] }))
    await store.loadSerie({ uf: 'AC' }, ['m3'], 'v-mismatch')
    expect(store.serieError).toContain('médicos diferentes')
    axios.get.mockRejectedValueOnce({ response: { status: 503, data: { detail: 'série indisponível' } } })
    await store.loadSerie({ uf: 'AC' }, ['m4'], 'v-error')
    expect(store.serieError).toBe('série indisponível')
    expect(store.serieLoading).toBe(false)

    const staleResponse = deferred()
    const currentResponse = deferred()
    axios.get.mockImplementationOnce(() => staleResponse.promise).mockImplementationOnce(() => currentResponse.promise)
    const staleSuccess = store.loadSerie({ uf: 'RO' }, ['m5'], 'v-serie-stale-success')
    const currentSuccess = store.loadSerie({ uf: 'AC' }, ['m6'], 'v-serie-stale-success')
    currentResponse.resolve(response({ meses: ['2025-01'], medicos: [{ id_medico: 'm6' }] }))
    await currentSuccess
    staleResponse.resolve(response({ meses: ['2025-01'], medicos: [{ id_medico: 'm5' }] }))
    await staleSuccess
    expect(store.serieResponse.medicos[0].id_medico).toBe('m6')

    const staleFailure = deferred()
    const latestSerie = deferred()
    axios.get.mockImplementationOnce(() => staleFailure.promise).mockImplementationOnce(() => latestSerie.promise)
    const staleError = store.loadSerie({ uf: 'RR' }, ['m7'], 'v-serie-stale-error')
    const latest = store.loadSerie({ uf: 'AP' }, ['m8'], 'v-serie-stale-error')
    latestSerie.resolve(response({ meses: ['2025-01'], medicos: [{ id_medico: 'm8' }] }))
    await latest
    staleFailure.reject(new Error('falha antiga'))
    await staleError
    expect(store.serieResponse.medicos[0].id_medico).toBe('m8')
    expect(store.serieError).toBeNull()
  })
})
