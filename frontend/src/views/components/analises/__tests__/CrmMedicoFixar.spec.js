import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { reactive } from 'vue'

import CrmMedicoFixar from '@/views/components/analises/CrmMedicoFixar.vue'

const mocks = vi.hoisted(() => ({ store: null, toastAdd: vi.fn() }))

vi.mock('@/stores/crmMedicosFixados', () => ({
  CRM_MEDICOS_FIXADOS_MAX: 100,
  useCrmMedicosFixadosStore: () => mocks.store,
}))
vi.mock('primevue/usetoast', () => ({ useToast: () => ({ add: mocks.toastAdd }) }))

describe('CrmMedicoFixar', () => {
  beforeEach(() => {
    mocks.toastAdd.mockReset()
    mocks.store = reactive({
      ids: new Set(),
      alternar: vi.fn((medico) => {
        if (mocks.store.ids.has(medico.id_medico)) {
          mocks.store.ids.delete(medico.id_medico)
          return true
        }
        mocks.store.ids.add(medico.id_medico)
        return true
      }),
    })
  })

  afterEach(() => vi.restoreAllMocks())

  it('fixa e solta o médico e mantém estado acessível no botão', async () => {
    const wrapper = mount(CrmMedicoFixar, {
      props: { idMedico: '123/RO', nome: 'Dra. Ana', crm: '123/RO' },
      global: { directives: { tooltip() {} } },
    })

    expect(wrapper.get('button').attributes('aria-pressed')).toBe('false')
    expect(wrapper.get('button').attributes('aria-label')).toBe('Fixar Dra. Ana')
    await wrapper.get('button').trigger('click')
    expect(mocks.store.alternar).toHaveBeenCalledWith({ id_medico: '123/RO', nome: 'Dra. Ana', crm: '123/RO' })
    expect(wrapper.get('button').attributes('aria-pressed')).toBe('true')
    expect(wrapper.get('button').attributes('aria-label')).toBe('Soltar Dra. Ana')

    await wrapper.get('button').trigger('click')
    expect(wrapper.get('button').attributes('aria-pressed')).toBe('false')
  })

  it('avisa quando o limite de médicos fixados impede a ação', async () => {
    mocks.store.alternar.mockReturnValue(false)
    const wrapper = mount(CrmMedicoFixar, {
      props: { idMedico: '456/SP', nome: 'Dr. Bruno', crm: '456/SP' },
      global: { directives: { tooltip() {} } },
    })

    await wrapper.get('button').trigger('click')
    expect(mocks.toastAdd).toHaveBeenCalledWith(expect.objectContaining({
      severity: 'warn',
      summary: 'Limite de médicos fixados',
      detail: expect.stringContaining('100 médicos'),
    }))
  })
})
