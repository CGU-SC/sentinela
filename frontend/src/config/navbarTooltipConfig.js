/** Tooltips HTML da navegação principal. Valores dinâmicos são escapados. */
const NAVBAR_TOOLTIP_COPY = Object.freeze({
  comingSoon: {
    title: 'Análises em preparação',
    body: 'Esta área ainda não está disponível para os usuários.',
    icon: 'pi-clock',
  },
  recentCnpj: {
    title: 'Último estabelecimento',
    body: 'Abre novamente o estabelecimento consultado mais recentemente.',
    icon: 'pi-history',
    detailLabel: 'Estabelecimento',
  },
  clearRecentCnpj: {
    title: 'Limpar atalho',
    body: 'Remove o atalho do último estabelecimento da barra de navegação.',
    icon: 'pi-times',
  },
  documentation: {
    title: 'Documentação do sistema',
    body: 'Abre a documentação do Sentinela em uma nova aba.',
    icon: 'pi-book',
  },
  lightTheme: {
    title: 'Modo claro',
    body: 'Altera a aparência do sistema para o tema claro.',
    icon: 'pi-sun',
  },
  darkTheme: {
    title: 'Modo escuro',
    body: 'Altera a aparência do sistema para o tema escuro.',
    icon: 'pi-moon',
  },
  settings: {
    title: 'Configurações do sistema',
    body: 'Abre as configurações do Sentinela.',
    icon: 'pi-cog',
  },
  monitoredPharmacies: {
    title: 'Farmácias monitoradas',
    body: 'Abre suas listas de estabelecimentos monitorados.',
    icon: 'pi-bookmark',
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

export function navbarTooltip(key, detail) {
  const copy = NAVBAR_TOOLTIP_COPY[key];
  if (!copy) throw new Error(`Tooltip da navbar não encontrado: ${key}`);

  const detailHtml = detail
    ? `<div class="navbar-tooltip-detail">
         <strong>${escapeTooltipHtml(copy.detailLabel || 'Detalhe')}</strong>
         <span>${escapeTooltipHtml(detail)}</span>
       </div>`
    : '';

  return {
    value: `<div class="navbar-tooltip-content">
      <div class="navbar-tooltip-heading">
        <i class="pi ${escapeTooltipHtml(copy.icon)}" aria-hidden="true"></i>
        <span>${escapeTooltipHtml(copy.title)}</span>
      </div>
      <p class="navbar-tooltip-body">${escapeTooltipHtml(copy.body)}</p>
      ${detailHtml}
    </div>`,
    escape: false,
    class: 'navbar-info-tooltip',
    showDelay: 120,
    hideDelay: 80,
  };
}
