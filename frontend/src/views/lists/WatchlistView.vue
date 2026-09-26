<script setup>
import { computed, onMounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import axios from "axios";
import { useFarmaciaListsStore } from "@/stores/farmaciaLists";
import { useFilterStore } from "@/stores/filters";
import { useGeoStore } from "@/stores/geo";
import { useNotaTecnicaConfigStore } from "@/stores/notaTecnicaConfig";
import { useFormatting } from "@/composables/useFormatting";
import { useFilterParameters } from "@/composables/useFilterParameters";
import { usePdfExport } from "@/composables/usePdfExport";
import { loadCnpjPdfReportData } from "@/composables/useCnpjPdfReportData";
import { API_ENDPOINTS } from "@/config/api";
import { getApiErrorMessage } from "@/utils/apiErrors";
import { convertDocxToPdf, downloadBlobFromResponse } from "@/utils/download";
import ObservationDialog from "@/views/components/cnpj/ObservationDialog.vue";
import EvidenciasPanel from "@/views/components/evidencias/EvidenciasPanel.vue";
import NotaTecnicaRegionalDialog from "@/views/components/nota-tecnica/NotaTecnicaRegionalDialog.vue";
import { useToast } from "primevue/usetoast";
import Dropdown from "primevue/dropdown";
import { useEvidenciasStore } from "@/stores/evidencias";
import {
  TIPO_EVIDENCIA_OPCOES,
  dataHoraCurta,
  quandoEvidencia,
  resumoEvidencia,
  tipoEvidencia,
} from "@/utils/evidencias";

const router = useRouter();
const route = useRoute();
const evidenciasStore = useEvidenciasStore();
const farmaciaLists = useFarmaciaListsStore();
const filterStore = useFilterStore();
const geoStore = useGeoStore();
const notaTecnicaConfig = useNotaTecnicaConfigStore();
const toast = useToast();
const { formatBRL, formatCurrencyFull, formatNumberFull, formatarData, formatTitleCase } = useFormatting();
const { getApiParams } = useFilterParameters();
const { exportCnpjPdf } = usePdfExport();
const watchlistAnalytics = ref([]);
const watchlistLoading = ref(false);
const watchlistError = ref(null);
const showObsDialog = ref(false);
const obsTarget = ref(null);
const copiedCnpj = ref(null);
const exportingReportCnpj = ref(null);
const generatingNoteCnpj = ref(null);
const regionalDialogVisible = ref(false);
const pendingNoteItem = ref(null);

const formatCnpj = (v) => {
  if (!v) return "—";
  const clean = v.replace(/\D/g, "");
  if (clean.length !== 14) return v;
  return clean.replace(/^(\d{2})(\d{3})(\d{3})(\d{4})(\d{2})$/, "$1.$2.$3/$4-$5");
};

const formatDate = (iso) => {
  if (!iso) return "—";
  return new Date(iso).toLocaleDateString("pt-BR", {
    day: "2-digit", month: "2-digit", year: "numeric",
  });
};

const formatPeriodMonth = (date) => {
  const value = date instanceof Date ? date : new Date(date);
  if (Number.isNaN(value.getTime())) return "—";

  const months = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"];
  return `${months[value.getMonth()]}/${value.getFullYear()}`;
};

const monitoredCnpjs = computed(() =>
  farmaciaLists.interesse.map((item) => item.cnpj).filter(Boolean),
);

const monitoredCnpjsKey = computed(() => monitoredCnpjs.value.join("|"));
const periodKey = computed(() =>
  Array.isArray(filterStore.periodo)
    ? filterStore.periodo.map((date) => date?.getTime?.() ?? String(date ?? "")).join("|")
    : "",
);
const periodoAnaliseLabel = computed(() => {
  const [inicio, fim] = Array.isArray(filterStore.periodo) ? filterStore.periodo : [];
  if (!inicio || !fim) return "Período não definido";

  return `${formatPeriodMonth(inicio)} - ${formatPeriodMonth(fim)}`;
});

async function fetchWatchlistAnalytics() {
  if (!monitoredCnpjs.value.length) {
    watchlistAnalytics.value = [];
    watchlistError.value = null;
    return;
  }

  const { inicio, fim } = getApiParams();
  const params = new URLSearchParams();
  if (inicio) params.append("data_inicio", inicio);
  if (fim) params.append("data_fim", fim);
  monitoredCnpjs.value.forEach((cnpj) => params.append("cnpjs", cnpj));

  watchlistLoading.value = true;
  watchlistError.value = null;
  try {
    const response = await axios.get(`${API_ENDPOINTS.analyticsResumo}?${params.toString()}`);
    watchlistAnalytics.value = response.data?.resultado_cnpjs || [];
  } catch (error) {
    console.error("Erro ao buscar dados da lista de interesse:", error);
    watchlistAnalytics.value = [];
    watchlistError.value = "Não foi possível carregar os indicadores da lista.";
  } finally {
    watchlistLoading.value = false;
  }
}

watch([monitoredCnpjsKey, periodKey], fetchWatchlistAnalytics, { immediate: true });

function isPreferencesUnavailable(error) {
  return error?.response?.status === 503 && error?.config?.url === API_ENDPOINTS.preferences;
}

async function carregarRegional({ force = false, reportarErroPreferencias = false } = {}) {
  try {
    await notaTecnicaConfig.ensureLoaded({ force });
  } catch (error) {
    // O aviso persistente das preferências já explica esta mesma falha.
    if (isPreferencesUnavailable(error) && !reportarErroPreferencias) return;
    toast.add({
      severity: "warn",
      summary: "Regional da Nota Técnica",
      detail: isPreferencesUnavailable(error)
        ? "Não foi possível carregar a regional porque as preferências continuam indisponíveis."
        : error?.response?.data?.detail || "Não foi possível carregar a configuração da Nota Técnica.",
      life: 6000,
    });
  }
}

onMounted(() => {
  farmaciaLists.loadRecoveryOptions();
  carregarRegional();
});

// Map O(1): cnpj → dados analíticos da consulta dedicada da lista
const analyticsMap = computed(() => {
  const map = new Map();
  for (const e of watchlistAnalytics.value) {
    map.set(e.cnpj, e);
  }
  return map;
});

const RISCO_COLOR = {
  'CRÍTICO':  '#ef4444',
  'ALTO':     '#f97316',
  'MÉDIO':    '#f59e0b',
  'BAIXO':    '#10b981',
};

// Lista enriquecida — une store + analytics + geo
const listaEnriquecida = computed(() =>
  farmaciaLists.interesse.map((item) => {
    const a = analyticsMap.value.get(item.cnpj) ?? {};
    return {
      ...item,
      razaoSocial:    item.razaoSocial || a.razao_social || '—',
      municipio:      a.municipio || '—',
      uf:             a.uf || '—',
      percValSemComp: a.percValSemComp ?? null,
      scoreRisco:     a.score_risco_final ?? null,
      classificacao:  a.classificacao_risco ?? null,
      totalMov:       a.totalMov ?? null,
      valSemComp:     a.valSemComp ?? null,
    };
  })
);

const totalBadge = computed(() => farmaciaLists.interesse.length);
const regionalLabel = computed(() => {
  if (farmaciaLists.loadState === 'error') return 'Regional da NT indisponível';
  if (!notaTecnicaConfig.loaded) return notaTecnicaConfig.loading
    ? 'Carregando regional da NT...'
    : 'Regional da NT indisponível';
  return notaTecnicaConfig.selectedRegionalLabel || 'Regional da NT não definida';
});

async function tentarCarregarNovamente() {
  await farmaciaLists.loadFromBackend();
  if (farmaciaLists.loadState === 'ready') {
    await carregarRegional({ force: true, reportarErroPreferencias: true });
  }
}

function remover(cnpj) {
  farmaciaLists.toggleInteresse(cnpj, "");
}

async function restaurarArquivo(source, count) {
  if (window.confirm(`Restaurar ${count} farmácia(s) desta cópia? A lista atual será preservada antes da restauração.`)) {
    if (await farmaciaLists.restoreFromFile(source)) {
      await carregarRegional({ force: true, reportarErroPreferencias: true });
    }
  }
}

async function restaurarLocal() {
  if (window.confirm(`Restaurar ${farmaciaLists.localSnapshot.length} farmácia(s) da cópia local desta janela?`)) {
    if (await farmaciaLists.restoreFromLocal()) {
      await carregarRegional({ force: true, reportarErroPreferencias: true });
    }
  }
}

function abrirEstabelecimento(cnpj) {
  router.push(`/estabelecimentos/${cnpj}`);
}

async function copyCnpj(cnpj) {
  await navigator.clipboard.writeText(cnpj);
  copiedCnpj.value = cnpj;
  window.setTimeout(() => {
    if (copiedCnpj.value === cnpj) copiedCnpj.value = null;
  }, 1400);
}

async function gerarRelatorio(item) {
  if (exportingReportCnpj.value) return;

  exportingReportCnpj.value = item.cnpj;
  try {
    const { inicio, fim, volumeAtipicoPercentual } = getApiParams();
    const payload = await loadCnpjPdfReportData({
      cnpj: item.cnpj,
      inicio,
      fim,
      volumeAtipicoPercentual,
      geoStore,
      formatTitleCase,
      formatarData,
    });

    const downloadResult = await exportCnpjPdf({
      ...payload,
      geoStore,
      formatCurrencyFull,
      formatNumberFull,
      formatarData,
    });
    if (downloadResult?.desktop) {
      toast.add({
        group: "download",
        severity: "success",
        summary: "Relatório PDF salvo",
        detail: `Arquivo salvo em notas_tecnicas\\${downloadResult.filename}.`,
        data: { path: downloadResult.path, previewPath: downloadResult.path },
      });
    }
  } catch (error) {
    console.error("Erro ao gerar Relatório PDF:", error);
    toast.add({
      severity: "error",
      summary: "Erro ao gerar Relatório PDF",
      detail: error?.message || "Não foi possível gerar o arquivo.",
      life: 8000,
    });
  } finally {
    exportingReportCnpj.value = null;
  }
}

function buildNotaTecnicaUrl(cnpj, dadosNota = {}) {
  const { inicio, fim } = getApiParams();
  const params = new URLSearchParams({
    data_inicio: inicio,
    data_fim: fim,
    regional_codigo: notaTecnicaConfig.selectedRegionalCodigo,
  });
  if (dadosNota.numeroNota) params.set("numero_nota", dadosNota.numeroNota);
  if (dadosNota.numeroProcesso) params.set("numero_processo", dadosNota.numeroProcesso);
  if (dadosNota.assinantesTecnicos?.length) {
    params.set("assinantes_tecnicos", JSON.stringify(dadosNota.assinantesTecnicos));
  }
  return `${API_ENDPOINTS.analyticsNotaTecnica(cnpj)}?${params.toString()}`;
}

async function gerarNotaTecnica(item, { skipRegionalCheck = false, dadosNota = {} } = {}) {
  if (generatingNoteCnpj.value) return;

  try {
    if (!skipRegionalCheck) {
      await notaTecnicaConfig.ensureLoaded();
      pendingNoteItem.value = item;
      regionalDialogVisible.value = true;
      return;
    }

    generatingNoteCnpj.value = item.cnpj;
    const url = buildNotaTecnicaUrl(item.cnpj, dadosNota);
    const response = await fetch(url);
    if (!response.ok) {
      throw new Error(
        await getApiErrorMessage(response, "Erro ao gerar nota técnica"),
      );
    }

    const downloadResult = await downloadBlobFromResponse(response, `Nota_Tecnica_${item.cnpj}.docx`);
    if (downloadResult?.desktop) {
      let previewPath = null;
      if (dadosNota.gerarPdf !== false) {
        try {
          const previewResult = await convertDocxToPdf(downloadResult.path);
          previewPath = previewResult.path;
        } catch (error) {
          toast.add({
            severity: "warn",
            summary: "Pre-visualizacao indisponivel",
            detail: error?.message || "A Nota Tecnica foi salva, mas nao foi possivel gerar a versao PDF para visualizacao.",
            life: 12000,
          });
        }
      }

      toast.add({
        group: "download",
        severity: "success",
        summary: "Nota Técnica salva",
        detail: `Arquivo salvo em notas_tecnicas\\${downloadResult.filename}.`,
        data: { path: downloadResult.path, previewPath },
      });
    }
  } catch (error) {
    console.error("Erro ao gerar Nota Técnica:", error);
    toast.add({
      severity: "error",
      summary: "Erro ao gerar Nota Técnica",
      detail: error?.message || "Não foi possível gerar o arquivo.",
      life: 8000,
    });
  } finally {
    generatingNoteCnpj.value = null;
  }
}

async function onRegionalSavedForList(dadosNota) {
  if (!pendingNoteItem.value) return;
  const item = pendingNoteItem.value;
  pendingNoteItem.value = null;
  await gerarNotaTecnica(item, { skipRegionalCheck: true, dadosNota });
}

function setRegionalDialogVisible(visible) {
  regionalDialogVisible.value = visible;
  if (!visible) pendingNoteItem.value = null;
}

// ── Abas: Farmácias monitoradas | Evidências ─────────────────────────────
const ABAS = ["farmacias", "evidencias"];
const abaDaRota = () => (ABAS.includes(route.query.aba) ? route.query.aba : "farmacias");
const aba = ref(abaDaRota());
const filtroEvidCnpj = ref(typeof route.query.cnpj === "string" ? route.query.cnpj : null);
const filtroEvidTipo = ref(null);
const removendoEvidId = ref(null);
const ocupadoEvidId = ref(null);

watch(() => [route.query.aba, route.query.cnpj], () => {
  aba.value = abaDaRota();
  if (typeof route.query.cnpj === "string") filtroEvidCnpj.value = route.query.cnpj;
});

function setAba(valor) {
  if (aba.value === valor) return;
  aba.value = valor;
  removendoEvidId.value = null;
  const { aba: _aba, cnpj: _cnpj, ...query } = route.query;
  router.replace({ query: valor === "farmacias" ? query : { ...query, aba: valor } });
}

const painelEvidCnpj = ref(null);

onMounted(() => {
  evidenciasStore.painelAberto = false;
  evidenciasStore.garantirCarregado();
});

const nomePorCnpj = computed(() => {
  const map = new Map();
  for (const item of listaEnriquecida.value) map.set(item.cnpj, item.razaoSocial);
  return map;
});

function nomeFarmacia(cnpj) {
  const nome = nomePorCnpj.value.get(cnpj);
  return nome && nome !== "—" ? nome : formatCnpj(cnpj);
}

const totalEvidencias = computed(() => evidenciasStore.itens.length);

const farmaciasComEvidencia = computed(() => {
  const cnpjs = [...new Set(evidenciasStore.itens.map((ev) => ev.cnpj))];
  return cnpjs
    .map((cnpj) => ({ value: cnpj, label: `${nomeFarmacia(cnpj)} (${evidenciasStore.contar(cnpj)})` }))
    .sort((a, b) => a.label.localeCompare(b.label, "pt-BR"));
});

const opcoesFiltroFarmacia = computed(() => [
  { value: null, label: `Todas as farmácias (${farmaciasComEvidencia.value.length})` },
  ...farmaciasComEvidencia.value,
]);

// Farmácia (A–Z) e, dentro dela, ordem cronológica — a ordem de leitura de um relatório.
const evidenciasFiltradas = computed(() => {
  const cnpjs = filtroEvidCnpj.value
    ? [filtroEvidCnpj.value]
    : farmaciasComEvidencia.value.map((f) => f.value);
  return cnpjs.flatMap((cnpj) => evidenciasStore
    .listarDoCnpj(cnpj)
    .filter((ev) => !filtroEvidTipo.value || ev.tipo === filtroEvidTipo.value));
});

function limparFiltrosEvidencia() {
  filtroEvidCnpj.value = null;
  filtroEvidTipo.value = null;
}

function abrirEvidencia(ev) {
  evidenciasStore.irPara(ev, router);
}

function abrirEvidenciasDaFarmacia(cnpj) {
  painelEvidCnpj.value = cnpj;
  evidenciasStore.painelAberto = true;
}

async function removerEvidencia(ev) {
  ocupadoEvidId.value = ev.id;
  try {
    await evidenciasStore.remover(ev.id);
    removendoEvidId.value = null;
    toast.add({ severity: "info", summary: "Evidência removida", detail: quandoEvidencia(ev), life: 2500 });
  } catch (error) {
    toast.add({ severity: "error", summary: "Evidência não removida", detail: error.message, life: 7000 });
  } finally {
    ocupadoEvidId.value = null;
  }
}

function editarObservacao(item) {
  obsTarget.value = item;
  showObsDialog.value = true;
}

function formatPerc(v) {
  if (v == null) return '—';
  return `${v.toFixed(1)}%`;
}

function formatScore(v) {
  if (v == null) return '—';
  return v.toFixed(3);
}
</script>

<template>
  <div class="lists-view">
    <div class="lists-header">
      <div class="lists-title">
        <i class="pi pi-bookmark" />
        <h2>Farmácias Monitoradas</h2>
        <span class="total-badge" v-if="totalBadge > 0">{{ totalBadge }}</span>
      </div>
      <p class="lists-subtitle">
        CNPJs adicionados à Lista de Interesse para acompanhamento manual. Os indicadores refletem o escopo de filtros atual.
      </p>
    </div>

    <section v-if="farmaciaLists.loadState === 'error' || farmaciaLists.error || farmaciaLists.localRecoveryAvailable ||
      (farmaciaLists.loadState === 'ready' && farmaciaLists.interesse.length === 0 &&
        (farmaciaLists.recoveryOptions?.backup?.watchlist_count > 0 || farmaciaLists.recoveryOptions?.corrupt?.watchlist_count > 0))"
      class="preferences-recovery" aria-label="Estado das Farmácias Monitoradas">
      <div class="preferences-recovery-copy">
        <i class="pi pi-shield" aria-hidden="true" />
        <div>
          <p v-if="farmaciaLists.loadState === 'error'">Não foi possível abrir sua lista. Nenhum favorito foi apagado por esta tela.</p>
          <p v-else-if="farmaciaLists.error">{{ farmaciaLists.error }}</p>
          <p v-else>Há cópias da sua lista disponíveis para conferência e recuperação.</p>
          <span>A restauração só acontece após sua confirmação. O arquivo atual é preservado.</span>
        </div>
      </div>
      <div class="preferences-recovery-actions">
        <button v-if="farmaciaLists.loadState === 'error'" type="button" :disabled="farmaciaLists.saving"
          @click="tentarCarregarNovamente">Tentar carregar novamente</button>
        <button v-if="farmaciaLists.recoveryOptions?.backup?.valid && farmaciaLists.recoveryOptions.backup.watchlist_count > 0"
          type="button" :disabled="farmaciaLists.saving"
          @click="restaurarArquivo('backup', farmaciaLists.recoveryOptions.backup.watchlist_count)">
          Restaurar backup ({{ farmaciaLists.recoveryOptions.backup.watchlist_count }})
        </button>
        <button v-if="farmaciaLists.recoveryOptions?.corrupt?.valid && farmaciaLists.recoveryOptions.corrupt.watchlist_count > 0"
          type="button" :disabled="farmaciaLists.saving"
          @click="restaurarArquivo('corrupt', farmaciaLists.recoveryOptions.corrupt.watchlist_count)">
          Restaurar cópia isolada ({{ farmaciaLists.recoveryOptions.corrupt.watchlist_count }})
        </button>
        <button v-if="farmaciaLists.localRecoveryAvailable && farmaciaLists.loadState === 'ready'"
          type="button" :disabled="farmaciaLists.saving" @click="restaurarLocal">
          Restaurar cópia local ({{ farmaciaLists.localSnapshot.length }})
        </button>
      </div>
    </section>

    <div class="lists-tabs" role="tablist" aria-label="Listas">
      <button
        type="button"
        role="tab"
        :aria-selected="aba === 'farmacias'"
        :class="['lists-tab', { 'is-active': aba === 'farmacias' }]"
        @click="setAba('farmacias')"
      >
        <i class="pi pi-bookmark" aria-hidden="true" />
        Farmácias monitoradas
        <span class="lists-tab-count">{{ totalBadge }}</span>
      </button>
      <button
        type="button"
        role="tab"
        :aria-selected="aba === 'evidencias'"
        :class="['lists-tab', { 'is-active': aba === 'evidencias' }]"
        @click="setAba('evidencias')"
      >
        <i class="pi pi-flag" aria-hidden="true" />
        Evidências
        <span class="lists-tab-count">{{ evidenciasStore.loadState === 'ready' ? totalEvidencias : '—' }}</span>
      </button>
    </div>

    <div v-if="aba === 'farmacias'" class="lists-card">
      <div class="card-header">
        <div class="card-header-left">
          <i class="pi pi-table" />
          <span>Estabelecimentos monitorados</span>
        </div>
        <div class="card-header-right">
          <button
            class="regional-nt-chip"
            type="button"
            @click="regionalDialogVisible = true"
            :disabled="farmaciaLists.loadState !== 'ready' || !notaTecnicaConfig.loaded"
            v-tooltip.top="farmaciaLists.loadState === 'error' ? 'Regional indisponível enquanto as preferências não puderem ser lidas' : 'Regional emissora das Notas Técnicas'"
          >
            <i class="pi pi-building" />
            <span>{{ regionalLabel }}</span>
          </button>
          <span class="period-chip" v-tooltip.top="'Período de análise atual'">
            <i class="pi pi-calendar" />
            <span>Período: {{ periodoAnaliseLabel }}</span>
          </span>
          <span v-if="watchlistLoading" class="card-count">Atualizando indicadores...</span>
          <span v-else-if="watchlistError" class="card-count card-error">{{ watchlistError }}</span>
          <span v-else-if="totalBadge > 0" class="card-count">{{ totalBadge }} registros</span>
        </div>
      </div>

      <div class="lists-content">
        <div v-if="farmaciaLists.loadState === 'loading'" class="empty-state" role="status">
          <i class="pi pi-spin pi-spinner empty-icon" aria-hidden="true" />
          <p>Carregando Farmácias Monitoradas...</p>
        </div>
        <div v-else-if="farmaciaLists.loadState === 'error'" class="empty-state" role="status">
          <i class="pi pi-exclamation-triangle empty-icon" aria-hidden="true" />
          <p>Lista indisponível. Use as opções de recuperação acima.</p>
        </div>
        <div v-else-if="farmaciaLists.interesse.length === 0" class="empty-state">
          <i class="pi pi-star empty-icon" />
          <p>Nenhuma farmácia na Lista de Interesse.</p>
          <span>Acesse o detalhe de um estabelecimento e clique no ícone de estrela.</span>
        </div>

      <table v-else class="lists-table">
        <thead>
          <tr>
            <th>#</th>
            <th>Estabelecimento</th>
            <th>Observação</th>
            <th>Localização</th>
            <th class="col-right">Risco</th>
            <th class="col-right">% Não Comp.</th>
            <th class="col-right">Valor s/ Comp.</th>
            <th class="col-right">Total Mov.</th>
            <th>Evidências</th>
            <th>Adicionado em</th>
            <th class="col-actions">Ações</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="(item, i) in listaEnriquecida"
            :key="item.cnpj"
            class="clickable-row"
            tabindex="0"
            @click="abrirEstabelecimento(item.cnpj)"
            @keydown.enter="abrirEstabelecimento(item.cnpj)"
            @keydown.space.prevent="abrirEstabelecimento(item.cnpj)"
          >
            <td class="col-num">{{ i + 1 }}</td>
            <td class="col-establishment">
              <div class="establishment-block">
                <span class="establishment-name" v-tooltip.top="item.razaoSocial">
                  {{ item.razaoSocial }}
                </span>
                <span class="cnpj-row">
                  <span class="cnpj-text">{{ formatCnpj(item.cnpj) }}</span>
                  <button
                    class="copy-btn"
                    @click.stop="copyCnpj(item.cnpj)"
                    v-tooltip.top="copiedCnpj === item.cnpj ? 'CNPJ copiado' : 'Copiar CNPJ'"
                    aria-label="Copiar CNPJ"
                  >
                    <i :class="copiedCnpj === item.cnpj ? 'pi pi-check' : 'pi pi-copy'" />
                  </button>
                </span>
              </div>
            </td>
            <td class="col-obs">
              <div class="obs-cell">
                <div v-if="item.observacao" class="obs-content" v-tooltip.top="item.observacao">
                  <i class="pi pi-comment mr-1 opacity-60" />
                  <span class="obs-text">{{ item.observacao }}</span>
                </div>
                <span v-else class="col-vazio">—</span>
                <button
                  class="obs-edit-btn"
                  @click.stop="editarObservacao(item)"
                  v-tooltip.top="item.observacao ? 'Editar Observação' : 'Adicionar Observação'"
                  aria-label="Editar observação"
                >
                  <i :class="item.observacao ? 'pi pi-comment' : 'pi pi-pencil'" />
                </button>
              </div>
            </td>
            <td class="col-loc">
              <div class="loc-block">
                <span v-if="item.municipio !== '—'" class="municipio-text" v-tooltip.top="item.municipio">
                  {{ item.municipio }}
                </span>
                <span v-else class="col-vazio">—</span>
                <span v-if="item.uf !== '—'" class="uf-tag">{{ item.uf }}</span>
              </div>
            </td>
            <td class="col-right col-score">
              <span v-if="item.scoreRisco != null"
                class="score-badge"
                :style="{ color: RISCO_COLOR[item.classificacao] || 'var(--text-muted)' }">
                <span class="score-value">{{ formatScore(item.scoreRisco) }}</span>
                <span v-if="item.classificacao" class="score-class">{{ item.classificacao }}</span>
              </span>
              <span v-else class="col-vazio">—</span>
            </td>
            <td class="col-right col-perc">
              <span v-if="item.percValSemComp != null"
                :class="['perc-badge', item.percValSemComp >= 50 ? 'perc-alto' : item.percValSemComp >= 20 ? 'perc-medio' : 'perc-baixo']">
                {{ formatPerc(item.percValSemComp) }}
              </span>
              <span v-else class="col-vazio">—</span>
            </td>
            <td class="col-right col-money col-sem-comp">
              {{ item.valSemComp != null ? formatBRL(item.valSemComp) : '—' }}
            </td>
            <td class="col-right col-money col-total-mov">
              {{ item.totalMov != null ? formatBRL(item.totalMov) : '—' }}
            </td>
            <td class="col-evid">
              <button
                v-if="evidenciasStore.contar(item.cnpj) > 0"
                type="button"
                class="evid-count-btn"
                :aria-label="`Abrir as ${evidenciasStore.contar(item.cnpj)} evidências de ${item.razaoSocial}`"
                @click.stop="abrirEvidenciasDaFarmacia(item.cnpj)"
              >
                <i class="pi pi-flag-fill" aria-hidden="true" />
                <span class="evid-count-num">{{ evidenciasStore.contar(item.cnpj) }}</span>
                <span class="evid-count-date">{{ dataHoraCurta(evidenciasStore.ultimaEm(item.cnpj)) }}</span>
              </button>
              <span v-else-if="evidenciasStore.loadState === 'error'" class="col-vazio">?</span>
              <span v-else class="col-vazio">—</span>
            </td>
            <td class="col-date">{{ formatDate(item.adicionadoEm) }}</td>
            <td class="col-actions">
              <div class="action-btns">
                <button
                  class="action-btn open"
                  @click.stop="abrirEstabelecimento(item.cnpj)"
                  v-tooltip.top="'Abrir detalhamento'"
                >
                  <i class="pi pi-arrow-up-right" />
                </button>
                <button
                  class="action-btn report"
                  @click.stop="gerarRelatorio(item)"
                  :disabled="!!exportingReportCnpj"
                  v-tooltip.top="'Gerar relatório PDF'"
                >
                  <i :class="exportingReportCnpj === item.cnpj ? 'pi pi-spin pi-spinner' : 'pi pi-file-pdf'" />
                </button>
                <button
                  class="action-btn note"
                  @click.stop="gerarNotaTecnica(item)"
                  :disabled="!!generatingNoteCnpj"
                  v-tooltip.top="'Gerar nota técnica'"
                >
                  <i :class="generatingNoteCnpj === item.cnpj ? 'pi pi-spin pi-spinner' : 'pi pi-book'" />
                </button>
                <button
                  class="action-btn remove"
                  @click.stop="remover(item.cnpj)"
                  :disabled="!farmaciaLists.canEdit"
                  v-tooltip.top="'Remover da lista'"
                >
                  <i class="pi pi-trash" />
                </button>
              </div>
            </td>
          </tr>
        </tbody>
      </table>
      </div><!-- /lists-content -->
    </div><!-- /lists-card -->

    <div v-else class="lists-card">
      <div class="card-header">
        <div class="card-header-left">
          <i class="pi pi-flag" />
          <span>Evidências marcadas</span>
        </div>
        <div class="card-header-right evid-toolbar">
          <Dropdown
            v-model="filtroEvidCnpj"
            :options="opcoesFiltroFarmacia"
            option-label="label"
            option-value="value"
            class="evid-filtro-farmacia"
            aria-label="Filtrar por farmácia"
            :disabled="evidenciasStore.loadState !== 'ready' || totalEvidencias === 0"
          />
          <div class="evid-tipos" role="radiogroup" aria-label="Filtrar por tipo">
            <button
              v-for="opcao in TIPO_EVIDENCIA_OPCOES"
              :key="String(opcao.value)"
              type="button"
              role="radio"
              :aria-checked="filtroEvidTipo === opcao.value"
              :class="['evid-tipo-btn', { 'is-active': filtroEvidTipo === opcao.value }]"
              :disabled="evidenciasStore.loadState !== 'ready' || totalEvidencias === 0"
              @click="filtroEvidTipo = opcao.value"
            >{{ opcao.label }}</button>
          </div>
          <span v-if="evidenciasStore.loadState === 'ready'" class="card-count">
            {{ evidenciasFiltradas.length }} de {{ totalEvidencias }}
          </span>
        </div>
      </div>

      <div class="lists-content">
        <div v-if="evidenciasStore.loadState === 'loading' || evidenciasStore.loadState === 'idle'" class="empty-state" role="status">
          <i class="pi pi-spin pi-spinner empty-icon" aria-hidden="true" />
          <p>Carregando evidências...</p>
        </div>
        <div v-else-if="evidenciasStore.loadState === 'error'" class="empty-state evid-error" role="alert">
          <i class="pi pi-exclamation-triangle empty-icon" aria-hidden="true" />
          <p>{{ evidenciasStore.error }}</p>
          <button type="button" class="evid-retry-btn" @click="evidenciasStore.carregar()">Tentar novamente</button>
        </div>
        <div v-else-if="totalEvidencias === 0" class="empty-state">
          <i class="pi pi-flag empty-icon" aria-hidden="true" />
          <p>Nenhuma evidência marcada.</p>
          <span>Na Cronologia de uma farmácia, marque dias, horas ou autorizações com a bandeira.</span>
        </div>
        <div v-else-if="evidenciasFiltradas.length === 0" class="empty-state">
          <i class="pi pi-filter-slash empty-icon" aria-hidden="true" />
          <p>Nenhuma evidência com estes filtros.</p>
          <button type="button" class="evid-retry-btn" @click="limparFiltrosEvidencia">Limpar filtros</button>
        </div>

        <table v-else class="lists-table evid-table">
          <thead>
            <tr>
              <th>Estabelecimento</th>
              <th>Tipo</th>
              <th>Data / hora</th>
              <th>Resumo</th>
              <th>Nota do auditor</th>
              <th>Marcada em</th>
              <th class="col-actions">Ações</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="ev in evidenciasFiltradas"
              :key="ev.id"
              class="clickable-row"
              :class="{ 'is-busy': ocupadoEvidId === ev.id }"
              tabindex="0"
              @click="abrirEvidencia(ev)"
              @keydown.enter="abrirEvidencia(ev)"
            >
              <td class="col-establishment">
                <div class="establishment-block">
                  <span class="establishment-name">{{ nomeFarmacia(ev.cnpj) }}</span>
                  <span class="cnpj-text">{{ formatCnpj(ev.cnpj) }}</span>
                </div>
              </td>
              <td>
                <span class="evid-tipo-tag">
                  <i :class="['pi', tipoEvidencia(ev.tipo).icon]" aria-hidden="true" />
                  {{ tipoEvidencia(ev.tipo).label }}
                </span>
              </td>
              <td class="evid-quando">{{ quandoEvidencia(ev) }}</td>
              <td class="evid-resumo">{{ resumoEvidencia(ev) }}</td>
              <td>
                <span v-if="ev.nota" class="evid-nota" v-tooltip.top="ev.nota.length > 120 ? ev.nota : null">{{ ev.nota }}</span>
                <span v-else class="col-vazio">—</span>
              </td>
              <td class="col-date">{{ dataHoraCurta(ev.criado_em) }}</td>
              <td class="col-actions">
                <div v-if="removendoEvidId === ev.id" class="evid-confirma" @click.stop>
                  <button type="button" class="action-btn remove is-confirm" :disabled="ocupadoEvidId === ev.id" aria-label="Confirmar remoção" @click.stop="removerEvidencia(ev)">
                    <i class="pi pi-check" />
                  </button>
                  <button type="button" class="action-btn" aria-label="Cancelar remoção" @click.stop="removendoEvidId = null">
                    <i class="pi pi-times" />
                  </button>
                </div>
                <div v-else class="action-btns">
                  <button type="button" class="action-btn open" aria-label="Abrir na Cronologia" @click.stop="abrirEvidencia(ev)">
                    <i class="pi pi-arrow-up-right" />
                  </button>
                  <button type="button" class="action-btn remove" aria-label="Remover evidência" @click.stop="removendoEvidId = ev.id">
                    <i class="pi pi-trash" />
                  </button>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
    <EvidenciasPanel
      v-if="painelEvidCnpj"
      :cnpj="painelEvidCnpj"
      :razao-social="nomeFarmacia(painelEvidCnpj)"
      contexto="listas"
    />
    <ObservationDialog
      v-if="obsTarget"
      v-model:visible="showObsDialog"
      :cnpj="obsTarget.cnpj"
      :entity-name="obsTarget.razaoSocial || formatCnpj(obsTarget.cnpj)"
    />
    <NotaTecnicaRegionalDialog
      :visible="regionalDialogVisible"
      :continue-label="pendingNoteItem ? 'Gerar Nota Técnica' : 'Salvar dados'"
      @update:visible="setRegionalDialogVisible"
      @saved="onRegionalSavedForList"
    />
  </div>
</template>

<style scoped>
.lists-view {
  padding: 2rem;
  display: flex;
  flex-direction: column;
  gap: 1.5rem;
  max-width: 98%;
  margin: 0 auto;
}

.lists-header {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
  border-bottom: 1px solid var(--tabs-border);
  padding-bottom: 1.5rem;
}

.lists-title {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}

.lists-title i {
  font-size: 1.2rem;
  color: var(--primary-color);
}

.lists-title h2 {
  font-size: 1.2rem;
  font-weight: 400;
  margin: 0;
  color: var(--text-color-85);
}

.total-badge {
  font-size: 0.72rem;
  font-weight: 400;
  padding: 0.1rem 0.5rem;
  border-radius: 20px;
  background: color-mix(in srgb, var(--primary-color) 15%, transparent);
  color: var(--primary-color);
  border: 1px solid color-mix(in srgb, var(--primary-color) 25%, transparent);
}

.lists-subtitle {
  font-size: 0.8rem;
  color: var(--text-color-85);
  opacity: 0.5;
  margin: 0;
}

.preferences-recovery {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 1rem;
  padding: 0.9rem 1.1rem;
  border: 1px solid var(--risk-high);
  border-radius: 12px;
  background: color-mix(in srgb, var(--risk-high) 8%, var(--card-bg));
  color: var(--text-color-85);
}

.preferences-recovery-copy { display: flex; align-items: flex-start; gap: 0.7rem; min-width: 0; }
.preferences-recovery-copy > i { color: var(--risk-high); margin-top: 0.1rem; }
.preferences-recovery-copy p { margin: 0 0 0.2rem; font-size: 0.85rem; }
.preferences-recovery-copy span { font-size: 0.75rem; opacity: 0.8; }
.preferences-recovery-actions { display: flex; flex-wrap: wrap; gap: 0.5rem; }
.preferences-recovery-actions button {
  cursor: pointer;
  border: 1px solid var(--card-border);
  border-radius: 8px;
  background: var(--card-bg);
  color: var(--text-color-85);
  padding: 0.45rem 0.75rem;
  font-size: 0.78rem;
}
.preferences-recovery-actions button:hover:not(:disabled) { border-color: var(--primary-color); }
.preferences-recovery-actions button:focus-visible { outline: 2px solid var(--primary-color); outline-offset: 2px; }
.preferences-recovery-actions button:disabled { cursor: not-allowed; opacity: 0.5; }

.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 6rem 2rem;
  gap: 0.75rem;
  color: var(--text-color-85);
  opacity: 0.4;
}

