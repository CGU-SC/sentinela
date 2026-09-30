import { defineStore } from 'pinia';
import axios from 'axios';
import { API_ENDPOINTS } from '@/config/api';

const DEFAULT_RANKING_PAGE_SIZE = 25;
const DEFAULT_RANKING_SORT_FIELD = 'taxa_prescricoes_dia';
const DEFAULT_RANKING_SORT_ORDER = 'desc';
const RANKING_SORT_FIELDS = new Set([
  'no_medico', 'taxa_prescricoes_dia', 'nu_prescricoes',
  'qtd_dias_com_prescricao', 'qtd_meses_ativos',
  'qtd_meses_alta_intensidade', 'percentual_meses_alta_intensidade',
  'nu_prescricoes_farmacias_filtradas', 'percentual_prescricoes_farmacias_filtradas',
]);
const MAX_CACHED_FILTERS = 8;
const MAX_CACHED_PAGES_PER_FILTER = 6;
const pendingMaps = new Map();
const pendingRankings = new Map();

class ContractError extends Error {}

function assertMapResponse(payload) {
  if (!Array.isArray(payload?.mapa) || !Number.isInteger(payload?.qtd_medicos)) {
    throw new ContractError('Resposta da análise de CRMs sem mapa.');
  }
  if (!payload.map_level || !payload.escopo || !payload.periodo_inicio || !payload.periodo_fim) {
    throw new ContractError('Resposta do mapa de CRMs sem metadados obrigatórios.');
  }
}

function assertRankingResponse(payload) {
  if (!Array.isArray(payload?.ranking)
    || !Number.isInteger(payload?.qtd_medicos)
    || !Number.isInteger(payload?.ranking_page)
    || !Number.isInteger(payload?.ranking_page_size)) {
    throw new ContractError('Resposta do ranking de CRMs sem contrato completo.');
  }
}

function responseError(err, message) {
  if (err instanceof ContractError) return err.message;
  const status = err?.response?.status;
  if (status === 503) return 'Os dados gerenciais de prescrições ainda não estão disponíveis. Sincronize o módulo de análise de CRMs e tente novamente.';
  if (status === 422) return err.response.data?.detail || 'Os parâmetros da análise precisam ser revisados.';
  return message;
}

function mapRequestParams(params) {
  if (params.map_level !== 'regiao') return params;
  return Object.fromEntries(Object.entries(params).filter(([key]) => key !== 'id_ibge7'));
}

function pageKey(page, pageSize, sortField, sortOrder, medicoQuery) {
  return JSON.stringify([page, pageSize, sortField, sortOrder, medicoQuery]);
}

function newEntry() {
  return {
    map: null,
    pages: {},
    pageOrder: [],
    lastPage: 1,
    lastPageSize: DEFAULT_RANKING_PAGE_SIZE,
    lastSortField: DEFAULT_RANKING_SORT_FIELD,
    lastSortOrder: DEFAULT_RANKING_SORT_ORDER,
    lastSearch: '',
  };
}

function rememberPage(entry, key, data) {
  entry.pages[key] = data;
  entry.pageOrder = entry.pageOrder.filter((item) => item !== key);
  entry.pageOrder.push(key);
  while (entry.pageOrder.length > MAX_CACHED_PAGES_PER_FILTER) {
    delete entry.pages[entry.pageOrder.shift()];
  }
}

