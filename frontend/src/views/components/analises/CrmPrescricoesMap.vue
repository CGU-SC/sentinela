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
import { CRM_INTENSIDADE_INDICE_SCALE } from '@/config/colors';
import { analysisTooltip } from '@/config/analysisTooltipConfig';

use([CanvasRenderer, MapChart, TooltipComponent, VisualMapComponent]);

const props = defineProps({
  mapLevel: { type: String, required: true },
  mapData: { type: Array, default: () => [] },
  uf: { type: String, default: null },
  regiaoId: { type: [String, Number], default: null },
  selectedIbge7: { type: [String, Number], default: null },
  escopo: { type: String, default: 'Brasil' },
  qtdMedicos: { type: Number, default: 0 },
  // Resposta do mapa: referencias (% Brasil/UF), faixa do corte P95 e minimo da amostra.
  mapMeta: { type: Object, default: null },
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

// Referencia da cor. No mapa nacional so existe Brasil (media das UFs); no
// municipal, a media dos municipios do Brasil, da UF ou da propria regiao.
const comparacao = ref('brasil');
const comparacaoAtiva = computed(() => isNational.value ? 'brasil' : comparacao.value);
const INDICE_POR_COMPARACAO = { brasil: 'indice_brasil', uf: 'indice_uf', regiao: 'indice_regiao' };
const opcoesComparacao = computed(() => [
  { value: 'brasil', label: 'Brasil', tooltip: 'Cor pela média dos municípios do Brasil' },
  { value: 'uf', label: props.uf ?? 'UF', tooltip: `Cor pela média dos municípios de ${props.uf ?? 'UF'}` },
  { value: 'regiao', label: 'Região', tooltip: 'Cor pela média dos municípios da região de saúde de cada município' },
]);
const referenciaTexto = computed(() => {
  if (isNational.value) return 'média das UFs';
  if (comparacaoAtiva.value === 'uf') return `média dos municípios de ${props.uf}`;
  if (comparacaoAtiva.value === 'regiao') return 'média dos municípios da própria região de saúde';
  return 'média dos municípios do Brasil';
});
const legendTitle = computed(() => {
  if (comparacaoAtiva.value === 'uf') return `vs. média ${props.uf}`;
  if (comparacaoAtiva.value === 'regiao') return 'vs. média da região';
  return 'vs. média Brasil';
});

function indiceAtivo(row) {
  const valor = row?.[INDICE_POR_COMPARACAO[comparacaoAtiva.value]];
  return valor == null ? null : Number(valor);
}

const mapTitle = computed(() => isNational.value ? 'Brasil' : props.mapLevel === 'regiao' ? 'Região de Saúde' : `Municípios de ${props.uf}`);
// Subtitulo curto: a explicacao completa fica no tooltip do titulo.
const mapSubtitle = computed(() => {
  const partes = [mapTitle.value, `comparado à ${referenciaTexto.value}`];
  if (props.mapLevel === 'regiao' && props.escopo) partes.push(props.escopo);
  return partes.join(' · ');
});
const mapInfoTooltip = computed(() => {
  const referencia = referenciaTexto.value;
  const extraSections = [{
    label: 'Referência atual',
    text: `${referencia.charAt(0).toUpperCase()}${referencia.slice(1)}.`,
  }];
  if (!isNational.value) {
    extraSections.push({
      label: 'Amostra pequena',
      text: `Municípios com menos de ${minAmostra.value ?? 20} médicos ativos no período ficam hachurados, sem cor de risco.`,
    });
  }
  return analysisTooltip('crmMap', { extraSections });
});
const backLabel = computed(() => props.mapLevel === 'regiao' ? `Voltar à UF ${props.uf}` : 'Voltar ao Brasil');
const activeScale = computed(() => CRM_INTENSIDADE_INDICE_SCALE[themeStore.isDark ? 'dark' : 'light']);
const hatchColor = computed(() => themeStore.isDark ? 'rgba(255,255,255,0.22)' : 'rgba(15,23,42,0.22)');
const smallSampleDecal = computed(() => ({
  symbol: 'rect',
  symbolSize: 1,
  color: hatchColor.value,
  dashArrayX: [1, 0],
  dashArrayY: [2, 4],
  rotation: -Math.PI / 4,
}));

function formatPct(value) {
  return value == null ? '—' : `${Number(value).toFixed(1).replace('.', ',')}%`;
}

function formatIndice(value) {
  return value == null ? '—' : `${Number(value).toFixed(2).replace('.', ',')}×`;
}

const minAmostra = computed(() => props.mapMeta?.min_medicos_amostra_municipio ?? null);
// Cartao de resumo: percentual de referencia da comparacao ativa. Com "Regiao"
// no mapa da UF cada municipio usa a sua regiao, entao nao ha um numero unico.
const referenciaResumo = computed(() => {
  const meta = props.mapMeta ?? {};
  if (comparacaoAtiva.value === 'uf') {
    return { label: `Média ${props.uf}`, valor: formatPct(meta.percentual_referencia_uf) };
  }
  if (comparacaoAtiva.value === 'regiao') {
    return props.mapLevel === 'regiao'
      ? { label: 'Média da região', valor: formatPct(meta.percentual_referencia_regiao) }
      : { label: 'Média da região', valor: 'Por região' };
  }
  return { label: 'Média Brasil', valor: formatPct(meta.percentual_referencia_brasil) };
});
const referenciaTooltip = computed(() => (isNational.value
  ? 'Soma dos médicos de alta intensidade ÷ soma dos médicos ativos das 27 UFs. Um médico conta em cada UF onde prescreveu, por isso a referência soma as UFs em vez de contar cada médico uma vez no país.'
  : 'Soma dos médicos de alta intensidade ÷ soma dos médicos ativos dos municípios de referência. Um médico conta em cada município onde prescreveu, por isso a referência soma os municípios.'));

// Classificacao visual do territorio: sem medicos, amostra pequena ou faixa do indice.
function territoryVisual(row) {
  const ativos = Number(row?.qtd_medicos_ativos ?? 0);
  if (!row || ativos === 0) return { kind: 'vazio', piece: null };
  if (row.amostra_pequena) return { kind: 'pequena', piece: null };
  const indice = indiceAtivo(row);
  if (indice == null) return { kind: 'vazio', piece: null };
  return { kind: 'dados', piece: getRiskPiece(indice) };
}
const mapAreaColor = computed(() => themeStore.isDark ? 'rgba(255,255,255,0.07)' : 'rgba(0,0,0,0.04)');
const mapBorderColor = computed(() => themeStore.isDark ? 'rgba(255,255,255,0.15)' : 'rgba(0,0,0,0.15)');
const hoverBorder = computed(() => `${themeStore.tokens.primary}B3`);

function getRiskPiece(perc) {
  return activeScale.value.find((piece) => (
    (piece.value == null || perc === piece.value)
    && (piece.min == null || perc >= piece.min)
    && (piece.max == null || perc < piece.max)
    && (piece.gt == null || perc > piece.gt)
    && (piece.gte == null || perc >= piece.gte)
    && (piece.lt == null || perc < piece.lt)
  )) ?? activeScale.value[activeScale.value.length - 1];
}

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
  if (isNational.value) return 'brasil-uf';
  if (props.mapLevel === 'regiao') return `regiao-filter-${props.regiaoId}`;
  return `municipios-${props.uf}`;
});

