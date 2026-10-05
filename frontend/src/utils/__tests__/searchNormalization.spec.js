import { describe, expect, it } from 'vitest'

import { normalizeSearchText } from '@/utils/searchNormalization'

describe('normalizeSearchText', () => {
  it('remove diacríticos, ignora caixa e normaliza espaços', () => {
    expect(normalizeSearchText('  JoÃO   da  Silva  ')).toBe('joao da silva')
  })

  it('normaliza caracteres compostos e preserva pontuação significativa', () => {
    expect(normalizeSearchText('AÇÃO — CNPJ 12.345')).toBe('acao — cnpj 12.345')
  })

  it('retorna texto vazio quando a entrada contém apenas espaços', () => {
    expect(normalizeSearchText(' \t\n ')).toBe('')
  })
})
