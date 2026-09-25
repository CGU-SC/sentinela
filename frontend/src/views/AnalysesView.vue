<script setup>
import { computed, ref, watch } from 'vue';
import { useFilterStore } from '@/stores/filters';
import { useGeoStore } from '@/stores/geo';
import { useFetchAnalytics } from '@/composables/useFetchAnalytics';
import { useCrmPrescricoesAnalysis } from '@/composables/useCrmPrescricoesAnalysis';
import { CRM_ANALYSIS_FILTER_SCOPE_NOTICE } from '@/config/constants';

import AnalysisSidebar from './components/analises/AnalysisSidebar.vue';
import CrmPrescricoesMap from './components/analises/CrmPrescricoesMap.vue';
import CrmPrescricoesRanking from './components/analises/CrmPrescricoesRanking.vue';
import KpiSection from './components/KpiSection.vue';

const filterStore = useFilterStore();
const geoStore = useGeoStore();
useFetchAnalytics({ includeFatorRisco: false, includeNationalContext: false });

function levelForFilters() {
  if (filterStore.selectedRegiaoSaude && filterStore.selectedRegiaoSaude !== 'Todos') return 'regiao';
  if (filterStore.selectedUF && filterStore.selectedUF !== 'Todos') return 'municipio';
  return 'uf';
}

const mapLevel = ref(levelForFilters());
const navigationError = ref(null);
const {
  mapResponse,
  rankingResponse,
  hasIgnoredFilters,
  isMapLoading,
  isRankingLoading,
  mapError,
  rankingError,
  rankingPageError,
  rankingPage,
  rankingPageSize,
  fetchRankingPage,
} = useCrmPrescricoesAnalysis(mapLevel);

const selectedUf = computed(() => filterStore.selectedUF !== 'Todos' ? filterStore.selectedUF : null);
const selectedRegiaoId = computed(() => filterStore.selectedRegiaoSaude !== 'Todos' ? filterStore.selectedRegiaoSaude : null);
const selectedMunicipioIbge7 = computed(() => {
  const value = filterStore.selectedMunicipio;
  return value && value !== 'Todos' ? Number(value) : null;
});
const mapData = computed(() => mapResponse.value?.mapa ?? []);
const ranking = computed(() => rankingResponse.value?.ranking ?? []);
const rankingTotal = computed(() => rankingResponse.value?.qtd_medicos ?? 0);
const rankingFirst = computed(() => (rankingPage.value - 1) * rankingPageSize.value);
const rankingInitialLoading = computed(() => isRankingLoading.value && ranking.value.length === 0);
const rankingPageLoading = computed(() => isRankingLoading.value && ranking.value.length > 0);

watch(
  [() => filterStore.selectedUF, () => filterStore.selectedRegiaoSaude, () => filterStore.selectedMunicipio],
  () => {
    mapLevel.value = levelForFilters();
  },
);

function onSelectUf(uf) {
  navigationError.value = null;
  filterStore.selectedUF = uf;
  filterStore.selectedRegiaoSaude = 'Todos';
  filterStore.selectedMunicipio = 'Todos';
  mapLevel.value = 'municipio';
}

function onSelectMunicipio(idIbge7) {
  navigationError.value = null;
  if (idIbge7 == null) {
    filterStore.selectedMunicipio = 'Todos';
    mapLevel.value = 'regiao';
    return;
  }
  const regionId = geoStore.getRegiaoByIbge7(idIbge7);
  if (regionId == null) {
    navigationError.value = 'Não foi possível localizar a Região de Saúde deste município.';
    return;
  }
  filterStore.selectedMunicipio = String(idIbge7);
  filterStore.selectedRegiaoSaude = String(regionId);
  mapLevel.value = 'regiao';
}

function goBack() {
  navigationError.value = null;
  if (mapLevel.value === 'regiao') {
    filterStore.selectedRegiaoSaude = 'Todos';
    filterStore.selectedMunicipio = 'Todos';
    mapLevel.value = 'municipio';
    return;
  }
  filterStore.selectedUF = 'Todos';
  filterStore.selectedRegiaoSaude = 'Todos';
  filterStore.selectedMunicipio = 'Todos';
  mapLevel.value = 'uf';
}

