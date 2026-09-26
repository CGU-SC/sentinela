<script setup>
import { onMounted, onBeforeUnmount, ref } from 'vue';
import { useAnalyticsStore } from '@/stores/analytics';
import { useGeoStore } from '@/stores/geo';
import { useFilterParameters } from '@/composables/useFilterParameters';
import axios from 'axios';
import { API_ENDPOINTS } from '@/config/api';
import { TIMING } from '@/config/constants';
import { useThemeStore } from '@/stores/theme';
import { useSystemUpdateStore } from '@/stores/systemUpdate';
import Toast from 'primevue/toast';
import { createPdfObjectUrlFromDesktopFile, openDownloadedFile } from '@/utils/download';
import UpdateBlocker from '@/views/components/UpdateBlocker.vue';
import ExecutionBlocker from '@/views/components/ExecutionBlocker.vue';
import UpdateDialog from '@/views/components/UpdateDialog.vue';
import DocumentPreviewDialog from '@/views/components/DocumentPreviewDialog.vue';
import EvidenciasRemocaoDialog from '@/views/components/evidencias/EvidenciasRemocaoDialog.vue';

const analyticsStore = useAnalyticsStore();
const geoStore = useGeoStore();
const themeStore = useThemeStore();
const updateStore = useSystemUpdateStore();
const { getApiParams } = useFilterParameters();
const isAppLoading = ref(true);
const syncProgress = ref(0);
const statusMessage = ref("Iniciando Sistema...");
const hasError = ref(false);
const errorMessageDetail = ref("");
const previewVisible = ref(false);
const previewUrl = ref("");
const previewPath = ref("");
const previewTitle = ref("");
let _bootTimer = null;
let _pollTimer = null;

const pollSyncStatus = async () => {
  try {
    const response = await axios.get(API_ENDPOINTS.cacheStatus);
    const { progress, status } = response.data;
    
    syncProgress.value = progress;
    
    if (status === 'ready' && progress === 100) {
      clearInterval(_pollTimer);
      statusMessage.value = "Finalizando Carga...";
      return true;
    } else if (status === 'error' || status === 'idle') {
      // Sync falhou ou foi abortada — não fica em loop, deixa o app subir
      clearInterval(_pollTimer);
      return true;
    } else if (status === 'fetching') {
      statusMessage.value = `Baixando dados do CGUData... (${progress}%)`;
    } else if (status === 'processing') {
      statusMessage.value = "Otimizando Banco de Dados...";
    }
    return false;
  } catch (err) {
    console.warn("Erro ao checar status:", err);
    return false;
  }
};

const initializeApp = async () => {
  hasError.value = false;
  errorMessageDetail.value = "";
  isAppLoading.value = true;
  statusMessage.value = "Iniciando Sistema...";
  syncProgress.value = 0;

  try {
    // 1. Verifica status do cache
    const statusResp = await axios.get(API_ENDPOINTS.cacheStatus);
    const { is_ready, status } = statusResp.data;

    // Se uma sincronização já estiver em andamento (iniciada externamente),
    // aguarda ela terminar antes de carregar o dashboard.
    // Se o cache estiver ausente mas nenhuma sync estiver rodando (idle/error),
    // o app inicializa normalmente — o DataIntegrityBanner informa o usuário.
    if (!is_ready && (status === 'fetching' || status === 'processing')) {
      statusMessage.value = "Sincronização em andamento no servidor...";
      await new Promise((resolve) => {
        _pollTimer = setInterval(async () => {
          const finished = await pollSyncStatus();
          if (finished) resolve();
        }, TIMING.POLL_INTERVAL);
      });
    }

    // 2. Carga padrão dos dados do dashboard (só ocorre quando cache estiver pronto)
    // Re-lê o status após eventual wait de sync acima
    const currentStatus = await axios.get(API_ENDPOINTS.cacheStatus);
    if (!currentStatus.data.is_ready) {
      // Sistema subirá em "modo degradado". 
      // Não fazemos mais 'return;' aqui, permitindo que a UI carregue o que existir na mémoria.
      console.warn("Alguns caches estão ausentes. Iniciando em Modo Degradado.");
    }

    statusMessage.value = "Sincronizando Dashboard...";
    const filters = getApiParams();
    const { uf, regiaoId, idIbge7, unidadePf } = filters;

    const fetchList = [
      analyticsStore.fetchDashboardSummary(filters),
      analyticsStore.fetchFatorRisco(filters),
      geoStore.fetchLocalidades(),
      geoStore.loadMunicipiosGeo(),
      geoStore.fetchCnpjLookup(),
    ];

    // Se houver filtros geográficos ativos, o fetchDashboardSummary NÃO popula
    // resultadoSentinelaUFNacional (por design). Forçamos a busca nacional aqui
    // para garantir que o mapa do Brasil sempre seja exibido corretamente.
    if (uf || regiaoId || idIbge7 || unidadePf) {
      fetchList.push(
        analyticsStore.fetchSentinelaUFNacional(filters)
      );
    }

    await Promise.allSettled(fetchList);

    if (!hasError.value) {
      _bootTimer = setTimeout(() => {
        isAppLoading.value = false;
      }, TIMING.RELOAD_DELAY);
    }

  } catch (error) {
    console.error("Erro crítico na carga inicial:", error);
    statusMessage.value = "Erro na conexão com o servidor.";
    errorMessageDetail.value = error.response?.data?.message || error.message || String(error);
    hasError.value = true;
  }
};

