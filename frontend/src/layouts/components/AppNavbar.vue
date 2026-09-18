<script setup>
import { ref, computed, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { useRecentCnpjStore } from '@/stores/recentCnpj';
import { useFarmaciaListsStore } from '@/stores/farmaciaLists';
import { useSyncManager } from '@/composables/useSyncManager';
import { useThemeStore } from '@/stores/theme';
import Button from 'primevue/button';
import AutoComplete from 'primevue/autocomplete';
import { useGeoStore } from '@/stores/geo';

const route = useRoute();
const router = useRouter();
const recentCnpjStore = useRecentCnpjStore();
const recentCnpj = computed(() => recentCnpjStore.recent);
const farmaciaLists = useFarmaciaListsStore();
const totalListas = computed(() => farmaciaLists.interesse.length);
const { showConfirmSync } = useSyncManager();
const geoStore = useGeoStore();
const themeStore = useThemeStore();

const tabs = [
  { label: 'Home', path: '/' },
  { label: 'Municípios', path: '/municipios' },
  { label: 'Estabelecimentos', path: '/estabelecimentos' },
  { label: 'Análises', path: '/analises', disabled: true },
  // { label: 'Alvos', path: '/alvos' },
];

// Busca rápida por CNPJ ou Razão Social
const navCnpjInput = ref('');
const navSuggestions = ref([]);

watch(navCnpjInput, (val) => {
  const str = typeof val === 'string' ? val : (val?.cnpj ?? '');
  const digits = str.replace(/\D/g, '');
  if (digits.length === 14) {
    navCnpjInput.value = '';
    router.push(`/estabelecimentos/${digits}`);
  }
});

function searchNav(event) {
  const q = (event.query || '').trim().toLowerCase();
  if (q.length < 2) { navSuggestions.value = []; return; }
  const numericQ = q.replace(/\D/g, '');
  const tokens = q.split(/\s+/).filter(Boolean);
  navSuggestions.value = geoStore.cnpjLookup
    .filter(e => {
      if (numericQ.length >= 4 && e.cnpj?.includes(numericQ)) return true;
      const nome = e.razao_social?.toLowerCase() ?? '';
      return tokens.every(t => nome.includes(t));
    })
    .slice(0, 40)
    .map(e => ({ label: e.razao_social, cnpj: e.cnpj, municipio: e.municipio, uf: e.uf }));
}

function onNavSelect(event) {
  navCnpjInput.value = '';
  router.push(`/estabelecimentos/${event.value.cnpj}`);
}
</script>

<template>
  <nav class="top-navbar">
    <div class="nav-left">
      <div class="nav-brand">
        <img src="/img/logo_sentinela_transparente.png" alt="Sentinela" class="nav-logo-img" />
        <div class="nav-brand-text">
          <span class="nav-brand-name">SENTINELA</span>
          <span class="nav-brand-sub">Auditoria no Farmácia Popular</span>
        </div>
      </div>

      <div class="nav-divider"></div>

      <div class="nav-tabs">
        <template v-for="tab in tabs" :key="tab.path">
          <span
            v-if="tab.disabled"
            class="nav-tab nav-tab--disabled"
            aria-disabled="true"
            v-tooltip.bottom="'Em breve...'"
          >
            {{ tab.label }}
          </span>
          <router-link
            v-else
            :to="tab.path"
            class="nav-tab"
            :class="{ active: route.path === tab.path }"
          >
            {{ tab.label }}
          </router-link>
        </template>

        <!-- Atalho: último CNPJ analisado -->
        <div v-if="recentCnpj" class="nav-recent-wrapper">
          <router-link
            :to="`/estabelecimentos/${recentCnpj.cnpj}`"
            class="nav-tab nav-recent-cnpj"
            :class="{ active: route.path.startsWith('/estabelecimentos/') }"
            v-tooltip.bottom="recentCnpj.razaoSocial"
          >
            <i class="pi pi-history" />
            {{ recentCnpj.cnpj.replace(/^(\d{2})(\d{3})(\d{3})(\d{4})(\d{2})$/, '$1.$2.$3/$4-$5') }}
          </router-link>
          <button class="nav-recent-clear" @click.prevent="recentCnpjStore.clear()" v-tooltip.bottom="'Limpar atalho'">
            <i class="pi pi-times" />
          </button>
        </div>
      </div>
    </div>

    <div class="nav-actions">
      <div class="nav-cnpj-search">
        <i class="pi pi-search nav-cnpj-icon" />
        <AutoComplete
          v-model="navCnpjInput"
          :suggestions="navSuggestions"
          optionLabel="label"
          @complete="searchNav"
          @option-select="onNavSelect"
          placeholder="CNPJ ou razão social..."
          :delay="200"
          :forceSelection="false"
          panelClass="nav-ac-panel"
          class="nav-ac"
        >
          <template #option="{ option }">
            <div class="nav-ac-option">
              <span class="nav-ac-razao">{{ option.label }}</span>
              <div class="nav-ac-meta">
                <span class="nav-ac-cnpj">{{ option.cnpj }}</span>
                <span v-if="option.municipio" class="nav-ac-loc">{{ option.municipio }}/{{ option.uf }}</span>
              </div>
            </div>
          </template>
        </AutoComplete>
      </div>
      <a
        href="https://cgu-sc.github.io/sentinela/"
        target="_blank"
        rel="noopener noreferrer"
        class="docs-nav-btn"
        v-tooltip.bottom="'Documentação do sistema'"
      >
        <i class="pi pi-book" />
      </a>
      <Button
        :icon="themeStore.isDark ? 'pi pi-sun' : 'pi pi-moon'"
        text
        rounded
        severity="secondary"
        v-tooltip.bottom="themeStore.isDark ? 'Modo claro' : 'Modo escuro'"
        @click="themeStore.toggleTheme()"
      />
      <Button
        icon="pi pi-cog"
        text
        rounded
        severity="secondary"
        v-tooltip.bottom="'Configurações do Sistema'"
        @click="router.push('/configuracoes')"
        :class="{ 'active-nav-btn': $route.path === '/configuracoes' }"
      />
      <div
        class="lists-nav-btn"
        @click="router.push('/listas')"
        v-tooltip.bottom="'Farmácias Monitoradas'"
      >
        <i class="pi pi-bookmark" />
        <span v-if="totalListas > 0" class="lists-nav-badge">{{ totalListas }}</span>
      </div>
      <Button
        icon="pi pi-refresh"
        text
        rounded
        severity="secondary"
        disabled
        v-tooltip.bottom="'Sincronização com CGUData temporariamente indisponível'"
      />
    </div>
  </nav>
</template>

<style scoped>
.top-navbar {
  height: 56px;
  min-height: 56px;
  max-height: 56px;
  flex-shrink: 0;
  background: color-mix(in srgb, var(--navbar-bg) 75%, transparent);
  backdrop-filter: blur(20px) saturate(160%);
  -webkit-backdrop-filter: blur(20px) saturate(160%);
  border-bottom: 1px solid color-mix(in srgb, var(--navbar-border) 60%, transparent);
  box-shadow: 0 1px 0 color-mix(in srgb, var(--primary-color) 6%, transparent),
              inset 0 -1px 0 color-mix(in srgb, var(--navbar-border) 40%, transparent);
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0 1.5rem;
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  z-index: 300;
  transition: background 0.3s ease, border-color 0.3s ease;
}

.nav-actions {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  flex-shrink: 0;
}

.nav-actions :deep(.p-button:focus),
.nav-actions :deep(.p-button:active) {
  box-shadow: none !important;
  outline: none !important;
}

.nav-actions :deep(.p-button:focus-visible) {
  box-shadow: 0 0 0 2px color-mix(in srgb, var(--text-color-85) 16%, transparent) !important;
  outline: none !important;
}

.nav-left {
  display: flex;
  align-items: center;
  gap: 1rem;
}

.nav-brand {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  flex-shrink: 0;
}

.nav-logo-img {
  width: 38px;
  height: 38px;
  object-fit: contain;
}

.nav-brand-text {
  display: flex;
  flex-direction: column;
  gap: 0.1rem;
}

.nav-brand-name {
  font-size: 0.78rem;
  font-weight: 600;
  letter-spacing: 0.08em;
  color: var(--text-color-85);
  white-space: nowrap;
  line-height: 1.1;
}

.nav-brand-sub {
  font-size: 0.58rem;
  font-weight: 400;
  letter-spacing: 0.03em;
  color: var(--text-muted);
  white-space: nowrap;
  opacity: 0.75;
  line-height: 1.1;
}

.nav-divider {
  width: 1px;
  height: 20px;
  background: color-mix(in srgb, var(--text-muted) 30%, transparent);
  flex-shrink: 0;
}

.nav-tabs {
  display: flex;
  align-items: stretch;
  gap: 0;
}

.nav-tab {
  position: relative;
  padding: 0 0.85rem;
  height: 56px;
  display: flex;
  align-items: center;
  text-decoration: none;
  color: var(--text-muted);
  font-size: 0.72rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  border: none;
  background: transparent;
  transition: color 0.2s ease;
  white-space: nowrap;
}

.nav-tab::after {
  content: '';
  position: absolute;
  bottom: 0;
  left: 0.5rem;
  right: 0.5rem;
  height: 2px;
  border-radius: 2px 2px 0 0;
  background: var(--primary-color);
  transform: scaleX(0);
  transition: transform 0.2s ease;
}

.nav-tab:hover {
  color: var(--text-color-85);
}

.nav-tab--disabled {
  cursor: not-allowed;
  color: var(--text-muted);
  opacity: 0.48;
}

.nav-tab--disabled:hover {
  color: var(--text-muted);
}

.nav-tab--disabled::after {
  display: none;
}

.nav-tab:hover::after {
  transform: scaleX(0.5);
  opacity: 0.4;
}

.nav-tab.active {
  color: var(--primary-color);
}

.nav-tab.active::after {
  transform: scaleX(1);
}

.nav-recent-wrapper {
  position: relative;
  display: flex;
  align-items: center;
}

.nav-recent-cnpj {
  gap: 0.4rem;
  padding-right: 1.4rem;
}

.nav-recent-cnpj::before {
  content: '';
  position: absolute;
  left: 0;
  width: 1px;
  height: 16px;
  background: color-mix(in srgb, var(--text-muted) 25%, transparent);
}

.nav-recent-cnpj .pi-history {
  font-size: 0.65rem;
  opacity: 0.6;
}

.nav-recent-clear {
  position: absolute;
  right: 0.3rem;
  top: 50%;
  transform: translateY(-50%);
  background: none;
  border: none;
  cursor: pointer;
  padding: 0.2rem;
  color: var(--text-muted);
  opacity: 0.4;
  display: flex;
  align-items: center;
  transition: opacity 0.15s;
}

.nav-recent-clear:hover {
  opacity: 1;
}

.nav-recent-clear .pi {
  font-size: 0.55rem;
}

.nav-cnpj-search {
  position: relative;
  display: flex;
  align-items: center;
}

.nav-cnpj-icon {
  position: absolute;
  left: 0.6rem;
  font-size: 0.7rem;
  color: var(--text-muted);
  pointer-events: none;
  z-index: 1;
}

:deep(.nav-ac) {
  width: 200px;
}

:deep(.nav-ac .p-autocomplete-input) {
  padding: 0.3rem 0.7rem 0.3rem 1.8rem !important;
  height: 30px !important;
  font-size: 0.72rem !important;
  font-family: 'Inter', sans-serif !important;
  font-weight: 500 !important;
  width: 200px !important;
  background: color-mix(in srgb, var(--card-bg) 80%, transparent) !important;
  border: 1px solid var(--card-border) !important;
  border-radius: 6px !important;
  color: var(--text-color-85) !important;
  letter-spacing: 0.03em;
  transition: border-color 0.2s, box-shadow 0.2s;
  box-sizing: border-box;
}

:deep(.nav-ac .p-autocomplete-input:focus) {
  border-color: color-mix(in srgb, var(--primary-color) 60%, transparent) !important;
  box-shadow: 0 0 0 3px color-mix(in srgb, var(--primary-color) 12%, transparent) !important;
  outline: none !important;
}

:deep(.nav-ac .p-autocomplete-input::placeholder) {
  color: var(--text-muted) !important;
  opacity: 0.6;
}

:global(.nav-ac-panel) {
  background: var(--card-bg) !important;
  border: 1px solid var(--card-border) !important;
  box-shadow: 0 10px 25px rgba(0, 0, 0, 0.15) !important;
  border-radius: 8px !important;
  max-height: 320px !important;
}

:global(.nav-ac-panel .p-autocomplete-item) {
  padding: 0 !important;
  background: transparent !important;
  color: var(--text-color-85) !important;
}

:global(.nav-ac-panel .p-autocomplete-item:hover),
:global(.nav-ac-panel .p-autocomplete-item.p-highlight) {
  background: color-mix(in srgb, var(--primary-color) 10%, transparent) !important;
}

.nav-ac-option {
  display: flex;
  flex-direction: column;
  padding: 0.45rem 0.75rem;
  gap: 0.15rem;
}

.nav-ac-razao {
  font-size: 0.75rem;
  color: var(--text-color-85);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 280px;
}

.nav-ac-meta {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.nav-ac-cnpj {
  font-size: 0.65rem;
  color: var(--text-muted);
}

.nav-ac-loc {
  font-size: 0.65rem;
  color: var(--primary-color);
  opacity: 0.75;
}

.docs-nav-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  border-radius: 6px;
  cursor: pointer;
  color: var(--text-secondary);
  text-decoration: none;
  transition: all 0.15s ease;
}

.docs-nav-btn:hover {
  background: color-mix(in srgb, var(--text-color-85) 8%, transparent);
  color: var(--text-color-85);
}

.docs-nav-btn:focus-visible {
  outline: none;
  box-shadow: 0 0 0 2px color-mix(in srgb, var(--text-color-85) 16%, transparent);
}

.docs-nav-btn i {
  font-size: 1rem;
}

.lists-nav-btn {
  position: relative;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  border-radius: 6px;
  cursor: pointer;
  color: var(--text-secondary);
  transition: all 0.15s ease;
}

.lists-nav-btn:focus,
.lists-nav-btn:active {
  outline: none;
  box-shadow: none;
}

.lists-nav-btn:focus-visible {
  outline: none;
  box-shadow: 0 0 0 2px color-mix(in srgb, var(--text-color-85) 16%, transparent);
}

.lists-nav-btn:hover {
  background: color-mix(in srgb, var(--text-color-85) 8%, transparent);
  color: var(--text-color-85);
}

.lists-nav-btn i {
  font-size: 1rem;
}

.lists-nav-badge {
  position: absolute;
  top: 2px;
  right: 2px;
  min-width: 16px;
  height: 16px;
  padding: 0 4px;
  font-size: 0.68rem;
  font-weight: 700;
  border-radius: 10px;
  background: var(--primary-color);
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  line-height: 1;
}
</style>
