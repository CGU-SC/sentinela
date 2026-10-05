import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { reactive } from 'vue'
import { createMemoryHistory, createRouter } from 'vue-router'

import ClinicalTargetTable from '@/views/components/targets/tables/ClinicalTargetTable.vue'
import { AUDIT_THRESHOLDS } from '@/config/riskConfig'

const mocks = vi.hoisted(() => ({ metodologia: null, formatCurrencyFull: vi.fn((value) => `R$ ${value}`) }))

vi.mock('@/stores/metodologiaConfig', () => ({ useMetodologiaConfigStore: () => mocks.metodologia }))
vi.mock('@/composables/useFrozenData', () => ({ useFrozenData: (source) => source() }))
vi.mock('@/composables/useFormatting', () => ({
  useFormatting: () => ({
    formatCurrencyFull: mocks.formatCurrencyFull,
    formatTitleCase: (value) => value ? `${value[0].toUpperCase()}${value.slice(1)}` : value,
  }),
}))
vi.mock('@/composables/useStatusClass', () => ({ useStatusClass: () => ({ conexaoMsClass: (active) => active ? 'is-active' : 'is-inactive' }) }))
vi.mock('primevue/datatable', async () => {
  const { computed, h, provide } = await import('vue')
  return {
    default: {
      name: 'DataTable',
      props: ['value', 'first', 'rows', 'totalRecords', 'sortField', 'sortOrder'],
      emits: ['page', 'sort', 'row-click'],
      setup(props, { emit, slots }) {
        const firstRow = computed(() => props.value?.[0] ?? null)
        provide('clinical-target-row', firstRow)
        return () => h('section', { class: 'mock-datatable' }, [
          ...(slots.default?.() ?? []),
          firstRow.value
            ? h('div', { class: 'mock-table-actions' }, [
                h('button', {
                  'data-test': 'open-row',
                  onClick: () => emit('row-click', { data: firstRow.value, originalEvent: { target: { closest: () => null } } }),
                }, 'Abrir linha'),
                h('button', {
                  'data-test': 'copy-origin-row',
                  onClick: () => emit('row-click', { data: firstRow.value, originalEvent: { target: { closest: () => ({}) } } }),
                }, 'Clique de cópia'),
                h('button', { 'data-test': 'page', onClick: () => emit('page', { first: 20, rows: 20 }) }, 'Página'),
                h('button', { 'data-test': 'sort', onClick: () => emit('sort', { sortField: 'cnpj', sortOrder: 1 }) }, 'Ordenar'),
              ])
            : slots.empty?.(),
          slots.footer?.(),
        ])
      },
    },
  }
})
vi.mock('primevue/column', async () => {
  const { h, inject } = await import('vue')
  return {
    default: {
      name: 'Column',
      props: ['field', 'header'],
      setup(props, { slots }) {
        const row = inject('clinical-target-row')
        return () => h('div', { class: 'mock-column', 'data-field': props.field }, row.value ? (slots.body?.({ data: row.value }) ?? []) : [])
      },
    },
  }
})
vi.mock('primevue/button', () => ({
  default: {
    props: ['icon'],
    emits: ['click'],
    template: '<button class="detail-btn" type="button" @click="$emit(\'click\', $event)"><i :class="icon" /></button>',
  },
}))
vi.mock('primevue/tag', () => ({ default: { props: ['value'], template: '<span class="mock-tag">{{ value }}</span>' } }))
vi.mock('@/views/components/common/TableFooter.vue', () => ({
  default: {
    props: ['first', 'rows', 'totalRecords', 'unidade'],
    emits: ['page'],
    template: '<button data-test="footer-page" @click="$emit(\'page\', { first: 40, rows: 20 })">Paginar rodapé</button>',
  },
}))

const ROW = {
  cnpj: '12345678000195',
  razao_social: 'farmácia alfa',
  municipio: 'porto velho',
  uf: 'RO',
  ano_base: 2025,
  casos_observados: 3,
  casos_esperados: 1,
  razao_observado_esperado: 3,
  valor_incompativel: 25000,
  participacao_municipio: 0.5,
  is_conexao_ativa: true,
  is_matriz: true,
}

