<script setup>
import { computed, ref, watch } from "vue";
import { useFormatting } from "@/composables/useFormatting";
import { useCnpjDetailStore } from '@/stores/cnpjDetail';
import { useFilterParameters } from "@/composables/useFilterParameters";
import CrmAtuacaoDialog from './CrmAtuacaoDialog.vue';
import { useThemeStore } from '@/stores/theme';
import { DATA_NEUTRAL } from '@/config/colors';
import { CRM_EXCLUSIVIDADE_THRESHOLDS } from '@/config/riskConfig';

const cnpjDetailStore = useCnpjDetailStore();
const { getApiParams } = useFilterParameters();

const props = defineProps({
  crmsInteresse:    { type: Array,  required: true },
  activeKpiFilter:  { type: String, default: null },
  kpiFilters:       { type: Object, required: true },
  kpiFilterLabels:  { type: Object, required: true },
  currentCnpj:      { type: String, default: '' },
  periodoCompetencias: { type: Object, default: null },
  serieMensalFarmacia: { type: Array, default: () => [] },
});

const emit = defineEmits(['clear-filters']);


const { formatCurrencyFull, formatNumberFull, formatarData, formatTitleCase } = useFormatting();
const formatPct = (val) => val != null ? `${Number(val).toFixed(2).replace('.', ',')}%` : "0,00%";

// Limite do "núcleo" de concentração (Pareto): CRMs que, somados do maior para o
// menor, formam até 80% do valor da farmácia.
const PARETO_LIMITE = 80;

const themeStore = useThemeStore();
// Cor de dados neutra (azul-aço) exposta como variáveis CSS para barras e mini gráficos.
const dataColorVars = computed(() => {
  const cores = DATA_NEUTRAL[themeStore.isDark ? 'dark' : 'light'];
  return { '--data-color': cores.strong, '--data-color-soft': cores.soft };
});

function getExclusividadeNivel(m) {
  const valor = Number(m.pct_volume_aqui_vs_total);
  if (valor >= CRM_EXCLUSIVIDADE_THRESHOLDS.alto) return 'alto';
  if (valor >= CRM_EXCLUSIVIDADE_THRESHOLDS.atencao) return 'atencao';
  return 'normal';
}

function getParticipacao(m) {
  const parte = Math.max(0, Math.min(100, Number(m.pct_participacao)));
  const acumulado = Math.max(0, Math.min(100, Number(m.pct_acumulado)));
  const anterior = Math.max(0, acumulado - parte);
  return {
    anterior,
    parte,
    nucleo: anterior < PARETO_LIMITE,
  };
}

const escapeTooltipHtml = (value) => String(value).replace(/[&<>"']/g, (character) => ({
  '&': '&amp;',
  '<': '&lt;',
  '>': '&gt;',
  '"': '&quot;',
  "'": '&#39;',
}[character]));

const createCrmTableTooltip = (title, body, note, icon = 'pi-info-circle') => ({
  value: `
    <div class="crm-profile-tooltip-content">
      <div class="crm-profile-tooltip-heading">
        <i class="pi ${icon}" aria-hidden="true"></i>
        <span>${escapeTooltipHtml(title)}</span>
      </div>
      <p class="crm-profile-tooltip-body">${escapeTooltipHtml(body)}</p>
      <div class="crm-profile-tooltip-note">
        <strong>Como interpretar</strong>
        <span>${escapeTooltipHtml(note)}</span>
      </div>
    </div>
  `,
  escape: false,
  class: 'crm-profile-info-tooltip',
  showDelay: 120,
  hideDelay: 80,
});

const crmTableTooltips = Object.freeze({
  filterBadge: createCrmTableTooltip(
    'Filtro de KPI ativo',
    'A tabela está exibindo somente os médicos relacionados ao indicador selecionado no card acima.',
    'O contador informa quantos registros permanecem visíveis em relação ao total carregado.',
    'pi-filter-fill'
  ),
  clearFilter: createCrmTableTooltip(
    'Limpar filtro',
    'Remove o filtro aplicado pelo card de KPI e restaura a lista completa de CRMs.',
    'A seleção de “Apenas com Alertas / Anomalias” permanece independente.',
    'pi-times'
  ),
  columns: Object.freeze({
    rank: createCrmTableTooltip(
      'Classificação',
      'Ordenação decrescente pelo valor financeiro total autorizado por este CRM no estabelecimento.',
      'A posição é recalculada conforme o período analisado e os filtros aplicados.',
      'pi-sort-amount-down'
    ),
    crm: createCrmTableTooltip(
      'CRM / Médico',
      'Identificação do CRM e da UF de registro, seguida do nome do prescritor conforme a base do Conselho Federal de Medicina. A linha abaixo informa a primeira inscrição disponível para esse registro; quando o CRM não consta da base, o nome aparece como “Não localizado na base do CFM”.',
      'O CRM é a chave usada para vincular as autorizações às análises de comportamento do prescritor.',
      'pi-id-card'
    ),
    status: createCrmTableTooltip(
      'Status / Alertas',
      'Lista os sinais do CRM, um por linha, em ordem de gravidade: CRM não localizado ou irregular no CFM (vermelho); mais de 30 prescrições por dia, local (vermelho) ou no Brasil (laranja-escuro); Autorizações em Sequência com Único CRM (laranja) e com Múltiplos CRMs (roxo); distância superior a 400 km (verde-azulado); e CRM exclusivo deste estabelecimento (azul).',
      'O número à direita é a quantidade de episódios detalhados. Clique na seta ou na linha para abrir as evidências.',
      'pi-shield'
    ),
    volume: createCrmTableTooltip(
      'Volume / Valor',
      'Mostra o valor financeiro total das autorizações vinculadas ao CRM e a quantidade de autorizações consideradas no período.',
      'O valor também é utilizado para ordenar a classificação financeira da tabela.',
      'pi-chart-bar'
    ),
    participation: createCrmTableTooltip(
      'Participação no valor',
      'Parcela do valor pago pela farmácia atribuída ao CRM. Na barra, o trecho cinza é o acumulado dos médicos acima dele na classificação e o trecho colorido é a participação deste médico; a ponta direita é o acumulado até ele.',
      'Lida de cima para baixo, a coluna forma uma escada: degraus largos no topo indicam faturamento concentrado em poucos médicos. Os médicos que, somados do maior para o menor, formam os primeiros 80% do valor aparecem em cor mais forte.',
      'pi-chart-line'
    ),
    prescriptions: createCrmTableTooltip(
      'Prescrições por dia',
      'Exibe a média diária de prescrições em duas perspectivas: local, considerando apenas esta farmácia; e Brasil, considerando as farmácias do Farmácia Popular associadas ao CRM.',
      'Médias acima de 30 prescrições por dia são sinalizadas como emissão atípica.',
      'pi-calendar-clock'
    ),
    atuacao: createCrmTableTooltip(
      'Atuação na farmácia',
      'Primeiro e último mês em que o CRM teve prescrições neste estabelecimento, dentro do período filtrado, e a quantidade de meses com movimento.',
      'O mini gráfico mostra as autorizações mês a mês, uma barra por mês, na mesma linha do tempo para todos os médicos: do primeiro ao último mês com prescrições na farmácia dentro do período filtrado. Barras alinhadas indicam atuação simultânea; a altura é relativa ao maior mês do próprio CRM.',
      'pi-calendar'
    ),
    exclusive: createCrmTableTooltip(
      'Exclusividade do médico nesta farmácia',
      'Mostra quantas das autorizações deste médico no Farmácia Popular, em todo o Brasil, foram realizadas nesta farmácia. Exemplo: 87% significa que, de cada 100 autorizações do médico no programa, 87 foram realizadas aqui.',
      `Destaque vermelho a partir de ${CRM_EXCLUSIVIDADE_THRESHOLDS.alto}% e texto em evidência entre ${CRM_EXCLUSIVIDADE_THRESHOLDS.atencao}% e ${CRM_EXCLUSIVIDADE_THRESHOLDS.alto}%. Um valor alto, sozinho, não indica irregularidade: um médico de bairro pode ter quase todas as autorizações concentradas na mesma farmácia. O sinal ganha peso quando vem acompanhado de volume alto, ou seja, participação relevante no valor e muitas prescrições por dia.`,
      'pi-lock'
    ),
  }),
  evidence: Object.freeze({
    unico: createCrmTableTooltip(
      'Autorizações em Sequência (Único CRM)',
      'Dias em que este CRM registrou muitas autorizações em sequência em um intervalo muito curto. A evidência detalha a data, o volume, a janela de tempo e a taxa por hora.',
      'Quanto maior a taxa por hora, maior o indício de lançamento automatizado com um único médico.',
      'pi-user'
    ),
    distancia: createCrmTableTooltip(
      'Distância geográfica',
      'Pares de estabelecimentos em que o mesmo CRM foi utilizado simultaneamente em municípios distantes entre si. A distância informa a separação entre os locais.',
      'O padrão pode indicar incompatibilidade de presença física e deve ser analisado junto às datas e horários das autorizações.',
      'pi-map-marker'
    ),
    multiplos: createCrmTableTooltip(
      'Autorizações em Sequência (Múltiplos CRMs)',
      'Horas em que este CNPJ registrou muitas autorizações em sequência com participação de diferentes CRMs. A evidência mostra a diversidade de médicos e o total de prescrições.',
      'O padrão é compatível com lançamento em lote com rodízio de prescritores.',
      'pi-users'
    ),
  }),
  raiox: createCrmTableTooltip(
    'Abrir no Raio-X',
    'Clique na linha para navegar diretamente para a análise detalhada do dia e da hora selecionados.',
    'O Raio-X apresenta as autorizações que compõem o episódio identificado.',
    'pi-search'
  ),
});

