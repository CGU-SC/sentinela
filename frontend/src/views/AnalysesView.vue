<script setup>
import { computed, ref, watch } from 'vue';
import { useFilterStore } from '@/stores/filters';
import { useGeoStore } from '@/stores/geo';
import { useFetchAnalytics } from '@/composables/useFetchAnalytics';
import { useCrmPrescricoesAnalysis } from '@/composables/useCrmPrescricoesAnalysis';

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
const { data, isLoading, error } = useCrmPrescricoesAnalysis(mapLevel);

const selectedUf = computed(() => filterStore.selectedUF !== 'Todos' ? filterStore.selectedUF : null);
const selectedRegiaoId = computed(() => filterStore.selectedRegiaoSaude !== 'Todos' ? filterStore.selectedRegiaoSaude : null);
const mapData = computed(() => data.value?.mapa ?? []);
const ranking = computed(() => data.value?.ranking ?? []);

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
  const regionId = geoStore.getRegiaoByIbge7(idIbge7);
  if (regionId == null) {
    navigationError.value = 'Não foi possível localizar a Região de Saúde deste município.';
    return;
  }
  filterStore.selectedMunicipio = 'Todos';
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

          <CrmPrescricoesMap
            :map-level="mapLevel"
            :map-data="mapData"
            :uf="selectedUf"
            :regiao-id="selectedRegiaoId"
            :escopo="data?.escopo ?? 'Brasil'"
            :qtd-medicos="data?.qtd_medicos ?? 0"
            :is-loading="isLoading"
            :error="error"
            @select-uf="onSelectUf"
            @select-municipio="onSelectMunicipio"
            @back="goBack"
          />

          <CrmPrescricoesRanking
            :rows="ranking"
            :escopo="data?.escopo ?? 'Brasil'"
            :is-loading="isLoading"
            :error="error"
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
</style>
