/** Tooltips HTML da tabela de estabelecimentos. Escapa os dados de cada linha. */
const TABLE_TOOLTIP_COPY = Object.freeze({
  nameColumn: {
    title: 'Identificação do estabelecimento',
    body: 'A coluna reúne razão social, CNPJ, município e UF. O ícone indica matriz ou filial. Clique na linha para abrir o estabelecimento. Ao passar o mouse sobre a linha, aparecem as ações de detalhar o indicador e favoritar. Nos favoritos, a estrela e a ação de anotação permanecem visíveis. Clique no cabeçalho para ordenar pela razão social.',
    icon: 'pi-building',
  },
  riskColumn: {
    title: 'Como ler o risco',
    body: 'O número em “x” compara o valor do indicador com a mediana de referência: 1x é igual à mediana, 2x é o dobro e 0,5x é metade. A referência é a mediana da região de saúde quando há pelo menos 40 estabelecimentos; caso contrário, usa-se a mediana da UF. Clique no cabeçalho para ordenar.',
    icon: 'pi-chart-line',
  },
  clearRegion: {
    title: 'Limpar filtro de região',
    body: 'Remove a região de saúde selecionada.',
    icon: 'pi-times',
  },
  clearMunicipality: {
    title: 'Limpar filtro de município',
    body: 'Remove o município selecionado.',
    icon: 'pi-times',
  },
  matrix: {
    title: 'Matriz',
    body: 'Este estabelecimento está identificado como matriz.',
    icon: 'pi-home',
  },
  branch: {
    title: 'Filial',
    body: 'Este estabelecimento está identificado como filial.',
    icon: 'pi-building',
  },
  pharmacyName: {
    title: 'Razão social',
    body: 'Nome completo do estabelecimento. Clique na linha para abrir sua análise.',
    icon: 'pi-building',
    detailLabel: 'Nome completo',
  },
  cnpjValue: {
    title: 'CNPJ',
    body: 'Identificador deste estabelecimento. Clique na linha para abrir sua análise ou no ícone de cópia para copiar o CNPJ.',
    icon: 'pi-id-card',
    detailLabel: 'Número',
  },
  stateValue: {
    title: 'Unidade da Federação',
    body: 'UF em que o estabelecimento está cadastrado.',
    icon: 'pi-map-marker',
    detailLabel: 'UF',
  },
  copyCnpj: {
    title: 'Copiar CNPJ',
    body: 'Copia o CNPJ deste estabelecimento para a área de transferência.',
    icon: 'pi-copy',
  },
  municipality: {
    title: 'Município',
    body: 'Município cadastrado para este estabelecimento.',
    icon: 'pi-map-marker',
    detailLabel: 'Localidade',
  },
  indicatorColumn: {
    title: 'Indicador analisado',
    body: 'Valor do indicador para o estabelecimento, comparado à mediana territorial.',
    icon: 'pi-chart-bar',
    detailLabel: 'Indicador',
  },
  totalSales: {
    title: 'Total de vendas',
    body: 'Valor movimentado pelo estabelecimento no período selecionado.',
    icon: 'pi-money-bill',
    detailLabel: 'Valor',
  },
  totalSalesFooter: {
    title: 'Total de vendas da tabela',
    body: 'Valor total de vendas informado no resumo da tabela.',
    icon: 'pi-money-bill',
    detailLabel: 'Valor',
  },
  unverifiedSales: {
    title: 'Valor sem comprovação',
    body: 'Valor de vendas sem comprovação do estabelecimento no período selecionado.',
    icon: 'pi-exclamation-triangle',
    detailLabel: 'Valor',
  },
  unverifiedSalesFooter: {
    title: 'Total sem comprovação da tabela',
    body: 'Valor sem comprovação informado no resumo da tabela.',
    icon: 'pi-exclamation-triangle',
    detailLabel: 'Valor',
  },
  largeNetworkFilter: {
    title: 'Filtrar por grande rede',
    body: 'Filtra a tabela pela classificação de grande rede selecionada.',
    icon: 'pi-filter',
    detailLabel: 'Classificação',
  },
  networkEstablishments: {
    title: 'Estabelecimentos da rede',
    body: 'Filtra a tabela para mostrar os estabelecimentos da mesma rede.',
    icon: 'pi-sitemap',
    detailLabel: 'Estabelecimentos',
  },
  ministryConnectionFilter: {
    title: 'Filtrar por conexão MS',
    body: 'Filtra a tabela pela situação de conexão com o Ministério da Saúde.',
    icon: 'pi-filter',
    detailLabel: 'Conexão',
  },
  indicatorDetails: {
    title: 'Detalhamento do indicador',
    body: 'Abre a análise detalhada deste indicador para o estabelecimento.',
    icon: 'pi-chart-bar',
  },
  favoriteAdd: {
    title: 'Adicionar às Farmácias Monitoradas',
    body: 'Salva este estabelecimento na sua lista de favoritos para acompanhamento.',
    icon: 'pi-star',
  },
  favoriteRemove: {
    title: 'Remover das Farmácias Monitoradas',
    body: 'Retira este estabelecimento da sua lista de favoritos.',
    icon: 'pi-star-fill',
  },
  observationAdd: {
    title: 'Adicionar anotação',
    body: 'Abre o campo de anotação deste estabelecimento favoritado.',
    icon: 'pi-pencil',
  },
  observationEdit: {
    title: 'Editar anotação',
    body: 'Abre a anotação já registrada para este estabelecimento favoritado.',
    icon: 'pi-comment',
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

export function establishmentTableTooltip(key, detail) {
  const copy = TABLE_TOOLTIP_COPY[key];
  if (!copy) throw new Error(`Tooltip da tabela de estabelecimentos não encontrado: ${key}`);

  const detailHtml = detail !== undefined && detail !== null && detail !== ''
    ? `<div class="establishment-table-tooltip-detail">
         <strong>${escapeTooltipHtml(copy.detailLabel || 'Detalhe')}</strong>
         <span>${escapeTooltipHtml(detail)}</span>
       </div>`
    : '';

  return {
    value: `<div class="establishment-table-tooltip-content">
      <div class="establishment-table-tooltip-heading">
        <i class="pi ${escapeTooltipHtml(copy.icon)}" aria-hidden="true"></i>
        <span>${escapeTooltipHtml(copy.title)}</span>
      </div>
      <p class="establishment-table-tooltip-body">${escapeTooltipHtml(copy.body)}</p>
      ${detailHtml}
    </div>`,
    escape: false,
    class: 'establishment-table-info-tooltip',
    showDelay: 120,
    hideDelay: 80,
  };
}

/** Usa os valores já formatados pela tabela; a razão é calculada com a precisão original no backend. */
export function establishmentRiskTooltip({ indicator, value, median, scope, ratio, status }) {
  const hasRatio = ratio !== null && ratio !== undefined;
  const scopeLabel = scope === 'UF' ? 'UF' : 'região de saúde';
  const ratioText = hasRatio ? `${Number(ratio).toFixed(1)}x` : '—';
  const explanation = hasRatio
    ? 'A relação é calculada dividindo o valor do indicador da farmácia pela mediana de referência. Ex.: 2x significa o dobro da mediana (100% acima); 0,5x significa metade (50% abaixo).'
    : 'Multiplicador indisponível: não há valor do indicador ou a mediana está ausente ou é menor ou igual a zero.';

  return {
    value: `<div class="establishment-table-tooltip-content">
      <div class="establishment-table-tooltip-heading">
        <i class="pi pi-chart-line" aria-hidden="true"></i>
        <span>Risco neste indicador</span>
      </div>
      <p class="establishment-table-tooltip-body">${escapeTooltipHtml(explanation)}</p>
      <div class="establishment-table-tooltip-detail">
        <strong>${escapeTooltipHtml(indicator)}</strong>
        <span>Estabelecimento: ${escapeTooltipHtml(value)}</span>
        <span>Mediana da ${escapeTooltipHtml(scopeLabel)}: ${escapeTooltipHtml(median)}</span>
        <span>Relação: ${escapeTooltipHtml(ratioText)}</span>
      </div>
      <div class="establishment-table-tooltip-detail">
        <strong>Classificação: ${escapeTooltipHtml(status)}</strong>
      </div>
    </div>`,
    escape: false,
    class: 'establishment-table-info-tooltip',
    showDelay: 120,
    hideDelay: 80,
  };
}
