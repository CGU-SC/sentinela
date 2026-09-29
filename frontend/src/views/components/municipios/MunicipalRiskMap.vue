<script setup>
import { computed, onMounted, ref, watch } from 'vue';
import { use, registerMap } from 'echarts/core';
import { CanvasRenderer } from 'echarts/renderers';
import { MapChart } from 'echarts/charts';
import { TooltipComponent, VisualMapComponent } from 'echarts/components';
import VChart from 'vue-echarts';
import { useGeoStore } from '@/stores/geo';
import { useThemeStore } from '@/stores/theme';
import { useChartTheme } from '@/config/chartTheme';
import { MAP_VISUAL_SCALE } from '@/config/colors';
import { useFormatting } from '@/composables/useFormatting';
import { buildHealthRegionGeoJson } from '@/utils/geo/municipalTerritory';
import { useStableMapSize } from '@/composables/useStableMapSize';
import MapBackButton from '@/views/components/maps/MapBackButton.vue';

use([CanvasRenderer, MapChart, TooltipComponent, VisualMapComponent]);

const props = defineProps({
  mapData: { type: Array, default: () => [] },
  kpis: { type: Object, default: null },
  activeUf: { type: String, default: 'Todos' },
  isLoading: { type: Boolean, default: false },
  error: { type: String, default: null },
  selectedIbge7: { type: Number, default: null },
  metricMode: { type: String, default: 'audit' },
  metricLabel: { type: String, default: 'Percentual não comprovação' },
  selectedRegiao: { type: String, default: 'Todos' },
  selectedMunicipioNome: { type: String, default: null },
  selectedRegiaoNome: { type: String, default: null },
});

const emit = defineEmits(['select-municipio', 'select-uf', 'back-to-uf', 'clear-geography']);

const geoStore = useGeoStore();
const themeStore = useThemeStore();
const { chartTheme } = useChartTheme();
const { formatBRL, formatNumberFull, formatPercent, formatTitleCase } = useFormatting();

const chartRef = ref(null);
const containerRef = ref(null);
const mapKey = ref(0);
const nationalMapReady = ref(false);
const zoomLevel = ref(1);
const { containerWidth, containerHeight, hasMeasured } = useStableMapSize(containerRef, chartRef);
const regionDataSnapshot = ref(null);

const isNational = computed(() => !props.activeUf || props.activeUf === 'Todos');
const hasRegionScope = computed(
  () => Boolean(props.selectedRegiao && props.selectedRegiao !== 'Todos')
);
const backButtonLabel = computed(() => hasRegionScope.value ? props.activeUf : 'Brasil');
const backButtonTooltip = computed(
  () => hasRegionScope.value
    ? `Voltar ao mapa de ${props.activeUf}`
    : 'Voltar ao mapa do Brasil'
);
const mapScopeLabel = computed(() => {
  if (isNational.value) return 'Brasil';
  const parts = [`UF ${props.activeUf}`];
  if (props.selectedRegiaoNome) parts.push(formatTitleCase(props.selectedRegiaoNome));
  if (props.selectedMunicipioNome) parts.push(formatTitleCase(props.selectedMunicipioNome));
  return parts.join(' › ');
});

function handleBackClick() {
  emit(hasRegionScope.value ? 'back-to-uf' : 'clear-geography');
}
const activeScale = computed(() => MAP_VISUAL_SCALE[themeStore.isDark ? 'dark' : 'light']);
const mapAreaColor = computed(() => themeStore.isDark ? 'rgba(255,255,255,0.07)' : 'rgba(0,0,0,0.04)');
const mapBorderColor = computed(() => themeStore.isDark ? 'rgba(255,255,255,0.16)' : 'rgba(0,0,0,0.14)');

