<script setup>
import { computed, ref, onMounted, watch, nextTick } from "vue";
import { useAnalyticsStore } from "@/stores/analytics";
import { useDelayedLoading } from "@/composables/useDelayedLoading";
import { useFormatting } from "@/composables/useFormatting";
import { useChartTheme } from "@/config/chartTheme";
import { useThemeStore } from "@/stores/theme";
import { useFilterStore } from "@/stores/filters";
import { MAP_VISUAL_SCALE } from "@/config/colors.js";
import { storeToRefs } from "pinia";
import { use } from "echarts/core";
import { ensureBrasilUfMap } from "@/composables/echartsMaps";
import { CanvasRenderer } from "echarts/renderers";
import { MapChart } from "echarts/charts";
import { TooltipComponent, VisualMapComponent } from "echarts/components";
import VChart from "vue-echarts";

use([CanvasRenderer, MapChart, TooltipComponent, VisualMapComponent]);

const analyticsStore = useAnalyticsStore();
const filterStore = useFilterStore();
const { resultadoSentinelaUFNacional, isLoading } = storeToRefs(analyticsStore);
const showRefreshing = useDelayedLoading(isLoading);
const { formatBRL, formatPercent } = useFormatting();
const { chartTheme } = useChartTheme();
const themeStore = useThemeStore();

const mapAreaColor = computed(() =>
  themeStore.isDark ? "rgba(255,255,255,0.07)" : "rgba(0,0,0,0.04)",
);
const mapBorderColor = computed(() =>
  themeStore.isDark ? "rgba(255,255,255,0.15)" : "rgba(0,0,0,0.15)",
);

// ── GeoJSON do Brasil ────────────────────────────────────────────────────────
const mapReady = ref(false);
const mapKey = ref(0);

onMounted(async () => {
  await ensureBrasilUfMap();
  mapReady.value = true;
  mapKey.value++;
});

// ── Escala ativa conforme tema ────────────────────────────────────────────────
const activeScale = computed(
  () => MAP_VISUAL_SCALE[themeStore.isDark ? "dark" : "light"],
);

const getRiskPiece = (perc) =>
  activeScale.value.find(
    (p) => (p.min == null || perc >= p.min) && (p.max == null || perc < p.max),
  ) ?? activeScale.value[activeScale.value.length - 1];

// ── mapData ──────────────────────────────────────────────────────────────────
const mapData = computed(() => {
  const hasSelection =
    filterStore.selectedUF && filterStore.selectedUF !== "Todos";

  return resultadoSentinelaUFNacional.value.map((d) => {
    const perc = d.percValSemComp ?? 0;
    const piece = getRiskPiece(perc);
    const isSelected = hasSelection && d.uf === filterStore.selectedUF;
    const opacity = hasSelection && !isSelected ? 0.85 : 1;

    return {
      name: d.uf,
      value: perc,
      valSemComp: d.valSemComp ?? 0,
      cnpjs: d.cnpjs ?? 0,
      selected: isSelected,
      itemStyle: { areaColor: piece.color, opacity },
      select: {
        itemStyle: {
          areaColor: piece.color,
          borderColor: piece.borderColor,
          borderWidth: 2.5,
          shadowColor: piece.borderColor,
          shadowBlur: 14,
          opacity: 1,
        },
      },
      unselected: { itemStyle: { areaColor: piece.color, opacity } },
      emphasis: {
        itemStyle: {
          areaColor: piece.color,
          borderColor: piece.borderColor,
          borderWidth: 2,
          opacity: 1,
        },
      },
    };
  });
});

