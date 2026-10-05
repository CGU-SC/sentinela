import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { reactive, ref } from 'vue'

import { usePeriodoAnalise } from '@/composables/usePeriodoAnalise'
import { AVAILABLE_MONTHS } from '@/config/constants'

const mocks = vi.hoisted(() => ({
  filterStore: null,
  timeSliderValue: null,
  applySliderPeriod: vi.fn(),
  resetYears: vi.fn(),
}))

vi.mock('@/stores/filters', () => ({ useFilterStore: () => mocks.filterStore }))
vi.mock('@/composables/useSliderPeriodLogic', async () => {
  const { AVAILABLE_MONTHS: availableMonths } = await import('@/config/constants')
  return { useSliderPeriodLogic: () => ({
    availableMonths,
    timeSliderValue: mocks.timeSliderValue,
    applySliderPeriod: mocks.applySliderPeriod,
    resetYears: mocks.resetYears,
  }) }
})

describe('usePeriodoAnalise', () => {
  beforeEach(() => {
    mocks.timeSliderValue = ref([0, AVAILABLE_MONTHS.length - 1])
    mocks.filterStore = reactive({ resetAnimationPreview: vi.fn() })
    mocks.applySliderPeriod.mockReset()
    mocks.resetYears.mockReset()
  })

  afterEach(() => vi.restoreAllMocks())

  it('expõe limites, atalhos de ano e o rótulo do período completo', () => {
    const period = usePeriodoAnalise()

    expect(period.PERIODO_MIN).toBe(201507)
    expect(period.PERIODO_MAX).toBe(202412)
    expect(period.periodoSelecionado.value).toEqual({ inicio: 201507, fim: 202412 })
    expect(period.periodoAtalhoAtivo.value).toBe('completo')
    expect(period.periodoRotulo.value).toBe('07/2015 a 12/2024')
    expect(period.periodoAtalhos[0]).toEqual({
      value: 'completo',
      label: 'Período completo',
      faixa: { inicio: 201507, fim: 202412 },
    })
    expect(period.periodoAtalhos.find(({ value }) => value === '2020-2024').faixa)
      .toEqual({ inicio: 202001, fim: 202412 })
    expect(period.periodoAtalhos.find(({ value }) => value === 'ano-2020').faixa)
      .toEqual({ inicio: 202001, fim: 202012 })
    expect(period.periodoAtalhos.at(-1)).toEqual({
      value: 'personalizado',
      label: 'Período personalizado',
      grade: true,
    })
  })

  it('aplica um período válido, reseta a prévia de animação e identifica atalhos', () => {
    const period = usePeriodoAnalise()
    const start = AVAILABLE_MONTHS.findIndex(({ date }) => date.getFullYear() === 2020 && date.getMonth() === 0)
    const end = AVAILABLE_MONTHS.findIndex(({ date }) => date.getFullYear() === 2020 && date.getMonth() === 11)

    period.aplicarPeriodo({ inicio: 202001, fim: 202012 })
    expect(mocks.filterStore.resetAnimationPreview).toHaveBeenCalledOnce()
    expect(period.timeSliderValue.value).toEqual([start, end])
    expect(mocks.applySliderPeriod).toHaveBeenCalledWith([start, end])
    expect(period.periodoAtalhoAtivo.value).toBe('ano-2020')
    expect(period.periodoRotulo.value).toBe('01/2020 a 12/2020')
  })

  it('aplica atalhos predefinidos e delega a restauração do intervalo completo', () => {
    const period = usePeriodoAnalise()
    period.aplicarAtalhoPeriodo('2020-2024')
    expect(mocks.filterStore.resetAnimationPreview).toHaveBeenCalledOnce()
    expect(period.periodoSelecionado.value).toEqual({ inicio: 202001, fim: 202412 })
    expect(period.periodoAtalhoAtivo.value).toBe('2020-2024')

    period.aplicarAtalhoPeriodo('completo')
    expect(period.periodoAtalhoAtivo.value).toBe('completo')
    period.resetYears()
    expect(mocks.resetYears).toHaveBeenCalledOnce()
  })

  it('marca intervalos parciais como personalizados e rejeita competência ou atalho inválido', () => {
    const period = usePeriodoAnalise()
    const first = AVAILABLE_MONTHS.find(({ date }) => date.getFullYear() === 2021 && date.getMonth() === 2)
    const last = AVAILABLE_MONTHS.find(({ date }) => date.getFullYear() === 2021 && date.getMonth() === 6)

    period.aplicarPeriodo({ inicio: 202103, fim: 202107 })
    expect(period.periodoAtalhoAtivo.value).toBe('personalizado')
    expect(period.periodoRotulo.value).toBe('03/2021 a 07/2021')
    expect(period.timeSliderValue.value[0]).toBe(AVAILABLE_MONTHS.indexOf(first))
    expect(period.timeSliderValue.value[1]).toBe(AVAILABLE_MONTHS.indexOf(last))
    expect(() => period.aplicarPeriodo({ inicio: 202001, fim: 203001 }))
      .toThrow('Competência 203001 fora do período de auditoria.')
    expect(() => period.aplicarAtalhoPeriodo('personalizado'))
      .toThrow('Atalho de período sem intervalo: personalizado')
    expect(() => period.aplicarAtalhoPeriodo('desconhecido'))
      .toThrow('Atalho de período sem intervalo: desconhecido')
  })
})
