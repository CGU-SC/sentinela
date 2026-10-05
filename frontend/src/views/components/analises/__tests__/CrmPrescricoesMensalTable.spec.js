import { afterEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, disposePinia, setActivePinia } from 'pinia'

import CrmPrescricoesMensalTable from '@/views/components/analises/CrmPrescricoesMensalTable.vue'
import { CRM_DAILY_RATE_HIGHLIGHT_THRESHOLD } from '@/config/riskConfig'

vi.mock('primevue/datatable', async () => {
  const { h } = await import('vue')
  return {
    default: {
      name: 'DataTable',
      props: ['value', 'dataKey', 'first', 'rows', 'totalRecords', 'sortField', 'sortOrder'],
      emits: ['row-click', 'sort', 'page'],
      setup(props, { emit, slots }) {
        return () => {
          const columns = (slots.default?.() ?? []).filter((node) => node.children && typeof node.children === 'object')
          const rowKeys = props.value.map((data) => props.dataKey(data))
          const cells = props.value.flatMap((data) => columns.map((column) => {
            const content = column.children.body?.({ data })
            return h('div', { class: 'mock-cell', 'data-header': column.props?.header ?? '' }, content)
          }))

          return h('div', { class: 'mock-datatable', 'data-first': props.first, 'data-rows': props.rows }, [
            h('button', { 'data-test': 'emit-row', onClick: () => emit('row-click', { data: props.value[0] }) }, 'Linha'),
            h('button', { 'data-test': 'emit-sort', onClick: () => emit('sort', { sortField: 'nu_prescricoes', sortOrder: 1 }) }, 'Ordenar'),
            h('button', { 'data-test': 'emit-page', onClick: () => emit('page', { first: 10, rows: 10 }) }, 'Página'),
            ...rowKeys.map((key) => h('span', { class: 'mock-row-key' }, key)),
            ...cells,
            slots.footer?.(),
          ])
        }
      },
    },
  }
})

vi.mock('primevue/column', () => ({ default: { name: 'Column', inheritAttrs: false, template: '<span />' } }))
vi.mock('@/views/components/common/HighlightedText.vue', () => ({
  default: { props: ['text', 'query'], template: '<span class="highlighted" :data-query="query">{{ text }}</span>' },
}))
vi.mock('@/views/components/common/TableFooter.vue', () => ({
  default: {
    props: ['first', 'rows', 'totalRecords', 'rowsPerPageOptions', 'unidade', 'disabled'],
    emits: ['page'],
    template: '<button data-test="footer-page" :disabled="disabled" @click="$emit(\'page\', { first: 20, rows: 20 })">Rodapé</button>',
  },
}))
vi.mock('@/views/components/analises/CrmAlertasBadge.vue', () => ({
  default: {
    props: ['pontos', 'periodo', 'competencia', 'nomeMedico'],
    emits: ['abrir'],
    template: '<button data-test="open-alerts" @click="$emit(\'abrir\')">{{ pontos.length }} alertas</button>',
  },
}))
vi.mock('@/views/components/analises/CrmMedicoFixar.vue', () => ({
  default: { props: ['idMedico', 'nome', 'crm'], template: '<span class="pin-doctor">{{ nome }} / {{ crm }}</span>' },
}))

const localRow = {
  id_medico: 'm-1',
  competencia: 202412,
  localizado_cfm: true,
  no_medico: 'MARIA DA SILVA',
  nu_crm: 12345,
  sg_uf: 'DF',
  taxa_prescricoes_dia: CRM_DAILY_RATE_HIGHLIGHT_THRESHOLD,
  nu_prescricoes: 1250,
  qtd_dias_com_prescricao: 1,
}