function onRankingPage(event) {
  const rows = event.rows ?? rankingPageSize.value;
  const first = event.first ?? 0;
  const page = Math.floor(first / rows) + 1;
  fetchRankingPage(page, rows);
}
</script>

<template>
  <div class="analises-page">
    <div class="analises-main">
      <KpiSection />

      <div class="analises-layout">
        <main class="analysis-panel">
          <div v-if="navigationError" class="analysis-error analysis-error--navigation">
            <i class="pi pi-exclamation-circle" />
            <span>{{ navigationError }}</span>
          </div>

          <div v-if="hasIgnoredFilters" class="analysis-scope-notice" role="status">
            <i class="pi pi-info-circle" aria-hidden="true" />
            <span>{{ CRM_ANALYSIS_FILTER_SCOPE_NOTICE }}</span>
          </div>

          <CrmPrescricoesMap
            :map-level="mapLevel"
            :map-data="mapData"
            :uf="selectedUf"
            :regiao-id="selectedRegiaoId"
            :selected-ibge7="selectedMunicipioIbge7"
            :escopo="mapResponse?.escopo ?? 'Brasil'"
            :qtd-medicos="mapResponse?.qtd_medicos ?? 0"
            :is-loading="isMapLoading"
            :error="mapError"
            @select-uf="onSelectUf"
            @select-municipio="onSelectMunicipio"
            @back="goBack"
          />

          <CrmPrescricoesRanking
            :rows="ranking"
            :escopo="rankingResponse?.escopo ?? 'Brasil'"
            :is-loading="rankingInitialLoading"
            :error="rankingError"
            :page-error="rankingPageError"
            :is-page-loading="rankingPageLoading"
            :total-records="rankingTotal"
            :first="rankingFirst"
            :page-size="rankingPageSize"
            @page="onRankingPage"
          />
        </main>

        <AnalysisSidebar />
      </div>
    </div>
  </div>
</template>

<style scoped>
.analises-page { --indicator-selector-width: 220px; display: flex; flex-direction: column; gap: 1rem; width: 100%; }
.analises-main { min-width: 0; width: 100%; display: flex; flex-direction: column; gap: 1rem; }
.analises-layout { display: flex; align-items: flex-start; gap: 1rem; width: 100%; }
.analysis-panel { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 1rem; padding-bottom: 1rem; }
.analysis-error { min-height: 180px; padding: 2rem; display: flex; align-items: center; justify-content: center; gap: .8rem; border: 1px solid color-mix(in srgb, var(--risk-high) 35%, var(--card-border)); border-radius: 12px; background: color-mix(in srgb, var(--risk-high) 7%, var(--card-bg)); color: var(--text-muted); text-align: left; }
.analysis-error > i { color: var(--risk-high); font-size: 1.35rem; }
.analysis-error strong, .analysis-error span { display: block; }
.analysis-error strong { color: var(--text-color-85); font-size: .84rem; font-weight: 600; }
.analysis-error span { margin-top: .25rem; font-size: .75rem; }
.analysis-error--navigation { min-height: auto; padding: .75rem 1rem; justify-content: flex-start; }
.analysis-scope-notice { min-width: 0; padding: .7rem .9rem; display: flex; align-items: flex-start; gap: .65rem; border: 1px solid color-mix(in srgb, var(--primary-color) 30%, var(--card-border)); border-radius: 12px; background: color-mix(in srgb, var(--primary-color) 7%, var(--card-bg)); color: var(--text-muted); font-size: .75rem; line-height: 1.45; }
.analysis-scope-notice > i { flex: 0 0 auto; margin-top: .1rem; color: var(--primary-color); font-size: .9rem; }
.analysis-scope-notice > span { min-width: 0; overflow-wrap: anywhere; }
</style>
