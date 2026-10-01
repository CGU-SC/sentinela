<script setup>
import { computed, onActivated, onDeactivated, ref, watch } from 'vue';
import { storeToRefs } from 'pinia';
import { useAnalyticsStore } from '@/stores/analytics';
import { buildAnalyticsParams } from '@/stores/analytics';
import { useFilterStore } from '@/stores/filters';
import { useRiskIndicatorsStore } from '@/stores/riskIndicators';
import { useGeoStore } from '@/stores/geo';
import { useMunicipalMapStore } from '@/stores/municipalMap';
import { useFetchAnalytics } from '@/composables/useFetchAnalytics';
import { useRiskIndicatorAnalysis } from '@/composables/useRiskIndicatorAnalysis';
import { INDICATOR_GROUPS } from '@/config/riskConfig';
import { MUNICIPIOS_HIDDEN_KPI_LABELS } from '@/config/constants';
import KpiSection from './components/KpiSection.vue';
import MunicipalRiskMap from './components/municipios/MunicipalRiskMap.vue';
import MunicipalRiskTable from './components/municipios/MunicipalRiskTable.vue';
import RiskIndicatorSelector from './components/risk-indicators/RiskIndicatorSelector.vue';

defineOptions({ name: 'MunicipalView' });

const analyticsStore = useAnalyticsStore();
const filterStore = useFilterStore();
const riskIndicatorsStore = useRiskIndicatorsStore();
const geoStore = useGeoStore();
const municipalMapStore = useMunicipalMapStore();
const isActive = ref(true);
const { resultadoMunicipios, isLoading, error: analyticsError, sectionKeys } = storeToRefs(analyticsStore);
// Seções do resumo exibidas nesta tela (KPIs + tabela/mapa municipal).
const DASHBOARD_SECOES = ['kpis', 'municipios'];
const municipiosLoadedKey = computed(() => sectionKeys.value.municipios);
const {
  selectedRiskIndicator,
  kpis,
  municipios: riskIndicatorMunicipios,
  isLoading: isRiskIndicatorLoading,
  summaryError: riskIndicatorError,
  summaryParamsKey,
} = storeToRefs(riskIndicatorsStore);
const { fetchRiskIndicator } = useRiskIndicatorAnalysis({ active: isActive, includeTable: false });

useFetchAnalytics({ secoes: DASHBOARD_SECOES, includeFatorRisco: false, includeNationalContext: false, active: isActive });

onActivated(() => {
  isActive.value = true;
});
onDeactivated(() => {
  isActive.value = false;
});

const selectedIbge7 = ref(null);
const displaySnapshot = ref(null);
const { rows: mapMunicipios, loadedKey: mapLoadedKey, isLoading: isMapLoading, error: mapError } = storeToRefs(municipalMapStore);

const activeUf = computed(() => filterStore.selectedUF);
const metricMode = computed(() => selectedRiskIndicator.value ? 'indicator' : 'audit');
const activeRiskIndicatorMeta = computed(() => {
  if (!selectedRiskIndicator.value) return null;
  for (const group of INDICATOR_GROUPS) {
    const indicador = group.indicators.find((item) => item.key === selectedRiskIndicator.value);
    if (indicador) return indicador;
  }
  return null;
});
function mergeIndicatorRows(baseRows) {
  if (metricMode.value !== 'indicator') return baseRows;

  const indicadorPorMunicipio = new Map(
    riskIndicatorMunicipios.value.map((row) => [Number(row.id_ibge7), row])
  );

  return baseRows.map((municipioRow) => {
    const indicadorRow = indicadorPorMunicipio.get(Number(municipioRow.id_ibge7));
    return {
      ...municipioRow,
      total_cnpjs: indicadorRow?.total_cnpjs ?? 0,
      total_critico: indicadorRow?.total_critico ?? 0,
      pct_critico: indicadorRow?.pct_critico ?? 0,
    };
  });
}

