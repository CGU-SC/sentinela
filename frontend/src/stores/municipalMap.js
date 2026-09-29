import { defineStore } from 'pinia';
import axios from 'axios';
import { API_ENDPOINTS } from '@/config/api';

let pendingRequest = null;

export const useMunicipalMapStore = defineStore('municipalMap', {
  state: () => ({
    rows: [],
    loadedKey: null,
    isLoading: false,
    error: null,
  }),
  actions: {
    useDashboardRows(key, rows) {
      if (!Array.isArray(rows)) throw new Error('Resumo do dashboard sem resultado_municipios.');
      this.rows = rows;
      this.loadedKey = key;
      this.error = null;
      this.isLoading = false;
    },
    async load(key, params) {
      if (this.loadedKey === key && !this.error) return;
      if (pendingRequest?.key === key) return pendingRequest.promise;

      this.isLoading = true;
      this.error = null;
      const promise = axios.get(API_ENDPOINTS.analyticsResumo, { params })
        .then(({ data }) => {
          if (!Array.isArray(data?.resultado_municipios)) {
            throw new Error('Contrato invalido em analytics/resumo: resultado_municipios ausente.');
          }
          if (pendingRequest?.key !== key) return;
          this.rows = data.resultado_municipios;
          this.loadedKey = key;
        })
        .catch((error) => {
          if (pendingRequest?.key !== key) return;
          console.error('Erro ao buscar municipios para o mapa:', error);
          this.error = 'Não foi possível carregar a base municipal do mapa.';
          throw error;
        })
        .finally(() => {
          if (pendingRequest?.key !== key) return;
          pendingRequest = null;
          this.isLoading = false;
        });
      pendingRequest = { key, promise };
      return promise;
    },
  },
});
