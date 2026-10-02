import { CRM_SEQUENCIA_MULTIPLO_MIN_AUTORIZACOES } from '@/config/crmFiltrosMedico';

/**
 * Tooltips informativos da página de Análises (mapa e ranking de CRMs).
 *
 * O conteúdo é entregue ao PrimeVue como HTML controlado. Qualquer valor
 * dinâmico é escapado antes de ser inserido no markup.
 */

const ANALYSIS_TOOLTIP_COPY = Object.freeze({
  crmFiltrosMedico: {
    title: 'Filtros dos médicos',
    body: 'Restringem os médicos do mapa, do ranking e da aba Por mês. Somam-se aos filtros da barra lateral esquerda (período, território e farmácias).',
    icon: 'pi-filter',
    sections: [
      {
        label: 'Duração',
        text: 'Valem enquanto o sistema estiver aberto; não são salvos entre sessões.',
      },
    ],
  },
  crmFiltroBusca: {
    title: 'Buscar médico',
    body: 'Filtra o ranking e a aba Por mês pelo nome do médico ou pelo número do CRM. O mapa não muda com a busca.',
    icon: 'pi-search',
    sections: [
      {
        label: 'CRM com UF',
        text: 'Aceita 800/SC, 800-SC, 800 SC, CRM-SC 800 e formatos parecidos: busca o CRM exato daquela UF. Só o número (800) busca o início do número em todas as UFs.',
      },
    ],
  },
  crmFiltroSituacaoCfm: {
    title: 'Situação no CFM',
    body: 'Localizado: o CRM consta no cadastro do CFM. Não localizado: o CRM usado nas prescrições não consta no cadastro.',
    icon: 'pi-id-card',
  },
  crmFiltroUfCrm: {
    title: 'UF do CRM',
    body: 'UF de registro do CRM usado nas prescrições (a UF do CRM, não a da farmácia). Vale também para CRMs não localizados no CFM. Marque uma ou mais.',
    icon: 'pi-map-marker',
  },
  crmFiltroTaxaDia: {
    title: 'Taxa diária',
    body: 'Prescrições ÷ dias com prescrição do médico no período, no recorte da página (Brasil, UF, região ou município): o mesmo número da coluna TAXA / DIA do ranking.',
    icon: 'pi-chart-bar',
    sections: [
      {
        label: 'Faixa',
        text: 'Escolha um atalho ou use a faixa personalizada (De / Até). Os limites são inclusivos; deixe um lado vazio para filtrar só "a partir de" ou "até". Aplica no botão Aplicar ou com Enter. Aceita decimais com vírgula (ex.: 30,5).',
      },
      {
        label: 'Aba Por mês',
        text: 'Cada linha é um mês: a faixa vale para a taxa daquele mês (coluna TAXA / DIA da aba). No mapa, no Resumo e na Linha do tempo, vale a taxa do período.',
      },
    ],
  },
  crmFiltroPrescricoes: {
    title: 'Total de prescrições',
    body: 'Prescrições do médico no período, no recorte da página: o mesmo número da coluna PRODUÇÃO do ranking.',
    icon: 'pi-file',
    sections: [
      {
        label: 'Faixa',
        text: 'Escolha um atalho ou use a faixa personalizada (De / Até). Os limites são inclusivos; deixe um lado vazio para filtrar só "a partir de" ou "até". Aplica no botão Aplicar ou com Enter.',
      },
      {
        label: 'Aba Por mês',
        text: 'Cada linha é um mês: a faixa vale para as prescrições daquele mês (coluna PRODUÇÃO da aba). No mapa, no Resumo e na Linha do tempo, vale o total do período.',
      },
    ],
  },
  crmFiltroExclusividade: {
    title: 'Exclusividade na farmácia principal',
    body: 'Prescrições do médico na farmácia onde ele mais prescreveu ÷ total de prescrições dele no Brasil, no período. É a coluna Exclusividade da aba CRMs do estabelecimento, olhando a farmácia principal do médico.',
    icon: 'pi-building',
    sections: [
      {
        label: 'Abrangência',
        text: 'Calculada com todas as farmácias do médico no Brasil, independentemente do recorte territorial e dos filtros de farmácia da barra lateral. Vale para o mapa, o Resumo, a Linha do tempo e a aba Por mês (escolhe os médicos).',
      },
      {
        label: 'Leitura',
        text: 'Valor alto, sozinho, não indica irregularidade: um médico de bairro pode concentrar quase tudo numa farmácia. O sinal ganha peso com volume alto e muitas prescrições por dia. 100% = o médico prescreveu em uma única farmácia no período.',
      },
      {
        label: 'Tempo',
        text: 'A primeira consulta de cada período calcula a exclusividade de todos os médicos (alguns segundos); depois, mudar a faixa ou outros filtros é imediato.',
      },
    ],
  },
  crmFiltroFarmacias: {
    title: 'Nº de farmácias onde atuou',
    body: 'Quantidade de farmácias distintas com prescrição do médico no período, em todo o Brasil. É o mesmo número do indicador "farmácias" do histórico do CRM.',
    icon: 'pi-sitemap',
    sections: [
      {
        label: 'Abrangência',
        text: 'Conta todas as farmácias do médico no Brasil, independentemente do recorte territorial e dos filtros de farmácia da barra lateral. Vale para o mapa, o Resumo, a Linha do tempo e a aba Por mês (escolhe os médicos).',
      },
      {
        label: 'Leitura',
        text: 'Metade dos médicos atua em até cerca de 20 farmácias no período. Os extremos merecem atenção: uma única farmácia (combine com a exclusividade) ou centenas de farmácias.',
      },
    ],
  },
  crmFiltroMunicipios: {
    title: 'Nº de municípios onde atuou',
    body: 'Quantidade de municípios distintos onde ficam as farmácias com prescrição do médico no período, em todo o Brasil. É o mesmo número do indicador "municípios" do histórico do CRM.',
    icon: 'pi-map-marker',
    sections: [
      {
        label: 'Abrangência',
        text: 'Conta todos os municípios do médico no Brasil, independentemente do recorte territorial e dos filtros de farmácia da barra lateral. Vale para o mapa, o Resumo, a Linha do tempo e a aba Por mês (escolhe os médicos).',
      },
      {
        label: 'Leitura',
        text: 'Metade dos médicos atua em até cerca de 8 municípios no período. Muitos municípios, sobretudo distantes entre si, merecem atenção; compare com o ponto de atenção "farmácias distantes" no histórico do CRM.',
      },
    ],
  },
  crmFiltroSequencia: {
    title: 'Autorizações em sequência',
    body: 'Filtra os médicos pelos dias com muitas autorizações em poucos minutos numa farmácia, no período. O tipo escolhe quais sequências contam; a severidade e os dias definem o quanto.',
    icon: 'pi-bolt',
    sections: [
      {
        label: 'Tipo',
        text: `Único CRM (padrão): dias em que o próprio médico concentrou as autorizações, o mesmo ponto de atenção do histórico do CRM. Múltiplos CRMs: dias em que a farmácia teve uma sequência com vários médicos e este médico tinha pelo menos ${CRM_SEQUENCIA_MULTIPLO_MIN_AUTORIZACOES} autorizações dentro dela (na maioria das janelas o médico aparece com 1 só; o mínimo evita marcar quem estava ali de passagem). Qualquer: dias de um tipo ou do outro. O tipo só tem efeito junto com a severidade ou com os dias.`,
      },
      {
        label: 'Severidade mínima',
        text: 'Define quais dias contam: "Grave ou pior" conta os dias graves, críticos e extremos. Sozinha, traz os médicos com pelo menos 1 dia nesse nível.',
      },
      {
        label: 'Dias com sequência',
        text: 'Quantidade de dias com sequência no período, na severidade escolhida (sem ela, qualquer uma). Em único CRM, cerca de 5% dos médicos têm algum dia; entre eles, metade tem até 3 dias e 10% passam de 44 dias. Médicos sem nenhuma sequência contam como 0 dias.',
      },
      {
        label: 'Abrangência',
        text: 'Todas as farmácias do médico no Brasil, no período, independentemente do recorte e dos filtros de farmácia. Escolhe os médicos em todas as abas.',
      },
    ],
  },
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
  listaInteresse: {
    title: 'Farmácias monitoradas',
    body: 'Estabelecimentos adicionados à lista de interesse para acompanhamento. Os números de cada farmácia são do período de análise escolhido; os demais filtros da barra lateral não se aplicam a esta tela.',
    icon: 'pi-bookmark',
    sections: [
      {
        label: 'Sua visão',
        text: 'Ordenação, filtros, agrupamento e densidade das linhas ficam salvos neste navegador. Os totais do topo somam só as farmácias exibidas.',
      },
      {
        label: 'Atalho',
        text: 'Tecle / para ir direto à busca.',
      },
    ],
  },
  crmRanking: {
    title: 'Ranking de médicos',
    body: 'Médicos com prescrição no escopo e no período selecionados. A ordem segue a coluna e a direção de ordenação escolhidas; inicialmente, a tabela mostra as maiores taxas diárias.',
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
        label: 'Farmácias',
        text: 'Farmácias e municípios distintos onde o médico prescreveu no período, no Brasil todo (não só no recorte da página). São os mesmos números dos filtros Nº de farmácias e Nº de municípios.',
      },
        {
          label: 'Colunas agrupadas',
          text: 'Produção ordena pelo número de prescrições; Farmácias ordena pelo número de farmácias; Farmácias filtradas, quando presente, ordena pelas prescrições nessas farmácias. Os valores complementares aparecem abaixo em cada célula.',
        },
    ],
  },
  crmRankingMensal: {
    title: 'Por mês',
    body: 'Uma linha por médico e mês, no escopo e no período selecionados. Inicialmente, os meses com maior taxa diária aparecem primeiro, de qualquer médico do recorte.',
    icon: 'pi-calendar',
    sections: [
      {
        label: 'Taxa diária do mês',
        text: 'Prescrições ÷ dias com prescrição naquele mês, dentro do escopo.',
      },
      {
        label: 'Colunas agrupadas',
        text: 'Produção ordena pelo número de prescrições; os dias com prescrição aparecem abaixo, na mesma célula.',
      },
    ],
  },
  crmRankingLinhaTempo: {
    title: 'Taxa diária mensal',
    body: 'Uma barra por mês do período, na mesma linha do tempo para todos os médicos. O seletor Escala, ao lado das abas, escolhe a régua da altura das barras.',
    icon: 'pi-chart-bar',
    sections: [
      {
        label: 'Cor',
        text: 'Tons de vermelho conforme o ×P95 do mês (taxa ÷ P95 nacional do mês), do mais claro ao mais marcado: de 1,5× a 2,5×, de 2,5× a 3,5×, de 3,5× a 4,5×, de 4,5× a 5,5×, de 5,5× a 6,5× e acima de 6,5×. Azul: demais meses (inclusive os pouco acima do P95, até 1,5×, que continuam contando como taxa elevada).',
      },
      {
        label: 'Escala comum',
        text: 'Altura = quantas vezes a taxa diária do mês passou do P95 nacional daquele mês (×P95), de 0 a 10×, igual para todos os médicos (acima de 10×, barra cheia com marca escura no topo). Barras mais altas são meses mais acima do P95, em qualquer linha. Meses abaixo do P95 ficam com até 1/10 da altura.',
      },
      {
        label: 'Escala por médico',
        text: 'Altura = taxa diária do mês ÷ o maior mês do próprio médico. Mostra o formato da atuação de cada um (quando cresceu, quando caiu), mas não compara médicos entre si.',
      },
      {
        label: 'Nas duas escalas',
        text: 'A cor segue o ×P95 do mês e o tooltip de cada mês traz a taxa, o ×P95 e o P95 do mês.',
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
        text: 'Taxa diária do CRM na farmácia mês a mês (prescrições ÷ dias com prescrição nela), uma barra por mês, na mesma linha do tempo para todas as farmácias. Barras alinhadas indicam atuação simultânea. A altura usa a mesma escala em todas as linhas, em vezes o P95 nacional do mês, até 4× o P95: acima disso a barra fica cheia com uma marca escura no topo (valor exato no detalhe).',
      },
      {
        label: 'Cor',
        text: 'Tons de vermelho conforme o ×P95 do mês (taxa ÷ P95 nacional do mês), do mais claro ao mais marcado: de 1,5× a 2,5×, de 2,5× a 3,5×, de 3,5× a 4,5×, de 4,5× a 5,5×, de 5,5× a 6,5× e acima de 6,5×. Azul: demais meses (inclusive os pouco acima do P95, até 1,5×, que continuam contando como taxa elevada).',
      },
      {
        label: 'Detalhe',
        text: 'Clique na célula para abrir o detalhe mensal da atuação do CRM na farmácia.',
      },
    ],
  },
  crmRankingAlertas: {
    title: 'Alertas',
    body: 'Número de pontos de atenção do médico no período da análise: os mesmos do modal do histórico, calculados com todas as farmácias. Passe o mouse no ícone para ver cada um e clique para abrir o histórico.',
    icon: 'pi-exclamation-triangle',
    sections: [
      {
        label: 'Sem ícone',
        text: 'O médico não tem pontos de atenção no período. Um marcador cinza indica que os alertas ainda estão sendo carregados.',
      },
      {
        label: 'Ordenação',
        text: 'Os alertas são calculados para os médicos da página exibida, por isso a coluna não é ordenável.',
      },
    ],
  },
  crmHistoricoFiltros: {
    title: 'Filtros do histórico',
    body: 'Valem só para este modal; os filtros da página de análises não mudam. Ao fechar, o modal volta ao período da análise, a todos os municípios e a todas as farmácias.',
    icon: 'pi-filter',
    sections: [
      {
        label: 'Período',
        text: 'Use um atalho ou escolha o intervalo na grade: clique no mês inicial e depois no final. Muda indicadores, pontos de atenção, tabela de farmácias e mapa de calor; a linha do tempo continua mostrando o histórico completo. "Últimos 12 meses de atuação" termina no último mês com prescrição do médico.',
      },
      {
        label: 'Município',
        text: 'Junta as farmácias do município onde o médico atuou: indicadores, linha do tempo, tabela, mapa de calor e evidências passam a ser só os delas. A taxa diária é exata: os dias com prescrição são contados uma vez no município, mesmo quando o médico prescreveu em duas farmácias dele no mesmo dia. A lista de farmácias passa a mostrar só as do município.',
      },
      {
        label: 'Farmácia',
        text: 'Uma farmácia por vez: indicadores, linha do tempo e pontos de atenção passam a ser só os dela, com taxa diária exata. Várias ao mesmo tempo não é possível porque o mesmo dia pode ter prescrição em duas farmácias, e os dados mensais não dizem quais dias se repetem.',
      },
      {
        label: 'Taxa elevada com município ou farmácia filtrados',
        text: 'Continua sendo a do total do médico no mês: o P95 é calculado sobre a produção total de cada médico, não sobre um município ou uma farmácia.',
      },
    ],
  },
  crmHistoricoAtencao: {
    title: 'Pontos de atenção',
    body: 'Fatos calculados sobre o período filtrado, sem juízo de valor. Servem para orientar a análise do auditor.',
    icon: 'pi-exclamation-circle',
    sections: [
      { label: 'Antes da inscrição no CFM', text: 'Meses com prescrição anteriores à data da 1ª inscrição do médico no CFM.' },
      { label: 'Autorizações em sequência (único CRM)', text: 'Dias em que o CRM teve muitas prescrições em poucos minutos numa farmácia (mesmos alertas da aba Autorizações do estabelecimento). Mostra quantos dias, em quantas farmácias e a pior severidade.' },
      { label: 'Farmácias distantes no mesmo mês', text: 'Meses em que o CRM prescreveu, no mesmo mês, em farmácias muito distantes entre si. Mostra a maior distância encontrada. Com município ou farmácia filtrados, não é avaliado.' },
      { label: 'Meses consecutivos com taxa elevada', text: 'A maior sequência de meses seguidos com taxa elevada (a partir de 2 meses).' },
      { label: 'Concentração em uma farmácia', text: 'A farmácia principal concentra ao menos o limite definido (50%) das prescrições do período. Com município ou farmácia filtrados, não é avaliado.' },
    ],
  },
  crmHistoricoEvidencias: {
    title: 'Evidências',
    body: 'Os alertas do CRM em todas as farmácias, uma linha por janela: os mesmos do painel do médico na aba Autorizações de cada estabelecimento. Respeitam o período e a farmácia escolhidos no topo do modal.',
    icon: 'pi-list',
    sections: [
      { label: 'Severidade', text: 'Clique numa severidade para ver só as janelas dela; clique de novo para voltar a todas.' },
      { label: 'Autorizações da janela', text: 'O ícone no fim da linha abre as autorizações daquela janela (todos os CRMs da farmácia no intervalo), com as deste CRM destacadas. Dali também dá para abrir a Cronologia do estabelecimento.' },
      { label: 'Exportar', text: 'O Excel traz as três evidências (uma aba cada), completas, no período e na farmácia escolhidos.' },
    ],
  },
  crmEvidenciasUnico: {
    title: 'Sequências (único CRM)',
    body: 'Janelas em que o próprio CRM teve muitas autorizações em poucos minutos numa farmácia.',
    icon: 'pi-bolt',
    sections: [
      { label: 'Janela', text: 'Minutos entre a primeira e a última autorização da sequência.' },
      { label: 'Taxa/hora', text: 'Ritmo da sequência, em autorizações por hora.' },
    ],
  },
  crmEvidenciasMultiplos: {
    title: 'Sequências (múltiplos CRMs)',
    body: 'Janelas em que vários CRMs diferentes tiveram muitas autorizações em poucos minutos numa farmácia e este CRM autorizou ao menos uma vez dentro da janela.',
    icon: 'pi-users',
    sections: [
      { label: 'Aut. do CRM', text: 'Autorizações deste CRM dentro da janela.' },
      { label: 'Total da janela', text: 'Autorizações de todos os CRMs na janela, na farmácia.' },
      { label: 'CRMs', text: 'Quantidade de CRMs diferentes na janela.' },
    ],
  },
  crmEvidenciasDistancia: {
    title: 'Farmácias distantes',
    body: 'Pares de farmácias muito distantes entre si em que o CRM prescreveu no mesmo mês. Com uma farmácia escolhida no topo, aparecem os pares que a envolvem.',
    icon: 'pi-directions',
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
/**
 * Faixa da taxa do mês em relação ao P95 nacional do mês (tons de vermelho da
 * linha do tempo). Só meses de taxa elevada (acima do P95) têm faixa.
 */
/**
 * Faixa de cor de um mês pelo ×P95 (barras, tooltips e legendas de todo o sistema).
 * Só meses de taxa elevada (acima do P95) têm faixa; até 1,5× a faixa não tem cor
 * (chave null: a barra fica neutra, mas o mês continua "taxa elevada" no tooltip).
 * Acima, um tom a cada 1×: leve (até 2,5×), media (até 3,5×), media-forte (até
 * 4,5×), forte (até 5,5×), muito-forte (até 6,5×) e extrema (acima de 6,5×).
 */
export function crmFaixaP95(ponto) {
  if (!ponto.taxa_elevada) return null;
  const razao = Number(ponto.razao_p95);
  if (razao > 6.5) return { chave: 'extrema', rotulo: 'acima de 6,5× o P95' };
  if (razao > 5.5) return { chave: 'muito-forte', rotulo: '5,5× a 6,5× o P95' };
  if (razao > 4.5) return { chave: 'forte', rotulo: '4,5× a 5,5× o P95' };
  if (razao > 3.5) return { chave: 'media-forte', rotulo: '3,5× a 4,5× o P95' };
  if (razao > 2.5) return { chave: 'media', rotulo: '2,5× a 3,5× o P95' };
  if (razao > 1.5) return { chave: 'leve', rotulo: '1,5× a 2,5× o P95' };
  return { chave: null, rotulo: '1× a 1,5× o P95' };
}

/**
 * Altura das barras de "Atuação na farmácia" (Perfil de CRMs e histórico do
 * CRM): escala comum a todas as linhas, em ×P95 do mês, com teto. Acima do teto
 * a barra fica cheia e marcada como cortada (valor real no tooltip/detalhe).
 */
export const CRM_ATUACAO_TETO_P95 = 4;
export function crmAlturaAtuacao(razaoP95, teto = CRM_ATUACAO_TETO_P95) {
  const razao = Number(razaoP95);
  if (!(razao >= 0)) throw new Error(`×P95 inválido: ${razaoP95}.`);
  if (!(teto > 0)) throw new Error(`Teto de ×P95 inválido: ${teto}.`);
  return {
    fracao: Math.min(razao, teto) / teto,
    cortada: razao > teto,
  };
}

/**
 * Mesma faixa a partir da taxa e do P95 do mês (quando a resposta não traz o
 * ×P95 pronto). Taxa elevada: taxa arredondada em 6 casas > P95, como no backend.
 */
/** Teto da escala comum da Linha do tempo do ranking: 0 a 10× o P95 (as barras de atuação usam 4×). */
export const CRM_LINHA_TEMPO_TETO_P95 = 10;

export function crmFaixaPorTaxa(taxa, p95) {
  const t = Number(taxa);
  const limite = Number(p95);
  if (!(limite > 0)) throw new Error(`P95 do mês inválido: ${p95}.`);
  return crmFaixaP95({ taxa_elevada: Number(t.toFixed(6)) > limite, razao_p95: t / limite });
}

export function crmMesTooltip(ponto, p95) {
  const comp = Number(ponto.competencia);
  const mes = `${String(comp % 100).padStart(2, '0')}/${Math.floor(comp / 100)}`;
  const dias = Number(ponto.qtd_dias_com_prescricao);
  const faixa = crmFaixaP95(ponto);
  return {
    value: `
      <div class="analysis-tooltip-content analysis-tooltip-content--mes">
        <div class="analysis-tooltip-heading">
          <i class="pi pi-calendar" aria-hidden="true"></i>
          <span>${escapeTooltipHtml(mes)}</span>
          ${faixa ? `<span class="analysis-tooltip-flag">Taxa elevada · ${escapeTooltipHtml(faixa.rotulo)}</span>` : ''}
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

/** Ícone de cada ponto de atenção do CRM (modal do histórico e ranking). */
export const CRM_ALERTA_ICONES = Object.freeze({
  antes_inscricao: 'pi-calendar-times',
  rajadas_unico: 'pi-bolt',
  distancia: 'pi-directions',
  sequencia_alta: 'pi-chart-line',
  concentracao: 'pi-building',
});

/** Ícone do selo "Não localizado no CFM" da coluna MÉDICO / CRM do ranking. */
export const CRM_NAO_LOCALIZADO_ICONE = 'pi-id-card';

/**
 * Tooltip do ícone de alertas do ranking de CRMs: todos os pontos de atenção
 * do médico no período. Com `competencia` (aba "Por mês"), marca os pontos que
 * envolvem aquele mês.
 * @param {Array<{codigo:string, titulo:string, detalhe:string, competencias:number[]}>} pontos
 * @param {{ periodo: string, competencia?: number|null }} opcoes
 */
/**
 * Tooltip do nome do médico cortado com reticências no ranking de CRMs.
 * @param {string} nome
 * @param {string} crm - ex.: "CRM 5123/SC"
 */
export function crmMedicoNomeTooltip(nome, crm) {
  if (!nome) throw new Error('Tooltip de médico sem nome.');
  return {
    value: `
      <div class="analysis-tooltip-content">
        <div class="analysis-tooltip-heading">
          <i class="pi pi-user" aria-hidden="true"></i>
          <span>${escapeTooltipHtml(nome)}</span>
        </div>
        <p class="analysis-tooltip-body">${escapeTooltipHtml(crm)}</p>
      </div>
    `,
    escape: false,
    class: 'analysis-info-tooltip',
    showDelay: 120,
    hideDelay: 80,
  };
}

export function crmAlertasTooltip(pontos, { periodo, competencia = null }) {
  if (!pontos?.length) throw new Error('Tooltip de alertas de CRM sem pontos de atenção.');
  const itens = pontos.map((ponto) => {
    const icone = CRM_ALERTA_ICONES[ponto.codigo];
    if (!icone) throw new Error(`Ponto de atenção sem ícone: ${ponto.codigo}`);
    const incluiMes = competencia != null && (ponto.competencias ?? []).includes(competencia);
    return `
      <li class="analysis-tooltip-alerta${incluiMes ? ' is-mes' : ''}">
        <i class="pi ${icone}" aria-hidden="true"></i>
        <div>
          <strong>${escapeTooltipHtml(ponto.titulo)}</strong>
          ${incluiMes ? '<span class="analysis-tooltip-flag">Inclui este mês</span>' : ''}
          <p>${escapeTooltipHtml(ponto.detalhe)}</p>
        </div>
      </li>
    `;
  }).join('');
  const total = pontos.length;
  return {
    value: `
      <div class="analysis-tooltip-content analysis-tooltip-content--alertas">
        <div class="analysis-tooltip-heading">
          <i class="pi pi-exclamation-triangle analysis-tooltip-alerta-icone" aria-hidden="true"></i>
          <span>${total} ${total === 1 ? 'ponto de atenção' : 'pontos de atenção'}</span>
          <span class="analysis-tooltip-periodo">${escapeTooltipHtml(periodo)}</span>
        </div>
        <ul class="analysis-tooltip-alertas">${itens}</ul>
        <p class="analysis-tooltip-rodape">Clique para abrir o histórico completo do CRM.</p>
      </div>
    `,
    escape: false,
    class: 'analysis-info-tooltip',
    showDelay: 120,
    hideDelay: 80,
  };
}
