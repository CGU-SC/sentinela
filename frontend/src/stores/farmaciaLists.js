import { defineStore } from 'pinia';
import { computed, ref } from 'vue';
import axios from 'axios';
import { API_ENDPOINTS } from '@/config/api';
import { useEvidenciasStore } from '@/stores/evidencias';

const STORAGE_KEY = 'sentinela_farmacia_lists';

function readLocalSnapshot() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const data = JSON.parse(raw);
    return Array.isArray(data?.interesse) ? data.interesse : [];
  } catch {
    return [];
  }
}

function writeLocalSnapshot(list) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify({ interesse: list }));
  } catch (error) {
    console.warn('[farmaciaLists] Cópia local não pôde ser atualizada:', error);
  }
}

function errorMessage(error, fallback) {
  return typeof error?.response?.data?.detail === 'string'
    ? error.response.data.detail
    : fallback;
}

export const useFarmaciaListsStore = defineStore('farmaciaLists', () => {
  const interesse = ref([]);
  const localSnapshot = ref(readLocalSnapshot());
  const recoveryOptions = ref(null);
  const loadState = ref('loading');
  const saving = ref(false);
  const error = ref('');
  const localRecoveryAvailable = computed(() => localSnapshot.value.length > 0
    && interesse.value.length === 0);
  const canEdit = computed(() => loadState.value === 'ready' && !saving.value);

  async function loadRecoveryOptions() {
    try {
      const { data } = await axios.get(API_ENDPOINTS.preferencesRecoveryStatus);
      recoveryOptions.value = data;
    } catch (cause) {
      console.warn('[farmaciaLists] Não foi possível consultar cópias de recuperação:', cause);
      recoveryOptions.value = null;
    }
  }

  async function loadFromBackend() {
    loadState.value = 'loading';
    error.value = '';
    try {
      const { data } = await axios.get(API_ENDPOINTS.preferences);
      if (!Array.isArray(data?.watchlist)) {
        throw new Error('Resposta de preferências sem a lista obrigatória.');
      }
      interesse.value = data.watchlist;
      loadState.value = 'ready';
      if (data.watchlist.length > 0 || localSnapshot.value.length === 0) {
        writeLocalSnapshot(data.watchlist);
        localSnapshot.value = data.watchlist;
      }
    } catch (cause) {
      loadState.value = 'error';
      error.value = errorMessage(cause, 'Não foi possível carregar as Farmácias Monitoradas. Nenhuma lista foi alterada.');
      console.error('[farmaciaLists] Falha ao carregar lista:', cause);
    }
    if (loadState.value === 'error' || localRecoveryAvailable.value) {
      await loadRecoveryOptions();
    }
  }

  async function saveList(next) {
    if (!canEdit.value) return false;
    saving.value = true;
    error.value = '';
    try {
      const { data } = await axios.put(API_ENDPOINTS.preferencesWatchlist, { interesse: next });
      if (!Array.isArray(data?.watchlist)) {
        throw new Error('O servidor não confirmou a lista salva.');
      }
      interesse.value = data.watchlist;
      localSnapshot.value = data.watchlist;
      writeLocalSnapshot(data.watchlist);
      return true;
    } catch (cause) {
      error.value = errorMessage(cause, 'Não foi possível salvar as Farmácias Monitoradas. A alteração não foi confirmada.');
      console.error('[farmaciaLists] Falha ao salvar lista:', cause);
      return false;
    } finally {
      saving.value = false;
    }
  }

  const isInteresse = computed(() => (cnpj) =>
    interesse.value.some((item) => item.cnpj === cnpj),
  );

  async function adicionarInteresse(cnpj, razaoSocial) {
    if (!canEdit.value) return false;
    if (isInteresse.value(cnpj)) return true;
    return saveList([...interesse.value, {
      cnpj, razaoSocial, adicionadoEm: new Date().toISOString(), observacao: '',
    }]);
  }

  /**
   * Toda farmácia com evidência está na lista. Remover uma farmácia com
   * evidências exige confirmação e apaga as evidências junto — primeiro as
   * evidências, depois a farmácia: se a segunda etapa falhar, a farmácia fica
   * na lista sem evidências, o que ainda respeita a regra.
   * Retorna true (removida), false (falha, ver `error`) ou null (cancelado).
   */
  async function removerInteresse(cnpj, razaoSocial) {
    if (!canEdit.value) return false;
    error.value = '';
    const evidencias = useEvidenciasStore();
    await evidencias.garantirCarregado();
    if (evidencias.loadState !== 'ready') {
      error.value = 'Não foi possível verificar as evidências desta farmácia. Ela não foi removida.';
      return false;
    }
    if (evidencias.contar(cnpj) > 0) {
      const nome = razaoSocial
        || interesse.value.find((item) => item.cnpj === cnpj)?.razaoSocial
        || cnpj;
      const confirmado = await evidencias.confirmarRemocaoFarmacia(cnpj, nome);
      if (!confirmado) return null;
      try {
        await evidencias.removerDoCnpj(cnpj);
      } catch (cause) {
        error.value = `${cause.message} A farmácia não foi removida.`;
        return false;
      }
    }
    return saveList(interesse.value.filter((item) => item.cnpj !== cnpj));
  }

  async function toggleInteresse(cnpj, razaoSocial) {
    if (!canEdit.value) return false;
    return isInteresse.value(cnpj)
      ? removerInteresse(cnpj, razaoSocial)
      : adicionarInteresse(cnpj, razaoSocial);
  }

  async function setObservacao(cnpj, text) {
    if (!canEdit.value) return false;
    const next = interesse.value.map((item) => item.cnpj === cnpj
      ? { ...item, observacao: text, atualizadoEm: new Date().toISOString() }
      : item);
    return saveList(next);
  }

  const getObservacao = computed(() => (cnpj) =>
    interesse.value.find((item) => item.cnpj === cnpj)?.observacao || '',
  );

  async function restoreFromFile(source) {
    if (!['backup', 'corrupt'].includes(source) || saving.value) return false;
    saving.value = true;
    error.value = '';
    try {
      const { data } = await axios.post(API_ENDPOINTS.preferencesRecovery, { source });
      if (!Array.isArray(data?.watchlist)) throw new Error('Restauração sem lista válida.');
      interesse.value = data.watchlist;
      localSnapshot.value = data.watchlist;
      writeLocalSnapshot(data.watchlist);
      loadState.value = 'ready';
      await loadRecoveryOptions();
      return true;
    } catch (cause) {
      error.value = errorMessage(cause, 'Não foi possível restaurar a lista. Os arquivos originais foram preservados.');
      return false;
    } finally {
      saving.value = false;
    }
  }

  async function restoreFromLocal() {
    if (!localRecoveryAvailable.value || loadState.value !== 'ready') return false;
    return saveList(localSnapshot.value);
  }

  loadFromBackend();

  return {
    interesse, loadState, saving, error, canEdit, recoveryOptions,
    localRecoveryAvailable, localSnapshot, isInteresse, getObservacao,
    loadFromBackend, loadRecoveryOptions, toggleInteresse, adicionarInteresse, removerInteresse, setObservacao,
    restoreFromFile, restoreFromLocal,
  };
});
