/**
 * Centraliza a logica de busca dos dados de analytics.
 *
 * @param {Object} options
 * @param {boolean} options.includeFatorRisco - Incluir busca do grafico Fator Risco (default: false)
 * @param {boolean} options.includeProducaoSemestral - Incluir serie semestral de producao (default: false)
 * @param {Array<'kpis'|'ufs'|'municipios'>} options.secoes - Secoes do resumo que a tela exibe (obrigatorio)
 */
import { onScopeDispose, unref, watch } from 'vue';
import { useFilterStore } from '@/stores/filters';
import { useAnalyticsStore, buildAnalyticsParams } from '@/stores/analytics';

const ESTABELECIMENTO_FETCH_DEBOUNCE_MS = 450;

export function useFetchAnalytics({ secoes, includeFatorRisco = false, includeNationalContext = true, includeProducaoSemestral = false, includeAlertasPanorama = false, active = true } = {}) {
  if (!Array.isArray(secoes) || !secoes.length) {
    throw new Error('useFetchAnalytics exige as secoes do resumo usadas pela tela.');
  }
  const filterStore = useFilterStore();
  const analyticsStore = useAnalyticsStore();

  const getApiParams = () => ({ ...filterStore.apiParams });
  const isPeriodoValido = () => Boolean(filterStore.isPeriodoValido);
  const isActive = () => Boolean(unref(active));

  const fetchAll = () => {
    const filters = getApiParams();
    analyticsStore.fetchDashboardSummary(filters, secoes);
    if (includeFatorRisco) analyticsStore.fetchFatorRisco(filters);
    if (includeProducaoSemestral) analyticsStore.fetchProducaoSemestral(filters);
    if (includeAlertasPanorama) analyticsStore.fetchAlertasPanorama(filters);
  };

  const fetchNacionalIfNeeded = () => {
    if (
      !includeNationalContext ||
      !isPeriodoValido() ||
      !filterStore.selectedUF ||
      filterStore.selectedUF === 'Todos'
    ) {
      return;
    }
    analyticsStore.fetchSentinelaUFNacional(getApiParams());
  };

  const isFresh = () => {
    const apiReadyParams = buildAnalyticsParams(getApiParams());
    const currentHash = JSON.stringify(apiReadyParams);
    return analyticsStore.isDashboardFresh(currentHash, secoes);
  };

  let dashboardFirstRun = true;
  let nationalFirstRun = true;
  let estabelecimentoFetchTimer = null;
  let lastEstabelecimentoKey = filterStore.estabelecimentoFilterKey;

  watch(
    () => [filterStore.apiParamsKey, isActive()],
    ([, enabled], previous = []) => {
      clearTimeout(estabelecimentoFetchTimer);
      if (!enabled) return;
      const resumed = previous[1] === false;
      const run = () => {
        if (!isActive()) return;
        const skip = (dashboardFirstRun || resumed) && isFresh();
        if (isPeriodoValido()) {
          if (!skip) {
            fetchAll();
          } else {
            const filters = getApiParams();
            if (includeFatorRisco && !analyticsStore.fatorRisco.length) {
              analyticsStore.fetchFatorRisco(filters);
            }
            if (includeProducaoSemestral && !analyticsStore.producaoSemestral.length) {
              analyticsStore.fetchProducaoSemestral(filters);
            }
            if (includeAlertasPanorama && !analyticsStore.alertasPanorama) {
              analyticsStore.fetchAlertasPanorama(filters);
            }
          }
        }
        dashboardFirstRun = false;
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

  watch(
    () => [`${filterStore.nationalContextApiParamsKey}|uf=${filterStore.selectedUF !== 'Todos'}`, isActive()],
    ([, enabled], previous = []) => {
      if (!enabled) return;
      const skip = (nationalFirstRun || previous[1] === false) && isFresh();
      if (isPeriodoValido() && !skip) {
        fetchNacionalIfNeeded();
      }
      nationalFirstRun = false;
    },
    { immediate: true }
  );

  onScopeDispose(() => {
    clearTimeout(estabelecimentoFetchTimer);
  });

  return { fetchAll };
}
