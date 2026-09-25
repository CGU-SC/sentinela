import { INDICATOR_TOOLTIP_COPY } from '@/config/indicatorTooltipConfig';

function escapeTooltipHtml(value) {
  return String(value).replace(/[&<>"']/g, (character) => ({
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    '"': '&quot;',
    "'": '&#39;',
  })[character]);
}

function renderTooltipSection(section) {
  const content = section.items
    ? `<ul>${section.items.map((item) => `<li>${escapeTooltipHtml(item)}</li>`).join('')}</ul>`
    : section.formula
      ? `<div class="indicator-tooltip-formula"><span>Fórmula</span><strong>${escapeTooltipHtml(section.formula)}</strong></div>`
      : section.value != null
        ? `<div class="indicator-tooltip-value"><strong>${escapeTooltipHtml(section.value)}</strong></div>`
        : `<p>${escapeTooltipHtml(section.text)}</p>`;

  return `
    <section class="indicator-tooltip-section">
      <strong class="indicator-tooltip-section-label">${escapeTooltipHtml(section.label)}</strong>
      ${content}
    </section>
  `;
}

export function createIndicatorHtmlTooltip(copy) {
  if (!copy?.title || !copy?.intro || !Array.isArray(copy.sections)) {
    throw new Error('Texto de tooltip de indicador incompleto.');
  }

  return {
    value: `
      <div class="indicator-tooltip-content">
        <div class="indicator-tooltip-heading">
          <i class="pi pi-info-circle" aria-hidden="true"></i>
          <span>${escapeTooltipHtml(copy.title)}</span>
        </div>
        <p class="indicator-tooltip-intro">${escapeTooltipHtml(copy.intro)}</p>
        <div class="indicator-tooltip-sections">
          ${copy.sections.map(renderTooltipSection).join('')}
        </div>
      </div>
    `,
    escape: false,
    class: 'indicator-info-tooltip',
    showDelay: 120,
    hideDelay: 80,
  };
}

export function indicatorTooltip(indicator) {
  const copy = INDICATOR_TOOLTIP_COPY[indicator?.key];
  if (!copy) throw new Error(`Texto de tooltip de indicador não encontrado: ${indicator?.key}`);
  return createIndicatorHtmlTooltip(copy);
}
