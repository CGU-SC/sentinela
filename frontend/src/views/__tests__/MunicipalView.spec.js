import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, disposePinia, setActivePinia } from 'pinia'
import { defineComponent, ref } from 'vue'
import axios from 'axios'

import MunicipalView from '@/views/MunicipalView.vue'
import { API_ENDPOINTS } from '@/config/api'
import { buildAnalyticsParams, useAnalyticsStore } from '@/stores/analytics'
import { useFilterStore } from '@/stores/filters'
import { useGeoStore } from '@/stores/geo'
import { useMunicipalMapStore } from '@/stores/municipalMap'
import { useRiskIndicatorsStore } from '@/stores/riskIndicators'

const mocks = vi.hoisted(() => ({ fetchRiskIndicator: vi.fn() }))

vi.mock('axios', () => ({
  default: {
    get: vi.fn(),
    put: vi.fn(),
  },
}))
vi.mock('@/composables/useFetchAnalytics', () => ({ useFetchAnalytics: vi.fn() }))
vi.mock('@/composables/useRiskIndicatorAnalysis', () => ({
  useRiskIndicatorAnalysis: () => ({ fetchRiskIndicator: mocks.fetchRiskIndicator }),
}))
vi.mock('@/views/components/KpiSection.vue', () => ({ default: { template: '<section data-test="kpis" />' } }))
vi.mock('@/views/components/municipios/MunicipalRiskMap.vue', () => ({
  default: {
    props: ['mapData', 'activeUf', 'selectedIbge7', 'selectedRegiao', 'selectedMunicipioNome', 'selectedRegiaoNome', 'metricMode', 'metricLabel', 'isLoading', 'error'],
    emits: ['select-municipio', 'select-uf', 'back-to-uf', 'clear-geography'],
    template: '<section data-test="municipal-map" :data-rows="mapData.length" :data-uf="activeUf" :data-mode="metricMode" :data-label="metricLabel" :data-selected-ibge7="selectedIbge7" :data-region-name="selectedRegiaoNome" :data-first-critical="mapData[0]?.total_critico"><button data-test="select-municipio" @click="$emit(\'select-municipio\', 1100015)">Município</button><button data-test="clear-municipio" @click="$emit(\'select-municipio\', null)">Limpar município</button><button data-test="select-uf" @click="$emit(\'select-uf\', \'AC\')">UF</button><button data-test="back-to-uf" @click="$emit(\'back-to-uf\')">Voltar UF</button><button data-test="clear-geography" @click="$emit(\'clear-geography\')">Limpar</button></section>',
  },
}))
vi.mock('@/views/components/municipios/MunicipalRiskTable.vue', () => ({
  default: {
    props: ['municipios', 'participationRows', 'selectedIbge7', 'metricMode', 'metricLabel', 'isLoading', 'isStale', 'error'],
    emits: ['select-municipio', 'clear-regiao-filter'],
    template: '<section data-test="municipal-table" :data-rows="municipios.length" :data-participation-rows="participationRows.length" :data-mode="metricMode"><button data-test="select-table-municipio" @click="$emit(\'select-municipio\', 1100015)">Município</button><button data-test="clear-region" @click="$emit(\'clear-regiao-filter\')">Limpar região</button></section>',
  },
}))
vi.mock('@/views/components/risk-indicators/RiskIndicatorSelector.vue', () => ({
  default: {
    props: ['activeRiskIndicatorMeta'],
    emits: ['select'],
    template: '<button data-test="select-indicator" @click="$emit(\'select\', \'falecidos\')">Indicador</button>',
  },
}))

const REGIAO_ID = 1100001
const MUNICIPIO = {
  id_ibge7: 1100015,
  id_regiao_saude: REGIAO_ID,
  sg_uf: 'RO',
  no_municipio: 'Alta Floresta D’Oeste',
  no_regiao_saude: 'Região Central',
}

