import { beforeEach, describe, expect, it, vi } from 'vitest'

const navigationMocks = vi.hoisted(() => ({
  begin: vi.fn(),
  dismiss: vi.fn(),
  prepare: vi.fn(),
}))

vi.mock('@/composables/prepareAnalysisPage', () => ({
  ANALYSIS_PAGE_PATHS: ['/municipios', '/estabelecimentos', '/analises'],
  beginAnalysisPageNavigation: navigationMocks.begin,
  dismissAnalysisPageNavigation: navigationMocks.dismiss,
  prepareAnalysisPage: navigationMocks.prepare,
}))

import router from '@/router'

describe('contrato de rotas do Sentinela', () => {
  it.each([
    ['/', 'Home'],
    ['/municipios', 'Municipalities'],
    ['/estabelecimentos', 'Establishments'],
    ['/estabelecimentos/12345678000195', 'EstablishmentDetail'],
    ['/analises', 'Analyses'],
    ['/alvos', 'Targets'],
    ['/listas', 'FarmaciaLists'],
    ['/configuracoes', 'Settings'],
  ])('resolve %s para a rota %s', (path, routeName) => {
    expect(router.resolve(path).name).toBe(routeName)
  })

  it('mantém os caminhos principais de dispersão e contexto regional', () => {
    const paths = router.getRoutes().map((route) => route.path)

    expect(paths).toContain('/dispersao-beneficio')
    expect(paths).toContain('/regional')
  })

  it('carrega todos os componentes registrados por importação sob demanda', async () => {
    const lazyRoutes = router.getRoutes().filter((route) => typeof route.components?.default === 'function')
    const components = await Promise.all(lazyRoutes.map((route) => route.components.default()))

    expect(lazyRoutes).toHaveLength(9)
    expect(components).toHaveLength(9)
    expect(components.every((component) => Boolean(component.default))).toBe(true)
  }, 15000)

  it.each([
    ['/municipio', '/municipios'],
    ['/cnpj', '/estabelecimentos'],
    ['/indicadores', '/estabelecimentos'],
  ])('preserva o redirecionamento legado de %s para %s', (legacyPath, destination) => {
    const record = router.getRoutes().find((route) => route.path === legacyPath)

    expect(record?.redirect).toBe(destination)
  })

  it('mantém o redirecionamento de estabelecimento legado com o CNPJ informado', () => {
    const record = router.getRoutes().find((route) => route.path === '/estabelecimento/:cnpj')

    expect(record).toBeDefined()
    expect(record.redirect({ params: { cnpj: '12345678000195' } })).toBe('/estabelecimentos/12345678000195')
  })
})

describe('guards de navegação das páginas de análise', () => {
  beforeEach(async () => {
    navigationMocks.begin.mockReset()
    navigationMocks.dismiss.mockReset()
    navigationMocks.prepare.mockReset().mockResolvedValue(undefined)
    await router.push('/')
    navigationMocks.begin.mockClear()
    navigationMocks.dismiss.mockClear()
  })

  it('prepara uma rota de análise antes de concluir a navegação', async () => {
    await router.push('/analises')

    expect(navigationMocks.begin).toHaveBeenCalledWith('/analises')
    expect(navigationMocks.prepare).toHaveBeenCalledWith('/analises')
    expect(router.currentRoute.value.path).toBe('/analises')
  })

  it('prepara novamente ao trocar entre páginas de análise e dispensa ao sair', async () => {
    await router.push('/analises')
    navigationMocks.begin.mockClear()
    navigationMocks.prepare.mockClear()

    await router.push('/municipios')
    expect(navigationMocks.begin).toHaveBeenCalledWith('/municipios')
    expect(navigationMocks.prepare).toHaveBeenCalledWith('/municipios')

    navigationMocks.dismiss.mockClear()
    await router.push('/listas')
    expect(navigationMocks.dismiss).toHaveBeenCalledOnce()
  })

  it('cancela a navegação quando a preparação da análise falha', async () => {
    navigationMocks.prepare.mockRejectedValueOnce(new Error('Falha ao preparar'))

    await router.push('/analises')

    expect(router.currentRoute.value.path).toBe('/')
    expect(navigationMocks.prepare).toHaveBeenCalledWith('/analises')
  })
})
