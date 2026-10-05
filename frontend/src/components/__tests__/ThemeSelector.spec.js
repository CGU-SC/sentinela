import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { reactive } from 'vue'

import ThemeSelector from '@/components/ThemeSelector.vue'
import { PALETTE_OPTIONS } from '@/config/themeConfig'

const mocks = vi.hoisted(() => ({ store: null, togglePanel: vi.fn() }))

vi.mock('@/stores/theme', () => ({ useThemeStore: () => mocks.store }))
vi.mock('primevue/button', () => ({
  default: {
    props: ['icon'],
    emits: ['click'],
    template: '<button type="button" data-test="theme-trigger" @click="$emit(\'click\', $event)"><i :class="icon" /></button>',
  },
}))
vi.mock('primevue/overlaypanel', async () => {
  const { h } = await import('vue')
  return {
    default: {
      name: 'OverlayPanel',
      props: ['dismissable'],
      setup(_, { expose, slots }) {
        expose({ toggle: mocks.togglePanel })
        return () => h('div', { class: 'overlay-panel' }, slots.default?.())
      },
    },
  }
})

describe('ThemeSelector', () => {
  beforeEach(() => {
    mocks.togglePanel.mockReset()
    mocks.store = reactive({
      isDark: false,
      currentPalette: PALETTE_OPTIONS[0].id,
      setMode: vi.fn((mode) => { mocks.store.isDark = mode === 'dark' }),
      setPalette: vi.fn((palette) => { mocks.store.currentPalette = palette }),
    })
  })

  afterEach(() => vi.restoreAllMocks())

  function mountSelector() {
    return mount(ThemeSelector, { global: { directives: { tooltip() {} } } })
  }

  it('aciona o painel de aparência pelo botão da paleta', async () => {
    const wrapper = mountSelector()
    const event = new MouseEvent('click')

    await wrapper.get('[data-test="theme-trigger"]').trigger('click', { event })

    expect(mocks.togglePanel).toHaveBeenCalledOnce()
    expect(mocks.togglePanel.mock.calls[0][0]).toBeDefined()
  })

  it('alterna modo claro/escuro e aplica uma paleta selecionada', async () => {
    const wrapper = mountSelector()
    const lightButton = wrapper.findAll('.mode-option').find((button) => button.text().includes('Claro'))
    expect(lightButton.classes()).toContain('active')
    await lightButton.trigger('click')
    expect(mocks.store.setMode).toHaveBeenCalledWith('light')

    const darkButton = wrapper.findAll('.mode-option').find((button) => button.text().includes('Escuro'))
    await darkButton.trigger('click')
    expect(mocks.store.setMode).toHaveBeenCalledWith('dark')
    expect(darkButton.classes()).toContain('active')

    const palette = PALETTE_OPTIONS[1]
    const paletteButton = wrapper.findAll('.theme-card').find((button) => button.text().includes(palette.name))
    await paletteButton.trigger('click')
    expect(mocks.store.setPalette).toHaveBeenCalledWith(palette.id)
    expect(paletteButton.classes()).toContain('active')
  })
})
