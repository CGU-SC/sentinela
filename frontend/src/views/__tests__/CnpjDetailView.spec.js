import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, disposePinia, setActivePinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'
import axios from 'axios'
import { nextTick } from 'vue'

import CnpjDetailView from '@/views/CnpjDetailView.vue'
import { useCnpjDetailStore } from '@/stores/cnpjDetail'
import { useCnpjNavStore } from '@/stores/cnpjNav'
import { useFilterStore } from '@/stores/filters'
import { useGeoStore } from '@/stores/geo'
import { useNotaTecnicaConfigStore } from '@/stores/notaTecnicaConfig'
import { useRecentCnpjStore } from '@/stores/recentCnpj'

const mocks = vi.hoisted(() => ({
  toastAdd: vi.fn(),
  exportCnpjPdf: vi.fn(),
  loadCnpjPdfReportData: vi.fn(),
  convertDocxToPdf: vi.fn(),
  downloadBlobFromResponse: vi.fn(),
  getApiErrorMessage: vi.fn(async (_, fallback) => fallback),
  logCnpjPerf: vi.fn(),
  perfSessionSequence: 0,
}))

vi.mock('axios', () => ({
  default: {
    get: vi.fn(),
    put: vi.fn(),
    post: vi.fn(),
    patch: vi.fn(),
    delete: vi.fn(),
  },
}))
vi.mock('primevue/usetoast', () => ({ useToast: () => ({ add: mocks.toastAdd }) }))
vi.mock('@/composables/usePdfExport', () => ({
  usePdfExport: () => ({ isExporting: false, exportCnpjPdf: mocks.exportCnpjPdf }),
}))
vi.mock('@/composables/useCnpjPdfReportData', () => ({ loadCnpjPdfReportData: mocks.loadCnpjPdfReportData }))
vi.mock('@/utils/apiErrors', () => ({ getApiErrorMessage: mocks.getApiErrorMessage }))
vi.mock('@/utils/download', () => ({
  convertDocxToPdf: mocks.convertDocxToPdf,
  downloadBlobFromResponse: mocks.downloadBlobFromResponse,
}))
vi.mock('@/views/components/nota-tecnica/NotaTecnicaRegionalDialog.vue', () => ({
  default: {
    props: ['visible', 'continueLabel'],
    emits: ['update:visible', 'saved'],
    template: '<div data-test="regional-dialog" :data-visible="visible" :data-label="continueLabel"><button data-test="close-regional-dialog" @click="$emit(\'update:visible\', false)">Fechar</button><button data-test="save-regional-dialog" @click="$emit(\'saved\', { numeroNota: \'NT 001/2026\', numeroProcesso: \'00000.000001/2026-00\', assinantesTecnicos: [{ nome: \'Auditor\', cargo: \'Auditor Federal\' }], gerarPdf: true })">Salvar regional</button></div>',
  },
}))
vi.mock('@/utils/cnpjPerfLogger', () => ({
  createCnpjPerfSession: () => ({ sessionId: `test-session-${mocks.perfSessionSequence++}` }),
  logCnpjPerf: mocks.logCnpjPerf,
}))

const EMPTY_PREFERENCES = { filters: {}, ui: { sidebarCollapsed: false, sidebarLocked: false }, nota_tecnica: {} }
const VALID_CNPJ = '12345678000195'
const READY_MODULES = { ready: true, preparable: false, modules: [], missing_modules: [] }

function deferred() {
  let resolve
  let reject
  const promise = new Promise((res, rej) => { resolve = res; reject = rej })
  return { promise, resolve, reject }
}

