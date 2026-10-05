import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { h, nextTick } from 'vue'
import { createPinia, disposePinia, setActivePinia } from 'pinia'
import axios from 'axios'

import MunicipalTable from '@/views/components/tables/MunicipalTable.vue'
import { useAnalyticsStore } from '@/stores/analytics'
import { useFilterStore } from '@/stores/filters'

vi.mock('axios', () => ({
  default: {
    get: vi.fn().mockResolvedValue({ data: { filters: {}, ui: { sidebarCollapsed: false, sidebarLocked: false } } }),
    put: vi.fn().mockResolvedValue({ data: {} }),
  },
}))

vi.mock('primevue/datatable', async () => {
  const { h } = await import('vue')
  return {
    default: {
      name: 'DataTable',
      props: ['value', 'first', 'rows'],
      emits: ['row-click', 'update:first'],
      setup(props, { emit, slots }) {
        return () => {
          const columns = (slots.default?.() ?? []).filter((node) => node.type?.name === 'Column')
          const headers = h('tr', columns.map((column) => h('th', column.props?.header ?? column.children?.header?.() ?? '')))
          const rows = props.value.map((data) => h('tr', {
            'data-p-selectable-row': 'true',
            onClick: () => emit('row-click', { data }),
          }, columns.map((column) => {
            const body = column.children?.body
            return h('td', body ? body({ data }) : String(data[column.props?.field] ?? ''))
          })))
          const footers = h('tr', columns.map((column) => h('td', column.children?.footer?.() ?? '')))
          return h('div', { class: 'mock-table', 'data-first': props.first, 'data-rows': props.rows }, [
            h('table', [h('thead', [headers]), h('tbody', rows), h('tfoot', [footers])]),
            h('button', { 'data-test': 'update-first', onClick: () => emit('update:first', 40) }, 'Atualizar página'),
            slots.footer?.(),
          ])
        }
      },
    },
  }
})
vi.mock('primevue/column', () => ({ default: { name: 'Column', inheritAttrs: false, template: '<span />' } }))
vi.mock('primevue/tag', () => ({
  default: { props: ['value'], template: '<span class="p-tag" :class="$attrs.class">{{ value }}</span>' },
}))
vi.mock('@/views/components/common/TableFooter.vue', () => ({
  default: {
    props: ['first', 'rows', 'totalRecords', 'unidade'],
    emits: ['page'],
    template: '<button data-test="next-page" @click="$emit(\'page\', { first: 20, rows: 20 })">Próxima página</button>',
  },
}))

const municipios = [
  { id_ibge7: 4207205, uf: 'SC', municipio: 'Lages', cnpjs: 2, percValSemComp: 50, valSemComp: 500, totalMov: 1000, percQtdeSemComp: 50, qtdeSemComp: 5, totalQtde: 10 },
  { id_ibge7: 4207207, uf: 'SC', municipio: 'Painel', cnpjs: 3, percValSemComp: 50, valSemComp: 1500, totalMov: 3000, percQtdeSemComp: 25, qtdeSemComp: 10, totalQtde: 40 },
]

