<script setup>
import { computed, nextTick, onMounted, ref, watch } from 'vue';
import { use } from 'echarts/core';
import { CanvasRenderer } from 'echarts/renderers';
import { MapChart } from 'echarts/charts';
import { TooltipComponent, VisualMapComponent } from 'echarts/components';
import VChart from 'vue-echarts';
import MapBackButton from '@/views/components/maps/MapBackButton.vue';
import { registerMap } from 'echarts/core';
import { ensureBrasilUfMap } from '@/composables/echartsMaps';
import { useGeoStore } from '@/stores/geo';
import { useThemeStore } from '@/stores/theme';
import { useChartTheme } from '@/config/chartTheme';
import { CRM_INTENSIDADE_INDICE_SCALE } from '@/config/colors';
import { CRM_FAIXAS } from '@/config/crmFiltrosMedico';
import { useCrmFiltrosMedicoStore } from '@/stores/crmFiltrosMedico';
import { analysisTooltip } from '@/config/analysisTooltipConfig';
import { useStableMapSize } from '@/composables/useStableMapSize';
import { useFormatting } from '@/composables/useFormatting';

use([CanvasRenderer, MapChart, TooltipComponent, VisualMapComponent]);

const props = defineProps({
  mapLevel: { type: String, required: true },
  mapData: { type: Array, default: () => [] },
  uf: { type: String, default: null },
  regiaoId: { type: [String, Number], default: null },
  selectedIbge7: { type: [String, Number], default: null },
  selectedMunicipioNome: { type: String, default: null },
  selectedRegiaoNome: { type: String, default: null },
  qtdMedicos: { type: Number, default: 0 },
  // Resposta do mapa: referencias (% Brasil/UF), faixa do corte P95 e minimo da amostra.
  mapMeta: { type: Object, default: null },
  isLoading: { type: Boolean, default: false },
  error: { type: String, default: null },
});

const emit = defineEmits(['select-uf', 'select-municipio', 'back']);
const geoStore = useGeoStore();
const filtrosMedicoStore = useCrmFiltrosMedicoStore();
const themeStore = useThemeStore();
const { chartTheme } = useChartTheme();
const { formatTitleCase } = useFormatting();

const chartRef = ref(null);
const containerRef = ref(null);
const nationalMapReady = ref(false);
const mapKey = ref(0);
const zoomLevel = ref(1);
const { containerWidth, containerHeight, hasMeasured } = useStableMapSize(containerRef, chartRef);

const isNational = computed(() => props.mapLevel === 'uf');
const requestedScopeLabel = computed(() => {
  if (isNational.value) return 'Brasil';
  const parts = [`UF ${props.uf}`];
  if (props.selectedRegiaoNome) parts.push(formatTitleCase(props.selectedRegiaoNome));
  if (props.selectedMunicipioNome) parts.push(formatTitleCase(props.selectedMunicipioNome));
  return parts.join(' › ');
});

// Cada municipio usa a propria regiao de saude como referencia. No mapa
// nacional, as UFs usam a media das 27 UFs porque nao ha regiao unica.
const referenciaTexto = computed(() => isNational.value ? 'média das UFs' : 'média da própria Região de Saúde');
const legendTitle = computed(() => isNational.value ? 'vs. média das UFs' : 'vs. região de saúde');

function indiceAtivo(row) {
  const valor = isNational.value ? row?.indice_brasil : row?.indice_regiao;
  return valor == null ? null : Number(valor);
}

