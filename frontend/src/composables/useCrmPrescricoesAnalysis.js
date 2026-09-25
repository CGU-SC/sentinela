import { computed, onScopeDispose, ref, watch } from 'vue';
import axios from 'axios';
import { useFilterStore } from '@/stores/filters';
import { buildAnalyticsParams } from '@/stores/analytics';
import { API_ENDPOINTS } from '@/config/api';
import { CRM_ANALYSIS_ALLOWED_QUERY_PARAMS } from '@/config/constants';

const FETCH_DEBOUNCE_MS = 450;
const DEFAULT_RANKING_PAGE_SIZE = 25;
const CRM_ANALYSIS_ALLOWED_QUERY_PARAM_SET = new Set(CRM_ANALYSIS_ALLOWED_QUERY_PARAMS);

function responseError(err, fallback) {
  const status = err?.response?.status;
  if (status === 503) return 'Os dados gerenciais de prescrições ainda não estão disponíveis. Sincronize o módulo de análise de CRMs e tente novamente.';
  if (status === 422) return err?.response?.data?.detail || 'Os parâmetros da análise precisam ser revisados.';
  return fallback;
}

function assertMapResponse(payload) {
  if (!Array.isArray(payload?.mapa) || !Number.isInteger(payload?.qtd_medicos)) {
    throw new Error('Resposta da análise de CRMs sem mapa.');
  }
  if (!payload?.map_level || !payload?.escopo || !payload?.periodo_inicio || !payload?.periodo_fim) {
    throw new Error('Resposta do mapa de CRMs sem metadados obrigatórios.');
  }
}

function assertRankingResponse(payload) {
  if (!Array.isArray(payload?.ranking)
    || !Number.isInteger(payload?.qtd_medicos)
    || !Number.isInteger(payload?.ranking_page)
    || !Number.isInteger(payload?.ranking_page_size)) {
    throw new Error('Resposta do ranking de CRMs sem contrato completo.');
  }
}

function buildMapRequestParams(requestParams) {
  if (requestParams.map_level !== 'regiao') return requestParams;
  return Object.fromEntries(
    Object.entries(requestParams).filter(([key]) => key !== 'id_ibge7'),
  );
}

function buildCrmAnalysisParams(apiParams, mapLevel) {
  const analyticsParams = buildAnalyticsParams(apiParams);
  const supportedParams = Object.fromEntries(
    Object.entries(analyticsParams).filter(([key]) => CRM_ANALYSIS_ALLOWED_QUERY_PARAM_SET.has(key)),
  );
  return { ...supportedParams, map_level: mapLevel };
}

