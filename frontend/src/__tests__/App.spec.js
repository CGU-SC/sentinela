import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import axios from 'axios'

import App from '@/App.vue'
import { API_ENDPOINTS } from '@/config/api'
import { TIMING } from '@/config/constants'

const mocks = vi.hoisted(() => ({
  geoStore: null,
  themeStore: null,
  updateStore: null,
  openDownloadedFile: vi.fn(),
  createPdfObjectUrlFromDesktopFile: vi.fn(),
}))

vi.mock('axios', () => ({ default: { get: vi.fn() } }))
vi.mock('@/stores/geo', () => ({ useGeoStore: () => mocks.geoStore }))
vi.mock('@/stores/theme', () => ({ useThemeStore: () => mocks.themeStore }))
vi.mock('@/stores/systemUpdate', () => ({ useSystemUpdateStore: () => mocks.updateStore }))
vi.mock('@/utils/download', () => ({
  openDownloadedFile: mocks.openDownloadedFile,
  createPdfObjectUrlFromDesktopFile: mocks.createPdfObjectUrlFromDesktopFile,
}))
vi.mock('primevue/toast', () => ({
  default: {
    name: 'ToastStub',
    props: ['group'],
    data: () => ({ message: { summary: 'Arquivo pronto', detail: 'Clique para abrir', data: { path: 'C:/arquivo.docx', previewPath: 'C:/relatorio.pdf' } } }),
    template: '<div><button v-if="group === \'download\'" data-test="toast-without-file" @click="message = { summary: \'Vazio\', detail: \'Sem arquivo\', data: {} }" /><slot v-if="group === \'download\'" name="message" :message="message" /></div>',
  },
}))
vi.mock('@/views/components/UpdateBlocker.vue', () => ({ default: { template: '<div data-test="update-blocker" />' } }))
vi.mock('@/views/components/ExecutionBlocker.vue', () => ({ default: { template: '<div data-test="execution-blocker" />' } }))
vi.mock('@/views/components/UpdateDialog.vue', () => ({ default: { template: '<div />' } }))
vi.mock('@/views/components/DocumentPreviewDialog.vue', () => ({
  default: {
    props: ['visible', 'title', 'fileUrl', 'filePath'],
    emits: ['close', 'open-file'],
    template: '<div v-if="visible" data-test="document-preview"><span>{{ title }}|{{ fileUrl }}|{{ filePath }}</span><button data-test="preview-close" @click="$emit(\'close\')" /><button data-test="preview-open" @click="$emit(\'open-file\')" /></div>',
  },
}))
vi.mock('@/views/components/evidencias/EvidenciasRemocaoDialog.vue', () => ({ default: { template: '<div />' } }))