const mapTitle = computed(() => isNational.value ? 'Brasil' : props.mapLevel === 'regiao' ? 'Região de Saúde' : `Municípios de ${props.uf}`);
// Faixas de producao (taxa/dia, total de prescricoes) sao avaliadas com os numeros
// do medico no recorte do mapa (UF ou regiao inteira), nao em cada municipio. Com
// municipio selecionado, o ranking usa os numeros no municipio: os totais diferem.
const faixaProducaoAtiva = computed(() => Object.entries(CRM_FAIXAS).some(([tipo, config]) => (
  config.grupo === 'producao'
  && (filtrosMedicoStore.faixas[tipo].min !== null || filtrosMedicoStore.faixas[tipo].max !== null)
)));
const avisoRecorteFaixa = computed(() => !isNational.value && faixaProducaoAtiva.value);
const recorteFaixaTexto = computed(() => {
  if (props.mapLevel !== 'regiao') return `na UF ${props.uf} inteira`;
  return props.selectedRegiaoNome
    ? `na Região de Saúde ${formatTitleCase(props.selectedRegiaoNome)} inteira`
    : 'na Região de Saúde inteira';
});
const municipioDiverge = computed(() => (
  avisoRecorteFaixa.value && props.mapLevel === 'regiao' && props.selectedIbge7 != null
));