// Legenda flutuante: faixas da escala da maior para a menor.
function pieceLabel(piece) {
  if (piece.min == null) return `< ${piece.max}%`;
  if (piece.max == null) return `≥ ${piece.min}%`;
  return `${piece.min}–${piece.max}%`;
}
const legendPieces = computed(() => [...activeScale.value].reverse().map((piece) => ({
  ...piece,
  label: pieceLabel(piece),
})));
const legendTitle = computed(() => (
  props.metricMode === 'indicator' ? '% farmácias críticas' : '% valor sem comprovação'
));
const hoverBorder = computed(() => `${themeStore.tokens.primary}B3`);

function getRiskPiece(value) {
  return activeScale.value.find((piece) =>
    (piece.min == null || value >= piece.min) &&
    (piece.max == null || value < piece.max)
  ) ?? activeScale.value[activeScale.value.length - 1];
}

function calcPercent(numerator, denominator) {
  if (!denominator || denominator <= 0) return 0;
  return (numerator / denominator) * 100;
}

const totals = computed(() => {
  return props.mapData.reduce((acc, row) => {
    acc.cnpjs += Number(row.cnpjs ?? row.total_cnpjs ?? 0);
    acc.criticos += Number(row.total_critico ?? 0);
    acc.valSemComp += Number(row.valSemComp ?? 0);
    acc.totalMov += Number(row.totalMov ?? 0);
    return acc;
  }, { cnpjs: 0, criticos: 0, valSemComp: 0, totalMov: 0 });
});

const statusKpis = computed(() => props.kpis ?? {});
const statusTotal = computed(() =>
  (statusKpis.value.total_critico ?? 0)
  + (statusKpis.value.total_atencao ?? 0)
  + (statusKpis.value.total_normal ?? 0)
  + (statusKpis.value.total_sem_dados ?? 0)
);

const dataByIbge7 = computed(() => {
  const map = new Map();
  for (const row of props.mapData) {
    if (row.id_ibge7 == null) continue;
    map.set(Number(row.id_ibge7), row);
  }
  return map;
});

const effectiveRegiaoId = computed(() => {
  if (!props.selectedRegiao || props.selectedRegiao === 'Todos') return null;
  return String(props.selectedRegiao);
});

const mapDataByIbge7 = computed(() => {
  if (props.selectedIbge7 != null && regionDataSnapshot.value?.size) {
    return regionDataSnapshot.value;
  }
  return dataByIbge7.value;
});

const dataByUf = computed(() => {
  const map = new Map();
  for (const row of props.mapData) {
    if (!row.uf) continue;
    const uf = row.uf;
    const current = map.get(uf) ?? {
      uf,
      municipios: 0,
      cnpjs: 0,
      criticos: 0,
      valSemComp: 0,
      totalMov: 0,
    };
    current.municipios += 1;
    current.cnpjs += Number(row.cnpjs ?? row.total_cnpjs ?? 0);
    current.criticos += Number(row.total_critico ?? 0);
    current.valSemComp += Number(row.valSemComp ?? 0);
    current.totalMov += Number(row.totalMov ?? 0);
    map.set(uf, current);
  }
  map.forEach((row) => {
    row.value = props.metricMode === 'indicator'
      ? calcPercent(row.criticos, row.cnpjs)
      : calcPercent(row.valSemComp, row.totalMov);
  });
  return map;
});

const effectiveMunicipiosGeo = computed(() => {
  if (isNational.value) return null;
  const geo = geoStore.getMunicipiosGeoByUF(props.activeUf);
  if (!geo) return null;
  if (!effectiveRegiaoId.value) return geo;
  return buildHealthRegionGeoJson({
    ufGeoJson: geo,
    localidades: geoStore.localidades,
    uf: props.activeUf,
    regiaoId: effectiveRegiaoId.value,
  });
});

const mapName = computed(() => {
  if (isNational.value) return 'brasil-uf';
  return effectiveRegiaoId.value
    ? `municipios-risk-regiao-${props.activeUf}-${effectiveRegiaoId.value}`
    : `municipios-risk-${props.activeUf}`;
});

