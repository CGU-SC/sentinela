import { afterEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'

import MultiOptionPicker from '@/views/components/common/MultiOptionPicker.vue'

const mocks = vi.hoisted(() => ({ toggle: vi.fn(), hide: vi.fn() }))

vi.mock('primevue/overlaypanel', async () => {
  const { h } = await import('vue')
  return {
    default: {
      name: 'OverlayPanel',
      props: ['dismissable'],
      setup(_, { expose, slots }) {
        expose({ toggle: mocks.toggle, hide: mocks.hide })
        return () => h('div', { class: 'overlay-panel' }, slots.default?.())
      },
    },
  }
})

const OPTIONS = ['RO', 'AC', 'SP']
const SHORTCUTS = [
  { value: 'norte', label: 'Norte', selecao: ['RO', 'AC'] },
  { value: 'todas', label: 'Todas', selecao: [] },
]

describe('MultiOptionPicker', () => {
  afterEach(() => vi.restoreAllMocks())

  function mountPicker(props = {}) {
    return mount(MultiOptionPicker, {
      props: { valor: [], opcoes: OPTIONS, rotulo: 'UF do CRM', atalhos: SHORTCUTS, nomePlural: 'UFs', ...props },
    })
  }

  it('abre com uma cópia da seleção, altera rascunho e aplica opções na ordem configurada', async () => {
    mocks.toggle.mockReset()
    mocks.hide.mockReset()
    const wrapper = mountPicker({ valor: ['RO'] })

    await wrapper.get('.rp-gatilho').trigger('click')
    expect(mocks.toggle).toHaveBeenCalledOnce()
    expect(wrapper.find('.mop-opcao.is-ativa').text()).toBe('RO')

    await wrapper.findAll('.mop-opcao').find((button) => button.text() === 'RO').trigger('click')
    expect(wrapper.get('.mop-resumo').text()).toBe('')
    await wrapper.findAll('.mop-opcao').find((button) => button.text() === 'RO').trigger('click')
    await wrapper.findAll('.mop-opcao').find((button) => button.text() === 'AC').trigger('click')
    expect(wrapper.get('.mop-resumo').text()).toBe('2 selecionadas')
    expect(wrapper.get('.mop-aplicar').attributes('disabled')).toBeUndefined()
    await wrapper.get('form').trigger('submit')

    expect(wrapper.emitted('select')).toEqual([[['RO', 'AC']]])
    expect(mocks.hide).toHaveBeenCalledOnce()
  })

  it('aplica atalhos imediatamente, ordena a seleção e não emite valor idêntico', async () => {
    mocks.hide.mockReset()
    const wrapper = mountPicker()
    await wrapper.get('.rp-atalho').trigger('click')

    expect(wrapper.emitted('select')).toEqual([[['RO', 'AC']]])
    expect(mocks.hide).toHaveBeenCalledOnce()

    await wrapper.findAll('.rp-atalho')[1].trigger('click')
    expect(wrapper.emitted('select')).toHaveLength(1)
  })

  it('trata marcar todas como ausência de filtro e limpa seleções temporárias', async () => {
    const wrapper = mountPicker({ valor: ['SP'] })
    await wrapper.get('.rp-gatilho').trigger('click')
    await wrapper.get('.mop-marcar').trigger('click')

    expect(wrapper.get('.mop-marcar').attributes('disabled')).toBeDefined()
    expect(wrapper.get('.mop-resumo').text()).toBe('3 selecionadas')
    await wrapper.get('form').trigger('submit')
    expect(wrapper.emitted('select')).toEqual([[[]]])

    await wrapper.get('.rp-gatilho').trigger('click')
    await wrapper.get('.mop-limpar').trigger('click')
    expect(wrapper.findAll('.mop-opcao.is-ativa')).toHaveLength(0)
    expect(wrapper.get('.mop-resumo').text()).toBe('')
  })

  it('não abre o painel quando está desabilitado', async () => {
    const wrapper = mountPicker({ disabled: true })
    await wrapper.get('.rp-gatilho').trigger('click')
    wrapper.vm.$.setupState.abrir(new Event('click'))

    expect(wrapper.get('.rp-gatilho').attributes('disabled')).toBeDefined()
    expect(mocks.toggle).not.toHaveBeenCalled()
  })
})
