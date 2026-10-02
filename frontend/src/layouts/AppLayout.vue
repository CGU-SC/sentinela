<script setup>
import { computed, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { useThemeStore } from "@/stores/theme";
import { useFilterStore } from "@/stores/filters";
import { useFarmaciaListsStore } from "@/stores/farmaciaLists";
import AppNavbar from "@/layouts/components/AppNavbar.vue";
import AppSidebar from "@/layouts/components/AppSidebar.vue";
import CnpjDialog from "@/layouts/components/dialogs/CnpjDialog.vue";
import SyncDialog from "@/layouts/components/dialogs/SyncDialog.vue";
import { ANALYSIS_PAGE_PATHS, analysisPageEntry, beginAnalysisPageNavigation, dismissAnalysisPageNavigation, prepareAnalysisPage, revealAnalysisPage } from "@/composables/prepareAnalysisPage";
import { TIMING } from "@/config/constants";

const route = useRoute();
const router = useRouter();
const themeStore = useThemeStore();
const filterStore = useFilterStore();
const farmaciaLists = useFarmaciaListsStore();
const sidebarMotionStyle = {
  '--sidebar-motion-duration': `${TIMING.SIDEBAR_MOTION_MS}ms`,
  '--page-reveal-duration': `${TIMING.SIDEBAR_MOTION_MS / 2}ms`,
};

// Lógica Profissional: Esconde a sidebar se a rota atual pedir via meta: { hideSidebar: true }
const isSidebarHidden = computed(() => !!route.meta?.hideSidebar);
const isAnalysisRoute = computed(() =>
  route.path === "/estabelecimentos" || route.path.startsWith("/analises"),
);
const isPreparingDirectEntry = computed(() =>
  ANALYSIS_PAGE_PATHS.includes(route.path) && analysisPageEntry.preparedPath !== route.path,
);
const entryPath = computed(() => analysisPageEntry.pendingPath || (isPreparingDirectEntry.value ? route.path : null));
const entryHasError = computed(() => analysisPageEntry.errorPath === entryPath.value);

watch(() => route.path, (path) => {
  if (!ANALYSIS_PAGE_PATHS.includes(path) || analysisPageEntry.preparedPath === path) return;
  prepareAnalysisPage(path).catch(() => {
    // A falha aparece no estado de entrada abaixo, com opção de tentar novamente.
  });
}, { immediate: true });

watch([() => route.path, () => analysisPageEntry.preparedPath], ([path, preparedPath]) => {
  if (path === preparedPath && analysisPageEntry.pendingPath === path) {
    revealAnalysisPage(path);
  }
}, { immediate: true });

function retryEntry() {
  const path = analysisPageEntry.errorPath;
  if (!path) return;
  if (route.path === path) {
    beginAnalysisPageNavigation(path);
    prepareAnalysisPage(path).catch(() => {});
  } else {
    router.push(path);
  }
}

function dismissEntry() {
  if (route.path === entryPath.value) {
    router.push('/');
  } else {
    dismissAnalysisPageNavigation();
  }
}
</script>

<template>
  <div 
    class="admin-layout" 
    :style="sidebarMotionStyle"
    :class="{ 
      collapsed: filterStore.sidebarCollapsed,
      'no-sidebar': isSidebarHidden,
      'analysis-route': isAnalysisRoute
    }"
  >
    <AppNavbar />
    <AppSidebar v-if="!isSidebarHidden" active-module="consolidado" />

    <main class="main-container">
      <CnpjDialog />
      <SyncDialog />
      <div v-if="farmaciaLists.error" class="preferences-alert" role="alert">
        <i class="pi pi-exclamation-triangle" aria-hidden="true" />
        <span>{{ farmaciaLists.error }}</span>
        <router-link to="/listas">Ver opções de recuperação</router-link>
      </div>
      <div class="page-content">
        <router-view v-slot="{ Component }">
          <KeepAlive include="MunicipalView">
            <component :is="Component" v-if="!isPreparingDirectEntry" />
          </KeepAlive>
        </router-view>
      </div>
      <Transition name="page-entry">
        <div v-if="entryPath" class="page-entry-panel"
          :role="entryHasError ? 'alert' : 'status'" aria-live="polite"
          :aria-label="entryHasError ? undefined : 'Carregando página'" :aria-busy="!entryHasError">
          <div v-if="entryHasError" class="page-entry-content">
            <i class="pi pi-exclamation-circle page-entry-error-icon" aria-hidden="true" />
            <p>{{ analysisPageEntry.errorMessage }}</p>
            <div class="page-entry-actions">
              <button type="button" @click="retryEntry">Tentar novamente</button>
              <button type="button" @click="dismissEntry">Voltar</button>
            </div>
          </div>
        </div>
      </Transition>
    </main>
  </div>
