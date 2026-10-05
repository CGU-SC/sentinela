import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, shallowMount } from '@vue/test-utils'
import { reactive } from 'vue'
import { createMemoryHistory, createRouter } from 'vue-router'

import WatchlistView from '@/views/lists/WatchlistView.vue'
import { API_ENDPOINTS } from '@/config/api'
import { AUDIT_THRESHOLDS } from '@/config/riskConfig'
import { CRM_ALERTA_BADGE_TONS } from '@/config/colors'

const mocks = vi.hoisted(() => ({
  farmaciaLists: null,
  filters: null,
  geo: null,
  notaTecnica: null,
  evidencias: null,
  metodologia: null,
  theme: null,
  apiParams: null,
  toastAdd: vi.fn(),
  requestResumo: vi.fn(),
  exportCnpjPdf: vi.fn(),
  loadCnpjPdfReportData: vi.fn(),
  convertDocxToPdf: vi.fn(),
  downloadBlobFromResponse: vi.fn(),
  getApiErrorMessage: vi.fn(async (_, fallback) => fallback),
}))

vi.mock('@/stores/farmaciaLists', () => ({ useFarmaciaListsStore: () => mocks.farmaciaLists }))
vi.mock('@/stores/filters', () => ({ useFilterStore: () => mocks.filters }))
vi.mock('@/stores/geo', () => ({ useGeoStore: () => mocks.geo }))
vi.mock('@/stores/notaTecnicaConfig', () => ({ useNotaTecnicaConfigStore: () => mocks.notaTecnica }))
vi.mock('@/stores/evidencias', () => ({ useEvidenciasStore: () => mocks.evidencias }))
vi.mock('@/stores/metodologiaConfig', () => ({ useMetodologiaConfigStore: () => mocks.metodologia }))
vi.mock('@/stores/theme', () => ({ useThemeStore: () => mocks.theme }))
vi.mock('@/stores/analytics', () => ({ requestResumo: mocks.requestResumo }))
vi.mock('@/composables/useFormatting', () => ({
  useFormatting: () => ({
    formatCurrencyFull: (value) => `R$ ${value}`,
    formatNumberFull: (value) => String(value),
    formatarData: (value) => String(value ?? '—'),
    formatTitleCase: (value) => value,
  }),
}))
vi.mock('@/composables/useFilterParameters', () => ({
  useFilterParameters: () => ({ getApiParams: () => mocks.apiParams ?? ({ inicio: '2025-01', fim: '2025-12' }) }),
}))
vi.mock('@/composables/usePdfExport', () => ({ usePdfExport: () => ({ exportCnpjPdf: mocks.exportCnpjPdf }) }))
vi.mock('@/composables/useCnpjPdfReportData', () => ({ loadCnpjPdfReportData: mocks.loadCnpjPdfReportData }))
vi.mock('@/composables/usePeriodoAnalise', () => ({
  usePeriodoAnalise: () => ({
    PERIODO_MIN: new Date('2020-01-01T12:00:00').getTime(),
    PERIODO_MAX: new Date('2025-12-31T12:00:00').getTime(),
    periodoAtalhos: [],
    periodoSelecionado: { inicio: new Date('2025-01-01T12:00:00').getTime(), fim: new Date('2025-12-31T12:00:00').getTime() },
    periodoAtalhoAtivo: null,
    aplicarPeriodo: vi.fn(),
    aplicarAtalhoPeriodo: vi.fn(),
  }),
}))
vi.mock('@/utils/apiErrors', () => ({ getApiErrorMessage: mocks.getApiErrorMessage }))
vi.mock('@/utils/download', () => ({
  convertDocxToPdf: mocks.convertDocxToPdf,
  downloadBlobFromResponse: mocks.downloadBlobFromResponse,
}))
vi.mock('@/utils/evidencias', () => ({ dataHoraCurta: vi.fn(() => 'data recente') }))
vi.mock('primevue/usetoast', () => ({ useToast: () => ({ add: mocks.toastAdd }) }))

const ESTABLISHMENT_A = {
  cnpj: '12345678000195',
  razaoSocial: 'Farmácia Alfa',
  observacao: 'Conferir documentação',
  adicionadoEm: '2025-01-10T12:00:00',
}
const ESTABLISHMENT_B = {
  cnpj: '98765432000198',
  razaoSocial: 'Farmácia Beta',
  observacao: '',
  adicionadoEm: '2025-01-11T12:00:00',
}
const ESTABLISHMENT_C = {
  cnpj: '11222333000181',
  razaoSocial: '',
  observacao: '',
  adicionadoEm: null,
}
const ESTABLISHMENT_D = {
  cnpj: '99888777000166',
  razaoSocial: 'Farmácia Delta',
  observacao: 'Revisar contrato',
  adicionadoEm: null,
}

