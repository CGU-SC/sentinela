import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, disposePinia, setActivePinia } from 'pinia'
import axios from 'axios'

import { API_ENDPOINTS } from '@/config/api'
import { requestResumo } from '@/stores/analytics'
import { fetchRegionalPayload } from '@/composables/useRegional'
import { useCnpjDetailStore } from '@/stores/cnpjDetail'

vi.mock('axios', () => ({ default: { get: vi.fn(), post: vi.fn() } }))
vi.mock('@/stores/analytics', () => ({ requestResumo: vi.fn() }))
vi.mock('@/composables/useRegional', () => ({ fetchRegionalPayload: vi.fn() }))

const cnpj = '12345678901234'
const response = (data) => ({ data })

function readinessData(overrides = {}) {
  return {
    ready: true,
    preparable: true,
    modules: [{
      key: 'cadastro', label: 'Cadastro', scope: 'cnpj', required: true,
      ready: true, missing_files: [], preparable: true,
    }],
    missing_modules: [],
    ...overrides,
  }
}

function bootstrapData(overrides = {}) {
  return {
    status: { status: 'valid' },
    cadastro: {
      is_dispersao_uf_nao_vizinha: false,
      pct_dispersao_uf_nao_vizinha: 0,
      valor_dispersao_uf_nao_vizinha: 0,
    },
    cnpj_data: { cnpj },
    geo_data: { sg_uf: 'RO', id_regiao_saude: 1100001 },
    period_summary: { inicio: '2025-01', fim: '2025-12' },
    ...overrides,
  }
}

function repassesData(overrides = {}) {
  return {
    cnpj,
    resumo: { total_repassado: 100 },
    mensal: [],
    pagamentos: [],
    ...overrides,
  }
}

function benchmarkLocalData() {
  return {
    indicador: 'risco',
    kpis: [],
    municipio: { label: 'Município', rows: [] },
    regiao_saude: { label: 'Região', rows: [] },
  }
}

function benchmarkEvolutionData() {
  return {
    indicador: 'risco',
    formato: 'percentual',
    periodo_marcado: { anos: [] },
    series: [],
  }
}

function socioData() {
  return { socios: [] }
}

function benchmarkRow() {
  return {
    cnpj,
    is_conexao_ativa: true,
    is_matriz: false,
    status: 'ATIVA',
    is_alvo: false,
    valor_movimentado: 100,
    valor_sem_comprovacao: 10,
    percentual_nao_comprovacao: 10,
  }
}

function benchmarkLocalWithRow(row, scopeName = 'municipio') {
  return {
    indicador: 'risco',
    kpis: [],
    municipio: { label: 'Município', rows: scopeName === 'municipio' ? [row] : [] },
    regiao_saude: { label: 'Região', rows: scopeName === 'regiao_saude' ? [row] : [] },
  }
}

function readinessWithModule(module) {
  return readinessData({ modules: [module] })
}

function integrityData(overrides = {}) {
  return { total: 0, total_criticos: 0, total_atencao: 0, alertas: [], ...overrides }
}

function deferred() {
  let resolve
  let reject
  const promise = new Promise((res, rej) => { resolve = res; reject = rej })
  return { promise, resolve, reject }
}

