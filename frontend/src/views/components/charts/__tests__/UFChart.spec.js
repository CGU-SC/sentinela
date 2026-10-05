import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { reactive } from 'vue'
import { createPinia, disposePinia, setActivePinia } from 'pinia'

import UFChart from '@/views/components/charts/UFChart.vue'
import { useAnalyticsStore } from '@/stores/analytics'

const mocks = vi.hoisted(() => ({ themeStore: null, useEcharts: vi.fn() }))

vi.mock('@/stores/theme', () => ({ useThemeStore: () => mocks.themeStore }))
vi.mock('echarts/core', () => ({ use: mocks.useEcharts }))
vi.mock('echarts/renderers', () => ({ CanvasRenderer: {} }))
vi.mock('echarts/charts', () => ({ BarChart: {}, LineChart: {} }))
vi.mock('echarts/components', () => ({ GridComponent: {}, TooltipComponent: {}, LegendComponent: {}, AxisPointerComponent: {} }))
vi.mock('vue-echarts', () => ({
  default: {
    name: 'VChart',
    props: { option: Object, autoresize: Boolean },
    template: '<div class="mock-echart" data-test="chart">{{ option.series.length }}</div>',
  },
}))

const data = [
  { uf: 'MG', percValSemComp: 12, percQtdeSemComp: 20, totalMov: 120000, cnpjs: 8 },
  { uf: 'SP', percValSemComp: 42.5, percQtdeSemComp: 37.25, totalMov: 999000, cnpjs: 100 },
  { uf: 'RJ', percValSemComp: null, percQtdeSemComp: null, totalMov: null, cnpjs: null },
  { percValSemComp: 5, percQtdeSemComp: 4, totalMov: 500, cnpjs: 1 },
]

describe('UFChart', () => {
  let wrappers
  let pinia
  let analytics

  beforeEach(() => {
    wrappers = []
    mocks.useEcharts.mockClear()
    pinia = createPinia()
    setActivePinia(pinia)
    analytics = useAnalyticsStore()
    analytics.resultadoSentinelaUF = data
    analytics.isLoading = false
    mocks.themeStore = reactive({
      isDark: true,
      currentPalette: 'carbon',
      tokens: { primary: '#123456', textColor: '#eeeeee', mutedColor: '#aaaaaa', borderColor: '#333333' },
    })
  })

  afterEach(() => {
    wrappers.forEach((wrapper) => wrapper.unmount())
    disposePinia(pinia)
    vi.restoreAllMocks()
  })

  function montar(props = {}) {
    const wrapper = mount(UFChart, { props, global: { plugins: [pinia], directives: { tooltip() {} } } })
    wrappers.push(wrapper)
    return wrapper
  }

  it('ordena as UFs por percentual e alinha as séries de volume e percentuais', () => {
    const wrapper = montar({ height: 520, grow: true })
    const option = wrapper.getComponent({ name: 'VChart' }).props('option')

    expect(wrapper.get('.chart-section').classes()).toContain('grow')
    expect(wrapper.get('h3').text()).toContain('POR UF')
    expect(wrapper.props('height')).toBe(520)
    expect(wrapper.getComponent({ name: 'VChart' }).props('autoresize')).toBe(true)
    expect(option.xAxis[0].data).toEqual(['SP', 'MG', 'ND', 'RJ'])
    expect(option.xAxis[1].data).toEqual(['SP', 'MG', 'ND', 'RJ'])
    expect(option.series.map((series) => series.name)).toEqual([
      'Valor Total Movimentado', '% Valor s/ Comp', '% Qtde s/ Comp',
    ])
    expect(option.series[0].data).toEqual([999000, 120000, 500, 0])
    expect(option.series[1].data).toEqual([42.5, 12, 5, 0])
    expect(option.series[2].data).toEqual([37.25, 20, 4, 0])
  })

  it('formata e rotula o tooltip com o risco e os valores da UF selecionada', () => {
    const wrapper = montar()
    const option = wrapper.getComponent({ name: 'VChart' }).props('option')
    const tooltip = option.tooltip.formatter([{ dataIndex: 0 }])

    expect(tooltip).toContain('SP')
    expect(tooltip).toContain('RISCO')
    expect(tooltip).toContain('VALOR TOTAL MOVIMENTADO')
    expect(tooltip).toContain('R$')
    expect(tooltip).toContain('42.50%')
    expect(tooltip).toContain('37.25%')
    expect(tooltip).toContain('100')
    expect(option.tooltip.formatter([])).toBe('')
    expect(option.yAxis[0].axisLabel.formatter(1500)).toContain('R$')
    expect(option.yAxis[1].axisLabel.formatter(12.5)).toBe('12.5%')
  })

  it('substitui por zero os campos ausentes no tooltip da UF', () => {
    const wrapper = montar()
    const option = wrapper.getComponent({ name: 'VChart' }).props('option')
    const tooltip = option.tooltip.formatter([{ dataIndex: 3 }])

    expect(tooltip).toContain('0,00')
    expect(tooltip).toContain('0.00%')
    expect(tooltip).toContain('0')
  })

  it('usa as cores do tema e reflete o estado de carregamento', async () => {
    const wrapper = montar()
    const chart = wrapper.getComponent({ name: 'VChart' })
    const darkColor = chart.props('option').series[0].lineStyle.color
    expect(wrapper.get('.chart-section').classes()).not.toContain('is-refreshing')

    mocks.themeStore.isDark = false
    analytics.isLoading = true
    await wrapper.vm.$nextTick()
    const lightColor = wrapper.getComponent({ name: 'VChart' }).props('option').series[0].lineStyle.color
    expect(lightColor).not.toBe(darkColor)
    expect(wrapper.get('.chart-section').classes()).toContain('is-refreshing')

    analytics.isLoading = false
    await wrapper.vm.$nextTick()
    expect(wrapper.get('.chart-section').classes()).not.toContain('is-refreshing')
  })
})
