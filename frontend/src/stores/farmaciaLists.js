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

function validateUltimaRemocao(data) {
  if (!data || !Array.isArray(data.farmacias) || (data.removido_em !== null && typeof data.removido_em !== 'string')
    || data.farmacias.some((item) => typeof item?.cnpj !== 'string' || typeof item.razaoSocial !== 'string'
      || !Number.isInteger(item.evidencias_count) || item.evidencias_count < 0)) {
    throw new Error('O servidor não informou o contrato da última remoção.');
  }
}

function validateRecoveryOptions(data) {
  for (const source of ['backup', 'corrupt']) {
    const copy = data?.[source];
    const counts = ['watchlist_count', 'evidencias_count', 'missing_watchlist_count', 'missing_evidencias_count',
      'farmacias_mantidas_count'];
    if (!copy || typeof copy.exists !== 'boolean' || typeof copy.valid !== 'boolean'
      || !['joint', 'separate'].includes(copy.kind) || typeof copy.evidencias_backup_valid !== 'boolean'
      || counts.some((key) => copy[key] !== null && (!Number.isInteger(copy[key]) || copy[key] < 0))) {
      throw new Error('O servidor não informou o contrato de recuperação da lista e das evidências.');
    }
  }
}

export const useFarmaciaListsStore = defineStore('farmaciaLists', () => {
  const interesse = ref([]);
  const localSnapshot = ref(readLocalSnapshot());
  const recoveryOptions = ref(null);
  const recoveryError = ref('');
  /** Farmácias da última remoção ainda fora da lista (para o "Desfazer"). */
  const ultimaRemocao = ref([]);
  const ultimaRemocaoError = ref('');
  const loadState = ref('loading');
  const saving = ref(false);
  const error = ref('');
  const localRecoveryAvailable = computed(() => localSnapshot.value.length > 0
    && interesse.value.length === 0);
  const canEdit = computed(() => loadState.value === 'ready' && !saving.value);
  /**
   * O aviso de recuperação só aparece em incidente: cópia inválida, evidência
   * perdida de farmácia monitorada, lista que não abre ou que ficou vazia, ou
   * farmácias só na cópia isolada. Remover uma farmácia de propósito também
   * deixa a farmácia só na cópia de segurança, mas isso é coberto pelo "Desfazer".
   */
  const recoveryAvailable = computed(() => Boolean(recoveryOptions.value?.principal?.evidencias_error)
    || ['backup', 'corrupt'].some((source) => {
    const copy = recoveryOptions.value?.[source];
    if (!copy?.exists) return false;
    const listaPerdida = copy.watchlist_count > 0
      && (loadState.value === 'error' || (loadState.value === 'ready' && interesse.value.length === 0));
    return !copy.valid || Boolean(copy.evidencias_error) || copy.missing_evidencias_count > 0 || listaPerdida
      || (source === 'corrupt' && copy.missing_watchlist_count > 0);
    }));

  async function loadRecoveryOptions() {
    recoveryError.value = '';
    try {
      const { data } = await axios.get(API_ENDPOINTS.preferencesRecoveryStatus);
      validateRecoveryOptions(data);
      recoveryOptions.value = data;
    } catch (cause) {
      console.warn('[farmaciaLists] Não foi possível consultar cópias de recuperação:', cause);
      recoveryOptions.value = null;
      recoveryError.value = errorMessage(cause, 'Não foi possível consultar as cópias da lista e das evidências. Verifique se o servidor está atualizado.');
    }
  }

  async function loadUltimaRemocao() {
    ultimaRemocaoError.value = '';
    try {
      const { data } = await axios.get(API_ENDPOINTS.preferencesWatchlistUltimaRemocao);
      validateUltimaRemocao(data);
      ultimaRemocao.value = data.farmacias;
    } catch (cause) {
      console.warn('[farmaciaLists] Não foi possível consultar a última remoção:', cause);
      ultimaRemocao.value = [];
      ultimaRemocaoError.value = errorMessage(cause, 'Não foi possível consultar a última remoção para desfazê-la.');
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
    await loadRecoveryOptions();
    if (loadState.value === 'ready') await loadUltimaRemocao();
  }

  async function refreshEvidencias(action) {
    const evidencias = useEvidenciasStore();
    // Aguarda uma consulta anterior antes de buscar o estado após a gravação.
    await evidencias.garantirCarregado();
    await evidencias.carregar();
    if (evidencias.loadState !== 'ready') {
      error.value = `${action} no servidor, mas não foi possível atualizar as evidências na tela. Recarregue a página.`;
    }
  }

  async function saveList(next) {
    if (!canEdit.value) return false;
    saving.value = true;
    error.value = '';
    const removed = interesse.value.some((item) => !next.some((candidate) => candidate.cnpj === item.cnpj));
    try {
      const { data } = await axios.put(API_ENDPOINTS.preferencesWatchlist, { interesse: next });
      if (!Array.isArray(data?.watchlist)) {
        throw new Error('O servidor não confirmou a lista salva.');
      }
      interesse.value = data.watchlist;
      localSnapshot.value = data.watchlist;
      writeLocalSnapshot(data.watchlist);
      if (removed) await refreshEvidencias('A remoção foi concluída');
      await loadRecoveryOptions();
      await loadUltimaRemocao();
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
   * evidências exige confirmação. O servidor guarda uma cópia conjunta e
   * atualiza a lista e as evidências sob o mesmo bloqueio.
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

  async function restoreFromFile(source, includeEvidenceBackup = false) {
    if (!['backup', 'corrupt'].includes(source) || saving.value) return false;
    saving.value = true;
    error.value = '';
    try {
      const { data } = await axios.post(API_ENDPOINTS.preferencesRecovery, { source }, {
        params: { incluir_evidencias_backup: includeEvidenceBackup },
      });
      if (!Array.isArray(data?.watchlist)) throw new Error('Restauração sem lista válida.');
      interesse.value = data.watchlist;
      localSnapshot.value = data.watchlist;
      writeLocalSnapshot(data.watchlist);
      loadState.value = 'ready';
      await refreshEvidencias('A restauração foi concluída');
      await loadRecoveryOptions();
      await loadUltimaRemocao();
      return true;
    } catch (cause) {
      error.value = errorMessage(cause, 'Não foi possível restaurar a lista. Os arquivos originais foram preservados.');
      return false;
    } finally {
      saving.value = false;
    }
  }

  /** Devolve só esta farmácia (registro e evidências) da cópia da última remoção. */
  async function desfazerRemocao(cnpj) {
    if (!canEdit.value) return false;
    const removida = ultimaRemocao.value.find((item) => item.cnpj === cnpj);
    if (!removida) return false;
    saving.value = true;
    error.value = '';
    try {
      const { data } = await axios.post(API_ENDPOINTS.preferencesWatchlistDesfazerRemocao, { cnpj });
      if (!Array.isArray(data?.watchlist)) throw new Error('O servidor não confirmou a lista restaurada.');
      interesse.value = data.watchlist;
      localSnapshot.value = data.watchlist;
      writeLocalSnapshot(data.watchlist);
      if (removida.evidencias_count > 0) await refreshEvidencias('A remoção foi desfeita');
      await loadRecoveryOptions();
      await loadUltimaRemocao();
      return true;
    } catch (cause) {
      error.value = errorMessage(cause, 'Não foi possível desfazer a remoção. A lista não foi alterada.');
      console.error('[farmaciaLists] Falha ao desfazer remoção:', cause);
      await loadUltimaRemocao();
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
    interesse, loadState, saving, error, canEdit, recoveryOptions, recoveryError, recoveryAvailable,
    localRecoveryAvailable, localSnapshot, isInteresse, getObservacao, ultimaRemocao, ultimaRemocaoError,
    loadFromBackend, loadRecoveryOptions, loadUltimaRemocao, toggleInteresse, adicionarInteresse, removerInteresse,
    setObservacao, desfazerRemocao, restoreFromFile, restoreFromLocal,
  };
});
