/**
 * Seletor do "Período de análise" (MonthRangePicker): atalhos, intervalo
 * selecionado em competências (AAAAMM), rótulo do botão e aplicação.
 *
 * Fonte única para todo lugar que mostra o seletor (sidebar de filtros e o
 * chip de período de /listas): o estado é o período global da filterStore, via
 * useSliderPeriodLogic, então os seletores ficam sempre em sincronia.
 */
import { computed } from 'vue';
import { useFilterStore } from '@/stores/filters';
import { ANALYSIS_YEARS } from '@/config/constants';
import { useSliderPeriodLogic } from '@/composables/useSliderPeriodLogic';

export function usePeriodoAnalise() {
  const filterStore = useFilterStore();
  const { availableMonths, timeSliderValue, applySliderPeriod, resetYears } = useSliderPeriodLogic();

  // Competência AAAAMM de cada mês do filtro (mesma ordem de availableMonths).
  const COMPS_PERIODO = availableMonths.map((m) => m.date.getFullYear() * 100 + m.date.getMonth() + 1);
  const PERIODO_MIN = COMPS_PERIODO[0];
  const PERIODO_MAX = COMPS_PERIODO[COMPS_PERIODO.length - 1];

  function indiceDaCompetencia(comp) {
    const indice = COMPS_PERIODO.indexOf(comp);
    if (indice === -1) throw new Error(`Competência ${comp} fora do período de auditoria.`);
    return indice;
  }
  function formatCompetencia(comp) {
    return `${String(comp % 100).padStart(2, '0')}/${Math.floor(comp / 100)}`;
  }

  const periodoAtalhos = [
    { value: 'completo', label: 'Período completo', faixa: { inicio: PERIODO_MIN, fim: PERIODO_MAX } },
    { value: '2020-2024', label: '2020 a 2024', faixa: { inicio: 202001, fim: Math.min(PERIODO_MAX, 202412) } },
    ...ANALYSIS_YEARS.filter((ano) => ano >= 2020)
      .reverse()
      .map((ano) => ({
        value: `ano-${ano}`,
        label: String(ano),
        faixa: { inicio: Math.max(PERIODO_MIN, ano * 100 + 1), fim: Math.min(PERIODO_MAX, ano * 100 + 12) },
      })),
    { value: 'personalizado', label: 'Período personalizado', grade: true },
  ];
  const periodoSelecionado = computed(() => ({
    inicio: COMPS_PERIODO[timeSliderValue.value[0]],
    fim: COMPS_PERIODO[timeSliderValue.value[1]],
  }));
  const periodoAtalhoAtivo = computed(() => {
    const { inicio, fim } = periodoSelecionado.value;
    const atalho = periodoAtalhos.find((a) => a.faixa && a.faixa.inicio === inicio && a.faixa.fim === fim);
    return atalho ? atalho.value : 'personalizado';
  });
  // Botão do seletor: só o intervalo (ex.: "01/2024 a 12/2024").
  const periodoRotulo = computed(() => {
    const { inicio, fim } = periodoSelecionado.value;
    return `${formatCompetencia(inicio)} a ${formatCompetencia(fim)}`;
  });

  function aplicarPeriodo({ inicio, fim }) {
    filterStore.resetAnimationPreview();
    timeSliderValue.value = [indiceDaCompetencia(inicio), indiceDaCompetencia(fim)];
    applySliderPeriod(timeSliderValue.value);
  }
  function aplicarAtalhoPeriodo(valor) {
    const atalho = periodoAtalhos.find((a) => a.value === valor);
    if (!atalho?.faixa) throw new Error(`Atalho de período sem intervalo: ${valor}`);
    aplicarPeriodo(atalho.faixa);
  }

  return {
    availableMonths,
    timeSliderValue,
    applySliderPeriod,
    resetYears,
    PERIODO_MIN,
    PERIODO_MAX,
    periodoAtalhos,
    periodoSelecionado,
    periodoAtalhoAtivo,
    periodoRotulo,
    aplicarPeriodo,
    aplicarAtalhoPeriodo,
  };
}
