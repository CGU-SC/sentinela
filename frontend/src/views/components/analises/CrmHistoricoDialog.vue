<script setup>
/**
 * Histórico completo de um CRM (clique numa linha do ranking de /analises).
 *
 * Indicadores, pontos de atenção, tabela de farmácias e mapa de calor usam o
 * período filtrado; a linha do tempo mostra todo o histórico, com o período
 * sombreado. Dados: GET /analytics/crm-medico-historico.
 */
import { computed, onBeforeUnmount, ref, watch } from 'vue';
import { useRouter } from 'vue-router';
import axios from 'axios';
import Dialog from 'primevue/dialog';
import Paginator from 'primevue/paginator';
import { use } from 'echarts/core';
import { CanvasRenderer } from 'echarts/renderers';
import { BarChart, HeatmapChart, LineChart, ScatterChart } from 'echarts/charts';
import {
  DataZoomComponent,
  GridComponent,
  MarkAreaComponent,
  MarkLineComponent,
  TooltipComponent,
  VisualMapComponent,
} from 'echarts/components';
import VChart from 'vue-echarts';
import { API_ENDPOINTS } from '@/config/api';
import { analysisTooltip } from '@/config/analysisTooltipConfig';
import { CRM_FARMACIA_SERIES, CRM_HEATMAP_TAXA_RAMP, DATA_NEUTRAL } from '@/config/colors';
import { useChartTheme } from '@/config/chartTheme';
import { useThemeStore } from '@/stores/theme';
import { useFormatting } from '@/composables/useFormatting';

use([
  CanvasRenderer, BarChart, LineChart, ScatterChart, HeatmapChart,
  GridComponent, TooltipComponent, DataZoomComponent, MarkAreaComponent,
  MarkLineComponent, VisualMapComponent,
]);

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  /** Linha do ranking: { id_medico, no_medico, nu_crm, sg_uf } */
  medico: { type: Object, default: null },
  dataInicio: { type: String, default: null },
  dataFim: { type: String, default: null },
});
const emit = defineEmits(['update:modelValue']);

const router = useRouter();
const themeStore = useThemeStore();
const { chartTheme } = useChartTheme();
const { formatNumberFull, formatarData, formatTitleCase, formatCnpj } = useFormatting();

const TOP_FARMACIAS_GRAFICO = 5;
const TOP_FARMACIAS_CALOR = 15;

const dados = ref(null);
const carregando = ref(false);
const erro = ref(null);
let controller = null;

const tema = computed(() => (themeStore.isDark ? 'dark' : 'light'));
const cores = computed(() => CRM_FARMACIA_SERIES[tema.value]);
const corOutras = computed(() => CRM_FARMACIA_SERIES.outras[tema.value]);
const corTaxa = computed(() => DATA_NEUTRAL[tema.value].line);

const infoTooltip = analysisTooltip('crmHistorico');
const atencaoTooltip = analysisTooltip('crmHistoricoAtencao');

async function carregar() {
  if (!props.medico?.id_medico) return;
  controller?.abort();
  controller = new AbortController();
  carregando.value = true;
  erro.value = null;
  dados.value = null;
  try {
    const params = { id_medico: props.medico.id_medico };
    if (props.dataInicio) params.data_inicio = props.dataInicio;
    if (props.dataFim) params.data_fim = props.dataFim;
    const { data } = await axios.get(API_ENDPOINTS.analyticsCrmMedicoHistorico, {
      params,
      signal: controller.signal,
    });
    dados.value = data;
  } catch (err) {
    if (axios.isCancel(err)) return;
    const status = err?.response?.status;
    erro.value = status === 404
      ? 'Este CRM não tem prescrições registradas.'
      : status === 503
        ? (err?.response?.data?.detail || 'Os dados de prescrições por médico não estão disponíveis. Sincronize os módulos CRM.')
        : 'Não foi possível carregar o histórico deste CRM.';
  } finally {
    carregando.value = false;
  }
}

watch(
  () => [props.modelValue, props.medico?.id_medico, props.dataInicio, props.dataFim],
  ([aberto]) => { if (aberto) carregar(); },
  { immediate: true },
);
onBeforeUnmount(() => controller?.abort());

function fechar() {
  emit('update:modelValue', false);
}

