import { defineStore } from 'pinia';
import { computed, ref } from 'vue';
import axios from 'axios';
import { API_ENDPOINTS } from '@/config/api';
import { useFarmaciaListsStore } from '@/stores/farmaciaLists';
import { useCnpjDetailStore } from '@/stores/cnpjDetail';

function errorMessage(error, fallback) {
  return typeof error?.response?.data?.detail === 'string'
    ? error.response.data.detail
    : fallback;
}

/** Identidade do item marcado — espelha a regra de duplicidade do backend. */
export function chaveEvidencia({ cnpj, tipo, dt_janela, hora, num_autorizacao }) {
  if (tipo === 'dia') return `${cnpj}|dia|${dt_janela}`;
  if (tipo === 'hora') return `${cnpj}|hora|${dt_janela}|${hora}`;
  if (tipo === 'autorizacao') return `${cnpj}|autorizacao|${num_autorizacao}`;
  throw new Error(`Tipo de evidência desconhecido: ${tipo}`);
}

function ordemCronologica(a, b) {
  const ka = `${a.dt_janela}|${String(a.hora ?? -1).padStart(2, '0')}|${a.snapshot?.horario ?? ''}`;
  const kb = `${b.dt_janela}|${String(b.hora ?? -1).padStart(2, '0')}|${b.snapshot?.horario ?? ''}`;
  return ka.localeCompare(kb);
}

