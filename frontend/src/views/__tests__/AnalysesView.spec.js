import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { reactive, ref } from 'vue'

import AnalysesView from '@/views/AnalysesView.vue'

const mocks = vi.hoisted(() => ({
  filters: null,
  analysisStore: null,
  mensalStore: null,
  geoStore: null,
  analysisComposable: null,
  fetchAnalytics: vi.fn(),
}))

vi.mock('@/stores/filters', () => ({ useFilterStore: () => mocks.filters }))
vi.mock('@/stores/crmPrescricoesAnalysis', () => ({ useCrmPrescricoesAnalysisStore: () => mocks.analysisStore }))
vi.mock('@/stores/crmPrescricoesMensal', () => ({ useCrmPrescricoesMensalStore: () => mocks.mensalStore }))
vi.mock('@/stores/geo', () => ({ useGeoStore: () => mocks.geoStore }))
vi.mock('@/composables/useFetchAnalytics', () => ({ useFetchAnalytics: mocks.fetchAnalytics }))
vi.mock('@/composables/useCrmPrescricoesAnalysis', () => ({
  getCrmMapLevel: (filters) => {
    if (filters.selectedMunicipio !== 'Todos') return 'municipio'
    if (filters.selectedRegiaoSaude !== 'Todos') return 'regiao'
    if (filters.selectedUF !== 'Todos') return 'uf'
    return 'brasil'
  },
  useCrmPrescricoesAnalysis: () => mocks.analysisComposable,
}))
vi.mock('@/views/components/KpiSection.vue', () => ({ default: { template: '<section data-test="kpis" />' } }))
vi.mock('@/views/components/analises/CrmPrescricoesMap.vue', () => ({
  default: {
    props: ['mapLevel', 'mapData', 'uf', 'regiaoId', 'selectedIbge7', 'selectedRegiaoNome', 'selectedMunicipioNome', 'qtdMedicos'],
    emits: ['select-uf', 'select-municipio', 'back'],
    template: '<section data-test="crm-map" :data-level="mapLevel" :data-municipio="selectedMunicipioNome" :data-regiao="selectedRegiaoNome" :data-qtd="qtdMedicos"><button data-test="select-city" @click="$emit(\'select-municipio\', 1100015)">Selecionar município</button><button data-test="select-no-city" @click="$emit(\'select-municipio\', null)">Limpar município</button><button data-test="select-uf" @click="$emit(\'select-uf\', \'RO\')">Selecionar UF</button><button data-test="back" @click="$emit(\'back\')">Voltar</button></section>',
  },
}))
vi.mock('@/views/components/analises/CrmPrescricoesRanking.vue', () => ({
  default: {
    props: ['rows', 'escopo', 'isLoading', 'error', 'pageError', 'pageSize', 'tab', 'mensal', 'serie'],
    emits: ['select-medico', 'update:tab', 'page', 'sort', 'mensal-page', 'mensal-sort'],
    template: '<section data-test="ranking" :data-tab="tab">{{ rows.length }} médicos<button data-test="ranking-page" @click="$emit(\'page\', { first: 30, rows: 10 })">Página</button><button data-test="ranking-page-defaults" @click="$emit(\'page\', {})">Página padrão</button><button data-test="ranking-sort" @click="$emit(\'sort\', { sortField: \'nome\', sortOrder: 1 })">Ordenar</button><button data-test="ranking-sort-desc" @click="$emit(\'sort\', { sortField: \'nome\', sortOrder: -1 })">Ordenar desc</button><button data-test="ranking-sort-invalid" @click="$emit(\'sort\', { sortField: null, sortOrder: 0 })">Ordenação inválida</button><button data-test="mensal-tab" @click="$emit(\'update:tab\', \'mes\')">Por mês</button><button data-test="mensal-page" @click="$emit(\'mensal-page\', { first: 30, rows: 10 })">Página mensal</button><button data-test="mensal-page-defaults" @click="$emit(\'mensal-page\', {})">Página mensal padrão</button><button data-test="mensal-sort" @click="$emit(\'mensal-sort\', { sortField: \'periodo\', sortOrder: -1 })">Ordenar mensal</button><button data-test="mensal-sort-invalid" @click="$emit(\'mensal-sort\', { sortField: \'periodo\', sortOrder: 0 })">Ordenação mensal inválida</button><button data-test="select-doctor" @click="$emit(\'select-medico\', { id_medico: \'crm-1\', nome: \'Dra. Teste\' })">Histórico</button></section>',
  },
}))
vi.mock('@/views/components/analises/CrmHistoricoDialog.vue', () => ({
  default: {
    props: ['modelValue', 'medico', 'dataInicio', 'dataFim', 'cacheVersion'],
    emits: ['update:modelValue'],
    template: '<div data-test="history-dialog" :data-visible="modelValue" :data-medico="medico?.id_medico"><button data-test="close-history" @click="$emit(\'update:modelValue\', false)">Fechar</button></div>',
  },
}))
vi.mock('@/views/components/analises/AnalysisSidebar.vue', () => ({
  default: {
    props: ['searchQuery', 'searchDisabled'],
    emits: ['search'],
    template: '<aside><slot name="header-acoes" /><input data-test="crm-search" :value="searchQuery" @input="$emit(\'search\', $event.target.value)" /></aside>',
  },
}))

