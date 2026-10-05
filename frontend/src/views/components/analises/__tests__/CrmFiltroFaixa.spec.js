import { afterEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, disposePinia, setActivePinia } from 'pinia'

import CrmFiltroFaixa from '@/views/components/analises/CrmFiltroFaixa.vue'
import { CRM_FAIXAS } from '@/config/crmFiltrosMedico'
import { useCrmFiltrosMedicoStore } from '@/stores/crmFiltrosMedico'

vi.mock('@/views/components/common/NumberRangePicker.vue', () => ({
  default: {
    props: ['valor', 'rotulo', 'casas', 'min', 'max', 'passo', 'sufixo', 'atalhos', 'formatar'],
    emits: ['select-range'],
    template: '<button data-test="range-picker" :data-format="formatar(valor[0] ?? 0)" @click="$emit(\'select-range\', [10, 20])">{{ rotulo }}</button>',
  },
}))

describe('CrmFiltroFaixa', () => {
  let pinia
  let store

  afterEach(() => {
    disposePinia(pinia)
    vi.restoreAllMocks()
  })

  it('aplica faixa recebida pelo seletor e limpa um filtro ativo', async () => {
    pinia = createPinia()
    setActivePinia(pinia)
    store = useCrmFiltrosMedicoStore()
    const tipo = 'prescricoes'
    const wrapper = mount(CrmFiltroFaixa, {
      props: { tipo },
      global: { plugins: [pinia], directives: { tooltip() {} } },
    })

    expect(wrapper.get('[data-test="range-picker"]').text()).toBe(CRM_FAIXAS[tipo].todas)
    await wrapper.get('[data-test="range-picker"]').trigger('click')
    await flushPromises()
    expect(store.faixas[tipo]).toEqual({ min: 10, max: 20 })
    expect(wrapper.classes()).toContain('is-ativo')
    expect(wrapper.find('[aria-label="Limpar o filtro total de prescrições"]').exists()).toBe(true)

    await wrapper.get('[aria-label="Limpar o filtro total de prescrições"]').trigger('click')
    expect(store.faixas[tipo]).toEqual({ min: null, max: null })
  })

  it('renderiza rótulo embutido sem ações do filtro externo', () => {
    pinia = createPinia()
    setActivePinia(pinia)
    store = useCrmFiltrosMedicoStore()
    const tipo = 'sequenciaDias'
    const wrapper = mount(CrmFiltroFaixa, {
      props: { tipo, campo: true },
      global: { plugins: [pinia], directives: { tooltip() {} } },
    })

    expect(wrapper.classes()).toContain('is-campo')
    expect(wrapper.text()).toContain(CRM_FAIXAS[tipo].label)
    expect(wrapper.find('.filtro-info').exists()).toBe(false)
    expect(wrapper.find('.filtro-limpar').exists()).toBe(false)
  })

  it('falha cedo para uma faixa sem configuração', () => {
    pinia = createPinia()
    setActivePinia(pinia)
    useCrmFiltrosMedicoStore()

    expect(() => mount(CrmFiltroFaixa, {
      props: { tipo: 'nao-configurada' },
      global: { plugins: [pinia], directives: { tooltip() {} } },
    }))
      .toThrow('Faixa de filtro de médico desconhecida: nao-configurada')
  })

  it('mostra atalhos, faixa igual, limites abertos e intervalo completo', async () => {
    pinia = createPinia()
    setActivePinia(pinia)
    store = useCrmFiltrosMedicoStore()
    const tipo = 'farmacias'
    const wrapper = mount(CrmFiltroFaixa, {
      props: { tipo },
      global: { plugins: [pinia], directives: { tooltip() {} } },
    })
    const picker = wrapper.get('[data-test="range-picker"]')

    store.setFaixa(tipo, CRM_FAIXAS[tipo].atalhos.find((atalho) => atalho.value === 'uma').faixa.reduce((faixa, value, i) => {
      faixa[i === 0 ? 'min' : 'max'] = value
      return faixa
    }, {}))
    await wrapper.vm.$nextTick()
    expect(picker.text()).toContain('1 (uma farmácia)')
    expect(picker.text()).toContain('1')

    store.setFaixa(tipo, { min: 2, max: 2 })
    await wrapper.vm.$nextTick()
    expect(picker.text()).toContain('= 2')

    store.setFaixa(tipo, { min: 3, max: null })
    await wrapper.vm.$nextTick()
    expect(picker.text()).toContain('≥ 3')

    store.setFaixa(tipo, { min: null, max: 4 })
    await wrapper.vm.$nextTick()
    expect(picker.text()).toContain('≤ 4')

    store.setFaixa(tipo, { min: 2, max: 7 })
    await wrapper.vm.$nextTick()
    expect(picker.text()).toContain('2 a 7')
  })
})
