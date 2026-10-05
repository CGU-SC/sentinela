import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { reactive } from 'vue'
import { createPinia, disposePinia, setActivePinia } from 'pinia'

import CrmPrescricoesMap from '@/views/components/analises/CrmPrescricoesMap.vue'
import { CRM_FAIXAS } from '@/config/crmFiltrosMedico'
import { useCrmFiltrosMedicoStore } from '@/stores/crmFiltrosMedico'

const mocks = vi.hoisted(() => ({
  useEcharts: vi.fn(),
  registerMap: vi.fn(),
  ensureBrasilUfMap: vi.fn(),
  geoStore: null,
  themeStore: null,
}))
const tooltipBindings = []

vi.mock('echarts/core', () => ({ use: mocks.useEcharts, registerMap: mocks.registerMap }))
vi.mock('echarts/renderers', () => ({ CanvasRenderer: {} }))
vi.mock('echarts/charts', () => ({ MapChart: {} }))
vi.mock('echarts/components', () => ({ TooltipComponent: {}, VisualMapComponent: {} }))
vi.mock('vue-echarts', async () => {
  const { h } = await import('vue')
  return {
    default: {
      name: 'VChart',
      props: ['option'],
      emits: ['click'],
      setup(props, { expose, emit }) {
        expose({ chart: { resize: vi.fn() } })
        return () => h('div', { class: 'mock-chart' }, [
          h('output', { 'data-test': 'chart-map-name' }, props.option.series?.[0]?.map ?? ''),
          h('output', { 'data-test': 'chart-zoom' }, String(props.option.series?.[0]?.zoom ?? '')),
          h('button', {
            'data-test': 'chart-click-first',
            onClick: () => emit('click', { data: props.option.series?.[0]?.data?.[0] }),
          }, 'Selecionar território'),
          h('button', {
            'data-test': 'chart-click-second',
            onClick: () => emit('click', { data: props.option.series?.[0]?.data?.[1] }),
          }, 'Selecionar segundo território'),
        ])
      },
    },
  }
})
vi.mock('@/composables/echartsMaps', () => ({ ensureBrasilUfMap: mocks.ensureBrasilUfMap }))
vi.mock('@/composables/useStableMapSize', async () => {
  const { ref } = await import('vue')
  return { useStableMapSize: () => ({ containerWidth: ref(1000), containerHeight: ref(600), hasMeasured: ref(true) }) }
})
vi.mock('@/stores/geo', () => ({ useGeoStore: () => mocks.geoStore }))
vi.mock('@/stores/theme', () => ({ useThemeStore: () => mocks.themeStore }))

const feature = (id, name, coordinates = [[[0, 0], [2, 0], [2, 1], [0, 0]]]) => ({
  type: 'Feature',
  properties: { id: String(id), name },
  geometry: { type: 'Polygon', coordinates },
})

const nationalRows = [
  { nome: 'DF & <Central>', uf: 'DF', qtd_medicos_ativos: 100, qtd_medicos_alta_intensidade: 12, percentual_alta_intensidade: 12, indice_brasil: 1.4, nivel: 'uf' },
  { nome: 'Sem médicos', uf: 'AC', qtd_medicos_ativos: 0, qtd_medicos_alta_intensidade: 0, percentual_alta_intensidade: 0, indice_brasil: null, nivel: 'uf' },
  { nome: 'Amostra pequena', uf: 'AP', qtd_medicos_ativos: 4, qtd_medicos_alta_intensidade: 1, percentual_alta_intensidade: 25, indice_brasil: 2, amostra_pequena: true, nivel: 'uf' },
]

const regionRows = [
  { nome: 'Lages', uf: 'SC', id_ibge7: 4207205, id_regiao_saude: 77, qtd_medicos_ativos: 30, qtd_medicos_alta_intensidade: 5, percentual_alta_intensidade: 16.7, percentual_referencia_regiao: 4, percentual_referencia_uf: 5, percentual_referencia_brasil: 3, indice_regiao: 1.7, nivel: 'municipio' },
  { nome: 'Painel', uf: 'SC', id_ibge7: 4207207, id_regiao_saude: 77, qtd_medicos_ativos: 5, qtd_medicos_alta_intensidade: 1, percentual_alta_intensidade: 20, percentual_referencia_regiao: 4, indice_regiao: 2, amostra_pequena: true, nivel: 'municipio' },
]