// ── Formatação ────────────────────────────────────────────────────────────────
function formatComp(comp) {
  if (!comp) return '—';
  return `${String(comp % 100).padStart(2, '0')}/${Math.floor(comp / 100)}`;
}
function formatDecimal(valor, casas = 2) {
  if (valor == null) return '—';
  return Number(valor).toLocaleString('pt-BR', { minimumFractionDigits: casas, maximumFractionDigits: casas });
}
function formatPct(valor) {
  return valor == null ? '—' : `${formatDecimal(valor, 1)}%`;
}
function indiceMes(comp) {
  return Math.floor(comp / 100) * 12 + (comp % 100) - 1;
}
function compDoIndice(idx) {
  return Math.floor(idx / 12) * 100 + (idx % 12) + 1;
}
function mesesEntre(inicio, fim) {
  const lista = [];
  for (let i = indiceMes(inicio); i <= indiceMes(fim); i += 1) lista.push(compDoIndice(i));
  return lista;
}
function compDaData(iso) {
  if (!iso) return null;
  const [ano, mes] = iso.split('-').map(Number);
  return ano * 100 + mes;
}

// ── Cabeçalho ─────────────────────────────────────────────────────────────────
const titulo = computed(() => {
  const nome = dados.value?.no_medico ?? props.medico?.no_medico;
  return nome ? formatTitleCase(nome) : 'Médico não localizado no cadastro do CFM';
});
const registro = computed(() => {
  const d = dados.value ?? props.medico;
  if (!d) return '';
  return d.nu_crm ? `CRM ${d.nu_crm}/${d.sg_uf ?? ''}` : `CRM ${d.id_medico}`;
});
const periodoTexto = computed(() => (
  dados.value ? `${formatarData(dados.value.periodo_inicio)} a ${formatarData(dados.value.periodo_fim)}` : ''
));

// ── Indicadores ───────────────────────────────────────────────────────────────
const kpis = computed(() => {
  const k = dados.value?.kpis;
  if (!k) return [];
  return [
    { label: 'Prescrições', value: formatNumberFull(k.nu_prescricoes) },
    { label: 'Dias com prescrição', value: formatNumberFull(k.qtd_dias_com_prescricao) },
    { label: 'Taxa diária', value: formatDecimal(k.taxa_prescricoes_dia) },
    { label: 'Meses ativos', value: formatNumberFull(k.qtd_meses_ativos) },
    {
      label: 'Meses com taxa elevada',
      value: `${formatNumberFull(k.qtd_meses_alta_intensidade)} (${formatPct(k.percentual_meses_alta_intensidade)})`,
    },
    { label: 'Farmácias', value: formatNumberFull(k.qtd_farmacias) },
    { label: 'Municípios / UFs', value: `${formatNumberFull(k.qtd_municipios)} / ${formatNumberFull(k.qtd_ufs)}` },
    { label: 'Farmácia principal', value: formatPct(k.percentual_farmacia_principal) },
    { label: '3 principais farmácias', value: formatPct(k.percentual_top3_farmacias) },
    {
      // Pior mes = maior taxa diaria do periodo (P95 do mes como referencia).
      label: 'Pior mês (taxa diária)',
      value: k.pior_mes_competencia
        ? `${formatDecimal(k.pior_mes_taxa_prescricoes_dia)}/dia em ${formatComp(k.pior_mes_competencia)}`
        : '—',
      detail: k.pior_mes_competencia
        ? `${formatNumberFull(k.pior_mes_prescricoes)} prescrições · P95 do mês ${formatDecimal(k.pior_mes_p95_taxa_dia)}`
        : null,
    },
  ];
});

// ── Farmácias (cor segue a farmácia: as 5 maiores do período) ────────────────
const farmacias = computed(() => dados.value?.farmacias ?? []);
const corPorFarmacia = computed(() => {
  const mapa = new Map();
  farmacias.value.slice(0, TOP_FARMACIAS_GRAFICO).forEach((f, i) => mapa.set(f.id_cnpj, cores.value[i]));
  return mapa;
});
function nomeFarmacia(f) {
  return f?.razao_social ? formatTitleCase(f.razao_social) : formatCnpj(f?.cnpj ?? '');
}
const legenda = computed(() => {
  const itens = farmacias.value.slice(0, TOP_FARMACIAS_GRAFICO).map((f) => ({
    nome: nomeFarmacia(f),
    cor: corPorFarmacia.value.get(f.id_cnpj),
  }));
  if (farmacias.value.length > TOP_FARMACIAS_GRAFICO || outrasForaDoPeriodo.value) {
    itens.push({ nome: 'Outras farmácias', cor: corOutras.value });
  }
  return itens;
});
const outrasForaDoPeriodo = computed(() => (
  (dados.value?.farmacia_mes ?? []).some((r) => !corPorFarmacia.value.has(r.id_cnpj))
));

// Tabela paginada (sem rolagem interna, para nao disputar a rolagem do modal).
const FARMACIAS_POR_PAGINA = 10;
const farmaciasInicio = ref(0);
const farmaciasPagina = computed(() => (
  farmacias.value.slice(farmaciasInicio.value, farmaciasInicio.value + FARMACIAS_POR_PAGINA)
));
watch(dados, () => { farmaciasInicio.value = 0; });

