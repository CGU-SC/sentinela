/**
 * Tooltips informativos da página de Análises (mapa e ranking de CRMs).
 *
 * O conteúdo é entregue ao PrimeVue como HTML controlado. Qualquer valor
 * dinâmico é escapado antes de ser inserido no markup.
 */

const ANALYSIS_TOOLTIP_COPY = Object.freeze({
  crmMap: {
    title: 'Médicos com taxa elevada',
    body: 'Percentual de médicos ativos que tiveram pelo menos um mês com taxa elevada no período.',
    icon: 'pi-map',
    sections: [
      {
        label: 'Mês com taxa elevada',
        text: 'Mês em que a taxa do médico no território (prescrições ÷ dias com prescrição) ficou acima do P95 nacional daquele mês, isto é, entre os 5% de maior taxa do Brasil.',
      },
      {
        label: 'Cor do território',
        text: 'Municípios: percentual do município ÷ percentual da sua Região de Saúde. No mapa do Brasil, cada UF é comparada à média das 27 UFs. 1,0× significa igual à referência; 2,0×, o dobro.',
      },
      {
        label: 'Média de referência',
        text: 'Soma dos médicos com taxa elevada ÷ soma dos médicos ativos dos municípios da região ou, no mapa nacional, das 27 UFs. Um médico conta em cada território onde prescreveu.',
      },
    ],
  },
  crmRanking: {
    title: 'Ranking de médicos por taxa diária',
    body: 'Médicos com prescrição no escopo e no período selecionados. A posição segue a coluna e a direção de ordenação escolhidas; inicialmente, a tabela mostra as maiores taxas diárias.',
    icon: 'pi-sort-amount-down',
    sections: [
      {
        label: 'Taxa diária',
        text: 'Prescrições ÷ dias com prescrição, somando os meses do período dentro do escopo.',
      },
      {
        label: 'Mês com taxa elevada',
        text: 'Mês em que a taxa do médico ficou acima do P95 nacional daquele mês, o corte dos 5% de médicos com maior taxa do Brasil.',
      },
      {
        label: '% meses com taxa elevada',
        text: 'Meses com taxa elevada ÷ meses com prescrição no período.',
      },
        {
          label: 'Colunas agrupadas',
          text: 'Produção ordena pelo número de prescrições; Meses com taxa elevada ordena pelo percentual; Farmácias filtradas, quando presente, ordena pelas prescrições nessas farmácias. Os valores complementares aparecem abaixo em cada célula.',
        },
    ],
  },
  crmRankingMensal: {
    title: 'Por mês',
    body: 'Uma linha por médico e mês, no escopo e no período selecionados. Inicialmente, os meses mais distantes do P95 aparecem primeiro, de qualquer médico do recorte.',
    icon: 'pi-calendar',
    sections: [
      {
        label: 'Taxa diária do mês',
        text: 'Prescrições ÷ dias com prescrição naquele mês, dentro do escopo.',
      },
      {
        label: '×P95',
        text: 'Taxa do mês ÷ P95 nacional do mesmo mês. Acima de 1× o mês tem taxa elevada. Comparar pelo ×P95 deixa meses de anos diferentes na mesma régua.',
      },
      {
        label: 'Colunas agrupadas',
        text: 'Produção ordena pelo número de prescrições; ×P95 / P95 do mês ordena pelo ×P95. Os valores complementares aparecem abaixo em cada célula.',
      },
    ],
  },
  crmRankingLinhaTempo: {
    title: 'Taxa diária mensal',
    body: 'Uma barra por mês do período, na mesma linha do tempo para todos os médicos. A altura é a taxa diária do mês (prescrições ÷ dias com prescrição) relativa ao maior mês do próprio médico.',
    icon: 'pi-chart-bar',
    sections: [
      {
        label: 'Cor',
        text: 'Vermelho: mês com taxa elevada (acima do P95 nacional do mês). Azul: demais meses.',
      },
      {
        label: 'Comparação entre médicos',
        text: 'Cada linha tem a própria escala: a altura mostra os meses que destoam do padrão do médico. Para comparar médicos entre si, use a cor ou o tooltip de cada mês, que traz a taxa, o ×P95 e o P95 do mês.',
      },
      {
        label: 'Mês sem barra',
        text: 'O médico não teve prescrição no escopo naquele mês.',
      },
    ],
  },
  crmHistorico: {
    title: 'Histórico do CRM',
    body: 'Tudo o que o CRM prescreveu no Farmácia Popular, em todas as farmácias. Os indicadores, a tabela, o mapa de calor e os pontos de atenção são do período filtrado; a linha do tempo mostra o histórico completo, com o período sombreado.',
    icon: 'pi-history',
    sections: [
      {
        label: 'Taxa diária',
        text: 'Prescrições ÷ dias com prescrição no Brasil (todas as farmácias). Um dia com prescrição em duas farmácias conta uma vez.',
      },
      {
        label: 'Mês com taxa elevada',
        text: 'Mês em que a taxa diária do médico ficou acima do P95 nacional daquele mês (os 5% de maior taxa do Brasil).',
      },
    ],
  },
  crmHistoricoAtuacao: {
    title: 'Atuação na farmácia',
    body: 'Primeiro e último mês em que o CRM teve prescrições nesta farmácia, dentro do período filtrado, e a quantidade de meses com movimento.',
    icon: 'pi-calendar',
    sections: [
      {
        label: 'Mini gráfico',
        text: 'Prescrições mês a mês, uma barra por mês, na mesma linha do tempo para todas as farmácias: do primeiro ao último mês com prescrição do CRM no período. Barras alinhadas indicam atuação simultânea; a altura é relativa ao maior mês do CRM naquela farmácia.',
      },
      {
        label: 'Detalhe',
        text: 'Clique na célula para abrir o detalhe mensal da atuação do CRM na farmácia.',
      },
    ],
  },
  crmHistoricoFiltros: {
    title: 'Filtros do histórico',
    body: 'Valem só para este modal; os filtros da página de análises não mudam. Ao fechar, o modal volta ao período da análise e a todas as farmácias.',
    icon: 'pi-filter',
    sections: [
      {
        label: 'Período',
        text: 'Use um atalho ou escolha o intervalo na grade: clique no mês inicial e depois no final. Muda indicadores, pontos de atenção, tabela de farmácias e mapa de calor; a linha do tempo continua mostrando o histórico completo. "Últimos 12 meses de atuação" termina no último mês com prescrição do médico.',
      },
      {
        label: 'Farmácia',
        text: 'Uma farmácia por vez: indicadores, linha do tempo e pontos de atenção passam a ser só os dela, com taxa diária exata. Várias ao mesmo tempo não é possível porque o mesmo dia pode ter prescrição em duas farmácias, e os dados mensais não dizem quais dias se repetem.',
      },
      {
        label: 'Taxa elevada com farmácia filtrada',
        text: 'Continua sendo a do total do médico no mês: o P95 é calculado sobre a produção total de cada médico, não sobre uma farmácia.',
      },
    ],
  },
  crmHistoricoAtencao: {
    title: 'Pontos de atenção',
    body: 'Fatos calculados sobre o período filtrado, sem juízo de valor. Servem para orientar a análise do auditor.',
    icon: 'pi-exclamation-circle',
    sections: [
      { label: 'Antes da inscrição no CFM', text: 'Meses com prescrição anteriores à data da 1ª inscrição do médico no CFM.' },
      { label: 'Mais de uma UF no mesmo mês', text: 'Meses em que o CRM aparece em farmácias de UFs diferentes.' },
      { label: 'Meses consecutivos com taxa elevada', text: 'A maior sequência de meses seguidos com taxa elevada (a partir de 2 meses).' },
      { label: 'Concentração em uma farmácia', text: 'A farmácia principal concentra ao menos o limite definido (50%) das prescrições do período.' },
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
    throw new Error('Seção de tooltip da página de análises incompleta.');
  }
  return `
    <section class="analysis-tooltip-section">
      <strong class="analysis-tooltip-section-label">${escapeTooltipHtml(section.label)}</strong>
      <p>${escapeTooltipHtml(section.text)}</p>
    </section>
  `;
}

/**
 * @param {string} key - chave em ANALYSIS_TOOLTIP_COPY
 * @param {{ extraSections?: Array<{label: string, text: string}> }} options
 *   Seções dinâmicas (ex.: referência ativa do mapa) exibidas depois das fixas.
 */
export function analysisTooltip(key, { extraSections = [] } = {}) {
  const copy = ANALYSIS_TOOLTIP_COPY[key];
  if (!copy) throw new Error(`Tooltip da página de análises não encontrado: ${key}`);

  const sections = [...(copy.sections ?? []), ...extraSections];
  const sectionsHtml = sections.length
    ? `<div class="analysis-tooltip-sections">${sections.map(renderSection).join('')}</div>`
    : '';

  return {
    value: `
      <div class="analysis-tooltip-content">
        <div class="analysis-tooltip-heading">
          <i class="pi ${escapeTooltipHtml(copy.icon)}" aria-hidden="true"></i>
          <span>${escapeTooltipHtml(copy.title)}</span>
        </div>
        <p class="analysis-tooltip-body">${escapeTooltipHtml(copy.body)}</p>
        ${sectionsHtml}
      </div>
    `,
    escape: false,
    class: 'analysis-info-tooltip',
    showDelay: 120,
    hideDelay: 80,
  };
}

function formatTooltipDecimal(value, casas = 2) {
  return Number(value).toLocaleString('pt-BR', { minimumFractionDigits: casas, maximumFractionDigits: casas });
}

/**
 * Tooltip de um mês de um médico (aba "Linha do tempo" do ranking de CRMs).
 * @param {{competencia:number, nu_prescricoes:number, qtd_dias_com_prescricao:number,
 *   taxa_prescricoes_dia:number, razao_p95:number, taxa_elevada:boolean}} ponto
 * @param {number} p95 - P95 nacional do mês
 */
export function crmMesTooltip(ponto, p95) {
  const comp = Number(ponto.competencia);
  const mes = `${String(comp % 100).padStart(2, '0')}/${Math.floor(comp / 100)}`;
  const dias = Number(ponto.qtd_dias_com_prescricao);
  return {
    value: `
      <div class="analysis-tooltip-content analysis-tooltip-content--mes">
        <div class="analysis-tooltip-heading">
          <i class="pi pi-calendar" aria-hidden="true"></i>
          <span>${escapeTooltipHtml(mes)}</span>
          ${ponto.taxa_elevada ? '<span class="analysis-tooltip-flag">Taxa elevada</span>' : ''}
        </div>
        <dl class="analysis-tooltip-metrics">
          <dt>Taxa diária</dt><dd>${formatTooltipDecimal(ponto.taxa_prescricoes_dia)}/dia</dd>
          <dt>×P95</dt><dd>${formatTooltipDecimal(ponto.razao_p95, 1)}× (P95 ${formatTooltipDecimal(p95)})</dd>
          <dt>Prescrições</dt><dd>${Number(ponto.nu_prescricoes).toLocaleString('pt-BR')} em ${dias} ${dias === 1 ? 'dia' : 'dias'}</dd>
        </dl>
      </div>
    `,
    escape: false,
    class: 'analysis-info-tooltip',
    showDelay: 0,
    hideDelay: 0,
  };
}
