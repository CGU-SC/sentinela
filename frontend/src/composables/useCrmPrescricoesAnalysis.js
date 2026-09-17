import { computed, onScopeDispose, ref, watch } from 'vue';
import axios from 'axios';
import { useFilterStore } from '@/stores/filters';
import { buildAnalyticsParams } from '@/stores/analytics';
import { API_ENDPOINTS } from '@/config/api';

const FETCH_DEBOUNCE_MS = 450;

export function useCrmPrescricoesAnalysis(mapLevel) {
  const filterStore = useFilterStore();
  const data = ref(null);
  const isLoading = ref(false);
  const error = ref(null);
  let timer = null;
  let requestId = 0;

  const params = computed(() => ({
    ...buildAnalyticsParams(filterStore.apiParams),
    map_level: mapLevel.value,
  }));

  async function fetchAnalysis() {
    const currentRequest = ++requestId;
    isLoading.value = true;
    error.value = null;
    try {
      const response = await axios.get(API_ENDPOINTS.analyticsCrmPrescricoesAnalise, {
        params: params.value,
      });
      if (currentRequest !== requestId) return;
      data.value = response.data;
    } catch (err) {
      if (currentRequest !== requestId) return;
      data.value = null;
      const status = err?.response?.status;
      if (status === 503) {
        error.value = 'Os dados gerenciais de prescrições ainda não estão disponíveis. Sincronize o módulo de análise de CRMs e tente novamente.';
      } else if (status === 422) {
        error.value = err?.response?.data?.detail || 'Os parâmetros da análise precisam ser revisados.';
      } else {
        error.value = 'Não foi possível carregar os dados da análise de CRMs. Tente novamente em instantes.';
      }
    } finally {
      if (currentRequest === requestId) isLoading.value = false;
    }
  }

  watch(
    () => [filterStore.apiParamsKey, mapLevel.value],
    () => {
      clearTimeout(timer);
      timer = setTimeout(fetchAnalysis, FETCH_DEBOUNCE_MS);
    },
    { immediate: true },
  );

  onScopeDispose(() => clearTimeout(timer));

  return { data, isLoading, error, fetchAnalysis };
}
