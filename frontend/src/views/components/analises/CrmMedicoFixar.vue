<script setup>
/**
 * Botão de fixar/soltar um médico nas tabelas do ranking de /analises (abas
 * Resumo, Linha do tempo e Por mês). Aparece ao passar o mouse na linha; fica
 * sempre visível quando o médico está fixado.
 */
import { computed } from 'vue';
import { useToast } from 'primevue/usetoast';
import { CRM_MEDICOS_FIXADOS_MAX, useCrmMedicosFixadosStore } from '@/stores/crmMedicosFixados';
import PinIcon from '@/views/components/common/PinIcon.vue';

const props = defineProps({
  idMedico: { type: String, required: true },
  nome: { type: String, required: true },
  crm: { type: String, required: true },
});

const store = useCrmMedicosFixadosStore();
const toast = useToast();
const fixado = computed(() => store.ids.has(props.idMedico));

function alternar() {
  const feito = store.alternar({ id_medico: props.idMedico, nome: props.nome, crm: props.crm });
  if (!feito) {
    toast.add({
      severity: 'warn',
      summary: 'Limite de médicos fixados',
      detail: `Dá para fixar até ${CRM_MEDICOS_FIXADOS_MAX} médicos. Solte algum para fixar outro.`,
      life: 4000,
    });
  }
}
</script>

<template>
  <button
    type="button"
    class="medico-fixar"
    :class="{ 'is-fixado': fixado }"
    :aria-pressed="fixado"
    :aria-label="fixado ? `Soltar ${nome}` : `Fixar ${nome}`"
    v-tooltip.top="fixado ? 'Soltar médico' : 'Fixar médico'"
    @click.stop="alternar"
    @keydown.enter.stop
    @keydown.space.stop
  >
    <PinIcon :preenchido="fixado" />
  </button>
</template>

<style scoped>
.medico-fixar { display: inline-flex; flex-shrink: 0; align-items: center; justify-content: center; width: 2.5rem; height: 2.5rem; margin-right: -.35rem; padding: 0; border: 0; border-radius: 8px; background: transparent; color: var(--text-muted); font-size: 1.15rem; cursor: pointer; opacity: 0; transition: opacity .12s ease, background .12s ease, color .12s ease; }
tr:hover .medico-fixar, .medico-fixar:focus-visible, .medico-fixar.is-fixado { opacity: 1; }
.medico-fixar:hover { background: color-mix(in srgb, var(--text-color) 9%, transparent); color: var(--text-color-85); }
.medico-fixar:focus-visible { outline: 2px solid color-mix(in srgb, var(--primary-color) 70%, transparent); outline-offset: 1px; }
.medico-fixar.is-fixado { color: var(--primary-color); }
</style>
