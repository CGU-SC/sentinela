<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue';
import { use } from 'echarts/core';
import { CanvasRenderer } from 'echarts/renderers';
import { MapChart } from 'echarts/charts';
import { TooltipComponent, VisualMapComponent } from 'echarts/components';
import VChart from 'vue-echarts';
import { registerMap } from 'echarts/core';
import { useGeoStore } from '@/stores/geo';
import { useThemeStore } from '@/stores/theme';
import { useChartTheme } from '@/config/chartTheme';
import { CRM_PRESCRICOES_SCALE } from '@/config/colors';

use([CanvasRenderer, MapChart, TooltipComponent, VisualMapComponent]);

const props = defineProps({
  mapLevel: { type: String, required: true },
  mapData: { type: Array, default: () => [] },
  uf: { type: String, default: null },
  regiaoId: { type: [String, Number], default: null },
  escopo: { type: String, default: 'Brasil' },
  qtdMedicos: { type: Number, default: 0 },
  isLoading: { type: Boolean, default: false },
  error: { type: String, default: null },
});

const emit = defineEmits(['select-uf', 'select-municipio', 'back']);
const geoStore = useGeoStore();
const themeStore = useThemeStore();
const { chartTheme } = useChartTheme();

const chartRef = ref(null);
const containerRef = ref(null);
const nationalMapReady = ref(false);
const mapKey = ref(0);
const zoomLevel = ref(1);
const containerWidth = ref(800);
const containerHeight = ref(400);
let resizeObserver = null;

const isNational = computed(() => props.mapLevel === 'uf');
const mapTitle = computed(() => isNational.value ? 'Brasil' : props.mapLevel === 'regiao' ? 'Região de Saúde' : `Municípios de ${props.uf}`);
const mapSubtitle = computed(() => `Percentual mensal de CRM-meses acima de 22 prescrições/dia · ${props.escopo}`);
const backLabel = computed(() => props.mapLevel === 'regiao' ? `Voltar à UF ${props.uf}` : 'Voltar ao Brasil');
const activeScale = computed(() => CRM_PRESCRICOES_SCALE[themeStore.isDark ? 'dark' : 'light']);
const mapAreaColor = computed(() => themeStore.isDark ? 'rgba(255,255,255,0.07)' : 'rgba(0,0,0,0.04)');
const mapBorderColor = computed(() => themeStore.isDark ? 'rgba(255,255,255,0.15)' : 'rgba(0,0,0,0.15)');
const hoverBorder = computed(() => themeStore.tokens.primary);

const currentGeo = computed(() => {
  if (isNational.value || !props.uf) return null;
  const base = geoStore.getMunicipiosGeoByUF(props.uf);
  if (!base) return null;
  if (props.mapLevel !== 'regiao' || props.regiaoId == null) return base;
  const ids = new Set(
    geoStore.localidades
      .filter((item) => String(item.id_regiao_saude) === String(props.regiaoId))
      .map((item) => Number(item.id_ibge7))
  );
  return {
    type: 'FeatureCollection',
    features: base.features.filter((feature) => ids.has(Number(feature.properties?.id))),
  };
});

const mapName = computed(() => {
  if (isNational.value) return 'crm-brasil-uf';
  if (props.mapLevel === 'regiao') return `crm-regiao-${props.regiaoId}`;
  return `crm-municipios-${props.uf}`;
});

const dataByMunicipio = computed(() => new Map(
  props.mapData
    .filter((row) => row.id_ibge7 != null)
    .map((row) => [Number(row.id_ibge7), row])
));

const maxPercentualAnomalia = computed(() => Math.max(
  1,
  ...props.mapData.map((row) => Number(row.percentual_crms_anomalos) || 0),
));
const maximumObservedPercentual = computed(() => Math.max(
  0,
  ...props.mapData.map((row) => Number(row.percentual_crms_anomalos) || 0),
));

