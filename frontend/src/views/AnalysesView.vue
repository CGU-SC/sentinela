<script setup>
import { computed, ref } from 'vue';
import { useFilterStore } from '@/stores/filters';
import { useGeoStore } from '@/stores/geo';
import { useFetchAnalytics } from '@/composables/useFetchAnalytics';
import { getCrmMapLevel, useCrmPrescricoesAnalysis } from '@/composables/useCrmPrescricoesAnalysis';
import { ANALISES_HIDDEN_KPI_LABELS } from '@/config/constants';

import AnalysisSidebar from './components/analises/AnalysisSidebar.vue';
import CrmPrescricoesMap from './components/analises/CrmPrescricoesMap.vue';
import CrmPrescricoesRanking from './components/analises/CrmPrescricoesRanking.vue';
import CrmHistoricoDialog from './components/analises/CrmHistoricoDialog.vue';
import KpiSection from './components/KpiSection.vue';

const filterStore = useFilterStore();
const geoStore = useGeoStore();
useFetchAnalytics({ includeFatorRisco: false, includeNationalContext: false });

// Nivel do mapa derivado dos filtros (fonte unica): muda junto com UF/regiao/
// municipio, sem estado intermediario incoerente nos pedidos.
const mapLevel = computed(() => getCrmMapLevel(filterStore));
const navigationError = ref(null);
const {
  mapResponse,
  rankingResponse,
  rankingResponseKey,
  activeKey,
  isMapLoading,
  isRankingLoading,
  isRankingPageLoading,
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
const selectedMunicipioNome = computed(() => {
  if (selectedMunicipioIbge7.value == null) return null;
  const nome = geoStore.getMunicipioNomeByIbge7(selectedMunicipioIbge7.value);
  if (!nome) throw new Error('Municipio selecionado sem nome no contrato de localidades.');
  return nome;
});
const selectedRegiaoNome = computed(() => {
  if (selectedRegiaoId.value == null) return null;
  const nome = geoStore.getRegiaoNomeById(selectedRegiaoId.value);
  if (!nome) throw new Error('Regiao de saude selecionada sem nome no contrato de localidades.');
  return nome;
});
const mapData = computed(() => mapResponse.value?.mapa ?? []);
const ranking = computed(() => rankingResponse.value?.ranking ?? []);
const rankingTotal = computed(() => rankingResponse.value?.qtd_medicos ?? 0);
const rankingFirst = computed(() => (rankingPage.value - 1) * rankingPageSize.value);
const rankingInitialLoading = computed(() => isRankingLoading.value && ranking.value.length === 0);
const rankingPageLoading = computed(() => isRankingPageLoading.value && ranking.value.length > 0);
const rankingIsStale = computed(() => Boolean(
  rankingResponse.value && rankingResponseKey.value !== activeKey.value,
));

function onSelectUf(uf) {
  navigationError.value = null;
  filterStore.selectedUF = uf;
  filterStore.selectedRegiaoSaude = 'Todos';
  filterStore.selectedMunicipio = 'Todos';
}

function onSelectMunicipio(idIbge7) {
  navigationError.value = null;
  if (idIbge7 == null) {
    filterStore.selectedMunicipio = 'Todos';
    return;
  }
  const regionId = geoStore.getRegiaoByIbge7(idIbge7);
  if (regionId == null) {
    navigationError.value = 'Não foi possível localizar a Região de Saúde deste município.';
    return;
  }
  filterStore.selectedMunicipio = String(idIbge7);
  filterStore.selectedRegiaoSaude = String(regionId);
}

function goBack() {
  navigationError.value = null;
  if (mapLevel.value === 'regiao') {
    filterStore.selectedRegiaoSaude = 'Todos';
    filterStore.selectedMunicipio = 'Todos';
    return;
  }
  filterStore.selectedUF = 'Todos';
  filterStore.selectedRegiaoSaude = 'Todos';
  filterStore.selectedMunicipio = 'Todos';
}

// Modal de histórico do CRM (clique numa linha do ranking), no período filtrado.
const historicoAberto = ref(false);
const historicoMedico = ref(null);
const historicoPeriodo = computed(() => ({
  inicio: filterStore.apiParams?.inicio ?? null,
  fim: filterStore.apiParams?.fim ?? null,
}));
function abrirHistorico(row) {
  historicoMedico.value = row;
  historicoAberto.value = true;
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
      <KpiSection :hidden-labels="ANALISES_HIDDEN_KPI_LABELS" />

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
            :selected-ibge7="selectedMunicipioIbge7"
            :selected-regiao-nome="selectedRegiaoNome"
            :selected-municipio-nome="selectedMunicipioNome"
            :qtd-medicos="mapResponse?.qtd_medicos ?? 0"
            :map-meta="mapResponse"
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
            :is-refreshing="isRankingLoading"
            :is-stale="rankingIsStale"
            :farmacias-filtradas="rankingResponse?.filtro_farmacias_ativo ?? false"
            :total-records="rankingTotal"
            :first="rankingFirst"
            :page-size="rankingPageSize"
            @page="onRankingPage"
            @select-medico="abrirHistorico"
          />
        </main>

        <AnalysisSidebar />
      </div>
    </div>

    <CrmHistoricoDialog
      v-model="historicoAberto"
      :medico="historicoMedico"
      :data-inicio="historicoPeriodo.inicio"
      :data-fim="historicoPeriodo.fim"
    />
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
