/**
 * Textos dos tooltips dos indicadores financeiros da aba de movimentação.
 *
 * A estrutura é transformada em HTML para manter o padrão visual dos
 * tooltips metodológicos do Sentinela.
 */
export const FINANCIAL_MOVEMENT_TOOLTIP_COPY = Object.freeze({
  totalVendas: {
    title: 'Total de vendas',
    body: 'Valor total das vendas registradas para este estabelecimento no período de análise.',
    sections: [
      {
        label: 'Cálculo',
        text: 'Soma dos valores mensais de vendas da movimentação do CNPJ, respeitando as datas inicial e final selecionadas.',
      },
    ],
  },
  ordensRecebidas: {
    title: 'Ordens bancárias recebidas',
    body: 'Valor acumulado dos pagamentos recebidos pelo estabelecimento no período de análise.',
    sections: [
      {
        label: 'Cálculo',
        text: 'Soma do campo valor_pago na base consolidada de pagamentos do Programa Farmácia Popular, após o filtro do CNPJ e do período.',
      },
    ],
  },
  numeroOrdens: {
    title: 'Número de ordens bancárias',
    body: 'Quantidade de ordens bancárias distintas recebidas pelo estabelecimento no período.',
    sections: [
      {
        label: 'Cálculo',
        text: 'Contagem dos números de ordem bancária distintos. Repetições do mesmo número não aumentam o total.',
      },
    ],
  },
  maiorOrdem: {
    title: 'Maior ordem bancária recebida',
    body: 'Maior valor individual de ordem bancária identificado no período.',
    sections: [
      {
        label: 'Cálculo',
        text: 'Maior valor_pago entre os registros de pagamento do estabelecimento.',
      },
    ],
  },
  ultimaOrdem: {
    title: 'Última ordem bancária recebida',
    body: 'Pagamento mais recente identificado para o estabelecimento dentro do período analisado.',
    sections: [
      {
        label: 'Exibição',
        text: 'Mostra a data de pagamento mais recente e, ao lado, o respectivo valor recebido.',
      },
    ],
  },
});

function escapeTooltipHtml(value) {
  return String(value).replace(/[&<>"']/g, (character) => ({
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    '"': '&quot;',
    "'": '&#39;',
  })[character]);
}

function renderSection(section) {
  if (!section?.label || !section?.text) {
    throw new Error('Seção de tooltip financeiro incompleta.');
  }

  return `
    <section class="financial-tooltip-section">
      <strong class="financial-tooltip-section-label">${escapeTooltipHtml(section.label)}</strong>
      <p>${escapeTooltipHtml(section.text)}</p>
    </section>
  `;
}

function createFinancialMovementHtmlTooltip(copy) {
  if (!copy?.title || !copy?.body || !Array.isArray(copy.sections) || copy.sections.length === 0) {
    throw new Error('Texto de tooltip financeiro incompleto.');
  }

  return {
    value: `
      <div class="financial-tooltip-content">
        <div class="financial-tooltip-heading">
          <i class="pi pi-info-circle" aria-hidden="true"></i>
          <span>${escapeTooltipHtml(copy.title)}</span>
        </div>
        <p class="financial-tooltip-body">${escapeTooltipHtml(copy.body)}</p>
        <div class="financial-tooltip-sections">
          ${copy.sections.map(renderSection).join('')}
        </div>
      </div>
    `,
    escape: false,
    class: 'financial-movement-tooltip',
    showDelay: 120,
    hideDelay: 80,
  };
}

export function financialMovementTooltip(key) {
  const copy = FINANCIAL_MOVEMENT_TOOLTIP_COPY[key];
  if (!copy) {
    throw new Error(`Texto de tooltip financeiro não encontrado: ${key}`);
  }
  return createFinancialMovementHtmlTooltip(copy);
}
