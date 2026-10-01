<script setup>
/**
 * Chips dos filtros de médico ativos em /analises (acima do mapa): o recorte
 * fica visível mesmo com o painel da direita fora de vista.
 */
import { storeToRefs } from 'pinia';
import { useCrmFiltrosMedicoStore } from '@/stores/crmFiltrosMedico';

defineProps({
  /** Busca aplicada ao ranking (nome/CRM); vazio = sem busca. */
  busca: { type: String, required: true },
});
const emit = defineEmits(['limpar-busca']);

const filtrosStore = useCrmFiltrosMedicoStore();
const { chips } = storeToRefs(filtrosStore);

function limparTodos() {
  filtrosStore.limpar();
  emit('limpar-busca');
}
</script>

<template>
  <div v-if="chips.length || busca" class="crm-filtros-ativos" role="region" aria-label="Filtros dos médicos ativos">
    <span class="crm-filtros-ativos-titulo"><i class="pi pi-filter" aria-hidden="true" />Médicos:</span>
    <button
      v-if="busca"
      type="button"
      class="crm-filtro-chip"
      :aria-label="`Remover busca ${busca}`"
      @click="emit('limpar-busca')"
    >
      Busca: {{ busca }}<i class="pi pi-times" aria-hidden="true" />
    </button>
    <button
      v-for="chip in chips"
      :key="chip.key"
      type="button"
      class="crm-filtro-chip"
      :aria-label="`Remover filtro ${chip.label}`"
      @click="filtrosStore.removerChip(chip.key)"
    >
      {{ chip.label }}<i class="pi pi-times" aria-hidden="true" />
    </button>
    <button type="button" class="crm-filtros-limpar" @click="limparTodos">Limpar todos</button>
  </div>
</template>

<style scoped>
.crm-filtros-ativos { display: flex; flex-wrap: wrap; align-items: center; gap: 0.4rem; padding: 0.55rem 0.8rem; border: 1px solid var(--card-border); border-radius: 10px; background: var(--card-bg); }
.crm-filtros-ativos-titulo { display: inline-flex; align-items: center; gap: 0.35rem; margin-right: 0.15rem; color: var(--text-muted); font-size: 0.7rem; font-weight: 500; }
.crm-filtros-ativos-titulo .pi { color: var(--primary-color); font-size: 0.7rem; }
.crm-filtro-chip { display: inline-flex; align-items: center; gap: 0.4rem; min-height: 24px; padding: 0 0.55rem; border: 1px solid color-mix(in srgb, var(--primary-color) 40%, transparent); border-radius: 999px; background: color-mix(in srgb, var(--primary-color) 12%, transparent); color: var(--primary-color); font: inherit; font-size: 0.7rem; font-weight: 500; cursor: pointer; }
.crm-filtro-chip .pi { font-size: 0.6rem; opacity: 0.75; }
.crm-filtro-chip:hover, .crm-filtro-chip:focus-visible { background: color-mix(in srgb, var(--primary-color) 20%, transparent); }
.crm-filtro-chip:hover .pi { opacity: 1; }
.crm-filtro-chip:focus-visible, .crm-filtros-limpar:focus-visible { outline: 2px solid color-mix(in srgb, var(--primary-color) 70%, transparent); outline-offset: 2px; }
.crm-filtros-limpar { margin-left: auto; padding: 0.15rem 0.4rem; border: 0; border-radius: 5px; background: transparent; color: var(--color-error); font: inherit; font-size: 0.7rem; font-weight: 500; cursor: pointer; }
.crm-filtros-limpar:hover { background: color-mix(in srgb, var(--color-error) 10%, transparent); }
</style>
