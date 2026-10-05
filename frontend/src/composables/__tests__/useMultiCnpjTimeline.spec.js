import { beforeEach, describe, expect, it, vi } from 'vitest';
import axios from 'axios';
import { useMultiCnpjTimeline } from '../useMultiCnpjTimeline';

vi.mock('axios', () => ({ default: { get: vi.fn() } }));

describe('useMultiCnpjTimeline', () => {
  beforeEach(() => { axios.get.mockReset(); });

  it('busca uma timeline uma vez por CPF e CNPJ e permite limpá-la', async () => {
    const payload = { transacoes: [{ id: 1 }] };
    axios.get.mockResolvedValue({ data: payload });
    const timeline = useMultiCnpjTimeline();

    await timeline.fetchTimeline('', '12345678000199');
    expect(axios.get).not.toHaveBeenCalled();
    await timeline.fetchTimeline('12345678900', '12345678000199');
    expect(timeline.timelineData.value).toEqual(payload);
    expect(timeline.timelineLoading.value).toBe(false);
    await timeline.fetchTimeline('12345678900', '12345678000199');
    expect(axios.get).toHaveBeenCalledTimes(1);

    timeline.clearTimeline();
    expect(timeline.timelineData.value).toBe(null);
    expect(timeline.timelineError.value).toBe(null);
  });

  it('registra falha e sempre encerra o estado de carregamento', async () => {
    const failure = new Error('indisponível');
    axios.get.mockRejectedValue(failure);
    vi.spyOn(console, 'error').mockImplementation(() => {});
    const timeline = useMultiCnpjTimeline();
    await timeline.fetchTimeline('98765432100', '98765432000199');
    expect(timeline.timelineError.value).toBe(failure);
    expect(timeline.timelineLoading.value).toBe(false);
  });
});
