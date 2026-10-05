import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, disposePinia, setActivePinia } from 'pinia'
import axios from 'axios'

import { API_ENDPOINTS } from '@/config/api'
import { CRM_FAIXAS, CRM_SEQUENCIA_SEVERIDADES, CRM_SEQUENCIA_TIPOS, CRM_SITUACAO_CFM_OPCOES } from '@/config/crmFiltrosMedico'
import { DEFAULT_TARGET_KEY, TARGET_GROUPS } from '@/config/targetConfig'
import { useCrmFiltrosMedicoStore, formatarValorFaixa, validarFaixa } from '@/stores/crmFiltrosMedico'
import { CRM_MEDICOS_FIXADOS_MAX, useCrmMedicosFixadosStore } from '@/stores/crmMedicosFixados'
import { useMunicipalMapStore } from '@/stores/municipalMap'
import { useMetodologiaConfigStore } from '@/stores/metodologiaConfig'
import { useNotaTecnicaConfigStore } from '@/stores/notaTecnicaConfig'
import { useRecentCnpjStore } from '@/stores/recentCnpj'
import { useGeoStore } from '@/stores/geo'
import { useRiskIndicatorsStore } from '@/stores/riskIndicators'
import { useThemeStore } from '@/stores/theme'
import { useTargetsStore } from '@/stores/targets'
import { useSystemUpdateStore } from '@/stores/systemUpdate'

vi.mock('axios', () => ({
  default: {
    get: vi.fn(),
    put: vi.fn(),
    post: vi.fn(),
    isCancel: vi.fn(() => false),
  },
}))

const response = (data) => ({ data })

function deferred() {
  let resolve
  let reject
  const promise = new Promise((res, rej) => { resolve = res; reject = rej })
  return { promise, resolve, reject }
}

const METODOLOGIA = {
  audit_high_value: 10000,
  volume_atipico_aumento_minimo: 0.5,
  defaults: { audit_high_value: 10000, volume_atipico_aumento_minimo: 0.5 },
  limits: {
    audit_high_value: { min: 100, max: 1000000 },
    volume_atipico_aumento_minimo: { min: 0.1, max: 5 },
  },
}

const EMPTY_COPY = {
  exists: false, valid: false, kind: 'joint', evidencias_backup_valid: false,
  watchlist_count: null, evidencias_count: null, missing_watchlist_count: null,
  missing_evidencias_count: null, farmacias_mantidas_count: null,
}

