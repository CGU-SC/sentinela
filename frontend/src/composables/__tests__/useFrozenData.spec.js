import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { createPinia, disposePinia, setActivePinia } from 'pinia';
import { effectScope, nextTick, ref } from 'vue';
import axios from 'axios';
import { useFilterStore } from '@/stores/filters';
import { useFrozenData } from '../useFrozenData';

vi.mock('axios', () => ({ default: { get: vi.fn(), put: vi.fn() } }));

describe('useFrozenData', () => {
  let pinia;
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => { vi.clearAllTimers(); disposePinia(pinia); localStorage.clear(); vi.useRealTimers(); });

  it('preserva o dado anterior durante animação e enquanto há carregamento', async () => {
    axios.get.mockResolvedValue({ data: { filters: {}, ui: { sidebarCollapsed: false, sidebarLocked: false } } });
    localStorage.clear();
    pinia = createPinia();
    setActivePinia(pinia);
    const filters = useFilterStore();
    const scope = effectScope();
    const source = ref({ version: 1 });
    const loading = ref(false);
    const frozen = scope.run(() => useFrozenData(source, loading));
    expect(frozen.value).toEqual({ version: 1 });

    filters.isAnimating = true;
    source.value = { version: 2 };
    await nextTick();
    expect(frozen.value).toEqual({ version: 1 });

    filters.isAnimating = false;
    loading.value = true;
    await nextTick();
    loading.value = false;
    await nextTick();
    expect(frozen.value).toEqual({ version: 2 });
    loading.value = true;
    source.value = { version: 3 };
    await nextTick();
    expect(frozen.value).toEqual({ version: 2 });
    scope.stop();
  });

  it('aceita initialValue até a primeira atualização estável', async () => {
    axios.get.mockResolvedValue({ data: { filters: {}, ui: { sidebarCollapsed: false, sidebarLocked: false } } });
    localStorage.clear();
    pinia = createPinia();
    setActivePinia(pinia);
    useFilterStore();
    const scope = effectScope();
    const source = ref('novo');
    const frozen = scope.run(() => useFrozenData(source, ref(true), { initialValue: 'inicial' }));
    expect(frozen.value).toBe('inicial');
    scope.stop();
  });
});
