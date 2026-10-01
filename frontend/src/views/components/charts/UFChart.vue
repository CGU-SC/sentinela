<script setup>
import { computed } from 'vue';
import { useAnalyticsStore } from '@/stores/analytics';
import { useFormatting } from '@/composables/useFormatting';
import { useRiskMetrics } from '@/composables/useRiskMetrics';
import { useChartTheme } from '@/config/chartTheme';
import { CHART_TOOLTIP_SHADOW } from '@/config/colors.js';
import { storeToRefs } from 'pinia';

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

// ── Props ─────────────────────────────────────────────────────────────────
const props = defineProps({
  height: { type: Number, default: 420 },
  grow:   { type: Boolean, default: false },
});

// ── Stores ────────────────────────────────────────────────────────────────
const analyticsStore = useAnalyticsStore();
const { resultadoSentinelaUF, isLoading } = storeToRefs(analyticsStore);
const { formatBRL, formatCurrencyFull } = useFormatting();
const { getRiskColor, getRiskLabel } = useRiskMetrics();
const { chartTheme, chartUFAccents } = useChartTheme();

// ── Dados ordenados por % Valor decrescente ───────────────────────────────
const sortedData = computed(() =>
  [...resultadoSentinelaUF.value].sort((a, b) => (b.percValSemComp ?? 0) - (a.percValSemComp ?? 0))
);

// ── Tema (cores do gráfico vindas de colors.js via useChartTheme) ─────────
const C = computed(() => ({
  ...chartTheme.value,
  ...chartUFAccents.value,  // bar1, bar1Grad, bar2, bar2Grad, area, areaGrad, barRed, barOrange
}));

