<script setup>
import { computed, ref, watch } from 'vue';
import Dialog from 'primevue/dialog';
import { use } from 'echarts/core';
import { CanvasRenderer } from 'echarts/renderers';
import { BarChart, LineChart } from 'echarts/charts';
import {
  GridComponent,
  LegendComponent,
  MarkLineComponent,
  TooltipComponent,
} from 'echarts/components';
import VChart from 'vue-echarts';
import { useCnpjDetailStore } from '@/stores/cnpjDetail';
import { useFilterParameters } from '@/composables/useFilterParameters';
import { useFormatting } from '@/composables/useFormatting';
import { useChartTheme } from '@/config/chartTheme';
import { useThemeStore } from '@/stores/theme';
import { DATA_NEUTRAL } from '@/config/colors';

use([CanvasRenderer, BarChart, LineChart, GridComponent, LegendComponent, TooltipComponent, MarkLineComponent]);

/**
 * Detalhe mensal da atuação de um CRM na farmácia: volume do CRM, participação
 * no movimento mensal da farmácia, volume do mesmo CRM no Brasil, meses com
 * alertas e data da 1ª inscrição no CFM.
 */
const props = defineProps({
  modelValue: { type: Boolean, default: false },
  medico: { type: Object, default: null },
  cnpj: { type: String, required: true },
  periodo: { type: Object, default: null },
  serieFarmacia: { type: Array, default: () => [] },
});
const emit = defineEmits(['update:modelValue']);

const cnpjDetailStore = useCnpjDetailStore();
const themeStore = useThemeStore();
const { getApiParams } = useFilterParameters();
const { formatCurrencyFull, formatNumberFull, formatTitleCase, formatarData } = useFormatting();
const { chartTheme } = useChartTheme();

const COR_BARRA_ALERTA = '#ef4444';
const COR_INSCRICAO = '#f59e0b';
const coresDados = computed(() => DATA_NEUTRAL[themeStore.isDark ? 'dark' : 'light']);

const metrica = ref('qtd');
const alertas = ref(null);
const alertasLoading = ref(false);
const alertasErro = ref(null);

function competenciaToIndex(comp) {
  return Math.floor(comp / 100) * 12 + (comp % 100) - 1;
}
function indexToCompetencia(idx) {
  return Math.floor(idx / 12) * 100 + (idx % 12) + 1;
}
function formatCompetencia(comp) {
  return `${String(comp % 100).padStart(2, '0')}/${Math.floor(comp / 100)}`;
}
function competenciaDeData(value) {
  const text = String(value ?? '');
  const match = text.match(/^(\d{4})-(\d{2})/) || text.match(/^\d{2}\/(\d{2})\/(\d{4})/);
  if (!match) return null;
  return text.includes('/') ? Number(match[2]) * 100 + Number(match[1]) : Number(match[1]) * 100 + Number(match[2]);
}

function temAlertasDetalhados(m) {
  return Number(m?.qtd_alertas_crm_unico || 0) > 0
    || Number(m?.qtd_alertas_geograficos || 0) > 0
    || Number(m?.qtd_alertas_crm_multiplos || 0) > 0;
}

watch(
  () => [props.modelValue, props.medico?.id_medico],
  async ([visible]) => {
    alertas.value = null;
    alertasErro.value = null;
    if (!visible || !props.medico || !temAlertasDetalhados(props.medico)) return;
    const { inicio, fim } = getApiParams();
    alertasLoading.value = true;
    try {
      alertas.value = await cnpjDetailStore.fetchCrmMedicoAlertas(props.cnpj, props.medico.id_medico, inicio, fim);
      if (!alertas.value) throw new Error('Alertas do CRM indisponíveis.');
    } catch (error) {
      alertasErro.value = error?.message || 'Não foi possível carregar os alertas do CRM.';
    } finally {
      alertasLoading.value = false;
    }
  },
  { immediate: true },
);

const meses = computed(() => {
  if (!props.periodo || !props.medico) return [];
  const inicio = competenciaToIndex(props.periodo.inicio);
  const fim = competenciaToIndex(props.periodo.fim);
  const serieCrm = new Map(props.medico.serie_mensal_atuacao.map(p => [Number(p.competencia), p]));
  const serieFarm = new Map(props.serieFarmacia.map(p => [Number(p.competencia), p]));
  const lista = [];
  for (let idx = inicio; idx <= fim; idx += 1) {
    const comp = indexToCompetencia(idx);
    const crm = serieCrm.get(comp);
    const farm = serieFarm.get(comp);
    lista.push({
      comp,
      label: formatCompetencia(comp),
      qtd: crm ? Number(crm.qtd) : 0,
      valor: crm ? Number(crm.valor) : 0,
      qtdBrasil: crm ? Number(crm.qtd_brasil) : 0,
      farmQtd: farm ? Number(farm.qtd) : 0,
      farmValor: farm ? Number(farm.valor) : 0,
    });
  }
  return lista;
});

