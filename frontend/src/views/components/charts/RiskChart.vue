<script setup>
import { computed } from 'vue';
import { useAnalyticsStore } from '@/stores/analytics';
import { useFormatting } from '@/composables/useFormatting';
import { useChartTheme } from '@/config/chartTheme';
import { CHART_TOOLTIP_SHADOW } from '@/config/colors.js';
import { homeTooltip } from '@/config/homeTooltipConfig';
import { storeToRefs } from 'pinia';
import Button from 'primevue/button';

// ── ECharts ───────────────────────────────────────────────────────────────
import { use } from 'echarts/core';
import { CanvasRenderer } from 'echarts/renderers';
import { BarChart, LineChart } from 'echarts/charts';
import {
  GridComponent,
  TooltipComponent,
  LegendComponent,
  AxisPointerComponent,
} from 'echarts/components';
import VChart from 'vue-echarts';

use([CanvasRenderer, BarChart, LineChart, GridComponent, TooltipComponent, LegendComponent, AxisPointerComponent]);

// ── Stores ────────────────────────────────────────────────────────────────
const analyticsStore = useAnalyticsStore();
const { fatorRisco, fatorRiscoLoading } = storeToRefs(analyticsStore);
const { formatBRL, formatCurrencyFull, formatNumberFull } = useFormatting();
const { chartTheme, chartDataColors, chartRiskAccents } = useChartTheme();
const riskChartInfoTooltip = homeTooltip('riskDistribution');

// ── Cache de Dados para Transição Suave (Flicker-Free) ──────────────────
// Mantém os dados anteriores visíveis para o ECharts animar a transição
// em vez de limpar o gráfico e redesenhar do zero.
import { ref, watch } from 'vue';
import { useDelayedLoading } from '@/composables/useDelayedLoading';
const cachedFatorRisco = ref(fatorRisco.value);
const showRefreshing = useDelayedLoading(fatorRiscoLoading);

watch([fatorRisco, fatorRiscoLoading], ([newVal, loading]) => {
  if (newVal?.length > 0 && !loading) {
    cachedFatorRisco.value = newVal;
  }
}, { immediate: true });

// ── Tema (cores do gráfico vindas de colors.js via useChartTheme) ─────────
const C = computed(() => ({
  ...chartTheme.value,
  ...chartRiskAccents.value,        // bar, barGrad (violeta)
  area: chartDataColors.value.red,  // mesmo vermelho do Volume Financeiro
}));

