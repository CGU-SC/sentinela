import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { reactive, ref } from 'vue'
import { createMemoryHistory, createRouter } from 'vue-router'

import TargetsView from '@/views/TargetsView.vue'
import { DEFAULT_TARGET_KEY, TARGET_GROUPS } from '@/config/targetConfig'

const mocks = vi.hoisted(() => ({ targetsStore: null, filters: null }))

vi.mock('@/stores/targets', () => ({ useTargetsStore: () => mocks.targetsStore }))
vi.mock('@/stores/filters', () => ({ useFilterStore: () => mocks.filters }))
vi.mock('@/composables/useFrozenData', () => ({ useFrozenData: (source) => source() }))
vi.mock('@/views/components/targets/TargetKpiStrip.vue', () => ({ default: { template: '<section data-test="target-kpis" />' } }))
vi.mock('@/views/components/targets/TargetMap.vue', () => ({
  default: {
    props: ['targetMeta', 'mapData', 'activeUf', 'selectedIbge7', 'selectedRegiao', 'isLoading'],
    emits: ['select-uf', 'select-municipio', 'back-to-uf', 'clear-geography'],
    template: '<section data-test="target-map" :data-selected-ibge7="selectedIbge7"><button data-test="select-target-city" @click="$emit(\'select-municipio\', 1100015)">Município</button><button data-test="clear-target-city" @click="$emit(\'select-municipio\', null)">Limpar município</button><button data-test="select-target-uf" @click="$emit(\'select-uf\', \'RO\')">UF</button><button data-test="back-target-uf" @click="$emit(\'back-to-uf\')">Voltar UF</button><button data-test="clear-target-geography" @click="$emit(\'clear-geography\')">Limpar geografia</button></section>',
  },
}))
vi.mock('@/views/components/targets/TargetTableRenderer.vue', () => ({
  default: {
    props: ['targetKey', 'rows', 'loading', 'totalRecords'],
    emits: ['lazy-load', 'open-incompatibility'],
    template: '<section data-test="target-table"><button data-test="lazy-load" @click="$emit(\'lazy-load\', { first: 25, rows: 25, sortField: \'cnpj\', sortOrder: 1 })">Paginar</button><button data-test="open-clinical" @click="$emit(\'open-incompatibility\', \'12345678000195\')">Abrir incompatibilidade</button><button data-test="open-empty-clinical" @click="$emit(\'open-incompatibility\', \'\')">Abrir sem CNPJ</button></section>',
  },
}))
vi.mock('@/views/components/cnpj/ClinicalIncompatibilityDialog.vue', () => ({ default: {
  props: ['modelValue', 'cnpj'],
  emits: ['update:modelValue'],
  template: '<div data-test="clinical-dialog" :data-open="modelValue" :data-cnpj="cnpj"><button data-test="close-clinical" @click="$emit(\'update:modelValue\', false)">Fechar</button></div>',
} }))

const DEFAULT_META = TARGET_GROUPS.flatMap((group) => group.targets)
  .find((target) => target.key === DEFAULT_TARGET_KEY)

