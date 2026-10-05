import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { mount } from '@vue/test-utils';
import { createPinia, disposePinia, setActivePinia } from 'pinia';
import axios from 'axios';
import { TIMING } from '@/config/constants';
import { useSyncManager } from '../useSyncManager';

vi.mock('axios', () => ({ default: { get: vi.fn(), post: vi.fn(), put: vi.fn() } }));

describe('useSyncManager', () => {
  let wrapper;
  let manager;
  let pinia;
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    wrapper?.unmount();
    vi.clearAllTimers();
    vi.unstubAllGlobals();
    if (pinia) disposePinia(pinia);
    vi.restoreAllMocks();
    vi.useRealTimers();
  });

  it('apresenta uma falha visível se o servidor não iniciar a sincronização', async () => {
    axios.get.mockResolvedValue({
      data: { filters: {}, ui: { sidebarCollapsed: false, sidebarLocked: false } },
    });
    axios.post.mockRejectedValue(new Error('servidor indisponível'));
    axios.put.mockResolvedValue({ data: {} });
    pinia = createPinia();
    setActivePinia(pinia);
    wrapper = mount({
      setup() { manager = useSyncManager(); return {}; },
      template: '<div></div>',
    }, { global: { plugins: [pinia] } });
    vi.spyOn(console, 'error').mockImplementation(() => {});

    await manager.handleSync();
    expect(axios.post).toHaveBeenCalledTimes(1);
    expect(manager.showConfirmSync.value).toBe(false);
    expect(manager.syncError.value).toBe(true);
    expect(manager.syncErrorMessage.value).toContain('Falha ao conectar com o servidor');

    manager.dismissError();
    expect(manager.syncError.value).toBe(false);
    expect(manager.syncErrorMessage.value).toBe('');
    expect(manager.isSyncing.value).toBe(false);
    expect(manager.syncProgress.value).toBe(0);
  });

  it('interrompe a consulta ao receber erro do servidor e permite tentar novamente', async () => {
    axios.get.mockResolvedValue({ data: { progress: 65, status: 'error' } });
    axios.post.mockResolvedValue({ data: {} });
    const setIntervalSpy = vi.spyOn(globalThis, 'setInterval');
    const clearIntervalSpy = vi.spyOn(globalThis, 'clearInterval');
    pinia = createPinia();
    setActivePinia(pinia);
    wrapper = mount({
      setup() { manager = useSyncManager(); return {}; },
      template: '<div></div>',
    }, { global: { plugins: [pinia] } });

    await manager.handleSync();
    await vi.advanceTimersByTimeAsync(TIMING.POLL_INTERVAL);
    expect(manager.syncProgress.value).toBe(65);
    expect(manager.syncStatus.value).toBe('error');
    expect(manager.syncError.value).toBe(true);
    expect(manager.syncErrorMessage.value).toContain('erro durante a sincronização');

    axios.get.mockResolvedValue({ data: { progress: 100, status: 'ready' } });
    manager.retrySync();
    await Promise.resolve();
    expect(axios.post).toHaveBeenCalledTimes(2);
    expect(manager.syncError.value).toBe(false);
    const retryPollingTimer = setIntervalSpy.mock.results.at(-1).value;
    wrapper.unmount();
    wrapper = null;
    expect(clearIntervalSpy).toHaveBeenCalledWith(retryPollingTimer);
  });

  it('registra falha de transporte durante o polling e limpa o intervalo ao desmontar', async () => {
    axios.get.mockRejectedValue(new Error('sem conexão'));
    axios.post.mockResolvedValue({ data: {} });
    pinia = createPinia();
    setActivePinia(pinia);
    wrapper = mount({
      setup() { manager = useSyncManager(); return {}; },
      template: '<div></div>',
    }, { global: { plugins: [pinia] } });
    const error = vi.spyOn(console, 'error').mockImplementation(() => {});

    await manager.handleSync();
    await vi.advanceTimersByTimeAsync(TIMING.POLL_INTERVAL);
    expect(error).toHaveBeenCalledWith('Erro ao consultar status:', expect.any(Error));
    expect(manager.syncError.value).toBe(false);
    wrapper.unmount();
    wrapper = null;
    expect(vi.getTimerCount()).toBe(0);
  });

  it('aguarda o estado pronto, encerra polling e recarrega após o intervalo configurado', async () => {
    axios.get.mockResolvedValue({ data: { progress: 100, status: 'ready' } });
    axios.post.mockResolvedValue({ data: {} });
    pinia = createPinia();
    setActivePinia(pinia);
    wrapper = mount({
      setup() { manager = useSyncManager(); return {}; },
      template: '<div></div>',
    }, { global: { plugins: [pinia] } });
    const reload = vi.fn();

    await manager.handleSync();
    vi.stubGlobal('window', { location: { reload } });
    await vi.advanceTimersByTimeAsync(TIMING.POLL_INTERVAL);
    expect(manager.syncProgress.value).toBe(100);
    expect(manager.syncStatus.value).toBe('ready');
    await vi.advanceTimersByTimeAsync(TIMING.RELOAD_DELAY);
    expect(reload).toHaveBeenCalledOnce();
    wrapper.unmount();
    wrapper = null;
  });
});