describe('AnalysesView — mapa e ranking CRM', () => {
  let wrapper

  beforeEach(() => {
    vi.useFakeTimers()
    mocks.fetchAnalytics.mockReset()
    mocks.filters = reactive({
      selectedUF: 'Todos',
      selectedRegiaoSaude: 'Todos',
      selectedMunicipio: 'Todos',
      apiParams: { inicio: '2024-01-01', fim: '2024-12-31' },
    })
    mocks.analysisStore = reactive({
      cacheVersion: null,
      activeParams: null,
      setRankingSearch: vi.fn(),
    })
    mocks.mensalStore = reactive({
      tab: ref('resumo'),
      mensalResponse: ref(null),
      mensalLoading: ref(false),
      mensalError: ref(null),
      mensalPage: ref(1),
      mensalPageSize: ref(15),
      mensalSortField: ref('valor'),
      mensalSortOrder: ref('desc'),
      mensalSearch: ref(''),
      serieResponse: ref(null),
      serieLoading: ref(false),
      serieError: ref(null),
      alertas: ref({}),
      alertasPeriodo: ref(null),
      alertasErro: ref(null),
      activateMensal: vi.fn(),
      loadSerie: vi.fn(),
      loadAlertas: vi.fn(),
      loadMensal: vi.fn(),
      setTab: vi.fn((tab) => { mocks.mensalStore.tab = tab }),
    })
    mocks.geoStore = {
      getMunicipioNomeByIbge7: vi.fn((id) => Number(id) === 1100015 ? 'Alta Floresta D’Oeste' : null),
      getRegiaoNomeById: vi.fn((id) => Number(id) === 1100001 ? 'Região Central' : null),
      getRegiaoByIbge7: vi.fn((id) => Number(id) === 1100015 ? 1100001 : null),
    }
    mocks.analysisComposable = {
      mapResponse: ref({ mapa: [], qtd_medicos: 0 }),
      rankingResponse: ref({ ranking: [], qtd_medicos: 0, escopo: 'Brasil' }),
      rankingResponseKey: ref(null),
      activeKey: ref(null),
      isMapLoading: ref(false),
      isRankingLoading: ref(false),
      isRankingPageLoading: ref(false),
      mapError: ref(null),
      rankingError: ref(null),
      rankingPageError: ref(null),
      rankingPage: ref(1),
      rankingPageSize: ref(15),
      rankingSortField: ref('score'),
      rankingSortOrder: ref('desc'),
      rankingSearch: ref(''),
      rankingResponseSearch: ref(''),
      fetchRankingPage: vi.fn(),
    }
  })

  afterEach(() => {
    wrapper?.unmount()
    wrapper = null
    vi.clearAllTimers()
    vi.useRealTimers()
    vi.restoreAllMocks()
  })

  function mountView() {
    return mount(AnalysesView, {
      global: {
        directives: { tooltip() {} },
      },
    })
  }

  it('monta mapa e ranking e solicita apenas as seções exibidas', () => {
    wrapper = mountView()

    expect(mocks.fetchAnalytics).toHaveBeenCalledWith({
      secoes: ['kpis'],
      includeFatorRisco: false,
      includeNationalContext: false,
    })
    expect(wrapper.find('[data-test="crm-map"]').attributes('data-level')).toBe('brasil')
    expect(wrapper.get('[data-test="ranking"]').text()).toContain('0 médicos')
    expect(wrapper.find('[data-test="kpis"]').exists()).toBe(true)
  })

  it('converte uma seleção no mapa para município IBGE7 e região de saúde por ID', async () => {
    wrapper = mountView()
    await wrapper.get('[data-test="select-city"]').trigger('click')

    expect(mocks.geoStore.getRegiaoByIbge7).toHaveBeenCalledWith(1100015)
    expect(mocks.filters.selectedMunicipio).toBe('1100015')
    expect(mocks.filters.selectedRegiaoSaude).toBe('1100001')
    expect(wrapper.find('[data-test="crm-map"]').attributes('data-level')).toBe('municipio')
    expect(wrapper.find('[data-test="crm-map"]').attributes('data-municipio')).toBe('Alta Floresta D’Oeste')
    expect(wrapper.find('[data-test="crm-map"]').attributes('data-regiao')).toBe('Região Central')
  })

  it('informa quando o município escolhido não existe no contrato geográfico', async () => {
    mocks.geoStore.getRegiaoByIbge7.mockReturnValue(null)
    wrapper = mountView()
    await wrapper.get('[data-test="select-city"]').trigger('click')

    expect(wrapper.text()).toContain('Não foi possível localizar a Região de Saúde deste município.')
    expect(mocks.filters.selectedMunicipio).toBe('Todos')
  })

  it('aguarda para consultar novamente enquanto o usuário digita o CRM', async () => {
    wrapper = mountView()
    const search = wrapper.get('[data-test="crm-search"]')
    await search.setValue('12345')

    expect(mocks.analysisComposable.fetchRankingPage).not.toHaveBeenCalled()
    await vi.advanceTimersByTimeAsync(350)

    expect(mocks.analysisComposable.fetchRankingPage).toHaveBeenCalledWith(1, 15, 'score', 'desc', '12345')
  })

  it('limpa a seleção de município e reseta a navegação regional ou nacional', async () => {
    mocks.filters.selectedUF = 'RO'
    mocks.filters.selectedRegiaoSaude = '1100001'
    mocks.filters.selectedMunicipio = 'Todos'
    wrapper = mountView()

    await wrapper.get('[data-test="back"]').trigger('click')
    expect(mocks.filters.selectedUF).toBe('RO')
    expect(mocks.filters.selectedRegiaoSaude).toBe('Todos')
    expect(mocks.filters.selectedMunicipio).toBe('Todos')

    await wrapper.get('[data-test="select-uf"]').trigger('click')
    expect(mocks.filters.selectedUF).toBe('RO')
    expect(mocks.filters.selectedRegiaoSaude).toBe('Todos')
    expect(mocks.filters.selectedMunicipio).toBe('Todos')
    await wrapper.get('[data-test="select-no-city"]').trigger('click')
    expect(mocks.filters.selectedMunicipio).toBe('Todos')

    mocks.filters.selectedUF = 'RO'
    await wrapper.get('[data-test="back"]').trigger('click')
    expect(mocks.filters.selectedUF).toBe('Todos')
  })

  it('encaminha paginação e ordenação válidas e ignora eventos inválidos', async () => {
    wrapper = mountView()

    await wrapper.get('[data-test="ranking-page"]').trigger('click')
    expect(mocks.analysisComposable.fetchRankingPage).toHaveBeenLastCalledWith(4, 10, 'score', 'desc')
    await wrapper.get('[data-test="ranking-page-defaults"]').trigger('click')
    expect(mocks.analysisComposable.fetchRankingPage).toHaveBeenLastCalledWith(1, 15, 'score', 'desc')

    await wrapper.get('[data-test="ranking-sort-invalid"]').trigger('click')
    expect(mocks.analysisComposable.fetchRankingPage).toHaveBeenCalledTimes(2)
    await wrapper.get('[data-test="ranking-sort"]').trigger('click')
    expect(mocks.analysisComposable.fetchRankingPage).toHaveBeenLastCalledWith(1, 15, 'nome', 'asc')

    await wrapper.get('[data-test="mensal-page"]').trigger('click')
    expect(mocks.mensalStore.loadMensal).toHaveBeenLastCalledWith(null, null, 4, 10, 'valor', 'desc')
    await wrapper.get('[data-test="mensal-page-defaults"]').trigger('click')
    expect(mocks.mensalStore.loadMensal).toHaveBeenLastCalledWith(null, null, 1, 15, 'valor', 'desc')
    await wrapper.get('[data-test="mensal-sort-invalid"]').trigger('click')
    expect(mocks.mensalStore.loadMensal).toHaveBeenCalledTimes(2)
    await wrapper.get('[data-test="mensal-sort"]').trigger('click')
    expect(mocks.mensalStore.loadMensal).toHaveBeenLastCalledWith(null, null, 1, 15, 'periodo', 'desc')
    wrapper.vm.$.setupState.onMensalSort({ sortField: 'periodo', sortOrder: 1 })
    expect(mocks.mensalStore.loadMensal).toHaveBeenLastCalledWith(null, null, 1, 15, 'periodo', 'asc')
  })

  it('carrega o histórico do médico escolhido e ativa a aba mensal', async () => {
    wrapper = mountView()

    await wrapper.get('[data-test="select-doctor"]').trigger('click')
    expect(wrapper.get('[data-test="history-dialog"]').attributes('data-visible')).toBe('true')
    expect(wrapper.get('[data-test="history-dialog"]').attributes('data-medico')).toBe('crm-1')
    await wrapper.get('[data-test="close-history"]').trigger('click')
    expect(wrapper.get('[data-test="history-dialog"]').attributes('data-visible')).toBe('false')

    await wrapper.get('[data-test="mensal-tab"]').trigger('click')
    expect(mocks.mensalStore.setTab).toHaveBeenCalledWith('mes')
    expect(mocks.mensalStore.tab).toBe('mes')
  })

  it('coordena prefetch mensal, série temporal e alertas conforme filtros e aba', async () => {
    const params = { data_inicio: '2024-01', data_fim: '2024-12', ids_fixados: 'crm-1,crm-2' }
    mocks.analysisStore.activeParams = params
    mocks.analysisStore.cacheVersion = 7
    mocks.analysisComposable.rankingResponse.value = {
      ranking: [{ id_medico: 'crm-1' }], qtd_medicos: 1, escopo: 'UF',
    }
    mocks.analysisComposable.rankingResponseKey.value = JSON.stringify(params)
    mocks.analysisComposable.activeKey.value = JSON.stringify(params)
    mocks.analysisComposable.rankingSearch.value = 'Dra. A'
    mocks.analysisComposable.rankingResponseSearch.value = 'Dra. A'
    mocks.mensalStore.mensalResponse = { linhas: [{ id_medico: 'crm-2' }] }
    wrapper = mountView()

    expect(mocks.mensalStore.activateMensal).toHaveBeenCalledWith(params, 'Dra. A', 7)
    expect(mocks.mensalStore.loadSerie).toHaveBeenCalledWith(params, ['crm-1'], 7)
    expect(mocks.mensalStore.loadAlertas).toHaveBeenCalledWith(params, ['crm-1'], 7)
    expect(wrapper.find('[data-test="ranking"]').exists()).toBe(true)

    mocks.mensalStore.tab = 'mes'
    await wrapper.get('[data-test="mensal-tab"]').trigger('click')
    mocks.mensalStore.tab = 'mes'
    await wrapper.vm.$nextTick()
    expect(wrapper.get('[data-test="ranking"]').attributes('data-tab')).toBe('mes')
    await wrapper.get('[data-test="crm-search"]').setValue(' CRM mensal ')
    expect(mocks.analysisStore.setRankingSearch).not.toHaveBeenCalled()
    await vi.advanceTimersByTimeAsync(350)
    expect(mocks.analysisStore.setRankingSearch).toHaveBeenCalledWith('CRM mensal')
    expect(mocks.mensalStore.loadAlertas).toHaveBeenLastCalledWith(params, ['crm-2'], 7)
    expect(wrapper.get('[data-test="ranking"]').exists()).toBe(true)
  })

  it('aplica busca vazia imediatamente, ignora consulta igual e refaz ranking ao voltar à aba resumo', async () => {
    mocks.analysisStore.activeParams = { inicio: '2024-01', fim: '2024-12' }
    mocks.analysisStore.cacheVersion = 3
    mocks.analysisComposable.rankingResponse.value = { ranking: [{ id_medico: 'crm-1' }], qtd_medicos: 1 }
    mocks.analysisComposable.rankingResponseKey.value = JSON.stringify({ inicio: '2024-01', fim: '2024-12' })
    mocks.analysisComposable.rankingResponseSearch.value = 'antiga'
    mocks.analysisComposable.rankingSearch.value = 'nova'
    wrapper = mountView()

    await wrapper.get('[data-test="crm-search"]').setValue('   ')
    expect(mocks.analysisComposable.fetchRankingPage).toHaveBeenLastCalledWith(1, 15, 'score', 'desc', '')
    mocks.analysisComposable.rankingSearch.value = ''
    mocks.analysisComposable.fetchRankingPage.mockClear()
    await wrapper.get('[data-test="crm-search"]').setValue('   ')
    expect(mocks.analysisComposable.fetchRankingPage).not.toHaveBeenCalled()

    await wrapper.get('[data-test="mensal-tab"]').trigger('click')
    await wrapper.get('[data-test="mensal-tab"]').trigger('click')
    mocks.analysisComposable.rankingSearch.value = 'nova'
    mocks.mensalStore.tab = 'resumo'
    await wrapper.vm.$nextTick()
    expect(mocks.analysisComposable.fetchRankingPage).toHaveBeenLastCalledWith(1, 15, 'score', 'desc', 'nova')
  })

  it('recolhe o painel pela interface e pelo atalho e restaura a preferência salva', async () => {
    localStorage.setItem('sentinela_analises_lateral_recolhida', 'true')
    wrapper = mountView()
    expect(wrapper.find('.analises-lateral').classes()).toContain('is-recolhida')

    await wrapper.get('[aria-label="Abrir painel de análises"]').trigger('click')
    expect(wrapper.find('.analises-lateral').classes()).not.toContain('is-recolhida')
    await wrapper.get('[aria-label="Fechar painel de análises"]').trigger('click')
    expect(wrapper.find('.analises-lateral').classes()).toContain('is-recolhida')

    const shortcut = new KeyboardEvent('keydown', {
      code: 'KeyB', ctrlKey: true, altKey: true, bubbles: true, cancelable: true,
    })
    window.dispatchEvent(shortcut)
    await wrapper.vm.$nextTick()
    expect(shortcut.defaultPrevented).toBe(true)
    expect(wrapper.find('.analises-lateral').classes()).not.toContain('is-recolhida')

    const ignored = new KeyboardEvent('keydown', { code: 'KeyB', ctrlKey: true, altKey: true, shiftKey: true, bubbles: true })
    window.dispatchEvent(ignored)
    expect(wrapper.find('.analises-lateral').classes()).not.toContain('is-recolhida')
  })

  it('ignora o atalho em conteúdo editável e lida com falhas de leitura e gravação da preferência', async () => {
    const getItem = vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => { throw new Error('storage unavailable') })
    wrapper = mountView()
    expect(wrapper.find('.analises-lateral').classes()).not.toContain('is-recolhida')
    getItem.mockRestore()

    const setItem = vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new Error('storage unavailable') })
    const editable = document.createElement('div')
    Object.defineProperty(editable, 'isContentEditable', { value: true })
    document.body.appendChild(editable)
    editable.dispatchEvent(new KeyboardEvent('keydown', {
      code: 'KeyB', ctrlKey: true, altKey: true, bubbles: true, cancelable: true,
    }))
    expect(wrapper.find('.analises-lateral').classes()).not.toContain('is-recolhida')
    editable.remove()

    await wrapper.get('[aria-label="Fechar painel de análises"]').trigger('click')
    expect(wrapper.find('.analises-lateral').classes()).toContain('is-recolhida')
    setItem.mockRestore()
  })

  it('trata ranking e mapa vazios, loading de página, ordenação descendente e geografia inválida', async () => {
    mocks.analysisStore.activeParams = { data_inicio: '2024-01', data_fim: '2024-12' }
    mocks.analysisStore.cacheVersion = 9
    mocks.analysisComposable.isRankingLoading.value = true
    wrapper = mountView()
    await wrapper.vm.$nextTick()
    expect(mocks.mensalStore.activateMensal).not.toHaveBeenCalled()

    await wrapper.get('[data-test="ranking-sort-desc"]').trigger('click')
    expect(mocks.analysisComposable.fetchRankingPage).toHaveBeenLastCalledWith(1, 15, 'nome', 'desc')

    const api = wrapper.vm.$.setupState
    mocks.analysisComposable.mapResponse.value = null
    mocks.analysisComposable.rankingResponse.value = null
    await wrapper.vm.$nextTick()
    expect(api.mapData).toEqual([])
    expect(api.ranking).toEqual([])
    expect(api.rankingTotal).toBe(0)
    expect(api.rankingInitialLoading).toBe(true)
    expect(wrapper.get('[data-test="crm-map"]').attributes('data-qtd')).toBe('0')

    mocks.analysisComposable.rankingResponse.value = { ranking: [{ id_medico: 'crm-1' }], qtd_medicos: 1 }
    mocks.analysisComposable.isRankingLoading.value = false
    mocks.analysisComposable.isRankingPageLoading.value = true
    await wrapper.vm.$nextTick()
    expect(api.rankingInitialLoading).toBe(false)
    expect(api.rankingPageLoading).toBe(true)

    mocks.filters.apiParams = null
    expect(api.historicoPeriodo).toEqual({ inicio: null, fim: null })
    mocks.geoStore.getMunicipioNomeByIbge7.mockReturnValue(null)
    mocks.filters.selectedMunicipio = '1100015'
    expect(() => api.selectedMunicipioNome).toThrow('Municipio selecionado sem nome no contrato de localidades.')
    mocks.filters.selectedMunicipio = 'Todos'
    mocks.geoStore.getRegiaoNomeById.mockReturnValue(null)
    mocks.filters.selectedRegiaoSaude = '1100001'
    expect(() => api.selectedRegiaoNome).toThrow('Regiao de saude selecionada sem nome no contrato de localidades.')
    mocks.filters.selectedRegiaoSaude = 'Todos'
  })
})
