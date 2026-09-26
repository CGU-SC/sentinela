<script setup>
import { computed, nextTick, ref, watch } from "vue";
import { storeToRefs } from 'pinia';
import { useCnpjDetailStore } from '@/stores/cnpjDetail';
import { useFilterStore } from '@/stores/filters';
import { useThemeStore } from '@/stores/theme';
import { useDelayedLoading } from '@/composables/useDelayedLoading';
import { useFormatting } from "@/composables/useFormatting";
import { useChartTheme } from '@/config/chartTheme';
import { API_ENDPOINTS } from '@/config/api';
import { downloadBlobFromResponse } from '@/utils/download';
import { getApiErrorMessage } from '@/utils/apiErrors';
import { useToast } from 'primevue/usetoast';
import Menu from 'primevue/menu';
import { CRM_RAIOX_INTERVALO_CURTO_SEGUNDOS } from '@/config/riskConfig';
import { CRM_IDENTITY_PALETTE } from '@/config/colors';
import TabPlaceholder from './TabPlaceholder.vue';
import EvidenciaFlag from '@/views/components/evidencias/EvidenciaFlag.vue';
import { alertasDaJanela } from '@/utils/evidencias';

import VChart from 'vue-echarts';
import { use } from 'echarts/core';
import { BarChart, LineChart } from 'echarts/charts';
import { GridComponent, TooltipComponent, DataZoomComponent, MarkLineComponent, MarkAreaComponent, LegendComponent } from 'echarts/components';
import { CanvasRenderer } from 'echarts/renderers';

use([BarChart, LineChart, GridComponent, TooltipComponent, DataZoomComponent, MarkLineComponent, MarkAreaComponent, LegendComponent, CanvasRenderer]);

const props = defineProps({
  cnpj: { type: String, required: true },
  periodSummary: { type: Object, default: null },
  periodLoading: { type: Boolean, default: false },
  razaoSocial: { type: String, default: '' },
});

const cnpjDetailStore = useCnpjDetailStore();
const filterStore = useFilterStore();
const toast = useToast();
const exportLoading = ref(false);

const {
  crmTimelineDataset,
  crmTimelineDatasetLoaded,
  crmTimelineDatasetLoading,
  selectedTimelineEvent,
} = storeToRefs(cnpjDetailStore);
const { formatarData, toLocalISO, formatTitleCase, formatCurrencyFull } = useFormatting();
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
const isRaioxAlertDay = (day) =>
  day.is_dia_com_volume_horario_anomalo === 1 || day.is_anomalo_unico === 1 || day.is_crm_multiplo === 1;

const raioxExportState = computed(() => {
  const { inicio, fim } = filterStore.apiParams;
  const cnpj = props.cnpj.replace(/\D/g, '').padStart(14, '0');
  const datasetKey = `${cnpj}|${inicio ?? ''}|${fim ?? ''}`;
  if (crmTimelineDatasetLoading.value || crmTimelineDatasetLoaded.value !== datasetKey) {
    return { enabled: false, reason: 'Aguarde o carregamento da cronologia do período.' };
  }
  const alertDays = (crmTimelineDataset.value?.days ?? []).filter(isRaioxAlertDay).length;
  if (!alertDays) {
    return { enabled: false, reason: 'Nenhum dia alertado no período selecionado.' };
  }
  return {
    enabled: true,
    reason: `Exporta todas as autorizações de ${alertDays} ${alertDays === 1 ? 'dia alertado' : 'dias alertados'} no período.`,
  };
});
const canExportRaiox = computed(() => raioxExportState.value.enabled);
const raioxExportTooltip = computed(() => {
  const { inicio, fim } = filterStore.apiParams;
  const periodo = inicio && fim ? `${formatarData(inicio)} a ${formatarData(fim)}` : 'Período filtrado';
  const alertDays = (crmTimelineDataset.value?.days ?? []).filter(isRaioxAlertDay).length;
  const { enabled, reason } = raioxExportState.value;
  return createCronologiaInfoTooltip(
    'Exportar · Dias alertados',
    enabled
      ? 'Gera um arquivo com todas as autorizações registradas nos dias que apresentaram alerta no período filtrado.'
      : reason,
    [
      ['Período', periodo],
      ['Dias alertados', enabled ? String(alertDays) : '—'],
      ['Alertas considerados', 'Volume Atípico e Autorizações em Sequência (Único CRM / Múltiplos CRMs)'],
      ['Excel', 'Planilha formatada com totais e resumos por dia e por médico'],
      ['CSV', 'Texto separado por ponto e vírgula, para outras ferramentas'],
    ],
    'O arquivo traz o dia inteiro, não apenas o horário do alerta.'
  );
});

const RAIOX_EXPORT_FORMATS = Object.freeze({
  xlsx: { label: 'Excel', extension: 'xlsx', icon: 'pi-file-excel' },
  csv: { label: 'CSV', extension: 'csv', icon: 'pi-file' },
});
const exportMenu = ref(null);
const exportMenuItems = [
  { label: 'Excel (.xlsx) · planilha formatada', icon: 'pi pi-file-excel', command: () => exportRaiox('xlsx') },
  { label: 'CSV (.csv) · texto simples', icon: 'pi pi-file', command: () => exportRaiox('csv') },
];

function toggleExportMenu(event) {
  exportMenu.value?.toggle(event);
}

async function exportRaiox(formato) {
  if (!canExportRaiox.value || exportLoading.value) return;
  const format = RAIOX_EXPORT_FORMATS[formato];
  if (!format) throw new Error(`Formato de exportação desconhecido: ${formato}`);
  const { inicio, fim } = filterStore.apiParams;
  const cnpj = props.cnpj.replace(/\D/g, '').padStart(14, '0');
  exportLoading.value = true;
  try {
    const response = await fetch(API_ENDPOINTS.analyticsCrmRaioXExport(cnpj, inicio, fim, formato));
    if (!response.ok) {
      throw new Error(
        await getApiErrorMessage(response, `Falha HTTP ${response.status} ao gerar o ${format.label} do Raio-X.`),
      );
    }
    const downloadResult = await downloadBlobFromResponse(
      response,
      `crm_raiox_dias_alertados_${cnpj}.${format.extension}`,
    );
    if (downloadResult?.desktop) {
      toast.add({
        group: 'download',
        severity: 'success',
        summary: `${format.label} do Raio-X salvo`,
        detail: `Arquivo salvo em notas_tecnicas\\${downloadResult.filename}.`,
        data: { path: downloadResult.path, icon: format.icon },
      });
    } else {
      toast.add({ severity: 'success', summary: `${format.label} do Raio-X baixado`, detail: downloadResult?.filename, life: 4000 });
    }
  } catch (error) {
    toast.add({ severity: 'error', summary: 'Falha na exportação', detail: error.message || `Não foi possível salvar o ${format.label}.`, life: 7000 });
  } finally {
    exportLoading.value = false;
  }
}


// ── Filtro e Zoom do Gráfico Diário ───────────────────────────────────────
const filterDailyOnlyAnomalous = ref(false);
// Padrão: piores dias por Volume Atípico, Top 20.
const dailyRankMode = ref('volume');
const dailyRankLimit = ref(20);
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

const dailyRankOptions = computed(() => [
  { value: null, label: 'Nenhum', className: 'is-none', tooltip: null },
  { value: 'unico', label: 'Sequência · Único CRM', className: 'is-unico', tooltip: cronologiaInfoTooltips.rankUnico },
  { value: 'multiplo', label: 'Sequência · Múltiplos CRMs', className: 'is-multiplo', tooltip: cronologiaInfoTooltips.rankMultiplo },
  { value: 'volume', label: 'Volume Atípico', className: 'is-volume', tooltip: cronologiaInfoTooltips.rankVolume },
]);