describe('WatchlistView — lista, consulta analítica, busca e ordenação', () => {
  let router
  let wrapper

  beforeEach(async () => {
    vi.clearAllMocks()
    localStorage.clear()
    mocks.farmaciaLists = reactive({
      interesse: [],
      ultimaRemocao: [],
      ultimaRemocaoError: null,
      loadState: 'ready',
      error: null,
      recoveryError: null,
      localRecoveryAvailable: false,
      recoveryAvailable: false,
      recoveryOptions: {},
      localSnapshot: [],
      saving: false,
      canEdit: true,
      loadRecoveryOptions: vi.fn().mockResolvedValue(),
      loadFromBackend: vi.fn().mockResolvedValue(),
      toggleInteresse: vi.fn().mockResolvedValue(),
      desfazerRemocao: vi.fn().mockResolvedValue(),
      restoreFromFile: vi.fn().mockResolvedValue(),
      restoreFromLocal: vi.fn().mockResolvedValue(),
    })
    mocks.filters = reactive({ periodo: [new Date('2025-01-01T12:00:00'), new Date('2025-12-31T12:00:00')] })
    mocks.geo = reactive({ localidades: [] })
    mocks.notaTecnica = reactive({
      loaded: true,
      loading: false,
      selectedRegionalCodigo: 'RO',
      selectedRegionalLabel: 'RO - Rondônia',
      ensureLoaded: vi.fn().mockResolvedValue(),
    })
    mocks.evidencias = reactive({
      loadState: 'ready',
      painelAberto: false,
      contar: vi.fn(() => 0),
      ultimaEm: vi.fn(() => null),
      garantirCarregado: vi.fn(),
    })
    mocks.metodologia = reactive({
      loaded: true,
      auditHighValue: 10000,
      ensureLoaded: vi.fn().mockResolvedValue(),
    })
    mocks.theme = reactive({ isDark: false })
    mocks.requestResumo.mockResolvedValue({ resultado_cnpjs: [] })
    mocks.exportCnpjPdf.mockResolvedValue()
    mocks.loadCnpjPdfReportData.mockReset()
    mocks.loadCnpjPdfReportData.mockResolvedValue({ report: true })
    mocks.convertDocxToPdf.mockReset()
    mocks.downloadBlobFromResponse.mockReset()
    mocks.getApiErrorMessage.mockReset()
    mocks.getApiErrorMessage.mockImplementation(async (_, fallback) => fallback)
    mocks.apiParams = null
    mocks.toastAdd.mockReset()

    router = createRouter({
      history: createMemoryHistory(),
      routes: [
        { path: '/listas', name: 'Watchlist', component: WatchlistView },
        { path: '/estabelecimentos', name: 'Establishments', component: { template: '<div />' } },
      ],
    })
    await router.push('/listas')
    await router.isReady()
  })

  afterEach(() => {
    wrapper?.unmount()
    wrapper = null
    vi.restoreAllMocks()
    vi.unstubAllGlobals()
    localStorage.clear()
  })

  function mountView(options = {}) {
    wrapper = shallowMount(WatchlistView, {
      ...options,
      global: {
        plugins: [router],
        directives: { tooltip() {} },
        stubs: {
          MonthRangePicker: { template: '<div data-test="month-picker" />' },
          ExportMenuButton: {
            props: ['exportacao'],
            template: '<div data-test="export-menu" :data-motivo="exportacao.motivo"><button v-for="item in exportacao.itens[0].items" :key="item.label" :data-test="item.label.startsWith(\'Excel\') ? \'export-xlsx\' : \'export-csv\'" @click="item.command()">{{ item.label }}</button></div>',
          },
          OptionPicker: {
            props: ['valor', 'opcoes', 'rotuloAcessivel'],
            emits: ['select'],
            template: '<select :aria-label="rotuloAcessivel" :value="valor ?? \'\'" @change="$emit(\'select\', $event.target.value || null)"><option v-for="opcao in opcoes" :key="String(opcao.value)" :value="opcao.value ?? \'\'">{{ opcao.label }}</option></select>',
          },
          ObservationDialog: {
            props: ['visible', 'cnpj', 'entityName'],
            emits: ['update:visible'],
            template: '<div data-test="observation-dialog" :data-visible="visible" :data-cnpj="cnpj" :data-entity="entityName"><button @click="$emit(\'update:visible\', false)">Fechar observação</button></div>',
          },
          EvidenciasPanel: {
            props: ['cnpj', 'razaoSocial', 'contexto'],
            template: '<div data-test="evidence-panel" :data-cnpj="cnpj" :data-name="razaoSocial" :data-context="contexto" />',
          },
          NotaTecnicaRegionalDialog: {
            props: ['visible', 'continueLabel'],
            emits: ['update:visible', 'saved'],
            template: '<div data-test="regional-dialog" :data-visible="visible" :data-label="continueLabel"><button data-test="close-regional" @click="$emit(\'update:visible\', false)">Fechar regional</button><button data-test="save-regional" @click="$emit(\'saved\', { numeroNota: \'NT 002/2026\', numeroProcesso: \'11111.111111/2026-11\', assinantesTecnicos: [{ nome: \'Equipe\', cargo: \'Auditor\' }], gerarPdf: false })">Salvar regional</button><button data-test="save-without-optional-fields" @click="$emit(\'saved\', { gerarPdf: false })">Salvar sem dados opcionais</button><button data-test="save-with-preview" @click="$emit(\'saved\', { numeroNota: \'NT 003/2026\', numeroProcesso: null, assinantesTecnicos: [{ nome: \'Equipe Técnica\', cargo: \'Auditora Federal\' }], gerarPdf: true })">Salvar e preparar visualização</button></div>',
          },
        },
      },
    })
    return wrapper
  }

  it('exibe lista vazia e navega para a busca de estabelecimentos', async () => {
    const view = mountView()
    await flushPromises()

    expect(view.text()).toContain('Nenhuma farmácia monitorada ainda')
    await view.get('.lists-botao').trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.name).toBe('Establishments')
  })

  it('consulta indicadores só para CNPJs monitorados e permite buscar e ordenar resultados', async () => {
    mocks.farmaciaLists.interesse = [ESTABLISHMENT_A, ESTABLISHMENT_B]
    mocks.requestResumo.mockResolvedValueOnce({
      resultado_cnpjs: [
        {
          cnpj: ESTABLISHMENT_A.cnpj,
          razao_social: 'Farmácia Alfa',
          municipio: 'Porto Velho',
          uf: 'RO',
          percValSemComp: 40,
          score_risco_final: 80,
          classificacao_risco: 'CRÍTICO',
          totalMov: 120000,
          valSemComp: 32000,
        },
        {
          cnpj: ESTABLISHMENT_B.cnpj,
          razao_social: 'Farmácia Beta',
          municipio: 'Ji-Paraná',
          uf: 'RO',
          percValSemComp: 20,
          score_risco_final: 30,
          classificacao_risco: 'ATENÇÃO',
          totalMov: 60000,
          valSemComp: 12000,
        },
      ],
    })
    const view = mountView()
    await flushPromises()

    expect(mocks.requestResumo).toHaveBeenCalledWith({
      cnpjs: [ESTABLISHMENT_A.cnpj, ESTABLISHMENT_B.cnpj],
      data_inicio: '2025-01',
      data_fim: '2025-12',
    }, ['cnpjs'])
    expect(view.findAll('.clickable-row')).toHaveLength(2)
    expect(view.text()).toContain('Farmácia Alfa')
    expect(view.text()).toContain('Porto Velho/RO')

    await view.get('[aria-label="Buscar na lista"]').setValue('Ji-Paraná')
    expect(view.findAll('.clickable-row')).toHaveLength(1)
    expect(view.text()).toContain('Farmácia Beta')
    expect(view.text()).not.toContain('Farmácia Alfa')

    await view.get('[aria-label="Limpar busca"]').trigger('click')
    await view.get('.th-ordenar').trigger('click')
    expect(view.findAll('.clickable-row')[0].text()).toContain('Farmácia Alfa')
  })

  it('busca sem falhar quando nome fantasia e observação estão ausentes', async () => {
    mocks.farmaciaLists.interesse = [{
      cnpj: ESTABLISHMENT_A.cnpj,
      razaoSocial: 'Farmácia Alfa',
      observacao: null,
      adicionadoEm: null,
    }]
    mocks.requestResumo.mockResolvedValueOnce({ resultado_cnpjs: [] })
    const view = mountView()
    await flushPromises()

    await view.get('[aria-label="Buscar na lista"]').setValue('sem correspondência')

    expect(view.findAll('.clickable-row')).toHaveLength(0)
    expect(view.text()).toContain('Nenhuma farmácia com estes filtros')
  })

  it('mostra esqueleto e erro da lista e permite tentar carregar de novo', async () => {
    mocks.farmaciaLists.loadState = 'loading'
    let view = mountView()
    await flushPromises()
    expect(view.get('.lists-esqueleto').exists()).toBe(true)
    expect(mocks.requestResumo).not.toHaveBeenCalled()
    wrapper?.unmount()
    wrapper = null

    mocks.farmaciaLists.loadState = 'error'
    mocks.farmaciaLists.error = 'Falha ao carregar'
    mocks.farmaciaLists.loadFromBackend.mockImplementation(async () => {
      mocks.farmaciaLists.loadState = 'ready'
      mocks.farmaciaLists.error = null
    })
    view = mountView()
    await flushPromises()
    expect(view.get('.preferences-recovery').text()).toContain('Não foi possível abrir sua lista')
    expect(view.get('.empty-state').text()).toContain('Lista indisponível')
    await view.get('.preferences-recovery-actions button').trigger('click')
    await flushPromises()
    expect(mocks.farmaciaLists.loadFromBackend).toHaveBeenCalledOnce()
    expect(mocks.notaTecnica.ensureLoaded).toHaveBeenCalledWith({ force: true })
  })

  it('silencia a indisponibilidade de preferências no aviso inicial e detalha a retentativa', async () => {
    const preferencesError = Object.assign(new Error('Preferências indisponíveis'), {
      response: { status: 503 },
      config: { url: API_ENDPOINTS.preferences },
    })
    mocks.notaTecnica.ensureLoaded.mockRejectedValue(preferencesError)
    mocks.farmaciaLists.loadState = 'error'
    mocks.farmaciaLists.loadFromBackend.mockImplementation(async () => {
      mocks.farmaciaLists.loadState = 'ready'
    })
    const view = mountView()
    await flushPromises()

    expect(mocks.toastAdd).not.toHaveBeenCalled()
    await view.get('.preferences-recovery-actions button').trigger('click')
    await flushPromises()

    expect(mocks.farmaciaLists.loadFromBackend).toHaveBeenCalledOnce()
    expect(mocks.notaTecnica.ensureLoaded).toHaveBeenCalledWith({ force: true })
    expect(mocks.toastAdd).toHaveBeenCalledWith(expect.objectContaining({
      summary: 'Regional da Nota Técnica',
      detail: 'Não foi possível carregar a regional porque as preferências continuam indisponíveis.',
    }))
  })

  it('registra a falha de carregamento da configuração metodológica', async () => {
    const warning = vi.spyOn(console, 'warn').mockImplementation(() => {})
    mocks.metodologia.ensureLoaded.mockRejectedValueOnce(new Error('Metodologia indisponível'))
    const view = mountView()
    await flushPromises()

    expect(view.get('.empty-state').exists()).toBe(true)
    expect(warning).toHaveBeenCalledWith(
      '[WatchlistView] Não foi possível carregar a configuração metodológica.',
      expect.objectContaining({ message: 'Metodologia indisponível' }),
    )
  })

  it('mostra os estados de carregamento e indisponibilidade da regional nas preferências', async () => {
    mocks.farmaciaLists.interesse = [ESTABLISHMENT_A]
    mocks.requestResumo.mockResolvedValueOnce({ resultado_cnpjs: [] })
    mocks.notaTecnica.loaded = false
    mocks.notaTecnica.loading = true
    const view = mountView()
    await flushPromises()

    const regionalButton = () => view.get('.lists-rodape .lists-link')
    expect(regionalButton().text()).toContain('Carregando regional da NT...')
    mocks.notaTecnica.loading = false
    await view.vm.$nextTick()
    expect(regionalButton().text()).toContain('Regional da NT indisponível')
  })

  it('exibe os erros das cópias de recuperação disponíveis para conferência', async () => {
    mocks.farmaciaLists.loadState = 'error'
    mocks.farmaciaLists.recoveryOptions = {
      backup: { error: 'Backup ilegível', watchlist_count: 0 },
      corrupt: { evidencias_error: 'Cópia de evidências incompleta', watchlist_count: 0 },
    }
    const view = mountView()
    await flushPromises()

    expect(view.text()).toContain('Backup ilegível')
    expect(view.text()).toContain('Cópia de evidências incompleta')
  })

  it('apresenta o detalhe de erro ao carregar a regional da Nota Técnica', async () => {
    mocks.notaTecnica.ensureLoaded.mockRejectedValue({
      response: { status: 500, data: { detail: 'Serviço de regionais indisponível' } },
      config: { url: '/api/v1/preferences' },
    })
    mocks.farmaciaLists.interesse = [ESTABLISHMENT_A]
    mocks.requestResumo.mockResolvedValueOnce({ resultado_cnpjs: [] })
    const view = mountView()
    await flushPromises()

    expect(view.get('.clickable-row').exists()).toBe(true)
    expect(mocks.toastAdd).toHaveBeenCalledWith(expect.objectContaining({
      summary: 'Regional da Nota Técnica', detail: 'Serviço de regionais indisponível',
    }))
  })

  it('recupera indicadores após erro analítico e refaz a consulta com período ausente', async () => {
    mocks.farmaciaLists.interesse = [ESTABLISHMENT_A]
    mocks.requestResumo.mockRejectedValueOnce(new Error('Sem conexão'))
      .mockResolvedValueOnce({ resultado_cnpjs: [{ cnpj: ESTABLISHMENT_A.cnpj, razao_social: 'Farmácia Alfa' }] })
    mocks.apiParams = {}
    const errorSpy = vi.spyOn(console, 'error').mockImplementation(() => {})
    const view = mountView()
    await flushPromises()

    expect(view.get('[role="alert"]').text()).toContain('Não foi possível carregar os indicadores da lista')
    expect(errorSpy).toHaveBeenCalled()
    await view.get('[role="alert"] .lists-link').trigger('click')
    await flushPromises()
    expect(mocks.requestResumo).toHaveBeenNthCalledWith(1, { cnpjs: [ESTABLISHMENT_A.cnpj] }, ['cnpjs'])
    expect(mocks.requestResumo).toHaveBeenNthCalledWith(2, { cnpjs: [ESTABLISHMENT_A.cnpj] }, ['cnpjs'])
    expect(view.find('.lists-estado--erro').exists()).toBe(false)
  })

  it('filtra por risco, UF, evidências, observação e busca normalizada', async () => {
    mocks.farmaciaLists.interesse = [ESTABLISHMENT_A, ESTABLISHMENT_B, ESTABLISHMENT_C, ESTABLISHMENT_D]
    mocks.evidencias.contar = vi.fn((cnpj) => cnpj === ESTABLISHMENT_A.cnpj ? 2 : 0)
    mocks.requestResumo.mockResolvedValueOnce({
      resultado_cnpjs: [
        { cnpj: ESTABLISHMENT_A.cnpj, razao_social: 'Farmácia Alfa', municipio: 'Porto Velho', uf: 'RO', percValSemComp: 60, score_risco_final: 80, classificacao_risco: 'CRÍTICO', totalMov: 120000, valSemComp: 32000 },
        { cnpj: ESTABLISHMENT_B.cnpj, razao_social: 'Farmácia Beta', municipio: 'Ji-Paraná', uf: 'RO', percValSemComp: 20, score_risco_final: 30, classificacao_risco: 'ATENÇÃO', totalMov: 60000, valSemComp: 12000 },
        { cnpj: ESTABLISHMENT_C.cnpj, razao_social: 'Farmácia Gama', nome_fantasia: 'Gama Popular', municipio: 'Rio Branco', uf: 'AC', percValSemComp: 10, score_risco_final: 10, classificacao_risco: 'NORMAL', totalMov: 0, valSemComp: 0 },
      ],
    })
    const view = mountView()
    await flushPromises()

    expect(view.findAll('.clickable-row')).toHaveLength(4)
    expect(view.get('.lists-total-valor').text()).toBe('4')
    expect(view.text()).toContain('3 de 4 com dados no período')
    expect(view.text()).toContain('24,4%')

    const riskChips = view.findAll('.risco-chip')
    await riskChips.find((chip) => chip.text().includes('Crítico')).trigger('click')
    expect(view.findAll('.clickable-row')).toHaveLength(1)
    expect(view.text()).toContain('Farmácia Alfa')
    await riskChips.find((chip) => chip.text().includes('Crítico')).trigger('click')
    expect(view.findAll('.clickable-row')).toHaveLength(4)
    await riskChips.find((chip) => chip.text().includes('Crítico')).trigger('click')
    await view.get('.lists-link').trigger('click')

    await view.get('select[aria-label="Filtrar por UF"]').setValue('RO')
    expect(view.findAll('.clickable-row')).toHaveLength(2)
    await view.get('select[aria-label="Filtrar por UF"]').setValue('')

    await view.get('.lists-chave').trigger('click')
    expect(view.findAll('.clickable-row')).toHaveLength(1)
    expect(view.text()).toContain('Farmácia Alfa')
    await view.get('.lists-chave').trigger('click')
    await view.findAll('.lists-chave')[1].trigger('click')
    expect(view.findAll('.clickable-row')).toHaveLength(2)
    await view.findAll('.lists-chave')[1].trigger('click')

    await view.get('[aria-label="Buscar na lista"]').setValue('FARMACIA ALFA')
    expect(view.findAll('.clickable-row')).toHaveLength(1)
    await view.get('[aria-label="Buscar na lista"]').setValue('112')
    expect(view.findAll('.clickable-row')).toHaveLength(1)
    await view.get('[aria-label="Buscar na lista"]').setValue('sem correspondente')
    expect(view.findAll('.clickable-row')).toHaveLength(0)
    expect(view.get('.empty-state').text()).toContain('Nenhuma farmácia com estes filtros')
    await view.get('.empty-state .lists-botao').trigger('click')
    expect(view.findAll('.clickable-row')).toHaveLength(4)
  })

  it('refaz a consulta quando mudam os CNPJs ou o período de análise', async () => {
    mocks.farmaciaLists.interesse = [ESTABLISHMENT_A]
    mocks.requestResumo.mockResolvedValue({ resultado_cnpjs: [] })
    const view = mountView()
    await flushPromises()
    expect(mocks.requestResumo).toHaveBeenCalledOnce()

    mocks.farmaciaLists.interesse = [ESTABLISHMENT_A, ESTABLISHMENT_B]
    await flushPromises()
    expect(mocks.requestResumo).toHaveBeenCalledTimes(2)
    expect(mocks.requestResumo).toHaveBeenLastCalledWith({
      cnpjs: [ESTABLISHMENT_A.cnpj, ESTABLISHMENT_B.cnpj],
      data_inicio: '2025-01',
      data_fim: '2025-12',
    }, ['cnpjs'])

    mocks.filters.periodo = [new Date('2024-01-01T12:00:00'), new Date('2024-12-31T12:00:00')]
    await flushPromises()
    expect(mocks.requestResumo).toHaveBeenCalledTimes(3)
    expect(view.findAll('.clickable-row')).toHaveLength(2)
  })

  it('mostra o período indefinido e consulta sem datas quando o filtro é limpo', async () => {
    mocks.farmaciaLists.interesse = [ESTABLISHMENT_A]
    mocks.filters.periodo = null
    mocks.apiParams = {}
    mocks.requestResumo.mockResolvedValueOnce({ resultado_cnpjs: [] })

    const view = mountView()
    await flushPromises()

    expect(view.get('[data-test="export-menu"]').attributes('data-motivo')).toBe('Período de análise não definido.')
    expect(mocks.requestResumo).toHaveBeenCalledWith({ cnpjs: [ESTABLISHMENT_A.cnpj] }, ['cnpjs'])
  })

  it('agrupa por UF ou risco, alterna densidade e restaura preferências válidas', async () => {
    localStorage.setItem('sentinela_listas_visao', JSON.stringify({
      ordenacao: { coluna: null, sentido: null },
      filtroClasses: ['CRÍTICO', 'INVALIDA'],
      filtroUf: 'RO',
      soComEvidencias: true,
      soComObservacao: false,
      agruparPor: 'uf',
      densidade: 'compacta',
    }))
    mocks.farmaciaLists.interesse = [ESTABLISHMENT_A, ESTABLISHMENT_B, ESTABLISHMENT_C, ESTABLISHMENT_D]
    mocks.evidencias.contar = vi.fn((cnpj) => cnpj === ESTABLISHMENT_A.cnpj ? 1 : 0)
    mocks.requestResumo.mockResolvedValueOnce({
      resultado_cnpjs: [
        { cnpj: ESTABLISHMENT_A.cnpj, razao_social: 'Farmácia Alfa', uf: 'RO', classificacao_risco: 'CRÍTICO', totalMov: 100, valSemComp: 20 },
        { cnpj: ESTABLISHMENT_B.cnpj, razao_social: 'Farmácia Beta', uf: 'RO', classificacao_risco: 'ATENÇÃO', totalMov: 200, valSemComp: 40 },
        { cnpj: ESTABLISHMENT_C.cnpj, razao_social: 'Farmácia Gama', uf: 'AC', classificacao_risco: 'NORMAL', totalMov: 0, valSemComp: 0 },
      ],
    })
    const view = mountView()
    await flushPromises()

    expect(view.get('.lists-card').classes()).toContain('is-compacta')
    expect(view.findAll('.grupo-linha')).toHaveLength(1)
    expect(view.get('.grupo-linha').text()).toContain('RO')
    expect(view.findAll('.clickable-row')).toHaveLength(1)

    await view.get('select[aria-label="Agrupar a tabela por"]').setValue('classificacao')
    expect(view.findAll('.grupo-linha')).toHaveLength(1)
    expect(view.get('.grupo-linha').text()).toContain('Crítico')
    await view.get('[aria-label="Usar linhas confortáveis"]').trigger('click')
    expect(view.get('.lists-card').classes()).not.toContain('is-compacta')
    expect(JSON.parse(localStorage.getItem('sentinela_listas_visao')).densidade).toBe('confortavel')
  })

  it('solta uma UF salva que saiu dos dados e mantém o grupo sem UF', async () => {
    localStorage.setItem('sentinela_listas_visao', JSON.stringify({
      ordenacao: { coluna: null, sentido: null },
      filtroClasses: [],
      filtroUf: 'ZZ',
      soComEvidencias: false,
      soComObservacao: false,
      agruparPor: 'uf',
      densidade: 'confortavel',
    }))
    mocks.farmaciaLists.interesse = [ESTABLISHMENT_A, ESTABLISHMENT_D]
    mocks.requestResumo.mockResolvedValueOnce({ resultado_cnpjs: [
      { cnpj: ESTABLISHMENT_A.cnpj, razao_social: 'Farmácia Alfa', uf: 'RO', totalMov: 100, valSemComp: 20 },
    ] })

    const view = mountView()
    await flushPromises()

    expect(view.get('select[aria-label="Filtrar por UF"]').element.value).toBe('')
    expect(view.findAll('.clickable-row')).toHaveLength(2)
    const groups = view.findAll('.grupo-linha').map((row) => row.text())
    expect(groups[0]).toContain('RO')
    expect(groups[1]).toContain('Sem UF')
    expect(view.findAll('.grupo-linha')[1].text()).not.toContain('R$')
  })

  it('usa o limite financeiro padrão e as cores de alerta do tema escuro', async () => {
    mocks.farmaciaLists.interesse = [ESTABLISHMENT_A]
    mocks.metodologia.loaded = false
    mocks.metodologia.auditHighValue = 999999999
    mocks.theme.isDark = true
    mocks.requestResumo.mockResolvedValueOnce({ resultado_cnpjs: [
      { cnpj: ESTABLISHMENT_A.cnpj, razao_social: 'Farmácia Alfa', uf: 'RO', totalMov: 20000, valSemComp: AUDIT_THRESHOLDS.HIGH_VALUE },
    ] })

    const view = mountView()
    await flushPromises()

    expect(view.get('.high-value-audit').exists()).toBe(true)
    expect(view.get('.lists-card').element.style.getPropertyValue('--alerta-cor')).toBe(CRM_ALERTA_BADGE_TONS.dark.cor)
  })

  it('ordena colunas numéricas e textuais e mantém valores ausentes no fim', async () => {
    const missingValues = { ...ESTABLISHMENT_D, cnpj: '11111222000185', razaoSocial: 'Farmácia Épsilon' }
    mocks.farmaciaLists.interesse = [ESTABLISHMENT_A, ESTABLISHMENT_B, ESTABLISHMENT_C, missingValues, ESTABLISHMENT_D]
    mocks.requestResumo.mockResolvedValueOnce({
      resultado_cnpjs: [
        { cnpj: ESTABLISHMENT_A.cnpj, razao_social: 'Farmácia Alfa', municipio: 'Porto Velho', uf: 'RO', score_risco_final: 80, totalMov: 120, valSemComp: 30, classificacao_risco: 'CRÍTICO' },
        { cnpj: ESTABLISHMENT_B.cnpj, razao_social: 'Farmácia Beta', municipio: 'Ji-Paraná', uf: 'RO', score_risco_final: 30, totalMov: 60, valSemComp: 12, classificacao_risco: 'ATENÇÃO' },
        { cnpj: ESTABLISHMENT_C.cnpj, razao_social: 'Farmácia Gama', municipio: 'Rio Branco', uf: 'AC', score_risco_final: 10, totalMov: 0, valSemComp: 0, classificacao_risco: 'NORMAL' },
      ],
    })
    const view = mountView()
    await flushPromises()
    const findSortButton = (label) => view.findAll('.th-ordenar').find((button) => button.text().includes(label))
    const firstName = () => view.find('.clickable-row .estab-nome').text()

    await findSortButton('Estabelecimento').trigger('click')
    expect(firstName()).toBe('Farmácia Alfa')
    await findSortButton('Estabelecimento').trigger('click')
    expect(firstName()).toBe('Farmácia Gama')
    await findSortButton('Estabelecimento').trigger('click')
    expect(firstName()).toBe('Farmácia Alfa')

    await findSortButton('Total mov.').trigger('click')
    expect(firstName()).toBe('Farmácia Alfa')
    expect(view.findAll('.clickable-row').at(-1).text()).toContain('Farmácia Delta')
    await findSortButton('Total mov.').trigger('click')
    expect(firstName()).toBe('Farmácia Gama')
    await findSortButton('Total mov.').trigger('click')
    expect(firstName()).toBe('Farmácia Alfa')
    view.vm.$.setupState.ordenarPor('localizacao')
    await view.vm.$nextTick()
    expect(firstName()).toBe('Farmácia Beta')
    await findSortButton('Risco').trigger('click')
    expect(firstName()).toBe('Farmácia Alfa')
    await findSortButton('Evidências').trigger('click')
    await findSortButton('Adicionada em').trigger('click')
    await findSortButton('Sem comprovação').trigger('click')
    expect(view.findAll('.clickable-row').at(-1).text()).toContain('Farmácia Delta')
  })

  it('abre detalhes, copia CNPJ, mostra evidências e permite editar e remover', async () => {
    mocks.farmaciaLists.interesse = [ESTABLISHMENT_A, ESTABLISHMENT_B]
    mocks.requestResumo.mockResolvedValueOnce({
      resultado_cnpjs: [
        { cnpj: ESTABLISHMENT_A.cnpj, razao_social: 'Farmácia Alfa', municipio: 'Porto Velho', uf: 'RO', score_risco_final: 80, classificacao_risco: 'CRÍTICO', totalMov: 120000, valSemComp: 32000, percValSemComp: 60 },
        { cnpj: ESTABLISHMENT_B.cnpj, razao_social: 'Farmácia Beta', municipio: 'Ji-Paraná', uf: 'RO' },
      ],
    })
    mocks.evidencias.contar = vi.fn((cnpj) => cnpj === ESTABLISHMENT_A.cnpj ? 2 : 0)
    mocks.evidencias.ultimaEm = vi.fn(() => '2025-02-03T10:30:00')
    const writeText = vi.fn().mockResolvedValue()
    vi.stubGlobal('navigator', Object.assign(Object.create(navigator), { clipboard: { writeText } }))
    const view = mountView()
    await flushPromises()

    expect(view.get('.high-value-audit').exists()).toBe(true)
    expect(view.text()).toContain('60,0%')
    await view.get('.evid-count-btn').trigger('click')
    expect(view.get('[data-test="evidence-panel"]').attributes('data-cnpj')).toBe(ESTABLISHMENT_A.cnpj)
    expect(view.get('[data-test="evidence-panel"]').attributes('data-name')).toBe('Farmácia Alfa')

    await view.get('.obs-btn').trigger('click')
    expect(view.get('[data-test="observation-dialog"]').attributes('data-visible')).toBe('true')
    expect(view.get('[data-test="observation-dialog"]').attributes('data-cnpj')).toBe(ESTABLISHMENT_A.cnpj)
    await view.get('[data-test="observation-dialog"] button').trigger('click')
    expect(view.get('[data-test="observation-dialog"]').attributes('data-visible')).toBe('false')
    vi.useFakeTimers()
    await view.get('.copy-btn').trigger('click')
    expect(view.findAll('.copy-btn')[0].get('i').classes()).toContain('pi-check')
    await view.findAll('.copy-btn')[1].trigger('click')
    expect(view.findAll('.copy-btn')[1].get('i').classes()).toContain('pi-check')
    expect(writeText).toHaveBeenCalledWith(ESTABLISHMENT_A.cnpj)
    expect(writeText).toHaveBeenCalledWith(ESTABLISHMENT_B.cnpj)
    await vi.advanceTimersByTimeAsync(1400)
    expect(view.findAll('.copy-btn')[0].get('i').classes()).not.toContain('pi-check')
    expect(view.findAll('.copy-btn')[1].get('i').classes()).not.toContain('pi-check')
    vi.useRealTimers()
    await view.get('.action-btn.remove').trigger('click')
    expect(mocks.farmaciaLists.toggleInteresse).toHaveBeenCalledWith(ESTABLISHMENT_A.cnpj, '')
    await view.get('.action-btn.open').trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.fullPath).toBe(`/estabelecimentos/${ESTABLISHMENT_A.cnpj}`)

    await router.push('/listas')
    await flushPromises()
    await view.get('.clickable-row').trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.fullPath).toBe(`/estabelecimentos/${ESTABLISHMENT_A.cnpj}`)
    await router.push('/listas')
    await flushPromises()
    await view.get('.clickable-row').trigger('keydown', { key: 'Enter' })
    await flushPromises()
    expect(router.currentRoute.value.fullPath).toBe(`/estabelecimentos/${ESTABLISHMENT_A.cnpj}`)
    await router.push('/listas')
    await flushPromises()
    await view.get('.clickable-row').trigger('keydown', { key: ' ' })
    await flushPromises()
    expect(router.currentRoute.value.fullPath).toBe(`/estabelecimentos/${ESTABLISHMENT_A.cnpj}`)

    await router.push('/listas')
    await flushPromises()
    await view.get('.lists-rodape .lists-link').trigger('click')
    expect(view.get('[data-test="regional-dialog"]').attributes('data-visible')).toBe('true')
    await view.get('[data-test="close-regional"]').trigger('click')
    expect(view.get('[data-test="regional-dialog"]').attributes('data-visible')).toBe('false')
  })

  it('desfaz uma remoção, restaura arquivos e cópia local após confirmação', async () => {
    mocks.farmaciaLists.interesse = [ESTABLISHMENT_A]
    mocks.farmaciaLists.ultimaRemocao = [
      { cnpj: ESTABLISHMENT_B.cnpj, razaoSocial: '', evidencias_count: 2 },
      { cnpj: ESTABLISHMENT_C.cnpj, razaoSocial: 'Farmácia Gama', evidencias_count: 0 },
      { cnpj: ESTABLISHMENT_D.cnpj, razaoSocial: 'Farmácia Delta', evidencias_count: 0 },
    ]
    mocks.farmaciaLists.recoveryAvailable = true
    mocks.farmaciaLists.localRecoveryAvailable = true
    mocks.farmaciaLists.localSnapshot = [ESTABLISHMENT_A]
    mocks.farmaciaLists.recoveryOptions = {
      principal: { evidencias_error: 'Cesta atual inválida' },
      backup: { valid: true, watchlist_count: 1, evidencias_count: null, evidencias_backup_valid: false, farmacias_mantidas_count: 0 },
      corrupt: { valid: true, watchlist_count: 2, evidencias_count: 1, evidencias_backup_valid: true, farmacias_mantidas_count: 3 },
    }
    mocks.farmaciaLists.desfazerRemocao.mockResolvedValueOnce(true).mockResolvedValueOnce(true).mockResolvedValueOnce(false)
    mocks.farmaciaLists.restoreFromFile.mockResolvedValueOnce(false).mockResolvedValueOnce(true)
    mocks.farmaciaLists.restoreFromLocal.mockResolvedValueOnce(true)
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(true)
    const view = mountView()
    await flushPromises()

    expect(view.get('.lists-undo').text()).toContain('98.765.432/0001-98 removida da lista (2 evidência(s))')
    await view.findAll('.lists-undo-btn')[0].trigger('click')
    expect(mocks.farmaciaLists.desfazerRemocao).toHaveBeenCalledWith(ESTABLISHMENT_B.cnpj)
    expect(mocks.toastAdd).toHaveBeenCalledWith(expect.objectContaining({
      summary: 'Remoção desfeita', detail: expect.stringContaining('2 evidência(s)'),
    }))
    await view.findAll('.lists-undo-btn')[1].trigger('click')
    expect(mocks.toastAdd).toHaveBeenCalledWith(expect.objectContaining({
      summary: 'Remoção desfeita', detail: 'Farmácia Gama voltou à lista.',
    }))
    await view.findAll('.lists-undo-btn')[2].trigger('click')
    expect(mocks.toastAdd).toHaveBeenCalledTimes(2)

    await view.get('.preferences-recovery-actions button').trigger('click')
    expect(confirm).toHaveBeenCalledWith(expect.stringContaining('somente a lista'))
    expect(mocks.farmaciaLists.restoreFromFile).toHaveBeenCalledWith('backup', false)
    expect(mocks.notaTecnica.ensureLoaded).not.toHaveBeenCalledWith({ force: true })
    await view.findAll('.preferences-recovery-actions button')[1].trigger('click')
    expect(confirm).toHaveBeenCalledWith(expect.stringContaining('será arquivada e substituída'))
    expect(confirm).toHaveBeenLastCalledWith(expect.stringContaining('continuarão na lista'))
    expect(mocks.farmaciaLists.restoreFromFile).toHaveBeenCalledWith('corrupt', true)
    expect(mocks.notaTecnica.ensureLoaded).toHaveBeenCalledWith({ force: true })

    mocks.farmaciaLists.recoveryOptions.principal.evidencias_error = null
    await view.findAll('.preferences-recovery-actions button')[1].trigger('click')
    expect(confirm).toHaveBeenLastCalledWith(expect.stringContaining('As evidências ausentes serão recuperadas do backup'))

    await view.findAll('.preferences-recovery-actions button')[2].trigger('click')
    expect(confirm).toHaveBeenCalledWith(expect.stringContaining('Restaurar 1 farmácia(s) da cópia local'))
    expect(mocks.farmaciaLists.restoreFromLocal).toHaveBeenCalledOnce()
  })

  it('exporta Excel e CSV e informa sucesso, falha e formato inválido', async () => {
    mocks.farmaciaLists.interesse = [ESTABLISHMENT_A]
    mocks.requestResumo.mockResolvedValueOnce({ resultado_cnpjs: [] })
    const fetchMock = vi.fn().mockResolvedValue({ ok: true })
    vi.stubGlobal('fetch', fetchMock)
    mocks.downloadBlobFromResponse.mockResolvedValueOnce({ filename: 'farmacias_monitoradas.xlsx' })
      .mockResolvedValueOnce({ desktop: true, filename: 'farmacias_monitoradas.csv', path: 'C:/export/farmacias.csv' })
    const view = mountView()
    await flushPromises()

    await view.get('[data-test="export-xlsx"]').trigger('click')
    expect(fetchMock).toHaveBeenNthCalledWith(1, expect.anything(), expect.objectContaining({ method: 'POST' }))
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({ formato: 'xlsx', data_inicio: '2025-01', data_fim: '2025-12' })
    expect(mocks.downloadBlobFromResponse).toHaveBeenNthCalledWith(1, { ok: true }, 'farmacias_monitoradas.xlsx')
    expect(mocks.toastAdd).toHaveBeenCalledWith(expect.objectContaining({ summary: 'Excel da lista baixado' }))

    await view.get('[data-test="export-csv"]').trigger('click')
    expect(mocks.toastAdd).toHaveBeenCalledWith(expect.objectContaining({
      summary: 'CSV da lista salvo', data: { path: 'C:/export/farmacias.csv', icon: 'pi-file' },
    }))

    fetchMock.mockResolvedValueOnce({ ok: false, status: 502 })
    mocks.getApiErrorMessage.mockResolvedValueOnce('Servidor recusou o arquivo')
    await view.get('[data-test="export-xlsx"]').trigger('click')
    expect(mocks.toastAdd).toHaveBeenCalledWith(expect.objectContaining({ summary: 'Falha na exportação', detail: 'Servidor recusou o arquivo' }))
    expect(view.vm.$.setupState.exportarLista).toBeTypeOf('function')
    await expect(view.vm.$.setupState.exportarLista('pdf')).rejects.toThrow('Formato de exportação desconhecido: pdf')
  })

  it('gera relatórios e notas e apresenta falhas de download', async () => {
    mocks.farmaciaLists.interesse = [ESTABLISHMENT_A]
    mocks.requestResumo.mockResolvedValueOnce({ resultado_cnpjs: [] })
    const fetchMock = vi.fn().mockResolvedValue({ ok: true })
    vi.stubGlobal('fetch', fetchMock)
    mocks.exportCnpjPdf.mockResolvedValue({ desktop: false })
    mocks.downloadBlobFromResponse.mockResolvedValue({ desktop: false, filename: 'nota.docx' })
    const view = mountView()
    await flushPromises()

    await view.get('.action-btn.report').trigger('click')
    await flushPromises()
    expect(mocks.loadCnpjPdfReportData).toHaveBeenCalledWith(expect.objectContaining({ cnpj: ESTABLISHMENT_A.cnpj }))
    expect(mocks.exportCnpjPdf).toHaveBeenCalled()
    expect(mocks.toastAdd).not.toHaveBeenCalledWith(expect.objectContaining({ summary: 'Relatório PDF salvo' }))

    await view.get('.action-btn.note').trigger('click')
    await flushPromises()
    expect(view.get('[data-test="regional-dialog"]').attributes('data-visible')).toBe('true')
    await view.get('[data-test="close-regional"]').trigger('click')
    await view.get('[data-test="save-without-optional-fields"]').trigger('click')
    await flushPromises()
    expect(fetchMock).not.toHaveBeenCalled()

    await view.get('.action-btn.note').trigger('click')
    await flushPromises()
    await view.get('[data-test="save-without-optional-fields"]').trigger('click')
    await flushPromises()
    expect(fetchMock).toHaveBeenCalled()
    expect(fetchMock.mock.calls[0][0]).toContain(`regional_codigo=RO`)
    expect(fetchMock.mock.calls[0][0]).not.toContain('numero_nota=')
    expect(fetchMock.mock.calls[0][0]).not.toContain('numero_processo=')
    expect(fetchMock.mock.calls[0][0]).not.toContain('assinantes_tecnicos=')
    expect(mocks.downloadBlobFromResponse).toHaveBeenCalledWith({ ok: true }, `Nota_Tecnica_${ESTABLISHMENT_A.cnpj}.docx`)
    expect(mocks.convertDocxToPdf).not.toHaveBeenCalled()

    mocks.exportCnpjPdf.mockRejectedValueOnce(new Error('PDF indisponível'))
    const errorSpy = vi.spyOn(console, 'error').mockImplementation(() => {})
    await view.get('.action-btn.report').trigger('click')
    await flushPromises()
    expect(mocks.toastAdd).toHaveBeenCalledWith(expect.objectContaining({ summary: 'Erro ao gerar Relatório PDF', detail: 'PDF indisponível' }))
    expect(errorSpy).toHaveBeenCalled()
  })

  it('salva o relatório em desktop e prepara a visualização da Nota Técnica', async () => {
    mocks.farmaciaLists.interesse = [ESTABLISHMENT_A]
    mocks.requestResumo.mockResolvedValueOnce({ resultado_cnpjs: [] })
    const fetchMock = vi.fn().mockResolvedValue({ ok: true })
    vi.stubGlobal('fetch', fetchMock)
    mocks.exportCnpjPdf.mockResolvedValue({
      desktop: true, filename: 'relatorio.pdf', path: 'C:/relatorios/relatorio.pdf',
    })
    mocks.downloadBlobFromResponse.mockResolvedValue({
      desktop: true, filename: 'nota.docx', path: 'C:/notas/nota.docx',
    })
    mocks.convertDocxToPdf.mockResolvedValueOnce({ path: 'C:/notas/nota.pdf' })
    const errorSpy = vi.spyOn(console, 'error').mockImplementation(() => {})
    const view = mountView()
    await flushPromises()

    await view.get('.action-btn.report').trigger('click')
    await flushPromises()
    expect(mocks.toastAdd).toHaveBeenCalledWith(expect.objectContaining({
      summary: 'Relatório PDF salvo',
      data: { path: 'C:/relatorios/relatorio.pdf', previewPath: 'C:/relatorios/relatorio.pdf' },
    }))

    await view.get('.action-btn.note').trigger('click')
    await flushPromises()
    await view.get('[data-test="save-with-preview"]').trigger('click')
    await flushPromises()
    expect(fetchMock).toHaveBeenCalledOnce()
    expect(mocks.convertDocxToPdf).toHaveBeenCalledWith('C:/notas/nota.docx')
    expect(fetchMock.mock.calls[0][0]).toContain('assinantes_tecnicos=')
    expect(mocks.toastAdd).toHaveBeenCalledWith(expect.objectContaining({
      summary: 'Nota Técnica salva',
      data: { path: 'C:/notas/nota.docx', previewPath: 'C:/notas/nota.pdf' },
    }))

    mocks.convertDocxToPdf.mockRejectedValueOnce({})
    await view.get('.action-btn.note').trigger('click')
    await flushPromises()
    await view.get('[data-test="save-with-preview"]').trigger('click')
    await flushPromises()
    expect(mocks.toastAdd).toHaveBeenCalledWith(expect.objectContaining({
      severity: 'warn',
      summary: 'Pre-visualizacao indisponivel',
      detail: 'A Nota Tecnica foi salva, mas nao foi possivel gerar a versao PDF para visualizacao.',
    }))
    expect(mocks.toastAdd).toHaveBeenCalledWith(expect.objectContaining({
      summary: 'Nota Técnica salva',
      data: { path: 'C:/notas/nota.docx', previewPath: null },
    }))

    fetchMock.mockResolvedValueOnce({ ok: false, status: 503 })
    mocks.getApiErrorMessage.mockResolvedValueOnce('API recusou a Nota Técnica')
    await view.get('.action-btn.note').trigger('click')
    await flushPromises()
    await view.get('[data-test="save-with-preview"]').trigger('click')
    await flushPromises()
    expect(mocks.toastAdd).toHaveBeenCalledWith(expect.objectContaining({
      severity: 'error', summary: 'Erro ao gerar Nota Técnica', detail: 'API recusou a Nota Técnica',
    }))
    expect(errorSpy).toHaveBeenCalled()
  })

  it('expõe falha ao renderizar uma classificação de risco desconhecida', async () => {
    mocks.farmaciaLists.interesse = [ESTABLISHMENT_A]
    mocks.requestResumo.mockResolvedValueOnce({
      resultado_cnpjs: [{ cnpj: ESTABLISHMENT_A.cnpj, classificacao_risco: 'RISCO_NOVO' }],
    })
    const errors = []
    wrapper = shallowMount(WatchlistView, {
      global: {
        plugins: [router],
        directives: { tooltip() {} },
        config: { errorHandler: (error) => errors.push(error) },
        stubs: {
          MonthRangePicker: { template: '<div />' },
          ExportMenuButton: true,
          OptionPicker: true,
          ObservationDialog: true,
          EvidenciasPanel: true,
          NotaTecnicaRegionalDialog: true,
        },
      },
    })
    await flushPromises()

    expect(errors.some((error) => error.message.includes('Classificação de risco desconhecida: RISCO_NOVO'))).toBe(true)
  })

  it('restaura configuração inválida com segurança e cobre atalhos e ordenação salva', async () => {
    localStorage.setItem('sentinela_listas_visao', '{json incompleto')
    mocks.farmaciaLists.interesse = [ESTABLISHMENT_A, ESTABLISHMENT_B]
    mocks.requestResumo.mockResolvedValueOnce({ resultado_cnpjs: [] })
    const view = mountView()
    await flushPromises()
    expect(view.findAll('.clickable-row')).toHaveLength(2)
    expect(view.find('.lists-total-aviso').exists()).toBe(false)

    localStorage.setItem('sentinela_listas_visao', JSON.stringify({
      ordenacao: { coluna: 'desconhecida', sentido: 'diagonal' },
      filtroClasses: 'CRÍTICO', filtroUf: 12, soComEvidencias: 'sim', soComObservacao: 1,
      agruparPor: 'cnpj', densidade: 'densa',
    }))
    wrapper?.unmount()
    wrapper = null
    const second = mountView({ attachTo: document.body })
    await flushPromises()
    expect(second.findAll('.clickable-row')).toHaveLength(2)

    const shortcut = new KeyboardEvent('keydown', { key: '/', bubbles: true, cancelable: true })
    window.dispatchEvent(shortcut)
    expect(shortcut.defaultPrevented).toBe(true)
    expect(document.activeElement).toBe(second.get('[aria-label="Buscar na lista"]').element)
    const ignored = new KeyboardEvent('keydown', { key: '/', altKey: true, bubbles: true, cancelable: true })
    window.dispatchEvent(ignored)
    expect(ignored.defaultPrevented).toBe(false)

    for (const modifier of [{ ctrlKey: true }, { metaKey: true }]) {
      const modified = new KeyboardEvent('keydown', { key: '/', ...modifier, bubbles: true, cancelable: true })
      window.dispatchEvent(modified)
      expect(modified.defaultPrevented).toBe(false)
    }

    const inputShortcut = new KeyboardEvent('keydown', { key: '/', bubbles: true, cancelable: true })
    second.get('[aria-label="Buscar na lista"]').element.dispatchEvent(inputShortcut)
    expect(inputShortcut.defaultPrevented).toBe(false)

    const editable = document.createElement('div')
    Object.defineProperty(editable, 'isContentEditable', { value: true })
    document.body.appendChild(editable)
    const editableShortcut = new KeyboardEvent('keydown', { key: '/', bubbles: true, cancelable: true })
    editable.dispatchEvent(editableShortcut)
    expect(editableShortcut.defaultPrevented).toBe(false)
    editable.remove()
  })

  it('cobre os formatadores, filtros derivados e estados alternativos da tela', async () => {
    mocks.farmaciaLists.interesse = [ESTABLISHMENT_A]
    mocks.requestResumo.mockResolvedValueOnce({ resultado_cnpjs: [] })
    const view = mountView()
    await flushPromises()
    const api = view.vm.$.setupState

    expect(api.formatCnpj('')).toBe('—')
    expect(api.formatCnpj('12.34')).toBe('12.34')
    expect(api.formatCnpj(ESTABLISHMENT_A.cnpj)).toBe('12.345.678/0001-95')
    expect(api.formatDate(null)).toBe('—')
    expect(api.formatPeriodMonth('data inválida')).toBe('—')
    expect(api.formatPeriodMonth('2025-01-01T12:00:00')).toContain('jan/2025')
    expect(api.normalizarTexto(null)).toBe('')
    expect(api.formatPerc(null)).toBe('—')
    expect(api.formatScore(null)).toBe('—')
    expect(api.nomeFarmacia('98765432000198')).toBe('98.765.432/0001-98')
    expect(api.corDaClasse('SEM_CLASSE')).toBe('var(--text-muted)')
    expect(api.faixaPerc(49)).toBe('is-medio')
    expect(() => api.ordenarPor('coluna-inexistente')).toThrow('Coluna não ordenável: coluna-inexistente')

    const focus = vi.fn()
    api.campoBusca = { focus }
    const preventDefault = vi.fn()
    api.atalhoBusca({ key: '/', target: document.body, preventDefault })
    expect(preventDefault).toHaveBeenCalledOnce()
    expect(focus).toHaveBeenCalledOnce()

    api.campoBusca = null
    const noSearchField = vi.fn()
    api.atalhoBusca({ key: '/', target: document.body, preventDefault: noSearchField })
    expect(noSearchField).not.toHaveBeenCalled()

    api.obsTarget = { cnpj: ESTABLISHMENT_A.cnpj, razaoSocial: '' }
    api.showObsDialog = true
    await view.vm.$nextTick()
    expect(view.get('[data-test="observation-dialog"]').attributes('data-entity')).toBe('12.345.678/0001-95')

    mocks.farmaciaLists.loadState = 'error'
    await view.vm.$nextTick()
    expect(api.regionalLabel).toBe('Regional da NT indisponível')
    mocks.farmaciaLists.loadState = 'ready'
    mocks.notaTecnica.loaded = false
    mocks.notaTecnica.loading = true
    await view.vm.$nextTick()
    expect(api.regionalLabel).toBe('Carregando regional da NT...')
    mocks.notaTecnica.loading = false
    await view.vm.$nextTick()
    expect(api.regionalLabel).toBe('Regional da NT indisponível')
    mocks.notaTecnica.loaded = true
    mocks.notaTecnica.selectedRegionalLabel = ''
    await view.vm.$nextTick()
    expect(api.regionalLabel).toBe('Regional da NT não definida')
  })

  it('protege exportações com período ausente, chamadas concorrentes e rejeições sem mensagem', async () => {
    mocks.farmaciaLists.interesse = [ESTABLISHMENT_A]
    mocks.requestResumo.mockResolvedValueOnce({ resultado_cnpjs: [] })
    const view = mountView()
    await flushPromises()
    const api = view.vm.$.setupState
    const fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)

    mocks.apiParams = {}
    await expect(api.exportarLista('xlsx')).rejects.toThrow('Exportação da lista sem período de análise.')
    expect(fetchMock).not.toHaveBeenCalled()

    mocks.apiParams = null
    let resolveResponse
    fetchMock.mockImplementationOnce(() => new Promise((resolve) => { resolveResponse = resolve }))
    const firstExport = api.exportarLista('xlsx')
    await Promise.resolve()
    expect(api.exportLoading).toBe(true)
    await expect(api.exportarLista('csv')).resolves.toBeUndefined()
    expect(fetchMock).toHaveBeenCalledOnce()
    resolveResponse({ ok: true })
    await firstExport

    fetchMock.mockRejectedValueOnce({})
    await api.exportarLista('csv')
    expect(mocks.toastAdd).toHaveBeenCalledWith(expect.objectContaining({
      severity: 'error',
      summary: 'Falha na exportação',
      detail: 'Não foi possível salvar o CSV.',
    }))
  })

  it('mostra erros de recuperação, usa plural e alterna a densidade nos dois sentidos', async () => {
    mocks.farmaciaLists.interesse = [ESTABLISHMENT_A, ESTABLISHMENT_B]
    mocks.farmaciaLists.ultimaRemocaoError = 'Não foi possível desfazer a remoção.'
    mocks.farmaciaLists.recoveryError = 'Falha ao ler a cópia de segurança.'
    mocks.requestResumo.mockResolvedValueOnce({ resultado_cnpjs: [
      { cnpj: ESTABLISHMENT_A.cnpj, razao_social: 'Farmácia Alfa', uf: 'RO', totalMov: 20, valSemComp: 10 },
      { cnpj: ESTABLISHMENT_B.cnpj, razao_social: 'Farmácia Beta', uf: 'RO', totalMov: 40, valSemComp: 20 },
    ] })
    const view = mountView()
    await flushPromises()

    expect(view.get('.lists-undo').text()).toContain('Não foi possível desfazer a remoção.')
    expect(view.get('.preferences-recovery').text()).toContain('Falha ao ler a cópia de segurança.')

    await view.get('select[aria-label="Agrupar a tabela por"]').setValue('uf')
    expect(view.get('.grupo-linha').text()).toContain('2 farmácias')

    await view.get('[aria-label="Usar linhas compactas"]').trigger('click')
    expect(view.get('.lists-card').classes()).toContain('is-compacta')
    await view.get('[aria-label="Usar linhas confortáveis"]').trigger('click')
    expect(view.get('.lists-card').classes()).not.toContain('is-compacta')

    mocks.farmaciaLists.error = 'Falha geral nas preferências.'
    await view.vm.$nextTick()
    expect(view.get('.preferences-recovery').text()).toContain('Falha geral nas preferências.')
    expect(view.get('.preferences-recovery').text()).not.toContain('Falha ao ler a cópia de segurança.')
  })

  it('restaura ordenação válida e trata falhas de persistência, filtros e regional', async () => {
    localStorage.setItem('sentinela_listas_visao', JSON.stringify({
      ordenacao: { coluna: 'estabelecimento', sentido: 'asc' },
      filtroClasses: [], filtroUf: null, soComEvidencias: false, soComObservacao: false,
      agruparPor: null, densidade: 'confortavel',
    }))
    mocks.farmaciaLists.interesse = [ESTABLISHMENT_A]
    mocks.requestResumo.mockResolvedValueOnce({ resultado_cnpjs: [
      { cnpj: ESTABLISHMENT_A.cnpj, razao_social: 'Farmácia Alfa', nome_fantasia: 'Rede Alfa' },
    ] })
    const view = mountView()
    await flushPromises()
    const api = view.vm.$.setupState

    expect(view.get('th.col-estab').attributes('aria-sort')).toBe('ascending')
    mocks.filters.periodo = null
    await view.vm.$nextTick()
    expect(api.periodoAnaliseLabel).toBe('Período não definido')
    expect(api.periodKey).toBe('')
    mocks.filters.periodo = ['2025-01', null]
    await view.vm.$nextTick()
    expect(api.periodKey).toBe('2025-01|')
    await flushPromises()

    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new Error('storage bloqueado') })
    api.densidade = 'compacta'
    await view.vm.$nextTick()
    expect(view.get('.lists-card').classes()).toContain('is-compacta')

    mocks.notaTecnica.ensureLoaded.mockRejectedValueOnce({ response: { status: 500, data: {} } })
    await api.carregarRegional()
    expect(mocks.toastAdd).toHaveBeenCalledWith(expect.objectContaining({
      summary: 'Regional da Nota Técnica',
      detail: 'Não foi possível carregar a configuração da Nota Técnica.',
    }))

    await view.get('[aria-label="Buscar na lista"]').setValue('sem resultado')
    expect(view.text()).toContain('1 farmácia está na lista')
  })

  it('ordena grupos de UF em ordem alfabética antes de agrupar as linhas sem UF', async () => {
    const noUf = { cnpj: '55555555000155', razaoSocial: '', observacao: '' }
    mocks.farmaciaLists.interesse = [noUf, ESTABLISHMENT_A, ESTABLISHMENT_B, ESTABLISHMENT_C]
    mocks.requestResumo.mockResolvedValueOnce({ resultado_cnpjs: [
      { cnpj: ESTABLISHMENT_A.cnpj, razao_social: 'Farmácia Alfa', nome_fantasia: 'Rede Alfa', uf: 'RO', totalMov: 100, valSemComp: 40 },
      { cnpj: ESTABLISHMENT_B.cnpj, razao_social: 'Farmácia Beta', uf: 'AM', totalMov: 100, valSemComp: 20 },
      { cnpj: ESTABLISHMENT_C.cnpj, razao_social: 'Farmácia Gama', uf: 'AC', totalMov: 50, valSemComp: 10 },
    ] })
    const view = mountView()
    await flushPromises()
    await view.get('select[aria-label="Agrupar a tabela por"]').setValue('uf')

    const groups = view.findAll('.grupo-linha').map((row) => row.get('.grupo-nome').text())
    expect(groups).toEqual(['AC', 'AM', 'RO', 'Sem UF'])
    const api = view.vm.$.setupState
    expect(api.listaOrdenada.map((item) => item.cnpj)[0]).toBe(ESTABLISHMENT_A.cnpj)
    api.ordenarPor('estabelecimento')
    expect(api.listaOrdenada.some((item) => item.razaoSocial === '—')).toBe(true)
    await view.get('[aria-label="Buscar na lista"]').setValue('alfa')
    expect(api.listaFiltrada.map((item) => item.cnpj)).toContain(ESTABLISHMENT_A.cnpj)
    api.busca = 'termo sem correspondência'
    expect(api.listaFiltrada).toEqual([])
  })

  it('impede relatórios e notas duplicados e apresenta erros sem mensagem', async () => {
    mocks.farmaciaLists.interesse = [ESTABLISHMENT_A]
    mocks.requestResumo.mockResolvedValueOnce({ resultado_cnpjs: [] })
    const view = mountView()
    await flushPromises()
    const api = view.vm.$.setupState
    const errorSpy = vi.spyOn(console, 'error').mockImplementation(() => {})

    let resolveReport
    mocks.exportCnpjPdf.mockImplementationOnce(() => new Promise((resolve) => { resolveReport = resolve }))
    const report = api.gerarRelatorio(ESTABLISHMENT_A)
    const duplicateReport = api.gerarRelatorio(ESTABLISHMENT_A)
    expect(mocks.loadCnpjPdfReportData).toHaveBeenCalledOnce()
    await Promise.resolve()
    resolveReport({ desktop: false })
    await Promise.all([report, duplicateReport])

    mocks.loadCnpjPdfReportData.mockRejectedValueOnce({})
    await api.gerarRelatorio(ESTABLISHMENT_A)
    expect(mocks.toastAdd).toHaveBeenCalledWith(expect.objectContaining({
      summary: 'Erro ao gerar Relatório PDF',
      detail: 'Não foi possível gerar o arquivo.',
    }))

    const fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)
    let resolveNote
    fetchMock.mockImplementationOnce(() => new Promise((resolve) => { resolveNote = resolve }))
    const noteData = {
      numeroNota: 'NT 004/2026',
      numeroProcesso: '11111.111111/2026-11',
      assinantesTecnicos: [{ nome: 'Equipe', cargo: 'Auditor' }],
      gerarPdf: false,
    }
    const note = api.gerarNotaTecnica(ESTABLISHMENT_A, { skipRegionalCheck: true, dadosNota: noteData })
    const duplicateNote = api.gerarNotaTecnica(ESTABLISHMENT_A, { skipRegionalCheck: true, dadosNota: noteData })
    expect(fetchMock).toHaveBeenCalledOnce()
    resolveNote({ ok: true })
    await Promise.all([note, duplicateNote])
    const noteUrl = new URL(fetchMock.mock.calls[0][0], 'http://sentinela.test')
    expect(noteUrl.searchParams.get('numero_processo')).toBe(noteData.numeroProcesso)

    fetchMock.mockRejectedValueOnce({})
    await api.gerarNotaTecnica(ESTABLISHMENT_A, { skipRegionalCheck: true, dadosNota: { gerarPdf: false } })
    expect(mocks.toastAdd).toHaveBeenCalledWith(expect.objectContaining({
      summary: 'Erro ao gerar Nota Técnica',
      detail: 'Não foi possível gerar o arquivo.',
    }))
    expect(errorSpy).toHaveBeenCalled()
  })
})
