<script setup>
import { computed, ref, watch } from "vue";
import { storeToRefs } from 'pinia';
import { useCnpjDetailStore } from '@/stores/cnpjDetail';
import { useFilterStore } from '@/stores/filters';
import { useThemeStore } from '@/stores/theme';
import { useDelayedLoading } from '@/composables/useDelayedLoading';
import { useFormatting } from "@/composables/useFormatting";
import { useChartTheme } from '@/config/chartTheme';
import { API_ENDPOINTS } from '@/config/api';
import TabPlaceholder from './TabPlaceholder.vue';

import VChart from 'vue-echarts';
import { use } from 'echarts/core';
import { BarChart, LineChart } from 'echarts/charts';
import { GridComponent, TooltipComponent, DataZoomComponent, MarkLineComponent, LegendComponent } from 'echarts/components';
import { CanvasRenderer } from 'echarts/renderers';

use([BarChart, LineChart, GridComponent, TooltipComponent, DataZoomComponent, MarkLineComponent, LegendComponent, CanvasRenderer]);

const props = defineProps({
  cnpj: { type: String, required: true },
  periodSummary: { type: Object, default: null },
  periodLoading: { type: Boolean, default: false },
});

const cnpjDetailStore = useCnpjDetailStore();
const filterStore = useFilterStore();
const {
  crmTimelineDataset,
  crmTimelineDatasetLoading,
  selectedTimelineEvent,
} = storeToRefs(cnpjDetailStore);
const { formatarData, toLocalISO } = useFormatting();
const { chartTheme, chartUFAccents } = useChartTheme();
const themeStore = useThemeStore();
const raioxBg = computed(() => themeStore.isDark ? 'rgba(0,0,0,0.15)' : 'rgba(255,255,255,0.6)');

const formattedPeriod = computed(() => {
  const [start, end] = filterStore.periodo ?? [];
  if (!start || !end) return null;
  return { start: formatarData(toLocalISO(start)), end: formatarData(toLocalISO(end)) };
});

const noMovementInPeriod = computed(() =>
  !props.periodLoading &&
  Boolean(props.periodSummary) &&
  Number(props.periodSummary.totalMov ?? 0) === 0
);

// ── Flicker-Free Cache ────────────────────────────────────────────────────
const cachedCrmTimelineDataset = ref(crmTimelineDataset.value);

const showRefreshingDaily  = useDelayedLoading(crmTimelineDatasetLoading);
const showRefreshingHourly = useDelayedLoading(crmTimelineDatasetLoading);

watch([crmTimelineDataset, crmTimelineDatasetLoading], ([newData, loading]) => {
  if (newData && !loading) cachedCrmTimelineDataset.value = newData;
}, { immediate: true });

const timelineDailyDataset = computed(() => ({
  cnpj: cachedCrmTimelineDataset.value?.cnpj ?? props.cnpj,
  days: cachedCrmTimelineDataset.value?.days ?? [],
}));

const timelineHourlyDataset = computed(() => {
  const days = cachedCrmTimelineDataset.value?.days ?? [];
  return {
    cnpj: cachedCrmTimelineDataset.value?.cnpj ?? props.cnpj,
    points: days.flatMap(day => day.hours),
    events: days.flatMap(day => day.events),
  };
});

const timelineDatasetReady = computed(() => Boolean(cachedCrmTimelineDataset.value));

function normalizeDailyDay(d) {
  return {
    ...d,
    is_volume_horario_anomalo: d.is_dia_com_volume_horario_anomalo,
    is_crm_unico: d.is_anomalo_unico,
    is_crm_multiplo: d.is_crm_multiplo ?? 0,
    is_anomalo: d.is_dia_com_volume_horario_anomalo || d.is_anomalo_unico || d.is_crm_multiplo ? 1 : 0,
  };
}

// Série unificada: cada dia já traz volume anômalo, CRM único e CRM múltiplo
// Não há mais necessidade de merge entre dois caches distintos.
const unifiedDays = computed(() =>
  (timelineDailyDataset.value?.days ?? []).map(normalizeDailyDay)
);


// Índice por data para lookup O(1) no tooltip (evita scan linear a cada hover)
const hourlyByDate = computed(() => {
  const map = new Map();
  for (const pt of timelineHourlyDataset.value?.points ?? []) {
    const key = String(pt.dt_janela).slice(0, 10);
    if (!map.has(key)) map.set(key, []);
    map.get(key).push(pt);
  }
  return map;
});

// ── Filtro e Zoom do Gráfico Diário ───────────────────────────────────────
const filterDailyOnlyAnomalous = ref(false);
const dailyRankMode = ref(null);
const dailyRankLimit = ref(10);
const dailyZoomStart = ref(0);
const dailyZoomEnd = ref(100);
const dailyRankLimitOptions = [
  { label: 'Top 10', value: 10 },
  { label: 'Top 20', value: 20 },
  { label: 'Top 50', value: 50 },
  { label: 'Todos', value: 0 },
];
const DAILY_RANK_VISIBLE_LIMIT = 50;

const volumeScoreByDate = computed(() => {
  const map = new Map();
  for (const pt of timelineHourlyDataset.value?.points ?? []) {
    if (pt.is_volume_horario_anomalo !== 1) continue;
    const key = String(pt.dt_janela).slice(0, 10);
    const nuPrescricoes = Number(pt.nu_prescricoes ?? 0);
    const mediana = Math.max(Number(pt.mediana_hora ?? 0), 1);
    const score = nuPrescricoes / mediana;
    const current = map.get(key);
    if (!current || score > current.score) {
      map.set(key, {
        score,
        hr_janela: pt.hr_janela,
        nu_prescricoes: nuPrescricoes,
        mediana_hora: mediana,
      });
    }
  }
  return map;
});

function getDailyRankScore(day, mode) {
  if (mode === 'unico') return Number(day.score_crm_unico_hora ?? 0);
  if (mode === 'multiplo') return Number(day.score_crm_multiplo_hora ?? 0);
  if (mode === 'volume') return Number(volumeScoreByDate.value.get(day.dt_janela)?.score ?? 0);
  return 0;
}

function formatVolumeMultiplier(value) {
  const score = Number(value ?? 0);
  if (score <= 0) return '';
  return score.toFixed(1);
}

const dailyRankedDays = computed(() => {
  if (!dailyRankMode.value) return [];
  const ranked = unifiedDays.value
    .map(day => ({ ...day, _rankScore: getDailyRankScore(day, dailyRankMode.value) }))
    .filter(day => day._rankScore > 0)
    .sort((a, b) => {
      const scoreDiff = b._rankScore - a._rankScore;
      if (scoreDiff !== 0) return scoreDiff;
      return String(b.dt_janela).localeCompare(String(a.dt_janela));
    });

  return dailyRankLimit.value > 0 ? ranked.slice(0, dailyRankLimit.value) : ranked;
});

function formatDailyRankMetric(day, mode = dailyRankMode.value) {
  if (!day || !mode) return '';
  if (mode === 'unico') {
    const qtd = day.score_crm_unico_qtd;
    const score = Number(day.score_crm_unico_hora ?? 0);
    const min = qtd && score ? Math.round((Number(qtd) * 60) / score) : 0;
    return score ? `${score.toFixed(1)}/h${qtd && min ? ` (${qtd} em ${min}min)` : ''}` : '';
  }
  if (mode === 'multiplo') {
    const qtd = day.score_crm_multiplo_qtd;
    const min = day.score_crm_multiplo_minutos;
    const crms = day.score_crm_multiplo_crms;
    const score = Number(day.score_crm_multiplo_hora ?? 0);
    return score ? `${score.toFixed(1)}/h${qtd && min ? ` (${qtd} em ${min}min)` : ''}${crms ? ` · ${crms} CRMs` : ''}` : '';
  }
  if (mode === 'volume') {
    const info = volumeScoreByDate.value.get(day.dt_janela);
    const scoreLabel = formatVolumeMultiplier(info?.score);
    if (!scoreLabel) return '';
    return `${scoreLabel}x · ${String(info.hr_janela).padStart(2, '0')}h`;
  }
  return '';
}

function formatDailyRankBadge(day, mode = dailyRankMode.value) {
  if (!day || !mode) return '';
  if (mode === 'unico') {
    const score = Number(day.score_crm_unico_hora ?? 0);
    return score ? `${Math.round(score)}/h` : '';
  }
  if (mode === 'multiplo') {
    const score = Number(day.score_crm_multiplo_hora ?? 0);
    return score ? `${Math.round(score)}/h` : '';
  }
  if (mode === 'volume') {
    const info = volumeScoreByDate.value.get(day.dt_janela);
    const scoreLabel = formatVolumeMultiplier(info?.score);
    return scoreLabel ? `${scoreLabel}x` : '';
  }
  return '';
}

function toggleDailyRankMode(mode) {
  dailyRankMode.value = dailyRankMode.value === mode ? null : mode;
  if (dailyRankMode.value) filterDailyOnlyAnomalous.value = false;
  selectedDay.value = null;
  selectedHourlyHour.value = null;
  dailyZoomStart.value = 0;
  dailyZoomEnd.value = 100;
}

function setDailyZoomWindow(total, centerIdx = null, maxVisible = 30) {
  if (total <= 0) return;

  const visible = Math.min(total, maxVisible);
  let startIdx;
  let endIdx;

  if (centerIdx === null) {
    endIdx = total;
    startIdx = Math.max(0, total - visible);
  } else {
    const halfWindow = visible / 2;
    startIdx = Math.max(0, centerIdx - halfWindow);
    endIdx = Math.min(total, startIdx + visible);
    if (endIdx === total) startIdx = Math.max(0, total - visible);
  }

  dailyZoomStart.value = (startIdx / total) * 100;
  dailyZoomEnd.value = (endIdx / total) * 100;
}

const filteredDailyDays = computed(() => {
  if (dailyRankMode.value) {
    if (dailyRankLimit.value > 0) return dailyRankedDays.value;
    return [...dailyRankedDays.value].sort((a, b) => String(a.dt_janela).localeCompare(String(b.dt_janela)));
  }
  if (!filterDailyOnlyAnomalous.value) return unifiedDays.value;
  return unifiedDays.value.filter(d => d.is_volume_horario_anomalo === 1 || d.is_crm_unico === 1 || d.is_crm_multiplo === 1);
});

const dailyDates     = computed(() => filteredDailyDays.value.map(d => d.dt_janela));
const dailyValues    = computed(() => filteredDailyDays.value.map(d => d.nu_prescricoes_dia));
const dailyAnomalous = computed(() => filteredDailyDays.value.map(d => d.is_anomalo === 1));
const dailyMedians   = computed(() => filteredDailyDays.value.map(d => d.mediana_diaria ?? 0));

// Zoom inicial e centralização são controlados pelo watch(filteredDailyDays) abaixo.

function onDailyZoom(params) {
  if (params.batch) {
    dailyZoomStart.value = params.batch[0].start;
    dailyZoomEnd.value = params.batch[0].end;
  } else {
    dailyZoomStart.value = params.start;
    dailyZoomEnd.value = params.end;
  }
}

// Navegação mensal manual
function shiftZoom(direction) {
  const totalDays = dailyDates.value.length;
  if (totalDays === 0) return;

  const currentSpan = dailyZoomEnd.value - dailyZoomStart.value;
  const monthPercent = (30 / totalDays) * 100;
  
  let newStart, newEnd;

  if (direction === 'next') {
    newEnd = Math.min(100, dailyZoomEnd.value + monthPercent);
    newStart = Math.max(0, newEnd - currentSpan);
  } else {
    newStart = Math.max(0, dailyZoomStart.value - monthPercent);
    newEnd = Math.min(100, newStart + currentSpan);
  }

  dailyZoomStart.value = newStart;
  dailyZoomEnd.value = newEnd;
}

// ── Drill-down Horário ────────────────────────────────────────────────────
const selectedDay = ref(null);
const selectedHourlyHour = ref(null);
const hourlyTransactions = ref([]);
const hourlyTransactionsLoading = ref(false);
const hoveredAlert = ref(null);
const raioxCache = new Map();
const raioxRequests = new Map();
const activeRaioxKey = ref(null);

// CRM Único: refs declaradas aqui (antes dos watches) para evitar TDZ quando o
// watch com immediate:true dispara durante o setup com dados já em cache.
const unicoAlertas = ref([]);
const multiAlertas = ref([]);

const unicoAlertasAgrupados = computed(() => {
  const grupos = new Map();

  unicoAlertas.value.forEach((alerta, index) => {
    const idMedico = String(alerta.id_medico || 'CRM nao informado');
    const alertaNormalizado = {
      ...alerta,
      id_medico: idMedico,
      numero_alerta: index + 1,
      ritmo_qtd_display: alerta.ritmo_qtd ?? alerta.nu_prescricoes_dia ?? alerta.nu_prescricoes ?? 0,
      ritmo_minutos_display: alerta.ritmo_minutos ?? alerta.nu_minutos_span ?? 0,
      ritmo_hora_num: Number(alerta.ritmo_hora ?? alerta.taxa_hora ?? 0),
    };

    if (!grupos.has(idMedico)) {
      grupos.set(idMedico, { id_medico: idMedico, alertas: [] });
    }
    grupos.get(idMedico).alertas.push(alertaNormalizado);
  });

  return Array.from(grupos.values())
    .map(grupo => ({
      ...grupo,
      alertas: grupo.alertas.sort((a, b) =>
        String(a.dt_ini_hora || '').localeCompare(String(b.dt_ini_hora || ''))
      ),
    }))
    .sort((a, b) => {
      const inicioA = a.alertas[0]?.dt_ini_hora || '';
      const inicioB = b.alertas[0]?.dt_ini_hora || '';
      return String(inicioA).localeCompare(String(inicioB)) || a.id_medico.localeCompare(b.id_medico);
    });
});