describe('MunicipalTable', () => {
  let pinia
  let analytics
  let filters
  let wrapper

  beforeEach(() => {
    vi.useFakeTimers()
    localStorage.clear()
    axios.get.mockResolvedValue({ data: { filters: {}, ui: { sidebarCollapsed: false, sidebarLocked: false } } })
    axios.put.mockResolvedValue({ data: {} })
    pinia = createPinia()
    setActivePinia(pinia)
    analytics = useAnalyticsStore()
    filters = useFilterStore()
    analytics.resultadoMunicipios = municipios
    analytics.isLoading = false
  })

  afterEach(() => {
    wrapper?.unmount()
    wrapper = null
    vi.clearAllTimers()
    disposePinia(pinia)
    localStorage.clear()
    vi.restoreAllMocks()
    vi.useRealTimers()
  })

  function montar() {
    wrapper = mount(MunicipalTable, { global: { plugins: [pinia] } })
    return wrapper
  }

  it('renderiza os municípios, os indicadores formatados e os totais agregados', () => {
    const view = montar()

    expect(view.get('h3').text()).toBe('Análise por município')
    expect(view.get('.subtitle').text()).toBe('Brasil — 2 Municípios')
    expect(view.text()).toContain('Lages')
    expect(view.text()).toContain('Painel')
    expect(view.text()).toContain('50,00%')
    expect(view.text()).toContain('R$')
    expect(view.get('tfoot').text()).toContain('R$ 2K')
    expect(view.get('tfoot').text()).toContain('R$ 4K')
    expect(view.text()).toContain('5')
    expect(view.text()).toContain('30,00%')
    expect(view.get('thead').text()).toContain('UF')
    expect(view.get('thead').text()).toContain('Município')
  })

  it('seleciona município pelo id_ibge7 e sincroniza o nome destacado ao passar o mouse', async () => {
    const view = montar()
    await view.get('tbody tr').trigger('click')
    expect(filters.selectedMunicipio).toBe('4207205')

    await view.get('tbody tr td:nth-child(2)').trigger('mouseover')
    expect(filters.hoveredMunicipioName).toBe('Lages')
    await view.get('tbody tr td:nth-child(2)').trigger('mouseover')
    expect(filters.hoveredMunicipioName).toBe('Lages')
    await view.get('.table-section').trigger('mouseover')
    expect(filters.hoveredMunicipioName).toBeNull()
    await view.get('tbody tr td:nth-child(1)').trigger('mouseover')
    expect(filters.hoveredMunicipioName).toBe('Lages')
    await view.get('.table-section').trigger('mouseleave')
    expect(filters.hoveredMunicipioName).toBeNull()

    view.vm.$.setupState.onTableHover({ target: { closest: () => ({ cells: [] }) } })
    expect(filters.hoveredMunicipioName).toBeNull()
  })

  it('mostra a UF ativa, pagina localmente e conserva os dados durante recarga vazia', async () => {
    const view = montar()
    filters.selectedUF = 'SC'
    await nextTick()
    expect(view.get('.subtitle').text()).toBe('SC — 2 Municípios')

    await view.get('[data-test="next-page"]').trigger('click')
    expect(view.get('.mock-table').attributes('data-first')).toBe('20')

    await view.get('[data-test="update-first"]').trigger('click')
    expect(view.get('.mock-table').attributes('data-first')).toBe('40')

    analytics.isLoading = true
    analytics.resultadoMunicipios = []
    await nextTick()
    await vi.advanceTimersByTimeAsync(500)
    expect(view.get('.table-section').classes()).toContain('is-refreshing')
    expect(view.text()).toContain('Lages')
    expect(view.get('.subtitle').text()).toBe('SC — 2 Municípios')

    analytics.isLoading = false
    analytics.resultadoMunicipios = [{ ...municipios[0], municipio: 'Curitibanos' }]
    await flushPromises()
    expect(view.text()).toContain('Curitibanos')
    expect(view.text()).not.toContain('Lages')
    expect(view.get('.table-section').classes()).not.toContain('is-refreshing')
  })

  it('mantém os percentuais do rodapé em zero quando não há denominador', async () => {
    analytics.resultadoMunicipios = [{
      id_ibge7: 4207205, uf: 'SC', municipio: 'Lages', cnpjs: 0,
      valSemComp: 0, totalMov: 0, qtdeSemComp: 0, totalQtde: 0,
    }]
    await nextTick()
    const view = montar()

    expect(view.get('tfoot').text()).toContain('0,00%')
  })

  it('omite totais quando a agregação não recebe municípios', async () => {
    analytics.resultadoMunicipios = []
    await nextTick()
    const view = montar()

    expect(view.get('.mock-table').exists()).toBe(true)
    expect(view.get('tfoot').text()).toBe('TOTAL')
  })

  it('falha visivelmente quando uma linha analítica não tem id_ibge7', async () => {
    analytics.resultadoMunicipios = [{ ...municipios[0], id_ibge7: null }]
    await nextTick()
    const view = montar()

    expect(() => view.vm.$.setupState.onRowSelect({ data: { id_ibge7: null } })).toThrow(
      'Municipio sem id_ibge7 no resultado analitico.',
    )
  })
})
