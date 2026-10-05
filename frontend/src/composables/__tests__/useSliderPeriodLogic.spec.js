import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { createPinia, disposePinia, setActivePinia } from 'pinia';
import { effectScope, nextTick } from 'vue';
import axios from 'axios';
import { AVAILABLE_MONTHS } from '@/config/constants';
import { useFilterStore } from '@/stores/filters';
import { useSliderPeriodLogic } from '../useSliderPeriodLogic';

vi.mock('axios', () => ({ default: { get: vi.fn(), put: vi.fn() } }));

describe('useSliderPeriodLogic', () => {
  let pinia;
  beforeEach(() => { vi.useFakeTimers(); });
  afterEach(async () => {
    await vi.runOnlyPendingTimersAsync();
    disposePinia(pinia);
    localStorage.clear();
    vi.useRealTimers();
  });

  it('sincroniza índices do slider com início e fim do mês selecionado', async () => {
    axios.get.mockResolvedValue({ data: { filters: {}, ui: { sidebarCollapsed: false, sidebarLocked: false } } });
    localStorage.clear();
    pinia = createPinia();
    setActivePinia(pinia);
    const filters = useFilterStore();
    const scope = effectScope();
    const slider = scope.run(() => useSliderPeriodLogic());

    slider.applySliderPeriod([0, 0]);
    expect(filters.periodo[0]).toEqual(AVAILABLE_MONTHS[0].date);
    expect(filters.periodo[1]).toEqual(new Date(AVAILABLE_MONTHS[0].date.getFullYear(), AVAILABLE_MONTHS[0].date.getMonth() + 1, 0));

    filters.periodo = [AVAILABLE_MONTHS[2].date, new Date(AVAILABLE_MONTHS[4].date.getFullYear(), AVAILABLE_MONTHS[4].date.getMonth() + 1, 0)];
    await nextTick();
    expect(slider.timeSliderValue.value).toEqual([2, 4]);
    const selectedPeriod = filters.periodo;
    slider.applySliderPeriod([2, 4]);
    expect(filters.periodo).toBe(selectedPeriod);

    filters.periodo = [AVAILABLE_MONTHS[2].date, null];
    await nextTick();
    expect(slider.timeSliderValue.value).toEqual([2, 4]);

    filters.periodo = [new Date(1900, 0, 1), new Date(1900, 1, 1)];
    await nextTick();
    expect(slider.timeSliderValue.value).toEqual([2, 4]);

    filters.periodo = null;
    await nextTick();
    filters.periodo = [AVAILABLE_MONTHS[2].date];
    await nextTick();
    filters.periodo = [null, AVAILABLE_MONTHS[4].date];
    await nextTick();
    filters.periodo = [AVAILABLE_MONTHS[2].date, AVAILABLE_MONTHS[4].date];
    await nextTick();
    expect(slider.timeSliderValue.value).toEqual([2, 4]);
    slider.resetYears();
    expect(slider.timeSliderValue.value).toEqual([0, AVAILABLE_MONTHS.length - 1]);
    scope.stop();
  });
});