describe('CrmPrescricoesMap', () => {
  let pinia
  let wrappers

  beforeEach(() => {
    wrappers = []
    tooltipBindings.length = 0
    mocks.useEcharts.mockClear()
    mocks.registerMap.mockClear()
    mocks.ensureBrasilUfMap.mockReset().mockResolvedValue(undefined)
    mocks.geoStore = reactive({
      localidades: [
        { id_ibge7: 4207205, id_regiao_saude: 77, no_regiao_saude: 'REGIÃO SERRANA' },
        { id_ibge7: 4207207, id_regiao_saude: 77, no_regiao_saude: 'REGIÃO SERRANA' },
        { id_ibge7: 4207304, id_regiao_saude: 78, no_regiao_saude: 'REGIÃO OESTE' },
      ],
      municipiosGeoJson: { type: 'FeatureCollection', features: [feature(4207205, 'Lages'), feature(4207207, 'Painel'), feature(4207304, 'Chapecó')] },
      getMunicipiosGeoByUF: vi.fn((uf) => (uf === 'SC'
        ? { type: 'FeatureCollection', features: [feature(4207205, 'Lages'), feature(4207207, 'Painel'), feature(4207304, 'Chapecó')] }
        : null)),
      getRegiaoNomeById: vi.fn((id) => ({ 77: 'REGIÃO SERRANA', 78: 'REGIÃO OESTE' })[id]),
    })
    mocks.themeStore = reactive({
      isDark: true,
      currentPalette: 'carbon',
      tokens: { primary: '#123456', textColor: '#eeeeee', mutedColor: '#aaaaaa', borderColor: '#333333' },
    })
    pinia = createPinia()
    setActivePinia(pinia)
  })

  afterEach(() => {
    wrappers.forEach((wrapper) => wrapper.unmount())
    disposePinia(pinia)
    vi.restoreAllMocks()
  })

  function montar(props = {}) {
    const wrapper = mount(CrmPrescricoesMap, {
      props: { mapLevel: 'uf', mapData: nationalRows, mapMeta: { map_level: 'uf', percentual_referencia_brasil: 7.5, min_medicos_amostra_municipio: 10 }, qtdMedicos: 100, ...props },
      global: { plugins: [pinia], directives: { tooltip: { mounted: (_element, binding) => tooltipBindings.push(binding.value) } } },
    })
    wrappers.push(wrapper)
    return wrapper
  }

  it('registra o mapa nacional e monta resumo, legenda e séries para UF vazia e amostra pequena', async () => {
    const wrapper = montar({ mapMeta: { map_level: 'uf', percentual_referencia_brasil: 7.5, min_medicos_amostra_municipio: 10, filtro_farmacias_ativo: true } })
    await flushPromises()

    expect(mocks.ensureBrasilUfMap).toHaveBeenCalledOnce()
    expect(wrapper.text()).toContain('Brasil · comparado à média das UFs · farmácias filtradas')
    expect(wrapper.text()).toContain('Média das UFs')
    expect(wrapper.text()).toContain('7,5%')
    expect(wrapper.find('.map-legend').exists()).toBe(true)
    expect(wrapper.text()).toContain('Amostra pequena (< 10)')
    expect(JSON.stringify(tooltipBindings)).toContain('Farmácias filtradas')

    const option = wrapper.findComponent({ name: 'VChart' }).props('option')
    expect(option.series[0].map).toBe('brasil-uf')
    expect(option.series[0].data.map((item) => item.value)).toEqual([1.4, null, null])
    expect(option.series[0].data[2].itemStyle.areaColor).not.toBe(option.series[0].data[0].itemStyle.areaColor)
  })

  it('emite seleção de UF, mostra tooltip escapado e controla zoom dentro dos limites', async () => {
    const wrapper = montar()
    await flushPromises()

    const option = wrapper.findComponent({ name: 'VChart' }).props('option')
    const tooltip = option.tooltip.formatter({ data: option.series[0].data[0], name: 'ignorado' })
    expect(tooltip).toContain('DF &amp; &lt;Central&gt;')
    expect(option.tooltip.formatter({ name: '<Sem dados>' })).toContain('&lt;Sem dados&gt;')

    await wrapper.get('[data-test="chart-click-first"]').trigger('click')
    expect(wrapper.emitted('select-uf')).toEqual([['DF']])

    const [increaseZoom, decreaseZoom, resetZoom] = wrapper.findAll('.map-controls .zoom-btn')
    expect(wrapper.get('[data-test="chart-zoom"]').text()).toBe('1')
    await increaseZoom.trigger('click')
    expect(wrapper.get('[data-test="chart-zoom"]').text()).toBe('1.5')
    await decreaseZoom.trigger('click')
    expect(wrapper.get('[data-test="chart-zoom"]').text()).toBe('1')
    await decreaseZoom.trigger('click')
    expect(wrapper.get('[data-test="chart-zoom"]').text()).toBe('1')
    await increaseZoom.trigger('click')
    await increaseZoom.trigger('click')
    await increaseZoom.trigger('click')
    await resetZoom.trigger('click')
    expect(wrapper.get('[data-test="chart-zoom"]').text()).toBe('1')
  })

  it('filtra o GeoJSON da região por id_regiao_saude e destaca a localidade selecionada', async () => {
    const wrapper = montar({
      mapLevel: 'regiao',
      uf: 'SC',
      regiaoId: 77,
      selectedIbge7: '4207205',
      selectedMunicipioNome: 'LAGES',
      selectedRegiaoNome: 'REGIÃO SERRANA',
      mapData: regionRows,
      mapMeta: { map_level: 'regiao', percentual_referencia_regiao: 4, percentual_referencia_brasil: 3, min_medicos_amostra_municipio: 10 },
    })
    await flushPromises()

    expect(mocks.geoStore.getMunicipiosGeoByUF).toHaveBeenCalledWith('SC')
    expect(mocks.registerMap).toHaveBeenCalledWith('regiao-filter-77', expect.objectContaining({ features: expect.any(Array) }))
    const option = wrapper.findComponent({ name: 'VChart' }).props('option')
    expect(option.series[0].map).toBe('regiao-filter-77')
    expect(option.series[0].data).toHaveLength(2)
    expect(option.series[0].data[0].itemStyle.borderWidth).toBe(2.5)
    expect(option.series[0].data[1].itemStyle.decal).toEqual(expect.objectContaining({ symbol: 'rect' }))
    expect(wrapper.text()).toContain('Região Serrana')
    expect(wrapper.text()).toContain('Lages')
    expect(wrapper.get('.map-summary-item--accent').text()).toContain('Média da região4,0%')
    expect(wrapper.get('.map-back-button').text()).toContain('Voltar à UF SC')
  })

  it('formata tooltip municipal com referência regional, UF, Brasil e amostra pequena', async () => {
    const wrapper = montar({
      mapLevel: 'regiao', uf: 'SC', regiaoId: 77, mapData: regionRows,
      mapMeta: { map_level: 'regiao', percentual_referencia_regiao: 4, percentual_referencia_uf: 5, percentual_referencia_brasil: 3, min_medicos_amostra_municipio: 10 },
    })
    await flushPromises()
    const formatter = wrapper.findComponent({ name: 'VChart' }).props('option').tooltip.formatter

    const tooltip = formatter({ data: wrapper.findComponent({ name: 'VChart' }).props('option').series[0].data[0], name: 'Lages' })
    expect(tooltip).toContain('Região de Saúde · Região Serrana')
    expect(tooltip).toContain('Média regional')
    expect(tooltip).toContain('UF SC')
    expect(tooltip).toContain('Brasil')
    const small = formatter({ data: wrapper.findComponent({ name: 'VChart' }).props('option').series[0].data[1], name: 'Painel' })
    expect(small).toContain('Amostra pequena: menos de 10 médicos')
  })

  it('inclui o recorte dos filtros de produção e explica a divergência no município selecionado', async () => {
    const store = useCrmFiltrosMedicoStore()
    const tipoProducao = Object.entries(CRM_FAIXAS).find(([, config]) => config.grupo === 'producao')[0]
    store.setFaixa(tipoProducao, { min: 0, max: null })
    const wrapper = montar({
      mapLevel: 'regiao', uf: 'SC', regiaoId: 77, selectedIbge7: 4207205, selectedMunicipioNome: 'LAGES', selectedRegiaoNome: 'REGIÃO SERRANA',
      mapData: regionRows,
      mapMeta: { map_level: 'regiao', percentual_referencia_regiao: 4, min_medicos_amostra_municipio: 10 },
    })
    await flushPromises()

    expect(wrapper.text()).toContain('taxa/prescrições avaliadas na Região de Saúde Região Serrana inteira')
    expect(JSON.stringify(tooltipBindings)).toContain('Taxa diária e total de prescrições')
    expect(JSON.stringify(tooltipBindings)).toContain('ranking usa os números do médico em Lages')
  })

  it('alterna seleção municipal, volta ao escopo anterior e atualiza o mapa quando o tema muda', async () => {
    const wrapper = montar({
      mapLevel: 'municipio', uf: 'SC', mapData: [regionRows[0]],
      mapMeta: { map_level: 'municipio', min_medicos_amostra_municipio: 10 },
    })
    await flushPromises()
    const option = wrapper.findComponent({ name: 'VChart' }).props('option')
    expect(option.series[0].map).toBe('municipios-SC')

    await wrapper.get('[data-test="chart-click-first"]').trigger('click')
    expect(wrapper.emitted('select-municipio')).toEqual([[4207205]])
    await wrapper.setProps({ selectedIbge7: 4207205 })
    await wrapper.get('[data-test="chart-click-first"]').trigger('click')
    expect(wrapper.emitted('select-municipio')).toEqual([[4207205], [null]])

    await wrapper.get('.map-back-button').trigger('click')
    expect(wrapper.emitted('back')).toHaveLength(1)
    const colorsBefore = wrapper.findComponent({ name: 'VChart' }).props('option').visualMap.pieces
    mocks.themeStore.isDark = false
    await wrapper.vm.$nextTick()
    await flushPromises()
    expect(wrapper.findComponent({ name: 'VChart' }).props('option').visualMap.pieces).not.toEqual(colorsBefore)
  })

  it('mostra a mensagem de erro da API em vez de deixar o gráfico aparente', async () => {
    const wrapper = montar({ error: 'Dados indisponíveis', isLoading: false })
    await flushPromises()

    expect(wrapper.text()).toContain('Mapa indisponível no momento')
    expect(wrapper.text()).toContain('Dados indisponíveis')
    expect(wrapper.findComponent({ name: 'VChart' }).exists()).toBe(false)
  })

  it('ignora o registro quando o GeoJSON do escopo ainda não existe', async () => {
    const wrapper = montar({ mapLevel: 'municipio', uf: 'XX', mapData: [] })
    await flushPromises()

    expect(mocks.geoStore.getMunicipiosGeoByUF).toHaveBeenCalledWith('XX')
    expect(mocks.registerMap).not.toHaveBeenCalled()

    const withoutUf = montar({ mapLevel: 'municipio', uf: null, mapData: [] })
    await flushPromises()
    expect(withoutUf.vm.$.setupState.currentGeo).toBeNull()
  })

  it('mantém a tela montada quando o carregamento do mapa nacional falha', async () => {
    mocks.ensureBrasilUfMap.mockRejectedValueOnce(new Error('GeoJSON indisponível'))
    const log = vi.spyOn(console, 'error').mockImplementation(() => {})
    const wrapper = montar()
    await flushPromises()

    expect(log).toHaveBeenCalledWith('[CRM map] GeoJSON indisponível:', expect.any(Error))
    expect(wrapper.exists()).toBe(true)
  })

  it('classifica todos os intervalos do índice e formata valores ausentes no tooltip', async () => {
    const indices = [0.2, 0.6, 1, 1.3, 1.7, 2.5, 3.5]
    const rows = indices.map((indice, index) => ({
      nome: `UF ${index}`,
      uf: `U${index}`,
      qtd_medicos_ativos: 10,
      qtd_medicos_alta_intensidade: 1,
      indice_brasil: indice,
      nivel: 'uf',
    }))
    const wrapper = montar({ mapData: rows, mapMeta: null })
    await flushPromises()

    const seriesData = wrapper.vm.$.setupState.mapSeriesData
    expect(seriesData).toHaveLength(indices.length)
    expect(new Set(seriesData.map((item) => item.itemStyle.areaColor)).size).toBeGreaterThan(1)
    const option = wrapper.vm.$.setupState.buildChartOption()
    const missingValues = option.tooltip.formatter({ data: {
      row: {
        nome: null,
        nivel: 'uf',
        qtd_medicos_ativos: 0,
        qtd_medicos_alta_intensidade: 0,
        percentual_alta_intensidade: null,
        indice_brasil: null,
      },
      name: null,
    } })

    expect(missingValues).toContain('—')
    expect(wrapper.vm.$.setupState.referenciaResumo).toEqual({ label: 'Média das UFs', valor: '—' })
  })

  it('valida o contrato regional no tooltip e deixa a série vazia sem GeoJSON', async () => {
    const regional = montar({
      mapLevel: 'regiao',
      uf: 'SC',
      regiaoId: 77,
      mapData: [regionRows[0]],
      mapMeta: { map_level: 'regiao' },
    })
    await flushPromises()
    const formatter = regional.findComponent({ name: 'VChart' }).props('option').tooltip.formatter

    expect(() => formatter({ data: { row: { ...regionRows[0], id_regiao_saude: null } } }))
      .toThrow('Municipio do mapa sem id_regiao_saude.')
    mocks.geoStore.getRegiaoNomeById.mockReturnValue(null)
    expect(() => formatter({ data: { row: regionRows[0] } }))
      .toThrow('Regiao de saude do mapa sem nome no contrato de localidades.')

    const withoutGeo = montar({
      mapLevel: 'municipio',
      uf: 'XX',
      mapData: [],
      mapMeta: { map_level: 'municipio' },
    })
    await flushPromises()
    expect(withoutGeo.vm.$.setupState.currentGeo).toBeNull()
    expect(withoutGeo.vm.$.setupState.mapSeriesData).toEqual([])
  })

  it('explica filtros de produção sem município selecionado e cobre limites da escala', async () => {
    const store = useCrmFiltrosMedicoStore()
    const tipoProducao = Object.entries(CRM_FAIXAS).find(([, config]) => config.grupo === 'producao')[0]
    store.setFaixa(tipoProducao, { min: 0, max: null })
    const wrapper = montar({
      mapLevel: 'regiao',
      uf: 'SC',
      regiaoId: 77,
      mapData: [
        { ...regionRows[0], indice_regiao: null },
        { ...regionRows[1], indice_regiao: 2 },
      ],
      selectedRegiaoNome: null,
      mapMeta: { map_level: 'regiao', min_medicos_amostra_municipio: 10 },
    })
    await flushPromises()

    expect(wrapper.text()).toContain('na Região de Saúde inteira')
    expect(JSON.stringify(tooltipBindings)).not.toContain('O ranking usa os números do médico em')
    expect(wrapper.vm.$.setupState.getRiskPiece(Number.NaN))
      .toBe(wrapper.vm.$.setupState.activeScale.at(-1))

    await wrapper.setProps({ mapLevel: 'municipio', uf: 'SC', regiaoId: null, mapData: regionRows })
    await flushPromises()
    expect(wrapper.text()).toContain('taxa/prescrições avaliadas na UF SC inteira')

    for (const indice of [0.25, 0.5, 0.79, 0.8, 1.24, 1.25, 1.49, 1.5, 1.99, 2, 2.99, 3, 4]) {
      expect(wrapper.vm.$.setupState.getRiskPiece(indice)).toBeDefined()
    }

    const selectedWithoutName = montar({
      mapLevel: 'regiao',
      uf: 'SC',
      regiaoId: 77,
      selectedIbge7: 4207205,
      mapData: [regionRows[0]],
      selectedRegiaoNome: null,
      selectedMunicipioNome: null,
      mapMeta: { map_level: 'regiao', min_medicos_amostra_municipio: 10 },
    })
    await flushPromises()
    expect(JSON.stringify(tooltipBindings)).toContain('no município selecionado')
    expect(JSON.stringify(tooltipBindings)).toContain('O ranking usa os números do médico em no município selecionado')
  })

  it('descarta o registro nacional obsoleto se o escopo muda durante o carregamento do mapa', async () => {
    let resolveNationalMap
    mocks.ensureBrasilUfMap.mockImplementationOnce(() => new Promise((resolve) => {
      resolveNationalMap = resolve
    }))

    const wrapper = montar()
    await wrapper.setProps({ mapLevel: 'regiao', uf: 'SC', regiaoId: 77, mapData: regionRows })
    await flushPromises()
    expect(wrapper.vm.$.setupState.registeredMapName).toBe('regiao-filter-77')

    resolveNationalMap()
    await flushPromises()
    expect(wrapper.vm.$.setupState.registeredMapName).toBe('regiao-filter-77')
  })

  it('usa proporção padrão em geometrias vazias, planas e sem coordenadas', async () => {
    const withoutGeo = montar({ mapLevel: 'municipio', uf: 'XX', mapData: [], mapMeta: { map_level: 'municipio' } })
    await flushPromises()
    expect(withoutGeo.vm.$.setupState.geoAspectRatio).toBe(1.5)

    mocks.geoStore.getMunicipiosGeoByUF.mockReturnValue({ type: 'FeatureCollection', features: [] })
    const emptyGeo = montar({ mapLevel: 'municipio', uf: 'SC', mapData: [], mapMeta: { map_level: 'municipio' } })
    await flushPromises()
    expect(emptyGeo.vm.$.setupState.geoAspectRatio).toBe(1.5)

    mocks.geoStore.getMunicipiosGeoByUF.mockReturnValue({
      type: 'FeatureCollection',
      features: [
        { ...feature(4207205, 'SEM COORDENADAS'), geometry: { type: 'Polygon' } },
        { ...feature(4207207, 'PLANO'), geometry: { type: 'Polygon', coordinates: [[[1, 1], [2, 1], [3, 1]]] } },
        { ...feature(4207304, 'MULTIPOLYGON'), geometry: { type: 'MultiPolygon', coordinates: [[[[0, 0], [4, 0], [4, 2], [0, 0]]]] } },
      ],
    })
    const geometries = montar({ mapLevel: 'municipio', uf: 'SC', mapData: [], mapMeta: { map_level: 'municipio' } })
    await flushPromises()
    expect(geometries.vm.$.setupState.geoAspectRatio).toBe(2)

    mocks.geoStore.getMunicipiosGeoByUF.mockReturnValue({
      type: 'FeatureCollection',
      features: [{ ...feature(4207205, 'PLANO'), geometry: { type: 'Polygon', coordinates: [[[1, 1], [2, 1], [3, 1]]] } }],
    })
    const flatGeometry = montar({ mapLevel: 'municipio', uf: 'SC', mapData: [], mapMeta: { map_level: 'municipio' } })
    await flushPromises()
    expect(flatGeometry.vm.$.setupState.geoAspectRatio).toBe(1.5)
  })
})
