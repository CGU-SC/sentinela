<script setup>
import { computed, ref, watch } from 'vue';
import { useAnalyticsStore } from '@/stores/analytics';
import { useChartTheme } from '@/config/chartTheme';
import { useDelayedLoading } from '@/composables/useDelayedLoading';
import { storeToRefs } from 'pinia';
import Button from 'primevue/button';

const props = defineProps({
  hiddenLabels: { type: Array, default: () => [] },
});

const analyticsStore = useAnalyticsStore();
const { enrichedKpis, isLoading, error } = storeToRefs(analyticsStore);
const { chartDataColors } = useChartTheme();

const showRefreshing = useDelayedLoading(isLoading);

// ── Cache de KPIs para Transição Suave ──────────────────
// Mantém os valores anteriores visíveis durante o refresh
const cachedKpis = ref(enrichedKpis.value);

watch([enrichedKpis, isLoading], ([newKpis, loading]) => {
  if (newKpis?.length > 0 && !loading) {
    cachedKpis.value = newKpis;
  }
}, { immediate: true });

const visibleKpis = computed(() =>
  (cachedKpis.value || enrichedKpis.value).filter(
    (kpi) => !props.hiddenLabels.includes(kpi.label)
  )
);
</script>

<template>
  <section class="kpi-section">
    <!-- FEEDBACK DE ERRO -->
    <div v-if="error" class="error-banner">
       <i class="pi pi-exclamation-circle"></i>
       <span>{{ error }}</span>
       <Button label="Tentar Novamente" icon="pi pi-refresh" @click="analyticsStore.fetchDashboardSummary()" text size="small" />
    </div>

    <!-- CARDS DE KPI -->
    <div
      class="kpi-grid"
      :class="{ 'is-refreshing': showRefreshing }"
      :style="{ gridTemplateColumns: visibleKpis.length ? `repeat(${visibleKpis.length}, minmax(0, 1fr))` : undefined }"
    >
      <div 
        v-for="kpi in visibleKpis"
        :key="kpi.label" 
        class="kpi-card"
        :style="{
          background: `linear-gradient(to top, color-mix(in srgb, ${kpi.color} 6%, var(--card-bg)) 0%, var(--card-bg) 60%)`
        }"
      >
        <div class="kpi-body">
          <div class="kpi-icon-bg" :style="{ backgroundColor: kpi.color + '20', color: kpi.color }">
             <i :class="kpi.icon"></i>
          </div>
          <div class="kpi-content">
            <span class="kpi-label">{{ kpi.label }}</span>
            <span class="kpi-value">{{ kpi.value }}</span>
          </div>
        </div>
      </div>
    </div>
  </section>
</template>

<style scoped>
.kpi-section {
  width: 100%;
  overflow: visible;
}


.kpi-grid {
  display: grid;
  grid-template-columns: repeat(6, minmax(0, 1fr)); /* TRAVA DE LARGURA: Garante colunas de exatos 20% sempre */
  gap: 0.75rem;
  width: 100%;
  transition: opacity 0.25s ease;
}

.kpi-card {
  background: var(--card-bg);
  border-radius: 12px;
  padding: 0.8rem 1rem;
  border: 1px solid color-mix(in srgb, var(--primary-color) 15%, var(--sidebar-border));
  min-height: 0;
  display: flex;
  align-items: center;
}

.kpi-body {
  display: flex;
  justify-content: flex-start;
  align-items: center;
  gap: 0.9rem; /* MEDIDA DO USUÁRIO */
  width: 100%;
}

.kpi-content {
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.kpi-label {
  font-size: 0.70rem; /* MEDIDA DO USUÁRIO */
  color: var(--text-color-85);
  opacity: 0.7; /* Hierarquia via transparência */
  font-weight: 700;
  text-transform: uppercase;
  white-space: nowrap;
  line-height: 1;
  margin-bottom: 0.3rem;
}

.kpi-value {
  font-size: 1.3rem; /* MEDIDA DO USUÁRIO */
  white-space: nowrap;
  letter-spacing: -0.6px;
  font-weight: 700; /* Bold padrão consolidado */
  color: var(--text-color-85);
  opacity: 0.90;
  line-height: 1;
}

.kpi-icon-bg {
  width: 2rem;
  height: 2rem;
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 0.75rem;
  font-size: 1rem;
}

.is-refreshing {
  opacity: 0.45;
  pointer-events: none;
}

.error-banner {
  display: flex;
  align-items: center;
  gap: 1rem;
  padding: 1rem;
  background: color-mix(in srgb, v-bind('chartDataColors.red') 10%, transparent);
  border: 1px solid color-mix(in srgb, v-bind('chartDataColors.red') 20%, transparent);
  border-radius: 8px;
  color: v-bind('chartDataColors.red');
  margin-bottom: 2rem;
}
</style>