// No modo ranking com Top N (ou com poucos dias) todos os dias já estão visíveis:
// as setas de mês não têm efeito e ficam desabilitadas.
const dailyNavDisabled = computed(() =>
  Boolean(dailyRankMode.value)
  && (dailyRankLimit.value > 0 || filteredDailyDays.value.length <= DAILY_RANK_VISIBLE_LIMIT)
);
const dailyNavInfoTooltip = computed(() => (dailyNavDisabled.value
  ? createCronologiaInfoTooltip(
    'Navegação indisponível',
    'Todos os dias do ranking já estão visíveis no gráfico.',
    [['Para navegar', 'Escolha “Nenhum” ou a opção “Todos” no ranking']],
  )
  : createCronologiaInfoTooltip(
    'Navegar entre meses',
    'As setas deslocam a janela do histórico diário para o período anterior ou seguinte.',
    [['Ação', 'Recuar ou avançar aproximadamente 30 dias']],
    'A navegação altera somente a janela visual do gráfico e preserva os filtros ativos.'
  )));

function resetDailySelection() {
  selectedDay.value = null;
  selectedHourlyHour.value = null;
}

function setDailyRankMode(mode) {
  if (dailyRankMode.value === mode) return;
  // Limpa a seleção ANTES de trocar a lista: assim o watch de filteredDailyDays
  // refaz a auto-seleção e reposiciona o zoom para a nova lista. Sem isso, o
  // zoom da visão anterior (ex.: últimos 30 de 300 dias = 90–100%) era aplicado
  // ao Top 10 e só 1 barra aparecia.
  resetDailySelection();
  dailyRankMode.value = mode;
  if (mode) filterDailyOnlyAnomalous.value = false;
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

const SEVERIDADE_ALERTA = {
  EXTREMO: { label: 'Extremo', className: 'is-extremo' },
  CRITICO: { label: 'Crítico', className: 'is-critico' },
  GRAVE: { label: 'Grave', className: 'is-grave' },
  ALTO: { label: 'Alto', className: 'is-alto' },
  ALERTA: { label: 'Alerta', className: 'is-alerta' },
};

function formatSeveridadeAlerta(severidade) {
  const key = String(severidade || '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').toUpperCase();
  return SEVERIDADE_ALERTA[key] ?? { label: severidade || '—', className: 'is-alerta' };
}

// Lista única dos alertas de sequência (Único CRM + Múltiplos CRMs), em ordem de início.
const alertasSequencia = computed(() => {
  const unicos = unicoAlertasAgrupados.value.flatMap(grupo => grupo.alertas).map(alerta => ({
    key: `U-${alerta.numero_alerta}`,
    tipo: 'unico',
    codigo: `U#${alerta.numero_alerta}`,
    tipoLabel: 'Único CRM',
    inicio: alerta.dt_ini_hora,
    fim: alerta.dt_fim_hora,
    medico: alerta.id_medico,
    medicoColor: getCRMColor(alerta.id_medico),
    qtd: alerta.ritmo_qtd_display,
    minutos: alerta.ritmo_minutos_display,
    severidade: formatSeveridadeAlerta(alerta.severidade),
    tooltip: formatUnicoAlertTitle(alerta),
    hover: () => setHoveredUnicoAlert(alerta),
  }));
  const multiplos = multiAlertasNumerados.value.map(alerta => ({
    key: `M-${alerta.numero_alerta}`,
    tipo: 'multi',
    codigo: `M#${alerta.numero_alerta}`,
    tipoLabel: 'Múltiplos CRMs',
    inicio: alerta.dt_ini_hora,
    fim: alerta.dt_fim_hora,
    medico: `${alerta.nu_crms_display} CRMs`,
    medicoColor: null,
    qtd: alerta.nu_prescricoes_display,
    minutos: alerta.ritmo_minutos_display,
    severidade: formatSeveridadeAlerta(alerta.severidade),
    tooltip: formatMultiAlertTitle(alerta),
    hover: () => setHoveredMultiAlert(alerta),
  }));
  return [...unicos, ...multiplos].sort((a, b) =>
    String(a.inicio || '').localeCompare(String(b.inicio || '')) || a.tipo.localeCompare(b.tipo) || a.key.localeCompare(b.key)
  );
});

const alertasSequenciaTitulo = computed(() => (
  selectedHourlyHour.value === 'all' || selectedHourlyHour.value === null
    ? 'Alertas do dia'
    : `Alertas das ${String(selectedHourlyHour.value).padStart(2, '0')}h`
));

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
          <div class="${String(value).length > 32 ? 'is-long' : ''}">
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
    'Ranqueamento · Volume Atípico',
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
  raioxTransacoes: createCronologiaInfoTooltip(
    'Raio-X: transações',
    'Lista cada autorização do dia (ou da hora selecionada) em ordem cronológica, com CRM, médico e valor.',
    [
      ['CRM colorido', 'Identifica os médicos que mais se repetem na janela (até 6 cores)'],
      ['CRM sem cor', 'Médico com uma única autorização ou fora dos 6 mais frequentes'],
      ['Contagem (ex.: 50×)', 'Total de autorizações do médico na janela, exibido na primeira aparição'],
      ['U#1 / M#1', 'Alerta de sequência (Único / Múltiplos CRMs) do qual a autorização participa'],
      ['Intervalo', 'Tempo desde a autorização anterior; curtos em destaque'],
    ],
    'Passe o mouse sobre um alerta na lista acima ou sobre um código U#/M# para destacar as autorizações correspondentes.'
  ),
  raioxIntervalo: createCronologiaInfoTooltip(
    'Intervalo entre autorizações',
    'Tempo decorrido desde a autorização anterior na lista, em minutos e segundos (ou horas, minutos e segundos).',
    [['Destaque', `Intervalos abaixo de ${CRM_RAIOX_INTERVALO_CURTO_SEGUNDOS} segundos`], ['Primeira linha', 'Sem autorização anterior (—)']],
    'Sequências de intervalos curtos indicam lançamentos em rajada, típicos das autorizações em sequência. Quando uma hora está selecionada, o intervalo considera apenas as autorizações daquela hora.'
  ),
  raioxEvidencia: createCronologiaInfoTooltip(
    'Marcar como evidência',
    'A bandeira guarda a autorização na cesta de evidências desta farmácia, com uma nota opcional.',
    [
      ['Bandeira vazia', 'Clique para marcar'],
      ['Bandeira preenchida', 'Já marcada: clique para editar a nota ou remover'],
      ['Dia e hora', 'Use “Marcar evidência” acima dos gráficos dos painéis 1 (dia selecionado) e 2 (hora selecionada)'],
    ],
    'As evidências ficam no painel Evidências do estabelecimento e em Listas › Evidências. Marcar a primeira evidência adiciona a farmácia às Farmácias Monitoradas.'
  ),
  alertasSection: createCronologiaInfoTooltip(
    'Alertas de Autorizações em Sequência',
    'Janelas em que muitas autorizações foram emitidas em sequência, em um intervalo reduzido.',
    [
      ['Único CRM (U#)', 'Sequência com o mesmo médico'],
      ['Múltiplos CRMs (M#)', 'Sequência com participação de diferentes médicos'],
      ['Ritmo', 'Autorizações na janela e sua duração'],
    ],
    'Passe o mouse sobre um alerta para destacar as autorizações correspondentes na tabela abaixo; os códigos U# e M# também aparecem nas autorizações.'
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

function segundosDoDia(dataHora) {
  const match = String(dataHora ?? '').match(/(\d{2}):(\d{2}):(\d{2})/);
  if (!match) throw new Error(`Horário inválido no Raio-X: ${dataHora}`);
  return Number(match[1]) * 3600 + Number(match[2]) * 60 + Number(match[3]);
}

function formatIntervalo(segundos) {
  const h = Math.floor(segundos / 3600);
  const m = Math.floor((segundos % 3600) / 60);
  const s = String(segundos % 60).padStart(2, '0');
  return h > 0 ? `+${h}:${String(m).padStart(2, '0')}:${s}` : `+${m}:${s}`;
}

// Intervalo desde a autorização anterior (lista já em ordem cronológica).
const raioxIntervalos = computed(() => {
  const mapa = new Map();
  let anterior = null;
  for (const tx of groupedRaiox.value) {
    const atual = segundosDoDia(tx.data_hora);
    if (anterior === null) {
      mapa.set(tx.num_autorizacao, null);
    } else {
      const delta = Math.max(0, atual - anterior);
      mapa.set(tx.num_autorizacao, {
        texto: formatIntervalo(delta),
        curto: delta < CRM_RAIOX_INTERVALO_CURTO_SEGUNDOS,
      });
    }
    anterior = atual;
  }
  return mapa;
});

const crmFrequencies = computed(() => {
  const freqs = {};
  groupedRaiox.value.forEach(tx => { freqs[tx.id_medico] = (freqs[tx.id_medico] || 0) + 1; });
  return freqs;
});

const raioxTotalValue = computed(() => {
  return groupedRaiox.value.reduce((sum, tx) => sum + tx.vl_autorizacao, 0);
});

// Cor de identidade por médico: paleta fixa atribuída por frequência na janela
// do Raio-X (mais frequente = 1ª cor). Médicos que aparecem uma única vez, ou
// além da quantidade de cores da paleta, ficam sem cor (null).
const crmColorMap = computed(() => {
  const paleta = CRM_IDENTITY_PALETTE[themeStore.isDark ? 'dark' : 'light'];
  const primeiraPosicao = new Map();
  groupedRaiox.value.forEach((tx, idx) => {
    if (!primeiraPosicao.has(tx.id_medico)) primeiraPosicao.set(tx.id_medico, idx);
  });
  const ordenados = Object.entries(crmFrequencies.value)
    .filter(([, qtd]) => qtd > 1)
    .sort((a, b) => b[1] - a[1] || primeiraPosicao.get(a[0]) - primeiraPosicao.get(b[0]));
  const mapa = new Map();
  ordenados.slice(0, paleta.length).forEach(([id], idx) => mapa.set(id, paleta[idx]));
  return mapa;
});

function getCRMColor(idMedico) {
  return crmColorMap.value.get(String(idMedico)) ?? null;
}

// Primeira autorização de cada médico na janela: só nela aparece a contagem (N×).
const primeiraAutorizacaoPorCrm = computed(() => {
  const set = new Set();
  const vistos = new Set();
  for (const tx of groupedRaiox.value) {
    if (!vistos.has(tx.id_medico)) {
      vistos.add(tx.id_medico);
      set.add(tx.num_autorizacao);
    }
  }
  return set;
});

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
  const dates = dailyDates.value;
  // Ano no eixo: sempre no ranking (datas fora de ordem) e na linha do tempo que cruza anos.
  const showYearOnAxis = Boolean(dailyRankMode.value)
    || (dates.length > 0 && String(dates[0]).slice(0, 4) !== String(dates[dates.length - 1]).slice(0, 4));
  const selectedDate = selectedDay.value?.dt_janela ?? null;
  const selectedLabelColor = themeStore.isDark ? '#f8fafc' : '#0f172a';

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
        formatter: (v) => {
          if (!v) return '';
          const label = showYearOnAxis
            ? `${v.slice(8, 10)}/${v.slice(5, 7)}/${v.slice(2, 4)}`
            : `${v.slice(8, 10)}/${v.slice(5, 7)}`;
          return v === selectedDate ? `{sel|${label}}` : label;
        },
        interval: 'auto',
        rotate: 45,
        fontSize: 10,
        color: chartTheme.value.muted,
        rich: {
          sel: { fontSize: 11, fontWeight: 600, color: selectedLabelColor },
        },
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
      // Ancorado no topo, no lado oposto ao cursor: não cobre a barra em foco nem as vizinhas.
      position: (point, params, dom, rect, size) => {
        const gap = 12;
        const viewWidth = size.viewSize[0];
        const tooltipWidth = size.contentSize[0];
        const x = point[0] < viewWidth / 2
          ? viewWidth - tooltipWidth - gap
          : gap + 40;
        return [Math.max(gap, x), 4];
      },
      textStyle: { color: chartTheme.value.tooltipText, fontFamily: 'Inter, sans-serif', fontSize: 12 },
      shadowBlur: 10,
      shadowColor: 'rgba(0,0,0,0.15)',
      formatter: (p) => {
        const idx = Array.isArray(p) ? p[0]?.dataIndex : p.dataIndex;
        const day = filteredDailyDays.value?.[idx];
        if (!day) return '';
        const c = chartTheme.value;
        const badges = [];
        if (day.is_volume_horario_anomalo === 1) {
          badges.push('<span style="font-size:10px; background:rgba(16, 185, 129, 0.15); color:#10b981; padding:2px 8px; border-radius:4px; font-weight:600; border:1px solid rgba(16, 185, 129, 0.3); margin-left:8px;">⚠ Volume Atípico</span>');
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
            ${(day.is_volume_horario_anomalo === 1 || day.is_crm_unico === 1 || day.is_crm_multiplo === 1) ? `<div style="margin-top:10px; font-size:11px; color:${c.tooltipText}; opacity:.85; text-align:center;">Clique na barra para abrir a análise horária</div>` : ''}
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
        silent: false,
        // Faixa de fundo suave na coluna do dia selecionado (atrás das barras).
        markArea: selectedDate
          ? {
              silent: true,
              itemStyle: { color: themeStore.isDark ? 'rgba(255, 255, 255, 0.07)' : 'rgba(15, 23, 42, 0.06)' },
              data: [[{ xAxis: selectedDate }, { xAxis: selectedDate }]],
            }
          : undefined,
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
          const isSelected = selectedDate === day.dt_janela;
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
              opacity: hasSelection && !isSelected ? 0.55 : 1,
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
        // No ranking os dias não são vizinhos no tempo: a linha em degrau não teria significado.
        data: dailyRankMode.value ? [] : dailyMedians.value,
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
  const hourLabel = (h) => `${String(h).padStart(2, '0')}h`;
  const hasSelectedHour = selectedHourlyHour.value !== 'all' && selectedHourlyHour.value !== null;
  const selectedHourLabel = hasSelectedHour ? hourLabel(selectedHourlyHour.value) : null;
  const selectedLabelColor = themeStore.isDark ? '#f8fafc' : '#0f172a';

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
        axisLabel: {
          color: c.muted,
          fontSize: 10,
          fontWeight: 600,
          fontFamily: 'Inter, sans-serif',
          interval: 0,
          formatter: (v, i) => (v === selectedHourLabel ? `{sel|${v}}` : (i % 2 === 0 ? v : '')),
          rich: { sel: { fontSize: 11, fontWeight: 600, color: selectedLabelColor } },
        },
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
              opacity: hasSelection && !isSelected ? 0.55 : 1
            } 
          };
        }),
        // Faixa de fundo suave na coluna da hora selecionada (mesmo padrão do Histórico Diário).
        markArea: selectedHourLabel
          ? {
              silent: true,
              itemStyle: { color: themeStore.isDark ? 'rgba(255, 255, 255, 0.07)' : 'rgba(15, 23, 42, 0.06)' },
              data: [[{ xAxis: selectedHourLabel }, { xAxis: selectedHourLabel }]],
            }
          : undefined,
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

