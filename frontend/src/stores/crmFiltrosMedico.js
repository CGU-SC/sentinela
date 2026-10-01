import { defineStore } from 'pinia';
import {
  CRM_ANTES_INSCRICAO_CHIP,
  CRM_FAIXAS,
  CRM_SEQUENCIA_SEVERIDADES,
  CRM_SITUACAO_CFM_CHIP,
  CRM_SITUACAO_CFM_OPCOES,
  CRM_UFS,
} from '@/config/crmFiltrosMedico';

const SITUACOES = new Set(CRM_SITUACAO_CFM_OPCOES.map((opcao) => opcao.value));
const SEVERIDADES = new Map(CRM_SEQUENCIA_SEVERIDADES.map((opcao) => [opcao.value, opcao]));
const FAIXA_VAZIA = Object.freeze({ min: null, max: null });

function formatarNumero(valor, casas) {
  return Number(valor).toLocaleString('pt-BR', { minimumFractionDigits: 0, maximumFractionDigits: casas });
}

/** Número de uma faixa com a unidade da config (ex.: "80%"). */
export function formatarValorFaixa(tipo, valor) {
  const config = CRM_FAIXAS[tipo];
  if (!config) throw new Error(`Faixa de filtro de médico desconhecida: ${tipo}`);
  return `${formatarNumero(valor, config.casas)}${config.sufixo}`;
}

/** Rótulo do chip de uma faixa: "Taxa/dia ≥ 30", "Exclusividade ≥ 80%"... */
function rotuloFaixa(tipo, config, { min, max }) {
  const fmt = (valor) => formatarValorFaixa(tipo, valor);
  if (min !== null && min === max) return `${config.chip} = ${fmt(min)}`;
  if (min !== null && max !== null) return `${config.chip} ${fmt(min)}–${fmt(max)}`;
  if (min !== null) return `${config.chip} ≥ ${fmt(min)}`;
  return `${config.chip} ≤ ${fmt(max)}`;
}

function faixaAtiva(faixa) {
  return faixa.min !== null || faixa.max !== null;
}

/**
 * Valida uma faixa já convertida para número (null = limite vazio).
 * @returns {string|null} mensagem de erro para o usuário, ou null se válida.
 */
export function validarFaixa(tipo, { min, max }) {
  const config = CRM_FAIXAS[tipo];
  if (!config) throw new Error(`Faixa de filtro de médico desconhecida: ${tipo}`);
  for (const valor of [min, max]) {
    if (valor === null) continue;
    if (!Number.isFinite(valor)) return 'Número inválido.';
    if (valor < 0) return 'O valor não pode ser negativo.';
    if (valor > config.max) return `Use valores até ${formatarValorFaixa(tipo, config.max)}.`;
    if (config.casas === 0 && !Number.isInteger(valor)) return 'Use um número inteiro.';
  }
  if (min !== null && max !== null && min > max) return 'O mínimo é maior que o máximo.';
  return null;
}

/**
 * Filtros de médico de /analises (grupos "Cadastro CFM", "Produção" e "Atuação nas farmácias").
 * Valem só durante a sessão (não são persistidos) e entram nos parâmetros do
 * mapa, do ranking e da aba "Por mês" (ver buildCrmAnalysisParams).
 */
