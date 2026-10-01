<script setup>
import { computed } from 'vue';
import { storeToRefs } from 'pinia';
import { use } from 'echarts/core';
import { CanvasRenderer } from 'echarts/renderers';
import { BarChart, LineChart } from 'echarts/charts';
import { GridComponent, TooltipComponent, LegendComponent, AxisPointerComponent } from 'echarts/components';
import VChart from 'vue-echarts';
import { useAnalyticsStore } from '@/stores/analytics';
import { useFormatting } from '@/composables/useFormatting';
import { useChartTheme } from '@/config/chartTheme';
import { PALETTE } from '@/config/colors';

use([CanvasRenderer, BarChart, LineChart, GridComponent, TooltipComponent, LegendComponent, AxisPointerComponent]);

const analyticsStore = useAnalyticsStore();
const { producaoSemestral, producaoSemestralLoading, producaoSemestralError } = storeToRefs(analyticsStore);
const { formatBRL, formatCurrencyFull } = useFormatting();
const { chartTheme, chartDataColors } = useChartTheme();

const chartRows = computed(() =>
  [...(producaoSemestral.value || [])].sort(
    (a, b) => Number(a.chave_semestre ?? 0) - Number(b.chave_semestre ?? 0),
  ),
);

const totalSemComprovacao = computed(() =>
  chartRows.value.reduce((sum, row) => sum + Number(row.valor_sem_comprovacao ?? 0), 0),
);

function formatSemestreLabel(semStr) {
  if (!semStr) return '';
  if (semStr.includes('S/')) {
    const [s, year] = semStr.split('S/');
    return `${s}º Semestre de ${year}`;
  }
  if (semStr.includes('-S')) {
    const [year, s] = semStr.split('-S');
    return `${s.replace('S', '')}º Semestre de ${year}`;
  }
  return semStr;
}

const C = computed(() => ({
  ...chartTheme.value,
  ...chartDataColors.value,
  percentual: PALETTE.amber[500],
}));

function formatPercentual(value) {
  return `${Number(value).toLocaleString('pt-BR', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}%`;
}

const chartOption = computed(() => {
  const c = C.value;
  const labels = chartRows.value.map((row) => row.semestre);
  const irregular = chartRows.value.map((row) => Number((row.valor_sem_comprovacao ?? 0).toFixed(2)));
  const percentualNaoComprovacao = chartRows.value.map((row) =>
    Number(Number(row.pct_sem_comprovacao).toFixed(2)),
  );

  return {
    backgroundColor: c.bg,
    animation: true,
    animationDuration: 900,
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

    grid: [
      { top: 48, left: 80, right: 58, height: '44%', containLabel: false },
      { top: '66%', left: 80, right: 58, bottom: 42, containLabel: false },
    ],

    tooltip: {
      trigger: 'axis',
      confine: true,
      axisPointer: { type: 'shadow', shadowStyle: { color: c.axisShadow } },
      backgroundColor: c.tooltip,
      borderColor: c.tooltipBorder,
      borderWidth: 1,
      padding: [12, 16],
      textStyle: { color: c.tooltipText, fontFamily: 'Inter, sans-serif', fontSize: 12 },
      shadowBlur: 10,
      shadowColor: 'rgba(0,0,0,0.15)',
      formatter: (params) => {
        const idx = params[0]?.dataIndex ?? 0;
        const row = chartRows.value[idx];
        if (!row) return '';

        return `
          <div style="color:${c.tooltipText}">
            <div style="font-weight:600;font-size:14px;margin-bottom:10px;">${formatSemestreLabel(row.semestre)}</div>
            <div style="display:flex;flex-direction:column;gap:6px;">
              <div style="display:flex;align-items:center;gap:8px;">
                <span style="width:10px;height:10px;border-radius:2px;background:${c.red};display:inline-block;"></span>
                <span style="font-size:10px;opacity:.6;letter-spacing:.04em;text-transform:uppercase;">Valor sem comprovação</span>
              </div>
              <div style="font-weight:600;font-size:13px;color:${c.red};margin-bottom:2px;">
                ${formatCurrencyFull(row.valor_sem_comprovacao ?? 0)}
              </div>
              <div style="display:flex;align-items:center;gap:8px;">
                <span style="width:10px;height:10px;border-radius:999px;background:${c.percentual};display:inline-block;"></span>
                <span style="font-size:10px;opacity:.6;letter-spacing:.04em;text-transform:uppercase;">% não comprovação</span>
              </div>
              <div style="font-weight:600;font-size:13px;color:${c.percentual};margin-bottom:2px;">${formatPercentual(row.pct_sem_comprovacao)}</div>
              <div style="font-size:11px;opacity:.65;">CNPJs com produção: ${(row.cnpjs ?? 0).toLocaleString('pt-BR')}</div>
            </div>
          </div>`;
      },
    },

    axisPointer: {
      link: [{ xAxisIndex: [0, 1] }],
      label: { backgroundColor: c.tooltip },
    },

    xAxis: [
      {
        gridIndex: 0,
        type: 'category',
        data: labels,
        axisLine: { lineStyle: { color: c.grid } },
        axisTick: { show: false },
        axisLabel: { show: false },
      },
      {
        gridIndex: 1,
        type: 'category',
        data: labels,
        axisLine: { lineStyle: { color: c.grid } },
        axisTick: { show: false },
        axisLabel: {
          color: c.muted,
          fontSize: 11,
          fontWeight: 600,
          fontFamily: 'Inter, sans-serif',
          rotate: labels.length > 10 ? 30 : 0,
        },
      },
    ],

    yAxis: [
      {
        gridIndex: 0,
        type: 'value',
        name: 'Valor',
        nameTextStyle: { color: c.muted, fontSize: 10, fontWeight: 600 },
        axisLine: { show: false },
        axisTick: { show: false },
        splitLine: { lineStyle: { color: c.grid, type: 'dashed' } },
        axisLabel: { color: c.muted, fontSize: 10, formatter: (value) => formatBRL(value) },
      },
      {
        gridIndex: 1,
        type: 'value',
        name: '% não comp.',
        min: 0,
        nameTextStyle: { color: c.muted, fontSize: 10, fontWeight: 600 },
        axisLine: { show: false },
        axisTick: { show: false },
        splitLine: { show: false },
        axisLabel: { color: c.muted, fontSize: 10, formatter: (value) => formatPercentual(value) },
      },
    ],

    series: [
      {
        name: 'Valor sem comprovação',
        type: 'bar',
        xAxisIndex: 0,
        yAxisIndex: 0,
        barMaxWidth: 56,
        data: irregular,
        itemStyle: {
          borderRadius: [6, 6, 0, 0],
          color: {
            type: 'linear',
            x: 0,
            y: 0,
            x2: 0,
            y2: 1,
            colorStops: [
              { offset: 0, color: c.redGrad },
              { offset: 1, color: `${c.red}55` },
            ],
          },
        },
      },
      {
        name: '% não comprovação',
        type: 'line',
        xAxisIndex: 1,
        yAxisIndex: 1,
        smooth: true,
        symbol: 'circle',
        symbolSize: 7,
        data: percentualNaoComprovacao,
        lineStyle: { color: c.percentual, width: 3 },
        itemStyle: { color: c.percentual },
        areaStyle: {
          color: {
            type: 'linear',
            x: 0,
            y: 0,
            x2: 0,
            y2: 1,
            colorStops: [
              { offset: 0, color: `${c.percentual}55` },
              { offset: 1, color: `${c.percentual}0f` },
            ],
          },
        },
        emphasis: { focus: 'series' },
        z: 3,
      },
    ],
  };
});
</script>