function abrirFarmacia(f) {
  if (!f?.cnpj) return;
  fechar();
  router.push(`/estabelecimentos/${f.cnpj}`);
}

// ── Linha do tempo (dois painéis, mesmo eixo de meses) ───────────────────────
const linhaDoTempo = computed(() => {
  const d = dados.value;
  if (!d?.meses?.length) return null;
  const meses = mesesEntre(d.meses[0].competencia, d.meses[d.meses.length - 1].competencia);
  const porMes = new Map(d.meses.map((m) => [m.competencia, m]));
  const topIds = farmacias.value.slice(0, TOP_FARMACIAS_GRAFICO).map((f) => f.id_cnpj);
  const series = new Map(topIds.map((id) => [id, new Map()]));
  const outras = new Map();
  for (const r of d.farmacia_mes) {
    const alvo = series.get(r.id_cnpj) ?? outras;
    alvo.set(r.competencia, (alvo.get(r.competencia) ?? 0) + r.nu_prescricoes);
  }
  return { meses, porMes, topIds, series, outras };
});

const chartOption = computed(() => {
  const lt = linhaDoTempo.value;
  if (!lt) return {};
  const c = chartTheme.value;
  const d = dados.value;
  const rotulos = lt.meses.map(formatComp);
  const superficie = themeStore.isDark ? '#1e1e1e' : '#ffffff';
  // Faixa do período, limitada ao trecho do eixo (meses com dados do médico).
  const primeiro = lt.meses[0];
  const ultimo = lt.meses[lt.meses.length - 1];
  const pIni = Math.max(compDaData(d.periodo_inicio), primeiro);
  const pFim = Math.min(compDaData(d.periodo_fim), ultimo);
  const periodoVisivel = pIni <= pFim;
  const periodoIni = formatComp(pIni);
  const periodoFim = formatComp(pFim);
  const compInscricao = compDaData(d.dt_primeira_inscricao);
  const inscricaoNoEixo = compInscricao && lt.meses.includes(compInscricao) ? formatComp(compInscricao) : null;

  const barra = (nome, cor, valores, extra = {}) => ({
    name: nome,
    type: 'bar',
    stack: 'farmacias',
    xAxisIndex: 0,
    yAxisIndex: 0,
    barMaxWidth: 14,
    itemStyle: { color: cor, borderColor: superficie, borderWidth: 1 },
    emphasis: { focus: 'series' },
    data: lt.meses.map((m) => valores.get(m) ?? null),
    ...extra,
  });

  const barras = lt.topIds.map((id) => {
    const f = farmacias.value.find((x) => x.id_cnpj === id);
    return barra(nomeFarmacia(f), corPorFarmacia.value.get(id), lt.series.get(id));
  });
  barras.push(barra('Outras farmácias', corOutras.value, lt.outras));
  // Período filtrado sombreado e 1ª inscrição no CFM (na primeira série).
  barras[0].markArea = {
    silent: true,
    itemStyle: { color: themeStore.isDark ? 'rgba(255,255,255,0.05)' : 'rgba(0,0,0,0.045)' },
    data: periodoVisivel ? [[{ xAxis: periodoIni }, { xAxis: periodoFim }]] : [],
  };
  if (inscricaoNoEixo) {
    barras[0].markLine = {
      silent: true,
      symbol: 'none',
      lineStyle: { color: c.muted, type: 'dashed', width: 1.5 },
      label: { formatter: '1ª inscrição CFM', color: c.muted, fontSize: 10, position: 'insideEndTop' },
      data: [{ xAxis: inscricaoNoEixo }],
    };
  }

  const taxa = lt.meses.map((m) => {
    const mes = lt.porMes.get(m);
    return mes ? Number(mes.taxa_prescricoes_dia.toFixed(2)) : null;
  });
  const p95 = lt.meses.map((m) => {
    const mes = lt.porMes.get(m);
    return mes ? Number(mes.p95_taxa_dia.toFixed(2)) : null;
  });
  const alta = lt.meses.map((m, i) => (lt.porMes.get(m)?.alta_intensidade ? [i, taxa[i]] : null)).filter(Boolean);
  const corAlerta = themeStore.isDark ? '#e66767' : '#d03b3b';

  return {
    backgroundColor: 'transparent',
    animationDuration: 300,
    axisPointer: { link: [{ xAxisIndex: 'all' }] },
    tooltip: {
      trigger: 'axis',
      confine: true,
      backgroundColor: c.tooltip,
      borderColor: c.tooltipBorder,
      textStyle: { color: c.tooltipText, fontSize: 12 },
      formatter: (params) => {
        const idx = params[0]?.dataIndex;
        const comp = lt.meses[idx];
        const mes = lt.porMes.get(comp);
        if (!mes) return `<strong>${formatComp(comp)}</strong><div style="opacity:.7;margin-top:6px">Sem prescrições</div>`;
        const linha = (r, v) => `<div style="display:flex;justify-content:space-between;gap:18px;margin:3px 0"><span style="opacity:.72">${r}</span><span>${v}</span></div>`;
        const farm = params
          .filter((p) => p.seriesType === 'bar' && p.value)
          .map((p) => linha(`${p.marker}${p.seriesName}`, formatNumberFull(p.value)))
          .join('');
        return `<div style="min-width:240px">
          <div style="font-weight:600;margin-bottom:6px">${formatComp(comp)}${mes.alta_intensidade ? ' · <span style="color:' + corAlerta + '">taxa elevada</span>' : ''}</div>
          <div style="display:flex;justify-content:space-between;align-items:baseline;gap:18px;margin:2px 0 8px;padding:6px 8px;border-radius:6px;background:${mes.alta_intensidade ? corAlerta + '22' : c.axisShadow}">
            <span style="font-weight:600">Taxa diária</span>
            <span><strong style="font-size:16px;font-weight:600;color:${mes.alta_intensidade ? corAlerta : c.tooltipText}">${formatDecimal(mes.taxa_prescricoes_dia)}</strong><span style="opacity:.72"> /dia · ${formatDecimal(mes.taxa_prescricoes_dia / mes.p95_taxa_dia, 1)}× o P95</span></span>
          </div>
          ${linha('Prescrições', formatNumberFull(mes.nu_prescricoes))}
          ${linha('Dias com prescrição', formatNumberFull(mes.qtd_dias_com_prescricao))}
          ${linha('P95 nacional do mês', formatDecimal(mes.p95_taxa_dia))}
          ${linha('Farmácias / UFs', `${mes.qtd_farmacias} / ${mes.qtd_ufs}`)}
          <div style="border-top:1px solid ${c.tooltipBorder};margin-top:6px;padding-top:4px">${farm}</div>
        </div>`;
      },
    },
    grid: [
      // Dois paineis da mesma altura: prescricoes (em cima) e taxa diaria.
      { left: 56, right: 18, top: 18, height: '39%' },
      { left: 56, right: 18, top: '51%', height: '39%' },
    ],
    xAxis: [0, 1].map((gi) => ({
      type: 'category',
      gridIndex: gi,
      data: rotulos,
      boundaryGap: true,
      axisLine: { lineStyle: { color: c.border } },
      axisTick: { show: false },
      axisLabel: { show: gi === 1, color: c.muted, fontSize: 10 },
    })),
    yAxis: [
      {
        gridIndex: 0,
        name: 'Prescrições',
        nameTextStyle: { color: c.muted, fontSize: 10, align: 'left' },
        axisLabel: { color: c.muted, fontSize: 10 },
        splitLine: { lineStyle: { color: c.grid } },
      },
      {
        gridIndex: 1,
        name: 'Taxa diária',
        nameTextStyle: { color: c.muted, fontSize: 10, align: 'left' },
        axisLabel: { color: c.muted, fontSize: 10 },
        splitLine: { lineStyle: { color: c.grid } },
      },
    ],
    dataZoom: [
      // Roda do mouse rola o modal (nao da zoom); zoom so pela barra de baixo.
      { type: 'inside', xAxisIndex: [0, 1], zoomOnMouseWheel: false, moveOnMouseWheel: false, moveOnMouseMove: false },
      {
        type: 'slider', xAxisIndex: [0, 1], bottom: 4, height: 16,
        borderColor: c.border, textStyle: { color: c.muted, fontSize: 10 },
      },
    ],
    series: [
      ...barras,
      {
        name: 'P95 nacional do mês',
        type: 'line',
        xAxisIndex: 1,
        yAxisIndex: 1,
        symbol: 'none',
        connectNulls: false,
        lineStyle: { color: c.muted, width: 1.5, type: 'dashed' },
        data: p95,
      },
      {
        name: 'Taxa diária',
        type: 'line',
        xAxisIndex: 1,
        yAxisIndex: 1,
        symbol: 'none',
        connectNulls: false,
        lineStyle: { color: corTaxa.value, width: 2 },
        data: taxa,
      },
      {
        name: 'Mês com taxa elevada',
        type: 'scatter',
        xAxisIndex: 1,
        yAxisIndex: 1,
        symbolSize: 8,
        itemStyle: { color: corAlerta, borderColor: superficie, borderWidth: 2 },
        data: alta,
      },
    ],
  };
});

