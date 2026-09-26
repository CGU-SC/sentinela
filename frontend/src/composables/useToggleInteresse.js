import { useToast } from 'primevue/usetoast';
import { useFarmaciaListsStore } from '@/stores/farmaciaLists';

/**
 * Alterna a farmácia na lista de monitoradas e mostra a falha, se houver.
 * `null` significa que o usuário cancelou a remoção (farmácia com evidências).
 */
export function useToggleInteresse() {
  const toast = useToast();
  const farmaciaLists = useFarmaciaListsStore();

  return async function toggleInteresse(cnpj, razaoSocial) {
    const resultado = await farmaciaLists.toggleInteresse(cnpj, razaoSocial);
    if (resultado === false && farmaciaLists.loadState === 'ready') {
      toast.add({
        severity: 'error',
        summary: 'Lista não alterada',
        detail: farmaciaLists.error || 'Não foi possível salvar a alteração.',
        life: 6000,
      });
    }
    return resultado;
  };
}