const retryConnection = () => {
  initializeApp();
};

onMounted(() => {
  themeStore.initTheme();
  initializeApp();
  // Consulta status de atualização em paralelo — não bloqueia o boot
  updateStore.fetchUpdateStatus();
});

onBeforeUnmount(() => {
  clearTimeout(_bootTimer);
  clearInterval(_pollTimer);
});

const openToastFile = async (message) => {
  const path = message?.data?.path;
  if (!path) return;
  try {
    await openDownloadedFile(path);
  } catch (error) {
    console.error('Erro ao abrir arquivo salvo:', error);
  }
};

const closeDocumentPreview = () => {
  previewVisible.value = false;
  if (previewUrl.value) {
    window.URL.revokeObjectURL(previewUrl.value);
  }
  previewUrl.value = "";
  previewPath.value = "";
  previewTitle.value = "";
};

const openToastPreview = async (message) => {
  const path = message?.data?.previewPath;
  if (!path) return;
  try {
    const result = await createPdfObjectUrlFromDesktopFile(path);
    closeDocumentPreview();
    previewUrl.value = result.url;
    previewPath.value = result.path;
    previewTitle.value = result.filename || "Nota Tecnica";
    previewVisible.value = true;
  } catch (error) {
    console.error('Erro ao visualizar PDF salvo:', error);
  }
};

const openPreviewExternalFile = async () => {
  if (!previewPath.value) return;
  try {
    await openDownloadedFile(previewPath.value);
  } catch (error) {
    console.error('Erro ao abrir PDF salvo:', error);
  }
};
</script>

<template>
  <Toast />
  <EvidenciasRemocaoDialog />
  <Toast group="download" position="bottom-right">
    <template #message="slotProps">
      <div class="download-toast">
        <div class="download-toast-icon">
          <i :class="['pi', slotProps.message.data?.icon || 'pi-file-word']" />
        </div>
        <div class="download-toast-body">
          <div class="download-toast-title">{{ slotProps.message.summary }}</div>
          <div class="download-toast-detail">{{ slotProps.message.detail }}</div>
          <button
            v-if="slotProps.message.data?.path"
            type="button"
            class="download-toast-action"
            @click="openToastFile(slotProps.message)"
          >
            <i class="pi pi-external-link" />
            Abrir arquivo
          </button>
          <button
            v-if="slotProps.message.data?.previewPath"
            type="button"
            class="download-toast-action"
            @click="openToastPreview(slotProps.message)"
          >
            <i class="pi pi-eye" />
            Visualizar
          </button>
        </div>
      </div>
    </template>
  </Toast>
  <DocumentPreviewDialog
    :visible="previewVisible"
    :title="previewTitle"
    :file-url="previewUrl"
    :file-path="previewPath"
    @close="closeDocumentPreview"
    @open-file="openPreviewExternalFile"
  />

  <!-- OVERLAY DE CARREGAMENTO GLOBAL -->
  <div v-if="isAppLoading" class="app-boot-overlay">

     <!-- Logo fixada no topo, independente do conteúdo -->
     <div class="boot-brand-anchor">
        <img src="/img/logo_sentinela_transparente.png" alt="Sentinela" class="boot-logo" />
        <div class="boot-brand-caption">
           <span class="boot-brand-text">SENTINELA</span>
           <span class="boot-brand-sub">Auditoria no Farmácia Popular</span>
        </div>
     </div>

     <!-- Conteúdo central dinâmico (spinner ou erro) -->
     <div class="boot-dynamic-content">
        <template v-if="!hasError">
           <div class="spinner-orbit">
              <div class="core"></div>
              <div class="electron one"></div>
              <div class="electron two"></div>
           </div>
           <p class="status-message">{{ statusMessage }}</p>
           <div class="progress-bar-mini" v-if="syncProgress > 0">
              <div class="progress-fill" :style="{ width: syncProgress + '%', animation: 'none' }"></div>
           </div>
           <div class="progress-bar-mini" v-else>
              <div class="progress-fill"></div>
           </div>
        </template>

        <!-- Estado de Erro Profissional -->
        <template v-else>
           <div class="error-state-container">
              <svg class="error-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                 <circle cx="12" cy="12" r="10"></circle>
                 <line x1="12" y1="8" x2="12" y2="12"></line>
                 <line x1="12" y1="16" x2="12.01" y2="16"></line>
              </svg>
              <h2 class="error-title">Falha de Conexão</h2>
              <p class="status-message error-desc">
                 Não foi possível comunicar com o servidor backend.<br/>
                 Verifique se o serviço está ativo e tente novamente.
              </p>
              <div class="error-detail-box" v-if="errorMessageDetail">
                 <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#ef4444" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="flex-shrink: 0;">
                    <polyline points="4 17 10 11 4 5"></polyline>
                    <line x1="12" y1="19" x2="20" y2="19"></line>
                 </svg>
                 <code>{{ errorMessageDetail }}</code>
              </div>
              <button @click="retryConnection" class="retry-button">
                 <svg class="retry-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <polyline points="1 4 1 10 7 10"></polyline>
                    <polyline points="23 20 23 14 17 14"></polyline>
                    <path d="M20.49 9A9 9 0 0 0 5.64 5.64L1 10M23 14l-4.64 4.36A9 9 0 0 1 3.51 15"></path>
                 </svg>
                 Tentar Novamente
              </button>
           </div>
        </template>
     </div>

  </div>

  <!-- O RouterView só aparece quando tudo está pronto -->
  <router-view v-else />

  <!-- Bloqueio de versão incompatível — sobrepõe tudo, sem fechar -->
  <UpdateBlocker v-if="updateStore.status === 'update_required'" />
  <ExecutionBlocker v-else-if="updateStore.isExecutionBlocked" />
  <UpdateDialog />