// ── Mapa de calor farmácia x mês (período filtrado) ──────────────────────────
const calor = computed(() => {
  const d = dados.value;
  if (!d || !farmacias.value.length) return null;
  const meses = mesesEntre(compDaData(d.periodo_inicio), compDaData(d.periodo_fim))
    .filter((m) => m >= d.meses[0].competencia && m <= d.meses[d.meses.length - 1].competencia);
  if (!meses.length) return null;
  const linhas = farmacias.value.slice(0, TOP_FARMACIAS_CALOR);
  const idxMes = new Map(meses.map((m, i) => [m, i]));
  const idxFarm = new Map(linhas.map((f, i) => [f.id_cnpj, i]));
  // Celula = taxa diaria do medico nesta farmacia no mes (prescricoes / dias).
  const pontos = [];
  let minimo = Infinity;
  let maximo = 0;
  for (const r of d.farmacia_mes) {
    const x = idxMes.get(r.competencia);
    const y = idxFarm.get(r.id_cnpj);
    if (x == null || y == null || !r.qtd_dias_com_prescricao) continue;
    const taxa = r.nu_prescricoes / r.qtd_dias_com_prescricao;
    pontos.push([x, y, Number(taxa.toFixed(2)), r.nu_prescricoes, r.qtd_dias_com_prescricao]);
    minimo = Math.min(minimo, taxa);
    maximo = Math.max(maximo, taxa);
  }
  if (!pontos.length) return null;
  return { meses, linhas, pontos, minimo, maximo, omitidas: farmacias.value.length - linhas.length };
});

