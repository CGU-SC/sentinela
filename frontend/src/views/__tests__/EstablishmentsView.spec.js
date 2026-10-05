import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, disposePinia, setActivePinia } from 'pinia'
import { nextTick } from 'vue'
import axios from 'axios'

import EstablishmentsView from '@/views/EstablishmentsView.vue'
import { API_ENDPOINTS } from '@/config/api'
import { useFilterStore } from '@/stores/filters'
import { useGeoStore } from '@/stores/geo'
import { useRiskIndicatorsStore } from '@/stores/riskIndicators'

const mocks = vi.hoisted(() => ({
  fetchRiskIndicator: vi.fn(),
  fetchRiskIndicatorEstablishmentsPage: vi.fn(),
}))

vi.mock('axios', () => ({
  default: {
    get: vi.fn(),
    put: vi.fn(),
  },
}))
vi.mock('@/composables/useFetchAnalytics', () => ({ useFetchAnalytics: vi.fn() }))
vi.mock('@/composables/useRiskIndicatorAnalysis', () => ({
  useRiskIndicatorAnalysis: () => ({
    fetchRiskIndicator: mocks.fetchRiskIndicator,
    fetchRiskIndicatorEstablishmentsPage: mocks.fetchRiskIndicatorEstablishmentsPage,
  }),
}))
vi.mock('@/views/components/KpiSection.vue', () => ({ default: { template: '<section data-test="kpis" />' } }))
vi.mock('@/views/components/establishments/EstablishmentRiskMap.vue', () => ({
  default: {
    props: ['mapData', 'activeUf', 'selectedIbge7', 'selectedRegiao', 'selectedMunicipioNome', 'selectedRegiaoNome', 'isLoading', 'error', 'kpis', 'indicadorLabel'],
    emits: ['select-municipio', 'select-uf', 'back-to-uf', 'clear-geography'],
    template: '<section data-test="risk-map" :data-selected-ibge7="selectedIbge7" :data-selected-municipio-nome="selectedMunicipioNome" :data-selected-regiao-nome="selectedRegiaoNome" :data-indicator-label="indicadorLabel" :data-kpi-critical="kpis?.total_critico" :data-kpi-attention="kpis?.total_atencao" :data-kpi-missing="kpis?.total_sem_dados" :data-kpi-exceed="kpis?.pct_acima_limiar"><button data-test="select-municipio" @click="$emit(\'select-municipio\', 1100015)">Município</button><button data-test="clear-municipio" @click="$emit(\'select-municipio\', null)">Limpar município</button><button data-test="select-uf" @click="$emit(\'select-uf\', \'RO\')">UF</button><button data-test="back-to-uf" @click="$emit(\'back-to-uf\')">Voltar UF</button><button data-test="clear-geography" @click="$emit(\'clear-geography\')">Limpar</button></section>',
  },
}))
vi.mock('@/views/components/establishments/EstablishmentRiskTable.vue', () => ({
  default: {
    props: ['cnpjs', 'indicadorKey', 'totalRecords', 'first', 'rows', 'sortField', 'sortOrder'],
    emits: ['lazy-load', 'clear-regiao-filter', 'clear-municipio-filter'],
    template: '<section data-test="risk-table">{{ cnpjs.map((item) => item.cnpj).join(\',\') }}<button data-test="lazy-load" @click="$emit(\'lazy-load\', { first: 50, rows: 25, sortField: \'cnpj\', sortOrder: 1 })">Carregar página</button><button data-test="lazy-load-defaults" @click="$emit(\'lazy-load\', {})">Carregar padrão</button><button data-test="clear-regiao" @click="$emit(\'clear-regiao-filter\')">Limpar região</button><button data-test="clear-table-municipio" @click="$emit(\'clear-municipio-filter\')">Limpar município</button></section>',
  },
}))
vi.mock('@/views/components/risk-indicators/RiskIndicatorSelector.vue', () => ({
  default: {
    emits: ['select'],
    template: '<button data-test="select-indicator" @click="$emit(\'select\', \'falecidos\')">Falecidos</button>',
  },
}))