const filterOnlyIssues = ref(false);
const showAllCrms     = ref(false);
const expandedAlertasMedico = ref(new Set());
const activeAlertTab  = ref({});

watch(() => props.activeKpiFilter, (newVal) => {
  if (newVal !== null) filterOnlyIssues.value = false;
});

function getAlertasKey(idMedico) {
  const { inicio, fim } = getApiParams();
  return `${props.currentCnpj}|${idMedico}|${inicio ?? ''}|${fim ?? ''}`;
}

function getAlertasDetalhados(idMedico) {
  return cnpjDetailStore.crmMedicoAlertasByKey[getAlertasKey(idMedico)] ?? null;
}

function isAlertasLoading(idMedico) {
  return Boolean(cnpjDetailStore.crmMedicoAlertasLoadingByKey[getAlertasKey(idMedico)]);
}

function getAlertasError(idMedico) {
  return cnpjDetailStore.crmMedicoAlertasErrorByKey[getAlertasKey(idMedico)] ?? null;
}

function requireAlertCount(m, field) {
  if (m[field] == null) {
    throw new Error(`Contrato invalido em crm-data: ${field} obrigatorio para ${m.id_medico}.`);
  }
  return Number(m[field]);
}

function qtdAlertasUnico(m) {
  return requireAlertCount(m, 'qtd_alertas_crm_unico');
}

function qtdAlertasGeo(m) {
  return requireAlertCount(m, 'qtd_alertas_geograficos');
}

function qtdAlertasMultiplos(m) {
  return requireAlertCount(m, 'qtd_alertas_crm_multiplos');
}

/**
 * Itens da coluna Status/Alertas em ordem de gravidade: cadastro CFM, volume
 * intensivo, sequências, distância e exclusividade. As cores seguem a Cronologia
 * (Único CRM laranja, Múltiplos CRMs roxo).
 */
function getStatusItems(m) {
  const items = [];
  if (m.flag_crm_invalido) items.push({ key: 'crm-invalido', label: 'CRM não localizado', tone: 'critico' });
  if (m.flag_prescricao_antes_registro) items.push({ key: 'crm-irregular', label: 'CRM irregular', tone: 'critico' });
  if (m.flag_robo) items.push({ key: 'robo-local', label: 'Mais de 30 presc./dia (local)', tone: 'critico' });
  if (m.flag_robo_oculto && !m.flag_robo) items.push({ key: 'robo-brasil', label: 'Mais de 30 presc./dia (Brasil)', tone: 'medio' });
  if (m.alerta_concentracao_unico_crm) items.push({ key: 'seq-unico', label: 'Sequência · Único CRM', tone: 'unico', count: qtdAlertasUnico(m) });
  if (m.alerta_concentracao_multiplos_crms) items.push({ key: 'seq-multi', label: 'Sequência · Múltiplos CRMs', tone: 'multi', count: qtdAlertasMultiplos(m) });
  if (m.alerta5_geografico) items.push({ key: 'distancia', label: 'Distância > 400 km', tone: 'geo', count: qtdAlertasGeo(m) });
  if (m.flag_crm_exclusivo > 0) items.push({ key: 'exclusivo', label: 'CRM exclusivo', tone: 'exclusivo' });
  return items;
}

// ── Atuação na farmácia ────────────────────────────────────────────────────
function competenciaToIndex(comp) {
  return Math.floor(comp / 100) * 12 + (comp % 100) - 1;
}

function formatCompetencia(comp) {
  return `${String(comp % 100).padStart(2, '0')}/${Math.floor(comp / 100)}`;
}

const periodoMeses = computed(() => {
  const periodo = props.periodoCompetencias;
  if (!periodo) return null;
  const inicio = competenciaToIndex(periodo.inicio);
  const total = competenciaToIndex(periodo.fim) - inicio + 1;
  if (!(total > 0)) throw new Error('Período de competências inválido para a coluna de atuação.');
  return { inicio, total };
});

/**
 * Resumo da atuação do CRM nesta farmácia: período, meses com prescrição e a
 * série mensal desenhada no eixo comum da movimentação da farmácia — assim os mini
 * gráficos ficam alinhados no tempo entre as linhas.
 */
function buildAtuacao(m) {
  const eixo = periodoMeses.value;
  if (!eixo) return null;
  if (m.competencia_inicio_atuacao == null || !Array.isArray(m.serie_mensal_atuacao)) {
    throw new Error(`Contrato invalido em crm-data: atuação obrigatória para ${m.id_medico}.`);
  }
  const inicio = Number(m.competencia_inicio_atuacao);
  const fim = Number(m.competencia_fim_atuacao);
  const meses = Number(m.qtd_meses_atuacao);
  const maximo = Math.max(1, ...m.serie_mensal_atuacao.map(p => Number(p.qtd)));
  const barras = m.serie_mensal_atuacao
    .map(p => ({
      x: competenciaToIndex(Number(p.competencia)) - eixo.inicio,
      h: Math.max(1.5, (Number(p.qtd) / maximo) * 16),
    }))
    .filter(b => b.x >= 0 && b.x < eixo.total);
  return {
    periodo: inicio === fim ? formatCompetencia(inicio) : `${formatCompetencia(inicio)} – ${formatCompetencia(fim)}`,
    meses: `${meses} ${meses === 1 ? 'mês' : 'meses'}`,
    total: eixo.total,
    barras,
  };
}

const atuacaoDialogMedico = ref(null);
const atuacaoDialogVisible = computed({
  get: () => atuacaoDialogMedico.value !== null,
  set: (visible) => { if (!visible) atuacaoDialogMedico.value = null; },
});

function openAtuacaoDialog(m) {
  atuacaoDialogMedico.value = m;
}

// Calculado uma vez por lista (e não a cada binding do template).
const atuacaoByMedico = computed(() => {
  const mapa = new Map();
  for (const m of props.crmsInteresse) mapa.set(m.id_medico, buildAtuacao(m));
  return mapa;
});

function hasAlertasDetalhados(m) {
  return qtdAlertasUnico(m) > 0 || qtdAlertasGeo(m) > 0 || qtdAlertasMultiplos(m) > 0;
}

