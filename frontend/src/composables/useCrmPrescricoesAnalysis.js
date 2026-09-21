import { computed, onScopeDispose, ref, watch } from 'vue';
import axios from 'axios';
import { useFilterStore } from '@/stores/filters';
import { buildAnalyticsParams } from '@/stores/analytics';
import { API_ENDPOINTS } from '@/config/api';

const FETCH_DEBOUNCE_MS = 450;
const DEFAULT_RANKING_PAGE_SIZE = 25;

export function useCrmPrescricoesAnalysis(mapLevel) {
  const filterStore = useFilterStore();
  const data = ref(null);
  const isLoading = ref(false);
  const isRankingLoading = ref(false);
  const error = ref(null);
  const rankingError = ref(null);
  const rankingPage = ref(1);
  const rankingPageSize = ref(DEFAULT_RANKING_PAGE_SIZE);
  let timer = null;
  let requestId = 0;

  const params = computed(() => ({
    ...buildAnalyticsParams(filterStore.apiParams),
    map_level: mapLevel.value,
  }));

  async function fetchAnalysis() {
    const currentRequest = ++requestId;
    isLoading.value = true;
    isRankingLoading.value = false;
    error.value = null;
    rankingError.value = null;
    try {
      const response = await axios.get(API_ENDPOINTS.analyticsCrmPrescricoesAnalise, {
        params: {
          ...params.value,
          page: 1,
          page_size: DEFAULT_RANKING_PAGE_SIZE,
          include_map: true,
        },
      });
      if (currentRequest !== requestId) return;
      if (!Array.isArray(response.data?.ranking) || !Array.isArray(response.data?.mapa)) {
        throw new Error('Resposta da análise de CRMs sem ranking ou mapa.');
      }
      if (!Number.isInteger(response.data?.qtd_medicos)
        || !Number.isInteger(response.data?.ranking_page)
        || !Number.isInteger(response.data?.ranking_page_size)) {
        throw new Error('Resposta da análise de CRMs sem metadados de paginação.');
      }
      data.value = response.data;
      rankingPage.value = response.data.ranking_page;
      rankingPageSize.value = response.data.ranking_page_size;
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

  async function fetchRankingPage(page, pageSize = rankingPageSize.value) {
    if (!data.value) {
      rankingError.value = 'O ranking ainda não foi carregado para receber uma nova página.';
      return;
    }
    if (!Number.isInteger(page) || page < 1) {
      rankingError.value = 'A página solicitada para o ranking é inválida.';
      return;
    }
    if (!Number.isInteger(pageSize) || pageSize < 1 || pageSize > 100) {
      rankingError.value = 'O tamanho solicitado para a página do ranking é inválido.';
      return;
    }

    const currentRequest = ++requestId;
    isRankingLoading.value = true;
    rankingError.value = null;
    try {
      const response = await axios.get(API_ENDPOINTS.analyticsCrmPrescricoesAnalise, {
        params: {
          ...params.value,
          page,
          page_size: pageSize,
          include_map: false,
        },
      });
      if (currentRequest !== requestId) return;
      if (!Array.isArray(response.data?.ranking)
        || !Number.isInteger(response.data?.qtd_medicos)
        || !Number.isInteger(response.data?.ranking_page)
        || !Number.isInteger(response.data?.ranking_page_size)) {
        throw new Error('Resposta da página do ranking sem contrato completo.');
      }
      if (!Array.isArray(data.value.mapa)) {
        throw new Error('O mapa da análise não está disponível para preservar a tela.');
      }
      data.value = {
        ...data.value,
        ...response.data,
        mapa: data.value.mapa,
      };
      rankingPage.value = response.data.ranking_page;
      rankingPageSize.value = response.data.ranking_page_size;
    } catch (err) {
      if (currentRequest !== requestId) return;
      const status = err?.response?.status;
      if (status === 422) {
        rankingError.value = err?.response?.data?.detail || 'Os parâmetros da página do ranking precisam ser revisados.';
      } else {
        rankingError.value = 'Não foi possível carregar a página solicitada do ranking.';
      }
    } finally {
      if (currentRequest === requestId) isRankingLoading.value = false;
    }
  }

  watch(
    () => [filterStore.apiParamsKey, mapLevel.value],
    () => {
      clearTimeout(timer);
      rankingPage.value = 1;
      timer = setTimeout(fetchAnalysis, FETCH_DEBOUNCE_MS);
    },
    { immediate: true },
  );

  onScopeDispose(() => clearTimeout(timer));

  return {
    data,
    isLoading,
    isRankingLoading,
    error,
    rankingError,
    rankingPage,
    rankingPageSize,
    fetchAnalysis,
    fetchRankingPage,
  };
}