const calorAltura = computed(() => `${Math.max(160, (calor.value?.linhas.length ?? 0) * 24 + 70)}px`);

const calorOption = computed(() => {
  const h = calor.value;
  if (!h) return {};
  const c = chartTheme.value;
  const nomes = h.linhas.map((f) => {
    const nome = nomeFarmacia(f);
    return nome.length > 34 ? `${nome.slice(0, 33)}…` : nome;
  });
  return {
    backgroundColor: 'transparent',
    animation: false,
    tooltip: {
      confine: true,
      backgroundColor: c.tooltip,
      borderColor: c.tooltipBorder,
      textStyle: { color: c.tooltipText, fontSize: 12 },
      formatter: (p) => {
        const f = h.linhas[p.value[1]];
        return `<div style="font-weight:600">${nomeFarmacia(f)}</div>
          <div style="opacity:.72;margin:2px 0 6px">${f.municipio ? formatTitleCase(f.municipio) : ''}${f.uf ? '/' + f.uf : ''}</div>
          ${formatComp(h.meses[p.value[0]])}: ${formatNumberFull(p.value[3])} prescrições em ${formatNumberFull(p.value[4])}
          ${p.value[4] === 1 ? 'dia' : 'dias'} = <strong>${formatDecimal(p.value[2], 1)}/dia</strong>`;
      },
    },
    grid: { left: 230, right: 18, top: 8, bottom: 44 },
    xAxis: {
      type: 'category',
      data: h.meses.map(formatComp),
      axisLabel: { color: c.muted, fontSize: 10 },
      axisLine: { lineStyle: { color: c.border } },
      axisTick: { show: false },
      splitArea: { show: false },
    },
    yAxis: {
      type: 'category',
      data: nomes,
      inverse: true,
      axisLabel: { color: c.text, fontSize: 11 },
      axisLine: { show: false },
      axisTick: { show: false },
    },
    visualMap: {
      min: Math.floor(h.minimo * 10) / 10,
      max: Math.max(Math.ceil(h.maximo * 10) / 10, Math.floor(h.minimo * 10) / 10 + 0.1),
      dimension: 2,
      calculable: false,
      orient: 'horizontal',
      left: 230,
      bottom: 4,
      itemHeight: 140,
      itemWidth: 10,
      text: [`${formatDecimal(h.maximo, 1)}/dia`, `${formatDecimal(h.minimo, 1)}/dia`],
      textStyle: { color: c.muted, fontSize: 10 },
      inRange: { color: CRM_HEATMAP_TAXA_RAMP[tema.value] },
    },
    series: [{
      type: 'heatmap',
      data: h.pontos,
      itemStyle: { borderColor: themeStore.isDark ? '#1e1e1e' : '#ffffff', borderWidth: 2, borderRadius: 2 },
      emphasis: { itemStyle: { borderColor: c.text, borderWidth: 1 } },
    }],
  };
});

// ── Pontos de atenção ─────────────────────────────────────────────────────────
const ICONE_ATENCAO = {
  antes_inscricao: 'pi-calendar-times',
  multiplas_ufs: 'pi-map-marker',
  sequencia_alta: 'pi-chart-line',
  concentracao: 'pi-building',
};
</script>

