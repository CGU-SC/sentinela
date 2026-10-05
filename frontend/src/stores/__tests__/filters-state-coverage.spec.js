import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, disposePinia, setActivePinia } from 'pinia'
import { nextTick } from 'vue'
import axios from 'axios'

import { API_ENDPOINTS } from '@/config/api'
import { FILTER_ALL_VALUE, FILTER_DEFAULTS, TIMING } from '@/config/constants'
import { useGeoStore } from '@/stores/geo'
import { useFilterStore } from '@/stores/filters'

vi.mock('axios', () => ({ default: { get: vi.fn(), put: vi.fn() } }))

const savedKey = 'sentinela_filters'
const localities = [
  { id_ibge7: 1100015, id_regiao_saude: 1100001, sg_uf: 'RO', unidade_pf: 'RO-1' },
  { id_ibge7: 1100205, id_regiao_saude: 1100002, sg_uf: 'RO', unidade_pf: 'RO-2' },
  { id_ibge7: 1200013, id_regiao_saude: 1200003, sg_uf: 'AC', unidade_pf: 'AC-1' },
]

async function settleLoad() {
  await Promise.resolve()
  await Promise.resolve()
  await nextTick()
}

describe('estados salvos e preferências da store de filtros', () => {
  let pinia

  beforeEach(() => {
    vi.useFakeTimers()
    vi.clearAllMocks()
    localStorage.clear()
    axios.get.mockResolvedValue({ data: { filters: {}, ui: { sidebarCollapsed: false, sidebarLocked: false } } })
    axios.put.mockResolvedValue({ data: {} })
    pinia = createPinia()
    setActivePinia(pinia)
    useGeoStore().localidades = localities
  })

  afterEach(async () => {
    await nextTick()
    await vi.runOnlyPendingTimersAsync()
    disposePinia(pinia)
    vi.useRealTimers()
    localStorage.clear()
  })

  it('rehidrata e normaliza campos persistidos e aplica filtros completos do backend', async () => {
    localStorage.setItem('sentinela_sidebar_collapsed', 'true')
    localStorage.setItem('sentinela_sidebar_locked', 'false')
    localStorage.setItem(savedKey, JSON.stringify({
      selectedUF: 'RO', selectedRegiaoSaude: 'texto legado', selectedMunicipio: 'nome legado',
      selectedCnaeIncompativel: true, selectedSocioIdadeAtipica: 'sim', selectedSocioFalecido: false,
      valorMinSemComp: 12, valorMinSemCompFilter: 18,
      populacaoMunicipio: [0, null], seqTipo: 'multiplo', seqSeveridade: 4, seqDias: [1, 9],
      volumeAtipicoEnabled: true, volumeAtipicoPercentual: 75,
      dispersaoUfSemFronteiraEnabled: true, dispersaoUfSemFronteiraPercentual: 80,
      periodo: ['2025-01-02T00:00:00.000Z', null], sliderValue: [2, 4],
    }))
    axios.get.mockResolvedValueOnce({ data: {
      filters: {
        selectedUF: 'AC', selectedRegiaoSaude: '1200003', selectedMunicipio: '1200013',
        selectedSituacao: 'ATIVA', selectedMS: 'sim', selectedPorte: 'MÉDIO', selectedGrandeRede: 'rede',
        selectedParTeia: 'par', selectedSocioBeneficio: 'direto_n3', selectedSocioEsocial: 'direto_n3',
        selectedCnaeIncompativel: false, selectedSocioIdadeAtipica: true, selectedSocioFalecido: true,
        selectedUnidadePf: 'AC-1', selectedCnpjRaiz: '12.345.678',
        percentualNaoComprovacaoRange: [10, 80], percentualNaoComprovacaoFilter: [15, 85],
        valorMinSemComp: 100, valorMinSemCompFilter: 200, populacaoMunicipio: [100, 500],
        seqTipo: 'qualquer', seqSeveridade: 2, seqDias: [3, 7],
        volumeAtipicoEnabled: true, volumeAtipicoPercentual: 65, volumeAtipicoPercentualFilter: 70,
        dispersaoUfSemFronteiraEnabled: true, dispersaoUfSemFronteiraPercentual: 75,
        periodo: ['2024-01-01T00:00:00.000Z', '2024-12-31T00:00:00.000Z'], sliderValue: [1, 12],
        clusterSelection: 'cluster', statusSelection: 'status', rfaSelection: 'rfa', searchTarget: 'consulta',
      },
      ui: { sidebarCollapsed: true, sidebarLocked: true },
    } })

    const store = useFilterStore()
    await settleLoad()
    expect(store.selectedUF).toBe('AC')
    expect(store.selectedRegiaoSaude).toBe('1200003')
    expect(store.selectedMunicipio).toBe('1200013')
    expect(store.selectedSocioBeneficio).toBe('direto_n3')
    expect(store.selectedSocioEsocial).toBe('direto_n3')
    expect(store.selectedCnaeIncompativel).toBe(false)
    expect(store.selectedSocioIdadeAtipica).toBe(true)
    expect(store.selectedSocioFalecido).toBe(true)
    expect(store.populacaoMunicipio).toEqual([100, 500])
    expect(store.seqTipo).toBe('qualquer')
    expect(store.seqSeveridade).toBe(2)
    expect(store.seqDias).toEqual([3, 7])
    expect(store.volumeAtipicoPercentualFilter).toBe(70)
    expect(store.clusterSelection).toBe('cluster')
    expect(store.searchTarget).toBe('consulta')
    expect(store.sidebarCollapsed).toBe(true)
    expect(store.sidebarLocked).toBe(true)
    expect(localStorage.getItem(savedKey)).toContain('selectedUF')
    expect(axios.put).not.toHaveBeenCalledWith(API_ENDPOINTS.preferencesFilters, expect.anything())

    const params = store.indicadoresApiParams
    expect(params).toMatchObject({
      uf: 'AC', regiao_id: 1200003, unidade_pf: 'AC-1', cnae_incompativel: false,
      socio_idade_atipica: true, socio_falecido: true, populacao_min: 100, populacao_max: 500,
      seq_tipo: 'qualquer', seq_severidade_min: 2, seq_dias_min: 3, seq_dias_max: 7,
    })
    expect(store.indicadoresTabelaApiParams.id_ibge7).toBe(1200013)
  })

  it('usa padrões para conteúdo local inválido e sincroniza armazenamento/backend quando aplicável', async () => {
    localStorage.setItem(savedKey, '{json inválido')
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {})
    axios.get.mockRejectedValueOnce(new Error('offline'))
    const store = useFilterStore()
    await settleLoad()
    expect(store.selectedUF).toBe(FILTER_DEFAULTS.UF)
    expect(store.apiParams.populacaoMin).toBe(FILTER_DEFAULTS.POPULACAO_MUNICIPIO_RANGE[0])
    expect(store.apiParams.seqTipo).toBeNull()
    expect(warn).toHaveBeenCalledWith('[filters] Usando filtros locais do navegador:', expect.any(Error))

    const noUiStorePinia = createPinia()
    setActivePinia(noUiStorePinia)
    axios.get.mockResolvedValueOnce({ data: { filters: null, ui: null } })
    const noUi = useFilterStore()
    await settleLoad()
    expect(axios.put).toHaveBeenCalledWith(API_ENDPOINTS.preferencesUi, {
      ui: { sidebarCollapsed: false, sidebarLocked: false },
    })
    noUi.sidebarCollapsed = true
    noUi.sidebarLocked = true
    await nextTick()
    expect(localStorage.getItem('sentinela_sidebar_collapsed')).toBe('true')
    expect(localStorage.getItem('sentinela_sidebar_locked')).toBe('true')
    axios.put.mockRejectedValueOnce(new Error('ui offline'))
    noUi.sidebarLocked = false
    await nextTick()
    await vi.advanceTimersByTimeAsync(TIMING.FILTER_DEBOUNCE + 1)
    expect(warn).toHaveBeenCalled()
    disposePinia(noUiStorePinia)
  })

  it('aplica filtros parciais do backend, preserva padrões para formatos inválidos e normaliza datas de API', async () => {
    axios.get.mockResolvedValueOnce({ data: {
      filters: {
        selectedRegiaoSaude: 'região antiga',
        selectedMunicipio: 'município antigo',
        volumeAtipicoEnabled: true,
        volumeAtipicoPercentual: 73,
        dispersaoUfSemFronteiraEnabled: true,
        dispersaoUfSemFronteiraPercentual: 0,
        periodo: ['2025-07-01T00:00:00.000Z', null],
      },
      ui: { sidebarCollapsed: false, sidebarLocked: false },
    } })

    const store = useFilterStore()
    await settleLoad()
    expect(store.selectedRegiaoSaude).toBe(FILTER_DEFAULTS.REGIAO)
    expect(store.selectedMunicipio).toBe(FILTER_DEFAULTS.MUNICIPIO)
    expect(store.volumeAtipicoPercentualFilter).toBe(73)
    expect(store.apiParams.volumeAtipicoPercentual).toBe(73)
    expect(store.apiParams.dispersaoUfSemFronteiraPercentual).toBe(
      FILTER_DEFAULTS.DISPERSAO_UF_SEM_FRONTEIRA_PERCENTUAL,
    )

    store.volumeAtipicoPercentualFilter = 0
    expect(store.apiParams.volumeAtipicoPercentual).toBe(FILTER_DEFAULTS.VOLUME_ATIPICO_PERCENTUAL)
    store.periodo = [{ toISOString: () => 'data inválida' }, new Date(2025, 11, 31)]
    expect(store.apiParams.inicio).toBeNull()
    expect(store.apiParams.fim).toBe('2025-12-31')
    store.selectedCnpjRaiz = { cnpj: null, label: null }
    expect(store.apiParams.cnpjRaiz).toBeNull()
    expect(store.apiParams.estabelecimento).toBeNull()

    store.selectedParTeia = ['par', 'teia']
    expect(store.apiParamsKey).toContain('"parTeia":["par","teia"]')
  })

  it('ignora filtros remotos que não seguem o formato de objeto', async () => {
    axios.get.mockResolvedValueOnce({ data: {
      filters: 'formato inválido',
      ui: { sidebarCollapsed: false, sidebarLocked: false },
    } })

    const store = useFilterStore()
    await settleLoad()
    expect(store.selectedUF).toBe(FILTER_DEFAULTS.UF)
    expect(store.selectedRegiaoSaude).toBe(FILTER_DEFAULTS.REGIAO)
  })

  it('normaliza formatos incorretos, calcula períodos opcionais e cobre os ramos das cascatas territoriais', async () => {
    localStorage.setItem(savedKey, JSON.stringify({
      selectedUF: 'RO', selectedRegiaoSaude: 'texto', selectedMunicipio: 'nome',
      selectedSocioBeneficio: 'desconhecido', selectedSocioEsocial: 'desconhecido',
      selectedSocioIdadeAtipica: 'false', selectedSocioFalecido: 0,
      populacaoMunicipio: [9, 2], seqTipo: 'outro', seqSeveridade: 9, seqDias: [-1, 5],
      volumeAtipicoPercentualFilter: 'inválido', volumeAtipicoPercentual: 70,
      periodo: [null, null],
    }))
    const store = useFilterStore()
    await settleLoad()
    expect(store.selectedRegiaoSaude).toBe(FILTER_DEFAULTS.REGIAO)
    expect(store.selectedMunicipio).toBe(FILTER_DEFAULTS.MUNICIPIO)
    expect(store.selectedSocioBeneficio).toBe(FILTER_DEFAULTS.SOCIO_BENEFICIO)
    expect(store.selectedSocioEsocial).toBe(FILTER_DEFAULTS.SOCIO_ESOCIAL)
    expect(store.populacaoMunicipio).toEqual([...FILTER_DEFAULTS.POPULACAO_MUNICIPIO_RANGE])
    expect(store.seqTipo).toBe(FILTER_DEFAULTS.SEQ_TIPO)
    expect(store.seqSeveridade).toBe(FILTER_DEFAULTS.SEQ_SEVERIDADE)
    expect(store.seqDias).toEqual([...FILTER_DEFAULTS.SEQ_DIAS_RANGE])
    expect(store.volumeAtipicoPercentualFilter).toBe(70)
    expect(store.isPeriodoValido).toBe(false)

    store.periodo = []
    expect(store.isPeriodoValido).toBe(false)
    expect(store.apiParams.inicio).toBeNull()
    expect(store.apiParams.fim).toBeNull()
    store.periodo = [new Date(2025, 0, 2), new Date(2025, 11, 31)]
    expect(store.isPeriodoValido).toBe(true)
    store.selectedCnpjRaiz = { label: '  Loja Central  ' }
    expect(store.apiParams.estabelecimento).toBe('Loja Central')
    store.selectedCnpjRaiz = { cnpj: '12.345.678/0001-95' }
    expect(store.apiParams.cnpjRaiz).toBe('12345678000195')
    store.selectedCnpjRaiz = 123
    expect(store.apiParams.cnpjRaiz).toBeNull()
    expect(store.apiParams.estabelecimento).toBeNull()

    store.selectedRegiaoSaude = '1100001'
    await nextTick()
    store.regionMapData = { features: [] }
    store.selectedRegiaoSaude = FILTER_ALL_VALUE
    await nextTick()
    expect(store.regionMapData).toBeNull()
    expect(store.selectedMunicipio).toBe(FILTER_ALL_VALUE)
    store.selectedUF = 'RO'
    store.selectedUnidadePf = 'RO-2'
    await nextTick()
    expect(store.selectedUF).toBe('RO')
    store.selectedUF = FILTER_ALL_VALUE
    await nextTick()
    expect(store.selectedUnidadePf).toBe(FILTER_ALL_VALUE)

    useGeoStore().localidades = []
    store.selectedUnidadePf = 'RO-1'
    store.selectedRegiaoSaude = '1100001'
    store.selectedMunicipio = '1100015'
    await nextTick()
    expect(store.selectedRegiaoSaude).toBe('1100001')
    useGeoStore().localidades = localities
    store.selectedUF = FILTER_ALL_VALUE
    store.selectedUnidadePf = 'AC-1'
    await nextTick()
    expect(store.selectedUF).toBe('AC')
    store.selectedUF = FILTER_ALL_VALUE
    await nextTick()
    store.selectedRegiaoSaude = '1200003'
    await nextTick()
    await nextTick()
    expect(store.selectedUF).toBe('AC')
    store.selectedMunicipio = '1100015'
    await nextTick()
    expect(store.selectedRegiaoSaude).toBe('1100001')
    store.selectedMunicipio = '9999999'
    await nextTick()
    expect(store.selectedMunicipio).toBe('9999999')
  })

  it('sincroniza preferências locais sem sobrepor o retorno do backend e trata gravação local e remota', async () => {
    localStorage.setItem(savedKey, JSON.stringify({ selectedUF: 'RO' }))
    axios.get.mockResolvedValueOnce({ data: { filters: {}, ui: { sidebarCollapsed: 'true', sidebarLocked: 1 } } })
    const store = useFilterStore()
    await settleLoad()
    expect(store.selectedUF).toBe('RO')
    expect(axios.put).toHaveBeenCalledWith(API_ENDPOINTS.preferencesFilters, expect.objectContaining({
      filters: expect.objectContaining({ selectedUF: 'RO' }),
    }))
    expect(store.sidebarCollapsed).toBe(false)
    expect(store.sidebarLocked).toBe(false)

    store.animationMode = true
    store.isAnimating = true
    store.animationDuration = 500
    store.animationBaseSliderRange = [1, 12]
    store.animationSliderValue = 2
    store.animationFrameRange = [2, 3]
    store.animationPreload.status = 'ready'
    store.animationPreload.dataInicio = '2025-01'
    store.animationPreload.dataFim = '2025-12'
    store.resetAnimationPreview()
    expect(store.animationMode).toBe(false)
    expect(store.animationPreload).toMatchObject({ status: 'idle', dataInicio: null, dataFim: null })

    store.selectedSocioFalecido = true
    await nextTick()
    await vi.advanceTimersByTimeAsync(TIMING.FILTER_DEBOUNCE + 1)
    expect(JSON.parse(localStorage.getItem(savedKey)).selectedSocioFalecido).toBe(true)
    axios.put.mockRejectedValueOnce(new Error('filters offline'))
    store.resetFilters()
    expect(localStorage.getItem(savedKey)).toBeNull()
    await vi.advanceTimersByTimeAsync(TIMING.FILTER_DEBOUNCE + 1)
    expect(JSON.parse(localStorage.getItem(savedKey)).selectedUF).toBe(FILTER_ALL_VALUE)
  })
})
