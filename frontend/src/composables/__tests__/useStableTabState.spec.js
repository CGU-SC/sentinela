import { afterEach, describe, expect, it, vi } from 'vitest';
import { createPinia, disposePinia, setActivePinia } from 'pinia';
import { effectScope, nextTick, ref } from 'vue';
import axios from 'axios';
import { useFilterStore } from '@/stores/filters';
import { useStableTabState } from '../useStableTabState';

vi.mock('axios', () => ({ default: { get: vi.fn(), put: vi.fn() } }));

describe('useStableTabState', () => {
  let pinia;
  afterEach(() => { disposePinia(pinia); localStorage.clear(); });

  it('separa carregamento inicial de atualização e congela os dados existentes', async () => {
    axios.get.mockResolvedValue({ data: { filters: {}, ui: { sidebarCollapsed: false, sidebarLocked: false } } });
    localStorage.clear();
    pinia = createPinia();
    setActivePinia(pinia);
    const filters = useFilterStore();
    const data = ref(null);
    const loading = ref(true);
    const error = ref(null);
    const scope = effectScope();
    const state = scope.run(() => useStableTabState(data, loading, error));
    expect(state.shouldShowInitialLoading.value).toBe(true);

    loading.value = false;
    data.value = [{ id: 1 }];
    await nextTick();
    expect(state.cachedData.value).toEqual([{ id: 1 }]);
    loading.value = true;
    await nextTick();
    expect(state.shouldShowInitialLoading.value).toBe(false);
    expect(state.isRefreshing.value).toBe(true);

    filters.isAnimating = true;
    expect(state.isRefreshing.value).toBe(false);
    scope.stop();
  });

  it('permite definir explicitamente quando existe dado utilizável', () => {
    axios.get.mockResolvedValue({ data: { filters: {}, ui: { sidebarCollapsed: false, sidebarLocked: false } } });
    localStorage.clear();
    pinia = createPinia();
    setActivePinia(pinia);
    useFilterStore();
    const scope = effectScope();
    const state = scope.run(() => useStableTabState(ref([]), ref(true), ref(null), {
      initialValue: [],
      hasCachedData: (value) => value.length > 0,
    }));
    expect(state.hasCachedData.value).toBe(false);
    expect(state.shouldShowInitialLoading.value).toBe(true);
    scope.stop();
  });
});
