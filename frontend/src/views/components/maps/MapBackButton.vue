<script setup>
/**
 * Botão "voltar" dos mapas coropléticos (municípios, estabelecimentos e análises).
 *
 * Padrão visual único para as três telas: componente raiz mantém a classe
 * .map-back-button, que é referenciada por seletores de layout dos pais.
 */
defineProps({
  /** Texto do destino do botão (ex.: 'Brasil' ou a UF ativa). */
  label: { type: String, required: true },
  /** Tooltip opcional; renderiza v-tooltip.bottom apenas quando informado. */
  tooltip: { type: String, default: null },
});

defineEmits(['click']);
</script>

<template>
  <button
    type="button"
    class="map-back-button"
    v-tooltip.bottom="tooltip"
    @click="$emit('click')"
  >
    <i class="pi pi-arrow-left" />
    <span>{{ label }}</span>
  </button>
</template>

<style scoped>
.map-back-button {
  height: 2rem;
  padding: 0 0.65rem;
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
  border: 1px solid var(--card-border);
  border-radius: 6px;
  background: color-mix(in srgb, var(--card-bg) 92%, var(--primary-color) 8%);
  color: var(--text-muted);
  font-size: 0.7rem;
  font-weight: 500;
  cursor: pointer;
}

.map-back-button:hover {
  border-color: color-mix(in srgb, var(--primary-color) 42%, var(--card-border));
  color: var(--primary-color);
}

.map-back-button:focus {
  outline: none;
  box-shadow: none;
}

.map-back-button:focus-visible {
  outline: 1px solid var(--primary-color);
  outline-offset: 2px;
}
</style>
