import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'

import HighlightedText from '@/views/components/common/HighlightedText.vue'
import PinIcon from '@/views/components/common/PinIcon.vue'
import MapBackButton from '@/views/components/maps/MapBackButton.vue'

describe('controles visuais compartilhados', () => {
  it('destaca correspondência normalizada sem mudar o texto original', () => {
    const wrapper = mount(HighlightedText, { props: { text: 'João da Silva', query: 'JOAO' } })

    expect(wrapper.get('mark').text()).toBe('João')
    expect(wrapper.text()).toBe('João da Silva')
  })

  it('renderiza o pino como contorno ou preenchido conforme a propriedade', async () => {
    const wrapper = mount(PinIcon)
    expect(wrapper.get('svg').attributes('fill')).toBe('none')

    await wrapper.setProps({ preenchido: true })
    expect(wrapper.get('svg').attributes('fill')).toBe('currentColor')
    expect(wrapper.get('svg').attributes('aria-hidden')).toBe('true')
  })

  it('exibe o destino e emite clique no botão de retorno do mapa', async () => {
    const wrapper = mount(MapBackButton, {
      props: { label: 'Brasil', tooltip: 'Voltar ao Brasil' },
      global: { directives: { tooltip() {} } },
    })

    expect(wrapper.text()).toContain('Brasil')
    await wrapper.get('button').trigger('click')
    expect(wrapper.emitted('click')).toHaveLength(1)
  })
})