<template>
  <Dialog
    :visible="modelValue"
    modal
    maximizable
    dismissableMask
    class="crm-historico-dialog"
    :style="{ width: '94vw', maxWidth: '1500px' }"
    @update:visible="emit('update:modelValue', $event)"
  >
    <template #header>
      <div class="hist-header">
        <span class="hist-eyebrow">
          Histórico do CRM
          <i class="pi pi-info-circle hist-info" v-tooltip.bottom="infoTooltip" aria-label="Como ler o histórico" />
        </span>
        <span class="hist-title">{{ titulo }}</span>
        <div class="hist-meta">
          <span>{{ registro }}</span>
          <span v-if="dados?.dt_primeira_inscricao">1ª inscrição no CFM: {{ formatarData(dados.dt_primeira_inscricao) }}</span>
          <span v-if="periodoTexto">Período: {{ periodoTexto }}</span>
          <span v-if="dados && !dados.localizado_cfm" class="hist-badge hist-badge--alerta">
            <i class="pi pi-exclamation-triangle" /> Não localizado no cadastro do CFM
          </span>
        </div>
      </div>
    </template>

    <div v-if="carregando" class="hist-estado">
      <i class="pi pi-spin pi-spinner" /> Carregando o histórico…
    </div>
    <div v-else-if="erro" class="hist-estado hist-estado--erro">
      <i class="pi pi-exclamation-circle" /> {{ erro }}
    </div>

    <div v-else-if="dados" class="hist-body">
      <!-- Indicadores do período -->
      <div class="hist-kpis">
        <div v-for="kpi in kpis" :key="kpi.label" class="hist-kpi">
          <span class="hist-kpi-label">{{ kpi.label }}</span>
          <span class="hist-kpi-value">{{ kpi.value }}</span>
          <span v-if="kpi.detail" class="hist-kpi-detail">{{ kpi.detail }}</span>
        </div>
      </div>

      <!-- Pontos de atenção -->
      <section class="hist-panel">
        <header class="hist-panel-header">
          <h3>Pontos de atenção</h3>
          <i class="pi pi-info-circle hist-info" v-tooltip.bottom="atencaoTooltip" aria-label="Como os pontos são calculados" />
        </header>
        <ul v-if="dados.pontos_atencao.length" class="hist-atencao">
          <li v-for="p in dados.pontos_atencao" :key="p.codigo">
            <i class="pi" :class="ICONE_ATENCAO[p.codigo]" aria-hidden="true" />
            <div>
              <strong>{{ p.titulo }}</strong>
              <span>{{ p.detalhe }}</span>
            </div>
          </li>
        </ul>
        <p v-else class="hist-vazio">Nenhum ponto de atenção no período.</p>
      </section>

      <!-- Linha do tempo -->
      <section class="hist-panel">
        <header class="hist-panel-header">
          <h3>Linha do tempo mensal</h3>
          <span class="hist-panel-sub">histórico completo · faixa sombreada = período filtrado</span>
        </header>
        <div class="hist-legenda">
          <span v-for="item in legenda" :key="item.nome" class="hist-legenda-item">
            <i class="hist-swatch" :style="{ backgroundColor: item.cor }" aria-hidden="true" />{{ item.nome }}
          </span>
          <span class="hist-legenda-item">
            <i class="hist-swatch hist-swatch--linha" :style="{ backgroundColor: corTaxa }" aria-hidden="true" />Taxa diária
          </span>
          <span class="hist-legenda-item">
            <i class="hist-swatch hist-swatch--tracejada" aria-hidden="true" />P95 nacional do mês
          </span>
          <span class="hist-legenda-item">
            <i class="hist-swatch hist-swatch--ponto" aria-hidden="true" />Mês com taxa elevada
          </span>
        </div>
        <VChart class="hist-chart" :option="chartOption" autoresize />
      </section>

      <!-- Farmácias -->
      <section class="hist-panel">
        <header class="hist-panel-header">
          <h3>Farmácias onde atuou</h3>
          <span class="hist-panel-sub">período filtrado · clique para abrir o estabelecimento</span>
        </header>
        <div class="hist-tabela-wrap">
          <table class="hist-tabela">
            <colgroup>
              <col class="c-nome"><col class="c-local"><col class="c-sit"><col class="c-ms">
              <col class="c-num"><col class="c-num"><col class="c-meses"><col class="c-comp"><col class="c-comp">
            </colgroup>
            <thead>
              <tr>
                <th>FARMÁCIA</th><th>MUNICÍPIO / UF</th><th>SITUAÇÃO RF</th><th>CONEXÃO MS</th>
                <th>PRESCRIÇÕES</th><th>% DO TOTAL</th><th>MESES</th><th>PRIMEIRO MÊS</th><th>ÚLTIMO MÊS</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="f in farmaciasPagina"
                :key="f.id_cnpj"
                tabindex="0"
                @click="abrirFarmacia(f)"
                @keydown.enter="abrirFarmacia(f)"
              >
                <td>
                  <span class="hist-farm">
                    <i
                      class="hist-swatch"
                      :style="{ backgroundColor: corPorFarmacia.get(f.id_cnpj) ?? corOutras }"
                      aria-hidden="true"
                    />
                    <span>
                      <span class="hist-farm-nome">{{ nomeFarmacia(f) }}</span>
                      <span class="hist-farm-cnpj">{{ formatCnpj(f.cnpj ?? '') }}</span>
                    </span>
                  </span>
                </td>
                <td>
                  {{ f.municipio ? formatTitleCase(f.municipio) : '—' }}{{ f.uf ? ` / ${f.uf}` : '' }}
                  <span v-if="f.fora_uf_crm" class="hist-badge">fora da UF do CRM</span>
                </td>
                <td>{{ f.situacao_rf ?? '—' }}</td>
                <td>{{ f.conexao_ativa == null ? '—' : f.conexao_ativa ? 'Ativa' : 'Inativa' }}</td>
                <td class="num">{{ formatNumberFull(f.nu_prescricoes) }}</td>
                <td class="num">{{ formatPct(f.percentual_prescricoes) }}</td>
                <td class="num">{{ formatNumberFull(f.qtd_meses) }}</td>
                <td class="num">{{ formatComp(f.primeira_competencia) }}</td>
                <td class="num">{{ formatComp(f.ultima_competencia) }}</td>
              </tr>
              <tr v-if="!farmacias.length"><td colspan="9" class="hist-vazio">Sem prescrições no período filtrado.</td></tr>
            </tbody>
          </table>
        </div>
        <Paginator
          v-if="farmacias.length > FARMACIAS_POR_PAGINA"
          :first="farmaciasInicio"
          :rows="FARMACIAS_POR_PAGINA"
          :total-records="farmacias.length"
          class="hist-paginator"
          @page="farmaciasInicio = $event.first"
        />
      </section>

      <!-- Mapa de calor -->
      <section v-if="calor" class="hist-panel">
        <header class="hist-panel-header">
          <h3>Taxa diária por farmácia e mês</h3>
          <span class="hist-panel-sub">
            prescrições ÷ dias com prescrição na farmácia · período filtrado ·
            {{ calor.linhas.length }} farmácias com mais prescrições{{ calor.omitidas ? ` (mais ${calor.omitidas} na tabela)` : '' }}
            · escala do próprio médico
          </span>
        </header>
        <VChart class="hist-calor" :style="{ height: calorAltura }" :option="calorOption" autoresize />
      </section>
    </div>

    <template #footer>
      <button type="button" class="hist-fechar" @click="fechar">Fechar</button>
    </template>
  </Dialog>