const mapSeriesData = computed(() => {
  if (isNational.value) {
    return props.mapData.map((row) => ({
      name: row.nome,
      value: row.percentual_crms_anomalos == null ? null : Number(row.percentual_crms_anomalos),
      row,
      itemStyle: { borderColor: mapBorderColor.value, borderWidth: 1 },
    }));
  }
  if (!currentGeo.value) return [];
  return currentGeo.value.features.map((feature) => {
    const idIbge7 = Number(feature.properties?.id);
    const row = dataByMunicipio.value.get(idIbge7);
    return {
      name: feature.properties?.name,
      value: row && row.percentual_crms_anomalos != null ? Number(row.percentual_crms_anomalos) : null,
      idIbge7,
      row,
      itemStyle: {
        areaColor: row ? undefined : mapAreaColor.value,
        borderColor: mapBorderColor.value,
        borderWidth: 0.7,
      },
    };
  });
});

const geoAspectRatio = computed(() => {
  if (isNational.value) return 4500 / 3800;
  const features = currentGeo.value?.features ?? [];
  let minLon = Infinity;
  let maxLon = -Infinity;
  let minLat = Infinity;
  let maxLat = -Infinity;
  for (const feature of features) {
    const coordinates = feature.geometry?.coordinates;
    if (!coordinates) continue;
    const rings = feature.geometry.type === 'MultiPolygon' ? coordinates.flat(1) : coordinates;
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
  if (geoAspectRatio.value > containerAspect) {
    return `${Math.round((containerAspect / geoAspectRatio.value) ** -1 * 96)}%`;
  }
  return '96%';
});

const chartOption = computed(() => {
  const c = chartTheme.value;
  return {
    backgroundColor: c.bg,
    tooltip: {
      trigger: 'item',
      confine: true,
      backgroundColor: c.tooltip,
      borderColor: c.tooltipBorder,
      borderWidth: 1,
      padding: [12, 16],
      textStyle: { color: c.tooltipText, fontFamily: 'Inter, sans-serif', fontSize: 12 },
      formatter: (params) => {
        const row = params.data?.row;
        const label = row?.nome ?? params.name ?? '—';
        if (!row) {
          return `<div style="min-width: 150px; color: ${c.tooltipText}"><strong>${label}</strong><div style="margin-top: 8px; opacity: .7">Sem dados no escopo atual</div></div>`;
        }
        return `<div style="min-width: 210px; color: ${c.tooltipText}">
          <div style="font-weight: 600; margin-bottom: 9px; border-bottom: 1px solid ${c.tooltipBorder}; padding-bottom: 7px">${label}</div>
          <div style="display:flex; justify-content:space-between; gap:20px; margin:4px 0"><span style="opacity:.72">CRMs anômalos</span><strong>${row.percentual_crms_anomalos == null ? '—' : `${Number(row.percentual_crms_anomalos).toFixed(2).replace('.', ',')}%`}</strong></div>
          <div style="display:flex; justify-content:space-between; gap:20px; margin:4px 0"><span style="opacity:.72">CRM-meses anômalos / ativos</span><span>${row.qtd_crms_anomalos} / ${row.qtd_crms_ativos}</span></div>
          <div style="display:flex; justify-content:space-between; gap:20px; margin:4px 0"><span style="opacity:.72">Prescrições</span><span>${Number(row.nu_prescricoes_total).toLocaleString('pt-BR')}</span></div>
          <div style="display:flex; justify-content:space-between; gap:20px; margin:4px 0"><span style="opacity:.72">Média por dia</span><span>${row.media_prescricoes_dia == null ? '—' : Number(row.media_prescricoes_dia).toFixed(2).replace('.', ',')}</span></div>
        </div>`;
      },
    },
    visualMap: {
      show: false,
      min: 0,
      max: maxPercentualAnomalia.value,
      inRange: { color: activeScale.value },
      outOfRange: { color: [mapAreaColor.value] },
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
      selectedMode: false,
      label: { show: false },
      emphasis: {
        label: { show: false },
        itemStyle: { borderColor: hoverBorder.value, borderWidth: 2 },
      },
      itemStyle: { borderColor: mapBorderColor.value, borderWidth: 1, areaColor: mapAreaColor.value },
      data: mapSeriesData.value,
    }],
  };
});

function handleZoom(delta) {
  zoomLevel.value = Math.max(1, Math.min(15, Number((zoomLevel.value + delta).toFixed(1))));
}

function onMapClick(params) {
  const row = params?.data?.row;
  if (isNational.value && row) emit('select-uf', row.uf);
  else if (params?.data?.idIbge7) emit('select-municipio', params.data.idIbge7);
}

