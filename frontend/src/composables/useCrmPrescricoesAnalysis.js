import { computed, onScopeDispose, watch } from 'vue';
import { storeToRefs } from 'pinia';
import { useFilterStore } from '@/stores/filters';
import { useCrmPrescricoesAnalysisStore } from '@/stores/crmPrescricoesAnalysis';
import { useCrmFiltrosMedicoStore } from '@/stores/crmFiltrosMedico';
import { buildAnalyticsParams } from '@/stores/analytics';

// Filtros de texto esperam o fim da digitacao; selecoes pedem imediatamente.
const ESTABELECIMENTO_FETCH_DEBOUNCE_MS = 450;

export function getCrmMapLevel(filterStore) {
  if (filterStore.selectedRegiaoSaude && filterStore.selectedRegiaoSaude !== 'Todos') return 'regiao';
  if (filterStore.selectedUF && filterStore.selectedUF !== 'Todos') return 'municipio';
  return 'uf';
}

/**
 * Parâmetros das consultas de CRM de /analises: filtros globais (farmácias,
 * território, período) + filtros de médico da página + nível do mapa.
 * Fonte única da chave de cache (página e preparação da rota usam a mesma).
 */
export function buildCrmAnalysisParams(filterStore, filtrosMedicoStore, mapLevel) {
  return {
    ...buildAnalyticsParams(filterStore.apiParams),
    ...filtrosMedicoStore.apiParams,
    map_level: mapLevel,
  };
}

export function useCrmPrescricoesAnalysis(mapLevel) {
  const filterStore = useFilterStore();
  const filtrosMedicoStore = useCrmFiltrosMedicoStore();
  const analysisStore = useCrmPrescricoesAnalysisStore();
  const params = computed(() => buildCrmAnalysisParams(filterStore, filtrosMedicoStore, mapLevel.value));
  const paramsKey = computed(() => JSON.stringify(params.value));
  let timer = null;
  let firstRun = true;
  let lastEstabelecimentoKey = filterStore.estabelecimentoFilterKey;

  watch(
    paramsKey,
    (key) => {
      clearTimeout(timer);
      const estabelecimentoChanged = filterStore.estabelecimentoFilterKey !== lastEstabelecimentoKey;
      lastEstabelecimentoKey = filterStore.estabelecimentoFilterKey;
      // A preparacao da rota ja ativou e validou esses dados antes de montar a view.
      // Evita uma segunda consulta ao status do cache na entrada da pagina.
      const preparedOnEntry = firstRun
        && analysisStore.activeKey === key
        && analysisStore.cacheVersion !== null
        && analysisStore.cacheEntries[key]?.map
        && analysisStore.mapResponse
        && analysisStore.rankingResponseKey === key
        && analysisStore.rankingResponse
        && !analysisStore.isMapLoading
        && !analysisStore.isRankingLoading
        && !analysisStore.mapError
        && !analysisStore.rankingError;
      firstRun = false;
      if (preparedOnEntry) return;
      if (estabelecimentoChanged) {
        timer = setTimeout(() => analysisStore.activate({ ...params.value }), ESTABELECIMENTO_FETCH_DEBOUNCE_MS);
        return;
      }
      analysisStore.activate({ ...params.value });
    },
    { immediate: true, flush: 'post' },
  );

  onScopeDispose(() => clearTimeout(timer));

  return {
    ...storeToRefs(analysisStore),
    fetchAnalysis: () => analysisStore.activate({ ...params.value }),
    fetchRankingPage: (page, pageSize, sortField, sortOrder, medicoQuery) => analysisStore.fetchRankingPage(page, pageSize, sortField, sortOrder, medicoQuery),
  };
}
