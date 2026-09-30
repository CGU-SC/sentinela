<script setup>
/**
 * Botão padrão de exportação (Excel/CSV) das abas do CNPJ.
 *
 * Fica sempre no mesmo lugar (barra de abas do Perfil de CRMs, Linha do tempo
 * e Falecidos); cada aba entrega o que exportar em `exportacao`:
 *   { itens, carregando, desabilitado, motivo, tooltip }
 * `itens` é o modelo do Menu do PrimeVue (grupos com rótulo do conteúdo e os
 * formatos). A aba continua dona do download: os comandos dos itens chamam a
 * exportação dela.
 */
import { ref } from 'vue';
import Menu from 'primevue/menu';

const props = defineProps({
  exportacao: { type: Object, required: true },
  menuId: { type: String, required: true },
});

const menu = ref(null);

function alternarMenu(event) {
  menu.value?.toggle(event);
}
</script>

<template>
  <span class="export-menu">
    <button
      class="export-menu-button"
      type="button"
      :disabled="props.exportacao.desabilitado || props.exportacao.carregando"
      :aria-busy="props.exportacao.carregando"
      aria-haspopup="menu"
      :aria-controls="props.menuId"
      :aria-label="props.exportacao.motivo ? `Exportar. ${props.exportacao.motivo}` : 'Exportar'"
      @click="alternarMenu"
    >
      <i :class="props.exportacao.carregando ? 'pi pi-spinner pi-spin' : 'pi pi-download'" aria-hidden="true" />
      <span>{{ props.exportacao.carregando ? 'Exportando…' : 'Exportar' }}</span>
      <i v-if="!props.exportacao.carregando" class="pi pi-chevron-down export-menu-caret" aria-hidden="true" />
    </button>
    <Menu :id="props.menuId" ref="menu" :model="props.exportacao.itens" :popup="true" />
    <i
      v-if="props.exportacao.tooltip"
      class="pi pi-info-circle export-menu-info"
      role="img"
      tabindex="0"
      aria-label="Informações sobre a exportação"
      v-tooltip.left="props.exportacao.tooltip"
    />
  </span>
</template>

<style scoped>
.export-menu { display: inline-flex; align-items: center; gap: 0.45rem; }
.export-menu-button {
  display: inline-flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.5rem 0.8rem;
  border: 1px solid var(--card-border);
  border-radius: 8px;
  background: var(--surface-card);
  color: var(--text-color);
  font: inherit;
  font-size: 0.75rem;
  font-weight: 500;
  cursor: pointer;
  transition: border-color 0.15s ease, color 0.15s ease;
}
.export-menu-button:hover:not(:disabled),
.export-menu-button:focus-visible {
  border-color: var(--primary-color);
  color: var(--primary-color);
}
.export-menu-button:focus-visible {
  outline: 2px solid var(--primary-color);
  outline-offset: 2px;
}
.export-menu-button:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
.export-menu-caret { font-size: 0.6rem; opacity: 0.7; }
.export-menu-info { font-size: 0.75rem; color: var(--text-secondary); cursor: help; }
</style>