const multiAlertasNumerados = computed(() => {
  return [...multiAlertas.value]
    .sort((a, b) => {
      const inicioA = a.dt_ini_hora || a.hr_janela || '';
      const inicioB = b.dt_ini_hora || b.hr_janela || '';
      return String(inicioA).localeCompare(String(inicioB));
    })
    .map((alerta, index) => {
      const qtd = alerta.ritmo_qtd ?? alerta.nu_prescricoes ?? alerta.nu_prescricoes_dia ?? 0;
      const minutos = alerta.ritmo_minutos ?? alerta.nu_minutos_span ?? calcularMinutosEntreHoras(alerta.dt_ini_hora, alerta.dt_fim_hora);
      const ritmoHora = Number(alerta.ritmo_hora ?? (minutos > 0 ? Number(qtd) * 60 / minutos : 0));
      return {
        ...alerta,
        numero_alerta: index + 1,
        nu_crms_display: alerta.nu_crms ?? alerta.nu_crms_distintos ?? 0,
        nu_prescricoes_display: qtd,
        ritmo_minutos_display: minutos,
        ritmo_hora_num: ritmoHora,
      };
    });
});

function getHoraMinuto(value) {
  if (!value) return '';
  const text = String(value);
  const timePart = text.includes(' ') ? text.split(' ')[1] : text;
  return timePart.slice(0, 5);
}

function calcularMinutosEntreHoras(inicio, fim) {
  const [hi, mi] = String(inicio || '').split(':').map(Number);
  const [hf, mf] = String(fim || '').split(':').map(Number);
  if (![hi, mi, hf, mf].every(Number.isFinite)) return 0;
  const inicioMinutos = hi * 60 + mi;
  const fimMinutos = hf * 60 + mf;
  return Math.max(0, fimMinutos - inicioMinutos);
}

function escapeTooltipHtml(value) {
  return String(value).replace(/[&<>\"']/g, (character) => ({
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    '\"': '&quot;',
    "'": '&#39;',
  })[character]);
}

function createCronologiaInfoTooltip(title, intro, details = [], note = '') {
  const detailsHtml = details.length
    ? `
      <div class="crm-info-tooltip-details">
        ${details.map(([label, value]) => `
          <div>
            <span>${escapeTooltipHtml(label)}</span>
            <strong>${escapeTooltipHtml(value)}</strong>
          </div>
        `).join('')}
      </div>`
    : '';
  const noteHtml = note
    ? `<div class="crm-info-tooltip-note"><strong>Como funciona</strong><span>${escapeTooltipHtml(note)}</span></div>`
    : '';

  return {
    value: `
      <div class="crm-info-tooltip-content">
        <div class="crm-info-tooltip-title-row">
          <i class="pi pi-info-circle" aria-hidden="true"></i>
          <div class="crm-info-tooltip-title">${escapeTooltipHtml(title)}</div>
        </div>
        <p class="crm-info-tooltip-intro">${escapeTooltipHtml(intro)}</p>
        ${detailsHtml}
        ${noteHtml}
      </div>
    `,
    escape: false,
    class: 'crm-info-tooltip',
    showDelay: 120,
    hideDelay: 80,
  };
}

const cronologiaInfoTooltips = Object.freeze({
  previousMonth: createCronologiaInfoTooltip(
    'Mês anterior',
    'Desloca a janela de visualização do histórico diário para o período anterior.',
    [['Ação', 'Recuar aproximadamente 30 dias']],
    'A navegação altera somente a janela visual do gráfico e preserva os filtros ativos.'
  ),
  nextMonth: createCronologiaInfoTooltip(
    'Próximo mês',
    'Desloca a janela de visualização do histórico diário para o período seguinte.',
    [['Ação', 'Avançar aproximadamente 30 dias']],
    'A navegação altera somente a janela visual do gráfico e preserva os filtros ativos.'
  ),
  rankUnico: createCronologiaInfoTooltip(
    'Ranqueamento · Autorizações em Sequência (Único CRM)',
    'Classifica os dias pela maior intensidade de autorizações emitidas em sequência com o mesmo CRM em um intervalo reduzido.',
    [['Critério', 'Autorizações em Sequência (Único CRM)'], ['Resultado', 'Dias mais intensos no gráfico']],
    'O ranking prioriza o maior ritmo horário identificado para esse padrão.'
  ),
  rankMultiplo: createCronologiaInfoTooltip(
    'Ranqueamento · Autorizações em Sequência (Múltiplos CRMs)',
    'Classifica os dias pela maior intensidade de autorizações emitidas em sequência com participação de múltiplos CRMs.',
    [['Critério', 'Autorizações em Sequência (Múltiplos CRMs)'], ['Resultado', 'Dias mais intensos no gráfico']],
    'O ranking considera o maior ritmo horário associado ao acionamento sequencial de diferentes CRMs.'
  ),
  rankVolume: createCronologiaInfoTooltip(
    'Ranqueamento · Volume',
    'Classifica os dias pelos maiores picos de dispensações por hora em comparação com a mediana histórica da operação.',
    [['Critério', 'Volume horário acima do padrão'], ['Resultado', 'Dias com maior multiplicador']],
    'O multiplicador compara o volume da hora com a mediana horária de referência.'
  ),
  rankLimit: createCronologiaInfoTooltip(
    'Quantidade de dias exibidos',
    'Define quantos dos dias mais intensos serão apresentados quando um critério de ranqueamento estiver ativo.',
    [['Opções', 'Top 10, Top 20, Top 50 ou Todos'], ['Base', 'Autorizações em Sequência (Único CRM), Autorizações em Sequência (Múltiplos CRMs) ou Volume']],
    'O controle fica disponível para limitar a lista ranqueada ou exibir todos os dias encontrados.'
  ),
  onlyAnomalies: createCronologiaInfoTooltip(
    'Filtro · Apenas Anomalias',
    'Exibe exclusivamente os dias que apresentaram volume horário atípico ou autorizações em sequência pelo mesmo CRM ou por alguns CRMs.',
    [['Inclui', 'Dias com pelo menos uma anomalia'], ['Oculta', 'Dias de operação normal']],
    'Ao selecionar um critério de ranqueamento, este filtro é desativado para que o ranking controle o recorte exibido.'
  ),
  unicoSection: createCronologiaInfoTooltip(
    'Alertas de Autorizações em Sequência (Único CRM) no período',
    'Apresenta as janelas em que o mesmo CRM registrou muitas autorizações em sequência.',
    [['Exibe', 'Janela, volume e duração'], ['Também informa', 'Ritmo e classificação de severidade']],
    'Cada alerta pode ser selecionado para acompanhar as autorizações correspondentes no Raio-X.'
  ),
  multiploSection: createCronologiaInfoTooltip(
    'Alertas de Autorizações em Sequência (Múltiplos CRMs) no período',
    'Apresenta as janelas em que a farmácia registrou muitas autorizações em sequência com participação de diferentes CRMs.',
    [['Exibe', 'CRMs distintos, volume e duração'], ['Também informa', 'Ritmo e classificação de severidade']],
    'Cada alerta pode ser selecionado para acompanhar as autorizações correspondentes no Raio-X.'
  ),
});

function formatUnicoAlertTitle(alerta) {
  const severityHtml = alerta.severidade
    ? `<div><span>Classificação</span><strong>${escapeTooltipHtml(alerta.severidade)}</strong></div>`
    : '';

  return `
    <div class="crm-alert-tooltip-content">
      <div class="crm-alert-tooltip-title">Autorizações em Sequência (Único CRM) · ALERTA #${escapeTooltipHtml(alerta.numero_alerta)}</div>
      <p class="crm-alert-tooltip-intro">Este alerta identifica muitas autorizações emitidas em sequência pelo mesmo CRM em um intervalo reduzido.</p>
      <div class="crm-alert-tooltip-details">
        <div><span>CRM</span><strong>${escapeTooltipHtml(alerta.id_medico)}</strong></div>
        <div><span>Janela observada</span><strong>${escapeTooltipHtml(alerta.dt_ini_hora)}–${escapeTooltipHtml(alerta.dt_fim_hora)}</strong></div>
        <div><span>Volume concentrado</span><strong>${escapeTooltipHtml(alerta.ritmo_qtd_display)} autorizações</strong></div>
        <div><span>Duração</span><strong>${escapeTooltipHtml(alerta.ritmo_minutos_display)} minutos</strong></div>
        <div><span>Ritmo equivalente</span><strong>${Number(alerta.ritmo_hora_num).toFixed(1)} autorizações por hora</strong></div>
        ${severityHtml}
      </div>
      <div class="crm-alert-tooltip-note"><strong>Interpretação</strong><span>O padrão indica uma concentração incomum de lançamentos em curto intervalo. Recomenda-se verificar as transações no Raio-X e comparar o comportamento com os demais alertas do estabelecimento.</span></div>
    </div>`;
}

function formatMultiAlertTitle(alerta) {
  const severityHtml = alerta.severidade
    ? `<div><span>Classificação</span><strong>${escapeTooltipHtml(alerta.severidade)}</strong></div>`
    : '';

  return `
    <div class="crm-alert-tooltip-content">
      <div class="crm-alert-tooltip-title">Autorizações em Sequência (Múltiplos CRMs) · ALERTA #${escapeTooltipHtml(alerta.numero_alerta)}</div>
      <p class="crm-alert-tooltip-intro">Este alerta identifica muitas autorizações emitidas em sequência por alguns CRMs em um intervalo reduzido.</p>
      <div class="crm-alert-tooltip-details">
        <div><span>CRMs distintos</span><strong>${escapeTooltipHtml(alerta.nu_crms_display)}</strong></div>
        <div><span>Janela observada</span><strong>${escapeTooltipHtml(alerta.dt_ini_hora)}–${escapeTooltipHtml(alerta.dt_fim_hora)}</strong></div>
        <div><span>Volume concentrado</span><strong>${escapeTooltipHtml(alerta.nu_prescricoes_display)} autorizações</strong></div>
        <div><span>Duração</span><strong>${escapeTooltipHtml(alerta.ritmo_minutos_display)} minutos</strong></div>
        <div><span>Ritmo equivalente</span><strong>${Number(alerta.ritmo_hora_num).toFixed(1)} autorizações por hora</strong></div>
        ${severityHtml}
      </div>
      <div class="crm-alert-tooltip-note"><strong>Interpretação</strong><span>O padrão sugere acionamento sequencial de diferentes CRMs em um intervalo reduzido. Recomenda-se conferir cada autorização no Raio-X, observando horários, prescritores e demais evidências associadas.</span></div>
    </div>`;
}

function setHoveredUnicoAlert(alerta) {
  hoveredAlert.value = {
    key: `U-${alerta.numero_alerta}`,
    type: 'unico',
    id_medico: alerta.id_medico,
  };
}

function setHoveredMultiAlert(alerta) {
  hoveredAlert.value = {
    key: `M-${alerta.numero_alerta}`,
    type: 'multi',
  };
}

function setHoveredTableAlert(alerta) {
  hoveredAlert.value = {
    key: alerta.key,
    type: alerta.type,
    id_medico: alerta.id_medico ?? null,
  };
}

function clearHoveredAlert() {
  hoveredAlert.value = null;
}

const groupedRaiox = computed(() => {
  return hourlyTransactions.value
    .map(item => ({
      num_autorizacao: item.num_autorizacao,
      data_hora: item.data_hora,
      id_medico: item.id_medico,
      no_medico: item.no_medico,
      vl_autorizacao: item.valor_pago || 0,
    }))
    .sort((a, b) => a.data_hora.localeCompare(b.data_hora));
});

const crmFrequencies = computed(() => {
  const freqs = {};
  groupedRaiox.value.forEach(tx => { freqs[tx.id_medico] = (freqs[tx.id_medico] || 0) + 1; });
  return freqs;
});

const raioxTotalValue = computed(() => {
  return groupedRaiox.value.reduce((sum, tx) => sum + tx.vl_autorizacao, 0);
});

function getCRMColor(idMedico) {
  if (!idMedico) return 'var(--primary-color)';
  idMedico = String(idMedico);
  let hash = 0;
  for (let i = 0; i < idMedico.length; i++) { hash = idMedico.charCodeAt(i) + ((hash << 5) - hash); }
  const h = Math.abs(hash % 360);
  const lightness = themeStore.isDark ? 65 : 35;
  return `hsl(${h}, 75%, ${lightness}%)`;
}

function buildRaioxKey(dt_janela, hourInt) {
  return `${props.cnpj}|${dt_janela}|${hourInt ?? 'all'}`;
}

function getSelectedRaioxHour() {
  return selectedHourlyHour.value === 'all' ? null : selectedHourlyHour.value;
}

function hasRaioxPayload(dt_janela, hourInt = null) {
  return raioxCache.has(buildRaioxKey(dt_janela, hourInt));
}

function hasRaioxRequest(dt_janela, hourInt = null) {
  return raioxRequests.has(buildRaioxKey(dt_janela, hourInt));
}

function assertRaioxPayload(data) {
  if (!data || !Array.isArray(data.transactions)) {
    throw new Error('Contrato invalido em crm/raio-x: transactions obrigatorio.');
  }
  if (!Array.isArray(data.alertas_unico)) {
    throw new Error('Contrato invalido em crm/raio-x: alertas_unico obrigatorio.');
  }
  if (!Array.isArray(data.alertas_multi)) {
    throw new Error('Contrato invalido em crm/raio-x: alertas_multi obrigatorio.');
  }
}

function applyRaioxPayload(data) {
  hourlyTransactions.value = data.transactions;
  unicoAlertas.value = data.alertas_unico;
  multiAlertas.value = data.alertas_multi;
}

