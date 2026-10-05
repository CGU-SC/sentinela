import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { API_ENDPOINTS } from '@/config/api'
import { createCnpjPerfSession, logCnpjPerf } from '@/utils/cnpjPerfLogger'

describe('logger de desempenho do detalhe CNPJ', () => {
  let originalSendBeacon
  beforeEach(() => {
    originalSendBeacon = Object.getOwnPropertyDescriptor(navigator, 'sendBeacon')
  })

  afterEach(() => {
    if (originalSendBeacon) Object.defineProperty(navigator, 'sendBeacon', originalSendBeacon)
    else delete navigator.sendBeacon
    vi.restoreAllMocks()
    vi.unstubAllGlobals()
  })

  it('normaliza o CNPJ e cria identificador e instante inicial para a sessão', () => {
    const session = createCnpjPerfSession('12.345.678/0001-95')

    expect(session.cnpj).toBe('12345678000195')
    expect(session.sessionId).toContain('12345678000195-')
    expect(session.startedAt).toEqual(expect.any(Number))
    expect(createCnpjPerfSession(null).sessionId).toContain('cnpj-')
  })

  it('ignora evento incompleto sem transmitir dados', () => {
    const sendBeacon = vi.fn()
    Object.defineProperty(navigator, 'sendBeacon', { configurable: true, value: sendBeacon })
    const fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)

    logCnpjPerf(null, 'loaded')
    logCnpjPerf({ cnpj: '12345678000195', sessionId: 'session', startedAt: 0 }, '')

    expect(sendBeacon).not.toHaveBeenCalled()
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('envia evento pelo beacon e deduplica o mesmo evento da sessão', () => {
    const sendBeacon = vi.fn(() => true)
    Object.defineProperty(navigator, 'sendBeacon', { configurable: true, value: sendBeacon })
    const fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)
    const session = { cnpj: '12345678000195', sessionId: 'beacon-session', startedAt: performance.now() }

    logCnpjPerf(session, 'tab-ready', { tab: 'risco' })
    logCnpjPerf(session, 'tab-ready', { tab: 'risco' })

    expect(sendBeacon).toHaveBeenCalledOnce()
    expect(sendBeacon).toHaveBeenCalledWith(API_ENDPOINTS.analyticsClientPerf, expect.any(Blob))
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('usa POST keepalive quando o beacon não aceita e registra falha de transporte', async () => {
    const sendBeacon = vi.fn(() => false)
    Object.defineProperty(navigator, 'sendBeacon', { configurable: true, value: sendBeacon })
    const fetchMock = vi.fn().mockRejectedValue(new Error('offline'))
    vi.stubGlobal('fetch', fetchMock)
    const warning = vi.spyOn(console, 'warn').mockImplementation(() => {})
    const session = { cnpj: '98765432000198', sessionId: 'fetch-session', startedAt: performance.now() }

    logCnpjPerf(session, 'data-ready', { tabs: 7 })
    await Promise.resolve()
    await Promise.resolve()

    expect(fetchMock).toHaveBeenCalledWith(API_ENDPOINTS.analyticsClientPerf, expect.objectContaining({
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      keepalive: true,
    }))
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toMatchObject({
      cnpj: '98765432000198',
      event: 'data-ready',
      session_id: 'fetch-session',
      detail: { tabs: 7 },
    })
    expect(warning).toHaveBeenCalledOnce()
  })

  it('usa POST keepalive quando o navegador não oferece sendBeacon', async () => {
    Object.defineProperty(navigator, 'sendBeacon', { configurable: true, value: undefined })
    const fetchMock = vi.fn().mockResolvedValue({ ok: true })
    vi.stubGlobal('fetch', fetchMock)
    const session = { cnpj: '12345678000199', sessionId: 'no-beacon', startedAt: performance.now() }

    logCnpjPerf(session, 'ready')
    await Promise.resolve()

    expect(fetchMock).toHaveBeenCalledWith(API_ENDPOINTS.analyticsClientPerf, expect.objectContaining({
      method: 'POST',
      keepalive: true,
    }))
  })
})
