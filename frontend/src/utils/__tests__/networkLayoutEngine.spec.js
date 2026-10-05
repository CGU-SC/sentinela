import { describe, expect, it } from 'vitest'

import {
  computeAnchoredFanPosition,
  computeRadialNetworkLayout,
} from '@/utils/network/networkLayoutEngine'

describe('networkLayoutEngine', () => {
  it('retorna mapa vazio quando faltam nós, dimensões ou nó alvo', () => {
    expect(computeRadialNetworkLayout({ nodes: [], edges: [], width: 800, height: 600 }).size).toBe(0)
    expect(computeRadialNetworkLayout({ nodes: [{ id: 'a', type: 'PJ' }], edges: [], width: 0, height: 600 }).size).toBe(0)
    expect(computeRadialNetworkLayout({ nodes: [{ id: 'a', type: 'PJ' }], edges: [], width: 800, height: 600 }).size).toBe(0)
  })

  it('posiciona alvo no centro, parceiros na órbita interna e relacionados conectados ao parceiro', () => {
    const nodes = [
      { id: 'root', type: 'PJ_ALVO', label: 'Alvo' },
      { id: 'partner-b', type: 'PF', label: 'Bruno' },
      { id: 'partner-a', type: 'PF', label: 'Ana' },
      { id: 'company-b', type: 'PJ', label: 'Empresa B' },
      { id: 'company-a', type: 'PJ', label: 'Empresa A' },
      { id: 'unconnected', type: 'PJ', label: 'Empresa Z' },
    ]
    const edges = [
      { source: 'root', target: 'partner-b' },
      { source: 'root', target: 'partner-a' },
      { source: 'partner-a', target: 'company-a' },
      { source: 'partner-a', target: 'company-b' },
    ]
    const positions = computeRadialNetworkLayout({ nodes, edges, width: 1000, height: 800 })

    expect(positions.get('root')).toEqual({ x: 500, y: 432 })
    expect(positions.has('partner-a')).toBe(true)
    expect(positions.has('partner-b')).toBe(true)
    expect(positions.get('company-a')).not.toEqual(positions.get('company-b'))
    expect(positions.get('unconnected')).toBeDefined()
    expect(positions.size).toBe(nodes.length)
  })

  it('ordena geometrias determinísticas para grupos isolados e nodos com múltiplas conexões', () => {
    const positions = computeRadialNetworkLayout({
      nodes: [
        { id: 'root', type: 'PJ_ALVO', fullLabel: 'Alvo' },
        { id: 'p1', type: 'PF', fullLabel: 'Ana' },
        { id: 'p2', type: 'PF', fullLabel: 'Zélia' },
        { id: 'c1', type: 'PJ', fullLabel: 'A' },
        { id: 'c2', type: 'PJ', fullLabel: 'B' },
        { id: 'c3', type: 'PJ', fullLabel: 'C' },
      ],
      edges: [
        { source: 'root', target: 'p1' },
        { source: 'root', target: 'p2' },
        { source: 'p1', target: 'c1' },
        { source: 'p1', target: 'c3' },
        { source: 'p2', target: 'c3' },
      ],
      width: 1200,
      height: 900,
    })
    for (const position of positions.values()) {
      expect(Number.isFinite(position.x)).toBe(true)
      expect(Number.isFinite(position.y)).toBe(true)
    }
  })

  it('limita e distribui posições da ventoinha ancorada, inclusive contagens inválidas', () => {
    const anchor = { x: 100, y: 200 }
    const single = computeAnchoredFanPosition({ anchor, anchorAngle: 0, index: 0, count: 1 })
    expect(single).toEqual({ x: 360, y: 200 })

    const first = computeAnchoredFanPosition({ anchor, anchorAngle: 0, index: -1, count: 3 })
    const last = computeAnchoredFanPosition({ anchor, anchorAngle: 0, index: 9, count: 3 })
    expect(first).not.toEqual(last)
    expect(computeAnchoredFanPosition({ anchor, anchorAngle: 0, index: 0, count: 0 })).toEqual(single)
    const constrained = computeAnchoredFanPosition({
      anchor,
      anchorAngle: Math.PI / 2,
      index: null,
      count: 3,
      maxSpread: 0,
      minSpread: 0,
    })
    expect(Number.isFinite(constrained.x) && Number.isFinite(constrained.y)).toBe(true)
  })

  it('posiciona alvos isolados e grafos densos com conexões a parceiros', () => {
    const isolated = computeRadialNetworkLayout({
      nodes: [{ id: 'root', type: 'PJ_ALVO' }, { id: 'sem-rótulo' }],
      edges: [],
      width: 800,
      height: 600,
    })
    expect(isolated.size).toBe(2)

    const nodes = [{ id: 'root', type: 'PJ_ALVO' }]
    const edges = []
    for (let index = 0; index < 30; index += 1) {
      const partner = { id: `p${index}`, type: 'PF', label: `Pessoa ${index}` }
      const company = { id: `c${index}`, type: 'PJ' }
      nodes.push(partner, company)
      edges.push({ source: 'root', target: partner.id }, { source: partner.id, target: company.id })
    }
    const positions = computeRadialNetworkLayout({ nodes, edges, width: 1400, height: 900 })
    expect(positions.size).toBe(nodes.length)
    expect([...positions.values()].every(({ x, y }) => Number.isFinite(x) && Number.isFinite(y))).toBe(true)
  })

  it('separa grupos sem parceiro quando milhares de nós colidem no mesmo ângulo arredondado', () => {
    const nodes = [{ id: 'root', type: 'PJ_ALVO' }]
    for (let index = 0; index < 700; index += 1) {
      nodes.push({ id: `isolated-${index}`, type: 'PJ' })
    }

    const positions = computeRadialNetworkLayout({ nodes, edges: [], width: 1600, height: 1200 })

    expect(positions.size).toBe(nodes.length)
    expect([...positions.values()].every(({ x, y }) => Number.isFinite(x) && Number.isFinite(y))).toBe(true)
  })

  it('ordena parceiros conectados sem rótulo usando seus identificadores', () => {
    const positions = computeRadialNetworkLayout({
      nodes: [
        { id: 'root', type: 'PJ_ALVO' },
        { id: 'partner-b', type: 'PF' },
        { id: 'partner-a', type: 'PF' },
        { id: 'company', type: 'PJ' },
      ],
      edges: [
        { source: 'root', target: 'partner-b' },
        { source: 'root', target: 'partner-a' },
        { source: 'partner-a', target: 'company' },
        { source: 'partner-b', target: 'company' },
      ],
      width: 1000,
      height: 800,
    })

    expect(positions.has('company')).toBe(true)
    expect([...positions.values()].every(({ x, y }) => Number.isFinite(x) && Number.isFinite(y))).toBe(true)
  })
})
