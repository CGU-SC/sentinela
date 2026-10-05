import { afterEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { computed } from 'vue'
import { createPinia, disposePinia, setActivePinia } from 'pinia'

import AnalysisSidebar from '@/views/components/analises/AnalysisSidebar.vue'
import { CRM_SEQUENCIA_TIPO_PADRAO, CRM_UF_ATALHOS, CRM_UFS } from '@/config/crmFiltrosMedico'
import { useCrmFiltrosMedicoStore } from '@/stores/crmFiltrosMedico'

vi.mock('primevue/button', () => ({
  default: {
    props: ['label'],
    emits: ['click'],
    template: '<button data-test="clear-all" type="button" @click="$emit(\'click\')">{{ label }}</button>',
  },
}))

vi.mock('@/views/components/common/OptionPicker.vue', () => ({
  default: {
    name: 'OptionPicker',
    props: ['valor', 'opcoes', 'rotuloAcessivel'],
    emits: ['select'],
    setup(props) {
      const selection = computed(() => {
        if (props.rotuloAcessivel.includes('Situação')) return 'localizado'
        if (props.rotuloAcessivel.includes('Severidade')) return 2
        return 'multiplo'
      })
      return { selection }
    },
    template: '<button :data-test="`option-${rotuloAcessivel}`" @click="$emit(\'select\', selection)">{{ valor }}</button>',
  },
}))

vi.mock('@/views/components/common/MultiOptionPicker.vue', () => ({
  default: {
    name: 'MultiOptionPicker',
    props: ['valor', 'opcoes', 'atalhos', 'rotulo', 'nomePlural'],
    emits: ['select'],
    template: '<button data-test="select-ufs" @click="$emit(\'select\', [\'RJ\', \'SP\'])">{{ rotulo }}</button>',
  },
}))

vi.mock('@/views/components/analises/CrmFiltroFaixa.vue', () => ({
  default: {
    props: ['tipo', 'campo'],
    template: '<span class="range-filter" :data-type="tipo" :data-field="campo" />',
  },
}))

describe('AnalysisSidebar', () => {
  let pinia
  let store

  function montar(props = {}, slots = {}) {
    pinia = createPinia()
    setActivePinia(pinia)
    store = useCrmFiltrosMedicoStore()
    return mount(AnalysisSidebar, {
      props: { searchQuery: '', ...props },
      slots,
      global: {
        plugins: [pinia],
        directives: { tooltip() {} },
        stubs: {
          'router-link': { props: ['to'], template: '<a :href="to"><slot /></a>' },
        },
      },
    })
  }

  afterEach(() => {
    if (pinia) disposePinia(pinia)
    pinia = null
    vi.restoreAllMocks()
  })

  it('renderiza navegação, grupos, faixas e ações opcionais de cabeçalho', () => {
    const wrapper = montar({}, { 'header-acoes': '<button>Fechar painel</button>' })

    expect(wrapper.get('a[href="/analises"]').attributes('aria-current')).toBe('page')
    expect(wrapper.text()).toContain('Filtros dos médicos')
    expect(wrapper.text()).toContain('Cadastro CFM')
    expect(wrapper.text()).toContain('Produção e atuação')
    expect(wrapper.text()).toContain('Autorizações em sequência')
    expect(wrapper.findAll('.range-filter').length).toBeGreaterThan(0)
    expect(wrapper.find('.selector-header-acoes').text()).toContain('Fechar painel')
    expect(wrapper.get('[data-test="clear-all"]').text()).toBe('Limpar Filtros')
  })

  it('emite a busca, limpa o texto e inclui a busca na contagem de filtros', async () => {
    const wrapper = montar({ searchQuery: '  Dra. Ana  ' })

    expect(wrapper.find('.filtro-busca-bloco').classes()).toContain('is-ativo')
    expect(wrapper.get('[data-test="clear-all"]').text()).toBe('Limpar Filtros (1)')
    expect(wrapper.get('[aria-label="Limpar busca de médico"]').element.disabled).toBe(false)

    await wrapper.get('[role="searchbox"]').setValue('CRM 123/DF')
    expect(wrapper.emitted('search').at(-1)).toEqual(['CRM 123/DF'])
    await wrapper.get('[aria-label="Limpar busca de médico"]').trigger('click')
    expect(wrapper.emitted('search').at(-1)).toEqual([''])

    wrapper.unmount()
    disposePinia(pinia)
    const disabled = montar({ searchDisabled: true })
    expect(disabled.get('[role="searchbox"]').element.disabled).toBe(true)
    expect(disabled.find('.filtro-busca').classes()).toContain('is-disabled')
  })

  it('aplica situação, UFs e filtros de sequência pelos controles', async () => {
    const wrapper = montar()

    await wrapper.get('[data-test="option-Situação no CFM"]').trigger('click')
    await wrapper.get('[data-test="select-ufs"]').trigger('click')
    await wrapper.get('[data-test="option-Severidade mínima das autorizações em sequência"]').trigger('click')
    await wrapper.get('[data-test="option-Tipo das autorizações em sequência"]').trigger('click')

    expect(store.situacaoCfm).toBe('localizado')
    expect(store.ufsCrm).toEqual(['RJ', 'SP'])
    expect(store.sequenciaSeveridadeMin).toBe(2)
    expect(store.sequenciaTipo).toBe('multiplo')
    expect(wrapper.get('[data-test="select-ufs"]').text()).toBe('RJ, SP')
    expect(wrapper.get('[data-test="clear-all"]').text()).toBe('Limpar Filtros (3)')
    expect(wrapper.find('[aria-label="Limpar o filtro situação no CFM"]').exists()).toBe(true)
    expect(wrapper.find('[aria-label="Limpar o filtro UF do CRM"]').exists()).toBe(true)
    expect(wrapper.find('[aria-label="Limpar o filtro autorizações em sequência"]').exists()).toBe(true)

    await wrapper.get('[aria-label="Limpar o filtro situação no CFM"]').trigger('click')
    await wrapper.get('[aria-label="Limpar o filtro UF do CRM"]').trigger('click')
    await wrapper.get('[aria-label="Limpar o filtro autorizações em sequência"]').trigger('click')
    expect(store.situacaoCfm).toBeNull()
    expect(store.ufsCrm).toEqual([])
    expect(store.sequenciaSeveridadeMin).toBeNull()
    expect(store.sequenciaTipo).toBe(CRM_SEQUENCIA_TIPO_PADRAO)
  })

  it('resume seleções de UF por atalho, lista curta, exceções e contagem', async () => {
    const wrapper = montar()
    const ufPicker = () => wrapper.get('[data-test="select-ufs"]').text()
    const atalho = CRM_UF_ATALHOS.find((item) => item.selecao.length > 0)

    store.setUfsCrm(atalho.selecao)
    await wrapper.vm.$nextTick()
    expect(ufPicker()).toBe(atalho.label)

    store.setUfsCrm(['SP', 'RJ', 'MG'])
    await wrapper.vm.$nextTick()
    expect(ufPicker()).toBe('MG, RJ, SP')

    const excluidas = CRM_UFS.slice(0, 2)
    store.setUfsCrm(CRM_UFS.filter((uf) => !excluidas.includes(uf)))
    await wrapper.vm.$nextTick()
    expect(ufPicker()).toBe(`Todas exceto ${excluidas.join(', ')}`)

    store.setUfsCrm(CRM_UFS.slice(0, 4))
    await wrapper.vm.$nextTick()
    expect(ufPicker()).toBe('4 UFs')
  })

  it('limpa todos os filtros de cadastro, sequência e busca em conjunto', async () => {
    const wrapper = montar({ searchQuery: 'Dra. Ana' })
    store.setSituacaoCfm('localizado')
    store.setUfsCrm(['SP'])
    store.setSequenciaSeveridadeMin(2)
    store.setSequenciaTipo('multiplo')

    await wrapper.get('[data-test="clear-all"]').trigger('click')

    expect(store.situacaoCfm).toBeNull()
    expect(store.ufsCrm).toEqual([])
    expect(store.sequenciaSeveridadeMin).toBeNull()
    expect(store.sequenciaTipo).toBe(CRM_SEQUENCIA_TIPO_PADRAO)
    expect(wrapper.emitted('search')).toEqual([['']])
    expect(wrapper.get('[data-test="clear-all"]').text()).toBe('Limpar Filtros (1)')
  })
})