</template>

<style scoped>
.admin-layout {
  --sidebar-width: 260px;
  /* Largura do conteúdo da barra (não muda ao recolher; ver AppSidebar). */
  --sidebar-width-aberta: 260px;
  /* Faixa visível com a barra recolhida (botão de reabrir). */
  --sidebar-rail-width: 44px;
  display: block !important;
  height: 100vh !important;
  width: 100vw;
  overflow: hidden;
  color: var(--text-color-85);
  scrollbar-gutter: stable;
  background: var(--bg-color) !important;
}

.admin-layout.collapsed {
  --sidebar-width: var(--sidebar-rail-width);
}

.admin-layout.no-sidebar {
  --sidebar-width: 0px;
}

.admin-layout.no-sidebar .main-container {
  margin-left: 0;
}

/* Conteúdo da barra: ao recolher some rápido, antes de a borda passar por ele; ao
   abrir aparece só depois de a barra estar quase aberta, já na largura final. */
:deep(.admin-sidebar > *) {
  opacity: 1;
  pointer-events: auto;
  transition: opacity calc(var(--sidebar-motion-duration) * 0.6) ease-out calc(var(--sidebar-motion-duration) * 0.5);
}

.admin-layout.collapsed :deep(.admin-sidebar > *) {
  opacity: 0;
  pointer-events: none;
  transition: opacity calc(var(--sidebar-motion-duration) * 0.45) ease-in 0ms;
}

.main-container {
  display: flex;
  flex-direction: column;
  height: 100vh;
  overflow-y: auto;
  scrollbar-gutter: stable;
  margin-left: var(--sidebar-width);
  padding-top: 56px;
  transition: margin-left var(--sidebar-motion-duration) cubic-bezier(0.4, 0, 0.2, 1);
  background: transparent !important;
}

@media (prefers-reduced-motion: reduce) {
  .main-container,
  :deep(.admin-sidebar > *),
  .page-entry-enter-active,
  .page-entry-leave-active {
    transition-duration: 0ms;
  }
}

.page-content {
  padding: 1.25rem 0.8rem 1.5rem 1rem;
  flex: 1;
  background: transparent !important;
}

.admin-layout.analysis-route .page-content {
  padding-bottom: 0;
}

.page-entry-panel {
  position: fixed;
  inset: 0;
  z-index: 100;
  display: flex;
  align-items: center;
  justify-content: center;
  padding-left: var(--sidebar-width);
  background: var(--bg-color);
  color: var(--text-color-85);
}

.page-entry-content {
  display: flex;
  align-items: center;
  justify-content: center;
  flex-direction: column;
  gap: 1rem;
  padding: 1.5rem;
  text-align: center;
  font-size: .9rem;
}

.page-entry-content p {
  margin: 0;
}

.page-entry-error-icon {
  color: var(--risk-high);
}

.page-entry-actions {
  display: flex;
  align-items: center;
  gap: .75rem;
}

.page-entry-actions button {
  border: 1px solid var(--sidebar-border);
  border-radius: 8px;
  padding: .55rem .8rem;
  background: var(--card-bg);
  color: var(--primary-color);
  cursor: pointer;
  font: inherit;
}

.page-entry-actions button:focus-visible {
  outline: 2px solid var(--primary-color);
  outline-offset: 2px;
}

.page-entry-enter-active,
.page-entry-leave-active {
  transition: opacity var(--page-reveal-duration) ease;
}

.page-entry-enter-from,
.page-entry-leave-to {
  opacity: 0;
}

/* OVERRIDES GLOBAIS DE COMPONENTES PRIMEVUE */
:deep(.p-dialog) {
  background: var(--card-bg);
  color: var(--text-color-85);
  border: 1px solid var(--sidebar-border);
}

:deep(.p-dialog-header),
:deep(.p-dialog-content),
:deep(.p-dialog-footer) {
  background: var(--card-bg);
  color: var(--text-color-85);
}