<template>
  <div class="semester-production-chart" :class="{ 'is-refreshing': producaoSemestralLoading }">
    <div class="chart-header">
      <div class="header-left">
        <i class="pi pi-chart-bar"></i>
        <div>
          <h3>VALOR SEM COMPROVAÇÃO E % SEM COMPROVAÇÃO POR SEMESTRE</h3>
          <span>Painel superior mostra valor sem comprovação; painel inferior mostra o percentual de não comprovação</span>
        </div>
      </div>
      <div class="header-total">
        <span>Total sem comprovação</span>
        <strong>{{ producaoSemestralError ? '—' : formatBRL(totalSemComprovacao) }}</strong>
      </div>
    </div>

    <div class="chart-wrapper">
      <div v-if="producaoSemestralError" class="empty-state error-state" role="alert">
        <i class="pi pi-exclamation-triangle"></i>
        <span>{{ producaoSemestralError }}</span>
      </div>
      <VChart v-else-if="chartRows.length" class="echart" :option="chartOption" autoresize />
      <div v-else class="empty-state">
        <i class="pi pi-chart-bar"></i>
        <span>Sem dados semestrais para o escopo atual</span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.semester-production-chart {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
  background: var(--card-bg);
  border: 1px solid var(--card-border);
  border-radius: 12px;
  box-shadow:
    0 1px 3px rgba(0, 0, 0, 0.08),
    0 1px 2px rgba(0, 0, 0, 0.04);
  overflow: hidden;
  transition: opacity 0.25s ease;
}

.chart-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
  padding: 0.85rem 1rem 0.2rem;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 0.7rem;
  min-width: 0;
}

.header-left i {
  width: 2rem;
  height: 2rem;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  border-radius: 8px;
  color: var(--primary-color);
  background: color-mix(in srgb, var(--primary-color) 10%, transparent);
}

.chart-header h3 {
  margin: 0;
  color: var(--text-color-85);
  font-size: 0.78rem;
  font-weight: 800;
  letter-spacing: 0.02em;
}

.chart-header span {
  color: var(--text-muted);
  font-size: 0.72rem;
}

.header-total {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 0.1rem;
  flex-shrink: 0;
}

.header-total strong {
  color: var(--text-color-85);
  font-size: 1rem;
  line-height: 1;
}

.chart-wrapper {
  flex: 1;
  min-height: 0;
}

.echart {
  width: 100%;
  height: 100%;
}

.empty-state {
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0.55rem;
  color: var(--text-muted);
  font-size: 0.8rem;
}

/* Erro da API: distinto de "sem dados" (filtro inválido ou dado indisponível). */
.error-state {
  padding: 0 1.5rem;
  text-align: center;
  color: var(--color-error);
}

.is-refreshing {
  opacity: 0.45;
  pointer-events: none;
}

@media (max-width: 680px) {
  .chart-header {
    align-items: flex-start;
    flex-direction: column;
  }

  .header-total {
    align-items: flex-start;
  }
}
</style>
