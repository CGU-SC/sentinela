import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { reactive } from 'vue'

import TargetMap from '@/views/components/targets/TargetMap.vue'

const mocks = vi.hoisted(() => ({
  geoStore: null,
  themeStore: null,
  registerMap: vi.fn(),
  useEcharts: vi.fn(),
}))

vi.mock('echarts/core', () => ({ use: mocks.useEcharts, registerMap: mocks.registerMap }))
vi.mock('echarts/renderers', () => ({ CanvasRenderer: {} }))
vi.mock('echarts/charts', () => ({ MapChart: {} }))
vi.mock('echarts/components', () => ({ TooltipComponent: {}, VisualMapComponent: {} }))
vi.mock('vue-echarts', async () => {
  const { h } = await import('vue')
  return {
    default: {
      name: 'VChart',
      props: { option: Object },
      emits: ['click'],
      setup(props, { expose, emit }) {
        expose({ chart: { resize: vi.fn() } })
        return () => h('div', { class: 'mock-target-chart' }, props.option.series[0].data.map((row, index) =>
          h('button', {
            key: `${row.name}-${index}`,
            'data-test': `map-item-${index}`,
            onClick: () => emit('click', { data: row }),
          }, row.name),
        ))
      },
    },
  }
})
vi.mock('@/stores/geo', () => ({ useGeoStore: () => mocks.geoStore }))
vi.mock('@/stores/theme', () => ({ useThemeStore: () => mocks.themeStore }))
vi.mock('@/config/chartTheme', async () => {
  const { computed } = await import('vue')
  return { useChartTheme: () => ({ chartTheme: computed(() => ({
    bg: '#fff', tooltip: '#222', tooltipBorder: '#444', tooltipText: '#eee',
  })) }) }
})

const feature = (id, name) => ({
  type: 'Feature',
  properties: { id, name },
  geometry: { type: 'Polygon', coordinates: [[[-46, -23], [-44, -23], [-44, -22], [-46, -23]]] },
})

const municipiosGeo = {
  type: 'FeatureCollection',
  features: [feature(3550308, 'SAO PAULO'), feature(3509502, 'CAMPINAS'), feature(3304557, 'RIO DE JANEIRO')],
}

const mapData = [
  { uf: 'SP', id_ibge7: 3550308, municipio: 'São Paulo', total_farmacias: 10, valor_incompativel: 800000, casos_observados: 12, participacao_uf: 0.8 },
  { uf: 'SP', id_ibge7: 3509502, municipio: 'Campinas', total_farmacias: 5, valor_incompativel: 200000, casos_observados: 3, participacao_uf: 0.2 },
  { uf: 'RJ', id_ibge7: 3304557, municipio: 'Rio de Janeiro', total_farmacias: 0, valor_incompativel: 0, casos_observados: 0, participacao_uf: 0 },
]

const targetMeta = { mapValueLabel: 'Valor incompatível', mapScopeLabel: 'Alvo selecionado' }

