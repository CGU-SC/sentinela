import { afterEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { reactive } from 'vue'

import ExecutionBlocker from '@/views/components/ExecutionBlocker.vue'

const mocks = vi.hoisted(() => ({ store: null }))

vi.mock('@/stores/systemUpdate', () => ({ useSystemUpdateStore: () => mocks.store }))

describe('ExecutionBlocker', () => {
  afterEach(() => vi.restoreAllMocks())

  it('mostra o motivo, a versão instalada, a data de bloqueio e permite consultar novamente', async () => {
    const forceCheckUpdate = vi.fn()
    mocks.store = reactive({
      blockTitle: 'Versão bloqueada',
      blockMessage: 'Atualize para continuar.',
      blockedSince: '2025-01-15T12:30:00',
      currentVersion: '1.2.0',
      forceCheckUpdate,
    })
    const wrapper = mount(ExecutionBlocker)

    expect(wrapper.get('[role="alertdialog"]').exists()).toBe(true)
    expect(wrapper.text()).toContain('Versão bloqueada')
    expect(wrapper.text()).toContain('Atualize para continuar.')
    expect(wrapper.text()).toContain('1.2.0')
    expect(wrapper.text()).toContain('15/01/2025')

    await wrapper.get('.execution-action--primary').trigger('click')
    expect(forceCheckUpdate).toHaveBeenCalledOnce()
  })

  it('usa mensagens padrão e omite a data quando não há data de bloqueio', () => {
    mocks.store = reactive({
      blockTitle: null,
      blockMessage: '',
      blockedSince: null,
      currentVersion: null,
      forceCheckUpdate: vi.fn(),
    })
    const wrapper = mount(ExecutionBlocker)

    expect(wrapper.text()).toContain('Execução bloqueada')
    expect(wrapper.text()).toContain('temporariamente bloqueada')
    expect(wrapper.text()).toContain('v—')
    expect(wrapper.find('.execution-blocker__since').exists()).toBe(false)
  })

  it('oculta uma data de bloqueio inválida', () => {
    mocks.store = reactive({
      blockTitle: 'Bloqueio',
      blockMessage: 'Sem acesso',
      blockedSince: 'não é uma data',
      currentVersion: '2.0.0',
      forceCheckUpdate: vi.fn(),
    })
    const wrapper = mount(ExecutionBlocker)

    expect(wrapper.find('.execution-blocker__since').exists()).toBe(false)
    expect(wrapper.text()).toContain('Bloqueio')
  })
})
