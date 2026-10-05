import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, disposePinia, setActivePinia } from 'pinia'
import { nextTick } from 'vue'
import axios from 'axios'

import { FILTER_ALL_VALUE, FILTER_DEFAULTS, TIMING } from '@/config/constants'
import { useFilterStore } from '@/stores/filters'
import { useGeoStore } from '@/stores/geo'

vi.mock('axios', () => ({
  default: {
    get: vi.fn(),
    put: vi.fn(),
  },
}))

// Campos obrigatórios para exercitar a cascata territorial da store.
const LOCALIDADES = [
  {
    id_ibge7: 1100015,
    id_regiao_saude: 1100001,
    sg_uf: 'RO',
    no_municipio: 'Alta Floresta D’Oeste',
    no_regiao_saude: 'Região Central',
  },
  {
    id_ibge7: 1100205,
    id_regiao_saude: 1100002,
    sg_uf: 'RO',
    no_municipio: 'Porto Velho',
    no_regiao_saude: 'Região Madeira-Mamoré',
  },
  {
    id_ibge7: 1200013,
    id_regiao_saude: 1200003,
    sg_uf: 'AC',
    no_municipio: 'Cruzeiro do Sul',
    no_regiao_saude: 'Região Juruá',
  },
]

describe('store de filtros territoriais', () => {
  let pinia
  let filters

  beforeEach(async () => {
    vi.useFakeTimers()
    localStorage.clear()
    axios.get.mockResolvedValue({
      data: {
        filters: {},
        ui: { sidebarCollapsed: false, sidebarLocked: false },
      },
    })
    axios.put.mockResolvedValue({ data: {} })

    pinia = createPinia()
    setActivePinia(pinia)
    useGeoStore().localidades = LOCALIDADES
    filters = useFilterStore()

    // Deixa a leitura de preferências mockada terminar antes de cada cenário.
    await Promise.resolve()
    await Promise.resolve()
  })

  afterEach(async () => {
    await nextTick()
    await vi.runOnlyPendingTimersAsync()
    disposePinia(pinia)
    vi.useRealTimers()
    localStorage.clear()
  })

  it('deriva UF e região pelo id_ibge7 e envia IDs numéricos à API', async () => {
    const municipio = LOCALIDADES[0]
    filters.selectedUF = 'AC'

    filters.selectedMunicipio = String(municipio.id_ibge7)
    await nextTick()

    expect(filters.selectedUF).toBe(municipio.sg_uf)
    expect(filters.selectedRegiaoSaude).toBe(String(municipio.id_regiao_saude))
    expect(filters.apiParams.idIbge7).toBe(municipio.id_ibge7)
    expect(typeof filters.apiParams.idIbge7).toBe('number')
    expect(filters.apiParams.regiaoId).toBe(municipio.id_regiao_saude)
    expect(typeof filters.apiParams.regiaoId).toBe('number')
  })

  it('deriva a UF ao selecionar região por ID', async () => {
    const regiao = LOCALIDADES[2]

    filters.selectedRegiaoSaude = String(regiao.id_regiao_saude)
    await nextTick()

    expect(filters.selectedUF).toBe(regiao.sg_uf)
    expect(filters.selectedRegiaoSaude).toBe(String(regiao.id_regiao_saude))
  })

  it('limpa o município ao trocar a região dentro da UF selecionada', async () => {
    filters.selectedMunicipio = String(LOCALIDADES[0].id_ibge7)
    await nextTick()
    expect(filters.selectedMunicipio).toBe(String(LOCALIDADES[0].id_ibge7))

    filters.selectedRegiaoSaude = String(LOCALIDADES[1].id_regiao_saude)
    await nextTick()

    expect(filters.selectedUF).toBe('RO')
    expect(filters.selectedRegiaoSaude).toBe(String(LOCALIDADES[1].id_regiao_saude))
    expect(filters.selectedMunicipio).toBe(FILTER_ALL_VALUE)
  })

  it('limpa região e município quando a UF volta ao valor geral', async () => {
    filters.selectedMunicipio = String(LOCALIDADES[0].id_ibge7)
    await nextTick()

    filters.selectedUF = FILTER_ALL_VALUE
    await nextTick()

    expect(filters.selectedRegiaoSaude).toBe(FILTER_ALL_VALUE)
    expect(filters.selectedMunicipio).toBe(FILTER_ALL_VALUE)
    expect(filters.apiParams.regiaoId).toBeNull()
    expect(filters.apiParams.idIbge7).toBeNull()
  })

  it('rejeita nomes textuais nos campos que exigem IDs territoriais', () => {
    filters.selectedRegiaoSaude = 'Região Central'
    expect(() => filters.apiParams).toThrow('Filtro regional invalido: use id_regiao_saude.')

    filters.selectedRegiaoSaude = FILTER_ALL_VALUE
    filters.selectedMunicipio = 'Alta Floresta D’Oeste'
    expect(() => filters.apiParams).toThrow('Filtro municipal invalido: use id_ibge7.')
  })

  it('restaura os filtros territoriais ao padrão', async () => {
    filters.selectedMunicipio = String(LOCALIDADES[0].id_ibge7)
    await nextTick()

    filters.resetFilters()
    await nextTick()

    expect(filters.selectedUF).toBe(FILTER_DEFAULTS.UF)
    expect(filters.selectedRegiaoSaude).toBe(FILTER_DEFAULTS.REGIAO)
    expect(filters.selectedMunicipio).toBe(FILTER_DEFAULTS.MUNICIPIO)
    expect(filters.apiParams.regiaoId).toBeNull()
    expect(filters.apiParams.idIbge7).toBeNull()
  })

  it('normaliza busca de CNPJ e texto de estabelecimento sem misturar os contratos', () => {
    filters.selectedCnpjRaiz = '12.345.678'
    expect(filters.apiParams.cnpjRaiz).toBe('12345678')
    expect(filters.apiParams.estabelecimento).toBeNull()

    filters.selectedCnpjRaiz = '12.345.678/0001-95'
    expect(filters.apiParams.cnpjRaiz).toBe('12345678000195')
    expect(filters.apiParams.estabelecimento).toBeNull()

    filters.selectedCnpjRaiz = '  Farmácia Central  '
    expect(filters.apiParams.cnpjRaiz).toBeNull()
    expect(filters.apiParams.estabelecimento).toBe('Farmácia Central')

    filters.selectedCnpjRaiz = 'F'
    expect(filters.apiParams.cnpjRaiz).toBeNull()
    expect(filters.apiParams.estabelecimento).toBeNull()
  })

  it('converte datas locais e só ativa limites quando os filtros correspondentes estão ligados', () => {
    filters.periodo = [new Date(2025, 2, 4), new Date(2025, 10, 9)]
    filters.volumeAtipicoEnabled = true
    filters.volumeAtipicoPercentualFilter = 1
    filters.dispersaoUfSemFronteiraEnabled = true
    filters.dispersaoUfSemFronteiraPercentual = 500
    filters.seqTipo = 'multiplo'

    expect(filters.apiParams.inicio).toBe('2025-03-04')
    expect(filters.apiParams.fim).toBe('2025-11-09')
    expect(filters.apiParams.volumeAtipicoPercentual).toBe(FILTER_DEFAULTS.VOLUME_ATIPICO_MIN)
    expect(filters.apiParams.dispersaoUfSemFronteiraPercentual).toBe(FILTER_DEFAULTS.DISPERSAO_UF_SEM_FRONTEIRA_MAX)
    expect(filters.apiParams.seqTipo).toBeNull()

    filters.seqDias = [2, 5]
    expect(filters.apiParams.seqTipo).toBe('multiplo')
    expect(filters.apiParams.seqDiasMin).toBe(2)
    expect(filters.apiParams.seqDiasMax).toBe(5)
  })

  it('mantém o contexto nacional independente dos filtros territoriais', async () => {
    const chaveNacional = filters.nationalContextApiParamsKey
    const chaveCompleta = filters.apiParamsKey
    filters.selectedUF = 'RO'
    filters.selectedMunicipio = String(LOCALIDADES[0].id_ibge7)
    await nextTick()

    expect(filters.apiParams.uf).toBe('RO')
    expect(filters.apiParams.idIbge7).toBe(LOCALIDADES[0].id_ibge7)
    expect(filters.apiParamsKey).not.toBe(chaveCompleta)
    expect(filters.nationalContextApiParamsKey).toBe(chaveNacional)
    expect(filters.indicadoresTabelaApiParams.id_ibge7).toBe(LOCALIDADES[0].id_ibge7)
  })

  it('persiste alterações após o debounce com os campos normalizados da sessão', async () => {
    filters.selectedSocioFalecido = true
    filters.populacaoMunicipio = [1000, 5000]
    filters.seqSeveridade = 3
    await nextTick()
    await vi.advanceTimersByTimeAsync(TIMING.FILTER_DEBOUNCE + 1)

    const persisted = JSON.parse(localStorage.getItem('sentinela_filters'))
    expect(persisted).toMatchObject({
      selectedSocioFalecido: true,
      populacaoMunicipio: [1000, 5000],
      seqSeveridade: 3,
    })
    expect(axios.put).toHaveBeenCalledWith(expect.any(String), {
      filters: expect.objectContaining({
        selectedSocioFalecido: true,
        populacaoMunicipio: [1000, 5000],
        seqSeveridade: 3,
      }),
    })
  })
})