async function toggleAlertasDiarios(idMedico) {
  if (expandedAlertasMedico.value.has(idMedico)) {
    expandedAlertasMedico.value.delete(idMedico);
  } else {
    expandedAlertasMedico.value.add(idMedico);
    // Define a aba padrão ao abrir: concentração se existir, senão geográfico
    const m = props.crmsInteresse.find(x => x.id_medico === idMedico);
    if (m && !activeAlertTab.value[idMedico]) {
      if (qtdAlertasUnico(m) > 0) activeAlertTab.value[idMedico] = 'conc';
      else if (qtdAlertasGeo(m) > 0) activeAlertTab.value[idMedico] = 'geo';
      else if (qtdAlertasMultiplos(m) > 0) activeAlertTab.value[idMedico] = 'surto';
    }
    expandedAlertasMedico.value = new Set(expandedAlertasMedico.value);
    if (m && hasAlertasDetalhados(m) && !getAlertasDetalhados(idMedico)) {
      const { inicio, fim } = getApiParams();
      await cnpjDetailStore.fetchCrmMedicoAlertas(props.currentCnpj, idMedico, inicio, fim);
    }
  }
  expandedAlertasMedico.value = new Set(expandedAlertasMedico.value);
}

function setAlertTab(idMedico, tab) {
  activeAlertTab.value = { ...activeAlertTab.value, [idMedico]: tab };
}

function handleTimelineNavigation(date, hour) {
  cnpjDetailStore.navigateTimeline(date, hour);
}

function clearAllFilters() {
  filterOnlyIssues.value = false;
  emit('clear-filters');
}

const hasAnyIssue = (m) =>
  m.flag_robo > 0 || m.flag_robo_oculto > 0 || m.alerta_concentracao_unico_crm ||
  m.flag_crm_invalido > 0 || m.flag_prescricao_antes_registro > 0 ||
  m.alerta5_geografico || m.flag_crm_exclusivo > 0 || m.alerta_concentracao_multiplos_crms > 0;

const filteredCrmsInteresse = computed(() => {
  let list = props.crmsInteresse;
  if (filterOnlyIssues.value) list = list.filter(hasAnyIssue);
  if (props.activeKpiFilter && props.kpiFilters[props.activeKpiFilter]) {
    list = list.filter(props.kpiFilters[props.activeKpiFilter]);
  }
  return list;
});

const visibleCrms = computed(() =>
  showAllCrms.value ? filteredCrmsInteresse.value : filteredCrmsInteresse.value.slice(0, 10)
);

function formatarDataAlerta(dt) {
  if (!dt) return "";
  const [y, m, d] = dt.split("-");
  return `${d}/${m}/${y}`;
}

function formatarJanela(minutos) {
  if (!minutos) return "—";
  if (minutos === 0) return "simultâneo";
  if (minutos < 60) return `${minutos}min`;
  return `${Math.floor(minutos / 60)}h ${minutos % 60}min`;
}

function formatDescricao(a) {
  const num = `<span class="desc-num">${a.nu_prescricoes}</span>`;
  if (!a.nu_minutos || a.nu_minutos === 0) {
    return `${num} autorizações de venda <span class="desc-janela">no mesmo instante</span> para o mesmo CRM`;
  }
  const h = Math.floor(a.nu_minutos / 60);
  const min = a.nu_minutos % 60;
  const janela = h > 0 ? `${h}h ${min}min` : `${min}min`;
  const taxa = a.taxa_hora?.toFixed(1) ?? '—';
  return `${num} autorizações de venda <span class="desc-janela">em ${janela} (${taxa}/hora)</span> para o mesmo CRM`;
}

function formatDescricaoSurto(s) {
  return s.descricao || 'Dados não disponíveis';
}
const maxPDOverall = computed(() => {
  if (!props.crmsInteresse?.length) return 40;
  const vals = props.crmsInteresse.flatMap(m => [m.nu_prescricoes_dia, m.prescricoes_dia_total_brasil]);
  return Math.max(...vals, 40);
});
</script>

