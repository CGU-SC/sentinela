/**
 * Período de análise global (filtro "Período de Análise" da sidebar):
 * - Índices em AVAILABLE_MONTHS ↔ datas de filterStore.periodo
 * - Sincronização nos dois sentidos com filterStore.sliderValue
 */
import { computed, watch } from 'vue';
import { useFilterStore } from '@/stores/filters';
import { AVAILABLE_MONTHS as availableMonths } from '@/config/constants';

export function useSliderPeriodLogic() {
  const filterStore = useFilterStore();

  // ── Índices sincronizados com a store ────────────────────────────────────
  const timeSliderValue = computed({
    get: () => filterStore.sliderValue,
    set: (val) => { filterStore.sliderValue = val; },
  });

  const applySliderPeriod = (indices) => {
    const startDate  = availableMonths[indices[0]].date;
    const rawEndDate = availableMonths[indices[1]].date;
    const endDate    = new Date(rawEndDate.getFullYear(), rawEndDate.getMonth() + 1, 0);
    if (
      filterStore.periodo[0]?.getTime() !== startDate.getTime() ||
      filterStore.periodo[1]?.getTime() !== endDate.getTime()
    ) {
      filterStore.periodo = [startDate, endDate];
    }
  };

  const resetYears = () => {
     // Reseta para o período total (Início 2015 até Fim 2024)
     timeSliderValue.value = [0, availableMonths.length - 1];
     applySliderPeriod(timeSliderValue.value);
  };

  // ── Sincronização reversa: periodo → índices ─────────────────────────────
  watch(() => filterStore.periodo, (newVal) => {
    if (!newVal || newVal.length < 2 || !newVal[0] || !newVal[1]) return;
    const startIdx = availableMonths.findIndex(
      m => m.date.getFullYear() === newVal[0].getFullYear() && m.date.getMonth() === newVal[0].getMonth()
    );
    const endIdx = availableMonths.findIndex(
      m => m.date.getFullYear() === newVal[1].getFullYear() && m.date.getMonth() === newVal[1].getMonth()
    );
    if (startIdx !== -1 && endIdx !== -1) {
      if (startIdx !== timeSliderValue.value[0] || endIdx !== timeSliderValue.value[1]) {
        timeSliderValue.value = [startIdx, endIdx];
      }
    }
  }, { deep: true });

  return {
    availableMonths,
    timeSliderValue,
    applySliderPeriod,
    resetYears,
  };
}
