import { beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => {
  const app = { use: vi.fn(), directive: vi.fn(), mount: vi.fn() }
  return {
    app,
    createApp: vi.fn(() => app),
    createPinia: vi.fn(() => ({ plugin: 'pinia' })),
    App: { name: 'SentinelaApp' },
    router: { name: 'SentinelaRouter' },
    PrimeVue: { name: 'PrimeVue' },
    Tooltip: { name: 'Tooltip' },
    ToastService: { name: 'ToastService' },
    ConfirmationService: { name: 'ConfirmationService' },
  }
})

vi.mock('vue', async (importOriginal) => ({
  ...(await importOriginal()),
  createApp: mocks.createApp,
}))
vi.mock('pinia', () => ({ createPinia: mocks.createPinia }))
vi.mock('@/App.vue', () => ({ default: mocks.App }))
vi.mock('@/router', () => ({ default: mocks.router }))
vi.mock('primevue/config', () => ({ default: mocks.PrimeVue }))
vi.mock('primevue/tooltip', () => ({ default: mocks.Tooltip }))
vi.mock('primevue/toastservice', () => ({ default: mocks.ToastService }))
vi.mock('primevue/confirmationservice', () => ({ default: mocks.ConfirmationService }))

describe('bootstrap da SPA', () => {
  beforeEach(() => {
    vi.resetModules()
    mocks.createApp.mockClear()
    mocks.createPinia.mockClear()
    mocks.app.use.mockClear()
    mocks.app.directive.mockClear()
    mocks.app.mount.mockClear()
  })

  it('registra Pinia, roteador, PrimeVue, serviços e tooltip antes de montar', async () => {
    await import('@/main.js')

    expect(mocks.createApp).toHaveBeenCalledWith(mocks.App)
    expect(mocks.createPinia).toHaveBeenCalledOnce()
    expect(mocks.app.use).toHaveBeenNthCalledWith(1, { plugin: 'pinia' })
    expect(mocks.app.use).toHaveBeenNthCalledWith(2, mocks.router)
    expect(mocks.app.use).toHaveBeenNthCalledWith(3, mocks.PrimeVue, {
      ripple: true,
      inputStyle: 'filled',
      pt: { directives: { tooltip: { root: { class: 'sentinela-tooltip' } } } },
    })
    expect(mocks.app.use).toHaveBeenNthCalledWith(4, mocks.ToastService)
    expect(mocks.app.use).toHaveBeenNthCalledWith(5, mocks.ConfirmationService)
    expect(mocks.app.directive).toHaveBeenCalledWith('tooltip', mocks.Tooltip)
    expect(mocks.app.mount).toHaveBeenCalledWith('#app')
  })
})