watch(
  [() => props.activeUf, effectiveRegiaoId, effectiveMunicipiosGeo],
  ([uf, _regiaoId, geoJson]) => {
    if (!uf || uf === 'Todos' || !geoJson) {
      mapKey.value += 1;
      return;
    }
    registerMap(mapName.value, geoJson);
    mapKey.value += 1;
  },
  { immediate: true },
);

watch(
  () => [props.activeUf, props.metricMode, props.selectedRegiao],
  () => {
    regionDataSnapshot.value = null;
  },
);

watch(
  dataByIbge7,
  (map) => {
    if (props.selectedIbge7 == null && map.size > 1) {
      regionDataSnapshot.value = new Map(map);
    }
  },
  { immediate: true },
);

watch(
  () => props.selectedIbge7,
  (selected) => {
    if (selected == null) {
      regionDataSnapshot.value = null;
    }
  },
);

onMounted(async () => {
  if (!window.__brasilUfRegistered) {
    const geo = await fetch('/geo/brasil-uf.json').then((response) => response.json());
    registerMap('brasil-uf', geo);
    window.__brasilUfRegistered = true;
  }
  nationalMapReady.value = true;
});

const geoAspectRatio = computed(() => {
  if (isNational.value) return 4500 / 3800;
  const geo = effectiveMunicipiosGeo.value;
  if (!geo?.features?.length) return 1.5;

  let minLon = Infinity;
  let maxLon = -Infinity;
  let minLat = Infinity;
  let maxLat = -Infinity;
  for (const feature of geo.features) {
    const coords = feature.geometry?.coordinates;
    if (!coords) continue;
    const rings = feature.geometry.type === 'MultiPolygon' ? coords.flat(1) : coords;
    for (const ring of rings) {
      for (const [lon, lat] of ring) {
        minLon = Math.min(minLon, lon);
        maxLon = Math.max(maxLon, lon);
        minLat = Math.min(minLat, lat);
        maxLat = Math.max(maxLat, lat);
      }
    }
  }
  const width = maxLon - minLon;
  const height = maxLat - minLat;
  return height > 0 ? width / height : 1.5;
});

const layoutSize = computed(() => {
  const containerAspect = containerWidth.value / containerHeight.value;
  const geoAspect = geoAspectRatio.value;
  if (geoAspect > containerAspect) {
    const factor = containerAspect / geoAspect;
    return `${Math.round((1 / factor) * 96)}%`;
  }
  const roomFactor = Math.max(0, (containerAspect / geoAspect) - 1);
  const fillBoost = Math.min(1.03, 1 + (roomFactor * 0.08));
  return `${Math.round(96 * fillBoost)}%`;
});

