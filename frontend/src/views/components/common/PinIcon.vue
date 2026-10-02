<script setup>
/**
 * Ícone de alfinete ("fixar"). O PrimeIcons 6 não tem alfinete, e estrela/marcador
 * já significam a lista de interesse; por isso um SVG próprio, na cor do texto.
 */
defineProps({
  /** Preenchido = item fixado. */
  preenchido: { type: Boolean, default: false },
});
</script>

<template>
  <svg
    class="pin-icon"
    viewBox="0 0 24 24"
    :fill="preenchido ? 'currentColor' : 'none'"
    stroke="currentColor"
    stroke-width="2"
    stroke-linecap="round"
    stroke-linejoin="round"
    aria-hidden="true"
  >
    <path d="M12 17v5" />
    <path d="M9 10.76a2 2 0 0 1-1.11 1.79l-1.78.9A2 2 0 0 0 5 15.24V16a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1v-.76a2 2 0 0 0-1.11-1.79l-1.78-.9A2 2 0 0 1 15 10.76V7a1 1 0 0 1 1-1 2 2 0 0 0 0-4H8a2 2 0 0 0 0 4 1 1 0 0 1 1 1z" />
  </svg>
</template>

<style scoped>
.pin-icon { display: block; width: 1em; height: 1em; }
</style>
