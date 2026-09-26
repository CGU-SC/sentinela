<script setup>
import { computed, ref } from 'vue';
import { storeToRefs } from 'pinia';
import { useCnpjDetailStore } from '@/stores/cnpjDetail';
import { useFilterStore } from '@/stores/filters';
import { useStableTabState } from '@/composables/useStableTabState';
import { useFormatting } from '@/composables/useFormatting';
import { useAnalyticsStore } from '@/stores/analytics';
import { useFarmaciaListsStore } from '@/stores/farmaciaLists';
import { useToggleInteresse } from '@/composables/useToggleInteresse';
import Tag from 'primevue/tag';
import Button from 'primevue/button';
import MortalityTimelineOverlay from './MortalityTimelineOverlay.vue';
import TabPlaceholder from './TabPlaceholder.vue';

const props = defineProps({
  cnpj: {
    type: String,
    required: true
  },
  periodSummary: {
    type: Object,
    default: null
  },
  periodLoading: {
    type: Boolean,
    default: false
  }
});

const filterStore = useFilterStore();
const { falecidosData, falecidosLoading, falecidosLoaded, falecidosError } = storeToRefs(useCnpjDetailStore());

// Mantém os dados anteriores visíveis durante a transição de período (evita flicker).
const {
  cachedData: cachedFalecidosData,
  isRefreshing,
} = useStableTabState(falecidosData, falecidosLoading, falecidosError);

const { formatCurrencyFull, formatarData, formatTitleCase, formatCnpj, toLocalISO } = useFormatting();
const analyticsStore = useAnalyticsStore();
const farmaciaLists = useFarmaciaListsStore();
const toggleInteresse = useToggleInteresse();

const createMortalityTooltip = (title, body, methodology) => ({
  value: `
    <div class="mortality-info-tooltip-content">
      <div class="mortality-info-tooltip-heading">
        <i class="pi pi-info-circle" aria-hidden="true"></i>
        <span>${title}</span>
      </div>
      <p class="mortality-info-tooltip-body">${body}</p>
      <div class="mortality-info-tooltip-note">
        <strong>Metodologia</strong>
        <span>${methodology}</span>
      </div>
    </div>
  `,
  escape: false,
  class: 'mortality-info-tooltip',
  showDelay: 120,
  hideDelay: 80,
});

const createMortalityTextTooltip = (value) => ({
  value,
  class: 'mortality-info-tooltip mortality-text-tooltip',
  showDelay: 120,
  hideDelay: 80,
});

const mortalityTooltips = Object.freeze({
  cards: Object.freeze({
    cpfsDistintos: createMortalityTooltip(
      'CPFs distintos',
      'Quantidade de CPFs únicos vinculados a pelo menos uma autorização identificada após o registro de óbito para este CNPJ, dentro do período selecionado. O mesmo CPF é contado uma única vez, ainda que possua várias autorizações.',
      'Contagem deduplicada pela identificação do CPF.'
    ),
    totalAutorizacoes: createMortalityTooltip(
      'Número de autorizações',
      'Quantidade de autorizações de venda identificadas para este CNPJ no período selecionado. Cada autorização é contabilizada uma vez e reúne os itens registrados com o mesmo número de autorização.',
      'Agrupamento dos itens pelo número da autorização.'
    ),
    valorTotal: createMortalityTooltip(
      'Prejuízo estimado',
      'Soma dos valores pagos registrados nas autorizações identificadas após o registro de óbito, no período selecionado. Representa o valor financeiro associado a essas ocorrências conforme os registros de venda.',
      'Soma dos valores pagos dos itens que compõem as autorizações identificadas.'
    ),
    mediaDias: createMortalityTooltip(
      'Média de dias pós-óbito',
      'Média aritmética do intervalo, em dias, entre o registro de óbito e a data da autorização. O cálculo considera todas as autorizações do período; por isso, autorizações diferentes do mesmo CPF têm peso individual na média.',
      'Média dos dias pós-óbito calculados para cada autorização.'
    ),
    maxDias: createMortalityTooltip(
      'Máximo de dias pós-óbito',
      'Maior intervalo, em dias, entre o registro de óbito e a data de uma autorização identificada para este CNPJ no período selecionado.',
      'Maior valor de dias pós-óbito encontrado entre as autorizações.'
    ),
    pctFaturamento: createMortalityTooltip(
      'Percentual do faturamento',
      'Percentual obtido pela relação entre o valor total das autorizações pós-óbito e o faturamento PFPB registrado para este CNPJ na base de movimentação. Indica a participação financeira dessas ocorrências no faturamento do estabelecimento.',
      'Valor das autorizações pós-óbito dividido pelo faturamento PFPB total registrado na base de movimentação.'
    ),
    cpfsMultiCnpj: createMortalityTooltip(
      'CPFs Multi-CNPJ',
      'Quantidade de CPFs identificados neste CNPJ que também aparecem vinculados a autorizações pós-óbito em outros CNPJs monitorados no mesmo período. O percentual entre parênteses é calculado sobre o total de CPFs distintos deste CNPJ.',
      'Contagem de CPFs compartilhados com outros CNPJs e proporção sobre os CPFs distintos do estabelecimento.'
    ),
  }),
  columns: Object.freeze({
    cpf: createMortalityTooltip(
      'CPF',
      'Identificador do beneficiário associado à autorização. É utilizado como chave de cruzamento entre os registros de venda e a base de óbitos, além de permitir o agrupamento das autorizações da mesma pessoa.',
      'Chave de cruzamento e agrupamento dos registros.'
    ),
    nomeFalecido: createMortalityTooltip(
      'Nome do falecido',
      'Nome associado ao CPF na base cadastral utilizada para complementar o registro. Quando não há nome disponível para o CPF, o sistema pode exibir “Não Identificado”.',
      'Informação obtida da base cadastral de pessoas físicas.'
    ),
    municipioUf: createMortalityTooltip(
      'Município / UF',
      'Município e unidade federativa associados ao beneficiário na base cadastral. Essa localização se refere ao CPF do beneficiário e não necessariamente ao endereço do estabelecimento que realizou a venda.',
      'Localização cadastral do beneficiário, não do estabelecimento.'
    ),
    fonteObito: createMortalityTooltip(
      'Fonte do óbito',
      'Identificação da fonte que forneceu o registro de óbito na base unificada, como SIM, SIRC ou SISOBI.',
      'Origem registrada na base unificada de óbitos.'
    ),
    numeroAutorizacao: createMortalityTooltip(
      'Número da autorização',
      'Número identificador da autorização registrada no Sistema Autorizador de Vendas. Ele é utilizado para reunir os itens pertencentes à mesma operação de venda.',
      'Identificador da operação de venda e chave de agregação dos itens.'
    ),
    dataObito: createMortalityTooltip(
      'Data do óbito',
      'Data de óbito consolidada para o CPF na base unificada de óbitos. Essa é a data utilizada pelo sistema no cruzamento com as autorizações.',
      'Data consolidada a partir dos registros disponíveis para o CPF.'
    ),
    dataVenda: createMortalityTooltip(
      'Data da venda',
      'Data em que a autorização foi registrada no sistema de vendas. Quando uma autorização possui vários itens, é considerada a primeira data/hora registrada para aquela autorização; a tabela exibe somente a data.',
      'Primeiro registro de data/hora associado ao número da autorização.'
    ),
    itens: createMortalityTooltip(
      'Itens',
      'Quantidade de registros de itens de medicamentos associados à autorização no recorte auditado. O número representa as linhas de itens consideradas na composição daquela autorização.',
      'Contagem das linhas de movimentação incluídas no conjunto de medicamentos auditado.'
    ),
    valor: createMortalityTooltip(
      'Valor da autorização',
      'Soma dos valores pagos registrados para os itens que compõem a autorização. Esse valor é utilizado na composição do prejuízo estimado.',
      'Soma do campo de valor pago dos itens da autorização.'
    ),
    diasAposObito: createMortalityTooltip(
      'Dias após o óbito',
      'Quantidade de dias entre a data do óbito e a data da autorização. O valor é calculado para cada autorização e permite avaliar a distância temporal entre o óbito registrado e a venda identificada.',
      'Diferença em dias entre o óbito e a data/hora da autorização.'
    ),
  }),
});