export const useCrmFiltrosMedicoStore = defineStore('crmFiltrosMedico', {
  state: () => ({
    /** null (todos) | 'localizado' | 'nao_localizado' */
    situacaoCfm: null,
    /** UFs do CRM selecionadas (vazio = todas). */
    ufsCrm: [],
    antesInscricao: false,
    /** Severidade mínima das sequências (único CRM): null | 1..4. */
    sequenciaSeveridadeMin: null,
    /** Faixas por tipo (chaves de CRM_FAIXAS): { min, max }. */
    faixas: Object.fromEntries(Object.keys(CRM_FAIXAS).map((tipo) => [tipo, { ...FAIXA_VAZIA }])),
  }),

  getters: {
    /**
     * Parâmetros da API só com os filtros ligados (UFs ordenadas: a chave de
     * cache não muda com a ordem de clique).
     */
    apiParams: (state) => {
      const params = {};
      if (state.situacaoCfm) params.situacao_cfm = state.situacaoCfm;
      if (state.ufsCrm.length) params.uf_crm = [...state.ufsCrm].sort();
      if (state.antesInscricao) params.antes_inscricao = true;
      if (state.sequenciaSeveridadeMin !== null) params.sequencia_severidade_min = state.sequenciaSeveridadeMin;
      for (const [tipo, config] of Object.entries(CRM_FAIXAS)) {
        const { min, max } = state.faixas[tipo];
        if (min !== null) params[`${config.param}_min`] = min;
        if (max !== null) params[`${config.param}_max`] = max;
      }
      return params;
    },
    qtdAtivos: (state) => (
      (state.situacaoCfm ? 1 : 0)
      + state.ufsCrm.length
      + (state.antesInscricao ? 1 : 0)
      + (state.sequenciaSeveridadeMin !== null ? 1 : 0)
      + Object.values(state.faixas).filter(faixaAtiva).length
    ),
    /** Médicos não localizados não têm data de inscrição no CFM. */
    antesInscricaoDisponivel: (state) => state.situacaoCfm !== 'nao_localizado',
    /** Chips dos filtros ativos, na ordem do painel. */
    chips: (state) => [
      ...(state.situacaoCfm ? [{ key: 'situacao', label: CRM_SITUACAO_CFM_CHIP[state.situacaoCfm] }] : []),
      ...[...state.ufsCrm].sort().map((uf) => ({ key: `uf:${uf}`, label: `CRM ${uf}` })),
      ...(state.antesInscricao ? [{ key: 'antes', label: CRM_ANTES_INSCRICAO_CHIP }] : []),
      ...(state.sequenciaSeveridadeMin !== null
        ? [{ key: 'sequencia', label: SEVERIDADES.get(state.sequenciaSeveridadeMin).chip }]
        : []),
      ...Object.entries(CRM_FAIXAS)
        .filter(([tipo]) => faixaAtiva(state.faixas[tipo]))
        .map(([tipo, config]) => ({ key: `faixa:${tipo}`, label: rotuloFaixa(tipo, config, state.faixas[tipo]) })),
    ],
  },

  actions: {
    setSituacaoCfm(value) {
      if (!SITUACOES.has(value)) throw new Error(`Situação no CFM inválida: ${value}`);
      this.situacaoCfm = value;
      // Sem data de inscrição, o filtro "antes da 1ª inscrição" não se aplica.
      if (value === 'nao_localizado') this.antesInscricao = false;
    },
    /** Aplica a lista de UFs do CRM de uma vez (vazia = todas). */
    setUfsCrm(ufs) {
      const invalidas = ufs.filter((uf) => !CRM_UFS.includes(uf));
      if (invalidas.length) throw new Error(`UF do CRM inválida: ${invalidas.join(', ')}`);
      this.ufsCrm = [...new Set(ufs)].sort();
    },
    setAntesInscricao(value) {
      if (value && !this.antesInscricaoDisponivel) {
        throw new Error('Filtro "antes da 1ª inscrição" indisponível para médicos não localizados.');
      }
      this.antesInscricao = Boolean(value);
    },
    setSequenciaSeveridadeMin(value) {
      if (!SEVERIDADES.has(value)) throw new Error(`Severidade de sequência inválida: ${value}`);
      this.sequenciaSeveridadeMin = value;
    },
    /** Aplica uma faixa já validada (validarFaixa); null = limite vazio. */
    setFaixa(tipo, faixa) {
      const erro = validarFaixa(tipo, faixa);
      if (erro) throw new Error(`Faixa ${tipo} inválida: ${erro}`);
      const atual = this.faixas[tipo];
      if (atual.min === faixa.min && atual.max === faixa.max) return;
      this.faixas = { ...this.faixas, [tipo]: { min: faixa.min, max: faixa.max } };
    },
    removerChip(key) {
      if (key === 'situacao') this.situacaoCfm = null;
      else if (key === 'antes') this.antesInscricao = false;
      else if (key === 'sequencia') this.sequenciaSeveridadeMin = null;
      else if (key.startsWith('uf:')) this.ufsCrm = this.ufsCrm.filter((uf) => `uf:${uf}` !== key);
      else if (key.startsWith('faixa:') && CRM_FAIXAS[key.slice(6)]) this.setFaixa(key.slice(6), { ...FAIXA_VAZIA });
      else throw new Error(`Chip de filtro de médico desconhecido: ${key}`);
    },
    limpar() {
      this.situacaoCfm = null;
      this.ufsCrm = [];
      this.antesInscricao = false;
      this.sequenciaSeveridadeMin = null;
      this.faixas = Object.fromEntries(Object.keys(CRM_FAIXAS).map((tipo) => [tipo, { ...FAIXA_VAZIA }]));
    },
  },
});