const alertasPorMes = computed(() => {
  const mapa = new Map();
  if (!alertas.value) return mapa;
  const add = (comp, tipo) => {
    if (comp == null) return;
    const atual = mapa.get(comp) ?? { unico: 0, multi: 0, geo: 0 };
    atual[tipo] += 1;
    mapa.set(comp, atual);
  };
  for (const a of alertas.value.alertas_crm_unico ?? []) add(competenciaDeData(a.dt), 'unico');
  for (const a of alertas.value.alertas_crm_multiplos ?? []) add(competenciaDeData(a.dt), 'multi');
  for (const g of alertas.value.alertas_geograficos ?? []) add(competenciaDeData(g.dt_ini_a), 'geo');
  return mapa;
});

const kpis = computed(() => {
  const m = props.medico;
  if (!m) return [];
  const ativos = meses.value.filter(x => x.qtd > 0);
  const pico = ativos.reduce((max, x) => (x.qtd > (max?.qtd ?? -1) ? x : max), null);
  const totalQtd = ativos.reduce((acc, x) => acc + x.qtd, 0);
  const inicio = Number(m.competencia_inicio_atuacao);
  const fim = Number(m.competencia_fim_atuacao);
  return [
    { label: 'Período de atuação', value: inicio === fim ? formatCompetencia(inicio) : `${formatCompetencia(inicio)} – ${formatCompetencia(fim)}` },
    { label: 'Meses com movimento', value: formatNumberFull(Number(m.qtd_meses_atuacao)) },
    { label: 'Mês de pico', value: pico ? `${pico.label} · ${formatNumberFull(pico.qtd)} autorizações` : '—' },
    { label: 'Média nos meses ativos', value: ativos.length ? `${formatNumberFull(Math.round(totalQtd / ativos.length))} autorizações` : '—' },
    { label: 'Valor total', value: formatCurrencyFull(m.vl_total_prescricoes) },
  ];
});

const titulo = computed(() => {
  const m = props.medico;
  if (!m) return '';
  return m.no_medico ? `${m.id_medico} · ${formatTitleCase(m.no_medico)}` : `${m.id_medico} · Não localizado na base do CFM`;
});