const formatNumeroBr = (valor, casas = 0) =>
  Number(valor).toLocaleString('pt-BR', { minimumFractionDigits: casas, maximumFractionDigits: casas });

/**
 * KPIs de vendas a falecidos no mesmo padrão dos cards de CRM: fundo neutro,
 * cor só na bolinha do título (vermelho = ocorrência; laranja = participação no
 * faturamento), número em destaque e uma linha de apoio.
 */
const falecidosKpiCards = computed(() => {
  const r = cachedFalecidosData.value?.summary;
  if (!r) return [];
  const tone = (valor, cor = 'critico') => (Number(valor) > 0 ? cor : null);
  return [
    {
      key: 'cpfs', label: 'CPFs distintos', value: formatNumeroBr(r.cpfs_distintos),
      hint: 'beneficiários falecidos', tone: tone(r.cpfs_distintos),
      tooltip: mortalityTooltips.cards.cpfsDistintos,
    },
    {
      key: 'autorizacoes', label: 'Autorizações', value: formatNumeroBr(r.total_autorizacoes),
      hint: 'após a data do óbito', tone: tone(r.total_autorizacoes),
      tooltip: mortalityTooltips.cards.totalAutorizacoes,
    },
    {
      key: 'prejuizo', label: 'Prejuízo estimado', value: formatCurrencyFull(r.valor_total),
      hint: 'valor pago após o óbito', tone: tone(r.valor_total),
      tooltip: mortalityTooltips.cards.valorTotal,
    },
    {
      key: 'media', label: 'Média pós-óbito', value: formatNumeroBr(r.media_dias || 0, 1), unit: 'dias',
      hint: 'entre o óbito e a venda', tone: tone(r.media_dias),
      tooltip: mortalityTooltips.cards.mediaDias,
    },
    {
      key: 'maximo', label: 'Máximo pós-óbito', value: formatNumeroBr(r.max_dias), unit: 'dias',
      hint: 'maior intervalo registrado', tone: tone(r.max_dias),
      tooltip: mortalityTooltips.cards.maxDias,
    },
    {
      key: 'faturamento', label: '% do faturamento', value: `${formatNumeroBr(r.pct_faturamento * 100, 3)}%`,
      hint: 'do valor total da farmácia', tone: tone(r.pct_faturamento, 'medio'),
      tooltip: mortalityTooltips.cards.pctFaturamento,
    },
    {
      key: 'multi', label: 'CPFs multi-CNPJ', value: formatNumeroBr(r.cpfs_multi_cnpj),
      hint: `${formatNumeroBr(r.pct_multi_cnpj * 100, 1)}% com vendas em outras farmácias`, tone: tone(r.cpfs_multi_cnpj),
      tooltip: mortalityTooltips.cards.cpfsMultiCnpj,
    },
  ];
});

// Mapa para busca O(1) de dados do CNPJ no Pinia Store para enriquecer o painel.
const cnpjsDict = computed(() => {
  const dict = {};
  if (analyticsStore.resultadoCnpjs) {
    for (const c of analyticsStore.resultadoCnpjs) {
      dict[c.cnpj] = c;
    }
  }
  return dict;
});

const formattedPeriod = computed(() => {
  if (!filterStore.periodo || filterStore.periodo.length < 2) return null;
  const start = filterStore.periodo[0];
  const end = filterStore.periodo[1];
  if (!start || !end) return null;
  return {
    start: formatarData(toLocalISO(start)),
    end:   formatarData(toLocalISO(end))
  };
});

const noMovementInPeriod = computed(() =>
  !props.periodLoading &&
  Boolean(props.periodSummary) &&
  Number(props.periodSummary.totalMov ?? 0) === 0
);


const getEstabelecimentoInfo = (estabStr) => {
  if (!estabStr) return { cnpj: '', name: '', geo: '' };
  const rawCnpj = estabStr.split(' - ')[0]?.trim() || '';
  const cleanCnpj = rawCnpj.replace(/\D/g, '');
  
  // Tenta puxar dados otimizados da store do Pinia
  const cnpjData = cnpjsDict.value[cleanCnpj];
  
  let name = estabStr.split(' - ')[1]?.split(' | ')[0]?.trim() || estabStr;
  let cityUF = estabStr.split(' | ')[1]?.trim() || '';
  let regiao = estabStr.split(' | ')[2]?.trim() || '';
  
  // Se existir no Pinia Store, prioriza dados consistentes e mais completos
  if (cnpjData) {
    if (cnpjData.razao_social) name = cnpjData.razao_social;
    if (cnpjData.municipio && cnpjData.uf) cityUF = `${cnpjData.municipio} - ${cnpjData.uf}`;
    if (cnpjData.regiao_saude) regiao = cnpjData.regiao_saude;
  }

  let geo = cityUF;
  if (regiao) {
     geo += ` • ${regiao}`;
  }

  return { 
    cnpj: rawCnpj,
    cleanCnpj: cleanCnpj,
    name: name,
    geo: geo
  };
};

