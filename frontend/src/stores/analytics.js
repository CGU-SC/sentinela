import { defineStore } from 'pinia';
import axios from 'axios';
import { API_ENDPOINTS } from '@/config/api';
import { KPI_CONFIGS, DEFAULT_KPI_STYLE } from '@/config/uiConfig';
import { FILTER_ALL_VALUE, KPI_LABEL_MAP, KPI_PRIORITY_ORDER } from '@/config/constants';
import { RISK_COLORS } from '@/config/colors';
import { RISK_THRESHOLDS } from '@/config/riskConfig';

let dashboardAbortController = null;
let fatorRiscoAbortController = null;
let nacionalAbortController = null;
let producaoSemestralAbortController = null;
let cacheStatusAbortController = null;
let alertasPanoramaAbortController = null;
let dashboardRequestSeq = 0;
let fatorRiscoRequestSeq = 0;
let nacionalRequestSeq = 0;
let producaoSemestralRequestSeq = 0;
let cacheStatusRequestSeq = 0;
let alertasPanoramaRequestSeq = 0;

/**
 * Constrói o objeto de parâmetros para as APIs de analytics.
 * Extrai lógica duplicada que existia em fetchDashboardSummary e fetchFatorRisco.
 */
export function buildAnalyticsParams(filters = {}) {
  const {
    inicio = null,
    fim = null,
    percMin = null,
    percMax = null,
    valMin = null,
    uf = null,
    regiaoId = null,
    idIbge7 = null,
    situacaoRf = null,
    conexaoMs = null,
    porteEmpresa = null,
    grandeRede = null,
    cnpjRaiz = null,
    unidadePf = null,
    estabelecimento = null,
    parTeia = null,
    socioBeneficio = null,
    socioEsocial = null,
    cnaeIncompativel = false,
    socioIdadeAtipica = false,
    socioFalecido = false,
    volumeAtipicoEnabled = false,
    volumeAtipicoPercentual = null,
    dispersaoUfSemFronteiraEnabled = false,
    dispersaoUfSemFronteiraPercentual = null,
  } = filters || {};

  const params = {};
  if (inicio) params.data_inicio = inicio;
  if (fim) params.data_fim = fim;
  if (percMin !== null && percMin !== 0) params.perc_min = percMin;
  if (percMax !== null && percMax !== 100) params.perc_max = percMax;
  if (valMin !== null && valMin > 0) params.val_min = valMin;
  if (uf && uf !== FILTER_ALL_VALUE) params.uf = uf;
  if (regiaoId !== null && regiaoId !== undefined) params.regiao_id = regiaoId;
  if (idIbge7 !== null && idIbge7 !== undefined) params.id_ibge7 = idIbge7;
  if (situacaoRf) params.situacao_rf = situacaoRf;
  if (conexaoMs) params.conexao_ms = conexaoMs;
  if (porteEmpresa) params.porte_empresa = porteEmpresa;
  if (grandeRede) params.grande_rede = grandeRede;
  if (cnpjRaiz) params.cnpj_raiz = cnpjRaiz;
  if (unidadePf) params.unidade_pf = unidadePf;
  if (estabelecimento) params.estabelecimento = estabelecimento;
  if (parTeia) params.par_teia = parTeia;
  if (socioBeneficio) params.socio_beneficio = socioBeneficio;
  if (socioEsocial) params.socio_esocial = socioEsocial;
  if (cnaeIncompativel) params.cnae_incompativel = cnaeIncompativel;
  if (socioIdadeAtipica) params.socio_idade_atipica = socioIdadeAtipica;
  if (socioFalecido) params.socio_falecido = socioFalecido;
  if (volumeAtipicoEnabled) {
    params.volume_atipico = true;
    if (volumeAtipicoPercentual !== null && volumeAtipicoPercentual !== undefined) {
      params.volume_atipico_limite = volumeAtipicoPercentual;
    }
  }
  if (dispersaoUfSemFronteiraEnabled) {
    params.dispersao_uf_sem_fronteira = true;
    if (dispersaoUfSemFronteiraPercentual !== null && dispersaoUfSemFronteiraPercentual !== undefined) {
      params.dispersao_uf_sem_fronteira_limite = dispersaoUfSemFronteiraPercentual;
    }
  }
  return params;
}