// flush 'sync': a seleção precisa ser limpa antes do watch de filteredDailyDays
// rodar, para que ele recalcule a auto-seleção e o zoom da nova lista.
watch(dailyRankLimit, () => {
  if (!dailyRankMode.value) return;
  resetDailySelection();
}, { flush: 'sync' });

watch(filterDailyOnlyAnomalous, () => {
  resetDailySelection();
}, { flush: 'sync' });

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
// immediate: a navegação pode chegar antes de este componente montar (ex.: vindo
// do painel de evidências com a Cronologia ainda fechada e os dados já em cache).
watch([selectedTimelineEvent, timelineDailyDataset], async ([evt, profile]) => {
  if (!evt || !profile) return;
  // Limpa já: permite nova navegação para o mesmo alvo e evita reprocessar.
  cnpjDetailStore.clearTimelineNavigation();

  const rawDayObj = profile.days.find(d => d.dt_janela === evt.date);
  if (!rawDayObj) {
    toast.add({
      severity: 'warn',
      summary: 'Dia fora do período em análise',
      detail: `${formatarData(evt.date)} não está no período filtrado. Ajuste o período para abrir este item.`,
      life: 8000,
    });
    return;
  }
  const dayObj = normalizeDailyDay(rawDayObj);

  // No ranking (ou com "apenas anomalias") o dia pode não estar entre os exibidos:
  // volta para a série completa antes de selecionar.
  if (!filteredDailyDays.value.some(d => d.dt_janela === evt.date)) {
    dailyRankMode.value = null;
    filterDailyOnlyAnomalous.value = false;
  }

  // 1. Seleciona o dia e, se informada, a hora
  const hour = parseTimelineHour(evt.hour);
  selectedDay.value = dayObj;
  selectedHourlyHour.value = hour ?? 'all';

  // 2. Centraliza o zoom na lista exibida
  const lista = filteredDailyDays.value;
  const idx = lista.findIndex(d => d.dt_janela === evt.date);
  if (idx !== -1) {
    setDailyZoomWindow(lista.length, idx, dailyRankMode.value ? DAILY_RANK_VISIBLE_LIMIT : 30);
  }

  // 3. Carrega as transações e, se for o caso, destaca a autorização
  await ensureRaioxLoaded(evt.date, hour);
  if (evt.autorizacao) await focarAutorizacao(String(evt.autorizacao));
}, { immediate: true });

