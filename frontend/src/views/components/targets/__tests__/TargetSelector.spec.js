import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import TargetSelector from '@/views/components/targets/TargetSelector.vue'
import { DEFAULT_TARGET_KEY, TARGET_GROUPS } from '@/config/targetConfig'

const enabledTarget = TARGET_GROUPS.flatMap((group) => group.targets).find((target) => target.enabled)
const disabledTarget = TARGET_GROUPS.flatMap((group) => group.targets).find((target) => !target.enabled)

function mountSelector(selectedTarget = DEFAULT_TARGET_KEY) {
  return mount(TargetSelector, {
    props: { selectedTarget },
    global: {
      directives: { tooltip() {} },
    },
  })
}

describe('TargetSelector', () => {
  it('renderiza os grupos e destaca o alvo selecionado', () => {
    const wrapper = mountSelector(enabledTarget.key)

    expect(wrapper.text()).toContain('Alvos')
    expect(wrapper.text()).toContain(enabledTarget.label)
    expect(wrapper.get(`button.target-btn--active`).text()).toContain(enabledTarget.label)
    expect(wrapper.findAll('.selector-group')).toHaveLength(TARGET_GROUPS.length)
  })

  it('emite select quando um alvo habilitado é escolhido', async () => {
    const wrapper = mountSelector(enabledTarget.key)
    const targetToSelect = TARGET_GROUPS.flatMap((group) => group.targets)
      .find((target) => target.enabled && target.key !== enabledTarget.key)

    const button = wrapper.findAll('button.target-btn')
      .find((candidate) => candidate.text().includes(targetToSelect.label))
    await button.trigger('click')

    expect(wrapper.emitted('select')).toEqual([[targetToSelect.key]])
  })

  it('mantém alvos indisponíveis desabilitados e sem evento de seleção', async () => {
    const wrapper = mountSelector(enabledTarget.key)
    const button = wrapper.findAll('button.target-btn')
      .find((candidate) => candidate.text().includes(disabledTarget.label))

    expect(button.exists()).toBe(true)
    expect(button.element.disabled).toBe(true)
    expect(button.text()).toContain('Em breve')
    await button.trigger('click')
    expect(wrapper.emitted('select')).toBeUndefined()
  })

  it('ignora uma seleção indisponível mesmo quando chamada diretamente', () => {
    const wrapper = mountSelector(enabledTarget.key)

    wrapper.vm.$.setupState.selectTarget(disabledTarget)

    expect(wrapper.emitted('select')).toBeUndefined()
  })

  it('falha visivelmente se receber uma chave de alvo sem configuração', () => {
    expect(() => mountSelector('alvo-inexistente')).toThrow(
      'Alvo selecionado sem configuração: alvo-inexistente',
    )
  })
})