// ── Opção ECharts ─────────────────────────────────────────────────────────
const chartOption = computed(() => {
  const c    = C.value;
  const ufs  = sortedData.value.map(i => i.uf ?? 'ND');

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

    // Dois grids sincronizados
    grid: [
      // Painel superior — Volume Total
      { top: 44, left: 80, right: 24, height: '35%' },
      // Painel inferior — % por UF (sem gap entre os dois)
      { top: '46%', left: 80, right: 24, bottom: 56 },
    ],

    // X axis espelhado nos dois painéis
    xAxis: [
      {
        gridIndex: 0,
        type: 'category',
        data: ufs,
        axisLine:  { lineStyle: { color: c.grid } },
        axisTick:  { show: false },
        axisLabel: { show: false },
        axisPointer: { label: { show: false } },
      },
      {
        gridIndex: 1,
        type: 'category',
        data: ufs,
        axisLine:  { lineStyle: { color: c.grid } },
        axisTick:  { show: false },
        axisLabel: { color: c.muted, fontSize: 11, fontWeight: 700, fontFamily: 'Inter, sans-serif' },
        name: 'UF — ordenado por % Valor s/ Comprovação (decrescente)',
        nameLocation: 'middle',
        nameGap: 40,
        nameTextStyle: { color: c.muted, fontSize: 10, fontWeight: 500 },
      },
    ],

    yAxis: [
      // Painel superior — BRL
      {
        gridIndex: 0,
        type: 'value',
        name: 'Valor Total',
        nameLocation: 'end',
        nameTextStyle: { color: c.area, fontSize: 11, fontWeight: 700 },
        axisLine:  { show: false },
        axisTick:  { show: false },
        splitLine: { lineStyle: { color: c.grid, type: 'dashed' } },
        axisLabel: { color: c.muted, fontSize: 10, formatter: (v) => formatBRL(v) },
      },
      // Painel inferior — %
      {
        gridIndex: 1,
        type: 'value',
        name: '% S/ Comp',
        nameLocation: 'end',
        nameTextStyle: { color: c.muted, fontSize: 11, fontWeight: 700 },
        axisLine:  { show: false },
        axisTick:  { show: false },
        splitLine: { lineStyle: { color: c.grid, type: 'dashed' } },
        axisLabel: { color: c.muted, fontSize: 10, formatter: (v) => `${v}%` },
      },
    ],

    axisPointer: {
      link: [{ xAxisIndex: 'all' }],
      label: { backgroundColor: 'rgba(15, 23, 42, 0.85)' },
    },

    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'shadow', shadowStyle: { color: CHART_TOOLTIP_SHADOW } },
      backgroundColor: 'rgba(15, 23, 42, 0.85)',
      borderColor: 'rgba(255, 255, 255, 0.1)',
      borderWidth: 1,
      padding: [12, 16],
      textStyle: { color: '#fff', fontFamily: 'Inter, sans-serif', fontSize: 12 },
      formatter: (params) => {
        const idx  = params[0]?.dataIndex;
        const item = sortedData.value[idx];
        if (!item) return '';
        const perc = item.percValSemComp ?? 0;
        const riskColor = getRiskColor(perc);
        const riskLabel = getRiskLabel(perc);
        return `
          <div style="font-weight:700;font-size:15px;margin-bottom:10px;display:flex;align-items:center;gap:8px;">
            ${item.uf}
            <span style="font-size:10px;font-weight:700;padding:2px 8px;border-radius:10px;
                         background:${riskColor}22;color:${riskColor};">RISCO ${riskLabel.toUpperCase()}</span>
          </div>
          <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px 18px;">
            <div style="grid-column:1/-1;">
              <div style="font-size:10px;opacity:.6;letter-spacing:.04em;display:flex;align-items:center;gap:5px;">
                <span style="width:10px;height:10px;border-radius:2px;background:${c.area};display:inline-block;"></span>
                VALOR TOTAL MOVIMENTADO
              </div>
              <div style="font-weight:700;font-size:14px;">${formatCurrencyFull(item.totalMov ?? 0)}</div>
            </div>
            <div>
              <div style="font-size:10px;opacity:.6;letter-spacing:.04em;display:flex;align-items:center;gap:5px;">
                <span style="width:10px;height:10px;border-radius:2px;background:${c.barRed};display:inline-block;"></span>
                % VALOR S/ COMP
              </div>
              <div style="font-weight:700;font-size:14px;color:${riskColor};">${perc.toFixed(2)}%</div>
            </div>
            <div>
              <div style="font-size:10px;opacity:.6;letter-spacing:.04em;display:flex;align-items:center;gap:5px;">
                <span style="width:10px;height:10px;border-radius:2px;background:${c.barOrange};display:inline-block;"></span>
                % QTDE S/ COMP
              </div>
              <div style="font-weight:700;font-size:14px;">${(item.percQtdeSemComp ?? 0).toFixed(2)}%</div>
            </div>
            <div>
              <div style="font-size:10px;opacity:.6;letter-spacing:.04em;">CNPJs</div>
              <div style="font-weight:600;">${(item.cnpjs ?? 0).toLocaleString('pt-BR')}</div>
            </div>
          </div>`;
      },
    },

    series: [
      // Painel superior — Área: Valor Total Movimentado
      {
        name: 'Valor Total Movimentado',
        type: 'line',
        xAxisIndex: 0,
        yAxisIndex: 0,
        smooth: true,
        symbol: 'none',
        data: sortedData.value.map(i => parseFloat((i.totalMov ?? 0).toFixed(2))),
        lineStyle: { color: c.area, width: 2 },
        areaStyle: {
          color: {
            type: 'linear', x: 0, y: 0, x2: 0, y2: 1,
            colorStops: [
              { offset: 0, color: c.area + 'bb' },
              { offset: 1, color: c.area + '08' },
            ],
          },
        },
        z: 1,
      },

      // Painel inferior — Barra: % Valor s/ Comprovação (vermelho)
      {
        name: '% Valor s/ Comp',
        type: 'bar',
        xAxisIndex: 1,
        yAxisIndex: 1,
        barMaxWidth: 20,
        data: sortedData.value.map(i => parseFloat((i.percValSemComp ?? 0).toFixed(2))),
        itemStyle: {
          borderRadius: [4, 4, 0, 0],
          color: {
            type: 'linear', x: 0, y: 0, x2: 0, y2: 1,
            colorStops: [
              { offset: 0, color: c.barRed },
              { offset: 1, color: c.barRed + '33' },
            ],
          },
        },
        emphasis: { itemStyle: { opacity: 1 } },
        z: 2,
      },

      // Painel inferior — Barra: % Qtde s/ Comprovação (laranja)
      {
        name: '% Qtde s/ Comp',
        type: 'bar',
        xAxisIndex: 1,
        yAxisIndex: 1,
        barMaxWidth: 20,
        data: sortedData.value.map(i => parseFloat((i.percQtdeSemComp ?? 0).toFixed(2))),
        itemStyle: {
          borderRadius: [4, 4, 0, 0],
          color: {
            type: 'linear', x: 0, y: 0, x2: 0, y2: 1,
            colorStops: [
              { offset: 0, color: c.barOrange },
              { offset: 1, color: c.barOrange + '33' },
            ],
          },
        },
        emphasis: { itemStyle: { opacity: 1 } },
        z: 2,
      },
    ],
  };
});
</script>

<template>
  <div class="chart-section shadow-card" :class="{ 'is-refreshing': isLoading, 'grow': props.grow }">
    <div class="section-header">
      <i class="pi pi-chart-bar"></i>
      <h3>% VALOR, % QTDE S/ COMPROVAÇÃO E VOLUME MOVIMENTADO POR UF</h3>
      <div class="spacer"></div>
      <i
        class="pi pi-info-circle help-icon"
        v-tooltip.top="'Barras = Valor Total Movimentado; Área vermelha = Valor sem Comprovação (exposição ao risco dentro do mercado); Linha = % Valor sem Comprovação.'"
        tabindex="0"
        aria-label="Como ler o gráfico por UF"
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
}

.chart-section.grow {
  flex: 1;
  min-height: 0;
}

.chart-wrapper {
  height: v-bind('props.height + "px"');
  margin: 0 -1rem -1rem -1rem;
}

.grow .chart-wrapper {
  flex: 1;
  min-height: 0;
  height: auto;
}

.echart {
  width: 100%;
  height: 100%;
}

.spacer { flex: 1; }

.is-refreshing {
  opacity: 0.5;
  pointer-events: none;
}
</style>