// Função para mapear o risco em 10 níveis térmicos descritivos
function getDayStepClass(days) {
  if (days <= 7)   return 'd-risk-0-7d';
  if (days <= 15)  return 'd-risk-8-15d';
  if (days <= 30)  return 'd-risk-16-30d';
  if (days <= 60)  return 'd-risk-31-60d';
  if (days <= 120) return 'd-risk-61-120d';
  if (days <= 240) return 'd-risk-121-240d';
  if (days <= 365) return 'd-risk-241-1y';
  if (days <= 730) return 'd-risk-1-2y';
  if (days <= 1095) return 'd-risk-2-3y';
  return 'd-risk-over-3y';
}


const falecidosAgrupados = computed(() => {
  const transacoes = cachedFalecidosData.value?.transacoes ?? [];
  const grupos = new Map();
  for (const t of transacoes) {
    if (!grupos.has(t.cpf)) {
      grupos.set(t.cpf, {
        cpf:           t.cpf,
        nome:          formatTitleCase(t.nome_falecido) || 'Não Identificado',
        municipio:     formatTitleCase(t.municipio_falecido),
        uf:            t.uf_falecido,
        dt_obito:      formatarData(t.dt_obito),
        dt_nascimento: formatarData(t.dt_nascimento),
        outros_cnpj:   t.outros_estabelecimentos,
        transacoes:    [],
        total_valor:   0,
        max_dias:      0,
      });
    }
    const g = grupos.get(t.cpf);
    g.transacoes.push({ ...t, nome_falecido: formatTitleCase(t.nome_falecido) });
    g.total_valor += t.valor_total_autorizacao ?? 0;
    g.max_dias = Math.max(g.max_dias, t.dias_apos_obito ?? 0);
  }
  return [...grupos.values()];
});

const timelineOverlay = ref(null);

defineExpose({
  getSummary:  () => cachedFalecidosData.value?.summary ?? null,
  getAgrupados: () => falecidosAgrupados.value ?? [],
  getRanking:  () => cachedFalecidosData.value?.ranking ?? [],
  hasData:     () => !!(falecidosLoaded.value && cachedFalecidosData.value?.transacoes?.length),
});

const toggleMultiCnpj = (event, grupo) => {
  timelineOverlay.value?.open(event, grupo);
};

const openEstablishment = (estabStr) => {
  if (!estabStr) return;
  const targetCnpj = estabStr.split(' - ')[0].replace(/\D/g, '');
  window.open(`/estabelecimento/${targetCnpj}`, '_blank');
};

const isRankingExpanded = ref(false);
const visibleRanking = computed(() => {
  const r = cachedFalecidosData.value?.ranking || [];
  if (isRankingExpanded.value || r.length <= 3) return r;
  return r.slice(0, 3);
});

const filteredRankingCnpj = ref(null);

const toggleRankingFilter = (cleanCnpj) => {
  filteredRankingCnpj.value = filteredRankingCnpj.value === cleanCnpj ? null : cleanCnpj;
};

const falecidosAgrupadosFiltrados = computed(() => {
  if (!filteredRankingCnpj.value) return falecidosAgrupados.value;
  return falecidosAgrupados.value.filter(
    (g) => g.outros_cnpj && g.outros_cnpj.includes(filteredRankingCnpj.value)
  );
});

</script>

