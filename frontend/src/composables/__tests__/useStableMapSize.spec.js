import { afterEach, describe, expect, it, vi } from 'vitest';
import { mount } from '@vue/test-utils';
import { ref, nextTick, defineComponent, KeepAlive } from 'vue';
import { createPinia, disposePinia, setActivePinia } from 'pinia';
import axios from 'axios';
import { useFilterStore } from '@/stores/filters';
import { useStableMapSize } from '../useStableMapSize';
import { TIMING } from '@/config/constants';

vi.mock('axios', () => ({ default: { get: vi.fn(), put: vi.fn() } }));

describe('useStableMapSize', () => {
  let pinia;
  let wrapper;
  afterEach(() => {
    wrapper?.unmount();
    disposePinia(pinia);
    localStorage.clear();
    vi.unstubAllGlobals();
    vi.useRealTimers();
  });

  it('mede o contêiner, redimensiona o gráfico e desconecta o observador ao desmontar', async () => {
    axios.get.mockResolvedValue({ data: { filters: {}, ui: { sidebarCollapsed: false, sidebarLocked: false } } });
    localStorage.clear();
    pinia = createPinia();
    setActivePinia(pinia);
    useFilterStore();

    class TestResizeObserver {
      static latest;
      constructor(callback) { this.callback = callback; this.disconnected = false; TestResizeObserver.latest = this; }
      observe() {}
      disconnect() { this.disconnected = true; }
      trigger() { this.callback([]); }
    }
    vi.stubGlobal('ResizeObserver', TestResizeObserver);
    const resize = vi.fn();
    wrapper = mount({
      setup() {
        const container = ref(null);
        const chart = ref({ resize });
        return { container, ...useStableMapSize(container, chart) };
      },
      template: '<div ref="container"></div>',
    });

    let width = 640;
    let height = 360;
    Object.defineProperties(wrapper.element, {
      clientWidth: { configurable: true, get: () => width },
      clientHeight: { configurable: true, get: () => height },
    });
    wrapper.vm.measure();
    await nextTick();
    expect(wrapper.vm.hasMeasured).toBe(true);
    expect(wrapper.vm.containerWidth).toBe(640);
    expect(wrapper.vm.containerHeight).toBe(360);
    expect(resize).toHaveBeenCalledTimes(1);

    width = 800;
    TestResizeObserver.latest.trigger();
    await nextTick();
    expect(wrapper.vm.containerWidth).toBe(800);
    expect(resize).toHaveBeenCalledTimes(2);
    const observer = TestResizeObserver.latest;
    wrapper.unmount();
    expect(observer.disconnected).toBe(true);
    wrapper = null;
  });

  it('suspende medições durante a animação da sidebar e mede ao concluir a transição', async () => {
    axios.get.mockResolvedValue({ data: { filters: {}, ui: { sidebarCollapsed: false, sidebarLocked: false } } });
    localStorage.clear();
    pinia = createPinia();
    setActivePinia(pinia);
    const filters = useFilterStore();
    let prefersReducedMotion = false;
    Object.defineProperty(window, 'matchMedia', {
      configurable: true,
      value: vi.fn(() => ({ matches: prefersReducedMotion })),
    });
    class TestResizeObserver {
      static latest;
      constructor(callback) { this.callback = callback; this.observe = vi.fn(); this.disconnect = vi.fn(); TestResizeObserver.latest = this; }
      trigger() { this.callback([]); }
    }
    vi.stubGlobal('ResizeObserver', TestResizeObserver);
    vi.stubGlobal('requestAnimationFrame', (callback) => { callback(); return 1; });
    const resize = vi.fn();
    wrapper = mount(defineComponent({
      setup() {
        const container = ref(null);
        return { container, ...useStableMapSize(container, ref({ chart: { resize } })) };
      },
      template: '<div class="main-container"><div ref="container"></div></div>',
    }), { global: { plugins: [pinia] } });

    const container = wrapper.element.querySelector('div');
    let width = 640;
    let height = 360;
    Object.defineProperties(container, {
      clientWidth: { configurable: true, get: () => width },
      clientHeight: { configurable: true, get: () => height },
    });
    wrapper.vm.measure();
    await nextTick();
    expect(wrapper.vm.containerWidth).toBe(640);
    const observer = TestResizeObserver.latest;

    filters.sidebarCollapsed = !filters.sidebarCollapsed;
    width = 720;
    observer.trigger();
    expect(wrapper.vm.containerWidth).toBe(640);

    const wrongTransition = new Event('transitionend');
    Object.defineProperty(wrongTransition, 'propertyName', { value: 'opacity' });
    wrapper.element.dispatchEvent(wrongTransition);
    expect(wrapper.vm.containerWidth).toBe(640);
    const sidebarTransition = new Event('transitionend');
    Object.defineProperty(sidebarTransition, 'propertyName', { value: 'margin-left' });
    wrapper.element.dispatchEvent(sidebarTransition);
    await nextTick();
    expect(wrapper.vm.containerWidth).toBe(720);
    expect(resize).toHaveBeenCalledTimes(2);

    prefersReducedMotion = true;
    width = 840;
    filters.sidebarCollapsed = !filters.sidebarCollapsed;
    await nextTick();
    expect(wrapper.vm.containerWidth).toBe(840);
    expect(observer.observe).toHaveBeenCalledWith(container);
  });

  it('ignora containers ausentes, dimensões inválidas e medições repetidas', async () => {
    axios.get.mockResolvedValue({ data: { filters: {}, ui: { sidebarCollapsed: false, sidebarLocked: false } } });
    localStorage.clear();
    pinia = createPinia();
    setActivePinia(pinia);
    useFilterStore();
    class TestResizeObserver {
      static latest;
      constructor(callback) { this.callback = callback; TestResizeObserver.latest = this; }
      observe = vi.fn();
      disconnect = vi.fn();
    }
    vi.stubGlobal('ResizeObserver', TestResizeObserver);
    const resize = vi.fn();
    const emptyContainer = ref(null);
    const noContainer = mount({
      setup() { return { ...useStableMapSize(emptyContainer, ref({ resize })) }; },
      template: '<div></div>',
    });
    noContainer.vm.measure();
    expect(noContainer.vm.hasMeasured).toBe(false);
    noContainer.unmount();

    wrapper = mount({
      setup() {
        const container = ref(null);
        return { container, ...useStableMapSize(container, ref({ resize })) };
      },
      template: '<div ref="container"></div>',
    });
    let width = 0;
    let height = 100;
    Object.defineProperties(wrapper.element, {
      clientWidth: { configurable: true, get: () => width },
      clientHeight: { configurable: true, get: () => height },
    });
    expect(wrapper.vm.hasMeasured).toBe(false);
    width = 400;
    wrapper.vm.measure();
    await nextTick();
    expect(resize).toHaveBeenCalledOnce();
    wrapper.vm.measure();
    await nextTick();
    expect(resize).toHaveBeenCalledOnce();
    wrapper.unmount();
    wrapper = null;

    const noChart = mount({
      setup() {
        const container = ref(null);
        return { container, ...useStableMapSize(container, ref(null)) };
      },
      template: '<div ref="container"></div>',
    });
    Object.defineProperties(noChart.element, {
      clientWidth: { configurable: true, value: 320 },
      clientHeight: { configurable: true, value: 180 },
    });
    noChart.vm.measure();
    await nextTick();
    expect(noChart.vm.hasMeasured).toBe(true);
    noChart.unmount();
  });

  it('finaliza pelo timeout se o container não tem elemento de transição', async () => {
    vi.useFakeTimers();
    axios.get.mockResolvedValue({ data: { filters: {}, ui: { sidebarCollapsed: false, sidebarLocked: false } } });
    localStorage.clear();
    pinia = createPinia();
    setActivePinia(pinia);
    const filters = useFilterStore();
    class TestResizeObserver {
      static latest;
      constructor(callback) { this.callback = callback; TestResizeObserver.latest = this; }
      observe() {}
      disconnect() {}
    }
    vi.stubGlobal('ResizeObserver', TestResizeObserver);
    vi.stubGlobal('requestAnimationFrame', (callback) => { callback(); return 1; });
    const resize = vi.fn();
    wrapper = mount({
      setup() {
        const container = ref(null);
        return { container, ...useStableMapSize(container, ref({ resize })) };
      },
      template: '<div ref="container"></div>',
    });
    let width = 400;
    Object.defineProperties(wrapper.element, {
      clientWidth: { configurable: true, get: () => width },
      clientHeight: { configurable: true, get: () => 200 },
    });
    wrapper.element.closest = vi.fn(() => null);
    wrapper.vm.measure();
    await nextTick();
    width = 600;
    filters.sidebarCollapsed = !filters.sidebarCollapsed;
    await vi.advanceTimersByTimeAsync(TIMING.SIDEBAR_MOTION_MS * 1.25 + 1);
    await nextTick();
    expect(wrapper.vm.containerWidth).toBe(600);
    expect(resize).toHaveBeenCalledTimes(2);
  });

  it('observa novamente e redimensiona ao reativar uma view em KeepAlive', async () => {
    axios.get.mockResolvedValue({ data: { filters: {}, ui: { sidebarCollapsed: false, sidebarLocked: false } } });
    localStorage.clear();
    pinia = createPinia();
    setActivePinia(pinia);
    useFilterStore();
    class TestResizeObserver {
      static latest;
      constructor(callback) { this.callback = callback; this.observe = vi.fn(); this.disconnect = vi.fn(); TestResizeObserver.latest = this; }
    }
    vi.stubGlobal('ResizeObserver', TestResizeObserver);
    const resize = vi.fn();
    const MapView = defineComponent({
      setup() {
        const container = ref(null);
        return { container, ...useStableMapSize(container, ref({ resize })) };
      },
      template: '<div ref="container"></div>',
    });
    wrapper = mount(defineComponent({
      components: { MapView, KeepAlive },
      data: () => ({ active: true }),
      template: '<KeepAlive><MapView v-if="active" /></KeepAlive>',
    }), { global: { plugins: [pinia] } });
    const observer = TestResizeObserver.latest;
    expect(observer.observe).toHaveBeenCalled();
    wrapper.vm.active = false;
    await nextTick();
    expect(observer.disconnect).toHaveBeenCalled();
    wrapper.vm.active = true;
    await nextTick();
    await nextTick();
    expect(observer.observe.mock.calls.length).toBeGreaterThan(1);
    expect(resize).toHaveBeenCalled();
  });

  it('ignora mudanças da sidebar antes do observer e quando o container já saiu', async () => {
    axios.get.mockResolvedValue({ data: { filters: {}, ui: { sidebarCollapsed: false, sidebarLocked: false } } });
    localStorage.clear();
    pinia = createPinia();
    setActivePinia(pinia);
    const filters = useFilterStore();
    class TestResizeObserver {
      constructor(callback) { this.callback = callback; this.observe = vi.fn(); this.disconnect = vi.fn(); }
    }
    vi.stubGlobal('ResizeObserver', TestResizeObserver);
    const matchMedia = vi.fn(() => ({ matches: false }));
    Object.defineProperty(window, 'matchMedia', { configurable: true, value: matchMedia });
    wrapper = mount({
      setup() {
        const container = ref(null);
        const size = useStableMapSize(container, ref(null));
        filters.sidebarCollapsed = true;
        return { container, ...size };
      },
      template: '<div ref="container"></div>',
    });
    expect(matchMedia).not.toHaveBeenCalled();

    wrapper.vm.container = null;
    filters.sidebarCollapsed = false;
    expect(matchMedia).not.toHaveBeenCalled();
  });
});