</template>

<style scoped>
.hist-header { display: flex; flex-direction: column; gap: .2rem; }
.hist-eyebrow { display: inline-flex; align-items: center; gap: .4rem; font-size: .66rem; font-weight: 600; letter-spacing: .08em; text-transform: uppercase; color: var(--text-muted); }
.hist-title { font-size: 1.05rem; font-weight: 600; color: var(--text-color); }
.hist-meta { display: flex; flex-wrap: wrap; align-items: center; gap: .35rem 1rem; font-size: .74rem; color: var(--text-secondary); }
.hist-info { font-size: .8rem; color: var(--text-muted); opacity: .7; cursor: default; }
.hist-info:hover { opacity: 1; }
.hist-badge { display: inline-flex; align-items: center; gap: .3rem; margin-left: .35rem; padding: .08rem .45rem; border: 1px solid var(--card-border); border-radius: 999px; font-size: .64rem; color: var(--text-secondary); white-space: nowrap; }
.hist-badge--alerta { margin-left: 0; border-color: color-mix(in srgb, var(--risk-critical) 45%, transparent); color: var(--risk-critical); }

.hist-estado { display: flex; align-items: center; justify-content: center; gap: .5rem; min-height: 260px; color: var(--text-muted); font-size: .82rem; }
.hist-estado--erro { color: var(--risk-critical); }