describe('MunicipalView — filtros, mapa, tabela e indicadores', () => {
  let pinia
  let filters
  let analytics
  let municipalMap
  let wrapper

  beforeEach(async () => {
    vi.useFakeTimers()
    vi.clearAllMocks()
    localStorage.clear()
    axios.get.mockImplementation(async (url) => ({
      data: url === API_ENDPOINTS.preferences ? { filters: {}, ui: {} } : {},
    }))
    axios.put.mockResolvedValue({ data: {} })

    pinia = createPinia()
    setActivePinia(pinia)
    filters = useFilterStore()
    filters.periodo = [new Date('2025-01-01T00:00:00'), new Date('2025-12-31T00:00:00')]
    filters.selectedUF = 'RO'
    filters.selectedRegiaoSaude = String(REGIAO_ID)
    useGeoStore().localidades = [MUNICIPIO]

    analytics = useAnalyticsStore()
    analytics.resultadoMunicipios = [{ ...MUNICIPIO, total_cnpjs: 1 }]
    analytics.sectionKeys = {
      kpis: JSON.stringify(buildAnalyticsParams(filters.apiParams)),
      ufs: null,
      municipios: JSON.stringify(buildAnalyticsParams(filters.apiParams)),
    }
    municipalMap = useMunicipalMapStore()
    municipalMap.rows = [{ ...MUNICIPIO, pct_critico: 12 }]
    municipalMap.loadedKey = JSON.stringify(buildAnalyticsParams({ ...filters.apiParams, idIbge7: null }))
    const indicators = useRiskIndicatorsStore()
    indicators.selectedRiskIndicator = null
  })

  afterEach(() => {
    wrapper?.unmount()
    wrapper = null
    disposePinia(pinia)
    vi.clearAllTimers()
    vi.useRealTimers()
    vi.restoreAllMocks()
    localStorage.clear()
  })

  function mountView() {
    wrapper = mount(MunicipalView, { global: { plugins: [pinia] } })
    return wrapper
  }

  function syncCurrentDataKeys() {
    const dashboardKey = JSON.stringify(buildAnalyticsParams(filters.apiParams))
    analytics.sectionKeys = { kpis: dashboardKey, ufs: null, municipios: dashboardKey }
    municipalMap.loadedKey = JSON.stringify(buildAnalyticsParams({ ...filters.apiParams, idIbge7: null }))
  }

  it('mostra os dados carregados do município no mapa e na tabela', async () => {
    const view = mountView()
    await flushPromises()

    expect(view.get('[data-test="municipal-map"]').attributes('data-rows')).toBe('1')
    expect(view.get('[data-test="municipal-map"]').attributes('data-uf')).toBe('RO')
    expect(view.get('[data-test="municipal-table"]').attributes('data-rows')).toBe('1')
    expect(view.get('[data-test="municipal-table"]').attributes('data-participation-rows')).toBe('1')
  })

  it('converte a seleção do mapa em filtro IBGE7 e permite limpar a geografia', async () => {
    const view = mountView()
    await view.get('[data-test="select-municipio"]').trigger('click')
    expect(filters.selectedMunicipio).toBe('1100015')

    await view.get('[data-test="clear-geography"]').trigger('click')
    expect(filters.selectedMunicipio).toBe('Todos')
    expect(filters.selectedRegiaoSaude).toBe('Todos')
    expect(filters.selectedUF).toBe('Todos')
  })

  it('encaminha a seleção de indicador para o fluxo de análise', async () => {
    const view = mountView()
    await view.get('[data-test="select-indicator"]').trigger('click')

    expect(mocks.fetchRiskIndicator).toHaveBeenCalledWith('falecidos')
  })

  it('mescla métricas do indicador no snapshot e sincroniza seleção geográfica', async () => {
    const indicatorStore = useRiskIndicatorsStore()
    indicatorStore.selectedRiskIndicator = 'falecidos'
    indicatorStore.summaryParamsKey = JSON.stringify({
      indicador: 'falecidos',
      params: filters.indicadoresApiParams,
    })
    indicatorStore.kpis = { total_critico: 1 }
    indicatorStore.municipios = [{ id_ibge7: 1100015, total_cnpjs: 8, total_critico: 2, pct_critico: 25 }]
    analytics.resultadoMunicipios = [{ ...MUNICIPIO, total_cnpjs: 3 }]
    municipalMap.rows = [{ ...MUNICIPIO, total_cnpjs: 3, total_critico: 1, pct_critico: 33 }]
    const view = mountView()
    await flushPromises()

    expect(view.get('[data-test="municipal-map"]').attributes('data-mode')).toBe('indicator')
    expect(view.get('[data-test="municipal-map"]').attributes('data-label')).toContain('Falecidos')
    expect(view.get('[data-test="municipal-map"]').attributes('data-rows')).toBe('1')
    expect(view.get('[data-test="municipal-table"]').attributes('data-mode')).toBe('indicator')

    await view.get('[data-test="select-municipio"]').trigger('click')
    expect(filters.selectedMunicipio).toBe('1100015')
    const nextDashboardKey = JSON.stringify(buildAnalyticsParams(filters.apiParams))
    analytics.sectionKeys = { kpis: nextDashboardKey, ufs: null, municipios: nextDashboardKey }
    municipalMap.loadedKey = JSON.stringify(buildAnalyticsParams({ ...filters.apiParams, idIbge7: null }))
    indicatorStore.summaryParamsKey = JSON.stringify({ indicador: 'falecidos', params: filters.indicadoresApiParams })
    await flushPromises()
    expect(view.get('[data-test="municipal-map"]').attributes('data-selected-ibge7')).toBe('1100015')
    await view.get('[data-test="clear-municipio"]').trigger('click')
    expect(filters.selectedMunicipio).toBe('Todos')

    await view.get('[data-test="select-uf"]').trigger('click')
    expect(filters.selectedUF).toBe('AC')
    expect(filters.selectedMunicipio).toBe('Todos')
    expect(filters.selectedRegiaoSaude).toBe('Todos')
    await view.get('[data-test="back-to-uf"]').trigger('click')
    expect(filters.selectedUF).toBe('AC')
    await view.get('[data-test="clear-geography"]').trigger('click')
    expect(filters.selectedUF).toBe('Todos')
    await view.get('[data-test="select-table-municipio"]').trigger('click')
    await view.get('[data-test="clear-region"]').trigger('click')
    expect(filters.selectedMunicipio).toBe('Todos')
    expect(filters.selectedRegiaoSaude).toBe('Todos')
  })

  it('usa os valores zero e o rótulo genérico quando o indicador não tem metadados ou linha municipal', async () => {
    const indicatorStore = useRiskIndicatorsStore()
    indicatorStore.selectedRiskIndicator = 'indicador_legado'
    indicatorStore.summaryParamsKey = JSON.stringify({ indicador: 'indicador_legado', params: filters.indicadoresApiParams })
    indicatorStore.kpis = { total_critico: 0 }
    indicatorStore.municipios = []
    const view = mountView()
    await flushPromises()

    expect(view.get('[data-test="municipal-map"]').attributes('data-mode')).toBe('indicator')
    expect(view.get('[data-test="municipal-map"]').attributes('data-label')).toBe('Indicador')
    expect(view.get('[data-test="municipal-map"]').attributes('data-first-critical')).toBe('0')
  })

  it('resolve a região pelo município quando o filtro regional está limpo', async () => {
    filters.selectedRegiaoSaude = 'Todos'
    filters.selectedMunicipio = '1100015'
    syncCurrentDataKeys()
    const view = mountView()
    await flushPromises()

    expect(view.get('[data-test="municipal-map"]').attributes('data-region-name')).toBe('Região Central')
  })

  it('retorna região nula quando não há filtro nem município selecionado', async () => {
    filters.selectedRegiaoSaude = 'Todos'
    syncCurrentDataKeys()
    const view = mountView()
    await flushPromises()

    expect(view.get('[data-test="municipal-map"]').attributes('data-region-name')).toBeUndefined()
  })

  it('falha quando o município selecionado não cumpre o contrato geográfico', () => {
    useGeoStore().localidades = [{ ...MUNICIPIO, no_municipio: null }]
    filters.selectedMunicipio = '1100015'
    syncCurrentDataKeys()

    expect(() => mountView()).toThrow('Municipio selecionado nao encontrado no contrato de localidades.')
  })

  it('falha ao selecionar município sem região de saúde obrigatória', async () => {
    filters.selectedRegiaoSaude = 'Todos'
    useGeoStore().localidades = []
    syncCurrentDataKeys()
    let capturedError = null
    wrapper = mount(MunicipalView, {
      global: {
        plugins: [pinia],
        config: { errorHandler: (error) => { capturedError = error } },
      },
    })
    await flushPromises()

    await wrapper.get('[data-test="select-municipio"]').trigger('click')

    expect(capturedError).toMatchObject({ message: 'Municipio selecionado sem contrato geografico completo.' })
  })

  it('falha quando o ID regional selecionado não tem rótulo cadastrado', () => {
    filters.selectedRegiaoSaude = '9999999'
    syncCurrentDataKeys()

    expect(() => mountView()).toThrow('Regiao de saude selecionada sem nome no contrato de localidades.')
  })

  it('reusa linhas do dashboard quando mapa e dashboard compartilham os mesmos filtros', async () => {
    municipalMap.loadedKey = null
    const useRowsSpy = vi.spyOn(municipalMap, 'useDashboardRows')
    const loadSpy = vi.spyOn(municipalMap, 'load')
    const view = mountView()
    await flushPromises()

    expect(useRowsSpy).toHaveBeenCalledWith(municipalMap.loadedKey, analytics.resultadoMunicipios)
    expect(loadSpy).not.toHaveBeenCalled()
    expect(view.get('[data-test="municipal-map"]').attributes('data-rows')).toBe('1')
  })

  it('consulta o endpoint de mapa quando o recorte municipal difere do dashboard', async () => {
    useGeoStore().localidades.push({
      id_ibge7: 1200013,
      id_regiao_saude: 1200002,
      sg_uf: 'AC',
      no_municipio: 'Rio Branco',
      no_regiao_saude: 'Baixo Acre',
    })
    filters.selectedUF = 'AC'
    filters.selectedMunicipio = '1200013'
    municipalMap.loadedKey = null
    const loadSpy = vi.spyOn(municipalMap, 'load').mockResolvedValue()
    mountView()
    await flushPromises()

    expect(loadSpy).toHaveBeenCalledWith(
      JSON.stringify(buildAnalyticsParams({ ...filters.apiParams, idIbge7: null })),
      buildAnalyticsParams({ ...filters.apiParams, idIbge7: null }),
    )
  })

  it('desativa as consultas ao sair da view e volta a carregar ao reativá-la', async () => {
    useGeoStore().localidades.push({
      id_ibge7: 1200013,
      id_regiao_saude: 1200002,
      sg_uf: 'AC',
      no_municipio: 'Rio Branco',
      no_regiao_saude: 'Baixo Acre',
    })
    const loadSpy = vi.spyOn(municipalMap, 'load').mockResolvedValue()
    const Host = defineComponent({
      components: { MunicipalView },
      setup() { return { visible: ref(true) } },
      template: '<KeepAlive><MunicipalView v-if="visible" /></KeepAlive><button data-test="toggle" @click="visible = !visible">alternar</button>',
    })
    wrapper = mount(Host, { global: { plugins: [pinia] } })
    await flushPromises()
    const viewInstance = wrapper.findComponent(MunicipalView).vm.$.setupState
    expect(viewInstance.isActive).toBe(true)
    await wrapper.get('[data-test="toggle"]').trigger('click')
    await flushPromises()
    expect(viewInstance.isActive).toBe(false)
    filters.selectedUF = 'AC'
    filters.selectedMunicipio = '1200013'
    await flushPromises()
    expect(loadSpy).not.toHaveBeenCalled()

    await wrapper.get('[data-test="toggle"]').trigger('click')
    await flushPromises()
    expect(viewInstance.isActive).toBe(true)
    expect(loadSpy).toHaveBeenCalledOnce()
  })

  it('não dispara consultas ao mapa quando o período selecionado é inválido', async () => {
    const loadSpy = vi.spyOn(municipalMap, 'load')
    const useRowsSpy = vi.spyOn(municipalMap, 'useDashboardRows')
    filters.periodo = []
    const view = mountView()
    await flushPromises()

    expect(view.exists()).toBe(true)
    expect(loadSpy).not.toHaveBeenCalled()
    expect(useRowsSpy).not.toHaveBeenCalled()
  })
})
