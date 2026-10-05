import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { reactive } from 'vue'

import MunicipalRiskMap from '@/views/components/municipios/MunicipalRiskMap.vue'

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
        return () => h('div', { class: 'mock-map-chart' }, props.option.series[0].data.map((row, index) =>
          h('button', {
            key: `${row.name}-${index}`,
            'data-test': `map-item-${index}`,
            onClick: () => emit('click', { data: row }),
          }, row.name),
        ).concat([
          h('button', { 'data-test': 'empty-map-click', onClick: () => emit('click', {}) }, 'Sem item'),
        ]))
      },
    },
  }
})
vi.mock('@/stores/geo', () => ({ useGeoStore: () => mocks.geoStore }))
vi.mock('@/stores/theme', () => ({ useThemeStore: () => mocks.themeStore }))
vi.mock('@/composables/echartsMaps', () => ({ ensureBrasilUfMap: mocks.ensureBrasilUfMap }))
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
  formatBRL: (value) => `R$ ${value}`,
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

const feature = (id, name) => ({
  type: 'Feature',
  properties: { id, name },
  geometry: { type: 'Polygon', coordinates: [[[0, 0], [2, 0], [2, 1], [0, 0]]] },
})

const municipiosGeo = {
  type: 'FeatureCollection',
  features: [feature(3550308, 'SAO PAULO'), feature(3509502, 'CAMPINAS'), feature(3304557, 'RIO DE JANEIRO')],
}

const localidades = [
  { sg_uf: 'SP', id_regiao_saude: 10, id_ibge7: 3550308 },
  { sg_uf: 'SP', id_regiao_saude: 10, id_ibge7: 3509502 },
  { sg_uf: 'SP', id_regiao_saude: 20, id_ibge7: 3550308 },
  { sg_uf: 'RJ', id_regiao_saude: 10, id_ibge7: 3304557 },
]