describe('CrmPrescricoesMensalTable', () => {
  let pinia

  function montar(props = {}) {
    pinia = createPinia()
    setActivePinia(pinia)
    return mount(CrmPrescricoesMensalTable, {
      props: {
        rows: [localRow],
        totalRecords: 23,
        alertas: {},
        alertasPeriodo: '01/2020 a 12/2024',
        ...props,
      },
      global: { plugins: [pinia], directives: { tooltip() {} } },
    })
  }

  afterEach(() => {
    if (pinia) disposePinia(pinia)
    pinia = null
    vi.restoreAllMocks()
  })

  it('formata médico, CRM, taxa, produção, competência e estado de alertas', () => {
    const wrapper = montar({ alertas: { 'm-1': [{ tipo: 'taxa', texto: 'Taxa elevada' }] } })

    expect(wrapper.text()).toContain('Maria Da Silva')
    expect(wrapper.text()).toContain('CRM 12345/DF')
    expect(wrapper.get('.rate-value').text()).toBe(CRM_DAILY_RATE_HIGHLIGHT_THRESHOLD.toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 }))
    expect(wrapper.get('.rate-value').classes()).toContain('rate-value--high')
    expect(wrapper.text()).toContain('1.250 prescrições')
    expect(wrapper.text()).toContain('1 dia com prescrição')
    expect(wrapper.text()).toContain('12/2024')
    expect(wrapper.get('[data-test="open-alerts"]').text()).toBe('1 alertas')
    expect(wrapper.get('[data-test="open-alerts"]').attributes('data-test')).toBe('open-alerts')
    expect(wrapper.get('.mock-row-key').text()).toBe('m-1|202412')
  })

  it('trata médico sem localização, CRM incompleto, plural e taxa abaixo do limite', () => {
    const row = {
      ...localRow,
      id_medico: 'm-2',
      competencia: 202401,
      localizado_cfm: false,
      no_medico: null,
      nu_crm: null,
      sg_uf: null,
      taxa_prescricoes_dia: CRM_DAILY_RATE_HIGHLIGHT_THRESHOLD - 0.01,
      qtd_dias_com_prescricao: 2,
    }
    const wrapper = montar({ rows: [row], alertas: {}, alertasErro: 'Falha ao carregar alertas' })

    expect(wrapper.text()).toContain('Não localizado no CFM')
    expect(wrapper.text()).toContain('CRM m-2')
    expect(wrapper.text()).toContain('2 dias com prescrição')
    expect(wrapper.get('.rate-value').classes()).not.toContain('rate-value--high')
    expect(wrapper.find('.alertas-carregando').exists()).toBe(false)
    expect(wrapper.find('[data-test="open-alerts"]').exists()).toBe(false)
  })

  it('mostra indicador enquanto alertas não foram carregados', () => {
    const wrapper = montar({ alertas: {} })
    expect(wrapper.get('[role="status"]').attributes('aria-label')).toBe('Carregando alertas')
  })

  it('identifica médico do Mais Médicos sem cadastro do CFM e mostra seu perfil', () => {
    const row = {
      ...localRow,
      id_medico: 'mm-1',
      localizado_cfm: false,
      no_medico: null,
      nu_crm: null,
      sg_uf: null,
      mais_medicos: {
        tp_perfil: 'INTERCAMBISTA',
        no_medico: 'ANA PEREIRA',
        no_nacionalidade: 'CUBANA',
        dt_atualizacao: '2025-03-08',
      },
    }
    const wrapper = montar({ rows: [row], alertas: {} })

    expect(wrapper.text()).toContain('Ana Pereira')
    expect(wrapper.text()).toContain('RMS mm-1')
    expect(wrapper.text()).toContain('Mais Médicos · Intercambista')
    expect(wrapper.find('.doctor-nao-localizado').exists()).toBe(false)
  })

  it('formata CRM sem UF e usa ordenação crescente quando solicitada', () => {
    const row = {
      ...localRow,
      id_medico: 'm-sem-uf',
      localizado_cfm: true,
      no_medico: 'JOSE SILVA',
      nu_crm: 2468,
      sg_uf: null,
    }
    const wrapper = montar({ rows: [row], sortOrder: 'asc' })

    expect(wrapper.text()).toContain('CRM 2468')
    expect(wrapper.text()).not.toContain('CRM 2468/')
    expect(wrapper.getComponent({ name: 'DataTable' }).props('sortOrder')).toBe(1)
  })

  it('emite seleção, ordenação e paginação quando não está carregando', async () => {
    const wrapper = montar({ alertas: { 'm-1': [{ tipo: 'taxa' }] } })

    await wrapper.get('[data-test="emit-row"]').trigger('click')
    await wrapper.get('[data-test="emit-sort"]').trigger('click')
    await wrapper.get('[data-test="emit-page"]').trigger('click')
    await wrapper.get('[data-test="footer-page"]').trigger('click')
    await wrapper.get('[data-test="open-alerts"]').trigger('click')

    expect(wrapper.emitted('select-medico')).toEqual([[localRow], [localRow]])
    expect(wrapper.emitted('sort')).toEqual([[{ sortField: 'nu_prescricoes', sortOrder: 1 }]])
    expect(wrapper.emitted('page')).toEqual([[{ first: 10, rows: 10 }], [{ first: 20, rows: 20 }]])
  })

  it('ignora interações de seleção e ordenação durante carregamento', async () => {
    const wrapper = montar({ isLoading: true, alertas: { 'm-1': [{ tipo: 'taxa' }] } })

    await wrapper.get('[data-test="emit-row"]').trigger('click')
    await wrapper.get('[data-test="emit-sort"]').trigger('click')
    await wrapper.get('[data-test="open-alerts"]').trigger('click')
    await wrapper.get('[data-test="footer-page"]').trigger('click')

    expect(wrapper.emitted('select-medico')).toBeUndefined()
    expect(wrapper.emitted('sort')).toBeUndefined()
    expect(wrapper.emitted('page')).toBeUndefined()
    expect(wrapper.get('[data-test="footer-page"]').element.disabled).toBe(true)
  })

  it('falha visivelmente quando o contrato diz que o médico está localizado mas não traz nome', () => {
    const row = { ...localRow, no_medico: null }

    expect(() => montar({ rows: [row] })).toThrow('Contrato inválido: médico m-1 localizado no CFM sem nome.')
  })
})
