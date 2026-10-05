import { afterEach, describe, expect, it, vi } from 'vitest';
import { createPinia, disposePinia, setActivePinia } from 'pinia';
import { effectScope, nextTick, ref } from 'vue';
import axios from 'axios';
import { useFilterStore } from '@/stores/filters';
import { useCrmPrescricoesAnalysisStore } from '@/stores/crmPrescricoesAnalysis';
import { useCrmFiltrosMedicoStore } from '@/stores/crmFiltrosMedico';
import { useCrmMedicosFixadosStore } from '@/stores/crmMedicosFixados';
import { buildCrmAnalysisParams, getCrmMapLevel, useCrmPrescricoesAnalysis } from '../useCrmPrescricoesAnalysis';

vi.mock('axios', () => ({ default: { get: vi.fn(), put: vi.fn() } }));

describe('useCrmPrescricoesAnalysis', () => {
  let pinia;
  afterEach(() => { vi.clearAllTimers(); if (pinia) disposePinia(pinia); localStorage.clear(); vi.useRealTimers(); vi.restoreAllMocks(); });

  it('escolhe o nível do mapa pelo território selecionado', () => {
    const filters = { selectedRegiaoSaude: 'Todos', selectedUF: 'Todos' };
    expect(getCrmMapLevel(filters)).toBe('uf');
    filters.selectedUF = 'SP';
    expect(getCrmMapLevel(filters)).toBe('municipio');
    filters.selectedRegiaoSaude = '3500001';
    expect(getCrmMapLevel(filters)).toBe('regiao');
  });

  it('ativa a análise com parâmetros reativos e limpa o watcher ao sair do escopo', async () => {
    axios.get.mockResolvedValue({ data: { filters: {}, ui: { sidebarCollapsed: false, sidebarLocked: false } } });
    localStorage.clear();
    pinia = createPinia();
    setActivePinia(pinia);
    useFilterStore();
    const analysis = useCrmPrescricoesAnalysisStore();
    const activate = vi.spyOn(analysis, 'activate').mockResolvedValue(undefined);
    const fetchPage = vi.spyOn(analysis, 'fetchRankingPage').mockResolvedValue(undefined);
    const mapLevel = ref('uf');
    const scope = effectScope();
    const api = scope.run(() => useCrmPrescricoesAnalysis(mapLevel));
    await nextTick();
    expect(activate).toHaveBeenCalledTimes(1);
    expect(activate.mock.calls[0][0].map_level).toBe('uf');

    mapLevel.value = 'municipio';
    await nextTick();
    expect(activate).toHaveBeenCalledTimes(2);
    expect(activate.mock.calls[1][0].map_level).toBe('municipio');
    api.fetchAnalysis();
    api.fetchRankingPage(2, 50, 'no_medico', 'asc', 'CRM 800');
    expect(activate).toHaveBeenCalledTimes(3);
    expect(fetchPage).toHaveBeenCalledWith(2, 50, 'no_medico', 'asc', 'CRM 800');
    scope.stop();
    mapLevel.value = 'regiao';
    await nextTick();
    expect(activate).toHaveBeenCalledTimes(3);
  });

  it('reaproveita resultados preparados ao entrar na página e chama cache completo', async () => {
    axios.get.mockResolvedValue({ data: { filters: {}, ui: { sidebarCollapsed: false, sidebarLocked: false } } });
    localStorage.clear();
    pinia = createPinia();
    setActivePinia(pinia);
    const filters = useFilterStore();
    const medicalFilters = useCrmFiltrosMedicoStore();
    useCrmMedicosFixadosStore();
    const analysis = useCrmPrescricoesAnalysisStore();
    const key = JSON.stringify(buildCrmAnalysisParams(filters, medicalFilters, 'uf'));
    analysis.activeKey = key;
    analysis.cacheVersion = 1;
    analysis.cacheEntries[key] = { map: { mapa: [] } };
    analysis.mapResponse = { mapa: [] };
    analysis.rankingResponseKey = key;
    analysis.rankingResponse = { ranking: [] };
    analysis.isMapLoading = false;
    analysis.isRankingLoading = false;
    analysis.mapError = null;
    analysis.rankingError = null;
    const activate = vi.spyOn(analysis, 'activate').mockResolvedValue(undefined);
    const scope = effectScope();
    scope.run(() => useCrmPrescricoesAnalysis(ref('uf')));
    await nextTick();
    expect(activate).not.toHaveBeenCalled();
    scope.stop();
  });

  it.each([
    ['activeKey', (store) => { store.activeKey = 'stale'; }],
    ['cacheVersion', (store) => { store.cacheVersion = null; }],
    ['map cache', (store, key) => { store.cacheEntries[key] = {}; }],
    ['mapResponse', (store) => { store.mapResponse = null; }],
    ['rankingResponseKey', (store) => { store.rankingResponseKey = 'stale'; }],
    ['rankingResponse', (store) => { store.rankingResponse = null; }],
    ['isMapLoading', (store) => { store.isMapLoading = true; }],
    ['isRankingLoading', (store) => { store.isRankingLoading = true; }],
    ['mapError', (store) => { store.mapError = 'erro'; }],
    ['rankingError', (store) => { store.rankingError = 'erro'; }],
  ])('refaz a análise quando o estado preparado não atende ao contrato: %s', async (_caseName, invalidate) => {
    axios.get.mockResolvedValue({ data: { filters: {}, ui: { sidebarCollapsed: false, sidebarLocked: false } } });
    localStorage.clear();
    pinia = createPinia();
    setActivePinia(pinia);
    const filters = useFilterStore();
    const medicalFilters = useCrmFiltrosMedicoStore();
    useCrmMedicosFixadosStore();
    const analysis = useCrmPrescricoesAnalysisStore();
    const key = JSON.stringify(buildCrmAnalysisParams(filters, medicalFilters, 'uf'));
    analysis.activeKey = key;
    analysis.cacheVersion = 1;
    analysis.cacheEntries[key] = { map: {} };
    analysis.mapResponse = {};
    analysis.rankingResponseKey = key;
    analysis.rankingResponse = {};
    analysis.isMapLoading = false;
    analysis.isRankingLoading = false;
    analysis.mapError = null;
    analysis.rankingError = null;
    invalidate(analysis, key);
    const activate = vi.spyOn(analysis, 'activate').mockResolvedValue(undefined);
    const scope = effectScope();
    scope.run(() => useCrmPrescricoesAnalysis(ref('uf')));
    await nextTick();
    expect(activate).toHaveBeenCalledOnce();
    scope.stop();
  });

  it('aguarda a digitação nos filtros de estabelecimento e cancela debounce ao sair', async () => {
    vi.useFakeTimers();
    axios.get.mockResolvedValue({ data: { filters: {}, ui: { sidebarCollapsed: false, sidebarLocked: false } } });
    localStorage.clear();
    pinia = createPinia();
    setActivePinia(pinia);
    const filters = useFilterStore();
    const analysis = useCrmPrescricoesAnalysisStore();
    const activate = vi.spyOn(analysis, 'activate').mockResolvedValue(undefined);
    const scope = effectScope();
    scope.run(() => useCrmPrescricoesAnalysis(ref('uf')));
    await nextTick();
    expect(activate).toHaveBeenCalledOnce();
    filters.selectedCnpjRaiz = '12345678';
    await nextTick();
    expect(activate).toHaveBeenCalledOnce();
    vi.advanceTimersByTime(449);
    expect(activate).toHaveBeenCalledOnce();
    vi.advanceTimersByTime(1);
    expect(activate).toHaveBeenCalledTimes(2);

    filters.selectedCnpjRaiz = '87654321';
    await nextTick();
    scope.stop();
    vi.advanceTimersByTime(500);
    expect(activate).toHaveBeenCalledTimes(2);
  });
});