const dataByMunicipio = computed(() => new Map(
  props.mapData
    .filter((row) => row.id_ibge7 != null)
    .map((row) => [Number(row.id_ibge7), row])
));

const mapSeriesData = computed(() => {
  if (isNational.value) {
    return props.mapData.map((row) => {
      const { kind, piece } = territoryVisual(row);
      const areaColor = kind === 'dados' ? piece.color : mapAreaColor.value;
      return {
        name: row.nome,
        value: kind === 'dados' ? indiceAtivo(row) : null,
        row,
        itemStyle: {
          areaColor,
          borderColor: mapBorderColor.value,
          borderWidth: 0.5,
        },
        emphasis: {
          itemStyle: {
            areaColor,
            borderColor: kind === 'dados' ? piece.borderColor : hoverBorder.value,
            borderWidth: 2,
          },
        },
      };
    });
  }
  if (!currentGeo.value) return [];
  return currentGeo.value.features.map((feature) => {
    const idIbge7 = Number(feature.properties?.id);
    const row = dataByMunicipio.value.get(idIbge7);
    const selectedId = props.selectedIbge7 == null ? null : Number(props.selectedIbge7);
    const isSelected = selectedId != null && idIbge7 === selectedId;
    const hasSelected = selectedId != null;
    const { kind, piece } = territoryVisual(row);
    const baseColor = kind === 'dados' ? piece.color : mapAreaColor.value;
    const decal = kind === 'pequena' ? smallSampleDecal.value : undefined;
    return {
      name: feature.properties?.name,
      value: kind === 'dados' ? indiceAtivo(row) : null,
      idIbge7,
      row,
      itemStyle: {
        areaColor: baseColor,
        decal,
        opacity: hasSelected && !isSelected ? 0.8 : 1,
        borderColor: isSelected ? themeStore.tokens.primary : mapBorderColor.value,
        borderWidth: isSelected ? 2.5 : 0.5,
      },
      emphasis: {
        itemStyle: {
          areaColor: baseColor,
          decal,
          borderColor: kind === 'dados' ? piece.borderColor : hoverBorder.value,
          borderWidth: 2,
          opacity: 1,
        },
      },
    };
  });
});

