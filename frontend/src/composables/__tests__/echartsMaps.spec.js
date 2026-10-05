import { afterEach, describe, expect, it, vi } from 'vitest'

const maps = vi.hoisted(() => ({ current: undefined, getMap: vi.fn(), registerMap: vi.fn(), use: vi.fn() }))

vi.mock('echarts/core', () => ({
  getMap: maps.getMap,
  registerMap: maps.registerMap,
  use: maps.use,
}))
vi.mock('echarts/charts', () => ({ MapChart: { name: 'MapChart' } }))

describe('ensureBrasilUfMap', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    vi.clearAllMocks()
    maps.current = undefined
  })

  async function loadComposable() {
    vi.resetModules()
    maps.getMap.mockImplementation(() => maps.current)
    maps.registerMap.mockImplementation((_name, geo) => { maps.current = geo })
    return import('../echartsMaps')
  }

  it('registra o GeoJSON validado uma única vez para chamadas simultâneas', async () => {
    const geo = { type: 'FeatureCollection', features: [{ type: 'Feature' }] }
    let resolveFetch
    const fetchMock = vi.fn(() => new Promise((resolve) => { resolveFetch = resolve }))
    vi.stubGlobal('fetch', fetchMock)
    const { ensureBrasilUfMap } = await loadComposable()

    const first = ensureBrasilUfMap()
    const second = ensureBrasilUfMap()
    expect(fetchMock).toHaveBeenCalledOnce()
    resolveFetch({ ok: true, json: async () => geo })
    await expect(Promise.all([first, second])).resolves.toEqual([undefined, undefined])
    expect(maps.registerMap).toHaveBeenCalledWith('brasil-uf', geo)
    await expect(ensureBrasilUfMap()).resolves.toBeUndefined()
    expect(fetchMock).toHaveBeenCalledOnce()
  })

  it('usa registro preexistente e reporta erro HTTP ou GeoJSON inválido', async () => {
    maps.current = { type: 'FeatureCollection', features: [] }
    vi.stubGlobal('fetch', vi.fn())
    const { ensureBrasilUfMap } = await loadComposable()
    await expect(ensureBrasilUfMap()).resolves.toBeUndefined()
    expect(fetch).not.toHaveBeenCalled()

    maps.current = undefined
    fetch.mockResolvedValueOnce({ ok: false, status: 503 })
    await expect(ensureBrasilUfMap()).rejects.toThrow('Não foi possível carregar o mapa do Brasil.')
    fetch.mockResolvedValueOnce({ ok: true, json: async () => ({ type: 'FeatureCollection', features: [] }) })
    await expect(ensureBrasilUfMap()).rejects.toThrow('GeoJSON nacional sem territórios válidos.')
  })

  it('falha se registerMap não disponibilizar o mapa e permite nova tentativa', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ type: 'FeatureCollection', features: [{ id: 'SP' }] }),
    })
    vi.stubGlobal('fetch', fetchMock)
    const { ensureBrasilUfMap } = await loadComposable()
    maps.registerMap.mockImplementationOnce(() => {})
    await expect(ensureBrasilUfMap()).rejects.toThrow('O ECharts não registrou o mapa do Brasil.')

    maps.current = { type: 'FeatureCollection', features: [{ id: 'SP' }] }
    await expect(ensureBrasilUfMap()).resolves.toBeUndefined()
    expect(fetchMock).toHaveBeenCalledOnce()
  })
})
