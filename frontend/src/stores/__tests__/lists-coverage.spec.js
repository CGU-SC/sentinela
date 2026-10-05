import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, disposePinia, setActivePinia } from 'pinia'
import axios from 'axios'

import { API_ENDPOINTS } from '@/config/api'
import { useCnpjDetailStore } from '@/stores/cnpjDetail'
import { useEvidenciasStore, chaveEvidencia } from '@/stores/evidencias'
import { useFarmaciaListsStore } from '@/stores/farmaciaLists'

vi.mock('axios', () => ({
  default: { get: vi.fn(), put: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn() },
}))

const response = (data) => ({ data })
const EMPTY_COPY = {
  exists: false, valid: false, kind: 'joint', evidencias_backup_valid: false,
  watchlist_count: null, evidencias_count: null, missing_watchlist_count: null,
  missing_evidencias_count: null, farmacias_mantidas_count: null,
}
const RECOVERY = { backup: { ...EMPTY_COPY }, corrupt: { ...EMPTY_COPY } }
const FARMACIA = { cnpj: '12345678000195', razaoSocial: 'Farmácia A', adicionadoEm: '2026-01-01', observacao: '' }
const EVIDENCIAS = [
  { id: 1, cnpj: FARMACIA.cnpj, tipo: 'hora', dt_janela: '2025-01-02', hora: 9, snapshot: { horario: '09:00' }, criado_em: '2025-01-02T10:00:00Z' },
  { id: 2, cnpj: FARMACIA.cnpj, tipo: 'dia', dt_janela: '2025-01-01', hora: null, criado_em: '2025-01-03T10:00:00Z' },
  { id: 3, cnpj: FARMACIA.cnpj, tipo: 'autorizacao', dt_janela: '2025-01-02', hora: 9, num_autorizacao: 'A-3', criado_em: '2025-01-04T10:00:00Z' },
]