</template>

<style scoped>
.app-boot-overlay {
  --boot-accent: #d97706;
  --boot-bg: #0d1117;
  --boot-card-bg: #161b22;
  --boot-text: #f8fafc;
  --boot-muted: #94a3b8;

  position: fixed;
  inset: 0;
  z-index: 9999;
  display: flex;
  align-items: center;
  justify-content: center;
  min-width: 100vw;
  min-height: 100vh;
  overflow: hidden;
  background:
    radial-gradient(circle at 50% 42%, rgba(22, 27, 34, 0.95) 0%, rgba(13, 17, 23, 0.98) 58%, var(--boot-bg) 100%);
  color: var(--boot-text);
}

.boot-brand-anchor {
  position: absolute;
  top: 25%;
  left: 50%;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.75rem;
  width: max-content;
  transform: translateX(-50%);
  color: var(--boot-text);
  text-align: center;
  white-space: nowrap;
}

.boot-dynamic-content {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 1.5rem;
  margin-top: 180px;
  color: var(--boot-text);
}

.boot-logo {
  width: 80px;
  height: auto;
  filter: drop-shadow(0 0 15px rgba(217, 119, 6, 0.32));
  animation: logo-pulse 2s ease-in-out infinite;
}

.boot-brand-caption {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.15rem;
}

.boot-brand-text {
  margin: 0;
  color: var(--boot-text);
  font-size: 2rem;
  font-weight: 900;
  letter-spacing: 6px;
  line-height: 1;
  background: linear-gradient(to right, #ffffff, #94a3b8);
  background-clip: text;
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
}

.boot-brand-sub {
  color: var(--boot-accent);
  font-size: 0.75rem;
  font-weight: 600;
  letter-spacing: 2px;
  line-height: 1;
  text-transform: uppercase;
  opacity: 0.9;
}

.spinner-orbit {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 80px;
  height: 80px;
}

.core {
  width: 12px;
  height: 12px;
  border-radius: 50%;
  background: var(--boot-accent);
  box-shadow: 0 0 20px rgba(217, 119, 6, 0.8);
}

.electron {
  position: absolute;
  border: 1px solid rgba(148, 163, 184, 0.3);
  border-radius: 50%;
}

.one {
  width: 60px;
  height: 60px;
  animation: orbit 2s linear infinite;
}

.one::after {
  content: '';
  position: absolute;
  top: 50%;
  left: -3px;
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--boot-accent);
}

.two {
  width: 40px;
  height: 40px;
  animation: orbit 1.5s linear reverse infinite;
}

.two::after {
  content: '';
  position: absolute;
  top: 0;
  left: 50%;
  width: 4px;
  height: 4px;
  border-radius: 50%;
  background: color-mix(in srgb, var(--boot-accent) 70%, white);
}