function parseTimelineHour(value) {
  if (value === null || value === undefined || value === 'all') return null;
  const hour = Number.parseInt(String(value), 10);
  return Number.isInteger(hour) && hour >= 0 && hour <= 23 ? hour : null;
}

// ── Destaque de autorização (navegação vinda da cesta de evidências) ──────
const focoAutorizacao = ref(null);
let focoTimer = null;

async function focarAutorizacao(numAutorizacao) {
  await nextTick();
  const existe = activeGroupedRaiox.value.some(tx => String(tx.num_autorizacao) === numAutorizacao);
  if (!existe) {
    toast.add({
      severity: 'warn',
      summary: 'Autorização não encontrada',
      detail: `A autorização nº ${numAutorizacao} não aparece nesta janela do Raio-X.`,
      life: 8000,
    });
    return;
  }
  focoAutorizacao.value = numAutorizacao;
  await nextTick();
  document
    .querySelector(`[data-autorizacao="${CSS.escape(numAutorizacao)}"]`)
    ?.scrollIntoView({ behavior: 'smooth', block: 'center' });
  window.clearTimeout(focoTimer);
  focoTimer = window.setTimeout(() => { focoAutorizacao.value = null; }, 2600);
}

// ── Cesta de evidências: alvos e retratos dos itens marcados ──────────────
const cnpjDigits = computed(() => props.cnpj.replace(/\D/g, '').padStart(14, '0'));

function horarioDaTx(tx) {
  return (tx.data_hora.split(' ')[1] || tx.data_hora).split('.')[0];
}

function horaDaTx(tx) {
  const hour = Number.parseInt(horarioDaTx(tx).slice(0, 2), 10);
  if (!Number.isInteger(hour)) throw new Error(`Horário inválido na autorização ${tx.num_autorizacao}.`);
  return hour;
}

function alvoDaTx(tx) {
  return {
    cnpj: cnpjDigits.value,
    tipo: 'autorizacao',
    dt_janela: selectedDay.value.dt_janela,
    hora: horaDaTx(tx),
    num_autorizacao: String(tx.num_autorizacao),
  };
}

function snapshotDia() {
  const dia = selectedDay.value;
  if (!dia) throw new Error('Nenhum dia selecionado.');
  return { qtd: Number(dia.nu_prescricoes_dia ?? 0), alertas: alertasDaJanela(dia) };
}

function snapshotHora() {
  const ponto = hourlyPoints.value.find(p => p.hr_janela === selectedHourlyHour.value);
  if (!ponto) throw new Error('Os dados da hora selecionada não estão disponíveis.');
  return { qtd: Number(ponto.nu_prescricoes ?? 0), alertas: alertasDaJanela(ponto) };
}