describe('CnpjDetailView — estado de acesso', () => {
  let pinia
  let router
  let wrapper
  let store

  beforeEach(async () => {
    localStorage.clear()
    mocks.perfSessionSequence = 0
    axios.get.mockImplementation(async (url) => {
      if (String(url).includes('/evidencias')) return { data: [] }
      if (String(url).includes('/preferences')) return { data: EMPTY_PREFERENCES }
      if (String(url).includes('/nota-tecnica/regionais')) return { data: [] }
      return { data: {} }
    })
    axios.put.mockResolvedValue({ data: {} })
    mocks.toastAdd.mockReset()
    mocks.exportCnpjPdf.mockReset()
    mocks.loadCnpjPdfReportData.mockReset()
    mocks.loadCnpjPdfReportData.mockResolvedValue({ title: 'Relatório pronto' })
    mocks.convertDocxToPdf.mockReset()
    mocks.downloadBlobFromResponse.mockReset()
    mocks.getApiErrorMessage.mockReset()
    mocks.getApiErrorMessage.mockImplementation(async (_, fallback) => fallback)

    pinia = createPinia()
    setActivePinia(pinia)
    store = useCnpjDetailStore()
    router = createRouter({
      history: createMemoryHistory(),
      routes: [
        { path: '/estabelecimentos/:cnpj', name: 'EstablishmentDetail', component: CnpjDetailView },
        { path: '/estabelecimentos', name: 'Establishments', component: { template: '<div />' } },
      ],
    })
    await router.push('/estabelecimentos/12')
    await router.isReady()
  })

  afterEach(() => {
    wrapper?.unmount()
    wrapper = null
    disposePinia(pinia)
    localStorage.clear()
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  function mountValid() {
    return mount(CnpjDetailView, {
      global: {
        plugins: [pinia, router],
        stubs: {
          CnpjHeader: {
            props: [
              'cnpj', 'cnpjData', 'geoData', 'qtdMunicipiosRegiao', 'periodSummary',
              'periodLoading', 'noteReadiness', 'pdfReadiness',
            ],
            emits: ['export', 'generate-note', 'navigate-section'],
            template: '<header data-test="cnpj-header" :data-cnpj="cnpj" :data-geo="geoData?.id_regiao_saude" :data-municipios="qtdMunicipiosRegiao" :data-summary="periodSummary ? JSON.stringify(periodSummary) : \'null\'" :data-note="noteReadiness?.ready" :data-pdf="pdfReadiness?.ready"><button data-test="export-pdf" @click="$emit(\'export\')">Exportar PDF</button><button data-test="generate-note" @click="$emit(\'generate-note\', {})">Gerar Nota</button><button data-test="navigate-section" @click="$emit(\'navigate-section\', \'regional\')">Região</button><button data-test="navigate-invalid" @click="$emit(\'navigate-section\', \'inexistente\')">Seção inválida</button></header>',
          },
          EvidenciasPanel: {
            props: ['cnpj', 'razaoSocial'],
            template: '<div data-test="evidence-panel" :data-name="razaoSocial" />',
          },
          FinancialMovementTab: { template: '<div data-test="financial-tab" />' },
          IndicatorsTab: { template: '<div data-test="indicators-tab" />' },
          RegionalTab: { template: '<div data-test="regional-tab" />' },
          AuthTab: {
            props: ['razaoSocial'],
            template: '<div data-test="auth-tab" :data-name="razaoSocial" />',
          },
          CalculationMemoryTab: { template: '<div data-test="memory-tab" />' },
          RiskDiagnosisTab: { template: '<div data-test="diagnosis-tab" />' },
          SociosTab: { template: '<div data-test="socios-tab" />' },
          NetworkTab: { template: '<div data-test="network-tab" />' },
          CnpjTabLoadingOverlay: {
            props: ['visible'],
            template: '<div v-if="visible" data-test="tab-loading" />',
          },
          TabView: {
            props: ['activeIndex'],
            emits: ['tab-change'],
            template: '<div data-test="tab-view"><slot /><button v-for="index in 8" :key="index - 1" :data-test="`tab-${index - 1}`" @click="$emit(\'tab-change\', { index: index - 1 })">Aba {{ index - 1 }}</button></div>',
          },
          TabPanel: { template: '<section><slot name="header" /><slot /></section>' },
        },
      },
    })
  }

  async function useValidCnpj({ query = {} } = {}) {
    await router.push({ path: `/estabelecimentos/${VALID_CNPJ}`, query })
    await router.isReady()
    store.fetchBootstrap = vi.fn(async (cnpj) => {
      store.cnpjAccessStatus = 'valid'
      store.cnpjAccessCnpj = cnpj
      store.bootstrapData = { qtd_municipios_regiao: 3 }
      store.bootstrapGeoData = { id_regiao_saude: 1100001, id_ibge7: 1100015 }
      store.bootstrapPeriodSummary = { totalMov: 500, valSemComp: 25, percValSemComp: 5 }
      store.cnpjsAvulsos.set(cnpj, { cnpj, razao_social: 'Farmácia Teste', id_ibge7: 1100015 })
      store.bootstrapLoading = false
      return { status: { status: 'valid' } }
    })
    store.fetchIntegrityAlerts = vi.fn().mockResolvedValue({ total: 0, total_criticos: 0, total_atencao: 0, alertas: [] })
    store.fetchNotaTecnicaReadiness = vi.fn().mockResolvedValue(READY_MODULES)
    store.fetchRelatorioPdfReadiness = vi.fn().mockResolvedValue(READY_MODULES)
    store.ensureTabData = vi.fn().mockResolvedValue()
    const config = useNotaTecnicaConfigStore(pinia)
    config.selectedRegionalCodigo = 'RO'
    config.ensureLoaded = vi.fn().mockResolvedValue()
    return {
      config,
      nav: useCnpjNavStore(pinia),
      filters: useFilterStore(pinia),
      geo: useGeoStore(pinia),
    }
  }

  it('mostra o estado de formato inválido sem tentar consultar o bootstrap', async () => {
    wrapper = mount(CnpjDetailView, { global: { plugins: [pinia, router] } })
    await flushPromises()

    expect(store.cnpjAccessStatus).toBe('invalid_format')
    expect(wrapper.get('.cnpj-access-state h2').text()).toBe('Identificador invalido')
    expect(wrapper.text()).toContain('CNPJ pesquisado')
    expect(wrapper.text()).toContain('12')
    expect(axios.get.mock.calls.some(([url]) => String(url).includes('/bootstrap'))).toBe(false)
  })

  it('ignora alterações de período quando o identificador da rota não contém dígitos', async () => {
    await router.push('/estabelecimentos/abc')
    wrapper = mount(CnpjDetailView, { global: { plugins: [pinia, router] } })
    await flushPromises()
    const fetchBootstrap = vi.spyOn(store, 'fetchBootstrap')
    const filters = useFilterStore(pinia)

    filters.periodo = [new Date('2024-01-01T12:00:00'), new Date('2024-12-31T12:00:00')]
    await nextTick()
    await flushPromises()

    expect(store.cnpjAccessStatus).toBe('invalid_format')
    expect(fetchBootstrap).not.toHaveBeenCalled()
  })

  it('volta à listagem de estabelecimentos pelo botão de ação', async () => {
    wrapper = mount(CnpjDetailView, { global: { plugins: [pinia, router] } })
    await flushPromises()
    await wrapper.get('.access-state-action').trigger('click')
    await flushPromises()

    expect(router.currentRoute.value.name).toBe('Establishments')
  })

  it('exibe o estado da base PFPB quando o bootstrap responde 404', async () => {
    axios.get.mockImplementation(async (url) => {
      if (String(url).includes('/bootstrap')) {
        throw Object.assign(new Error('CNPJ ausente'), {
          response: { status: 404, data: { detail: { status: 'not_in_program', message: 'CNPJ não consta no PFPB.' } } },
        })
      }
      if (String(url).includes('/nota-tecnica/regionais')) return { data: [] }
      if (String(url).includes('/preferences')) return { data: EMPTY_PREFERENCES }
      return { data: [] }
    })
    await router.push(`/estabelecimentos/${VALID_CNPJ}`)
    wrapper = mount(CnpjDetailView, { global: { plugins: [pinia, router] } })
    await flushPromises()

    expect(store.cnpjAccessStatus).toBe('not_in_program')
    expect(wrapper.get('.cnpj-access-state').classes()).toContain('cnpj-access-state--warning')
    expect(wrapper.get('.cnpj-access-state h2').text()).toBe('CNPJ nao encontrado no Farmacia Popular')
    expect(wrapper.text()).toContain('12.345.678/0001-95')
    expect(wrapper.find('.detail-tabs').exists()).toBe(false)
  })

  it('mostra indisponibilidade quando o bootstrap falha por erro inesperado', async () => {
    axios.get.mockImplementation(async (url) => {
      if (String(url).includes('/bootstrap')) throw new Error('Servidor indisponível')
      if (String(url).includes('/nota-tecnica/regionais')) return { data: [] }
      if (String(url).includes('/preferences')) return { data: EMPTY_PREFERENCES }
      return { data: [] }
    })
    await router.push(`/estabelecimentos/${VALID_CNPJ}`)
    wrapper = mount(CnpjDetailView, { global: { plugins: [pinia, router] } })
    await flushPromises()

    expect(store.cnpjAccessStatus).toBe('error')
    expect(wrapper.get('.cnpj-access-state').classes()).toContain('cnpj-access-state--error')
    expect(wrapper.get('.cnpj-access-state h2').text()).toBe('Validacao indisponivel')
  })

  it('mantém a sobreposição global até o bootstrap público confirmar acesso', async () => {
    await useValidCnpj()
    const pendingBootstrap = deferred()
    store.fetchBootstrap = vi.fn(async (requestedCnpj) => {
      store.cnpjAccessStatus = 'checking'
      store.cnpjAccessCnpj = requestedCnpj
      store.bootstrapLoading = true
      store.bootstrapData = null
      await pendingBootstrap.promise
      store.cnpjAccessStatus = 'valid'
      store.cnpjAccessCnpj = requestedCnpj
      store.bootstrapData = { qtd_municipios_regiao: 3 }
      store.bootstrapGeoData = { id_regiao_saude: 1100001, id_ibge7: 1100015 }
      store.bootstrapPeriodSummary = { totalMov: 500, valSemComp: 25, percValSemComp: 5 }
      store.cnpjsAvulsos.set(requestedCnpj, { cnpj: requestedCnpj, razao_social: 'Farmácia Teste' })
      store.bootstrapLoading = false
      return { status: { status: 'valid' } }
    })

    wrapper = mountValid()
    await nextTick()
    expect(wrapper.find('.global-loading-overlay').exists()).toBe(true)
    expect(wrapper.find('.detail-tabs').exists()).toBe(false)

    pendingBootstrap.resolve()
    await flushPromises()
    expect(wrapper.find('.global-loading-overlay').exists()).toBe(false)
    expect(wrapper.find('.detail-tabs').exists()).toBe(true)
  })

  it('mostra os dados do bootstrap e visita abas sob demanda, sincronizando a rota', async () => {
    const { nav } = await useValidCnpj()
    wrapper = mountValid()
    await flushPromises()

    expect(store.cnpjAccessStatus).toBe('valid')
    expect(wrapper.get('[data-test="cnpj-header"]').attributes('data-cnpj')).toBe(VALID_CNPJ)
    expect(wrapper.get('[data-test="cnpj-header"]').attributes('data-geo')).toBe('1100001')
    expect(wrapper.get('[data-test="cnpj-header"]').attributes('data-municipios')).toBe('3')
    expect(wrapper.get('[data-test="cnpj-header"]').attributes('data-summary')).toBe(JSON.stringify({
      totalMov: 500, valSemComp: 25, percValSemComp: 5,
    }))
    expect(wrapper.get('[data-test="evidence-panel"]').exists()).toBe(true)
    expect(wrapper.get('[data-test="financial-tab"]').exists()).toBe(true)
    expect(store.ensureTabData).toHaveBeenCalledWith('movimentacao', VALID_CNPJ, '2015-07-01', '2024-12-31', null)

    await wrapper.get('[data-test="tab-2"]').trigger('click')
    await flushPromises()
    expect(nav.activeTabIndex).toBe(2)
    expect(router.currentRoute.value.query.s).toBe('memoria')
    expect(wrapper.get('[data-test="memory-tab"]').exists()).toBe(true)

    store.indicadoresLoading = true
    await wrapper.get('[data-test="tab-3"]').trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.query.s).toBe('indicadores')
    expect(wrapper.get('[data-test="tab-loading"]').exists()).toBe(true)
  })

  it('visita diagnóstico, sócios e teia e exibe os respectivos estados de carregamento', async () => {
    const { nav } = await useValidCnpj()
    wrapper = mountValid()
    await flushPromises()

    store.metricPercentilesLoading = true
    await wrapper.get('[data-test="tab-1"]').trigger('click')
    await flushPromises()
    expect(nav.activeTabIndex).toBe(1)
    expect(wrapper.get('[data-test="diagnosis-tab"]').exists()).toBe(true)
    expect(wrapper.get('[data-test="tab-loading"]').exists()).toBe(true)

    store.metricPercentilesLoading = false
    store.sociosLoading = true
    await wrapper.get('[data-test="tab-5"]').trigger('click')
    await flushPromises()
    expect(wrapper.get('[data-test="socios-tab"]').exists()).toBe(true)
    expect(wrapper.get('[data-test="tab-loading"]').exists()).toBe(true)

    store.sociosLoading = false
    store.networkLoading = true
    await wrapper.get('[data-test="tab-6"]').trigger('click')
    await flushPromises()
    expect(wrapper.get('[data-test="network-tab"]').exists()).toBe(true)
    expect(wrapper.get('[data-test="tab-loading"]').exists()).toBe(true)

    store.networkLoading = false
    store.networkLevelLoading[3] = true
    await nextTick()
    expect(wrapper.get('[data-test="tab-loading"]').exists()).toBe(true)
    store.networkLevelLoading[3] = false
    await nextTick()
    expect(wrapper.find('[data-test="tab-loading"]').exists()).toBe(false)
  })

  it('absorve falha ao carregar dados da aba ativa e registra a conclusão como rejeitada', async () => {
    const { filters } = await useValidCnpj()
    wrapper = mountValid()
    await flushPromises()
    mocks.logCnpjPerf.mockClear()

    store.ensureTabData.mockRejectedValueOnce(new Error('Falha ao carregar diagnóstico'))
    await wrapper.get('[data-test="tab-1"]').trigger('click')
    await flushPromises()
    expect(mocks.logCnpjPerf).toHaveBeenCalledWith(
      expect.anything(), 'tab_fetch_settled', expect.objectContaining({ tab: 'diagnostico', status: 'rejected' }),
    )

    store.fetchBootstrap.mockRejectedValueOnce(new Error('Falha ao atualizar período'))
    filters.periodo = [new Date('2022-01-01T12:00:00'), new Date('2022-12-31T12:00:00')]
    await nextTick()
    await flushPromises()
    expect(mocks.logCnpjPerf).toHaveBeenCalledWith(
      expect.anything(), 'period_bootstrap_settled', expect.objectContaining({ status: 'rejected' }),
    )
  })

  it('reseta os dados ao trocar de CNPJ e usa as localidades como fonte geográfica', async () => {
    const { geo } = await useValidCnpj()
    geo.localidades = [{
      id_ibge7: 1100015,
      id_regiao_saude: 1100001,
      no_municipio: 'Alta Floresta D’Oeste',
      no_regiao_saude: 'Região Central',
    }]
    wrapper = mountValid()
    await flushPromises()
    store.bootstrapGeoData = null
    store.bootstrapData = null
    await nextTick()
    expect(wrapper.get('[data-test="cnpj-header"]').attributes('data-geo')).toBe('1100001')
    expect(wrapper.get('[data-test="cnpj-header"]').attributes('data-municipios')).toBe('1')

    const resetSpy = vi.spyOn(store, 'resetAll')
    await router.push(`/estabelecimentos/12345678000196`)
    await flushPromises()
    expect(resetSpy).toHaveBeenCalledOnce()
    expect(store.fetchBootstrap).toHaveBeenCalledWith('12345678000196', expect.any(String), expect.any(String))
    expect(store.cnpjsAvulsos.has('12345678000196')).toBe(true)
  })

  it('registra o estabelecimento recente quando o cadastro fica disponível', async () => {
    await useValidCnpj()
    const recent = useRecentCnpjStore(pinia)
    const setSpy = vi.spyOn(recent, 'set')
    wrapper = mountValid()
    await flushPromises()

    expect(setSpy).toHaveBeenCalledWith(VALID_CNPJ, 'Farmácia Teste')
  })

  it('refaz o bootstrap ao mudar o período e aguarda a animação para atualizar filtros', async () => {
    const { filters } = await useValidCnpj()
    wrapper = mountValid()
    await flushPromises()
    store.fetchBootstrap.mockClear()

    filters.isAnimating = true
    filters.periodo = [new Date('2024-01-01T12:00:00'), new Date('2024-12-31T12:00:00')]
    await nextTick()
    await flushPromises()
    expect(store.fetchBootstrap).not.toHaveBeenCalled()

    filters.isAnimating = false
    filters.periodo = [new Date('2023-01-01T12:00:00'), new Date('2023-12-31T12:00:00')]
    await nextTick()
    await flushPromises()
    expect(store.fetchBootstrap).toHaveBeenCalledWith(VALID_CNPJ, expect.any(String), expect.any(String))
  })

  it('interpreta seção falecidos e parâmetro legado de aba', async () => {
    const { nav } = await useValidCnpj({ query: { s: ['falecidos', 'teia'] } })
    const setCrmViewMode = vi.spyOn(store, 'setCrmViewMode')
    wrapper = mountValid()
    await flushPromises()

    expect(nav.activeTabIndex).toBe(4)
    expect(setCrmViewMode).toHaveBeenCalledWith('falecidos')
    expect(wrapper.get('[data-test="auth-tab"]').exists()).toBe(true)

    await router.push({ path: `/estabelecimentos/${VALID_CNPJ}`, query: { tab: 'regional' } })
    await flushPromises()
    expect(nav.activeTabIndex).toBe(7)
    expect(wrapper.get('[data-test="regional-tab"]').exists()).toBe(true)
  })

  it('normaliza parâmetro legado em lista e evita sincronização redundante da aba', async () => {
    const { nav } = await useValidCnpj({ query: { tab: ['socios', 'regional'] } })
    wrapper = mountValid()
    await flushPromises()

    expect(nav.activeTabIndex).toBe(5)
    const replace = vi.spyOn(router, 'replace')
    const api = wrapper.vm.$.setupState

    api.setActiveTab(5)
    await flushPromises()
    expect(router.currentRoute.value.query).toEqual({ s: 'socios' })
    const replacements = replace.mock.calls.length

    api.setActiveTab(5)
    api.setActiveTab(99)
    await flushPromises()
    expect(replace).toHaveBeenCalledTimes(replacements)
    expect(nav.activeTabIndex).toBe(99)

    api.setActiveTab(7, { syncUrl: false })
    await flushPromises()
    expect(router.currentRoute.value.query).toEqual({ s: 'socios' })
  })

  it('trata estados opcionais da aba de rede, geografia ausente e formatação do CNPJ', async () => {
    const { geo, nav } = await useValidCnpj({ query: { s: 'teia' } })
    wrapper = mountValid()
    await flushPromises()

    store.networkLevelLoading = null
    store.bootstrapData = {}
    store.bootstrapGeoData = null
    store.cnpjsAvulsos.set(VALID_CNPJ, { cnpj: VALID_CNPJ, razao_social: '' })
    geo.localidades = [{ id_ibge7: 1100015, id_regiao_saude: 1100001, no_municipio: 'Cidade' }]
    await nextTick()

    const api = wrapper.vm.$.setupState
    expect(nav.activeTabIndex).toBe(6)
    expect(wrapper.get('[data-test="network-tab"]').exists()).toBe(true)
    expect(wrapper.get('[data-test="cnpj-header"]').attributes('data-geo')).toBeUndefined()
    expect(wrapper.get('[data-test="cnpj-header"]').attributes('data-municipios')).toBeUndefined()
    expect(wrapper.get('[data-test="evidence-panel"]').attributes('data-name')).toBe('')
    expect(api.formatCnpj('')).toBe('—')
    expect(api.formatCnpj('123')).toBe('123')
    expect(api.formatCnpj(VALID_CNPJ)).toBe('12.345.678/0001-95')

    store.cnpjsAvulsos.set(VALID_CNPJ, { cnpj: VALID_CNPJ, razao_social: '', id_ibge7: 9999999 })
    await nextTick()
    expect(wrapper.get('[data-test="cnpj-header"]').attributes('data-geo')).toBeUndefined()

    store.cnpjsAvulsos.delete(VALID_CNPJ)
    geo.localidades = []
    await nextTick()
    expect(wrapper.get('[data-test="cnpj-header"]').attributes('data-geo')).toBeUndefined()

    store.cnpjsAvulsos.set(VALID_CNPJ, { cnpj: VALID_CNPJ, razao_social: '' })
    await wrapper.get('[data-test="tab-4"]').trigger('click')
    await flushPromises()
    expect(wrapper.get('[data-test="auth-tab"]').attributes('data-name')).toBe('')
  })

  it('ignora mudanças de período enquanto o acesso ao CNPJ ainda não é válido', async () => {
    wrapper = mount(CnpjDetailView, { global: { plugins: [pinia, router] } })
    await flushPromises()
    const filters = useFilterStore(pinia)
    const api = wrapper.vm.$.setupState
    const fetchBootstrap = vi.spyOn(store, 'fetchBootstrap')
    const ensureTabData = vi.spyOn(store, 'ensureTabData')
    fetchBootstrap.mockClear()
    ensureTabData.mockClear()

    await api.loadActiveTabData(null)
    expect(ensureTabData).not.toHaveBeenCalled()

    filters.periodo = [new Date('2024-01-01T12:00:00'), new Date('2024-12-31T12:00:00')]
    await nextTick()
    await flushPromises()

    expect(fetchBootstrap).not.toHaveBeenCalled()

    store.cnpjAccessStatus = 'idle'
    store.bootstrapLoading = true
    store.bootstrapData = null
    await nextTick()
    expect(wrapper.get('.global-loading-overlay').exists()).toBe(true)
  })

  it('descarta bootstrap atrasado depois que a rota troca para outro CNPJ', async () => {
    await useValidCnpj()
    const firstBootstrap = deferred()
    store.fetchBootstrap = vi.fn(async (requestedCnpj) => {
      if (requestedCnpj === VALID_CNPJ) {
        await firstBootstrap.promise
        return { status: { status: 'valid' } }
      }
      store.cnpjAccessStatus = 'valid'
      store.cnpjAccessCnpj = requestedCnpj
      store.bootstrapLoading = false
      store.bootstrapData = { qtd_municipios_regiao: 2 }
      store.bootstrapGeoData = { id_regiao_saude: 1100002, id_ibge7: 1100023 }
      store.bootstrapPeriodSummary = null
      store.cnpjsAvulsos.set(requestedCnpj, { cnpj: requestedCnpj, razao_social: 'Outra Farmácia' })
      return { status: { status: 'valid' } }
    })
    store.fetchIntegrityAlerts.mockClear()
    wrapper = mountValid()
    await nextTick()
    await router.push('/estabelecimentos/12345678000196')
    await flushPromises()
    expect(store.fetchIntegrityAlerts).toHaveBeenCalledOnce()

    firstBootstrap.resolve()
    await flushPromises()

    expect(store.fetchIntegrityAlerts).toHaveBeenCalledOnce()
    expect(store.cnpjAccessCnpj).toBe('12345678000196')
  })

  it('não registra resultado de período que chega depois de uma nova sessão de CNPJ', async () => {
    const { filters } = await useValidCnpj()
    wrapper = mountValid()
    await flushPromises()
    mocks.logCnpjPerf.mockClear()

    const periodSuccess = deferred()
    store.fetchBootstrap.mockImplementationOnce(() => periodSuccess.promise)
    filters.periodo = [new Date('2024-01-01T12:00:00'), new Date('2024-12-31T12:00:00')]
    await nextTick()
    await router.push('/estabelecimentos/12345678000196')
    await flushPromises()
    periodSuccess.resolve({ status: { status: 'valid' } })
    await flushPromises()

    const settledEvents = () => mocks.logCnpjPerf.mock.calls.filter(([, event]) => event === 'period_bootstrap_settled')
    expect(settledEvents()).toHaveLength(0)

    const periodFailure = deferred()
    store.fetchBootstrap.mockImplementationOnce(() => periodFailure.promise)
    filters.periodo = [new Date('2023-01-01T12:00:00'), new Date('2023-12-31T12:00:00')]
    await nextTick()
    await router.push(`/estabelecimentos/${VALID_CNPJ}`)
    await flushPromises()
    periodFailure.reject(new Error('período antigo indisponível'))
    await flushPromises()

    expect(settledEvents()).toHaveLength(0)
  })

  it('encaminha os métodos da aba de falecidos e trata a referência ainda ausente', async () => {
    await useValidCnpj()
    wrapper = mountValid()
    await flushPromises()
    const api = wrapper.vm.$.setupState
    const deceasedBridge = api.falecidosTabRef

    expect(deceasedBridge.hasData()).toBe(false)
    expect(deceasedBridge.getSummary()).toBeNull()
    expect(deceasedBridge.getAgrupados()).toEqual([])
    expect(deceasedBridge.getRanking()).toEqual([])

    api.authTabRef = {
      hasFalecidosData: vi.fn(() => true),
      getFalecidosSummary: vi.fn(() => ({ total: 3 })),
      getFalecidosAgrupados: vi.fn(() => [{ cpf: '12345678901' }]),
      getFalecidosRanking: vi.fn(() => [{ cpf: '12345678901', total: 3 }]),
    }
    expect(deceasedBridge.hasData()).toBe(true)
    expect(deceasedBridge.getSummary()).toEqual({ total: 3 })
    expect(deceasedBridge.getAgrupados()).toEqual([{ cpf: '12345678901' }])
    expect(deceasedBridge.getRanking()).toEqual([{ cpf: '12345678901', total: 3 }])
  })

  it('usa os dados financeiros carregados quando o resumo do bootstrap não existe', async () => {
    await useValidCnpj()
    wrapper = mountValid()
    await flushPromises()
    store.bootstrapPeriodSummary = null
    store.evolucaoFinanceira = { semestres: [] }
    store.evolucaoLoaded = false
    await nextTick()
    expect(wrapper.get('[data-test="cnpj-header"]').attributes('data-summary')).toBe('null')

    store.evolucaoLoaded = true
    await nextTick()
    expect(wrapper.get('[data-test="cnpj-header"]').attributes('data-summary')).toBe(JSON.stringify({
      totalMov: 0, valSemComp: 0, percValSemComp: 0,
    }))

    store.evolucaoFinanceira = { semestres: [{ total: 100, irregular: 25 }, { total: 0, irregular: 5 }] }
    await nextTick()
    expect(wrapper.get('[data-test="cnpj-header"]').attributes('data-summary')).toBe(JSON.stringify({
      totalMov: 100, valSemComp: 30, percValSemComp: 30,
    }))

    store.evolucaoFinanceira = { semestres: [{ total: 0, irregular: 0 }] }
    await nextTick()
    expect(wrapper.get('[data-test="cnpj-header"]').attributes('data-summary')).toBe(JSON.stringify({
      totalMov: 0, valSemComp: 0, percValSemComp: 0,
    }))
  })

  it('navega por alertas de integridade e rejeita uma seção inexistente', async () => {
    const { nav } = await useValidCnpj()
    wrapper = mountValid()
    await flushPromises()

    await wrapper.get('[data-test="navigate-section"]').trigger('click')
    await flushPromises()
    expect(nav.activeTabIndex).toBe(7)
    expect(router.currentRoute.value.query.s).toBe('regional')
    expect(wrapper.get('[data-test="regional-tab"]').exists()).toBe(true)

    const errorSpy = vi.fn()
    wrapper.vm.$.appContext.config.errorHandler = errorSpy
    await wrapper.get('[data-test="navigate-invalid"]').trigger('click')
    expect(errorSpy).toHaveBeenCalledWith(expect.objectContaining({ message: expect.stringContaining('Aba de destino invalida') }), expect.anything(), expect.anything())
  })

  it('prepara e gera a Nota Técnica depois da escolha regional', async () => {
    const { config } = await useValidCnpj()
    const fetchMock = vi.fn().mockResolvedValue({ ok: true })
    vi.stubGlobal('fetch', fetchMock)
    mocks.downloadBlobFromResponse.mockResolvedValue({ desktop: true, filename: 'Nota_Tecnica.docx', path: 'C:/notas/Nota_Tecnica.docx' })
    mocks.convertDocxToPdf.mockResolvedValue({ path: 'C:/notas/Nota_Tecnica.pdf' })
    wrapper = mountValid()
    await flushPromises()

    store.fetchNotaTecnicaReadiness = vi.fn()
      .mockResolvedValueOnce({ ready: false, preparable: true, modules: [], missing_modules: [] })
      .mockResolvedValueOnce(READY_MODULES)
    store.prepareNotaTecnica = vi.fn().mockResolvedValue({})

    await wrapper.get('[data-test="generate-note"]').trigger('click')
    await flushPromises()
    expect(store.prepareNotaTecnica).toHaveBeenCalledWith(VALID_CNPJ, expect.anything(), expect.anything())
    expect(store.fetchNotaTecnicaReadiness).toHaveBeenLastCalledWith(VALID_CNPJ, expect.anything(), expect.anything(), { force: true })
    expect(config.ensureLoaded).toHaveBeenCalled()
    expect(wrapper.get('[data-test="regional-dialog"]').attributes('data-visible')).toBe('true')

    await wrapper.get('[data-test="save-regional-dialog"]').trigger('click')
    await flushPromises()
    expect(fetchMock).toHaveBeenCalledOnce()
    expect(String(fetchMock.mock.calls[0][0])).toContain('numero_nota=NT+001%2F2026')
    expect(String(fetchMock.mock.calls[0][0])).toContain('numero_processo=00000.000001%2F2026-00')
    expect(mocks.downloadBlobFromResponse).toHaveBeenCalledWith({ ok: true }, `Nota_Tecnica_${VALID_CNPJ}.docx`)
    expect(mocks.convertDocxToPdf).toHaveBeenCalledWith('C:/notas/Nota_Tecnica.docx')
    expect(mocks.toastAdd).toHaveBeenCalledWith(expect.objectContaining({
      summary: 'Nota Técnica salva',
      data: { path: 'C:/notas/Nota_Tecnica.docx', previewPath: 'C:/notas/Nota_Tecnica.pdf' },
    }))
  })

  it('informa erro ao carregar a configuração regional antes de abrir o diálogo', async () => {
    const { config } = await useValidCnpj()
    wrapper = mountValid()
    await flushPromises()
    mocks.toastAdd.mockClear()
    config.ensureLoaded.mockRejectedValueOnce(new Error('Regional indisponível'))

    await wrapper.get('[data-test="generate-note"]').trigger('click')
    await flushPromises()

    expect(wrapper.get('[data-test="regional-dialog"]').attributes('data-visible')).toBe('false')
    expect(mocks.toastAdd).toHaveBeenCalledWith(expect.objectContaining({
      summary: 'Erro ao gerar Nota Técnica', detail: 'Regional indisponível',
    }))
  })

  it('informa falha ao carregar a configuração regional ao montar o detalhe', async () => {
    const { config } = await useValidCnpj()
    config.ensureLoaded.mockRejectedValueOnce({})
    wrapper = mountValid()
    await flushPromises()

    expect(mocks.toastAdd).toHaveBeenCalledWith(expect.objectContaining({
      severity: 'warn',
      summary: 'Regional da Nota Técnica',
      detail: 'Não foi possível carregar a configuração da Nota Técnica.',
    }))
  })

  it('limpa a geração pendente ao fechar o diálogo regional', async () => {
    await useValidCnpj()
    const fetchMock = vi.fn().mockResolvedValue({ ok: true })
    vi.stubGlobal('fetch', fetchMock)
    wrapper = mountValid()
    await flushPromises()

    await wrapper.get('[data-test="generate-note"]').trigger('click')
    await flushPromises()
    expect(wrapper.get('[data-test="regional-dialog"]').attributes('data-visible')).toBe('true')
    await wrapper.get('[data-test="close-regional-dialog"]').trigger('click')
    expect(wrapper.get('[data-test="regional-dialog"]').attributes('data-visible')).toBe('false')

    await wrapper.get('[data-test="save-regional-dialog"]').trigger('click')
    await flushPromises()
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('apresenta os módulos pendentes e erros ao preparar a Nota Técnica', async () => {
    await useValidCnpj()
    wrapper = mountValid()
    await flushPromises()
    store.fetchNotaTecnicaReadiness = vi.fn().mockResolvedValue({
      ready: false, preparable: false, modules: [], missing_modules: [{ label: 'Cadastro' }, { label: '' }],
    })
    await wrapper.get('[data-test="generate-note"]').trigger('click')
    await flushPromises()
    expect(mocks.toastAdd).toHaveBeenCalledWith(expect.objectContaining({
      summary: 'Nota Técnica indisponível', detail: 'Módulos pendentes: Cadastro.',
    }))
    expect(wrapper.get('[data-test="regional-dialog"]').attributes('data-visible')).toBe('false')

    store.fetchNotaTecnicaReadiness.mockResolvedValueOnce({ ready: false, preparable: true, modules: [], missing_modules: [] })
    store.prepareNotaTecnica = vi.fn().mockRejectedValue(new Error('Falha de preparação'))
    await wrapper.get('[data-test="generate-note"]').trigger('click')
    await flushPromises()
    expect(mocks.toastAdd).toHaveBeenCalledWith(expect.objectContaining({
      summary: 'Preparação da Nota Técnica indisponível', detail: 'Falha de preparação',
    }))

    store.fetchNotaTecnicaReadiness.mockResolvedValueOnce({ ready: false, preparable: true, modules: [], missing_modules: [] })
    store.prepareNotaTecnica.mockRejectedValueOnce({})
    store.notaTecnicaPrepareError = null
    await wrapper.get('[data-test="generate-note"]').trigger('click')
    await flushPromises()
    expect(mocks.toastAdd).toHaveBeenCalledWith(expect.objectContaining({
      summary: 'Preparação da Nota Técnica indisponível',
      detail: 'Não foi possível preparar os dados da Nota Técnica.',
    }))

    store.fetchNotaTecnicaReadiness.mockResolvedValueOnce({ ready: false, preparable: false, missing_modules: null })
    store.notaTecnicaReadinessError = null
    await wrapper.get('[data-test="generate-note"]').trigger('click')
    await flushPromises()
    expect(mocks.toastAdd).toHaveBeenCalledWith(expect.objectContaining({
      summary: 'Nota Técnica indisponível',
      detail: 'Não foi possível verificar os módulos da Nota Técnica.',
    }))
  })

  it('gera o Relatório PDF e informa falhas de prontidão e exportação', async () => {
    await useValidCnpj()
    const fetchMock = vi.fn().mockResolvedValue({ ok: true })
    vi.stubGlobal('fetch', fetchMock)
    mocks.exportCnpjPdf.mockResolvedValue({ desktop: true, filename: 'relatorio.pdf', path: 'C:/relatorios/relatorio.pdf' })
    wrapper = mountValid()
    await flushPromises()
    await wrapper.get('[data-test="export-pdf"]').trigger('click')
    await flushPromises()

    expect(mocks.loadCnpjPdfReportData).toHaveBeenCalledWith(expect.objectContaining({ cnpj: VALID_CNPJ }))
    expect(mocks.exportCnpjPdf).toHaveBeenCalledWith(expect.objectContaining({ title: 'Relatório pronto' }))
    expect(mocks.toastAdd).toHaveBeenCalledWith(expect.objectContaining({
      summary: 'Relatório PDF salvo',
      data: { path: 'C:/relatorios/relatorio.pdf', previewPath: 'C:/relatorios/relatorio.pdf' },
    }))

    store.fetchRelatorioPdfReadiness = vi.fn().mockResolvedValue({
      ready: false, preparable: false, modules: [], missing_modules: [{ label: 'Memória' }],
    })
    await wrapper.get('[data-test="export-pdf"]').trigger('click')
    await flushPromises()
    expect(mocks.toastAdd).toHaveBeenCalledWith(expect.objectContaining({
      summary: 'Relatório PDF indisponível', detail: 'Módulos pendentes: Memória.',
    }))
  })

  it('prepara o Relatório PDF quando a prontidão permite e trata falha ao montar os dados', async () => {
    await useValidCnpj()
    mocks.exportCnpjPdf.mockResolvedValue({ desktop: false })
    wrapper = mountValid()
    await flushPromises()
    store.fetchRelatorioPdfReadiness = vi.fn()
      .mockResolvedValueOnce({ ready: false, preparable: true, modules: [], missing_modules: [] })
      .mockResolvedValueOnce(READY_MODULES)
    store.prepareRelatorioPdf = vi.fn().mockResolvedValue({})

    await wrapper.get('[data-test="export-pdf"]').trigger('click')
    await flushPromises()

    expect(store.prepareRelatorioPdf).toHaveBeenCalledWith(VALID_CNPJ, expect.any(String), expect.any(String))
    expect(store.fetchRelatorioPdfReadiness).toHaveBeenLastCalledWith(
      VALID_CNPJ, expect.any(String), expect.any(String), { force: true },
    )
    expect(mocks.toastAdd).toHaveBeenCalledWith(expect.objectContaining({ summary: 'Preparando Relatório PDF' }))

    store.fetchRelatorioPdfReadiness.mockResolvedValue(READY_MODULES)
    mocks.loadCnpjPdfReportData.mockRejectedValueOnce(new Error('Dados do PDF indisponíveis'))
    await wrapper.get('[data-test="export-pdf"]').trigger('click')
    await flushPromises()
    expect(mocks.toastAdd).toHaveBeenCalledWith(expect.objectContaining({
      severity: 'error', summary: 'Erro ao gerar Relatório PDF', detail: 'Dados do PDF indisponíveis',
    }))
  })

  it('usa erros registrados ao preparar ou verificar prontidão do Relatório PDF', async () => {
    await useValidCnpj()
    wrapper = mountValid()
    await flushPromises()
    store.fetchRelatorioPdfReadiness = vi.fn()
      .mockResolvedValueOnce({ ready: false, preparable: true, modules: [], missing_modules: [] })
      .mockResolvedValueOnce({ ready: false, preparable: false, modules: [], missing_modules: [] })
    store.prepareRelatorioPdf = vi.fn().mockRejectedValue({})
    store.relatorioPdfPrepareError = 'Falha de preparação registrada'

    await wrapper.get('[data-test="export-pdf"]').trigger('click')
    await flushPromises()
    expect(mocks.toastAdd).toHaveBeenCalledWith(expect.objectContaining({
      summary: 'Preparação do Relatório PDF indisponível', detail: 'Falha de preparação registrada',
    }))

    store.fetchRelatorioPdfReadiness = vi.fn().mockResolvedValueOnce({ ready: false, preparable: true, modules: [], missing_modules: [] })
    store.prepareRelatorioPdf = vi.fn().mockRejectedValueOnce({})
    store.relatorioPdfPrepareError = null
    await wrapper.get('[data-test="export-pdf"]').trigger('click')
    await flushPromises()
    expect(mocks.toastAdd).toHaveBeenCalledWith(expect.objectContaining({
      summary: 'Preparação do Relatório PDF indisponível',
      detail: 'Não foi possível preparar os dados do Relatório PDF.',
    }))

    store.fetchRelatorioPdfReadiness = vi.fn().mockResolvedValue({
      ready: false, preparable: false, modules: [], missing_modules: null,
    })
    store.relatorioPdfReadinessError = null
    await wrapper.get('[data-test="export-pdf"]').trigger('click')
    await flushPromises()
    expect(mocks.toastAdd).toHaveBeenCalledWith(expect.objectContaining({
      summary: 'Relatório PDF indisponível', detail: 'Não foi possível verificar os módulos do Relatório PDF.',
    }))
  })

  it('trata erro HTTP e falha de conversão ao salvar os documentos', async () => {
    await useValidCnpj()
    const fetchMock = vi.fn().mockResolvedValue({ ok: false, status: 503 })
    vi.stubGlobal('fetch', fetchMock)
    mocks.getApiErrorMessage.mockResolvedValue('Falha HTTP controlada')
    wrapper = mountValid()
    await flushPromises()
    await wrapper.get('[data-test="generate-note"]').trigger('click')
    await flushPromises()
    await wrapper.get('[data-test="save-regional-dialog"]').trigger('click')
    await flushPromises()
    expect(mocks.toastAdd).toHaveBeenCalledWith(expect.objectContaining({
      summary: 'Erro ao gerar Nota Técnica', detail: 'Falha HTTP controlada',
    }))

    fetchMock.mockResolvedValue({ ok: true })
    mocks.downloadBlobFromResponse.mockResolvedValue({ desktop: true, filename: 'Nota_Tecnica.docx', path: 'C:/notas/Nota_Tecnica.docx' })
    mocks.convertDocxToPdf.mockRejectedValue(new Error('Conversão indisponível'))
    await wrapper.get('[data-test="generate-note"]').trigger('click')
    await flushPromises()
    await wrapper.get('[data-test="save-regional-dialog"]').trigger('click')
    await flushPromises()
    expect(mocks.toastAdd).toHaveBeenCalledWith(expect.objectContaining({
      severity: 'warn', summary: 'Pre-visualizacao indisponivel', detail: 'Conversão indisponível',
    }))
    expect(mocks.toastAdd).toHaveBeenCalledWith(expect.objectContaining({
      summary: 'Nota Técnica salva', data: { path: 'C:/notas/Nota_Tecnica.docx', previewPath: null },
    }))

    mocks.convertDocxToPdf.mockRejectedValueOnce({})
    await wrapper.get('[data-test="generate-note"]').trigger('click')
    await flushPromises()
    await wrapper.get('[data-test="save-regional-dialog"]').trigger('click')
    await flushPromises()
    expect(mocks.toastAdd).toHaveBeenCalledWith(expect.objectContaining({
      severity: 'warn',
      summary: 'Pre-visualizacao indisponivel',
      detail: 'A Nota Tecnica foi salva, mas nao foi possivel gerar a versao PDF para visualizacao.',
    }))

    fetchMock.mockRejectedValueOnce({})
    await wrapper.get('[data-test="generate-note"]').trigger('click')
    await flushPromises()
    await wrapper.get('[data-test="save-regional-dialog"]').trigger('click')
    await flushPromises()
    expect(mocks.toastAdd).toHaveBeenCalledWith(expect.objectContaining({
      severity: 'error', summary: 'Erro ao gerar Nota Técnica', detail: 'Não foi possível gerar o arquivo.',
    }))

    mocks.loadCnpjPdfReportData.mockRejectedValueOnce({})
    await wrapper.get('[data-test="export-pdf"]').trigger('click')
    await flushPromises()
    expect(mocks.toastAdd).toHaveBeenCalledWith(expect.objectContaining({
      severity: 'error', summary: 'Erro ao gerar Relatório PDF', detail: 'Não foi possível gerar o arquivo.',
    }))
  })
})
