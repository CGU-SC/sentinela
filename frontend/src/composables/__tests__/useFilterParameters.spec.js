import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { createPinia, disposePinia, setActivePinia } from 'pinia';
import axios from 'axios';
import { useFilterStore } from '@/stores/filters';
import { useFilterParameters } from '../useFilterParameters';

vi.mock('axios', () => ({ default: { get: vi.fn(), put: vi.fn() } }));

describe('useFilterParameters', () => {
  let pinia;
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => { vi.clearAllTimers(); disposePinia(pinia); localStorage.clear(); vi.useRealTimers(); });

  it('expõe uma cópia dos parâmetros normalizados e validade do período da store', () => {
    axios.get.mockResolvedValue({ data: { filters: {}, ui: { sidebarCollapsed: false, sidebarLocked: false } } });
    localStorage.clear();
    pinia = createPinia();
    setActivePinia(pinia);
    const store = useFilterStore();
    const filters = useFilterParameters();
    const first = filters.getApiParams();
    expect(filters.isPeriodoValido()).toBe(true);
    first.cnpjRaiz = 'mutação local';
    expect(filters.getApiParams().cnpjRaiz).not.toBe('mutação local');
    store.periodo = [new Date(2024, 0, 1), null];
    expect(filters.isPeriodoValido()).toBe(false);
  });
});
