import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { reactive } from 'vue'
import { createPinia, disposePinia, setActivePinia } from 'pinia'
import axios from 'axios'

import UFDrillMap from '@/views/components/maps/UFDrillMap.vue'
import { useAnalyticsStore } from '@/stores/analytics'
import { useFilterStore } from '@/stores/filters'

const mocks = vi.hoisted(() => ({
  themeStore: null,
  ensureBrasilUfMap: vi.fn(),
  dispatchAction: vi.fn(),
  useEcharts: vi.fn(),
  chartAvailable: true,
}))

vi.mock('axios', () => ({
  default: {
    get: vi.fn().mockResolvedValue({ data: { filters: {}, ui: { sidebarCollapsed: false, sidebarLocked: false } } }),
    put: vi.fn().mockResolvedValue({ data: {} }),
  },
}))
vi.mock('@/stores/theme', () => ({ useThemeStore: () => mocks.themeStore }))
vi.mock('@/composables/echartsMaps', () => ({ ensureBrasilUfMap: mocks.ensureBrasilUfMap }))
vi.mock('echarts/core', () => ({ use: mocks.useEcharts }))
vi.mock('echarts/renderers', () => ({ CanvasRenderer: {} }))
vi.mock('echarts/charts', () => ({ MapChart: {} }))
vi.mock('echarts/components', () => ({ TooltipComponent: {}, VisualMapComponent: {} }))
vi.mock('vue-echarts', async () => {
  const { h } = await import('vue')
  return {
    default: {
      name: 'VChart',
      props: { option: Object, autoresize: Boolean },
      emits: ['click'],
      setup(props, { expose, emit }) {
        if (mocks.chartAvailable) expose({ chart: { dispatchAction: mocks.dispatchAction } })
        return () => h('div', { class: 'mock-map-chart' }, [
          h('output', { 'data-test': 'selected-map' }, props.option.series[0].data.filter((item) => item.selected).map((item) => item.name).join(',')),
          h('button', { 'data-test': 'click-uf', onClick: () => emit('click', { data: props.option.series[0].data[0] }) }, 'Selecionar UF'),
          h('button', { 'data-test': 'click-uf-name', onClick: () => emit('click', { name: 'RJ' }) }, 'Selecionar pelo nome'),
        ])
      },
    },
  }
})

const ufData = [
  { uf: 'SP', percValSemComp: 42.5, valSemComp: 1200000, cnpjs: 55, percQtdeSemComp: 18.75 },
  { uf: 'RJ', percValSemComp: 3.5, valSemComp: 45000, cnpjs: 8, percQtdeSemComp: 2 },
  { uf: 'AC', percValSemComp: null, valSemComp: null, cnpjs: null, percQtdeSemComp: null },
]