export const useCrmPrescricoesAnalysisStore = defineStore('crmPrescricoesAnalysis', {
  state: () => ({
    cacheVersion: null,
    cacheEntries: {},
    cacheOrder: [],
    activeKey: null,
    activeParams: null,
    activationId: 0,
    rankingRequestId: 0,
    mapResponse: null,
    rankingResponse: null,
    rankingResponseKey: null,
    isMapLoading: false,
    isRankingLoading: false,
    isRankingPageLoading: false,
    mapError: null,
    rankingError: null,
    rankingPageError: null,
    rankingPage: 1,
    rankingPageSize: DEFAULT_RANKING_PAGE_SIZE,
    rankingSortField: DEFAULT_RANKING_SORT_FIELD,
    rankingSortOrder: DEFAULT_RANKING_SORT_ORDER,
    rankingSearch: '',
    rankingResponseSearch: '',
  }),
  actions: {
    touchEntry(key) {
      if (!this.cacheEntries[key]) this.cacheEntries[key] = newEntry();
      this.cacheOrder = this.cacheOrder.filter((item) => item !== key);
      this.cacheOrder.push(key);
      while (this.cacheOrder.length > MAX_CACHED_FILTERS) {
        const oldest = this.cacheOrder.shift();
        delete this.cacheEntries[oldest];
      }
      return this.cacheEntries[key];
    },

    resetCachedResponses() {
      this.cacheEntries = {};
      this.cacheOrder = [];
      this.mapResponse = null;
      this.rankingResponse = null;
      this.rankingResponseKey = null;
      this.rankingPage = 1;
      this.rankingPageSize = DEFAULT_RANKING_PAGE_SIZE;
      this.rankingSortField = DEFAULT_RANKING_SORT_FIELD;
      this.rankingSortOrder = DEFAULT_RANKING_SORT_ORDER;
      this.rankingResponseSearch = '';
    },

    async requestMap(key, params, version) {
      const requestKey = JSON.stringify([version, key]);
      let pending = pendingMaps.get(requestKey);
      if (!pending) {
        pending = axios.get(API_ENDPOINTS.analyticsCrmPrescricoesAnalise, {
          params: {
            ...mapRequestParams(params),
            page: 1,
            page_size: DEFAULT_RANKING_PAGE_SIZE,
            include_map: true,
            map_only: true,
          },
        }).then(({ data }) => {
          assertMapResponse(data);
          if (version === this.cacheVersion) this.touchEntry(key).map = data;
          return data;
        }).finally(() => pendingMaps.delete(requestKey));
        pendingMaps.set(requestKey, pending);
      }
      return pending;
    },

    async requestRanking(key, params, version, page, pageSize, sortField, sortOrder, medicoQuery) {
      const requestKey = JSON.stringify([version, key, page, pageSize, sortField, sortOrder, medicoQuery]);
      let pending = pendingRankings.get(requestKey);
      if (!pending) {
        pending = axios.get(API_ENDPOINTS.analyticsCrmPrescricoesAnalise, {
          params: {
            ...params,
            page,
            page_size: pageSize,
            sort_field: sortField,
            sort_order: sortOrder,
            medico_query: medicoQuery || undefined,
            include_map: false,
            map_only: false,
          },
        }).then(({ data }) => {
          assertRankingResponse(data);
          if (data.ranking_page !== page || data.ranking_page_size !== pageSize) {
            throw new ContractError('Resposta do ranking de CRMs com paginação divergente da solicitação.');
          }
          if (version === this.cacheVersion) {
            rememberPage(this.touchEntry(key), pageKey(page, pageSize, sortField, sortOrder, medicoQuery), data);
          }
          return data;
        }).finally(() => pendingRankings.delete(requestKey));
        pendingRankings.set(requestKey, pending);
      }
      return pending;
    },

    async loadMap(key, params, version, activationId) {
      try {
        const data = await this.requestMap(key, params, version);
        if (activationId === this.activationId && key === this.activeKey && version === this.cacheVersion) {
          this.mapResponse = data;
        }
      } catch (err) {
        if (activationId === this.activationId && key === this.activeKey) {
          this.mapError = responseError(err, 'Não foi possível carregar os dados do mapa de prescrições. Tente novamente em instantes.');
        }
      } finally {
        if (activationId === this.activationId && key === this.activeKey) this.isMapLoading = false;
      }
    },

    async loadRanking(key, params, version, activationId, rankingRequestId, page, pageSize, sortField, sortOrder, medicoQuery, isPageChange) {
      try {
        const data = await this.requestRanking(key, params, version, page, pageSize, sortField, sortOrder, medicoQuery);
        if (activationId === this.activationId && rankingRequestId === this.rankingRequestId
          && key === this.activeKey && version === this.cacheVersion) {
          this.rankingResponse = data;
          this.rankingResponseKey = key;
          this.rankingResponseSearch = medicoQuery;
          this.rankingPage = data.ranking_page;
          this.rankingPageSize = data.ranking_page_size;
          this.rankingSortField = sortField;
          this.rankingSortOrder = sortOrder;
          const entry = this.touchEntry(key);
          entry.lastPage = data.ranking_page;
          entry.lastPageSize = data.ranking_page_size;
          entry.lastSortField = sortField;
          entry.lastSortOrder = sortOrder;
          entry.lastSearch = medicoQuery;
        }
      } catch (err) {
        if (activationId === this.activationId && rankingRequestId === this.rankingRequestId
          && key === this.activeKey) {
          const message = isPageChange
            ? 'Não foi possível carregar a página solicitada do ranking.'
            : 'Não foi possível carregar o ranking de médicos. Tente novamente em instantes.';
          if (isPageChange) this.rankingPageError = responseError(err, message);
          else this.rankingError = responseError(err, message);
        }
      } finally {
        if (activationId === this.activationId && rankingRequestId === this.rankingRequestId
          && key === this.activeKey) {
          this.isRankingLoading = false;
          this.isRankingPageLoading = false;
        }
      }
    },

    async activate(params) {
      const key = JSON.stringify(params);
      const activationId = ++this.activationId;
      const rankingRequestId = ++this.rankingRequestId;
      const previousMap = this.mapResponse;
      const previousRanking = this.rankingResponse;
      const previousRankingKey = this.rankingResponseKey;
      const previousPage = this.rankingPage;
      const previousPageSize = this.rankingPageSize;
      const previousSortField = this.rankingSortField;
      const previousSortOrder = this.rankingSortOrder;
      const medicoQuery = this.rankingSearch;
      this.activeKey = key;
      this.activeParams = { ...params };
      const cached = this.cacheEntries[key];
      let page = cached?.lastSearch === medicoQuery ? cached.lastPage : 1;
      let pageSize = cached?.lastPageSize ?? DEFAULT_RANKING_PAGE_SIZE;
      let sortField = cached?.lastSortField ?? previousSortField;
      let sortOrder = cached?.lastSortOrder ?? previousSortOrder;
      if (!cached && key !== previousRankingKey
        && (sortField === 'nu_prescricoes_farmacias_filtradas'
          || sortField === 'percentual_prescricoes_farmacias_filtradas')) {
        sortField = DEFAULT_RANKING_SORT_FIELD;
        sortOrder = DEFAULT_RANKING_SORT_ORDER;
      }
      const cachedRanking = cached?.pages[pageKey(page, pageSize, sortField, sortOrder, medicoQuery)] ?? null;
      this.mapResponse = cached?.map ?? previousMap;
      this.rankingResponse = cachedRanking ?? previousRanking;
      this.rankingResponseKey = cachedRanking ? key : previousRankingKey;
      if (cachedRanking) this.rankingResponseSearch = medicoQuery;
      this.rankingPage = cachedRanking ? page : previousPage;
      this.rankingPageSize = cachedRanking ? pageSize : previousPageSize;
      this.rankingSortField = cachedRanking ? sortField : previousSortField;
      this.rankingSortOrder = cachedRanking ? sortOrder : previousSortOrder;
      this.isMapLoading = !cached?.map;
      this.isRankingLoading = !cachedRanking;
      this.isRankingPageLoading = false;
      this.mapError = null;
      this.rankingError = null;
      this.rankingPageError = null;

      try {
        const { data: status } = await axios.get(API_ENDPOINTS.cacheStatus);
        if (activationId !== this.activationId) return;
        if (typeof status?.cache_version !== 'string' || !status.cache_version) {
          throw new ContractError('Status do cache sem versão obrigatória.');
        }
        if (status.status === 'fetching' || status.status === 'processing') {
          throw new Error('A sincronização dos dados está em andamento. Aguarde sua conclusão.');
        }
        if (this.cacheVersion !== null && this.cacheVersion !== status.cache_version) {
          this.resetCachedResponses();
          page = 1;
          pageSize = DEFAULT_RANKING_PAGE_SIZE;
          sortField = DEFAULT_RANKING_SORT_FIELD;
          sortOrder = DEFAULT_RANKING_SORT_ORDER;
          this.isMapLoading = true;
          this.isRankingLoading = true;
        }
        this.cacheVersion = status.cache_version;
        const entry = this.touchEntry(key);
        const ranking = entry.pages[pageKey(page, pageSize, sortField, sortOrder, medicoQuery)];
        if (entry.map) this.mapResponse = entry.map;
        if (ranking) {
          this.rankingResponse = ranking;
          this.rankingResponseKey = key;
          this.rankingResponseSearch = medicoQuery;
          this.rankingPage = ranking.ranking_page;
          this.rankingPageSize = ranking.ranking_page_size;
          this.rankingSortField = sortField;
          this.rankingSortOrder = sortOrder;
        }
        this.isMapLoading = !entry.map;
        this.isRankingLoading = !ranking;
        await Promise.all([
          entry.map ? Promise.resolve() : this.loadMap(key, params, status.cache_version, activationId),
          ranking ? Promise.resolve() : this.loadRanking(
            key, params, status.cache_version, activationId, rankingRequestId,
            page, pageSize, sortField, sortOrder, medicoQuery, false,
          ),
        ]);
      } catch (err) {
        if (activationId !== this.activationId) return;
        const message = err instanceof ContractError || err.message === 'A sincronização dos dados está em andamento. Aguarde sua conclusão.'
          ? err.message
          : 'Não foi possível verificar a versão dos dados da análise.';
        this.mapError = message;
        this.rankingError = message;
        this.isMapLoading = false;
        this.isRankingLoading = false;
      }
    },

    async fetchRankingPage(
      page, pageSize = this.rankingPageSize,
      sortField = this.rankingSortField, sortOrder = this.rankingSortOrder,
      medicoQuery = this.rankingSearch,
    ) {
      const normalizedQuery = medicoQuery.trim();
      if (!this.rankingResponse || this.rankingResponseKey !== this.activeKey
        || !this.activeParams || this.cacheVersion === null) {
        this.rankingPageError = 'O ranking ainda não foi carregado para receber uma nova página.';
        return;
      }
      if (!Number.isInteger(page) || page < 1) {
        this.rankingPageError = 'A página solicitada para o ranking é inválida.';
        return;
      }
      if (!Number.isInteger(pageSize) || pageSize < 1 || pageSize > 100) {
        this.rankingPageError = 'O tamanho solicitado para a página do ranking é inválido.';
        return;
      }
      if (!RANKING_SORT_FIELDS.has(sortField) || !['asc', 'desc'].includes(sortOrder)) {
        this.rankingPageError = 'A ordenação solicitada para o ranking é inválida.';
        return;
      }
      if ((sortField === 'nu_prescricoes_farmacias_filtradas'
        || sortField === 'percentual_prescricoes_farmacias_filtradas')
        && !this.rankingResponse.filtro_farmacias_ativo) {
        this.rankingPageError = 'A ordenação por farmácias filtradas exige um filtro de farmácia ativo.';
        return;
      }
      if (normalizedQuery.length > 120) {
        this.rankingPageError = 'A busca deve ter no máximo 120 caracteres.';
        return;
      }

      const key = this.activeKey;
      const rankingRequestId = ++this.rankingRequestId;
      this.rankingSearch = normalizedQuery;
      const cached = this.cacheEntries[key]?.pages[pageKey(page, pageSize, sortField, sortOrder, normalizedQuery)];
      this.rankingPageError = null;
      if (cached) {
        this.isRankingLoading = false;
        this.isRankingPageLoading = false;
        this.rankingResponse = cached;
        this.rankingResponseKey = key;
        this.rankingResponseSearch = normalizedQuery;
        this.rankingPage = cached.ranking_page;
        this.rankingPageSize = cached.ranking_page_size;
        this.rankingSortField = sortField;
        this.rankingSortOrder = sortOrder;
        const entry = this.touchEntry(key);
        rememberPage(entry, pageKey(page, pageSize, sortField, sortOrder, normalizedQuery), cached);
        entry.lastPage = this.rankingPage;
        entry.lastPageSize = this.rankingPageSize;
        entry.lastSortField = sortField;
        entry.lastSortOrder = sortOrder;
        entry.lastSearch = normalizedQuery;
        return;
      }

      this.isRankingLoading = true;
      this.isRankingPageLoading = true;
      await this.loadRanking(key, { ...this.activeParams }, this.cacheVersion,
        this.activationId, rankingRequestId, page, pageSize, sortField, sortOrder, normalizedQuery, true);
    },
  },
});
