import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, disposePinia, setActivePinia } from 'pinia'
import { reactive } from 'vue'
import { createMemoryHistory, createRouter } from 'vue-router'
import axios from 'axios'

import HomeView from '@/views/HomeView.vue'
import { API_ENDPOINTS } from '@/config/api'
import { useAnalyticsStore } from '@/stores/analytics'
import { useFilterStore } from '@/stores/filters'
import { useGeoStore } from '@/stores/geo'

const mocks = vi.hoisted(() => ({ methodologyStore: null, updateStore: null, panoramaAlertTooltip: vi.fn((alerta, options) => ({ value: `${alerta.tipo}:${options.aumentoMinimo}` })) }))

vi.mock('axios', () => ({ default: { get: vi.fn(), put: vi.fn() } }))
vi.mock('@/composables/useFetchAnalytics', () => ({ useFetchAnalytics: vi.fn() }))
vi.mock('@/stores/metodologiaConfig', () => ({ useMetodologiaConfigStore: () => mocks.methodologyStore }))
vi.mock('@/stores/systemUpdate', () => ({ useSystemUpdateStore: () => mocks.updateStore }))
vi.mock('@/config/integrityAlertTooltipConfig', () => ({ panoramaAlertTooltip: mocks.panoramaAlertTooltip }))
vi.mock('@/views/components/charts/RiskChart.vue', () => ({ default: { template: '<div data-test="risk-chart" />' } }))
vi.mock('@/views/components/maps/BrazilMap.vue', () => ({ default: { template: '<div data-test="brazil-map" />' } }))
vi.mock('@/views/components/charts/TopUfRiskChart.vue', () => ({ default: { template: '<div data-test="uf-chart" />' } }))
vi.mock('@/views/components/charts/SemesterProductionChart.vue', () => ({ default: { template: '<div data-test="production-chart" />' } }))

