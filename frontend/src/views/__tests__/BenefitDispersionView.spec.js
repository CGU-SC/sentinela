import { describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'

import BenefitDispersionView from '@/views/BenefitDispersionView.vue'

const mocks = vi.hoisted(() => ({ useFetchAnalytics: vi.fn() }))

vi.mock('@/composables/useFetchAnalytics', () => ({
  useFetchAnalytics: mocks.useFetchAnalytics,
}))
vi.mock('@/views/components/KpiSection.vue', () => ({ default: { template: '<section data-test="kpis" />' } }))
vi.mock('@/views/components/charts/UFChart.vue', () => ({ default: { template: '<div data-test="uf-chart" />' } }))

describe('BenefitDispersionView', () => {
  it('solicita as seções necessárias e apresenta KPIs e distribuição por UF', () => {
    const wrapper = mount(BenefitDispersionView)

    expect(mocks.useFetchAnalytics).toHaveBeenCalledWith({ secoes: ['kpis', 'ufs'] })
    expect(wrapper.find('[data-test="kpis"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="uf-chart"]').exists()).toBe(true)
  })
})