export const useEvidenciasStore = defineStore('evidencias', () => {
  const itens = ref([]);
  const loadState = ref('idle'); // idle | loading | ready | error
  const error = ref('');
  const painelAberto = ref(false);
  const navegacaoPendente = ref(null);
  const remocaoPendente = ref(null); // { cnpj, nome, quantidade, resolve }
  let carregando = null;

  async function carregar() {
    if (carregando) return carregando;
    loadState.value = 'loading';
    error.value = '';
    carregando = (async () => {
      try {
        const { data } = await axios.get(API_ENDPOINTS.evidencias);
        if (!Array.isArray(data)) throw new Error('Resposta de evidências inválida.');
        itens.value = data;
        loadState.value = 'ready';
      } catch (cause) {
        loadState.value = 'error';
        error.value = errorMessage(cause, 'Não foi possível carregar a cesta de evidências.');
        console.error('[evidencias] Falha ao carregar:', cause);
      } finally {
        carregando = null;
      }
    })();
    return carregando;
  }

  function garantirCarregado() {
    if (loadState.value === 'idle' || loadState.value === 'error') return carregar();
    return carregando ?? Promise.resolve();
  }

  const porCnpj = computed(() => {
    const map = new Map();
    for (const item of itens.value) {
      if (!map.has(item.cnpj)) map.set(item.cnpj, []);
      map.get(item.cnpj).push(item);
    }
    for (const lista of map.values()) lista.sort(ordemCronologica);
    return map;
  });

  const porChave = computed(() => new Map(itens.value.map((item) => [chaveEvidencia(item), item])));

  function listarDoCnpj(cnpj) {
    return porCnpj.value.get(cnpj) ?? [];
  }

  function contar(cnpj) {
    return porCnpj.value.get(cnpj)?.length ?? 0;
  }

  function ultimaEm(cnpj) {
    const lista = porCnpj.value.get(cnpj);
    if (!lista?.length) return null;
    return lista.reduce((max, item) => (item.criado_em > max ? item.criado_em : max), lista[0].criado_em);
  }

  function encontrar(alvo) {
    return porChave.value.get(chaveEvidencia(alvo)) ?? null;
  }

  function exigirPronto() {
    if (loadState.value !== 'ready') {
      throw new Error(error.value || 'A cesta de evidências ainda não foi carregada. Nenhuma alteração foi feita.');
    }
  }

  /**
   * Marca um item. Toda farmácia com evidência fica na lista de monitoradas:
   * se ainda não estiver, é adicionada ANTES de gravar a evidência.
   * Retorna { evidencia, farmaciaAdicionada }. Erros sobem para quem chamou.
   */
  async function marcar(payload, { razaoSocial = '' } = {}) {
    exigirPronto();
    const farmaciaLists = useFarmaciaListsStore();
    let farmaciaAdicionada = false;
    if (!farmaciaLists.isInteresse(payload.cnpj)) {
      if (!farmaciaLists.canEdit) {
        throw new Error('A lista de Farmácias Monitoradas está indisponível. A evidência não foi salva.');
      }
      const ok = await farmaciaLists.adicionarInteresse(payload.cnpj, razaoSocial);
      if (!ok) {
        throw new Error(farmaciaLists.error || 'Não foi possível adicionar a farmácia às monitoradas. A evidência não foi salva.');
      }
      farmaciaAdicionada = true;
    }
    try {
      const { data } = await axios.post(API_ENDPOINTS.evidencias, payload);
      itens.value = [...itens.value, data];
      return { evidencia: data, farmaciaAdicionada };
    } catch (cause) {
      const detalhe = errorMessage(cause, 'Não foi possível salvar a evidência.');
      throw new Error(farmaciaAdicionada
        ? `${detalhe} A farmácia foi adicionada às Farmácias Monitoradas.`
        : detalhe);
    }
  }

  async function atualizarNota(id, nota) {
    exigirPronto();
    try {
      const { data } = await axios.patch(API_ENDPOINTS.evidencia(id), { nota });
      itens.value = itens.value.map((item) => (item.id === id ? data : item));
      return data;
    } catch (cause) {
      throw new Error(errorMessage(cause, 'Não foi possível salvar a nota.'));
    }
  }

  async function remover(id) {
    exigirPronto();
    try {
      await axios.delete(API_ENDPOINTS.evidencia(id));
      itens.value = itens.value.filter((item) => item.id !== id);
    } catch (cause) {
      throw new Error(errorMessage(cause, 'Não foi possível remover a evidência.'));
    }
  }

  async function removerDoCnpj(cnpj) {
    exigirPronto();
    try {
      await axios.delete(API_ENDPOINTS.evidenciasDoCnpj(cnpj));
      itens.value = itens.value.filter((item) => item.cnpj !== cnpj);
    } catch (cause) {
      throw new Error(errorMessage(cause, 'Não foi possível remover as evidências da farmácia.'));
    }
  }

  // ── Confirmação de remoção da farmácia (diálogo global em App.vue) ──────
  function confirmarRemocaoFarmacia(cnpj, nome) {
    if (remocaoPendente.value) remocaoPendente.value.resolve(false);
    return new Promise((resolve) => {
      remocaoPendente.value = { cnpj, nome, quantidade: contar(cnpj), resolve };
    });
  }

  function responderRemocao(confirmado) {
    const pendente = remocaoPendente.value;
    remocaoPendente.value = null;
    pendente?.resolve(Boolean(confirmado));
  }

  // ── Navegação até o item marcado ────────────────────────────────────────
  function alvoNavegacao(evidencia) {
    return {
      cnpj: evidencia.cnpj,
      date: evidencia.dt_janela,
      hour: evidencia.tipo === 'dia' ? 'all' : evidencia.hora,
      autorizacao: evidencia.tipo === 'autorizacao' ? evidencia.num_autorizacao : null,
    };
  }

  /** Abre a Cronologia no item. `cnpjAtual` é o CNPJ da tela aberta (ou null). */
  async function irPara(evidencia, router, cnpjAtual = null) {
    const alvo = alvoNavegacao(evidencia);
    const destino = { name: 'EstablishmentDetail', params: { cnpj: alvo.cnpj }, query: { s: 'autorizacoes' } };
    if (cnpjAtual === alvo.cnpj) {
      await router.replace(destino);
      useCnpjDetailStore().navigateTimeline(alvo.date, alvo.hour, alvo.autorizacao);
      return;
    }
    // A tela do CNPJ zera o estado ao abrir; ela consome a navegação depois do reset.
    navegacaoPendente.value = alvo;
    await router.push(destino);
  }

  function consumirNavegacaoPendente(cnpj) {
    const alvo = navegacaoPendente.value;
    if (!alvo || alvo.cnpj !== cnpj) return;
    navegacaoPendente.value = null;
    useCnpjDetailStore().navigateTimeline(alvo.date, alvo.hour, alvo.autorizacao);
  }

  carregar();

  return {
    itens, loadState, error, painelAberto, remocaoPendente,
    carregar, garantirCarregado, listarDoCnpj, contar, ultimaEm, encontrar,
    marcar, atualizarNota, remover, removerDoCnpj,
    confirmarRemocaoFarmacia, responderRemocao, irPara, consumirNavegacaoPendente,
  };
});
