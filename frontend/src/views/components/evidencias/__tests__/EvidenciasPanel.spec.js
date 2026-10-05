import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, disposePinia, setActivePinia } from 'pinia'
import { defineComponent } from 'vue'
import { createMemoryHistory, createRouter } from 'vue-router'
import axios from 'axios'

import EvidenciasPanel from '@/views/components/evidencias/EvidenciasPanel.vue'
import { useEvidenciasStore } from '@/stores/evidencias'
import { API_ENDPOINTS } from '@/config/api'

const mocks = vi.hoisted(() => ({
  toastAdd: vi.fn(),
  downloadBlobFromResponse: vi.fn(),
  getApiErrorMessage: vi.fn(),
}))

vi.mock('axios', () => ({
  default: {
    get: vi.fn(),
    patch: vi.fn(),
    delete: vi.fn(),
  },
}))

vi.mock('primevue/usetoast', () => ({
  useToast: () => ({ add: mocks.toastAdd }),
}))
vi.mock('@/utils/download', () => ({ downloadBlobFromResponse: mocks.downloadBlobFromResponse }))
vi.mock('@/utils/apiErrors', () => ({ getApiErrorMessage: mocks.getApiErrorMessage }))

const CNPJ = '12345678000195'
const EVIDENCIAS = [
  {
    id: 'ev-dia', cnpj: CNPJ, tipo: 'dia', dt_janela: '2025-01-02', hora: null,
    num_autorizacao: null, nota: null, criado_em: '2025-01-03T12:00:00Z',
    snapshot: { qtd: 3, alertas: ['Volume Atípico'] },
  },
  {
    id: 'ev-hora', cnpj: CNPJ, tipo: 'hora', dt_janela: '2025-01-02', hora: 11,
    num_autorizacao: null, nota: 'Revisar documentos', criado_em: '2025-01-03T12:10:00Z',
    snapshot: { qtd: 2, alertas: [] },
  },
]

const SidebarStub = defineComponent({
  props: { visible: Boolean },
  emits: ['update:visible'],
  template: '<section v-if="visible"><button data-test="sidebar-update-close" @click="$emit(\'update:visible\', false)">Fechar pela sidebar</button><header><slot name="header" /></header><slot /><footer><slot name="footer" /></footer></section>',
})

function makeRouter() {
  return createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/', name: 'Home', component: { template: '<div />' } },
      { path: '/estabelecimentos/:cnpj', name: 'EstablishmentDetail', component: { template: '<div />' } },
    ],
  })
}