.empty-icon { font-size: 2.5rem; }
.empty-state p { font-size: 0.95rem; font-weight: 400; margin: 0; }
.empty-state span { font-size: 0.8rem; }

/* Card container */
.lists-card {
  background: var(--card-bg);
  border: 1px solid var(--card-border);
  border-radius: 14px;
  overflow: hidden;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.06);
}

.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem;
  flex-wrap: wrap;
  padding: 0.85rem 1.25rem;
  border-bottom: 1px solid var(--card-border);
  background: rgba(255, 255, 255, 0.02);
}

.card-header-left {
  display: flex;
  align-items: center;
  gap: 0.6rem;
  font-size: 0.78rem;
  font-weight: 400;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--text-color-85);
}

.card-header-left i {
  color: var(--primary-color);
  font-size: 1rem;
}

.card-header-right {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 0.65rem;
  flex-wrap: wrap;
  margin-left: auto;
}

.period-chip {
  display: inline-flex;
  align-items: center;
  gap: 0.38rem;
  padding: 0.24rem 0.58rem;
  border-radius: 6px;
  border: 1px solid color-mix(in srgb, var(--primary-color) 22%, transparent);
  background: color-mix(in srgb, var(--primary-color) 8%, transparent);
  color: var(--primary-color);
  font-size: 0.7rem;
  font-weight: 500;
  white-space: nowrap;
}