const echartsMapData = computed(() => {
  if (isNational.value) {
    return [...dataByUf.value.values()].map((row) => {
      const piece = getRiskPiece(row.value ?? 0);
      return {
        name: row.uf,
        value: row.value,
        municipios: row.municipios,
        cnpjs: row.cnpjs,
        criticos: row.criticos,
        valSemComp: row.valSemComp,
        totalMov: row.totalMov,
        hasData: row.cnpjs > 0,
        itemStyle: { areaColor: row.cnpjs > 0 ? piece.color : mapAreaColor.value },
        emphasis: { itemStyle: { areaColor: piece.color, borderColor: piece.borderColor, borderWidth: 2 } },
      };
    });
  }

  const geo = effectiveMunicipiosGeo.value;
  if (!geo) return [];
  const selected = props.selectedIbge7;

  return geo.features.map((feature) => {
    const ibge7 = Number(feature.properties.id);
    const row = mapDataByIbge7.value.get(ibge7);
    const cnpjs = Number(row?.cnpjs ?? row?.total_cnpjs ?? 0);
    const criticos = Number(row?.total_critico ?? 0);
    const hasData = !!row && cnpjs > 0;
    const value = hasData
      ? (props.metricMode === 'indicator'
          ? Number(row.pct_critico ?? calcPercent(criticos, cnpjs))
          : Number(row.percValSemComp ?? calcPercent(Number(row.valSemComp ?? 0), Number(row.totalMov ?? 0))))
      : 0;
    const piece = getRiskPiece(value);
    const isSelected = selected != null && Number(selected) === ibge7;
    const dimmed = selected != null && !isSelected;

    return {
      name: feature.properties.name,
      ibge7,
      value: hasData ? value : null,
      municipio: row?.municipio ?? feature.properties.name,
      cnpjs,
      criticos,
      valSemComp: Number(row?.valSemComp ?? 0),
      totalMov: Number(row?.totalMov ?? 0),
      hasData,
      itemStyle: {
        areaColor: hasData ? piece.color : mapAreaColor.value,
        opacity: dimmed ? 0.72 : 1,
        borderColor: isSelected ? themeStore.tokens.primary : mapBorderColor.value,
        borderWidth: isSelected ? 2.5 : 0.5,
      },
      emphasis: {
        itemStyle: {
          areaColor: hasData ? piece.color : mapAreaColor.value,
          borderColor: hasData ? piece.borderColor : hoverBorder.value,
          borderWidth: 2,
          opacity: 1,
        },
      },
    };
  });
});

const chartOption = computed(() => {
  const theme = chartTheme.value;
  return {
    backgroundColor: theme.bg,
    tooltip: {
      trigger: 'item',
      confine: true,
      backgroundColor: theme.tooltip,
      borderColor: theme.tooltipBorder,
      borderWidth: 1,
      padding: [12, 16],
      textStyle: { color: theme.tooltipText, fontFamily: 'Inter, sans-serif', fontSize: 12 },
      formatter: (params) => {
        const row = params.data;
        if (!row) return '';
        const label = isNational.value ? row.name : (row.municipio ?? row.name);
        if (!row.hasData) {
          return `
            <div style="color:${theme.tooltipText};min-width:150px">
              <div style="font-weight:600;font-size:13px;margin-bottom:8px;">${label}</div>
              <div style="font-size:11px;opacity:.72;text-transform:uppercase;">Sem estabelecimentos no recorte</div>
            </div>
          `;
        }
        return `
          <div style="color:${theme.tooltipText};min-width:190px">
            <div style="font-weight:600;font-size:13px;margin-bottom:10px;border-bottom:1px solid ${theme.tooltipBorder};padding-bottom:6px;">${label}</div>
            <div style="display:flex;justify-content:space-between;gap:16px;margin-bottom:4px;">
              <span style="opacity:.72;font-size:10px;text-transform:uppercase;">${props.metricMode === 'indicator' ? '% críticas' : '% sem comprovação'}</span>
              <span style="font-weight:600;">${formatPercent(row.value ?? 0)}</span>
            </div>
            ${props.metricMode === 'indicator' ? `
              <div style="display:flex;justify-content:space-between;gap:16px;margin-bottom:4px;">
                <span style="opacity:.72;font-size:10px;text-transform:uppercase;">Críticas</span>
                <span style="font-weight:600;">${formatNumberFull(row.criticos ?? 0)}</span>
              </div>
            ` : ''}
            <div style="display:flex;justify-content:space-between;gap:16px;margin-bottom:4px;">
              <span style="opacity:.72;font-size:10px;text-transform:uppercase;">Valor sem comprovação</span>
              <span style="font-weight:600;">${formatBRL(row.valSemComp ?? 0)}</span>
            </div>
            <div style="display:flex;justify-content:space-between;gap:16px;">
              <span style="opacity:.72;font-size:10px;text-transform:uppercase;">Estabelecimentos</span>
              <span style="font-weight:600;">${formatNumberFull(row.cnpjs ?? 0)}</span>
            </div>
          </div>
        `;
      },
    },
    visualMap: {
      show: false,
      pieces: activeScale.value,
      seriesIndex: 0,
    },
    series: [{
      type: 'map',
      map: mapName.value,
      nameProperty: isNational.value ? 'UF' : 'name',
      roam: 'move',
      zoom: zoomLevel.value,
      scaleLimit: { min: 1, max: 15 },
      layoutCenter: ['50%', '50%'],
      layoutSize: layoutSize.value,
      aspectScale: 1,
      selectedMode: false,
      label: { show: false },
      emphasis: { label: { show: false } },
      itemStyle: { borderColor: mapBorderColor.value, borderWidth: 1, areaColor: mapAreaColor.value },
      data: echartsMapData.value,
    }],
  };
});

