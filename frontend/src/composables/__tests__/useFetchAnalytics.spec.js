import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { createPinia, disposePinia, setActivePinia } from 'pinia';
import { effectScope, nextTick, ref } from 'vue';
import axios from 'axios';
import { buildAnalyticsParams, useAnalyticsStore } from '@/stores/analytics';
import { useFilterStore } from '@/stores/filters';
import { useFetchAnalytics } from '../useFetchAnalytics';

vi.mock('axios', () => ({ default: { get: vi.fn(), put: vi.fn() } }));

describe('useFetchAnalytics', () => {
  let pinia;
  beforeEach(() => { vi.useFakeTimers(); });
  afterEach(() => {
    vi.clearAllTimers();
    if (pinia) disposePinia(pinia);
    localStorage.clear();
    vi.restoreAllMocks();
    vi.useRealTimers();
  });

  it('exige as seções do resumo na criação', () => {
    expect(() => useFetchAnalytics()).toThrow('useFetchAnalytics exige as secoes do resumo usadas pela tela.');
  });

  it('suspende fetch enquanto inativo e busca os conjuntos habilitados ao ativar', async () => {
    axios.get.mockResolvedValue({ data: { filters: {}, ui: { sidebarCollapsed: false, sidebarLocked: false } } });
    localStorage.clear();
    pinia = createPinia();
    setActivePinia(pinia);
    const filters = useFilterStore();
    const analytics = useAnalyticsStore();
    filters.selectedUF = 'SP';
    const summary = vi.spyOn(analytics, 'fetchDashboardSummary').mockResolvedValue(undefined);
    const factor = vi.spyOn(analytics, 'fetchFatorRisco').mockResolvedValue(undefined);
    const production = vi.spyOn(analytics, 'fetchProducaoSemestral').mockResolvedValue(undefined);
    const alerts = vi.spyOn(analytics, 'fetchAlertasPanorama').mockResolvedValue(undefined);
    const national = vi.spyOn(analytics, 'fetchSentinelaUFNacional').mockResolvedValue(undefined);
    const active = ref(false);
    const scope = effectScope();
    scope.run(() => useFetchAnalytics({
      secoes: ['kpis', 'ufs'],
      includeFatorRisco: true,
      includeProducaoSemestral: true,
      includeAlertasPanorama: true,
      active,
    }));
    await nextTick();
    expect(summary).not.toHaveBeenCalled();

    active.value = true;
    await nextTick();
    expect(summary).toHaveBeenCalledWith(expect.any(Object), ['kpis', 'ufs']);
    expect(factor).toHaveBeenCalledTimes(1);
    expect(production).toHaveBeenCalledTimes(1);
    expect(alerts).toHaveBeenCalledTimes(1);
    expect(national).toHaveBeenCalledTimes(1);
    scope.stop();
  });

  it('evita refetch do resumo fresco, mas preenche blocos auxiliares ainda vazios', async () => {
    axios.get.mockResolvedValue({ data: { filters: {}, ui: { sidebarCollapsed: false, sidebarLocked: false } } });
    localStorage.clear();
    pinia = createPinia();
    setActivePinia(pinia);
    const filters = useFilterStore();
    filters.selectedUF = 'SP';
    const analytics = useAnalyticsStore();
    const freshKey = JSON.stringify(buildAnalyticsParams(filters.apiParams));
    analytics.sectionKeys.kpis = freshKey;
    const summary = vi.spyOn(analytics, 'fetchDashboardSummary').mockResolvedValue(undefined);
    const factor = vi.spyOn(analytics, 'fetchFatorRisco').mockResolvedValue(undefined);
    const production = vi.spyOn(analytics, 'fetchProducaoSemestral').mockResolvedValue(undefined);
    const alerts = vi.spyOn(analytics, 'fetchAlertasPanorama').mockResolvedValue(undefined);
    const national = vi.spyOn(analytics, 'fetchSentinelaUFNacional').mockResolvedValue(undefined);
    const active = ref(true);
    const scope = effectScope();
    scope.run(() => useFetchAnalytics({
      secoes: ['kpis'],
      includeFatorRisco: true,
      includeProducaoSemestral: true,
      includeAlertasPanorama: true,
      active,
    }));
    await nextTick();
    expect(summary).not.toHaveBeenCalled();
    expect(factor).toHaveBeenCalledOnce();
    expect(production).toHaveBeenCalledOnce();
    expect(alerts).toHaveBeenCalledOnce();
    expect(national).not.toHaveBeenCalled();

    analytics.fatorRisco = [1];
    analytics.producaoSemestral = [1];
    analytics.alertasPanorama = {};
    active.value = false;
    await nextTick();
    active.value = true;
    await nextTick();
    expect(summary).not.toHaveBeenCalled();
    expect(factor).toHaveBeenCalledOnce();
    expect(production).toHaveBeenCalledOnce();
    expect(alerts).toHaveBeenCalledOnce();
    scope.stop();
  });

  it('respeita período inválido, contexto nacional desabilitado e filtros de estabelecimento com debounce', async () => {
    axios.get.mockResolvedValue({ data: { filters: {}, ui: { sidebarCollapsed: false, sidebarLocked: false } } });
    localStorage.clear();
    pinia = createPinia();
    setActivePinia(pinia);
    const filters = useFilterStore();
    const analytics = useAnalyticsStore();
    const summary = vi.spyOn(analytics, 'fetchDashboardSummary').mockResolvedValue(undefined);
    const national = vi.spyOn(analytics, 'fetchSentinelaUFNacional').mockResolvedValue(undefined);
    filters.selectedUF = 'SP';
    filters.periodo = [new Date(2024, 0, 1), null];
    const inactiveScope = effectScope();
    inactiveScope.run(() => useFetchAnalytics({ secoes: ['kpis'] }));
    await nextTick();
    expect(summary).not.toHaveBeenCalled();
    expect(national).not.toHaveBeenCalled();
    inactiveScope.stop();

    filters.periodo = [new Date(2024, 0, 1), new Date(2024, 5, 30)];
    analytics.sectionKeys.kpis = JSON.stringify(buildAnalyticsParams(filters.apiParams));
    const scope = effectScope();
    const active = ref(false);
    const api = scope.run(() => useFetchAnalytics({
      secoes: ['kpis'], includeNationalContext: false, active,
    }));
    await nextTick();
    api.fetchAll();
    expect(summary).toHaveBeenCalledOnce();
    active.value = true;
    await nextTick();
    expect(national).not.toHaveBeenCalled();

    vi.useFakeTimers();
    filters.selectedCnpjRaiz = '12345678';
    await nextTick();
    expect(summary).toHaveBeenCalledOnce();
    vi.advanceTimersByTime(449);
    expect(summary).toHaveBeenCalledOnce();
    vi.advanceTimersByTime(1);
    expect(summary).toHaveBeenCalledTimes(2);
    scope.stop();
  });

  it('só busca contexto nacional quando há período e UF selecionada', async () => {
    axios.get.mockResolvedValue({ data: { filters: {}, ui: { sidebarCollapsed: false, sidebarLocked: false } } });
    localStorage.clear();
    pinia = createPinia();
    setActivePinia(pinia);
    const filters = useFilterStore();
    filters.periodo = [new Date(2024, 0, 1), new Date(2024, 5, 30)];
    filters.selectedUF = 'Todos';
    const analytics = useAnalyticsStore();
    const summary = vi.spyOn(analytics, 'fetchDashboardSummary').mockResolvedValue(undefined);
    const national = vi.spyOn(analytics, 'fetchSentinelaUFNacional').mockResolvedValue(undefined);
    const scope = effectScope();
    scope.run(() => useFetchAnalytics({ secoes: ['kpis'] }));
    await nextTick();
    expect(summary).toHaveBeenCalledOnce();
    expect(national).not.toHaveBeenCalled();

    filters.selectedUF = '';
    await nextTick();
    expect(national).not.toHaveBeenCalled();

    filters.selectedUF = 'SP';
    await nextTick();
    expect(national).toHaveBeenCalledOnce();
    scope.stop();
  });

  it('abandona o debounce se a página ficar inativa antes da execução', async () => {
    axios.get.mockResolvedValue({ data: { filters: {}, ui: { sidebarCollapsed: false, sidebarLocked: false } } });
    localStorage.clear();
    pinia = createPinia();
    setActivePinia(pinia);
    const filters = useFilterStore();
    filters.selectedUF = 'SP';
    const analytics = useAnalyticsStore();
    const summary = vi.spyOn(analytics, 'fetchDashboardSummary').mockResolvedValue(undefined);
    vi.spyOn(analytics, 'fetchSentinelaUFNacional').mockResolvedValue(undefined);
    const active = ref(true);
    const scope = effectScope();
    scope.run(() => useFetchAnalytics({ secoes: ['kpis'], active }));
    await nextTick();
    expect(summary).toHaveBeenCalledOnce();

    filters.selectedCnpjRaiz = '12345678';
    await nextTick();
    active.value = false;
    vi.advanceTimersByTime(450);
    await nextTick();

    expect(summary).toHaveBeenCalledOnce();
    scope.stop();
  });
});