.period-chip i {
  font-size: 0.72rem;
}

.regional-nt-chip {
  display: inline-flex;
  align-items: center;
  gap: 0.38rem;
  padding: 0.24rem 0.58rem;
  border-radius: 6px;
  border: 1px solid color-mix(in srgb, var(--primary-color) 26%, transparent);
  background: color-mix(in srgb, var(--primary-color) 6%, transparent);
  color: var(--text-color-85);
  font-size: 0.7rem;
  font-weight: 500;
  white-space: nowrap;
  cursor: pointer;
}

.regional-nt-chip:hover {
  border-color: var(--primary-color);
  background: color-mix(in srgb, var(--primary-color) 12%, transparent);
}

.regional-nt-chip:disabled {
  cursor: not-allowed;
  opacity: 0.7;
}

.card-count {
  font-size: 0.7rem;
  font-weight: 500;
  color: var(--text-muted);
}

.card-error {
  color: var(--risk-critical);
}

.lists-content {
  overflow-x: auto;
}

.lists-table {
  width: 100%;
  min-width: 1120px;
  border-collapse: collapse;
  table-layout: fixed;
  background: transparent;
}

.lists-table th {
  padding: 0.7rem 0.9rem;
  font-size: 0.68rem;
  font-weight: 400;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--text-color-85);
  opacity: 0.8;
  background: color-mix(in srgb, var(--card-bg) 85%, var(--card-border));
  border-bottom: 1px solid var(--card-border);
  text-align: left;
  white-space: nowrap;
}