async function loadRaiox(dt_janela, hourInt = null) {
  const key = buildRaioxKey(dt_janela, hourInt);
  activeRaioxKey.value = key;

  if (raioxCache.has(key)) {
    applyRaioxPayload(raioxCache.get(key));
    hourlyTransactionsLoading.value = false;
    return;
  }

  hourlyTransactionsLoading.value = true;
  try {
    const request = raioxRequests.get(key) ?? (async () => {
      const url = API_ENDPOINTS.analyticsCrmRaioX(props.cnpj, dt_janela, hourInt);
      const res = await fetch(url);
      if (!res.ok) throw new Error('Falha HTTP');
      const data = await res.json();
      assertRaioxPayload(data);
      raioxCache.set(key, data);
      return data;
    })();

    if (!raioxRequests.has(key)) {
      raioxRequests.set(key, request);
    }

    const data = await request;
    if (activeRaioxKey.value !== key) return;
    applyRaioxPayload(data);
  } catch (err) {
    console.error("Erro ao buscar Raio-X CRM:", err);
    hourlyTransactions.value = [];
    unicoAlertas.value = [];
    multiAlertas.value = [];
  } finally {
    raioxRequests.delete(key);
    if (activeRaioxKey.value === key) {
      hourlyTransactionsLoading.value = false;
    }
  }
}

async function ensureRaioxLoaded(dt_janela, hourInt = null) {
  if (!dt_janela) return;

  const key = buildRaioxKey(dt_janela, hourInt);
  activeRaioxKey.value = key;

  if (raioxCache.has(key)) {
    applyRaioxPayload(raioxCache.get(key));
    hourlyTransactionsLoading.value = false;
    return;
  }

  await loadRaiox(dt_janela, hourInt);
}

async function onDailyZrClick() {
  if (hoveredDailyDayIndex.value === null) return;
  const day = filteredDailyDays.value?.[hoveredDailyDayIndex.value];
  if (!day || (day.is_volume_horario_anomalo === 0 && day.is_crm_unico === 0 && day.is_crm_multiplo === 0)) return;

  if (selectedDay.value?.dt_janela === day.dt_janela) return;

  selectedDay.value = day;
  selectedHourlyHour.value = 'all';

  await ensureRaioxLoaded(day.dt_janela, null);
}

async function onChartClick(params) {
  // Mantemos para compatibilidade se necessário, mas o principal agora é onDailyZrClick
}


function truncate(str, n) {
  if (!str) return '';
  return str.length > n ? str.substring(0, n - 1) + '...' : str;
}

// ── Chart Options ─────────────────────────────────────────────────────────
const chartOptionDaily = computed(() => {
  const totalDays = dailyDates.value.length;
  const startZoom = dailyZoomStart.value;
  const endZoom = dailyZoomEnd.value;
  const fixedSpan = totalDays > 30 ? (30 / totalDays) * 100 : 100;
  const dailyBarWidth = dailyRankMode.value
    ? (totalDays <= 10 ? '46%' : totalDays <= 20 ? '54%' : totalDays <= 50 ? '58%' : '52%')
    : '100%';
  const dailyBarMaxWidth = dailyRankMode.value
    ? (totalDays <= 10 ? 58 : totalDays <= 20 ? 42 : totalDays <= 50 ? 30 : 24)
    : 40;
  const showDailySlider = !dailyRankMode.value || dailyRankLimit.value === 0;
  const showDailyRankBadge = !!dailyRankMode.value && dailyRankLimit.value > 0 && totalDays <= 20;
  const rankBadgeColors = {
    unico: { bg: 'rgba(245, 158, 11, 0.18)', text: '#f59e0b', border: 'rgba(245, 158, 11, 0.38)' },
    multiplo: { bg: 'rgba(139, 92, 246, 0.18)', text: '#8b5cf6', border: 'rgba(139, 92, 246, 0.38)' },
    volume: { bg: 'rgba(16, 185, 129, 0.18)', text: '#10b981', border: 'rgba(16, 185, 129, 0.38)' },
  };
  const rankBadgeColor = rankBadgeColors[dailyRankMode.value] ?? rankBadgeColors.unico;

  return {
    ...chartTheme.value,
    animation: true,
    animationDuration: 100,
    animationDurationUpdate: 100,
    legend: { show: false },
    grid: { top: showDailyRankBadge ? 34 : 16, right: 20, bottom: 80, left: 50, containLabel: false },
    xAxis: {
      type: 'category',
      data: dailyDates.value,
      axisPointer: {
        show: true,
        type: 'shadow',
        shadowStyle: { color: 'rgba(99, 102, 241, 0.05)' },
        triggerTooltip: true,
        handle: { show: false }
      },
      axisLabel: {
        formatter: (v) => v ? `${v.slice(8, 10)}/${v.slice(5, 7)}` : '',
        interval: 'auto',
        rotate: 45,
        fontSize: 10,
        color: chartTheme.value.muted
      },
      axisLine: { lineStyle: { color: chartTheme.value.border } },
    },
    yAxis: [
      {
        type: 'value',
        minInterval: 1,
        axisLabel: { fontSize: 11 },
        splitLine: { lineStyle: { color: chartTheme.value.grid } },
      },
      {
        type: 'value',
        min: 0,
        max: 1,
        show: false
      }
    ],
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'shadow' },
      backgroundColor: chartTheme.value.tooltip,
      borderColor: chartTheme.value.tooltipBorder,
      borderWidth: 1,
      padding: [12, 16],
      confine: true,
      position: (point, params, dom, rect, size) => {
        const gap = 16;
        const viewWidth = size.viewSize[0];
        const viewHeight = size.viewSize[1];
        const tooltipWidth = size.contentSize[0];
        const tooltipHeight = size.contentSize[1];
        const x = point[0] + tooltipWidth + gap > viewWidth
          ? Math.max(gap, point[0] - tooltipWidth - gap)
          : point[0] + gap;
        const y = Math.min(Math.max(gap, point[1] + gap), viewHeight - tooltipHeight - gap);
        return [x, y];
      },
      textStyle: { color: chartTheme.value.tooltipText, fontFamily: 'Inter, sans-serif', fontSize: 12 },
      shadowBlur: 10,
      shadowColor: 'rgba(0,0,0,0.15)',
      formatter: (p) => {
        const idx = Array.isArray(p) ? p[0]?.dataIndex : p.dataIndex;
        const day = filteredDailyDays.value?.[idx];
        if (!day) return '';
        const c = chartTheme.value;
        const points = hourlyByDate.value.get(day.dt_janela) ?? [];
        let sparklineHtml = '';
        if (points.length > 0) {
          const maxVal = Math.max(...points.map(pt => pt.nu_prescricoes), 1);
          const bars = Array.from({ length: 24 }, (_, h) => {
            const pt = points.find(x => x.hr_janela === h);
            const hPerc = pt ? (pt.nu_prescricoes / maxVal) * 100 : 0;
            const isAnomalo = pt?.is_hora_com_alerta === 1;
            const color = isAnomalo ? '#ef4444' : c.muted;
            const opacity = hPerc > 0 ? 1 : 0.3;
            return `<div style="flex:1; height:${Math.max(hPerc, 2)}%; background:${color}; border-radius:1px; opacity:${opacity};"></div>`;
          }).join('');
          sparklineHtml = `
            <div style="margin-top:10px; border-top:1px solid ${c.tooltipBorder}; padding-top:10px;">
              <div style="font-size:10px; opacity:.6; letter-spacing:.04em; text-transform:uppercase; margin-bottom:6px; text-align:center;">Distribuição Horária</div>
              <div style="display:flex; align-items:flex-end; gap:2px; height:40px;">${bars}</div>
            </div>`;
        }
        const badges = [];
        if (day.is_volume_horario_anomalo === 1) {
          badges.push('<span style="font-size:10px; background:rgba(239, 68, 68, 0.15); color:#ef4444; padding:2px 8px; border-radius:4px; font-weight:600; border:1px solid rgba(239, 68, 68, 0.3); margin-left:8px;">⚠ SURTO</span>');
        }
        if (day.is_crm_unico === 1) {
          badges.push('<span style="font-size:10px; background:rgba(245, 158, 11, 0.15); color:#f59e0b; padding:2px 8px; border-radius:4px; font-weight:600; border:1px solid rgba(245, 158, 11, 0.3); margin-left:8px;">⚠ Autorizações em Sequência (Único CRM)</span>');
        }
        if (day.is_crm_multiplo === 1) {
          badges.push('<span style="font-size:10px; background:rgba(139, 92, 246, 0.15); color:#8b5cf6; padding:2px 8px; border-radius:4px; font-weight:600; border:1px solid rgba(139, 92, 246, 0.3); margin-left:8px;">⚠ Autorizações em Sequência (Múltiplos CRMs)</span>');
        }
        const rankMetric = dailyRankMode.value ? formatDailyRankMetric(day) : '';
        const rankMetricHtml = rankMetric
          ? `<div style="display:flex; justify-content:space-between; align-items:center;">
                <span style="font-size:11px; opacity:.6; text-transform:uppercase;">Ranking Ativo</span>
                <span style="font-weight:700; font-size:13px;">${rankMetric}</span>
             </div>`
          : '';
        return `
          <div style="color: ${c.tooltipText}; min-width: 200px;">
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:10px;">
              <span style="font-weight:700; font-size:14px;">${formatarData(day.dt_janela)}</span>
              ${badges.join('')}
            </div>
            <div style="display:flex; flex-direction:column; gap:8px;">
              <div style="display:flex; justify-content:space-between; align-items:center;">
                <span style="font-size:11px; opacity:.6; text-transform:uppercase;">Volume Total</span>
                <span style="font-weight:700; font-size:13px;">${day.nu_prescricoes_dia} <small>autorizações</small></span>
              </div>
              <div style="display:flex; justify-content:space-between; align-items:center;">
                <span style="font-size:11px; opacity:.6; text-transform:uppercase;">Médicos Distintos</span>
                <span style="font-weight:700; font-size:13px;">${day.nu_crms_distintos}</span>
              </div>
              ${rankMetricHtml}
            </div>
            ${sparklineHtml}
            ${(day.is_volume_horario_anomalo === 1 || day.is_crm_unico === 1 || day.is_crm_multiplo === 1) ? '<div style="margin-top:10px; font-size:10px; color:#6366f1; text-align:center; opacity:.8; font-style:italic;">Clique para drill-down detalhado</div>' : ''}
          </div>`;
      },
    },
    dataZoom: [
      { type: 'inside', start: startZoom, end: endZoom, zoomLock: true },
      { 
        type: 'slider', 
        show: showDailySlider,
        start: startZoom, 
        end: endZoom, 
        height: 16, 
        bottom: 10, 
        borderColor: 'transparent',
        backgroundColor: themeStore.isDark ? 'rgba(255,255,255,0.03)' : 'rgba(0,0,0,0.03)',
        fillerColor: themeStore.isDark ? 'rgba(99, 102, 241, 0.3)' : 'rgba(99, 102, 241, 0.2)',
        handleSize: 0, 
        showDetail: false,
        showDataShadow: false,
        zoomLock: true,
        brushSelect: false,
        borderRadius: 8
      },
    ],
    series: [
      {
        name: 'Área de Clique',
        type: 'bar',
        barGap: '-100%',
        barWidth: '100%',
        yAxisIndex: 1,
        z: 1,
        data: filteredDailyDays.value.map(d => ({
          value: 1,
          itemStyle: { color: 'transparent' },
          cursor: (d.is_volume_horario_anomalo === 1 || d.is_crm_unico === 1 || d.is_crm_multiplo === 1) ? 'pointer' : 'default'
        })),
        tooltip: { show: false },
        emphasis: { disabled: true },
        silent: false
      },
      {
        name: 'Prescrições',
        type: 'bar',
        barGap: '-100%',
        barWidth: dailyBarWidth,
        barMaxWidth: dailyBarMaxWidth,
        z: 2,
        label: {
          show: showDailyRankBadge,
          position: 'top',
          distance: 6,
          formatter: (params) => params.data?.rankBadge ? `{badge|${params.data.rankBadge}}` : '',
          rich: {
            badge: {
              color: rankBadgeColor.text,
              backgroundColor: rankBadgeColor.bg,
              borderColor: rankBadgeColor.border,
              borderWidth: 1,
              borderRadius: 4,
              padding: [2, 5],
              fontSize: 10,
              fontWeight: 700,
              lineHeight: 14,
            },
          },
        },
        emphasis: {
          label: { show: showDailyRankBadge },
        },
        blur: {
          label: { show: showDailyRankBadge, opacity: 1 },
        },
        data: dailyValues.value.map((v, i) => {
          const day = filteredDailyDays.value[i];
          const isSelected = selectedDay.value && selectedDay.value.dt_janela === day.dt_janela;
          const hasSelection = !!selectedDay.value;
          const isAnomalo = day.is_volume_horario_anomalo === 1 || day.is_crm_unico === 1 || day.is_crm_multiplo === 1;
          const color = isAnomalo
            ? { type: 'linear', x: 0, y: 0, x2: 0, y2: 1, colorStops: [{ offset: 0, color: '#ef4444' }, { offset: 1, color: '#ef444440' }] }
            : { type: 'linear', x: 0, y: 0, x2: 0, y2: 1, colorStops: [{ offset: 0, color: 'rgba(148,163,184,0.6)' }, { offset: 1, color: 'rgba(148,163,184,0.15)' }] };
          return {
            value: v,
            rankBadge: formatDailyRankBadge(day),
            cursor: (day.is_volume_horario_anomalo === 1 || day.is_crm_unico === 1 || day.is_crm_multiplo === 1) ? 'pointer' : 'default',
            itemStyle: {
              opacity: hasSelection && !isSelected ? 0.5 : 1,
              color,
            },
          };
        }),
      },
      {
        name: 'Mediana Referência (Dia)',
        type: 'line',
        step: 'end',
        symbol: 'none',
        data: dailyMedians.value,
        lineStyle: { color: '#f59e0b', type: 'dashed', width: 1.5, opacity: 0.8 },
        z: 10,
        silent: true,
      },
    ],
  };
});

