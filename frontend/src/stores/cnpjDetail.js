import { defineStore } from 'pinia';
import axios from 'axios';
import { API_ENDPOINTS } from '@/config/api';
import { fetchRegionalPayload } from '@/composables/useRegional';

const PREFETCH_CONCURRENCY = 2;
const networkRequests = new Map();
const networkLevelRequests = new Map();
const crmMedicoAlertasRequests = new Map();

async function runTasksWithConcurrency(tasks, limit = PREFETCH_CONCURRENCY) {
  const queue = [...tasks];
  const workers = Array.from(
    { length: Math.min(limit, queue.length) },
    async () => {
      while (queue.length) {
        const task = queue.shift();
        await task();
      }
    },
  );
  await Promise.all(workers);
}

function normalizeCnpj(value) {
  return String(value ?? '').replace(/\D/g, '');
}

const ERROR_MSG = 'Não foi possível carregar os dados. Verifique a conexão com o servidor.';

function extractAxiosErrorMessage(error, fallback = ERROR_MSG) {
  const detail = error?.response?.data?.detail;
  if (typeof detail === 'string' && detail.trim()) return detail;
  if (Array.isArray(detail) && detail.length) {
    return detail.map((item) => item?.msg || String(item)).join('; ');
  }
  if (typeof error?.response?.data?.message === 'string' && error.response.data.message.trim()) {
    return error.response.data.message;
  }
  return error?.message || fallback;
}

function assertCrmTimelineDataset(data) {
  if (!data || !Array.isArray(data.days)) {
    throw new Error('Contrato invalido em crm/timeline-dataset: campo days obrigatorio.');
  }
  data.days.forEach((day, index) => {
    if (!day.dt_janela) {
      throw new Error(`Contrato invalido em crm/timeline-dataset: days[${index}].dt_janela obrigatorio.`);
    }
    if (!Array.isArray(day.hours)) {
      throw new Error(`Contrato invalido em crm/timeline-dataset: days[${index}].hours obrigatorio.`);
    }
    if (!Array.isArray(day.events)) {
      throw new Error(`Contrato invalido em crm/timeline-dataset: days[${index}].events obrigatorio.`);
    }
  });
}

function assertIntegrityAlerts(data) {
  if (
    !data
    || !Number.isInteger(data.total)
    || !Number.isInteger(data.total_criticos)
    || !Number.isInteger(data.total_atencao)
    || !Array.isArray(data.alertas)
  ) {
    throw new Error('Contrato invalido em alertas-integridade.');
  }

  data.alertas.forEach((alerta, index) => {
    const required = [
      'tipo',
      'escopo',
      'entidade_id',
      'entidade_nome',
      'severidade',
      'titulo',
      'fonte',
      'aba_destino',
    ];
    required.forEach((field) => {
      if (!alerta?.[field]) {
        throw new Error(`Contrato invalido em alertas-integridade: alertas[${index}].${field} obrigatorio.`);
      }
    });
  });
}

function assertNotaTecnicaReadiness(data) {
  if (
    !data
    || typeof data.ready !== 'boolean'
    || typeof data.preparable !== 'boolean'
    || !Array.isArray(data.modules)
    || !Array.isArray(data.missing_modules)
  ) {
    throw new Error('Contrato invalido em nota-tecnica/readiness.');
  }

  data.modules.forEach((module, index) => {
    ['key', 'label', 'scope', 'required', 'ready', 'missing_files'].forEach((field) => {
      if (module?.[field] === undefined || module?.[field] === null) {
        throw new Error(`Contrato invalido em nota-tecnica/readiness: modules[${index}].${field} obrigatorio.`);
      }
    });
    if (typeof module.preparable !== 'boolean') {
      throw new Error(`Contrato invalido em nota-tecnica/readiness: modules[${index}].preparable obrigatorio.`);
    }
    if (!Array.isArray(module.missing_files)) {
      throw new Error(`Contrato invalido em nota-tecnica/readiness: modules[${index}].missing_files deve ser lista.`);
    }
  });
}

function assertNotaTecnicaPrepare(data) {
  if (!data || !Array.isArray(data.prepared_modules) || !data.readiness) {
    throw new Error('Contrato invalido em nota-tecnica/prepare.');
  }
  assertNotaTecnicaReadiness(data.readiness);
}

function assertIndicadorBenchmarkLocal(data) {
  if (!data || !data.indicador || !Array.isArray(data.kpis) || !data.municipio || !data.regiao_saude) {
    throw new Error('Contrato invalido em indicadores/benchmark-local.');
  }
  ['municipio', 'regiao_saude'].forEach((scopeName) => {
    const scope = data[scopeName];
    if (!scope?.label || !Array.isArray(scope.rows)) {
      throw new Error(`Contrato invalido em indicadores/benchmark-local: ${scopeName}.rows obrigatorio.`);
    }
    scope.rows.forEach((row, index) => {
      [
        'cnpj',
        'is_conexao_ativa',
        'is_matriz',
        'status',
        'is_alvo',
        'valor_movimentado',
        'valor_sem_comprovacao',
        'percentual_nao_comprovacao',
      ].forEach((field) => {
        if (row?.[field] === undefined) {
          throw new Error(`Contrato invalido em indicadores/benchmark-local: ${scopeName}.rows[${index}].${field} obrigatorio.`);
        }
      });
      ['cnpj', 'is_conexao_ativa', 'is_matriz', 'status', 'is_alvo', 'valor_movimentado', 'valor_sem_comprovacao'].forEach((field) => {
        if (row?.[field] === undefined || row?.[field] === null) {
          throw new Error(`Contrato invalido em indicadores/benchmark-local: ${scopeName}.rows[${index}].${field} obrigatorio.`);
        }
      });
    });
  });
}

function assertIndicadorEvolucaoBenchmark(data) {
  if (
    !data
    || !data.indicador
    || !data.formato
    || !data.periodo_marcado
    || !Array.isArray(data.periodo_marcado.anos)
    || !Array.isArray(data.series)
  ) {
    throw new Error('Contrato invalido em indicadores/evolucao-benchmark.');
  }
  data.series.forEach((point, index) => {
    if (!Number.isInteger(point?.ano_base)) {
      throw new Error(`Contrato invalido em indicadores/evolucao-benchmark: series[${index}].ano_base obrigatorio.`);
    }
    ['farmacia', 'regiao_saude', 'uf'].forEach((field) => {
      if (point?.[field] === undefined) {
        throw new Error(`Contrato invalido em indicadores/evolucao-benchmark: series[${index}].${field} obrigatorio.`);
      }
    });
  });
}

function assertSocios(data) {
  if (!data || !Array.isArray(data.socios)) {
    throw new Error('Contrato invalido em socios: campo socios obrigatorio.');
  }

  data.socios.forEach((socio, index) => {
    ['cnpj', 'cpf_cnpj_socio', 'indicador_socio', 'is_cadunico', 'is_esocial', 'is_seguro_defeso', 'is_falecido'].forEach((field) => {
      if (socio?.[field] === undefined || socio?.[field] === null) {
        throw new Error(`Contrato invalido em socios: socios[${index}].${field} obrigatorio.`);
      }
    });
  });
}

function assertCadastroBootstrap(cadastro) {
  if (!cadastro) {
    throw new Error('Contrato invalido em bootstrap: cadastro obrigatorio.');
  }
  [
    'is_dispersao_uf_nao_vizinha',
    'pct_dispersao_uf_nao_vizinha',
    'valor_dispersao_uf_nao_vizinha',
  ].forEach((field) => {
    if (cadastro[field] === undefined || cadastro[field] === null) {
      throw new Error(`Contrato invalido em bootstrap.cadastro: ${field} obrigatorio.`);
    }
  });
}

function assertCrmDataLight(data) {
  if (!data || !Array.isArray(data.crms_interesse) || !data.summary) {
    throw new Error('Contrato invalido em crm-data: summary e crms_interesse obrigatorios.');
  }
  data.crms_interesse.forEach((crm, index) => {
    ['qtd_alertas_crm_unico', 'qtd_alertas_geograficos', 'qtd_alertas_crm_multiplos'].forEach((field) => {
      if (crm[field] == null) {
        throw new Error(`Contrato invalido em crm-data: crms_interesse[${index}].${field} obrigatorio.`);
      }
    });
  });
}

function assertCrmMedicoAlertas(data) {
  if (!data || !data.id_medico) {
    throw new Error('Contrato invalido em crm/medico-alertas: id_medico obrigatorio.');
  }
  ['alertas_crm_unico', 'alertas_geograficos', 'alertas_crm_multiplos'].forEach((field) => {
    if (!Array.isArray(data[field])) {
      throw new Error(`Contrato invalido em crm/medico-alertas: ${field} obrigatorio.`);
    }
  });
}

