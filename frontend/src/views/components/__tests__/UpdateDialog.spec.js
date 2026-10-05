import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { reactive } from 'vue'

import UpdateDialog from '@/views/components/UpdateDialog.vue'

const mocks = vi.hoisted(() => ({ store: null }))

vi.mock('@/stores/systemUpdate', () => ({ useSystemUpdateStore: () => mocks.store }))
vi.mock('primevue/dialog', () => ({
  default: {
    props: ['visible', 'closable', 'closeOnEscape', 'modal'],
    emits: ['hide', 'update:visible'],
    template: '<div class="dialog"><slot name="header" /><slot /><button data-test="hide-dialog" @click="$emit(\'hide\')">Ocultar</button><button data-test="set-invisible" @click="$emit(\'update:visible\', false)">Fechar por visibilidade</button></div>',
  },
}))
vi.mock('primevue/button', () => ({
  default: {
    props: ['label'],
    emits: ['click'],
    template: '<button type="button" @click="$emit(\'click\')">{{ label }}</button>',
  },
}))

describe('UpdateDialog', () => {
  beforeEach(() => {
    mocks.store = reactive({
      downloadDialogVisible: true,
      isDownloading: false,
      downloadDone: false,
      downloadFailed: false,
      downloadProgress: 35,
      downloadStatus: 'downloading',
      downloadStatusLabel: 'Baixando atualização',
      downloadError: null,
      latestVersion: '2.2.0',
      closeDownloadDialog: vi.fn(),
      startDownload: vi.fn(),
    })
  })

  afterEach(() => vi.restoreAllMocks())

  it('exibe progresso ativo e bloqueia o fechamento durante o download', async () => {
    mocks.store.isDownloading = true
    const wrapper = mount(UpdateDialog)

    expect(wrapper.text()).toContain('Sentinela v2.2.0')
    expect(wrapper.get('[role="progressbar"]').attributes('aria-valuenow')).toBe('35')
    expect(wrapper.get('.update-progress-bar__fill').attributes('style')).toContain('width: 35%')
    expect(wrapper.get('.update-progress-bar__fill').classes()).toContain('update-progress-bar__fill--active')
    const retryButton = wrapper.findAll('button').find((button) => button.text() === 'Tentar novamente')
    expect(retryButton.exists()).toBe(true)
    expect(retryButton.element.style.display).toBe('none')

    await wrapper.get('[data-test="hide-dialog"]').trigger('click')
    expect(mocks.store.closeDownloadDialog).not.toHaveBeenCalled()
  })

  it('mostra erro, permite fechar e iniciar nova tentativa', async () => {
    mocks.store.downloadFailed = true
    mocks.store.downloadError = 'Falha de rede'
    mocks.store.downloadProgress = 73
    const wrapper = mount(UpdateDialog)

    expect(wrapper.get('.update-dialog__icon').classes()).toContain('update-dialog__icon--error')
    expect(wrapper.get('.update-progress-bar__fill').classes()).toContain('update-progress-bar__fill--error')
    expect(wrapper.text()).toContain('Falha de rede')
    await wrapper.findAll('button').find((button) => button.text() === 'Fechar').trigger('click')
    await wrapper.findAll('button').find((button) => button.text() === 'Tentar novamente').trigger('click')
    expect(mocks.store.closeDownloadDialog).toHaveBeenCalledOnce()
    expect(mocks.store.startDownload).toHaveBeenCalledOnce()
  })

  it('marca conclusão e não fecha novamente ao receber evento de ocultação', async () => {
    mocks.store.downloadDone = true
    mocks.store.downloadProgress = 100
    const wrapper = mount(UpdateDialog)

    expect(wrapper.get('.update-dialog__icon').classes()).toContain('update-dialog__icon--done')
    expect(wrapper.get('.update-progress-bar__fill').classes()).toContain('update-progress-bar__fill--done')
    await wrapper.get('[data-test="hide-dialog"]').trigger('click')
    expect(mocks.store.closeDownloadDialog).not.toHaveBeenCalled()
  })

  it('fecha o estado ocioso quando o diálogo é ocultado', async () => {
    const wrapper = mount(UpdateDialog)
    await wrapper.get('[data-test="hide-dialog"]').trigger('click')
    expect(mocks.store.closeDownloadDialog).toHaveBeenCalledOnce()
  })

  it('sincroniza o v-model de visibilidade emitido pelo diálogo', async () => {
    const wrapper = mount(UpdateDialog)

    await wrapper.get('[data-test="set-invisible"]').trigger('click')

    expect(mocks.store.downloadDialogVisible).toBe(false)
  })

  it('identifica a fase de aplicação enquanto aguarda a conclusão', async () => {
    mocks.store.downloadStatus = 'applying'
    mocks.store.downloadStatusLabel = 'Aplicando atualização'
    mocks.store.latestVersion = null
    const wrapper = mount(UpdateDialog)

    expect(wrapper.get('.update-progress-bar__fill').classes()).toContain('update-progress-bar__fill--applying')
    expect(wrapper.get('.update-dialog__icon').classes()).toContain('update-dialog__icon--active')
    expect(wrapper.get('.update-dialog__icon i').classes()).toContain('pi-cloud-download')
    expect(wrapper.text()).toContain('Aplicando atualização')
    expect(wrapper.text()).toContain('Sentinela v...')
  })
})