const hourlyPoints = computed(() => {
  if (!selectedDay.value || !timelineHourlyDataset.value) return [];
  const targetDate = selectedDay.value.dt_janela;
  return timelineHourlyDataset.value.points.filter(p => String(p.dt_janela).substring(0,10) === String(targetDate).substring(0,10));
});

const hourlyEvents = computed(() => {
  if (!selectedDay.value || !timelineHourlyDataset.value) return [];
  const targetDate = selectedDay.value.dt_janela;
  return (timelineHourlyDataset.value.events ?? []).filter(e => String(e.dt_janela).substring(0,10) === String(targetDate).substring(0,10));
});

const chartOptionHourly = computed(() => {
  if (!selectedDay.value || !hourlyPoints.value.length) return {};
  const c = chartTheme.value;
  const fullPoints = hourlyPoints.value;

  const barColors = fullPoints.map(p => {
    if (p.is_hora_com_alerta === 1 && p.nu_prescricoes > 0) {
      return { type: 'linear', x: 0, y: 0, x2: 0, y2: 1, colorStops: [{ offset: 0, color: '#ef4444' }, { offset: 1, color: 'rgba(239, 68, 68, 0.4)' }] };
    }
    return { type: 'linear', x: 0, y: 0, x2: 0, y2: 1, colorStops: [{ offset: 0, color: 'rgba(99, 102, 241, 0.65)' }, { offset: 1, color: 'rgba(99, 102, 241, 0.15)' }] };
  });

  return {
    backgroundColor: c.bg,
    animation: true,
    animationDuration: 600,
    animationEasing: 'cubicOut',
    textStyle: { fontFamily: 'Inter, sans-serif' },
    legend: { show: false },
    grid: [
      { top: 16, left: 100, right: 20, height: '55%' }, // Grid 0: Barras
      { top: '75%', left: 100, right: 20, height: '18%' } // Grid 1: Trilhas
    ],
    xAxis: [
      {
        gridIndex: 0,
        type: 'category',
        data: fullPoints.map(p => `${String(p.hr_janela).padStart(2, '0')}h`),
        axisLine: { lineStyle: { color: c.grid } },
        axisTick: { show: false },
        axisLabel: { color: c.muted, fontSize: 10, fontWeight: 600, fontFamily: 'Inter, sans-serif', interval: 1, formatter: (v, i) => (i % 2 === 0 ? v : '') },
      },
      {
        gridIndex: 1,
        type: 'category',
        data: fullPoints.map(p => `${String(p.hr_janela).padStart(2, '0')}h`),
        axisLine: { show: false },
        axisTick: { show: false },
        axisLabel: { show: false }
      }
    ],
    yAxis: [
      { 
        gridIndex: 0,
        type: 'value', 
        minInterval: 1, 
        axisLine: { show: false }, 
        axisTick: { show: false }, 
        splitLine: { lineStyle: { color: c.grid, type: 'dashed' } }, 
        axisLabel: { color: c.muted, fontSize: 10, fontFamily: 'Inter, sans-serif' } 
      },
      {
        gridIndex: 1,
        type: 'value',
        min: 0,
        max: 10,
        interval: 1,
        axisLine: { show: false },
        axisTick: { show: false },
        splitLine: { show: false },
        axisLabel: {
          show: true,
          color: c.textSecondary || '#94a3b8',
          fontSize: 9,
          fontWeight: 700,
          fontFamily: 'Inter, sans-serif',
          margin: 12,
          formatter: (v) => {
            if (v === 2) return 'VOLUME';
            if (v === 5) return 'ÚNICO';
            if (v === 8) return 'MÚLTIPLO';
            return '';
          }
        }
      }
    ],
    tooltip: {
      trigger: 'axis',
      backgroundColor: c.tooltip,
      borderColor: c.tooltipBorder,
      borderWidth: 1,
      padding: [12, 16],
      confine: true,
      textStyle: { color: c.tooltipText, fontFamily: 'Inter, sans-serif', fontSize: 12 },
      shadowBlur: 10,
      shadowColor: 'rgba(0,0,0,0.15)',
      axisPointer: { type: 'shadow', shadowStyle: { color: c.axisShadow } },
      formatter: (params) => {
        const tooltipParams = Array.isArray(params) ? params : [params];
        const barParam = tooltipParams.find(p => p.seriesName === 'Autorizações (Volume)');
        const anchorParam = barParam ?? tooltipParams.find(p => p.dataIndex != null);
        if (!anchorParam) return '';
        const dataIndex = anchorParam.dataIndex;
        const pt = fullPoints[dataIndex];
        if (!pt) return '';
        const hora = `${String(pt.hr_janela).padStart(2, '0')}h`;
        const vol = pt.nu_prescricoes;
        const crms = pt.nu_crms_diferentes;
        const med = pt.mediana_hora ?? 0;
        const ratio = med > 0 ? (vol / med).toFixed(1) : null;
        const isAnomalo = pt.is_hora_com_alerta === 1;

        const trackAlerts = [
          pt.is_volume_horario_anomalo === 1 && {
            color: '#10b981',
            label: 'VOLUME',
            description: 'pico de autorizações acima do padrão histórico do horário',
          },
          pt.is_crm_unico === 1 && {
            color: '#f59e0b',
            label: 'Autorizações em Sequência (Único CRM)',
            description: 'muitas autorizações em sequência pelo mesmo CRM em uma janela curta',
          },
          pt.is_crm_multiplo === 1 && {
            color: '#8b5cf6',
            label: 'Autorizações em Sequência (Múltiplos CRMs)',
            description: 'muitas autorizações em sequência por alguns CRMs em uma janela curta',
          },
        ].filter(Boolean);

        const trackAlertsHtml = trackAlerts.length > 0
          ? `
            <div style="margin-top:12px; padding-top:10px; border-top:1px solid ${c.tooltipBorder};">
              <div style="font-size:10px; color:${c.muted}; text-transform:uppercase; letter-spacing:.05em; margin-bottom:8px;">Trilhas de alerta nesta hora</div>
              <div style="display:flex; flex-direction:column; gap:7px;">
                ${trackAlerts.map(alert => `
                  <div style="display:flex; align-items:flex-start; gap:7px;">
                    <span style="width:9px; height:5px; border-radius:2px; background:${alert.color}; display:inline-block; margin-top:4px; flex:0 0 auto;"></span>
                    <span style="display:flex; flex-direction:column; gap:2px;">
                      <strong style="font-size:11px; color:${alert.color};">${alert.label}</strong>
                      <span style="font-size:10px; color:${c.muted}; line-height:1.35;">${alert.description}</span>
                    </span>
                  </div>`).join('')}
              </div>
            </div>`
          : '';

        const ratioHtml = ratio !== null
          ? `<div style="margin-top:8px; font-size:12px; color:${isAnomalo ? '#ef4444' : c.muted}; font-weight:${isAnomalo ? '600' : '400'};">${ratio}× ${isAnomalo ? 'acima da mediana' : 'da mediana'}</div>`
          : '';

        return `
          <div style="color:${c.tooltipText}; min-width:190px;">
            <div style="font-weight:700; font-size:14px; margin-bottom:10px;">${hora}</div>
            <div style="display:flex; flex-direction:column; gap:8px;">
              <div style="display:flex; justify-content:space-between; align-items:center;">
                <span style="display:flex;align-items:center;gap:6px;"><span style="width:10px;height:10px;border-radius:2px;background:#ef4444;display:inline-block;"></span><span style="font-size:11px; opacity:.6; text-transform:uppercase;">Volume</span></span>
                <span style="font-weight:700; font-size:13px;">${vol} <small>autorizações</small></span>
              </div>
              <div style="display:flex; justify-content:space-between; align-items:center;">
                <span style="display:flex;align-items:center;gap:6px;"><span style="width:10px;height:10px;border-radius:2px;background:#6366f1;display:inline-block;"></span><span style="font-size:11px; opacity:.6; text-transform:uppercase;">Médicos</span></span>
                <span style="font-weight:700; font-size:13px;">${crms}</span>
              </div>
            </div>
            ${trackAlertsHtml}
            ${ratioHtml}
          </div>`;
      },
    },
    series: [
      {
        name: 'Autorizações (Volume)',
        type: 'bar',
        xAxisIndex: 0, yAxisIndex: 0,
        barGap: '-100%',
        barWidth: '100%',
        barMaxWidth: 28,
        z: 2,
        data: fullPoints.map((p, i) => {
          const isSelected = selectedHourlyHour.value === p.hr_janela;
          const hasSelection = selectedHourlyHour.value !== 'all' && selectedHourlyHour.value !== null;
          return { 
            value: p.nu_prescricoes,
            itemStyle: { 
              color: barColors[i],
              opacity: hasSelection && !isSelected ? 0.3 : 1
            } 
          };
        }),
      },
      {
        name: 'Mediana Referência (Hora)',
        type: 'line',
        xAxisIndex: 0, yAxisIndex: 0,
        step: 'middle',
        z: 3,
        data: fullPoints.map(p => p.mediana_hora),
        lineStyle: { color: '#f59e0b', type: 'dashed', width: 1.5 },
        symbol: 'none',
      },
      {
        name: 'Trilha Volume',
        type: 'scatter',
        xAxisIndex: 1, yAxisIndex: 1,
        symbol: 'roundRect',
        symbolSize: [26, 6],
        z: 5,
        data: fullPoints.map((p, i) => p.is_volume_horario_anomalo === 1 ? [i, 2] : null),
        itemStyle: { color: '#10b981' }
      },
      {
        name: 'Trilha Único',
        type: 'scatter',
        xAxisIndex: 1, yAxisIndex: 1,
        symbol: 'roundRect',
        symbolSize: [26, 6],
        z: 5,
        data: fullPoints.map((p, i) => p.is_crm_unico === 1 ? [i, 5] : null),
        itemStyle: { color: '#f59e0b' }
      },
      {
        name: 'Trilha Múltiplo',
        type: 'scatter',
        xAxisIndex: 1, yAxisIndex: 1,
        symbol: 'roundRect',
        symbolSize: [26, 6],
        z: 5,
        data: fullPoints.map((p, i) => p.is_crm_multiplo === 1 ? [i, 8] : null),
        itemStyle: { color: '#8b5cf6' }
      }
    ],
  };
});

// ── Auto-seleção do Dia Mais Anômalo e Ajuste de Foco do Gráfico ──
watch(filteredDailyDays, (newDays) => {
  if (newDays.length > 0 && !selectedDay.value) {
    const anomalousDays = newDays.filter(d => d.is_anomalo === 1);
    const candidateDays = dailyRankMode.value ? dailyRankedDays.value : anomalousDays;
    if (candidateDays.length > 0) {
      // 1. Encontra o pior dia do contexto atual
      const maxDay = dailyRankMode.value
        ? candidateDays[0]
        : candidateDays.reduce((max, d) =>
            (d.nu_prescricoes_dia > max.nu_prescricoes_dia) ? d : max, candidateDays[0]
          );
      selectedDay.value = maxDay;
      selectedHourlyHour.value = 'all';
      ensureRaioxLoaded(maxDay.dt_janela, null);

      // 2. Centraliza o Gráfico no dia selecionado
      const idx = newDays.findIndex(d => d.dt_janela === maxDay.dt_janela);
      if (idx !== -1) {
        setDailyZoomWindow(newDays.length, idx, dailyRankMode.value ? DAILY_RANK_VISIBLE_LIMIT : 30);
      }
    } else {
      // 3. Caso não haja anomalia, mostra os últimos 30 dias por padrão
      setDailyZoomWindow(newDays.length, null, dailyRankMode.value ? DAILY_RANK_VISIBLE_LIMIT : 30);
    }
  }
}, { immediate: true });

watch(dailyRankLimit, () => {
  if (!dailyRankMode.value) return;
  selectedDay.value = null;
  selectedHourlyHour.value = null;
});

// ── Retrigger quando o dataset horario fica pronto (race condition com auto-selecao) ──
// O timeline-dataset aquece o parquet do Raio-X antes de responder.
watch(crmTimelineDatasetLoading, (loading) => {
  if (!loading && selectedDay.value) {
    const hour = getSelectedRaioxHour();
    if (!hasRaioxPayload(selectedDay.value.dt_janela, hour) && !hasRaioxRequest(selectedDay.value.dt_janela, hour)) {
      ensureRaioxLoaded(selectedDay.value.dt_janela, hour);
    }
  }
});

// Belt-and-suspenders: quando o usuário abre a aba Cronologia e o dado ainda está vazio
const { activeCrmViewMode } = storeToRefs(cnpjDetailStore);
watch(activeCrmViewMode, (mode) => {
  if (mode === 'cronologia' && selectedDay.value) {
    const hour = getSelectedRaioxHour();
    if (!hasRaioxPayload(selectedDay.value.dt_janela, hour) && !hasRaioxRequest(selectedDay.value.dt_janela, hour)) {
      ensureRaioxLoaded(selectedDay.value.dt_janela, hour);
    }
  }
});

// ── Watch para Navegação Externa (Deep-Link) ──────────────────────────────
// Observa AMBOS: o evento de navegação e o cache de dados.
// Isso garante que mesmo se o evento disparar antes do cache estar pronto,
// o handler tentará novamente assim que os dados chegarem.
watch([selectedTimelineEvent, timelineDailyDataset], async ([evt, profile]) => {
  if (!evt || !profile) return;

  const rawDayObj = profile.days.find(d => d.dt_janela === evt.date);
  const dayObj = rawDayObj ? normalizeDailyDay(rawDayObj) : null;
  if (!dayObj) return;

  // 1. Seleciona o dia — mostra o dia todo sem filtrar por hora
  selectedDay.value = dayObj;
  selectedHourlyHour.value = 'all';

  // 2. Carrega as transações do dia inteiro
  await ensureRaioxLoaded(evt.date, null);

  // 3. Centraliza o zoom
  const idx = profile.days.findIndex(d => d.dt_janela === evt.date);
  if (idx !== -1) {
    const total = profile.days.length;
    const windowSize = 30;
    const halfWindow = windowSize / 2;
    let startIdx = Math.max(0, idx - halfWindow);
    let endIdx = Math.min(total, startIdx + windowSize);
    if (endIdx === total) startIdx = Math.max(0, total - windowSize);

    dailyZoomStart.value = (startIdx / total) * 100;
    dailyZoomEnd.value = (endIdx / total) * 100;
  }

  // 4. Limpa o evento para permitir futuras navegações
  cnpjDetailStore.clearTimelineNavigation();
});