const activeMetricLabel = computed(() =>
  metricMode.value === 'indicator'
    ? (activeRiskIndicatorMeta.value?.label ?? 'Indicador')
    : 'Percentual não comprovação'
);
const selectedLocalidade = computed(() => {
  if (selectedIbge7.value == null) return null;
  const localidade = geoStore.localidades.find(
    (item) => Number(item.id_ibge7) === Number(selectedIbge7.value)
  );
  if (!localidade?.id_ibge7 || !localidade?.id_regiao_saude || !localidade?.sg_uf || !localidade?.no_municipio) {
    throw new Error('Municipio selecionado nao encontrado no contrato de localidades.');
  }
  return localidade;
});
const selectedRegiaoNome = computed(() => {
  const regiaoId = filterStore.selectedRegiaoSaude && filterStore.selectedRegiaoSaude !== 'Todos'
    ? filterStore.selectedRegiaoSaude
    : selectedLocalidade.value?.id_regiao_saude;
  if (!regiaoId) return null;
  const nome = geoStore.getRegiaoNomeById(regiaoId);
  if (!nome) throw new Error('Regiao de saude selecionada sem nome no contrato de localidades.');
  return nome;
});

watch(
  () => filterStore.selectedMunicipio,
  (municipio) => {
    selectedIbge7.value = municipio && municipio !== 'Todos'
      ? Number(municipio)
      : null;
  },
  { immediate: true },
);

const mapApiParams = computed(() => {
  const params = { ...filterStore.apiParams, idIbge7: null };
  return buildAnalyticsParams(params);
});

const mapApiParamsKey = computed(() => JSON.stringify(mapApiParams.value));
const dashboardParamsKey = computed(() => JSON.stringify(buildAnalyticsParams(filterStore.apiParams)));
const indicatorParamsKey = computed(() => selectedRiskIndicator.value
  ? JSON.stringify({ indicador: selectedRiskIndicator.value, params: filterStore.indicadoresApiParams })
  : null);
const requestedSnapshotKey = computed(() => JSON.stringify({
  dashboard: dashboardParamsKey.value,
  map: mapApiParamsKey.value,
  indicator: indicatorParamsKey.value,
}));
const currentDataReady = computed(() =>
  filterStore.isPeriodoValido
  && analyticsStore.isDashboardFresh(dashboardParamsKey.value, DASHBOARD_SECOES)
  && mapLoadedKey.value === mapApiParamsKey.value
  && (!indicatorParamsKey.value || summaryParamsKey.value === indicatorParamsKey.value)
  && !isLoading.value
  && !isMapLoading.value
  && (!indicatorParamsKey.value || !isRiskIndicatorLoading.value)
  && !analyticsError.value
  && !mapError.value
  && (!indicatorParamsKey.value || !riskIndicatorError.value)
);

watch(
  [currentDataReady, resultadoMunicipios, mapMunicipios, riskIndicatorMunicipios, kpis],
  () => {
    if (!currentDataReady.value) return;
    displaySnapshot.value = {
      key: requestedSnapshotKey.value,
      mapData: mergeIndicatorRows(mapMunicipios.value),
      tableData: mergeIndicatorRows(resultadoMunicipios.value),
      kpis: kpis.value,
      activeUf: activeUf.value,
      selectedRegiao: filterStore.selectedRegiaoSaude,
      selectedIbge7: selectedIbge7.value,
      selectedMunicipioNome: selectedLocalidade.value?.no_municipio ?? null,
      selectedRegiaoNome: selectedRegiaoNome.value,
      metricMode: metricMode.value,
      metricLabel: activeMetricLabel.value,
    };
  },
  { immediate: true },
);

const snapshotStale = computed(() => displaySnapshot.value?.key !== requestedSnapshotKey.value || !currentDataReady.value);
const displayError = computed(() => {
  if (!snapshotStale.value) return null;
  return mapError.value || analyticsError.value || (indicatorParamsKey.value ? riskIndicatorError.value : null);
});

watch(
  [mapApiParamsKey, dashboardParamsKey, municipiosLoadedKey, isActive],
  ([requestKey, dashboardKey, loadedDashboardKey, active]) => {
    if (!active) return;
    if (!filterStore.isPeriodoValido) return;
    if (mapLoadedKey.value === requestKey && !mapError.value) return;
    if (requestKey === dashboardKey) {
      if (loadedDashboardKey === dashboardKey && !isLoading.value && !analyticsError.value) {
        municipalMapStore.useDashboardRows(requestKey, resultadoMunicipios.value);
      }
    } else {
      municipalMapStore.load(requestKey, mapApiParams.value).catch(() => {});
    }
  },
  { immediate: true },
);

