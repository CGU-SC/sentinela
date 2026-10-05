import { describe, expect, it } from 'vitest'

import { createRespostaCache } from '@/utils/respostaCache'

describe('createRespostaCache', () => {
  it.each([0, -1, 1.5, '2', null])('exige capacidade inteira positiva: %s', (capacity) => {
    expect(() => createRespostaCache(capacity)).toThrow(`Tamanho de cache inválido: ${capacity}`)
  })

  it('retorna undefined para ausentes e mantém o acesso mais recente no topo do LRU', () => {
    const cache = createRespostaCache(2)
    expect(cache.get('ausente')).toBeUndefined()
    cache.set('a', { value: 1 })
    cache.set('b', { value: 2 })
    expect(cache.get('a')).toEqual({ value: 1 })
    cache.set('c', { value: 3 })
    expect(cache.get('b')).toBeUndefined()
    expect(cache.get('a')).toEqual({ value: 1 })
    expect(cache.get('c')).toEqual({ value: 3 })
  })

  it('substitui uma chave existente sem criar entrada duplicada nem expulsar outra chave', () => {
    const cache = createRespostaCache(2)
    cache.set('a', 1)
    cache.set('b', 2)
    cache.set('a', 3)
    cache.set('c', 4)
    expect(cache.get('a')).toBe(3)
    expect(cache.get('b')).toBeUndefined()
    expect(cache.get('c')).toBe(4)
  })
})