const hourlyChartRef = ref(null);
const hoveredHourlyHour = ref(null);
const hoveredDailyDayIndex = ref(null);

function onDailyAxisPointerUpdate(params) {
  if (params.axesInfo && params.axesInfo.length > 0) {
    hoveredDailyDayIndex.value = params.axesInfo[0].value;
  } else {
    hoveredDailyDayIndex.value = null;
  }
}
watch(selectedHourlyHour, () => {
  if (hourlyChartRef.value) {
    setTimeout(() => {
      hourlyChartRef.value.resize();
    }, 100);
  }
});

function onHourlyAxisPointerUpdate(params) {
  if (params.axesInfo && params.axesInfo.length > 0) {
    // O value aqui é o index (0-23) que coincide com hr_janela
    hoveredHourlyHour.value = params.axesInfo[0].value;
  } else {
    hoveredHourlyHour.value = null;
  }
}

async function onHourlyZrClick() {
  if (hoveredHourlyHour.value === null || !selectedDay.value) return;
  
  const hourInt = hoveredHourlyHour.value;
  
  const point = hourlyPoints.value.find(p => p.hr_janela === hourInt);
  if (!point || (point.nu_prescricoes || 0) === 0) return;
  
  // Toggle do filtro
  if (selectedHourlyHour.value === hourInt) {
    selectedHourlyHour.value = 'all';
    await ensureRaioxLoaded(selectedDay.value.dt_janela, null);
    return;
  }
  
  selectedHourlyHour.value = hourInt;
  await ensureRaioxLoaded(selectedDay.value.dt_janela, hourInt);
}


// ── CRM ÚNICO: Estado de Raio-X ─────────────────────────────────────────────
// (refs declaradas no topo do script para evitar TDZ com watch immediate:true)

const unicoGatilhoMap = computed(() => {
  const map = {};
  unicoAlertasAgrupados.value.flatMap(grupo => grupo.alertas).forEach(a => {
    if (!map[a.id_medico]) map[a.id_medico] = [];
    map[a.id_medico].push(a);
  });
  return map;
});

function getUnicoAlertasDaTx(tx) {
  const intervals = unicoGatilhoMap.value[tx.id_medico];
  if (!intervals?.length) return [];
  const txTime = getHoraMinuto(tx.data_hora);
  return intervals.filter(a => txTime >= a.dt_ini_hora && txTime <= a.dt_fim_hora);
}

function getMultiAlertasDaTx(tx) {
  const txTime = getHoraMinuto(tx.data_hora);
  return multiAlertasNumerados.value.filter(a => txTime >= a.dt_ini_hora && txTime <= a.dt_fim_hora);
}

function getAlertasDaTx(tx) {
  return [
    ...getUnicoAlertasDaTx(tx).map(alerta => ({
      key: `U-${alerta.numero_alerta}`,
      label: `U#${alerta.numero_alerta}`,
      type: 'unico',
      id_medico: alerta.id_medico,
      title: formatUnicoAlertTitle(alerta),
    })),
    ...getMultiAlertasDaTx(tx).map(alerta => ({
      key: `M-${alerta.numero_alerta}`,
      label: `M#${alerta.numero_alerta}`,
      type: 'multi',
      title: formatMultiAlertTitle(alerta),
    })),
  ];
}

function getHoveredAlertaType(tx) {
  const alert = hoveredAlert.value;
  if (!alert) return null;
  if (alert.type === 'unico') return tx.id_medico === alert.id_medico ? 'unico' : null;
  return getMultiAlertasDaTx(tx).some(a => `M-${a.numero_alerta}` === alert.key) ? 'multi' : null;
}

function isGatilhoTx(tx) {
  return getUnicoAlertasDaTx(tx).length > 0;
}

function isMultiAlertaTx(tx) {
  return getMultiAlertasDaTx(tx).length > 0;
}

function getRaioxRowClasses(tx) {
  const hasUnico = isGatilhoTx(tx);
  const hoveredType = getHoveredAlertaType(tx);
  return {
    'row-gatilho': hasUnico,
    'row-multi-alerta': isMultiAlertaTx(tx) && !hasUnico,
    'row-alert-highlight-unico': hoveredType === 'unico',
    'row-alert-highlight-multi': hoveredType === 'multi',
  };
}

// ── Dados Ativos: fonte unificada para o RAIO-X ───────────────────────────
// CRM Único: Agora o filtro de hora também é processado no servidor para consistência.
const activeGroupedRaiox = computed(() => {
  return selectedDay.value ? groupedRaiox.value : [];
});

const activeTransactions = computed(() => {
  return selectedDay.value ? hourlyTransactions.value : [];
});

const activeRaioxTotalValue = computed(() => {
  return selectedDay.value ? raioxTotalValue.value : 0;
});

const activeCrmFrequencies = computed(() => {
  return selectedDay.value ? crmFrequencies.value : {};
});

const activeTransactionsLoading = computed(() =>
  hourlyTransactionsLoading.value
);

</script>