// ── chart option ─────────────────────────────────────────────────────────────
const chartOption = computed(() => {
  const c = chartTheme.value;
  return {
    backgroundColor: c.bg,
    tooltip: {
      trigger: "item",
      confine: true,
      backgroundColor: c.tooltip,
      borderColor: c.tooltipBorder,
      borderWidth: 1,
      padding: [12, 16],
      textStyle: {
        color: c.tooltipText,
        fontFamily: "Inter, sans-serif",
        fontSize: 12,
      },
      formatter: (params) => {
        if (!params.data)
          return `
          <div style="color:${c.tooltipText};">
            <div style="font-weight:700;font-size:14px;margin-bottom:4px;">${params.name}</div>
            <div style="font-size:11px;opacity:0.6;">Sem dados</div>
          </div>`;
        const d = params.data;
        return `
          <div style="color:${c.tooltipText}">
            <div style="font-weight:700;font-size:14px;margin-bottom:8px;">${params.name}</div>
            <div style="display:flex;flex-direction:column;gap:4px;font-size:12px;">
              <div>% sem comprovação: <strong>${formatPercent(d.value)}</strong></div>
              <div>Valor sem comprovação: <strong>${formatBRL(d.valSemComp)}</strong></div>
              <div>CNPJs: <strong>${(d.cnpjs ?? 0).toLocaleString("pt-BR")}</strong></div>
            </div>
          </div>`;
      },
    },
    visualMap: {
      show: false,
      pieces: activeScale.value,
      seriesIndex: 0,
    },
    series: [
      {
        type: "map",
        map: "brasil-uf",
        nameProperty: "UF",
        roam: false,
        layoutCenter: ["50%", "45%"],
        layoutSize: "95%",
        aspectScale: 1,
        selectedMode: "single",
        select: { label: { show: false } }, // Adicionado para manter consistência e evitar poluição
        emphasis: {
          label: { show: true, fontSize: 10, fontWeight: 700, color: c.text },
        },
        label: {
          show: true,
          fontSize: 9,
          fontWeight: 600,
          color: c.text,
          fontFamily: "Inter, sans-serif",
        },
        itemStyle: {
          borderColor: mapBorderColor.value,
          borderWidth: 1,
          areaColor: mapAreaColor.value,
        },
        data: mapData.value,
      },
    ],
  };
});

const chartRef = ref(null);
let _prevSelectedName = null;

watch(
  () => [filterStore.selectedUF, mapReady.value, mapData.value],
  async ([uf, isReady]) => {
    if (!isReady) return;
    await nextTick();
    const chart = chartRef.value?.chart;
    if (!chart) return;

    if (_prevSelectedName) {
      chart.dispatchAction({
        type: "unselect",
        seriesIndex: 0,
        name: _prevSelectedName,
      });
      _prevSelectedName = null;
    }

    if (!uf || uf === "Todos") return;
    _prevSelectedName = uf;
    chart.dispatchAction({ type: "select", seriesIndex: 0, name: uf });
  },
  { immediate: true },
);

const onClick = (params) => {
  const name = params.data?.name ?? params.name;
  if (name === filterStore.selectedUF) {
    filterStore.selectedUF = "Todos";
  } else {
    filterStore.selectedUF = name;
  }
};
</script>

<template>
  <div class="chart-section" :class="{ 'is-refreshing': showRefreshing }">
    <div class="chart-header">
      <i class="pi pi-map"></i>
      <h3>MAPA DE RISCO — UFs</h3>
      <div class="spacer"></div>
    </div>
    <div class="chart-wrapper">
      <VChart
        v-if="mapReady"
        ref="chartRef"
        :key="`ud-${mapKey}`"
        class="echart"
        :option="chartOption"
        autoresize
        @click="onClick"
      />
    </div>
  </div>
</template>

<style scoped>
.chart-section {
  display: flex;
  flex-direction: column;
  flex: 1;
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

.chart-wrapper {
  flex: 1;
  min-height: 0;
  padding: 1.5rem;
}

.echart {
  width: 100%;
  height: 100%;
  cursor: pointer;
}

.spacer {
  flex: 1;
}

.is-refreshing {
  opacity: 0.45;
  pointer-events: none;
}
</style>