function handleZoom(delta) {
  const next = zoomLevel.value + delta;
  if (next < 1 || next > 15) return;
  zoomLevel.value = Number(next.toFixed(1));
}

function onMapClick(params) {
  const row = params?.data;
  if (!row) return;
  if (isNational.value) {
    if (row.name) emit('select-uf', row.name);
    return;
  }
  if (!row.hasData || !row.ibge7) return;
  if (row.ibge7 !== props.selectedIbge7 && dataByIbge7.value.size > 1) {
    regionDataSnapshot.value = new Map(dataByIbge7.value);
  }
  emit('select-municipio', row.ibge7 === props.selectedIbge7 ? null : row.ibge7);
}
</script>

<template>
  <section class="municipal-map-card" :class="{ 'is-refreshing': isLoading }">
    <div class="map-header">
      <i class="pi pi-map" />
      <div class="map-title">
        <h2>Municípios</h2>
        <span v-if="error" class="map-status-error" role="alert">{{ error }}</span>
        <span v-else>
          {{ metricMode === 'indicator' ? '% de farmácias críticas' : '% de valor sem comprovação' }}
          por {{ isNational ? 'UF' : 'município' }} · {{ metricLabel }}
        </span>
      </div>
      <MapBackButton
        v-if="!isNational"
        :label="backButtonLabel"
        :tooltip="backButtonTooltip"
        @click="handleBackClick"
      />
      <div class="map-summary">
        <div v-if="metricMode === 'indicator'" class="summary-item summary-item--critical">
          <span>Críticos</span>
          <div class="summary-inline">
            <strong class="summary-main">{{ formatNumberFull(totals.criticos) }}</strong>
            <small class="summary-sub">
              {{ formatPercent(calcPercent(totals.criticos, totals.cnpjs)) }}
            </small>
          </div>
        </div>
        <div v-if="metricMode === 'indicator'" class="summary-item summary-item--warning">
          <span>Atenção</span>
          <div class="summary-inline">
            <strong class="summary-main">{{ formatNumberFull(statusKpis.total_atencao ?? 0) }}</strong>
            <small class="summary-sub">
              {{ formatPercent(calcPercent(statusKpis.total_atencao ?? 0, statusTotal)) }}
            </small>
          </div>
        </div>
        <div v-else class="summary-item">
          <span>% sem comprovação</span>
          <strong>{{ formatPercent(calcPercent(totals.valSemComp, totals.totalMov)) }}</strong>
        </div>
      </div>
    </div>

    <div v-show="!isNational || nationalMapReady" ref="containerRef" class="map-wrapper">
      <VChart
        v-if="hasMeasured"
        ref="chartRef"
        :key="mapKey"
        class="echart"
        :option="chartOption"
        @click="onMapClick"
      />

      <div
        class="map-scope-badge"
        :aria-label="`Recorte do mapa: ${mapScopeLabel}`"
      >
        <i class="pi pi-map-marker" aria-hidden="true" />
        <span>{{ mapScopeLabel }}</span>
      </div>

      <div class="map-controls">
        <button class="zoom-btn" type="button" @click="handleZoom(0.5)" v-tooltip.bottom="'Aumentar zoom'">
          <i class="pi pi-plus" />
        </button>
        <button class="zoom-btn" type="button" @click="handleZoom(-0.5)" v-tooltip.bottom="'Diminuir zoom'">
          <i class="pi pi-minus" />
        </button>
        <button class="zoom-btn" type="button" @click="zoomLevel = 1" v-tooltip.bottom="'Reiniciar zoom'">
          <i class="pi pi-refresh" />
        </button>
      </div>

      <!-- Legenda flutuante no canto inferior esquerdo: nao ocupa altura do card. -->
      <div class="map-legend" :aria-label="`Escala: ${legendTitle}`">
        <span class="legend-title">{{ legendTitle }}</span>
        <span v-for="piece in legendPieces" :key="piece.label" class="legend-step">
          <i class="legend-swatch" :style="{ backgroundColor: piece.color, borderColor: piece.borderColor }" aria-hidden="true" />
          {{ piece.label }}
        </span>
        <span class="legend-step legend-step--extra">
          <i class="legend-swatch" :style="{ backgroundColor: mapAreaColor, borderColor: mapBorderColor }" aria-hidden="true" />
          Sem dados
        </span>
      </div>
    </div>

    <div v-show="isNational && !nationalMapReady" class="map-loading">
      <i class="pi pi-spin pi-spinner" />
    </div>
  </section>