<template>
  <TabPlaceholder
    v-if="noMovementInPeriod"
    variant="info"
    icon="pi-chart-bar"
    title="Sem movimentação no período"
  >
    <template #description>
      Não foram encontradas movimentações financeiras para este CNPJ no período de <u>{{ formattedPeriod?.start }}</u> até <u>{{ formattedPeriod?.end }}</u>.
    </template>
  </TabPlaceholder>

  <div v-else class="cronologia-flow animate-fade-in">
    
    <!-- Breadcrumb de Navegação Dinâmico -->
    <div class="drill-breadcrumb">
      <span class="crumb-item" :class="{ 'is-current': !selectedDay }">
        <i class="pi pi-chart-bar crumb-icon" />
        <span>Histórico Diário</span>
      </span>
      <template v-if="selectedDay">
        <i class="pi pi-chevron-right crumb-arrow" />
        <span class="crumb-item" :class="{ 'is-current': selectedDay && selectedHourlyHour === null }">
          <i class="pi pi-calendar crumb-icon" />
          <span>{{ formatarData(selectedDay.dt_janela) }}</span>
          <span v-if="selectedDay.is_anomalo" class="crumb-anomaly-dot" />
        </span>
      </template>
      <template v-if="selectedHourlyHour !== null">
        <i class="pi pi-chevron-right crumb-arrow" />
        <span class="crumb-item is-current">
          <i class="pi pi-search crumb-icon" />
          <span>Raio-X · {{ selectedHourlyHour === 'all' ? 'Dia Todo' : `${String(selectedHourlyHour).padStart(2, '0')}h` }}</span>
        </span>
      </template>
    </div>

    <!-- NÍVEL 1: Histórico Diário -->
    <div class="drill-panel level-daily" :class="{ 'is-refreshing': showRefreshingDaily }">
      <div class="drill-panel-header">
        <div class="drill-panel-title">
          <i class="pi pi-chart-bar" />
          <span>HISTÓRICO DIÁRIO DE DISPENSAÇÕES</span>
          <span v-if="crmTimelineDatasetLoading" class="chart-loading-badge">
            <i class="pi pi-spinner pi-spin"></i> Carregando...
          </span>
        </div>
        <div class="filter-controls">
          <div class="chart-nav-buttons">
            <button
              class="nav-btn"
              @click="shiftZoom('prev')"
              v-tooltip.bottom="cronologiaInfoTooltips.previousMonth"
              aria-label="Mês anterior"
            >
              <i class="pi pi-chevron-left" />
            </button>
            <button
              class="nav-btn"
              @click="shiftZoom('next')"
              v-tooltip.bottom="cronologiaInfoTooltips.nextMonth"
              aria-label="Próximo mês"
            >
              <i class="pi pi-chevron-right" />
            </button>
          </div>
          <div class="filter-divider"></div>
          <div class="daily-rank-controls" aria-label="Piores dias por">
            <button
              class="rank-btn is-unico"
              :class="{ 'is-active': dailyRankMode === 'unico' }"
              @click="toggleDailyRankMode('unico')"
            >
              <i class="pi pi-user" />
              <span>Autorizações em Sequência (Único CRM)</span>
              <i
                class="pi pi-info-circle control-info-icon"
                role="img"
                aria-label="Informações sobre o ranqueamento por autorizações em sequência por um único CRM"
                v-tooltip.top="cronologiaInfoTooltips.rankUnico"
                @click.stop
              />
            </button>
            <button
              class="rank-btn is-multiplo"
              :class="{ 'is-active': dailyRankMode === 'multiplo' }"
              @click="toggleDailyRankMode('multiplo')"
            >
              <i class="pi pi-users" />
              <span>Autorizações em Sequência (Múltiplos CRMs)</span>
              <i
                class="pi pi-info-circle control-info-icon"
                role="img"
                aria-label="Informações sobre o ranqueamento por autorizações em sequência por múltiplos CRMs"
                v-tooltip.top="cronologiaInfoTooltips.rankMultiplo"
                @click.stop
              />
            </button>
            <button
              class="rank-btn is-volume"
              :class="{ 'is-active': dailyRankMode === 'volume' }"
              @click="toggleDailyRankMode('volume')"
            >
              <i class="pi pi-chart-bar" />
              <span>Volume</span>
              <i
                class="pi pi-info-circle control-info-icon"
                role="img"
                aria-label="Informações sobre o ranqueamento por volume"
                v-tooltip.top="cronologiaInfoTooltips.rankVolume"
                @click.stop
              />
            </button>
            <div class="rank-limit-control">
              <select
                v-model.number="dailyRankLimit"
                class="rank-limit-select"
                :disabled="!dailyRankMode"
              >
                <option v-for="option in dailyRankLimitOptions" :key="option.value" :value="option.value">
                  {{ option.label }}
                </option>
              </select>
              <i
                class="pi pi-info-circle control-info-icon rank-limit-info"
                role="img"
                aria-label="Informações sobre a quantidade de dias exibidos"
                tabindex="0"
                v-tooltip.top="cronologiaInfoTooltips.rankLimit"
              />
            </div>
          </div>
          <div class="filter-divider"></div>
          <label
            class="filter-toggle"
            :class="{ 'is-disabled': dailyRankMode }"
          >
            <input type="checkbox" v-model="filterDailyOnlyAnomalous" :disabled="dailyRankMode !== null" />
            <span class="toggle-slider"></span>
            <span class="toggle-label">Apenas Anomalias</span>
            <i
              class="pi pi-info-circle control-info-icon anomaly-filter-info"
              role="img"
              aria-label="Informações sobre o filtro Apenas Anomalias"
              tabindex="0"
                  v-tooltip.left="cronologiaInfoTooltips.onlyAnomalies"
              @click.prevent.stop
            />
          </label>
        </div>
      </div>
      <p class="subtitle" style="padding-left: 1.75rem; margin-top: 0; margin-bottom: 0.75rem">
        Evolução diária de autorizações. Barras vermelhas indicam dias com algum tipo de anomalia. Os alertas podem refletir volume atípico, autorizações em sequência com uso de um único CRM ou autorizações em sequência com uso de múltiplos CRMs. Clique em um dia sinalizado para análise detalhada.
      </p>
      
      <div v-if="!timelineDatasetReady && !crmTimelineDatasetLoading" class="chart-empty">
        <i class="pi pi-chart-bar" style="font-size:1.5rem; opacity:.4"></i>
        <span>Sem dados da linha do tempo CRM disponíveis.</span>
      </div>
      <div class="daily-chart-wrapper" :class="{ 'cursor-pointer-active': hoveredDailyDayIndex !== null }">
        <div class="chart-legend-html">
          <span class="legend-item">
            <span class="legend-swatch legend-bar" style="background: #ef4444;"></span>
            Dia Anômalo
          </span>
          <span class="legend-item">
            <span class="legend-swatch legend-bar" :style="{ background: chartUFAccents.bar1 }"></span>
            Dia Normal
          </span>
          <span class="legend-item">
            <span class="legend-swatch legend-dashed"></span>
            Mediana de Referência
          </span>
        </div>
        <VChart
          :option="chartOptionDaily"
          autoresize
          class="daily-dispensacao-chart"
          @zr:click="onDailyZrClick"
          @updateAxisPointer="onDailyAxisPointerUpdate"
          @datazoom="onDailyZoom"
        />
      </div>
      <div v-if="!selectedDay && timelineDatasetReady" class="drill-hint">
        <i class="pi pi-hand-pointer" />
        <span>Clique em um dia sinalizado para análise detalhada</span>
      </div>
    </div>

    <!-- Conector Diário → Horário -->
    <div v-if="selectedDay" class="drill-connector">
      <div class="connector-line" />
      <div class="connector-dot">
        <i class="pi pi-clock" />
      </div>
    </div>

    <!-- NÍVEL 2: Análise Horária -->
    <div v-if="selectedDay" class="drill-panel level-hourly animate-fade-in" :class="{ 'is-refreshing': showRefreshingHourly }">
      <div class="drill-panel-header">
        <div class="drill-panel-title">
          <i class="pi pi-clock" style="color: #6366f1;" />
          <span>ANÁLISE HORÁRIA</span>
          <span class="drill-context-tag">{{ formatarData(selectedDay.dt_janela) }}</span>
        </div>
        <div class="drill-panel-actions">
          <button 
            v-if="selectedHourlyHour !== 'all'" 
            class="reset-filter-btn animate-fade-in"
            @click="selectedHourlyHour = 'all'; ensureRaioxLoaded(selectedDay.dt_janela, null)"
          >
            <i class="pi pi-filter-slash" />
            <span>Ver Dia Todo</span>
          </button>
          <button class="close-detail-btn" @click="selectedDay = null; selectedHourlyHour = null">
            <i class="pi pi-times" />
          </button>
        </div>
      </div>
      <p class="subtitle" style="padding-left: 1.75rem; margin-top: 0; margin-bottom: 0.75rem">
        Distribuição das <strong>{{ selectedDay.nu_prescricoes_dia }} autorizações</strong> ao longo do dia.
      </p>
      <div class="daily-chart-wrapper" :class="{ 'cursor-pointer-active': hoveredHourlyHour !== null }">
        <div class="chart-legend-html">
          <div class="legend-group">
            <span class="legend-item">
              <span class="legend-swatch legend-bar" style="background: #ef4444;"></span>
              Hora com Alerta
            </span>
            <span class="legend-item">
              <span class="legend-swatch legend-bar" :style="{ background: 'rgba(99, 102, 241, 0.65)' }"></span>
              Hora Normal
            </span>
            <span class="legend-item">
              <span class="legend-swatch legend-dashed"></span>
              Mediana Referência
            </span>
          </div>
          <div v-if="selectedDay.is_volume_horario_anomalo || selectedDay.is_crm_unico || selectedDay.is_crm_multiplo" class="legend-divider"></div>
          <div class="legend-group">
            <span v-if="selectedDay.is_volume_horario_anomalo === 1" class="track-badge is-volume">Volume Atípico</span>
            <span v-if="selectedDay.is_crm_unico === 1" class="track-badge is-unico">Autorizações em Sequência (Único CRM)</span>
            <span v-if="selectedDay.is_crm_multiplo === 1" class="track-badge is-multiplo">Autorizações em Sequência (Múltiplos CRMs)</span>
          </div>
        </div>
        <VChart
          v-if="selectedDay"
          ref="hourlyChartRef"
          :option="chartOptionHourly"
          autoresize
          class="hourly-chart"
          @zr:click="onHourlyZrClick"
          @updateAxisPointer="onHourlyAxisPointerUpdate"
        />

      </div>
      <div v-if="selectedHourlyHour === null" class="drill-hint">
        <i class="pi pi-hand-pointer" />
        <span>Clique em uma barra para ver as transações detalhadas no Raio-X</span>
      </div>
    </div>

    <!-- Conector Horário → Raio-X -->
    <div v-if="selectedHourlyHour !== null" class="drill-connector">
      <div class="connector-line" />
      <div class="connector-dot connector-dot-raiox">
        <i class="pi pi-search" />
      </div>
    </div>

    <!-- NÍVEL 3: Raio-X (unificado: CRM Múltiplos ou CRM Único) -->
    <div v-if="selectedHourlyHour !== null" class="drill-panel level-raiox animate-fade-in">
      <div class="drill-panel-header">
        <div class="drill-panel-title">
          <i class="pi pi-search" style="color: #8b5cf6;" />
          <span>RAIO-X: TRANSAÇÕES</span>
          <span class="drill-context-tag drill-context-tag-raiox">
            {{ selectedHourlyHour === 'all' ? 'Dia Todo' : `${String(selectedHourlyHour).padStart(2, '0')}h` }}
          </span>
          <span v-if="!activeTransactionsLoading && activeGroupedRaiox.length > 0" class="raiox-count-badge">
            {{ activeGroupedRaiox.length }} Autorização{{ activeGroupedRaiox.length !== 1 ? 'es' : '' }}
          </span>
          <i v-if="activeTransactionsLoading" class="pi pi-spinner pi-spin raiox-spinner" />
        </div>
      </div>

      <!-- Médicos Gatilho (CRM Único) -->
      <div v-if="unicoAlertas.length > 0" class="unico-alertas-section alertas-unico-section">
        <div class="unico-alertas-header">
          <i class="pi pi-exclamation-triangle" />
          <span>Alertas de Autorizações em Sequência (Único CRM) no Período</span>
          <i
            class="pi pi-info-circle section-info-icon"
            role="img"
            aria-label="Informações sobre os alertas de autorizações em sequência por um único CRM"
            tabindex="0"
            v-tooltip.top="cronologiaInfoTooltips.unicoSection"
          />
        </div>
        <div class="unico-alertas-grouped-list">
          <div v-for="grupo in unicoAlertasAgrupados" :key="grupo.id_medico" class="unico-alerta-group">
            <div class="unico-alerta-group-title">
              <span class="alerta-crm" :style="{ color: getCRMColor(grupo.id_medico) }">{{ grupo.id_medico }}</span>
              <span class="unico-alerta-group-count">
                {{ grupo.alertas.length }} alerta{{ grupo.alertas.length !== 1 ? 's' : '' }}
              </span>
            </div>
            <div class="unico-alerta-group-items">
              <div
                v-for="alerta in grupo.alertas"
                :key="`${alerta.id_medico}-${alerta.dt_ini_hora}-${alerta.dt_fim_hora}-${alerta.numero_alerta}`"
                class="unico-alerta-row"
              >
                <span
                  class="alerta-alert-id"
                  v-tooltip.right="{ value: formatUnicoAlertTitle(alerta), escape: false, class: 'crm-alert-tooltip', showDelay: 120, hideDelay: 80 }"
                  @pointerenter="setHoveredUnicoAlert(alerta)"
                  @pointerleave="clearHoveredAlert"
                >
                  #{{ alerta.numero_alerta }}
                </span>
                <span class="alerta-stat">{{ alerta.dt_ini_hora }} -> {{ alerta.dt_fim_hora }}</span>
                <span v-if="alerta.severidade" class="alerta-severity">{{ alerta.severidade }}</span>
                <span class="alerta-stat">{{ alerta.ritmo_qtd_display }} em {{ alerta.ritmo_minutos_display }}min</span>
                <span class="alerta-stat">{{ alerta.ritmo_hora_num.toFixed(1) }}/h</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Surtos Coordenados (Multi-CRM) -->
      <div v-if="multiAlertas.length > 0" class="unico-alertas-section alertas-multi-section">
        <div class="unico-alertas-header">
          <i class="pi pi-users" />
          <span>Alertas de Autorizações em Sequência (Múltiplos CRMs) no Período</span>
          <i
            class="pi pi-info-circle section-info-icon"
            role="img"
            aria-label="Informações sobre os alertas de autorizações em sequência por múltiplos CRMs"
            tabindex="0"
            v-tooltip.top="cronologiaInfoTooltips.multiploSection"
          />
        </div>
        <div class="multi-alertas-numbered-list">
          <div
            v-for="alerta in multiAlertasNumerados"
            :key="`${alerta.dt_janela}-${alerta.hr_janela}-${alerta.dt_ini_hora}-${alerta.numero_alerta}`"
            class="multi-alerta-row"
          >
            <span
              class="multi-alerta-id"
              v-tooltip.right="{ value: formatMultiAlertTitle(alerta), escape: false, class: 'crm-alert-tooltip', showDelay: 120, hideDelay: 80 }"
              @pointerenter="setHoveredMultiAlert(alerta)"
              @pointerleave="clearHoveredAlert"
            >
              #{{ alerta.numero_alerta }}
            </span>
            <span class="alerta-crm alerta-crm-multi">{{ alerta.nu_crms_display }} CRMs</span>
            <span class="alerta-stat">{{ alerta.dt_ini_hora }} -> {{ alerta.dt_fim_hora }}</span>
            <span v-if="alerta.severidade" class="multi-alerta-severity">{{ alerta.severidade }}</span>
            <span class="alerta-stat">{{ alerta.nu_prescricoes_display }} em {{ alerta.ritmo_minutos_display }}min</span>
            <span class="alerta-stat">{{ alerta.ritmo_hora_num.toFixed(1) }}/h</span>
          </div>
        </div>
      </div>

      <!-- Legenda de Apoio Visual -->
      <div class="raiox-legend-tip animate-fade-in">
        <div class="legend-tip-item">
          <i class="pi pi-palette" />
          <span>Cores identificam <strong>médicos diferentes</strong> para destacar padrões de concentração.</span>
        </div>
        <div class="legend-tip-divider" />
        <div v-if="unicoAlertas.length > 0 || multiAlertas.length > 0" class="legend-tip-item">
          <span class="alerta-participacao-badge is-unico">U#1</span>
          <span class="alerta-participacao-badge is-multi">M#1</span>
          <span>Badges indicam a <strong>janela de alerta</strong> da qual a autorização participa.</span>
        </div>
        <div v-else class="legend-tip-item">
          <span class="sample-badge">2x</span>
          <span>Indica a <strong>recorrência</strong> deste médico na mesma janela horária.</span>
        </div>
      </div>

      <div v-if="!activeTransactionsLoading && activeTransactions.length === 0" class="raiox-empty">
        <i class="pi pi-inbox raiox-empty-icon" />
        <span>Nenhuma transação encontrada para este período.</span>
      </div>

      <div v-else class="raiox-table-wrapper" :class="{ 'is-loading': activeTransactionsLoading }">
        <table class="premium-table row-hover raiox-table flat-mode">
          <thead class="sticky-thead">
            <tr>
              <th width="12%" class="col-center">Horário</th>
              <th width="18%">Nº Autorização</th>
              <th width="16%">CRM</th>
              <th width="34%">Médico</th>
              <th width="20%" class="col-right">Valor Total</th>
            </tr>
          </thead>
          <tbody>
            <template v-for="tx in activeGroupedRaiox" :key="tx.num_autorizacao">
              <tr :class="getRaioxRowClasses(tx)">
                <td class="col-center raiox-time align-top">
                  {{ (tx.data_hora.split(' ')[1] || tx.data_hora).split('.')[0] }}
                </td>
                <td class="raiox-auth align-top">{{ tx.num_autorizacao }}</td>
                <td class="align-top">
                  <div class="crm-badge-container">
                    <span class="issue-tag raiox-crm-tag"
                          :style="activeCrmFrequencies[tx.id_medico] > 1 ? {
                            borderColor: getCRMColor(tx.id_medico),
                            color: getCRMColor(tx.id_medico),
                            background: `color-mix(in srgb, ${getCRMColor(tx.id_medico)} 15%, transparent)`
                          } : {}">
                      {{ tx.id_medico }}
                    </span>
                    <span v-if="activeCrmFrequencies[tx.id_medico] > 1"
                          class="crm-recurrence-badge"
                          :style="{ border: `1px solid ${getCRMColor(tx.id_medico)}`, color: getCRMColor(tx.id_medico) }">
                      {{ activeCrmFrequencies[tx.id_medico] }}x
                    </span>
                    <span
                      v-for="alerta in getAlertasDaTx(tx)"
                      :key="alerta.key"
                      class="alerta-participacao-badge"
                      :class="`is-${alerta.type}`"
                      v-tooltip.top="{ value: alerta.title, escape: false, class: 'crm-alert-tooltip', showDelay: 120, hideDelay: 80 }"
                      @pointerenter.stop="setHoveredTableAlert(alerta)"
                      @pointerleave.stop="clearHoveredAlert"
                    >
                      {{ alerta.label }}
                    </span>
                  </div>
                </td>
                <td class="align-top">
                  <span class="raiox-doctor-name">{{ truncate(tx.no_medico || 'Médico não identificado', 48) }}</span>
                </td>
                <td class="col-right raiox-val-cell align-top">
                  R$ {{ tx.vl_autorizacao.toFixed(2) }}
                </td>
              </tr>
            </template>
          </tbody>
          <tfoot v-if="activeGroupedRaiox.length > 0">
            <tr class="raiox-footer-row">
              <td colspan="4" class="col-right footer-label">VALOR TOTAL DO PERÍODO SELECIONADO:</td>
              <td class="col-right footer-value">R$ {{ activeRaioxTotalValue.toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) }}</td>
            </tr>
          </tfoot>
        </table>
      </div>
    </div>


  </div>
</template>

<style scoped>
/* ── Layout Base (Cronologia Flow) ───────────────────────────────────────── */
.cronologia-flow {
  display: flex;
  flex-direction: column;
  gap: 0;
  width: 100%;
}

.animate-fade-in {
  animation: fadeIn 0.4s cubic-bezier(0.4, 0, 0.2, 1);
}
@keyframes fadeIn {
  from { opacity: 0; transform: translateY(15px); }
  to { opacity: 1; transform: translateY(0); }
}

/* ── Breadcrumb Dinâmico ─────────────────────────────────────────────────── */
.drill-breadcrumb {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 0.5rem 1.25rem;
  background: var(--surface-card);
  border: 1px solid var(--card-border);
  border-radius: 99px;
  margin-bottom: 1.5rem;
  width: fit-content;
  align-self: center;
  box-shadow: 0 4px 12px rgba(0,0,0,0.1);
  backdrop-filter: blur(8px);
}
.crumb-item {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-size: 0.75rem;
  font-weight: 500;
  color: var(--text-muted);
  transition: all 0.2s;
}
.crumb-item.is-current { color: var(--primary-color); font-weight: 700; }
.crumb-icon { font-size: 0.85rem; }
.crumb-arrow { font-size: 0.6rem; opacity: 0.3; }
.crumb-anomaly-dot {
  width: 6px;
  height: 6px;
  background: #ef4444;
  border-radius: 50%;
  box-shadow: 0 0 8px #ef4444;
}

/* ── Painéis de Detalhamento (Drill Panels) ──────────────────────────────── */
.drill-panel {
  background: var(--card-bg);
  border: 1px solid var(--card-border);
  border-radius: 12px;
  padding: 1.25rem;
  position: relative;
  transition: all 0.3s ease;
  box-shadow: 0 2px 8px rgba(0,0,0,0.05);
  display: flex;
  flex-direction: column;
}

