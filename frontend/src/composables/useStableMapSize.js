import { nextTick, onActivated, onBeforeUnmount, onDeactivated, onMounted, ref, watch } from 'vue';
import { useFilterStore } from '@/stores/filters';
import { TIMING } from '@/config/constants';

// Mantém o desenho do mapa estável enquanto a sidebar muda de largura.
// O gráfico é medido uma vez no tamanho final; demais mudanças de tamanho
// (janela, painéis internos) continuam sendo atendidas pelo ResizeObserver.
export function useStableMapSize(containerRef, chartRef) {
  const filterStore = useFilterStore();
  const containerWidth = ref(0);
  const containerHeight = ref(0);
  const hasMeasured = ref(false);
  let observer = null;
  let isSidebarMoving = false;
  let settleTimer = null;
  let transitionTarget = null;

  function resizeChart() {
    const instance = chartRef.value;
    if (instance?.chart?.resize) instance.chart.resize();
    else instance?.resize?.();
  }

  function measure() {
    const element = containerRef.value;
    if (!element) return;
    const width = element.clientWidth;
    const height = element.clientHeight;
    if (width <= 0 || height <= 0) return;
    if (hasMeasured.value && width === containerWidth.value && height === containerHeight.value) return;
    containerWidth.value = width;
    containerHeight.value = height;
    hasMeasured.value = true;
    nextTick(resizeChart);
  }

  function clearSidebarWait() {
    clearTimeout(settleTimer);
    settleTimer = null;
    transitionTarget?.removeEventListener('transitionend', onTransitionEnd);
    transitionTarget = null;
  }

  function finishSidebarMove() {
    clearSidebarWait();
    isSidebarMoving = false;
    requestAnimationFrame(measure);
  }

  function onTransitionEnd(event) {
    if (event.target === transitionTarget && event.propertyName === 'margin-left') {
      finishSidebarMove();
    }
  }

  watch(() => filterStore.sidebarCollapsed, () => {
    if (!observer || !containerRef.value) return;
    clearSidebarWait();
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
      nextTick(measure);
      return;
    }
    isSidebarMoving = true;
    transitionTarget = containerRef.value.closest('.main-container');
    transitionTarget?.addEventListener('transitionend', onTransitionEnd);
    settleTimer = window.setTimeout(finishSidebarMove, TIMING.SIDEBAR_MOTION_MS * 1.25);
  }, { flush: 'sync' });

  onMounted(() => {
    observer = new ResizeObserver(() => {
      if (!isSidebarMoving) measure();
    });
    if (containerRef.value) observer.observe(containerRef.value);
    measure();
  });

  onActivated(() => {
    if (observer && containerRef.value) observer.observe(containerRef.value);
    nextTick(() => {
      measure();
      // O KeepAlive pode recriar o gráfico enquanto a view está oculta.
      // Mesmo com o container no tamanho anterior, o canvas precisa ser redimensionado.
      resizeChart();
    });
  });

  onDeactivated(() => {
    observer?.disconnect();
    clearSidebarWait();
    isSidebarMoving = false;
  });

  onBeforeUnmount(() => {
    observer?.disconnect();
    clearSidebarWait();
  });

  return { containerWidth, containerHeight, hasMeasured, measure };
}
