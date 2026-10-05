import { describe, expect, it } from 'vitest'

import { destaqueBuscaMedico, parseBuscaCrm } from '@/utils/crmBusca'

describe('parseBuscaCrm', () => {
  it.each([
    ['800', { numero: '800', uf: null }],
    ['CRM 00800', { numero: '00800', uf: null }],
    ['800/SC', { numero: '800', uf: 'SC' }],
    ['800-SC', { numero: '800', uf: 'SC' }],
    ['CRM-SC 800', { numero: '800', uf: 'SC' }],
    ['sc/800', { numero: '800', uf: 'SC' }],
  ])('interpreta a forma %s', (query, expected) => {
    expect(parseBuscaCrm(query)).toEqual(expected)
  })

  it.each(['', 'Dra. Maria', '800/XX', 'CRM SC', '800/SS'])('retorna null para busca que não é CRM válida: %s', (query) => {
    expect(parseBuscaCrm(query)).toBeNull()
  })

  it('trata entradas nulas e normaliza espaços externos sem inventar uma UF', () => {
    expect(parseBuscaCrm(null)).toBeNull()
    expect(parseBuscaCrm('  800   ')).toEqual({ numero: '800', uf: null })
    expect(destaqueBuscaMedico('800')).toEqual({ nome: '', crm: '800' })
  })
})

describe('destaqueBuscaMedico', () => {
  it('separa o CRM normalizado do nome quando a busca contém número e UF', () => {
    expect(destaqueBuscaMedico('CRM-SC 00800')).toEqual({ nome: '', crm: '00800/SC' })
  })

  it('mantém a busca original nos dois campos quando ela é textual', () => {
    expect(destaqueBuscaMedico('Dra. Maria')).toEqual({ nome: 'Dra. Maria', crm: 'Dra. Maria' })
  })
})
