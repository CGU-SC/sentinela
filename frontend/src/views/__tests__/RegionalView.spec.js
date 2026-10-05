import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, disposePinia, setActivePinia } from 'pinia'
import { nextTick } from 'vue'
import axios from 'axios'

import RegionalView from '@/views/RegionalView.vue'
import { API_ENDPOINTS } from '@/config/api'
import { useFilterStore } from '@/stores/filters'
import { useGeoStore } from '@/stores/geo'

vi.mock('axios', () => ({
  default: {
    get: vi.fn(),
    put: vi.fn(),
  },
}))

const REGIAO_ID = 1100001
const LOCALIDADES = [{
  id_ibge7: 1100015,
  id_regiao_saude: REGIAO_ID,
  sg_uf: 'RO',
  no_municipio: 'Alta Floresta D’Oeste',
  no_regiao_saude: 'Região Central',
}]

const MUNICIPIOS = [{ id_ibge7: 1100015, no_municipio: 'Alta Floresta D’Oeste' }]
const FARMACIAS = [{ cnpj: '12345678000195', razao_social: 'Farmácia Teste' }]

const RegionalMunicipalTableStub = {
  props: ['municipios'],
  template: '<div data-test="municipal-table">{{ municipios.length }}</div>',
}
const RegionalPharmacyTableStub = {
  props: ['farmacias'],
  template: '<div data-test="pharmacy-table">{{ farmacias.length }}</div>',
}

describe('RegionalView — integração entre filtros, tela e API', () => {
  let pinia
  let filters
  let fetchMock

  beforeEach(async () => {
    vi.useFakeTimers()
    localStorage.clear()
    axios.get.mockResolvedValue({
      data: { filters: {}, ui: { sidebarCollapsed: false, sidebarLocked: false } },
    })
    axios.put.mockResolvedValue({ data: {} })
    fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        nome_regiao: 'Região Central',
        id_regiao: REGIAO_ID,
        municipios: MUNICIPIOS,
        farmacias: FARMACIAS,
      }),
    })
    vi.stubGlobal('fetch', fetchMock)

    pinia = createPinia()
    setActivePinia(pinia)
    useGeoStore().localidades = LOCALIDADES
    filters = useFilterStore()
    await Promise.resolve()
    await Promise.resolve()
    filters.selectedRegiaoSaude = String(REGIAO_ID)
    await nextTick()
  })

  afterEach(() => {
    disposePinia(pinia)
    vi.clearAllTimers()
    vi.useRealTimers()
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
    localStorage.clear()
  })

  function mountView() {
    return mount(RegionalView, {
      global: {
        plugins: [pinia],
        stubs: {
          ProgressBar: true,
          RegionalMunicipalTable: RegionalMunicipalTableStub,
          RegionalPharmacyTable: RegionalPharmacyTableStub,
        },
      },
    })
  }

  it('envia os IDs territoriais e mostra os dados retornados', async () => {
    const wrapper = mountView()
    await flushPromises()

    expect(fetchMock).toHaveBeenCalledWith(
      API_ENDPOINTS.analyticsRegionalBenchmarking('RO', String(REGIAO_ID)),
    )
    expect(wrapper.get('h1').text()).toBe('Região Central')
    expect(wrapper.text()).toContain('1 farmácias')
    expect(wrapper.text()).toContain('1 municípios')
    expect(wrapper.get('[data-test="municipal-table"]').text()).toBe('1')
    expect(wrapper.get('[data-test="pharmacy-table"]').text()).toBe('1')
  })

  it('apresenta o estado vazio quando a API retorna uma região sem farmácias', async () => {
    fetchMock.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ nome_regiao: 'Região Central', id_regiao: REGIAO_ID, municipios: [], farmacias: [] }),
    })

    const wrapper = mountView()
    await flushPromises()

    expect(wrapper.text()).toContain('Nenhum dado encontrado')
    expect(wrapper.text()).toContain('Região Central não possui farmácias no cache atual.')
    expect(wrapper.find('[data-test="pharmacy-table"]').exists()).toBe(false)
  })

  it('exibe erro recuperável quando a API responde com falha HTTP', async () => {
    const errorSpy = vi.spyOn(console, 'error').mockImplementation(() => {})
    fetchMock.mockResolvedValueOnce({ ok: false, status: 503 })

    const wrapper = mountView()
    await flushPromises()

    expect(wrapper.get('.error-state').text()).toContain('Não foi possível carregar os dados da região')
    expect(errorSpy).toHaveBeenCalled()
  })

  it('orienta o usuário e não consulta a API sem uma região selecionada', async () => {
    filters.selectedRegiaoSaude = 'Todos'
    await nextTick()
    fetchMock.mockClear()

    const wrapper = mountView()
    await flushPromises()

    expect(wrapper.vm.regiaoSelecionadaNome).toBeNull()
    expect(wrapper.text()).toContain('Selecione uma Região de Saúde')
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('mostra o ID da região enquanto carrega quando o nome não existe no cadastro geográfico', async () => {
    useGeoStore().localidades = []
    filters.selectedRegiaoSaude = String(REGIAO_ID)
    await nextTick()

    let resolveFetch
    fetchMock.mockImplementationOnce(() => new Promise((resolve) => { resolveFetch = resolve }))
    const wrapper = mountView()
    await nextTick()

    expect(wrapper.get('.loading-state').text()).toContain(String(REGIAO_ID))

    resolveFetch({
      ok: true,
      json: async () => ({ nome_regiao: 'Região Central', id_regiao: REGIAO_ID, municipios: [], farmacias: [] }),
    })
    await flushPromises()
    expect(wrapper.text()).toContain(`A região ${REGIAO_ID} não possui farmácias no cache atual.`)
  })
})
