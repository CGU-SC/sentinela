import { describe, expect, it } from 'vitest'

import {
  TIPO_EVIDENCIA,
  TIPO_EVIDENCIA_OPCOES,
  alertasDaJanela,
  dataHoraCurta,
  quandoEvidencia,
  resumoEvidencia,
  tipoEvidencia,
} from '@/utils/evidencias'

describe('apresentação de evidências', () => {
  it('expõe os tipos conhecidos e rejeita tipo desconhecido', () => {
    expect(TIPO_EVIDENCIA.dia).toEqual({ label: 'Dia', icon: 'pi-calendar' })
    expect(TIPO_EVIDENCIA_OPCOES.map(({ value }) => value)).toEqual([null, 'dia', 'hora', 'autorizacao'])
    expect(tipoEvidencia('hora')).toEqual({ label: 'Hora', icon: 'pi-clock' })
    expect(() => tipoEvidencia('minuto')).toThrow('Tipo de evidência desconhecido: minuto')
  })

  it('formata janelas diárias, horárias e autorizações', () => {
    expect(quandoEvidencia({ tipo: 'dia', dt_janela: '2024-02-09' })).toBe('09/02/2024')
    expect(quandoEvidencia({ tipo: 'hora', dt_janela: '2024-02-09', hora: 3 })).toBe('09/02/2024 · 03h')
    expect(quandoEvidencia({ tipo: 'autorizacao', dt_janela: '2024-02-09', hora: 4 }))
      .toBe('09/02/2024 · 04h')
    expect(quandoEvidencia({ tipo: 'autorizacao', dt_janela: '2024-02-09', hora: 4, snapshot: { horario: '04:15:30' } }))
      .toBe('09/02/2024 · 04:15:30')
  })

  it('resume autorizações, dias sem alertas e janelas com valores presentes', () => {
    expect(resumoEvidencia({ tipo: 'autorizacao', num_autorizacao: 'A1', snapshot: {
      crm: '123/SC', medico: 'Ana', valor: 12.5, alertas: ['Sequência', 'Volume'],
    } })).toBe('Nº A1 · CRM 123/SC · Ana · R$\u00a012,50 · Sequência, Volume')
    expect(resumoEvidencia({ tipo: 'autorizacao', num_autorizacao: 'A2', snapshot: {} })).toBe('Nº A2')
    expect(resumoEvidencia({ tipo: 'dia', snapshot: { qtd: 1234, alertas: ['Volume Atípico'] } }))
      .toBe('1.234 autorizações · Volume Atípico')
    expect(resumoEvidencia({ tipo: 'hora', snapshot: { qtd: 1, alertas: [] } })).toBe('1 autorização')
    expect(resumoEvidencia({ tipo: 'dia', snapshot: { qtd: null } })).toBe('—')
    expect(resumoEvidencia({ tipo: 'dia' })).toBe('—')
  })

  it('lista alertas ativos e normaliza datas curtas', () => {
    expect(alertasDaJanela(null)).toEqual([])
    expect(alertasDaJanela({
      is_volume_horario_anomalo: 1,
      is_crm_unico: 1,
      is_crm_multiplo: 1,
    })).toEqual(['Volume Atípico', 'Sequência · Único CRM', 'Sequência · Múltiplos CRMs'])
    expect(alertasDaJanela({ is_volume_horario_anomalo: true, is_crm_unico: 0, is_crm_multiplo: 0 })).toEqual([])
    expect(dataHoraCurta(null)).toBe('—')
    expect(dataHoraCurta('data inválida')).toBe('—')
    expect(dataHoraCurta('2024-02-09T13:30:00')).toBe('09/02/2024')
  })
})