function handleSelectMunicipio(ibge7) {
  if (!ibge7) {
    selectedIbge7.value = null;
    filterStore.selectedMunicipio = 'Todos';
    return;
  }

  const localidade = geoStore.localidades.find(
    (item) => Number(item.id_ibge7) === Number(ibge7)
  );
  if (!localidade?.id_ibge7 || !localidade?.id_regiao_saude || !localidade?.sg_uf) {
    throw new Error('Municipio selecionado sem contrato geografico completo.');
  }

  selectedIbge7.value = Number(localidade.id_ibge7);
  filterStore.selectedMunicipio = String(localidade.id_ibge7);
}

function handleClearRegiaoFilter() {
  filterStore.selectedRegiaoSaude = 'Todos';
  filterStore.selectedMunicipio = 'Todos';
}

function handleSelectUf(uf) {
  filterStore.selectedMunicipio = 'Todos';
  filterStore.selectedRegiaoSaude = 'Todos';
  filterStore.selectedUF = uf;
}

function handleMapBackToUf() {
  filterStore.selectedMunicipio = 'Todos';
  filterStore.selectedRegiaoSaude = 'Todos';
}

function handleMapBackToBrazil() {
  filterStore.selectedMunicipio = 'Todos';
  filterStore.selectedRegiaoSaude = 'Todos';
  filterStore.selectedUF = 'Todos';
}

function handleRiskIndicatorSelect(key) {
  fetchRiskIndicator(key);
}
</script>

<template>
  <div class="municipios-page">
    <KpiSection :hidden-labels="MUNICIPIOS_HIDDEN_KPI_LABELS" />

    <div class="municipios-layout">
      <div class="municipios-analysis-panel">
        <MunicipalRiskMap
          :map-data="displaySnapshot?.mapData ?? []"
          :kpis="displaySnapshot?.kpis ?? null"
          :active-uf="displaySnapshot?.activeUf ?? activeUf"
          :is-loading="snapshotStale"
          :error="displayError"
          :selected-ibge7="displaySnapshot?.selectedIbge7 ?? null"
          :selected-regiao="displaySnapshot?.selectedRegiao ?? 'Todos'"
          :metric-mode="displaySnapshot?.metricMode ?? metricMode"
          :metric-label="displaySnapshot?.metricLabel ?? activeMetricLabel"
          :selected-municipio-nome="displaySnapshot?.selectedMunicipioNome ?? null"
          :selected-regiao-nome="displaySnapshot?.selectedRegiaoNome ?? null"
          @select-municipio="handleSelectMunicipio"
          @select-uf="handleSelectUf"
          @back-to-uf="handleMapBackToUf"
          @clear-geography="handleMapBackToBrazil"
        />

        <MunicipalRiskTable
          :municipios="displaySnapshot?.tableData ?? []"
          :participation-rows="displaySnapshot?.mapData ?? []"
          :is-loading="snapshotStale && !displayError"
          :is-stale="snapshotStale"
          :error="displayError"
          :selected-ibge7="displaySnapshot?.selectedIbge7 ?? null"
          :metric-mode="displaySnapshot?.metricMode ?? metricMode"
          :metric-label="displaySnapshot?.metricLabel ?? activeMetricLabel"
          :selected-regiao-nome="displaySnapshot?.selectedRegiaoNome ?? null"
          @select-municipio="handleSelectMunicipio"
          @clear-regiao-filter="handleClearRegiaoFilter"
        />
      </div>

      <RiskIndicatorSelector :active-risk-indicator-meta="activeRiskIndicatorMeta" @select="handleRiskIndicatorSelect" />
    </div>
  </div>
</template>

<style scoped>
.municipios-page {
  --indicator-selector-width: 240px;
  display: flex;
  flex-direction: column;
  gap: 1rem;
  width: 100%;
  min-width: 0;
}

.municipios-layout {
  display: flex;
  align-items: flex-start;
  gap: 1rem;
  width: 100%;
}

.municipios-analysis-panel {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

</style>
