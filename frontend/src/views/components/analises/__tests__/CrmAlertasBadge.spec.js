import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { reactive } from 'vue'

import CrmAlertasBadge from '@/views/components/analises/CrmAlertasBadge.vue'

const mocks = vi.hoisted(() => ({ theme: null, crmAlertasTooltip: vi.fn(() => ({ value: 'tooltip de alertas' })) }))

vi.mock('@/stores/theme', () => ({ useThemeStore: () => mocks.theme }))
vi.mock('@/config/analysisTooltipConfig', () => ({ crmAlertasTooltip: mocks.crmAlertasTooltip }))

describe('CrmAlertasBadge', () => {
  beforeEach(() => {
    mocks.crmAlertasTooltip.mockClear()
    mocks.theme = reactive({ isDark: false })
  })

  afterEach(() => vi.restoreAllMocks())

  it('exibe contagem singular, aplica tema e abre o histórico', async () => {
    const wrapper = mount(CrmAlertasBadge, {
      props: {
        pontos: [{ codigo: 'alerta_teste' }],
        periodo: '01/2025 a 12/2025',
        competencia: 202501,
        nomeMedico: 'Dra. Maria',
      },
      global: { directives: { tooltip() {} } },
    })

    expect(wrapper.get('button').attributes('aria-label')).toBe('1 ponto de atenção de Dra. Maria. Abrir histórico.')
    expect(wrapper.text()).toContain('1')
    expect(mocks.crmAlertasTooltip).toHaveBeenCalledWith(wrapper.props('pontos'), {
      periodo: '01/2025 a 12/2025',
      competencia: 202501,
    })
    expect(wrapper.get('button').attributes('style')).toContain('--alerta-cor')

    await wrapper.get('button').trigger('click')
    expect(wrapper.emitted('abrir')).toHaveLength(1)
  })

  it('usa rótulo plural e atualiza as cores quando muda o tema', async () => {
    const wrapper = mount(CrmAlertasBadge, {
      props: { pontos: [{}, {}], periodo: '2025', nomeMedico: 'Dr. João' },
      global: { directives: { tooltip() {} } },
    })

    expect(wrapper.get('button').attributes('aria-label')).toBe('2 pontos de atenção de Dr. João. Abrir histórico.')
    const lightStyle = wrapper.get('button').attributes('style')
    mocks.theme.isDark = true
    await wrapper.vm.$nextTick()
    expect(wrapper.get('button').attributes('style')).not.toBe(lightStyle)
  })
})
