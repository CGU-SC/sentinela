import { defineStore } from 'pinia';
import { requestResumo } from '@/stores/analytics';

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
      const promise = requestResumo(params, ['municipios'])
        .then((data) => {
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
