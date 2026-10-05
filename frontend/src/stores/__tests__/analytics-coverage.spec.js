import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, disposePinia, setActivePinia } from 'pinia'
import axios from 'axios'

import { API_ENDPOINTS } from '@/config/api'
import { FILTER_ALL_VALUE, KPI_PRIORITY_ORDER } from '@/config/constants'
import { RISK_COLORS } from '@/config/colors'
import { RISK_THRESHOLDS } from '@/config/riskConfig'
import { DEFAULT_KPI_STYLE, KPI_CONFIGS } from '@/config/uiConfig'
import { buildAnalyticsParams, requestResumo, useAnalyticsStore } from '@/stores/analytics'

vi.mock('axios', () => ({
  default: { get: vi.fn(), isCancel: vi.fn(() => false) },
}))

const response = (data) => ({ data })
const resumoCompleto = {
  kpis: [{ label: 'Valor total de vendas', value: 10 }],
  resultado_sentinela_uf: [{ uf: 'RO' }],
  resultado_municipios: [{ id_ibge7: 1100015 }],
  resultado_cnpjs: [],
}

function deferred() {
  let resolve
  let reject
  const promise = new Promise((res, rej) => { resolve = res; reject = rej })
  return { promise, resolve, reject }
}

describe('cobertura da store de analytics', () => {
  let pinia

  beforeEach(() => {
    vi.clearAllMocks()
    axios.isCancel.mockReturnValue(false)
    axios.get.mockResolvedValue(response({}))
    pinia = createPinia()
    setActivePinia(pinia)
  })

  afterEach(() => disposePinia(pinia))

  it('monta parâmetros somente para os filtros informados e respeita habilitações', () => {
    expect(buildAnalyticsParams()).toEqual({})
    expect(buildAnalyticsParams(null)).toEqual({})
    expect(buildAnalyticsParams({
      inicio: '2025-01-01', fim: '2025-12-31', percMin: 0, percMax: 100, valMin: 0,
      uf: FILTER_ALL_VALUE, regiaoId: null, idIbge7: undefined,
      cnaeIncompativel: false, socioIdadeAtipica: false, socioFalecido: false,
      volumeAtipicoEnabled: false, dispersaoUfSemFronteiraEnabled: false,
    })).toEqual({ data_inicio: '2025-01-01', data_fim: '2025-12-31' })

    expect(buildAnalyticsParams({
      inicio: '2025-01-01', fim: '2025-12-31', percMin: 1, percMax: 99, valMin: 1,
      uf: 'RO', regiaoId: 0, idIbge7: 0, situacaoRf: 'ATIVA', conexaoMs: 'conectada',
      porteEmpresa: 'grande', grandeRede: 'rede', cnpjRaiz: '12345678', unidadePf: 'RO-1',
      estabelecimento: 'Farmácia', parTeia: 'teia', socioBeneficio: 'sim', socioEsocial: 'nao',
      cnaeIncompativel: true, socioIdadeAtipica: true, socioFalecido: true,
      populacaoMin: 0, populacaoMax: 1000, seqTipo: 'multiplo', seqSeveridadeMin: 2,
      seqDiasMin: 3, seqDiasMax: 6, volumeAtipicoEnabled: true,
      volumeAtipicoPercentual: 60, dispersaoUfSemFronteiraEnabled: true,
      dispersaoUfSemFronteiraPercentual: 70,
    })).toEqual({
      data_inicio: '2025-01-01', data_fim: '2025-12-31', perc_min: 1, perc_max: 99, val_min: 1,
      uf: 'RO', regiao_id: 0, id_ibge7: 0, situacao_rf: 'ATIVA', conexao_ms: 'conectada',
      porte_empresa: 'grande', grande_rede: 'rede', cnpj_raiz: '12345678', unidade_pf: 'RO-1',
      estabelecimento: 'Farmácia', par_teia: 'teia', socio_beneficio: 'sim', socio_esocial: 'nao',
      cnae_incompativel: true, socio_idade_atipica: true, socio_falecido: true,
      populacao_min: 0, populacao_max: 1000, seq_tipo: 'multiplo', seq_severidade_min: 2,
      seq_dias_min: 3, seq_dias_max: 6, volume_atipico: true, volume_atipico_limite: 60,
      dispersao_uf_sem_fronteira: true, dispersao_uf_sem_fronteira_limite: 70,
    })
    expect(buildAnalyticsParams({
      volumeAtipicoEnabled: true, volumeAtipicoPercentual: null,
      dispersaoUfSemFronteiraEnabled: true, dispersaoUfSemFronteiraPercentual: undefined,
    })).toEqual({ volume_atipico: true, dispersao_uf_sem_fronteira: true })
  })

  it('valida todas as seções do resumo, deduplica a consulta e exige cada campo solicitado', async () => {
    await expect(requestResumo({}, null)).rejects.toThrow('Informe as seções do resumo')
    await expect(requestResumo({}, [])).rejects.toThrow('Informe as seções do resumo')
    await expect(requestResumo({}, ['invalida'])).rejects.toThrow('Seções inválidas no resumo: invalida.')
    axios.get.mockResolvedValueOnce(response(resumoCompleto))
    const data = await requestResumo({ uf: 'RO' }, ['municipios', 'kpis', 'kpis', 'ufs', 'cnpjs'])
    expect(data).toBe(resumoCompleto)
    expect(axios.get).toHaveBeenCalledWith(API_ENDPOINTS.analyticsResumo, expect.objectContaining({
      params: { uf: 'RO', secoes: ['cnpjs', 'kpis', 'municipios', 'ufs'] },
      paramsSerializer: { indexes: null },
    }))
    for (const [section, field] of Object.entries({
      kpis: 'kpis', ufs: 'resultado_sentinela_uf', municipios: 'resultado_municipios', cnpjs: 'resultado_cnpjs',
    })) {
      axios.get.mockResolvedValueOnce(response({}))
      await expect(requestResumo({}, [section])).rejects.toThrow(`seção ${section} ausente`)
      expect(field).toBeTruthy()
    }
  })

  it('carrega seções, preserva o contexto nacional, repete pedidos e trata erro e cancelamento', async () => {
    const store = useAnalyticsStore()
    expect(() => store.retryDashboardSummary()).toThrow('Nenhum pedido anterior')
    axios.get.mockResolvedValueOnce(response(resumoCompleto))
    await store.fetchDashboardSummary({}, ['kpis', 'ufs', 'municipios'])
    expect(store.kpis).toEqual(resumoCompleto.kpis)
    expect(store.resultadoSentinelaUFNacional).toEqual(resumoCompleto.resultado_sentinela_uf)
    expect(store.resultadoMunicipios).toEqual(resumoCompleto.resultado_municipios)
    expect(store.lastSync).toBeInstanceOf(Date)
    expect(store.isDashboardFresh(JSON.stringify({}), ['kpis', 'ufs'])).toBe(true)
    expect(store.isDashboardFresh(JSON.stringify({}), [])).toBe(true)

    axios.get.mockResolvedValueOnce(response(resumoCompleto))
    await store.fetchDashboardSummary({ uf: 'RO' }, ['ufs'])
    expect(store.resultadoSentinelaUF).toEqual(resumoCompleto.resultado_sentinela_uf)
    expect(store.resultadoSentinelaUFNacional).toEqual(resumoCompleto.resultado_sentinela_uf)
    axios.get.mockResolvedValueOnce(response(resumoCompleto))
    await store.retryDashboardSummary()
    expect(axios.get).toHaveBeenLastCalledWith(API_ENDPOINTS.analyticsResumo, expect.objectContaining({
      params: expect.objectContaining({ secoes: ['ufs'] }),
    }))
    await expect(store.fetchDashboardSummary({}, ['cnpjs'])).rejects.toThrow('Seções inválidas no resumo: cnpjs.')

    const consoleError = vi.spyOn(console, 'error').mockImplementation(() => {})
    axios.get.mockRejectedValueOnce(new Error('offline'))
    await store.fetchDashboardSummary({}, ['kpis'])
    expect(store.error).toContain('métricas estratégicas')
    axios.isCancel.mockReturnValueOnce(true)
    axios.get.mockRejectedValueOnce(new Error('cancelled'))
    await store.fetchDashboardSummary({}, ['kpis'])
    expect(store.error).toBeNull()
    expect(store.isLoading).toBe(false)
    expect(consoleError).toHaveBeenCalled()
  })

  it('cobre panorama, cache, mapa nacional, faixas de risco e produção semestral', async () => {
    const store = useAnalyticsStore()
    axios.get.mockResolvedValueOnce(response({ alertas: [1] }))
    await store.fetchAlertasPanorama({ uf: 'RO' })
    expect(store.alertasPanorama).toEqual({ alertas: [1] })
    expect(store.alertasPanoramaLoading).toBe(false)
    const log = vi.spyOn(console, 'error').mockImplementation(() => {})
    axios.get.mockRejectedValueOnce(new Error('offline'))
    await store.fetchAlertasPanorama()
    expect(store.alertasPanorama).toBeNull()
    axios.isCancel.mockReturnValueOnce(true)
    axios.get.mockRejectedValueOnce(new Error('cancelled'))
    await store.fetchAlertasPanorama()

    axios.get.mockResolvedValueOnce(response({ status: 'ready' }))
    await store.fetchCacheStatus()
    expect(store.cacheStatus).toEqual({ status: 'ready' })
    axios.get.mockRejectedValueOnce(new Error('offline'))
    await store.fetchCacheStatus()
    expect(store.cacheStatus).toBeNull()
    axios.isCancel.mockReturnValueOnce(true)
    axios.get.mockRejectedValueOnce(new Error('cancelled'))
    await store.fetchCacheStatus()

    axios.get.mockResolvedValueOnce(response({ resultado_sentinela_uf: [{ uf: 'AC' }] }))
    await store.fetchSentinelaUFNacional({ uf: 'RO', regiaoId: 1, idIbge7: 2, cnpjRaiz: '12345678', estabelecimento: 'Farmácia' })
    expect(store.resultadoSentinelaUFNacional).toEqual([{ uf: 'AC' }])
    expect(axios.get).toHaveBeenLastCalledWith(API_ENDPOINTS.analyticsResumo, expect.objectContaining({
      params: { secoes: ['ufs'] },
    }))
    axios.get.mockRejectedValueOnce(new Error('offline'))
    await store.fetchSentinelaUFNacional()
    axios.isCancel.mockReturnValueOnce(true)
    axios.get.mockRejectedValueOnce(new Error('cancelled'))
    await store.fetchSentinelaUFNacional()

    axios.get.mockResolvedValueOnce(response({ buckets: [{ faixa: 'alto' }] }))
    await store.fetchFatorRisco({ uf: 'RO' })
    expect(store.fatorRisco).toEqual([{ faixa: 'alto' }])
    expect(store.fatorRiscoLoading).toBe(false)
    axios.get.mockRejectedValueOnce(new Error('offline'))
    await store.fetchFatorRisco()
    expect(store.error).toContain('fator de risco')
    axios.isCancel.mockReturnValueOnce(true)
    axios.get.mockRejectedValueOnce(new Error('cancelled'))
    await store.fetchFatorRisco()

    axios.get.mockResolvedValueOnce(response({ pontos: [{ semestre: '2025-S1' }] }))
    await store.fetchProducaoSemestral()
    expect(store.producaoSemestral).toEqual([{ semestre: '2025-S1' }])
    axios.get.mockResolvedValueOnce(response({}))
    await store.fetchProducaoSemestral()
    expect(store.producaoSemestral).toEqual([])
    axios.get.mockRejectedValueOnce({ response: { data: { detail: 'período inválido' } } })
    await store.fetchProducaoSemestral()
    expect(store.producaoSemestralError).toBe('período inválido')
    axios.get.mockRejectedValueOnce(new Error('offline'))
    await store.fetchProducaoSemestral()
    expect(store.producaoSemestralError).toContain('produção por semestre')
    axios.isCancel.mockReturnValueOnce(true)
    axios.get.mockRejectedValueOnce(new Error('cancelled'))
    await store.fetchProducaoSemestral()
    expect(store.producaoSemestralLoading).toBe(false)
    expect(log).toHaveBeenCalled()
  })

  it('ignora respostas antigas quando chega uma consulta mais recente', async () => {
    const store = useAnalyticsStore()
    const first = deferred()
    const second = deferred()
    axios.get.mockImplementationOnce(() => first.promise).mockImplementationOnce(() => second.promise)
    const oldRequest = store.fetchDashboardSummary({}, ['kpis'])
    const currentRequest = store.fetchDashboardSummary({}, ['kpis'])
    second.resolve(response({ kpis: [{ label: 'novo' }] }))
    await currentRequest
    first.resolve(response({ kpis: [{ label: 'antigo' }] }))
    await oldRequest
    expect(store.kpis).toEqual([{ label: 'novo' }])

    const oldAlert = deferred()
    const newAlert = deferred()
    axios.get.mockImplementationOnce(() => oldAlert.promise).mockImplementationOnce(() => newAlert.promise)
    const oldAlertRequest = store.fetchAlertasPanorama({ uf: 'AC' })
    const currentAlertRequest = store.fetchAlertasPanorama({ uf: 'RO' })
    newAlert.resolve(response({ id: 'new' }))
    await currentAlertRequest
    oldAlert.resolve(response({ id: 'old' }))
    await oldAlertRequest
    expect(store.alertasPanorama).toEqual({ id: 'new' })
  })

  it('descarta respostas obsoletas do cache, mapa nacional e indicadores', async () => {
    const store = useAnalyticsStore()
    vi.spyOn(console, 'error').mockImplementation(() => {})

    const oldCache = deferred()
    const currentCache = deferred()
    axios.get.mockImplementationOnce(() => oldCache.promise).mockImplementationOnce(() => currentCache.promise)
    const staleCacheRequest = store.fetchCacheStatus()
    const currentCacheRequest = store.fetchCacheStatus()
    currentCache.resolve(response({ status: 'current' }))
    await currentCacheRequest
    oldCache.resolve(response({ status: 'stale' }))
    await staleCacheRequest
    expect(store.cacheStatus).toEqual({ status: 'current' })

    const oldNational = deferred()
    const currentNational = deferred()
    axios.get.mockImplementationOnce(() => oldNational.promise).mockImplementationOnce(() => currentNational.promise)
    const staleNationalRequest = store.fetchSentinelaUFNacional({ uf: 'AC' })
    const currentNationalRequest = store.fetchSentinelaUFNacional({ uf: 'RO' })
    currentNational.resolve(response({ resultado_sentinela_uf: [{ uf: 'RO' }] }))
    await currentNationalRequest
    oldNational.resolve(response({ resultado_sentinela_uf: [{ uf: 'AC' }] }))
    await staleNationalRequest
    expect(store.resultadoSentinelaUFNacional).toEqual([{ uf: 'RO' }])

    const oldRisk = deferred()
    const currentRisk = deferred()
    axios.get.mockImplementationOnce(() => oldRisk.promise).mockImplementationOnce(() => currentRisk.promise)
    const staleRiskRequest = store.fetchFatorRisco({ uf: 'AC' })
    const currentRiskRequest = store.fetchFatorRisco({ uf: 'RO' })
    currentRisk.resolve(response({ buckets: [{ uf: 'RO' }] }))
    await currentRiskRequest
    oldRisk.resolve(response({ buckets: [{ uf: 'AC' }] }))
    await staleRiskRequest
    expect(store.fatorRisco).toEqual([{ uf: 'RO' }])

    const oldProduction = deferred()
    const currentProduction = deferred()
    axios.get.mockImplementationOnce(() => oldProduction.promise).mockImplementationOnce(() => currentProduction.promise)
    const staleProductionRequest = store.fetchProducaoSemestral({ uf: 'AC' })
    const currentProductionRequest = store.fetchProducaoSemestral({ uf: 'RO' })
    currentProduction.resolve(response({ pontos: [{ uf: 'RO' }] }))
    await currentProductionRequest
    oldProduction.reject(new Error('resposta antiga'))
    await staleProductionRequest
    expect(store.producaoSemestral).toEqual([{ uf: 'RO' }])

    const staleProductionSuccess = deferred()
    const latestProductionSuccess = deferred()
    axios.get.mockImplementationOnce(() => staleProductionSuccess.promise).mockImplementationOnce(() => latestProductionSuccess.promise)
    const staleProductionSuccessRequest = store.fetchProducaoSemestral({ uf: 'AC' })
    const latestProductionSuccessRequest = store.fetchProducaoSemestral({ uf: 'SP' })
    latestProductionSuccess.resolve(response({ pontos: [{ uf: 'SP' }] }))
    await latestProductionSuccessRequest
    staleProductionSuccess.resolve(response({ pontos: [{ uf: 'AC' }] }))
    await staleProductionSuccessRequest
    expect(store.producaoSemestral).toEqual([{ uf: 'SP' }])
  })

  it('enriquece KPIs com rótulos, ícones, cores, limiares e ordenação', () => {
    const store = useAnalyticsStore()
    const knownLabel = Object.keys(KPI_CONFIGS)[0]
    const knownConfig = KPI_CONFIGS[knownLabel]
    const percent = '% SEM COMPROVAÇÃO'
    store.kpis = [
      { id: 'unknown', label: 'zz sem prioridade', value: 1 },
      { id: 'percent-high', label: percent.toLowerCase(), value: `${RISK_THRESHOLDS.HIGH + 1}%` },
      { id: 'percent-medium', label: percent, value: String((RISK_THRESHOLDS.MEDIUM + RISK_THRESHOLDS.HIGH) / 2).replace('.', ',') },
      { id: 'percent-low', label: percent, value: `${RISK_THRESHOLDS.MEDIUM}%` },
      { id: 'percent-invalid', label: percent, value: 'sem valor' },
      { id: 'configured', label: knownLabel.toLowerCase(), value: 4 },
      { id: 'overrides', label: knownLabel, value: 5, icon: 'custom-icon', color: 'custom-color' },
      { id: 'missing-value', label: percent },
      { id: 'priority', label: KPI_PRIORITY_ORDER[0], value: 10 },
    ]
    const enriched = store.enrichedKpis
    expect(enriched.find((item) => item.id === 'percent-high').color).toBe(RISK_COLORS.HIGH)
    expect(enriched.find((item) => item.id === 'percent-medium').color).toBe(RISK_COLORS.MEDIUM)
    expect(enriched.find((item) => item.id === 'percent-low').color).toBe(RISK_COLORS.LOW)
    expect(enriched.find((item) => item.id === 'percent-invalid').color).toBeTruthy()
    expect(enriched.find((item) => item.id === 'configured')).toMatchObject({ icon: knownConfig.icon, color: knownConfig.color })
    expect(enriched.find((item) => item.id === 'overrides')).toMatchObject({ icon: 'custom-icon', color: 'custom-color' })
    expect(enriched.find((item) => item.id === 'unknown')).toMatchObject({ icon: DEFAULT_KPI_STYLE.icon, color: DEFAULT_KPI_STYLE.color })
    expect(enriched.find((item) => item.id === 'missing-value').color).toBeTruthy()
    expect(enriched[0].label).toBe(KPI_PRIORITY_ORDER[0])
    expect(store.getKpiById('priority')).toEqual(expect.objectContaining({ id: 'priority' }))
    expect(store.getKpiById('missing')).toBeUndefined()
  })
})
