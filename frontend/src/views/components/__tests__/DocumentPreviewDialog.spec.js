import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'

import DocumentPreviewDialog from '@/views/components/DocumentPreviewDialog.vue'

describe('DocumentPreviewDialog', () => {
  it('fica oculto até abrir e apresenta estado vazio para PDF sem URL', async () => {
    const wrapper = mount(DocumentPreviewDialog, { props: { visible: false } })
    expect(wrapper.find('[role="dialog"]').exists()).toBe(false)

    await wrapper.setProps({ visible: true, title: 'Relatório mensal' })
    expect(wrapper.get('[role="dialog"]').text()).toContain('Relatório mensal')
    expect(wrapper.text()).toContain('PDF indisponivel para visualizacao.')
    expect(wrapper.find('iframe').exists()).toBe(false)
  })

  it('mostra o PDF, oferece abertura local quando há caminho e emite ações', async () => {
    const wrapper = mount(DocumentPreviewDialog, {
      props: { visible: true, title: 'Nota Técnica', fileUrl: 'blob:test-pdf', filePath: 'C:/relatorio.pdf' },
    })

    expect(wrapper.get('iframe').attributes('src')).toBe('blob:test-pdf')
    expect(wrapper.get('iframe').attributes('title')).toBe('Pre-visualizacao do documento PDF')
    await wrapper.get('.document-preview__button').trigger('click')
    await wrapper.get('.document-preview__close').trigger('click')
    expect(wrapper.emitted('open-file')).toHaveLength(1)
    expect(wrapper.emitted('close')).toHaveLength(1)
  })

  it('omite a ação para abrir arquivo quando não há caminho local', () => {
    const wrapper = mount(DocumentPreviewDialog, { props: { visible: true, fileUrl: 'blob:test-pdf' } })
    expect(wrapper.find('.document-preview__button').exists()).toBe(false)
  })
})
