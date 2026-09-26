<script setup>
import { ref, computed, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { useRecentCnpjStore } from '@/stores/recentCnpj';
import { useFarmaciaListsStore } from '@/stores/farmaciaLists';
import { useSyncManager } from '@/composables/useSyncManager';
import { useThemeStore } from '@/stores/theme';
import Button from 'primevue/button';
import AutoComplete from 'primevue/autocomplete';
import Dialog from 'primevue/dialog';
import { useGeoStore } from '@/stores/geo';
import { useSystemUpdateStore } from '@/stores/systemUpdate';
import { APP_RUNTIME, getAppRuntimeLabel } from '@/config/appInfo';
import { navbarTooltip } from '@/config/navbarTooltipConfig';

const route = useRoute();
const router = useRouter();
const recentCnpjStore = useRecentCnpjStore();
const recentCnpj = computed(() => recentCnpjStore.recent);
const farmaciaLists = useFarmaciaListsStore();
const totalListas = computed(() => farmaciaLists.interesse.length);
const { showConfirmSync } = useSyncManager();
const geoStore = useGeoStore();
const themeStore = useThemeStore();
const updateStore = useSystemUpdateStore();
const updateDetailsVisible = ref(false);
const isDesktop = () => getAppRuntimeLabel() === APP_RUNTIME.DESKTOP;

function confirmUpdate() {
  if (!updateStore.hasUpdate || updateStore.isDownloading || !updateStore.downloadUrl) return;

  if (isDesktop()) {
    updateDetailsVisible.value = false;
    updateStore.startDownload();
    return;
  }

  window.open(updateStore.downloadUrl, '_blank', 'noopener,noreferrer');
  updateDetailsVisible.value = false;
}

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
            v-tooltip.bottom="navbarTooltip('comingSoon')"
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
            :aria-label="`Abrir último estabelecimento: ${recentCnpj.razaoSocial || recentCnpj.cnpj}`"
          >
            <i class="pi pi-history" />
            {{ recentCnpj.cnpj.replace(/^(\d{2})(\d{3})(\d{3})(\d{4})(\d{2})$/, '$1.$2.$3/$4-$5') }}
          </router-link>
          <i
            class="pi pi-info-circle nav-recent-info"
            role="img"
            tabindex="0"
            aria-label="Informações sobre o último estabelecimento"
            v-tooltip.bottom="navbarTooltip('recentCnpj', recentCnpj.razaoSocial)"
          />
          <button class="nav-recent-clear" aria-label="Limpar atalho" @click.prevent="recentCnpjStore.clear()" v-tooltip.bottom="navbarTooltip('clearRecentCnpj')">
            <i class="pi pi-times" />
          </button>
        </div>
      </div>
    </div>

    <div class="nav-actions">
      <button
        v-if="updateStore.hasUpdate"
        type="button"
        class="nav-update-badge"
        :aria-label="`Atualização disponível: versão ${updateStore.latestVersion}. Ver detalhes`"
        @click="updateDetailsVisible = true"
      >
        <i class="pi pi-download" aria-hidden="true" />
        <span class="nav-update-badge__label">Atualização disponível</span>
        <span class="nav-update-badge__version">· v{{ updateStore.latestVersion }}</span>
      </button>
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
        class="nav-icon-btn"
        aria-label="Documentação do sistema"
        v-tooltip.bottom="navbarTooltip('documentation')"
      >
        <i class="pi pi-book" />
      </a>
      <Button
        :icon="themeStore.isDark ? 'pi pi-sun' : 'pi pi-moon'"
        text
        severity="secondary"
        class="nav-icon-btn"
        :aria-label="themeStore.isDark ? 'Modo claro' : 'Modo escuro'"
        v-tooltip.bottom="navbarTooltip(themeStore.isDark ? 'lightTheme' : 'darkTheme')"
        @click="themeStore.toggleTheme()"
      />
      <Button
        icon="pi pi-cog"
        text
        severity="secondary"
        aria-label="Configurações do Sistema"
        v-tooltip.bottom="navbarTooltip('settings')"
        @click="router.push('/configuracoes')"
        :class="['nav-icon-btn', { 'active-nav-btn': $route.path === '/configuracoes' }]"
      />
      <button
        type="button"
        class="nav-icon-btn lists-nav-btn"
        aria-label="Farmácias Monitoradas"
        @click="router.push('/listas')"
        v-tooltip.bottom="navbarTooltip('monitoredPharmacies')"
      >
        <i class="pi pi-bookmark" />
        <span v-if="totalListas > 0" class="lists-nav-badge">{{ totalListas }}</span>
      </button>
    </div>
  </nav>

  <Dialog
    v-model:visible="updateDetailsVisible"
    header="Atualização disponível"
    modal
    :draggable="false"
    class="nav-update-dialog"
  >
    <div class="nav-update-dialog__content">
      <p>Uma nova versão do Sentinela está disponível.</p>
      <p>Versão atual: <strong>v{{ updateStore.currentVersion }}</strong> · Nova versão: <strong>v{{ updateStore.latestVersion }}</strong></p>
      <a
        v-if="updateStore.releaseNotesUrl"
        :href="updateStore.releaseNotesUrl"
        target="_blank"
        rel="noopener noreferrer"
      >Notas da versão <i class="pi pi-external-link" aria-hidden="true" /></a>
      <p v-if="!updateStore.downloadUrl" class="nav-update-dialog__error">
        O link de download não está disponível. Tente verificar as atualizações novamente.
      </p>
    </div>
    <template #footer>
      <Button label="Mais tarde" text severity="secondary" @click="updateDetailsVisible = false" />
      <Button
        :label="isDesktop() ? 'Atualizar agora' : 'Abrir download'"
        icon="pi pi-download"
        :disabled="!updateStore.hasUpdate || updateStore.isDownloading || !updateStore.downloadUrl"
        @click="confirmUpdate"
      />
    </template>
  </Dialog>
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

.nav-update-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 0.35rem;
  height: 30px;
  padding: 0 0.65rem;
  border: 1px solid color-mix(in srgb, var(--risk-medium) 45%, transparent);
  border-radius: 6px;
  background: color-mix(in srgb, var(--risk-medium) 12%, var(--navbar-bg));
  color: var(--text-color-85);
  font: inherit;
  font-size: 0.68rem;
  font-weight: 600;
  white-space: nowrap;
  cursor: pointer;
  animation: nav-update-enter 0.6s cubic-bezier(0.16, 1, 0.3, 1) both,
    nav-update-pulse 1s ease-in-out 10;
}