describe('MunicipalRiskMap', () => {
  let wrappers

  beforeEach(() => {
    wrappers = []
    mocks.ensureBrasilUfMap.mockReset().mockResolvedValue(undefined)
    mocks.registerMap.mockClear()
    mocks.useEcharts.mockClear()
    mocks.geoStore = reactive({
      localidades,
      getMunicipiosGeoByUF: vi.fn(() => municipiosGeo),
    })
    mocks.themeStore = reactive({
      isDark: true,
      tokens: { primary: '#123456' },
    })
  })

  afterEach(() => {
    wrappers.forEach((wrapper) => wrapper.unmount())
    vi.restoreAllMocks()
  })

  function montar(props = {}) {
    const wrapper = mount(MunicipalRiskMap, {
      props,
      global: { directives: { tooltip() {} } },
    })
    wrappers.push(wrapper)
    return wrapper
  }

  const auditRows = [
    { uf: 'SP', id_ibge7: 3550308, municipio: 'Sao Paulo', cnpjs: 10, total_critico: 4, valSemComp: 250, totalMov: 1000 },
    { uf: 'SP', id_ibge7: 3509502, municipio: 'Campinas', cnpjs: 5, total_critico: 1, valSemComp: 100, totalMov: 1000 },
    { uf: 'RJ', id_ibge7: 3304557, municipio: 'Rio de Janeiro', cnpjs: 0, total_critico: 0, valSemComp: 0, totalMov: 0 },
  ]

  it('carrega o mapa nacional, agrega por UF e calcula totais e percentuais de auditoria', async () => {
    const wrapper = montar({ mapData: auditRows, isLoading: true })
    await flushPromises()

    const chart = wrapper.getComponent({ name: 'VChart' })
    const option = chart.props('option')
    expect(mocks.ensureBrasilUfMap).toHaveBeenCalledOnce()
    expect(option.series[0].map).toBe('brasil-uf')
    expect(option.series[0].data.map(({ name }) => name)).toEqual(['SP', 'RJ'])
    expect(option.series[0].data[0].value).toBe(17.5)
    expect(option.series[0].data[0].municipios).toBe(2)
    expect(option.series[0].data[1].hasData).toBe(false)
    expect(wrapper.text()).toContain('17.50%')
    expect(wrapper.get('.municipal-map-card').classes()).toContain('is-refreshing')
  })

  it('abre a UF selecionada e ignora itens sem dados ou sem identificador', async () => {
    const wrapper = montar({ mapData: auditRows })
    await flushPromises()
    await wrapper.get('[data-test="map-item-0"]').trigger('click')
    expect(wrapper.emitted('select-uf')).toEqual([['SP']])

    await wrapper.setProps({ activeUf: 'SP' })
    await wrapper.get('[data-test="map-item-2"]').trigger('click')
    expect(wrapper.emitted('select-municipio')).toBeUndefined()
  })

  it('filtra geometrias da região por UF e id_regiao_saude e calcula indicador crítico por município', async () => {
    const wrapper = montar({
      activeUf: 'SP',
      selectedRegiao: '10',
      selectedRegiaoNome: 'REGIAO METROPOLITANA',
      metricMode: 'indicator',
      metricLabel: 'Indicador crítico',
      mapData: auditRows,
      kpis: { total_atencao: 2, total_critico: 5, total_normal: 3 },
    })
    await flushPromises()

    const option = wrapper.getComponent({ name: 'VChart' }).props('option')
    expect(mocks.geoStore.getMunicipiosGeoByUF).toHaveBeenCalledWith('SP')
    expect(mocks.registerMap).toHaveBeenCalledWith('municipios-risk-regiao-SP-10', {
      type: 'FeatureCollection',
      features: municipiosGeo.features.slice(0, 2),
    })
    expect(option.series[0].data.map(({ ibge7 }) => ibge7)).toEqual([3550308, 3509502])
    expect(option.series[0].data.map(({ value }) => value)).toEqual([40, 20])
    expect(wrapper.get('.map-scope-badge').text()).toContain('Regiao Metropolitana')
    expect(wrapper.get('.map-legend').text()).toContain('% farmácias críticas')
    expect(wrapper.text()).toContain('Críticos')
    expect(wrapper.text()).toContain('Atenção')
  })

  it('mostra o recorte municipal, volta ao nível correto e alterna seleção do município', async () => {
    const wrapper = montar({
      activeUf: 'SP',
      selectedRegiao: '10',
      selectedMunicipioNome: 'SAO PAULO',
      selectedIbge7: 3550308,
      mapData: auditRows,
    })
    await flushPromises()
    expect(wrapper.get('.map-scope-badge').text()).toContain('Sao Paulo')
    expect(wrapper.get('[data-test="back-button"]').text()).toBe('SP')
    expect(wrapper.getComponent({ name: 'VChart' }).props('option').series[0].data[0].itemStyle.borderWidth).toBe(2.5)

    await wrapper.get('[data-test="back-button"]').trigger('click')
    expect(wrapper.emitted('back-to-uf')).toHaveLength(1)
    await wrapper.get('[data-test="map-item-0"]').trigger('click')
    expect(wrapper.emitted('select-municipio')).toEqual([[null]])
  })

  it('formata tooltips de auditoria, indicadores e municípios sem estabelecimentos', async () => {
    const wrapper = montar({ mapData: auditRows })
    await flushPromises()
    let option = wrapper.getComponent({ name: 'VChart' }).props('option')
    expect(option.tooltip.formatter({ data: option.series[0].data[0] })).toContain('% sem comprovação')
    expect(option.tooltip.formatter({ data: option.series[0].data[1] })).toContain('Sem estabelecimentos')
    expect(option.tooltip.formatter({})).toBe('')

    await wrapper.setProps({ activeUf: 'SP', metricMode: 'indicator' })
    option = wrapper.getComponent({ name: 'VChart' }).props('option')
    const tooltip = option.tooltip.formatter({ data: option.series[0].data[0] })
    expect(tooltip).toContain('% críticas')
    expect(tooltip).toContain('Críticas')
  })

  it('aplica zoom com limites e permite reiniciar o nível', async () => {
    const wrapper = montar({ mapData: auditRows })
    await flushPromises()
    const option = () => wrapper.getComponent({ name: 'VChart' }).props('option')

    await wrapper.findAll('.zoom-btn')[1].trigger('click')
    expect(option().series[0].zoom).toBe(1)
    await wrapper.findAll('.zoom-btn')[0].trigger('click')
    expect(option().series[0].zoom).toBe(1.5)
    await wrapper.findAll('.zoom-btn')[2].trigger('click')
    expect(option().series[0].zoom).toBe(1)
  })

  it('exibe erro e emite limpeza da geografia ao voltar do mapa estadual', async () => {
    const wrapper = montar({ activeUf: 'SP', error: 'Falha ao carregar mapa', mapData: auditRows })
    await flushPromises()
    expect(wrapper.get('[role="alert"]').text()).toBe('Falha ao carregar mapa')
    expect(wrapper.get('[data-test="back-button"]').text()).toBe('Brasil')
    await wrapper.get('[data-test="back-button"]').trigger('click')
    expect(wrapper.emitted('clear-geography')).toHaveLength(1)
  })

  it('usa snapshots na seleção municipal, campos alternativos e tema claro', async () => {
    const geo = {
      type: 'FeatureCollection',
      features: [
        {
          ...feature(3550308, 'SAO PAULO'),
          geometry: { type: 'MultiPolygon', coordinates: [[[[0, 0], [4, 0], [4, 2], [0, 0]]]] },
        },
        {
          ...feature(0, 'MUNICIPIO ZERO'),
          geometry: { type: 'Polygon', coordinates: [[[0, 2], [1, 2], [2, 2], [0, 2]]] },
        },
        {
          ...feature(9999999, 'SEM DADOS'),
          geometry: { type: 'Polygon', coordinates: null },
        },
      ],
    }
    mocks.geoStore.getMunicipiosGeoByUF.mockReturnValue(geo)
    mocks.themeStore.isDark = false
    const mapData = [
      {
        uf: 'SP', id_ibge7: 3550308, total_cnpjs: 4, total_critico: 3,
        pct_critico: 75, percValSemComp: 30, valSemComp: 30, totalMov: 100,
      },
      { uf: 'SP', id_ibge7: 0, cnpjs: 2, total_critico: 1, valSemComp: 25, totalMov: 50 },
      { id_ibge7: null },
    ]
    const wrapper = montar({ activeUf: 'SP', metricMode: 'indicator', mapData })
    await flushPromises()

    const option = () => wrapper.getComponent({ name: 'VChart' }).props('option')
    expect(option().series[0].data.map(({ value }) => value)).toEqual([75, 50, null])
    expect(option().series[0].data[0].municipio).toBe('SAO PAULO')
    expect(option().series[0].data[2].itemStyle.areaColor).toBe('rgba(0,0,0,0.04)')
    expect(option().series[0].layoutSize).toBe('120%')
    expect(option().tooltip.formatter({ data: option().series[0].data[0] })).toContain('Críticas')

    await wrapper.get('[data-test="map-item-0"]').trigger('click')
    expect(wrapper.emitted('select-municipio')).toEqual([[3550308]])
    await wrapper.setProps({ selectedIbge7: 3550308 })
    expect(option().series[0].data[1].itemStyle.opacity).toBe(0.72)
    expect(option().series[0].data[0].itemStyle.borderColor).toBe('#123456')

    await wrapper.setProps({ metricMode: 'audit' })
    expect(option().series[0].data[0].value).toBe(30)
    await wrapper.get('[data-test="map-item-1"]').trigger('click')
    await wrapper.get('[data-test="map-item-2"]').trigger('click')
    await wrapper.get('[data-test="empty-map-click"]').trigger('click')
    expect(wrapper.emitted('select-municipio')).toHaveLength(1)

    await wrapper.setProps({ selectedIbge7: null })
    expect(option().series[0].data[1].itemStyle.opacity).toBe(1)
  })

  it('usa a proporção padrão quando a UF não tem GeoJSON e trata geometrias planas', async () => {
    mocks.geoStore.getMunicipiosGeoByUF.mockReturnValue(null)
    const semGeo = montar({ activeUf: 'SP' })
    await flushPromises()
    expect(semGeo.getComponent({ name: 'VChart' }).props('option').series[0].data).toEqual([])

    mocks.geoStore.getMunicipiosGeoByUF.mockReturnValue({
      type: 'FeatureCollection',
      features: [{
        ...feature(3550308, 'SAO PAULO'),
        geometry: { type: 'Polygon', coordinates: [[[0, 2], [1, 2], [2, 2], [0, 2]]] },
      }],
    })
    const plana = montar({ activeUf: 'SP', mapData: auditRows.slice(0, 1) })
    await flushPromises()
    expect(plana.getComponent({ name: 'VChart' }).props('option').series[0].layoutSize).toBe('97%')
  })

  it('ignora linhas sem UF e usa os campos alternativos ou valores padrão das métricas', async () => {
    const wrapper = montar({
      mapData: [
        { uf: null, total_cnpjs: 50, total_critico: 10, valSemComp: 100, totalMov: 200 },
        { uf: 'SP', id_ibge7: 3550308, total_cnpjs: 2 },
      ],
    })
    await flushPromises()

    const chart = wrapper.getComponent({ name: 'VChart' })
    const option = chart.props('option')
    expect(option.series[0].data.map(({ name }) => name)).toEqual(['SP'])
    expect(option.tooltip.formatter({ data: {
      name: 'SP', hasData: true, value: null, criticos: null,
      valSemComp: null, cnpjs: null,
    } })).toContain('0.00%')
    expect(wrapper.vm.$.setupState.getRiskPiece(Number.NaN)).toEqual(
      wrapper.vm.$.setupState.activeScale.at(-1),
    )

    chart.vm.$emit('click', { data: { name: null } })
    expect(wrapper.emitted('select-uf')).toBeUndefined()

    const local = montar({
      activeUf: 'SP',
      mapData: [{ uf: 'SP', id_ibge7: 3550308, total_cnpjs: 2 }],
    })
    await flushPromises()
    expect(local.getComponent({ name: 'VChart' }).props('option').series[0].data[0])
      .toMatchObject({ municipio: 'SAO PAULO', cnpjs: 2, criticos: 0, valSemComp: 0, totalMov: 0 })
  })

  it('trata campos municipais ausentes no agregado e no tooltip de indicador', async () => {
    const wrapper = montar({
      activeUf: 'SP',
      metricMode: 'indicator',
      mapData: [{ uf: 'SP', id_ibge7: 3550308, total_critico: 0, valSemComp: 0, totalMov: 0 }],
    })
    await flushPromises()

    const option = wrapper.getComponent({ name: 'VChart' }).props('option')
    expect(option.tooltip.formatter({ data: {
      name: 'Rótulo alternativo', municipio: null, hasData: true, value: null,
      criticos: null, valSemComp: null, cnpjs: null,
    } })).toContain('Rótulo alternativo')
    expect(option.tooltip.formatter({ data: {
      name: 'Rótulo alternativo', municipio: null, hasData: true, value: null,
      criticos: null, valSemComp: null, cnpjs: null,
    } })).toContain('0')
    expect(wrapper.vm.$.setupState.dataByUf.get('SP').cnpjs).toBe(0)
  })
})
