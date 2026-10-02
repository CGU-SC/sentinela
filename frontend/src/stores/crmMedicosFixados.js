import { defineStore } from 'pinia';

/**
 * Médicos fixados no ranking de /analises: o usuário fixa médicos em qualquer aba
 * (Resumo, Linha do tempo, Por mês) e, com "só fixados" ligado, as três abas
 * mostram apenas eles. O recorte se soma aos demais filtros (ver
 * buildCrmAnalysisParams): um fixado fora dos filtros não aparece.
 *
 * A lista é preferência do navegador (localStorage); a chave "só fixados" não é
 * guardada, para a página nunca abrir já recortada.
 */
/** Mesmo limite do backend (MEDICOS_FIXADOS_MAX em crm_analysis.py). */
export const CRM_MEDICOS_FIXADOS_MAX = 100;
const STORAGE_KEY = 'sentinela_crm_medicos_fixados';

function itemValido(item) {
  return typeof item?.id_medico === 'string' && item.id_medico !== '' && !item.id_medico.includes(',')
    && typeof item.nome === 'string' && typeof item.crm === 'string';
}

function lerSalvos() {
  try {
    const salvos = JSON.parse(localStorage.getItem(STORAGE_KEY) ?? '[]');
    if (!Array.isArray(salvos)) return [];
    const vistos = new Set();
    return salvos
      .filter((item) => itemValido(item) && !vistos.has(item.id_medico) && vistos.add(item.id_medico))
      .slice(0, CRM_MEDICOS_FIXADOS_MAX)
      .map(({ id_medico, nome, crm }) => ({ id_medico, nome, crm }));
  } catch {
    return [];
  }
}

export const useCrmMedicosFixadosStore = defineStore('crmMedicosFixados', {
  state: () => ({
    /** [{ id_medico, nome, crm }] na ordem em que foram fixados. */
    medicos: lerSalvos(),
    soFixados: false,
  }),
  getters: {
    ids: (state) => new Set(state.medicos.map((m) => m.id_medico)),
    total: (state) => state.medicos.length,
    /** Parâmetro das consultas do ranking e do "Por mês" (vazio com a chave desligada). */
    apiParams: (state) => (
      state.soFixados && state.medicos.length
        ? { ids_fixados: state.medicos.map((m) => m.id_medico).join(',') }
        : {}
    ),
  },
  actions: {
    salvar() {
      try { localStorage.setItem(STORAGE_KEY, JSON.stringify(this.medicos)); } catch { /* preferência só do navegador */ }
    },
    /**
     * Fixa ou solta um médico.
     * @param {{ id_medico: string, nome: string, crm: string }} medico
     * @returns {boolean} false quando o limite de fixados impede fixar mais um.
     */
    alternar(medico) {
      if (!itemValido(medico)) throw new Error(`Médico inválido para fixar: ${JSON.stringify(medico)}`);
      if (this.ids.has(medico.id_medico)) {
        this.soltar(medico.id_medico);
        return true;
      }
      if (this.medicos.length >= CRM_MEDICOS_FIXADOS_MAX) return false;
      this.medicos = [...this.medicos, { id_medico: medico.id_medico, nome: medico.nome, crm: medico.crm }];
      this.salvar();
      return true;
    },
    soltar(idMedico) {
      this.medicos = this.medicos.filter((m) => m.id_medico !== idMedico);
      if (!this.medicos.length) this.soFixados = false;
      this.salvar();
    },
    soltarTodos() {
      this.medicos = [];
      this.soFixados = false;
      this.salvar();
    },
    setSoFixados(valor) {
      this.soFixados = Boolean(valor) && this.medicos.length > 0;
    },
  },
});