describe('App — inicialização da aplicação', () => {
  let wrapper
  let originalRevokeDescriptor

  beforeEach(() => {
    axios.get.mockResolvedValue({ data: { is_ready: true, status: 'ready', progress: 100 } })
    mocks.geoStore = {
      fetchLocalidades: vi.fn().mockResolvedValue(),
      loadMunicipiosGeo: vi.fn().mockResolvedValue(),
      fetchCnpjLookup: vi.fn().mockResolvedValue(),
    }
    mocks.themeStore = { initTheme: vi.fn() }
    mocks.updateStore = {
      status: 'current',
      isExecutionBlocked: false,
      fetchUpdateStatus: vi.fn().mockResolvedValue(),
    }
    mocks.openDownloadedFile.mockReset().mockResolvedValue()
    mocks.createPdfObjectUrlFromDesktopFile.mockReset().mockResolvedValue({
      url: 'blob:nota-tecnica', path: 'C:/nota-tecnica.pdf', filename: 'Nota Técnica',
    })
    originalRevokeDescriptor = Object.getOwnPropertyDescriptor(window.URL, 'revokeObjectURL')
    Object.defineProperty(window.URL, 'revokeObjectURL', {
      configurable: true,
      writable: true,
      value: vi.fn(),
    })
  })

  afterEach(() => {
    wrapper?.unmount()
    wrapper = null
    vi.restoreAllMocks()
    if (originalRevokeDescriptor) {
      Object.defineProperty(window.URL, 'revokeObjectURL', originalRevokeDescriptor)
    } else {
      delete window.URL.revokeObjectURL
    }
    vi.useRealTimers()
  })

  function mountApp() {
    return mount(App, {
      global: {
        stubs: {
          RouterView: { template: '<main data-test="router-view">Conteúdo da rota</main>' },
        },
      },
    })
  }

  it('mostra o carregamento e monta a área de rotas após o boot bem-sucedido', async () => {
    wrapper = mountApp()
    expect(wrapper.find('.app-boot-overlay').exists()).toBe(true)

    await flushPromises()

    expect(wrapper.find('.app-boot-overlay').exists()).toBe(false)
    expect(wrapper.get('[data-test="router-view"]').text()).toBe('Conteúdo da rota')
    expect(axios.get).toHaveBeenCalledTimes(2)
    expect(axios.get).toHaveBeenNthCalledWith(1, API_ENDPOINTS.cacheStatus)
    expect(mocks.geoStore.fetchLocalidades).toHaveBeenCalledOnce()
    expect(mocks.geoStore.loadMunicipiosGeo).toHaveBeenCalledOnce()
    expect(mocks.geoStore.fetchCnpjLookup).toHaveBeenCalledOnce()
    expect(mocks.themeStore.initTheme).toHaveBeenCalledOnce()
    expect(mocks.updateStore.fetchUpdateStatus).toHaveBeenCalledOnce()
  })

  it('expõe erro de conexão e permite tentar novamente', async () => {
    const errorSpy = vi.spyOn(console, 'error').mockImplementation(() => {})
    axios.get.mockRejectedValueOnce(new Error('Servidor indisponível'))
    wrapper = mountApp()

    await flushPromises()

    expect(wrapper.get('.error-title').text()).toBe('Falha de Conexão')
    expect(wrapper.text()).toContain('Servidor indisponível')
    expect(wrapper.get('.retry-button').exists()).toBe(true)

    await wrapper.get('.retry-button').trigger('click')
    await flushPromises()

    expect(wrapper.find('.app-boot-overlay').exists()).toBe(false)
    expect(wrapper.get('[data-test="router-view"]').exists()).toBe(true)
    expect(axios.get).toHaveBeenCalledTimes(3)
    expect(errorSpy).toHaveBeenCalledOnce()
  })

  it('aguarda sincronização ativa, atualiza as mensagens de progresso e libera a interface', async () => {
    vi.useFakeTimers()
    axios.get
      .mockResolvedValueOnce({ data: { is_ready: false, status: 'fetching' } })
      .mockResolvedValueOnce({ data: { progress: 25, status: 'fetching' } })
      .mockResolvedValueOnce({ data: { progress: 60, status: 'processing' } })
      .mockResolvedValueOnce({ data: { progress: 100, status: 'ready' } })
      .mockResolvedValueOnce({ data: { is_ready: true, status: 'ready' } })
    wrapper = mountApp()
    await flushPromises()

    expect(wrapper.text()).toContain('Sincronização em andamento no servidor...')
    await vi.advanceTimersByTimeAsync(TIMING.POLL_INTERVAL)
    await flushPromises()
    expect(wrapper.text()).toContain('Baixando dados do CGUData... (25%)')
    await vi.advanceTimersByTimeAsync(TIMING.POLL_INTERVAL)
    await flushPromises()
    expect(wrapper.text()).toContain('Otimizando Banco de Dados...')
    await vi.advanceTimersByTimeAsync(TIMING.POLL_INTERVAL)
    await flushPromises()

    expect(wrapper.find('[data-test="router-view"]').exists()).toBe(true)
    expect(axios.get).toHaveBeenCalledTimes(5)
  })

  it.each(['idle', 'error'])('libera o boot sem aguardar quando a sincronização termina em %s', async (status) => {
    vi.useFakeTimers()
    axios.get
      .mockResolvedValueOnce({ data: { is_ready: false, status: 'processing' } })
      .mockResolvedValueOnce({ data: { progress: 0, status } })
      .mockResolvedValueOnce({ data: { is_ready: false, status } })
    wrapper = mountApp()
    await flushPromises()
    await vi.advanceTimersByTimeAsync(TIMING.POLL_INTERVAL)
    await flushPromises()

    expect(wrapper.find('[data-test="router-view"]').exists()).toBe(true)
    expect(axios.get).toHaveBeenCalledTimes(3)
  })

  it('sobe em modo degradado mesmo quando uma carga de referência falha', async () => {
    const warningSpy = vi.spyOn(console, 'warn').mockImplementation(() => {})
    axios.get.mockResolvedValue({ data: { is_ready: false, status: 'idle', progress: 0 } })
    mocks.geoStore.fetchLocalidades.mockRejectedValueOnce(new Error('Localidades indisponíveis'))
    wrapper = mountApp()

    await flushPromises()

    expect(wrapper.find('[data-test="router-view"]').exists()).toBe(true)
    expect(warningSpy).toHaveBeenCalledWith('Alguns caches estão ausentes. Iniciando em Modo Degradado.')
  })

  it('usa a mensagem retornada pela API quando a conexão inicial falha', async () => {
    vi.spyOn(console, 'error').mockImplementation(() => {})
    axios.get.mockRejectedValueOnce({ response: { data: { message: 'API em manutenção' } } })
    wrapper = mountApp()

    await flushPromises()

    expect(wrapper.text()).toContain('API em manutenção')
  })

  it('converte um erro sem mensagem em texto legível para diagnóstico', async () => {
    vi.spyOn(console, 'error').mockImplementation(() => {})
    axios.get.mockRejectedValueOnce({})
    wrapper = mountApp()

    await flushPromises()

    expect(wrapper.text()).toContain('[object Object]')
  })

  it('abre arquivo baixado e visualiza PDF salvo a partir do toast', async () => {
    wrapper = mountApp()
    await flushPromises()

    await wrapper.get('.download-toast-action').trigger('click')
    expect(mocks.openDownloadedFile).toHaveBeenCalledWith('C:/arquivo.docx')

    await wrapper.findAll('.download-toast-action')[1].trigger('click')
    await flushPromises()
    expect(mocks.createPdfObjectUrlFromDesktopFile).toHaveBeenCalledWith('C:/relatorio.pdf')
    expect(wrapper.get('[data-test="document-preview"]').text()).toContain('Nota Técnica|blob:nota-tecnica|C:/nota-tecnica.pdf')

    await wrapper.get('[data-test="preview-open"]').trigger('click')
    expect(mocks.openDownloadedFile).toHaveBeenLastCalledWith('C:/nota-tecnica.pdf')
    await wrapper.get('[data-test="preview-close"]').trigger('click')
    expect(window.URL.revokeObjectURL).toHaveBeenCalledWith('blob:nota-tecnica')
    expect(wrapper.find('[data-test="document-preview"]').exists()).toBe(false)
  })

  it('mantém o toast sem ações quando ele não contém arquivo', async () => {
    wrapper = mountApp()
    await flushPromises()

    await wrapper.get('[data-test="toast-without-file"]').trigger('click')

    expect(wrapper.findAll('.download-toast-action')).toHaveLength(0)
  })

  it('usa o título padrão quando o arquivo PDF não traz nome', async () => {
    mocks.createPdfObjectUrlFromDesktopFile.mockResolvedValueOnce({
      url: 'blob:sem-nome', path: 'C:/sem-nome.pdf', filename: '',
    })
    wrapper = mountApp()
    await flushPromises()

    await wrapper.findAll('.download-toast-action')[1].trigger('click')
    await flushPromises()

    expect(wrapper.get('[data-test="document-preview"]').text()).toContain('Nota Tecnica|blob:sem-nome|C:/sem-nome.pdf')
  })

  it('trata erros ao abrir arquivos e não faz nada quando falta o caminho', async () => {
    const errorSpy = vi.spyOn(console, 'error').mockImplementation(() => {})
    wrapper = mountApp()
    await flushPromises()
    const appSetup = wrapper.vm.$.setupState

    await appSetup.openToastFile({ data: {} })
    await appSetup.openToastPreview({ data: {} })
    await appSetup.openPreviewExternalFile()
    expect(mocks.openDownloadedFile).not.toHaveBeenCalled()
    expect(mocks.createPdfObjectUrlFromDesktopFile).not.toHaveBeenCalled()

    mocks.openDownloadedFile.mockRejectedValueOnce(new Error('Não foi possível abrir'))
    await appSetup.openToastFile({ data: { path: 'C:/falha.docx' } })
    mocks.createPdfObjectUrlFromDesktopFile.mockRejectedValueOnce(new Error('PDF inválido'))
    await appSetup.openToastPreview({ data: { previewPath: 'C:/falha.pdf' } })
    appSetup.previewPath = 'C:/falha.pdf'
    mocks.openDownloadedFile.mockRejectedValueOnce(new Error('PDF não abriu'))
    await appSetup.openPreviewExternalFile()

    expect(errorSpy).toHaveBeenCalledWith('Erro ao abrir arquivo salvo:', expect.any(Error))
    expect(errorSpy).toHaveBeenCalledWith('Erro ao visualizar PDF salvo:', expect.any(Error))
    expect(errorSpy).toHaveBeenCalledWith('Erro ao abrir PDF salvo:', expect.any(Error))
  })

  it('continua aguardando quando uma consulta de progresso falha e limpa o timer ao desmontar', async () => {
    vi.useFakeTimers()
    const warningSpy = vi.spyOn(console, 'warn').mockImplementation(() => {})
    axios.get
      .mockResolvedValueOnce({ data: { is_ready: false, status: 'fetching' } })
      .mockRejectedValueOnce(new Error('Status temporariamente indisponível'))
    wrapper = mountApp()
    await flushPromises()

    await vi.advanceTimersByTimeAsync(TIMING.POLL_INTERVAL)
    await flushPromises()

    expect(wrapper.find('.app-boot-overlay').exists()).toBe(true)
    expect(warningSpy).toHaveBeenCalledWith('Erro ao checar status:', expect.any(Error))
    wrapper.unmount()
    wrapper = null
  })

  it('renderiza bloqueios de atualização incompatível e de execução', async () => {
    mocks.updateStore.status = 'update_required'
    wrapper = mountApp()
    await flushPromises()
    expect(wrapper.find('[data-test="update-blocker"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="execution-blocker"]').exists()).toBe(false)

    wrapper.unmount()
    mocks.updateStore.status = 'current'
    mocks.updateStore.isExecutionBlocked = true
    wrapper = mountApp()
    await flushPromises()
    expect(wrapper.find('[data-test="update-blocker"]').exists()).toBe(false)
    expect(wrapper.find('[data-test="execution-blocker"]').exists()).toBe(true)
  })
})
