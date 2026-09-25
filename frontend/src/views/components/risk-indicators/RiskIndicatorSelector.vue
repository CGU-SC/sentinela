<script setup>
import { storeToRefs } from 'pinia';
import { useRiskIndicatorsStore } from '@/stores/riskIndicators';
import { INDICATOR_GROUPS } from '@/config/riskConfig';
import { indicatorTooltip } from '@/utils/indicatorTooltip';

const emit = defineEmits(['select']);

const riskIndicatorsStore = useRiskIndicatorsStore();
const { selectedRiskIndicator, isLoading } = storeToRefs(riskIndicatorsStore);



function selectRiskIndicator(key) {
  emit('select', key);
}

function showTooltipOnFocus(event) {
  event.currentTarget.dispatchEvent(new Event('mouseenter'));
}

function hideTooltipOnBlur(event) {
  event.currentTarget.dispatchEvent(new Event('mouseleave'));
}
</script>

<template>
  <aside class="indicator-selector">
    <div class="selector-header">
      <i class="pi pi-shield selector-header-icon" />
      <span class="selector-header-label">Indicadores</span>
    </div>

    <div class="selector-groups">
      <div
        v-for="grupo in INDICATOR_GROUPS"
        :key="grupo.id"
        class="selector-group"
      >
        <div class="group-title">{{ grupo.label }}</div>

        <div
          v-for="ind in grupo.indicators"
          :key="ind.key"
          class="ind-row"
          :class="{ 'ind-row--active': selectedRiskIndicator === ind.key }"
        >
          <button
            type="button"
            class="ind-btn"
            :aria-current="selectedRiskIndicator === ind.key ? 'true' : null"
            @click="selectRiskIndicator(ind.key)"
          >
            <span class="ind-btn-label">{{ ind.label }}</span>
            <i
              v-if="isLoading && selectedRiskIndicator === ind.key"
              class="pi pi-spin pi-spinner ind-loading-icon"
              aria-hidden="true"
            />
          </button>
          <button
            type="button"
            class="ind-info-btn"
            :aria-label="`Explicação do indicador ${ind.label}`"
            v-tooltip.left="indicatorTooltip(ind)"
            @focus="showTooltipOnFocus"
            @blur="hideTooltipOnBlur"
          >
            <i class="pi pi-info-circle" aria-hidden="true" />
          </button>
        </div>
      </div>
    </div>

  </aside>
</template>

<style scoped>
.indicator-selector {
  width: var(--indicator-selector-width, 260px);
  flex-shrink: 0;
  position: sticky;
  top: 0;
  min-height: calc(100dvh - 56px - 1.25rem);
  display: flex;
  flex-direction: column;
  gap: 0;
  background: var(--card-bg);
  border: 1px solid var(--card-border);
  border-radius: 8px;
  overflow: visible;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
  align-self: start;
}

.selector-header {
  display: flex;
  align-items: center;
  gap: 0.6rem;
  padding: 0.9rem 1rem;
  border-bottom: 1px solid var(--card-border);
  background: color-mix(in srgb, var(--primary-color) 6%, var(--card-bg));
}

.selector-header-icon {
  font-size: 0.9rem;
  color: var(--primary-color);
}

.selector-header-label {
  font-size: 0.75rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--text-color-85);
  opacity: 0.85;
}

.selector-groups {
  display: flex;
  flex-direction: column;
  padding: 0.5rem 0;
}

.selector-group {
  display: flex;
  flex-direction: column;
}

.group-title {
  padding: 0.6rem 1rem 0.25rem;
  font-size: 0.65rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.07em;
  color: var(--primary-color);
  opacity: 0.75;
  border-top: 1px solid var(--card-border);
  margin-top: 0.25rem;
}

.selector-group:first-child .group-title {
  border-top: none;
  margin-top: 0;
}

.ind-row {
  display: flex;
  align-items: center;
  min-height: 2.4rem;
  padding-right: 0.55rem;
  color: var(--text-color-85);
  opacity: 0.8;
  transition: background 0.15s ease, opacity 0.15s ease;
}

.ind-row:hover,
.ind-row:focus-within {
  background: var(--table-hover);
  opacity: 1;
}

.ind-row--active {
  background: color-mix(in srgb, var(--primary-color) 12%, var(--card-bg));
  opacity: 1;
  border-left: 3px solid var(--primary-color);
}

.ind-row--active .ind-btn-label {
  color: var(--primary-color);
  font-weight: 600;
}

.ind-btn {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  flex: 1;
  min-width: 0;
  min-height: 2.4rem;
  padding: 0.5rem 0.4rem 0.5rem 1rem;
  background: transparent;
  border: none;
  color: inherit;
  cursor: pointer;
  text-align: left;
}

.ind-row--active .ind-btn {
  padding-left: calc(1rem - 3px);
}

.ind-btn-label {
  font-size: 0.78rem;
  font-weight: 500;
  line-height: 1.3;
  flex: 1;
  min-width: 0;
  white-space: normal;
  overflow-wrap: break-word;
}

.ind-info-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex: 0 0 28px;
  width: 28px;
  height: 28px;
  padding: 0;
  border: none;
  border-radius: 6px;
  background: transparent;
  color: var(--text-muted);
  cursor: help;
  font-size: 0.8rem;
}

.ind-info-btn:hover,
.ind-info-btn:focus-visible {
  color: var(--primary-color);
  background: color-mix(in srgb, var(--primary-color) 10%, transparent);
}

.ind-btn:focus-visible,
.ind-info-btn:focus-visible {
  outline: 2px solid var(--primary-color);
  outline-offset: -2px;
}



.ind-loading-icon {
  flex-shrink: 0;
  font-size: 0.7rem;
  color: var(--primary-color);
  opacity: 0.7;
}

</style>