function assertRepasses(data) {
  if (!data || typeof data.cnpj !== 'string') {
    throw new Error('Contrato invalido em repasses: cnpj obrigatorio.');
  }
  if (!data.resumo || typeof data.resumo.total_repassado !== 'number') {
    throw new Error('Contrato invalido em repasses: resumo.total_repassado obrigatorio.');
  }
  if (!Array.isArray(data.mensal)) {
    throw new Error('Contrato invalido em repasses: mensal obrigatorio.');
  }
  if (!Array.isArray(data.pagamentos)) {
    throw new Error('Contrato invalido em repasses: pagamentos obrigatorio.');
  }
}

export const useCnpjDetailStore = defineStore('cnpjDetail', {
  state: () => ({
    // ── Cadastro ──────────────────────────────────────────────────────────────
    dadosCadastro:        null,
    dadosCadastroLoading: false,

    // ── Movimentação Financeira ───────────────────────────────────────────────
    evolucaoFinanceira: null,
    evolucaoLoading:    false,
    evolucaoLoaded:     false,
    evolucaoError:      null,
    evolucaoKey:        null,   // Cache key: "cnpj|inicio|fim" — evita re-fetch desnecessário
    evolucaoRequestKey: null,

    // ── Memória de Cálculo ────────────────────────────────────────────────────
    movimentacaoData:    null,
    movimentacaoLoading: false,
    movimentacaoLoaded:  false,
    movimentacaoLoadingKey: null,
    movimentacaoLoadedKey:  null,
    movimentacaoError:   null,

    // ── Indicadores de Risco ──────────────────────────────────────────────────
    indicadoresData:    null,
    indicadoresLoading: false,
    indicadoresLoaded:  false,
    indicadoresLoadingKey: null,
    indicadoresLoadedKey:  null,
    indicadoresError:   null,
    indicadorBenchmarkDataByKey: {},
    indicadorBenchmarkLoadingByKey: {},
    indicadorBenchmarkErrorByKey: {},
    indicadorEvolucaoBenchmarkDataByKey: {},
    indicadorEvolucaoBenchmarkLoadingByKey: {},
    indicadorEvolucaoBenchmarkErrorByKey: {},

    // ── Dispersão Geográfica por UF ──────────────────────────────────────────
    geograficoOrigemUfData: null,
    geograficoOrigemUfLoading: false,
    geograficoOrigemUfLoadedKey: null,
    geograficoOrigemUfRequestKey: null,
    geograficoOrigemUfError: null,
    geograficoBenchmarkData: null,
    geograficoBenchmarkLoading: false,
    geograficoBenchmarkLoadedKey: null,
    geograficoBenchmarkRequestKey: null,
    geograficoBenchmarkError: null,

    // ── Incompatibilidade Patológica ─────────────────────────────────────────
    incompatibilidadePatologicaData: null,
    incompatibilidadePatologicaLoading: false,
    incompatibilidadePatologicaLoadedKey: null,
    incompatibilidadePatologicaRequestKey: null,
    incompatibilidadePatologicaError: null,

    // ── Falecidos ─────────────────────────────────────────────────────────────
    falecidosData:    null,
    falecidosLoading: false,
    falecidosLoaded:  null,   // Cache key: "cnpj|inicio|fim"
    falecidosRequestKey: null,
    falecidosError:   null,

    // ── Prescritores / CRMs ───────────────────────────────────────────────────
    prescritoresData:    null,
    prescritoresLoading: false,
    prescritoresLoaded:  null,   // Cache key: "cnpj|inicio|fim"
    prescritoresRequestKey: null,
    prescritoresError:   null,
    crmMedicoAlertasByKey: {},
    crmMedicoAlertasLoadingByKey: {},
    crmMedicoAlertasErrorByKey: {},

    // Dataset semantico da linha do tempo CRM
    crmTimelineDataset:        null,
    crmTimelineDatasetLoading: false,
    crmTimelineDatasetLoaded:  null,  // Cache key: "cnpj|inicio|fim"
    crmTimelineDatasetRequestKey: null,

    // ── CNPJs abertos por URL direta (fora do fluxo de filtros globais) ───────
    cnpjsAvulsos:        new Map(),
    cnpjsAvulsosLoading: false,
    cnpjAccessStatus:    'idle',
    cnpjAccessCnpj:      null,
    cnpjAccessMessage:   null,
    cnpjAccessData:      null,
    bootstrapData:       null,
    bootstrapLoading:    false,
    bootstrapLoadedKey:  null,
    bootstrapRequestKey: null,
    bootstrapGeoData:    null,
    bootstrapPeriodSummary: null,

    // ── Municípios da região do CNPJ (para RegionalTab) ──────────────────────
    municipiosRegiao:        [],
    municipiosRegiaoKey:     null,
    municipiosRegiaoLoading: false,

    // ── Curva de Percentis (Contexto Regional/UF/Brasil) ────────────────────
    metricPercentiles:        null,
    metricPercentilesLoading: false,
    metricPercentilesLoaded:  false, // Guarda a chave do escopo atual
    metricPercentilesRequestKey: null,
    
    // ── Evolução Mensal GTIN ─────────────────────────────────────────────────
    evolucaoMensalGtin:        null,
    evolucaoMensalGtinLoading: false,
    evolucaoMensalGtinKey:     null,
    evolucaoMensalGtinRequestKey: null,

    // ── Repasses Farmácia Popular ─────────────────────────────────────────────
    repassesData:        null,
    repassesLoading:     false,
    repassesLoaded:      false,
    repassesError:       null,
    repassesKey:         null,
    repassesRequestKey:  null,

    // ── Navegação Deep-Link (Timeline) ──────────────────────────────────────
    selectedTimelineEvent: null, // { date: 'YYYY-MM-DD', hour: number | 'all', autorizacao: string | null }
    activeCrmViewMode:     'medicos', // 'medicos' | 'cronologia' | 'falecidos'

    // ── Ranking GTINs ─────────────────────────────────────────────────────────
    gtinDetalhamentoMensalData: null,
    gtinDetalhamentoMensalLoading: false,
    gtinDetalhamentoMensalError: null,
    
    // ── Quadro Societário ─────────────────────────────────────────────────────
    sociosData:    null,
    sociosLoading: false,
    sociosLoaded:  false,
    sociosRequestKey: null,
    sociosError:   null,

    // ── Alertas de Integridade ────────────────────────────────────────────────
    integrityAlertsData: null,
    integrityAlertsLoading: false,
    integrityAlertsLoaded: false,
    integrityAlertsRequestKey: null,
    integrityAlertsError: null,

    // ── Prontidão da Nota Técnica ─────────────────────────────────────────────
    notaTecnicaReadinessData: null,
    notaTecnicaReadinessLoading: false,
    notaTecnicaReadinessLoadedKey: null,
    notaTecnicaReadinessRequestKey: null,
    notaTecnicaReadinessError: null,
    notaTecnicaPreparing: false,
    notaTecnicaPrepareError: null,

    // ── Prontidão do Relatório PDF ───────────────────────────────────────────
    relatorioPdfReadinessData: null,
    relatorioPdfReadinessLoading: false,
    relatorioPdfReadinessLoadedKey: null,
    relatorioPdfReadinessRequestKey: null,
    relatorioPdfReadinessError: null,
    relatorioPdfPreparing: false,
    relatorioPdfPrepareError: null,

    // ── Teia Societária (Grafo de Relacionamentos) ────────────────────────────
    networkData:    null,
    networkLoading: false,
    networkLoaded:  false,
    networkRequestKey: null,
    networkLevelData: { 3: null, 4: null },
    networkLevelLoading: { 3: false, 4: false },
    networkLevelLoaded: { 3: null, 4: null },
    networkLevelRequestKey: { 3: null, 4: null },
    networkPresentationState: null,
    networkError:   null,

    prefetchRequestKey: null,
  }),

  actions: {
    setInvalidCnpjFormat(cnpj) {
      const clean = normalizeCnpj(cnpj);
      this.cnpjAccessStatus = 'invalid_format';
      this.cnpjAccessCnpj = clean;
      this.cnpjAccessMessage = clean.length
        ? `O identificador informado tem ${clean.length} digitos. A tela de estabelecimento aceita CNPJ com 14 digitos.`
        : 'Informe um CNPJ com 14 digitos para abrir a tela de estabelecimento.';
      this.cnpjAccessData = null;
      return {
        status: this.cnpjAccessStatus,
        cnpj: clean,
        message: this.cnpjAccessMessage,
      };
    },

    async validateCnpjAccess(cnpj) {
      const clean = normalizeCnpj(cnpj);
      if (clean.length !== 14) {
        return this.setInvalidCnpjFormat(clean);
      }

      this.cnpjAccessStatus = 'checking';
      this.cnpjAccessCnpj = clean;
      this.cnpjAccessMessage = null;
      this.cnpjAccessData = null;

      try {
        const { data } = await axios.get(API_ENDPOINTS.analyticsCnpjStatus(clean));
        this.cnpjAccessStatus = 'valid';
        this.cnpjAccessData = data;
        this.cnpjAccessMessage = null;
        return data;
      } catch (error) {
        const statusCode = error?.response?.status;
        const detail = error?.response?.data?.detail;
        if (statusCode === 404 && detail?.status) {
          this.cnpjAccessStatus = detail?.status || 'not_in_program';
          this.cnpjAccessMessage = detail?.message || 'CNPJ nao encontrado na base carregada do Programa Farmacia Popular.';
        } else if (statusCode === 422) {
          this.cnpjAccessStatus = detail?.status || 'invalid_format';
          this.cnpjAccessMessage = detail?.message || 'A tela de estabelecimento aceita apenas CNPJ com 14 digitos.';
        } else {
          this.cnpjAccessStatus = 'error';
          this.cnpjAccessMessage = ERROR_MSG;
        }
        this.cnpjAccessData = null;
        return {
          status: this.cnpjAccessStatus,
          cnpj: clean,
          message: this.cnpjAccessMessage,
        };
      }
    },

    async fetchBootstrap(cnpj, inicio = null, fim = null) {
      const clean = normalizeCnpj(cnpj);
      if (clean.length !== 14) {
        return this.setInvalidCnpjFormat(clean);
      }

      const key = `${clean}|${inicio ?? ''}|${fim ?? ''}`;
      if (this.bootstrapLoadedKey === key && this.bootstrapData) {
        return this.bootstrapData;
      }

      const isBackgroundRefresh =
        this.cnpjAccessStatus === 'valid' &&
        this.cnpjAccessCnpj === clean &&
        Boolean(this.bootstrapData);

      this.bootstrapLoading = true;
      this.bootstrapRequestKey = key;
      this.cnpjAccessCnpj = clean;
      if (!isBackgroundRefresh) {
        this.cnpjAccessStatus = 'checking';
        this.cnpjAccessMessage = null;
        this.cnpjAccessData = null;
      }

      try {
        const params = {};
        if (inicio) params.data_inicio = inicio;
        if (fim)    params.data_fim    = fim;

        const { data } = await axios.get(API_ENDPOINTS.analyticsCnpjBootstrap(clean), { params });
        if (this.bootstrapRequestKey !== key) {
          return null;
        }

        if (!data.status?.status || !data.cadastro || !data.cnpj_data || !data.geo_data || !data.period_summary) {
          throw new Error('Resposta de bootstrap incompleta para a tela de estabelecimento.');
        }
        assertCadastroBootstrap(data.cadastro);

        this.bootstrapData = data;
        this.bootstrapLoadedKey = key;
        this.bootstrapGeoData = data.geo_data;
        this.bootstrapPeriodSummary = data.period_summary;

        this.cnpjAccessStatus = data.status.status;
        this.cnpjAccessData = data.status;
        this.cnpjAccessMessage = null;

        this.dadosCadastro = data.cadastro;
        this.dadosCadastroLoading = false;

        this.cnpjsAvulsos.set(clean, data.cnpj_data);
        this.cnpjsAvulsosLoading = false;

        return data;
      } catch (error) {
        if (this.bootstrapRequestKey !== key) {
          return null;
        }
        if (isBackgroundRefresh) {
          throw error;
        }
        const statusCode = error?.response?.status;
        const detail = error?.response?.data?.detail;
        if (statusCode === 404) {
          this.cnpjAccessStatus = detail?.status || 'not_in_program';
          this.cnpjAccessMessage = detail?.message || 'CNPJ nao encontrado na base carregada do Programa Farmacia Popular.';
        } else if (statusCode === 422) {
          this.cnpjAccessStatus = detail?.status || 'invalid_format';
          this.cnpjAccessMessage = detail?.message || 'A tela de estabelecimento aceita apenas CNPJ com 14 digitos.';
        } else {
          this.cnpjAccessStatus = 'error';
          this.cnpjAccessMessage = detail || ERROR_MSG;
        }
        this.cnpjAccessData = null;
        this.bootstrapData = null;
        this.bootstrapLoadedKey = null;
        this.bootstrapGeoData = null;
        this.bootstrapPeriodSummary = null;
        this.cnpjsAvulsos.delete(clean);
        throw error;
      } finally {
        if (this.bootstrapRequestKey === key) {
          this.bootstrapLoading = false;
          this.bootstrapRequestKey = null;
        }
      }
    },

    async ensureTabData(tabSlug, cnpj, inicio = null, fim = null, volumeAtipicoPercentual = null) {
      if (!cnpj) return;

      if (tabSlug === 'movimentacao') {
        await Promise.all([
          this.fetchEvolucaoFinanceira(cnpj, inicio, fim, volumeAtipicoPercentual),
          this.fetchEvolucaoMensalGtin(cnpj, inicio, fim),
          this.fetchRepasses(cnpj, inicio, fim),
        ]);
        return;
      }

      if (tabSlug === 'memoria') {
        await this.fetchMovimentacao(cnpj);
        return;
      }

      if (tabSlug === 'indicadores') {
        await this.fetchIndicadores(cnpj, inicio, fim);
        return;
      }

      if (tabSlug === 'autorizacoes') {
        const fetches = [this.fetchCrmData(cnpj, inicio, fim)];
        if (this.activeCrmViewMode === 'cronologia') {
          fetches.push(this.fetchCrmTimelineDataset(cnpj, inicio, fim));
        }
        if (this.activeCrmViewMode === 'falecidos') {
          fetches.push(this.fetchFalecidos(cnpj, inicio, fim));
        }
        await Promise.all(fetches);
        return;
      }

      if (tabSlug === 'falecidos') {
        await this.fetchFalecidos(cnpj, inicio, fim);
        return;
      }

      if (tabSlug === 'socios') {
        await this.fetchSocios(cnpj);
        return;
      }

      if (tabSlug === 'teia') {
        await this.fetchNetwork(cnpj, inicio, fim);
      }
    },

    async prefetchAllDetailData({
      cnpj,
      inicio = null,
      fim = null,
      volumeAtipicoPercentual = null,
      geoData = null,
      concurrency = PREFETCH_CONCURRENCY,
    }) {
      const clean = normalizeCnpj(cnpj);
      if (clean.length !== 14 || this.cnpjAccessStatus !== 'valid') return;

      const uf = geoData?.sg_uf ?? null;
      const regiaoId = geoData?.id_regiao_saude ?? null;
      const requestKey = [
        clean,
        inicio ?? '',
        fim ?? '',
        `vol:${volumeAtipicoPercentual ?? ''}`,
        `uf:${uf ?? ''}`,
        `regiao:${regiaoId ?? ''}`,
      ].join('|');

      this.prefetchRequestKey = requestKey;
      const isCurrentPrefetch = () =>
        this.prefetchRequestKey === requestKey &&
        this.cnpjAccessStatus === 'valid' &&
        this.cnpjAccessCnpj === clean;

      const tasks = [
        ['movimentacao-financeira', () => this.fetchEvolucaoFinanceira(clean, inicio, fim, volumeAtipicoPercentual)],
        ['movimentacao-gtin', () => this.fetchEvolucaoMensalGtin(clean, inicio, fim)],
        ['repasses', () => this.fetchRepasses(clean, inicio, fim)],
        ['indicadores', () => this.fetchIndicadores(clean, inicio, fim)],
        ['crm-prescritores', () => this.fetchCrmData(clean, inicio, fim)],
        ['crm-cronologia', () => this.fetchCrmTimelineDataset(clean, inicio, fim)],
        ['falecidos', () => this.fetchFalecidos(clean, inicio, fim)],
        ['socios', () => this.fetchSocios(clean)],
        ['teia-n2', () => this.fetchNetwork(clean, inicio, fim)],
      ];

      if (uf) {
        tasks.push(
          ['regional-benchmarking', () => fetchRegionalPayload(uf, inicio, fim, regiaoId)],
          ['percentis-risco', () => this.fetchMetricPercentiles(
            'brasil',
            uf,
            regiaoId,
            'percentual_sem_comprovacao',
            inicio,
            fim,
          )],
        );
      }

      await runTasksWithConcurrency(
        tasks.map(([label, run]) => async () => {
          if (!isCurrentPrefetch()) return;
          try {
            await run();
          } catch (error) {
            console.error(`[CNPJ preload] Falha ao carregar ${label}:`, error);
          }
        }),
        concurrency,
      );

      if (this.prefetchRequestKey === requestKey) {
        this.prefetchRequestKey = null;
      }
    },
    // ── Cadastro ──────────────────────────────────────────────────────────────
    async fetchDadosCadastro(cnpj) {
      if (!cnpj) return;
      this.dadosCadastroLoading = true;
      try {
        const { data } = await axios.get(API_ENDPOINTS.analyticsCadastro(cnpj));
        this.dadosCadastro = data;
      } catch (e) {
        console.error('Erro ao buscar dados cadastrais:', e);
      } finally {
        this.dadosCadastroLoading = false;
      }
    },

    // ── Movimentação Financeira ───────────────────────────────────────────────
    async fetchEvolucaoFinanceira(cnpj, inicio = null, fim = null, volumeAtipicoPercentual = null) {
      const key = `${cnpj}|${inicio ?? ''}|${fim ?? ''}|vol:${volumeAtipicoPercentual ?? ''}`;
      if (this.evolucaoKey === key) return;
      if (this.evolucaoRequestKey === key) return;

      this.evolucaoLoading = true;
      this.evolucaoRequestKey = key;

      try {
        const params = {};
        if (inicio) params.data_inicio = inicio;
        if (fim)    params.data_fim    = fim;
        if (volumeAtipicoPercentual !== null && volumeAtipicoPercentual !== undefined) {
          params.volume_atipico_limite = volumeAtipicoPercentual;
        }

        const { data } = await axios.get(API_ENDPOINTS.analyticsEvolucao(cnpj), { params });
        if (this.evolucaoRequestKey !== key) return;
        this.evolucaoFinanceira = data;
        this.evolucaoKey        = key;
        this.evolucaoLoaded     = true;
        this.evolucaoError      = null;
      } catch (e) {
        if (this.evolucaoRequestKey !== key) return;
        console.error('Erro ao buscar evolução financeira:', e);
        this.evolucaoError = ERROR_MSG;
      } finally {
        if (this.evolucaoRequestKey === key) {
          this.evolucaoLoading = false;
          this.evolucaoRequestKey = null;
        }
      }
    },

    // ── Evolução Mensal GTIN ─────────────────────────────────────────────────
    async fetchEvolucaoMensalGtin(cnpj, inicio = null, fim = null) {
      const key = `${cnpj}|${inicio ?? ''}|${fim ?? ''}`;
      if (this.evolucaoMensalGtinKey === key) return;
      if (this.evolucaoMensalGtinRequestKey === key) return;
      this.evolucaoMensalGtinLoading = true;
      this.evolucaoMensalGtinRequestKey = key;
      try {
        const params = {};
        if (inicio) params.data_inicio = inicio;
        if (fim)    params.data_fim    = fim;
        const { data } = await axios.get(API_ENDPOINTS.analyticsEvolucaoMensalGtin(cnpj), { params });
        if (this.evolucaoMensalGtinRequestKey !== key) return;
        this.evolucaoMensalGtin    = data;
        this.evolucaoMensalGtinKey = key;
      } catch (e) {
        if (this.evolucaoMensalGtinRequestKey !== key) return;
        console.error('Erro ao buscar evolução mensal GTIN:', e);
      } finally {
        if (this.evolucaoMensalGtinRequestKey === key) {
          this.evolucaoMensalGtinLoading = false;
          this.evolucaoMensalGtinRequestKey = null;
        }
      }
    },

    async fetchRepasses(cnpj, inicio = null, fim = null) {
      const key = `${cnpj}|${inicio ?? ''}|${fim ?? ''}`;
      if (this.repassesKey === key) return;
      if (this.repassesRequestKey === key) return;

      this.repassesLoading = true;
      this.repassesRequestKey = key;

      try {
        const params = {};
        if (inicio) params.data_inicio = inicio;
        if (fim)    params.data_fim    = fim;

        const { data } = await axios.get(API_ENDPOINTS.analyticsRepasses(cnpj), { params });
        if (this.repassesRequestKey !== key) return;
        assertRepasses(data);
        this.repassesData   = data;
        this.repassesKey    = key;
        this.repassesLoaded = true;
        this.repassesError  = null;
      } catch (e) {
        if (this.repassesRequestKey !== key) return;
        console.error('Erro ao buscar repasses:', e);
        const detail = e?.response?.data?.detail;
        this.repassesError = typeof detail === 'string'
          ? detail
          : ERROR_MSG;
        this.repassesData   = null;
        this.repassesLoaded = true;
      } finally {
        if (this.repassesRequestKey === key) {
          this.repassesLoading = false;
          this.repassesRequestKey = null;
        }
      }
    },

    // ── Ranking de GTINs Infratores ──────────────────────────────────────────
    async fetchGtinDetalhamentoMensal(cnpj, periodo) {
      this.gtinDetalhamentoMensalLoading = true;
      this.gtinDetalhamentoMensalError = null;
      try {
        const { data } = await axios.get(API_ENDPOINTS.analyticsGtinDetalhamentoMensal(cnpj, periodo));
        // Agrupar os resultados diretamente usando o "periodo" fornecido como chave.
        // Diferente das outras chamadas que vêm com listas longas, o Raio-X Mensal traz o ranking de um mês específico
        this.gtinDetalhamentoMensalData = data;
      } catch (error) {
        console.error('Erro ao buscar detalhamento mensal de GTINs:', error);
        this.gtinDetalhamentoMensalError = ERROR_MSG;
        this.gtinDetalhamentoMensalData = null;
      } finally {
        this.gtinDetalhamentoMensalLoading = false;
      }
    },

    // ── Memória de Cálculo ────────────────────────────────────────────────────
    async fetchMovimentacao(cnpj) {
      const clean = normalizeCnpj(cnpj);
      if (!clean) return;
      if (this.movimentacaoLoadedKey === clean || this.movimentacaoLoadingKey === clean) return;
      this.movimentacaoLoading = true;
      this.movimentacaoLoadingKey = clean;
      try {
        const { data } = await axios.get(API_ENDPOINTS.analyticsMovimentacao(clean));
        if (this.movimentacaoLoadingKey !== clean) return;
        this.movimentacaoData   = data;
        this.movimentacaoLoaded = true;
        this.movimentacaoLoadedKey = clean;
        this.movimentacaoError  = null;
      } catch (e) {
        if (this.movimentacaoLoadingKey !== clean) return;
        console.error('Erro ao buscar movimentação:', e);
        this.movimentacaoError = ERROR_MSG;
      } finally {
        if (this.movimentacaoLoadingKey === clean) {
          this.movimentacaoLoading = false;
          this.movimentacaoLoadingKey = null;
        }
      }
    },

    // ── Indicadores ───────────────────────────────────────────────────────────
    async fetchIndicadores(cnpj, inicio = null, fim = null) {
      const clean = normalizeCnpj(cnpj);
      if (!clean) return;
      const requestKey = `${clean}|${inicio || ''}|${fim || ''}`;
      if (this.indicadoresLoadedKey === requestKey || this.indicadoresLoadingKey === requestKey) return;
      this.indicadoresLoading = true;
      this.indicadoresLoadingKey = requestKey;
      try {
        const params = {};
        if (inicio) params.data_inicio = inicio;
        if (fim)    params.data_fim    = fim;
        const { data } = await axios.get(API_ENDPOINTS.analyticsIndicadores(clean), { params });
        if (this.indicadoresLoadingKey !== requestKey) return;
        this.indicadoresData   = data;
        this.indicadoresLoaded = true;
        this.indicadoresLoadedKey = requestKey;
        this.indicadoresError  = null;
      } catch (e) {
        if (this.indicadoresLoadingKey !== requestKey) return;
        console.error('Erro ao buscar indicadores:', e);
        this.indicadoresError = ERROR_MSG;
      } finally {
        if (this.indicadoresLoadingKey === requestKey) {
          this.indicadoresLoading = false;
          this.indicadoresLoadingKey = null;
        }
      }
    },

    async fetchIndicadorBenchmarkLocal(cnpj, indicador, inicio = null, fim = null) {
      const clean = normalizeCnpj(cnpj);
      const indicatorKey = String(indicador ?? '').trim();
      if (!clean || !indicatorKey) return null;
      const requestKey = `${clean}|${indicatorKey}|${inicio || ''}|${fim || ''}`;
      if (this.indicadorBenchmarkDataByKey[requestKey]) {
        return this.indicadorBenchmarkDataByKey[requestKey];
      }
      if (this.indicadorBenchmarkLoadingByKey[requestKey]) return null;

      this.indicadorBenchmarkLoadingByKey = {
        ...this.indicadorBenchmarkLoadingByKey,
        [requestKey]: true,
      };
      this.indicadorBenchmarkErrorByKey = {
        ...this.indicadorBenchmarkErrorByKey,
        [requestKey]: null,
      };

      try {
        const params = {};
        if (inicio) params.data_inicio = inicio;
        if (fim)    params.data_fim    = fim;
        const { data } = await axios.get(
          API_ENDPOINTS.analyticsIndicadorBenchmarkLocal(clean, indicatorKey),
          { params },
        );
        assertIndicadorBenchmarkLocal(data);
        this.indicadorBenchmarkDataByKey = {
          ...this.indicadorBenchmarkDataByKey,
          [requestKey]: data,
        };
        return data;
      } catch (e) {
        console.error('Erro ao buscar benchmark local do indicador:', e);
        this.indicadorBenchmarkErrorByKey = {
          ...this.indicadorBenchmarkErrorByKey,
          [requestKey]: e?.response?.data?.detail || ERROR_MSG,
        };
        return null;
      } finally {
        this.indicadorBenchmarkLoadingByKey = {
          ...this.indicadorBenchmarkLoadingByKey,
          [requestKey]: false,
        };
      }
    },

    async fetchIndicadorEvolucaoBenchmark(cnpj, indicador, inicio = null, fim = null) {
      const clean = normalizeCnpj(cnpj);
      const indicatorKey = String(indicador ?? '').trim();
      if (!clean || !indicatorKey) return null;
      const requestKey = `${clean}|${indicatorKey}|${inicio || ''}|${fim || ''}`;
      if (this.indicadorEvolucaoBenchmarkDataByKey[requestKey]) {
        return this.indicadorEvolucaoBenchmarkDataByKey[requestKey];
      }
      if (this.indicadorEvolucaoBenchmarkLoadingByKey[requestKey]) return null;

      this.indicadorEvolucaoBenchmarkLoadingByKey = {
        ...this.indicadorEvolucaoBenchmarkLoadingByKey,
        [requestKey]: true,
      };
      this.indicadorEvolucaoBenchmarkErrorByKey = {
        ...this.indicadorEvolucaoBenchmarkErrorByKey,
        [requestKey]: null,
      };

      try {
        const params = {};
        if (inicio) params.data_inicio = inicio;
        if (fim)    params.data_fim    = fim;
        const { data } = await axios.get(
          API_ENDPOINTS.analyticsIndicadorEvolucaoBenchmark(clean, indicatorKey),
          { params },
        );
        assertIndicadorEvolucaoBenchmark(data);
        this.indicadorEvolucaoBenchmarkDataByKey = {
          ...this.indicadorEvolucaoBenchmarkDataByKey,
          [requestKey]: data,
        };
        return data;
      } catch (e) {
        console.error('Erro ao buscar evolucao anual do indicador:', e);
        this.indicadorEvolucaoBenchmarkErrorByKey = {
          ...this.indicadorEvolucaoBenchmarkErrorByKey,
          [requestKey]: e?.response?.data?.detail || ERROR_MSG,
        };
        return null;
      } finally {
        this.indicadorEvolucaoBenchmarkLoadingByKey = {
          ...this.indicadorEvolucaoBenchmarkLoadingByKey,
          [requestKey]: false,
        };
      }
    },

    async fetchGeograficoOrigemUf(cnpj, inicio = null, fim = null) {
      const clean = normalizeCnpj(cnpj);
      if (!clean) return null;
      const requestKey = `${clean}|${inicio || ''}|${fim || ''}`;
      if (this.geograficoOrigemUfLoadedKey === requestKey && this.geograficoOrigemUfData) {
        return this.geograficoOrigemUfData;
      }
      if (this.geograficoOrigemUfRequestKey === requestKey) return null;

      this.geograficoOrigemUfLoading = true;
      this.geograficoOrigemUfRequestKey = requestKey;
      this.geograficoOrigemUfError = null;
      try {
        const params = {};
        if (inicio) params.data_inicio = inicio;
        if (fim)    params.data_fim    = fim;
        const { data } = await axios.get(API_ENDPOINTS.analyticsGeograficoOrigemUf(clean), { params });
        if (this.geograficoOrigemUfRequestKey !== requestKey) return null;
        if (!data || !Array.isArray(data.rows) || data.uf_farmacia == null) {
          throw new Error('Contrato invalido em geografico/origem-uf: rows e uf_farmacia obrigatorios.');
        }
        this.geograficoOrigemUfData = data;
        this.geograficoOrigemUfLoadedKey = requestKey;
        return data;
      } catch (e) {
        if (this.geograficoOrigemUfRequestKey !== requestKey) return null;
        console.error('Erro ao buscar dispersão geográfica por UF:', e);
        this.geograficoOrigemUfError = e?.response?.data?.detail || ERROR_MSG;
        return null;
      } finally {
        if (this.geograficoOrigemUfRequestKey === requestKey) {
          this.geograficoOrigemUfLoading = false;
          this.geograficoOrigemUfRequestKey = null;
        }
      }
    },

    async fetchGeograficoBenchmarkLocal(cnpj, inicio = null, fim = null) {
      const clean = normalizeCnpj(cnpj);
      const requestKey = `${clean}|${inicio || ''}|${fim || ''}`;
      if (!clean) return null;
      if (this.geograficoBenchmarkLoadedKey === requestKey && this.geograficoBenchmarkData) {
        return this.geograficoBenchmarkData;
      }
      if (this.geograficoBenchmarkRequestKey === requestKey) return null;

      this.geograficoBenchmarkLoading = true;
      this.geograficoBenchmarkRequestKey = requestKey;
      this.geograficoBenchmarkError = null;

      try {
        const params = {};
        if (inicio) params.data_inicio = inicio;
        if (fim) params.data_fim = fim;
        const { data } = await axios.get(API_ENDPOINTS.analyticsGeograficoBenchmarkLocal(clean), { params });
        if (this.geograficoBenchmarkRequestKey !== requestKey) return null;
        if (!data?.municipio?.rows || !data?.regiao_saude?.rows) {
          throw new Error('Contrato invalido em geografico/benchmark-local: municipio.rows e regiao_saude.rows obrigatorios.');
        }
        this.geograficoBenchmarkData = data;
        this.geograficoBenchmarkLoadedKey = requestKey;
        return data;
      } catch (e) {
        if (this.geograficoBenchmarkRequestKey !== requestKey) return null;
        console.error('Erro ao buscar benchmark geografico local:', e);
        this.geograficoBenchmarkError = e?.response?.data?.detail || ERROR_MSG;
        return null;
      } finally {
        if (this.geograficoBenchmarkRequestKey === requestKey) {
          this.geograficoBenchmarkLoading = false;
          this.geograficoBenchmarkRequestKey = null;
        }
      }
    },

    async fetchIncompatibilidadePatologica(cnpj, inicio = null, fim = null) {
      const clean = normalizeCnpj(cnpj);
      if (!clean) return null;
      const requestKey = `${clean}|${inicio || ''}|${fim || ''}`;
      if (this.incompatibilidadePatologicaLoadedKey === requestKey && this.incompatibilidadePatologicaData) {
        return this.incompatibilidadePatologicaData;
      }
      if (this.incompatibilidadePatologicaRequestKey === requestKey) return null;

      this.incompatibilidadePatologicaLoading = true;
      this.incompatibilidadePatologicaRequestKey = requestKey;
      this.incompatibilidadePatologicaError = null;
      try {
        const params = {};
        if (inicio) params.data_inicio = inicio;
        if (fim)    params.data_fim    = fim;
        params.ranking_municipal_limite = 10;
        const { data } = await axios.get(API_ENDPOINTS.analyticsIncompatibilidadePatologica(clean), { params });
        if (this.incompatibilidadePatologicaRequestKey !== requestKey) return null;
        if (!data || !data.summary || !Array.isArray(data.patologias)) {
          throw new Error('Contrato invalido em clinico/incompatibilidades: summary e patologias obrigatorios.');
        }
        this.incompatibilidadePatologicaData = data;
        this.incompatibilidadePatologicaLoadedKey = requestKey;
        return data;
      } catch (e) {
        if (this.incompatibilidadePatologicaRequestKey !== requestKey) return null;
        console.error('Erro ao buscar incompatibilidade patologica:', e);
        this.incompatibilidadePatologicaError = e?.response?.data?.detail || ERROR_MSG;
        return null;
      } finally {
        if (this.incompatibilidadePatologicaRequestKey === requestKey) {
          this.incompatibilidadePatologicaLoading = false;
          this.incompatibilidadePatologicaRequestKey = null;
        }
      }
    },

    // ── Quadro Societário ─────────────────────────────────────────────────────
    async fetchSocios(cnpj) {
      const clean = normalizeCnpj(cnpj);
      if (!clean || this.sociosLoaded === clean || this.sociosRequestKey === clean) return;
      this.sociosLoading = true;
      this.sociosRequestKey = clean;
      this.sociosError   = null;
      try {
        const { data } = await axios.get(API_ENDPOINTS.analyticsSocios(clean));
        assertSocios(data);
        if (this.sociosRequestKey !== clean) return;
        this.sociosData   = data;
        this.sociosLoaded = clean;
      } catch (e) {
        if (this.sociosRequestKey !== clean) return;
        console.error('Erro ao buscar quadro societário:', e);
        this.sociosError = ERROR_MSG;
      } finally {
        if (this.sociosRequestKey === clean) {
          this.sociosLoading = false;
          this.sociosRequestKey = null;
        }
      }
    },

    // ── Teia Societária ─────────────────────────────────────────────────────
    async fetchNetwork(cnpj, inicio = null, fim = null) {
      const clean = normalizeCnpj(cnpj);
      const key = `${clean}|${inicio || ''}|${fim || ''}`;
      if (!clean || this.networkLoaded === key) return this.networkData;
      if (networkRequests.has(key)) return networkRequests.get(key);

      this.networkLoading = true;
      this.networkRequestKey = key;
      this.networkError   = null;

      const request = (async () => {
        const { data } = await axios.get(API_ENDPOINTS.analyticsNetwork(clean), {
          params: {
            data_inicio: inicio,
            data_fim: fim,
          },
        });
        if (this.networkRequestKey !== key) return null;
        this.networkData   = data;
        this.networkLoaded = key;
        return data;
      })();

      networkRequests.set(key, request);
      try {
        return await request;
      } catch (e) {
        if (this.networkRequestKey !== key) return null;
        console.error('Erro ao buscar teia societária:', e);
        this.networkError = ERROR_MSG;
        return null;
      } finally {
        networkRequests.delete(key);
        if (this.networkRequestKey === key) {
          this.networkLoading = false;
          this.networkRequestKey = null;
        }
      }
    },

    async fetchIntegrityAlerts(cnpj, inicio = null, fim = null, volumeAtipicoPercentual = null) {
      const clean = normalizeCnpj(cnpj);
      const key = `${clean}|${inicio ?? ''}|${fim ?? ''}|vol:${volumeAtipicoPercentual ?? ''}`;
      if (
        !clean
        || this.integrityAlertsLoaded === key
        || this.integrityAlertsRequestKey === key
      ) return;

      this.integrityAlertsLoading = true;
      this.integrityAlertsRequestKey = key;
      this.integrityAlertsError = null;

      try {
        const params = {};
        if (inicio) params.data_inicio = inicio;
        if (fim) params.data_fim = fim;
        if (volumeAtipicoPercentual != null) {
          params.volume_atipico_limite = volumeAtipicoPercentual;
        }

        const { data } = await axios.get(API_ENDPOINTS.analyticsIntegrityAlerts(clean), { params });
        assertIntegrityAlerts(data);
        if (this.integrityAlertsRequestKey !== key) return;
        this.integrityAlertsData = data;
        this.integrityAlertsLoaded = key;
      } catch (e) {
        if (this.integrityAlertsRequestKey !== key) return;
        console.error('Erro ao buscar alertas de integridade:', e);
        this.integrityAlertsError = e?.response?.data?.detail || e?.message || ERROR_MSG;
      } finally {
        if (this.integrityAlertsRequestKey === key) {
          this.integrityAlertsLoading = false;
          this.integrityAlertsRequestKey = null;
        }
      }
    },

    async fetchNotaTecnicaReadiness(cnpj, inicio = null, fim = null, options = {}) {
      const clean = normalizeCnpj(cnpj);
      const key = `${clean}|${inicio ?? ''}|${fim ?? ''}`;
      const force = options?.force === true;
      if (
        !clean
        || (!force && this.notaTecnicaReadinessLoadedKey === key)
        || this.notaTecnicaReadinessRequestKey === key
      ) return this.notaTecnicaReadinessData;

      this.notaTecnicaReadinessLoading = true;
      this.notaTecnicaReadinessRequestKey = key;
      this.notaTecnicaReadinessError = null;

      try {
        const params = {};
        if (inicio) params.data_inicio = inicio;
        if (fim) params.data_fim = fim;

        const { data } = await axios.get(API_ENDPOINTS.analyticsNotaTecnicaReadiness(clean), { params });
        assertNotaTecnicaReadiness(data);
        if (this.notaTecnicaReadinessRequestKey !== key) return null;
        this.notaTecnicaReadinessData = data;
        this.notaTecnicaReadinessLoadedKey = key;
        return data;
      } catch (e) {
        if (this.notaTecnicaReadinessRequestKey !== key) return null;
        console.error('Erro ao verificar prontidao da Nota Tecnica:', e);
        this.notaTecnicaReadinessError = e?.response?.data?.detail || e?.message || ERROR_MSG;
        this.notaTecnicaReadinessData = null;
        return null;
      } finally {
        if (this.notaTecnicaReadinessRequestKey === key) {
          this.notaTecnicaReadinessLoading = false;
          this.notaTecnicaReadinessRequestKey = null;
        }
      }
    },

    async prepareNotaTecnica(cnpj, inicio = null, fim = null) {
      const clean = normalizeCnpj(cnpj);
      if (!clean) return null;

      this.notaTecnicaPreparing = true;
      this.notaTecnicaPrepareError = null;

      try {
        const params = {};
        if (inicio) params.data_inicio = inicio;
        if (fim) params.data_fim = fim;

        const { data } = await axios.post(API_ENDPOINTS.analyticsNotaTecnicaPrepare(clean), null, { params });
        assertNotaTecnicaPrepare(data);
        this.notaTecnicaReadinessData = data.readiness;
        this.notaTecnicaReadinessLoadedKey = `${clean}|${inicio ?? ''}|${fim ?? ''}`;
        this.notaTecnicaReadinessError = null;
        return data;
      } catch (e) {
        console.error('Erro ao preparar dados da Nota Tecnica:', e);
        this.notaTecnicaPrepareError = extractAxiosErrorMessage(e);
        throw new Error(this.notaTecnicaPrepareError);
      } finally {
        this.notaTecnicaPreparing = false;
      }
    },

    async fetchRelatorioPdfReadiness(cnpj, inicio = null, fim = null, options = {}) {
      const clean = normalizeCnpj(cnpj);
      const key = `${clean}|${inicio ?? ''}|${fim ?? ''}`;
      const force = options?.force === true;
      if (
        !clean
        || (!force && this.relatorioPdfReadinessLoadedKey === key)
        || this.relatorioPdfReadinessRequestKey === key
      ) return this.relatorioPdfReadinessData;

      this.relatorioPdfReadinessLoading = true;
      this.relatorioPdfReadinessRequestKey = key;
      this.relatorioPdfReadinessError = null;

      try {
        const params = {};
        if (inicio) params.data_inicio = inicio;
        if (fim) params.data_fim = fim;

        const { data } = await axios.get(API_ENDPOINTS.analyticsRelatorioPdfReadiness(clean), { params });
        assertNotaTecnicaReadiness(data);
        if (this.relatorioPdfReadinessRequestKey !== key) return null;
        this.relatorioPdfReadinessData = data;
        this.relatorioPdfReadinessLoadedKey = key;
        return data;
      } catch (e) {
        if (this.relatorioPdfReadinessRequestKey !== key) return null;
        console.error('Erro ao verificar prontidao do Relatorio PDF:', e);
        this.relatorioPdfReadinessError = e?.response?.data?.detail || e?.message || ERROR_MSG;
        this.relatorioPdfReadinessData = null;
        return null;
      } finally {
        if (this.relatorioPdfReadinessRequestKey === key) {
          this.relatorioPdfReadinessLoading = false;
          this.relatorioPdfReadinessRequestKey = null;
        }
      }
    },

    async prepareRelatorioPdf(cnpj, inicio = null, fim = null) {
      const clean = normalizeCnpj(cnpj);
      if (!clean) return null;

      this.relatorioPdfPreparing = true;
      this.relatorioPdfPrepareError = null;

      try {
        const params = {};
        if (inicio) params.data_inicio = inicio;
        if (fim) params.data_fim = fim;

        const { data } = await axios.post(API_ENDPOINTS.analyticsRelatorioPdfPrepare(clean), null, { params });
        assertNotaTecnicaPrepare(data);
        this.relatorioPdfReadinessData = data.readiness;
        this.relatorioPdfReadinessLoadedKey = `${clean}|${inicio ?? ''}|${fim ?? ''}`;
        this.relatorioPdfReadinessError = null;
        return data;
      } catch (e) {
        console.error('Erro ao preparar dados do Relatorio PDF:', e);
        this.relatorioPdfPrepareError = extractAxiosErrorMessage(e);
        throw new Error(this.relatorioPdfPrepareError);
      } finally {
        this.relatorioPdfPreparing = false;
      }
    },

    async expandNetworkNode(cnpj, targetCnpj, inicio = null, fim = null) {
      if (!cnpj || !targetCnpj) return null;
      try {
        const { data } = await axios.get(
          API_ENDPOINTS.analyticsNetworkExpand(cnpj, targetCnpj),
          {
            params: {
              data_inicio: inicio,
              data_fim: fim,
            },
          },
        );
        return data;
      } catch (e) {
        console.error(`Erro ao expandir nó ${targetCnpj}:`, e);
        return null;
      }
    },

    async fetchNetworkLevel(cnpj, level, inicio = null, fim = null) {
      const clean = normalizeCnpj(cnpj);
      const numericLevel = Number(level);
      if (!clean) return null;
      if (![3, 4].includes(numericLevel)) {
        throw new Error(`Nivel de teia invalido: ${level}`);
      }

      const key = `${clean}|${numericLevel}|${inicio || ''}|${fim || ''}`;
      if (this.networkLevelLoaded[numericLevel] === key) {
        return this.networkLevelData[numericLevel];
      }
      if (networkLevelRequests.has(key)) {
        return networkLevelRequests.get(key);
      }

      this.networkLevelLoading[numericLevel] = true;
      this.networkLevelRequestKey[numericLevel] = key;

      const request = (async () => {
        const endpoint = numericLevel === 3
          ? API_ENDPOINTS.analyticsNetworkLevel3(clean)
          : API_ENDPOINTS.analyticsNetworkLevel4(clean);
        const { data } = await axios.get(endpoint, {
          params: {
            data_inicio: inicio,
            data_fim: fim,
          },
        });
        if (this.networkLevelRequestKey[numericLevel] !== key) return null;
        this.networkLevelData[numericLevel] = data;
        this.networkLevelLoaded[numericLevel] = key;
        return data;
      })();

      networkLevelRequests.set(key, request);
      try {
        return await request;
      } catch (e) {
        if (this.networkLevelRequestKey[numericLevel] !== key) return null;
        console.error(`Erro ao buscar nível ${numericLevel}:`, e);
        return null;
      } finally {
        networkLevelRequests.delete(key);
        if (this.networkLevelRequestKey[numericLevel] === key) {
          this.networkLevelLoading[numericLevel] = false;
          this.networkLevelRequestKey[numericLevel] = null;
        }
      }
    },

    saveNetworkPresentationState(cnpj, state) {
      const clean = normalizeCnpj(cnpj);
      if (!clean || !state) return;
      this.networkPresentationState = {
        ...state,
        cnpj: clean,
      };
    },

    getNetworkPresentationState(cnpj) {
      const clean = normalizeCnpj(cnpj);
      if (!clean || this.networkPresentationState?.cnpj !== clean) return null;
      return this.networkPresentationState;
    },

    // ── Falecidos ─────────────────────────────────────────────────────────────
    async fetchFalecidos(cnpj, inicio = null, fim = null) {
      const clean = normalizeCnpj(cnpj);
      if (!clean) return;
      const key = `${clean}|${inicio ?? ''}|${fim ?? ''}`;
      if (this.falecidosLoaded === key) return;
      if (this.falecidosRequestKey === key) return;

      this.falecidosLoading = true;
      this.falecidosRequestKey = key;
      try {
        const params = {};
        if (inicio) params.data_inicio = inicio;
        if (fim)    params.data_fim    = fim;

        const { data } = await axios.get(API_ENDPOINTS.analyticsFalecidos(clean), { params });
        if (this.falecidosRequestKey !== key) return;

        this.falecidosData   = data;
        this.falecidosLoaded = key;
        this.falecidosError  = null;
      } catch (e) {
        if (this.falecidosRequestKey !== key) return;
        console.error('Erro ao buscar dados de falecidos:', e);
        this.falecidosError = ERROR_MSG;
      } finally {
        if (this.falecidosRequestKey === key) {
          this.falecidosLoading = false;
          this.falecidosRequestKey = null;
        }
      }
    },

    // ── Prescritores / CRMs ───────────────────────────────────────────────────
    async fetchCrmData(cnpj, inicio = null, fim = null) {
      const clean = normalizeCnpj(cnpj);
      if (!clean) return;
      const key = `${clean}|${inicio ?? ''}|${fim ?? ''}`;
      if (this.prescritoresLoaded === key) return;
      if (this.prescritoresRequestKey === key) return;
      this.prescritoresLoading = true;
      this.prescritoresRequestKey = key;
      try {
        const params = {};
        if (inicio) params.data_inicio = inicio;
        if (fim)    params.data_fim    = fim;
        const { data } = await axios.get(API_ENDPOINTS.analyticsCrmData(clean), { params });
        if (this.prescritoresRequestKey !== key) return;
        assertCrmDataLight(data);
        this.prescritoresData   = data;
        this.prescritoresLoaded = key;
        this.prescritoresError  = null;
      } catch (e) {
        if (this.prescritoresRequestKey !== key) return;
        console.error('Erro ao buscar dados de prescritores:', e);
        this.prescritoresError = ERROR_MSG;
      } finally {
        if (this.prescritoresRequestKey === key) {
          this.prescritoresLoading = false;
          this.prescritoresRequestKey = null;
        }
      }
    },

    async fetchCrmMedicoAlertas(cnpj, idMedico, inicio = null, fim = null) {
      const clean = normalizeCnpj(cnpj);
      const medico = String(idMedico ?? '').trim();
      if (!clean || !medico) return null;

      const key = `${clean}|${medico}|${inicio ?? ''}|${fim ?? ''}`;
      if (this.crmMedicoAlertasByKey[key]) return this.crmMedicoAlertasByKey[key];
      if (crmMedicoAlertasRequests.has(key)) return crmMedicoAlertasRequests.get(key);

      this.crmMedicoAlertasLoadingByKey = {
        ...this.crmMedicoAlertasLoadingByKey,
        [key]: true,
      };
      this.crmMedicoAlertasErrorByKey = {
        ...this.crmMedicoAlertasErrorByKey,
        [key]: null,
      };

      const request = (async () => {
        const params = {};
        if (inicio) params.data_inicio = inicio;
        if (fim)    params.data_fim    = fim;
        const { data } = await axios.get(API_ENDPOINTS.analyticsCrmMedicoAlertas(clean, medico), { params });
        assertCrmMedicoAlertas(data);
        this.crmMedicoAlertasByKey = {
          ...this.crmMedicoAlertasByKey,
          [key]: data,
        };
        return data;
      })();

      crmMedicoAlertasRequests.set(key, request);
      try {
        return await request;
      } catch (e) {
        console.error('Erro ao buscar alertas do CRM:', e);
        this.crmMedicoAlertasErrorByKey = {
          ...this.crmMedicoAlertasErrorByKey,
          [key]: ERROR_MSG,
        };
        return null;
      } finally {
        crmMedicoAlertasRequests.delete(key);
        this.crmMedicoAlertasLoadingByKey = {
          ...this.crmMedicoAlertasLoadingByKey,
          [key]: false,
        };
      }
    },

    async fetchCrmTimelineDataset(cnpj, inicio = null, fim = null) {
      const clean = normalizeCnpj(cnpj);
      const key = `${clean}|${inicio ?? ''}|${fim ?? ''}`;
      if (!clean || this.crmTimelineDatasetLoaded === key) return;
      if (this.crmTimelineDatasetRequestKey === key) return;
      this.crmTimelineDatasetRequestKey = key;
      this.crmTimelineDatasetLoading = true;
      try {
        const params = {};
        if (inicio) params.data_inicio = inicio;
        if (fim)    params.data_fim    = fim;
        const { data } = await axios.get(API_ENDPOINTS.analyticsCrmTimelineDataset(clean), { params });
        if (this.crmTimelineDatasetRequestKey !== key) return;
        assertCrmTimelineDataset(data);
        this.crmTimelineDataset        = data;
        this.crmTimelineDatasetLoaded  = key;
      } catch (e) {
        console.error('Erro ao buscar timeline CRM:', e);
      } finally {
        if (this.crmTimelineDatasetRequestKey === key) {
          this.crmTimelineDatasetLoading = false;
          this.crmTimelineDatasetRequestKey = null;
        }
      }
    },

    // CNPJs Avulsos
    async fetchCnpjAvulso(cnpj, inicio = null, fim = null) {
      if (!cnpj || this.cnpjsAvulsos.has(cnpj)) return;
      this.cnpjsAvulsosLoading = true;
      try {
        const params = {};
        if (inicio) params.data_inicio = inicio;
        if (fim)    params.data_fim    = fim;
        params.cnpj_raiz = cnpj;
        const response = await axios.get(API_ENDPOINTS.analyticsResumo, { params });
        const found = (response.data.resultado_cnpjs || []).find(c => c.cnpj === cnpj);
        if (found) this.cnpjsAvulsos.set(cnpj, found);
      } catch (err) {
        console.error('Erro ao carregar CNPJ avulso:', err);
      } finally {
        this.cnpjsAvulsosLoading = false;
      }
    },

    // ── Municípios da Região ──────────────────────────────────────────────────
    async fetchMunicipiosRegiao(uf, regiaoId, inicio = null, fim = null) {
      if (!uf || !regiaoId) return;
      const key = `${uf}|${regiaoId}|${inicio ?? ''}|${fim ?? ''}`;
      if (this.municipiosRegiaoKey === key) return;
      this.municipiosRegiaoLoading = true;
      try {
        const params = {};
        if (inicio) params.data_inicio = inicio;
        if (fim)    params.data_fim    = fim;
        params.uf        = uf;
        params.regiao_id = regiaoId;
        const response = await axios.get(API_ENDPOINTS.analyticsResumo, { params });
        this.municipiosRegiao    = response.data.resultado_municipios || [];
        this.municipiosRegiaoKey = key;
      } catch (err) {
        console.error('Erro ao buscar municípios da região:', err);
      } finally {
        this.municipiosRegiaoLoading = false;
      }
    },

    setMetricPercentilesDirectly(data, cacheKey) {
      this.metricPercentiles = data || [];
      this.metricPercentilesLoaded = cacheKey;
    },

    async fetchMetricPercentiles(scope, uf = null, regiao_id = null, metric = 'score', inicio = null, fim = null) {
      const key = `${scope}|${uf ?? ''}|${regiao_id ?? ''}|${metric}|${inicio ?? ''}|${fim ?? ''}`;
      if (this.metricPercentilesLoaded === key) return;
      if (this.metricPercentilesRequestKey === key) return;
      
      this.metricPercentilesLoading = true;
      this.metricPercentilesRequestKey = key;
      try {
        const params = { scope, uf, regiao_id, metric };
        if (inicio) params.data_inicio = inicio;
        if (fim)    params.data_fim    = fim;

        const { data } = await axios.get(API_ENDPOINTS.analyticsMetricPercentiles, { params });
        if (this.metricPercentilesRequestKey !== key) return;
        this.metricPercentiles = data || [];
        this.metricPercentilesLoaded = key;
      } catch (e) {
        if (this.metricPercentilesRequestKey !== key) return;
        console.error('Erro ao buscar percentis da métrica:', e);
      } finally {
        if (this.metricPercentilesRequestKey === key) {
          this.metricPercentilesLoading = false;
          this.metricPercentilesRequestKey = null;
        }
      }
    },

    // ── Navegação ─────────────────────────────────────────────────────────────
    // hour: 'all' ou 0–23. autorizacao: nº da autorização a destacar no Raio-X.
    navigateTimeline(date, hour = 'all', autorizacao = null) {
      this.selectedTimelineEvent = { date, hour, autorizacao, ts: Date.now() };
      this.activeCrmViewMode     = 'cronologia';
    },

    setCrmViewMode(mode) {
      this.activeCrmViewMode = mode;
    },

    clearTimelineNavigation() {
      this.selectedTimelineEvent = null;
    },

    // ── Reset completo ao trocar de CNPJ ──────────────────────────────────────
    resetAll() {
      networkRequests.clear();
      networkLevelRequests.clear();

      this.dadosCadastro        = null;
      this.dadosCadastroLoading = false;

      this.evolucaoFinanceira = null;
      this.evolucaoLoading    = false;
      this.evolucaoLoaded     = false;
      this.evolucaoError      = null;
      this.evolucaoKey        = null;
      this.evolucaoRequestKey = null;

      this.evolucaoMensalGtin        = null;
      this.evolucaoMensalGtinLoading = false;
      this.evolucaoMensalGtinKey     = null;
      this.evolucaoMensalGtinRequestKey = null;

      this.repassesData        = null;
      this.repassesLoading     = false;
      this.repassesLoaded      = false;
      this.repassesError       = null;
      this.repassesKey         = null;
      this.repassesRequestKey  = null;

      this.gtinDetalhamentoMensalData    = null;
      this.gtinDetalhamentoMensalLoading = false;
      this.gtinDetalhamentoMensalError   = null;

      this.movimentacaoData    = null;
      this.movimentacaoLoading = false;
      this.movimentacaoLoaded  = false;
      this.movimentacaoLoadingKey = null;
      this.movimentacaoLoadedKey  = null;
      this.movimentacaoError   = null;

      this.indicadoresData    = null;
      this.indicadoresLoading = false;
      this.indicadoresLoaded  = false;
      this.indicadoresLoadingKey = null;
      this.indicadoresLoadedKey  = null;
      this.indicadoresError   = null;
      this.indicadorBenchmarkDataByKey = {};
      this.indicadorBenchmarkLoadingByKey = {};
      this.indicadorBenchmarkErrorByKey = {};
      this.indicadorEvolucaoBenchmarkDataByKey = {};
      this.indicadorEvolucaoBenchmarkLoadingByKey = {};
      this.indicadorEvolucaoBenchmarkErrorByKey = {};

      this.geograficoOrigemUfData = null;
      this.geograficoOrigemUfLoading = false;
      this.geograficoOrigemUfLoadedKey = null;
      this.geograficoOrigemUfRequestKey = null;
      this.geograficoOrigemUfError = null;
      this.geograficoBenchmarkData = null;
      this.geograficoBenchmarkLoading = false;
      this.geograficoBenchmarkLoadedKey = null;
      this.geograficoBenchmarkRequestKey = null;
      this.geograficoBenchmarkError = null;

      this.incompatibilidadePatologicaData = null;
      this.incompatibilidadePatologicaLoading = false;
      this.incompatibilidadePatologicaLoadedKey = null;
      this.incompatibilidadePatologicaRequestKey = null;
      this.incompatibilidadePatologicaError = null;

      this.falecidosData    = null;
      this.falecidosLoading = false;
      this.falecidosLoaded  = null;
      this.falecidosRequestKey = null;
      this.falecidosError   = null;

      this.prescritoresData    = null;
      this.prescritoresLoading = false;
      this.prescritoresLoaded  = null;
      this.prescritoresRequestKey = null;
      this.prescritoresError   = null;
      this.crmMedicoAlertasByKey = {};
      this.crmMedicoAlertasLoadingByKey = {};
      this.crmMedicoAlertasErrorByKey = {};

      this.crmTimelineDataset        = null;
      this.crmTimelineDatasetLoading = false;
      this.crmTimelineDatasetLoaded  = null;
      this.crmTimelineDatasetRequestKey = null;

      this.activeCrmViewMode = 'medicos';
      this.selectedTimelineEvent = null;

      this.cnpjsAvulsos        = new Map();
      this.cnpjsAvulsosLoading = false;
      this.cnpjAccessStatus    = 'idle';
      this.cnpjAccessCnpj      = null;
      this.cnpjAccessMessage   = null;
      this.cnpjAccessData      = null;
      this.bootstrapData       = null;
      this.bootstrapLoading    = false;
      this.bootstrapLoadedKey  = null;
      this.bootstrapRequestKey = null;
      this.bootstrapGeoData    = null;
      this.bootstrapPeriodSummary = null;

      this.municipiosRegiao        = [];
      this.municipiosRegiaoKey     = null;
      this.municipiosRegiaoLoading = false;

      this.metricPercentiles        = null;
      this.metricPercentilesLoading = false;
      this.metricPercentilesLoaded  = false;
      this.metricPercentilesRequestKey = null;

      this.sociosData    = null;
      this.sociosLoading = false;
      this.sociosLoaded  = false;
      this.sociosRequestKey = null;
      this.sociosError   = null;

      this.integrityAlertsData = null;
      this.integrityAlertsLoading = false;
      this.integrityAlertsLoaded = false;
      this.integrityAlertsRequestKey = null;
      this.integrityAlertsError = null;

      this.notaTecnicaReadinessData = null;
      this.notaTecnicaReadinessLoading = false;
      this.notaTecnicaReadinessLoadedKey = null;
      this.notaTecnicaReadinessRequestKey = null;
      this.notaTecnicaReadinessError = null;
      this.notaTecnicaPreparing = false;
      this.notaTecnicaPrepareError = null;

      this.relatorioPdfReadinessData = null;
      this.relatorioPdfReadinessLoading = false;
      this.relatorioPdfReadinessLoadedKey = null;
      this.relatorioPdfReadinessRequestKey = null;
      this.relatorioPdfReadinessError = null;
      this.relatorioPdfPreparing = false;
      this.relatorioPdfPrepareError = null;

      this.networkData    = null;
      this.networkLoading = false;
      this.networkLoaded  = false;
      this.networkRequestKey = null;
      this.networkLevelData = { 3: null, 4: null };
      this.networkLevelLoading = { 3: false, 4: false };
      this.networkLevelLoaded = { 3: null, 4: null };
      this.networkLevelRequestKey = { 3: null, 4: null };
      this.networkPresentationState = null;
      this.networkError   = null;
      this.prefetchRequestKey = null;
    },
  },
});

