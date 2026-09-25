<script setup>
import { onMounted, computed } from "vue";
import { useRoute } from "vue-router";
import { useThemeStore } from "@/stores/theme";
import { useFilterStore } from "@/stores/filters";
import { useFarmaciaListsStore } from "@/stores/farmaciaLists";
import AppNavbar from "@/layouts/components/AppNavbar.vue";
import AppSidebar from "@/layouts/components/AppSidebar.vue";
import CnpjDialog from "@/layouts/components/dialogs/CnpjDialog.vue";
import SyncDialog from "@/layouts/components/dialogs/SyncDialog.vue";

const route = useRoute();
const themeStore = useThemeStore();
const filterStore = useFilterStore();
const farmaciaLists = useFarmaciaListsStore();

// Lógica Profissional: Esconde a sidebar se a rota atual pedir via meta: { hideSidebar: true }
const isSidebarHidden = computed(() => !!route.meta?.hideSidebar);
const isAnalysisRoute = computed(() =>
  route.path === "/estabelecimentos" || route.path.startsWith("/analises"),
);

onMounted(() => {});
</script>

<template>
  <div 
    class="admin-layout" 
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
          <Transition name="page-fade" mode="out-in">
            <component :is="Component" />
          </Transition>
        </router-view>
      </div>
    </main>
  </div>
</template>

<style scoped>
.admin-layout {
  --sidebar-width: 280px;
  display: block !important;
  height: 100vh !important;
  width: 100vw;
  overflow: hidden;
  color: var(--text-color-85);
  scrollbar-gutter: stable;
  background: var(--bg-color) !important;
}

.admin-layout.collapsed {
  --sidebar-width: 0px;
}

.admin-layout.no-sidebar {
  --sidebar-width: 0px;
}

.admin-layout.no-sidebar .main-container {
  margin-left: 0;
}

/* Oculta conteúdo da sidebar ao colapsar — usa :deep() para cruzar o componente */
:deep(.sidebar-content),
:deep(.sidebar-footer) {
  opacity: 1;
  pointer-events: auto;
  transition: opacity 0.2s 0.25s ease;
}

.admin-layout.collapsed :deep(.sidebar-content),
.admin-layout.collapsed :deep(.sidebar-footer) {
  opacity: 0;
  pointer-events: none;
  transition: opacity 0.15s ease;
}

/* Remove borda direita quando colapsada */
.admin-layout.collapsed :deep(.admin-sidebar) {
  border-right: none;
}

.main-container {
  display: flex;
  flex-direction: column;
  height: 100vh;
  overflow-y: auto;
  scrollbar-gutter: stable;
  margin-left: var(--sidebar-width);
  padding-top: 56px;
  transition: margin-left 0.35s cubic-bezier(0.4, 0, 0.2, 1);
  background: transparent !important;
}

.page-content {
  padding: 1.25rem 0.8rem 1.5rem 1.4rem;
  flex: 1;
  background: transparent !important;
}

.admin-layout.analysis-route .page-content {
  padding-bottom: 0;
}

/* PAGE TRANSITIONS */
.page-fade-enter-active,
.page-fade-leave-active {
  transition: opacity 0.15s ease, transform 0.15s ease;
}
.page-fade-enter-from { opacity: 0; transform: translateY(8px); }
.page-fade-leave-to   { opacity: 0; transform: translateY(-8px); }

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