describe('cobertura de stores de apoio', () => {
  let pinia

  beforeEach(() => {
    vi.clearAllMocks()
    localStorage.clear()
    axios.isCancel.mockReturnValue(false)
    axios.get.mockResolvedValue(response({}))
    axios.put.mockResolvedValue(response({}))
    axios.post.mockResolvedValue(response({}))
    pinia = createPinia()
    setActivePinia(pinia)
  })

  afterEach(() => {
    vi.clearAllTimers()
    vi.useRealTimers()
    disposePinia(pinia)
    localStorage.clear()
  })

  it('valida filtros de médico, normaliza faixas e limpa sequência e filtros', () => {
    const store = useCrmFiltrosMedicoStore()
    const faixa = Object.keys(CRM_FAIXAS)[0]
    const config = CRM_FAIXAS[faixa]
    const valorInteiro = Object.values(CRM_FAIXAS).find((item) => item.casas === 0)

    expect(formatarValorFaixa(faixa, 12.34)).toBe(
      `${Number(12.34).toLocaleString('pt-BR', { minimumFractionDigits: 0, maximumFractionDigits: config.casas })}${config.sufixo}`,
    )
    expect(() => formatarValorFaixa('inexistente', 1)).toThrow('Faixa de filtro de médico desconhecida: inexistente')
    expect(() => validarFaixa('inexistente', { min: null, max: null })).toThrow('Faixa de filtro de médico desconhecida: inexistente')
    expect(validarFaixa(faixa, { min: Number.NaN, max: null })).toBe('Número inválido.')
    expect(validarFaixa(faixa, { min: null, max: -1 })).toBe('O valor não pode ser negativo.')
    expect(validarFaixa('exclusividade', { min: null, max: 101 })).toContain('Use valores até')
    expect(validarFaixa(Object.keys(CRM_FAIXAS).find((key) => CRM_FAIXAS[key] === valorInteiro), { min: 1.5, max: null }))
      .toBe('Use um número inteiro.')
    expect(validarFaixa(faixa, { min: 8, max: 7 })).toBe('O mínimo é maior que o máximo.')
    expect(validarFaixa(faixa, { min: null, max: null })).toBeNull()

    expect(store.sequenciaAtiva).toBe(false)
    expect(store.qtdAtivos).toBe(0)
    store.setSituacaoCfm(CRM_SITUACAO_CFM_OPCOES[1].value)
    expect(() => store.setSituacaoCfm('desconhecida')).toThrow('Situação no CFM inválida: desconhecida')
    store.setUfsCrm(['SP', 'RO', 'SP'])
    expect(store.ufsCrm).toEqual(['RO', 'SP'])
    expect(() => store.setUfsCrm(['XX'])).toThrow('UF do CRM inválida: XX')
    store.setSequenciaSeveridadeMin(CRM_SEQUENCIA_SEVERIDADES[1].value)
    expect(() => store.setSequenciaSeveridadeMin(99)).toThrow('Severidade de sequência inválida: 99')
    store.setSequenciaTipo(CRM_SEQUENCIA_TIPOS[1].value)
    expect(() => store.setSequenciaTipo('desconhecida')).toThrow('Tipo de sequência inválido: desconhecida')
    store.setFaixa(faixa, { min: 1, max: null })
    store.setFaixa(faixa, { min: 1, max: null })
    expect(() => store.setFaixa(faixa, { min: 8, max: 7 })).toThrow(`Faixa ${faixa} inválida`)
    store.setFaixa('sequenciaDias', { min: null, max: 5 })
    store.setSequenciaTipo(CRM_SEQUENCIA_TIPOS[0].value)
    expect(store.apiParams[`${config.param}_min`]).toBe(1)
    expect(store.apiParams.sequencia_dias_max).toBe(5)
    expect(store.apiParams.sequencia_tipo).toBeUndefined()
    expect(store.qtdAtivos).toBe(5)
    store.setSequenciaTipo(CRM_SEQUENCIA_TIPOS[1].value)
    expect(store.apiParams.sequencia_tipo).toBe(CRM_SEQUENCIA_TIPOS[1].value)
    store.limparSequencia()
    expect(store.sequenciaAtiva).toBe(false)
    expect(store.apiParams).not.toHaveProperty('sequencia_tipo')
    store.limparFaixa(faixa)
    store.limpar()
    expect(store.qtdAtivos).toBe(0)
  })

  it('lê, valida, limita, fixa e remove médicos persistidos', () => {
    const key = 'sentinela_crm_medicos_fixados'
    localStorage.setItem(key, '{quebrado')
    expect(useCrmMedicosFixadosStore().medicos).toEqual([])

    localStorage.setItem(key, JSON.stringify({ medicos: [] }))
    disposePinia(pinia)
    pinia = createPinia()
    setActivePinia(pinia)
    expect(useCrmMedicosFixadosStore().medicos).toEqual([])

    const entradas = [
      null,
      { id_medico: 4, nome: 'Tipo inválido', crm: 'RO 1' },
      { id_medico: '', nome: 'Vazio', crm: 'RO 2' },
      { id_medico: 'm,2', nome: 'Vírgula', crm: 'RO 3' },
      { id_medico: 'm3', nome: 3, crm: 'RO 4' },
      { id_medico: 'm4', nome: 'Sem CRM', crm: 4 },
      { id_medico: 'm1', nome: 'Ana', crm: 'RO 1' },
      { id_medico: 'm1', nome: 'Duplicada', crm: 'RO 1' },
    ]
    localStorage.setItem(key, JSON.stringify(entradas))
    disposePinia(pinia)
    pinia = createPinia()
    setActivePinia(pinia)
    const store = useCrmMedicosFixadosStore()
    expect(store.medicos).toEqual([{ id_medico: 'm1', nome: 'Ana', crm: 'RO 1' }])
    expect(store.ids).toEqual(new Set(['m1']))
    expect(store.total).toBe(1)
    expect(store.apiParams).toEqual({})
    store.setSoFixados(true)
    expect(store.apiParams.ids_fixados).toBe('m1')
    store.setSoFixados(false)
    expect(store.apiParams).toEqual({})

    expect(() => store.alternar({ id_medico: 'bad,1', nome: 'Inválido', crm: 'RO 2' })).toThrow('Médico inválido para fixar:')
    expect(store.alternar({ id_medico: 'm2', nome: 'Bruno', crm: 'SP 2' })).toBe(true)
    expect(store.alternar({ id_medico: 'm2', nome: 'Bruno', crm: 'SP 2' })).toBe(true)
    expect(store.medicos).toEqual([{ id_medico: 'm1', nome: 'Ana', crm: 'RO 1' }])
    store.setSoFixados(true)
    store.soltar('m1')
    expect(store.soFixados).toBe(false)
    store.alternar({ id_medico: 'm3', nome: 'Caio', crm: 'AC 3' })

    const limite = Array.from({ length: CRM_MEDICOS_FIXADOS_MAX }, (_, i) => ({
      id_medico: `id-${i}`, nome: `Médico ${i}`, crm: 'RO 1',
    }))
    store.medicos = limite
    expect(store.alternar({ id_medico: 'extra', nome: 'Extra', crm: 'RO 2' })).toBe(false)
    const setItem = vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new Error('storage cheio') })
    store.soltarTodos()
    expect(store.medicos).toEqual([])
    expect(store.alternar({ id_medico: 'novo', nome: 'Novo', crm: 'RO 3' })).toBe(true)
    expect(setItem).toHaveBeenCalled()
    store.setSoFixados(true)
    expect(store.apiParams.ids_fixados).toBe('novo')
  })

  it('carrega o mapa municipal do dashboard, evita requisição repetida e registra falhas', async () => {
    const store = useMunicipalMapStore()
    expect(() => store.useDashboardRows('x', {})).toThrow('Resumo do dashboard sem resultado_municipios.')
    store.useDashboardRows('dashboard', [{ id_ibge7: 1 }])
    expect(store.error).toBeNull()
    expect(store.isLoading).toBe(false)
    await store.load('dashboard', {})
    expect(axios.get).not.toHaveBeenCalled()

    axios.get.mockResolvedValueOnce(response({ resultado_municipios: [{ id_ibge7: 2 }] }))
    await store.load('mapa', { uf: 'RO' })
    expect(store.rows).toEqual([{ id_ibge7: 2 }])
    expect(store.loadedKey).toBe('mapa')
    expect(store.isLoading).toBe(false)

    const log = vi.spyOn(console, 'error').mockImplementation(() => {})
    axios.get.mockResolvedValueOnce(response({}))
    await expect(store.load('falha', {})).rejects.toThrow('seção municipios ausente')
    expect(store.error).toBe('Não foi possível carregar a base municipal do mapa.')
    expect(store.isLoading).toBe(false)
    expect(log).toHaveBeenCalled()
  })

  it('deduplica pedidos municipais simultâneos e descarta resultados de chaves antigas', async () => {
    const store = useMunicipalMapStore()
    const oldRequest = deferred()
    const currentRequest = deferred()
    axios.get.mockImplementationOnce(() => oldRequest.promise).mockImplementationOnce(() => currentRequest.promise)
    const oldLoad = store.load('old', { uf: 'AC' })
    const duplicateLoad = store.load('old', { uf: 'AC' })
    expect(axios.get).toHaveBeenCalledTimes(1)
    const currentLoad = store.load('current', { uf: 'RO' })
    currentRequest.resolve(response({ resultado_municipios: [{ uf: 'RO' }] }))
    await currentLoad
    oldRequest.resolve(response({ resultado_municipios: [{ uf: 'AC' }] }))
    await Promise.all([oldLoad, duplicateLoad])
    expect(store.loadedKey).toBe('current')
    expect(store.rows).toEqual([{ uf: 'RO' }])
    expect(store.error).toBeNull()
    expect(store.isLoading).toBe(false)

    const staleFailure = deferred()
    const latestSuccess = deferred()
    axios.get.mockImplementationOnce(() => staleFailure.promise).mockImplementationOnce(() => latestSuccess.promise)
    const staleLoad = store.load('stale-error', { uf: 'AC' })
    const latestLoad = store.load('latest', { uf: 'SP' })
    latestSuccess.resolve(response({ resultado_municipios: [{ uf: 'SP' }] }))
    await latestLoad
    staleFailure.reject(new Error('falha obsoleta'))
    await staleLoad
    expect(store.loadedKey).toBe('latest')
    expect(store.rows).toEqual([{ uf: 'SP' }])
    expect(store.error).toBeNull()
  })

  it('exige todos os campos da configuração metodológica e atualiza os dois parâmetros', async () => {
    const store = useMetodologiaConfigStore()
    const incompletos = [
      (({ audit_high_value, ...rest }) => rest)(METODOLOGIA),
      { ...METODOLOGIA, defaults: { volume_atipico_aumento_minimo: 0.5 } },
      { ...METODOLOGIA, limits: { volume_atipico_aumento_minimo: { min: 0.1, max: 5 } } },
      (({ volume_atipico_aumento_minimo, ...rest }) => rest)(METODOLOGIA),
      { ...METODOLOGIA, defaults: { audit_high_value: 10000 } },
      { ...METODOLOGIA, limits: { audit_high_value: { min: 100, max: 1000000 } } },
    ]
    for (const payload of incompletos) {
      axios.get.mockResolvedValueOnce(response(payload))
      await expect(store.ensureLoaded({ force: true })).rejects.toThrow('Configuração metodológica incompleta.')
      expect(store.loading).toBe(false)
    }
    axios.get.mockResolvedValueOnce(response(METODOLOGIA))
    await store.ensureLoaded()
    await store.ensureLoaded()
    expect(axios.get).toHaveBeenCalledTimes(7)
    expect(store.auditHighValueDefault).toBe(10000)
    expect(store.volumeAtipicoDefault).toBe(0.5)
    expect(store.volumeAtipicoLimits).toEqual(METODOLOGIA.limits.volume_atipico_aumento_minimo)

    const saved = { ...METODOLOGIA, volume_atipico_aumento_minimo: 1.25 }
    axios.put.mockResolvedValueOnce(response(saved))
    await store.saveVolumeAtipicoAumentoMinimo(1.25)
    expect(store.volumeAtipicoAumentoMinimo).toBe(1.25)
    axios.put.mockRejectedValueOnce(new Error('sem rede'))
    await expect(store.saveAuditHighValue(25000)).rejects.toThrow('sem rede')
    expect(store.saving).toBe(false)
    axios.get.mockRejectedValueOnce(new Error('sem rede'))
    await expect(store.ensureLoaded({ force: true })).rejects.toThrow('sem rede')
    expect(store.loading).toBe(false)
  })

  it('carrega preferências da Nota Técnica e cobre normalização e validação de assinantes', async () => {
    const store = useNotaTecnicaConfigStore()
    axios.get.mockImplementation(async (url) => {
      if (url === API_ENDPOINTS.analyticsNotaTecnicaRegionais) return response([{ codigo: 'AC', estado: 'Acre' }])
      if (url === API_ENDPOINTS.preferences) return response({ nota_tecnica: {
        regional_codigo: 'AC', ultimo_numero_nota: 'NT-4', ultimo_numero_processo: 'P-5',
        assinantes_tecnicos: [{ nome: ' A ', cargo: '' }, null, { nome: '', cargo: ' Cargo ' },
          { nome: 'B', cargo: 'CB' }, { nome: 'C', cargo: 'CC' }, { nome: 'D', cargo: 'CD' }],
        gerar_pdf_visualizacao: true,
      } })
      return response({})
    })
    await store.ensureLoaded()
    await store.ensureLoaded()
    expect(store.selectedRegionalLabel).toBe('AC - Acre')
    expect(store.assinantesTecnicos).toEqual([
      { nome: 'A', cargo: '' }, { nome: '', cargo: 'Cargo' }, { nome: 'B', cargo: 'CB' },
    ])
    expect(store.gerarPdfVisualizacao).toBe(true)
    expect(store.selectedRegional).toEqual({ codigo: 'AC', estado: 'Acre' })
    await expect(store.saveNotaTecnicaConfig({ regionalCodigo: ' ' })).rejects.toThrow('Selecione a Regional emissora')
    await expect(store.saveNotaTecnicaConfig({ regionalCodigo: '' })).rejects.toThrow('Selecione a Regional emissora')
    await expect(store.saveNotaTecnicaConfig({ regionalCodigo: 'XX' })).rejects.toThrow('Regional emissora inválida: XX.')

    axios.put.mockResolvedValueOnce(response({}))
    const saved = await store.saveNotaTecnicaConfig({
      regionalCodigo: ' ac ', numeroNota: '', numeroProcesso: null,
      assinantes: 'formato incorreto', gerarPdf: false,
    })
    expect(saved).toEqual({ codigo: 'AC', estado: 'Acre' })
    expect(store.ultimoNumeroNota).toBe('')
    expect(store.assinantesTecnicos).toEqual([])
    expect(store.gerarPdfVisualizacao).toBe(false)
    store.selectedRegionalCodigo = 'ZZ'
    expect(store.selectedRegional).toBeNull()
    expect(store.selectedRegionalLabel).toBeNull()
    axios.put.mockResolvedValueOnce(response({ nota_tecnica: {
      regional_codigo: 'AC', ultimo_numero_nota: 'NT-5', ultimo_numero_processo: 'P-6',
      assinantes_tecnicos: [], gerar_pdf_visualizacao: true,
    } }))
    await store.saveNotaTecnicaConfig({ regionalCodigo: 'AC' })
    expect(store.selectedRegionalCodigo).toBe('AC')
    expect(store.selectedRegionalLabel).toBe('AC - Acre')

    disposePinia(pinia)
    pinia = createPinia()
    setActivePinia(pinia)
    const broken = useNotaTecnicaConfigStore()
    axios.get.mockResolvedValueOnce(response({})).mockResolvedValueOnce(response({}))
    await expect(broken.ensureLoaded()).rejects.toThrow('Lista de regionais da Nota Técnica inválida.')
    expect(broken.loading).toBe(false)
  })

  it('recupera último CNPJ de localStorage e trata conteúdo inválido', () => {
    const key = 'sentinela_recent_cnpj'
    localStorage.setItem(key, '{quebrado')
    expect(useRecentCnpjStore().recent).toBeNull()

    disposePinia(pinia)
    pinia = createPinia()
    setActivePinia(pinia)
    localStorage.setItem(key, JSON.stringify({ cnpj: '12345678000195', razaoSocial: 'Farmácia' }))
    const store = useRecentCnpjStore()
    expect(store.recent).toEqual({ cnpj: '12345678000195', razaoSocial: 'Farmácia' })
    store.clear()
    expect(localStorage.getItem(key)).toBeNull()
  })

  it('filtra localidades e municípios por IDs e trata carregamentos geográficos', async () => {
    const store = useGeoStore()
    const localidades = [
      { id_ibge7: 1100015, id_regiao_saude: 1100001, sg_uf: 'RO', no_municipio: 'Alta Floresta', no_regiao_saude: 'Central', unidade_pf: 'PF-1' },
      { id_ibge7: '1100015', id_regiao_saude: 1100001, sg_uf: 'RO', no_municipio: 'Alta Floresta', no_regiao_saude: 'Central', unidade_pf: null },
      { id_ibge7: 1100205, id_regiao_saude: 1100002, sg_uf: 'RO', no_municipio: 'Porto Velho', no_regiao_saude: 'Madeira', unidade_pf: 'PF-2' },
      { id_ibge7: null, id_regiao_saude: null, sg_uf: 'AC', no_municipio: 'Cruzeiro', no_regiao_saude: '', unidade_pf: '' },
    ]
    store.localidades = localidades
    expect(store.ufs).toEqual(['Todos', 'AC', 'RO'])
    expect(store.regioesPorUF('Todos')).toEqual([
      { label: 'Todos', value: 'Todos' }, { label: 'Central', value: '1100001' },
      { label: 'Madeira', value: '1100002' },
    ])
    expect(store.regioesPorUF('AC')).toEqual([{ label: 'Todos', value: 'Todos' }])
    expect(store.jurisdicoesPorFiltro('RO', '1100001', 'Todos')).toEqual(['Todos', 'PF-1'])
    expect(store.jurisdicoesPorFiltro('Todos', 'Todos', '1100205')).toEqual(['Todos', 'PF-2'])
    expect(store.municipiosPorFiltro('RO', 'Todos', 'PF-1').map(({ value }) => value)).toEqual(['Todos', '1100015'])
    expect(store.qtdMunicipiosPorRegiao(null)).toBeNull()
    expect(store.qtdMunicipiosPorRegiao('1100001')).toBe(1)
    expect(store.qtdMunicipiosPorRegiao('desconhecida')).toBeNull()
    expect(store.municipiosPorFiltro('Todos', 'Todos', 'Todos')).toHaveLength(4)
    expect(store.municipiosPorFiltro('RO', '1100001', 'Todos')[1].value).toBe('1100015')
    expect(store.getFilterValueByIbge7('Todos')).toBe('Todos')
    expect(store.getFilterValueByIbge7(1100015)).toBe('Alta Floresta|RO')
    expect(store.getFilterValueByIbge7(9999999)).toBe('Todos')
    expect(store.getMunicipioNomeByIbge7('1100205')).toBe('Porto Velho')
    expect(store.getMunicipioNomeByIbge7(9999999)).toBeNull()
    expect(store.getMunicipioNomeByIbge7(null)).toBeNull()
    expect(store.getMunicipioNomeByIbge7('Todos')).toBeNull()
    expect(store.getRegiaoByIbge7('1100015')).toBe('1100001')
    expect(store.getRegiaoByIbge7(9999999)).toBe('Todos')
    expect(store.getRegiaoByIbge7(0)).toBe('Todos')
    expect(store.getRegiaoByIbge7('Todos')).toBe('Todos')
    expect(store.getRegiaoNomeById('1100002')).toBe('Madeira')
    expect(store.getRegiaoNomeById('inexistente')).toBeNull()
    expect(store.getRegiaoNomeById('Todos')).toBeNull()

    store.municipiosGeoJson = { type: 'FeatureCollection', features: [
      { properties: { id: 1100015 } }, { properties: { id: 1200013 } },
    ] }
    expect(store.getMunicipiosGeoByUF('RO').features).toHaveLength(1)
    expect(store.getMunicipiosGeoByUF('XX')).toBeNull()
    expect(store.getMunicipiosGeoByUF('Todos')).toBeNull()
    expect(store.getMunicipiosGeoByUF('RO')).toEqual(expect.objectContaining({ type: 'FeatureCollection' }))

    axios.get.mockResolvedValueOnce(response({ localidades: [{ id_ibge7: 1 }] }))
    await store.fetchLocalidades()
    expect(store.localidades).toEqual([{ id_ibge7: 1 }])
    expect(store.isLoading).toBe(false)
    const errorLog = vi.spyOn(console, 'error').mockImplementation(() => {})
    axios.get.mockRejectedValueOnce(new Error('offline'))
    await store.fetchLocalidades()
    expect(store.isLoading).toBe(false)
    expect(errorLog).toHaveBeenCalled()

    axios.get.mockResolvedValueOnce(response({ estabelecimentos: [
      { id_ibge7: '1100015', cnpj: '1' }, { id_ibge7: 'inválido', cnpj: '2' }, { id_ibge7: null, cnpj: '3' },
    ] }))
    await store.fetchEstabelecimentos('2025-01-01', null)
    expect(axios.get).toHaveBeenLastCalledWith(API_ENDPOINTS.geoEstabelecimentos, {
      params: { data_inicio: '2025-01-01' },
    })
    expect(store.estabelecimentosPorIbge7.get(1100015)).toHaveLength(1)
    await store.fetchEstabelecimentos('2025-01-01', null)
    expect(axios.get).toHaveBeenCalledTimes(3)
    axios.get.mockResolvedValueOnce(response({ estabelecimentos: [] }))
    await store.fetchEstabelecimentos('2025-01-01', '2025-12-31')
    expect(axios.get).toHaveBeenLastCalledWith(API_ENDPOINTS.geoEstabelecimentos, {
      params: { data_inicio: '2025-01-01', data_fim: '2025-12-31' },
    })
    axios.get.mockResolvedValueOnce(response({ estabelecimentos: [] }))
    await store.fetchEstabelecimentos()
    expect(axios.get).toHaveBeenLastCalledWith(API_ENDPOINTS.geoEstabelecimentos, { params: {} })
    axios.get.mockRejectedValueOnce(new Error('geo indisponível'))
    await store.fetchEstabelecimentos('2026-01-01', '2026-12-31')
    expect(errorLog).toHaveBeenCalledWith('Erro ao buscar estabelecimentos geo:', expect.any(Error))
    axios.get.mockResolvedValueOnce(response([{ cnpj: '1' }]))
    await store.fetchCnpjLookup()
    expect(store.cnpjLookup).toEqual([{ cnpj: '1' }])
    axios.get.mockRejectedValueOnce(new Error('offline'))
    await store.fetchCnpjLookup()
    expect(errorLog).toHaveBeenCalled()

    global.fetch = vi.fn().mockResolvedValue({ json: async () => store.municipiosGeoJson })
    await store.loadMunicipiosGeo()
    expect(global.fetch).toHaveBeenCalledWith('/geo/brasil-mun.json')
    global.fetch.mockRejectedValueOnce(new Error('offline'))
    await store.loadMunicipiosGeo()
    expect(errorLog).toHaveBeenCalled()
  })

  it('trata preferências, contratos, cancelamentos e paginação da análise de risco', async () => {
    const store = useRiskIndicatorsStore()
    axios.get.mockResolvedValueOnce(response({ ui: { selectedRiskIndicator: '  ticket_medio  ' } }))
    await store.loadPreferences()
    await store.loadPreferences()
    expect(axios.get).toHaveBeenCalledTimes(1)
    expect(store.selectedRiskIndicator).toBe('ticket_medio')
    await store.saveSelectedRiskIndicator()
    expect(axios.put).toHaveBeenCalledWith(API_ENDPOINTS.preferencesUi, { ui: { selectedRiskIndicator: 'ticket_medio' } })

    store.setSelectedRiskIndicator('ticket_medio')
    store.setSelectedRiskIndicator('falecidos')
    await Promise.resolve()
    expect(store.selectedRiskIndicator).toBe('falecidos')
    axios.put.mockRejectedValueOnce(new Error('offline'))
    await store.saveSelectedRiskIndicator()

    const consoleError = vi.spyOn(console, 'error').mockImplementation(() => {})
    store.preferencesLoaded = false
    axios.get.mockResolvedValueOnce(response({ ui: null }))
    await expect(store.loadPreferences()).rejects.toThrow('Preferencias sem contrato')
    expect(store.preferencesError).toContain('preferências')
    axios.get.mockRejectedValueOnce(new Error('offline'))
    await expect(store.loadPreferences()).rejects.toThrow('offline')

    await store.fetchRiskIndicatorSummary(null)
    expect(axios.get).toHaveBeenCalledTimes(3)
    const beforeMissingTableIndicator = axios.get.mock.calls.length
    await store.fetchRiskIndicatorEstablishments(null)
    expect(axios.get).toHaveBeenCalledTimes(beforeMissingTableIndicator)
    axios.get.mockResolvedValueOnce(response({ municipios: [], kpis: {} }))
    await store.fetchRiskIndicatorSummary('ticket_medio', { uf: 'RO' })
    expect(store.summaryParamsKey).toBe(JSON.stringify({ indicador: 'ticket_medio', params: { uf: 'RO' } }))
    axios.get.mockRejectedValueOnce({ __cancel: true })
    axios.isCancel.mockReturnValueOnce(true)
    await store.fetchRiskIndicatorSummary('falecidos')
    expect(store.summaryError).toBeNull()

    const table = { items: [{ cnpj: '1' }], total: 1, page: 2, page_size: 5, sort_field: 'valor', sort_order: 'asc', kpis: { x: 1 } }
    axios.get.mockResolvedValueOnce(response(table))
    await store.fetchRiskIndicatorEstablishments('ticket_medio', {}, { page: 2, pageSize: 5, sortField: 'valor', sortOrder: 1 })
    expect(store.cnpjs).toEqual(table.items)
    expect(store.cnpjKpis).toEqual({ x: 1 })
    expect(store.cnpjsSortOrder).toBe(1)
    expect(axios.get).toHaveBeenLastCalledWith(API_ENDPOINTS.analyticsIndicadoresAnaliseCnpjs, expect.objectContaining({
      params: expect.objectContaining({ page: 2, page_size: 5, sort_order: 'asc' }),
    }))
    axios.get.mockResolvedValueOnce(response({ ...table, sort_order: 'desc', kpis: undefined }))
    await store.fetchRiskIndicatorEstablishments('ticket_medio')
    expect(store.cnpjKpis).toBeNull()
    expect(store.cnpjsSortOrder).toBe(-1)
    axios.get.mockResolvedValueOnce(response({ ...table, page: 99 }))
    await store.fetchRiskIndicatorEstablishments('ticket_medio')
    expect(store.tableError).toContain('tabela')
    axios.get.mockRejectedValueOnce({ __cancel: true })
    axios.isCancel.mockReturnValueOnce(true)
    await store.fetchRiskIndicatorEstablishments('ticket_medio')
    expect(consoleError).toHaveBeenCalled()
    store.reset()
    expect(store.cnpjsPage).toBe(1)
    expect(store.summaryParamsKey).toBeNull()
    expect(store.isLoading).toBe(false)
  })

  it('deduplica preferências e descarta requisições obsoletas da análise de risco', async () => {
    const store = useRiskIndicatorsStore()
    vi.spyOn(console, 'error').mockImplementation(() => {})
    const preferences = deferred()
    axios.get.mockImplementationOnce(() => preferences.promise)
    const firstPreferencesLoad = store.loadPreferences()
    const duplicatePreferencesLoad = store.loadPreferences()
    expect(axios.get).toHaveBeenCalledTimes(1)
    preferences.resolve(response({ ui: { selectedRiskIndicator: '   ' } }))
    await Promise.all([firstPreferencesLoad, duplicatePreferencesLoad])
    expect(store.selectedRiskIndicator).toBeNull()
    expect(store.preferencesLoaded).toBe(true)
    store.setSelectedRiskIndicator(null)

    store.preferencesLoaded = false
    axios.get.mockResolvedValueOnce(response({ ui: { selectedRiskIndicator: 42 } }))
    await expect(store.loadPreferences()).rejects.toThrow('Preferencias sem contrato')

    const staleSummary = deferred()
    const currentSummary = deferred()
    axios.get.mockImplementationOnce(() => staleSummary.promise).mockImplementationOnce(() => currentSummary.promise)
    const staleSummaryRequest = store.fetchRiskIndicatorSummary('antigo')
    const currentSummaryRequest = store.fetchRiskIndicatorSummary('atual')
    staleSummary.reject(new Error('resposta obsoleta'))
    await staleSummaryRequest
    currentSummary.resolve(response({ municipios: [{ id_ibge7: 1 }], kpis: { total: 1 } }))
    await currentSummaryRequest
    expect(store.summaryError).toBeNull()
    expect(store.kpis).toEqual({ total: 1 })

    const staleTable = deferred()
    const currentTable = deferred()
    axios.get.mockImplementationOnce(() => staleTable.promise).mockImplementationOnce(() => currentTable.promise)
    const staleTableRequest = store.fetchRiskIndicatorEstablishments('antigo')
    const currentTableRequest = store.fetchRiskIndicatorEstablishments('atual')
    staleTable.reject(new Error('tabela obsoleta'))
    await staleTableRequest
    currentTable.resolve(response({
      items: [], total: 0, page: 1, page_size: 20, sort_field: 'cnpj', sort_order: 'desc',
    }))
    await currentTableRequest
    expect(store.tableError).toBeNull()
    expect(store.cnpjsSortField).toBe('cnpj')

    const pendingSummary = deferred()
    const pendingTable = deferred()
    axios.get.mockImplementationOnce(() => pendingSummary.promise).mockImplementationOnce(() => pendingTable.promise)
    const summaryDuringReset = store.fetchRiskIndicatorSummary('reset')
    const tableDuringReset = store.fetchRiskIndicatorEstablishments('reset')
    store.reset()
    pendingSummary.resolve(response({ municipios: [], kpis: {} }))
    pendingTable.resolve(response({ items: [], total: 0, page: 1, page_size: 20, sort_field: 'cnpj', sort_order: 'asc' }))
    await Promise.all([summaryDuringReset, tableDuringReset])
    expect(store.kpis).toBeNull()
    expect(store.cnpjs).toEqual([])
    expect(store.isLoading).toBe(false)
    expect(store.isTableLoading).toBe(false)
  })

  it('aplica tema e percorre estados de preferências válidos, ausentes e indisponíveis', async () => {
    vi.useFakeTimers()
    const store = useThemeStore()
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {})
    store.setMode('light')
    await Promise.resolve()
    expect(store.isDark).toBe(false)
    expect(document.documentElement.classList.contains('light-mode')).toBe(true)
    store.toggleTheme()
    await Promise.resolve()
    expect(store.isDark).toBe(true)
    store.toggleTheme()
    await Promise.resolve()
    expect(store.isDark).toBe(false)

    axios.put.mockRejectedValueOnce(new Error('offline'))
    store.setMode('dark')
    await Promise.resolve()
    expect(warn).toHaveBeenCalled()

    axios.get.mockResolvedValueOnce(response({ ui: null }))
    const putsBeforeMissingUi = axios.put.mock.calls.length
    await store.initTheme()
    expect(axios.put).toHaveBeenCalledTimes(putsBeforeMissingUi + 1)
    expect(axios.put).toHaveBeenLastCalledWith(API_ENDPOINTS.preferencesUi, { ui: { themeMode: 'dark', themePalette: 'carbon' } })
    const putsBeforeNormalized = axios.put.mock.calls.length
    axios.get.mockResolvedValueOnce(response({ ui: { themeMode: 'dark', themePalette: 'carbon' } }))
    await store.initTheme()
    expect(axios.put).toHaveBeenCalledTimes(putsBeforeNormalized)
    const putsBeforePaletteChange = axios.put.mock.calls.length
    axios.get.mockResolvedValueOnce(response({ ui: { themeMode: 'light', themePalette: 'azul_dark' } }))
    await store.initTheme()
    expect(store.isDark).toBe(false)
    expect(store.currentPalette).toBe('carbon')
    expect(axios.put).toHaveBeenCalledTimes(putsBeforePaletteChange + 1)
    store.currentPalette = 'azul_dark'
    store.setMode('dark')
    expect(document.documentElement.classList.contains('palette-azul-dark')).toBe(true)
    expect(store.tokens.primary).toBeTruthy()
    store.currentPalette = 'desconhecida'
    store.setMode('claro')
    expect(document.documentElement.classList.contains('light-mode')).toBe(true)
    expect(store.tokens.primary).toBeTruthy()
    axios.get.mockRejectedValueOnce(new Error('offline'))
    await store.initTheme()
    expect(warn).toHaveBeenCalled()
    await vi.runOnlyPendingTimersAsync()
  })

  it('valida seleção de alvos, parâmetros, respostas, cancelamento e falhas de tabela', async () => {
    const store = useTargetsStore()
    expect(store.selectedTarget).toBe(DEFAULT_TARGET_KEY)
    expect(store.targetKpis).toHaveLength(5)
    expect(() => store.setSelectedTarget('inexistente')).toThrow('Alvo sem configuração: inexistente')
    expect(() => store.setSelectedTarget('aumento_atipico_vendas')).toThrow('Alvo desabilitado não pode ser selecionado')

    store.kpis = [{ label: 'Farmácias', value: 2 }]
    expect(store.targetKpis).toEqual(store.kpis)
    store.setSelectedTarget('diabetes_menor_20')
    expect(store.page).toBe(1)
    expect(store.sortField).toBe('valor_incompativel')
    expect(localStorage.getItem('sentinela_targets_selected')).toBe('diabetes_menor_20')

    const filters = (await import('@/stores/filters')).useFilterStore()
    filters.indicadoresTabelaApiParams
    axios.get.mockResolvedValueOnce(response({ items: [{ cnpj: 'x' }], total: 1, page: 1, page_size: 20, sort_order: 'desc' }))
    await store.loadCurrentTarget()
    expect(store.rows).toEqual([{ cnpj: 'x' }])
    expect(store.sortField).toBe('valor_incompativel')
    expect(store.sortOrder).toBe(-1)

    store.updateTableState({ rows: 10, first: 20, sortField: 'cnpj', sortOrder: 1 })
    await Promise.resolve()
    expect(store.page).toBe(3)
    expect(store.rowsPerPage).toBe(10)

    store.updateTableState()
    await Promise.resolve()
    expect(store.page).toBe(1)
    axios.get.mockResolvedValueOnce(response({
      kpis: [{ id: 'kpi' }], mapa: [{ id_ibge7: 1 }], items: [{ cnpj: 'x' }],
      total: 8, page: 2, page_size: 7, sort_field: 'cnpj', sort_order: 'asc',
    }))
    await store.loadCurrentTarget()
    expect(store.kpis).toEqual([{ id: 'kpi' }])
    expect(store.mapData).toEqual([{ id_ibge7: 1 }])
    expect(store.totalRecords).toBe(8)
    expect(store.page).toBe(2)
    expect(store.rowsPerPage).toBe(7)
    expect(store.sortField).toBe('cnpj')
    expect(store.sortOrder).toBe(1)

    const log = vi.spyOn(console, 'error').mockImplementation(() => {})
    axios.get.mockRejectedValueOnce(new Error('offline'))
    await store.loadCurrentTarget()
    expect(store.error).toBe('Nao foi possivel carregar o alvo selecionado.')
    axios.isCancel.mockReturnValueOnce(true)
    axios.get.mockRejectedValueOnce(new Error('cancelado'))
    await store.loadCurrentTarget()
    expect(store.error).toBeNull()
    expect(store.isLoading).toBe(false)
    expect(log).toHaveBeenCalled()
  })

  it('preserva estado de fonte pendente e falha quando o endpoint configurado não existe', async () => {
    const target = TARGET_GROUPS.flatMap((group) => group.targets).find((item) => item.key === DEFAULT_TARGET_KEY)
    const originalStatus = target.sourceStatus
    const originalEndpoint = target.endpoint
    try {
      localStorage.setItem('sentinela_targets_selected', 'alvo-removido')
      target.sourceStatus = 'pending'
      const store = useTargetsStore()
      expect(store.selectedTarget).toBe(DEFAULT_TARGET_KEY)
      expect(store.sourceNotice).toContain('ainda não conectada')

      store.kpis = [{ id: 'antigo' }]
      store.mapData = [{ id: 'antigo' }]
      store.rows = [{ id: 'antigo' }]
      store.totalRecords = 9
      store.setSelectedTarget(DEFAULT_TARGET_KEY)
      expect(store.kpis).toEqual([])
      expect(store.mapData).toEqual([])
      expect(store.rows).toEqual([])
      expect(store.totalRecords).toBe(0)
      expect(store.sourceNotice).toContain('ainda não conectada')
      expect(store.isLoading).toBe(false)
      const callsBeforePendingLoad = axios.get.mock.calls.length
      await store.loadCurrentTarget()
      expect(axios.get).toHaveBeenCalledTimes(callsBeforePendingLoad)

      target.sourceStatus = 'ready'
      target.endpoint = 'endpointAusente'
      await expect(store.loadCurrentTarget()).rejects.toThrow(`Endpoint sem configuração para alvo: ${DEFAULT_TARGET_KEY}`)
    } finally {
      target.sourceStatus = originalStatus
      target.endpoint = originalEndpoint
    }
  })

  it('exibe o estado de atualização, consulta progresso, aplica e trata falhas de download', async () => {
    vi.useFakeTimers()
    const store = useSystemUpdateStore()
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {})
    const error = vi.spyOn(console, 'error').mockImplementation(() => {})
    const update = (status) => ({
      status, current_version: '1.0', latest_version: '2.0', minimum_supported_version: '1.5',
      download_url: 'https://example.invalid/a', release_notes_url: null,
      checked_at: '2026-10-02T12:00:00Z', source: 'remote', message: 'msg',
      block_title: null, block_message: null, blocked_since: null,
    })

    expect(store.statusLabel).toBe('—')
    expect(store.statusTone).toBe('muted')
    expect(store.checkedAtFormatted).toBeNull()
    expect(store.downloadStatusLabel).toBe('Aguardando')
    axios.get.mockRejectedValueOnce(new Error('offline'))
    await store.fetchUpdateStatus()
    expect(store.status).toBe('verification_unavailable')
    expect(store.source).toBe('none')
    axios.post.mockResolvedValueOnce(response(update('current')))
    await store.forceCheckUpdate()
    expect(store.isCurrent).toBe(true)
    expect(store.statusLabel).toBe('Atualizado')
    expect(store.statusTone).toBe('ok')
    expect(store.checkedAtFormatted).toContain('2026')
    store.status = 'update_required'
    expect(store.isBlocked).toBe(true)
    expect(store.isExecutionBlocked).toBe(false)
    expect(store.statusLabel).toBe('Atualização obrigatória')
    expect(store.statusTone).toBe('critical')
    store.status = 'execution_blocked'
    expect(store.isBlocked).toBe(true)
    expect(store.isExecutionBlocked).toBe(true)
    expect(store.statusLabel).toContain('bloqueada')
    expect(store.statusTone).toBe('critical')
    store.status = 'update_available'
    expect(store.hasUpdate).toBe(true)
    expect(store.statusTone).toBe('warn')
    expect(store.statusLabel).toBe('Atualização disponível')
    store.status = 'offline_cached'
    expect(store.isOffline).toBe(true)
    expect(store.statusLabel).toBe('Verificação offline')
    expect(store.statusTone).toBe('muted')
    store.status = 'verification_unavailable'
    expect(store.isUnavailable).toBe(true)
    expect(store.statusLabel).toBe('Não verificado')
    expect(store.statusTone).toBe('muted')
    store.status = 'unknown'
    expect(store.statusLabel).toBe('—')
    expect(store.statusTone).toBe('muted')
    store.checkedAt = 'not-a-date'
    expect(store.checkedAtFormatted).toBeNull()

    axios.get.mockResolvedValueOnce(response(update('offline_cached')))
    await store.fetchUpdateStatus()
    expect(store.isOffline).toBe(true)
    store.status = 'current'
    store.message = 'preservar status conhecido'
    axios.get.mockRejectedValueOnce(new Error('consulta indisponível'))
    await store.fetchUpdateStatus()
    expect(store.status).toBe('current')
    expect(store.message).toBe('preservar status conhecido')
    expect(warn).toHaveBeenCalled()

    axios.post.mockRejectedValueOnce(new Error('offline'))
    await store.forceCheckUpdate()
    expect(store.loading).toBe(false)
    expect(warn).toHaveBeenCalled()
    axios.post.mockResolvedValueOnce(response(update('current')))
    await vi.advanceTimersByTimeAsync(15 * 60 * 1000)
    expect(axios.post).toHaveBeenCalledWith(API_ENDPOINTS.systemCheckUpdate)
    axios.post.mockRejectedValueOnce(new Error('poll falhou'))
    await vi.advanceTimersByTimeAsync(15 * 60 * 1000)
    expect(store.status).toBe('current')

    await store.startDownload()
    expect(axios.post).toHaveBeenLastCalledWith(API_ENDPOINTS.systemDownloadUpdate, undefined)
    expect(store.downloadStatusLabel).toContain('Baixando')
    expect(store.isDownloading).toBe(true)
    store.closeDownloadDialog()
    expect(store.downloadDialogVisible).toBe(true)
    store.openDownloadDialog()
    store.downloadStatus = 'applying'
    expect(store.downloadStatusLabel).toBe('Preparando arquivos...')
    store.downloadStatus = 'unexpected'
    expect(store.downloadStatusLabel).toBe('')
    store.downloadStatus = 'downloading'
    await store.startDownload('https://example.invalid/second')
    expect(axios.post).toHaveBeenLastCalledWith(API_ENDPOINTS.systemDownloadUpdate, { download_url: 'https://example.invalid/second' })
    axios.get.mockResolvedValueOnce(response({ status: 'downloading', progress: 0.456, error: null }))
    await vi.advanceTimersByTimeAsync(800)
    expect(store.downloadProgress).toBe(46)
    axios.get.mockResolvedValueOnce(response({ status: 'done', progress: 1, error: null }))
    axios.post.mockResolvedValueOnce(response({}))
    await vi.advanceTimersByTimeAsync(800)
    expect(store.downloadDone).toBe(true)
    expect(store.downloadStatusLabel).toContain('iniciando')
    expect(axios.post).toHaveBeenCalledWith(API_ENDPOINTS.systemApplyUpdate)
    store.closeDownloadDialog()
    expect(store.downloadStatus).toBe('idle')

    await store.startDownload('https://example.invalid/custom')
    expect(axios.post).toHaveBeenLastCalledWith(API_ENDPOINTS.systemDownloadUpdate, { download_url: 'https://example.invalid/custom' })
    axios.get.mockResolvedValueOnce(response({ status: 'error', progress: null, error: 'falhou' }))
    await vi.advanceTimersByTimeAsync(800)
    expect(store.downloadFailed).toBe(true)
    expect(store.isDownloading).toBe(false)
    expect(store.downloadStatusLabel).toBe('Falha no download')
    store.closeDownloadDialog()
    expect(store.downloadProgress).toBe(0)
    expect(store.downloadError).toBeNull()

    axios.post.mockRejectedValueOnce({ response: { data: { detail: 'sem espaço' } } })
    await store.startDownload()
    expect(store.downloadError).toBe('sem espaço')
    store.closeDownloadDialog()
    expect(store.downloadStatus).toBe('idle')
    axios.post.mockRejectedValueOnce(new Error('falha ao aplicar'))
    await store.applyUpdate()
    expect(warn).toHaveBeenCalled()
    axios.post.mockRejectedValueOnce(new Error('download error message'))
    await store.startDownload()
    expect(store.downloadError).toBe('download error message')
    axios.post.mockRejectedValueOnce({})
    await store.startDownload()
    expect(store.downloadError).toBe('Erro desconhecido.')
    axios.get.mockRejectedValueOnce(new Error('progresso indisponível'))
    await store.startDownload()
    axios.get.mockRejectedValueOnce(new Error('polling error'))
    await vi.advanceTimersByTimeAsync(800)
    expect(warn).toHaveBeenCalled()
    expect(error).toHaveBeenCalled()
  })
})