async function registerActiveMap() {
  if (isNational.value) {
    if (!window.__crmBrasilUfRegistered) {
      const response = await fetch('/geo/brasil-uf.json');
      if (!response.ok) throw new Error('GeoJSON nacional indisponível.');
      registerMap('crm-brasil-uf', await response.json());
      window.__crmBrasilUfRegistered = true;
    }
  } else if (currentGeo.value) {
    registerMap(mapName.value, currentGeo.value);
  }
  mapKey.value += 1;
  await nextTick();
  chartRef.value?.chart?.resize();
}

onMounted(async () => {
  try {
    await registerActiveMap();
    nationalMapReady.value = true;
  } catch (error) {
    console.error('[CRM map] GeoJSON indisponível:', error);
  }
  if (containerRef.value) {
    resizeObserver = new ResizeObserver(([entry]) => {
      containerWidth.value = entry.contentRect.width;
      containerHeight.value = entry.contentRect.height;
    });
    resizeObserver.observe(containerRef.value);
  }
});

watch(
  () => [props.mapLevel, props.uf, props.regiaoId, props.mapData, themeStore.isDark],
  () => registerActiveMap().catch((error) => console.error('[CRM map] GeoJSON indisponível:', error)),
  { deep: true },
);

onBeforeUnmount(() => resizeObserver?.disconnect());
</script>

<template>
  <section class="crm-map-card" :class="{ 'is-refreshing': isLoading }">
    <header class="crm-map-header">
      <i class="pi pi-map" />
      <div class="crm-map-heading">
        <h2>CRMs com taxa diária anômala</h2>
        <span>{{ mapTitle }} · {{ mapSubtitle }}</span>
      </div>
      <button v-if="!isNational" type="button" class="map-back-button" @click="emit('back')">
        <i class="pi pi-arrow-left" />
        <span>{{ backLabel }}</span>
      </button>
      <div class="crm-map-summary">
        <div class="map-summary-item">
          <span>Médicos no escopo</span>
          <strong>{{ qtdMedicos.toLocaleString('pt-BR') }}</strong>
        </div>
        <div class="map-summary-item map-summary-item--accent">
          <span>Critério de cor</span>
          <strong>% anômalo</strong>
        </div>
      </div>
    </header>

    <div ref="containerRef" class="crm-map-wrapper">
      <div v-if="error && !isLoading" class="map-error-state">
        <div class="map-error-icon"><i class="pi pi-database" /></div>
        <div class="map-error-copy">
          <h3>Mapa indisponível no momento</h3>
          <p>{{ error }}</p>
          <span>Após a sincronização, recarregue esta tela para visualizar o mapa e os indicadores.</span>
        </div>
      </div>
      <div v-else-if="isNational && !nationalMapReady" class="map-loading">
        <i class="pi pi-spin pi-spinner" />
      </div>
      <template v-else>
        <VChart ref="chartRef" :key="mapKey" class="crm-echart" :option="chartOption" autoresize @click="onMapClick" />
        <div class="map-controls">
          <button type="button" class="zoom-btn" @click="handleZoom(0.5)" v-tooltip.bottom="'Aumentar zoom'"><i class="pi pi-plus" /></button>
          <button type="button" class="zoom-btn" @click="handleZoom(-0.5)" v-tooltip.bottom="'Diminuir zoom'"><i class="pi pi-minus" /></button>
          <button type="button" class="zoom-btn" @click="zoomLevel = 1" v-tooltip.bottom="'Reiniciar zoom'"><i class="pi pi-refresh" /></button>
        </div>
      </template>
    </div>
    <footer v-if="error && !isLoading" class="map-legend map-legend--unavailable">
      <span>Escala de cores e percentual de CRMs anômalos serão exibidos após a sincronização dos dados.</span>
    </footer>
    <footer v-else class="map-legend">
      <span class="legend-title">Cor: percentual mensal de CRM-meses anômalos</span>
      <div class="legend-scale" aria-label="Escala de menor para maior percentual mensal de CRM-meses anômalos">
        <span>Menor</span>
        <i v-for="color in activeScale" :key="color" class="legend-swatch" :style="{ backgroundColor: color }" />
        <span>Maior{{ maximumObservedPercentual ? ` · ${maximumObservedPercentual.toFixed(2).replace('.', ',')}%` : '' }}</span>
      </div>
    </footer>
  </section>
