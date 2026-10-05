import { afterEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, disposePinia, setActivePinia } from 'pinia'

import RiskIndicatorSelector from '@/views/components/risk-indicators/RiskIndicatorSelector.vue'
import { INDICATOR_GROUPS } from '@/config/riskConfig'
import { useRiskIndicatorsStore } from '@/stores/riskIndicators'

describe('RiskIndicatorSelector', () => {
  let pinia

  afterEach(() => {
    disposePinia(pinia)
  })

  it('agrupa indicadores, destaca o ativo e emite a seleção', async () => {
    pinia = createPinia()
    setActivePinia(pinia)
    const store = useRiskIndicatorsStore()
    const active = INDICATOR_GROUPS[0].indicators[0]
    const next = INDICATOR_GROUPS.flatMap((group) => group.indicators).find((item) => item.key !== active.key)
    store.selectedRiskIndicator = active.key
    store.isLoading = true

    const wrapper = mount(RiskIndicatorSelector, {
      global: { plugins: [pinia], directives: { tooltip() {} } },
    })

    expect(wrapper.findAll('.selector-group')).toHaveLength(INDICATOR_GROUPS.length)
    expect(wrapper.find(`.ind-row--active .ind-btn[aria-current="true"]`).text()).toContain(active.label)
    expect(wrapper.find('.ind-loading-icon').exists()).toBe(true)

    const nextButton = wrapper.findAll('.ind-btn').find((button) => button.text().includes(next.label))
    await nextButton.trigger('click')
    expect(wrapper.emitted('select')).toEqual([[next.key]])

    const info = wrapper.find('.ind-info-btn')
    const hover = vi.fn()
    const leave = vi.fn()
    info.element.addEventListener('mouseenter', hover)
    info.element.addEventListener('mouseleave', leave)
    await info.trigger('focus')
    await info.trigger('blur')
    expect(hover).toHaveBeenCalledOnce()
    expect(leave).toHaveBeenCalledOnce()
  })

  it('não exibe carregamento quando outro indicador está selecionado ou o store está ocioso', () => {
    pinia = createPinia()
    setActivePinia(pinia)
    const store = useRiskIndicatorsStore()
    store.selectedRiskIndicator = INDICATOR_GROUPS[0].indicators[0].key
    store.isLoading = false

    const wrapper = mount(RiskIndicatorSelector, {
      global: { plugins: [pinia], directives: { tooltip() {} } },
    })

    expect(wrapper.find('.ind-loading-icon').exists()).toBe(false)
    expect(wrapper.find('.ind-row--active .ind-btn[aria-current="true"]').exists()).toBe(true)
  })
})