describe('HomeView — painel nacional', () => {
  let pinia
  let analytics
  let filters
  let wrapper

  beforeEach(async () => {
    vi.useFakeTimers()
    vi.clearAllMocks()
    localStorage.clear()
    axios.get.mockImplementation((url) => {
      if (url === API_ENDPOINTS.preferences) {
        return Promise.resolve({ data: { filters: {}, ui: { sidebarCollapsed: false, sidebarLocked: false } } })
      }
      if (url === API_ENDPOINTS.cacheStatus) {
        return Promise.resolve({ data: { is_ready: true, modules: {} } })
      }
      return Promise.resolve({ data: {} })
    })
    axios.put.mockResolvedValue({ data: {} })
    mocks.methodologyStore = reactive({
      loaded: true,
      volumeAtipicoAumentoMinimo: 500,
      ensureLoaded: vi.fn().mockResolvedValue(),
    })
    mocks.updateStore = reactive({
      status: null,
      statusTone: 'current',
      statusLabel: 'Atualizado',
      isCurrent: true,
      loading: false,
      hasUpdate: false,
      isBlocked: false,
      downloadUrl: null,
      releaseNotesUrl: null,
      latestVersion: null,
      currentVersion: '2.0.3',
      checkedAtFormatted: null,
      message: null,
      fetchUpdateStatus: vi.fn().mockResolvedValue(),
      forceCheckUpdate: vi.fn().mockResolvedValue(),
      startDownload: vi.fn(),
    })

    pinia = createPinia()
    setActivePinia(pinia)
    analytics = useAnalyticsStore()
    filters = useFilterStore()
    analytics.kpis = [
      { label: 'CNPJs', value: '12' },
      { label: 'Municípios', value: '3' },
      { label: 'Valor das vendas', value: 'R$ 1.000' },
      { label: 'Sem comprovação', value: 'R$ 200' },
      { label: '% sem comprovação', value: '20%' },
    ]
    analytics.resultadoSentinelaUF = [{ uf: 'RO' }]
    analytics.cacheStatus = { is_ready: true, modules: {} }
    analytics.alertasPanorama = {
      total_cnpjs_com_alerta: 4,
      alertas: [{ tipo: 'volume_atipico', titulo: 'Volume atípico', severidade: 'critico', qtd_cnpjs: 3 }],
    }
    analytics.alertasPanoramaLoading = false
    await Promise.resolve()
  })

  afterEach(() => {
    wrapper?.unmount()
    disposePinia(pinia)
    vi.clearAllTimers()
    vi.useRealTimers()
    vi.restoreAllMocks()
    localStorage.clear()
  })

  function mountHome() {
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [{ path: '/', component: { template: '<div />' } }],
    })
    return mount(HomeView, {
      global: {
        plugins: [pinia, router],
        directives: { tooltip() {} },
      },
    })
  }

  it('exibe o resumo nacional, os alertas e as visualizações principais', async () => {
    wrapper = mountHome()
    await flushPromises()

    expect(wrapper.text()).toContain('Status operacional')
    expect(wrapper.text()).toContain('Quadro de Alertas')
    expect(wrapper.text()).toContain('4')
    expect(wrapper.text()).toContain('Movimentação financeira')
    expect(wrapper.find('[data-test="production-chart"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="uf-chart"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="risk-chart"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="brazil-map"]').exists()).toBe(true)
  })

  it('mostra a mensagem inicial e formata a data da última sincronização', async () => {
    analytics.lastSync = null
    wrapper = mountHome()
    await flushPromises()
    const api = wrapper.vm.$.setupState

    expect(api.syncText).toBe('Aguardando primeira atualização')
    analytics.lastSync = '2025-06-01T12:34:00'
    await flushPromises()
    expect(api.syncText).toBe(new Intl.DateTimeFormat('pt-BR', {
      day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit',
    }).format(new Date(analytics.lastSync)))
  })

  it('aplica o filtro correspondente ao clicar em um alerta do panorama', async () => {
    // O serviço de atualização preenche esta versão quando sua consulta termina.
    mocks.updateStore.currentVersion = '2.0.3'
    wrapper = mountHome()
    await flushPromises()
    const alerta = wrapper.get('[aria-label^="Volume atípico:"]')

    expect(alerta.attributes('aria-pressed')).toBe('false')
    await alerta.trigger('click')

    expect(filters.volumeAtipicoEnabled).toBe(true)
    expect(wrapper.get('[aria-label^="Volume atípico:"]').attributes('aria-pressed')).toBe('true')
  })

  it('mostra estados de cache e falha de análise com o resumo dos módulos', async () => {
    mocks.methodologyStore.loaded = false
    wrapper = mountHome()
    await flushPromises()

    analytics.error = 'Falha ao consultar métricas'
    analytics.cacheStatus = null
    analytics.alertasPanorama = null
    analytics.alertasPanoramaLoading = true
    await wrapper.vm.$nextTick()
    expect(wrapper.get('.system-stat__value--warning').text()).toBe('Atenção')
    expect(wrapper.text()).toContain('verificando módulos')
    expect(wrapper.findAll('.alert-cell--skeleton')).toHaveLength(6)

    analytics.error = null
    analytics.cacheStatus = {
      is_ready: false,
      modules: {
        movimento: { label: 'Movimentação', loaded: true, exists: true },
        farmacia: { label: 'Farmácias', loaded: false, exists: true },
        socios: { label: 'Sócios', loaded: false, exists: false },
      },
    }
    analytics.alertasPanoramaLoading = false
    await wrapper.vm.$nextTick()

    expect(wrapper.text()).toContain('1/3 módulos carregados')
    expect(wrapper.find('.operational-module--ok').text()).toContain('Carregado')
    expect(wrapper.find('.operational-module--error').text()).toContain('Erro')
    expect(wrapper.find('.operational-module--missing').text()).toContain('Ausente')

    analytics.cacheStatus = {
      is_ready: true,
      modules: { pendente: { label: 'Pendente', loaded: false, exists: true } },
    }
    await wrapper.vm.$nextTick()
    expect(wrapper.text()).toContain('0/1 módulos carregados')
    expect(mocks.panoramaAlertTooltip).toHaveBeenCalledWith(
      expect.objectContaining({ tipo: 'volume_atipico' }),
      { aumentoMinimo: 'valor configurado' },
    )
  })

  it('mostra o estado de verificação sem cache e registra erro de metodologia', async () => {
    const warning = vi.spyOn(console, 'warn').mockImplementation(() => {})
    mocks.methodologyStore.ensureLoaded.mockRejectedValueOnce(new Error('Metodologia indisponível'))
    wrapper = mountHome()
    await flushPromises()

    expect(warning).toHaveBeenCalledWith(
      '[HomeView] Não foi possível carregar a configuração metodológica.',
      expect.objectContaining({ message: 'Metodologia indisponível' }),
    )
    analytics.cacheStatus = null
    analytics.error = null
    await wrapper.vm.$nextTick()
    expect(wrapper.get('.system-stat__value--loading').text()).toBe('Verificando')
    expect(wrapper.find('.priority-card--loading').exists()).toBe(true)
  })

  it('resolve o escopo financeiro conforme município, região, UF e Brasil', async () => {
    const geo = useGeoStore()
    geo.localidades = [{
      id_ibge7: 1100015,
      id_regiao_saude: 1100001,
      sg_uf: 'RO',
      no_municipio: 'Alta Floresta D’Oeste',
      no_regiao_saude: 'Região Central',
    }]
    filters.periodo = [null, null]
    analytics.resultadoSentinelaUF = [{ uf: 'RO' }, {}, { uf: 'AC' }]
    wrapper = mountHome()
    await flushPromises()

    const scope = () => wrapper.find('.financeiro-stat--wide').text()
    filters.selectedMunicipio = '1100015'
    await wrapper.vm.$nextTick()
    expect(scope()).toContain('Município')
    expect(scope()).toContain('Alta Floresta D’Oeste')

    filters.selectedMunicipio = 'Todos'
    filters.selectedRegiaoSaude = '1100001'
    await wrapper.vm.$nextTick()
    expect(scope()).toContain('Região')
    expect(scope()).toContain('Região Central')

    filters.selectedRegiaoSaude = 'Todos'
    filters.selectedUF = 'RO'
    await wrapper.vm.$nextTick()
    expect(scope()).toContain('UFRO')

    filters.selectedUF = 'Todos'
    await wrapper.vm.$nextTick()
    expect(scope()).toContain('EscopoBrasil')
    expect(wrapper.text()).toContain('Período não definido')
    expect(wrapper.find('.escopo-stat:nth-child(2)').text()).toContain('2')
  })

  it('alterna alertas booleanos e de seleção e respeita alertas sem filtro', async () => {
    analytics.alertasPanorama = {
      total_cnpjs_com_alerta: 7,
      alertas: [
        { tipo: 'socio_beneficio_social', titulo: 'Benefício social', severidade: 'atencao', qtd_cnpjs: 2 },
        { tipo: 'socio_esocial', titulo: 'Vínculo eSocial', severidade: 'critico', qtd_cnpjs: 1 },
        { tipo: 'par_teia_n2', titulo: 'Par na teia N2', severidade: 'atencao', qtd_cnpjs: 3 },
        { tipo: 'socio_cadunico', titulo: 'Alerta informativo', severidade: 'normal', qtd_cnpjs: 1 },
      ],
    }
    wrapper = mountHome()
    await flushPromises()

    const beneficio = wrapper.get('[aria-label^="Benefício social:"]')
    await beneficio.trigger('click')
    expect(filters.selectedSocioBeneficio).toBe('direto')
    expect(wrapper.get('[aria-label^="Benefício social:"]').attributes('aria-pressed')).toBe('true')
    await wrapper.get('[aria-label^="Benefício social:"]').trigger('click')
    expect(filters.selectedSocioBeneficio).toBe('Todos')

    await wrapper.get('[aria-label^="Vínculo eSocial:"]').trigger('click')
    expect(filters.selectedSocioEsocial).toBe('direto')
    await wrapper.get('[aria-label^="Par na teia N2:"]').trigger('click')
    expect(filters.selectedParTeia).toBe('n2')
    const unknown = wrapper.get('[aria-label^="Alerta informativo:"]')
    await unknown.trigger('click')
    expect(filters.selectedSocioBeneficio).toBe('Todos')
    expect(filters.selectedSocioEsocial).toBe('direto')
    expect(filters.selectedParTeia).toBe('n2')
    expect(mocks.panoramaAlertTooltip).toHaveBeenCalledWith(
      expect.objectContaining({ tipo: 'socio_cadunico' }),
      expect.objectContaining({ aumentoMinimo: expect.stringContaining('500') }),
    )
  })

  it('aciona verificação e atualização no modo web e desktop', async () => {
    wrapper = mountHome()
    await flushPromises()
    const openSpy = vi.spyOn(window, 'open').mockImplementation(() => null)
    await wrapper.get('[aria-label="Verificar atualizações"]').trigger('click')
    expect(mocks.updateStore.forceCheckUpdate).toHaveBeenCalledOnce()

    mocks.updateStore.status = { available: true }
    mocks.updateStore.isCurrent = false
    mocks.updateStore.downloadUrl = null
    mocks.updateStore.hasUpdate = true
    await wrapper.get('.system-stat--update').trigger('click')
    expect(openSpy).toHaveBeenCalledWith('https://cgu-sc.github.io/sentinela/', '_blank')
    expect(wrapper.find('.update-pulse-icon').exists()).toBe(true)

    Object.defineProperty(window, 'pywebview', { configurable: true, value: { api: {} } })
    await wrapper.get('.system-stat--update').trigger('keydown.enter')
    expect(mocks.updateStore.startDownload).toHaveBeenCalledOnce()
    delete window.pywebview
  })

  it('cobre fallbacks de versão, período, cache, KPIs e escopo geográfico', async () => {
    const geo = useGeoStore()
    filters.periodo = null
    analytics.resultadoSentinelaUF = []
    const cacheStatus = {
      is_ready: true,
      modules_summary_label: 'Resumo do cache',
      modules: { movimento: { label: 'Movimentação', loaded: true, exists: true } },
    }
    analytics.kpis = [{ label: 'Métrica sem valor', value: null }]
    mocks.updateStore.currentVersion = null
    mocks.updateStore.checkedAtFormatted = null
    mocks.updateStore.message = null
    mocks.updateStore.statusLabel = null
    mocks.updateStore.status = null
    mocks.updateStore.isCurrent = true
    mocks.updateStore.loading = true
    wrapper = mountHome()
    await flushPromises()
    analytics.cacheStatus = cacheStatus
    await wrapper.vm.$nextTick()
    const api = wrapper.vm.$.setupState

    expect(api.normalizeLabel(0)).toBe('')
    expect(api.getKpiValue('métrica sem valor')).toBe('-')
    expect(api.periodText).toBe('Período não definido')
    expect(api.ufCount).toBe(0)
    expect(api.cacheSummaryText).toBe('Resumo do cache')
    expect(api.cacheModuleSummary).toMatchObject({ value: '100%', label: 'módulos carregados' })
    expect(api.appVersionLabel).toContain('v')
    expect(JSON.stringify(api.updateStatusTooltip)).toContain('Verificação pendente')
    mocks.updateStore.checkedAtFormatted = '02/10/2026 10:30'
    await wrapper.vm.$nextTick()
    expect(JSON.stringify(api.updateStatusTooltip)).toContain('Última verificação: 02/10/2026 10:30')
    analytics.resultadoSentinelaUF = null
    await wrapper.vm.$nextTick()
    expect(api.ufCount).toBe(0)
    expect(wrapper.get('.system-stat--update').text()).toContain('—')
    expect(wrapper.find('.system-stat--update .pi-spin').exists()).toBe(true)

    const openSpy = vi.spyOn(window, 'open').mockImplementation(() => null)
    api.handleUpdateClick()
    expect(openSpy).not.toHaveBeenCalled()
    expect(mocks.updateStore.startDownload).not.toHaveBeenCalled()

    geo.localidades = []
    filters.selectedMunicipio = '9999999'
    expect(() => api.financialScopeMetric).toThrow('Municipio selecionado sem nome no contrato de localidades.')
    filters.selectedMunicipio = 'Todos'
    filters.selectedRegiaoSaude = '9999999'
    expect(() => api.financialScopeMetric).toThrow('Regiao selecionada sem nome no contrato de localidades.')
    filters.selectedRegiaoSaude = 'Todos'
  })
})
