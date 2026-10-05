import { describe, expect, it } from 'vitest'

import { highlightSegments } from '@/utils/textHighlight'

describe('highlightSegments', () => {
  it('realça trecho sem diferenciar caixa ou acentuação', () => {
    expect(highlightSegments('João da Silva', 'JOAO')).toEqual([
      { text: 'João', matched: true },
      { text: ' da Silva', matched: false },
    ])
  })

  it('normaliza espaços da busca sem alterar o texto apresentado', () => {
    expect(highlightSegments('Alta   Floresta', 'alta floresta')).toEqual([
      { text: 'Alta   Floresta', matched: true },
    ])
  })

  it('devolve o texto integral sem marcação quando a busca está vazia ou não encontra trecho', () => {
    expect(highlightSegments('Farmácia Central', '   ')).toEqual([
      { text: 'Farmácia Central', matched: false },
    ])
    expect(highlightSegments('Farmácia Central', 'hospital')).toEqual([
      { text: 'Farmácia Central', matched: false },
    ])
  })

  it('realça ocorrências no início e no fim sem segmentos vazios', () => {
    expect(highlightSegments('CNPJ 12345678', 'cnpj')).toEqual([
      { text: 'CNPJ', matched: true },
      { text: ' 12345678', matched: false },
    ])
    expect(highlightSegments('CNPJ 12345678', '5678')).toEqual([
      { text: 'CNPJ 1234', matched: false },
      { text: '5678', matched: true },
    ])
  })

  it('ignora marcas combinantes soltas preservando os índices do texto original', () => {
    expect(highlightSegments('A\u0301B', 'b')).toEqual([
      { text: 'A\u0301', matched: false },
      { text: 'B', matched: true },
    ])
  })
})