export const useAnalyticsStore = defineStore('analytics', {
  state: () => ({
    kpis: [],
    resultadoSentinelaUF: [],
    resultadoSentinelaUFNacional: [], // dados de todas as UFs — só atualiza sem filtro de UF
    resultadoMunicipios: [],
    resultadoCnpjs: [],
    fatorRisco: [],
    producaoSemestral: [],
    cacheStatus: null,
    alertasPanorama: null,
    alertasPanoramaLoading: false,
    isLoading: false,
    fatorRiscoLoading: false,
    producaoSemestralLoading: false,
    error: null,
    lastSync: null,
    lastParamsHash: null
  }),

  actions: {
    async fetchDashboardSummary(filters = {}) {
      const params = buildAnalyticsParams(filters);
      
      // Gera um hash simples (string JSON) dos parâmetros para comparar
      const currentParamsHash = JSON.stringify(params);
      const requestId = ++dashboardRequestSeq;
      if (dashboardAbortController) {
        dashboardAbortController.abort();
      }
      dashboardAbortController = new AbortController();

      this.isLoading = true;
      this.error = null;
      try {
        const response = await axios.get(API_ENDPOINTS.analyticsResumo, {
          params,
          signal: dashboardAbortController.signal,
        });
        if (requestId !== dashboardRequestSeq) return;
        this.kpis = response.data.kpis;
        this.resultadoSentinelaUF = response.data.resultado_sentinela_uf;
        if (!filters.uf || filters.uf === FILTER_ALL_VALUE) {
          this.resultadoSentinelaUFNacional = response.data.resultado_sentinela_uf;
        }
        this.resultadoMunicipios = response.data.resultado_municipios || [];
        this.resultadoCnpjs = response.data.resultado_cnpjs || [];
        this.lastSync = new Date();
        this.lastParamsHash = currentParamsHash;
      } catch (err) {
        if (axios.isCancel(err)) return;
        console.error('Erro ao buscar resumo do dashboard:', err);
        this.error = 'Não foi possível carregar as métricas estratégicas.';
      } finally {
        if (requestId === dashboardRequestSeq) {
          this.isLoading = false;
        }
      }
    },

    async fetchAlertasPanorama(filters = {}) {
      const params = buildAnalyticsParams(filters);

      const requestId = ++alertasPanoramaRequestSeq;
      if (alertasPanoramaAbortController) alertasPanoramaAbortController.abort();
      alertasPanoramaAbortController = new AbortController();

      this.alertasPanoramaLoading = true;
      try {
        const response = await axios.get(API_ENDPOINTS.analyticsAlertasPanorama, {
          params,
          signal: alertasPanoramaAbortController.signal,
        });
        if (requestId !== alertasPanoramaRequestSeq) return;
        this.alertasPanorama = response.data;
      } catch (err) {
        if (axios.isCancel(err)) return;
        console.error('Erro ao buscar panorama de alertas:', err);
        this.alertasPanorama = null;
      } finally {
        if (requestId === alertasPanoramaRequestSeq) {
          this.alertasPanoramaLoading = false;
        }
      }
    },

    async fetchCacheStatus() {
      const requestId = ++cacheStatusRequestSeq;
      if (cacheStatusAbortController) {
        cacheStatusAbortController.abort();
      }
      cacheStatusAbortController = new AbortController();

      try {
        const response = await axios.get(API_ENDPOINTS.cacheStatus, {
          signal: cacheStatusAbortController.signal,
        });
        if (requestId !== cacheStatusRequestSeq) return;
        this.cacheStatus = response.data;
      } catch (err) {
        if (axios.isCancel(err)) return;
        console.error('Erro ao buscar status do cache:', err);
        this.cacheStatus = null;
      }
    },

    /**
     * Atualiza apenas resultadoSentinelaUFNacional (mapa do Brasil).
     * Chamado quando filtros de valor/percentual mudam com UF selecionada.
     * Nunca inclui filtros de UF/região/município para garantir dados nacionais.
     */
    async fetchSentinelaUFNacional(filters = {}) {
      const requestId = ++nacionalRequestSeq;
      if (nacionalAbortController) {
        nacionalAbortController.abort();
      }
      nacionalAbortController = new AbortController();

      try {
        const params = buildAnalyticsParams({
          ...filters,
          uf: null,
          regiaoId: null,
          idIbge7: null,
          cnpjRaiz: null,
          estabelecimento: null,
        });
        const response = await axios.get(API_ENDPOINTS.analyticsResumo, {
          params,
          signal: nacionalAbortController.signal,
        });
        if (requestId !== nacionalRequestSeq) return;
        this.resultadoSentinelaUFNacional = response.data.resultado_sentinela_uf;
      } catch (err) {
        if (axios.isCancel(err)) return;
        console.error('Erro ao buscar dados nacionais por UF:', err);
      }
    },

    async fetchFatorRisco(filters = {}) {
      const requestId = ++fatorRiscoRequestSeq;
      if (fatorRiscoAbortController) {
        fatorRiscoAbortController.abort();
      }
      fatorRiscoAbortController = new AbortController();

      this.fatorRiscoLoading = true;
      try {
        const params = buildAnalyticsParams(filters);
        const response = await axios.get(API_ENDPOINTS.analyticsFatorRisco, {
          params,
          signal: fatorRiscoAbortController.signal,
        });
        if (requestId !== fatorRiscoRequestSeq) return;
        this.fatorRisco = response.data.buckets;
      } catch (err) {
        if (axios.isCancel(err)) return;
        console.error('Erro ao buscar fator de risco:', err);
        this.error = 'Não foi possível carregar o gráfico de fator de risco.';
      } finally {
        if (requestId === fatorRiscoRequestSeq) {
          this.fatorRiscoLoading = false;
        }
      }
    },

    async fetchProducaoSemestral(filters = {}) {
      const requestId = ++producaoSemestralRequestSeq;
      if (producaoSemestralAbortController) {
        producaoSemestralAbortController.abort();
      }
      producaoSemestralAbortController = new AbortController();

      this.producaoSemestralLoading = true;
      try {
        const params = buildAnalyticsParams(filters);
        const response = await axios.get(API_ENDPOINTS.analyticsProducaoSemestral, {
          params,
          signal: producaoSemestralAbortController.signal,
        });
        if (requestId !== producaoSemestralRequestSeq) return;
        this.producaoSemestral = response.data?.pontos || [];
      } catch (err) {
        if (axios.isCancel(err)) return;
        console.error('Erro ao buscar producao semestral:', err);
        this.producaoSemestral = [];
      } finally {
        if (requestId === producaoSemestralRequestSeq) {
          this.producaoSemestralLoading = false;
        }
      }
    },

  },

  getters: {
    enrichedKpis: (state) => {
      const enriched = state.kpis.map(kpi => {
        let label = kpi.label.toUpperCase();
        // Aplica mapeamento de labels do backend → UI
        label = KPI_LABEL_MAP[label] ?? label;

        const labelKey = Object.keys(KPI_CONFIGS).find(key => key.toUpperCase() === label);
        const config = KPI_CONFIGS[labelKey] || DEFAULT_KPI_STYLE;

        let finalColor = kpi.color || config.color;

        // Regra Dinâmica Estrita para o KPI: % SEM COMPROVAÇÃO
        if (label === '% SEM COMPROVAÇÃO' && kpi.value !== undefined) {
          const valStr = String(kpi.value).replace('%', '').replace(/\s/g, '').replace(',', '.');
          const percent = parseFloat(valStr);
          if (!isNaN(percent)) {
            if (percent <= RISK_THRESHOLDS.MEDIUM) {
               finalColor = RISK_COLORS.LOW;     // Verde (Seguro)
            } else if (percent <= RISK_THRESHOLDS.HIGH) {
               finalColor = RISK_COLORS.MEDIUM;  // Laranja/Alerta
            } else {
               finalColor = RISK_COLORS.HIGH;    // Vermelho/Crítico
            }
          }
        }

        return {
          ...kpi,
          label,
          icon: kpi.icon || config.icon,
          color: finalColor
        };
      });

      return enriched.sort((a, b) => {
        const indexA = KPI_PRIORITY_ORDER.indexOf(a.label.toUpperCase());
        const indexB = KPI_PRIORITY_ORDER.indexOf(b.label.toUpperCase());
        if (indexA !== -1 && indexB !== -1) return indexA - indexB;
        if (indexA !== -1) return -1;
        if (indexB !== -1) return 1;
        return 0;
      });
    },
    getKpiById: (state) => (id) => state.kpis.find(k => k.id === id)
  }
});