</template>

<style scoped>
.crm-map-card {
  background: var(--card-bg);
  border: 1px solid var(--card-border);
  border-radius: 12px;
  height: calc(40vh + 42px);
  min-height: 390px;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  transition: opacity .25s ease;
}

.crm-map-card.is-refreshing { opacity: .58; pointer-events: none; }
.crm-map-header { display: flex; align-items: center; gap: .8rem; padding: .8rem 1.15rem; border-bottom: 1px solid var(--tabs-border); flex-shrink: 0; }
.crm-map-header > i { color: var(--primary-color); font-size: 1rem; }
.crm-map-heading { min-width: 0; display: flex; flex-direction: column; gap: .15rem; }
.crm-map-heading h2 { margin: 0; color: var(--text-color-85); font-size: .84rem; font-weight: 600; letter-spacing: .02em; }
.crm-map-heading span { color: var(--text-muted); font-size: .68rem; }
.map-back-button { height: 2rem; padding: 0 .65rem; display: inline-flex; align-items: center; gap: .4rem; border: 1px solid var(--card-border); border-radius: 6px; background: var(--card-bg); color: var(--text-muted); cursor: pointer; }
.map-back-button:hover, .map-back-button:focus-visible { color: var(--primary-color); border-color: var(--primary-color); }
.map-back-button:focus-visible, .zoom-btn:focus-visible { outline: 1px solid var(--primary-color); outline-offset: 2px; }
.crm-map-summary { margin-left: auto; display: flex; gap: .65rem; }
.map-summary-item { min-width: 112px; padding: .45rem .62rem; border: 1px solid var(--card-border); border-radius: 8px; background: color-mix(in srgb, var(--card-bg) 90%, var(--primary-color) 10%); }
.map-summary-item span { display: block; color: var(--text-muted); font-size: .6rem; margin-bottom: .2rem; }
.map-summary-item strong { color: var(--text-color-85); font-size: .82rem; font-weight: 600; }
.map-summary-item--accent strong { color: var(--primary-color); }
.crm-map-wrapper { position: relative; flex: 1; min-height: 0; }
.crm-echart { width: 100%; height: 100%; }
.map-loading { height: 100%; display: grid; place-items: center; color: var(--primary-color); font-size: 1.5rem; }
.map-error-state { height: 100%; display: flex; align-items: center; justify-content: center; gap: 1rem; padding: 2rem; }
.map-error-icon { width: 3.5rem; height: 3.5rem; display: grid; place-items: center; flex: 0 0 auto; border: 1px solid color-mix(in srgb, var(--risk-high) 35%, var(--card-border)); border-radius: 50%; background: color-mix(in srgb, var(--risk-high) 9%, var(--card-bg)); color: var(--risk-high); font-size: 1.35rem; }
.map-error-copy { max-width: 520px; }
.map-error-copy h3 { margin: 0; color: var(--text-color-85); font-size: .92rem; font-weight: 600; }
.map-error-copy p { margin: .4rem 0 0; color: var(--text-muted); font-size: .76rem; line-height: 1.5; }
.map-error-copy span { display: block; margin-top: .55rem; color: var(--text-color-70); font-size: .68rem; line-height: 1.45; }
.map-legend { display: flex; align-items: center; justify-content: flex-end; gap: .75rem; min-height: 2rem; padding: 0 1.15rem; border-top: 1px solid var(--tabs-border); color: var(--text-muted); font-size: .64rem; }
.map-legend--unavailable { justify-content: flex-start; }
.legend-title { margin-right: auto; }
.legend-scale { display: inline-flex; align-items: center; gap: .3rem; }
.legend-swatch { width: .85rem; height: .55rem; border-radius: 2px; }
.map-controls { position: absolute; right: 1rem; bottom: 1rem; display: flex; flex-direction: column; gap: .45rem; }
.zoom-btn { width: 2rem; height: 2rem; border: 1px solid var(--card-border); border-radius: 7px; background: color-mix(in srgb, var(--card-bg) 90%, transparent); color: var(--text-muted); cursor: pointer; }
.zoom-btn:hover { color: var(--primary-color); border-color: var(--primary-color); }
</style>
