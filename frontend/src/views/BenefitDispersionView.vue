<script setup>
import { useFetchAnalytics } from '@/composables/useFetchAnalytics';
import KpiSection from './components/KpiSection.vue';
import UFChart from './components/charts/UFChart.vue';

useFetchAnalytics({ secoes: ['kpis', 'ufs'] });
</script>

<template>
  <div class="dashboard-container">
    <KpiSection />
    <div class="scatter-wrapper">
      <UFChart grow />
    </div>
  </div>
</template>

<style scoped>
.dashboard-container {
  display: flex;
  flex-direction: column;
  gap: 1.5rem;
  height: 100%;
  overflow: visible;
}

.scatter-wrapper {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
}
</style>
