/**
 * Tooltips informativos da página inicial.
 *
 * O conteúdo é entregue ao PrimeVue como HTML controlado. Qualquer valor
 * dinâmico é escapado antes de ser inserido no markup.
 */

const HOME_TOOLTIP_COPY = Object.freeze({
  updateStatus: {
    title: "Atualização do sistema",
    body: "Informa o resultado da verificação de versão do Sentinela.",
    icon: "pi-sync",
    detailLabel: "Detalhe",
  },
  refreshUpdates: {
    title: "Verificar atualizações",
    body: "Consulta novamente se existe uma versão mais recente do Sentinela.",
    icon: "pi-refresh",
  },
  riskDistribution: {
    title: "Estabelecimentos por faixa de não comprovação",
    body: "Distribui os estabelecimentos conforme o percentual do valor autorizado sem comprovação no período analisado.",
    icon: "pi-chart-bar",
    sections: [
      {
        label: "Como ler",
        text: "As barras representam a quantidade de estabelecimentos em cada faixa. A série sobreposta mostra o valor financeiro sem comprovação correspondente.",
      },
    ],
  },
});

function escapeTooltipHtml(value) {
  return String(value).replace(/[&<>"']/g, (character) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
  })[character]);
}

function renderSection(section) {
  if (!section?.label || !section?.text) {
    throw new Error("Seção de tooltip da página inicial incompleta.");
  }

  return `
    <section class="home-tooltip-section">
      <strong class="home-tooltip-section-label">${escapeTooltipHtml(section.label)}</strong>
      <p>${escapeTooltipHtml(section.text)}</p>
    </section>
  `;
}

function createHomeHtmlTooltip(copy) {
  if (!copy?.title || !copy?.body) {
    throw new Error("Texto de tooltip da página inicial incompleto.");
  }

  const detailHtml = copy.detail
    ? `
        <section class="home-tooltip-detail">
          <strong>${escapeTooltipHtml(copy.detailLabel || "Detalhe")}</strong>
          <p>${escapeTooltipHtml(copy.detail)}</p>
        </section>
      `
    : "";

  const sectionsHtml = copy.sections?.length
    ? `<div class="home-tooltip-sections">${copy.sections.map(renderSection).join("")}</div>`
    : "";

  return {
    value: `
      <div class="home-tooltip-content">
        <div class="home-tooltip-heading">
          <i class="pi ${escapeTooltipHtml(copy.icon || "pi-info-circle")}" aria-hidden="true"></i>
          <span>${escapeTooltipHtml(copy.title)}</span>
        </div>
        <p class="home-tooltip-body">${escapeTooltipHtml(copy.body)}</p>
        ${detailHtml}
        ${sectionsHtml}
      </div>
    `,
    escape: false,
    class: "home-info-tooltip",
    showDelay: 120,
    hideDelay: 80,
  };
}

export function homeTooltip(key, overrides = {}) {
  const copy = HOME_TOOLTIP_COPY[key];
  if (!copy) {
    throw new Error(`Texto de tooltip da página inicial não encontrado: ${key}`);
  }
  return createHomeHtmlTooltip({ ...copy, ...overrides });
}