// ── Opção ECharts ─────────────────────────────────────────────────────────
const chartOption = computed(() => {
  const c      = C.value;
  const currentData = cachedFatorRisco.value || [];
  const faixas = currentData.map(b => b.faixa);

  return {
    backgroundColor: c.bg,
    animation: true,
    animationDuration: 1000,
    animationEasing: 'cubicOut',
    textStyle: { fontFamily: 'Inter, sans-serif' },

    legend: {
      top: 6,
      left: 'center',
      textStyle: { color: c.muted, fontSize: 12, fontWeight: 600 },
      itemGap: 24,
      itemWidth: 14,
      itemHeight: 8,
    },

    grid: { top: 44, left: 80, right: 80, bottom: 64 },

    xAxis: {
      type: 'category',
      data: faixas,
      axisLine:  { lineStyle: { color: c.grid } },
      axisTick:  { show: false },
      axisLabel: { color: c.muted, fontSize: 11, fontWeight: 700, fontFamily: 'Inter, sans-serif', interval: 0, rotate: 15 },
      name: 'Faixa de Percentual de Não Comprovação',
      nameLocation: 'middle',
      nameGap: 50,
      nameTextStyle: { color: c.muted, fontSize: 10, fontWeight: 500 },
    },

    yAxis: [
      {
        type: 'value',
        name: 'Qtd Estab',
        nameLocation: 'end',
        nameTextStyle: { color: c.bar, fontSize: 11, fontWeight: 700 },
        axisLine:  { show: false },
        axisTick:  { show: false },
        splitLine: { lineStyle: { color: c.grid, type: 'dashed' } },
        axisLabel: { color: c.muted, fontSize: 10, formatter: (v) => v.toLocaleString('pt-BR') },
      },
      {
        type: 'value',
        name: 'Valor S/ Comp',
        nameLocation: 'end',
        nameTextStyle: { color: c.area, fontSize: 11, fontWeight: 700 },
        axisLine:  { show: false },
        axisTick:  { show: false },
        splitLine: { show: false },
        axisLabel: { color: c.muted, fontSize: 10, formatter: (v) => formatBRL(v) },
      },
    ],

    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'shadow', shadowStyle: { color: CHART_TOOLTIP_SHADOW } },
      backgroundColor: c.tooltip,
      borderColor: c.tooltipBorder,
      borderWidth: 1,
      padding: [12, 16],
      textStyle: { color: c.tooltipText, fontFamily: 'Inter, sans-serif', fontSize: 12 },
      formatter: (params) => {
        const bar  = params.find(p => p.seriesIndex === 0);
        const area = params.find(p => p.seriesIndex === 1);
        const faixa = bar?.axisValue ?? '';
        return `
          <div style="color:${c.tooltipText}">
            <div style="font-weight:700;font-size:14px;margin-bottom:10px;">${faixa}</div>
            <div style="display:flex;flex-direction:column;gap:6px;">
              <div style="display:flex;align-items:center;gap:8px;">
                <span style="width:10px;height:10px;border-radius:2px;background:${c.bar};display:inline-block;"></span>
                <span style="font-size:10px;opacity:.6;letter-spacing:.04em;text-transform:uppercase;">Qtd Estabelecimentos</span>
              </div>
              <div style="font-weight:700;font-size:14px;margin-bottom:4px;">${formatNumberFull(bar?.value ?? 0)}</div>
              <div style="display:flex;align-items:center;gap:8px;">
                <span style="width:10px;height:10px;border-radius:2px;background:${c.area};display:inline-block;"></span>
                <span style="font-size:10px;opacity:.6;letter-spacing:.04em;text-transform:uppercase;">Valor Sem Comprovação</span>
              </div>
              <div style="font-weight:700;font-size:14px;color:${c.area};">${formatCurrencyFull(area?.value ?? 0)}</div>
            </div>
          </div>`;
      },
    },

    series: [
      // Barras — Qtd Estab (eixo Y esquerdo)
      {
        name: 'Qtd Estab',
        type: 'bar',
        yAxisIndex: 0,
        barMaxWidth: 40,
        data: currentData.map(b => b.qtd),
        itemStyle: {
          borderRadius: [6, 6, 0, 0],
          color: {
            type: 'linear', x: 0, y: 0, x2: 0, y2: 1,
            colorStops: [
              { offset: 0, color: c.barGrad },
              { offset: 1, color: c.bar + '55' },
            ],
          },
        },
        emphasis: { itemStyle: { opacity: 1 } },
      },

      // Área — Valor Sem Comprovação (eixo Y direito)
      {
        name: 'Valor S/ Comp',
        type: 'line',
        yAxisIndex: 1,
        smooth: true,
        symbol: 'none',
        data: currentData.map(b => b.valor_raw),
        lineStyle: { color: c.area, width: 2.5 },
        areaStyle: {
          color: {
            type: 'linear', x: 0, y: 0, x2: 0, y2: 1,
            colorStops: [
              { offset: 0, color: c.area + 'aa' },
              { offset: 1, color: c.area + '08' },
            ],
          },
        },
      },
    ],
  };
});
</script>

<template>
  <div class="chart-section" :class="{ 'is-refreshing': showRefreshing }">
    <div class="chart-header">
      <i class="pi pi-chart-bar"></i>
      <h3>Estabelecimentos por faixa de não comprovação</h3>
      <div class="spacer"></div>
      <i
        class="pi pi-info-circle info-icon"
        v-tooltip.top="riskChartInfoTooltip"
      />
    </div>
    <div class="chart-wrapper">
      <v-chart class="echart" :option="chartOption" autoresize />
    </div>
  </div>
</template>

<style scoped>
.chart-section {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
  background: var(--card-bg);
  border: 1px solid var(--card-border);
  border-radius: 12px;
  box-shadow: 0 1px 3px rgba(0,0,0,0.08), 0 1px 2px rgba(0,0,0,0.04);
  overflow: hidden;
  transition: opacity 0.25s ease;
}

.chart-header {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 0.75rem 1.25rem;
  border-bottom: 1px solid var(--tabs-border);
  flex-shrink: 0;
}

.chart-header h3 {
  margin: 0;
  font-size: 0.85rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--text-color-85);
  opacity: 0.8;
}

.chart-header i {
  color: var(--primary-color);
  font-size: 1rem;
}

.info-icon {
  font-size: 0.8rem;
  color: var(--text-muted);
  opacity: 0.6;
  cursor: default;
  line-height: 1;
  display: flex;
  align-items: center;
}

.chart-wrapper {
  flex: 1;
  min-height: 0;
}

.echart {
  width: 100%;
  height: 100%;
}

.spacer { flex: 1; }

.is-refreshing {
  opacity: 0.45;
  pointer-events: none;
}
</style>