describe('UFDrillMap', () => {
  let pinia
  let analytics
  let filters
  let wrappers

  beforeEach(() => {
    vi.useFakeTimers()
    localStorage.clear()
    axios.get.mockResolvedValue({ data: { filters: {}, ui: { sidebarCollapsed: false, sidebarLocked: false } } })
    axios.put.mockResolvedValue({ data: {} })
    mocks.ensureBrasilUfMap.mockReset().mockResolvedValue(undefined)
    mocks.dispatchAction.mockClear()
    mocks.useEcharts.mockClear()
    mocks.chartAvailable = true
    mocks.themeStore = reactive({
      isDark: true,
      currentPalette: 'carbon',
      tokens: { primary: '#123456', textColor: '#eeeeee', mutedColor: '#aaaaaa', borderColor: '#333333' },
    })
    wrappers = []
    pinia = createPinia()
    setActivePinia(pinia)
    analytics = useAnalyticsStore()
    analytics.resultadoSentinelaUFNacional = ufData
    analytics.isLoading = false
    filters = useFilterStore()
  })

  afterEach(() => {
    wrappers.forEach((wrapper) => wrapper.unmount())
    vi.clearAllTimers()
    disposePinia(pinia)
    localStorage.clear()
    vi.restoreAllMocks()
    vi.useRealTimers()
  })

  function montar() {
    const wrapper = mount(UFDrillMap, {
      global: { plugins: [pinia] },
    })
    wrappers.push(wrapper)
    return wrapper
  }

  it('aguarda o mapa nacional, cria as faixas visuais e exibe os dados por UF', async () => {
    let resolveMap
    mocks.ensureBrasilUfMap.mockImplementation(() => new Promise((resolve) => { resolveMap = resolve }))
    const wrapper = montar()
    expect(wrapper.findComponent({ name: 'VChart' }).exists()).toBe(false)
    expect(wrapper.get('h3').text()).toBe('MAPA DE RISCO — UFs')

    resolveMap()
    await flushPromises()
    const option = wrapper.findComponent({ name: 'VChart' }).props('option')

    expect(mocks.ensureBrasilUfMap).toHaveBeenCalledOnce()
    expect(option.series[0].map).toBe('brasil-uf')
    expect(option.series[0].data.map((item) => item.value)).toEqual([42.5, 3.5, 0])
    expect(option.series[0].data[0].itemStyle.opacity).toBe(1)
    expect(option.series[0].data[2].valSemComp).toBe(0)
    expect(option.visualMap.pieces.length).toBeGreaterThan(1)
  })

  it('formata tooltips com dados e estados sem dados', async () => {
    const wrapper = montar()
    await flushPromises()
    const option = wrapper.findComponent({ name: 'VChart' }).props('option')
    const first = option.series[0].data[0]

    const tooltip = option.tooltip.formatter({ name: first.name, data: first })
    expect(tooltip).toContain('SP')
    expect(tooltip).toContain('42,50%')
    expect(tooltip).toContain('R$')
    expect(tooltip).toContain('55')
    expect(option.tooltip.formatter({ name: 'XX', data: null })).toContain('Sem dados')
    expect(option.tooltip.formatter({ name: 'AC', data: option.series[0].data[2] })).toContain('0')
    expect(option.tooltip.formatter({ name: 'UF sem CNPJ', data: { ...first, cnpjs: null } }))
      .toContain('CNPJs: <strong>0</strong>')
  })

  it('usa a última faixa para valores inválidos e aceita o nome da UF no evento', async () => {
    analytics.resultadoSentinelaUFNacional = [{ uf: 'XX', percValSemComp: Number.NaN }]
    const wrapper = montar()
    await flushPromises()
    const option = wrapper.findComponent({ name: 'VChart' }).props('option')
    expect(option.series[0].data[0].itemStyle.areaColor).toBe(option.visualMap.pieces.at(-1).color)

    await wrapper.get('[data-test="click-uf-name"]').trigger('click')
    expect(filters.selectedUF).toBe('RJ')
  })

  it('ignora a sincronização quando o gráfico não expõe uma instância', async () => {
    mocks.chartAvailable = false
    filters.selectedUF = 'SP'
    montar()
    await flushPromises()

    expect(mocks.dispatchAction).not.toHaveBeenCalled()
  })

  it('atualiza e limpa a seleção, mantendo outras UFs esmaecidas', async () => {
    const wrapper = montar()
    await flushPromises()

    await wrapper.get('[data-test="click-uf"]').trigger('click')
    expect(filters.selectedUF).toBe('SP')
    expect(wrapper.get('[data-test="selected-map"]').text()).toBe('SP')
    expect(wrapper.findComponent({ name: 'VChart' }).props('option').series[0].data[1].itemStyle.opacity).toBe(0.85)
    await flushPromises()
    expect(mocks.dispatchAction).toHaveBeenCalledWith({ type: 'select', seriesIndex: 0, name: 'SP' })

    await wrapper.get('[data-test="click-uf"]').trigger('click')
    expect(filters.selectedUF).toBe('Todos')
    await flushPromises()
    expect(mocks.dispatchAction).toHaveBeenCalledWith({ type: 'unselect', seriesIndex: 0, name: 'SP' })
  })

  it('reage ao tema e exibe opacidade de atualização após a espera configurada', async () => {
    const wrapper = montar()
    await flushPromises()
    const darkColor = wrapper.findComponent({ name: 'VChart' }).props('option').series[0].data[0].itemStyle.areaColor

    mocks.themeStore.isDark = false
    analytics.isLoading = true
    await wrapper.vm.$nextTick()
    expect(wrapper.findComponent({ name: 'VChart' }).props('option').series[0].data[0].itemStyle.areaColor).not.toBe(darkColor)
    await vi.advanceTimersByTimeAsync(500)
    expect(wrapper.get('.chart-section').classes()).toContain('is-refreshing')

    analytics.isLoading = false
    await wrapper.vm.$nextTick()
    expect(wrapper.get('.chart-section').classes()).not.toContain('is-refreshing')
  })
})