export function useCrmPrescricoesAnalysis(mapLevel) {
  const filterStore = useFilterStore();
  const mapResponse = ref(null);
  const rankingResponse = ref(null);
  const isMapLoading = ref(false);
  const isRankingLoading = ref(false);
  const mapError = ref(null);
  const rankingError = ref(null);
  const rankingPageError = ref(null);
  const rankingPage = ref(1);
  const rankingPageSize = ref(DEFAULT_RANKING_PAGE_SIZE);
  let timer = null;
  let analysisRequestId = 0;
  let rankingRequestId = 0;
  let activeRankingParams = null;

  const allAnalyticsParams = computed(() => buildAnalyticsParams(filterStore.apiParams));
  const params = computed(() => buildCrmAnalysisParams(filterStore.apiParams, mapLevel.value));
  const paramsKey = computed(() => JSON.stringify(params.value));
  const hasIgnoredFilters = computed(() => Object.keys(allAnalyticsParams.value).some(
    (key) => !CRM_ANALYSIS_ALLOWED_QUERY_PARAM_SET.has(key),
  ));

  async function loadMap(requestId, requestParams) {
    try {
      const mapRequestParams = buildMapRequestParams(requestParams);
      const response = await axios.get(API_ENDPOINTS.analyticsCrmPrescricoesAnalise, {
        params: {
          ...mapRequestParams,
          page: 1,
          page_size: DEFAULT_RANKING_PAGE_SIZE,
          include_map: true,
          map_only: true,
        },
      });
      if (requestId !== analysisRequestId) return;
      assertMapResponse(response.data);
      mapResponse.value = response.data;
    } catch (err) {
      if (requestId !== analysisRequestId) return;
      mapError.value = responseError(
        err,
        'Não foi possível carregar os dados do mapa de prescrições. Tente novamente em instantes.',
      );
    } finally {
      if (requestId === analysisRequestId) isMapLoading.value = false;
    }
  }

  async function loadInitialRanking(analysisId, rankingId, requestParams) {
    try {
      const response = await axios.get(API_ENDPOINTS.analyticsCrmPrescricoesAnalise, {
        params: {
          ...requestParams,
          page: 1,
          page_size: DEFAULT_RANKING_PAGE_SIZE,
          include_map: false,
          map_only: false,
        },
      });
      if (analysisId !== analysisRequestId || rankingId !== rankingRequestId) return;
      assertRankingResponse(response.data);
      rankingResponse.value = response.data;
      rankingPage.value = response.data.ranking_page;
      rankingPageSize.value = response.data.ranking_page_size;
    } catch (err) {
      if (analysisId !== analysisRequestId || rankingId !== rankingRequestId) return;
      rankingError.value = responseError(
        err,
        'Não foi possível carregar o ranking de médicos. Tente novamente em instantes.',
      );
    } finally {
      if (analysisId === analysisRequestId && rankingId === rankingRequestId) {
        isRankingLoading.value = false;
      }
    }
  }

  async function fetchAnalysis() {
    const currentAnalysisId = ++analysisRequestId;
    const currentRankingId = ++rankingRequestId;
    const requestParams = { ...params.value };

    mapResponse.value = null;
    rankingResponse.value = null;
    activeRankingParams = requestParams;
    isMapLoading.value = true;
    isRankingLoading.value = true;
    mapError.value = null;
    rankingError.value = null;
    rankingPageError.value = null;
    rankingPage.value = 1;
    rankingPageSize.value = DEFAULT_RANKING_PAGE_SIZE;

    await Promise.all([
      loadMap(currentAnalysisId, requestParams),
      loadInitialRanking(currentAnalysisId, currentRankingId, requestParams),
    ]);
  }

  async function fetchRankingPage(page, pageSize = rankingPageSize.value) {
    if (!rankingResponse.value || !activeRankingParams) {
      rankingPageError.value = 'O ranking ainda não foi carregado para receber uma nova página.';
      return;
    }
    if (!Number.isInteger(page) || page < 1) {
      rankingPageError.value = 'A página solicitada para o ranking é inválida.';
      return;
    }
    if (!Number.isInteger(pageSize) || pageSize < 1 || pageSize > 100) {
      rankingPageError.value = 'O tamanho solicitado para a página do ranking é inválido.';
      return;
    }

    const currentAnalysisId = analysisRequestId;
    const currentRankingId = ++rankingRequestId;
    isRankingLoading.value = true;
    rankingPageError.value = null;
    try {
      const response = await axios.get(API_ENDPOINTS.analyticsCrmPrescricoesAnalise, {
        params: {
          ...activeRankingParams,
          page,
          page_size: pageSize,
          include_map: false,
          map_only: false,
        },
      });
      if (currentAnalysisId !== analysisRequestId || currentRankingId !== rankingRequestId) return;
      assertRankingResponse(response.data);
      rankingResponse.value = response.data;
      rankingPage.value = response.data.ranking_page;
      rankingPageSize.value = response.data.ranking_page_size;
    } catch (err) {
      if (currentAnalysisId !== analysisRequestId || currentRankingId !== rankingRequestId) return;
      rankingPageError.value = responseError(
        err,
        'Não foi possível carregar a página solicitada do ranking.',
      );
    } finally {
      if (currentAnalysisId === analysisRequestId && currentRankingId === rankingRequestId) {
        isRankingLoading.value = false;
      }
    }
  }

  watch(
    paramsKey,
    () => {
      clearTimeout(timer);
      timer = setTimeout(fetchAnalysis, FETCH_DEBOUNCE_MS);
    },
    { immediate: true },
  );

  onScopeDispose(() => clearTimeout(timer));

  return {
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
    fetchAnalysis,
    fetchRankingPage,
  };
}