.level-daily { border-left: 4px solid var(--primary-color); }
.level-hourly { 
  border-left: 4px solid #6366f1; 
  background: color-mix(in srgb, var(--card-bg) 85%, transparent); 
}
.level-raiox { 
  border-left: 4px solid #8b5cf6; 
  background: color-mix(in srgb, var(--card-bg) 70%, transparent);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  min-height: 650px !important;
}

.drill-panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 1rem;
}
.drill-panel-title {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  font-size: 0.85rem;
  font-weight: 700;
  letter-spacing: 0.05em;
  text-transform: uppercase;
  color: var(--text-color-85);
}
.drill-panel-title i { font-size: 1.1rem; }

.drill-context-tag {
  font-size: 0.75rem;
  background: rgba(99, 102, 241, 0.15);
  color: #818cf8;
  padding: 2px 10px;
  border-radius: 6px;
  border: 1px solid rgba(99, 102, 241, 0.3);
  margin-left: 0.5rem;
  text-transform: none;
  letter-spacing: 0;
}
.drill-context-tag-raiox { background: rgba(139, 92, 246, 0.15); color: #a78bfa; border-color: rgba(139, 92, 246, 0.3); }

/* ── Conectores Visuais ─────────────────────────────────────────────────── */
.drill-connector {
  height: 40px;
  position: relative;
  display: flex;
  justify-content: center;
  align-items: center;
}
.connector-line {
  position: absolute;
  top: 0;
  bottom: 0;
  width: 2px;
  background: linear-gradient(to bottom, var(--card-border), var(--primary-color), var(--card-border));
  opacity: 0.5;
}
.connector-dot {
  width: 28px;
  height: 28px;
  background: var(--surface-card);
  border: 2px solid var(--primary-color);
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 2;
  box-shadow: 0 0 15px rgba(99, 102, 241, 0.3);
}
.connector-dot i { font-size: 0.75rem; color: var(--primary-color); }
.connector-dot-raiox { border-color: #8b5cf6; box-shadow: 0 0 15px rgba(139, 92, 246, 0.3); }
.connector-dot-raiox i { color: #8b5cf6; }

/* ── Elementos Internos ─────────────────────────────────────────────────── */
.drill-hint {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0.6rem;
  margin-top: 1.5rem;
  padding: 0.75rem;
  background: rgba(255,255,255,0.03);
  border-radius: 8px;
  font-size: 0.78rem;
  color: var(--text-muted);
  font-style: italic;
}
.drill-hint i { color: var(--primary-color); font-size: 0.9rem; animation: pulseHand 2s infinite; }
@keyframes pulseHand {
  0%, 100% { transform: scale(1); opacity: 0.6; }
  50% { transform: scale(1.2); opacity: 1; }
}

.subtitle { margin: 0; font-size: 0.8rem; color: var(--text-muted); }
.is-refreshing { opacity: 0.6; pointer-events: none; }

.daily-chart-wrapper { display: flex; flex-direction: column; gap: 0.5rem; }
.chart-legend-html { 
  display: flex; 
  align-items: center; 
  justify-content: center; 
  gap: 1.25rem; 
  padding: 0.5rem 0; 
  flex-wrap: wrap;
}
.legend-group {
  display: flex;
  align-items: center;
  gap: 1rem;
}
.legend-divider {
  width: 1px;
  height: 14px;
  background: var(--card-border);
  opacity: 0.6;
}
:global(.dark-mode) .legend-divider { background: rgba(255,255,255,0.1); }
.legend-item { display: flex; align-items: center; gap: 0.4rem; font-size: 0.72rem; color: var(--text-secondary); }
.legend-swatch { width: 14px; height: 8px; border-radius: 2px; }
.legend-dashed { background: none; border-top: 2px dashed #f59e0b; height: 0; width: 18px; }
.daily-dispensacao-chart { width: 100%; height: 280px; }
.hourly-chart { width: 100%; height: 240px; }

.chart-loading-badge { margin-left: 0.75rem; font-size: 0.78rem; color: var(--text-muted); }
.chart-empty { display: flex; align-items: center; gap: 0.6rem; padding: 2rem; color: var(--text-muted); justify-content: center; }

.filter-controls { display: flex; align-items: center; flex-wrap: wrap; row-gap: 0.5rem; }
.filter-toggle { display: flex; align-items: center; gap: 0.5rem; cursor: pointer; font-size: 0.75rem; color: var(--text-secondary); }
.filter-toggle.is-disabled { opacity: 0.45; cursor: not-allowed; }
.filter-toggle.is-disabled .toggle-slider,
.filter-toggle.is-disabled .toggle-label { cursor: not-allowed; }

/* ── Botões de Navegação do Gráfico ── */
.chart-nav-buttons {
  display: flex;
  gap: 2px;
  background: rgba(0, 0, 0, 0.04);
  padding: 2px;
  border-radius: 8px;
  border: 1px solid var(--card-border);
}

:global(.dark-mode) .chart-nav-buttons {
  background: rgba(255, 255, 255, 0.06) !important;
  border-color: rgba(255, 255, 255, 0.1) !important;
}

.nav-btn {
  background: transparent !important;
  border: none;
  color: var(--text-color-85);
  width: 28px;
  height: 28px;
  border-radius: 6px;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
}

:global(.dark-mode) .nav-btn {
  color: rgba(255, 255, 255, 0.8) !important;
}

.nav-btn:hover {
  background: var(--primary-color) !important;
  color: white !important;
  transform: translateY(-1px);
}

.nav-btn:active {
  transform: translateY(0);
}

.filter-divider {
  width: 1px;
  height: 18px;
  background: var(--card-border);
  margin: 0 12px;
  opacity: 0.6;
}

:global(.dark-mode) .filter-divider {
  background: rgba(255, 255, 255, 0.1);
}
.daily-rank-controls {
  display: flex;
  gap: 4px;
  background: rgba(0, 0, 0, 0.04);
  padding: 2px;
  border: 1px solid var(--card-border);
  border-radius: 8px;
}
:global(.dark-mode) .daily-rank-controls {
  background: rgba(255, 255, 255, 0.06);
  border-color: rgba(255, 255, 255, 0.1);
}
.rank-btn {
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
  min-height: 28px;
  padding: 0 0.55rem;
  border: 1px solid transparent;
  border-radius: 6px;
  background: transparent;
  color: var(--text-secondary);
  cursor: pointer;
  font-size: 0.7rem;
  font-weight: 700;
  white-space: normal;
  line-height: 1.2;
  text-align: left;
  transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
}
.rank-btn i { font-size: 0.75rem; }
.rank-btn .control-info-icon { font-size: 0.65rem; }
.rank-btn:hover {
  background: color-mix(in srgb, var(--text-color-85) 8%, transparent);
  color: var(--text-color-85);
}
.rank-btn.is-unico.is-active {
  background: rgba(245, 158, 11, 0.15);
  border-color: rgba(245, 158, 11, 0.3);
  color: #f59e0b;
}
.rank-btn.is-multiplo.is-active {
  background: rgba(139, 92, 246, 0.15);
  border-color: rgba(139, 92, 246, 0.3);
  color: #8b5cf6;
}
.rank-btn.is-volume.is-active {
  background: rgba(16, 185, 129, 0.15);
  border-color: rgba(16, 185, 129, 0.3);
  color: #10b981;
}
.rank-limit-select {
  min-height: 28px;
  border: 1px solid var(--card-border);
  border-radius: 6px;
  background: var(--surface-card);
  color: var(--text-color-85);
  padding: 0 1.7rem 0 0.55rem;
  font-size: 0.7rem;
  font-weight: 700;
  cursor: pointer;
}
.rank-limit-select:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}
.rank-limit-control {
  display: inline-flex;
  align-items: center;
  gap: 0.3rem;
}
.control-info-icon {
  color: var(--text-muted);
  cursor: help;
  flex-shrink: 0;
  line-height: 1;
  opacity: 0.65;
  transition: color 0.15s ease, opacity 0.15s ease;
}
.control-info-icon:hover {
  color: var(--primary-color);
  opacity: 1;
}
.control-info-icon:focus-visible,
.section-info-icon:focus-visible,
.nav-btn:focus-visible {
  outline: 2px solid color-mix(in srgb, var(--primary-color) 70%, transparent);
  outline-offset: 2px;
}
.rank-btn .control-info-icon { color: inherit; }
.rank-btn:hover .control-info-icon { opacity: 1; }
.rank-limit-info { margin-right: 0.15rem; }
.anomaly-filter-info { margin-left: 0.05rem; }
:global(.dark-mode) .rank-limit-select {
  background: rgba(255, 255, 255, 0.06);
  border-color: rgba(255, 255, 255, 0.1);
}
.filter-toggle input { display: none; }
.toggle-slider { position: relative; width: 32px; height: 18px; background-color: var(--tabs-border); border-radius: 20px; transition: 0.3s; }
.toggle-slider:before { content: ""; position: absolute; height: 12px; width: 12px; left: 3px; bottom: 3px; background-color: white; border-radius: 50%; transition: 0.3s; }
input:checked + .toggle-slider { background-color: var(--primary-color); }
input:checked + .toggle-slider:before { transform: translateX(14px); }

.anomalo-badge { background: rgba(239, 68, 68, 0.15); color: #ef4444; border: 1px solid rgba(239, 68, 68, 0.3); font-size: 0.65rem; font-weight: 700; padding: 2px 8px; border-radius: 99px; margin-left: 0.75rem; }
.concentracao-badge { background: rgba(245, 158, 11, 0.15); color: #f59e0b; border: 1px solid rgba(245, 158, 11, 0.3); font-size: 0.65rem; font-weight: 700; padding: 2px 8px; border-radius: 99px; margin-left: 0.75rem; }
.multiplo-badge { background: rgba(139, 92, 246, 0.15); color: #8b5cf6; border: 1px solid rgba(139, 92, 246, 0.3); font-size: 0.65rem; font-weight: 700; padding: 2px 8px; border-radius: 99px; margin-left: 0.75rem; }
.close-detail-btn { background: none; border: none; color: var(--text-muted); cursor: pointer; padding: 4px; border-radius: 4px; transition: all 0.2s; }
.close-detail-btn:hover { background: var(--surface-hover); color: #ef4444; }

.drill-panel-actions {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}

.reset-filter-btn {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  background: rgba(99, 102, 241, 0.1);
  border: 1px solid rgba(99, 102, 241, 0.2);
  color: #818cf8;
  padding: 4px 12px;
  border-radius: 6px;
  font-size: 0.7rem;
  font-weight: 700;
  cursor: pointer;
  transition: all 0.2s;
  text-transform: uppercase;
  letter-spacing: 0.02em;
}

.reset-filter-btn:hover {
  background: #6366f1;
  color: white;
  border-color: #6366f1;
  box-shadow: 0 4px 10px rgba(99, 102, 241, 0.3);
}

.reset-filter-btn i {
  font-size: 0.75rem;
}

/* ── Raio-X Table Styling ───────────────────────────────────────────────── */
.raiox-table-wrapper { 
  border-radius: 8px; 
  background: transparent; 
  border: 1px solid var(--tabs-border); 
  overflow: hidden; 
  flex: 1;
  display: flex;
  flex-direction: column;
}
.premium-table { width: 100%; border-collapse: collapse; }
.premium-table th { padding: 0.75rem 0.5rem; background: var(--card-bg); color: var(--text-secondary); font-size: 0.65rem; text-transform: uppercase; border-bottom: 2px solid var(--tabs-border); }
.premium-table td { padding: 0.75rem 0.5rem; border-bottom: 1px solid var(--tabs-border); color: var(--text-color-85); font-size: 0.78rem; }
.premium-table tbody tr:hover { background: rgba(255,255,255,0.03); cursor: pointer; }
.premium-table tbody tr.raiox-details-expanded-row:hover { background: transparent !important; cursor: default; }

.raiox-count-badge { background: rgba(139, 92, 246, 0.15); color: #a78bfa; border: 1px solid rgba(139, 92, 246, 0.3); border-radius: 99px; font-size: 0.65rem; padding: 1px 8px; margin-left: 0.75rem; }
.raiox-spinner { font-size: 0.8rem; margin-left: 0.5rem; }
.raiox-legend-tip {
  display: flex;
  align-items: center;
  gap: 1.5rem;
  padding: 0.75rem 1.25rem;
  background: rgba(139, 92, 246, 0.05);
  border: 1px dashed rgba(139, 92, 246, 0.2);
  border-radius: 8px;
  margin-bottom: 1.25rem;
}

.legend-tip-item {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  font-size: 0.72rem;
  color: var(--text-secondary);
}

.legend-tip-item i {
  color: #8b5cf6;
  font-size: 0.85rem;
}

.legend-tip-divider {
  width: 1px;
  height: 16px;
  background: rgba(139, 92, 246, 0.15);
}

.sample-badge {
  font-size: 0.6rem;
  font-weight: 800;
  color: #8b5cf6;
  border: 1px solid #8b5cf6;
  padding: 1px 4px;
  border-radius: 3px;
  background: rgba(139, 92, 246, 0.1);
}

.raiox-empty { 
  display: flex; 
  flex-direction: column; 
  align-items: center; 
  justify-content: center; 
  gap: 1rem; 
  padding: 3rem; 
  color: var(--text-muted); 
  flex: 1;
}
.raiox-empty-icon { font-size: 2rem; opacity: 0.3; }

.raiox-footer-row {
  background: rgba(139, 92, 246, 0.08);
  border-top: 2px solid var(--primary-color);
}

.footer-label {
  font-weight: 700;
  font-size: 0.7rem;
  letter-spacing: 0.05em;
  color: var(--text-secondary);
}

.footer-value {
  font-weight: 800;
  font-size: 0.9rem;
  color: var(--primary-color);
  font-family: var(--font-mono);
}

.crm-badge-container { display: flex; align-items: center; gap: 0.4rem; }
.issue-tag { font-size: 0.68rem; font-weight: 600; padding: 0.2rem 0.6rem; border-radius: 4px; }
.crm-recurrence-badge { font-size: 0.6rem; font-weight: 800; padding: 1px 4px; border-radius: 3px; }
.count-pill { background: var(--tabs-border); padding: 1px 6px; border-radius: 4px; font-weight: 600; font-size: 0.7rem; }
.raiox-doctor-name { color: var(--text-color-85); font-weight: 600; }
.raiox-val-cell { font-weight: 700; font-family: var(--font-mono); }

.col-center { text-align: center; }
.col-right { text-align: right; }
.sticky-thead th { position: sticky; top: 0; z-index: 10; }
.cursor-pointer { cursor: pointer; }
.align-top { vertical-align: top; }
.cursor-pointer-active, .cursor-pointer-active canvas { cursor: pointer !important; }

/* ── CRM ÚNICO ────────────────────────────────────────────────────────────── */
.section-separator {
  display: flex;
  align-items: center;
  gap: 1rem;
  margin: 2rem 0 1.5rem;
}
.separator-line {
  flex: 1;
  height: 1px;
  background: linear-gradient(to right, transparent, var(--card-border), transparent);
}
.separator-label {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-size: 0.72rem;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--text-muted);
  white-space: nowrap;
}

.level-unico { border-left: 4px solid #f59e0b; }
.level-raiox-unico {
  border-left: 4px solid #d97706;
  background: color-mix(in srgb, var(--card-bg) 70%, transparent);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
}

.connector-dot-unico { border-color: #f59e0b; box-shadow: 0 0 15px rgba(245,158,11,0.3); }
.connector-dot-unico i { color: #f59e0b; }

.drill-context-tag-unico { background: rgba(245,158,11,0.12); color: #fbbf24; border-color: rgba(245,158,11,0.3); }
.unico-count-badge { background: rgba(245,158,11,0.12); color: #fbbf24; border-color: rgba(245,158,11,0.3); }

/* Médicos Gatilho */
.unico-alertas-section {
  background: rgba(245,158,11,0.05);
  border: 1px dashed rgba(245,158,11,0.25);
  border-radius: 8px;
  padding: 0.75rem 1rem;
  margin-bottom: 1.25rem;
}
.unico-alertas-header {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-size: 0.72rem;
  font-weight: 700;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: #f59e0b;
  margin-bottom: 0.75rem;
}
.section-info-icon {
  font-size: 0.7rem;
  color: inherit;
  cursor: help;
  opacity: 0.65;
  transition: opacity 0.15s ease, color 0.15s ease;
}
.section-info-icon:hover {
  color: var(--text-color-85);
  opacity: 1;
}
.unico-alertas-list { display: flex; flex-wrap: wrap; gap: 0.5rem; }
.unico-alerta-chip {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  background: rgba(245,158,11,0.08);
  border: 1px solid rgba(245,158,11,0.22);
  border-radius: 6px;
  padding: 0.3rem 0.75rem;
  font-size: 0.72rem;
}
.unico-alertas-grouped-list {
  display: grid;
  gap: 0.75rem;
}
.unico-alerta-group {
  display: grid;
  gap: 0.35rem;
}
.unico-alerta-group-title {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  min-height: 1.3rem;
}
.unico-alerta-group-title .alerta-crm {
  font-size: 0.86rem;
  line-height: 1.2;
}
.unico-alerta-group-count {
  color: var(--text-secondary);
  background: rgba(245,158,11,0.08);
  border: 1px solid rgba(245,158,11,0.22);
  border-radius: 4px;
  padding: 0.1rem 0.45rem;
  font-size: 0.62rem;
  font-weight: 700;
  line-height: 1.2;
  text-transform: uppercase;
  white-space: nowrap;
}
.unico-alerta-group-items {
  display: flex;
  flex-wrap: wrap;
  gap: 0.45rem;
}
.unico-alerta-row {
  display: inline-flex;
  align-items: center;
  gap: 0.45rem;
  background: rgba(245,158,11,0.08);
  border: 1px solid rgba(245,158,11,0.22);
  border-radius: 6px;
  padding: 0.3rem 0.65rem;
  font-size: 0.72rem;
  min-height: 1.7rem;
  white-space: nowrap;
}
.alerta-alert-id {
  color: #f59e0b;
  background: rgba(245,158,11,0.12);
  border: 1px solid rgba(245,158,11,0.28);
  border-radius: 4px;
  padding: 0.05rem 0.35rem;
  font-size: 0.68rem;
  font-weight: 800;
  line-height: 1.2;
}
.alerta-severity {
  color: #f59e0b;
  font-weight: 800;
  text-transform: uppercase;
}
.alertas-multi-section {
  background: rgba(139, 92, 246, 0.05);
  border-color: rgba(139, 92, 246, 0.25);
}
.alertas-multi-section .unico-alertas-header {
  color: #8b5cf6;
}
.alertas-multi-section .unico-alerta-chip {
  background: rgba(139, 92, 246, 0.08);
  border-color: rgba(139, 92, 246, 0.22);
}
.multi-alertas-numbered-list {
  display: flex;
  flex-wrap: wrap;
  gap: 0.45rem;
}
.multi-alerta-row {
  display: inline-flex;
  align-items: center;
  gap: 0.45rem;
  background: rgba(139, 92, 246, 0.08);
  border: 1px solid rgba(139, 92, 246, 0.22);
  border-radius: 6px;
  padding: 0.3rem 0.65rem;
  font-size: 0.72rem;
  min-height: 1.7rem;
  white-space: nowrap;
}
.multi-alerta-id {
  color: #a78bfa;
  background: rgba(139, 92, 246, 0.14);
  border: 1px solid rgba(139, 92, 246, 0.32);
  border-radius: 4px;
  padding: 0.05rem 0.35rem;
  font-size: 0.68rem;
  font-weight: 800;
  line-height: 1.2;
}
.multi-alerta-severity {
  color: #a78bfa;
  font-weight: 800;
  text-transform: uppercase;
}
.alerta-crm-multi { color: #8b5cf6; }
.alerta-crm { font-weight: 700; }
.alerta-stat { color: var(--text-secondary); }
.alerta-sep { opacity: 0.3; }
.alerta-nivel { color: #f59e0b; font-size: 0.65rem; font-weight: 600; opacity: 0.8; }

:global(.p-tooltip.crm-alert-tooltip) {
  max-width: min(360px, calc(100vw - 2rem));
  padding: 0;
  background: var(--tooltip-bg);
  border: 1px solid var(--tooltip-border);
  border-radius: 9px;
  box-shadow: var(--tooltip-shadow);
}
:global(.p-tooltip.crm-info-tooltip) {
  max-width: min(360px, calc(100vw - 2rem));
  padding: 0;
  background: var(--tooltip-bg);
  border: 1px solid var(--tooltip-border);
  border-radius: 9px;
  box-shadow: var(--tooltip-shadow);
}
:global(.crm-alert-tooltip-content) {
  display: flex;
  width: min(330px, calc(100vw - 2rem));
  flex-direction: column;
  gap: 0.65rem;
  padding: 0.75rem 0.85rem;
  line-height: 1.35;
}
:global(.crm-alert-tooltip-title) {
  color: var(--text-color-85);
  font-size: 0.8rem;
  font-weight: 700;
  letter-spacing: 0.02em;
}
:global(.crm-alert-tooltip-intro) {
  margin: 0;
  color: var(--text-secondary);
  font-size: 0.72rem;
}
:global(.crm-alert-tooltip-details) {
  display: flex;
  flex-direction: column;
  gap: 0.3rem;
  padding: 0.55rem 0.65rem;
  border: 1px solid var(--tabs-border);
  border-radius: 6px;
  background: color-mix(in srgb, var(--card-bg) 70%, transparent);
}
:global(.crm-alert-tooltip-details > div) {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 1rem;
}
:global(.crm-alert-tooltip-details span) {
  color: var(--text-muted);
  font-size: 0.67rem;
}
:global(.crm-alert-tooltip-details strong) {
  color: var(--text-color-85);
  font-size: 0.7rem;
  text-align: right;
}
:global(.crm-alert-tooltip-note) {
  display: flex;
  flex-direction: column;
  gap: 0.2rem;
  color: var(--text-secondary);
  font-size: 0.68rem;
}
:global(.crm-alert-tooltip-note strong) {
  color: var(--risk-medium);
  font-size: 0.67rem;
  text-transform: uppercase;
  letter-spacing: 0.04em;
}
:global(.crm-info-tooltip-content) {
  display: flex;
  width: min(330px, calc(100vw - 2rem));
  flex-direction: column;
  gap: 0.62rem;
  padding: 0.75rem 0.85rem;
  line-height: 1.42;
}
:global(.crm-info-tooltip-title-row) {
  display: flex;
  align-items: center;
  gap: 0.45rem;
}
:global(.crm-info-tooltip-title-row > i) {
  flex-shrink: 0;
  color: var(--risk-medium);
  font-size: 0.8rem;
}
:global(.crm-info-tooltip-title) {
  color: var(--text-color-85);
  font-size: 0.8rem;
  font-weight: 700;
  letter-spacing: 0.02em;
}
:global(.crm-info-tooltip-intro) {
  margin: 0;
  color: var(--text-secondary);
  font-size: 0.72rem;
}
:global(.crm-info-tooltip-details) {
  display: flex;
  flex-direction: column;
  gap: 0.3rem;
  padding: 0.55rem 0.65rem;
  border: 1px solid var(--tabs-border);
  border-radius: 6px;
  background: color-mix(in srgb, var(--card-bg) 70%, transparent);
}
:global(.crm-info-tooltip-details > div) {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 1rem;
}
:global(.crm-info-tooltip-details span) {
  color: var(--text-muted);
  font-size: 0.67rem;
}
:global(.crm-info-tooltip-details strong) {
  color: var(--text-color-85);
  font-size: 0.7rem;
  text-align: right;
}
:global(.crm-info-tooltip-note) {
  display: flex;
  flex-direction: column;
  gap: 0.2rem;
  color: var(--text-secondary);
  font-size: 0.68rem;
}
:global(.crm-info-tooltip-note strong) {
  color: var(--risk-medium);
  font-size: 0.67rem;
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

/* Legenda CRM Único */
.unico-legend-tip {
  background: rgba(245,158,11,0.05);
  border-color: rgba(245,158,11,0.2);
}
.unico-legend-tip .legend-tip-item i { color: #f59e0b; }
.unico-gatilho-sample { font-size: 0.85rem; color: #f59e0b; line-height: 1; }

/* Linha gatilho na tabela */
.row-gatilho td:first-child { border-left: 3px solid #f59e0b; }
.row-multi-alerta td:first-child { border-left: 3px solid #8b5cf6; }
.premium-table tbody tr.row-alert-highlight-unico {
  background: rgba(245,158,11,0.12) !important;
}
.premium-table tbody tr.row-alert-highlight-multi {
  background: rgba(139, 92, 246, 0.13) !important;
}
.premium-table tbody tr.row-alert-highlight-unico td:first-child {
  border-left-color: #f59e0b;
}
.premium-table tbody tr.row-alert-highlight-multi td:first-child {
  border-left-color: #8b5cf6;
}

.alerta-participacao-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 2.1rem;
  border-radius: 4px;
  padding: 2px 6px;
  font-size: 0.62rem;
  font-weight: 800;
  line-height: 1.1;
  white-space: nowrap;
}
.alerta-participacao-badge.is-unico {
  color: #f59e0b;
  background: rgba(245,158,11,0.12);
  border: 1px solid rgba(245,158,11,0.3);
}
.alerta-participacao-badge.is-multi {
  color: #a78bfa;
  background: rgba(139, 92, 246, 0.12);
  border: 1px solid rgba(139, 92, 246, 0.3);
}

:global(.p-tooltip) {
  z-index: 99999 !important;
}

.gatilho-badge {
  font-size: 0.6rem;
  font-weight: 700;
  color: #f59e0b;
  background: rgba(245,158,11,0.12);
  border: 1px solid rgba(245,158,11,0.3);
  padding: 1px 5px;
  border-radius: 3px;
  white-space: nowrap;
}

.track-badge {
  font-size: 0.65rem;
  font-weight: 700;
  padding: 2px 10px;
  border-radius: 99px;
  letter-spacing: 0.02em;
  text-transform: uppercase;
  display: inline-flex;
  align-items: center;
  gap: 4px;
}
.track-badge.is-volume { background: rgba(16, 185, 129, 0.15); color: #10b981; border: 1px solid rgba(16, 185, 129, 0.3); }
.track-badge.is-unico { background: rgba(245, 158, 11, 0.15); color: #f59e0b; border: 1px solid rgba(245, 158, 11, 0.3); }
.track-badge.is-multiplo { background: rgba(139, 92, 246, 0.15); color: #8b5cf6; border: 1px solid rgba(139, 92, 246, 0.3); }

.anomalo-badge { background: rgba(239, 68, 68, 0.12); color: #f87171; border: 1px solid rgba(239, 68, 68, 0.3); border-radius: 4px; font-size: 0.65rem; font-weight: 700; padding: 2px 8px; }
.concentracao-badge { background: rgba(245, 158, 11, 0.12); color: #fbbf24; border: 1px solid rgba(245, 158, 11, 0.3); border-radius: 4px; font-size: 0.65rem; font-weight: 700; padding: 2px 8px; }
.multiplo-badge { background: rgba(139, 92, 246, 0.12); color: #a78bfa; border: 1px solid rgba(139, 92, 246, 0.3); border-radius: 4px; font-size: 0.65rem; font-weight: 700; padding: 2px 8px; }

/* ── Trilha de Eventos Horários Legada (Removida) ─────────────────────────── */
</style>