describe('cobertura da store de detalhe CNPJ', () => {
  let pinia

  beforeEach(() => {
    vi.clearAllMocks()
    axios.get.mockReset()
    axios.post.mockReset()
    axios.get.mockResolvedValue(response({}))
    axios.post.mockResolvedValue(response({}))
    requestResumo.mockResolvedValue({ resultado_municipios: [] })
    fetchRegionalPayload.mockResolvedValue({})
    pinia = createPinia()
    setActivePinia(pinia)
    vi.spyOn(console, 'error').mockImplementation(() => {})
    vi.spyOn(console, 'warn').mockImplementation(() => {})
  })

  afterEach(() => {
    vi.restoreAllMocks()
    disposePinia(pinia)
  })

  it('valida o acesso e inicializa o bootstrap com cache, falhas e respostas obsoletas', async () => {
    const store = useCnpjDetailStore()
    const invalid = await store.validateCnpjAccess('12.3')
    expect(invalid.status).toBe('invalid_format')
    expect(axios.get).not.toHaveBeenCalled()
    expect(store.setInvalidCnpjFormat('')).toMatchObject({ status: 'invalid_format', cnpj: '' })

    axios.get.mockResolvedValueOnce(response({ status: 'valid', cnpj }))
    await expect(store.validateCnpjAccess(cnpj)).resolves.toMatchObject({ status: 'valid' })
    expect(store.cnpjAccessData).toMatchObject({ status: 'valid' })

    axios.get.mockRejectedValueOnce({ response: { status: 404, data: { detail: { status: 'not_in_program' } } } })
    expect(await store.validateCnpjAccess(cnpj)).toMatchObject({ status: 'not_in_program' })
    expect(store.cnpjAccessMessage).toContain('CNPJ nao encontrado')
    axios.get.mockRejectedValueOnce({ response: { status: 422, data: { detail: {} } } })
    expect(await store.validateCnpjAccess(cnpj)).toMatchObject({ status: 'invalid_format' })
    expect(store.cnpjAccessMessage).toContain('14 digitos')
    axios.get.mockRejectedValueOnce(new Error('offline'))
    expect(await store.validateCnpjAccess(cnpj)).toMatchObject({ status: 'error' })

    expect((await store.fetchBootstrap('123')).status).toBe('invalid_format')
    const payload = bootstrapData()
    axios.get.mockResolvedValueOnce(response(payload))
    await expect(store.fetchBootstrap(cnpj, '2025-01', '2025-12')).resolves.toEqual(payload)
    expect(axios.get).toHaveBeenLastCalledWith(API_ENDPOINTS.analyticsCnpjBootstrap(cnpj), {
      params: { data_inicio: '2025-01', data_fim: '2025-12' },
    })
    expect(store.bootstrapGeoData).toEqual(payload.geo_data)
    expect(store.cnpjsAvulsos.get(cnpj)).toEqual(payload.cnpj_data)
    const callsAfterLoad = axios.get.mock.calls.length
    await expect(store.fetchBootstrap(cnpj, '2025-01', '2025-12')).resolves.toEqual(payload)
    expect(axios.get).toHaveBeenCalledTimes(callsAfterLoad)

    const oldBootstrap = store.bootstrapData
    axios.get.mockRejectedValueOnce({ response: { status: 503, data: { detail: 'refresh indisponível' } } })
    await expect(store.fetchBootstrap(cnpj, '2024-01', '2024-12')).rejects.toMatchObject({
      response: { status: 503 },
    })
    expect(store.bootstrapData).toBe(oldBootstrap)

    for (const failure of [
      { response: { status: 404, data: { detail: { status: 'fora', message: 'fora da base' } } } },
      { response: { status: 422, data: { detail: {} } } },
      { response: { status: 500, data: { detail: 'falha de origem' } } },
      new Error('sem rede'),
    ]) {
      store.cnpjAccessStatus = 'idle'
      axios.get.mockRejectedValueOnce(failure)
      await expect(store.fetchBootstrap(cnpj, `2023-0${axios.get.mock.calls.length}`, null)).rejects.toBeDefined()
      expect(store.bootstrapLoading).toBe(false)
      expect(store.bootstrapRequestKey).toBeNull()
    }

    axios.get.mockRejectedValueOnce({ response: { status: 404 } })
    await expect(store.fetchBootstrap(cnpj, '2019-01')).rejects.toBeDefined()
    expect(store.cnpjAccessStatus).toBe('not_in_program')
    expect(store.cnpjAccessMessage).toContain('CNPJ nao encontrado')

    axios.get.mockResolvedValueOnce(response({ ...bootstrapData(), cadastro: {} }))
    await expect(store.fetchBootstrap(cnpj, '2022-01', '2022-12')).rejects.toThrow('Contrato invalido em bootstrap.cadastro')
    expect(store.bootstrapData).toBeNull()
    axios.get.mockResolvedValueOnce(response({ ...bootstrapData(), period_summary: null }))
    await expect(store.fetchBootstrap(cnpj, '2020-01', '2020-12')).rejects.toThrow('Resposta de bootstrap incompleta')

    const stale = deferred()
    axios.get.mockImplementationOnce(() => stale.promise)
    const staleResponse = store.fetchBootstrap(cnpj, '2021-01', '2021-12')
    store.resetAll()
    stale.resolve(response(bootstrapData()))
    await expect(staleResponse).resolves.toBeNull()
    expect(store.bootstrapLoading).toBe(false)
    expect(store.bootstrapRequestKey).toBeNull()
  })

  it('omite filtros de período ausentes e reaproveita chaves sem datas opcionais', async () => {
    const store = useCnpjDetailStore()

    axios.get.mockResolvedValueOnce(response(bootstrapData()))
    await expect(store.fetchBootstrap(cnpj)).resolves.toMatchObject(bootstrapData())
    expect(axios.get).toHaveBeenLastCalledWith(API_ENDPOINTS.analyticsCnpjBootstrap(cnpj), { params: {} })

    axios.get.mockResolvedValueOnce(response({ meses: [] }))
    await store.fetchEvolucaoMensalGtin(cnpj)
    expect(axios.get).toHaveBeenLastCalledWith(API_ENDPOINTS.analyticsEvolucaoMensalGtin(cnpj), { params: {} })
    const callsAfterMonthlyGtin = axios.get.mock.calls.length
    await store.fetchEvolucaoMensalGtin(cnpj)
    expect(axios.get).toHaveBeenCalledTimes(callsAfterMonthlyGtin)

    axios.get.mockResolvedValueOnce(response({ transacoes: [] }))
    await store.fetchFalecidos(cnpj)
    expect(axios.get).toHaveBeenLastCalledWith(API_ENDPOINTS.analyticsFalecidos(cnpj), { params: {} })

    axios.get.mockResolvedValueOnce(response({ crms_interesse: [], summary: {} }))
    await store.fetchCrmData(cnpj)
    expect(axios.get).toHaveBeenLastCalledWith(API_ENDPOINTS.analyticsCrmData(cnpj), { params: {} })

    axios.get.mockResolvedValueOnce(response({ serie: [] }))
    await store.fetchEvolucaoFinanceira(cnpj)
    expect(axios.get).toHaveBeenLastCalledWith(API_ENDPOINTS.analyticsEvolucao(cnpj), { params: {} })

    axios.get.mockResolvedValueOnce(response(repassesData()))
    await store.fetchRepasses(cnpj)
    expect(axios.get).toHaveBeenLastCalledWith(API_ENDPOINTS.analyticsRepasses(cnpj), { params: {} })

    axios.get.mockResolvedValueOnce(response({ itens: [] }))
    await store.fetchIndicadores(cnpj)
    expect(axios.get).toHaveBeenLastCalledWith(API_ENDPOINTS.analyticsIndicadores(cnpj), { params: {} })

    expect(await store.fetchIndicadorBenchmarkLocal(cnpj, null)).toBeNull()
    expect(await store.fetchIndicadorEvolucaoBenchmark(cnpj, null)).toBeNull()

    axios.get.mockResolvedValueOnce(response(benchmarkEvolutionData()))
    await store.fetchIndicadorEvolucaoBenchmark(cnpj, 'risco')
    expect(axios.get).toHaveBeenLastCalledWith(
      API_ENDPOINTS.analyticsIndicadorEvolucaoBenchmark(cnpj, 'risco'),
      { params: {} },
    )

    axios.get.mockResolvedValueOnce(response({ rows: [], uf_farmacia: 'RO' }))
    await store.fetchGeograficoOrigemUf(cnpj)
    expect(axios.get).toHaveBeenLastCalledWith(API_ENDPOINTS.analyticsGeograficoOrigemUf(cnpj), { params: {} })

    axios.get.mockResolvedValueOnce(response({ municipio: { rows: [] }, regiao_saude: { rows: [] } }))
    await store.fetchGeograficoBenchmarkLocal(cnpj)
    expect(axios.get).toHaveBeenLastCalledWith(API_ENDPOINTS.analyticsGeograficoBenchmarkLocal(cnpj), { params: {} })

    axios.get.mockResolvedValueOnce(response({ summary: {}, patologias: [] }))
    await store.fetchIncompatibilidadePatologica(cnpj)
    expect(axios.get).toHaveBeenLastCalledWith(API_ENDPOINTS.analyticsIncompatibilidadePatologica(cnpj), {
      params: { ranking_municipal_limite: 10 },
    })

    const prepared = { prepared_modules: ['cadastro'], readiness: readinessData() }
    axios.post.mockResolvedValueOnce(response(prepared))
    await store.prepareNotaTecnica(cnpj)
    expect(axios.post).toHaveBeenLastCalledWith(API_ENDPOINTS.analyticsNotaTecnicaPrepare(cnpj), null, { params: {} })

    axios.post.mockResolvedValueOnce(response(prepared))
    await store.prepareRelatorioPdf(cnpj)
    expect(axios.post).toHaveBeenLastCalledWith(API_ENDPOINTS.analyticsRelatorioPdfPrepare(cnpj), null, { params: {} })
  })

  it('rejeita campos obrigatórios ausentes nos contratos públicos de bootstrap, repasses e CRM', async () => {
    const store = useCnpjDetailStore()
    axios.get.mockResolvedValueOnce(response(bootstrapData({ cadastro: null })))
    await expect(store.fetchBootstrap(cnpj, '2009-01'))
      .rejects.toThrow('Resposta de bootstrap incompleta para a tela de estabelecimento.')

    const cadastroFields = [
      'is_dispersao_uf_nao_vizinha',
      'pct_dispersao_uf_nao_vizinha',
      'valor_dispersao_uf_nao_vizinha',
    ]
    let sequence = 0
    for (const field of cadastroFields) {
      for (const value of [undefined, null]) {
        const cadastro = { ...bootstrapData().cadastro }
        if (value === undefined) delete cadastro[field]
        else cadastro[field] = value
        axios.get.mockResolvedValueOnce(response(bootstrapData({ cadastro })))
        sequence += 1
        await expect(store.fetchBootstrap(cnpj, `2010-${String(sequence).padStart(2, '0')}`))
          .rejects.toThrow(`Contrato invalido em bootstrap.cadastro: ${field} obrigatorio.`)
      }
    }

    const invalidRepasses = [
      {},
      { ...repassesData(), resumo: null },
      { ...repassesData(), resumo: {} },
      { ...repassesData(), mensal: null },
      { ...repassesData(), pagamentos: null },
    ]
    for (const payload of invalidRepasses) {
      axios.get.mockResolvedValueOnce(response(payload))
      sequence += 1
      await store.fetchRepasses(cnpj, `2011-${String(sequence).padStart(2, '0')}`)
      expect(store.repassesLoaded).toBe(true)
      expect(store.repassesData).toBeNull()
      expect(store.repassesError).toContain('Verifique a conexão')
    }

    const crmFields = ['qtd_alertas_crm_unico', 'qtd_alertas_geograficos', 'qtd_alertas_crm_multiplos']
    for (const field of crmFields) {
      for (const value of [undefined, null]) {
        const crm = Object.fromEntries(crmFields.map((name) => [name, 0]))
        if (value === undefined) delete crm[field]
        else crm[field] = value
        axios.get.mockResolvedValueOnce(response({ crms_interesse: [crm], summary: {} }))
        sequence += 1
        await store.fetchCrmData(cnpj, `2012-${String(sequence).padStart(2, '0')}`)
        expect(store.prescritoresError).toContain('Verifique a conexão')
      }
    }
  })

  it('despacha abas e prefetch respeitando o CNPJ ativo, o modo CRM e os erros isolados', async () => {
    const store = useCnpjDetailStore()
    await store.ensureTabData('indicadores', '')
    const fetches = ['fetchEvolucaoFinanceira', 'fetchEvolucaoMensalGtin', 'fetchRepasses', 'fetchMovimentacao',
      'fetchIndicadores', 'fetchCrmData', 'fetchCrmTimelineDataset', 'fetchFalecidos', 'fetchSocios', 'fetchNetwork']
    fetches.forEach((method) => { store[method] = vi.fn().mockResolvedValue(undefined) })

    await store.ensureTabData('movimentacao', cnpj, '2025-01', '2025-12', 50)
    expect(store.fetchEvolucaoFinanceira).toHaveBeenCalledWith(cnpj, '2025-01', '2025-12', 50)
    expect(store.fetchEvolucaoMensalGtin).toHaveBeenCalledWith(cnpj, '2025-01', '2025-12')
    expect(store.fetchRepasses).toHaveBeenCalledWith(cnpj, '2025-01', '2025-12')
    await store.ensureTabData('memoria', cnpj)
    await store.ensureTabData('indicadores', cnpj)
    store.activeCrmViewMode = 'cronologia'
    await store.ensureTabData('autorizacoes', cnpj)
    expect(store.fetchCrmTimelineDataset).toHaveBeenCalled()
    store.activeCrmViewMode = 'falecidos'
    await store.ensureTabData('autorizacoes', cnpj)
    await store.ensureTabData('falecidos', cnpj)
    await store.ensureTabData('socios', cnpj)
    await store.ensureTabData('teia', cnpj)
    await store.ensureTabData('desconhecida', cnpj)

    await store.prefetchAllDetailData({ cnpj: '123', concurrency: 1 })
    await store.prefetchAllDetailData({ cnpj, concurrency: 1 })
    expect(store.prefetchRequestKey).toBeNull()
    store.fetchEvolucaoFinanceira = vi.fn().mockImplementation(async () => {
      store.cnpjAccessStatus = 'checking'
      throw new Error('falha isolada')
    })
    store.cnpjAccessStatus = 'valid'
    store.cnpjAccessCnpj = cnpj
    await store.prefetchAllDetailData({ cnpj, inicio: '2024-01', fim: '2024-12', concurrency: 1 })
    store.cnpjAccessStatus = 'valid'
    store.cnpjAccessCnpj = cnpj
    store.fetchEvolucaoFinanceira = vi.fn().mockResolvedValue(undefined)
    store.fetchEvolucaoMensalGtin = vi.fn().mockResolvedValue(undefined)
    store.fetchRepasses = vi.fn().mockResolvedValue(undefined)
    store.fetchIndicadores = vi.fn().mockResolvedValue(undefined)
    store.fetchCrmData = vi.fn().mockResolvedValue(undefined)
    store.fetchCrmTimelineDataset = vi.fn().mockResolvedValue(undefined)
    store.fetchFalecidos = vi.fn().mockResolvedValue(undefined)
    store.fetchSocios = vi.fn().mockResolvedValue(undefined)
    store.fetchNetwork = vi.fn().mockResolvedValue(undefined)
    await store.prefetchAllDetailData({ cnpj, geoData: { sg_uf: 'RO', id_regiao_saude: 1100001 }, concurrency: 1 })
    expect(fetchRegionalPayload).toHaveBeenCalledWith('RO', null, null, 1100001)
  })

  it('carrega cadastro, séries, repasses, detalhamento GTIN, movimentação e indicadores', async () => {
    const store = useCnpjDetailStore()
    await store.fetchDadosCadastro('')
    axios.get.mockResolvedValueOnce(response({ razao_social: 'Farmácia' }))
    await store.fetchDadosCadastro(cnpj)
    expect(store.dadosCadastro).toEqual({ razao_social: 'Farmácia' })
    axios.get.mockRejectedValueOnce(new Error('cadastro indisponível'))
    await store.fetchDadosCadastro(cnpj)
    expect(store.dadosCadastroLoading).toBe(false)

    const financial = { serie: [1] }
    axios.get.mockResolvedValueOnce(response(financial))
    await store.fetchEvolucaoFinanceira(cnpj, '2025-01', '2025-12', 40)
    expect(store.evolucaoFinanceira).toEqual(financial)
    await store.fetchEvolucaoFinanceira(cnpj, '2025-01', '2025-12', 40)
    expect(axios.get).toHaveBeenCalledTimes(3)
    axios.get.mockRejectedValueOnce(new Error('financeiro indisponível'))
    await store.fetchEvolucaoFinanceira(cnpj, '2024-01', '2024-12')
    expect(store.evolucaoError).toContain('Verifique a conexão')

    axios.get.mockResolvedValueOnce(response({ meses: [] }))
    await store.fetchEvolucaoMensalGtin(cnpj, '2025-01', '2025-12')
    expect(store.evolucaoMensalGtin).toEqual({ meses: [] })
    axios.get.mockRejectedValueOnce(new Error('GTIN indisponível'))
    await store.fetchEvolucaoMensalGtin(cnpj, '2024-01', '2024-12')
    expect(store.evolucaoMensalGtinLoading).toBe(false)

    axios.get.mockResolvedValueOnce(response(repassesData()))
    await store.fetchRepasses(cnpj, '2025-01', '2025-12')
    expect(store.repassesLoaded).toBe(true)
    await store.fetchRepasses(cnpj, '2025-01', '2025-12')
    axios.get.mockResolvedValueOnce(response({ cnpj }))
    await store.fetchRepasses(cnpj, '2024-01', '2024-12')
    expect(store.repassesError).toContain('Verifique a conexão')
    axios.get.mockRejectedValueOnce({ response: { data: { detail: 'sem repasses' } } })
    await store.fetchRepasses(cnpj, '2023-01', '2023-12')
    expect(store.repassesError).toBe('sem repasses')

    axios.get.mockResolvedValueOnce(response({ gtins: [] }))
    await store.fetchGtinDetalhamentoMensal(cnpj, '2025-01')
    expect(store.gtinDetalhamentoMensalData).toEqual({ gtins: [] })
    axios.get.mockRejectedValueOnce(new Error('GTIN falhou'))
    await store.fetchGtinDetalhamentoMensal(cnpj, '2025-02')
    expect(store.gtinDetalhamentoMensalError).toContain('Verifique a conexão')

    await store.fetchMovimentacao('')
    axios.get.mockResolvedValueOnce(response({ linhas: [] }))
    await store.fetchMovimentacao('12.345.678/9012-34')
    expect(store.movimentacaoLoadedKey).toBe(cnpj)
    const movementCalls = axios.get.mock.calls.length
    await store.fetchMovimentacao(cnpj)
    expect(axios.get).toHaveBeenCalledTimes(movementCalls)
    axios.get.mockRejectedValueOnce(new Error('memória indisponível'))
    await store.fetchMovimentacao('22345678901234')
    expect(store.movimentacaoError).toContain('Verifique a conexão')

    axios.get.mockResolvedValueOnce(response({ itens: [] }))
    await store.fetchIndicadores(cnpj, '2025-01', '2025-12')
    expect(store.indicadoresLoadedKey).toBe(`${cnpj}|2025-01|2025-12`)
    const indicatorCalls = axios.get.mock.calls.length
    await store.fetchIndicadores(cnpj, '2025-01', '2025-12')
    expect(axios.get).toHaveBeenCalledTimes(indicatorCalls)
    await store.fetchIndicadores('')
    axios.get.mockRejectedValueOnce(new Error('indicadores indisponíveis'))
    await store.fetchIndicadores(cnpj, '2024-01', '2024-12')
    expect(store.indicadoresError).toContain('Verifique a conexão')
  })

  it('valida, cacheia e apresenta erros em benchmarks e indicadores geográficos/clínicos', async () => {
    const store = useCnpjDetailStore()
    expect(await store.fetchIndicadorBenchmarkLocal('', 'risco')).toBeNull()
    expect(await store.fetchIndicadorBenchmarkLocal(cnpj, '  ')).toBeNull()
    const local = benchmarkLocalData()
    axios.get.mockResolvedValueOnce(response(local))
    await expect(store.fetchIndicadorBenchmarkLocal(cnpj, ' risco ', '2025-01', '2025-12')).resolves.toEqual(local)
    await expect(store.fetchIndicadorBenchmarkLocal(cnpj, 'risco', '2025-01', '2025-12')).resolves.toEqual(local)
    expect(store.indicadorBenchmarkLoadingByKey[`${cnpj}|risco|2025-01|2025-12`]).toBe(false)
    store.indicadorBenchmarkLoadingByKey[`${cnpj}|risco|2024-01|2024-12`] = true
    expect(await store.fetchIndicadorBenchmarkLocal(cnpj, 'risco', '2024-01', '2024-12')).toBeNull()
    axios.get.mockRejectedValueOnce({ response: { data: { detail: 'benchmark fora' } } })
    expect(await store.fetchIndicadorBenchmarkLocal(cnpj, 'risco', '2023-01', '2023-12')).toBeNull()
    expect(Object.values(store.indicadorBenchmarkErrorByKey)).toContain('benchmark fora')
    axios.get.mockResolvedValueOnce(response({ indicador: 'risco' }))
    await store.fetchIndicadorBenchmarkLocal(cnpj, 'risco', '2022-01', '2022-12')
    expect(Object.values(store.indicadorBenchmarkErrorByKey)).toContain('Não foi possível carregar os dados. Verifique a conexão com o servidor.')

    const evolution = benchmarkEvolutionData()
    axios.get.mockResolvedValueOnce(response(evolution))
    await expect(store.fetchIndicadorEvolucaoBenchmark(cnpj, 'risco')).resolves.toEqual(evolution)
    expect(await store.fetchIndicadorEvolucaoBenchmark(cnpj, 'risco')).toEqual(evolution)
    store.indicadorEvolucaoBenchmarkLoadingByKey[`${cnpj}|risco-loading||`] = true
    expect(await store.fetchIndicadorEvolucaoBenchmark(cnpj, 'risco-loading')).toBeNull()
    axios.get.mockRejectedValueOnce(new Error('evolução indisponível'))
    await store.fetchIndicadorEvolucaoBenchmark(cnpj, 'risco', '2020-01', '2020-12')
    expect(Object.values(store.indicadorEvolucaoBenchmarkErrorByKey)).toContain('Não foi possível carregar os dados. Verifique a conexão com o servidor.')
    axios.get.mockRejectedValueOnce({ response: { data: { detail: 'benchmark evolutivo indisponível' } } })
    await store.fetchIndicadorEvolucaoBenchmark(cnpj, 'risco', '2018-01', '2018-12')
    expect(Object.values(store.indicadorEvolucaoBenchmarkErrorByKey)).toContain('benchmark evolutivo indisponível')
    axios.get.mockResolvedValueOnce(response({ indicador: 'risco' }))
    await store.fetchIndicadorEvolucaoBenchmark(cnpj, 'risco', '2019-01', '2019-12')
    expect(Object.values(store.indicadorEvolucaoBenchmarkErrorByKey)).toContain('Não foi possível carregar os dados. Verifique a conexão com o servidor.')
    expect(await store.fetchIndicadorEvolucaoBenchmark('', 'risco')).toBeNull()

    expect(await store.fetchGeograficoOrigemUf('')).toBeNull()
    const origin = { rows: [], uf_farmacia: 'RO' }
    axios.get.mockResolvedValueOnce(response(origin))
    await expect(store.fetchGeograficoOrigemUf(cnpj, '2025-01', '2025-12')).resolves.toEqual(origin)
    await expect(store.fetchGeograficoOrigemUf(cnpj, '2025-01', '2025-12')).resolves.toEqual(origin)
    axios.get.mockResolvedValueOnce(response({ rows: [] }))
    await store.fetchGeograficoOrigemUf(cnpj, '2024-01', '2024-12')
    expect(store.geograficoOrigemUfError).toContain('Verifique a conexão')
    axios.get.mockRejectedValueOnce({ response: { data: { detail: 'sem geografia' } } })
    await store.fetchGeograficoOrigemUf(cnpj, '2023-01', '2023-12')
    expect(store.geograficoOrigemUfError).toBe('sem geografia')
    axios.get.mockRejectedValueOnce(new Error('rede indisponível'))
    await store.fetchGeograficoOrigemUf(cnpj, '2022-01', '2022-12')
    expect(store.geograficoOrigemUfError).toContain('Verifique a conexão')

    expect(await store.fetchGeograficoBenchmarkLocal('')).toBeNull()
    const geoBenchmark = { municipio: { rows: [] }, regiao_saude: { rows: [] } }
    axios.get.mockResolvedValueOnce(response(geoBenchmark))
    await expect(store.fetchGeograficoBenchmarkLocal(cnpj)).resolves.toEqual(geoBenchmark)
    await expect(store.fetchGeograficoBenchmarkLocal(cnpj)).resolves.toEqual(geoBenchmark)
    axios.get.mockResolvedValueOnce(response({ municipio: { rows: [] } }))
    await store.fetchGeograficoBenchmarkLocal(cnpj, '2024-01')
    expect(store.geograficoBenchmarkError).toContain('Verifique a conexão')
    axios.get.mockRejectedValueOnce({ response: { data: { detail: 'sem benchmark' } } })
    await store.fetchGeograficoBenchmarkLocal(cnpj, '2023-01')
    expect(store.geograficoBenchmarkError).toBe('sem benchmark')

    expect(await store.fetchIncompatibilidadePatologica('')).toBeNull()
    const clinic = { summary: {}, patologias: [] }
    axios.get.mockResolvedValueOnce(response(clinic))
    await expect(store.fetchIncompatibilidadePatologica(cnpj, '2025-01', '2025-12')).resolves.toEqual(clinic)
    await expect(store.fetchIncompatibilidadePatologica(cnpj, '2025-01', '2025-12')).resolves.toEqual(clinic)
    axios.get.mockResolvedValueOnce(response({ summary: {} }))
    await store.fetchIncompatibilidadePatologica(cnpj, '2024-01', '2024-12')
    expect(store.incompatibilidadePatologicaError).toContain('Verifique a conexão')
    axios.get.mockRejectedValueOnce({ response: { data: { detail: 'falha clínica' } } })
    await store.fetchIncompatibilidadePatologica(cnpj, '2023-01', '2023-12')
    expect(store.incompatibilidadePatologicaError).toBe('falha clínica')
  })

  it('carrega quadro societário, teia, níveis e alertas com cache, concorrência e falhas', async () => {
    const store = useCnpjDetailStore()
    await store.fetchSocios('')
    axios.get.mockResolvedValueOnce(response(socioData()))
    await store.fetchSocios(`12.345.678/9012-34`)
    expect(store.sociosLoaded).toBe(cnpj)
    const sociosCalls = axios.get.mock.calls.length
    await store.fetchSocios(cnpj)
    expect(axios.get).toHaveBeenCalledTimes(sociosCalls)
    axios.get.mockResolvedValueOnce(response({ socios: [{ cnpj }] }))
    await store.fetchSocios('22345678901234')
    expect(store.sociosError).toContain('Verifique a conexão')
    axios.get.mockRejectedValueOnce(new Error('sócios indisponíveis'))
    await store.fetchSocios('32345678901234')
    expect(store.sociosError).toContain('Verifique a conexão')

    expect(await store.fetchNetwork('')).toBeNull()
    const network = { nodes: [], edges: [] }
    const networkRequest = deferred()
    axios.get.mockImplementationOnce(() => networkRequest.promise)
    const networkFirst = store.fetchNetwork(cnpj, '2025-01', '2025-12')
    const networkDuplicate = store.fetchNetwork(cnpj, '2025-01', '2025-12')
    networkRequest.resolve(response(network))
    await expect(networkFirst).resolves.toEqual(network)
    await expect(networkDuplicate).resolves.toEqual(network)
    await expect(store.fetchNetwork(cnpj, '2025-01', '2025-12')).resolves.toEqual(network)
    axios.get.mockRejectedValueOnce(new Error('teia indisponível'))
    await expect(store.fetchNetwork(cnpj, '2024-01', '2024-12')).resolves.toBeNull()
    expect(store.networkError).toContain('Verifique a conexão')

    await expect(store.fetchNetworkLevel('', 3)).resolves.toBeNull()
    await expect(store.fetchNetworkLevel(cnpj, 2)).rejects.toThrow('Nivel de teia invalido: 2')
    const level3 = { nodes: [{ id: '3' }] }
    axios.get.mockResolvedValueOnce(response(level3))
    await expect(store.fetchNetworkLevel(cnpj, 3, '2025-01', '2025-12')).resolves.toEqual(level3)
    await expect(store.fetchNetworkLevel(cnpj, '3', '2025-01', '2025-12')).resolves.toEqual(level3)
    const level4 = { nodes: [{ id: '4' }] }
    const level4Request = deferred()
    axios.get.mockImplementationOnce(() => level4Request.promise)
    const level4First = store.fetchNetworkLevel(cnpj, 4)
    const level4Duplicate = store.fetchNetworkLevel(cnpj, 4)
    level4Request.resolve(response(level4))
    await expect(level4First).resolves.toEqual(level4)
    await expect(level4Duplicate).resolves.toEqual(level4)
    axios.get.mockRejectedValueOnce(new Error('nível indisponível'))
    await expect(store.fetchNetworkLevel('22345678901234', 3)).resolves.toBeNull()
    expect(store.networkLevelLoading[3]).toBe(false)

    store.saveNetworkPresentationState('', { zoom: 1 })
    store.saveNetworkPresentationState(cnpj, null)
    expect(store.getNetworkPresentationState(cnpj)).toBeNull()
    store.saveNetworkPresentationState(`12.345.678/9012-34`, { zoom: 2 })
    expect(store.getNetworkPresentationState(cnpj)).toMatchObject({ cnpj, zoom: 2 })
    expect(store.getNetworkPresentationState('22345678901234')).toBeNull()

    await store.fetchIntegrityAlerts('')
    axios.get.mockResolvedValueOnce(response(integrityData()))
    await store.fetchIntegrityAlerts(cnpj, '2025-01', '2025-12', 55)
    expect(store.integrityAlertsLoaded).toBe(`${cnpj}|2025-01|2025-12|vol:55`)
    const alertCalls = axios.get.mock.calls.length
    await store.fetchIntegrityAlerts(cnpj, '2025-01', '2025-12', 55)
    expect(axios.get).toHaveBeenCalledTimes(alertCalls)
    axios.get.mockResolvedValueOnce(response({ ...integrityData(), alertas: [{}] }))
    await store.fetchIntegrityAlerts(cnpj, '2024-01', '2024-12')
    expect(store.integrityAlertsError).toContain('alertas[0].tipo')
    axios.get.mockRejectedValueOnce({ response: { data: { detail: 'alertas indisponíveis' } } })
    await store.fetchIntegrityAlerts(cnpj, '2023-01', '2023-12')
    expect(store.integrityAlertsError).toBe('alertas indisponíveis')
    axios.get.mockRejectedValueOnce(new Error('sem alertas'))
    await store.fetchIntegrityAlerts(cnpj, '2022-01', '2022-12')
    expect(store.integrityAlertsError).toBe('sem alertas')
    axios.get.mockRejectedValueOnce({})
    await store.fetchIntegrityAlerts(cnpj, '2021-01', '2021-12')
    expect(store.integrityAlertsError).toBe('Não foi possível carregar os dados. Verifique a conexão com o servidor.')
  })

  it('consulta e prepara Nota Técnica e relatório, validando contratos e mensagens de erro', async () => {
    const store = useCnpjDetailStore()
    await expect(store.fetchNotaTecnicaReadiness('')).resolves.toBeNull()
    const ready = readinessData()
    axios.get.mockResolvedValueOnce(response(ready))
    await expect(store.fetchNotaTecnicaReadiness(cnpj, '2025-01', '2025-12')).resolves.toEqual(ready)
    const readinessCalls = axios.get.mock.calls.length
    await expect(store.fetchNotaTecnicaReadiness(cnpj, '2025-01', '2025-12')).resolves.toEqual(ready)
    expect(axios.get).toHaveBeenCalledTimes(readinessCalls)
    axios.get.mockResolvedValueOnce(response(ready))
    await store.fetchNotaTecnicaReadiness(cnpj, '2025-01', '2025-12', { force: true })
    axios.get.mockResolvedValueOnce(response({ ready: true }))
    await expect(store.fetchNotaTecnicaReadiness(cnpj, '2024-01', '2024-12')).resolves.toBeNull()
    expect(store.notaTecnicaReadinessError).toContain('Contrato invalido em nota-tecnica/readiness')
    axios.get.mockRejectedValueOnce({ response: { data: { detail: 'readiness indisponível' } } })
    await store.fetchNotaTecnicaReadiness(cnpj, '2023-01', '2023-12')
    expect(store.notaTecnicaReadinessError).toBe('readiness indisponível')
    axios.get.mockRejectedValueOnce(new Error('offline'))
    await store.fetchNotaTecnicaReadiness(cnpj, '2022-01', '2022-12')
    expect(store.notaTecnicaReadinessError).toBe('offline')
    axios.get.mockRejectedValueOnce({})
    await store.fetchNotaTecnicaReadiness(cnpj, '2021-01', '2021-12')
    expect(store.notaTecnicaReadinessError).toBe('Não foi possível carregar os dados. Verifique a conexão com o servidor.')

    await expect(store.prepareNotaTecnica('')).resolves.toBeNull()
    const prepared = { prepared_modules: ['cadastro'], readiness: ready }
    axios.post.mockResolvedValueOnce(response(prepared))
    await expect(store.prepareNotaTecnica(cnpj, '2025-01', '2025-12')).resolves.toBe(prepared)
    expect(store.notaTecnicaReadinessData).toEqual(ready)
    axios.post.mockRejectedValueOnce({ response: { data: { detail: 'prepare detail' } } })
    await expect(store.prepareNotaTecnica(cnpj)).rejects.toThrow('prepare detail')
    axios.post.mockRejectedValueOnce({ response: { data: { detail: [{ msg: 'campo inválido' }] } } })
    await expect(store.prepareNotaTecnica(cnpj, '2024-01')).rejects.toThrow('campo inválido')
    axios.post.mockRejectedValueOnce(new Error('prepare offline'))
    await expect(store.prepareNotaTecnica(cnpj, '2023-01')).rejects.toThrow('prepare offline')
    expect(store.notaTecnicaPreparing).toBe(false)

    await expect(store.fetchRelatorioPdfReadiness('')).resolves.toBeNull()
    axios.get.mockResolvedValueOnce(response(ready))
    await expect(store.fetchRelatorioPdfReadiness(cnpj)).resolves.toBe(ready)
    const pdfCalls = axios.get.mock.calls.length
    await store.fetchRelatorioPdfReadiness(cnpj)
    expect(axios.get).toHaveBeenCalledTimes(pdfCalls)
    axios.get.mockResolvedValueOnce(response(ready))
    await store.fetchRelatorioPdfReadiness(cnpj, null, null, { force: true })
    axios.get.mockResolvedValueOnce(response({ ready: 'sim' }))
    await store.fetchRelatorioPdfReadiness(cnpj, '2024-01')
    expect(store.relatorioPdfReadinessError).toContain('Contrato invalido em nota-tecnica/readiness')
    axios.get.mockRejectedValueOnce(new Error('pdf offline'))
    await store.fetchRelatorioPdfReadiness(cnpj, '2023-01')
    expect(store.relatorioPdfReadinessError).toBe('pdf offline')
    axios.get.mockRejectedValueOnce({ response: { data: { detail: 'readiness PDF indisponível' } } })
    await store.fetchRelatorioPdfReadiness(cnpj, '2022-01')
    expect(store.relatorioPdfReadinessError).toBe('readiness PDF indisponível')
    axios.get.mockRejectedValueOnce({})
    await store.fetchRelatorioPdfReadiness(cnpj, '2021-01')
    expect(store.relatorioPdfReadinessError).toBe('Não foi possível carregar os dados. Verifique a conexão com o servidor.')

    await expect(store.prepareRelatorioPdf('')).resolves.toBeNull()
    axios.post.mockResolvedValueOnce(response(prepared))
    await expect(store.prepareRelatorioPdf(cnpj, '2025-01', '2025-12')).resolves.toBe(prepared)
    axios.post.mockRejectedValueOnce(new Error('pdf prepare offline'))
    await expect(store.prepareRelatorioPdf(cnpj, '2024-01')).rejects.toThrow('pdf prepare offline')
    expect(store.relatorioPdfPreparing).toBe(false)
  })

  it('busca falecidos, CRM, municípios e percentis e reseta a navegação do detalhe', async () => {
    const store = useCnpjDetailStore()
    await store.fetchFalecidos('')
    axios.get.mockResolvedValueOnce(response({ total: 1 }))
    await store.fetchFalecidos(`12.345.678/9012-34`, '2025-01', '2025-12')
    const deceasedCalls = axios.get.mock.calls.length
    await store.fetchFalecidos(cnpj, '2025-01', '2025-12')
    expect(axios.get).toHaveBeenCalledTimes(deceasedCalls)
    axios.get.mockRejectedValueOnce(new Error('falecidos indisponíveis'))
    await store.fetchFalecidos(cnpj, '2024-01', '2024-12')
    expect(store.falecidosError).toContain('Verifique a conexão')

    await store.fetchCrmData('')
    const crm = { crms_interesse: [], summary: {} }
    axios.get.mockResolvedValueOnce(response(crm))
    await store.fetchCrmData(cnpj, '2025-01', '2025-12')
    const crmCalls = axios.get.mock.calls.length
    await store.fetchCrmData(cnpj, '2025-01', '2025-12')
    expect(axios.get).toHaveBeenCalledTimes(crmCalls)
    axios.get.mockResolvedValueOnce(response({ crms_interesse: [] }))
    await store.fetchCrmData(cnpj, '2024-01', '2024-12')
    expect(store.prescritoresError).toContain('Verifique a conexão')
    axios.get.mockRejectedValueOnce(new Error('CRM offline'))
    await store.fetchCrmData(cnpj, '2023-01', '2023-12')
    expect(store.prescritoresError).toContain('Verifique a conexão')

    await store.fetchCrmTimelineDataset('')
    axios.get.mockResolvedValueOnce(response({ days: [{ dt_janela: '2025-01-01', hours: [], events: [] }] }))
    await store.fetchCrmTimelineDataset(cnpj, '2025-01', '2025-12')
    const timelineCalls = axios.get.mock.calls.length
    await store.fetchCrmTimelineDataset(cnpj, '2025-01', '2025-12')
    expect(axios.get).toHaveBeenCalledTimes(timelineCalls)
    axios.get.mockResolvedValueOnce(response({ days: [{}] }))
    await store.fetchCrmTimelineDataset(cnpj, '2024-01', '2024-12')
    expect(store.crmTimelineDataset).toEqual({ days: [{ dt_janela: '2025-01-01', hours: [], events: [] }] })
    axios.get.mockRejectedValueOnce(new Error('timeline offline'))
    await store.fetchCrmTimelineDataset(cnpj, '2023-01', '2023-12')
    expect(store.crmTimelineDatasetLoading).toBe(false)

    await store.fetchMunicipiosRegiao('', 1)
    await store.fetchMunicipiosRegiao('RO', 0)
    await store.fetchMunicipiosRegiao('RO', 1100001, '2025-01', '2025-12')
    expect(requestResumo).toHaveBeenLastCalledWith({
      data_inicio: '2025-01', data_fim: '2025-12', uf: 'RO', regiao_id: 1100001,
    }, ['municipios'])
    const regionsCalls = requestResumo.mock.calls.length
    await store.fetchMunicipiosRegiao('RO', 1100001, '2025-01', '2025-12')
    expect(requestResumo).toHaveBeenCalledTimes(regionsCalls)
    requestResumo.mockRejectedValueOnce(new Error('região offline'))
    await store.fetchMunicipiosRegiao('AC', 1200001)
    expect(store.municipiosRegiaoLoading).toBe(false)

    store.setMetricPercentilesDirectly(null, 'direto')
    expect(store.metricPercentiles).toEqual([])
    expect(store.metricPercentilesLoaded).toBe('direto')
    await store.fetchMetricPercentiles('brasil')
    const percentilesCalls = axios.get.mock.calls.length
    await store.fetchMetricPercentiles('brasil')
    expect(axios.get).toHaveBeenCalledTimes(percentilesCalls)
    axios.get.mockResolvedValueOnce(response(null))
    await store.fetchMetricPercentiles('uf', 'RO', null, 'score', '2025-01', '2025-12')
    expect(store.metricPercentiles).toEqual([])
    axios.get.mockRejectedValueOnce(new Error('percentis offline'))
    await store.fetchMetricPercentiles('uf', 'AC')
    expect(store.metricPercentilesLoading).toBe(false)

    store.navigateTimeline('2025-01-10', 3, 'aut-1')
    expect(store.selectedTimelineEvent).toMatchObject({ date: '2025-01-10', hour: 3, autorizacao: 'aut-1' })
    expect(store.activeCrmViewMode).toBe('cronologia')
    store.setCrmViewMode('falecidos')
    expect(store.activeCrmViewMode).toBe('falecidos')
    store.clearTimelineNavigation()
    expect(store.selectedTimelineEvent).toBeNull()

    store.resetAll()
    expect(store.cnpjAccessStatus).toBe('idle')
    expect(store.activeCrmViewMode).toBe('medicos')
    expect(store.metricPercentiles).toBeNull()
    expect(store.networkLevelData).toEqual({ 3: null, 4: null })
  })

  it('exercita as variantes inválidas dos contratos de dados do detalhe', async () => {
    const store = useCnpjDetailStore()
    await store.fetchMovimentacao(null)
    expect((await store.validateCnpjAccess(null)).status).toBe('invalid_format')

    const alertFields = ['tipo', 'escopo', 'entidade_id', 'entidade_nome', 'severidade', 'titulo', 'fonte', 'aba_destino']
    const validAlert = Object.fromEntries(alertFields.map((field) => [field, field]))
    const invalidIntegrityPayloads = [
      {},
      { total: 0 },
      { total: 0, total_criticos: 0 },
      { total: 0, total_criticos: 0, total_atencao: 0 },
      ...alertFields.map((field) => ({ ...integrityData(), alertas: [Object.fromEntries(alertFields
        .filter((name) => name !== field).map((name) => [name, validAlert[name]]))] })),
    ]
    for (let index = 0; index < invalidIntegrityPayloads.length; index += 1) {
      axios.get.mockResolvedValueOnce(response(invalidIntegrityPayloads[index]))
      await store.fetchIntegrityAlerts(cnpj, `2010-${String(index + 1).padStart(2, '0')}`)
      expect(store.integrityAlertsError).toBeTruthy()
    }

    const invalidTimelinePayloads = [
      {},
      { days: [{}] },
      { days: [{ dt_janela: '2025-01-01' }] },
      { days: [{ dt_janela: '2025-01-01', hours: [] }] },
    ]
    for (let index = 0; index < invalidTimelinePayloads.length; index += 1) {
      axios.get.mockResolvedValueOnce(response(invalidTimelinePayloads[index]))
      await store.fetchCrmTimelineDataset(cnpj, `2011-${String(index + 1).padStart(2, '0')}`)
    }

    const requiredReadinessFields = ['key', 'label', 'scope', 'required', 'ready', 'missing_files']
    const validModule = readinessData().modules[0]
    const invalidReadinessPayloads = [
      null,
      { ready: 'yes', preparable: true, modules: [], missing_modules: [] },
      { ready: true, preparable: 1, modules: [], missing_modules: [] },
      { ready: true, preparable: true, modules: {}, missing_modules: [] },
      { ready: true, preparable: true, modules: [], missing_modules: {} },
      ...requiredReadinessFields.flatMap((field) => {
        const missing = { ...validModule }
        delete missing[field]
        const empty = { ...validModule, [field]: null }
        return [readinessWithModule(missing), readinessWithModule(empty)]
      }),
      readinessWithModule({ ...validModule, preparable: 'sim' }),
      readinessWithModule({ ...validModule, missing_files: {} }),
    ]
    for (let index = 0; index < invalidReadinessPayloads.length; index += 1) {
      axios.get.mockResolvedValueOnce(response(invalidReadinessPayloads[index]))
      await store.fetchNotaTecnicaReadiness(cnpj, `2012-${String(index + 1).padStart(2, '0')}`)
      expect(store.notaTecnicaReadinessError).toBeTruthy()
    }
    for (const invalidPrepare of [null, {}, { prepared_modules: [], readiness: null }]) {
      axios.post.mockResolvedValueOnce(response(invalidPrepare))
      await expect(store.prepareNotaTecnica(cnpj)).rejects.toThrow('Contrato invalido em nota-tecnica/prepare')
    }

    for (const [index, failure] of [
      { response: { data: { message: 'mensagem alternativa' } } },
      { response: { data: { detail: [{ msg: 'campo', loc: ['body', 'campo'] }] } } },
      { response: { data: { detail: [{ loc: ['body', 'sem-msg'] }] } } },
      {},
    ].entries()) {
      axios.post.mockRejectedValueOnce(failure)
      const expected = ['mensagem alternativa', 'campo', '[object Object]', 'Não foi possível carregar os dados. Verifique a conexão com o servidor.'][index]
      await expect(store.prepareNotaTecnica(cnpj, `2013-0${index + 1}`)).rejects.toThrow(expected)
    }
  })

  it('cobre campos obrigatórios de benchmarks, sócios, CRM, repasses e expansão da teia', async () => {
    const store = useCnpjDetailStore()
    const benchmarkTopFailures = [
      {},
      { indicador: 'risco', kpis: [], municipio: {}, regiao_saude: {} },
      { indicador: 'risco', kpis: [], municipio: { label: 'Município' }, regiao_saude: { label: 'Região', rows: [] } },
      { indicador: 'risco', kpis: [], municipio: { label: 'Município', rows: [] }, regiao_saude: { label: 'Região' } },
    ]
    let sequence = 0
    for (const payload of benchmarkTopFailures) {
      axios.get.mockResolvedValueOnce(response(payload))
      await store.fetchIndicadorBenchmarkLocal(cnpj, `top-${sequence++}`)
    }

    const rowFields = ['cnpj', 'is_conexao_ativa', 'is_matriz', 'status', 'is_alvo', 'valor_movimentado', 'valor_sem_comprovacao', 'percentual_nao_comprovacao']
    for (const field of rowFields) {
      const row = benchmarkRow()
      delete row[field]
      axios.get.mockResolvedValueOnce(response(benchmarkLocalWithRow(row)))
      await store.fetchIndicadorBenchmarkLocal(cnpj, `missing-${field}`, `2014-${String(++sequence).padStart(2, '0')}`)
    }
    for (const field of rowFields.slice(0, -1)) {
      const row = { ...benchmarkRow(), [field]: null }
      axios.get.mockResolvedValueOnce(response(benchmarkLocalWithRow(row, 'regiao_saude')))
      await store.fetchIndicadorBenchmarkLocal(cnpj, `null-${field}`, `2015-${String(++sequence).padStart(2, '0')}`)
    }

    const evolutionBase = {
      indicador: 'risco', formato: 'percentual', periodo_marcado: { anos: [] },
      series: [{ ano_base: 2025, farmacia: 1, regiao_saude: 2, uf: 3 }],
    }
    for (const payload of [
      {},
      { ...evolutionBase, series: [{ ...evolutionBase.series[0], ano_base: 1.5 }] },
      ...['farmacia', 'regiao_saude', 'uf'].map((field) => {
        const point = { ...evolutionBase.series[0] }
        delete point[field]
        return { ...evolutionBase, series: [point] }
      }),
    ]) {
      axios.get.mockResolvedValueOnce(response(payload))
      await store.fetchIndicadorEvolucaoBenchmark(cnpj, `evol-${sequence++}`, `2016-${String(sequence).padStart(2, '0')}`)
    }

    const socioFields = ['cnpj', 'cpf_cnpj_socio', 'indicador_socio', 'is_cadunico', 'is_esocial', 'is_seguro_defeso', 'is_falecido']
    axios.get.mockResolvedValueOnce(response({}))
    await store.fetchSocios('42345678901234')
    for (const [index, field] of socioFields.entries()) {
      const socio = Object.fromEntries(socioFields.map((name) => [name, true]))
      socio[field] = null
      axios.get.mockResolvedValueOnce(response({ socios: [socio] }))
      await store.fetchSocios(`${String(index + 5).repeat(14)}`)
    }

    const crmFields = ['qtd_alertas_crm_unico', 'qtd_alertas_geograficos', 'qtd_alertas_crm_multiplos']
    for (const [index, field] of crmFields.entries()) {
      const crm = Object.fromEntries(crmFields.map((name) => [name, 0]))
      crm[field] = null
      axios.get.mockResolvedValueOnce(response({ crms_interesse: [crm], summary: {} }))
      await store.fetchCrmData(cnpj, `2017-0${index + 1}`)
    }

    const repasseCases = [
      {},
      { cnpj },
      { cnpj, resumo: {} },
      { cnpj, resumo: { total_repassado: 1 } },
      { cnpj, resumo: { total_repassado: 1 }, mensal: [] },
    ]
    for (const [index, payload] of repasseCases.entries()) {
      axios.get.mockResolvedValueOnce(response(payload))
      await store.fetchRepasses(cnpj, `2018-0${index + 1}`)
    }

    expect(await store.expandNetworkNode('', cnpj)).toBeNull()
    axios.get.mockResolvedValueOnce(response({ nodes: [{ id: 'n3' }] }))
    await expect(store.expandNetworkNode(cnpj, '22345678901234', '2025-01', '2025-12'))
      .resolves.toEqual({ nodes: [{ id: 'n3' }] })
    expect(axios.get).toHaveBeenLastCalledWith(API_ENDPOINTS.analyticsNetworkExpand(cnpj, '22345678901234'), {
      params: { data_inicio: '2025-01', data_fim: '2025-12' },
    })
    axios.get.mockRejectedValueOnce(new Error('expansão indisponível'))
    await expect(store.expandNetworkNode(cnpj, '32345678901234')).resolves.toBeNull()
  })

  it('descarta respostas e falhas atrasadas após reset público do detalhe', async () => {
    const store = useCnpjDetailStore()
    vi.spyOn(console, 'error').mockImplementation(() => {})
    const timeline = { days: [{ dt_janela: '2025-01-01', hours: [], events: [] }] }
    const scenarios = [
      { request: () => store.fetchBootstrap(cnpj, '2030-01', '2030-12'), data: bootstrapData(), duplicate: false },
      { request: () => store.fetchEvolucaoFinanceira(cnpj, '2030-01', '2030-12', 50), data: {}, duplicate: true },
      { request: () => store.fetchEvolucaoMensalGtin(cnpj, '2030-01', '2030-12'), data: {}, duplicate: true },
      { request: () => store.fetchRepasses(cnpj, '2030-01', '2030-12'), data: repassesData(), duplicate: true },
      { request: () => store.fetchMovimentacao(cnpj), data: {}, duplicate: true },
      { request: () => store.fetchIndicadores(cnpj, '2030-01', '2030-12'), data: {}, duplicate: true },
      { request: () => store.fetchGeograficoOrigemUf(cnpj, '2030-01', '2030-12'), data: { rows: [], uf_farmacia: 'RO' }, duplicate: true },
      { request: () => store.fetchGeograficoBenchmarkLocal(cnpj, '2030-01', '2030-12'), data: { municipio: { rows: [] }, regiao_saude: { rows: [] } }, duplicate: true },
      { request: () => store.fetchIncompatibilidadePatologica(cnpj, '2030-01', '2030-12'), data: { summary: {}, patologias: [] }, duplicate: true },
      { request: () => store.fetchSocios(cnpj), data: socioData(), duplicate: true },
      { request: () => store.fetchNetwork(cnpj, '2030-01', '2030-12'), data: { nodes: [], edges: [] }, duplicate: true },
      { request: () => store.fetchIntegrityAlerts(cnpj, '2030-01', '2030-12'), data: integrityData(), duplicate: true },
      { request: () => store.fetchNotaTecnicaReadiness(cnpj, '2030-01', '2030-12'), data: readinessData(), duplicate: true },
      { request: () => store.fetchRelatorioPdfReadiness(cnpj, '2030-01', '2030-12'), data: readinessData(), duplicate: true },
      { request: () => store.fetchNetworkLevel(cnpj, 3, '2030-01', '2030-12'), data: { nodes: [] }, duplicate: true },
      { request: () => store.fetchFalecidos(cnpj, '2030-01', '2030-12'), data: {}, duplicate: true },
      { request: () => store.fetchCrmData(cnpj, '2030-01', '2030-12'), data: { crms_interesse: [], summary: {} }, duplicate: true },
      { request: () => store.fetchCrmTimelineDataset(cnpj, '2030-01', '2030-12'), data: timeline, duplicate: true },
      { request: () => store.fetchMetricPercentiles('brasil', null, null, 'score', '2030-01', '2030-12'), data: [], duplicate: true },
    ]

    for (const scenario of scenarios) {
      const pending = deferred()
      axios.get.mockImplementationOnce(() => pending.promise)
      const callsBefore = axios.get.mock.calls.length
      const request = scenario.request()
      const duplicate = scenario.duplicate ? scenario.request() : null
      expect(axios.get).toHaveBeenCalledTimes(callsBefore + 1)
      store.resetAll()
      pending.resolve(response(scenario.data))
      await request
      if (duplicate) await duplicate

      const rejected = deferred()
      axios.get.mockImplementationOnce(() => rejected.promise)
      const staleFailure = scenario.request()
      store.resetAll()
      rejected.reject(new Error('resposta de outro CNPJ'))
      await staleFailure
    }

    expect(store.bootstrapRequestKey).toBeNull()
    expect(store.evolucaoRequestKey).toBeNull()
    expect(store.indicadoresLoadingKey).toBeNull()
    expect(store.networkLevelRequestKey).toEqual({ 3: null, 4: null })
    expect(store.metricPercentilesRequestKey).toBeNull()
  })
})
