import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { createPinia, disposePinia, setActivePinia } from 'pinia';
import { effectScope, nextTick, ref } from 'vue';
import axios from 'axios';
import { useFilterStore } from '@/stores/filters';
import { useRiskIndicatorsStore } from '@/stores/riskIndicators';
import { useRiskIndicatorAnalysis } from '../useRiskIndicatorAnalysis';

vi.mock('axios', () => ({ default: { get: vi.fn(), put: vi.fn() } }));

describe('useRiskIndicatorAnalysis', () => {
  let pinia;
  beforeEach(() => { vi.useFakeTimers(); });
  afterEach(() => { vi.clearAllTimers(); if (pinia) disposePinia(pinia); localStorage.clear(); vi.useRealTimers(); vi.restoreAllMocks(); });

  it('consulta o indicador selecionado e mantém paginação sob comando explícito', () => {
    axios.get.mockResolvedValue({ data: { filters: {}, ui: { sidebarCollapsed: false, sidebarLocked: false } } });
    localStorage.clear();
    pinia = createPinia();
    setActivePinia(pinia);
    useFilterStore();
    const risk = useRiskIndicatorsStore();
    risk.preferencesLoaded = true;
    risk.selectedRiskIndicator = 'ticket_medio';
    const summary = vi.spyOn(risk, 'fetchRiskIndicatorSummary').mockResolvedValue(undefined);
    const table = vi.spyOn(risk, 'fetchRiskIndicatorEstablishments').mockResolvedValue(undefined);
    const scope = effectScope();
    const api = scope.run(() => useRiskIndicatorAnalysis({ includeTable: false }));

    expect(summary).toHaveBeenCalledWith('ticket_medio', expect.any(Object));
    expect(table).not.toHaveBeenCalled();
    api.fetchRiskIndicatorEstablishmentsPage('ticket_medio', { page: 3, pageSize: 50 });
    expect(table).toHaveBeenCalledWith('ticket_medio', expect.any(Object), { page: 3, pageSize: 50 });
    scope.stop();
  });

  it('aguarda preferências, indicador e ativação antes de consultar a tabela', async () => {
    axios.get.mockResolvedValue({ data: { filters: {}, ui: { sidebarCollapsed: false, sidebarLocked: false } } });
    localStorage.clear();
    pinia = createPinia();
    setActivePinia(pinia);
    useFilterStore();
    const risk = useRiskIndicatorsStore();
    const summary = vi.spyOn(risk, 'fetchRiskIndicatorSummary').mockResolvedValue(undefined);
    const table = vi.spyOn(risk, 'fetchRiskIndicatorEstablishments').mockResolvedValue(undefined);
    const active = ref(false);
    const scope = effectScope();
    scope.run(() => useRiskIndicatorAnalysis({ active, includeTable: true }));
    await Promise.resolve();
    expect(summary).not.toHaveBeenCalled();
    expect(table).not.toHaveBeenCalled();

    risk.preferencesLoaded = true;
    await Promise.resolve();
    expect(summary).not.toHaveBeenCalled();
    risk.selectedRiskIndicator = 'ticket_medio';
    await Promise.resolve();
    expect(summary).not.toHaveBeenCalled();
    active.value = true;
    await Promise.resolve();
    expect(summary).toHaveBeenCalledWith('ticket_medio', expect.any(Object));
    expect(table).toHaveBeenCalledWith('ticket_medio', expect.any(Object), { page: 1 });
    scope.stop();
  });

  it('pula resultados ainda frescos, refaz após filtros de estabelecimento e cancela timer no dispose', async () => {
    vi.useFakeTimers();
    axios.get.mockResolvedValue({ data: { filters: {}, ui: { sidebarCollapsed: false, sidebarLocked: false } } });
    localStorage.clear();
    pinia = createPinia();
    setActivePinia(pinia);
    const filters = useFilterStore();
    const risk = useRiskIndicatorsStore();
    risk.preferencesLoaded = true;
    risk.selectedRiskIndicator = 'ticket_medio';
    const summaryParams = { ...filters.indicadoresApiParams };
    const tableParams = { ...filters.indicadoresTabelaApiParams };
    risk.summaryParamsKey = JSON.stringify({ indicador: 'ticket_medio', params: summaryParams });
    risk.tableParamsKey = JSON.stringify({
      indicador: 'ticket_medio',
      params: tableParams,
      page: 1,
      pageSize: risk.cnpjsRows,
      sortField: risk.cnpjsSortField,
      sortOrder: risk.cnpjsSortOrder,
    });
    risk.isLoading = false;
    risk.isTableLoading = false;
    const summary = vi.spyOn(risk, 'fetchRiskIndicatorSummary').mockResolvedValue(undefined);
    const table = vi.spyOn(risk, 'fetchRiskIndicatorEstablishments').mockResolvedValue(undefined);
    const active = ref(true);
    const scope = effectScope();
    scope.run(() => useRiskIndicatorAnalysis({ active }));
    await Promise.resolve();
    expect(summary).not.toHaveBeenCalled();
    expect(table).not.toHaveBeenCalled();

    active.value = false;
    await Promise.resolve();
    active.value = true;
    await Promise.resolve();
    expect(summary).not.toHaveBeenCalled();
    filters.selectedCnpjRaiz = '12345678';
    await Promise.resolve();
    vi.advanceTimersByTime(450);
    expect(summary).toHaveBeenCalledOnce();
    expect(table).toHaveBeenCalledOnce();

    filters.selectedCnpjRaiz = '87654321';
    await Promise.resolve();
    scope.stop();
    vi.advanceTimersByTime(500);
    expect(summary).toHaveBeenCalledOnce();
  });

  it('aguarda uma chave de indicador antes de iniciar consultas', async () => {
    axios.get.mockResolvedValue({ data: { filters: {}, ui: { sidebarCollapsed: false, sidebarLocked: false } } });
    localStorage.clear();
    pinia = createPinia();
    setActivePinia(pinia);
    const filters = useFilterStore();
    const risk = useRiskIndicatorsStore();
    risk.preferencesLoaded = true;
    const summary = vi.spyOn(risk, 'fetchRiskIndicatorSummary').mockResolvedValue(undefined);
    const table = vi.spyOn(risk, 'fetchRiskIndicatorEstablishments').mockResolvedValue(undefined);
    const scope = effectScope();
    scope.run(() => useRiskIndicatorAnalysis());
    await nextTick();
    expect(summary).not.toHaveBeenCalled();
    expect(table).not.toHaveBeenCalled();

    filters.selectedCnpjRaiz = '12345678';
    await nextTick();
    expect(summary).not.toHaveBeenCalled();
    expect(table).not.toHaveBeenCalled();
    scope.stop();
  });

  it('refaz consulta quando a tabela correspondente ainda está carregando', async () => {
    axios.get.mockResolvedValue({ data: { filters: {}, ui: { sidebarCollapsed: false, sidebarLocked: false } } });
    localStorage.clear();
    pinia = createPinia();
    setActivePinia(pinia);
    const filters = useFilterStore();
    const risk = useRiskIndicatorsStore();
    risk.preferencesLoaded = true;
    risk.selectedRiskIndicator = 'ticket_medio';
    risk.summaryParamsKey = JSON.stringify({
      indicador: 'ticket_medio',
      params: { ...filters.indicadoresApiParams },
    });
    risk.tableParamsKey = JSON.stringify({
      indicador: 'ticket_medio',
      params: { ...filters.indicadoresTabelaApiParams },
      page: 1,
      pageSize: risk.cnpjsRows,
      sortField: risk.cnpjsSortField,
      sortOrder: risk.cnpjsSortOrder,
    });
    risk.isLoading = false;
    risk.isTableLoading = true;
    const summary = vi.spyOn(risk, 'fetchRiskIndicatorSummary').mockResolvedValue(undefined);
    const table = vi.spyOn(risk, 'fetchRiskIndicatorEstablishments').mockResolvedValue(undefined);
    const scope = effectScope();
    scope.run(() => useRiskIndicatorAnalysis());
    await nextTick();

    expect(summary).toHaveBeenCalledOnce();
    expect(table).toHaveBeenCalledWith('ticket_medio', expect.any(Object), { page: 1 });
    scope.stop();
  });

  it('abandona o debounce se a tela ficar inativa antes da consulta', async () => {
    vi.useFakeTimers();
    axios.get.mockResolvedValue({ data: { filters: {}, ui: { sidebarCollapsed: false, sidebarLocked: false } } });
    localStorage.clear();
    pinia = createPinia();
    setActivePinia(pinia);
    const filters = useFilterStore();
    const risk = useRiskIndicatorsStore();
    risk.preferencesLoaded = true;
    risk.selectedRiskIndicator = 'ticket_medio';
    const summary = vi.spyOn(risk, 'fetchRiskIndicatorSummary').mockResolvedValue(undefined);
    const table = vi.spyOn(risk, 'fetchRiskIndicatorEstablishments').mockResolvedValue(undefined);
    const active = ref(true);
    const scope = effectScope();
    scope.run(() => useRiskIndicatorAnalysis({ active }));
    await nextTick();
    expect(summary).toHaveBeenCalledOnce();
    expect(table).toHaveBeenCalledOnce();

    filters.selectedCnpjRaiz = '12345678';
    await nextTick();
    active.value = false;
    vi.advanceTimersByTime(450);
    await nextTick();

    expect(summary).toHaveBeenCalledOnce();
    expect(table).toHaveBeenCalledOnce();
    scope.stop();
  });
});