describe('EstablishmentsView — análise de indicadores por estabelecimento', () => {
  let pinia
  let filters
  let indicators
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
    indicators = useRiskIndicatorsStore()
    useGeoStore().localidades = [
      {
        id_ibge7: 1100015,
        id_regiao_saude: 1100001,
        sg_uf: 'RO',
        no_municipio: 'Alta Floresta D’Oeste',
        no_regiao_saude: 'Região Central',
      },
      {
        id_ibge7: 1100023,
        id_regiao_saude: 1100002,
        sg_uf: 'RO',
        no_municipio: 'Ariquemes',
        no_regiao_saude: 'Região Vale do Jamari',
      },
    ]
    await Promise.resolve()
    await Promise.resolve()
  })

  afterEach(async () => {
    wrapper?.unmount()
    wrapper = null
    await nextTick()
    await vi.runOnlyPendingTimersAsync()
    disposePinia(pinia)
    vi.restoreAllMocks()
    vi.useRealTimers()
    localStorage.clear()
  })

  function mountView() {
    wrapper = mount(EstablishmentsView, { global: { plugins: [pinia] } })
    return wrapper
  }

  it('apresenta instrução inicial quando nenhum indicador foi selecionado', () => {
    const view = mountView()

    expect(view.text()).toContain('Selecione um Indicador')
    expect(view.find('[data-test="risk-map"]').exists()).toBe(false)
    expect(view.find('[data-test="risk-table"]').exists()).toBe(false)
  })

  it('encaminha seleção, filtros geográficos e paginação ao fluxo de análise', async () => {
    indicators.selectedRiskIndicator = 'falecidos'
    indicators.cnpjsRows = 25
    indicators.cnpjsSortField = 'score'
    indicators.cnpjsSortOrder = -1
    const view = mountView()
    await flushPromises()

    await view.get('[data-test="select-indicator"]').trigger('click')
    expect(mocks.fetchRiskIndicator).toHaveBeenCalledWith('falecidos')

    await view.get('[data-test="select-municipio"]').trigger('click')
    expect(filters.selectedMunicipio).toBe('1100015')
    await view.get('[data-test="clear-geography"]').trigger('click')
    expect(filters.selectedMunicipio).toBe('Todos')
    expect(filters.selectedRegiaoSaude).toBe('Todos')
    expect(filters.selectedUF).toBe('Todos')

    await view.get('[data-test="lazy-load"]').trigger('click')
    expect(mocks.fetchRiskIndicatorEstablishmentsPage).toHaveBeenCalledWith('falecidos', {
      page: 3,
      pageSize: 25,
      sortField: 'cnpj',
      sortOrder: 1,
    })
  })

  it('filtra os CNPJs pelo município, repassa os nomes de localidade e limpa cada filtro', async () => {
    indicators.selectedRiskIndicator = 'falecidos'
    indicators.kpis = { total_critico: 9 }
    indicators.cnpjKpis = { total_critico: 2 }
    indicators.municipios = [{ id_ibge7: 1100015, total_critico: 2 }]
    indicators.cnpjs = [
      { cnpj: '11111111000111', id_ibge7: 1100015 },
      { cnpj: '22222222000122', id_ibge7: 1100023 },
    ]
    filters.selectedUF = 'RO'
    filters.selectedRegiaoSaude = String(1100001)
    filters.selectedMunicipio = '1100015'
    const view = mountView()
    await flushPromises()

    expect(view.get('[data-test="risk-table"]').text()).toContain('11111111000111')
    expect(view.get('[data-test="risk-table"]').text()).not.toContain('22222222000122')
    expect(view.get('[data-test="risk-map"]').attributes('data-selected-ibge7')).toBe('1100015')
    expect(view.get('[data-test="risk-map"]').attributes('data-selected-municipio-nome')).toBe('Alta Floresta D’Oeste')
    expect(view.get('[data-test="risk-map"]').attributes('data-selected-regiao-nome')).toBe('Região Central')
    expect(view.get('[data-test="risk-map"]').attributes('data-kpi-critical')).toBe('2')

    await view.get('[data-test="clear-municipio"]').trigger('click')
    expect(filters.selectedMunicipio).toBe('Todos')
    filters.selectedMunicipio = '1100015'
    await nextTick()
    await view.get('[data-test="clear-table-municipio"]').trigger('click')
    expect(filters.selectedMunicipio).toBe('Todos')
    await view.get('[data-test="clear-regiao"]').trigger('click')
    expect(filters.selectedRegiaoSaude).toBe('Todos')
    await view.get('[data-test="select-uf"]').trigger('click')
    expect(filters.selectedUF).toBe('RO')
    expect(filters.selectedMunicipio).toBe('Todos')
    expect(filters.selectedRegiaoSaude).toBe('Todos')

    filters.selectedMunicipio = '1100015'
    filters.selectedRegiaoSaude = String(1100001)
    await view.get('[data-test="back-to-uf"]').trigger('click')
    expect(filters.selectedMunicipio).toBe('Todos')
    expect(filters.selectedRegiaoSaude).toBe('Todos')
  })

  it('recalcula os KPIs a partir dos estabelecimentos da região selecionada', async () => {
    indicators.selectedRiskIndicator = 'falecidos'
    indicators.kpis = { total_critico: 80, mediana: 12 }
    indicators.cnpjs = [
      { cnpj: '11111111000111', id_ibge7: 1100015, status: 'CRÍTICO' },
      { cnpj: '22222222000122', id_ibge7: 1100015, status: 'ATENÇÃO' },
      { cnpj: '33333333000133', id_ibge7: 1100023, status: 'NORMAL' },
      { cnpj: '44444444000144', id_ibge7: 1100015, status: 'SEM DADOS' },
    ]
    filters.selectedRegiaoSaude = '1100001'
    const view = mountView()
    await flushPromises()

    const map = view.get('[data-test="risk-map"]')
    expect(map.attributes('data-kpi-critical')).toBe('1')
    expect(map.attributes('data-kpi-attention')).toBe('1')
    expect(map.attributes('data-kpi-missing')).toBe('1')
    expect(map.attributes('data-kpi-exceed')).toBe('100')
    expect(view.get('[data-test="risk-table"]').text()).not.toContain('33333333000133')
  })

  it('retorna percentual nulo se a seleção não contém estabelecimentos com dados', async () => {
    indicators.selectedRiskIndicator = 'falecidos'
    indicators.kpis = { total_critico: 80 }
    indicators.cnpjs = [{ cnpj: '11111111000111', id_ibge7: 1100015, status: 'SEM DADOS' }]
    filters.selectedRegiaoSaude = '1100001'
    const view = mountView()
    await flushPromises()

    expect(view.get('[data-test="risk-map"]').attributes('data-kpi-critical')).toBe('0')
    expect(view.get('[data-test="risk-map"]').attributes('data-kpi-exceed')).toBeUndefined()
  })

  it('mostra a tabela vazia quando ainda não existe lista de estabelecimentos', async () => {
    indicators.selectedRiskIndicator = 'falecidos'
    indicators.cnpjs = null
    const view = mountView()
    await flushPromises()

    expect(view.get('[data-test="risk-table"]').exists()).toBe(true)
    expect(view.get('[data-test="risk-table"]').text()).not.toContain('11111111000111')
  })

  it('falha visivelmente quando o município selecionado não consta nas localidades', () => {
    indicators.selectedRiskIndicator = 'falecidos'
    filters.selectedMunicipio = '9999999'

    expect(() => mountView()).toThrow('Municipio selecionado sem nome no contrato de localidades.')
  })

  it('falha visivelmente quando a região selecionada não consta nas localidades', () => {
    indicators.selectedRiskIndicator = 'falecidos'
    filters.selectedRegiaoSaude = '9999999'

    expect(() => mountView()).toThrow('Regiao de saude selecionada sem nome no contrato de localidades.')
  })

  it('usa estado padrão da paginação e ignora eventos se nenhum indicador foi escolhido', async () => {
    indicators.selectedRiskIndicator = 'falecidos'
    indicators.cnpjsRows = 20
    indicators.cnpjsSortField = 'razao_social'
    indicators.cnpjsSortOrder = -1
    const view = mountView()
    await flushPromises()
    await view.get('[data-test="lazy-load-defaults"]').trigger('click')

    expect(mocks.fetchRiskIndicatorEstablishmentsPage).toHaveBeenCalledWith('falecidos', {
      page: 1,
      pageSize: 20,
      sortField: 'razao_social',
      sortOrder: -1,
    })

    indicators.selectedRiskIndicator = null
    indicators.isLoading = true
    await nextTick()
    const callsBefore = mocks.fetchRiskIndicatorEstablishmentsPage.mock.calls.length
    await view.get('[data-test="lazy-load-defaults"]').trigger('click')
    expect(mocks.fetchRiskIndicatorEstablishmentsPage).toHaveBeenCalledTimes(callsBefore)
  })

  it('não inventa metadados para um indicador legado desconhecido', async () => {
    indicators.selectedRiskIndicator = 'indicador_legado'
    const view = mountView()
    await flushPromises()

    expect(view.get('[data-test="risk-map"]').attributes('data-indicator-label')).toBe('')
    expect(view.get('[data-test="risk-table"]').exists()).toBe(true)
  })
})
