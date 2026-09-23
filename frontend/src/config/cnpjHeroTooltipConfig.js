/**
 * Tooltips explicativos da hero do detalhe do estabelecimento.
 *
 * O PrimeVue recebe HTML por meio de `escape: false`. Os valores dinâmicos
 * passam por escape antes de serem interpolados no conteúdo do tooltip.
 */

const CNPJ_HERO_TOOLTIP_COPY = Object.freeze({
  back: {
    title: "Voltar",
    body: "Retorna à tela anterior.",
    icon: "pi-arrow-left",
  },
  copyCnpj: {
    title: "Copiar CNPJ",
    body: "Copia o CNPJ completo para a área de transferência.",
    icon: "pi-copy",
  },
  cadastro: {
    title: "Dados cadastrais",
    body: "Abre os dados cadastrais e geográficos disponíveis para este estabelecimento.",
    icon: "pi-id-card",
  },
  nomeFantasia: {
    title: "Nome do estabelecimento",
    body: "Nome fantasia completo registrado para o estabelecimento.",
    icon: "pi-home",
  },
  razaoSocial: {
    title: "Razão social",
    body: "Razão social completa registrada para o estabelecimento.",
    icon: "pi-building",
  },
  rede: {
    title: "Estabelecimentos da rede",
    body: "Indica quantos estabelecimentos da mesma rede foram identificados na base consultada.",
    icon: "pi-sitemap",
    detailLabel: "Interação",
  },
  ministerioSaude: {
    title: "Ministério da Saúde",
    body: "Indica a situação da conexão do estabelecimento com o Ministério da Saúde na base consultada.",
    icon: "pi-link",
    detailLabel: "Situação atual",
  },
  receitaFederal: {
    title: "Receita Federal",
    body: "Apresenta a situação cadastral do CNPJ conforme a base consultada da Receita Federal.",
    icon: "pi-building",
    detailLabel: "Situação atual",
  },
  rankRegiao: {
    title: "Estabelecimentos na Região de Saúde",
    body: "Abre o ranking completo de estabelecimentos da Região de Saúde.",
    icon: "pi-sitemap",
    detailLabel: "Ação",
    detail: "Clique para consultar o ranking regional.",
  },
  rankMunicipio: {
    title: "Estabelecimentos no município",
    body: "Abre o ranking de estabelecimentos do município dentro da Região de Saúde.",
    icon: "pi-building",
    detailLabel: "Ação",
    detail: "Clique para consultar o ranking municipal.",
  },
  pdf: {
    title: "Relatório PDF",
    body: "Gera o Relatório PDF do estabelecimento com os dados disponíveis para o período de análise.",
    icon: "pi-file-pdf",
    detailLabel: "Status",
  },
  notaTecnica: {
    title: "Nota Técnica",
    body: "Gera a Nota Técnica do estabelecimento com as análises e evidências disponíveis.",
    icon: "pi-book",
    detailLabel: "Status",
  },
  listaInteresse: {
    title: "Lista de Interesse",
    body: "Adiciona ou remove este estabelecimento da Lista de Interesse.",
    icon: "pi-star",
    detailLabel: "Ação disponível",
  },
  observacao: {
    title: "Observação",
    body: "Abre o campo para consultar ou editar a observação do estabelecimento.",
    icon: "pi-comment",
    detailLabel: "Ação disponível",
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

function createCnpjHeroHtmlTooltip(copy) {
  if (!copy?.title || !copy?.body) {
    throw new Error("Texto de tooltip da hero do CNPJ incompleto.");
  }

  const detailHtml = copy.detail
    ? `
        <section class="cnpj-hero-tooltip-detail">
          <strong>${escapeTooltipHtml(copy.detailLabel || "Detalhe")}</strong>
          <p>${escapeTooltipHtml(copy.detail)}</p>
        </section>
      `
    : "";

  return {
    value: `
      <div class="cnpj-hero-tooltip-content">
        <div class="cnpj-hero-tooltip-heading">
          <i class="pi ${escapeTooltipHtml(copy.icon || "pi-info-circle")}" aria-hidden="true"></i>
          <span>${escapeTooltipHtml(copy.title)}</span>
        </div>
        <p class="cnpj-hero-tooltip-body">${escapeTooltipHtml(copy.body)}</p>
        ${detailHtml}
      </div>
    `,
    escape: false,
    class: "cnpj-hero-tooltip",
    showDelay: 120,
    hideDelay: 80,
  };
}

export function cnpjHeroTooltip(key, overrides = {}) {
  const copy = CNPJ_HERO_TOOLTIP_COPY[key];
  if (!copy) {
    throw new Error(`Texto de tooltip da hero do CNPJ não encontrado: ${key}`);
  }
  return createCnpjHeroHtmlTooltip({ ...copy, ...overrides });
}

export function cnpjHeroTextTooltip(title, body, detail, detailLabel = "Valor") {
  return createCnpjHeroHtmlTooltip({
    title,
    body,
    detail,
    detailLabel,
    icon: "pi-info-circle",
  });
}