<template>
  <div class="tab-content falecidos-tab" :class="{ 'is-refreshing': isRefreshing }">
    <div
      v-if="falecidosLoading && !cachedFalecidosData && !falecidosError"
      class="falecidos-initial-loading-sentinel"
      aria-hidden="true"
    />

    <TabPlaceholder
      v-else-if="falecidosError"
      variant="error"
      icon="pi-exclamation-circle"
      title="Erro ao carregar"
      :description="falecidosError"
    />

    <TabPlaceholder
      v-else-if="noMovementInPeriod"
      variant="info"
      icon="pi-chart-bar"
      title="Sem movimentação no período"
    >
      <template #description>
        Não foram encontradas movimentações financeiras para este CNPJ no período de <u>{{ formattedPeriod?.start }}</u> até <u>{{ formattedPeriod?.end }}</u>.
      </template>
    </TabPlaceholder>

    <TabPlaceholder
      v-else-if="falecidosLoaded && !cachedFalecidosData?.transacoes?.length"
      variant="success"
      icon="pi-check-circle"
      title="Sem ocorrências no período"
    >
      <template #description>
        Não foram encontradas transações vinculadas a CPFs de pessoas falecidas no período de <u>{{ formattedPeriod?.start }}</u> até <u>{{ formattedPeriod?.end }}</u>.
      </template>
    </TabPlaceholder>


    <template v-else-if="falecidosLoaded">
      <!-- 7 CARDS DE KPI -->
      <div class="falecidos-kpi-grid">
        <div v-for="(card, idx) in falecidosKpiCards" :key="card.key" class="f-kpi-card">
          <span class="f-kpi-label">
            <span v-if="card.tone" class="f-kpi-dot" :class="`tone-${card.tone}`" aria-hidden="true" />
            <span class="f-kpi-label-text">{{ card.label }}</span>
            <i
              class="pi pi-info-circle mortality-info-icon"
              role="img"
              tabindex="0"
              :aria-label="`Informações sobre ${card.label}`"
              v-tooltip="{ ...card.tooltip, position: idx === 0 ? 'right' : idx === falecidosKpiCards.length - 1 ? 'left' : 'top' }"
            />
          </span>
          <span class="f-kpi-val">
            {{ card.value }}<small v-if="card.unit"> {{ card.unit }}</small>
          </span>
          <span class="f-kpi-hint">{{ card.hint }}</span>
        </div>
      </div>

      <!-- PAINEL MULTI-CNPJ (REDE DE COINCIDÊNCIA) -->
      <div class="falecidos-ranking-panel" v-if="cachedFalecidosData.ranking?.length">
        <div class="ranking-header-flex">
          <div class="title-wrap">
            <i class="pi pi-sitemap" />
            <span>Rede de Coincidência (Cross-CNPJ)</span>
          </div>
          <p class="ranking-subtitle">Outras farmácias monitoradas que aprovaram medicamentos para os mesmos falecidos identificados nesta unidade.</p>
        </div>
        
        <div class="pro-ranking-list">
          <div
             v-for="(r, index) in visibleRanking"
             :key="r.estabelecimento"
             class="pro-ranking-item"
          >
            <div class="rank-badge" :class="`rank-${index + 1}`">#{{ index + 1 }}</div>
            
            <div class="rank-info">
               <div class="rank-info-top">
                   <span class="rank-cnpj">{{ formatCnpj(getEstabelecimentoInfo(r.estabelecimento).cnpj) }}</span>
                   <span class="rank-name">{{ getEstabelecimentoInfo(r.estabelecimento).name }}</span>
               </div>
               <div class="rank-geo" v-if="getEstabelecimentoInfo(r.estabelecimento).geo">
                   <i class="pi pi-map-marker"></i>
                   <span>{{ getEstabelecimentoInfo(r.estabelecimento).geo }}</span>
               </div>
               <div class="rank-bar-wrapper">
                   <div class="rank-bar-bg">
                      <div class="rank-bar-fill" :style="{ width: (r.pct_total * 100) + '%' }"></div>
                   </div>
               </div>
            </div>

            <div class="rank-metrics">
               <span class="metric-val">{{ r.qtd_cpfs }}</span>
               <span class="metric-lbl">CPFs em Comum</span>
               <span class="metric-pct">({{ Math.round(r.pct_total * 100) }}%)</span>
            </div>

             <div class="rank-action">
                <button
                  class="rank-filter-btn"
                  :class="{ active: filteredRankingCnpj === getEstabelecimentoInfo(r.estabelecimento).cleanCnpj }"
                  @click.stop="toggleRankingFilter(getEstabelecimentoInfo(r.estabelecimento).cleanCnpj)"
                  v-tooltip.top="createMortalityTextTooltip('Filtrar a tabela de transações por este CNPJ')"
                >
                  <i :class="filteredRankingCnpj === getEstabelecimentoInfo(r.estabelecimento).cleanCnpj ? 'pi pi-filter-slash' : 'pi pi-filter'" />
                  <span>Exibir</span>
                </button>
                <button
                  class="rank-filter-btn"
                  :class="{ active: farmaciaLists.isInteresse(getEstabelecimentoInfo(r.estabelecimento).cleanCnpj) }"
                  v-tooltip.top="createMortalityTextTooltip(farmaciaLists.isInteresse(getEstabelecimentoInfo(r.estabelecimento).cleanCnpj) ? 'Remover da lista de interesse' : 'Salvar na lista de interesse para acompanhamento')"
                  @click.stop="toggleInteresse(getEstabelecimentoInfo(r.estabelecimento).cleanCnpj, getEstabelecimentoInfo(r.estabelecimento).name)"
                >
                  <i :class="farmaciaLists.isInteresse(getEstabelecimentoInfo(r.estabelecimento).cleanCnpj) ? 'pi pi-star-fill' : 'pi pi-star'" />
                  <span>Interesse</span>
                </button>
                <button
                  class="rank-filter-btn rank-open-btn"
                  v-tooltip.top="createMortalityTextTooltip('Abrir análise completa deste CNPJ')"
                  @click.stop="openEstablishment(r.estabelecimento)"
                >
                  <i class="pi pi-external-link" />
                  <span>Analisar CNPJ</span>
                </button>
             </div>
          </div>
        </div>

        <div v-if="cachedFalecidosData.ranking?.length > 3" class="ranking-expand-action">
           <Button 
              :icon="isRankingExpanded ? 'pi pi-chevron-up' : 'pi pi-chevron-down'" 
              :label="isRankingExpanded ? 'Recolher Lista' : `Ver Mais ${cachedFalecidosData.ranking.length - 3} Farmácias Conectadas`" 
              class="p-button-text p-button-sm p-button-secondary"
              @click="isRankingExpanded = !isRankingExpanded" 
           />
        </div>
      </div>

      <!-- TABELA DE TRANSAÇÕES -->
      <div class="falecidos-list-container">
        <div class="section-title">
          <i class="pi pi-list" />
          <span>Detalhamento de Transações (Agrupado por CPF)</span>
        </div>
        <div v-if="filteredRankingCnpj" class="filter-active-banner">
          <i class="pi pi-filter" />
          <span>
            Exibindo apenas CPFs em comum com
            <strong>{{ formatCnpj(filteredRankingCnpj) }}</strong>
            <template v-if="getEstabelecimentoInfo(falecidosData?.ranking?.find(r => getEstabelecimentoInfo(r.estabelecimento).cleanCnpj === filteredRankingCnpj)?.estabelecimento)?.name">
              — {{ getEstabelecimentoInfo(falecidosData?.ranking?.find(r => getEstabelecimentoInfo(r.estabelecimento).cleanCnpj === filteredRankingCnpj)?.estabelecimento)?.name }}
            </template>
            · <strong>{{ falecidosAgrupadosFiltrados.length }}</strong> CPF(s)
          </span>
          <button class="filter-clear-btn" @click="filteredRankingCnpj = null">
            <i class="pi pi-times" /> Limpar filtro
          </button>
        </div>
        <div class="f-table-wrap">
          <table class="f-table">
            <colgroup>
              <col style="width: 10%" />
              <col style="width: 17%" />
              <col style="width: 12%" />
              <col style="width: 6%" />
              <col style="width: 12%" />
              <col style="width: 8%" />
              <col style="width: 10%" />
              <col style="width: 6%" />
              <col style="width: 9%" />
              <col style="width: 10%" />
            </colgroup>
            <thead>
              <tr>
                <th>
                  <span class="f-th-label">
                    <span>CPF</span>
                    <i
                      class="pi pi-info-circle mortality-info-icon"
                      role="img"
                      tabindex="0"
                      aria-label="Informações sobre a coluna CPF"
                      v-tooltip.right="mortalityTooltips.columns.cpf"
                    />
                  </span>
                </th>
                <th>
                  <span class="f-th-label">
                    <span>Nome do Falecido</span>
                    <i
                      class="pi pi-info-circle mortality-info-icon"
                      role="img"
                      tabindex="0"
                      aria-label="Informações sobre a coluna Nome do Falecido"
                      v-tooltip.top="mortalityTooltips.columns.nomeFalecido"
                    />
                  </span>
                </th>
                <th>
                  <span class="f-th-label">
                    <span>Município / UF</span>
                    <i
                      class="pi pi-info-circle mortality-info-icon"
                      role="img"
                      tabindex="0"
                      aria-label="Informações sobre a coluna Município ou UF"
                      v-tooltip.top="mortalityTooltips.columns.municipioUf"
                    />
                  </span>
                </th>
                <th>
                  <span class="f-th-label">
                    <span>Fonte Óbito</span>
                    <i
                      class="pi pi-info-circle mortality-info-icon"
                      role="img"
                      tabindex="0"
                      aria-label="Informações sobre a coluna Fonte Óbito"
                      v-tooltip.top="mortalityTooltips.columns.fonteObito"
                    />
                  </span>
                </th>
                <th>
                  <span class="f-th-label">
                    <span>Nº Autorização</span>
                    <i
                      class="pi pi-info-circle mortality-info-icon"
                      role="img"
                      tabindex="0"
                      aria-label="Informações sobre a coluna Número da Autorização"
                      v-tooltip.top="mortalityTooltips.columns.numeroAutorizacao"
                    />
                  </span>
                </th>
                <th>
                  <span class="f-th-label">
                    <span>Dt. Óbito</span>
                    <i
                      class="pi pi-info-circle mortality-info-icon"
                      role="img"
                      tabindex="0"
                      aria-label="Informações sobre a coluna Data do Óbito"
                      v-tooltip.top="mortalityTooltips.columns.dataObito"
                    />
                  </span>
                </th>
                <th>
                  <span class="f-th-label">
                    <span>Data da Venda</span>
                    <i
                      class="pi pi-info-circle mortality-info-icon"
                      role="img"
                      tabindex="0"
                      aria-label="Informações sobre a coluna Data da Venda"
                      v-tooltip.top="mortalityTooltips.columns.dataVenda"
                    />
                  </span>
                </th>
                <th>
                  <span class="f-th-label">
                    <span>Itens</span>
                    <i
                      class="pi pi-info-circle mortality-info-icon"
                      role="img"
                      tabindex="0"
                      aria-label="Informações sobre a coluna Itens"
                      v-tooltip.top="mortalityTooltips.columns.itens"
                    />
                  </span>
                </th>
                <th>
                  <span class="f-th-label">
                    <span>Valor (R$)</span>
                    <i
                      class="pi pi-info-circle mortality-info-icon"
                      role="img"
                      tabindex="0"
                      aria-label="Informações sobre a coluna Valor"
                      v-tooltip.top="mortalityTooltips.columns.valor"
                    />
                  </span>
                </th>
                <th class="txt-center">
                  <span class="f-th-label">
                    <span>Dias após Óbito</span>
                    <i
                      class="pi pi-info-circle mortality-info-icon"
                      role="img"
                      tabindex="0"
                      aria-label="Informações sobre a coluna Dias após Óbito"
                      v-tooltip.left="mortalityTooltips.columns.diasAposObito"
                    />
                  </span>
                </th>
              </tr>
            </thead>
            <tbody>
              <template v-for="grupo in falecidosAgrupadosFiltrados" :key="grupo.cpf">
                <tr class="f-group-header">
                  <td colspan="10">
                    <span class="f-group-cpf">{{ grupo.cpf }}</span>
                    <span class="f-group-sep">|</span>
                    <span class="f-group-nome">{{ grupo.nome }}</span>
                    <span class="f-group-sep">—</span>
                    <span class="f-group-meta">{{ grupo.transacoes.length }} autorização(ões)</span>
                    <span class="f-group-sep">|</span>
                    <span class="f-group-meta">{{ formatCurrencyFull(grupo.total_valor) }}</span>
                    <span class="f-group-sep">|</span>
                    <span class="f-group-meta">Óbito: {{ grupo.dt_obito }}</span>
                    <Tag 
                      v-if="grupo.outros_cnpj" 
                      icon="pi pi-share-alt" 
                      value="MULTI-CNPJ" 
                      class="f-multi-tag status-info clickable-badge"
                      @click="(e) => toggleMultiCnpj(e, grupo)"
                      style="margin-left: 0.75rem;" 
                    />
                  </td>
                </tr>
                <tr v-for="t in grupo.transacoes" :key="t.num_autorizacao" class="f-row">
                  <td class="f-cpf-cell">{{ t.cpf }}</td>
                  <td>
                    <span class="f-nome">{{ t.nome_falecido || 'Não Identificado' }}</span>
                  </td>
                  <td class="f-date">{{ grupo.municipio }}/{{ grupo.uf }}</td>
                  <td class="f-fonte">
                    <span v-if="t.fonte_obito && t.fonte_obito.length > 10" v-tooltip.top="createMortalityTextTooltip(t.fonte_obito)" style="cursor: default">
                      {{ t.fonte_obito.substring(0, 10) }}...
                    </span>
                    <span v-else>{{ t.fonte_obito }}</span>
                  </td>
                  <td class="f-aut">{{ t.num_autorizacao }}</td>
                  <td class="f-date">{{ formatarData(t.dt_obito) }}</td>
                  <td class="f-date">{{ formatarData(t.data_autorizacao) }}</td>
                  <td class="f-num">{{ t.qtd_itens_na_autorizacao }}</td>
                  <td class="f-val">{{ formatCurrencyFull(t.valor_total_autorizacao) }}</td>
                  <td class="txt-center">
                    <span class="f-days-badge" :class="getDayStepClass(t.dias_apos_obito)">
                      {{ t.dias_apos_obito }} d
                    </span>
                  </td>
                </tr>
                <tr class="f-subtotal-row">
                  <td colspan="8" class="f-subtotal-label">Subtotal — {{ grupo.transacoes.length }} autorização(ões)</td>
                  <td class="f-val f-subtotal-val">{{ formatCurrencyFull(grupo.total_valor) }}</td>
                  <td></td>
                </tr>
              </template>
            </tbody>
            <tfoot>
              <tr class="f-grand-total">
                <td colspan="8">
                  TOTAL GERAL — {{ falecidosAgrupados.length }} CPF(s) distintos — {{ cachedFalecidosData.transacoes.length }} autorização(ões)
                </td>
                <td class="f-val">{{ formatCurrencyFull(cachedFalecidosData.summary.valor_total) }}</td>
                <td></td>
              </tr>
            </tfoot>
          </table>
        </div>
      </div>
    </template>

    <MortalityTimelineOverlay ref="timelineOverlay" :current-cnpj="cnpj" />
  </div>