// Subtitulo curto: a explicacao completa fica no tooltip do titulo.
const mapSubtitle = computed(() => {
  const partes = [mapTitle.value, `comparado à ${referenciaTexto.value}`];
  if (props.mapMeta?.filtro_farmacias_ativo) partes.push('farmácias filtradas');
  if (avisoRecorteFaixa.value) partes.push(`taxa/prescrições avaliadas ${recorteFaixaTexto.value}`);
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
  if (props.mapMeta?.filtro_farmacias_ativo) {
    extraSections.push({
      label: 'Farmácias filtradas',
      text: 'Com filtros de farmácia, contam só os médicos que prescreveram em pelo menos uma farmácia filtrada do território em algum mês do período. Entre eles, têm taxa elevada os que tiveram pelo menos um mês acima do P95 no território, considerando todas as prescrições do médico ali.',
    });
  }
  if (avisoRecorteFaixa.value) {
    const municipio = props.selectedMunicipioNome ? formatTitleCase(props.selectedMunicipioNome) : 'no município selecionado';
    extraSections.push({
      label: 'Taxa diária e total de prescrições',
      text: `Com esses filtros, cada município do mapa conta os médicos cujos números ${recorteFaixaTexto.value} estão na faixa, e não os números do médico só naquele município.`
        + (municipioDiverge.value
          ? ` O ranking usa os números do médico em ${municipio}; por isso o número do município no mapa pode ser maior que o do ranking.`
          : ''),
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

function escapeMapTooltip(value) {
  return String(value).replace(/[&<>"']/g, (character) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  })[character]);
}

const minAmostra = computed(() => props.mapMeta?.min_medicos_amostra_municipio ?? null);
// Na UF cada municipio usa sua propria regiao, sem um percentual unico no cabecalho.
const referenciaResumo = computed(() => {
  const meta = props.mapMeta ?? {};
  if (isNational.value) return { label: 'Média das UFs', valor: formatPct(meta.percentual_referencia_brasil) };
  if (props.mapLevel === 'regiao') return { label: 'Média da região', valor: formatPct(meta.percentual_referencia_regiao) };
  return { label: 'Referência', valor: 'Por região' };
});
const referenciaTooltip = computed(() => (isNational.value
  ? 'Soma dos médicos com taxa elevada ÷ soma dos médicos ativos das 27 UFs. Um médico conta em cada UF onde prescreveu, por isso a referência soma as UFs em vez de contar cada médico uma vez no país.'
  : 'Cada município é comparado à sua Região de Saúde. A referência soma os médicos com taxa elevada dos municípios da região e divide pela soma dos médicos ativos desses municípios.'));

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

// Mapa ja registrado no ECharts. Ao trocar de nivel (ex.: limpar a UF), o
// GeoJSON nacional pode ainda estar sendo baixado: enquanto o mapa pedido nao
// estiver registrado, o grafico mantem a ultima opcao valida em vez de receber
// um mapa inexistente (o ECharts lanca erro e trava a atualizacao da tela).
const registeredMapName = ref(null);
let lastValidOption = null;

// Troca de escopo (Brasil -> UF -> regiao): o mapa atual fica na tela ate o
// GeoJSON do novo escopo estar registrado E a resposta do servidor ser desse
// escopo; so entao o grafico e recriado, uma vez, ja com as cores certas.
// (Antes era recriado no clique com os dados antigos -- tudo cinza -- e
// redesenhado quando os dados chegavam.) Com erro no pedido, desenha sem dados.
const committedMapName = ref(null);
const committedScopeLabel = ref(null);
const dataMatchesScope = computed(() => {
  const meta = props.mapMeta;
  if (!meta || meta.map_level !== props.mapLevel) return false;
  if (props.mapLevel === 'uf') return true;
  const first = props.mapData[0];
  if (!first) return false;
  if (props.mapLevel === 'municipio') return first.uf === props.uf;
  return String(first.id_regiao_saude) === String(props.regiaoId);
});
const changingScope = computed(() => mapName.value !== committedMapName.value);

watch(
  [mapName, registeredMapName, dataMatchesScope, () => props.error],
  () => {
    if (!changingScope.value || registeredMapName.value !== mapName.value) return;
    if (!dataMatchesScope.value && !props.error) return;
    committedMapName.value = mapName.value;
    mapKey.value += 1;
    nextTick(() => chartRef.value?.chart?.resize());
  },
  { immediate: true },
);
watch(
  [requestedScopeLabel, changingScope, () => props.isLoading],
  () => {
    if (!changingScope.value && !props.isLoading) committedScopeLabel.value = requestedScopeLabel.value;
  },
  { immediate: true },
);
const mapScopeLabel = computed(() => committedScopeLabel.value ?? requestedScopeLabel.value);

const chartOption = computed(() => {
  if (changingScope.value) {
    return lastValidOption ?? {};
  }
  lastValidOption = buildChartOption();
  return lastValidOption;
});

function buildChartOption() {
  const c = chartTheme.value;
  const mapMeta = props.mapMeta;
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
        const label = escapeMapTooltip(row?.nome ?? params.name ?? '—');
        if (!row) {
          return `<div style="min-width: 150px; color: ${c.tooltipText}"><strong>${label}</strong><div style="margin-top: 8px; opacity: .7">Sem dados no escopo atual</div></div>`;
        }
        const linha = (rotulo, valor) => `<div style="display:flex; justify-content:space-between; gap:20px; margin:4px 0"><span style="opacity:.72">${rotulo}</span><span>${valor}</span></div>`;
        const ativos = Number(row.qtd_medicos_ativos).toLocaleString('pt-BR');
        const alta = Number(row.qtd_medicos_alta_intensidade).toLocaleString('pt-BR');
        const isMunicipio = row.nivel === 'municipio';
        let referencia;
        let contexto = '';
        if (isMunicipio) {
          if (row.id_regiao_saude == null) throw new Error('Municipio do mapa sem id_regiao_saude.');
          const nomeRegiao = geoStore.getRegiaoNomeById(row.id_regiao_saude);
          if (!nomeRegiao) throw new Error('Regiao de saude do mapa sem nome no contrato de localidades.');
          referencia = `
            <div style="opacity:.72; margin-bottom:5px">Região de Saúde · ${escapeMapTooltip(formatTitleCase(nomeRegiao))}</div>
            ${linha('Média regional', `<strong>${formatPct(row.percentual_referencia_regiao)}</strong>`)}
            ${linha('Município / região', `<strong>${formatIndice(row.indice_regiao)}</strong>`)}
          `;
          contexto = `
            <div style="margin-top:10px; padding-top:8px; border-top:1px solid ${c.tooltipBorder}; opacity:.72">Outras referências</div>
            ${linha(`UF ${escapeMapTooltip(row.uf)}`, formatPct(mapMeta?.percentual_referencia_uf))}
            ${linha('Brasil', formatPct(mapMeta?.percentual_referencia_brasil))}
          `;
        } else {
          referencia = `
            ${linha('Média das UFs', `<strong>${formatPct(mapMeta?.percentual_referencia_brasil)}</strong>`)}
            ${linha('UF / média', `<strong>${formatIndice(row.indice_brasil)}</strong>`)}
          `;
        }
        const aviso = row.amostra_pequena && Number(row.qtd_medicos_ativos) > 0
          ? `<div style="margin-top:10px; padding-top:8px; border-top:1px solid ${c.tooltipBorder}; opacity:.72">Amostra pequena: menos de ${minAmostra.value} médicos no período (sem cor de risco).</div>`
          : '';
        return `<div style="min-width: 240px; max-width: 300px; color: ${c.tooltipText}">
          <div style="font-weight:600; padding-bottom:8px; border-bottom:1px solid ${c.tooltipBorder}">${label}</div>
          <div style="display:flex; justify-content:space-between; align-items:baseline; gap:16px; margin-top:9px">
            <span style="opacity:.72">Taxa elevada</span>
            <strong style="font-size:16px">${formatPct(row.percentual_alta_intensidade)}</strong>
          </div>
          <div style="opacity:.72; font-size:11px; margin-top:2px">${alta} de ${ativos} médicos ativos</div>
          <div style="margin-top:10px; padding-top:8px; border-top:1px solid ${c.tooltipBorder}">
            <div style="font-weight:600; margin-bottom:5px">Referência de cor</div>
            ${referencia}
          </div>
          ${contexto}
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
}

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
  let nomeRegistrado;
  if (isNational.value) {
    await ensureBrasilUfMap();
    nomeRegistrado = 'brasil-uf';
  } else if (currentGeo.value) {
    nomeRegistrado = mapName.value;
    registerMap(nomeRegistrado, currentGeo.value);
  } else {
    return;
  }
  // Durante o download do GeoJSON o usuario pode ter trocado de nivel de novo:
  // so libera o grafico se o mapa registrado ainda for o pedido.
  if (nomeRegistrado !== mapName.value) return;
  registeredMapName.value = nomeRegistrado;
}

onMounted(async () => {
  try {
    await registerActiveMap();
    nationalMapReady.value = true;
  } catch (error) {
    console.error('[CRM map] GeoJSON indisponível:', error);
  }
});

// Sem deep: o GeoJSON so e trocado inteiro (ao carregar). Com deep, o Vue
// percorria os 642 mil pontos a cada clique em UF (~1-2 s de tela travada).
watch(
  () => [props.mapLevel, props.uf, props.regiaoId, geoStore.municipiosGeoJson],
  () => registerActiveMap().catch((error) => console.error('[CRM map] GeoJSON indisponível:', error)),
);

watch(() => themeStore.isDark, () => mapKey.value++);

</script>

<template>
  <section class="crm-map-card" :class="{ 'is-refreshing': isLoading }">
    <header class="crm-map-header">
      <i class="pi pi-map" />
      <div class="crm-map-heading">
        <div class="crm-map-title-row">
          <h2>Médicos com taxa elevada</h2>
          <i class="pi pi-info-circle info-icon" v-tooltip.bottom="mapInfoTooltip" aria-label="Como ler o mapa" />
        </div>
        <span>{{ mapSubtitle }}</span>
      </div>
      <MapBackButton v-if="!isNational" :label="backLabel" @click="emit('back')" />
      <div class="crm-map-summary">
        <div class="map-summary-item">
          <span>Nº de CRMs</span>
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
        <VChart v-if="hasMeasured" ref="chartRef" :key="mapKey" class="crm-echart" :option="chartOption" @click="onMapClick" />
        <div class="map-scope-badge" :aria-label="`Recorte do mapa: ${mapScopeLabel}`">
          <i class="pi pi-map-marker" aria-hidden="true" />
          <span>{{ mapScopeLabel }}</span>
        </div>
        <div class="map-controls">
          <button type="button" class="zoom-btn" @click="handleZoom(0.5)" v-tooltip.bottom="'Aumentar zoom'"><i class="pi pi-plus" /></button>
          <button type="button" class="zoom-btn" @click="handleZoom(-0.5)" v-tooltip.bottom="'Diminuir zoom'"><i class="pi pi-minus" /></button>
          <button type="button" class="zoom-btn" @click="zoomLevel = 1" v-tooltip.bottom="'Reiniciar zoom'"><i class="pi pi-refresh" /></button>
        </div>
        <!-- Legenda flutuante no canto superior esquerdo: nao ocupa altura do card. -->
        <div v-if="mapMeta" class="map-legend" aria-label="Escala da concentração de médicos com taxa elevada em relação à média de referência">
          <span class="legend-title">{{ legendTitle }}</span>
          <span v-for="piece in [...activeScale].reverse()" :key="piece.label" class="legend-step">
            <i class="legend-swatch" :style="{ backgroundColor: piece.color, borderColor: piece.borderColor }" aria-hidden="true" />
            {{ piece.label }}
          </span>
          <!-- Sempre visivel (tambem no mapa Brasil) para a legenda nao mudar de tamanho. -->
          <span class="legend-step legend-step--extra">
            <i class="legend-swatch legend-swatch--hatch" :style="{ borderColor: mapBorderColor, '--hatch-color': hatchColor }" aria-hidden="true" />
            Amostra pequena (&lt; {{ minAmostra }})
          </span>
          <span class="legend-step">
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
}

.crm-map-card.is-refreshing { pointer-events: none; }
.crm-map-header { --map-header-item-height: 2.75rem; display: grid; grid-template-columns: 1rem minmax(0, 1fr) auto auto; align-items: center; gap: .8rem; padding: .8rem 1.15rem; border-bottom: 1px solid var(--tabs-border); flex-shrink: 0; }
.crm-map-header :deep(.map-back-button) { grid-column: 3; grid-row: 1; height: var(--map-header-item-height); }
.crm-map-header > i { grid-column: 1; grid-row: 1; color: var(--primary-color); font-size: 1rem; }
.crm-map-heading { grid-column: 2; grid-row: 1; min-width: 0; display: flex; flex-direction: column; gap: .15rem; }
.crm-map-heading h2 { margin: 0; color: var(--text-color-85); font-size: .84rem; font-weight: 600; letter-spacing: .02em; }
.crm-map-heading span { color: var(--text-muted); font-size: .68rem; }
.crm-map-title-row { display: flex; align-items: center; gap: .4rem; }
.info-icon { display: flex; align-items: center; color: var(--text-muted); font-size: .8rem; line-height: 1; opacity: .6; cursor: default; }
.info-icon:hover { opacity: 1; }
.zoom-btn:focus-visible { outline: 1px solid var(--primary-color); outline-offset: 2px; }
.crm-map-summary { grid-column: 4; grid-row: 1; display: flex; gap: .65rem; }
.map-summary-item { box-sizing: border-box; width: 120px; height: var(--map-header-item-height); display: flex; flex-direction: column; justify-content: center; padding: 0 .62rem; border: 1px solid var(--card-border); border-radius: 8px; background: color-mix(in srgb, var(--card-bg) 86%, transparent); }
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
.map-scope-badge { position: absolute; top: .75rem; right: .75rem; z-index: 1; display: inline-flex; align-items: center; gap: .4rem; max-width: min(55%, 24rem); padding: .4rem .6rem; border: 1px solid var(--card-border); border-radius: 8px; background: color-mix(in srgb, var(--card-bg) 92%, transparent); color: var(--text-secondary); font-size: .75rem; line-height: 1.25; backdrop-filter: blur(4px); -webkit-backdrop-filter: blur(4px); }
.map-scope-badge i { flex: none; color: var(--primary-color); font-size: .7rem; }
.map-scope-badge span { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.map-legend { position: absolute; left: .75rem; top: .75rem; display: flex; flex-direction: column; gap: .1rem; padding: .45rem .6rem; border: 1px solid var(--card-border); border-radius: 8px; background: color-mix(in srgb, var(--card-bg) 88%, transparent); backdrop-filter: blur(4px); color: var(--text-color-70); font-size: .62rem; pointer-events: none; }
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
