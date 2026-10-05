import { describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'

import TargetTableRenderer from '@/views/components/targets/TargetTableRenderer.vue'

const tableStub = {
  props: ['targetMeta', 'rows', 'loading', 'totalRecords', 'first', 'rowsPerPage', 'sortField', 'sortOrder', 'sourceNotice'],
  emits: ['lazy-load', 'open-incompatibility'],
  template: '<div data-test="clinical-table"><button data-test="page" @click="$emit(\'lazy-load\', { first: 20 })">Página</button><button data-test="open" @click="$emit(\'open-incompatibility\', rows[0])">Abrir</button></div>',
}

describe('TargetTableRenderer', () => {
  it('encaminha os dados e os eventos da tabela clínica', async () => {
    const targetMeta = { tableComponent: 'ClinicalTargetTable' }
    const rows = [{ cnpj: '12345678000195' }]
    const wrapper = mount(TargetTableRenderer, {
      props: {
        targetKey: 'parkinson_menor_50',
        targetMeta,
        rows,
        loading: true,
        totalRecords: 21,
        first: 20,
        rowsPerPage: 20,
        sortField: 'valor_incompativel',
        sortOrder: -1,
        sourceNotice: 'Base atualizada',
      },
      global: { stubs: { ClinicalTargetTable: tableStub } },
    })

    expect(wrapper.findComponent(tableStub).props()).toMatchObject({
      targetMeta,
      rows,
      loading: true,
      totalRecords: 21,
      first: 20,
      rowsPerPage: 20,
      sortField: 'valor_incompativel',
      sortOrder: -1,
      sourceNotice: 'Base atualizada',
    })
    await wrapper.get('[data-test="page"]').trigger('click')
    await wrapper.get('[data-test="open"]').trigger('click')
    expect(wrapper.emitted('lazy-load')).toEqual([[{ first: 20 }]])
    expect(wrapper.emitted('open-incompatibility')).toEqual([[rows[0]]])
  })

  it('falha com erro explícito quando o alvo não possui componente configurado', () => {
    expect(() => mount(TargetTableRenderer, {
      props: { targetKey: 'unmapped', targetMeta: { tableComponent: 'UnknownTable' } },
    })).toThrow('Tabela sem componente para alvo: unmapped')
  })
})