</template>

<style scoped>
.falecidos-tab {
  padding: 1rem 0 0;
  display: flex;
  flex-direction: column;
  gap: 1.5rem;
}

.falecidos-kpi-grid {
  display: grid;
  grid-template-columns: repeat(7, 1fr);
  gap: 0.75rem;
}

.f-kpi-card {
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
  min-width: 0;
  padding: 0.8rem 0.9rem;
  background: var(--card-bg);
  border: 1px solid var(--card-border);
  border-radius: 10px;
}

.f-kpi-label {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  font-size: 0.65rem;
  font-weight: 600;
  color: var(--text-secondary);
  text-transform: uppercase;
  letter-spacing: 0.06em;
}
.f-kpi-label-text {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.f-kpi-dot {
  width: 8px;
  height: 8px;
  flex-shrink: 0;
  border-radius: 50%;
}
.f-kpi-dot.tone-critico { background: var(--risk-critical); }
.f-kpi-dot.tone-medio { background: var(--risk-medium); }
.f-kpi-hint {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 0.7rem;
  color: var(--text-muted);
}

.f-th-label {
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
  white-space: nowrap;
}

.mortality-info-icon {
  flex-shrink: 0;
  color: var(--text-muted);
  cursor: help;
  font-size: 0.68rem;
  line-height: 1;
  opacity: 0.68;
  outline: none;
  transition: color 0.15s ease, opacity 0.15s ease;
}

.mortality-info-icon:hover,
.mortality-info-icon:focus-visible {
  color: var(--primary-color);
  opacity: 1;
}


.f-kpi-val {
  font-size: 1.3rem;
  font-weight: 600;
  line-height: 1.1;
  color: var(--text-color);
  white-space: nowrap;
}


.f-kpi-val small {
  font-size: 0.72rem;
  font-weight: 500;
  color: var(--text-muted);
}




.falecidos-list-container {
  background: var(--card-bg);
  border: 1px solid var(--card-border);
  border-radius: 12px;
  padding: 1.25rem;
  box-shadow: 0 4px 15px rgba(0,0,0,0.1);
}

.section-title {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-size: 0.85rem;
  font-weight: 600;
  text-transform: uppercase;
  color: var(--text-color-85);
  margin-bottom: 1rem;
  letter-spacing: 0.05em;
  border-bottom: 1px solid var(--tabs-border);
  padding-bottom: 0.5rem;
  opacity: 0.85;
}

.section-title i {
  color: var(--primary-color);
  font-size: 0.9rem;
}

/* Tabela de Falecidos */
.f-table-wrap {
  overflow: hidden;
  padding-top: 0.5rem;
}

.f-table {
  width: 100%;
  border-collapse: collapse;
}

.f-table th {
  text-align: left;
  padding: 0.6rem 1rem;
  background: transparent;
  font-size: 0.68rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.02em;
  color: color-mix(in srgb, var(--text-secondary) 85%, transparent);
  border-bottom: 2px solid var(--tabs-border);
}

.f-table td {
  padding: 0.55rem 1rem;
  border-bottom: 1px solid var(--tabs-border);
  font-size: 0.8rem;
  color: color-mix(in srgb, var(--text-color-85) 85%, transparent);
  transition: background 0.15s ease;
}

.f-row:hover td {
  background: var(--table-stripe) !important;
}

.f-nome { font-weight: 400; font-size: 0.82rem; text-transform: none !important; }

.f-multi-tag {
  align-self: flex-start;
  font-size: 0.65rem !important;
  margin-top: 0.1rem;
  height: auto;
  padding: 0.1rem 0.5rem;
  border-radius: 99px;
}

.clickable-badge {
  cursor: pointer;
  transition: transform 0.1s;
}
.clickable-badge:hover { transform: scale(1.05); }


.f-date, .f-aut, .f-num, .f-val { font-size: 0.78rem; }
.f-date { text-transform: none !important; }
.f-num, .f-val { font-weight: 500; }

.txt-center { text-align: center !important; }

.f-days-badge {
  display: inline-block;
  padding: 0.25rem 0.65rem;
  border-radius: 6px;
  font-size: 0.82rem;
  font-weight: 700;
}

/* 10 Degraus de Risco Térmico Descritivos (Dias após Óbito) */
.d-risk-0-7d    { background: color-mix(in srgb, var(--risk-death-0-7d) 15%, transparent);    color: var(--risk-death-0-7d);    border: 1px solid color-mix(in srgb, var(--risk-death-0-7d) 30%, transparent); }
.d-risk-8-15d   { background: color-mix(in srgb, var(--risk-death-8-15d) 15%, transparent);   color: var(--risk-death-8-15d);   border: 1px solid color-mix(in srgb, var(--risk-death-8-15d) 30%, transparent); }
.d-risk-16-30d  { background: color-mix(in srgb, var(--risk-death-16-30d) 15%, transparent);  color: var(--risk-death-16-30d);  border: 1px solid color-mix(in srgb, var(--risk-death-16-30d) 30%, transparent); }
.d-risk-31-60d  { background: color-mix(in srgb, var(--risk-death-31-60d) 15%, transparent);  color: var(--risk-death-31-60d);  border: 1px solid color-mix(in srgb, var(--risk-death-31-60d) 30%, transparent); }
.d-risk-61-120d { background: color-mix(in srgb, var(--risk-death-61-120d) 15%, transparent); color: var(--risk-death-61-120d); border: 1px solid color-mix(in srgb, var(--risk-death-61-120d) 30%, transparent); }
.d-risk-121-240d{ background: color-mix(in srgb, var(--risk-death-121-240d) 15%, transparent);color: var(--risk-death-121-240d);border: 1px solid color-mix(in srgb, var(--risk-death-121-240d) 30%, transparent); }
.d-risk-241-1y  { background: color-mix(in srgb, var(--risk-death-241-1y) 15%, transparent);   color: var(--risk-death-241-1y);   border: 1px solid color-mix(in srgb, var(--risk-death-241-1y) 30%, transparent); }
.d-risk-1-2y    { background: color-mix(in srgb, var(--risk-death-1-2y) 15%, transparent);    color: var(--risk-death-1-2y);    border: 1px solid color-mix(in srgb, var(--risk-death-1-2y) 30%, transparent); font-weight: 800; }
.d-risk-2-3y    { background: color-mix(in srgb, var(--risk-death-2-3y) 15%, transparent);    color: var(--risk-death-2-3y);    border: 1px solid color-mix(in srgb, var(--risk-death-2-3y) 30%, transparent); font-weight: 800; }
.d-risk-over-3y { background: color-mix(in srgb, var(--risk-death-over-3y) 20%, transparent);  color: var(--risk-death-over-3y);  border: 1px solid color-mix(in srgb, var(--risk-death-over-3y) 40%, transparent); font-weight: 900; }

.f-cpf-cell { font-size: 0.75rem; color: var(--text-secondary); }
.f-fonte { font-size: 0.72rem; color: var(--text-secondary); }

/* ── Linha de cabeçalho do grupo (por falecido) - Estilo Relatório de Mesa (Neutro Ultra-Suave) ── */
.f-group-header td {
  background: color-mix(in srgb, var(--primary-color) 8%, var(--card-bg)) !important;
  border-top: 1px solid var(--tabs-border) !important;
  border-bottom: 1px solid var(--tabs-border) !important;
  padding: 0.5rem 1rem !important;
  font-size: 0.72rem;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--text-color-85) !important;
  font-weight: 500;
}