:deep(.p-dialog .p-dialog-header .p-dialog-title)      { color: var(--text-color-85); }
:deep(.p-dialog .p-dialog-header .p-dialog-header-icon) { color: var(--text-color-85); }
:deep(.p-dialog-content)                                { color: var(--text-color-85); }

:global(.admin-layout) .p-datatable .p-datatable-header,
:global(.admin-layout) .p-datatable .p-datatable-thead > tr > th,
:global(.admin-layout) .p-datatable .p-datatable-tbody > tr > td,
:global(.admin-layout) .p-datatable .p-datatable-tfoot > tr > td,
:global(.admin-layout) .p-paginator {
  background: var(--card-bg) !important;
  color: var(--text-color-85) !important;
  border-color: var(--sidebar-border) !important;
}

:global(.dark-mode) .p-datatable .p-datatable-tbody > tr > td {
  background: var(--card-bg) !important;
}

:global(.admin-layout) .p-datatable .p-datatable-thead > tr > th {
  color: var(--table-header-text) !important;
  font-size: 0.7rem;
  text-transform: uppercase;
  font-weight: 700;
  border-bottom: 2px solid var(--sidebar-border) !important;
}

:global(.admin-layout) .p-datatable .p-datatable-tbody > tr > td {
  text-transform: none;
}

:global(.dark-mode) .p-datatable .p-datatable-thead > tr > th,
:global(.dark-mode) .p-datatable .p-datatable-tbody > tr,
:global(.dark-mode) .p-datatable .p-datatable-tfoot > tr > td {
  background: var(--card-bg) !important;
  color: var(--text-color-85) !important;
  border-color: var(--sidebar-border) !important;
}

:global(.dark-mode) .p-datatable.p-datatable-striped .p-datatable-tbody > tr.p-row-odd {
  background: var(--table-stripe) !important;
}

:global(.admin-layout) .p-datatable .p-datatable-tbody > tr {
  background: var(--card-bg) !important;
  color: var(--text-color-85) !important;
  font-size: 0.85rem;
}

:global(.admin-layout) .p-datatable.p-datatable-striped .p-datatable-tbody > tr.p-row-odd {
  background: var(--table-stripe) !important;
}

:global(.admin-layout) .p-datatable .p-datatable-tbody > tr:hover {
  background: var(--table-hover);
}

:global(.admin-layout) .p-paginator .p-paginator-pages .p-paginator-page,
:global(.admin-layout) .p-paginator .p-paginator-first,
:global(.admin-layout) .p-paginator .p-paginator-prev,
:global(.admin-layout) .p-paginator .p-paginator-next,
:global(.admin-layout) .p-paginator .p-paginator-last {
  color: var(--text-color-85);
}

:global(.admin-layout) .p-paginator .p-paginator-pages .p-paginator-page.p-highlight {
  background: var(--primary-color);
  color: var(--color-on-primary);
  border-color: var(--primary-color);
}

:global(.dark-mode .p-dropdown),
:global(.dark-mode .p-dropdown-panel),
:global(.dark-mode .p-dropdown-header),
:global(.dark-mode .p-inputtext),
:global(.dark-mode .p-calendar .p-inputtext),
:global(.dark-mode .p-datepicker),
:global(.dark-mode .p-datepicker-header),
:global(.dark-mode .p-monthpicker),
:global(.dark-mode .p-yearpicker) {
  background: var(--card-bg) !important;
  color: var(--text-color-85) !important;
  border-color: var(--sidebar-border) !important;
}

:global(.dark-mode .p-dropdown:not(.p-disabled):hover),
:global(.p-dropdown:not(.p-disabled):hover) {
  border-color: var(--primary-color) !important;
  background: rgba(255, 255, 255, 0.04) !important;
  box-shadow: none !important;
}

:global(.dark-mode .p-dropdown:not(.p-disabled).p-focus),
:global(.p-dropdown:not(.p-disabled).p-focus) {
  border-color: var(--primary-color) !important;
  box-shadow: 0 0 0 2px color-mix(in srgb, var(--primary-color) 25%, transparent) !important;
  outline: none !important;
}

