import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { h, nextTick } from 'vue'
import { createPinia, disposePinia, setActivePinia } from 'pinia'
import axios from 'axios'

import CrmPrescricoesRanking from '@/views/components/analises/CrmPrescricoesRanking.vue'
import { CRM_DAILY_RATE_HIGHLIGHT_THRESHOLD } from '@/config/riskConfig'
import { useCrmMedicosFixadosStore } from '@/stores/crmMedicosFixados'
import { useThemeStore } from '@/stores/theme'

const observerMocks = vi.hoisted(() => ({ instances: [] }))

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
      props: ['value', 'first', 'rows', 'totalRecords', 'sortField', 'sortOrder'],
      emits: ['row-click', 'sort', 'page'],
      setup(props, { emit, slots }) {
        return () => {
          const columns = (slots.default?.() ?? []).filter((node) => node.type?.name === 'Column')
          const headers = columns.map((column) => column.children?.header?.()).filter(Boolean)
          const cells = props.value.flatMap((data) => columns.map((column) => {
            const body = column.children?.body
            return h('div', { class: 'mock-cell', 'data-field': column.props?.field ?? '' }, body ? body({ data }) : null)
          }))
          return h('div', { class: 'mock-datatable' }, [
            h('button', { 'data-test': 'ranking-row', onClick: () => emit('row-click', { data: props.value[0] }) }, 'Linha'),
            h('button', { 'data-test': 'ranking-sort', onClick: () => emit('sort', { sortField: 'no_medico', sortOrder: 1 }) }, 'Ordenar'),
            h('button', { 'data-test': 'ranking-page', onClick: () => emit('page', { first: 10, rows: 10 }) }, 'Página'),
            ...headers,
            ...cells,
            slots.footer?.(),
          ])
        }
      },
    },
  }
})

