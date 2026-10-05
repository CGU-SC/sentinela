import { afterEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, disposePinia, setActivePinia } from 'pinia'
import axios from 'axios'

import KpiSection from '@/views/components/KpiSection.vue'
import { useAnalyticsStore } from '@/stores/analytics'

vi.mock('axios', () => ({ default: { get: vi.fn(), put: vi.fn() } }))
vi.mock('@/config/chartTheme', () => ({ useChartTheme: () => ({ chartDataColors: { red: 'crimson' } }) }))
vi.mock('@/composables/useDelayedLoading', () => ({ useDelayedLoading: (loading) => loading }))
vi.mock('primevue/button', () => ({
  default: {
    props: ['label'],
    emits: ['click'],
    template: '<button type="button" @click="$emit(\'click\')">{{ label }}</button>',
  },
}))

describe('KpiSection', () => {
  let pinia
  let analytics

  afterEach(() => {
    disposePinia(pinia)
    vi.restoreAllMocks()
    localStorage.clear()
  })

  function mountSection(props = {}) {
    return mount(KpiSection, { props, global: { plugins: [pinia] } })
  }

  it('oculta os KPIs solicitados e mantém os demais valores enriquecidos', () => {
    pinia = createPinia()
    setActivePinia(pinia)
    analytics = useAnalyticsStore()
    analytics.kpis = [
      { label: 'KPI reservado', value: '4' },
      { label: 'KPI visível', value: '2' },
    ]

    const wrapper = mountSection({ hiddenLabels: ['KPI RESERVADO'] })

    expect(wrapper.findAll('.kpi-card')).toHaveLength(1)
    expect(wrapper.text()).toContain('KPI VISÍVEL')
    expect(wrapper.text()).not.toContain('KPI RESERVADO')
  })

  it('mantém o grid sem cards quando a store ainda não recebeu KPIs', () => {
    pinia = createPinia()
    setActivePinia(pinia)
    analytics = useAnalyticsStore()
    analytics.kpis = []

    const wrapper = mountSection()

    expect(wrapper.findAll('.kpi-card')).toHaveLength(0)
  })

  it('usa os KPIs atuais quando o cache local não está disponível', async () => {
    pinia = createPinia()
    setActivePinia(pinia)
    analytics = useAnalyticsStore()
    analytics.kpis = [{ label: 'Resumo atual', value: '10' }]
    const wrapper = mountSection()

    wrapper.vm.$.setupState.cachedKpis = null
    await flushPromises()

    expect(wrapper.text()).toContain('RESUMO ATUAL')
  })

  it('exibe falha, chama a nova tentativa e conserva dados anteriores durante atualização', async () => {
    pinia = createPinia()
    setActivePinia(pinia)
    analytics = useAnalyticsStore()
    analytics.kpis = [{ label: 'Resumo atual', value: '10' }]
    analytics.error = 'Falha temporária'
    const retry = vi.spyOn(analytics, 'retryDashboardSummary').mockResolvedValue()
    const wrapper = mountSection()

    expect(wrapper.text()).toContain('Falha temporária')
    await wrapper.get('button').trigger('click')
    expect(retry).toHaveBeenCalledOnce()

    analytics.isLoading = true
    analytics.kpis = [{ label: 'Novo resumo', value: '12' }]
    await flushPromises()
    expect(wrapper.text()).toContain('RESUMO ATUAL')
    expect(wrapper.text()).not.toContain('NOVO RESUMO')
    expect(wrapper.get('.kpi-grid').classes()).toContain('is-refreshing')

    analytics.isLoading = false
    await flushPromises()
    expect(wrapper.text()).toContain('NOVO RESUMO')
  })
})