function snapshotDaTx(tx) {
  return () => ({
    horario: horarioDaTx(tx),
    crm: tx.id_medico == null ? null : String(tx.id_medico),
    medico: tx.no_medico ? formatTitleCase(tx.no_medico) : null,
    valor: Number(tx.vl_autorizacao ?? 0),
    intervalo: raioxIntervalos.value.get(tx.num_autorizacao)?.texto ?? null,
    alertas: getAlertasDaTx(tx).map(alerta => alerta.label),
  });
}

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
  // Só as autorizações dentro da janela do alerta (não todas as do médico).
  if (alert.type === 'unico') return getUnicoAlertasDaTx(tx).some(a => `U-${a.numero_alerta}` === alert.key) ? 'unico' : null;
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
    // Ao passar o mouse num alerta, as linhas de fora dele recuam; as do alerta ficam como estão.
    'row-alert-dimmed': hoveredAlert.value !== null && hoveredType === null,
    'row-evidencia-foco': focoAutorizacao.value === String(tx.num_autorizacao),
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
    <div class="drill-navigation-row">
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
      <span class="crm-export-wrapper">
        <button
          class="crm-export-button"
          type="button"
          :disabled="!canExportRaiox || exportLoading"
          :aria-busy="exportLoading"
          aria-haspopup="menu"
          aria-controls="crm-export-menu"
          :aria-label="`Exportar dias alertados. ${raioxExportState.reason}`"
          @click="toggleExportMenu"
        >
          <i :class="exportLoading ? 'pi pi-spinner pi-spin' : 'pi pi-download'" aria-hidden="true" />
          <span>{{ exportLoading ? 'Exportando…' : 'Exportar dias alertados' }}</span>
          <i v-if="!exportLoading" class="pi pi-chevron-down crm-export-caret" aria-hidden="true" />
        </button>
        <Menu id="crm-export-menu" ref="exportMenu" :model="exportMenuItems" :popup="true" />
        <i
          class="pi pi-info-circle control-info-icon crm-export-info"
          role="img"
          tabindex="0"
          aria-label="Informações sobre a exportação dos dias alertados"
          v-tooltip.left="raioxExportTooltip"
        />
      </span>
    </div>

    <!-- NÍVEL 1: Histórico Diário -->
    <div class="drill-panel level-daily" :class="{ 'is-refreshing': showRefreshingDaily }">
      <div class="drill-panel-header">
        <div class="drill-panel-title">
          <span class="drill-step" aria-hidden="true">1</span>
          <span>HISTÓRICO DIÁRIO DE DISPENSAÇÕES</span>
          <span v-if="crmTimelineDatasetLoading" class="chart-loading-badge">
            <i class="pi pi-spinner pi-spin"></i> Carregando...
          </span>
        </div>
      </div>
      <p class="subtitle daily-subtitle">
        Autorizações por dia. Barras vermelhas indicam dias com alerta —
        <strong>clique em uma barra</strong> para abrir a análise horária do dia.
      </p>
      <div class="daily-toolbar" role="group" aria-label="Controles do histórico diário">
        <div class="daily-toolbar-group daily-toolbar-nav">
          <span class="daily-toolbar-label daily-toolbar-label-info">
            Navegar
            <i
              class="pi pi-info-circle control-info-icon"
              role="img"
              aria-label="Informações sobre a navegação entre meses"
              tabindex="0"
              v-tooltip.right="dailyNavInfoTooltip"
            />
          </span>
          <div class="daily-toolbar-nav-buttons">
            <button
              class="nav-btn"
              type="button"
              :disabled="dailyNavDisabled"
              @click="shiftZoom('prev')"
              aria-label="Mês anterior"
            >
              <i class="pi pi-chevron-left" />
            </button>
            <button
              class="nav-btn"
              type="button"
              :disabled="dailyNavDisabled"
              @click="shiftZoom('next')"
              aria-label="Próximo mês"
            >
              <i class="pi pi-chevron-right" />
            </button>
          </div>
        </div>

        <div class="daily-toolbar-group daily-toolbar-rank">
          <span id="daily-rank-label" class="daily-toolbar-label">Piores dias por</span>
          <div class="daily-toolbar-row">
            <div class="rank-segmented" role="radiogroup" aria-labelledby="daily-rank-label">
              <button
                v-for="option in dailyRankOptions"
                :key="option.value ?? 'nenhum'"
                type="button"
                role="radio"
                class="rank-seg"
                :class="[option.className, { 'is-active': dailyRankMode === option.value }]"
                :aria-checked="dailyRankMode === option.value"
                @click="setDailyRankMode(option.value)"
              >
                <span v-if="option.value" class="rank-seg-dot" aria-hidden="true" />
                <span>{{ option.label }}</span>
                <i
                  v-if="option.tooltip"
                  class="pi pi-info-circle control-info-icon"
                  role="img"
                  :aria-label="`Informações sobre ${option.label}`"
                  v-tooltip.top="option.tooltip"
                  @click.stop
                />
              </button>
            </div>
            <div class="rank-limit-control">
              <select
                v-model.number="dailyRankLimit"
                class="rank-limit-select"
                aria-label="Quantidade de dias exibidos"
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
        </div>

        <div class="daily-toolbar-group daily-toolbar-filter">
          <span class="daily-toolbar-label">Filtro</span>
          <label class="filter-toggle" :class="{ 'is-disabled': dailyRankMode }">
            <input type="checkbox" v-model="filterDailyOnlyAnomalous" :disabled="dailyRankMode !== null" />
            <span class="toggle-slider"></span>
            <span class="toggle-label">Apenas anomalias</span>
            <i
              class="pi pi-info-circle control-info-icon anomaly-filter-info"
              role="img"
              aria-label="Informações sobre o filtro Apenas anomalias"
              tabindex="0"
              v-tooltip.left="cronologiaInfoTooltips.onlyAnomalies"
              @click.prevent.stop
            />
          </label>
          <span class="daily-toolbar-help">
            {{ dailyRankMode ? 'Indisponível com ranking ativo — escolha “Nenhum”.' : 'Oculta os dias de operação normal.' }}
          </span>
        </div>
      </div>
      
      <div v-if="!timelineDatasetReady && !crmTimelineDatasetLoading" class="chart-empty">
        <i class="pi pi-chart-bar" style="font-size:1.5rem; opacity:.4"></i>
        <span>Sem dados da linha do tempo CRM disponíveis.</span>
      </div>
      <div class="daily-chart-wrapper" :class="{ 'cursor-pointer-active': hoveredDailyDayIndex !== null }">
        <div class="legend-bar-evid">
        <div class="chart-legend-html">
          <span class="legend-item">
            <span class="legend-swatch legend-bar" style="background: #ef4444;"></span>
            Dia Anômalo
          </span>
          <span class="legend-item">
            <span class="legend-swatch legend-bar" :style="{ background: chartUFAccents.bar1 }"></span>
            Dia Normal
          </span>
          <span v-if="!dailyRankMode" class="legend-item">
            <span class="legend-swatch legend-dashed"></span>
            Mediana de Referência
          </span>
        </div>
        <div v-if="selectedDay" class="legend-evid">
          <span class="legend-evid-contexto">
            Dia selecionado: <strong>{{ formatarData(selectedDay.dt_janela) }}</strong>
          </span>
          <EvidenciaFlag
            :alvo="{ cnpj: cnpjDigits, tipo: 'dia', dt_janela: selectedDay.dt_janela }"
            :snapshot="snapshotDia"
            :descricao="`Dia ${formatarData(selectedDay.dt_janela)}`"
            :razao-social="razaoSocial"
          />
        </div>
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


    <!-- Ligação entre etapas: seta em SVG com o contexto da seleção -->
    <div v-if="selectedDay" class="drill-link" aria-hidden="true">
      <svg class="drill-link-svg" viewBox="0 0 24 60" width="24" height="60">
        <defs>
          <linearGradient id="drillLinkFadeDia" gradientUnits="userSpaceOnUse" x1="12" y1="0" x2="12" y2="50">
            <stop offset="0" stop-color="currentColor" stop-opacity="0" />
            <stop offset="0.3" stop-color="currentColor" stop-opacity="0.55" />
            <stop offset="1" stop-color="currentColor" stop-opacity="0.95" />
          </linearGradient>
        </defs>
        <path class="drill-link-line" d="M12 0 V50" stroke="url(#drillLinkFadeDia)" />
        <path class="drill-link-head" d="M7.5 48 L12 55 L16.5 48 Z" />
      </svg>
      <span class="drill-link-chip">
        <i class="pi pi-calendar" />
        {{ formatarData(selectedDay.dt_janela) }}
      </span>
    </div>

    <!-- NÍVEL 2: Análise Horária -->
    <div v-if="selectedDay" class="drill-panel level-hourly animate-fade-in" :class="{ 'is-refreshing': showRefreshingHourly }">
      <div class="drill-panel-header">
        <div class="drill-panel-title">
          <span class="drill-step" aria-hidden="true">2</span>
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
        <div class="legend-bar-evid">
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
        <div v-if="Number.isInteger(selectedHourlyHour)" class="legend-evid">
          <span class="legend-evid-contexto">
            Hora selecionada: <strong>{{ String(selectedHourlyHour).padStart(2, '0') }}h</strong>
          </span>
          <EvidenciaFlag
            :alvo="{ cnpj: cnpjDigits, tipo: 'hora', dt_janela: selectedDay.dt_janela, hora: selectedHourlyHour }"
            :snapshot="snapshotHora"
            :descricao="`${formatarData(selectedDay.dt_janela)}, das ${String(selectedHourlyHour).padStart(2, '0')}h às ${String(selectedHourlyHour).padStart(2, '0')}h59`"
            :razao-social="razaoSocial"
          />
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


    <!-- Ligação entre etapas: seta em SVG com o contexto da seleção -->
    <div v-if="selectedHourlyHour !== null" class="drill-link" aria-hidden="true">
      <svg class="drill-link-svg" viewBox="0 0 24 60" width="24" height="60">
        <defs>
          <linearGradient id="drillLinkFadeHora" gradientUnits="userSpaceOnUse" x1="12" y1="0" x2="12" y2="50">
            <stop offset="0" stop-color="currentColor" stop-opacity="0" />
            <stop offset="0.3" stop-color="currentColor" stop-opacity="0.55" />
            <stop offset="1" stop-color="currentColor" stop-opacity="0.95" />
          </linearGradient>
        </defs>
        <path class="drill-link-line" d="M12 0 V50" stroke="url(#drillLinkFadeHora)" />
        <path class="drill-link-head" d="M7.5 48 L12 55 L16.5 48 Z" />
      </svg>
      <span class="drill-link-chip">
        <i class="pi pi-clock" />
        {{ selectedHourlyHour === 'all' ? 'Dia todo' : `${String(selectedHourlyHour).padStart(2, '0')}h` }}
      </span>
    </div>

    <!-- NÍVEL 3: Raio-X (unificado: CRM Múltiplos ou CRM Único) -->
    <div v-if="selectedHourlyHour !== null" class="drill-panel level-raiox animate-fade-in">
      <div class="drill-panel-header">
        <div class="drill-panel-title">
          <span class="drill-step" aria-hidden="true">3</span>
          <span>RAIO-X: TRANSAÇÕES</span>
          <i
            class="pi pi-info-circle control-info-icon"
            role="img"
            tabindex="0"
            aria-label="Informações sobre o Raio-X de transações"
            v-tooltip.right="cronologiaInfoTooltips.raioxTransacoes"
          />
          <span class="drill-context-tag">
            {{ selectedHourlyHour === 'all' ? 'Dia Todo' : `${String(selectedHourlyHour).padStart(2, '0')}h` }}
          </span>
          <span v-if="!activeTransactionsLoading && activeGroupedRaiox.length > 0" class="raiox-count-badge">
            {{ activeGroupedRaiox.length }} Autorização{{ activeGroupedRaiox.length !== 1 ? 'es' : '' }}
          </span>
          <i v-if="activeTransactionsLoading" class="pi pi-spinner pi-spin raiox-spinner" />
        </div>
      </div>

      <!-- Alertas de Autorizações em Sequência (Único CRM + Múltiplos CRMs) -->
      <section v-if="alertasSequencia.length > 0" class="alertas-sequencia" aria-labelledby="alertas-sequencia-titulo">
        <header class="alertas-sequencia-header">
          <h3 id="alertas-sequencia-titulo">
            {{ alertasSequenciaTitulo }}
            <span class="alertas-sequencia-count">{{ alertasSequencia.length }}</span>
          </h3>
          <i
            class="pi pi-info-circle section-info-icon"
            role="img"
            aria-label="Informações sobre os alertas de autorizações em sequência"
            tabindex="0"
            v-tooltip.top="cronologiaInfoTooltips.alertasSection"
          />
        </header>
        <table class="alertas-sequencia-table">
          <thead>
            <tr>
              <th scope="col">Tipo</th>
              <th scope="col">Janela</th>
              <th scope="col">Médico(s)</th>
              <th scope="col">Ritmo</th>
              <th scope="col">Gravidade</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="alerta in alertasSequencia"
              :key="alerta.key"
              :class="['alerta-seq-row', `is-${alerta.tipo}`, { 'is-hovered': hoveredAlert?.key === alerta.key }]"
              @pointerenter="alerta.hover()"
              @pointerleave="clearHoveredAlert"
            >
              <td>
                <span class="alerta-seq-tipo">
                  <span
                    class="alerta-seq-codigo"
                    tabindex="0"
                    v-tooltip.right="{ value: alerta.tooltip, escape: false, class: 'crm-alert-tooltip', showDelay: 120, hideDelay: 80 }"
                    @focus="alerta.hover()"
                    @blur="clearHoveredAlert"
                  >{{ alerta.codigo }}</span>
                  <span class="alerta-seq-dot" aria-hidden="true" />
                  {{ alerta.tipoLabel }}
                </span>
              </td>
              <td class="alerta-seq-num">{{ alerta.inicio }} – {{ alerta.fim }}</td>
              <td>
                <span class="alerta-seq-medico" :style="alerta.medicoColor ? { color: alerta.medicoColor } : null">{{ alerta.medico }}</span>
              </td>
              <td class="alerta-seq-num">
                {{ alerta.qtd }} autorizaç{{ Number(alerta.qtd) === 1 ? 'ão' : 'ões' }} em {{ alerta.minutos }} min
              </td>
              <td>
                <span :class="['alerta-seq-severidade', alerta.severidade.className]">{{ alerta.severidade.label }}</span>
              </td>
            </tr>
          </tbody>
        </table>
      </section>

      <div v-if="!activeTransactionsLoading && activeTransactions.length === 0" class="raiox-empty">
        <i class="pi pi-inbox raiox-empty-icon" />
        <span>Nenhuma transação encontrada para este período.</span>
      </div>

      <div v-else class="raiox-table-wrapper" :class="{ 'is-loading': activeTransactionsLoading }">
        <table class="premium-table row-hover raiox-table flat-mode">
          <thead class="sticky-thead">
            <tr>
              <th width="5%" class="col-center">
                <span class="sr-only">Evidência</span>
                <i
                  class="pi pi-info-circle control-info-icon"
                  role="img"
                  tabindex="0"
                  aria-label="Informações sobre a marcação de evidências"
                  v-tooltip.right="cronologiaInfoTooltips.raioxEvidencia"
                />
              </th>
              <th width="10%" class="col-center">Horário</th>
              <th width="10%" class="col-center">
                Intervalo
                <i
                  class="pi pi-info-circle control-info-icon"
                  role="img"
                  tabindex="0"
                  aria-label="Informações sobre o intervalo entre autorizações"
                  v-tooltip.top="cronologiaInfoTooltips.raioxIntervalo"
                />
              </th>
              <th width="16%">Nº Autorização</th>
              <th width="16%">CRM</th>
              <th width="25%">Médico</th>
              <th width="18%" class="col-right">Valor Total</th>
            </tr>
          </thead>
          <tbody>
            <template v-for="tx in activeGroupedRaiox" :key="tx.num_autorizacao">
              <tr :class="getRaioxRowClasses(tx)" :data-autorizacao="tx.num_autorizacao">
                <td class="col-center align-top raiox-evid-cell">
                  <EvidenciaFlag
                    variant="icon"
                    :alvo="alvoDaTx(tx)"
                    :snapshot="snapshotDaTx(tx)"
                    :descricao="`Autorização nº ${tx.num_autorizacao}, ${formatarData(selectedDay.dt_janela)} às ${horarioDaTx(tx)}`"
                    :razao-social="razaoSocial"
                  />
                </td>
                <td class="col-center raiox-time align-top">
                  {{ (tx.data_hora.split(' ')[1] || tx.data_hora).split('.')[0] }}
                </td>
                <td class="col-center align-top">
                  <span
                    v-if="raioxIntervalos.get(tx.num_autorizacao)"
                    class="raiox-intervalo"
                    :class="{ 'is-curto': raioxIntervalos.get(tx.num_autorizacao).curto }"
                  >{{ raioxIntervalos.get(tx.num_autorizacao).texto }}</span>
                  <span v-else class="raiox-intervalo is-vazio">—</span>
                </td>
                <td class="raiox-auth align-top">{{ tx.num_autorizacao }}</td>
                <td class="align-top">
                  <div class="crm-badge-container">
                    <span
                      class="raiox-crm-id"
                      :class="{ 'is-grupo': getCRMColor(tx.id_medico) }"
                      :style="getCRMColor(tx.id_medico) ? { color: getCRMColor(tx.id_medico) } : null"
                    >{{ tx.id_medico }}</span>
                    <span
                      v-if="activeCrmFrequencies[tx.id_medico] > 1 && primeiraAutorizacaoPorCrm.has(tx.num_autorizacao)"
                      class="crm-recurrence-count"
                    >{{ activeCrmFrequencies[tx.id_medico] }}×</span>
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
                  <span class="raiox-doctor-name">{{ truncate(tx.no_medico ? formatTitleCase(tx.no_medico) : 'Médico não identificado', 48) }}</span>
                </td>
                <td class="col-right raiox-val-cell align-top">
                  {{ formatCurrencyFull(tx.vl_autorizacao) }}
                </td>
              </tr>
            </template>
          </tbody>
          <tfoot v-if="activeGroupedRaiox.length > 0">
            <tr class="raiox-footer-row">
              <td colspan="6" class="col-right footer-label">VALOR TOTAL DO PERÍODO SELECIONADO:</td>
              <td class="col-right footer-value">{{ formatCurrencyFull(activeRaioxTotalValue) }}</td>
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
.drill-navigation-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto minmax(0, 1fr);
  align-items: center;
  gap: 1rem;
  margin-bottom: 1.5rem;
}
.drill-breadcrumb {
  grid-column: 2;
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 0.5rem 1.25rem;
  background: var(--surface-card);
  border: 1px solid var(--card-border);
  border-radius: 99px;
  margin-bottom: 0;
  width: fit-content;
  align-self: center;
  box-shadow: 0 4px 12px rgba(0,0,0,0.1);
  backdrop-filter: blur(8px);
}
.crm-export-wrapper {
  grid-column: 3;
  justify-self: end;
  display: inline-flex;
  align-items: center;
  gap: 0.45rem;
}
.crm-export-info { font-size: 0.75rem; }
.crm-export-caret { font-size: 0.6rem; opacity: 0.7; }
.crm-export-button {
  display: inline-flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.55rem 0.8rem;
  border: 1px solid var(--card-border);
  border-radius: 8px;
  background: var(--surface-card);
  color: var(--text-color);
  font: inherit;
  font-size: 0.78rem;
  cursor: pointer;
}
.crm-export-button:hover:not(:disabled),
.crm-export-button:focus-visible {
  border-color: var(--primary-color);
  color: var(--primary-color);
}
.crm-export-button:focus-visible {
  outline: 2px solid var(--primary-color);
  outline-offset: 2px;
}
.crm-export-button:disabled {
  opacity: 0.5;
  cursor: not-allowed;
  pointer-events: none;
}
@media (max-width: 900px) {
  .drill-navigation-row {
    grid-template-columns: minmax(0, 1fr);
    justify-items: center;
    gap: 0.75rem;
  }
  .drill-breadcrumb,
  .crm-export-wrapper {
    grid-column: 1;
  }
  .drill-breadcrumb {
    max-width: 100%;
    flex-wrap: wrap;
    justify-content: center;
  }
  .crm-export-wrapper {
    justify-self: center;
  }
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

/* Os três níveis usam a mesma superfície neutra; a ordem do fluxo vem do número de etapa no título. */
.level-raiox { min-height: 650px !important; }

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
  font-weight: 600;
  letter-spacing: 0.05em;
  text-transform: uppercase;
  color: var(--text-color-85);
}
.drill-panel-title i { font-size: 1.1rem; }
.drill-step {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 22px;
  flex-shrink: 0;
  border-radius: 50%;
  border: 1px solid var(--card-border);
  background: color-mix(in srgb, var(--text-color-85) 6%, transparent);
  color: var(--text-secondary);
  font-size: 0.72rem;
  font-weight: 600;
  letter-spacing: 0;
}