.f-group-cpf {
  font-weight: 700;
  margin-right: 0.75rem;
  color: var(--text-color-85);
}

.f-group-nome {
  color: var(--text-color-85);
  opacity: 0.9;
}

.f-group-sep {
  margin: 0 0.5rem;
  opacity: 0.3;
}

.f-group-meta {
  font-weight: 600;
  color: var(--text-secondary);
}

/* ── Linha de subtotal por falecido ── */
.f-subtotal-row td {
  background: transparent;
  border-top: 1px solid var(--tabs-border);
  border-bottom: 2px solid var(--tabs-border);
  padding: 0.45rem 1rem;
}

.f-subtotal-label {
  font-size: 0.72rem;
  font-weight: 500;
  text-transform: none !important;
  letter-spacing: 0.04em;
  color: var(--text-secondary);
  text-align: right;
}

.f-subtotal-val {
  font-weight: 500 !important;
  color: var(--text-secondary) !important;
}

/* ── Total geral (tfoot) ── */
.f-grand-total td {
  background: color-mix(in srgb, var(--bg-color) 95%, var(--text-color-85) 5%);
  border-top: 2px solid var(--tabs-border);
  padding: 0.75rem 1rem;
  font-size: 0.78rem;
  font-weight: 500;
  color: var(--text-color-85);
}