const geoAspectRatio = computed(() => {
  if (isNational.value) return 4500 / 3800;
  const geo = geoStore.getMunicipiosGeoByUF(props.uf);
  if (!geo || !geo.features.length) return 1.5;
  const features = geo.features;
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

const optimalLayoutSize = computed(() => {
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
        const linha = (rotulo, valor) => `<div style="display:flex; justify-content:space-between; gap:20px; margin:4px 0"><span style="opacity:.72">${rotulo}</span><span>${valor}</span></div>`;
        const ativos = Number(row.qtd_medicos_ativos).toLocaleString('pt-BR');
        const alta = Number(row.qtd_medicos_alta_intensidade).toLocaleString('pt-BR');
        const comparacaoLinha = (chave, rotulo) => {
          const valor = formatIndice(row[INDICE_POR_COMPARACAO[chave]]);
          return comparacaoAtiva.value === chave
            ? linha(`<strong>${rotulo}</strong>`, `<strong>${valor}</strong>`)
            : linha(rotulo, valor);
        };
        const comparacoes = row.nivel === 'municipio'
          ? [
            comparacaoLinha('regiao', `vs. média da região${row.no_regiao_saude ? ` (${row.no_regiao_saude})` : ''}`),
            comparacaoLinha('uf', `vs. média ${row.uf}`),
            comparacaoLinha('brasil', 'vs. média Brasil'),
          ].join('')
          : comparacaoLinha('brasil', 'vs. média das UFs');
        const aviso = row.amostra_pequena && Number(row.qtd_medicos_ativos) > 0
          ? `<div style="margin-top:8px; opacity:.72">Amostra pequena: menos de ${minAmostra.value} médicos no período (sem cor de risco).</div>`
          : '';
        return `<div style="min-width: 230px; color: ${c.tooltipText}">
          <div style="font-weight: 600; margin-bottom: 9px; border-bottom: 1px solid ${c.tooltipBorder}; padding-bottom: 7px">${label}</div>
          ${linha('Alta intensidade', `<strong>${formatPct(row.percentual_alta_intensidade)}</strong>`)}
          ${linha('Médicos', `${alta} de ${ativos}`)}
          ${comparacoes}
          ${aviso}
        </div>`;
      },
    },
    // Mesmo esquema de /estabelecimentos: visualMap oculto com as faixas do indice,
    // para o ECharts animar a troca de cor quando o periodo muda. Territorios sem
    // indice (sem medicos ou amostra pequena) ficam com value null e cor propria.
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
      layoutSize: optimalLayoutSize.value,
      aspectScale: 1,
      selectedMode: false,
      label: { show: false },
      emphasis: { label: { show: false } },
      itemStyle: { borderColor: mapBorderColor.value, borderWidth: 2, areaColor: mapAreaColor.value },
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
  else if (params?.data?.idIbge7) {
    const idIbge7 = Number(params.data.idIbge7);
    const selectedId = props.selectedIbge7 == null ? null : Number(props.selectedIbge7);
    emit('select-municipio', idIbge7 === selectedId ? null : idIbge7);
  }
}

async function registerActiveMap() {
  if (isNational.value) {
    if (!window.__brasilUfRegistered) {
      const response = await fetch('/geo/brasil-uf.json');
      if (!response.ok) throw new Error('GeoJSON nacional indisponível.');
      registerMap('brasil-uf', await response.json());
      window.__brasilUfRegistered = true;
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
    containerWidth.value = containerRef.value.clientWidth;
    containerHeight.value = containerRef.value.clientHeight;
  }
  await nextTick();
  chartRef.value?.chart?.resize();
  mapKey.value += 1;
});

watch(
  () => [props.mapLevel, props.uf, props.regiaoId, geoStore.municipiosGeoJson],
  () => registerActiveMap().catch((error) => console.error('[CRM map] GeoJSON indisponível:', error)),
  { deep: true },
);

watch(() => themeStore.isDark, () => mapKey.value++);

onBeforeUnmount(() => resizeObserver?.disconnect());
</script>

<template>
  <section class="crm-map-card" :class="{ 'is-refreshing': isLoading }">
    <header class="crm-map-header">
      <i class="pi pi-map" />
      <div class="crm-map-heading">
        <div class="crm-map-title-row">
          <h2>Médicos de alta intensidade</h2>
          <i class="pi pi-info-circle info-icon" v-tooltip.bottom="mapInfoTooltip" aria-label="Como ler o mapa" />
        </div>
        <span>{{ mapSubtitle }}</span>
      </div>
      <div v-if="!isNational" class="comparacao-control" role="group" aria-label="Comparar com">
        <span class="comparacao-label">Comparar com</span>
        <div class="segmented-control">
          <button
            v-for="opcao in opcoesComparacao"
            :key="opcao.value"
            type="button"
            class="segment-btn"
            :class="{ 'seg-active': comparacao === opcao.value }"
            :aria-pressed="comparacao === opcao.value"
            v-tooltip.bottom="opcao.tooltip"
            @click="comparacao = opcao.value"
          >
            {{ opcao.label }}
          </button>
        </div>
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
        <div class="map-summary-item map-summary-item--accent" v-tooltip.bottom="referenciaTooltip">
          <span>{{ referenciaResumo.label }}</span>
          <strong>{{ referenciaResumo.valor }}</strong>
        </div>
      </div>
    </header>

    <div v-show="!isNational || nationalMapReady" ref="containerRef" class="crm-map-wrapper">
      <div v-if="error && !isLoading" class="map-error-state">
        <div class="map-error-icon"><i class="pi pi-database" /></div>
        <div class="map-error-copy">
          <h3>Mapa indisponível no momento</h3>
          <p>{{ error }}</p>
          <span>Após a sincronização, recarregue esta tela para visualizar o mapa e os indicadores.</span>
        </div>
      </div>
      <template v-else>
        <VChart ref="chartRef" :key="mapKey" class="crm-echart" :option="chartOption" autoresize @click="onMapClick" />
        <div class="map-controls">
          <button type="button" class="zoom-btn" @click="handleZoom(0.5)" v-tooltip.bottom="'Aumentar zoom'"><i class="pi pi-plus" /></button>
          <button type="button" class="zoom-btn" @click="handleZoom(-0.5)" v-tooltip.bottom="'Diminuir zoom'"><i class="pi pi-minus" /></button>
          <button type="button" class="zoom-btn" @click="zoomLevel = 1" v-tooltip.bottom="'Reiniciar zoom'"><i class="pi pi-refresh" /></button>
        </div>
        <!-- Legenda flutuante no canto inferior esquerdo: nao ocupa altura do card. -->
        <div v-if="mapMeta" class="map-legend" aria-label="Escala da concentração de médicos de alta intensidade em relação à média de referência">
          <span class="legend-title">{{ legendTitle }}</span>
          <span v-for="piece in [...activeScale].reverse()" :key="piece.label" class="legend-step">
            <i class="legend-swatch" :style="{ backgroundColor: piece.color, borderColor: piece.borderColor }" aria-hidden="true" />
            {{ piece.label }}
          </span>
          <span v-if="!isNational" class="legend-step legend-step--extra">
            <i class="legend-swatch legend-swatch--hatch" :style="{ borderColor: mapBorderColor, '--hatch-color': hatchColor }" aria-hidden="true" />
            Amostra pequena (&lt; {{ minAmostra }})
          </span>
          <span class="legend-step" :class="{ 'legend-step--extra': isNational }">
            <i class="legend-swatch" :style="{ backgroundColor: mapAreaColor, borderColor: mapBorderColor }" aria-hidden="true" />
            Sem médicos
          </span>
        </div>
      </template>
    </div>
    <div v-show="isNational && !nationalMapReady" class="map-loading">
      <i class="pi pi-spin pi-spinner" />
    </div>
  </section>
</template>

<style scoped>
.crm-map-card {
  background: var(--card-bg);
  border: 1px solid var(--card-border);
  border-radius: 12px;
  height: calc(40vh + 42px);
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
.crm-map-title-row { display: flex; align-items: center; gap: .4rem; }
.info-icon { display: flex; align-items: center; color: var(--text-muted); font-size: .8rem; line-height: 1; opacity: .6; cursor: default; }
.info-icon:hover { opacity: 1; }
.map-back-button { height: 2rem; padding: 0 .65rem; display: inline-flex; align-items: center; gap: .4rem; border: 1px solid var(--card-border); border-radius: 6px; background: var(--card-bg); color: var(--text-muted); cursor: pointer; }
.map-back-button:hover, .map-back-button:focus-visible { color: var(--primary-color); border-color: var(--primary-color); }
.map-back-button:focus-visible, .zoom-btn:focus-visible { outline: 1px solid var(--primary-color); outline-offset: 2px; }
.crm-map-summary { margin-left: auto; display: flex; gap: .65rem; }
.comparacao-control { margin-left: auto; display: flex; align-items: center; gap: .45rem; flex-shrink: 0; }
.comparacao-control + .map-back-button + .crm-map-summary { margin-left: 0; }
.comparacao-label { color: var(--text-muted); font-size: .62rem; white-space: nowrap; }
.segmented-control { display: flex; align-items: center; gap: 2px; padding: 3px; border: 1px solid var(--tabs-border); border-radius: 8px; background: color-mix(in srgb, var(--text-color-85) 7%, transparent); }
.segment-btn { padding: .28rem .7rem; border: 1px solid transparent; border-radius: 6px; background: none; color: var(--text-muted); font-size: .66rem; font-weight: 600; letter-spacing: .03em; white-space: nowrap; cursor: pointer; transition: background .2s ease, color .2s ease; }
.segment-btn:hover { background: color-mix(in srgb, var(--text-color-85) 5%, transparent); }
.segment-btn.seg-active { background: var(--card-bg); border-color: var(--tabs-border); color: var(--primary-color); box-shadow: 0 1px 4px color-mix(in srgb, var(--text-color-85) 15%, transparent); }
.segment-btn:focus-visible { outline: 1px solid var(--primary-color); outline-offset: 2px; }
.map-summary-item { min-width: 112px; padding: .45rem .62rem; border: 1px solid var(--card-border); border-radius: 8px; background: color-mix(in srgb, var(--card-bg) 90%, var(--primary-color) 10%); }
.map-summary-item span { display: block; color: var(--text-muted); font-size: .6rem; margin-bottom: .2rem; }
.map-summary-item strong { color: var(--text-color-85); font-size: .82rem; font-weight: 600; }
.map-summary-item--accent strong { color: var(--primary-color); }
.crm-map-wrapper { position: relative; flex: 1; min-height: 0; }
.crm-echart { width: 100%; height: 100%; }
.map-loading { flex: 1; min-height: 0; display: flex; align-items: center; justify-content: center; color: var(--text-muted); font-size: 1.4rem; }
.map-error-state { height: 100%; display: flex; align-items: center; justify-content: center; gap: 1rem; padding: 2rem; }
.map-error-icon { width: 3.5rem; height: 3.5rem; display: grid; place-items: center; flex: 0 0 auto; border: 1px solid color-mix(in srgb, var(--risk-high) 35%, var(--card-border)); border-radius: 50%; background: color-mix(in srgb, var(--risk-high) 9%, var(--card-bg)); color: var(--risk-high); font-size: 1.35rem; }
.map-error-copy { max-width: 520px; }
.map-error-copy h3 { margin: 0; color: var(--text-color-85); font-size: .92rem; font-weight: 600; }
.map-error-copy p { margin: .4rem 0 0; color: var(--text-muted); font-size: .76rem; line-height: 1.5; }
.map-error-copy span { display: block; margin-top: .55rem; color: var(--text-color-70); font-size: .68rem; line-height: 1.45; }
.map-legend { position: absolute; left: .75rem; bottom: .75rem; display: flex; flex-direction: column; gap: .22rem; padding: .5rem .6rem; border: 1px solid var(--card-border); border-radius: 8px; background: color-mix(in srgb, var(--card-bg) 88%, transparent); backdrop-filter: blur(4px); color: var(--text-color-70); font-size: .62rem; pointer-events: none; }
.legend-title { margin-bottom: .12rem; color: var(--text-muted); white-space: nowrap; }
.legend-step { display: flex; align-items: center; gap: .35rem; white-space: nowrap; }
.legend-step--extra { margin-top: .2rem; padding-top: .3rem; border-top: 1px solid var(--tabs-border); }
.legend-step--extra + .legend-step { margin-top: 0; }
.legend-swatch { display: inline-block; width: .72rem; height: .72rem; flex-shrink: 0; border: 1px solid; border-radius: 2px; }
.legend-swatch--hatch { background: repeating-linear-gradient(-45deg, var(--hatch-color) 0 1px, transparent 1px 4px); }
.map-controls { position: absolute; right: 1rem; bottom: 1rem; display: flex; flex-direction: column; gap: .45rem; }
.zoom-btn { width: 2rem; height: 2rem; border: 1px solid var(--card-border); border-radius: 7px; background: color-mix(in srgb, var(--card-bg) 90%, transparent); color: var(--text-muted); cursor: pointer; }
.zoom-btn:hover { color: var(--primary-color); border-color: var(--primary-color); }
</style>
