import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { reactive } from 'vue'

import SettingsView from '@/views/SettingsView.vue'

const mocks = vi.hoisted(() => ({ notaTecnica: null, metodologia: null, toastAdd: vi.fn() }))

vi.mock('@/stores/notaTecnicaConfig', () => ({ useNotaTecnicaConfigStore: () => mocks.notaTecnica }))
vi.mock('@/stores/metodologiaConfig', () => ({ useMetodologiaConfigStore: () => mocks.metodologia }))
vi.mock('primevue/usetoast', () => ({ useToast: () => ({ add: mocks.toastAdd }) }))
vi.mock('primevue/dropdown', () => ({
  default: {
    name: 'Dropdown',
    props: ['modelValue', 'options', 'disabled'],
    emits: ['update:modelValue', 'change'],
    template: '<select data-test="regional-picker" :disabled="disabled" @change="$emit(\'update:modelValue\', $event.target.value); $emit(\'change\', { value: $event.target.value })"><option v-for="option in options" :key="option.codigo" :value="option.codigo">{{ option.estado }}</option></select>',
  },
}))
vi.mock('primevue/inputtext', () => ({
  default: {
    props: ['modelValue', 'disabled'],
    emits: ['update:modelValue'],
    template: '<input :value="modelValue" :disabled="disabled" @input="$emit(\'update:modelValue\', $event.target.value)" />',
  },
}))
vi.mock('primevue/inputnumber', () => ({
  default: {
    props: ['modelValue', 'disabled'],
    emits: ['update:modelValue', 'blur'],
    template: '<input :value="modelValue" :disabled="disabled" @input="$emit(\'update:modelValue\', Number($event.target.value))" @blur="$emit(\'blur\')" />',
  },
}))