describe('ClinicalTargetTable', () => {
  let router
  let wrapper

  beforeEach(async () => {
    vi.clearAllMocks()
    mocks.metodologia = reactive({
      loaded: true,
      auditHighValue: 10000,
      ensureLoaded: vi.fn().mockResolvedValue(),
    })
    router = createRouter({
      history: createMemoryHistory(),
      routes: [
        { path: '/alvos', component: { template: '<div />' } },
        { path: '/estabelecimentos/:cnpj', name: 'detail', component: { template: '<div />' } },
      ],
    })
    await router.push('/alvos')
    await router.isReady()
  })

  afterEach(() => {
    wrapper?.unmount()
    wrapper = null
    vi.restoreAllMocks()
  })

  function mountTable(rows = [ROW], sourceNotice = null) {
    wrapper = mount(ClinicalTargetTable, {
      props: {
        targetMeta: {
          tableSubtitle: 'Ranking clínico',
          valueHeader: 'Valor incompatível',
        },
        rows,
        totalRecords: rows.length,
        sourceNotice,
      },
      global: { plugins: [router], directives: { tooltip() {} } },
    })
    return wrapper
  }

  it('formata os campos clínicos, financeiros e o estado de conexão', async () => {
    const view = mountTable()
    await flushPromises()

    expect(mocks.metodologia.ensureLoaded).toHaveBeenCalledOnce()
    expect(view.text()).toContain('Farmácia alfa')
    expect(view.text()).toContain('Porto velho')
    expect(view.text()).toContain('Observados 3')
    expect(view.text()).toContain('Esperados 1 | Razão 3,00')
    expect(view.text()).toContain('R$ 25000')
    expect(view.text()).toContain('50,00%')
    expect(view.text()).toContain('Ativa')
    expect(view.find('.high-value-audit').exists()).toBe(true)
  })

  it('navega para o estabelecimento e ignora clique originado no controle de cópia', async () => {
    const view = mountTable()
    await view.get('[data-test="open-row"]').trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.fullPath).toBe('/estabelecimentos/12345678000195?s=indicadores')

    await router.push('/alvos')
    await view.get('[data-test="copy-origin-row"]').trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.path).toBe('/alvos')
  })

  it('copia o CNPJ e remove o estado visual depois do intervalo indicado', async () => {
    const writeText = vi.fn()
    vi.stubGlobal('navigator', Object.assign(Object.create(navigator), { clipboard: { writeText } }))
    vi.useFakeTimers()
    const view = mountTable()

    await view.get('.copy-btn').trigger('click')
    expect(writeText).toHaveBeenCalledWith(ROW.cnpj)
    expect(view.get('.copy-btn').classes()).toContain('text-success')
    await vi.advanceTimersByTimeAsync(1200)
    expect(view.get('.copy-btn').classes()).not.toContain('text-success')
    vi.useRealTimers()
  })

  it('mantém estados ausentes sem navegar ou abrir diálogo clínico', async () => {
    const row = {
      ...ROW,
      cnpj: '',
      razao_social: null,
      municipio: null,
      casos_observados: null,
      casos_esperados: null,
      razao_observado_esperado: null,
      participacao_municipio: null,
      is_conexao_ativa: false,
      is_matriz: false,
    }
    const view = mountTable([row])
    await flushPromises()

    expect(view.text()).toContain('—')
    await view.get('[data-test="open-row"]').trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.path).toBe('/alvos')
    const writeText = vi.fn()
    vi.stubGlobal('navigator', Object.assign(Object.create(navigator), { clipboard: { writeText } }))
    await view.get('.copy-btn').trigger('click')
    expect(writeText).not.toHaveBeenCalled()
    await view.get('.detail-btn').trigger('click')
    expect(view.emitted('open-incompatibility')).toBeUndefined()
  })

  it('usa o limiar financeiro padrão antes de carregar a metodologia', async () => {
    mocks.metodologia.loaded = false
    const view = mountTable([{ ...ROW, valor_incompativel: AUDIT_THRESHOLDS.HIGH_VALUE - 1 }])
    await flushPromises()

    expect(view.find('.high-value-audit').exists()).toBe(false)
  })

  it('mantém a tabela renderizada quando a configuração metodológica falha', async () => {
    const warning = vi.spyOn(console, 'warn').mockImplementation(() => {})
    mocks.metodologia.ensureLoaded.mockRejectedValueOnce(new Error('Configuração indisponível'))
    const view = mountTable()
    await flushPromises()

    expect(view.find('.mock-datatable').exists()).toBe(true)
    expect(warning).toHaveBeenCalledWith(
      '[ClinicalTargetTable] Não foi possível carregar a configuração metodológica.',
      expect.objectContaining({ message: 'Configuração indisponível' }),
    )
  })

  it('emite paginação, ordenação e incompatibilidade e preserva o aviso de fonte vazia', async () => {
    const view = mountTable([], 'Sem dados no período')
    expect(view.text()).toContain('Sem dados no período')
    await view.get('[data-test="footer-page"]').trigger('click')
    expect(view.emitted('lazy-load')).toEqual([[{ first: 40, rows: 20 }]])
    view.unmount()

    const populated = mountTable()
    await populated.get('[data-test="page"]').trigger('click')
    await populated.get('[data-test="sort"]').trigger('click')
    expect(populated.emitted('lazy-load')).toEqual([
      [{ first: 20, rows: 20 }],
      [{ sortField: 'cnpj', sortOrder: 1 }],
    ])

    await populated.get('.detail-btn').trigger('click')
    expect(populated.emitted('open-incompatibility')).toEqual([[ROW.cnpj]])

    const empty = mountTable([], null)
    expect(empty.text()).toContain('Nenhuma farmácia encontrada para o alvo selecionado.')
  })
})
