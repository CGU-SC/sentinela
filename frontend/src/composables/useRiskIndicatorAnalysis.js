import { onScopeDispose, unref, watch } from 'vue';
import { useFilterStore } from '@/stores/filters';
import { useRiskIndicatorsStore } from '@/stores/riskIndicators';

const ESTABELECIMENTO_FETCH_DEBOUNCE_MS = 450;

/**
 * Orquestra o fetch da analise de indicadores reagindo aos filtros globais.
 */
export function useRiskIndicatorAnalysis({ active = true, includeTable = true } = {}) {
  const filterStore = useFilterStore();
  const riskIndicatorsStore = useRiskIndicatorsStore();
  let estabelecimentoFetchTimer = null;
  let lastEstabelecimentoKey = filterStore.estabelecimentoFilterKey;
  const isActive = () => Boolean(unref(active));

  function getRiskIndicatorParams() {
    return { ...filterStore.indicadoresApiParams };
  }

  function getRiskIndicatorTableParams() {
    return { ...filterStore.indicadoresTabelaApiParams };
  }

  function fetchRiskIndicator(indicatorKey) {
    riskIndicatorsStore.fetchRiskIndicatorSummary(indicatorKey, getRiskIndicatorParams());
    if (includeTable) riskIndicatorsStore.fetchRiskIndicatorEstablishments(indicatorKey, getRiskIndicatorTableParams(), { page: 1 });
  }

  function fetchRiskIndicatorEstablishmentsPage(indicatorKey, tableState = {}) {
    riskIndicatorsStore.fetchRiskIndicatorEstablishments(indicatorKey, getRiskIndicatorTableParams(), tableState);
  }

  watch(
    () => [filterStore.indicadoresTabelaApiParamsKey, riskIndicatorsStore.preferencesLoaded, isActive()],
    ([, preferencesLoaded, enabled], previous = []) => {
      clearTimeout(estabelecimentoFetchTimer);
      if (!preferencesLoaded || !enabled) return;
      const resumed = previous[2] === false;

      const run = () => {
        if (!isActive()) return;
        const indicatorKey = riskIndicatorsStore.selectedRiskIndicator;
        if (!indicatorKey) return;
        const paramsKey = JSON.stringify({ indicador: indicatorKey, params: getRiskIndicatorParams() });
        const tableKey = JSON.stringify({
          indicador: indicatorKey,
          params: getRiskIndicatorTableParams(),
          page: 1,
          pageSize: riskIndicatorsStore.cnpjsRows,
          sortField: riskIndicatorsStore.cnpjsSortField,
          sortOrder: riskIndicatorsStore.cnpjsSortOrder,
        });
        if ((resumed || previous.length === 0)
          && riskIndicatorsStore.summaryParamsKey === paramsKey
          && !riskIndicatorsStore.isLoading
          && (!includeTable || (riskIndicatorsStore.tableParamsKey === tableKey && !riskIndicatorsStore.isTableLoading))) return;
        fetchRiskIndicator(indicatorKey);
      };

      const estabelecimentoChanged = filterStore.estabelecimentoFilterKey !== lastEstabelecimentoKey;
      lastEstabelecimentoKey = filterStore.estabelecimentoFilterKey;
      if (estabelecimentoChanged) {
        estabelecimentoFetchTimer = setTimeout(run, ESTABELECIMENTO_FETCH_DEBOUNCE_MS);
      } else {
        run();
      }
    },
    { immediate: true }
  );

  onScopeDispose(() => {
    clearTimeout(estabelecimentoFetchTimer);
  });

  return { fetchRiskIndicator, fetchRiskIndicatorEstablishmentsPage };
}