.status-message {
  margin: 0;
  color: var(--boot-text);
  font-size: 0.95rem;
  font-weight: 600;
  letter-spacing: 0.5px;
  opacity: 0.85;
}

.progress-bar-mini {
  width: 200px;
  height: 2px;
  overflow: hidden;
  border-radius: 1px;
  background: rgba(255, 255, 255, 0.1);
}

.progress-fill {
  width: 100%;
  height: 100%;
  background: var(--boot-accent);
  transform-origin: left;
  animation: loading-bar 2s ease-in-out infinite;
}

@keyframes logo-pulse {
  0%, 100% { transform: scale(1); opacity: 1; }
  50% { transform: scale(1.05); opacity: 0.9; }
}

@keyframes orbit {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

@keyframes loading-bar {
  0% { transform: scaleX(0); }
  50% { transform: scaleX(1); }
  100% { transform: scaleX(0); transform-origin: right; }
}

.error-state-container {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  animation: fadeIn 0.4s ease-out;
  margin-top: 1.5rem;
}

.error-icon {
  width: 56px;
  height: 56px;
  stroke: #ef4444;
  margin-bottom: 1rem;
  filter: drop-shadow(0 0 8px rgba(239, 68, 68, 0.4));
}

.error-title {
  color: #f8fafc;
  font-size: 1.15rem;
  font-weight: 500;
  margin: 0 0 0.5rem 0;
  letter-spacing: 0.5px;
}

.error-desc {
  max-width: 320px;
  line-height: 1.5;
  margin-bottom: 1rem;
  color: #94a3b8;
}

.error-detail-box {
  display: flex !important;
  flex-direction: row !important;
  align-items: center;
  justify-content: flex-start;
  gap: 12px;
  background: rgba(239, 68, 68, 0.05) !important;
  border: 1px solid rgba(239, 68, 68, 0.25) !important;
  border-radius: 8px;
  padding: 12px 16px;
  margin-top: 8px;
  margin-bottom: 32px;
  width: 100%;
  max-width: 450px;
}

.error-detail-box code {
  color: #fca5a5 !important;
  font-size: 0.85rem;
  letter-spacing: 0.5px;
  overflow-wrap: break-word;
  word-break: break-word;
  text-align: left;
  line-height: 1.4;
  margin: 0;
}

.retry-button {
  background: color-mix(in srgb, var(--primary-color) 85%, transparent);
  backdrop-filter: blur(8px);
  -webkit-backdrop-filter: blur(8px);
  color: white;
  border: 1px solid color-mix(in srgb, var(--primary-color) 30%, white 10%);
  padding: 0.75rem 1.5rem;
  border-radius: 10px;
  font-size: 0.95rem;
  font-weight: 600;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0.6rem;
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  box-shadow: 0 4px 15px color-mix(in srgb, var(--primary-color) 25%, transparent);
  font-family: inherit;
  letter-spacing: 0.02em;
}

.retry-button:hover {
  transform: translateY(-2px);
  background: var(--primary-color);
  box-shadow: 0 8px 25px color-mix(in srgb, var(--primary-color) 40%, transparent);
}

.retry-button:active {
  transform: translateY(0);
}

.retry-icon {
  width: 16px;
  height: 16px;
}

.download-toast {
  display: flex;
  align-items: flex-start;
  gap: 0.85rem;
  min-width: 320px;
  max-width: 440px;
}

.download-toast-icon {
  width: 2.25rem;
  height: 2.25rem;
  border-radius: 8px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  color: var(--primary-color);
  background: color-mix(in srgb, var(--primary-color) 12%, transparent);
  border: 1px solid color-mix(in srgb, var(--primary-color) 28%, transparent);
  flex: 0 0 auto;
}

.download-toast-body {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
}

.download-toast-title {
  color: var(--text-color-85);
  font-size: 0.95rem;
  font-weight: 600;
}

.download-toast-detail {
  color: var(--text-muted);
  font-size: 0.82rem;
  line-height: 1.35;
  word-break: break-word;
}

.download-toast-action {
  align-self: flex-start;
  margin-top: 0.25rem;
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
  min-height: 2rem;
  padding: 0 0.65rem;
  border-radius: 6px;
  border: 1px solid color-mix(in srgb, var(--primary-color) 40%, transparent);
  background: color-mix(in srgb, var(--primary-color) 10%, transparent);
  color: var(--primary-color);
  font-size: 0.78rem;
  font-weight: 600;
  cursor: pointer;
}

.download-toast-action:hover {
  background: color-mix(in srgb, var(--primary-color) 16%, transparent);
}

@keyframes fadeIn {
  from { opacity: 0; transform: translateY(10px); }
  to { opacity: 1; transform: translateY(0); }
}
</style>