describe('TargetsView — consulta e recortes territoriais', () => {
  let router
  let wrapper

  beforeEach(async () => {
    const selectedTarget = ref(DEFAULT_TARGET_KEY)
    mocks.targetsStore = reactive({
      selectedTarget,
      selectedTargetMeta: ref(DEFAULT_META),
      targetKpis: ref([]),
      mapData: ref([]),
      rows: ref([]),
      totalRecords: ref(0),
      page: ref(1),
      rowsPerPage: ref(25),
      sortField: ref('score'),
      sortOrder: ref(-1),
      isLoading: ref(false),
      isTableLoading: ref(false),
      sourceNotice: ref(null),
      setSelectedTarget: vi.fn((key) => {
        const meta = TARGET_GROUPS.flatMap((group) => group.targets).find((target) => target.key === key)
        mocks.targetsStore.selectedTarget = key
        mocks.targetsStore.selectedTargetMeta = meta
      }),
      loadCurrentTarget: vi.fn().mockResolvedValue(),
      updateTableState: vi.fn(),
    })
    mocks.filters = reactive({
      selectedUF: 'Todos',
      selectedMunicipio: 'Todos',
      selectedRegiaoSaude: 'Todos',
      indicadoresTabelaApiParamsKey: 'sem-filtros',
    })
    router = createRouter({
      history: createMemoryHistory(),
      routes: [{ path: '/alvos', name: 'Targets', component: TargetsView }],
    })
    await router.push('/alvos')
    await router.isReady()
  })

  afterEach(() => {
    wrapper?.unmount()
    wrapper = null
    vi.restoreAllMocks()
  })

  function mountView() {
    return mount(TargetsView, {
      global: {
        plugins: [router],
        directives: { tooltip() {} },
      },
    })
  }

  it('carrega o alvo padrão e monta mapa, tabela e KPIs', async () => {
    wrapper = mountView()
    await flushPromises()

    expect(mocks.targetsStore.loadCurrentTarget).toHaveBeenCalled()
    expect(wrapper.find('[data-test="target-kpis"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="target-map"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="target-table"]').exists()).toBe(true)
  })

  it('sincroniza a seleção de alvo com store, rota e nova consulta', async () => {
    wrapper = mountView()
    await flushPromises()
    const callsBeforeSelection = mocks.targetsStore.loadCurrentTarget.mock.calls.length
    const target = TARGET_GROUPS.flatMap((group) => group.targets)
      .find((item) => item.enabled && item.key !== DEFAULT_TARGET_KEY)
    const button = wrapper.findAll('button.target-btn').find((item) => item.text().includes(target.label))
    await button.trigger('click')
    await flushPromises()

    expect(mocks.targetsStore.setSelectedTarget).toHaveBeenCalledWith(target.key)
    expect(mocks.targetsStore.selectedTarget).toBe(target.key)
    expect(router.currentRoute.value.query.tipo).toBe(target.key)
    expect(mocks.targetsStore.loadCurrentTarget.mock.calls.length).toBeGreaterThan(callsBeforeSelection)
  })

  it('aplica a seleção de município em formato IBGE7', async () => {
    wrapper = mountView()
    await flushPromises()
    await wrapper.get('[data-test="select-target-city"]').trigger('click')

    expect(mocks.filters.selectedMunicipio).toBe('1100015')
  })

  it('encaminha a paginação e a ordenação da tabela à store', async () => {
    wrapper = mountView()
    await flushPromises()
    await wrapper.get('[data-test="lazy-load"]').trigger('click')

    expect(mocks.targetsStore.updateTableState).toHaveBeenCalledWith({
      first: 25,
      rows: 25,
      sortField: 'cnpj',
      sortOrder: 1,
    })
  })

  it('normaliza alvos inválidos na rota e sincroniza alvos válidos abertos externamente', async () => {
    wrapper = mountView()
    await flushPromises()

    await router.push({ path: '/alvos', query: { tipo: 'inexistente' } })
    await flushPromises()
    expect(router.currentRoute.value.query.tipo).toBe(DEFAULT_TARGET_KEY)

    const otherTarget = TARGET_GROUPS.flatMap((group) => group.targets)
      .find((item) => item.enabled && item.key !== DEFAULT_TARGET_KEY)
    const callsBefore = mocks.targetsStore.loadCurrentTarget.mock.calls.length
    await router.push({ path: '/alvos', query: { tipo: otherTarget.key } })
    await flushPromises()

    expect(mocks.targetsStore.selectedTarget).toBe(otherTarget.key)
    expect(mocks.targetsStore.setSelectedTarget).toHaveBeenCalledWith(otherTarget.key)
    expect(mocks.targetsStore.loadCurrentTarget.mock.calls.length).toBeGreaterThan(callsBefore)
  })

  it('encaminha mudanças geográficas, incompatibilidade e alterações dos filtros da tabela', async () => {
    wrapper = mountView()
    await flushPromises()

    await wrapper.get('[data-test="select-target-uf"]').trigger('click')
    expect(mocks.filters.selectedUF).toBe('RO')
    expect(mocks.filters.selectedMunicipio).toBe('Todos')
    expect(mocks.filters.selectedRegiaoSaude).toBe('Todos')

    await wrapper.get('[data-test="select-target-city"]').trigger('click')
    expect(wrapper.get('[data-test="target-map"]').attributes('data-selected-ibge7')).toBe('1100015')
    await wrapper.get('[data-test="clear-target-city"]').trigger('click')
    expect(mocks.filters.selectedMunicipio).toBe('Todos')

    await wrapper.get('[data-test="back-target-uf"]').trigger('click')
    expect(mocks.filters.selectedMunicipio).toBe('Todos')
    expect(mocks.filters.selectedRegiaoSaude).toBe('Todos')
    await wrapper.get('[data-test="clear-target-geography"]').trigger('click')
    expect(mocks.filters.selectedUF).toBe('Todos')

    await wrapper.get('[data-test="open-empty-clinical"]').trigger('click')
    expect(wrapper.get('[data-test="clinical-dialog"]').attributes('data-open')).toBe('false')
    await wrapper.get('[data-test="open-clinical"]').trigger('click')
    expect(wrapper.get('[data-test="clinical-dialog"]').attributes('data-open')).toBe('true')
    expect(wrapper.get('[data-test="clinical-dialog"]').attributes('data-cnpj')).toBe('12345678000195')
    await wrapper.get('[data-test="close-clinical"]').trigger('click')
    expect(wrapper.get('[data-test="clinical-dialog"]').attributes('data-open')).toBe('false')

    mocks.targetsStore.page = 4
    const loadsBeforeFilterChange = mocks.targetsStore.loadCurrentTarget.mock.calls.length
    mocks.filters.indicadoresTabelaApiParamsKey = 'com-filtro'
    await flushPromises()
    expect(mocks.targetsStore.page).toBe(1)
    expect(mocks.targetsStore.loadCurrentTarget.mock.calls.length).toBeGreaterThan(loadsBeforeFilterChange)
  })
})
