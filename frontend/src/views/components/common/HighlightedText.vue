<script setup>
// Portado de NuvoInvest/frontend/app/components/common/HighlightedText.vue.
import { computed } from 'vue';
import { highlightSegments } from '@/utils/textHighlight';

const props = defineProps({
  text: { type: String, required: true },
  query: { type: String, required: true },
});
const segments = computed(() => highlightSegments(props.text, props.query));
</script>

<template>
  <template v-for="(segment, index) in segments" :key="`${segment.matched ? 'match' : 'text'}-${segment.text}-${index}`">
    <mark v-if="segment.matched">{{ segment.text }}</mark>
    <template v-else>{{ segment.text }}</template>
  </template>
</template>

<style scoped>
mark {
  background: var(--search-highlight-bg);
  color: var(--search-highlight-text);
  border-radius: 3px;
  padding: 0 1px;
  box-shadow: inset 0 0 0 1px var(--search-highlight-border);
}
</style>