.f-grand-total .f-val {
  color: var(--text-secondary) !important;
  font-size: 0.88rem;
}

/* Ranking Panel - PRO Design */
.falecidos-ranking-panel {
  background: var(--card-bg);
  border: 1px solid var(--card-border);
  border-radius: 12px;
  padding: 0.75rem;
  margin-top: 0.75rem;
  box-shadow: 0 4px 15px rgba(0,0,0,0.1);
}

.ranking-header-flex {
  margin-bottom: 0.6rem;
  border-bottom: 1px solid var(--tabs-border);
  padding-bottom: 0.5rem;
}

.ranking-header-flex .title-wrap {
  display: flex;
  align-items: center;
  gap: 0.6rem;
  font-size: 0.85rem;
  font-weight: 600;
  text-transform: uppercase;
  color: var(--text-color-85);
  letter-spacing: 0.05em;
  opacity: 0.85;
}

.title-wrap i {
  color: var(--primary-color);
  font-size: 1.1rem;
}

.ranking-subtitle {
  font-size: 0.72rem;
  color: var(--text-muted);
  margin-top: 0.3rem;
  margin-left: 1.7rem;
}

.pro-ranking-list {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.pro-ranking-item {
  display: flex;
  align-items: center;
  gap: 1rem;
  padding: 0.5rem 0.75rem;
  background: color-mix(in srgb, var(--text-color-85) 2%, transparent);
  border: 1px solid color-mix(in srgb, var(--text-color-85) 6%, transparent);
  border-radius: 8px;
  transition: none;
}


.rank-badge {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  background: color-mix(in srgb, var(--text-color-85) 6%, transparent);
  color: var(--text-secondary);
  font-weight: 800;
  font-size: 0.75rem;
  border-radius: 6px;
}

/* Podium Colors (Contrast-safe for both Light & Dark modes) */
.rank-1 { background: color-mix(in srgb, #D4AF37 12%, transparent); color: #D4AF37; border: 1px solid color-mix(in srgb, #D4AF37 40%, transparent); }
.rank-2 { background: color-mix(in srgb, #9E9E9E 12%, transparent); color: #9E9E9E; border: 1px solid color-mix(in srgb, #9E9E9E 40%, transparent); }
.rank-3 { background: color-mix(in srgb, #B08D57 12%, transparent); color: #B08D57; border: 1px solid color-mix(in srgb, #B08D57 40%, transparent); }

.rank-info {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 0.4rem;
}

.rank-info-top {
  display: flex;
  align-items: baseline;
  gap: 0.75rem;
}

.rank-cnpj {
  font-size: 0.75rem;
  font-weight: 700;
  color: color-mix(in srgb, var(--text-color-85) 85%, transparent);
}

.ranking-expand-action {
  display: flex;
  justify-content: center;
  align-items: center;
  margin-top: 1rem;
  padding-top: 0.5rem;
  border-top: 1px dashed var(--tabs-border);
}

.ranking-expand-action .p-button {
  font-size: 0.72rem;
  font-weight: 700;
  letter-spacing: 0.05em;
  opacity: 0.7;
  transition: opacity 0.2s;
}

.ranking-expand-action .p-button:hover {
  opacity: 1;
}

.rank-name {
  font-size: 0.75rem;
  color: var(--text-secondary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.rank-geo {
  font-size: 0.65rem;
  color: var(--text-muted);
  display: flex;
  align-items: center;
  gap: 0.4rem;
  margin-top: -0.1rem;
  opacity: 0.85;
}

.rank-geo i {
  font-size: 0.6rem;
  color: var(--primary-color);
}

.rank-bar-wrapper {
  width: 100%;
  max-width: 300px;
}

.rank-bar-bg {
  height: 4px;
  background: color-mix(in srgb, var(--text-color-85) 10%, transparent);
  border-radius: 2px;
  overflow: hidden;
}

.rank-bar-fill {
  height: 100%;
  background: linear-gradient(90deg, var(--risk-medium), var(--risk-high));
  border-radius: 2px;
}

.rank-metrics {
  display: flex;
  align-items: baseline;
  gap: 0.4rem;
  text-align: right;
  min-width: 130px;
  justify-content: flex-end;
}

.metric-val {
  font-size: 1.1rem;
  font-weight: 800;
  color: var(--risk-high);
}

.metric-lbl {
  font-size: 0.65rem;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.metric-pct {
  font-size: 0.75rem;
  font-weight: 700;
  color: var(--text-secondary);
}

.rank-action {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  margin-left: 0.5rem;
}


.rank-filter-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 0.35rem;
  padding: 0.35rem 0.75rem;
  height: 32px;
  border-radius: 6px;
  border: 1px solid color-mix(in srgb, var(--primary-color) 35%, transparent);
  background: color-mix(in srgb, var(--primary-color) 10%, transparent);
  backdrop-filter: blur(8px);
  -webkit-backdrop-filter: blur(8px);
  color: var(--primary-color);
  cursor: pointer;
  transition: all 0.2s ease;
  font-size: 0.75rem;
  font-weight: 600;
  white-space: nowrap;
  box-shadow: inset 0 1px 0 color-mix(in srgb, white 20%, transparent),
              0 2px 6px color-mix(in srgb, var(--primary-color) 10%, transparent);
}

.rank-filter-btn:hover {
  background: color-mix(in srgb, var(--primary-color) 20%, transparent);
  border-color: color-mix(in srgb, var(--primary-color) 60%, transparent);
  box-shadow: inset 0 1px 0 color-mix(in srgb, white 25%, transparent),
              0 4px 10px color-mix(in srgb, var(--primary-color) 18%, transparent);
}

.rank-filter-btn.active {
  background: color-mix(in srgb, var(--primary-color) 75%, transparent);
  backdrop-filter: blur(8px);
  -webkit-backdrop-filter: blur(8px);
  border-color: var(--primary-color);
  color: #fff;
  box-shadow: inset 0 1px 0 color-mix(in srgb, white 30%, transparent),
              0 4px 12px color-mix(in srgb, var(--primary-color) 35%, transparent);
}

.rank-open-btn {
  color: var(--status-info);
  border-color: color-mix(in srgb, var(--status-info) 35%, transparent);
  background: color-mix(in srgb, var(--status-info) 10%, transparent);
  box-shadow: inset 0 1px 0 color-mix(in srgb, white 15%, transparent),
              0 2px 6px color-mix(in srgb, var(--status-info) 12%, transparent);
}

.rank-open-btn:hover {
  color: var(--status-info);
  background: color-mix(in srgb, var(--status-info) 20%, transparent);
  border-color: color-mix(in srgb, var(--status-info) 60%, transparent);
  box-shadow: inset 0 1px 0 color-mix(in srgb, white 20%, transparent),
              0 4px 10px color-mix(in srgb, var(--status-info) 20%, transparent);
}

.filter-active-banner {
  display: flex;
  align-items: center;
  gap: 0.6rem;
  padding: 0.55rem 1rem;
  border-radius: 8px;
  background: color-mix(in srgb, var(--primary-color) 5%, transparent);
  border: 1px solid color-mix(in srgb, var(--primary-color) 15%, transparent);
  font-size: 0.82rem;
  color: var(--text-color-85);
  opacity: 0.9;
  margin-bottom: 0.75rem;
}

.filter-active-banner i {
  color: var(--primary-color);
  font-size: 0.85rem;
  opacity: 0.85;
}

.filter-clear-btn {
  display: inline-flex;
  align-items: center;
  gap: 0.3rem;
  margin-left: auto;
  padding: 0.25rem 0.7rem;
  border-radius: 6px;
  border: 1px solid color-mix(in srgb, var(--primary-color) 30%, transparent);
  background: transparent;
  color: var(--primary-color);
  font-size: 0.75rem;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s ease;
}

.filter-clear-btn:hover {
  background: color-mix(in srgb, var(--primary-color) 12%, transparent);
}

.tab-placeholder {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 1rem;
  min-height: 300px;
  color: var(--text-muted);
  opacity: 0.5;
}

.placeholder-icon {
  font-size: 3rem;
}

.tab-placeholder p {
  font-size: 0.875rem;
}

:global(.p-tooltip.mortality-info-tooltip) {
  max-width: min(360px, calc(100vw - 2rem));
  padding: 0;
  background: var(--tooltip-bg);
  border: 1px solid var(--tooltip-border);
  border-radius: 9px;
  box-shadow: var(--tooltip-shadow);
}

:global(.mortality-info-tooltip-content) {
  display: flex;
  width: min(330px, calc(100vw - 2rem));
  flex-direction: column;
  gap: 0.62rem;
  padding: 0.75rem 0.85rem;
  line-height: 1.42;
}

:global(.mortality-info-tooltip-heading) {
  display: flex;
  align-items: center;
  gap: 0.45rem;
  color: var(--text-color-85);
  font-size: 0.8rem;
  font-weight: 700;
  letter-spacing: 0.025em;
}

:global(.mortality-info-tooltip-heading i) {
  flex-shrink: 0;
  color: var(--risk-medium);
  font-size: 0.8rem;
}

:global(.mortality-info-tooltip-body) {
  margin: 0;
  color: var(--text-secondary);
  font-size: 0.72rem;
}

:global(.mortality-info-tooltip-note) {
  display: flex;
  flex-direction: column;
  gap: 0.2rem;
  padding-top: 0.55rem;
  border-top: 1px solid var(--tabs-border);
  color: var(--text-secondary);
  font-size: 0.68rem;
}

:global(.mortality-info-tooltip-note strong) {
  color: var(--risk-medium);
  font-size: 0.65rem;
  font-weight: 700;
  letter-spacing: 0.04em;
  text-transform: uppercase;
}

:global(.p-tooltip.mortality-text-tooltip .p-tooltip-text) {
  padding: 0.75rem 0.85rem;
}
</style>