:global(.dark-mode .p-inputtext:enabled:focus),
:global(.p-inputtext:enabled:focus) {
  border-color: var(--primary-color) !important;
  box-shadow: 0 0 0 2px color-mix(in srgb, var(--primary-color) 25%, transparent) !important;
  outline: none !important;
}

:global(.dark-mode) .p-datepicker .p-datepicker-header button,
:global(.dark-mode) .p-monthpicker .p-monthpicker-month,
:global(.dark-mode) .p-yearpicker .p-yearpicker-year {
  color: var(--text-color-85) !important;
}

:global(.dark-mode) .p-monthpicker .p-monthpicker-month:not(.p-highlight):not(.p-disabled):hover,
:global(.dark-mode) .p-yearpicker .p-yearpicker-year:not(.p-highlight):not(.p-disabled):hover {
  background: var(--table-hover) !important;
}

:global(.dark-mode) .p-monthpicker .p-monthpicker-month.p-highlight,
:global(.dark-mode) .p-yearpicker .p-yearpicker-year.p-highlight {
  background: var(--primary-color) !important;
  color: var(--color-on-primary) !important;
  border-color: var(--primary-color) !important;
}

:global(.p-dropdown-item)       { font-size: 0.75rem !important; padding: 0.5rem 0.75rem !important; white-space: normal !important; word-break: break-word !important; }
:global(.dark-mode .p-dropdown-item) { color: var(--text-color-85) !important; }

:global(.dark-mode .p-dropdown-panel .p-dropdown-items .p-dropdown-item:not(.p-highlight):not(.p-disabled):hover),
:global(.dark-mode .p-dropdown-panel .p-dropdown-items .p-dropdown-item.p-focus:not(.p-highlight)) {
  background: var(--table-hover) !important;
  color: var(--text-color-85) !important;
}

:global(.dark-mode .p-dropdown-panel .p-dropdown-items .p-dropdown-item.p-highlight) {
  background: var(--primary-color) !important;
  color: var(--color-on-primary) !important;
}

:global(.dark-mode .p-dropdown-panel .p-dropdown-items .p-dropdown-item.p-highlight:hover),
:global(.dark-mode .p-dropdown-panel .p-dropdown-items .p-dropdown-item.p-highlight.p-focus) {
  background: var(--primary-color) !important;
  color: var(--color-on-primary) !important;
  opacity: 0.9;
}

:global(.admin-layout) .p-listbox {
  background: var(--card-bg);
  border-color: var(--sidebar-border);
}

:global(.p-listbox-item)  { font-size: 0.75rem !important; }
:global(.p-datepicker)    { font-size: 0.8rem !important; }
:global(.p-datepicker table td) { padding: 0.2rem !important; }

:global(.admin-layout) .p-calendar .p-datepicker {
  background: var(--card-bg);
  border-color: var(--sidebar-border);
  color: var(--text-color-85);
}

:global(.admin-layout) .p-calendar .p-datepicker table td > span { color: var(--text-color-85); }
:global(.admin-layout) .p-calendar .p-datepicker table td > span:hover { background: var(--sidebar-bg); }
:global(.admin-layout) .p-calendar .p-datepicker .p-datepicker-header {
  background: var(--card-bg);
  color: var(--text-color-85);
  border-color: var(--sidebar-border);
}

:global(.admin-layout) .p-inputtext,
:global(.admin-layout) .p-dropdown,
:global(.admin-layout) .p-calendar .p-inputtext,
:global(.admin-layout) .p-multiselect {
  background: var(--sidebar-input-bg) !important;
  border-color: var(--sidebar-border) !important;
  color: var(--sidebar-text) !important;
}

.preferences-alert {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 0.7rem 1.4rem;
  background: color-mix(in srgb, var(--risk-high) 10%, var(--card-bg));
  border-bottom: 1px solid var(--risk-high);
  color: var(--text-color-85);
  font-size: 0.85rem;
}

.preferences-alert span { flex: 1; min-width: 0; }
.preferences-alert i { color: var(--risk-high); }
.preferences-alert a { color: var(--text-color-85); text-decoration: underline; text-underline-offset: 3px; }
.preferences-alert a:focus-visible { outline: 2px solid var(--primary-color); outline-offset: 3px; }

:global(.admin-layout) .p-inputtext:enabled:hover,
:global(.admin-layout) .p-dropdown:not(.p-disabled):hover {
  border-color: var(--primary-color) !important;
}
</style>