.hist-body { display: flex; flex-direction: column; gap: 1rem; }
.hist-kpis { display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); gap: .65rem; }
.hist-kpi { display: flex; flex-direction: column; gap: .3rem; padding: .65rem .85rem; border: 1px solid var(--card-border); border-radius: 10px; background: color-mix(in srgb, var(--text-color) 3%, transparent); }
.hist-kpi-label { font-size: .62rem; font-weight: 600; letter-spacing: .06em; text-transform: uppercase; color: var(--text-muted); }
.hist-kpi-value { font-size: .92rem; font-weight: 600; color: var(--text-color); }
.hist-kpi-detail { font-size: .66rem; color: var(--text-muted); }

.hist-panel { display: flex; flex-direction: column; gap: .6rem; padding: .85rem 1rem; border: 1px solid var(--card-border); border-radius: 10px; }
.hist-panel-header { display: flex; align-items: baseline; gap: .6rem; flex-wrap: wrap; }
.hist-panel-header h3 { margin: 0; font-size: .82rem; font-weight: 600; color: var(--text-color); }
.hist-panel-sub { font-size: .7rem; color: var(--text-muted); }
.hist-vazio { margin: 0; font-size: .76rem; color: var(--text-muted); }

.hist-atencao { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: .6rem; margin: 0; padding: 0; list-style: none; }
.hist-atencao li { display: flex; gap: .6rem; padding: .55rem .7rem; border-radius: 8px; background: color-mix(in srgb, var(--risk-critical) 7%, transparent); }
.hist-atencao li > i { margin-top: .12rem; color: var(--risk-critical); }
.hist-atencao strong { display: block; font-size: .76rem; font-weight: 600; color: var(--text-color); }
.hist-atencao span { font-size: .72rem; color: var(--text-secondary); }

.hist-legenda { display: flex; flex-wrap: wrap; gap: .35rem 1rem; font-size: .7rem; color: var(--text-secondary); }
.hist-legenda-item { display: inline-flex; align-items: center; gap: .35rem; }
.hist-swatch { display: inline-block; flex-shrink: 0; width: 10px; height: 10px; border-radius: 2px; }
.hist-swatch--linha { height: 2px; border-radius: 1px; }
.hist-swatch--tracejada { height: 0; border-top: 2px dashed var(--text-muted); border-radius: 0; }
.hist-swatch--ponto { width: 8px; height: 8px; border-radius: 50%; background: var(--risk-critical); }
.hist-chart { width: 100%; height: 540px; }
.hist-calor { width: 100%; }

.hist-tabela-wrap { overflow-x: auto; overflow-y: hidden; border: 1px solid var(--tabs-border); border-radius: 8px; }
.hist-paginator { padding: 0; background: transparent; font-size: .74rem; }
.hist-tabela { width: 100%; min-width: 60rem; table-layout: fixed; border-collapse: collapse; font-size: .74rem; color: var(--text-color-85); }
.hist-tabela .c-nome { width: auto; }
.hist-tabela .c-local { width: 12rem; }
.hist-tabela .c-sit { width: 6.5rem; }
.hist-tabela .c-ms { width: 6rem; }
.hist-tabela .c-num { width: 6.5rem; }
.hist-tabela .c-meses { width: 4.5rem; }
.hist-tabela .c-comp { width: 6rem; }
.hist-tabela th { padding: .55rem .7rem; background: var(--table-header-bg); color: var(--text-muted); font-size: .6rem; font-weight: 600; letter-spacing: .04em; text-align: left; white-space: normal; vertical-align: bottom; }
.hist-tabela th:nth-child(n+5) { text-align: right; }
.hist-tabela td { padding: .5rem .7rem; border-top: 1px solid var(--tabs-border); vertical-align: middle; overflow-wrap: anywhere; }
.hist-tabela td.num { text-align: right; }
.hist-tabela tbody tr { cursor: pointer; }
.hist-tabela tbody tr:hover, .hist-tabela tbody tr:focus-visible { background: color-mix(in srgb, var(--primary-color) 6%, var(--card-bg)); outline: none; }
.hist-farm { display: flex; align-items: flex-start; gap: .5rem; }
.hist-farm .hist-swatch { margin-top: .25rem; }
.hist-farm-nome, .hist-farm-cnpj { display: block; }
.hist-farm-nome { color: var(--text-color-85); font-weight: 600; }
.hist-farm-cnpj { margin-top: .12rem; color: var(--text-muted); font-size: .66rem; }

.hist-fechar { min-height: 34px; padding: 0 1.1rem; border: 1px solid var(--card-border); border-radius: 8px; background: transparent; color: var(--text-color); font: inherit; font-size: .8rem; font-weight: 500; cursor: pointer; }
.hist-fechar:hover { border-color: var(--primary-color); color: var(--primary-color); }

@media (max-width: 1100px) {
  .hist-kpis { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .hist-atencao { grid-template-columns: 1fr; }
}
</style>