</template>

<style scoped>
.municipal-map-card {
  background: var(--card-bg);
  border: 1px solid var(--card-border);
  border-radius: 12px;
  height: calc(40vh + 42px);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.municipal-map-card.is-refreshing {
  pointer-events: none;
}

.map-status-error {
  color: var(--risk-indicator-critical);
}

.map-header {
  --map-header-item-height: 2.75rem;
  display: flex;
  align-items: center;
  gap: 0.8rem;
  padding: 0.8rem 1.15rem;
  border-bottom: 1px solid var(--tabs-border);
  flex-shrink: 0;
}

.map-header :deep(.map-back-button) {
  height: var(--map-header-item-height);
  flex-shrink: 0;
}

.map-header > i {
  color: var(--primary-color);
  font-size: 1rem;
  flex-shrink: 0;
}

.map-title {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 0.1rem;
}

.map-title h2 {
  margin: 0;
  font-size: 0.82rem;
  font-weight: 600;
  line-height: 1.1;
  color: var(--text-color-85);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.map-title span {
  font-size: 0.68rem;
  color: var(--text-muted);
}

.map-title .map-scope {
  color: var(--text-color-85);
  font-size: 0.72rem;
  font-weight: 500;
}

.map-summary {
  margin-left: auto;
  display: flex;
  align-items: center;
  gap: 0.65rem;
}

.summary-item {
  box-sizing: border-box;
  height: var(--map-header-item-height);
  min-width: 104px;
  display: flex;
  flex-direction: column;
  justify-content: center;
  padding: 0 0.62rem;
  border: 1px solid color-mix(in srgb, var(--card-border) 82%, transparent);
  border-radius: 8px;
  background: color-mix(in srgb, var(--card-bg) 86%, transparent);
}

.summary-item--critical {
  width: 120px;
  border-color: color-mix(in srgb, var(--risk-critical) 34%, var(--card-border));
  background:
    linear-gradient(
      135deg,
      color-mix(in srgb, var(--risk-critical) 13%, var(--card-bg)),
      color-mix(in srgb, var(--card-bg) 92%, transparent)
    );
}

.summary-item span {
  display: block;
  margin-bottom: 0.2rem;
  font-size: 0.62rem;
  color: var(--text-muted);
}

.summary-item strong {
  display: block;
  font-size: 0.82rem;
  font-weight: 600;
  color: var(--text-color-85);
  line-height: 1;
}

.summary-item--critical .summary-main {
  color: var(--risk-critical);
}

.summary-item--warning {
  width: 120px;
  border-color: color-mix(in srgb, var(--risk-indicator-warning) 34%, var(--card-border));
  background:
    linear-gradient(
      135deg,
      color-mix(in srgb, var(--risk-indicator-warning) 13%, var(--card-bg)),
      color-mix(in srgb, var(--card-bg) 92%, transparent)
    );
}

.summary-item--warning .summary-main {
  color: var(--risk-indicator-warning);
}

.summary-inline {
  display: flex;
  align-items: baseline;
  gap: 0.45rem;
}

.summary-sub {
  font-size: 0.75rem;
  font-weight: 500;
  line-height: 1;
  color: color-mix(in srgb, var(--text-muted) 78%, var(--text-color-85));
}

.summary-item--critical .summary-sub {
  color: color-mix(in srgb, var(--risk-critical) 78%, var(--text-muted));
}

.summary-item--warning .summary-sub {
  color: color-mix(in srgb, var(--risk-indicator-warning) 78%, var(--text-muted));
}

.map-wrapper {
  position: relative;
  flex: 1;
  min-height: 0;
}

.echart {
  width: 100%;
  height: 100%;
}

.map-scope-badge {
  position: absolute;
  top: 0.75rem;
  right: 0.75rem;
  z-index: 1;
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
  max-width: min(55%, 24rem);
  padding: 0.4rem 0.6rem;
  border: 1px solid var(--card-border);
  border-radius: 8px;
  background: color-mix(in srgb, var(--card-bg) 92%, transparent);
  color: var(--text-secondary);
  font-size: 0.75rem;
  line-height: 1.25;
  backdrop-filter: blur(4px);
  -webkit-backdrop-filter: blur(4px);
}

.map-scope-badge i {
  flex: none;
  color: var(--primary-color);
  font-size: 0.7rem;
}

.map-scope-badge span {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.map-loading {
  flex: 1;
  min-height: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--text-muted);
  font-size: 1.4rem;
}

.map-legend {
  position: absolute;
  left: 0.75rem;
  top: 0.75rem;
  display: flex;
  flex-direction: column;
  gap: 0.12rem;
  padding: 0.45rem 0.6rem;
  border: 1px solid var(--card-border);
  border-radius: 8px;
  background: color-mix(in srgb, var(--card-bg) 88%, transparent);
  backdrop-filter: blur(4px);
  -webkit-backdrop-filter: blur(4px);
  color: var(--text-color-70);
  font-size: 0.6rem;
  line-height: 1.25;
  pointer-events: none;
}

.legend-title {
  margin-bottom: 0.12rem;
  color: var(--text-muted);
  white-space: nowrap;
}

.legend-step {
  display: flex;
  align-items: center;
  gap: 0.35rem;
  white-space: nowrap;
}

.legend-step--extra {
  margin-top: 0.2rem;
  padding-top: 0.3rem;
  border-top: 1px solid var(--tabs-border);
}

.legend-swatch {
  display: inline-block;
  width: 0.68rem;
  height: 0.68rem;
  flex-shrink: 0;
  border: 1px solid;
  border-radius: 2px;
}

.map-controls {
  position: absolute;
  right: 1rem;
  bottom: 1rem;
  display: flex;
  flex-direction: column;
  gap: 0.45rem;
}

.zoom-btn {
  width: 32px;
  height: 32px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border: 1px solid var(--card-border);
  border-radius: 8px;
  background: color-mix(in srgb, var(--card-bg) 88%, transparent);
  color: var(--text-color-85);
  cursor: pointer;
  backdrop-filter: blur(8px);
  -webkit-backdrop-filter: blur(8px);
  transition: border-color 0.16s ease, color 0.16s ease, transform 0.16s ease;
}

.zoom-btn:hover {
  border-color: var(--primary-color);
  color: var(--primary-color);
  transform: translateY(-1px);
}

.zoom-btn i {
  font-size: 0.72rem;
}
</style>