.lists-table th.col-right { text-align: right; }

.lists-table:not(.evid-table) th:nth-child(1) { width: 42px; }
.lists-table:not(.evid-table) th:nth-child(2) { width: 19%; }
.lists-table:not(.evid-table) th:nth-child(3) { width: 14%; }
.lists-table:not(.evid-table) th:nth-child(4) { width: 11%; }
.lists-table:not(.evid-table) th:nth-child(5) { width: 8%; }
.lists-table:not(.evid-table) th:nth-child(6) { width: 8%; }
.lists-table:not(.evid-table) th:nth-child(7) { width: 10%; }
.lists-table:not(.evid-table) th:nth-child(8) { width: 9%; }
.lists-table:not(.evid-table) th:nth-child(9) { width: 9%; }
.lists-table:not(.evid-table) th:nth-child(10) { width: 8%; }
.lists-table:not(.evid-table) th:nth-child(11) { width: 136px; }

.evid-table th:nth-child(1) { width: 20%; }
.evid-table th:nth-child(2) { width: 9%; }
.evid-table th:nth-child(3) { width: 12%; }
.evid-table th:nth-child(4) { width: 25%; }
.evid-table th:nth-child(5) { width: 20%; }
.evid-table th:nth-child(6) { width: 8%; }
.evid-table th:nth-child(7) { width: 96px; }