<template>
  <div class="section-container animate-fade-in" :style="dataColorVars">
    <div class="section-title" style="border-bottom: none; margin-bottom: 0">
      <div style="display: flex; align-items: center; gap: 1.5rem; width: 100%">
        <div style="display: flex; align-items: center; gap: 0.75rem">
          <i class="pi pi-users" />
          <span>CRMs DE INTERESSE - DETALHAMENTO</span>
        </div>
        <div class="filter-controls">
          <label class="filter-toggle">
            <input type="checkbox" v-model="filterOnlyIssues" />
            <span class="toggle-slider"></span>
            <span class="toggle-label">Apenas com Alertas / Anomalias</span>
          </label>
        </div>
      </div>
    </div>

    <p class="subtitle" style="padding-left: 1.75rem; margin-top: -0.5rem; margin-bottom: 1rem">
      Detalhamento dos médicos que mais aprovaram medicamentos nesta unidade, ordenados pelo financeiro.
      <div v-if="activeKpiFilter" class="filter-badge animate-fade-in" v-tooltip.bottom="crmTableTooltips.filterBadge">
        <i class="pi pi-filter-fill" />
        <span class="filter-text">
          <small style="opacity: 0.8; font-weight: 500; margin-right: 2px; text-transform: uppercase; font-size: 0.6rem;">Filtro:</small>
          {{ kpiFilterLabels[activeKpiFilter] }} — <strong class="filter-count">{{ filteredCrmsInteresse.length }} de {{ crmsInteresse.length }}</strong>
        </span>
        <button
          class="clear-filter-btn"
          v-tooltip.top="crmTableTooltips.clearFilter"
          aria-label="Limpar filtro"
          @click.stop="clearAllFilters"
        >
          <i class="pi pi-times" />
        </button>
      </div>
      <span
        v-else-if="filterOnlyIssues && filteredCrmsInteresse.length < crmsInteresse.length"
        class="text-orange"
        style="font-weight: 600; margin-left: 8px"
      >
        (Filtrado: exibindo {{ filteredCrmsInteresse.length }} de {{ crmsInteresse.length }})
      </span>
    </p>

    <div class="table-responsive">
      <table class="ind-table premium-table row-hover">
        <thead class="sticky-thead">
          <tr>
            <th style="width: 45px;" class="col-center">
              #
              <i
                class="pi pi-info-circle th-info-icon"
                v-tooltip.top="crmTableTooltips.columns.rank"
                tabindex="0"
                aria-label="Informações sobre a classificação"
              />
            </th>
            <th style="width: 270px;">
              CRM / Médico
              <i
                class="pi pi-info-circle th-info-icon"
                v-tooltip.top="crmTableTooltips.columns.crm"
                tabindex="0"
                aria-label="Informações sobre CRM e médico"
              />
            </th>
            <th style="width: 19%">
              Status / Alertas
              <i
                class="pi pi-info-circle th-info-icon"
                v-tooltip.top="crmTableTooltips.columns.status"
                tabindex="0"
                aria-label="Informações sobre status e alertas"
              />
            </th>
            <th style="width: 26%">
              Atuação na farmácia
              <i
                class="pi pi-info-circle th-info-icon"
                v-tooltip.top="crmTableTooltips.columns.atuacao"
                tabindex="0"
                aria-label="Informações sobre a atuação na farmácia"
              />
            </th>
            <th class="col-right" style="width: 11%">
              Volume / Valor
              <i
                class="pi pi-info-circle th-info-icon"
                v-tooltip.top="crmTableTooltips.columns.volume"
                tabindex="0"
                aria-label="Informações sobre volume e valor"
              />
            </th>
            <th class="col-center" style="width: 16%">
              Participação no valor
              <i
                class="pi pi-info-circle th-info-icon"
                v-tooltip.top="crmTableTooltips.columns.participation"
                tabindex="0"
                aria-label="Informações sobre a participação no valor"
              />
            </th>
            <th class="col-center" style="width: 11%">
              Prescrições por Dia
              <i
                class="pi pi-info-circle th-info-icon"
                v-tooltip.top="crmTableTooltips.columns.prescriptions"
                tabindex="0"
                aria-label="Informações sobre prescrições por dia"
              />
            </th>
            <th class="col-center" style="width: 6%">
              Exclusividade
              <i
                class="pi pi-info-circle th-info-icon"
                v-tooltip.left="crmTableTooltips.columns.exclusive"
                tabindex="0"
                aria-label="Informações sobre a taxa de exclusividade"
              />
            </th>
          </tr>
        </thead>
        <tbody>
          <template v-for="(m, i) in visibleCrms" :key="i">
            <tr
              :class="{ 'row-expandable': m.alerta_concentracao_unico_crm || m.alerta5_geografico || m.alerta_concentracao_multiplos_crms }"
              @click="hasAlertasDetalhados(m) ? toggleAlertasDiarios(m.id_medico) : null"
            >
              <td class="col-center">
                  <div class="rank-badge" :class="{ 'gold': i === 0, 'silver': i === 1, 'bronze': i === 2 }">
                    <span class="rank-val">{{ (i + 1).toString().padStart(2, '0') }}</span>
                  </div>
              </td>
              <td>
                <div class="med-id-row">
                  <span class="med-id">{{ m.id_medico }}</span>
                  <span class="med-name" :class="{ 'is-missing': !m.no_medico }">
                    {{ m.no_medico ? formatTitleCase(m.no_medico) : 'Não localizado na base do CFM' }}
                  </span>
                </div>
                <div class="med-sub">1ª inscrição UF: {{ m.dt_inscricao_crm ? formatarData(m.dt_inscricao_crm) : 'ND' }}</div>
              </td>
              <td class="flags-cell">
                <div class="status-cell">
                  <ul v-if="getStatusItems(m).length" class="status-list">
                    <li
                      v-for="item in getStatusItems(m)"
                      :key="item.key"
                      class="status-item"
                      :class="`tone-${item.tone}`"
                    >
                      <span class="status-dot" aria-hidden="true" />
                      <span class="status-label">{{ item.label }}</span>
                      <span v-if="item.count > 0" class="status-count">{{ formatNumberFull(item.count) }}×</span>
                    </li>
                  </ul>
                  <span v-else class="status-empty">
                    <i class="pi pi-check-circle" aria-hidden="true" />
                    Sem ocorrências
                  </span>
                  <button
                    v-if="hasAlertasDetalhados(m)"
                    type="button"
                    class="status-expand"
                    :aria-expanded="expandedAlertasMedico.has(m.id_medico)"
                    :aria-label="`${expandedAlertasMedico.has(m.id_medico) ? 'Ocultar' : 'Ver'} evidências de ${m.id_medico}`"
                    @click.stop="toggleAlertasDiarios(m.id_medico)"
                  >
                    <i :class="expandedAlertasMedico.has(m.id_medico) ? 'pi pi-chevron-up' : 'pi pi-chevron-down'" aria-hidden="true" />
                  </button>
                </div>
              </td>
              <td class="atuacao-cell">
                <button
                  v-if="atuacaoByMedico.get(m.id_medico)"
                  type="button"
                  class="atuacao-btn"
                  :aria-label="`Abrir detalhe mensal da atuação de ${m.id_medico}`"
                  @click.stop="openAtuacaoDialog(m)"
                >
                  <i class="pi pi-window-maximize atuacao-expand-icon" aria-hidden="true" />
                  <span class="atuacao-texto">
                    <span class="atuacao-periodo">{{ atuacaoByMedico.get(m.id_medico).periodo }}</span>
                    <span class="atuacao-meses">{{ atuacaoByMedico.get(m.id_medico).meses }}</span>
                  </span>
                  <svg
                    class="atuacao-spark"
                    :viewBox="`0 0 ${atuacaoByMedico.get(m.id_medico).total} 16`"
                    preserveAspectRatio="none"
                    role="img"
                    :aria-label="`Autorizações mensais de ${m.id_medico}: ${atuacaoByMedico.get(m.id_medico).periodo}, ${atuacaoByMedico.get(m.id_medico).meses}`"
                  >
                    <line class="atuacao-base" x1="0" y1="15.75" :x2="atuacaoByMedico.get(m.id_medico).total" y2="15.75" />
                    <rect
                      v-for="barra in atuacaoByMedico.get(m.id_medico).barras"
                      :key="barra.x"
                      class="atuacao-bar"
                      :x="barra.x + 0.1"
                      :y="16 - barra.h"
                      width="0.8"
                      :height="barra.h"
                    />
                  </svg>
                </button>
              </td>
              <td class="col-right">
                <div class="cell-stacked">
                  <span class="cell-main text-primary">{{ formatCurrencyFull(m.vl_total_prescricoes) }}</span>
                  <span class="cell-sub">{{ formatNumberFull(m.nu_prescricoes) }} autorizações</span>
                </div>
              </td>
              <td class="col-center">
                <div class="pareto-cell" :class="{ 'is-nucleo': getParticipacao(m).nucleo }">
                  <div class="pareto-texto">
                    <span class="pareto-parte">{{ formatPct(m.pct_participacao) }}</span>
                    <span class="pareto-acum">
                      <span class="pareto-acum-label">Acumulado</span>
                      <span class="pareto-acum-valor">{{ formatPct(m.pct_acumulado) }}</span>
                    </span>
                  </div>
                  <div
                    class="pareto-track"
                    role="img"
                    :aria-label="`Participação de ${formatPct(m.pct_participacao)}, acumulado de ${formatPct(m.pct_acumulado)} do valor da farmácia`"
                  >
                    <span class="pareto-anterior" :style="{ width: `${getParticipacao(m).anterior}%` }" />
                    <span
                      class="pareto-parte-bar"
                      :style="{ left: `${getParticipacao(m).anterior}%`, width: `${getParticipacao(m).parte}%` }"
                    />
                  </div>
                </div>
              </td>
              <td class="col-center">
                <div class="cell-stacked" style="align-items: center; gap: 0.1rem;">
                  <div :class="{ 'text-red': m.nu_prescricoes_dia > 30 }" style="font-weight: 600; font-size: 0.85rem;">
                    {{ formatNumberFull(m.nu_prescricoes_dia) }} <span style="font-size: 0.68rem; color: var(--text-muted); font-weight: 400">local</span>
                  </div>
                  <div :class="{ 'text-red': m.prescricoes_dia_total_brasil > 30 }" style="font-size: 0.75rem; color: var(--text-secondary);">
                    {{ formatNumberFull(m.prescricoes_dia_total_brasil) }} <span style="font-size: 0.68rem; color: var(--text-muted); font-weight: 400">brasil</span>
                  </div>
                </div>
              </td>
              <td class="col-center">
                <span class="excl-valor" :class="`is-${getExclusividadeNivel(m)}`">{{ formatPct(m.pct_volume_aqui_vs_total) }}</span>
              </td>
            </tr>

            <!-- Linha expandida de alertas (Concentração ou Geográfico) com sistema de abas -->
            <tr v-if="expandedAlertasMedico.has(m.id_medico) && hasAlertasDetalhados(m)" class="alertas-diarios-row">
              <td colspan="11" class="alertas-diarios-cell">
                <div
                  v-if="isAlertasLoading(m.id_medico)"
                  class="evidence-panel"
                >
                  <div class="panel-header">
                    <div class="panel-header-left">
                      <i class="pi pi-spin pi-spinner panel-icon" />
                      <span class="panel-title">Carregando alertas detalhados</span>
                      <span class="panel-crm-badge">{{ m.id_medico }}</span>
                    </div>
                  </div>
                </div>
                <div
                  v-else-if="getAlertasError(m.id_medico)"
                  class="evidence-panel"
                >
                  <div class="panel-header">
                    <div class="panel-header-left">
                      <i class="pi pi-exclamation-triangle panel-icon" />
                      <span class="panel-title">{{ getAlertasError(m.id_medico) }}</span>
                      <span class="panel-crm-badge">{{ m.id_medico }}</span>
                    </div>
                  </div>
                </div>
                <div
                  v-else-if="getAlertasDetalhados(m.id_medico)"
                  class="evidence-panel"
                  :class="{
                    'theme-conc': activeAlertTab[m.id_medico] === 'conc',
                    'theme-geo':  activeAlertTab[m.id_medico] === 'geo',
                    'theme-surto': activeAlertTab[m.id_medico] === 'surto'
                  }"
                >
                  <!-- PANEL HEADER -->
                  <div class="panel-header">
                    <div class="panel-header-left">
                      <i :class="{
                        'pi pi-user': activeAlertTab[m.id_medico] === 'conc',
                        'pi pi-map-marker': activeAlertTab[m.id_medico] === 'geo',
                        'pi pi-users': activeAlertTab[m.id_medico] === 'surto'
                      }" class="panel-icon" />
                      <span class="panel-title">
                        <template v-if="activeAlertTab[m.id_medico] === 'conc'">Lançamentos Sequenciais para um único CRM</template>
                        <template v-else-if="activeAlertTab[m.id_medico] === 'geo'">Evidências de Distância Geográfica</template>
                        <template v-else-if="activeAlertTab[m.id_medico] === 'surto'">Lançamentos Sequenciais com múltiplos CRMs</template>
                      </span>
                      <span class="panel-crm-badge">{{ m.id_medico }}</span>
                    </div>
                    <!-- SEGMENTED CONTROL (Abas Dinâmicas) -->
                    <div class="segmented-control" v-if="(qtdAlertasUnico(m) > 0 ? 1 : 0) + (qtdAlertasGeo(m) > 0 ? 1 : 0) + (qtdAlertasMultiplos(m) > 0 ? 1 : 0) > 1">
                      <button
                        v-if="qtdAlertasUnico(m) > 0"
                        class="segment-btn"
                        :class="{ 'seg-active': activeAlertTab[m.id_medico] === 'conc' }"
                        @click="setAlertTab(m.id_medico, 'conc')"
                      >
                        Autorizações em Sequência (Único CRM)
                        <span class="seg-count">{{ qtdAlertasUnico(m) }}</span>
                        <i
                          class="pi pi-info-circle seg-info-icon"
                          v-tooltip.top="crmTableTooltips.evidence.unico"
                          @click.stop
                        />
                      </button>
                      <button
                        v-if="qtdAlertasGeo(m) > 0"
                        class="segment-btn"
                        :class="{ 'seg-active': activeAlertTab[m.id_medico] === 'geo' }"
                        @click="setAlertTab(m.id_medico, 'geo')"
                      >
                        <i class="pi pi-map-marker" />
                        Distância
                        <span class="seg-count">{{ qtdAlertasGeo(m) }}</span>
                        <i
                          class="pi pi-info-circle seg-info-icon"
                          v-tooltip.top="crmTableTooltips.evidence.distancia"
                          @click.stop
                        />
                      </button>
                      <button
                        v-if="qtdAlertasMultiplos(m) > 0"
                        class="segment-btn"
                        :class="{ 'seg-active': activeAlertTab[m.id_medico] === 'surto' }"
                        @click="setAlertTab(m.id_medico, 'surto')"
                      >
                        Autorizações em Sequência (Múltiplos CRMs)
                        <span class="seg-count">{{ qtdAlertasMultiplos(m) }}</span>
                        <i
                          class="pi pi-info-circle seg-info-icon"
                          v-tooltip.top="crmTableTooltips.evidence.multiplos"
                          @click.stop
                        />
                      </button>
                    </div>
                  </div>

                  <!-- CONTEÚDO: Tabela de Concentração -->
                  <table
                    v-if="activeAlertTab[m.id_medico] === 'conc'"
                    class="evidence-table"
                  >
                    <thead>
                      <tr>
                        <th><i class="pi pi-calendar" /> Data</th>
                        <th><i class="pi pi-id-card" /> CRM</th>
                        <th class="col-right"><i class="pi pi-chart-bar" /> Autorizações</th>
                        <th class="col-center"><i class="pi pi-clock" /> Janela</th>
                        <th class="col-right"><i class="pi pi-chart-line" /> Taxa/hora</th>
                        <th><i class="pi pi-align-left" /> Descrição</th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr v-for="(a, j) in getAlertasDetalhados(m.id_medico).alertas_crm_unico" :key="j" class="alerta-diario-item">
                        <td class="col-date">{{ formatarDataAlerta(a.dt) }}</td>
                        <td class="col-crm">{{ m.id_medico }}</td>
                        <td class="col-right td-metric">{{ a.nu_prescricoes }}</td>
                        <td class="col-center">{{ formatarJanela(a.nu_minutos) }}</td>
                        <td class="col-right td-metric">{{ a.taxa_hora?.toFixed(1) }}/h</td>
                        <td class="col-descricao" v-html="formatDescricao(a)" />
                      </tr>
                    </tbody>
                  </table>

                  <!-- CONTEÚDO: Tabela de Distância Geográfica -->
                  <table
                    v-if="activeAlertTab[m.id_medico] === 'geo'"
                    class="evidence-table"
                  >
                    <thead>
                      <tr>
                        <th style="width: 40%"><i class="pi pi-building" /> Estabelecimento A</th>
                        <th style="width: 40%"><i class="pi pi-building" /> Estabelecimento B</th>
                        <th style="width: 10%" class="col-center"><i class="pi pi-arrows-h" /> Distância</th>
                        <th style="width: 10%" class="col-center"><i class="pi pi-calendar" /> Comp.</th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr v-for="(g, k) in getAlertasDetalhados(m.id_medico).alertas_geograficos" :key="'geo-'+k">
                        <td class="geo-cell">
                          <div class="geo-main">{{ g.municipio_a }}/{{ g.uf_a }}</div>
                          <div class="geo-sub">{{ g.cnpj_a }} · {{ g.nu_presc_a }} presc.</div>
                          <div class="geo-sub">{{ formatarDataAlerta(g.dt_ini_a) }} → {{ formatarDataAlerta(g.dt_fim_a) }}</div>
                        </td>
                        <td class="geo-cell">
                          <div class="geo-main">{{ g.municipio_b }}/{{ g.uf_b }}</div>
                          <div class="geo-sub">{{ g.cnpj_b }} · {{ g.nu_presc_b }} presc.</div>
                          <div class="geo-sub">{{ formatarDataAlerta(g.dt_ini_b) }} → {{ formatarDataAlerta(g.dt_fim_b) }}</div>
                        </td>
                        <td class="col-center">
                          <span class="dist-badge">{{ Math.round(g.distancia_km) }}km</span>
                        </td>
                        <td class="col-center" style="font-size: 0.75rem; color: var(--text-muted);">{{ g.competencia }}</td>
                      </tr>
                    </tbody>
                  </table>

                  <!-- CONTEÚDO: Tabela de Surto Geral -->
                  <table
                    v-if="activeAlertTab[m.id_medico] === 'surto'"
                    class="evidence-table"
                  >
                    <thead>
                      <tr>
                        <th><i class="pi pi-calendar" /> Data</th>
                        <th class="col-center"><i class="pi pi-clock" /> Hora</th>
                        <th class="col-right"><i class="pi pi-user-edit" /> Autorizações CRM</th>
                        <th class="col-right"><i class="pi pi-users" /> Total Hora (CNPJ)</th>
                        <th class="col-center"><i class="pi pi-id-card" /> Diversidade</th>
                        <th><i class="pi pi-align-left" /> Descrição</th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr 
                        v-for="(s, l) in getAlertasDetalhados(m.id_medico).alertas_crm_multiplos" 
                        :key="'surto-'+l"
                        class="clickable-surto-row"
                        v-tooltip.top="crmTableTooltips.raiox"
                        @click="handleTimelineNavigation(s.dt, s.hr)"
                      >
                        <td class="col-date">{{ formatarDataAlerta(s.dt) }}</td>
                        <td class="col-center">
                          <span class="time-badge">{{ s.hr.toString().padStart(2, '0') }}:00h</span>
                        </td>
                        <td class="col-right td-metric">{{ s.nu_presc_crm }}</td>
                        <td class="col-right">{{ s.nu_presc_total }}</td>
                        <td class="col-center">{{ s.nu_crms_total }} CRMs</td>
                        <td class="col-descricao">
                           <span class="surto-desc">{{ formatDescricaoSurto(s) }}</span>
                        </td>
                      </tr>
                    </tbody>
                  </table>

                </div>
              </td>
            </tr>
          </template>
        </tbody>
      </table>
    </div>

    <div class="crm-table-footer">
      <button v-if="filteredCrmsInteresse.length > 10" class="crm-more-btn" @click="showAllCrms = !showAllCrms">
        <template v-if="!showAllCrms">
          <i class="pi pi-angle-double-down" />
          Exibir mais {{ filteredCrmsInteresse.length - 10 }} registros
        </template>
        <template v-else>
          <i class="pi pi-angle-double-up" />
          Recolher
        </template>
      </button>
    </div>

    <CrmAtuacaoDialog
      v-model="atuacaoDialogVisible"
      :medico="atuacaoDialogMedico"
      :cnpj="currentCnpj"
      :periodo="periodoCompetencias"
      :serie-farmacia="serieMensalFarmacia"
    />
  </div>