describe('EvidenciasPanel', () => {
  let pinia
  let store
  let router
  let wrapper

  beforeEach(() => {
    vi.clearAllMocks()
    mocks.downloadBlobFromResponse.mockResolvedValue({ desktop: false, filename: 'evidencias.xlsx' })
    mocks.getApiErrorMessage.mockResolvedValue('Falha detalhada do servidor')
    axios.get.mockResolvedValue({ data: EVIDENCIAS })
    axios.patch.mockImplementation(async (url, payload) => {
      const id = url.endsWith('/ev-dia') ? 'ev-dia' : 'ev-hora'
      return { data: { ...EVIDENCIAS.find((item) => item.id === id), nota: payload.nota } }
    })
    axios.delete.mockResolvedValue({ data: {} })
    mocks.toastAdd.mockReset()

    pinia = createPinia()
    setActivePinia(pinia)
    store = useEvidenciasStore()
    router = makeRouter()
    wrapper = mount(EvidenciasPanel, {
      props: { cnpj: CNPJ, razaoSocial: 'Farmácia Exemplo', contexto: 'listas' },
      global: {
        plugins: [pinia, router],
        stubs: { Sidebar: SidebarStub },
      },
    })
  })

  afterEach(() => {
    wrapper?.unmount()
    disposePinia(pinia)
    vi.restoreAllMocks()
    vi.unstubAllGlobals()
  })

  it('carrega e exibe evidências ao abrir o painel', async () => {
    expect(wrapper.find('section').exists()).toBe(false)
    store.painelAberto = true
    await flushPromises()

    expect(axios.get).toHaveBeenCalledOnce()
    expect(wrapper.text()).toContain('Farmácia Exemplo')
    expect(wrapper.findAll('.evid-item')).toHaveLength(2)
    expect(wrapper.text()).toContain('Volume Atípico')
  })

  it('filtra a lista pelo tipo selecionado', async () => {
    store.itens = EVIDENCIAS
    store.loadState = 'ready'
    store.painelAberto = true
    await flushPromises()

    const filtroHoras = wrapper.findAll('[role="radio"]').find((button) => button.text().startsWith('Horas'))
    await filtroHoras.trigger('click')

    expect(wrapper.findAll('.evid-item')).toHaveLength(1)
    expect(wrapper.get('.evid-item-tipo').text()).toContain('Hora')
  })

  it('informa quando o tipo selecionado não tem evidências', async () => {
    store.itens = EVIDENCIAS
    store.loadState = 'ready'
    store.painelAberto = true
    await flushPromises()

    const filtroAutorizacoes = wrapper.findAll('[role="radio"]')
      .find((button) => button.text().startsWith('Autorizações'))
    await filtroAutorizacoes.trigger('click')

    expect(wrapper.findAll('.evid-item')).toHaveLength(0)
    expect(wrapper.get('.evid-sb-vazio').text()).toBe('Nenhuma evidência deste tipo.')
  })

  it('limpa filtro e edição quando muda o CNPJ e fecha por qualquer controle do painel', async () => {
    store.itens = EVIDENCIAS
    store.loadState = 'ready'
    store.painelAberto = true
    await flushPromises()

    const filtroHoras = wrapper.findAll('[role="radio"]').find((button) => button.text().startsWith('Horas'))
    await filtroHoras.trigger('click')
    await wrapper.get('[aria-label^="Editar nota:"]').trigger('click')
    expect(wrapper.get('textarea[aria-label="Nota do auditor"]').exists()).toBe(true)

    await wrapper.setProps({ cnpj: '98765432000198', razaoSocial: 'Outra Farmácia' })
    await flushPromises()
    expect(wrapper.find('textarea[aria-label="Nota do auditor"]').exists()).toBe(false)
    expect(wrapper.vm.$.setupState.filtroTipo).toBeNull()

    await wrapper.get('[data-test="sidebar-update-close"]').trigger('click')
    expect(store.painelAberto).toBe(false)
    store.painelAberto = true
    await wrapper.vm.$nextTick()
    await wrapper.get('[aria-label="Fechar painel de evidências"]').trigger('click')
    expect(store.painelAberto).toBe(false)
  })

  it('salva a nota editada e atualiza o item exibido', async () => {
    store.itens = EVIDENCIAS
    store.loadState = 'ready'
    store.painelAberto = true
    await flushPromises()
    await wrapper.get('[aria-label^="Editar nota:"]').trigger('click')
    await wrapper.get('textarea[aria-label="Nota do auditor"]').setValue('Evidência conferida')
    await wrapper.get('button.is-primary').trigger('click')
    await flushPromises()

    expect(axios.patch).toHaveBeenCalledWith(expect.any(String), { nota: 'Evidência conferida' })
    expect(store.itens.find((item) => item.id === 'ev-dia').nota).toBe('Evidência conferida')
    expect(wrapper.text()).toContain('Evidência conferida')
    expect(wrapper.find('textarea').exists()).toBe(false)
  })

  it('pede confirmação antes de remover e atualiza a lista após confirmar', async () => {
    store.itens = EVIDENCIAS
    store.loadState = 'ready'
    store.painelAberto = true
    await flushPromises()
    await wrapper.get('[aria-label^="Remover evidência:"]').trigger('click')

    expect(wrapper.text()).toContain('Remover esta evidência?')
    expect(axios.delete).not.toHaveBeenCalled()
    await wrapper.findAll('.evid-item-confirma button').find((button) => button.text().trim() === 'Cancelar').trigger('click')
    expect(wrapper.text()).not.toContain('Remover esta evidência?')
    expect(axios.delete).not.toHaveBeenCalled()
    await wrapper.get('[aria-label^="Remover evidência:"]').trigger('click')

    const removeButton = wrapper.findAll('button.is-danger').find((button) => button.text().trim() === 'Remover')
    await removeButton.trigger('click')
    await flushPromises()

    expect(axios.delete).toHaveBeenCalledOnce()
    expect(store.itens.map((item) => item.id)).toEqual(['ev-hora'])
    expect(wrapper.findAll('.evid-item')).toHaveLength(1)
  })

  it('mostra erro de carregamento, permite tentar novamente e trata lista vazia', async () => {
    store.itens = []
    store.loadState = 'error'
    store.error = 'Não foi possível carregar'
    vi.spyOn(store, 'garantirCarregado').mockImplementation(() => {})
    store.painelAberto = true
    const retry = vi.spyOn(store, 'carregar').mockResolvedValue()
    await flushPromises()

    expect(wrapper.get('[role="alert"]').text()).toContain('Não foi possível carregar')
    await wrapper.get('[role="alert"] button').trigger('click')
    expect(retry).toHaveBeenCalledOnce()

    store.loadState = 'ready'
    store.error = null
    await wrapper.vm.$nextTick()
    expect(wrapper.text()).toContain('Nenhuma evidência marcada nesta farmácia.')
    expect(wrapper.get('.evid-sb-export').element.disabled).toBe(true)
  })

  it('não exporta uma lista vazia e abre evidência sem contexto de farmácia', async () => {
    store.itens = []
    store.loadState = 'ready'
    store.painelAberto = true
    await flushPromises()
    const fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)

    await wrapper.vm.$.setupState.exportarExcel()
    expect(fetchMock).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain('Nenhuma evidência marcada nesta farmácia.')

    store.itens = EVIDENCIAS
    await wrapper.vm.$nextTick()
    const abrirEvidencia = vi.spyOn(store, 'irPara').mockResolvedValue()
    await wrapper.get('[aria-label^="Abrir na Cronologia:"]').trigger('click')
    await flushPromises()

    expect(abrirEvidencia).toHaveBeenCalledWith(EVIDENCIAS[0], router, null)
  })

  it('cancela a edição por teclado, salva por atalho e mostra erro da API', async () => {
    store.itens = EVIDENCIAS
    store.loadState = 'ready'
    store.painelAberto = true
    await flushPromises()

    await wrapper.get('[aria-label^="Editar nota:"]').trigger('click')
    await wrapper.get('textarea[aria-label="Nota do auditor"]').setValue('rascunho')
    await wrapper.get('textarea[aria-label="Nota do auditor"]').trigger('keydown', { key: 'Escape' })
    expect(wrapper.find('textarea').exists()).toBe(false)

    const update = vi.spyOn(store, 'atualizarNota').mockResolvedValueOnce({})
    await wrapper.get('[aria-label^="Editar nota:"]').trigger('click')
    await wrapper.get('textarea[aria-label="Nota do auditor"]').setValue('Nota via atalho')
    await wrapper.get('textarea[aria-label="Nota do auditor"]').trigger('keydown', {
      key: 'Enter', ctrlKey: false, metaKey: true,
    })
    await flushPromises()
    expect(update).toHaveBeenCalledWith('ev-dia', 'Nota via atalho')
    expect(wrapper.find('textarea').exists()).toBe(false)

    update.mockRejectedValueOnce(new Error('Nota bloqueada'))
    await wrapper.get('[aria-label^="Editar nota:"]').trigger('click')
    await wrapper.get('textarea[aria-label="Nota do auditor"]').setValue('Não salvar')
    await wrapper.get('button.is-primary').trigger('click')
    await flushPromises()
    expect(wrapper.find('li.is-busy').exists()).toBe(false)
    expect(wrapper.find('textarea').exists()).toBe(true)
    expect(mocks.toastAdd).toHaveBeenCalledWith(expect.objectContaining({
      severity: 'error', summary: 'Nota não salva', detail: 'Nota bloqueada',
    }))
  })

  it('apresenta falha ao remover e navega para cronologia no contexto da farmácia', async () => {
    store.itens = EVIDENCIAS
    store.loadState = 'ready'
    store.painelAberto = true
    await wrapper.setProps({ contexto: 'farmacia' })
    const remove = vi.spyOn(store, 'remover').mockRejectedValueOnce(new Error('Exclusão negada'))
    const goToEvidence = vi.spyOn(store, 'irPara').mockResolvedValue()
    await flushPromises()

    await wrapper.get('[aria-label^="Remover evidência:"]').trigger('click')
    await wrapper.findAll('button.is-danger').find((button) => button.text().trim() === 'Remover').trigger('click')
    await flushPromises()
    expect(remove).toHaveBeenCalledWith('ev-dia')
    expect(mocks.toastAdd).toHaveBeenCalledWith(expect.objectContaining({
      severity: 'error', summary: 'Evidência não removida', detail: 'Exclusão negada',
    }))

    await wrapper.get('[aria-label^="Abrir na Cronologia:"]').trigger('click')
    await flushPromises()
    expect(goToEvidence).toHaveBeenCalledWith(EVIDENCIAS[0], router, CNPJ)
    expect(store.painelAberto).toBe(false)
  })

  it('permite abrir a farmácia a partir de listas e exportar Excel nos dois destinos', async () => {
    store.itens = EVIDENCIAS
    store.loadState = 'ready'
    store.painelAberto = true
    await router.push('/')
    await router.isReady()
    await flushPromises()
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, status: 200 })
    vi.stubGlobal('fetch', fetchMock)

    await wrapper.get('.evid-sb-export').trigger('click')
    await flushPromises()
    expect(fetchMock).toHaveBeenCalledWith(API_ENDPOINTS.evidenciasExportar(CNPJ))
    expect(mocks.downloadBlobFromResponse).toHaveBeenCalledWith(expect.any(Object), `evidencias_${CNPJ}.xlsx`)
    expect(mocks.toastAdd).toHaveBeenCalledWith(expect.objectContaining({
      severity: 'success', summary: 'Excel das evidências baixado', detail: 'evidencias.xlsx',
    }))

    mocks.downloadBlobFromResponse.mockResolvedValueOnce({ desktop: true, filename: 'evidencias.xlsx', path: 'C:/Downloads/evidencias.xlsx' })
    await wrapper.get('.evid-sb-export').trigger('click')
    await flushPromises()
    expect(mocks.toastAdd).toHaveBeenCalledWith(expect.objectContaining({
      group: 'download', severity: 'success', summary: 'Excel das evidências salvo',
      data: expect.objectContaining({ path: 'C:/Downloads/evidencias.xlsx' }),
    }))

    await wrapper.get('.evid-sb-link').trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.name).toBe('EstablishmentDetail')
    expect(router.currentRoute.value.params.cnpj).toBe(CNPJ)
  })

  it('trata HTTP e exceções durante a exportação e zera o estado ocupado', async () => {
    store.itens = EVIDENCIAS
    store.loadState = 'ready'
    store.painelAberto = true
    await flushPromises()
    const fetchMock = vi.fn()
      .mockResolvedValueOnce({ ok: false, status: 503 })
      .mockRejectedValueOnce(new Error('Sem conexão'))
    vi.stubGlobal('fetch', fetchMock)

    await wrapper.get('.evid-sb-export').trigger('click')
    await flushPromises()
    expect(mocks.getApiErrorMessage).toHaveBeenCalledWith(expect.any(Object), expect.stringContaining('503'))
    expect(mocks.toastAdd).toHaveBeenCalledWith(expect.objectContaining({
      severity: 'error', summary: 'Falha na exportação', detail: 'Falha detalhada do servidor',
    }))
    expect(wrapper.get('.evid-sb-export').element.disabled).toBe(false)

    await wrapper.get('.evid-sb-export').trigger('click')
    await flushPromises()
    expect(mocks.toastAdd).toHaveBeenCalledWith(expect.objectContaining({
      severity: 'error', summary: 'Falha na exportação', detail: 'Sem conexão',
    }))
  })
})
