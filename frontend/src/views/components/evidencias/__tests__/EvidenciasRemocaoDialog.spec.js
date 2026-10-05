import { afterEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { reactive } from 'vue'

import EvidenciasRemocaoDialog from '@/views/components/evidencias/EvidenciasRemocaoDialog.vue'

const mocks = vi.hoisted(() => ({ store: null }))

vi.mock('@/stores/evidencias', () => ({ useEvidenciasStore: () => mocks.store }))
vi.mock('primevue/dialog', () => ({
  default: {
    props: ['visible'],
    emits: ['update:visible'],
    template: '<div class="dialog"><slot name="header" /><slot /><slot name="footer" /><button data-test="close-dialog" @click="$emit(\'update:visible\', false)">Fechar</button></div>',
  },
}))

describe('EvidenciasRemocaoDialog', () => {
  afterEach(() => vi.restoreAllMocks())

  function mountDialog(remocaoPendente) {
    mocks.store = reactive({
      remocaoPendente,
      responderRemocao: vi.fn(),
    })
    return mount(EvidenciasRemocaoDialog)
  }

  it('exibe nome e contagem singular/plural e encaminha confirmação ou cancelamento', async () => {
    const wrapper = mountDialog({ nome: 'Farmácia Alfa', quantidade: 1 })

    expect(wrapper.text()).toContain('Farmácia Alfa')
    expect(wrapper.text()).toContain('1 evidência marcada')
    await wrapper.get('.evid-rm-btn.is-danger').trigger('click')
    expect(mocks.store.responderRemocao).toHaveBeenCalledWith(true)

    mocks.store.remocaoPendente = { nome: 'Farmácia Beta', quantidade: 3 }
    await wrapper.vm.$nextTick()
    expect(wrapper.text()).toContain('3 evidências marcadas')
    await wrapper.get('.evid-rm-btn:not(.is-danger)').trigger('click')
    expect(mocks.store.responderRemocao).toHaveBeenCalledWith(false)
  })

  it('interpreta fechamento do diálogo como cancelamento', async () => {
    const wrapper = mountDialog({ nome: 'Farmácia Alfa', quantidade: 2 })
    await wrapper.get('[data-test="close-dialog"]').trigger('click')

    expect(mocks.store.responderRemocao).toHaveBeenCalledWith(false)
  })

  it('usa contagem zero quando o contrato não informa a quantidade', () => {
    const wrapper = mountDialog({ nome: 'Farmácia Alfa', quantidade: null })

    expect(wrapper.text()).toContain('0 evidências marcadas')
  })

  it('não renderiza a mensagem da remoção quando não há confirmação pendente', () => {
    const wrapper = mountDialog(null)

    expect(wrapper.find('.evid-rm-body').exists()).toBe(false)
    expect(wrapper.text()).toContain('Remover das Farmácias Monitoradas?')
  })
})
