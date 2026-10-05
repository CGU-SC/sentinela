import { describe, expect, it } from 'vitest'

import { buildNetworkStylesheet } from '@/utils/network/networkStylesheet'

describe('buildNetworkStylesheet', () => {
  it('monta seletores de risco, entidade, vínculo e destaque para tema escuro', () => {
    const stylesheet = buildNetworkStylesheet()
    const rule = (selector) => stylesheet.filter((entry) => entry.selector === selector).at(-1)

    expect(rule('node[type="PJ_ALVO"]').style).toMatchObject({ 'border-width': 5, 'z-index': 20 })
    expect(rule('node[type="PJ_FARMACIA_POPULAR"]').style).toMatchObject({
      'border-color': 'data(risk_border_color)',
      'text-wrap': 'wrap',
    })
    expect(rule('node.cadunico-pf').style['border-style']).toBe('double')
    expect(rule('node.esocial-pf').style['border-color']).toBe('#22c55e')
    expect(rule('node.seguro-defeso-pf').style['underlay-opacity']).toBe(0.62)
    expect(rule('node.deceased-pf').style['background-image']).toContain('data:image/svg+xml;utf8,')
    expect(rule('edge[type="representante"]').style['line-style']).toBe('dotted')
    expect(rule('node.inactive-company').style.opacity).toBe(0.35)
    expect(rule('node.par-company').style['z-index']).toBe(13)
    expect(rule('.faded').style.opacity).toBe(0.08)
    expect(rule('node.deceased-pf.highlighted').style).toMatchObject({ opacity: 0.82, 'border-width': 4 })
  })

  it('usa as cores apropriadas no tema claro e define a folha inteira como regras Cytoscape', () => {
    const stylesheet = buildNetworkStylesheet({ isDark: false })
    const baseNode = stylesheet.find((entry) => entry.selector === 'node[type="PF"]')
    const edge = stylesheet.find((entry) => entry.selector === 'edge')

    expect(baseNode.style.color).toBe('#1e293b')
    expect(baseNode.style['text-outline-color']).toBe('#f8fafc')
    expect(edge.style.color).toBe('#475569')
    expect(edge.style['text-outline-color']).toBe('#f8fafc')
    expect(stylesheet.every((entry) => typeof entry.selector === 'string' && entry.style)).toBe(true)
    expect(stylesheet.some((entry) => entry.selector === 'edge[!is_ativo]')).toBe(true)
  })
})
