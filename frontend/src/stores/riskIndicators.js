import { defineStore } from 'pinia';
import axios from 'axios';
import { API_ENDPOINTS } from '@/config/api';

let summaryAbortController = null;
let cnpjsAbortController = null;
let pendingPreferences = null;

export const useRiskIndicatorsStore = defineStore('riskIndicators', {
  state: () => ({
    /** Chave do indicador de risco selecionado. Restaurado das preferencias para manter o foco do auditor. */
    selectedRiskIndicator: null,
    preferencesLoaded: false,
    preferencesError: null,
    /** KPIs de resumo: total_critico, total_atencao, total_normal, total_sem_dados, mediana_reg, pct_acima_limiar */
    kpis: null,
    /** KPIs do escopo da tabela, util para filtro municipal sem perder o mapa da UF/regiao. */
    cnpjKpis: null,
    /** Array de { municipio, uf, id_ibge7, total_cnpjs, total_critico, pct_critico } */
    municipios: [],
    /** Identifica o recorte da ultima analise municipal concluida. */
    summaryParamsKey: null,
    /** Pagina atual de CNPJs ranqueados no backend. */
    cnpjs: [],
    tableParamsKey: null,
    cnpjsTotal: 0,
    cnpjsPage: 1,
    cnpjsRows: 20,
    cnpjsSortField: 'val_sem_comp',
    cnpjsSortOrder: -1,
    isLoading: false,
    isTableLoading: false,
    summaryError: null,
    tableError: null,
  }),

  actions: {
    async loadPreferences() {
      if (this.preferencesLoaded) return;
      if (pendingPreferences) return pendingPreferences;
      pendingPreferences = axios.get(API_ENDPOINTS.preferences)
        .then(({ data }) => {
          const ui = data?.ui;
          if (!ui || typeof ui !== 'object'
            || (ui.selectedRiskIndicator != null && typeof ui.selectedRiskIndicator !== 'string')) {
            throw new Error('Preferencias sem contrato para o indicador selecionado.');
          }
          this.selectedRiskIndicator = ui.selectedRiskIndicator?.trim() || null;
          this.preferencesLoaded = true;
          this.preferencesError = null;
        })
        .catch((error) => {
          console.error('[riskIndicators] Nao foi possivel carregar preferencias do indicador:', error);
          this.preferencesError = 'Não foi possível carregar as preferências do indicador.';
          throw error;
        })
        .finally(() => { pendingPreferences = null; });
      return pendingPreferences;
    },

    async saveSelectedRiskIndicator() {
      try {
        await axios.put(API_ENDPOINTS.preferencesUi, {
          ui: {
            selectedRiskIndicator: this.selectedRiskIndicator,
          },
        });
      } catch (error) {
        console.warn('[riskIndicators] Nao foi possivel salvar indicador selecionado:', error);
      }
    },

    setSelectedRiskIndicator(indicador) {
      if (!indicador) return;
      if (this.selectedRiskIndicator === indicador) return;
      this.selectedRiskIndicator = indicador;
      this.saveSelectedRiskIndicator();
    },

    async fetchRiskIndicatorSummary(indicador, params = {}) {
      if (!indicador) return;
      const paramsKey = JSON.stringify({ indicador, params });
      this.setSelectedRiskIndicator(indicador);
      this.isLoading = true;
      this.summaryError = null;

      summaryAbortController?.abort();
      const requestController = new AbortController();
      summaryAbortController = requestController;

      try {
        const response = await axios.get(API_ENDPOINTS.analyticsIndicadoresAnalise, {
          params: { indicador, ...params },
          signal: requestController.signal,
        });

        if (requestController !== summaryAbortController) return;
        if (!Array.isArray(response.data?.municipios) || !response.data?.kpis
          || typeof response.data.kpis !== 'object') {
          throw new Error('Contrato invalido em indicadores-analise: KPIs ou municipios ausentes.');
        }
        this.kpis = response.data.kpis;
        this.municipios = response.data.municipios;
        this.summaryParamsKey = paramsKey;
      } catch (err) {
        if (axios.isCancel(err)) {
          return;
        }
        if (requestController !== summaryAbortController) return;
        console.error('Erro ao buscar analise de indicadores:', err);
        this.summaryError = 'Nao foi possivel carregar a analise do indicador.';
      } finally {
        if (requestController === summaryAbortController) {
          summaryAbortController = null;
          this.isLoading = false;
        }
      }
    },

    async fetchRiskIndicatorEstablishments(indicador, params = {}, tableState = {}) {
      if (!indicador) return;
      this.setSelectedRiskIndicator(indicador);

      const page = tableState.page ?? this.cnpjsPage;
      const pageSize = tableState.pageSize ?? this.cnpjsRows;
      const sortField = tableState.sortField ?? this.cnpjsSortField;
      const sortOrder = tableState.sortOrder ?? this.cnpjsSortOrder;
      const paramsKey = JSON.stringify({ indicador, params, page, pageSize, sortField, sortOrder });

      this.isTableLoading = true;
      this.tableError = null;

      cnpjsAbortController?.abort();
      const requestController = new AbortController();
      cnpjsAbortController = requestController;

      try {
        const response = await axios.get(API_ENDPOINTS.analyticsIndicadoresAnaliseCnpjs, {
          params: {
            indicador,
            ...params,
            page,
            page_size: pageSize,
            sort_field: sortField,
            sort_order: sortOrder === 1 ? 'asc' : 'desc',
          },
          signal: requestController.signal,
        });

        if (requestController !== cnpjsAbortController) return;
        if (!Array.isArray(response.data?.items) || !Number.isInteger(response.data?.total)
          || response.data?.page !== page || response.data?.page_size !== pageSize
          || typeof response.data?.sort_field !== 'string'
          || !['asc', 'desc'].includes(response.data?.sort_order)) {
          throw new Error('Contrato invalido em indicadores-analise/cnpjs: pagina ausente ou divergente.');
        }
        this.cnpjs = response.data.items;
        this.cnpjKpis = response.data.kpis ?? null;
        this.cnpjsTotal = response.data.total;
        this.cnpjsPage = response.data.page;
        this.cnpjsRows = response.data.page_size;
        this.cnpjsSortField = response.data.sort_field;
        this.cnpjsSortOrder = response.data.sort_order === 'asc' ? 1 : -1;
        this.tableParamsKey = paramsKey;
      } catch (err) {
        if (axios.isCancel(err)) {
          return;
        }
        if (requestController !== cnpjsAbortController) return;
        console.error('Erro ao buscar CNPJs do indicador:', err);
        this.tableError = 'Nao foi possivel carregar a tabela de farmacias do indicador.';
      } finally {
        if (requestController === cnpjsAbortController) {
          cnpjsAbortController = null;
          this.isTableLoading = false;
        }
      }
    },

    reset() {
      summaryAbortController?.abort();
      cnpjsAbortController?.abort();
      summaryAbortController = null;
      cnpjsAbortController = null;
      this.selectedRiskIndicator = null;
      this.saveSelectedRiskIndicator();
      this.kpis = null;
      this.cnpjKpis = null;
      this.municipios = [];
      this.summaryParamsKey = null;
      this.cnpjs = [];
      this.tableParamsKey = null;
      this.cnpjsTotal = 0;
      this.cnpjsPage = 1;
      this.cnpjsRows = 20;
      this.cnpjsSortField = 'val_sem_comp';
      this.cnpjsSortOrder = -1;
      this.isLoading = false;
      this.isTableLoading = false;
      this.summaryError = null;
      this.tableError = null;
    },
  },
});