describe('SettingsView', () => {
  let wrapper

  beforeEach(() => {
    mocks.toastAdd.mockReset()
    mocks.notaTecnica = reactive({
      loading: false,
      selectedRegionalCodigo: 'RO',
      selectedRegional: { codigo: 'RO', estado: 'Rondônia', nome_unidade: 'CGU-RO' },
      selectedRegionalLabel: 'RO - Rondônia',
      regionais: [{ codigo: 'RO', estado: 'Rondônia', nome_unidade: 'CGU-RO' }],
      ultimoNumeroNota: '001/2025',
      ultimoNumeroProcesso: '00000.000000/2025-00',
      assinantesTecnicos: [{ nome: 'Auditor', cargo: 'Auditor Federal' }],
      ensureLoaded: vi.fn().mockResolvedValue(),
      saveRegionalCodigo: vi.fn().mockResolvedValue(),
      saveNotaTecnicaConfig: vi.fn().mockResolvedValue(),
      $patch: vi.fn((callback) => callback(mocks.notaTecnica)),
    })
    mocks.metodologia = reactive({
      loaded: true,
      loading: false,
      saving: false,
      volumeAtipicoAumentoMinimo: 500,
      volumeAtipicoLimits: { min: 0, max: 100000 },
      volumeAtipicoDefault: 500,
      auditHighValue: 10000,
      auditHighValueLimits: { min: 0, max: 1000000 },
      auditHighValueDefault: 10000,
      ensureLoaded: vi.fn().mockResolvedValue(),
      saveVolumeAtipicoAumentoMinimo: vi.fn().mockResolvedValue(),
      saveAuditHighValue: vi.fn().mockResolvedValue(),
    })
  })

  afterEach(() => {
    wrapper?.unmount()
    wrapper = null
    vi.restoreAllMocks()
  })

  it('carrega a configuração da Nota Técnica e permite salvar os dados institucionais', async () => {
    wrapper = mount(SettingsView)
    await flushPromises()

    expect(mocks.notaTecnica.ensureLoaded).toHaveBeenCalledOnce()
    expect(mocks.metodologia.ensureLoaded).toHaveBeenCalledOnce()
    expect(wrapper.text()).toContain('Regional emissora')
    expect(wrapper.text()).toContain('Assinantes técnicos')

    await wrapper.get('.cfg-btn-save').trigger('click')
    await flushPromises()

    expect(mocks.notaTecnica.saveNotaTecnicaConfig).toHaveBeenCalledWith({
      regionalCodigo: 'RO',
      numeroNota: '001/2025',
      numeroProcesso: '00000.000000/2025-00',
      assinantes: [{ nome: 'Auditor', cargo: 'Auditor Federal' }],
    })
    expect(mocks.toastAdd).toHaveBeenCalledWith(expect.objectContaining({ severity: 'success', summary: 'Salvo' }))
  })

  it('abre a seção de metodologia e salva o valor ao sair do campo', async () => {
    wrapper = mount(SettingsView)
    await flushPromises()
    const navItem = wrapper.findAll('.cfg-nav-item').find((button) => button.text().includes('Metodologia'))
    await navItem.trigger('click')

    expect(wrapper.text()).toContain('Metodologia de Alertas')
    expect(wrapper.text()).toContain('Auditoria financeira')
    await wrapper.get('.cfg-input-number').trigger('blur')
    await flushPromises()

    expect(mocks.metodologia.saveVolumeAtipicoAumentoMinimo).toHaveBeenCalledWith(500)
    expect(mocks.toastAdd).toHaveBeenCalledWith(expect.objectContaining({ severity: 'success', summary: 'Salvo' }))
  })

  it('apresenta retorno de erro quando a gravação da Nota Técnica falha', async () => {
    mocks.notaTecnica.saveNotaTecnicaConfig.mockRejectedValueOnce(new Error('Falha de persistência'))
    wrapper = mount(SettingsView)
    await flushPromises()

    await wrapper.get('.cfg-btn-save').trigger('click')
    await flushPromises()

    expect(mocks.toastAdd).toHaveBeenCalledWith(expect.objectContaining({
      severity: 'warn',
      summary: 'Nota Técnica',
      detail: 'Falha de persistência',
    }))
  })

  it('usa a mensagem padrão quando a gravação da Nota Técnica falha sem detalhe', async () => {
    mocks.notaTecnica.saveNotaTecnicaConfig.mockRejectedValueOnce({})
    wrapper = mount(SettingsView)
    await flushPromises()

    await wrapper.get('.cfg-btn-save').trigger('click')
    await flushPromises()

    expect(mocks.toastAdd).toHaveBeenCalledWith(expect.objectContaining({
      severity: 'warn',
      summary: 'Nota Técnica',
      detail: 'Não foi possível salvar.',
    }))
  })

  it('salva mudança de regional e captura falha com mensagem específica', async () => {
    mocks.notaTecnica.regionais.push({ codigo: 'AC', estado: 'Acre', nome_unidade: 'CGU-AC' })
    wrapper = mount(SettingsView)
    await flushPromises()
    await wrapper.get('[data-test="regional-picker"]').setValue('AC')
    await flushPromises()

    expect(mocks.notaTecnica.saveRegionalCodigo).toHaveBeenCalledWith('AC')
    expect(mocks.toastAdd).toHaveBeenCalledWith(expect.objectContaining({
      severity: 'success',
      detail: 'Regional emissora atualizada.',
    }))

    mocks.notaTecnica.saveRegionalCodigo.mockRejectedValueOnce(new Error('Regional indisponível'))
    await wrapper.get('[data-test="regional-picker"]').setValue('RO')
    await flushPromises()
    expect(mocks.toastAdd).toHaveBeenCalledWith(expect.objectContaining({
      severity: 'warn',
      summary: 'Regional da Nota Técnica',
      detail: 'Regional indisponível',
    }))
  })

  it('atualiza campos de assinantes e salva os dois parâmetros metodológicos', async () => {
    wrapper = mount(SettingsView)
    await flushPromises()
    await wrapper.get('input[placeholder="Ex: 001/2025"]').setValue('002/2026')
    await wrapper.get('input[placeholder="Ex: 00000.000000/2025-00"]').setValue('11111.222222/2026-33')
    const nomeInputs = wrapper.findAll('input[placeholder="Nome completo"]')
    const cargoInputs = wrapper.findAll('input[placeholder="Auditor Federal de Finanças e Controle"]')
    await nomeInputs[1].setValue('Segunda auditora')
    await cargoInputs[1].setValue('Auditora Federal')
    await nomeInputs[2].setValue('Terceira auditora')
    await cargoInputs[2].setValue('Auditora Sênior')

    expect(mocks.notaTecnica.$patch).toHaveBeenCalled()
    expect(mocks.notaTecnica.assinantesTecnicos[1]).toEqual({ nome: 'Segunda auditora', cargo: 'Auditora Federal' })
    expect(mocks.notaTecnica.assinantesTecnicos[2]).toEqual({ nome: 'Terceira auditora', cargo: 'Auditora Sênior' })

    const navItem = wrapper.findAll('.cfg-nav-item').find((button) => button.text().includes('Metodologia'))
    await navItem.trigger('click')
    const numberInputs = wrapper.findAll('.cfg-input-number')
    await numberInputs[0].setValue('700')
    await numberInputs[1].setValue('25000')
    await numberInputs[1].trigger('blur')
    await flushPromises()
    await numberInputs[0].trigger('blur')
    await flushPromises()
    expect(mocks.metodologia.saveVolumeAtipicoAumentoMinimo).toHaveBeenCalledWith(700)
    expect(mocks.metodologia.auditHighValue).toBe(25000)
    expect(mocks.metodologia.saveAuditHighValue).toHaveBeenCalledWith(25000)
    expect(mocks.toastAdd).toHaveBeenCalledWith(expect.objectContaining({
      severity: 'success',
      detail: 'Destaque financeiro atualizado.',
    }))
  })

  it('mostra o detalhe retornado pela API e as falhas de carregamento', async () => {
    mocks.metodologia.saveVolumeAtipicoAumentoMinimo.mockRejectedValueOnce({
      response: { data: { detail: 'Limite fora da faixa' } },
    })
    mocks.notaTecnica.ensureLoaded.mockRejectedValueOnce(new Error('NT indisponível'))
    mocks.metodologia.ensureLoaded.mockRejectedValueOnce({
      response: { data: { detail: 'Configuração inválida' } },
    })

    wrapper = mount(SettingsView)
    await flushPromises()
    expect(mocks.toastAdd).toHaveBeenCalledWith(expect.objectContaining({
      severity: 'warn', summary: 'Nota Técnica', detail: 'NT indisponível',
    }))
    expect(mocks.toastAdd).toHaveBeenCalledWith(expect.objectContaining({
      severity: 'warn', summary: 'Metodologia', detail: 'Configuração inválida',
    }))

    const navItem = wrapper.findAll('.cfg-nav-item').find((button) => button.text().includes('Metodologia'))
    await navItem.trigger('click')
    await wrapper.get('.cfg-input-number').trigger('blur')
    await flushPromises()
    expect(mocks.toastAdd).toHaveBeenCalledWith(expect.objectContaining({
      severity: 'warn', summary: 'Metodologia de Alertas', detail: 'Limite fora da faixa',
    }))
  })

  it('usa a mensagem da exceção quando a resposta HTTP não inclui detail', async () => {
    mocks.metodologia.saveVolumeAtipicoAumentoMinimo.mockRejectedValueOnce(
      Object.assign(new Error('Mensagem da exceção'), { response: { data: {} } }),
    )
    wrapper = mount(SettingsView)
    await flushPromises()

    const navItem = wrapper.findAll('.cfg-nav-item').find((button) => button.text().includes('Metodologia'))
    await navItem.trigger('click')
    await wrapper.get('.cfg-input-number').trigger('blur')
    await flushPromises()

    expect(mocks.toastAdd).toHaveBeenCalledWith(expect.objectContaining({
      severity: 'warn', summary: 'Metodologia de Alertas', detail: 'Mensagem da exceção',
    }))

    mocks.metodologia.saveVolumeAtipicoAumentoMinimo.mockRejectedValueOnce({ response: { data: {} } })
    await wrapper.get('.cfg-input-number').trigger('blur')
    await flushPromises()
    expect(mocks.toastAdd).toHaveBeenCalledWith(expect.objectContaining({
      severity: 'warn', summary: 'Metodologia de Alertas', detail: 'Não foi possível salvar.',
    }))
  })

  it('informa erro genérico ao salvar o limite financeiro e ao carregar configurações', async () => {
    mocks.metodologia.saveAuditHighValue.mockRejectedValueOnce({})
    mocks.notaTecnica.ensureLoaded.mockRejectedValueOnce({})
    mocks.metodologia.ensureLoaded.mockRejectedValueOnce({})
    wrapper = mount(SettingsView)
    await flushPromises()

    expect(mocks.toastAdd).toHaveBeenCalledWith(expect.objectContaining({
      severity: 'warn', summary: 'Nota Técnica', detail: 'Não foi possível carregar.',
    }))
    expect(mocks.toastAdd).toHaveBeenCalledWith(expect.objectContaining({
      severity: 'warn', summary: 'Metodologia', detail: 'Não foi possível carregar.',
    }))

    const navItem = wrapper.findAll('.cfg-nav-item').find((button) => button.text().includes('Metodologia'))
    await navItem.trigger('click')
    await wrapper.findAll('.cfg-input-number')[1].trigger('blur')
    await flushPromises()
    expect(mocks.toastAdd).toHaveBeenCalledWith(expect.objectContaining({
      severity: 'warn', summary: 'Metodologia de Alertas', detail: 'Não foi possível salvar.',
    }))
  })

  it('seleciona mensagens de erro da regional e dos dois parâmetros metodológicos', async () => {
    mocks.notaTecnica.saveRegionalCodigo.mockRejectedValueOnce({})
    mocks.metodologia.saveVolumeAtipicoAumentoMinimo.mockRejectedValueOnce(new Error('Falha no aumento mínimo'))
    mocks.metodologia.saveAuditHighValue.mockRejectedValueOnce({
      response: { data: { detail: 'Falha no destaque financeiro' } },
    })
    wrapper = mount(SettingsView)
    await flushPromises()

    await wrapper.get('[data-test="regional-picker"]').setValue('RO')
    await flushPromises()
    expect(mocks.toastAdd).toHaveBeenCalledWith(expect.objectContaining({
      summary: 'Regional da Nota Técnica', detail: 'Não foi possível salvar a regional emissora.',
    }))

    await wrapper.findAll('.cfg-nav-item').find((button) => button.text().includes('Metodologia')).trigger('click')
    const numberInputs = wrapper.findAll('.cfg-input-number')
    await numberInputs[0].trigger('blur')
    await numberInputs[1].trigger('blur')
    await flushPromises()

    expect(mocks.toastAdd).toHaveBeenCalledWith(expect.objectContaining({
      summary: 'Metodologia de Alertas', detail: 'Falha no aumento mínimo',
    }))
    expect(mocks.toastAdd).toHaveBeenCalledWith(expect.objectContaining({
      summary: 'Metodologia de Alertas', detail: 'Falha no destaque financeiro',
    }))
  })

  it.each([
    ['Nota Técnica', true, false],
    ['Metodologia', false, true],
  ])('exibe o estado de sincronização quando %s ainda está carregando', async (_label, notaTecnicaLoading, metodologiaLoading) => {
    mocks.notaTecnica.loading = notaTecnicaLoading
    mocks.metodologia.loading = metodologiaLoading
    wrapper = mount(SettingsView)
    await flushPromises()

    expect(wrapper.get('.cfg-sync-badge').classes()).toContain('is-syncing')
    expect(wrapper.get('.cfg-sync-badge').text()).toContain('Carregando')
  })
})