vi.mock('primevue/column', () => ({ default: { name: 'Column', inheritAttrs: false, template: '<span />' } }))
vi.mock('primevue/overlaypanel', async () => {
  const { h, ref } = await import('vue')
  return {
    default: {
      name: 'OverlayPanel',
      setup(_, { expose, slots }) {
        const visible = ref(false)
        expose({ toggle: () => { visible.value = !visible.value }, hide: () => { visible.value = false } })
        return () => visible.value ? h('div', { class: 'mock-overlay' }, slots.default?.()) : null
      },
    },
  }
})
vi.mock('@/views/components/common/HighlightedText.vue', () => ({
  default: { props: ['text', 'query'], template: '<span class="highlighted">{{ text }}</span>' },
}))
vi.mock('@/views/components/common/PinIcon.vue', () => ({
  default: { props: ['preenchido'], template: '<span class="pin-icon" :data-filled="preenchido" />' },
}))
vi.mock('@/views/components/common/TableFooter.vue', () => ({
  default: {
    props: ['first', 'rows', 'totalRecords', 'rowsPerPageOptions', 'unidade', 'disabled'],
    emits: ['page'],
    template: '<button data-test="footer-page" :disabled="disabled" @click="$emit(\'page\', { first: 20, rows: 20 })">Rodapé</button>',
  },
}))
vi.mock('@/views/components/common/CrmBarrasMensais.vue', () => ({
  default: {
    props: ['total', 'barras', 'divisores'],
    template: '<span data-test="monthly-bars" :data-total="total" :data-divisores="divisores.join(\',\')">{{ barras.map((barra) => barra.faixa).join(\',\') }}</span>',
  },
}))
vi.mock('@/views/components/analises/CrmPrescricoesMensalTable.vue', () => ({
  default: {
    name: 'CrmPrescricoesMensalTable',
    props: ['rows', 'totalRecords', 'first', 'pageSize', 'sortField', 'sortOrder', 'isLoading', 'appliedQuery', 'alertas', 'alertasPeriodo', 'alertasErro'],
    emits: ['page', 'sort', 'select-medico'],
    template: '<div data-test="monthly-child"><button @click="$emit(\'page\', { first: 20, rows: 20 })">Mudar página</button><button @click="$emit(\'sort\', { field: \'competencia\', order: 1 })">Ordenar mês</button><button @click="$emit(\'select-medico\', rows[0])">Selecionar médico</button>{{ rows.length }} linhas</div>',
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
  default: { props: ['idMedico', 'nome', 'crm'], template: '<span class="pin-doctor">{{ nome }} {{ crm }}</span>' },
}))

const row = {
  id_medico: 'm-1',
  localizado_cfm: true,
  no_medico: 'MARIA DA SILVA',
  nu_crm: 12345,
  sg_uf: 'DF',
  taxa_prescricoes_dia: CRM_DAILY_RATE_HIGHLIGHT_THRESHOLD,
  nu_prescricoes: 1250,
  qtd_dias_com_prescricao: 9,
  qtd_farmacias: 1,
  qtd_municipios: 1,
  nu_prescricoes_farmacias_filtradas: 100,
  percentual_prescricoes_farmacias_filtradas: 8.5,
}

function dadosBase(overrides = {}) {
  return {
    mensal: { response: null, loading: false, error: null, first: 0, pageSize: 10, sortField: 'competencia', sortOrder: 'desc', appliedQuery: '' },
    serie: { response: null, loading: false, error: null },
    alertas: { porMedico: {}, periodo: null, erro: null },
    ...overrides,
  }
}

describe('CrmPrescricoesRanking', () => {
  let pinia
  let wrappers

  beforeEach(() => {
    localStorage.clear()
    axios.get.mockResolvedValue({ data: { filters: {}, ui: { sidebarCollapsed: false, sidebarLocked: false } } })
    axios.put.mockResolvedValue({ data: {} })
    wrappers = []
    observerMocks.instances = []
    vi.stubGlobal('ResizeObserver', class {
      constructor(callback) { this.callback = callback; observerMocks.instances.push(this) }
      observe() {}
      disconnect() { this.disconnected = true }
    })
    pinia = createPinia()
    setActivePinia(pinia)
  })

  afterEach(() => {
    wrappers.forEach((wrapper) => wrapper.unmount())
    disposePinia(pinia)
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  function montar(props = {}) {
    const wrapper = mount(CrmPrescricoesRanking, {
      props: { rows: [row], mensal: dadosBase().mensal, serie: dadosBase().serie, alertas: dadosBase().alertas, ...props },
      global: { plugins: [pinia], directives: { tooltip() {} } },
    })
    wrappers.push(wrapper)
    return wrapper
  }

  it('exibe ranking, escopo, filtros de farmácia, alertas e mensagens de atualização', async () => {
    const wrapper = montar({
      escopo: 'São Paulo',
      totalRecords: 12,
      farmaciasFiltradas: true,
      appliedQuery: 'CRM DF 12345',
      pageError: 'Página seguinte indisponível',
      alertas: { porMedico: { 'm-1': [{ tipo: 'taxa' }] }, periodo: { inicio: '2024-01', fim: '2024-12' }, erro: 'alertas incompletos' },
    })

    expect(wrapper.get('h2').text()).toBe('Ranking de médicos')
    expect(wrapper.text()).toContain('São Paulo · 12 médicos encontrados')
    await wrapper.setProps({ error: 'Atualização indisponível' })
    expect(wrapper.text()).toContain('Falha ao atualizar · resultado anterior exibido')
    expect(wrapper.text()).toContain('Página seguinte indisponível')
    expect(wrapper.text()).toContain('Alertas dos médicos indisponíveis: alertas incompletos')
    expect(wrapper.text()).toContain('Maria Da Silva')
    expect(wrapper.text()).toContain('CRM 12345/DF')
    expect(wrapper.get('.rate-value').classes()).toContain('rate-value--high')
    expect(wrapper.text()).toContain('1 farmácia')
    expect(wrapper.text()).toContain('1 município')
    expect(wrapper.text()).toContain('100 prescrições')
    expect(wrapper.text()).toContain('8,5% do total')
    expect(wrapper.get('[data-test="open-alerts"]').text()).toBe('1 alertas')
  })

  it('renderiza estados vazio, carregando e erro do ranking', () => {
    const vazio = montar({ rows: [], appliedQuery: 'ninguém' })
    expect(vazio.text()).toContain('Nenhum médico encontrado para o termo')

    const carregando = montar({ rows: [], isLoading: true })
    expect(carregando.text()).toContain('Calculando ranking...')

    const erro = montar({ rows: [], error: 'Base indisponível' })
    expect(erro.text()).toContain('Ranking indisponível no momento')
    expect(erro.text()).toContain('Base indisponível')

    const semFixados = montar({ rows: [], fixadosPedidos: 2 })
    expect(semFixados.text()).toContain('Nenhum médico fixado aparece com os filtros atuais.')

    const vazioSemFiltros = montar({ rows: [] })
    expect(vazioSemFiltros.text()).toContain('Nenhum médico encontrado para os filtros atuais.')
  })

  it('troca de abas e emite paginação, ordenação e seleção no estado atualizado', async () => {
    const wrapper = montar({ alertas: { porMedico: { 'm-1': [{ tipo: 'taxa' }] }, periodo: null, erro: null } })

    await wrapper.findAll('[role="tab"]')[1].trigger('click')
    expect(wrapper.emitted('update:tab')).toEqual([['linha']])
    await wrapper.findAll('[role="tab"]')[2].trigger('click')
    expect(wrapper.emitted('update:tab')).toEqual([['linha'], ['mes']])

    await wrapper.get('[data-test="ranking-row"]').trigger('click')
    await wrapper.get('[data-test="ranking-sort"]').trigger('click')
    await wrapper.get('[data-test="ranking-page"]').trigger('click')
    await wrapper.get('[data-test="footer-page"]').trigger('click')
    await wrapper.get('[data-test="open-alerts"]').trigger('click')

    expect(wrapper.emitted('select-medico')).toEqual([[row], [row]])
    expect(wrapper.emitted('sort')).toEqual([[{ sortField: 'no_medico', sortOrder: 1 }]])
    expect(wrapper.emitted('page')).toEqual([[{ first: 10, rows: 10 }], [{ first: 20, rows: 20 }]])
  })

  it('bloqueia interações enquanto o resultado está sendo atualizado ou está obsoleto', async () => {
    for (const props of [{ isRefreshing: true }, { isStale: true }]) {
      const wrapper = montar(props)
      await wrapper.get('[data-test="ranking-row"]').trigger('click')
      await wrapper.get('[data-test="ranking-sort"]').trigger('click')
      await wrapper.get('[data-test="ranking-page"]').trigger('click')
      await wrapper.get('[data-test="footer-page"]').trigger('click')
      expect(wrapper.emitted('select-medico')).toBeUndefined()
      expect(wrapper.emitted('sort')).toBeUndefined()
      expect(wrapper.emitted('page')).toBeUndefined()
      expect(wrapper.get('[data-test="footer-page"]').element.disabled).toBe(true)
    }
  })

  it('mantém os dados congelados no refresh e troca para a resposta nova ao concluir', async () => {
    const wrapper = montar({ isRefreshing: true, rows: [row] })
    const updated = { ...row, id_medico: 'm-2', no_medico: 'JOAO SOUZA' }

    await wrapper.setProps({ rows: [updated] })
    await flushPromises()
    expect(wrapper.text()).toContain('Maria Da Silva')
    expect(wrapper.text()).not.toContain('Joao Souza')

    await wrapper.setProps({ isRefreshing: false })
    await nextTick()
    expect(wrapper.text()).toContain('Joao Souza')
  })

  it('exibe os estados vazio, erro e carregamento da visão mensal e encaminha seus eventos', async () => {
    const wrapper = montar({ rows: [row], tab: 'mes', mensal: { ...dadosBase().mensal, error: 'Falha mensal' } })
    expect(wrapper.text()).toContain('Visão mensal indisponível no momento')

    await wrapper.setProps({ mensal: { ...dadosBase().mensal, loading: true, error: null } })
    expect(wrapper.get('.ranking-table-loading').attributes('aria-label')).toBe('Carregando a visão mensal')

    await wrapper.setProps({ mensal: { ...dadosBase().mensal, response: { linhas: [], qtd_linhas: 0 }, appliedQuery: 'nome' } })
    expect(wrapper.text()).toContain('Nenhum médico encontrado para o termo')

    await wrapper.setProps({ mensal: { ...dadosBase().mensal, response: { linhas: [], qtd_linhas: 0 } } })
    expect(wrapper.text()).toContain('Nenhum mês com prescrição para os filtros atuais.')

    const monthlyRows = [{ ...row, competencia: 202406 }]
    await wrapper.setProps({ mensal: { ...dadosBase().mensal, response: { linhas: monthlyRows, qtd_linhas: 5 }, loading: true, error: 'Resposta antiga' } })
    expect(wrapper.get('[data-test="monthly-child"]').text()).toContain('1 linhas')
    expect(wrapper.get('.ranking-table-loading').attributes('aria-label')).toBe('Atualizando visão mensal')
    await wrapper.get('[data-test="monthly-child"]').findAll('button')[0].trigger('click')
    await wrapper.get('[data-test="monthly-child"]').findAll('button')[1].trigger('click')
    await wrapper.get('[data-test="monthly-child"]').findAll('button')[2].trigger('click')
    expect(wrapper.emitted('mensal-page')).toEqual([[{ first: 20, rows: 20 }]])
    expect(wrapper.emitted('mensal-sort')).toEqual([[{ field: 'competencia', order: 1 }]])
    expect(wrapper.emitted('select-medico')).toEqual([[monthlyRows[0]]])
    expect(wrapper.text()).toContain('Resposta antiga')
  })

  it('exibe fixados, alterna o recorte e permite soltar um ou todos', async () => {
    const fixedStore = useCrmMedicosFixadosStore()
    fixedStore.alternar({ id_medico: 'm-1', nome: 'Maria Silva', crm: '123/DF' })
    fixedStore.alternar({ id_medico: 'm-2', nome: 'João Souza', crm: '456/SP' })
    const wrapper = montar({ fixadosPedidos: 2, totalRecords: 1 })

    expect(wrapper.get('.ranking-fixados-total').text()).toBe('2')
    expect(wrapper.text()).toContain('1 de 2 médicos fixados no recorte')
    await wrapper.get('.ranking-fixados-chave').trigger('click')
    expect(fixedStore.soFixados).toBe(true)
    expect(wrapper.get('.ranking-fixados-chave').attributes('aria-pressed')).toBe('true')
    await wrapper.get('[aria-label="Ver os médicos fixados"]').trigger('click')
    expect(wrapper.get('[role="dialog"]').text()).toContain('Médicos fixados')
    await wrapper.get('[aria-label="Soltar Maria Silva"]').trigger('click')
    expect(fixedStore.medicos.map((medico) => medico.id_medico)).toEqual(['m-2'])
    await wrapper.get('.rfx-soltar-todos').trigger('click')
    expect(fixedStore.total).toBe(0)
    expect(fixedStore.soFixados).toBe(false)
  })

  it('renderiza a linha do tempo, alterna escala e rejeita meses fora do período', async () => {
    const serie = {
      loading: false,
      error: null,
      response: {
        meses: [
          { competencia: 202312, p95_taxa_dia: 2 },
          { competencia: 202401, p95_taxa_dia: 4 },
          { competencia: 202402, p95_taxa_dia: 4 },
        ],
        medicos: [{
          id_medico: 'm-1',
          meses: [
            { competencia: 202312, taxa_prescricoes_dia: 2, taxa_elevada: true, razao_p95: 2 },
            { competencia: 202401, taxa_prescricoes_dia: 8 },
            { competencia: 202402, taxa_prescricoes_dia: 1 },
          ],
        }],
      },
    }
    const wrapper = montar({ tab: 'linha', serie })

    expect(wrapper.get('[data-test="monthly-bars"]').attributes('data-total')).toBe('3')
    expect(wrapper.get('[data-test="monthly-bars"]').attributes('data-divisores')).toBe('1')
    expect(wrapper.vm.$.setupState.barrasPorMedico.get('m-1')).toHaveLength(3)
    expect(wrapper.vm.$.setupState.barrasPorMedico.get('m-1')[0].faixa).toBe('leve')
    expect(wrapper.text()).toContain('2023')
    expect(wrapper.text()).toContain('2024')
    await wrapper.get('[role="radio"][aria-checked="false"]').trigger('click')
    expect(localStorage.getItem('sentinela_crm_linha_tempo_escala')).toBe('medico')

    const contratoInvalido = {
      ...serie,
      response: { ...serie.response, medicos: [{ id_medico: 'm-1', meses: [{ competencia: 202212, taxa_prescricoes_dia: 2 }] }] },
    }
    expect(() => montar({ tab: 'linha', serie: contratoInvalido })).toThrow('Contrato inválido em crm-prescricoes-serie-mensal: mês 202212 fora do período.')
  })

  it('limpa o observador de redimensionamento ao desmontar', () => {
    const wrapper = montar()
    const observer = observerMocks.instances[0]
    wrapper.unmount()
    expect(observer.disconnected).toBe(true)
  })

  it('exibe o selo Mais Médicos para profissional ausente do cadastro do CFM', () => {
    const maisMedicos = {
      ...row,
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
    const wrapper = montar({ rows: [maisMedicos] })

    expect(wrapper.text()).toContain('Ana Pereira')
    expect(wrapper.text()).toContain('RMS mm-1')
    expect(wrapper.text()).toContain('Mais Médicos · Intercambista')
    expect(wrapper.find('.doctor-nao-localizado').exists()).toBe(false)
  })

  it('usa escala comum quando a preferência não pode ser lida e mantém a escolha sem persistência', async () => {
    const escalaStorage = 'sentinela_crm_linha_tempo_escala'
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(function getItem(key) {
      if (key === escalaStorage) throw new Error('leitura bloqueada')
      return null
    })
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new Error('gravação bloqueada') })
    const wrapper = montar({
      tab: 'linha',
      serie: { loading: false, error: null, response: { meses: [], medicos: [] } },
    })
    await flushPromises()

    const scaleButtons = wrapper.findAll('.ranking-escala button[role="radio"]')
    const common = scaleButtons.find((button) => button.text() === 'Comum')
    const perDoctor = scaleButtons.find((button) => button.text() === 'Por médico')
    expect(common.attributes('aria-checked')).toBe('true')

    await perDoctor.trigger('click')
    expect(perDoctor.attributes('aria-checked')).toBe('true')
  })

  it('fornece tokens de cor neutra conforme o tema ativo', async () => {
    const wrapper = montar()
    const themeStore = useThemeStore()
    const darkColors = wrapper.vm.$.setupState.dataColorVars

    themeStore.isDark = false
    await nextTick()
    const lightColors = wrapper.vm.$.setupState.dataColorVars

    expect(darkColors).toHaveProperty('--data-color')
    expect(darkColors).toHaveProperty('--data-color-soft')
    expect(lightColors).toHaveProperty('--data-color')
    expect(lightColors['--data-color']).not.toBe(darkColors['--data-color'])
  })

  it('normaliza as visões mensal e de linha do tempo antes da primeira resposta', async () => {
    const wrapper = montar({ tab: 'mes' })
    const state = wrapper.vm.$.setupState

    expect(state.mensalRows).toEqual([])
    expect(state.mensalTotal).toBe(0)
    expect(state.mensalPronta).toBe(false)

    await wrapper.setProps({ tab: 'linha' })
    expect(state.linhaPronta).toBe(false)
    expect(state.eixo).toBeNull()
    expect(state.divisoresAno).toEqual([])
    expect(state.barrasPorMedico.size).toBe(0)
  })

  it('trata resposta mensal vazia no recorte só de fixados e monta os subtítulos', async () => {
    const fixadosStore = useCrmMedicosFixadosStore()
    fixadosStore.alternar({ id_medico: 'm-1', nome: 'Maria Silva', crm: '123/DF' })
    fixadosStore.soFixados = true
    const wrapper = montar({
      tab: 'mes',
      mensal: { ...dadosBase().mensal, response: { escopo: 'Distrito Federal', linhas: [], qtd_linhas: 0 } },
    })

    expect(wrapper.text()).toContain('Nenhum médico fixado tem mês com prescrição nos filtros atuais.')
    expect(wrapper.text()).toContain('Distrito Federal · 0 linhas médico × mês · só fixados')

    await wrapper.setProps({
      tab: 'resumo',
      rows: [{ ...row, qtd_farmacias: 2, qtd_municipios: 3, percentual_prescricoes_farmacias_filtradas: null }],
      sortOrder: 'asc',
      farmaciasFiltradas: true,
    })
    expect(wrapper.text()).toContain('2 farmácias')
    expect(wrapper.text()).toContain('3 municípios')
    expect(wrapper.text()).toContain('— do total')
    expect(wrapper.findComponent({ name: 'DataTable' }).props('sortOrder')).toBe(1)

    await wrapper.setProps({ fixadosPedidos: 1, totalRecords: 1, rows: [{ ...row }] })
    expect(wrapper.text()).toContain('1 de 1 médico fixado no recorte')
  })

  it('avalia ramos de contratos incompletos, identificadores e estados da linha do tempo', async () => {
    const naoLocalizado = {
      ...row,
      localizado_cfm: false,
      no_medico: null,
      nu_crm: null,
      sg_uf: null,
      mais_medicos: null,
    }
    const wrapper = montar({ rows: [naoLocalizado], sortOrder: 'asc' })
    const state = wrapper.vm.$.setupState

    expect(wrapper.text()).toContain('Não localizado no CFM')
    expect(state.crmLabel({ ...row, sg_uf: null })).toBe('CRM 12345')
    expect(() => state.doctorLabel({ id_medico: 'sem-nome', localizado_cfm: true, no_medico: null }))
      .toThrow('Contrato inválido: médico sem-nome localizado no CFM sem nome.')
    expect(wrapper.findComponent({ name: 'DataTable' }).props('sortOrder')).toBe(1)

    await wrapper.setProps({ tab: 'linha', serie: { response: null, loading: false, error: null } })
    expect(wrapper.get('.ranking-table-loading').attributes('aria-label')).toBe('Carregando a linha do tempo')
    await wrapper.setProps({ serie: { response: null, loading: false, error: 'Série indisponível' } })
    expect(wrapper.text()).toContain('Série indisponível')

    await wrapper.setProps({ tab: 'resumo', isPageLoading: true })
    expect(wrapper.get('.ranking-table-loading').attributes('aria-label')).toBe('Atualizando ranking')
  })

  it('ativa tooltip apenas quando a medição de nome detecta texto cortado', async () => {
    const wrapper = montar()
    const name = wrapper.get('.doctor-name').element
    Object.defineProperty(name, 'scrollWidth', { configurable: true, value: 180 })
    Object.defineProperty(name, 'clientWidth', { configurable: true, value: 80 })

    observerMocks.instances[0].callback()
    await nextTick()

    expect(wrapper.vm.$.setupState.nomeTooltip(row).disabled).toBe(false)
  })
})
