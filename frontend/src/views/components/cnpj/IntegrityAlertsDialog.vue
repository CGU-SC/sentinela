<script setup>
import { computed } from "vue";
import Dialog from "primevue/dialog";
import { integrityAlertTooltip } from "@/config/integrityAlertTooltipConfig";

const props = defineProps({
  visible: { type: Boolean, default: false },
  data: { type: Object, default: null },
});

const emit = defineEmits(["update:visible", "navigate"]);

const dialogVisible = computed({
  get: () => props.visible,
  set: (value) => emit("update:visible", value),
});

const alerts = computed(() => props.data?.alertas ?? []);

const formatDocument = (value) => {
  const clean = String(value ?? "").replace(/\D/g, "");
  if (clean.length === 11) {
    return clean.replace(/^(\d{3})(\d{3})(\d{3})(\d{2})$/, "$1.$2.$3-$4");
  }
  if (clean.length === 14) {
    return clean.replace(
      /^(\d{2})(\d{3})(\d{3})(\d{4})(\d{2})$/,
      "$1.$2.$3/$4-$5",
    );
  }
  return value;
};

const navigate = (alert) => {
  dialogVisible.value = false;
  emit("navigate", alert.aba_destino);
};
</script>

<template>
  <Dialog
    v-model:visible="dialogVisible"
    modal
    header="Alertas"
    :style="{ width: '720px' }"
    class="integrity-alerts-dialog"
  >
    <div class="integrity-list">
      <article
        v-for="alert in alerts"
        :key="`${alert.tipo}-${alert.entidade_id}`"
        class="integrity-alert-row"
        :class="`integrity-alert-row--${alert.severidade}`"
      >
        <div class="integrity-alert-icon">
          <i
            :class="alert.severidade === 'critico'
              ? 'pi pi-exclamation-triangle'
              : 'pi pi-info-circle'"
          />
        </div>

        <div class="integrity-alert-content">
          <div class="integrity-alert-heading">
            <span class="integrity-alert-title">{{ alert.titulo }}</span>
            <i
              class="pi pi-info-circle integrity-alert-info"
              role="img"
              tabindex="0"
              :aria-label="`Explicação do alerta ${alert.titulo}`"
              v-tooltip.right="integrityAlertTooltip(alert)"
            />
            <span class="integrity-alert-sep">·</span>
            <span class="integrity-alert-entity">{{ alert.entidade_nome }}</span>
          </div>
          <span class="integrity-alert-meta">
            {{ formatDocument(alert.entidade_id) }} · Fonte: {{ alert.fonte }}
          </span>
        </div>

        <button
          class="integrity-alert-action"
          type="button"
          @click="navigate(alert)"
        >
          <span>Ver {{ alert.aba_destino }}</span>
          <i class="pi pi-arrow-right" />
        </button>
      </article>
    </div>
  </Dialog>
</template>

<style scoped>
.integrity-list {
  display: flex;
  flex-direction: column;
}

.integrity-alert-row {
  display: grid;
  grid-template-columns: 30px minmax(0, 1fr) auto;
  align-items: center;
  gap: 0.75rem;
  padding: 0.9rem 0;
  border-bottom: 1px solid var(--card-border);
}

.integrity-alert-row:last-child {
  border-bottom: 0;
}

.integrity-alert-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  border-radius: 6px;
}

.integrity-alert-row--critico .integrity-alert-icon {
  color: var(--risk-critical);
  background: color-mix(in srgb, var(--risk-critical) 12%, transparent);
}

.integrity-alert-row--atencao .integrity-alert-icon {
  color: var(--risk-medium);
  background: color-mix(in srgb, var(--risk-medium) 12%, transparent);
}

.integrity-alert-content {
  display: flex;
  min-width: 0;
  flex-direction: column;
  gap: 0.2rem;
}

.integrity-alert-heading {
  display: flex;
  align-items: center;
  gap: 0.35rem;
}

.integrity-alert-title {
  font-size: 0.82rem;
  font-weight: 600;
  color: var(--text-color-85);
}

.integrity-alert-info {
  flex-shrink: 0;
  color: var(--primary-color);
  cursor: help;
  font-size: 0.72rem;
}

.integrity-alert-info:focus-visible {
  outline: 2px solid var(--primary-color);
  outline-offset: 2px;
  border-radius: 3px;
}

.integrity-alert-sep {
  font-size: 0.82rem;
  color: var(--text-muted);
  opacity: 0.4;
}

.integrity-alert-entity {
  font-size: 0.82rem;
  font-weight: 500;
  color: var(--text-muted);
}

.integrity-alert-meta {
  font-size: 0.72rem;
  color: var(--text-muted);
}

.integrity-alert-action {
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
  border: 0;
  background: transparent;
  color: var(--primary-color);
  font-size: 0.75rem;
  font-weight: 600;
  cursor: pointer;
}

.integrity-alert-action:hover {
  text-decoration: underline;
}
</style>