</template>

<style scoped>
.animate-fade-in { animation: fadeIn 0.3s ease-out; }
@keyframes fadeIn { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: translateY(0); } }

.section-container {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
  background: var(--card-bg);
  border: 1px solid var(--card-border);
  border-radius: 12px;
  padding: 1rem;
  width: 100%;
  box-sizing: border-box;
  overflow: hidden;
}
.section-title {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  font-size: 0.85rem;
  font-weight: 600;
  text-transform: uppercase;
  color: var(--text-color-85);
  margin-bottom: 1rem;
  letter-spacing: 0.05em;
  border-bottom: 1px solid var(--tabs-border);
  padding-bottom: 0.5rem;
  width: 100%;
  opacity: 0.85;
}
.section-title i { color: var(--primary-color); font-size: 1rem; }
.subtitle { margin: 0.25rem 0 0 0; font-size: 0.8rem; color: var(--text-muted); }

.filter-controls { display: flex; align-items: center; gap: 1rem; }
.filter-toggle { display: flex; align-items: center; gap: 0.5rem; cursor: pointer; user-select: none; font-size: 0.75rem; text-transform: none; font-weight: 600; color: var(--text-secondary); }
.filter-toggle input { display: none; }
.toggle-slider { position: relative; width: 32px; height: 18px; background-color: var(--tabs-border); border: 1px solid var(--tabs-border); border-radius: 20px; transition: 0.3s; }
.toggle-slider:before { content: ""; position: absolute; height: 12px; width: 12px; left: 3px; bottom: 3px; background-color: white; border-radius: 50%; transition: 0.3s; }
input:checked + .toggle-slider { background-color: var(--primary-color); }
input:checked + .toggle-slider:before { transform: translateX(14px); }
.toggle-label { letter-spacing: normal; }

