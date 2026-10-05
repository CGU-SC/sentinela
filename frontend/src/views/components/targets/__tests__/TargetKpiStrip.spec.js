import { describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'

import TargetKpiStrip from '@/views/components/targets/TargetKpiStrip.vue'

vi.mock('@/composables/useFormatting', () => ({
  useFormatting: () => ({ formatCurrencyFull: (value) => `R$ ${Number(value).toFixed(2)}` }),
}))

describe('TargetKpiStrip', () => {
  it('formata valores financeiros, contagens, texto e campos ausentes', () => {
    const wrapper = mount(TargetKpiStrip, {
      props: {
        kpis: [
          { key: 'valor_incompativel', label: 'Valor incompatível', value: 1234.5 },
          { key: 'farmacias', label: 'Farmácias', value: 1200 },
          { key: 'cpfs_envolvidos', label: 'CPFs', value: 'Não informado' },
          { key: 'municipios', label: 'Municípios', value: null },
        ],
        sourceNotice: 'Fonte de dados de teste',
      },
    })

    expect(wrapper.text()).toContain('Fonte de dados de teste')
    expect(wrapper.findAll('.target-kpi')).toHaveLength(4)
    expect(wrapper.text()).toContain('R$ 1234.50')
    expect(wrapper.text()).toContain('1.200')
    expect(wrapper.text()).toContain('Não informado')
    expect(wrapper.text()).toContain('—')
  })

  it('renderiza a grade vazia sem criar cartões quando não há KPIs', () => {
    const wrapper = mount(TargetKpiStrip)

    expect(wrapper.findAll('.target-kpi')).toHaveLength(0)
    expect(wrapper.find('.target-contract-note').exists()).toBe(false)
  })
})
