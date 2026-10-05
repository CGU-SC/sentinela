import { afterEach, describe, expect, it, vi } from 'vitest';
import { fetchRegionalPayload, useRegional } from '../useRegional';

describe('useRegional', () => {
  afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks(); });

  it('carrega por ID regional e reutiliza o payload para a mesma chave', async () => {
    const payload = { municipios: [{ id_ibge7: 9990001 }] };
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => payload });
    vi.stubGlobal('fetch', fetchMock);
    const regional = useRegional();

    await regional.fetchRegional('ZZ', '2024-01-01', '2024-06-30', 9999001);
    await regional.fetchRegional('ZZ', '2024-01-01', '2024-06-30', 9999001);

    expect(regional.regionalData.value).toEqual(payload);
    expect(regional.regionalLoaded.value).toBe(true);
    expect(regional.regionalLoading.value).toBe(false);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(fetchMock.mock.calls[0][0]).toContain('regiao_id=9999001');
    await expect(fetchRegionalPayload(null, null, null, null)).resolves.toBe(null);
  });

  it('expõe uma mensagem de erro quando a API falha', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, status: 503 }));
    vi.spyOn(console, 'error').mockImplementation(() => {});
    const regional = useRegional();
    await regional.fetchRegional('ZZ', null, null, 9999002);
    expect(regional.regionalError.value).toBe('Não foi possível carregar os dados. Verifique a conexão com o servidor.');
    expect(regional.regionalLoaded.value).toBe(true);
    expect(regional.regionalLoading.value).toBe(false);
  });

  it('deduplica requisições concorrentes para o mesmo ID e guarda o resultado', async () => {
    let resolveResponse;
    const pendingResponse = new Promise((resolve) => { resolveResponse = resolve; });
    const fetchMock = vi.fn(() => pendingResponse);
    vi.stubGlobal('fetch', fetchMock);
    const first = fetchRegionalPayload('SP', null, null, 12345);
    const second = fetchRegionalPayload('SP', null, null, 12345);
    expect(fetchMock).toHaveBeenCalledOnce();
    resolveResponse({ ok: true, json: async () => ({ municipios: [] }) });
    await expect(Promise.all([first, second])).resolves.toEqual([
      { municipios: [] }, { municipios: [] },
    ]);
    await expect(fetchRegionalPayload('SP', null, null, 12345)).resolves.toEqual({ municipios: [] });
    expect(fetchMock).toHaveBeenCalledOnce();
  });

  it('remove uma requisição rejeitada para permitir nova tentativa e não altera estado sem escopo', async () => {
    const fetchMock = vi.fn()
      .mockRejectedValueOnce(new Error('timeout'))
      .mockResolvedValueOnce({ ok: true, json: async () => ({ municipios: ['retry'] }) });
    vi.stubGlobal('fetch', fetchMock);
    await expect(fetchRegionalPayload('RJ', null, null, 54321)).rejects.toThrow('timeout');
    await expect(fetchRegionalPayload('RJ', null, null, 54321)).resolves.toEqual({ municipios: ['retry'] });
    expect(fetchMock).toHaveBeenCalledTimes(2);

    const regional = useRegional();
    await regional.fetchRegional(null, null, null, null);
    expect(regional.regionalData.value).toBeNull();
    expect(regional.regionalLoading.value).toBe(false);
    expect(regional.regionalLoaded.value).toBe(false);
  });

  it('carrega outra chave depois do cache e expõe erro se o JSON não puder ser lido', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce({ ok: true, json: async () => ({ municipios: ['SP'] }) })
      .mockResolvedValueOnce({ ok: true, json: async () => ({ municipios: ['RJ'] }) })
      .mockResolvedValueOnce({ ok: true, json: async () => { throw new Error('JSON inválido'); } });
    vi.stubGlobal('fetch', fetchMock);
    vi.spyOn(console, 'error').mockImplementation(() => {});
    const regional = useRegional();

    await regional.fetchRegional('SP', null, null, 111);
    await regional.fetchRegional('RJ', null, null, 222);
    expect(regional.regionalData.value).toEqual({ municipios: ['RJ'] });
    expect(fetchMock).toHaveBeenCalledTimes(2);

    await regional.fetchRegional('RJ', '2025-01-01', '2025-06-30', 222);
    expect(regional.regionalError.value).toBe('Não foi possível carregar os dados. Verifique a conexão com o servidor.');
    expect(regional.regionalLoading.value).toBe(false);
    expect(regional.regionalLoaded.value).toBe(true);
    expect(fetchMock).toHaveBeenCalledTimes(3);
  });

  it('permite consulta apenas por ID regional quando a UF não foi fornecida', async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ municipios: ['por-id'] }) });
    vi.stubGlobal('fetch', fetchMock);

    await expect(fetchRegionalPayload('', null, null, 98765)).resolves.toEqual({ municipios: ['por-id'] });
    expect(fetchMock).toHaveBeenCalledOnce();
    expect(fetchMock.mock.calls[0][0]).toContain('regiao_id=98765');
  });

  it('usa a chave de UF quando o ID regional é nulo e normaliza UF ausente no escopo por ID', async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ municipios: [] }) });
    vi.stubGlobal('fetch', fetchMock);

    await expect(fetchRegionalPayload('DF')).resolves.toEqual({ municipios: [] });
    await expect(fetchRegionalPayload(null, null, null, 7654321)).resolves.toEqual({ municipios: [] });

    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(fetchMock.mock.calls[0][0]).toContain('uf=DF');
    expect(fetchMock.mock.calls[1][0]).toContain('regiao_id=7654321');
  });
});