.filter-badge {
  display: inline-flex;
  align-items: center;
  gap: 0.6rem;
  padding: 0.25rem 0.4rem 0.25rem 0.75rem;
  background: color-mix(in srgb, var(--risk-high) 12%, transparent);
  border: 1px solid color-mix(in srgb, var(--risk-high) 35%, transparent);
  border-radius: 99px;
  color: var(--risk-high);
  font-size: 0.72rem;
  font-weight: 600;
  margin-left: 1rem;
  box-shadow: 0 4px 12px rgba(0,0,0,0.15);
  position: relative;
  overflow: hidden;
  backdrop-filter: blur(8px);
  -webkit-backdrop-filter: blur(8px);
}
.filter-badge::after {
  content: "";
  position: absolute;
  top: 0; left: -100%;
  width: 100%; height: 100%;
  background: linear-gradient(90deg, transparent, rgba(255,255,255,0.05), rgba(255,255,255,0.2), rgba(255,255,255,0.05), transparent);
  animation: shimmer-sweep 4s infinite ease-in-out;
}
@keyframes shimmer-sweep { 0% { left: -100%; } 15% { left: 100%; } 100% { left: 100%; } }
.filter-badge i.pi-filter-fill { font-size: 0.65rem; opacity: 0.8; animation: icon-spin-subtle 4s infinite ease-in-out; }
@keyframes icon-spin-subtle { 0%, 70% { transform: rotate(0deg); } 85% { transform: rotate(-360deg); } 100% { transform: rotate(-360deg); } }
.filter-text { letter-spacing: 0.02em; }
.filter-count { font-weight: 600; margin-left: 0.2rem; }
.clear-filter-btn { display: flex; align-items: center; justify-content: center; width: 18px; height: 18px; background: color-mix(in srgb, var(--risk-high) 15%, transparent); color: var(--risk-high); border: none; border-radius: 50%; cursor: pointer; transition: all 0.2s ease; padding: 0; }
.clear-filter-btn:hover { background: var(--risk-high); color: white; }
.clear-filter-btn i { font-size: 0.55rem; font-weight: 900; }

.table-responsive { overflow-x: auto; border-top: 1px solid var(--tabs-border); border-bottom: 1px solid var(--tabs-border); min-height: 35rem; }

.premium-table { width: 100%; border-collapse: collapse; table-layout: fixed; }
.premium-table th { padding: 0.6rem 0.5rem; background: transparent; color: color-mix(in srgb, var(--text-secondary) 85%, transparent); font-size: 0.68rem; font-weight: 500; text-transform: uppercase; letter-spacing: 0.02em; border-bottom: 2px solid var(--tabs-border); text-align: center; }
.premium-table th:first-child { text-align: left; }
.th-info-icon { font-size: 0.72rem; margin-left: 0.25rem; opacity: 0.6; cursor: help; vertical-align: middle; transition: opacity 0.2s ease, color 0.2s ease; }
.th-info-icon:hover { opacity: 1; color: var(--primary-color); }
.premium-table td { padding: 0.55rem 0.5rem; border-bottom: 1px solid var(--tabs-border); vertical-align: middle; color: color-mix(in srgb, var(--text-color-85) 85%, transparent); font-size: 0.8rem; text-transform: none !important; }
.premium-table th:nth-child(2), .premium-table td:nth-child(2) { text-align: left; overflow: hidden; text-overflow: ellipsis; }
.premium-table tbody tr:last-child td { border-bottom: none; }
.premium-table.row-hover tbody tr:hover { background: var(--table-hover) !important; cursor: pointer; }

.sticky-thead th { position: sticky; top: 0; z-index: 10; box-shadow: 0 2px 4px rgba(0, 0, 0, 0.2); }

.col-center { text-align: center; }
.col-right { text-align: right; }

.cell-stacked { display: flex; flex-direction: column; align-items: flex-end; gap: 0.15rem; line-height: 1.2; }
.cell-main { font-size: 0.85rem; font-weight: 600; }
.cell-sub { font-size: 0.7rem; color: var(--text-muted); font-weight: 400; opacity: 0.8; }

.pareto-cell { display: flex; flex-direction: column; gap: 0.5rem; width: 100%; }
.pareto-texto {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 0.5rem;
  white-space: nowrap;
}
.pareto-parte { font-size: 0.85rem; font-weight: 500; color: var(--text-color-85); }
.pareto-acum { display: inline-flex; align-items: baseline; gap: 0.35rem; }
.pareto-acum-label {
  font-size: 0.62rem;
  font-weight: 600;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--text-muted);
}
.pareto-acum-valor { font-size: 0.85rem; font-weight: 500; color: var(--text-secondary); }
.pareto-track {
  position: relative;
  height: 14px;
  border-radius: 7px;
  overflow: hidden;
  background: color-mix(in srgb, var(--text-color-85) 7%, transparent);
}
.pareto-anterior {
  position: absolute;
  inset: 0 auto 0 0;
  background: color-mix(in srgb, var(--text-color-85) 26%, transparent);
}
.pareto-parte-bar {
  position: absolute;
  top: 0;
  bottom: 0;
  min-width: 2px;
  border-radius: 2px;
  background: var(--data-color-soft);
  transition: left 0.4s ease, width 0.4s ease;
}
.pareto-cell.is-nucleo .pareto-parte-bar { background: var(--data-color); }

