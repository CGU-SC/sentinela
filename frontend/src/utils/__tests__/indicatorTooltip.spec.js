import { describe, expect, it } from 'vitest'

import { INDICATOR_TOOLTIP_COPY } from '@/config/indicatorTooltipConfig'
import { createIndicatorHtmlTooltip, indicatorTooltip } from '@/utils/indicatorTooltip'

describe('tooltips HTML dos indicadores', () => {
  it('exige o conteúdo estrutural e escapa HTML em todos os campos renderizados', () => {
    expect(() => createIndicatorHtmlTooltip(null)).toThrow('Texto de tooltip de indicador incompleto.')
    expect(() => createIndicatorHtmlTooltip({ title: 'x', intro: 'y', sections: {} }))
      .toThrow('Texto de tooltip de indicador incompleto.')

    const tooltip = createIndicatorHtmlTooltip({
      title: '<Título & "risco">',
      intro: "D'água <segura>",
      sections: [
        { label: 'Itens &', items: ['<um>', 'dois & três'] },
        { label: 'Equação', formula: 'a < b && c > d' },
        { label: 'Valor', value: '"alto"' },
        { label: 'Texto', text: "linha d'água" },
      ],
    })

    expect(tooltip).toMatchObject({ escape: false, class: 'indicator-info-tooltip', showDelay: 120, hideDelay: 80 })
    expect(tooltip.value).toContain('&lt;Título &amp; &quot;risco&quot;&gt;')
    expect(tooltip.value).toContain('D&#39;água &lt;segura&gt;')
    expect(tooltip.value).toContain('&lt;um&gt;')
    expect(tooltip.value).toContain('a &lt; b &amp;&amp; c &gt; d')
    expect(tooltip.value).toContain('&quot;alto&quot;')
    expect(tooltip.value).toContain('linha d&#39;água')
  })

  it('renderiza uma cópia conhecida e informa a chave ausente', () => {
    const key = Object.keys(INDICATOR_TOOLTIP_COPY)[0]
    expect(indicatorTooltip({ key }).value).toContain(INDICATOR_TOOLTIP_COPY[key].title)
    expect(() => indicatorTooltip({ key: 'inexistente' }))
      .toThrow('Texto de tooltip de indicador não encontrado: inexistente')
    expect(() => indicatorTooltip(null)).toThrow('Texto de tooltip de indicador não encontrado: undefined')
  })
})
