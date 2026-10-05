import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { reactive } from 'vue'

import UpdateBlocker from '@/views/components/UpdateBlocker.vue'

const mocks = vi.hoisted(() => ({ store: null }))

vi.mock('@/stores/systemUpdate', () => ({ useSystemUpdateStore: () => mocks.store }))

describe('UpdateBlocker', () => {
  beforeEach(() => {
    mocks.store = reactive({
      currentVersion: '1.0.0',
      minimumVersion: '2.0.0',
      latestVersion: '2.1.0',
      downloadUrl: 'https://sentinela.test/download',
      releaseNotesUrl: 'https://sentinela.test/releases',
    })
    delete window.pywebview
  })

  afterEach(() => {
    delete window.pywebview
    vi.restoreAllMocks()
  })

  it('mostra as versões e abre o instalador e as notas de versão', async () => {
    const open = vi.spyOn(window, 'open').mockImplementation(() => null)
    const wrapper = mount(UpdateBlocker)

    expect(wrapper.text()).toContain('Atualização obrigatória')
    expect(wrapper.text()).toContain('1.0.0')
    expect(wrapper.text()).toContain('2.0.0')
    expect(wrapper.text()).toContain('2.1.0')

    await wrapper.get('.update-action--primary').trigger('click')
    await wrapper.get('.update-action--secondary').trigger('click')
    expect(open).toHaveBeenNthCalledWith(1, mocks.store.downloadUrl, '_blank')
    expect(open).toHaveBeenNthCalledWith(2, mocks.store.releaseNotesUrl, '_blank')
    expect(wrapper.find('.update-action--ghost').exists()).toBe(false)
  })

  it('exibe saída e encerra o aplicativo no runtime desktop', async () => {
    const exitApp = vi.fn()
    Object.defineProperty(window, 'pywebview', { configurable: true, value: { api: { exit_app: exitApp } } })
    const wrapper = mount(UpdateBlocker)

    expect(wrapper.find('.update-action--ghost').exists()).toBe(true)
    await wrapper.get('.update-action--ghost').trigger('click')
    expect(exitApp).toHaveBeenCalledOnce()
  })

  it('fecha a janela quando o runtime desktop não oferece exit_app', async () => {
    Object.defineProperty(window, 'pywebview', { configurable: true, value: { api: {} } })
    const close = vi.spyOn(window, 'close').mockImplementation(() => {})
    const wrapper = mount(UpdateBlocker)

    expect(wrapper.find('.update-action--ghost').exists()).toBe(true)
    await wrapper.get('.update-action--ghost').trigger('click')

    expect(close).toHaveBeenCalledOnce()
  })

  it('mantém ações sem navegação quando os endereços não estão configurados', async () => {
    mocks.store.downloadUrl = null
    mocks.store.releaseNotesUrl = null
    const open = vi.spyOn(window, 'open').mockImplementation(() => null)
    const wrapper = mount(UpdateBlocker)

    await wrapper.get('.update-action--primary').trigger('click')
    await wrapper.get('.update-action--secondary').trigger('click')
    expect(open).not.toHaveBeenCalled()
  })

  it('apresenta traços quando o servidor não fornece as versões', () => {
    mocks.store.currentVersion = null
    mocks.store.minimumVersion = null
    mocks.store.latestVersion = null
    const wrapper = mount(UpdateBlocker)

    expect(wrapper.findAll('.update-version-row__value').map((value) => value.text())).toEqual(['—', '—', '—'])
  })
})