.drill-context-tag {
  font-size: 0.75rem;
  font-weight: 500;
  background: color-mix(in srgb, var(--text-color-85) 6%, transparent);
  color: var(--text-color-85);
  padding: 2px 10px;
  border-radius: 6px;
  border: 1px solid var(--card-border);
  margin-left: 0.5rem;
  text-transform: none;
  letter-spacing: 0;
}

/* ── Ligação entre etapas (seta SVG + contexto) ─────────────────────────── */
.drill-link {
  position: relative;
  display: flex;
  justify-content: center;
  height: 60px;
  color: var(--text-muted);
}
.drill-link-svg {
  display: block;
  overflow: visible;
}
.drill-link-line {
  fill: none;
  stroke-width: 1.5;
  stroke-linecap: round;
  stroke-dasharray: 50;
  stroke-dashoffset: 50;
  animation: drill-link-draw 0.45s ease-out forwards;
}
.drill-link-head {
  fill: currentColor;
  stroke: currentColor;
  stroke-width: 1.5;
  stroke-linejoin: round;
  opacity: 0;
  transform-origin: 12px 51px;
  transform: scale(0.6);
  animation: drill-link-pop 0.25s ease-out 0.4s forwards;
}
/* Chip com a seleção, sobre a linha (o fundo "recorta" o traço). */
.drill-link-chip {
  position: absolute;
  top: 40%;
  left: 50%;
  transform: translate(-50%, -50%);
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
  padding: 2px 10px;
  border: 1px solid var(--card-border);
  border-radius: 999px;
  background: var(--card-bg);
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.12);
  color: var(--text-secondary);
  font-size: 0.68rem;
  font-weight: 500;
  white-space: nowrap;
  opacity: 0;
  animation: drill-link-fade 0.3s ease-out 0.25s forwards;
}
.drill-link-chip i { font-size: 0.64rem; color: var(--text-muted); }
@keyframes drill-link-draw { to { stroke-dashoffset: 0; } }
@keyframes drill-link-pop { to { opacity: 1; transform: scale(1); } }
@keyframes drill-link-fade { to { opacity: 1; } }
@media (prefers-reduced-motion: reduce) {
  .drill-link-line { animation: none; stroke-dashoffset: 0; }
  .drill-link-head { animation: none; opacity: 1; transform: none; }
  .drill-link-chip { animation: none; opacity: 1; }
}

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
/* Legenda centralizada; a marcação de evidência (dia ou hora selecionados) fica à direita, junto ao gráfico. */
.legend-bar-evid {
  display: grid;
  grid-template-columns: 1fr auto 1fr;
  align-items: center;
  gap: 1rem;
}
.legend-bar-evid .chart-legend-html { grid-column: 2; }
.legend-evid {
  grid-column: 3;
  justify-self: end;
  display: flex;
  align-items: center;
  gap: 0.6rem;
}
.legend-evid-contexto { font-size: 0.8rem; color: var(--text-secondary); white-space: nowrap; }
.legend-evid-contexto strong { font-weight: 600; color: var(--text-color-85); }
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

