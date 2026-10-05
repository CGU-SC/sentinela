import { beforeEach, describe, expect, it, vi } from 'vitest';
import { useToggleInteresse } from '../useToggleInteresse';

const mocks = vi.hoisted(() => ({
  addToast: vi.fn(),
  toggle: vi.fn(),
  store: { toggleInteresse: null, loadState: 'ready', error: '' },
}));

vi.mock('primevue/usetoast', () => ({ useToast: () => ({ add: mocks.addToast }) }));
vi.mock('@/stores/farmaciaLists', () => ({ useFarmaciaListsStore: () => mocks.store }));

describe('useToggleInteresse', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.store.toggleInteresse = mocks.toggle;
    mocks.store.loadState = 'ready';
    mocks.store.error = '';
  });

  it('delega a alternância e avisa quando a lista não foi alterada', async () => {
    mocks.toggle.mockResolvedValue(false);
    mocks.store.error = 'A remoção requer confirmação.';
    const toggleInteresse = useToggleInteresse();

    await expect(toggleInteresse('12345678000199', 'Farmácia')).resolves.toBe(false);
    expect(mocks.toggle).toHaveBeenCalledWith('12345678000199', 'Farmácia');
    expect(mocks.addToast).toHaveBeenCalledWith({
      severity: 'error',
      summary: 'Lista não alterada',
      detail: 'A remoção requer confirmação.',
      life: 6000,
    });
  });

  it('não mostra erro quando o usuário cancela a remoção', async () => {
    mocks.toggle.mockResolvedValue(null);
    const toggleInteresse = useToggleInteresse();
    await expect(toggleInteresse('12345678000199', 'Farmácia')).resolves.toBe(null);
    expect(mocks.addToast).not.toHaveBeenCalled();
  });

  it('usa a mensagem padrão quando a lista pronta não informa o erro e ignora estados de carregamento', async () => {
    mocks.toggle.mockResolvedValue(false);
    mocks.store.error = '';
    const toggleInteresse = useToggleInteresse();
    await expect(toggleInteresse('12345678000199', 'Farmácia')).resolves.toBe(false);
    expect(mocks.addToast).toHaveBeenCalledWith(expect.objectContaining({
      detail: 'Não foi possível salvar a alteração.',
    }));

    vi.clearAllMocks();
    mocks.store.toggleInteresse = mocks.toggle;
    mocks.store.loadState = 'loading';
    mocks.toggle.mockResolvedValue(false);
    await toggleInteresse('12345678000199', 'Farmácia');
    expect(mocks.addToast).not.toHaveBeenCalled();
  });
});
