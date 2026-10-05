import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { reactive } from 'vue'

import EstablishmentRiskMap from '@/views/components/establishments/EstablishmentRiskMap.vue'

const mocks = vi.hoisted(() => ({
  geoStore: null,
  themeStore: null,
  ensureBrasilUfMap: vi.fn(),
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
      setup(props, { emit }) {
        return () => h('div', { class: 'mock-risk-chart' }, (props.option?.series?.[0]?.data ?? []).map((row, index) =>
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
vi.mock('@/composables/echartsMaps', () => ({ ensureBrasilUfMap: mocks.ensureBrasilUfMap }))
vi.mock('@/composables/useFrozenData', async () => {
  const { ref, watch } = await import('vue')
  return { useFrozenData: (source, loading) => {
    const frozen = ref(source())
    watch([source, loading], ([nextData, isLoading]) => {
      if (!isLoading) frozen.value = nextData
    }, { immediate: true })
    return frozen
  } }
})
vi.mock('@/composables/useStableMapSize', async () => {
  const { ref } = await import('vue')
  return { useStableMapSize: () => ({
    containerWidth: ref(800),
    containerHeight: ref(500),
    hasMeasured: ref(true),
  }) }
})
vi.mock('@/config/chartTheme', async () => {
  const { computed } = await import('vue')
  return { useChartTheme: () => ({ chartTheme: computed(() => ({
    bg: '#fff', tooltip: '#222', tooltipBorder: '#444', tooltipText: '#eee',
  })) }) }
})
vi.mock('@/composables/useFormatting', () => ({ useFormatting: () => ({
  formatNumberFull: (value) => String(value),
  formatPercent: (value) => `${Number(value).toFixed(2)}%`,
  formatTitleCase: (value) => value.toLowerCase().replace(/\b\w/g, (letter) => letter.toUpperCase()),
}) }))
vi.mock('@/views/components/maps/MapBackButton.vue', () => ({
  default: {
    name: 'MapBackButton',
    props: { label: String, tooltip: String },
    emits: ['click'],
    template: '<button data-test="back-button" @click="$emit(\'click\')">{{ label }}</button>',
  },
}))

const feature = (id, name, geometry = { type: 'Polygon', coordinates: [[[-46, -23], [-44, -23], [-44, -22], [-46, -23]]] }) => ({
  type: 'Feature',
  properties: { id, name },
  geometry,
})

const geoJson = {
  type: 'FeatureCollection',
  features: [
    feature(3550308, 'SAO PAULO'),
    feature(3509502, 'CAMPINAS', { type: 'MultiPolygon', coordinates: [[[[-47, -24], [-45, -24], [-45, -22], [-47, -24]]]] }),
    feature(3304557, 'RIO DE JANEIRO'),
  ],
}

const mapData = [
  { uf: 'SP', id_ibge7: 3550308, municipio: 'São Paulo', total_cnpjs: 10, total_critico: 4, pct_critico: 40 },
  { uf: 'SP', id_ibge7: 3509502, municipio: 'Campinas', total_cnpjs: 5, total_critico: 1, pct_critico: 20 },
  { uf: 'RJ', id_ibge7: 3304557, municipio: 'Rio de Janeiro', total_cnpjs: 0, total_critico: 0, pct_critico: 0 },
]

describe('EstablishmentRiskMap', () => {
  let wrappers

  beforeEach(() => {
    wrappers = []
    mocks.ensureBrasilUfMap.mockReset().mockResolvedValue(undefined)
    mocks.registerMap.mockClear()
    mocks.useEcharts.mockClear()
    mocks.geoStore = reactive({
      municipiosGeoJson: geoJson,
      localidades: [
        { sg_uf: 'SP', id_regiao_saude: 10, id_ibge7: 3550308 },
        { sg_uf: 'SP', id_regiao_saude: 10, id_ibge7: 3509502 },
        { sg_uf: 'RJ', id_regiao_saude: 20, id_ibge7: 3304557 },
      ],
      getMunicipiosGeoByUF: vi.fn(() => geoJson),
    })
    mocks.themeStore = reactive({ isDark: true, tokens: { primary: '#123456' } })
  })

  afterEach(() => {
    wrappers.forEach((wrapper) => wrapper.unmount())
    vi.restoreAllMocks()
  })

  function montar(props = {}) {
    const wrapper = mount(EstablishmentRiskMap, {
      props,
      global: { directives: { tooltip() {} } },
    })
    wrappers.push(wrapper)
    return wrapper
  }

  it('carrega o mapa nacional e calcula percentual crítico após agregar UFs', async () => {
    const wrapper = montar({
      mapData,
      kpis: { total_critico: 5, total_atencao: 4, total_normal: 6, total_sem_dados: 1 },
      indicadorLabel: 'Concentração de risco',
    })
    await flushPromises()
    const option = wrapper.getComponent({ name: 'VChart' }).props('option')

    expect(mocks.ensureBrasilUfMap).toHaveBeenCalledOnce()
    expect(option.series[0].map).toBe('brasil-uf')
    expect(option.series[0].data.map(({ name }) => name)).toEqual(['SP', 'RJ'])
    expect(option.series[0].data[0].value).toBeCloseTo(100 / 3, 12)
    expect(option.series[0].data[1].value).toBe(0)
    expect(option.tooltip.formatter({ data: option.series[0].data[0] })).toContain('% Críticas:')
    expect(option.tooltip.formatter({ data: option.series[0].data[1] })).toContain('Sem dados disponíveis')
    expect(option.tooltip.formatter({})).toBe('')
    await wrapper.get('[data-test="map-item-0"]').trigger('click')
    expect(wrapper.emitted('select-uf')).toEqual([['SP']])
    wrapper.getComponent({ name: 'VChart' }).vm.$emit('click', {})
    expect(wrapper.emitted('select-municipio')).toBeUndefined()
    expect(wrapper.text()).toContain('Críticos')
    expect(wrapper.get('.ind-map-card').classes()).not.toContain('is-refreshing')
  })

  it('filtra a região pelo ID, mapeia dados municipais e mantém a seleção destacada', async () => {
    const wrapper = montar({
      activeUf: 'SP',
      selectedRegiao: '10',
      selectedRegiaoNome: 'REGIAO METROPOLITANA',
      selectedMunicipioNome: 'SAO PAULO',
      selectedIbge7: 3550308,
      mapData,
      indicadorLabel: 'Indicador A',
    })
    await flushPromises()
    const option = wrapper.getComponent({ name: 'VChart' }).props('option')

    expect(mocks.registerMap).toHaveBeenCalledWith('regiao-filter-10', {
      type: 'FeatureCollection',
      features: geoJson.features.slice(0, 2),
    })
    expect(option.series[0].map).toBe('regiao-filter-10')
    expect(option.series[0].data.map(({ ibge7 }) => ibge7)).toEqual([3550308, 3509502])
    expect(option.series[0].data[0].itemStyle.borderWidth).toBe(2.5)
    expect(option.series[0].data[1].itemStyle.opacity).toBe(0.8)
    expect(wrapper.get('.map-scope-badge').text()).toContain('Sao Paulo')
  })

  it('aciona drill-down, alterna município selecionado e volta para o escopo adequado', async () => {
    const wrapper = montar({ activeUf: 'SP', mapData })
    await flushPromises()
    await wrapper.get('[data-test="map-item-0"]').trigger('click')
    expect(wrapper.emitted('select-municipio')).toEqual([[3550308, 'São Paulo']])
    await wrapper.get('[data-test="back-button"]').trigger('click')
    expect(wrapper.emitted('clear-geography')).toHaveLength(1)

    await wrapper.setProps({ selectedRegiao: '10', selectedIbge7: 3550308 })
    await wrapper.get('[data-test="back-button"]').trigger('click')
    expect(wrapper.emitted('back-to-uf')).toHaveLength(1)
    await wrapper.get('[data-test="map-item-0"]').trigger('click')
    expect(wrapper.emitted('select-municipio').at(-1)).toEqual([null, 'São Paulo'])
  })

  it('preserva os dados durante carregamento e reflete erros, escopo e zoom', async () => {
    const wrapper = montar({
      activeUf: 'SP',
      mapData,
      kpis: { total_critico: 5, total_atencao: 2, total_normal: 3 },
      selectedRegiaoNome: 'REGIAO METROPOLITANA',
    })
    await flushPromises()
    await wrapper.setProps({ isLoading: true, mapData: [] })
    expect(wrapper.getComponent({ name: 'VChart' }).props('option').series[0].data[0].hasData).toBe(true)
    expect(wrapper.get('.map-scope-badge').text()).toContain('Regiao Metropolitana')

    await wrapper.setProps({ isLoading: false, error: 'Falha ao buscar indicador' })
    expect(wrapper.get('[role="alert"]').text()).toBe('Falha ao buscar indicador')
    expect(wrapper.get('.ind-map-card').classes()).not.toContain('is-refreshing')
    await wrapper.findAll('.zoom-btn')[0].trigger('click')
    expect(wrapper.getComponent({ name: 'VChart' }).props('option').series[0].zoom).toBe(1.5)
    await wrapper.findAll('.zoom-btn')[1].trigger('click')
    expect(wrapper.getComponent({ name: 'VChart' }).props('option').series[0].zoom).toBe(1)
    await wrapper.findAll('.zoom-btn')[0].trigger('click')
    await wrapper.findAll('.zoom-btn')[2].trigger('click')
    expect(wrapper.getComponent({ name: 'VChart' }).props('option').series[0].zoom).toBe(1)
  })

  it('expande o mapa quando a geometria da UF é mais larga que o painel', async () => {
    const wideGeo = {
      type: 'FeatureCollection',
      features: [feature(3550308, 'SAO PAULO', {
        type: 'Polygon',
        coordinates: [[[0, 0], [2, 0], [2, 1], [0, 0]]],
      })],
    }
    mocks.geoStore.getMunicipiosGeoByUF.mockReturnValue(wideGeo)
    const wrapper = montar({ activeUf: 'SP', mapData })
    await flushPromises()

    expect(wrapper.getComponent({ name: 'VChart' }).props('option').series[0].layoutSize).toBe('120%')
  })

  it('usa o tema claro e cobre fallbacks de município, métricas e clique no mapa municipal', async () => {
    mocks.themeStore.isDark = false
    const wrapper = montar({
      activeUf: 'SP',
      mapData: [{ uf: 'SP', id_ibge7: 3550308, municipio: null, total_cnpjs: 1 }],
    })
    await flushPromises()
    const chart = wrapper.getComponent({ name: 'VChart' })
    const option = chart.props('option')
    const saoPaulo = option.series[0].data.find((row) => row.ibge7 === 3550308)
    const campinas = option.series[0].data.find((row) => row.ibge7 === 3509502)

    expect(saoPaulo).toMatchObject({ municipio: 'SAO PAULO', total_critico: 0, value: 0 })
    expect(saoPaulo.itemStyle.areaColor).toBe('#ffedd5')
    expect(campinas.itemStyle.areaColor).toBe('rgba(0,0,0,0.04)')
    expect(option.series[0].itemStyle.borderColor).toBe('rgba(0,0,0,0.15)')
    expect(option.tooltip.formatter({ data: {
      name: null, municipio: null, hasData: true, total_cnpjs: 1, total_critico: null, value: null,
    } })).toContain('—')
    expect(option.tooltip.formatter({ data: {
      name: 'Cidade', municipio: null, hasData: true, total_cnpjs: 1, total_critico: null, value: 15,
    } })).toContain('0 <small')

    chart.vm.$emit('click', { data: { ibge7: null, name: 'Sem código' } })
    expect(wrapper.emitted('select-municipio')).toBeUndefined()
    chart.vm.$emit('click', { data: { ibge7: 3550308, municipio: null, name: 'Cidade pelo nome' } })
    chart.vm.$emit('click', { data: { ibge7: 3550308, municipio: null, name: null } })
    expect(wrapper.emitted('select-municipio')).toEqual([
      [3550308, 'Cidade pelo nome'],
      [3550308, null],
    ])
  })

  it('lida com GeoJSON municipal vazio e com geometria sem coordenadas', async () => {
    const emptyGeo = { type: 'FeatureCollection', features: [] }
    mocks.geoStore.getMunicipiosGeoByUF.mockReturnValue(emptyGeo)
    const emptyWrapper = montar({ activeUf: 'SP', mapData: [] })
    await flushPromises()

    expect(emptyWrapper.getComponent({ name: 'VChart' }).props('option').series[0].data).toEqual([])
    expect(emptyWrapper.vm.$.setupState.geoAspectRatio).toBe(1.5)

    const noCoordinatesGeo = {
      type: 'FeatureCollection',
      features: [{ ...feature(3550308, 'SAO PAULO'), geometry: { type: 'Polygon' } }],
    }
    mocks.geoStore.getMunicipiosGeoByUF.mockReturnValue(noCoordinatesGeo)
    const noCoordinatesWrapper = montar({ activeUf: 'SP', mapData: [] })
    await flushPromises()
    expect(noCoordinatesWrapper.vm.$.setupState.geoAspectRatio).toBe(1.5)
  })

  it('não registra de novo um mesmo mapa e ignora uma região sem GeoJSON', async () => {
    const wrapper = montar({ activeUf: 'SP', mapData })
    await flushPromises()
    const callsBeforeRefresh = mocks.registerMap.mock.calls.filter(([name]) => name === 'municipios-SP').length
    mocks.geoStore.municipiosGeoJson = { ...geoJson }
    await wrapper.vm.$nextTick()
    await flushPromises()
    expect(mocks.registerMap.mock.calls.filter(([name]) => name === 'municipios-SP').length)
      .toBe(callsBeforeRefresh + 1)

    mocks.geoStore.getMunicipiosGeoByUF.mockReturnValue(null)
    const withoutRegionGeo = montar({ activeUf: 'SP', selectedRegiao: '10', mapData })
    await flushPromises()
    expect(withoutRegionGeo.vm.$.setupState.echartsMapData).toEqual([])
  })

  it('trata linhas sem UF, regiões sem geometrias e valores sem faixa de risco', async () => {
    const wrapper = montar({ mapData: [{ uf: null, total_cnpjs: null, total_critico: null }] })
    await flushPromises()
    expect(wrapper.getComponent({ name: 'VChart' }).props('option').series[0].data).toEqual([])
    expect(wrapper.vm.$.setupState.getRiskPiece(Number.NaN)).toBe(wrapper.vm.$.setupState.activeScale.at(-1))

    const local = montar({ activeUf: 'SP', selectedRegiao: '999', mapData })
    await flushPromises()
    expect(local.vm.$.setupState.echartsMapData).toEqual([])
    expect(mocks.registerMap).not.toHaveBeenCalledWith('regiao-filter-999', expect.anything())

    const tooltip = wrapper.vm.$.setupState.buildChartOption().tooltip.formatter({
      data: { name: null, municipio: null, hasData: true, total_cnpjs: null, total_critico: null, value: null },
    })
    expect(tooltip).toContain('—')
  })
})