.filter-toggle { display: flex; align-items: center; gap: 0.5rem; cursor: pointer; font-size: 0.75rem; color: var(--text-secondary); }
.filter-toggle.is-disabled { opacity: 0.45; cursor: not-allowed; }
.filter-toggle.is-disabled .toggle-slider,
.filter-toggle.is-disabled .toggle-label { cursor: not-allowed; }

/* ── Botões de Navegação do Gráfico ── */


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

.nav-btn:hover:not(:disabled) {
  background: var(--primary-color) !important;
  color: white !important;
  transform: translateY(-1px);
}
.nav-btn:disabled {
  opacity: 0.35;
  cursor: not-allowed;
}
.daily-subtitle {
  padding-left: 1.75rem;
  margin: 0 0 0.75rem;
  max-width: 90ch;
}
.daily-subtitle strong { font-weight: 700; color: var(--text-color-85); }

.nav-btn:active {
  transform: translateY(0);
}


/* ── Barra de controles do Histórico Diário ── */
.daily-toolbar {
  display: flex;
  align-items: stretch;
  flex-wrap: wrap;
  margin: 0 0 1rem;
  background: rgba(0, 0, 0, 0.03);
  border: 1px solid var(--card-border);
  border-radius: 10px;
}
:global(.dark-mode) .daily-toolbar {
  background: rgba(255, 255, 255, 0.03);
  border-color: rgba(255, 255, 255, 0.08);
}
.daily-toolbar-group {
  display: flex;
  flex-direction: column;
  justify-content: center;
  gap: 0.4rem;
  padding: 0.65rem 1rem;
  border-left: 1px solid var(--card-border);
}
:global(.dark-mode) .daily-toolbar-group { border-left-color: rgba(255, 255, 255, 0.08); }
.daily-toolbar-group:first-child { border-left: 0; }
.daily-toolbar-nav-buttons { display: flex; align-items: center; gap: 4px; }
.daily-toolbar-label-info { display: inline-flex; align-items: center; gap: 0.35rem; }
.daily-toolbar-label-info .control-info-icon { font-size: 0.65rem; letter-spacing: 0; }
.daily-toolbar-rank { flex: 1 1 auto; }
.daily-toolbar-filter { min-width: 230px; }
.daily-toolbar-label {
  font-size: 0.65rem;
  font-weight: 700;
  letter-spacing: 0.09em;
  text-transform: uppercase;
  color: var(--text-secondary);
}
.daily-toolbar-row {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 0.6rem;
}
.daily-toolbar-help {
  font-size: 0.68rem;
  color: var(--text-muted);
  min-height: 1em;
}
.daily-toolbar .nav-btn { border: 1px solid var(--card-border); }
:global(.dark-mode) .daily-toolbar .nav-btn { border-color: rgba(255, 255, 255, 0.1) !important; }
.rank-segmented {
  display: inline-flex;
  flex-wrap: wrap;
  gap: 2px;
  padding: 3px;
  background: rgba(0, 0, 0, 0.05);
  border: 1px solid var(--card-border);
  border-radius: 9px;
}
:global(.dark-mode) .rank-segmented {
  background: rgba(0, 0, 0, 0.25);
  border-color: rgba(255, 255, 255, 0.1);
}
.rank-seg {
  --rank-color: var(--primary-color);
  display: inline-flex;
  align-items: center;
  gap: 0.45rem;
  min-height: 30px;
  padding: 0 0.75rem;
  border: 0;
  border-radius: 7px;
  background: transparent;
  color: var(--text-secondary);
  font: inherit;
  font-size: 0.72rem;
  font-weight: 600;
  cursor: pointer;
  transition: background 0.15s ease, color 0.15s ease, box-shadow 0.15s ease;
}
.rank-seg.is-unico { --rank-color: #f59e0b; }
.rank-seg.is-multiplo { --rank-color: #8b5cf6; }
.rank-seg.is-volume { --rank-color: #10b981; }
.rank-seg:hover {
  color: var(--text-color-85);
  background: color-mix(in srgb, var(--text-color-85) 6%, transparent);
}
.rank-seg:focus-visible {
  outline: 2px solid color-mix(in srgb, var(--primary-color) 70%, transparent);
  outline-offset: 2px;
}
.rank-seg-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--rank-color);
  flex-shrink: 0;
}
.rank-seg.is-active {
  background: color-mix(in srgb, var(--rank-color) 18%, transparent);
  box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--rank-color) 50%, transparent);
  color: var(--rank-color);
}
.rank-seg.is-none.is-active {
  background: color-mix(in srgb, var(--text-color-85) 14%, transparent);
  box-shadow: none;
  color: var(--text-color-85);
}
.rank-seg .control-info-icon { font-size: 0.65rem; color: inherit; }
.rank-seg:hover .control-info-icon { opacity: 1; }
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
.premium-table th { padding: 0.75rem 0.5rem; background: var(--card-bg); color: var(--text-secondary); font-size: 0.65rem; text-transform: uppercase; border-bottom: 2px solid var(--tabs-border); text-align: left; white-space: nowrap; }
/* O navegador centraliza <th> por padrão; os cabeçalhos seguem o alinhamento das células. */
.premium-table th.col-center { text-align: center; }
.premium-table th.col-right { text-align: right; }
.premium-table td { padding: 0.75rem 0.5rem; border-bottom: 1px solid var(--tabs-border); color: var(--text-color-85); font-size: 0.78rem; }
.premium-table tbody tr:hover { background: rgba(255,255,255,0.03); cursor: pointer; }
.premium-table tbody tr.raiox-details-expanded-row:hover { background: transparent !important; cursor: default; }

