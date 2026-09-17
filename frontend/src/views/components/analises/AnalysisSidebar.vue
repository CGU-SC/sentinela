<template>
  <aside class="analysis-selector">
    <div class="selector-header">
      <i class="pi pi-chart-bar selector-header-icon" />
      <span class="selector-header-label">Análises</span>
    </div>

    <div class="selector-groups">
      <div class="selector-group">
        <div class="group-title">Análises disponíveis</div>

        <router-link
          to="/analises"
          class="analysis-btn analysis-btn--active"
          aria-current="page"
        >
          <span class="analysis-btn-label">Análise de CRMs</span>
        </router-link>
      </div>
    </div>
  </aside>
</template>

<style scoped>
.analysis-selector {
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
}

.analysis-btn {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  padding: 0.5rem 1rem;
  min-height: 2.4rem;
  background: transparent;
  border: none;
  text-decoration: none;
  cursor: pointer;
  text-align: left;
  color: var(--text-color-85);
  opacity: 1;
  min-width: 0;
}

.analysis-btn--active {
  background: color-mix(in srgb, var(--primary-color) 12%, var(--card-bg));
  box-shadow: inset 1px 0 0 var(--primary-color);
}

.analysis-btn-label {
  font-size: 0.78rem;
  font-weight: 600;
  line-height: 1.2;
  color: var(--primary-color);
  flex: 1;
  min-width: 0;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
</style>