.lists-table td {
  padding: 0.7rem 0.9rem;
  font-size: 0.8rem;
  color: var(--text-color-85);
  border-bottom: 1px solid var(--card-border);
  vertical-align: middle;
}

.lists-table tbody tr:last-child td { border-bottom: none; }
.lists-table tbody tr:hover {
  background: color-mix(in srgb, var(--primary-color) 4%, transparent);
}

.clickable-row {
  cursor: pointer;
}

.clickable-row:focus-visible {
  outline: 2px solid color-mix(in srgb, var(--primary-color) 70%, transparent);
  outline-offset: -2px;
  background: color-mix(in srgb, var(--primary-color) 6%, transparent);
}

.col-num   { width: 36px; opacity: 0.4; font-weight: 400; }
.col-establishment,
.col-obs,
.col-loc {
  min-width: 0;
}

.establishment-block {
  display: flex;
  flex-direction: column;
  gap: 0.22rem;
  min-width: 0;
  overflow: hidden;
}

.establishment-name {
  display: block;
  max-width: 100%;
  font-size: 0.8rem;
  font-weight: 500;
  line-height: 1.25;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.cnpj-row {
  display: flex;
  align-items: center;
  gap: 0.3rem;
  min-width: 0;
}

.cnpj-text {
  font-size: 0.68rem;
  color: var(--text-muted);
  white-space: nowrap;
  letter-spacing: 0.01em;
}

.copy-btn {
  width: 20px;
  height: 20px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  padding: 0;
  border: none;
  border-radius: 4px;
  background: transparent;
  color: var(--text-muted);
  cursor: pointer;
  opacity: 0;
  transition: opacity 0.15s ease, color 0.15s ease, background 0.15s ease;
}

.clickable-row:hover .copy-btn,
.copy-btn:focus-visible {
  opacity: 1;
}

.copy-btn:hover,
.copy-btn:focus-visible {
  color: var(--primary-color);
  background: color-mix(in srgb, var(--primary-color) 8%, transparent);
  outline: none;
}

.copy-btn i {
  font-size: 0.68rem;
}

.obs-cell {
  display: flex;
  align-items: center;
  gap: 0.45rem;
}

.obs-content {
  display: flex;
  align-items: center;
  min-width: 0;
  flex: 1;
  font-size: 0.75rem;
  color: var(--text-color-85);
  opacity: 0.8;
  background: color-mix(in srgb, var(--primary-color) 5%, transparent);
  padding: 0.25rem 0.6rem;
  border-radius: 6px;
  border: 1px solid color-mix(in srgb, var(--primary-color) 10%, transparent);
}
.obs-text {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.obs-edit-btn {
  width: 26px;
  height: 26px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  border-radius: 6px;
  border: 1px solid color-mix(in srgb, var(--primary-color) 20%, transparent);
  background: color-mix(in srgb, var(--primary-color) 5%, transparent);
  color: var(--text-muted);
  cursor: pointer;
  opacity: 0.72;
  transition: all 0.15s ease;
}

.obs-edit-btn:hover {
  opacity: 1;
  color: var(--primary-color);
  border-color: color-mix(in srgb, var(--primary-color) 45%, transparent);
  background: color-mix(in srgb, var(--primary-color) 10%, transparent);
}

.obs-edit-btn i {
  font-size: 0.76rem;
}

.col-date  { opacity: 0.46; font-size: 0.72rem; white-space: nowrap; }
.col-right { text-align: right; }
.col-vazio { opacity: 0.3; }
.col-money { font-size: 0.78rem; white-space: nowrap; opacity: 0.75; }
.col-sem-comp { color: var(--risk-critical); opacity: 0.65; }
.col-total-mov { opacity: 0.45; font-size: 0.74rem; }

.loc-block {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 0.22rem;
  min-width: 0;
}

.municipio-text {
  display: block;
  max-width: 100%;
  font-size: 0.78rem;
  line-height: 1.2;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  opacity: 0.75;
}

.uf-tag {
  display: inline-flex;
  align-items: center;
  padding: 0.05rem 0.34rem;
  border-radius: 4px;
  background: color-mix(in srgb, var(--primary-color) 12%, transparent);
  color: var(--primary-color);
  font-size: 0.64rem;
  font-weight: 600;
}

/* Badge % Não Comprovação */
.perc-badge {
  display: inline-block;
  padding: 0.15rem 0.45rem;
  border-radius: 4px;
  font-size: 0.75rem;
  font-weight: 400;
}
.perc-alto  { background: color-mix(in srgb, #ef4444 12%, transparent); color: #ef4444; }
.perc-medio { background: color-mix(in srgb, #f59e0b 12%, transparent); color: #f59e0b; }
.perc-baixo { background: color-mix(in srgb, #10b981 12%, transparent); color: #10b981; }

/* Score de Risco */
.score-badge {
  display: inline-flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 0.18rem;
  font-size: 0.78rem;
  font-weight: 400;
}
.score-value {
  font-weight: 600;
  line-height: 1;
}
.score-class {
  font-size: 0.65rem;
  font-weight: 500;
  opacity: 0.75;
  background: color-mix(in srgb, currentColor 10%, transparent);
  padding: 0.1rem 0.3rem;
  border-radius: 3px;
}

.col-actions { width: 136px; text-align: center; }

.action-btns {
  display: flex;
  gap: 0.4rem;
  justify-content: center;
}

.action-btn {
  width: 28px;
  height: 28px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: 6px;
  border: 1px solid var(--tabs-border);
  background: color-mix(in srgb, var(--text-color-85) 3%, transparent);
  cursor: pointer;
  transition: all 0.15s ease;
  font-size: 0.72rem;
  color: var(--text-color-85);
  opacity: 0.6;
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.08);
}
.action-btn:disabled {
  cursor: wait;
  opacity: 0.45;
}
.action-btn:hover { opacity: 1; }
.action-btn.open:hover {
  border-color: var(--primary-color);
  color: var(--primary-color);
  background: color-mix(in srgb, var(--primary-color) 8%, transparent);
}
.action-btn.report {
  color: var(--primary-color);
  border-color: color-mix(in srgb, var(--primary-color) 30%, transparent);
  background: color-mix(in srgb, var(--primary-color) 8%, transparent);
}
.action-btn.report:hover {
  border-color: var(--primary-color);
  color: var(--primary-color);
  background: color-mix(in srgb, var(--primary-color) 15%, transparent);
  box-shadow: 0 4px 12px color-mix(in srgb, var(--primary-color) 25%, transparent);
}
.action-btn.note {
  --btn-note-color: #a855f7;
  color: var(--btn-note-color);
  border-color: color-mix(in srgb, var(--btn-note-color) 30%, transparent);
  background: color-mix(in srgb, var(--btn-note-color) 8%, transparent);
}
.action-btn.note:hover {
  --btn-note-color: #a855f7;
  border-color: var(--btn-note-color);
  color: var(--btn-note-color);
  background: color-mix(in srgb, var(--btn-note-color) 15%, transparent);
  box-shadow: 0 4px 12px color-mix(in srgb, var(--btn-note-color) 25%, transparent);
}
/* ── Abas ─────────────────────────────────────────────────────────────── */
.lists-tabs {
  display: flex;
  gap: 0.25rem;
  margin-bottom: -0.75rem;
}

.lists-tab {
  display: inline-flex;
  align-items: center;
  gap: 0.5rem;
  height: 38px;
  padding: 0 1rem;
  border: 1px solid transparent;
  border-radius: 8px;
  background: transparent;
  color: var(--text-muted);
  font-family: inherit;
  font-size: 0.85rem;
  font-weight: 500;
  cursor: pointer;
}

.lists-tab:hover { color: var(--text-color-85); }

.lists-tab.is-active {
  color: var(--text-color-85);
  border-color: var(--card-border);
  background: var(--card-bg);
}

.lists-tab i { font-size: 0.85rem; }
.lists-tab.is-active i { color: var(--evidence-color); }

.lists-tab-count {
  padding: 0.05rem 0.45rem;
  border-radius: 999px;
  font-size: 0.7rem;
  font-weight: 500;
  background: color-mix(in srgb, var(--text-muted) 14%, transparent);
}

/* ── Coluna Evidências (farmácias) ───────────────────────────────────── */
.evid-count-btn {
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
  padding: 0.2rem 0.5rem;
  border: 1px solid color-mix(in srgb, var(--evidence-color) 35%, transparent);
  border-radius: 6px;
  background: color-mix(in srgb, var(--evidence-color) 8%, transparent);
  color: var(--evidence-color);
  font-family: inherit;
  cursor: pointer;
  white-space: nowrap;
}

.evid-count-btn:hover,
.evid-count-btn:focus-visible {
  border-color: var(--evidence-color);
  outline: none;
}

.evid-count-btn i { font-size: 0.68rem; }
.evid-count-num { font-size: 0.8rem; font-weight: 600; }
.evid-count-date { font-size: 0.68rem; color: var(--text-muted); }

/* ── Aba Evidências ──────────────────────────────────────────────────── */
.evid-toolbar { gap: 0.75rem; }

.evid-filtro-farmacia { width: 280px; font-size: 0.78rem; }
:deep(.evid-filtro-farmacia .p-dropdown-label) { font-size: 0.78rem; padding: 0.35rem 0.6rem; }

.evid-tipos {
  display: inline-flex;
  gap: 2px;
  padding: 2px;
  border: 1px solid var(--card-border);
  border-radius: 8px;
}

.evid-tipo-btn {
  height: 28px;
  padding: 0 0.7rem;
  border: none;
  border-radius: 6px;
  background: transparent;
  color: var(--text-muted);
  font-family: inherit;
  font-size: 0.74rem;
  font-weight: 500;
  cursor: pointer;
}

.evid-tipo-btn:disabled { cursor: not-allowed; opacity: 0.5; }

.evid-tipo-btn.is-active {
  color: var(--evidence-color);
  background: color-mix(in srgb, var(--evidence-color) 12%, transparent);
}

.evid-table td { vertical-align: top; }
.evid-table tr.is-busy { opacity: 0.55; }

.evid-table .cnpj-text { display: block; margin-top: 0.15rem; }

.evid-tipo-tag {
  display: inline-flex;
  align-items: center;
  gap: 0.3rem;
  padding: 0.1rem 0.45rem;
  border-radius: 5px;
  font-size: 0.7rem;
  font-weight: 500;
  color: var(--text-color-85);
  background: color-mix(in srgb, var(--text-muted) 12%, transparent);
  white-space: nowrap;
}

.evid-tipo-tag i { font-size: 0.68rem; color: var(--text-muted); }

.evid-quando { white-space: nowrap; font-weight: 500; }

.evid-resumo {
  font-size: 0.76rem;
  line-height: 1.45;
}

.evid-nota {
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
  font-size: 0.76rem;
  line-height: 1.45;
  white-space: pre-wrap;
}

.evid-confirma {
  display: flex;
  justify-content: center;
  gap: 0.4rem;
}

.action-btn.remove.is-confirm {
  color: var(--risk-critical);
  border-color: var(--risk-critical);
  opacity: 1;
}

.evid-retry-btn {
  margin-top: 0.5rem;
  height: 30px;
  padding: 0 0.9rem;
  border: 1px solid var(--card-border);
  border-radius: 7px;
  background: var(--card-bg);
  color: var(--text-color-85);
  font-family: inherit;
  font-size: 0.78rem;
  cursor: pointer;
}

.evid-error { opacity: 1; }
.evid-error .empty-icon { color: var(--risk-critical); }

.action-btn.remove:hover {
  border-color: var(--risk-critical);
  color: var(--risk-critical);
  background: color-mix(in srgb, var(--risk-critical) 8%, transparent);
}
</style>