.raiox-count-badge { background: transparent; color: var(--text-secondary); border: 1px solid var(--card-border); border-radius: 99px; font-size: 0.65rem; font-weight: 500; padding: 1px 8px; margin-left: 0.25rem; }
.raiox-spinner { font-size: 0.8rem; margin-left: 0.5rem; }





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

.crm-badge-container { display: flex; align-items: center; gap: 0.45rem; }
.raiox-crm-id { font-size: 0.78rem; font-weight: 500; color: var(--text-color-85); }
.raiox-crm-id.is-grupo { font-weight: 600; }
.crm-recurrence-count { font-size: 0.7rem; color: var(--text-muted); }
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

/* Intervalo entre autorizações no Raio-X */
.raiox-intervalo {
  display: inline-block;
  padding: 0.05rem 0.45rem;
  border-radius: 999px;
  font-size: 0.74rem;
  color: var(--text-muted);
  border: 1px solid transparent;
}
.raiox-intervalo.is-curto {
  font-weight: 600;
  color: var(--risk-critical);
  background: color-mix(in srgb, var(--risk-critical) 12%, transparent);
  border-color: color-mix(in srgb, var(--risk-critical) 30%, transparent);
}
.raiox-intervalo.is-vazio { opacity: 0.5; }

/* Alertas de Autorizações em Sequência */
.alertas-sequencia {
  margin-bottom: 1.25rem;
  border: 1px solid var(--card-border);
  border-radius: 10px;
  background: rgba(0, 0, 0, 0.02);
  overflow-x: auto;
}
:global(.dark-mode) .alertas-sequencia {
  background: rgba(255, 255, 255, 0.02);
  border-color: rgba(255, 255, 255, 0.08);
}
.alertas-sequencia-header {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.65rem 1rem 0.4rem;
  color: var(--text-secondary);
}
.alertas-sequencia-header h3 {
  display: inline-flex;
  align-items: center;
  gap: 0.5rem;
  margin: 0;
  font-size: 0.72rem;
  font-weight: 700;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--text-color-85);
}
.alertas-sequencia-count {
  min-width: 1.35rem;
  padding: 0.05rem 0.4rem;
  border-radius: 99px;
  background: color-mix(in srgb, var(--text-color-85) 12%, transparent);
  font-size: 0.66rem;
  text-align: center;
  letter-spacing: 0;
}
.alertas-sequencia-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.76rem;
}
.alertas-sequencia-table th {
  padding: 0.35rem 1rem;
  text-align: left;
  font-size: 0.64rem;
  font-weight: 700;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--text-muted);
  border-bottom: 1px solid var(--card-border);
  white-space: nowrap;
}
.alertas-sequencia-table td {
  padding: 0.5rem 1rem;
  color: var(--text-color-85);
  border-bottom: 1px solid color-mix(in srgb, var(--card-border) 60%, transparent);
  white-space: nowrap;
}
.alerta-seq-row:last-child td { border-bottom: 0; }
.alerta-seq-row { --alerta-color: #f59e0b; transition: background 0.15s ease; }
.alerta-seq-row.is-multi { --alerta-color: #8b5cf6; }
.alerta-seq-row:hover,
.alerta-seq-row.is-hovered {
  background: color-mix(in srgb, var(--alerta-color) 9%, transparent);
}
.alerta-seq-tipo {
  display: inline-flex;
  align-items: center;
  gap: 0.5rem;
  font-weight: 600;
}
.alerta-seq-codigo {
  padding: 0.05rem 0.4rem;
  border-radius: 4px;
  border: 1px solid color-mix(in srgb, var(--alerta-color) 40%, transparent);
  background: color-mix(in srgb, var(--alerta-color) 14%, transparent);
  color: var(--alerta-color);
  font-size: 0.66rem;
  font-weight: 800;
  cursor: help;
}
.alerta-seq-codigo:focus-visible {
  outline: 2px solid color-mix(in srgb, var(--primary-color) 70%, transparent);
  outline-offset: 2px;
}
.alerta-seq-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--alerta-color);
  flex-shrink: 0;
}
.alerta-seq-num { font-variant-numeric: tabular-nums; }
.alerta-seq-medico { font-weight: 700; }
.alerta-seq-row.is-multi .alerta-seq-medico { color: var(--text-color-85); }
.alerta-seq-severidade {
  display: inline-block;
  padding: 0.1rem 0.5rem;
  border-radius: 99px;
  font-size: 0.68rem;
  font-weight: 700;
  color: var(--sev-color);
  background: color-mix(in srgb, var(--sev-color) 14%, transparent);
  border: 1px solid color-mix(in srgb, var(--sev-color) 35%, transparent);
}
.alerta-seq-severidade.is-extremo { --sev-color: #ef4444; }
.alerta-seq-severidade.is-critico { --sev-color: #f97316; }
.alerta-seq-severidade.is-grave { --sev-color: #f59e0b; }
.alerta-seq-severidade.is-alto { --sev-color: #eab308; }
.alerta-seq-severidade.is-alerta { --sev-color: #94a3b8; }

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
  flex-shrink: 0;
  color: var(--text-muted);
  font-size: 0.67rem;
  white-space: nowrap;
}
:global(.crm-info-tooltip-details strong) {
  color: var(--text-color-85);
  font-size: 0.7rem;
  font-weight: 600;
  text-align: right;
}
/* Valores longos: rótulo em cima e descrição embaixo, alinhada à esquerda. */
:global(.crm-info-tooltip-details > div.is-long) {
  flex-direction: column;
  align-items: flex-start;
  gap: 0.1rem;
}
:global(.crm-info-tooltip-details > div.is-long + div),
:global(.crm-info-tooltip-details > div + div.is-long) {
  padding-top: 0.35rem;
  border-top: 1px solid var(--tabs-border);
}
:global(.crm-info-tooltip-details > div.is-long span) {
  color: var(--text-color-85);
  font-weight: 600;
}
:global(.crm-info-tooltip-details > div.is-long strong) {
  color: var(--text-secondary);
  font-weight: 400;
  text-align: left;
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

/* Linha gatilho na tabela */
.row-gatilho td:first-child { border-left: 3px solid #f59e0b; }
.row-multi-alerta td:first-child { border-left: 3px solid #8b5cf6; }
.premium-table tbody tr { transition: opacity 0.15s ease; }
.premium-table tbody tr.row-alert-dimmed { opacity: 0.4; }

/* Cesta de evidências */
.raiox-evid-cell { padding-left: 0.25rem !important; padding-right: 0.25rem !important; }
.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  padding: 0;
  margin: -1px;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  white-space: nowrap;
  border: 0;
}
.premium-table tbody tr.row-evidencia-foco td {
  animation: evidenciaFoco 2.6s ease-out;
}
@keyframes evidenciaFoco {
  0%, 35% { background: color-mix(in srgb, var(--evidence-color) 22%, transparent); }
  100% { background: transparent; }
}
@media (prefers-reduced-motion: reduce) {
  .premium-table tbody tr.row-evidencia-foco td {
    animation: none;
    background: color-mix(in srgb, var(--evidence-color) 16%, transparent);
  }
}

.alerta-participacao-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 2.1rem;
  border-radius: 4px;
  padding: 1px 5px;
  font-size: 0.62rem;
  font-weight: 600;
  line-height: 1.1;
  white-space: nowrap;
}
.alerta-participacao-badge.is-unico {
  color: #f59e0b;
  background: transparent;
  border: 1px solid rgba(245,158,11,0.45);
}
.alerta-participacao-badge.is-multi {
  color: #a78bfa;
  background: transparent;
  border: 1px solid rgba(139, 92, 246, 0.45);
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