const chartOption = computed(() => {
  const c = chartTheme.value;
  const dados = meses.value;
  const porValor = metrica.value === 'valor';
  const inscricao = props.medico?.dt_inscricao_crm ? competenciaDeData(props.medico.dt_inscricao_crm) : null;
  const labelInscricao = inscricao != null ? formatCompetencia(inscricao) : null;
  const inscricaoNoEixo = labelInscricao && dados.some(d => d.label === labelInscricao);

  return {
    backgroundColor: 'transparent',
    animationDuration: 300,
    textStyle: { color: c.text },
    legend: {
      top: 0,
      right: 8,
      textStyle: { color: c.muted, fontSize: 11 },
      itemWidth: 12,
      itemHeight: 8,
      data: [
        { name: porValor ? 'Valor do CRM' : 'Autorizações do CRM' },
        { name: '% da farmácia no mês' },
      ],
    },
    grid: { top: 36, right: 56, bottom: 36, left: 64 },
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'shadow', shadowStyle: { color: c.axisShadow } },
      backgroundColor: c.tooltip,
      borderColor: c.tooltipBorder,
      textStyle: { color: c.tooltipText, fontSize: 12 },
      formatter: (params) => {
        const d = dados[params[0]?.dataIndex];
        if (!d) return '';
        const pct = d.farmQtd > 0 ? (d.qtd / d.farmQtd) * 100 : 0;
        const al = alertasPorMes.value.get(d.comp);
        const linhas = [
          ['Autorizações do CRM', formatNumberFull(d.qtd)],
          ['Valor do CRM', formatCurrencyFull(d.valor)],
          ['% das autorizações da farmácia', `${pct.toFixed(1).replace('.', ',')}%`],
          ['Autorizações do CRM no Brasil', formatNumberFull(d.qtdBrasil)],
        ];
        const alertasHtml = al
          ? `<div style="margin-top:8px;padding-top:8px;border-top:1px solid ${c.tooltipBorder};font-size:11px;">
               ${al.unico ? `<div>● Sequência · Único CRM: ${al.unico}</div>` : ''}
               ${al.multi ? `<div>● Sequência · Múltiplos CRMs: ${al.multi}</div>` : ''}
               ${al.geo ? `<div>● Distância &gt; 400 km: ${al.geo}</div>` : ''}
             </div>`
          : '';
        return `<div style="min-width:240px">
          <div style="font-weight:600;margin-bottom:6px">${d.label}</div>
          ${linhas.map(([k, v]) => `<div style="display:flex;justify-content:space-between;gap:16px"><span style="opacity:.7">${k}</span><span style="font-weight:600">${v}</span></div>`).join('')}
          ${alertasHtml}
        </div>`;
      },
    },
    xAxis: {
      type: 'category',
      data: dados.map(d => d.label),
      axisLine: { lineStyle: { color: c.border } },
      axisTick: { show: false },
      axisLabel: { color: c.muted, fontSize: 10 },
    },
    yAxis: [
      {
        type: 'value',
        axisLabel: {
          color: c.muted,
          fontSize: 10,
          formatter: (v) => (porValor ? `R$ ${formatNumberFull(v)}` : formatNumberFull(v)),
        },
        splitLine: { lineStyle: { color: c.grid } },
      },
      {
        type: 'value',
        min: 0,
        max: 100,
        axisLabel: { color: c.muted, fontSize: 10, formatter: '{value}%' },
        splitLine: { show: false },
      },
    ],
    series: [
      {
        name: porValor ? 'Valor do CRM' : 'Autorizações do CRM',
        type: 'bar',
        barMaxWidth: 28,
        itemStyle: { color: coresDados.value.strong, borderRadius: [3, 3, 0, 0] },
        data: dados.map(d => ({
          value: porValor ? d.valor : d.qtd,
          itemStyle: alertasPorMes.value.has(d.comp) ? { color: COR_BARRA_ALERTA } : undefined,
        })),
        markLine: inscricaoNoEixo
          ? {
              symbol: 'none',
              silent: true,
              lineStyle: { color: COR_INSCRICAO, type: 'dashed', width: 1.5 },
              label: { formatter: '1ª inscrição no CRM', color: COR_INSCRICAO, fontSize: 10, position: 'insideEndTop' },
              data: [{ xAxis: labelInscricao }],
            }
          : undefined,
      },
      {
        name: '% da farmácia no mês',
        type: 'line',
        yAxisIndex: 1,
        smooth: 0.25,
        symbol: 'none',
        lineStyle: { color: coresDados.value.line, width: 2, type: 'dashed' },
        itemStyle: { color: coresDados.value.line },
        data: dados.map(d => {
          const base = porValor ? d.farmValor : d.farmQtd;
          const parte = porValor ? d.valor : d.qtd;
          return base > 0 ? Number(((parte / base) * 100).toFixed(2)) : 0;
        }),
      },
    ],
  };
});

function fechar() {
  emit('update:modelValue', false);
}
</script>