describe('TargetMap', () => {
  let wrappers
  let originalResizeObserver
  let resizeObservers

  beforeEach(() => {
    wrappers = []
    resizeObservers = []
    originalResizeObserver = globalThis.ResizeObserver
    globalThis.ResizeObserver = class ResizeObserverMock {
      constructor(callback) {
        this.callback = callback
        resizeObservers.push(this)
      }
      observe() {}
      disconnect = vi.fn()
    }
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => ({ type: 'FeatureCollection', features: [] }) }))
    window.__targetBrasilUfRegistered = false
    mocks.registerMap.mockClear()
    mocks.useEcharts.mockClear()
    mocks.geoStore = reactive({
      localidades: [
        { sg_uf: 'SP', id_regiao_saude: 10, id_ibge7: 3550308 },
        { sg_uf: 'SP', id_regiao_saude: 10, id_ibge7: 3509502 },
        { sg_uf: 'SP', id_regiao_saude: 20, id_ibge7: 3550308 },
        { sg_uf: 'RJ', id_regiao_saude: 10, id_ibge7: 3304557 },
      ],
      getMunicipiosGeoByUF: vi.fn(() => municipiosGeo),
    })
    mocks.themeStore = reactive({ isDark: true, tokens: { primary: '#123456' } })
  })

  afterEach(() => {
    wrappers.forEach((wrapper) => wrapper.unmount())
    if (originalResizeObserver === undefined) delete globalThis.ResizeObserver
    else globalThis.ResizeObserver = originalResizeObserver
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  function montar(props = {}, errorHandler = vi.fn()) {
    const wrapper = mount(TargetMap, {
      props: { targetMeta, ...props },
      global: { directives: { tooltip() {} }, config: { errorHandler } },
    })
    wrappers.push(wrapper)
    return wrapper
  }

  it('registra o mapa nacional, agrega valores e exibe os resumos do alvo', async () => {
    const wrapper = montar({ mapData, isLoading: true })
    await flushPromises()
    const option = wrapper.getComponent({ name: 'VChart' }).props('option')

    expect(fetch).toHaveBeenCalledWith('/geo/brasil-uf.json')
    expect(mocks.registerMap).toHaveBeenCalledWith('target-brasil-uf', expect.any(Object))
    expect(option.series[0].map).toBe('target-brasil-uf')
    expect(option.series[0].data.map(({ name }) => name)).toEqual(['SP', 'RJ'])
    expect(option.series[0].data[0].valor_incompativel).toBe(1000000)
    expect(option.series[0].data[0].participacao).toBe(1)
    expect(wrapper.text().replace(/\u00a0/g, ' ')).toContain('R$ 1.000.000,00')
    expect(wrapper.text()).toContain('15')
    expect(wrapper.get('.target-map-card').classes()).toContain('is-refreshing')
  })

  it('seleciona uma UF nacional e ignora a que não possui ocorrências', async () => {
    const wrapper = montar({ mapData })
    await flushPromises()
    await wrapper.get('[data-test="map-item-0"]').trigger('click')
    expect(wrapper.emitted('select-uf')).toEqual([['SP']])

    await wrapper.setProps({ activeUf: 'RJ' })
    await wrapper.get('[data-test="map-item-0"]').trigger('click')
    expect(wrapper.emitted('select-uf')).toHaveLength(1)
  })

  it('filtra o mapa municipal pela UF e pelo id_regiao_saude, destacando a cidade selecionada', async () => {
    const wrapper = montar({ activeUf: 'SP', selectedRegiao: '10', selectedIbge7: 3550308, mapData })
    await flushPromises()
    const option = wrapper.getComponent({ name: 'VChart' }).props('option')

    expect(mocks.geoStore.getMunicipiosGeoByUF).toHaveBeenCalledWith('SP')
    expect(mocks.registerMap).toHaveBeenCalledWith('target-municipios-SP-10', {
      type: 'FeatureCollection',
      features: municipiosGeo.features.slice(0, 2),
    })
    expect(option.series[0].data.map(({ ibge7 }) => ibge7)).toEqual([3550308, 3509502])
    expect(option.series[0].data[0].itemStyle.borderWidth).toBe(2.5)
    expect(option.series[0].data[1].hasData).toBe(true)
    expect(wrapper.find('.back-button').text()).toContain('SP')
  })

  it('mostra tooltip completo e o estado sem ocorrências', async () => {
    const wrapper = montar({ mapData })
    await flushPromises()
    let option = wrapper.getComponent({ name: 'VChart' }).props('option')
    expect(option.tooltip.formatter({ data: option.series[0].data[0] })).toContain('Valor incompatível')
    expect(option.tooltip.formatter({ data: option.series[0].data[0] })).toContain('CPFs únicos')
    expect(option.tooltip.formatter({ data: option.series[0].data[0] })).toContain('Participação')
    expect(option.tooltip.formatter({ data: option.series[0].data[1] })).toContain('Sem ocorrências')
    expect(option.tooltip.formatter({})).toBe('')

    await wrapper.setProps({ activeUf: 'SP' })
    option = wrapper.getComponent({ name: 'VChart' }).props('option')
    expect(option.tooltip.formatter({ data: option.series[0].data[0] })).toContain('São Paulo')
  })

  it('emite a navegação geográfica apropriada e alterna município selecionado', async () => {
    const wrapper = montar({ activeUf: 'SP', mapData })
    await flushPromises()
    await wrapper.get('.back-button').trigger('click')
    expect(wrapper.emitted('clear-geography')).toHaveLength(1)

    await wrapper.setProps({ selectedRegiao: '10', selectedIbge7: 3550308 })
    await wrapper.get('.back-button').trigger('click')
    expect(wrapper.emitted('back-to-uf')).toHaveLength(1)
    await wrapper.get('[data-test="map-item-0"]').trigger('click')
    expect(wrapper.emitted('select-municipio')).toEqual([[null]])
  })

  it('trata aviso e ausência de dados, e controla zoom com limite inferior', async () => {
    const notice = montar({ sourceNotice: 'Dados de origem indisponíveis', mapData })
    await flushPromises()
    expect(notice.text()).toContain('Dados de origem indisponíveis')
    expect(notice.findComponent({ name: 'VChart' }).exists()).toBe(false)

    const empty = montar({ mapData: [] })
    await flushPromises()
    expect(empty.text()).toContain('Nenhum município encontrado')
    const chart = empty.getComponent({ name: 'VChart' })
    const zoomOut = empty.findAll('.map-controls button')[1]
    await zoomOut.trigger('click')
    expect(chart.props('option').series[0].zoom).toBe(1)
    await empty.findAll('.map-controls button')[0].trigger('click')
    expect(chart.props('option').series[0].zoom).toBe(1.5)
    await empty.findAll('.map-controls button')[2].trigger('click')
    expect(chart.props('option').series[0].zoom).toBe(1)
  })

  it('redimensiona o gráfico e calcula o espaço para uma geometria larga', async () => {
    mocks.geoStore.getMunicipiosGeoByUF.mockReturnValue({
      type: 'FeatureCollection',
      features: [{
        ...feature(3550308, 'SAO PAULO'),
        geometry: { type: 'Polygon', coordinates: [[[0, 0], [2, 0], [2, 1], [0, 0]]] },
      }],
    })
    const wrapper = montar({ activeUf: 'SP', mapData })
    await flushPromises()
    const chart = wrapper.getComponent({ name: 'VChart' })
    const resize = vi.spyOn(chart.vm.chart, 'resize')
    const requestFrame = vi.fn((callback) => { callback(); return 1 })
    vi.stubGlobal('requestAnimationFrame', requestFrame)
    resizeObservers[0].callback([{ contentRect: { width: 900, height: 500 } }])
    await flushPromises()

    expect(chart.props('option').series[0].layoutSize).toBe('104%')
    expect(requestFrame).toHaveBeenCalledOnce()
    expect(resize).toHaveBeenCalledOnce()
  })

  it('falha visivelmente quando o GeoJSON nacional não pode ser carregado', async () => {
    fetch.mockResolvedValueOnce({ ok: false, status: 503 })
    const hookErrors = []
    const wrapper = montar({}, (error) => hookErrors.push(error))
    await flushPromises()
    expect(hookErrors[0].message).toBe('Falha ao carregar GeoJSON nacional: HTTP 503')
    expect(wrapper.findComponent({ name: 'VChart' }).exists()).toBe(false)
  })

  it('usa os tokens claros, preserva o nome do GeoJSON e trata valores e geometrias ausentes', async () => {
    mocks.themeStore.isDark = false
    mocks.geoStore.getMunicipiosGeoByUF.mockReturnValue({
      type: 'FeatureCollection',
      features: [{
        type: 'Feature',
        properties: { id: 3550308, name: 'São Paulo' },
        geometry: { type: 'Polygon' },
      }],
    })
    const wrapper = montar({
      activeUf: 'SP',
      mapData: [{
        uf: 'SP', id_ibge7: 3550308, municipio: null, total_farmacias: 0,
        valor_incompativel: 0, casos_observados: 0, participacao_uf: null,
      }],
    })
    await flushPromises()

    const chart = wrapper.getComponent({ name: 'VChart' })
    const option = chart.props('option')
    expect(option.series[0].data[0]).toMatchObject({ municipio: 'São Paulo', hasData: false })
    expect(option.series[0].data[0].itemStyle).toMatchObject({
      areaColor: 'rgba(0,0,0,0.04)',
      borderColor: 'rgba(0,0,0,0.18)',
    })
    expect(wrapper.vm.$.setupState.geoAspectRatio).toBe(1.5)
    expect(option.tooltip.formatter({ data: {
      municipio: 'São Paulo', hasData: true, valor_incompativel: null,
      casos_observados: null, total_farmacias: null, participacao: null,
    } })).toContain('0,0%')

    chart.vm.$emit('click', { data: option.series[0].data[0] })
    wrapper.vm.$.setupState.handleMapClick({ data: { hasData: true, ibge7: null } })
    expect(wrapper.emitted('select-municipio')).toBeUndefined()

    const zoomIn = wrapper.findAll('.map-controls button')[0]
    for (let index = 0; index < 40; index += 1) await zoomIn.trigger('click')
    expect(chart.props('option').series[0].zoom).toBe(15)
  })

  it('mantém vazia a série quando a UF ainda não tem GeoJSON', async () => {
    mocks.geoStore.getMunicipiosGeoByUF.mockReturnValue(null)
    const wrapper = montar({ activeUf: 'XX', mapData: [] })
    await flushPromises()

    expect(wrapper.vm.$.setupState.visibleGeo).toBeNull()
    expect(wrapper.vm.$.setupState.chartData).toEqual([])
    expect(wrapper.vm.$.setupState.geoAspectRatio).toBe(1.5)
  })

  it('usa participação zero sem valores e cai na última faixa para valor não classificável', async () => {
    const wrapper = montar({
      mapData: [{ uf: 'AC', total_farmacias: 0, valor_incompativel: 0, casos_observados: 0 }],
    })
    await flushPromises()

    const option = wrapper.getComponent({ name: 'VChart' }).props('option')
    expect(option.series[0].data[0]).toMatchObject({ valor_incompativel: 0, participacao: 0, hasData: false })
    expect(wrapper.vm.$.setupState.getScalePiece(Number.NaN, 1))
      .toBe(wrapper.vm.$.setupState.activeScale.at(-1))
  })
})
