import { defineStore } from 'pinia';
import axios from 'axios';
import { API_ENDPOINTS } from '@/config/api';

/**
 * Abas mensais do ranking de médicos (/analises):
 * - "Por mês": uma linha por médico e mês (GET /crm-prescricoes-mensal);
 * - "Linha do tempo": série mensal dos médicos da página do ranking
 *   (GET /crm-prescricoes-serie-mensal).
 */
export const CRM_RANKING_TABS = Object.freeze(['resumo', 'linha', 'mes']);
const DEFAULT_PAGE_SIZE = 25;
const DEFAULT_SORT_FIELD = 'razao_p95';
const DEFAULT_SORT_ORDER = 'desc';
const MENSAL_SORT_FIELDS = new Set(['razao_p95', 'taxa_prescricoes_dia', 'nu_prescricoes', 'competencia']);
const SERIE_PARAM_KEYS = ['data_inicio', 'data_fim', 'uf', 'regiao_id', 'id_ibge7'];
const MAX_CACHED = 24;
const pageCache = new Map();
const serieCache = new Map();

class ContractError extends Error {}

function lruGet(map, key) {
  if (!map.has(key)) return null;
  const value = map.get(key);
  map.delete(key);
  map.set(key, value);
  return value;
}

function lruSet(map, key, value) {
  map.delete(key);
  map.set(key, value);
  while (map.size > MAX_CACHED) map.delete(map.keys().next().value);
}

function responseError(err, fallback) {
  if (err instanceof ContractError) return err.message;
  const detail = err?.response?.data?.detail;
  const status = err?.response?.status;
  if ((status === 422 || status === 503) && typeof detail === 'string') return detail;
  return fallback;
}

// map_level so muda o mapa; fora da chave para nao repetir consultas iguais.
function mensalParams(params) {
  return Object.fromEntries(Object.entries(params).filter(([key]) => key !== 'map_level'));
}

function assertMensal(data, page, pageSize) {
  if (!Array.isArray(data?.linhas) || !Number.isInteger(data?.qtd_linhas)
    || data?.page !== page || data?.page_size !== pageSize || !data?.escopo) {
    throw new ContractError('Resposta da visão mensal do ranking sem contrato completo.');
  }
}

function assertSerie(data, ids) {
  if (!Array.isArray(data?.meses) || !data.meses.length || !Array.isArray(data?.medicos)) {
    throw new ContractError('Resposta da série mensal sem eixo de meses ou médicos.');
  }
  const recebidos = data.medicos.map((m) => m.id_medico);
  if (recebidos.length !== ids.length || recebidos.some((id, i) => id !== ids[i])) {
    throw new ContractError('Série mensal com médicos diferentes da página do ranking.');
  }
}

export const useCrmPrescricoesMensalStore = defineStore('crmPrescricoesMensal', {
  state: () => ({
    tab: 'resumo',
    // Aba "Por mês"
    mensalParamsKey: null,
    mensalResponse: null,
    mensalLoading: false,
    mensalError: null,
    mensalPage: 1,
    mensalPageSize: DEFAULT_PAGE_SIZE,
    mensalSortField: DEFAULT_SORT_FIELD,
    mensalSortOrder: DEFAULT_SORT_ORDER,
    mensalSearch: '',
    mensalRequestId: 0,
    // Aba "Linha do tempo"
    serieResponse: null,
    serieResponseKey: null,
    serieLoading: false,
    serieError: null,
    serieRequestId: 0,
  }),
  actions: {
    setTab(tab) {
      if (!CRM_RANKING_TABS.includes(tab)) throw new Error(`Aba do ranking de CRMs inválida: ${tab}`);
      this.tab = tab;
    },

    /** Recorte (filtros + busca) ativo: volta à 1ª página quando muda. */
    activateMensal(params, search, version) {
      const paramsKey = JSON.stringify([version, mensalParams(params), search]);
      if (paramsKey === this.mensalParamsKey && this.mensalResponse) return;
      const page = paramsKey === this.mensalParamsKey ? this.mensalPage : 1;
      this.mensalParamsKey = paramsKey;
      this.mensalSearch = search;
      return this.loadMensal(params, version, page, this.mensalPageSize, this.mensalSortField, this.mensalSortOrder);
    },

    async loadMensal(params, version, page, pageSize, sortField, sortOrder) {
      if (!Number.isInteger(page) || page < 1 || !Number.isInteger(pageSize) || pageSize < 1 || pageSize > 100) {
        this.mensalError = 'Página inválida para a visão mensal.';
        return;
      }
      if (!MENSAL_SORT_FIELDS.has(sortField) || !['asc', 'desc'].includes(sortOrder)) {
        this.mensalError = 'Ordenação inválida para a visão mensal.';
        return;
      }
      const requestParams = {
        ...mensalParams(params),
        page,
        page_size: pageSize,
        sort_field: sortField,
        sort_order: sortOrder,
        medico_query: this.mensalSearch || undefined,
      };
      const key = JSON.stringify([version, requestParams]);
      const requestId = ++this.mensalRequestId;
      this.mensalError = null;
      const cached = lruGet(pageCache, key);
      if (cached) {
        this.mensalResponse = cached;
        this.mensalPage = page;
        this.mensalPageSize = pageSize;
        this.mensalSortField = sortField;
        this.mensalSortOrder = sortOrder;
        this.mensalLoading = false;
        return;
      }
      this.mensalLoading = true;
      try {
        const { data } = await axios.get(API_ENDPOINTS.analyticsCrmPrescricoesMensal, { params: requestParams });
        assertMensal(data, page, pageSize);
        lruSet(pageCache, key, data);
        if (requestId !== this.mensalRequestId) return;
        this.mensalResponse = data;
        this.mensalPage = page;
        this.mensalPageSize = pageSize;
        this.mensalSortField = sortField;
        this.mensalSortOrder = sortOrder;
      } catch (err) {
        if (requestId !== this.mensalRequestId) return;
        this.mensalError = responseError(err, 'Não foi possível carregar a visão mensal do ranking.');
      } finally {
        if (requestId === this.mensalRequestId) this.mensalLoading = false;
      }
    },

    async loadSerie(params, ids, version) {
      const scope = Object.fromEntries(SERIE_PARAM_KEYS.filter((k) => params[k] != null).map((k) => [k, params[k]]));
      const key = JSON.stringify([version, scope, ids]);
      if (key === this.serieResponseKey && this.serieResponse) return;
      const requestId = ++this.serieRequestId;
      this.serieError = null;
      const cached = lruGet(serieCache, key);
      if (cached) {
        this.serieResponse = cached;
        this.serieResponseKey = key;
        this.serieLoading = false;
        return;
      }
      this.serieLoading = true;
      try {
        const { data } = await axios.get(API_ENDPOINTS.analyticsCrmPrescricoesSerieMensal, {
          params: { ...scope, ids: ids.join(',') },
        });
        assertSerie(data, ids);
        lruSet(serieCache, key, data);
        if (requestId !== this.serieRequestId) return;
        this.serieResponse = data;
        this.serieResponseKey = key;
      } catch (err) {
        if (requestId !== this.serieRequestId) return;
        this.serieError = responseError(err, 'Não foi possível carregar a série mensal dos médicos.');
      } finally {
        if (requestId === this.serieRequestId) this.serieLoading = false;
      }
    },
  },
});