.med-id-row {
  display: flex;
  align-items: baseline;
  gap: 0.4rem;
  min-width: 0;
  margin-bottom: 0.1rem;
}
.med-id {
  flex-shrink: 0;
  font-weight: 600;
  font-size: 0.88rem;
  color: var(--text-color);
  text-transform: uppercase;
  letter-spacing: 0.01em;
}
.med-name {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 0.8rem;
  font-weight: 500;
  color: var(--text-color-85);
}
.med-name::before {
  content: '·';
  margin-right: 0.4rem;
  color: var(--text-muted);
}
.med-name.is-missing {
  font-style: italic;
  font-weight: 400;
  color: var(--text-muted);
}
.med-sub { font-size: 0.72rem; color: var(--text-muted); font-weight: 400; opacity: 0.8; }

.status-cell {
  display: flex;
  align-items: flex-start;
  gap: 0.5rem;
}
.status-list {
  flex: 1 1 auto;
  min-width: 0;
  margin: 0;
  padding: 0;
  list-style: none;
  display: grid;
  gap: 0.2rem;
}
.status-item {
  --tone: var(--text-muted);
  display: grid;
  grid-template-columns: 8px minmax(0, 1fr) auto;
  align-items: center;
  column-gap: 0.5rem;
  font-size: 0.76rem;
  line-height: 1.35;
  color: var(--text-color-85);
}
.status-item.tone-critico { --tone: var(--risk-critical); }
.status-item.tone-medio { --tone: #f97316; }
.status-item.tone-unico { --tone: #f59e0b; }
.status-item.tone-multi { --tone: #8b5cf6; }
.status-item.tone-geo { --tone: #14b8a6; }
.status-item.tone-exclusivo { --tone: #3b82f6; }
.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--tone);
}
.status-label {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-weight: 500;
}
.status-item.tone-critico .status-label { color: var(--tone); }
.status-count {
  min-width: 3.2rem;
  text-align: right;
  font-size: 0.72rem;
  font-weight: 600;
  color: var(--text-secondary);
}
.status-empty {
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
  font-size: 0.74rem;
  color: var(--text-muted);
}
.status-expand {
  flex-shrink: 0;
  width: 24px;
  height: 24px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border: 1px solid var(--card-border);
  border-radius: 6px;
  background: transparent;
  color: var(--text-secondary);
  cursor: pointer;
  transition: color 0.15s ease, border-color 0.15s ease;
}
.status-expand i { font-size: 0.6rem; }
.status-expand:hover,
.status-expand[aria-expanded="true"] {
  color: var(--primary-color);
  border-color: var(--primary-color);
}
.status-expand:focus-visible {
  outline: 2px solid color-mix(in srgb, var(--primary-color) 70%, transparent);
  outline-offset: 2px;
}
.atuacao-cell { vertical-align: middle; }
.atuacao-btn {
  position: relative;
  display: block;
  width: 100%;
  padding: 0.35rem 0.5rem;
  margin: -0.35rem -0.5rem;
  box-sizing: content-box;
  border: 1px solid transparent;
  border-radius: 8px;
  background: transparent;
  color: inherit;
  font: inherit;
  text-align: left;
  cursor: pointer;
  transition: border-color 0.15s ease, background 0.15s ease;
}
.atuacao-btn:hover,
.atuacao-btn:focus-visible {
  border-color: color-mix(in srgb, var(--primary-color) 45%, transparent);
  background: color-mix(in srgb, var(--primary-color) 5%, transparent);
  outline: none;
}
.atuacao-expand-icon {
  position: absolute;
  top: 0.35rem;
  right: 0.45rem;
  font-size: 0.62rem;
  color: var(--text-muted);
  opacity: 0;
  transition: opacity 0.15s ease;
}
.atuacao-btn:hover .atuacao-expand-icon,
.atuacao-btn:focus-visible .atuacao-expand-icon { opacity: 1; }
.atuacao-btn .atuacao-texto { padding-right: 1rem; }
.atuacao-texto {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 0.5rem;
  margin-bottom: 0.3rem;
  white-space: nowrap;
}
.atuacao-periodo { font-size: 0.76rem; font-weight: 500; color: var(--text-color-85); }
.atuacao-meses { font-size: 0.7rem; color: var(--text-muted); }
.atuacao-spark { display: block; width: 100%; height: 35px; overflow: visible; }
.atuacao-base { stroke: var(--card-border); stroke-width: 0.5; vector-effect: non-scaling-stroke; }
.atuacao-bar { fill: var(--data-color); }
.row-expandable { cursor: pointer; user-select: none; }
.excl-valor {
  display: inline-block;
  padding: 0.12rem 0.5rem;
  border-radius: 999px;
  font-size: 0.8rem;
  font-weight: 400;
  color: var(--text-secondary);
  border: 1px solid transparent;
}
.excl-valor.is-atencao { font-weight: 600; color: var(--text-color-85); }
.excl-valor.is-alto {
  font-weight: 600;
  color: var(--risk-critical);
  background: color-mix(in srgb, var(--risk-critical) 12%, transparent);
  border-color: color-mix(in srgb, var(--risk-critical) 30%, transparent);
}

.text-red { color: var(--risk-critical) !important; }
.text-orange { color: var(--risk-medium) !important; }

.alertas-diarios-row,
.premium-table.row-hover tbody tr.alertas-diarios-row:hover { background: transparent !important; cursor: default !important; }
.alertas-diarios-cell { padding: 0.75rem 1rem !important; border-bottom: 2px solid var(--tabs-border) !important; background: transparent !important; }

/* ── Rank & Medals ──────────────────────────────────────────────────────── */
/* ── Rank Styling (Modern Squircle) ─────────────────────────────────────── */
.rank-badge {
  width: 32px;
  height: 24px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 6px;
  background: rgba(148, 163, 184, 0.05);
  border: 1px solid rgba(148, 163, 184, 0.1);
  position: relative;
  transition: all 0.3s ease;
}
.rank-val {
  font-family: var(--font-mono);
  font-size: 0.75rem;
  font-weight: 700;
  color: var(--text-muted);
  letter-spacing: -0.02em;
}

/* Estilos de Destaque para o Top 3 */
.rank-badge.gold {
  background: rgba(255, 215, 0, 0.08);
  border-color: rgba(255, 215, 0, 0.4);
  box-shadow: 0 0 12px rgba(255, 215, 0, 0.1);
}
.rank-badge.gold .rank-val { color: #d4af37; }

.rank-badge.silver {
  background: rgba(192, 192, 192, 0.1);
  border-color: rgba(192, 192, 192, 0.4);
}
.rank-badge.silver .rank-val { color: #94a3b8; }

.rank-badge.bronze {
  background: rgba(205, 127, 50, 0.08);
  border-color: rgba(205, 127, 50, 0.4);
}
.rank-badge.bronze .rank-val { color: #a0522d; }

/* Efeito Hover na Linha realça o Rank */
tr:hover .rank-badge {
  transform: translateX(2px);
  border-color: var(--primary-color);
}
tr:hover .rank-badge .rank-val { color: var(--primary-color); }

.alertas-diarios-cell {
  background: var(--card-bg) !important;
  padding: 1.25rem !important;
  border-bottom: 1px solid var(--tabs-border);
}
.col-date { font-weight: 400; white-space: nowrap; }
.col-crm { white-space: nowrap; color: var(--text-secondary); font-size: 0.75rem; }
.col-descricao { color: var(--text-secondary); font-size: 0.75rem; }
.col-descricao .desc-num { color: var(--primary-color); font-weight: 500; }
.col-descricao .desc-janela { color: var(--risk-high); font-weight: 500; }

.crm-table-footer { background: var(--card-bg); border-bottom: 1px solid color-mix(in srgb, var(--card-border) 60%, transparent); display: flex; justify-content: center; padding: 0.35rem 0; }
.crm-more-btn { background: none; border: none; font-size: 0.65rem; font-weight: 500; color: var(--primary-color); text-transform: uppercase; letter-spacing: 0.05em; cursor: pointer; display: inline-flex; align-items: center; gap: 0.4rem; padding: 0.2rem 1rem; border-radius: 4px; transition: all 0.2s; opacity: 0.85; }
.crm-more-btn:hover { opacity: 1; background: color-mix(in srgb, var(--primary-color) 8%, transparent); letter-spacing: 0.08em; }
.crm-more-btn i { font-size: 0.7rem; }

/* Estilos da Tabela Geográfica */
.geo-cell { line-height: 1.4; padding: 0.6rem 0.75rem !important; }
.geo-main { font-weight: 600; color: var(--text-color-85); font-size: 0.8rem; opacity: 0.85; }
.geo-sub { font-size: 0.68rem; color: var(--text-color-85); opacity: 0.75; }

.dist-badge {
  background: rgba(239, 68, 68, 0.1);
  color: #ef4444;
  padding: 2px 6px;
  border-radius: 4px;
  font-weight: 600;
  border: 1px solid rgba(239, 68, 68, 0.2);
}

/* ── Evidence Panel (Design Premium) ───────────────────────────────── */
.evidence-panel {
  background: var(--table-expansion-bg);
  border-radius: 8px;
  border: 1px solid var(--card-border);
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.2);
}
.theme-conc { border-left-color: var(--risk-medium) !important; }
.theme-geo { border-left-color: #8b5cf6 !important; }
.theme-surto { border-left-color: var(--amber-500) !important; }

/* Header do painel */
.panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0.65rem 1rem;
  background: color-mix(in srgb, var(--table-expansion-bg) 92%, var(--text-color-85) 8%);
  border-bottom: 1px solid var(--tabs-border);
  gap: 1rem;
}
.panel-header-left {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  min-width: 0;
}
.panel-icon {
  font-size: 0.8rem;
  color: var(--primary-color);
  flex-shrink: 0;
}

.panel-title {
  font-size: 0.7rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.07em;
  color: var(--text-secondary);
  white-space: nowrap;
}
.panel-crm-badge {
  font-size: 0.65rem;
  font-weight: 600;
  color: var(--text-muted);
  background: color-mix(in srgb, var(--text-color-85) 8%, transparent);
  border: 1px solid var(--tabs-border);
  border-radius: 4px;
  padding: 1px 6px;
  font-family: var(--font-mono, monospace);
}

/* Segmented Control (Refatorado para 3+ abas) */
.segmented-control {
  display: flex;
  align-items: center;
  background: color-mix(in srgb, var(--text-color-85) 7%, transparent);
  border: 1px solid var(--tabs-border);
  border-radius: 8px;
  padding: 3px;
  gap: 2px;
  flex-shrink: 0;
}

.segment-btn {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  padding: 0.3rem 0.8rem;
  background: none;
  border: none;
  border-radius: 6px;
  font-size: 0.68rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--text-muted);
  cursor: pointer;
  position: relative;
  z-index: 1;
  transition: all 0.2s ease;
  white-space: nowrap;
}
.segment-btn:hover { background: color-mix(in srgb, var(--text-color-85) 5%, transparent); }
.segment-btn.seg-active { 
  background: var(--card-bg);
  color: var(--primary-color); 
  box-shadow: 0 1px 4px rgba(0,0,0,0.15);
  border: 1px solid var(--tabs-border);
}
.segment-btn i { font-size: 0.68rem; }

.seg-count {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 16px;
  height: 14px;
  padding: 0 4px;
  background: color-mix(in srgb, var(--primary-color) 12%, transparent);
  color: var(--primary-color);
  border-radius: 99px;
  font-size: 0.58rem;
  font-weight: 600;
}

/* Tabela de evidências (unificada) */
.evidence-table {
  width: 100%;
  border-collapse: collapse;
  background: transparent;
  font-size: 0.78rem;
}
.evidence-table thead tr,
.evidence-table thead tr:hover,
.evidence-table thead tr th,
.evidence-table thead tr:hover th {
  background: color-mix(in srgb, var(--text-color-85) 4%, transparent) !important;
}
.evidence-table th {
  padding: 0.3rem 0.75rem;
  font-size: 0.65rem;
  font-weight: 600;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  text-align: left;
  border-bottom: 1px solid var(--tabs-border);
  cursor: default;
  user-select: none;
}
.evidence-table td {
  padding: 0.45rem 0.75rem;
  border-top: 1px solid var(--tabs-border);
  color: var(--text-color-85);
  opacity: 0.85;
}
.evidence-table tbody tr:nth-child(even) { background: color-mix(in srgb, var(--text-color-85) 2%, transparent); }
.evidence-table tbody tr:hover { background: color-mix(in srgb, var(--text-color-85) 5%, transparent); }
.theme-conc .evidence-table tbody tr:hover { background: color-mix(in srgb, var(--risk-medium) 8%, transparent); }
.theme-surto .evidence-table tbody tr:hover { background: color-mix(in srgb, var(--amber-500) 8%, transparent); }



.time-badge {
  background: color-mix(in srgb, var(--text-color-85) 7%, transparent);
  padding: 1px 5px;
  border-radius: 4px;
  font-weight: 600;
  font-size: 0.72rem;
  font-family: monospace;
}
.surto-desc { 
  font-size: 0.72rem; 
  opacity: 0.85; 
  line-height: 1.3; 
  display: block; 
  max-width: 400px;
  white-space: normal; 
}
.theme-surto .panel-icon { color: var(--amber-500); }
.theme-surto .seg-active { color: var(--amber-500) !important; }
.theme-surto .td-metric { color: var(--amber-500); font-weight: 600; }
.theme-geo .panel-icon { color: #8b5cf6; }
.theme-geo .seg-active { color: #8b5cf6 !important; }
.theme-conc .panel-icon { color: var(--risk-medium); }
.theme-conc .seg-active { color: var(--risk-medium) !important; }
.theme-conc .td-metric { color: var(--risk-medium); font-weight: 600; }

.clickable-surto-row {
  cursor: pointer;
  transition: background 0.2s ease;
}

/* Ícones de informação no cabeçalho da tabela */
.th-info-icon {
  font-size: 0.68rem;
  opacity: 0.7;
  margin-left: 0.3rem;
  cursor: help;
  outline: none;
  vertical-align: middle;
  color: var(--primary-color);
  transition: opacity 0.15s ease, color 0.15s ease;
}
th:hover .th-info-icon {
  opacity: 1;
}
.th-info-icon:focus-visible {
  outline: 2px solid color-mix(in srgb, var(--primary-color) 70%, transparent);
  outline-offset: 2px;
  border-radius: 50%;
}

/* Ícones de informação nos botões do segmented control */
.seg-info-icon {
  font-size: 0.65rem;
  opacity: 0.65;
  margin-left: 0.25rem;
  cursor: help;
  vertical-align: middle;
  color: inherit;
  transition: opacity 0.15s ease;
}
.segment-btn:hover .seg-info-icon {
  opacity: 1;
}

:global(.p-tooltip.crm-profile-info-tooltip) {
  max-width: min(360px, calc(100vw - 2rem));
  padding: 0;
  background: var(--tooltip-bg);
  border: 1px solid var(--tooltip-border);
  border-radius: 9px;
  box-shadow: var(--tooltip-shadow);
}

:global(.crm-profile-tooltip-content) {
  display: flex;
  width: min(330px, calc(100vw - 2rem));
  flex-direction: column;
  gap: 0.62rem;
  padding: 0.75rem 0.85rem;
  line-height: 1.42;
}

:global(.crm-profile-tooltip-heading) {
  display: flex;
  align-items: center;
  gap: 0.45rem;
  color: var(--text-color-85);
  font-size: 0.8rem;
  font-weight: 700;
  letter-spacing: 0.025em;
}

:global(.crm-profile-tooltip-heading i) {
  flex-shrink: 0;
  color: var(--risk-medium);
  font-size: 0.8rem;
}

:global(.crm-profile-tooltip-body) {
  margin: 0;
  color: var(--text-secondary);
  font-size: 0.72rem;
}

:global(.crm-profile-tooltip-note) {
  display: flex;
  flex-direction: column;
  gap: 0.2rem;
  padding-top: 0.55rem;
  border-top: 1px solid var(--tabs-border);
  color: var(--text-secondary);
  font-size: 0.68rem;
}

:global(.crm-profile-tooltip-note strong) {
  color: var(--risk-medium);
  font-size: 0.65rem;
  font-weight: 700;
  letter-spacing: 0.04em;
  text-transform: uppercase;
}
</style>
