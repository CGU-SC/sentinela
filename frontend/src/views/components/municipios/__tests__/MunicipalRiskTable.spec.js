import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'

import MunicipalRiskTable from '@/views/components/municipios/MunicipalRiskTable.vue'

vi.mock('primevue/datatable', async () => {
  const { h } = await import('vue')
  return {
    default: {
      name: 'DataTable',
      props: ['value', 'first', 'rows', 'rowClass'],
      emits: ['row-click', 'update:first'],
      setup(props, { emit, slots }) {
        return () => {
          const columns = (slots.default?.() ?? []).filter((node) => node.type?.name === 'Column')
          const headers = h('tr', columns.map((column) => h('th', column.props?.header ?? '')))
          const rows = props.value.map((data) => h('tr', {
            class: typeof props.rowClass === 'function' ? props.rowClass(data) : '',
            onClick: () => emit('row-click', { data }),
          }, columns.map((column) => {
            const body = column.children?.body
            return h('td', body ? body({ data }) : String(data[column.props?.field] ?? ''))
          })))
          const footers = h('tr', columns.map((column) => h('td', column.children?.footer?.() ?? '')))
          return h('div', { class: 'mock-table', 'data-first': props.first, 'data-rows': props.rows }, [
            h('table', [h('thead', [headers]), h('tbody', rows), h('tfoot', [footers])]),
            h('button', { 'data-test': 'update-first', onClick: () => emit('update:first', 50) }, 'Atualizar página'),
            slots.footer?.(),
          ])
        }
      },
    },
  }
})
vi.mock('primevue/column', () => ({ default: { name: 'Column', inheritAttrs: false, template: '<span />' } }))
vi.mock('primevue/tag', () => ({ default: { props: ['value'], template: '<span class="p-tag">{{ value }}</span>' } }))
vi.mock('@/views/components/common/TableFooter.vue', () => ({
  default: {
    props: ['first', 'rows', 'totalRecords', 'rowsPerPageOptions', 'unidade', 'disabled'],
    emits: ['page'],
    template: '<button data-test="change-page" :disabled="disabled" @click="$emit(\'page\', { first: 25, rows: 50 })">Próxima página</button>',
  },
}))

const rows = [
  { id_ibge7: 4207205, municipio: 'LAGES', uf: 'SC', cnpjs: 2, total_critico: 1, valSemComp: 500, totalMov: 1000, percValSemComp: 50, pct_critico: 50 },
  { id_ibge7: 4207207, municipio: 'PAINEL', uf: 'SC', total_cnpjs: 3, total_critico: 2, valSemComp: 1500, totalMov: 3000, percValSemComp: 50, pct_critico: 66.7 },
]
const participationRows = [
  ...rows,
  { id_ibge7: 4207304, municipio: 'CHAPECÓ', uf: 'SC', cnpjs: 4, total_critico: 0, valSemComp: 1000, totalMov: 4000, percValSemComp: 25, pct_critico: 0 },
]