.nav-update-badge:hover {
  background: color-mix(in srgb, var(--risk-medium) 20%, var(--navbar-bg));
}

.nav-update-badge:focus-visible {
  outline: 2px solid var(--risk-medium);
  outline-offset: 2px;
}

.nav-update-badge .pi {
  color: var(--risk-indicator-warning);
  font-size: 0.75rem;
}

.nav-update-badge__version {
  color: var(--text-secondary);
}

@keyframes nav-update-enter {
  from { opacity: 0.7; transform: translateY(-4px); }
  to { opacity: 1; transform: translateY(0); }
}

@keyframes nav-update-pulse {
  0%, 100% { border-color: color-mix(in srgb, var(--risk-medium) 45%, transparent); }
  50% { border-color: color-mix(in srgb, var(--risk-medium) 95%, transparent); }
}

@media (prefers-reduced-motion: reduce) {
  .nav-update-badge { animation: none; }
}

@media (max-width: 1600px) {
  .nav-update-badge__version { display: none; }
}

@media (max-width: 1500px) {
  .nav-update-badge__label { display: none; }
  .nav-update-badge { width: 30px; padding: 0; }
}

:deep(.nav-update-dialog) {
  width: min(450px, 90vw);
}

.nav-update-dialog__content {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
  color: var(--text-color-85);
  font-size: 0.88rem;
}

.nav-update-dialog__content p {
  margin: 0;
}

.nav-update-dialog__content strong {
  font-weight: 600;
}

.nav-update-dialog__content a {
  color: var(--primary-color);
  text-decoration: underline;
  text-underline-offset: 3px;
}

.nav-update-dialog__error {
  color: var(--risk-high);
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
  padding-right: 2.45rem;
}

.nav-recent-info {
  position: absolute;
  right: 1.35rem;
  top: 50%;
  transform: translateY(-50%);
  font-size: 0.65rem;
  color: var(--text-muted);
  opacity: 0.6;
  cursor: help;
  transition: opacity 0.15s, color 0.15s;
}

.nav-recent-info:hover,
.nav-recent-info:focus-visible {
  opacity: 1;
  color: var(--primary-color);
  outline: none;
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

.nav-icon-btn,
.nav-actions :deep(.nav-icon-btn.p-button) {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex: 0 0 36px;
  width: 36px;
  height: 36px;
  padding: 0;
  border: 0;
  border-radius: 6px;
  background: transparent;
  cursor: pointer;
  color: var(--text-secondary);
  font-size: 1rem;
  text-decoration: none;
  transition: background-color 0.15s ease, color 0.15s ease;
}

.nav-icon-btn:hover,
.nav-actions :deep(.nav-icon-btn.p-button:hover) {
  background: color-mix(in srgb, var(--text-color-85) 8%, transparent);
  color: var(--text-color-85);
}

.nav-icon-btn:focus-visible,
.nav-actions :deep(.nav-icon-btn.p-button:focus-visible) {
  outline: none;
  box-shadow: 0 0 0 2px color-mix(in srgb, var(--text-color-85) 16%, transparent);
}

.lists-nav-btn {
  position: relative;
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