describe('cobertura de evidências e lista de farmácias', () => {
  let pinia

  function setupBackend({ watchlist = [], evidence = [], ultima = { farmacias: [], removido_em: null } } = {}) {
    axios.get.mockImplementation(async (url) => {
      if (url === API_ENDPOINTS.preferences) return response({ watchlist })
      if (url === API_ENDPOINTS.evidencias) return response(evidence)
      if (url === API_ENDPOINTS.preferencesRecoveryStatus) return response(RECOVERY)
      if (url === API_ENDPOINTS.preferencesWatchlistUltimaRemocao) return response(ultima)
      return response({})
    })
    axios.put.mockImplementation(async (url, payload) => (
      url === API_ENDPOINTS.preferencesWatchlist ? response({ watchlist: payload.interesse }) : response({})
    ))
    axios.post.mockResolvedValue(response({}))
    axios.patch.mockResolvedValue(response({}))
    axios.delete.mockResolvedValue(response({}))
  }

  async function initialize({ watchlist = [], evidence = [], ultima } = {}) {
    pinia = createPinia()
    setActivePinia(pinia)
    setupBackend({ watchlist, evidence, ultima })
    const listas = useFarmaciaListsStore()
    const evidencias = useEvidenciasStore()
    for (let i = 0; i < 10; i += 1) await Promise.resolve()
    return { listas, evidencias }
  }

  beforeEach(() => {
    vi.clearAllMocks()
    localStorage.clear()
    pinia = createPinia()
    setActivePinia(pinia)
    setupBackend()
  })

  afterEach(() => {
    disposePinia(pinia)
    localStorage.clear()
  })

  it('carrega snapshots, recuperação, última remoção e normaliza contratos inválidos', async () => {
    localStorage.setItem('sentinela_farmacia_lists', JSON.stringify({ interesse: [FARMACIA] }))
    setupBackend({ watchlist: [], ultima: { farmacias: [{ cnpj: 'x', razaoSocial: 'X', evidencias_count: 2 }], removido_em: '2026-01-01' } })
    const store = useFarmaciaListsStore()
    for (let i = 0; i < 10; i += 1) await Promise.resolve()
    expect(store.loadState).toBe('ready')
    expect(store.localRecoveryAvailable).toBe(true)
    expect(store.localSnapshot).toEqual([FARMACIA])
    expect(store.ultimaRemocao).toHaveLength(1)
    expect(store.canEdit).toBe(true)
    expect(store.getObservacao(FARMACIA.cnpj)).toBe('')

    store.recoveryOptions = {
      principal: { evidencias_error: true },
      backup: { ...EMPTY_COPY }, corrupt: { ...EMPTY_COPY },
    }
    expect(store.recoveryAvailable).toBe(true)
    store.recoveryOptions = {
      backup: { ...EMPTY_COPY, exists: true, valid: true, watchlist_count: 2, missing_evidencias_count: 1 },
      corrupt: { ...EMPTY_COPY },
    }
    expect(store.recoveryAvailable).toBe(true)
    store.recoveryOptions = {
      backup: { ...EMPTY_COPY, exists: true, valid: true, watchlist_count: 0 },
      corrupt: { ...EMPTY_COPY, exists: true, valid: true, missing_watchlist_count: 1 },
    }
    expect(store.recoveryAvailable).toBe(true)
    store.recoveryOptions = {
      backup: { ...EMPTY_COPY, exists: true, valid: true }, corrupt: { ...EMPTY_COPY },
    }
    expect(store.recoveryAvailable).toBe(false)

    for (const backup of [
      { ...EMPTY_COPY, exists: true, valid: false },
      { ...EMPTY_COPY, exists: true, valid: true, evidencias_error: 'cópia inválida' },
    ]) {
      axios.get.mockResolvedValueOnce(response({ backup, corrupt: { ...EMPTY_COPY } }))
      await store.loadRecoveryOptions()
      expect(store.recoveryOptions.backup).toEqual(backup)
      expect(store.recoveryAvailable).toBe(true)
    }

    await store.loadRecoveryOptions()
    expect(store.recoveryOptions).toEqual(RECOVERY)
    await store.loadUltimaRemocao()
    expect(store.ultimaRemocao).toHaveLength(1)
    axios.get.mockResolvedValueOnce(response({ backup: { ...EMPTY_COPY, watchlist_count: -1 }, corrupt: { ...EMPTY_COPY } }))
    await store.loadRecoveryOptions()
    expect(store.recoveryOptions).toBeNull()
    expect(store.recoveryError).toContain('Verifique se o servidor está atualizado')
    axios.get.mockResolvedValueOnce(response({ farmacias: [{ cnpj: 'x' }], removido_em: 3 }))
    await store.loadUltimaRemocao()
    expect(store.ultimaRemocao).toEqual([])
    expect(store.ultimaRemocaoError).toContain('última remoção')
  })

  it('recupera JSON local inválido e relata falha ao gravar cópia ou recarregar evidências', async () => {
    localStorage.setItem('sentinela_farmacia_lists', '{json inválido')
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {})
    const { listas } = await initialize({ watchlist: [FARMACIA] })
    expect(listas.localSnapshot).toEqual([FARMACIA])

    const originalSetItem = Storage.prototype.setItem
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(function setItem(key, value) {
      if (key === 'sentinela_farmacia_lists') throw new Error('armazenamento indisponível')
      return originalSetItem.call(this, key, value)
    })
    expect(await listas.setObservacao(FARMACIA.cnpj, 'nota local')).toBe(true)
    expect(warn).toHaveBeenCalledWith(
      '[farmaciaLists] Cópia local não pôde ser atualizada:',
      expect.any(Error),
    )

    axios.get.mockRejectedValueOnce(new Error('cesta indisponível'))
    expect(await listas.removerInteresse(FARMACIA.cnpj)).toBe(true)
    expect(listas.error).toContain('não foi possível atualizar as evidências na tela')
  })

  it('ignora snapshot local cujo campo de monitoradas não seja uma lista', async () => {
    localStorage.setItem('sentinela_farmacia_lists', JSON.stringify({ interesse: { cnpj: FARMACIA.cnpj } }))
    const { listas } = await initialize()
    expect(listas.localSnapshot).toEqual([])
    expect(listas.localRecoveryAvailable).toBe(false)
  })

  it('lida com erros de carregamento e mantém a cópia local quando a lista remota vem vazia', async () => {
    localStorage.setItem('sentinela_farmacia_lists', JSON.stringify({ interesse: [FARMACIA] }))
    axios.get.mockImplementation(async (url) => {
      if (url === API_ENDPOINTS.preferences) return response({})
      if (url === API_ENDPOINTS.preferencesRecoveryStatus) throw { response: { data: { detail: 'erro detalhado' } } }
      return response({})
    })
    const log = vi.spyOn(console, 'error').mockImplementation(() => {})
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {})
    const store = useFarmaciaListsStore()
    for (let i = 0; i < 10; i += 1) await Promise.resolve()
    expect(store.loadState).toBe('error')
    expect(store.error).toContain('Nenhuma lista foi alterada')
    expect(store.localRecoveryAvailable).toBe(true)
    expect(store.recoveryError).toBe('erro detalhado')
    expect(store.canEdit).toBe(false)
    expect(log).toHaveBeenCalled()
    expect(warn).toHaveBeenCalled()

    store.localSnapshot = [FARMACIA]
    store.loadState = 'ready'
    store.interesse = []
    store.recoveryOptions = {
      backup: { ...EMPTY_COPY, exists: true, valid: true, watchlist_count: 1 },
      corrupt: { ...EMPTY_COPY },
    }
    expect(store.recoveryAvailable).toBe(true)
    store.loadState = 'error'
    expect(store.recoveryAvailable).toBe(true)
  })

  it('adiciona, observa e alterna interesse com validação de resposta e falha HTTP', async () => {
    const { listas } = await initialize()
    expect(listas.loadState).toBe('ready')
    expect(await listas.adicionarInteresse(FARMACIA.cnpj, 'Farmácia A')).toBe(true)
    expect(listas.isInteresse(FARMACIA.cnpj)).toBe(true)
    expect(listas.localSnapshot).toEqual(listas.interesse)
    expect(await listas.adicionarInteresse(FARMACIA.cnpj, 'Outro nome')).toBe(true)
    expect(axios.put).toHaveBeenCalledTimes(1)

    expect(await listas.setObservacao(FARMACIA.cnpj, 'verificar')).toBe(true)
    expect(listas.getObservacao(FARMACIA.cnpj)).toBe('verificar')
    expect(await listas.setObservacao('ausente', 'nota')).toBe(true)
    expect(await listas.toggleInteresse('98765432000100', 'Farmácia B')).toBe(true)
    expect(listas.isInteresse('98765432000100')).toBe(true)
    expect(await listas.toggleInteresse('98765432000100', 'Farmácia B')).toBe(true)
    expect(listas.isInteresse('98765432000100')).toBe(false)

    const log = vi.spyOn(console, 'error').mockImplementation(() => {})
    axios.put.mockResolvedValueOnce(response({}))
    expect(await listas.adicionarInteresse('11111111000111', 'Inválida')).toBe(false)
    expect(listas.error).toContain('não foi confirmada')
    axios.put.mockRejectedValueOnce({ response: { data: { detail: 'servidor recusou' } } })
    expect(await listas.setObservacao(FARMACIA.cnpj, 'outra')).toBe(false)
    expect(listas.error).toBe('servidor recusou')
    expect(listas.saving).toBe(false)
    expect(log).toHaveBeenCalled()

    listas.saving = true
    expect(await listas.toggleInteresse(FARMACIA.cnpj)).toBe(false)
    expect(await listas.adicionarInteresse('22222222000122', 'Bloqueada')).toBe(false)
    expect(await listas.removerInteresse(FARMACIA.cnpj)).toBe(false)
    expect(await listas.setObservacao(FARMACIA.cnpj, 'bloqueada')).toBe(false)
    expect(await listas.desfazerRemocao(FARMACIA.cnpj)).toBe(false)
    expect(await listas.restoreFromLocal()).toBe(false)
  })

  it('remove apenas após confirmar evidências, atualiza a cesta e oferece desfazer', async () => {
    const removida = { ...FARMACIA, evidencias_count: 2 }
    const { listas, evidencias } = await initialize({ watchlist: [FARMACIA], evidence: EVIDENCIAS, ultima: { farmacias: [removida], removido_em: '2026-01-01' } })
    expect(evidencias.loadState).toBe('ready')
    expect(evidencias.contar(FARMACIA.cnpj)).toBe(3)
    expect(listas.canEdit).toBe(true)
    expect(await listas.removerInteresse('nao-monitorada')).toBe(true)
    expect(listas.isInteresse(FARMACIA.cnpj)).toBe(true)

    const fallbackCnpj = '33333333000133'
    evidencias.itens = [...evidencias.itens, { id: 99, cnpj: fallbackCnpj, tipo: 'dia', dt_janela: '2025-02-01' }]
    const fallbackNameRemoval = listas.removerInteresse(fallbackCnpj)
    await vi.waitFor(() => expect(evidencias.remocaoPendente).not.toBeNull())
    expect(evidencias.remocaoPendente.nome).toBe(fallbackCnpj)
    evidencias.responderRemocao(false)
    await expect(fallbackNameRemoval).resolves.toBeNull()
    evidencias.itens = EVIDENCIAS

    const cancelado = listas.removerInteresse(FARMACIA.cnpj)
    await vi.waitFor(() => expect(evidencias.remocaoPendente).not.toBeNull())
    expect(evidencias.remocaoPendente).toMatchObject({ cnpj: FARMACIA.cnpj, nome: FARMACIA.razaoSocial, quantidade: 3 })
    evidencias.responderRemocao(false)
    await expect(cancelado).resolves.toBeNull()
    axios.get.mockResolvedValueOnce(response([]))
    const confirmado = listas.removerInteresse(FARMACIA.cnpj, 'Nome informado')
    await vi.waitFor(() => expect(evidencias.remocaoPendente).not.toBeNull())
    expect(evidencias.remocaoPendente.nome).toBe('Nome informado')
    evidencias.responderRemocao(true)
    await expect(confirmado).resolves.toBe(true)
    expect(listas.isInteresse(FARMACIA.cnpj)).toBe(false)
    expect(evidencias.itens).toEqual([])
    expect(listas.ultimaRemocao).toEqual([removida])
    expect(await listas.desfazerRemocao('ausente')).toBe(false)
    axios.post.mockResolvedValueOnce(response({ watchlist: [FARMACIA] }))
    expect(await listas.desfazerRemocao(FARMACIA.cnpj)).toBe(true)
    expect(listas.isInteresse(FARMACIA.cnpj)).toBe(true)
  })

  it('trata erro ao verificar evidências, cancelar e concluir falhas de remoção', async () => {
    const { listas, evidencias } = await initialize({ watchlist: [FARMACIA], evidence: EVIDENCIAS })
    evidencias.loadState = 'error'
    axios.get.mockRejectedValueOnce(new Error('falha de verificação'))
    expect(await listas.removerInteresse(FARMACIA.cnpj)).toBe(false)
    expect(listas.error).toContain('Não foi possível verificar')

    evidencias.loadState = 'ready'
    evidencias.itens = []
    axios.put.mockRejectedValueOnce(new Error('offline'))
    await expect(listas.removerInteresse(FARMACIA.cnpj, 'Nome alternativo')).resolves.toBe(false)
    expect(listas.error).toContain('Não foi possível salvar')
  })

  it('revalida a permissão após a confirmação pública de remoção', async () => {
    const { listas, evidencias } = await initialize({ watchlist: [FARMACIA], evidence: EVIDENCIAS })
    const pendingRemoval = listas.removerInteresse(FARMACIA.cnpj)
    await vi.waitFor(() => expect(evidencias.remocaoPendente).not.toBeNull())
    listas.saving = true
    evidencias.responderRemocao(true)
    await expect(pendingRemoval).resolves.toBe(false)
    expect(axios.put).not.toHaveBeenCalledWith(API_ENDPOINTS.preferencesWatchlist, expect.anything())
    listas.saving = false
  })

  it('restaura backups, cópias locais e farmácias removidas em fluxos válidos e inválidos', async () => {
    const { listas, evidencias } = await initialize({ ultima: { farmacias: [{ ...FARMACIA, evidencias_count: 0 }], removido_em: null } })
    expect(await listas.restoreFromFile('invalida')).toBe(false)
    listas.saving = true
    expect(await listas.restoreFromFile('backup')).toBe(false)
    listas.saving = false
    axios.post.mockResolvedValueOnce(response({ watchlist: [FARMACIA] }))
    expect(await listas.restoreFromFile('backup', true)).toBe(true)
    expect(axios.post).toHaveBeenCalledWith(API_ENDPOINTS.preferencesRecovery, { source: 'backup' }, { params: { incluir_evidencias_backup: true } })
    expect(listas.loadState).toBe('ready')

    axios.post.mockResolvedValueOnce(response({}))
    expect(await listas.restoreFromFile('corrupt')).toBe(false)
    expect(listas.error).toContain('restaurar a lista')

    listas.localSnapshot = [{ ...FARMACIA, razaoSocial: 'cópia local' }]
    listas.interesse = []
    listas.loadState = 'ready'
    expect(listas.localRecoveryAvailable).toBe(true)
    axios.put.mockResolvedValueOnce(response({ watchlist: listas.localSnapshot }))
    expect(await listas.restoreFromLocal()).toBe(true)
    expect(listas.interesse).toEqual(listas.localSnapshot)

    axios.post.mockResolvedValueOnce(response({}))
    expect(await listas.desfazerRemocao(FARMACIA.cnpj)).toBe(false)
    expect(listas.error).toContain('desfazer a remoção')
    axios.post.mockResolvedValueOnce(response({ watchlist: [FARMACIA] }))
    expect(await listas.desfazerRemocao(FARMACIA.cnpj)).toBe(true)
    expect(evidencias.loadState).toBe('ready')

    listas.ultimaRemocao = [{ ...FARMACIA, evidencias_count: 2 }]
    axios.post.mockRejectedValueOnce({ response: { data: { detail: 'não foi possível desfazer' } } })
    expect(await listas.desfazerRemocao(FARMACIA.cnpj)).toBe(false)
    expect(listas.error).toBe('não foi possível desfazer')
  })

  it('valida identidades, carrega e ordena evidências, atualiza notas e remove registros', async () => {
    const { evidencias } = await initialize({ watchlist: [FARMACIA], evidence: EVIDENCIAS })
    expect(chaveEvidencia(EVIDENCIAS[0])).toBe(`${FARMACIA.cnpj}|hora|2025-01-02|9`)
    expect(chaveEvidencia(EVIDENCIAS[1])).toBe(`${FARMACIA.cnpj}|dia|2025-01-01`)
    expect(chaveEvidencia(EVIDENCIAS[2])).toBe(`${FARMACIA.cnpj}|autorizacao|A-3`)
    expect(() => chaveEvidencia({ tipo: 'x' })).toThrow('Tipo de evidência desconhecido: x')
    expect(evidencias.listarDoCnpj(FARMACIA.cnpj).map((item) => item.id)).toEqual([2, 3, 1])
    expect(evidencias.contar('sem itens')).toBe(0)
    expect(evidencias.ultimaEm(FARMACIA.cnpj)).toBe('2025-01-04T10:00:00Z')
    expect(evidencias.ultimaEm('sem itens')).toBeNull()
    expect(evidencias.encontrar(EVIDENCIAS[2])).toEqual(EVIDENCIAS[2])
    expect(evidencias.encontrar({ cnpj: 'outro', tipo: 'dia', dt_janela: '2025-01-01' })).toBeNull()

    const atualizada = { ...EVIDENCIAS[0], nota: 'nota' }
    axios.patch.mockResolvedValueOnce(response(atualizada))
    expect(await evidencias.atualizarNota(1, 'nota')).toEqual(atualizada)
    expect(evidencias.itens[0]).toEqual(atualizada)
    axios.patch.mockResolvedValueOnce(response(atualizada))
    await expect(evidencias.atualizarNota(1, 'x')).resolves.toEqual(atualizada)
    axios.patch.mockRejectedValueOnce({ response: { data: { detail: 'nota recusada' } } })
    await expect(evidencias.atualizarNota(1, 'x')).rejects.toThrow('nota recusada')

    await evidencias.remover(1)
    expect(evidencias.itens.map((item) => item.id)).toEqual([2, 3])
    axios.delete.mockRejectedValueOnce(new Error('offline'))
    await expect(evidencias.remover(1)).rejects.toThrow('Não foi possível remover a evidência')
    await evidencias.removerDoCnpj(FARMACIA.cnpj)
    expect(evidencias.itens).toEqual([])
    axios.delete.mockRejectedValueOnce({ response: { data: { detail: 'falha do servidor' } } })
    await expect(evidencias.removerDoCnpj(FARMACIA.cnpj)).rejects.toThrow('falha do servidor')
  })

  it('exige carregamento e monitoração antes de marcar, e atualiza lista se houver conflito', async () => {
    const { listas, evidencias } = await initialize()
    const cnpj = '22222222000122'
    const payload = { cnpj, tipo: 'dia', dt_janela: '2025-03-01' }
    listas.loadState = 'error'
    expect(await evidencias.marcar(payload).catch((error) => error.message)).toContain('indisponível')
    evidencias.loadState = 'ready'
    listas.loadState = 'error'
    await expect(evidencias.marcar(payload)).rejects.toThrow('lista de Farmácias Monitoradas está indisponível')
    listas.loadState = 'ready'
    listas.saving = true
    await expect(evidencias.marcar(payload)).rejects.toThrow('lista de Farmácias Monitoradas está indisponível')
    listas.saving = false
    axios.put.mockResolvedValueOnce(response({}))
    await expect(evidencias.marcar(payload)).rejects.toThrow('A alteração não foi confirmada')

    listas.error = ''
    vi.spyOn(listas, 'adicionarInteresse').mockResolvedValueOnce(false)
    await expect(evidencias.marcar(payload)).rejects.toThrow(
      'Não foi possível adicionar a farmácia às monitoradas. A evidência não foi salva.',
    )

    axios.put.mockResolvedValueOnce(response({ watchlist: [{ ...FARMACIA, cnpj }] }))
    axios.post.mockResolvedValueOnce(response({ ...payload, id: 10 }))
    await expect(evidencias.marcar(payload, { razaoSocial: 'Nova' })).resolves.toMatchObject({ farmaciaAdicionada: true })

    axios.post.mockRejectedValueOnce({ response: { status: 409, data: { detail: 'conflito' } } })
    await expect(evidencias.marcar({ ...payload, dt_janela: '2025-03-02' })).rejects.toThrow('conflito')
    expect(listas.loadState).toBe('ready')

    axios.post.mockRejectedValueOnce(new Error('offline'))
    await expect(evidencias.marcar({ ...payload, dt_janela: '2025-03-03' })).rejects.toThrow('A farmácia foi adicionada')
    axios.post.mockResolvedValueOnce(response({ ...payload, id: 11 }))
    await expect(evidencias.marcar(payload)).resolves.toMatchObject({ farmaciaAdicionada: false })
  })

  it('deduplica carregamento, trata respostas inválidas e resolve confirmações pendentes', async () => {
    const { evidencias } = await initialize()
    const waiting = new Promise((resolve) => { setTimeout(() => resolve(response([])), 0) })
    axios.get.mockImplementationOnce(() => waiting)
    evidencias.loadState = 'idle'
    const callsBeforeLoad = axios.get.mock.calls.filter(([url]) => url === API_ENDPOINTS.evidencias).length
    const first = evidencias.carregar()
    const concurrent = evidencias.carregar()
    const ensured = evidencias.garantirCarregado()
    await Promise.all([first, concurrent, ensured])
    expect(evidencias.loadState).toBe('ready')
    expect(evidencias.itens).toEqual([])
    expect(axios.get.mock.calls.filter(([url]) => url === API_ENDPOINTS.evidencias)).toHaveLength(callsBeforeLoad + 1)

    axios.get.mockResolvedValueOnce(response({ itens: [] }))
    await evidencias.carregar()
    expect(evidencias.loadState).toBe('error')
    expect(evidencias.error).toContain('Não foi possível carregar')
    axios.get.mockRejectedValueOnce({ response: { data: { detail: 'offline evidências' } } })
    await evidencias.garantirCarregado()
    expect(evidencias.error).toBe('offline evidências')
    evidencias.loadState = 'ready'
    await evidencias.garantirCarregado()
    expect(evidencias.loadState).toBe('ready')

    const antiga = evidencias.confirmarRemocaoFarmacia('cnpj-1', 'Antiga')
    const atual = evidencias.confirmarRemocaoFarmacia('cnpj-2', 'Atual')
    await expect(antiga).resolves.toBe(false)
    evidencias.responderRemocao(1)
    await expect(atual).resolves.toBe(true)
    evidencias.responderRemocao(false)
    expect(evidencias.remocaoPendente).toBeNull()
  })

  it('abre a cronologia no mesmo CNPJ ou navega para outro e consome deep link', async () => {
    const { evidencias } = await initialize({ watchlist: [FARMACIA], evidence: EVIDENCIAS })
    const router = { push: vi.fn().mockResolvedValue(), replace: vi.fn().mockResolvedValue() }
    await expect(evidencias.abrirNaCronologia({ cnpj: 'inválido', date: 'x' }, router)).rejects.toThrow('Destino da Cronologia')
    await expect(evidencias.abrirNaCronologia({ cnpj: FARMACIA.cnpj, date: 'data inválida' }, router))
      .rejects.toThrow('Destino da Cronologia')
    await expect(evidencias.abrirNaCronologia({ cnpj: FARMACIA.cnpj, date: null }, router))
      .rejects.toThrow('Destino da Cronologia')
    await expect(evidencias.abrirNaCronologia({ date: '2025-01-02' }, router))
      .rejects.toThrow('Destino da Cronologia')

    const evidenciaDia = EVIDENCIAS[1]
    await evidencias.irPara(evidenciaDia, router, 'outro-cnpj')
    expect(router.push).toHaveBeenCalledWith({ name: 'EstablishmentDetail', params: { cnpj: FARMACIA.cnpj }, query: { s: 'autorizacoes' } })
    expect(useCnpjDetailStore().selectedTimelineEvent).toBeNull()
    evidencias.consumirNavegacaoPendente('00000000000000')
    expect(useCnpjDetailStore().selectedTimelineEvent).toBeNull()
    evidencias.consumirNavegacaoPendente(FARMACIA.cnpj)
    expect(useCnpjDetailStore().selectedTimelineEvent).toMatchObject({ date: '2025-01-01', hour: 'all' })

    await evidencias.abrirNaCronologia({ cnpj: FARMACIA.cnpj, date: '2025-01-02', hour: 9, autorizacao: 'A-3' }, router, FARMACIA.cnpj)
    expect(router.replace).toHaveBeenCalledWith({ name: 'EstablishmentDetail', params: { cnpj: FARMACIA.cnpj }, query: { s: 'autorizacoes' } })
    expect(useCnpjDetailStore().selectedTimelineEvent).toMatchObject({ date: '2025-01-02', hour: 9, autorizacao: 'A-3' })
    await evidencias.irPara(EVIDENCIAS[2], router, FARMACIA.cnpj)
    expect(useCnpjDetailStore().activeCrmViewMode).toBe('cronologia')
  })
})
