import { afterEach, describe, expect, it, vi } from 'vitest';
import { nextTick, ref } from 'vue';
import { mount } from '@vue/test-utils';
import { useDelayedLoading } from '../useDelayedLoading';

describe('useDelayedLoading', () => {
  afterEach(() => vi.useRealTimers());

  it('só exibe o refresh quando o carregamento ultrapassa o atraso', async () => {
    vi.useFakeTimers();
    let loading;
    const wrapper = mount({
      setup() {
        loading = ref(false);
        return { loading, refreshing: useDelayedLoading(loading, 250) };
      },
      template: '<div></div>',
    });

    wrapper.vm.loading = true;
    await nextTick();
    await vi.advanceTimersByTimeAsync(249);
    expect(wrapper.vm.refreshing).toBe(false);
    await vi.advanceTimersByTimeAsync(1);
    expect(wrapper.vm.refreshing).toBe(true);

    wrapper.vm.loading = false;
    await nextTick();
    expect(wrapper.vm.refreshing).toBe(false);
    wrapper.unmount();
  });

  it('cancela um atraso curto e limpa o timer ao desmontar o componente', async () => {
    vi.useFakeTimers();
    let loading;
    let refreshing;
    const wrapper = mount({
      setup() {
        loading = ref(false);
        refreshing = useDelayedLoading(loading, 100);
        return { loading, refreshing };
      },
      template: '<div></div>',
    });
    wrapper.vm.loading = true;
    await nextTick();
    wrapper.vm.loading = false;
    await nextTick();
    await vi.advanceTimersByTimeAsync(100);
    expect(wrapper.vm.refreshing).toBe(false);

    wrapper.vm.loading = true;
    await nextTick();
    wrapper.unmount();
    await vi.advanceTimersByTimeAsync(100);
    expect(refreshing.value).toBe(false);
  });
});