describe('MunicipalRiskTable', () => {
  let wrappers

  beforeEach(() => {
    vi.useFakeTimers()
    wrappers = []
  })

  afterEach(() => {
    wrappers.forEach((wrapper) => wrapper.unmount())
    vi.clearAllTimers()
    vi.restoreAllMocks()
    vi.useRealTimers()
  })

  function montar(props = {}) {
    const wrapper = mount(MunicipalRiskTable, {
      props: { municipios: rows, participationRows, ...props },
      global: { directives: { tooltip() {} } },
    })
    wrappers.push(wrapper)
    return wrapper
  }

  it('renderiza ranking de auditoria, distribuição, percentuais e totais ponderados', () => {
    const wrapper = montar({ selectedRegiaoNome: 'REGIÃO SERRANA' })

    expect(wrapper.get('h2').text()).toBe('Ranking municipal')
    expect(wrapper.text()).toContain('Percentual não comprovação — 2 municípios no recorte atual')
    expect(wrapper.text()).toContain('Lages')
    expect(wrapper.text()).toContain('Painel')
    expect(wrapper.text()).toContain('da Região')
    expect(wrapper.text()).toContain('Região: Região Serrana')
    expect(wrapper.get('thead').text()).toContain('Participação')
    expect(wrapper.get('thead').text()).toContain('% Sem Comprovar')
    expect(wrapper.get('tfoot').text()).toContain('5')
    expect(wrapper.get('tfoot').text()).toContain('50,00%')
    expect(wrapper.get('thead').text()).not.toContain('Críticas')
  })

  it('mostra contagem e percentuais de indicadores críticos em modo indicador', () => {
    const wrapper = montar({ metricMode: 'indicator', metricLabel: 'Falecidos', selectedIbge7: 4207205 })

    expect(wrapper.get('.header-main span').text()).toBe('Falecidos — 1 municípios no recorte atual')
    expect(wrapper.text()).toContain('Município: Lages')
    expect(wrapper.get('thead').text()).toContain('Críticas')
    expect(wrapper.get('thead').text()).toContain('% Críticas')
    expect(wrapper.get('tbody').text()).toContain('50,00%')
    expect(wrapper.get('tfoot').text()).toContain('50,00%')
    expect(wrapper.get('tbody tr').classes()).toContain('row-selected')
    expect(wrapper.get('.participation-cell small').text()).toBe('da UF')
  })

  it('usa a linha de participação quando o município não consta no recorte atual', () => {
    const wrapper = montar({ municipios: [rows[0]], selectedIbge7: 4207304 })

    expect(wrapper.text()).toContain('Chapecó')
    expect(wrapper.text()).toContain('Município: Chapecó')
    expect(wrapper.get('tbody tr').classes()).toContain('row-selected')
    expect(wrapper.get('tfoot').text()).toContain('25,00%')
  })

  it('alterna a seleção do município e permite limpar o filtro regional', async () => {
    const wrapper = montar({ selectedIbge7: 4207205, selectedRegiaoNome: 'REGIÃO SERRANA' })

    await wrapper.get('tbody tr').trigger('click')
    expect(wrapper.emitted('select-municipio')).toEqual([[null]])
    await wrapper.get('.chip-clear').trigger('click')
    expect(wrapper.emitted('clear-regiao-filter')).toHaveLength(1)
    await wrapper.setProps({ selectedIbge7: null })
    await wrapper.get('tbody tr:nth-child(2)').trigger('click')
    expect(wrapper.emitted('select-municipio')).toEqual([[null], [4207207]])
  })

  it('limpa o município pelo chip de seleção', async () => {
    const wrapper = montar({ selectedIbge7: 4207205 })

    await wrapper.get('.chip-clear').trigger('click')

    expect(wrapper.emitted('select-municipio')).toEqual([[null]])
  })

  it('não altera seleção quando os dados estão obsoletos e bloqueia ações de limpeza', async () => {
    const wrapper = montar({ isStale: true, selectedRegiaoNome: 'REGIÃO SERRANA', selectedIbge7: 4207205 })

    await wrapper.get('tbody tr').trigger('click')
    await wrapper.get('.chip-clear').trigger('click')
    expect(wrapper.emitted('select-municipio')).toBeUndefined()
    expect(wrapper.emitted('clear-regiao-filter')).toBeUndefined()
    expect(wrapper.get('.chip-clear').element.disabled).toBe(true)
    expect(wrapper.get('.municipal-table-card').classes()).toContain('is-stale')
  })

  it('mostra erro e estado de atualização, preservando as regras de paginação', async () => {
    const wrapper = montar({ error: 'Serviço indisponível' })
    expect(wrapper.get('[role="alert"]').text()).toBe('Serviço indisponível')

    await wrapper.setProps({ error: null, isLoading: true })
    await vi.advanceTimersByTimeAsync(500)
    expect(wrapper.get('[role="status"]').text()).toBe('Atualizando resultados')
    expect(wrapper.get('.municipal-table-card').classes()).toContain('is-refreshing')

    await wrapper.get('[data-test="change-page"]').trigger('click')
    expect(wrapper.get('.mock-table').attributes('data-first')).toBe('25')
    expect(wrapper.get('.mock-table').attributes('data-rows')).toBe('50')

    await wrapper.get('[data-test="update-first"]').trigger('click')
    expect(wrapper.get('.mock-table').attributes('data-first')).toBe('50')
  })

  it('usa métricas ausentes como zero e não mostra chip para município fora dos dados', async () => {
    const wrapper = montar({
      municipios: [{ id_ibge7: 1, municipio: 'Município A', uf: 'AC' }],
      participationRows: [],
      metricMode: 'indicator',
    })

    expect(wrapper.get('tfoot').text()).toContain('0,00%')
    expect(wrapper.get('.participation-cell span').text()).toBe('0,00%')

    await wrapper.setProps({ selectedIbge7: 999 })
    expect(wrapper.find('.header-filter-chips').exists()).toBe(false)
    expect(wrapper.findAll('tbody tr')).toHaveLength(0)
  })

  it('falha visivelmente quando uma linha analítica não tem id_ibge7', async () => {
    const wrapper = montar({ municipios: [{ ...rows[0], id_ibge7: null }] })

    expect(() => wrapper.vm.$.setupState.onRowClick({ data: {} })).toThrow(
      'Municipio sem id_ibge7 no resultado analitico.',
    )
  })

  it('retorna percentuais zero quando totais e universo de participação não têm vendas', () => {
    const wrapper = montar({
      municipios: [{ id_ibge7: 1, municipio: 'A', uf: 'AC', cnpjs: 0, total_critico: 0, valSemComp: 0, totalMov: 0 }],
      participationRows: [],
    })

    expect(wrapper.get('tfoot').text()).toContain('0,00%')
    expect(wrapper.get('.participation-cell span').text()).toBe('0,00%')
  })

  it('trata totalMov ausente como zero quando o universo de participação tem vendas', () => {
    const wrapper = montar({
      municipios: [{ id_ibge7: 1, municipio: 'A', uf: 'AC', cnpjs: 1, total_critico: 0, valSemComp: 0 }],
      participationRows: [{ id_ibge7: 2, municipio: 'B', uf: 'AC', totalMov: 100 }],
    })

    expect(wrapper.get('.participation-cell span').text()).toBe('0,00%')
    expect(wrapper.get('tbody tr').text()).toContain('A')
  })
})