<template>
  <Dialog
    :visible="modelValue"
    modal
    dismissableMask
    class="crm-atuacao-dialog"
    :style="{ width: '94vw', maxWidth: '1600px' }"
    @update:visible="emit('update:modelValue', $event)"
  >
    <template #header>
      <div class="atuacao-dialog-header">
        <span class="atuacao-dialog-eyebrow">Atuação na farmácia</span>
        <span class="atuacao-dialog-title">{{ titulo }}</span>
      </div>
    </template>

    <div v-if="medico" class="atuacao-dialog-body">
      <div class="atuacao-kpis">
        <div v-for="kpi in kpis" :key="kpi.label" class="atuacao-kpi">
          <span class="atuacao-kpi-label">{{ kpi.label }}</span>
          <span class="atuacao-kpi-value">{{ kpi.value }}</span>
        </div>
      </div>

      <div class="atuacao-toolbar">
        <div class="atuacao-metrica" role="radiogroup" aria-label="Métrica do gráfico">
          <button
            type="button"
            role="radio"
            :aria-checked="metrica === 'qtd'"
            :class="{ 'is-active': metrica === 'qtd' }"
            @click="metrica = 'qtd'"
          >Autorizações</button>
          <button
            type="button"
            role="radio"
            :aria-checked="metrica === 'valor'"
            :class="{ 'is-active': metrica === 'valor' }"
            @click="metrica = 'valor'"
          >Valor (R$)</button>
        </div>
        <div class="atuacao-legenda">
          <span><i class="legenda-cor is-alerta" /> Mês com alerta de sequência ou distância</span>
          <span v-if="medico.dt_inscricao_crm"><i class="legenda-cor is-inscricao" /> 1ª inscrição: {{ formatarData(medico.dt_inscricao_crm) }}</span>
          <span v-if="alertasLoading" class="legenda-status"><i class="pi pi-spinner pi-spin" /> Carregando alertas…</span>
          <span v-else-if="alertasErro" class="legenda-status is-erro"><i class="pi pi-exclamation-triangle" /> {{ alertasErro }}</span>
        </div>
      </div>

      <VChart class="atuacao-chart" :option="chartOption" autoresize />

      <p class="atuacao-nota">
        A linha mostra a parcela das autorizações (ou do valor) da farmácia no mês que foi atribuída a este CRM.
        O tooltip de cada mês traz também o volume do mesmo CRM no Brasil.
      </p>
    </div>

    <template #footer>
      <button type="button" class="atuacao-fechar" @click="fechar">Fechar</button>
    </template>
  </Dialog>
</template>

<style scoped>
.atuacao-dialog-header { display: flex; flex-direction: column; gap: 0.15rem; }
.atuacao-dialog-eyebrow {
  font-size: 0.66rem;
  font-weight: 600;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--text-muted);
}
.atuacao-dialog-title { font-size: 1rem; font-weight: 600; color: var(--text-color); }
.atuacao-dialog-body { display: flex; flex-direction: column; gap: 1rem; }
.atuacao-kpis {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 0.75rem;
}
.atuacao-kpi {
  display: flex;
  flex-direction: column;
  gap: 0.3rem;
  padding: 0.7rem 0.9rem;
  border: 1px solid var(--card-border);
  border-radius: 10px;
  background: color-mix(in srgb, var(--text-color) 3%, transparent);
}
.atuacao-kpi-label {
  font-size: 0.64rem;
  font-weight: 600;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--text-muted);
}
.atuacao-kpi-value { font-size: 0.92rem; font-weight: 600; color: var(--text-color); }
.atuacao-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
  flex-wrap: wrap;
}
.atuacao-metrica {
  display: inline-flex;
  gap: 2px;
  padding: 3px;
  border: 1px solid var(--card-border);
  border-radius: 9px;
}
.atuacao-metrica button {
  min-height: 30px;
  padding: 0 0.9rem;
  border: 0;
  border-radius: 7px;
  background: transparent;
  color: var(--text-secondary);
  font: inherit;
  font-size: 0.74rem;
  font-weight: 600;
  cursor: pointer;
}
.atuacao-metrica button.is-active {
  background: color-mix(in srgb, var(--primary-color) 18%, transparent);
  color: var(--primary-color);
}
.atuacao-metrica button:focus-visible {
  outline: 2px solid color-mix(in srgb, var(--primary-color) 70%, transparent);
  outline-offset: 2px;
}
.atuacao-legenda {
  display: flex;
  align-items: center;
  gap: 1.1rem;
  font-size: 0.72rem;
  color: var(--text-secondary);
}
.atuacao-legenda span { display: inline-flex; align-items: center; gap: 0.4rem; }
.legenda-cor { width: 10px; height: 10px; border-radius: 2px; display: inline-block; }
.legenda-cor.is-alerta { background: var(--risk-critical); }
.legenda-cor.is-inscricao { background: var(--risk-medium); height: 2px; }
.legenda-status { color: var(--text-muted); }
.legenda-status.is-erro { color: var(--risk-critical); }
.atuacao-chart { width: 100%; height: 360px; }
.atuacao-nota { margin: 0; font-size: 0.72rem; color: var(--text-muted); }
.atuacao-fechar {
  min-height: 34px;
  padding: 0 1.1rem;
  border: 1px solid var(--card-border);
  border-radius: 8px;
  background: transparent;
  color: var(--text-color);
  font: inherit;
  font-size: 0.8rem;
  font-weight: 500;
  cursor: pointer;
}
.atuacao-fechar:hover { border-color: var(--primary-color); color: var(--primary-color); }
</style>
