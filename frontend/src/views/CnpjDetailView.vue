<script setup>
import { useRoute, useRouter } from "vue-router";
import { computed, onMounted, ref, watch } from "vue";
import { useAnalyticsStore } from "@/stores/analytics";
import { useCnpjDetailStore } from "@/stores/cnpjDetail";
import { useGeoStore } from "@/stores/geo";
import { useFilterStore } from "@/stores/filters";
import { useCnpjNavStore } from "@/stores/cnpjNav";
import { useRecentCnpjStore } from "@/stores/recentCnpj";
import { useNotaTecnicaConfigStore } from "@/stores/notaTecnicaConfig";
import { useFormatting } from "@/composables/useFormatting";
import { useFilterParameters } from "@/composables/useFilterParameters";
import CnpjHeader from "./components/cnpj/CnpjHeader.vue";
import EvidenciasPanel from "./components/evidencias/EvidenciasPanel.vue";
import { useEvidenciasStore } from "@/stores/evidencias";
import FinancialMovementTab from "./components/cnpj/FinancialMovementTab.vue";
import IndicatorsTab from "./components/cnpj/IndicatorsTab.vue";
import RegionalTab from "./components/cnpj/RegionalTab.vue";
import AuthTab from "./components/cnpj/AuthTab.vue";
import CalculationMemoryTab from "./components/cnpj/CalculationMemoryTab.vue";
import RiskDiagnosisTab from "./components/cnpj/RiskDiagnosisTab.vue";
import SociosTab from "./components/cnpj/SociosTab.vue";
import NetworkTab from "./components/cnpj/NetworkTab.vue";
import CnpjTabLoadingOverlay from "./components/cnpj/CnpjTabLoadingOverlay.vue";
import NotaTecnicaRegionalDialog from "./components/nota-tecnica/NotaTecnicaRegionalDialog.vue";
import { storeToRefs } from "pinia";
import TabView from "primevue/tabview";
import TabPanel from "primevue/tabpanel";
import { useToast } from "primevue/usetoast";
import { API_ENDPOINTS } from "@/config/api";
import { getApiErrorMessage } from "@/utils/apiErrors";
import { convertDocxToPdf, downloadBlobFromResponse } from "@/utils/download";
import { createCnpjPerfSession, logCnpjPerf } from "@/utils/cnpjPerfLogger";

// ── Índices das abas (evita números mágicos no template) ──
const TAB_INDEX = {
  EVOLUTION: 0,
  DIAGNOSIS: 1,
  MOVEMENT: 2,
  INDICATORS: 3,
  CRMS: 4,
  SOCIOS: 5,
  NETWORK: 6,
  REGIONAL: 7,
};

const TAB_SLUG_BY_INDEX = {
  [TAB_INDEX.EVOLUTION]: "movimentacao",
  [TAB_INDEX.DIAGNOSIS]: "diagnostico",
  [TAB_INDEX.MOVEMENT]: "memoria",
  [TAB_INDEX.INDICATORS]: "indicadores",
  [TAB_INDEX.CRMS]: "autorizacoes",
  [TAB_INDEX.SOCIOS]: "socios",
  [TAB_INDEX.NETWORK]: "teia",
  [TAB_INDEX.REGIONAL]: "regional",
};

const TAB_INDEX_BY_SLUG = Object.fromEntries(
  Object.entries(TAB_SLUG_BY_INDEX).map(([index, slug]) => [slug, Number(index)]),
);

const route = useRoute();
const router = useRouter();
const normalizeCnpj = (value) => String(value ?? "").replace(/\D/g, "");
const cnpj = computed(() => normalizeCnpj(route.params.cnpj));

const getTabIndexFromRoute = () => {
  const sectionParam = Array.isArray(route.query.s)
    ? route.query.s[0]
    : route.query.s;
  const legacyTabParam = Array.isArray(route.query.tab)
    ? route.query.tab[0]
    : route.query.tab;
  const routeSlug = String(sectionParam ?? legacyTabParam ?? "").toLowerCase();
  if (routeSlug === "falecidos") {
    cnpjDetailStore.setCrmViewMode("falecidos");
    return TAB_INDEX.CRMS;
  }
  const tabIndex = TAB_INDEX_BY_SLUG[
    routeSlug
  ];
  return Number.isInteger(tabIndex) ? tabIndex : TAB_INDEX.EVOLUTION;
};

// ── Stores ────────────────────────────────────────────────
const analyticsStore = useAnalyticsStore();
const cnpjDetailStore = useCnpjDetailStore();
const { resultadoCnpjs } = storeToRefs(analyticsStore);
const {
  dadosCadastro,
  evolucaoFinanceira,
  evolucaoLoading,
  evolucaoLoaded,
  bootstrapLoading,
  bootstrapGeoData,
  bootstrapPeriodSummary,
  integrityAlertsData,
  integrityAlertsLoading,
  integrityAlertsError,
  notaTecnicaReadinessData,
  notaTecnicaReadinessLoading,
  notaTecnicaReadinessError,
  notaTecnicaPreparing,
  relatorioPdfReadinessData,
  relatorioPdfReadinessLoading,
  relatorioPdfReadinessError,
  relatorioPdfPreparing,
} =
  storeToRefs(cnpjDetailStore);

const geoStore = useGeoStore();
const { localidades } = storeToRefs(geoStore);

const filterStore = useFilterStore();
const cnpjNav = useCnpjNavStore();
const evidenciasStore = useEvidenciasStore();
const notaTecnicaConfig = useNotaTecnicaConfigStore();
const visitedTabIndexes = ref(new Set([cnpjNav.activeTabIndex]));

const hasVisitedTab = (index) => visitedTabIndexes.value.has(index);

const markTabVisited = (index) => {
  if (!Number.isInteger(index) || visitedTabIndexes.value.has(index)) return;
  visitedTabIndexes.value = new Set([...visitedTabIndexes.value, index]);
};

const resetVisitedTabs = (activeIndex = cnpjNav.activeTabIndex) => {
  visitedTabIndexes.value = new Set([activeIndex]);
};

const tabLoadingByIndex = computed(() => ({
  [TAB_INDEX.EVOLUTION]:
    cnpjDetailStore.evolucaoLoading ||
    cnpjDetailStore.evolucaoMensalGtinLoading ||
    cnpjDetailStore.repassesLoading ||
    cnpjDetailStore.gtinDetalhamentoMensalLoading,
  [TAB_INDEX.DIAGNOSIS]: cnpjDetailStore.metricPercentilesLoading,
  [TAB_INDEX.MOVEMENT]: cnpjDetailStore.movimentacaoLoading,
  [TAB_INDEX.INDICATORS]: cnpjDetailStore.indicadoresLoading,
  [TAB_INDEX.CRMS]:
    cnpjDetailStore.prescritoresLoading ||
    cnpjDetailStore.crmTimelineDatasetLoading ||
    cnpjDetailStore.falecidosLoading,
  [TAB_INDEX.SOCIOS]: cnpjDetailStore.sociosLoading,
  [TAB_INDEX.NETWORK]:
    cnpjDetailStore.networkLoading ||
    Object.values(cnpjDetailStore.networkLevelLoading ?? {}).some(Boolean),
  [TAB_INDEX.REGIONAL]:
    cnpjDetailStore.municipiosRegiaoLoading ||
    cnpjDetailStore.metricPercentilesLoading,
}));

const showTabLoadingOverlay = (index) =>
  !isInitialLoading.value &&
  cnpjNav.activeTabIndex === index &&
  Boolean(tabLoadingByIndex.value[index]);

// ── Composables ───────────────────────────────────────────
const { getApiParams } = useFilterParameters();
const { formatCurrencyFull, formatNumberFull, formatarData, formatTitleCase } = useFormatting();
const toast = useToast();

import { usePdfExport } from "@/composables/usePdfExport";
import { loadCnpjPdfReportData } from "@/composables/useCnpjPdfReportData";
const { isExporting, exportCnpjPdf } = usePdfExport();

const financialMovementTabRef = ref(null);
const indicatorsTabRef = ref(null);
const authTabRef = ref(null);
const falecidosTabRef = computed(() => ({
  hasData: () => authTabRef.value?.hasFalecidosData?.() ?? false,
  getSummary: () => authTabRef.value?.getFalecidosSummary?.() ?? null,
  getAgrupados: () => authTabRef.value?.getFalecidosAgrupados?.() ?? [],
  getRanking: () => authTabRef.value?.getFalecidosRanking?.() ?? [],
}));

const qtdMunicipiosRegiao = computed(
  () =>
    cnpjDetailStore.bootstrapData?.qtd_municipios_regiao ??
    geoStore.qtdMunicipiosPorRegiao?.(geoData.value?.id_regiao_saude) ??
    null,
);

const formatMissingModules = (readiness) =>
  (readiness?.missing_modules ?? [])
    .map((module) => module.label)
    .filter(Boolean);

const ensureRelatorioPdfReady = async () => {
  const { inicio, fim } = getApiParams();
  let readiness = await cnpjDetailStore.fetchRelatorioPdfReadiness(cnpj.value, inicio, fim);
  if (readiness?.ready === true) return true;

  if (readiness?.preparable === true) {
    toast.add({
      severity: "info",
      summary: "Preparando Relatório PDF",
      detail: "Preparando dados do estabelecimento para geração do Relatório PDF.",
      life: 3500,
    });
    try {
      await cnpjDetailStore.prepareRelatorioPdf(cnpj.value, inicio, fim);
    } catch (error) {
      toast.add({
        severity: "warn",
        summary: "Preparação do Relatório PDF indisponível",
        detail: error?.message || cnpjDetailStore.relatorioPdfPrepareError || "Não foi possível preparar os dados do Relatório PDF.",
        life: 12000,
      });
      return false;
    }
    readiness = await cnpjDetailStore.fetchRelatorioPdfReadiness(cnpj.value, inicio, fim, { force: true });
    if (readiness?.ready === true) return true;
  }

  const missingLabels = formatMissingModules(readiness);
  toast.add({
    severity: "warn",
    summary: "Relatório PDF indisponível",
    detail: missingLabels.length
      ? `Módulos pendentes: ${missingLabels.join(", ")}.`
      : cnpjDetailStore.relatorioPdfReadinessError || "Não foi possível verificar os módulos do Relatório PDF.",
    life: 8000,
  });
  return false;
};

const handleExport = async () => {
  try {
    if (!(await ensureRelatorioPdfReady())) {
      return;
    }

    const { inicio, fim, volumeAtipicoPercentual } = getApiParams();
    const payload = await loadCnpjPdfReportData({
      cnpj: cnpj.value,
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
  }
};
const isGeneratingNote = ref(false);
const regionalDialogVisible = ref(false);
const pendingNoteGeneration = ref(false);

const buildNotaTecnicaUrl = (dadosNota = {}) => {
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
  return `${API_ENDPOINTS.analyticsNotaTecnica(cnpj.value)}?${params.toString()}`;
};

const downloadNotaTecnica = async (dadosNota = {}) => {
  isGeneratingNote.value = true;
  try {
    const url = buildNotaTecnicaUrl(dadosNota);

    // Baixa o arquivo como blob para não sair da página
    const response = await fetch(url);
    if (!response.ok) {
      throw new Error(
        await getApiErrorMessage(response, "Erro ao gerar nota técnica"),
      );
    }

    const downloadResult = await downloadBlobFromResponse(response, `Nota_Tecnica_${cnpj.value}.docx`);
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
  } finally {
    isGeneratingNote.value = false;
  }
};

const ensureNotaTecnicaReady = async () => {
  const { inicio, fim } = getApiParams();
  let readiness = await cnpjDetailStore.fetchNotaTecnicaReadiness(cnpj.value, inicio, fim);
  if (readiness?.ready === true) return true;

  if (readiness?.preparable === true) {
    toast.add({
      severity: "info",
      summary: "Preparando Nota Técnica",
      detail: "Preparando dados do estabelecimento para geração da Nota Técnica.",
      life: 3500,
    });
    try {
      await cnpjDetailStore.prepareNotaTecnica(cnpj.value, inicio, fim);
    } catch (error) {
      toast.add({
        severity: "warn",
        summary: "Preparação da Nota Técnica indisponível",
        detail: error?.message || cnpjDetailStore.notaTecnicaPrepareError || "Não foi possível preparar os dados da Nota Técnica.",
        life: 12000,
      });
      return false;
    }
    readiness = await cnpjDetailStore.fetchNotaTecnicaReadiness(cnpj.value, inicio, fim, { force: true });
    if (readiness?.ready === true) return true;
  }

  const missingLabels = formatMissingModules(readiness);
  toast.add({
    severity: "warn",
    summary: "Nota Técnica indisponível",
    detail: missingLabels.length
      ? `Módulos pendentes: ${missingLabels.join(", ")}.`
      : cnpjDetailStore.notaTecnicaReadinessError || "Não foi possível verificar os módulos da Nota Técnica.",
    life: 8000,
  });
  return false;
};

const handleGenerateNote = async ({ skipRegionalCheck = false, dadosNota = {} } = {}) => {
  try {
    if (!skipRegionalCheck && !(await ensureNotaTecnicaReady())) {
      return;
    }

    if (!skipRegionalCheck) {
      await notaTecnicaConfig.ensureLoaded();
      pendingNoteGeneration.value = true;
      regionalDialogVisible.value = true;
      return;
    }

    await downloadNotaTecnica(dadosNota);
  } catch (error) {
    console.error("Erro ao gerar Nota Técnica:", error);
    toast.add({
      severity: "error",
      summary: "Erro ao gerar Nota Técnica",
      detail: error?.message || "Não foi possível gerar o arquivo.",
      life: 8000,
    });
  }
};

const handleRegionalSaved = async (dadosNota) => {
  if (!pendingNoteGeneration.value) return;
  pendingNoteGeneration.value = false;
  await handleGenerateNote({ skipRegionalCheck: true, dadosNota });
};

const setRegionalDialogVisible = (visible) => {
  regionalDialogVisible.value = visible;
  if (!visible) pendingNoteGeneration.value = false;
};
// ── Composables (Fim) ─────────────────────────────────────

// ── Dados do CNPJ ─────────────────────────────────────────
const setActiveTab = (index, { syncUrl = true } = {}) => {
  cnpjNav.activeTabIndex = index;
  markTabVisited(index);
  if (cnpjDetailStore.cnpjAccessStatus === "valid") {
    queueMicrotask(() => loadActiveTabData(activePerfSession.value, "tab_change"));
  }

  if (!syncUrl) return;

  const tabSlug = TAB_SLUG_BY_INDEX[index];
  if (!tabSlug || (route.query.s === tabSlug && route.query.tab == null)) return;

  const { tab: _legacyTab, ...query } = route.query;
  router.replace({
    name: route.name,
    params: route.params,
    query: { ...query, s: tabSlug },
  });
};

const navigateToSection = (slug) => {
  const tabIndex = TAB_INDEX_BY_SLUG[slug];
  if (!Number.isInteger(tabIndex)) {
    throw new Error(`Aba de destino invalida para alerta de integridade: ${slug}`);
  }
  setActiveTab(tabIndex);
};

watch(
  () => [route.query.s, route.query.tab],
  () => {
    const routeTabIndex = getTabIndexFromRoute();
    if (cnpjNav.activeTabIndex !== routeTabIndex) {
      setActiveTab(routeTabIndex, { syncUrl: false });
    }
  },
  { immediate: true },
);

const cnpjData = computed(
  () =>
    cnpjDetailStore.cnpjsAvulsos.get(cnpj.value) ??
    resultadoCnpjs.value?.find((c) => c.cnpj === cnpj.value) ??
    null,
);

const isPeriodSummaryLoading = computed(() => bootstrapLoading.value || evolucaoLoading.value);

// O bootstrap é a fonte canônica dos KPIs do período exibidos no header.
// A evolução financeira pode estar stale se outra aba estiver ativa.
const periodSummary = computed(() => {
  if (bootstrapPeriodSummary.value) {
    return bootstrapPeriodSummary.value;
  }

  const semestres = evolucaoFinanceira.value?.semestres;
  if (!semestres?.length) {
    return evolucaoLoaded.value ? { totalMov: 0, valSemComp: 0, percValSemComp: 0 } : null;
  }
  const totalMov = semestres.reduce((a, s) => a + s.total, 0);
  const valSemComp = semestres.reduce((a, s) => a + s.irregular, 0);
  const percValSemComp = totalMov > 0 ? (valSemComp / totalMov) * 100 : 0;
  return { totalMov, valSemComp, percValSemComp };
});

const hasCnpjAccessIssue = computed(() =>
  ["invalid_format", "not_in_program", "error"].includes(
    cnpjDetailStore.cnpjAccessStatus,
  ),
);

const canRenderDetail = computed(
  () => cnpjDetailStore.cnpjAccessStatus === "valid",
);

const accessState = computed(() => {
  const status = cnpjDetailStore.cnpjAccessStatus;
  if (status === "invalid_format") {
    return {
      icon: "pi pi-id-card",
      badge: "Formato invalido",
      title: "Identificador invalido",
      description: "A rota recebeu um identificador que nao possui 14 digitos. A tela de estabelecimento aceita apenas CNPJ completo.",
      severity: "warning",
    };
  }
  if (status === "not_in_program") {
    return {
      icon: "pi pi-search",
      badge: "Fora da base PFPB",
      title: "CNPJ nao encontrado no Farmacia Popular",
      description: "O CNPJ informado tem formato valido, mas nao consta na base carregada do Programa Farmacia Popular.",
      severity: "warning",
    };
  }
  return {
    icon: "pi pi-exclamation-triangle",
    badge: "Servico indisponivel",
    title: "Validacao indisponivel",
    description: "Nao foi possivel consultar a base de estabelecimentos neste momento.",
    severity: "error",
  };
});

const goToEstablishments = () => {
  router.push("/estabelecimentos");
};

let cnpjValidationRequest = 0;
const activePerfSession = ref(null);

const loadActiveTabData = async (perfSession, reason = "active_tab") => {
  if (!cnpj.value || cnpjDetailStore.cnpjAccessStatus !== "valid") return;

  const { inicio, fim, volumeAtipicoPercentual } = getApiParams();
  const tabSlug = TAB_SLUG_BY_INDEX[cnpjNav.activeTabIndex];
  if (!tabSlug) return;

  logCnpjPerf(perfSession, "tab_fetch_dispatched", {
    reason,
    tab: tabSlug,
    inicio,
    fim,
  });

  try {
    await cnpjDetailStore.ensureTabData(
      tabSlug,
      cnpj.value,
      inicio,
      fim,
      volumeAtipicoPercentual,
    );
    logCnpjPerf(perfSession, "tab_fetch_settled", {
      reason,
      tab: tabSlug,
      status: "fulfilled",
    });
  } catch (error) {
    logCnpjPerf(perfSession, "tab_fetch_settled", {
      reason,
      tab: tabSlug,
      status: "rejected",
    });
  }
};

watch(
  () => cnpj.value,
  async (newCnpj, oldCnpj) => {
    // Ao trocar de CNPJ, reseta tudo e carrega bootstrap + aba ativa.
    if (newCnpj !== oldCnpj) {
      cnpjDetailStore.resetAll();
      cnpjNav.reset(getTabIndexFromRoute());
      resetVisitedTabs(cnpjNav.activeTabIndex);
      evidenciasStore.painelAberto = false;
      // Navegação vinda da cesta de evidências (Listas): aplicada depois do reset.
      evidenciasStore.consumirNavegacaoPendente(newCnpj);
    }
    const requestId = ++cnpjValidationRequest;
    if (!newCnpj) {
      cnpjDetailStore.setInvalidCnpjFormat(newCnpj);
      return;
    }

    const perfSession = createCnpjPerfSession(newCnpj);
    activePerfSession.value = perfSession;
    logCnpjPerf(perfSession, "bootstrap_started");

    const { inicio, fim, volumeAtipicoPercentual } = getApiParams();
    let access = null;
    try {
      const bootstrap = await cnpjDetailStore.fetchBootstrap(newCnpj, inicio, fim);
      access = bootstrap?.status;
    } catch (error) {
      access = { status: cnpjDetailStore.cnpjAccessStatus };
    }
    if (requestId !== cnpjValidationRequest || cnpj.value !== newCnpj) return;
    logCnpjPerf(perfSession, "bootstrap_finished", {
      status: access?.status ?? "unknown",
    });
    if (access?.status !== "valid") return;

    if (newCnpj) {
      await Promise.all([
        cnpjDetailStore.fetchIntegrityAlerts(newCnpj, inicio, fim, volumeAtipicoPercentual),
        cnpjDetailStore.fetchNotaTecnicaReadiness(newCnpj, inicio, fim),
        cnpjDetailStore.fetchRelatorioPdfReadiness(newCnpj, inicio, fim),
        loadActiveTabData(perfSession, "initial"),
      ]);
    }
  },
  { immediate: true },
);

watch(
  () => cnpjNav.activeTabIndex,
  (index) => markTabVisited(index),
  { immediate: true },
);

// Re-fetch quando o período de análise muda
watch(
  () => [
    filterStore.periodo,
    filterStore.volumeAtipicoEnabled,
    filterStore.volumeAtipicoPercentualFilter,
  ],
  () => {
    if (!cnpj.value) return;
    if (cnpjDetailStore.cnpjAccessStatus !== "valid") return;
    if (filterStore.isAnimating) return;
    const { inicio, fim, volumeAtipicoPercentual } = getApiParams();
    const perfSession = activePerfSession.value;
    logCnpjPerf(perfSession, "period_bootstrap_dispatched", {
      inicio,
      fim,
    });
    cnpjDetailStore.fetchBootstrap(cnpj.value, inicio, fim)
      .then(() => Promise.all([
        cnpjDetailStore.fetchIntegrityAlerts(
          cnpj.value,
          inicio,
          fim,
          volumeAtipicoPercentual,
        ),
        cnpjDetailStore.fetchNotaTecnicaReadiness(cnpj.value, inicio, fim),
        cnpjDetailStore.fetchRelatorioPdfReadiness(cnpj.value, inicio, fim),
      ]))
      .then(() => loadActiveTabData(perfSession, "period_change"))
      .then(() => {
        if (activePerfSession.value?.sessionId !== perfSession?.sessionId) return;
        logCnpjPerf(perfSession, "period_bootstrap_settled", {
          status: "fulfilled",
        });
      })
      .catch(() => {
        if (activePerfSession.value?.sessionId !== perfSession?.sessionId) return;
        logCnpjPerf(perfSession, "period_bootstrap_settled", {
          status: "rejected",
        });
      });
    return;
  },
  { deep: true },
);

const recentCnpjStore = useRecentCnpjStore();

// Registra o CNPJ atual como recente assim que os dados estiverem disponíveis
watch(
  cnpjData,
  (data) => {
    if (data?.razao_social) {
      recentCnpjStore.set(cnpj.value, data.razao_social);
    }
  },
  { immediate: true },
);

onMounted(() => {
  // Movimentação Financeira agora é carregada de forma autônoma pelo componente filho
  notaTecnicaConfig.ensureLoaded().catch((error) => {
    toast.add({
      severity: "warn",
      summary: "Regional da Nota Técnica",
      detail: error?.message || "Não foi possível carregar a configuração da Nota Técnica.",
      life: 6000,
    });
  });
});

const geoData = computed(() => {
  if (bootstrapGeoData.value) return bootstrapGeoData.value;

  const data = cnpjData.value;
  if (!data || !localidades.value?.length) return null;

  if (!data.id_ibge7) return null;
  return localidades.value.find((l) => String(l.id_ibge7) === String(data.id_ibge7)) ?? null;
});

const formatCnpj = (v) => {
  if (!v) return "—";
  const clean = v.replace(/\D/g, "");
  if (clean.length !== 14) return v;
  return clean.replace(
    /^(\d{2})(\d{3})(\d{3})(\d{4})(\d{2})$/,
    "$1.$2.$3/$4-$5",
  );
};

// ── Controle de Carregamento Global ───────────────────────
const isInitialLoading = computed(() => {
  const hasBootstrap = Boolean(cnpjDetailStore.bootstrapData);
  return (
    (cnpjDetailStore.cnpjAccessStatus === "checking" && !hasBootstrap) ||
    (cnpjDetailStore.bootstrapLoading && !hasBootstrap)
  );
});

watch(
  isInitialLoading,
  (loading, wasLoading) => {
    if (wasLoading && !loading) {
      logCnpjPerf(activePerfSession.value, "initial_overlay_hidden", {
        active_tab: TAB_SLUG_BY_INDEX[cnpjNav.activeTabIndex],
      });
    }
  },
);
</script>

<template>
  <div class="cnpj-detail-page">
    <!-- OVERLAY DE CARREGAMENTO GLOBAL -->
    <Transition name="fade-blur">
      <div v-if="isInitialLoading" class="global-loading-overlay">
        <div class="loader-content">
          <i class="pi pi-spin pi-spinner" aria-hidden="true" />
          <span>Carregando estabelecimento...</span>
        </div>
      </div>
    </Transition>

    <section
      v-if="hasCnpjAccessIssue"
      class="cnpj-access-state"
      :class="`cnpj-access-state--${accessState.severity}`"
    >
      <div class="access-state-glow" />
      <div class="access-state-icon">
        <i :class="accessState.icon" />
      </div>
      <div class="access-state-copy">
        <div class="access-state-meta">
          <p class="access-state-kicker">Consulta de estabelecimento</p>
          <span class="access-state-badge">{{ accessState.badge }}</span>
        </div>
        <h2>{{ accessState.title }}</h2>
        <p>{{ accessState.description }}</p>
        <div v-if="cnpjDetailStore.cnpjAccessCnpj" class="access-state-query">
          <span>CNPJ pesquisado</span>
          <strong>{{ formatCnpj(cnpjDetailStore.cnpjAccessCnpj) }}</strong>
        </div>
      </div>
      <button class="access-state-action" type="button" @click="goToEstablishments">
        <i class="pi pi-arrow-left" />
        <span>Voltar para estabelecimentos</span>
      </button>
    </section>

    <EvidenciasPanel
      v-if="canRenderDetail"
      :cnpj="cnpj"
      :razao-social="cnpjData?.razao_social || ''"
    />

    <!-- HEADER (COMPONENTE ISOLADO) -->
    <CnpjHeader
      v-if="canRenderDetail"
      :cnpj="cnpj"
      :cnpj-data="cnpjData"
      :geo-data="geoData"
      :qtd-municipios-regiao="qtdMunicipiosRegiao"
      :cadastro="dadosCadastro"
      :is-exporting="isExporting"
      :is-preparing-pdf="relatorioPdfPreparing"
      :is-generating-note="isGeneratingNote"
      :is-preparing-note="notaTecnicaPreparing"
      :period-summary="periodSummary"
      :period-loading="isPeriodSummaryLoading"
      :integrity-alerts="integrityAlertsData"
      :integrity-alerts-loading="integrityAlertsLoading"
      :integrity-alerts-error="integrityAlertsError"
      :note-readiness="notaTecnicaReadinessData"
      :note-readiness-loading="notaTecnicaReadinessLoading"
      :note-readiness-error="notaTecnicaReadinessError"
      :pdf-readiness="relatorioPdfReadinessData"
      :pdf-readiness-loading="relatorioPdfReadinessLoading"
      :pdf-readiness-error="relatorioPdfReadinessError"
      @export="handleExport"
      @generate-note="handleGenerateNote"
      @navigate-section="navigateToSection"
    />

    <NotaTecnicaRegionalDialog
      :visible="regionalDialogVisible"
      :continue-label="pendingNoteGeneration ? 'Gerar Nota Técnica' : 'Salvar dados'"
      @update:visible="setRegionalDialogVisible"
      @saved="handleRegionalSaved"
    />

    <!-- TABS -->
    <TabView
      v-if="canRenderDetail"
      class="detail-tabs"
      :activeIndex="cnpjNav.activeTabIndex"
      @tab-change="setActiveTab($event.index)"
    >
      <TabPanel>
        <template #header
          ><i class="pi pi-chart-line tab-icon" /><span
            >Movimentação Financeira</span
          ></template
        >
        <div class="cnpj-tab-panel">
          <FinancialMovementTab
            v-if="hasVisitedTab(TAB_INDEX.EVOLUTION)"
            ref="financialMovementTabRef"
            class="tab-content detail-tab-enter"
          />
          <CnpjTabLoadingOverlay :visible="showTabLoadingOverlay(TAB_INDEX.EVOLUTION)" />
        </div>
      </TabPanel>

      <TabPanel>
        <template #header
          ><i class="pi pi-chart-bar tab-icon" /><span
            >Diagnóstico de Risco</span
          ></template
        >
        <div class="cnpj-tab-panel">
          <RiskDiagnosisTab
            v-if="hasVisitedTab(TAB_INDEX.DIAGNOSIS)"
            :cnpj="cnpj"
            :cnpj-data="cnpjData"
            :geo-data="geoData"
            :period-summary="periodSummary"
            :period-loading="isPeriodSummaryLoading"
            :is-active="cnpjNav.activeTabIndex === TAB_INDEX.DIAGNOSIS"
            class="tab-content detail-tab-enter"
          />
          <CnpjTabLoadingOverlay :visible="showTabLoadingOverlay(TAB_INDEX.DIAGNOSIS)" />
        </div>
      </TabPanel>

      <TabPanel>
        <template #header
          ><i class="pi pi-list tab-icon" /><span
            >Memória de Cálculo</span
          ></template
        >
        <div class="cnpj-tab-panel">
          <CalculationMemoryTab
            v-if="hasVisitedTab(TAB_INDEX.MOVEMENT)"
            :cnpj="cnpj"
            :period-summary="periodSummary"
            :period-loading="isPeriodSummaryLoading"
            class="tab-content detail-tab-enter"
          />
          <CnpjTabLoadingOverlay :visible="showTabLoadingOverlay(TAB_INDEX.MOVEMENT)" />
        </div>
      </TabPanel>

      <TabPanel>
        <template #header
          ><i class="pi pi-shield tab-icon" /><span>Indicadores</span></template
        >
        <div class="cnpj-tab-panel">
          <IndicatorsTab
            v-if="hasVisitedTab(TAB_INDEX.INDICATORS)"
            ref="indicatorsTabRef"
            class="tab-content detail-tab-enter"
          />
          <CnpjTabLoadingOverlay :visible="showTabLoadingOverlay(TAB_INDEX.INDICATORS)" />
        </div>
      </TabPanel>

      <TabPanel>
        <template #header
          ><i class="pi pi-id-card tab-icon" /><span
            >Análise de Autorizações</span
          ></template
        >
        <div class="cnpj-tab-panel">
          <AuthTab
            v-if="hasVisitedTab(TAB_INDEX.CRMS)"
            ref="authTabRef"
            :cnpj="cnpj"
            :is-active="cnpjNav.activeTabIndex === TAB_INDEX.CRMS"
            :razao-social="cnpjData?.razao_social || ''"
            :period-summary="periodSummary"
            :period-loading="isPeriodSummaryLoading"
            class="tab-content detail-tab-enter"
          />
          <CnpjTabLoadingOverlay :visible="showTabLoadingOverlay(TAB_INDEX.CRMS)" />
        </div>
      </TabPanel>

      <TabPanel>
        <template #header
          ><i class="pi pi-users tab-icon" /><span
            >Quadro Societário</span
          ></template
        >
        <div class="cnpj-tab-panel">
          <SociosTab
            v-if="hasVisitedTab(TAB_INDEX.SOCIOS)"
            class="tab-content detail-tab-enter"
          />
          <CnpjTabLoadingOverlay :visible="showTabLoadingOverlay(TAB_INDEX.SOCIOS)" />
        </div>
      </TabPanel>

      <TabPanel>
        <template #header>
          <i class="pi pi-share-alt tab-icon" /><span>Teia Societária</span>
        </template>
        <div class="cnpj-tab-panel">
          <NetworkTab
            v-if="hasVisitedTab(TAB_INDEX.NETWORK)"
            class="tab-content detail-tab-enter"
          />
          <CnpjTabLoadingOverlay :visible="showTabLoadingOverlay(TAB_INDEX.NETWORK)" />
        </div>
      </TabPanel>

      <TabPanel>
        <template #header>
          <i class="pi pi-map tab-icon" /><span>Região de Saúde</span>
        </template>
        <div class="cnpj-tab-panel">
          <RegionalTab
            v-if="hasVisitedTab(TAB_INDEX.REGIONAL)"
            :cnpj="cnpj"
            :geo-data="geoData"
            :cnpj-data="cnpjData"
            :is-active="cnpjNav.activeTabIndex === TAB_INDEX.REGIONAL"
            class="tab-content detail-tab-enter"
          />
          <CnpjTabLoadingOverlay :visible="showTabLoadingOverlay(TAB_INDEX.REGIONAL)" />
        </div>
      </TabPanel>
    </TabView>
  </div>
</template>

<style scoped>
.cnpj-detail-page {
  display: flex;
  flex-direction: column;
  height: 100%;
  overflow-y: auto;
  position: relative; /* Referência para o overlay de loading */
  gap: 0;
  background: transparent;
}

.cnpj-tab-panel {
  position: relative;
  min-height: 18rem;
  height: 100%;
  display: flex;
  flex-direction: column;
}

.cnpj-tab-panel > :deep(.tab-content) {
  flex: 1;
  min-height: 0;
}

/* Estado de acesso da rota do estabelecimento */
.cnpj-access-state {
  --access-accent: var(--primary-color);
  --access-accent-strong: var(--primary-color);
  --access-glass-highlight: color-mix(in srgb, var(--text-color-85) 6%, transparent);
  --access-soft-shadow: color-mix(in srgb, var(--text-color-85) 8%, transparent);
  min-height: 22rem;
  margin: 1rem 0 2rem;
  padding: 3rem 3.5rem;
  border: 1px solid color-mix(in srgb, var(--tabs-border) 72%, var(--text-color-85) 8%);
  border-radius: 14px;
  background:
    linear-gradient(
      135deg,
      color-mix(in srgb, var(--card-bg) 94%, var(--primary-color) 2%),
      color-mix(in srgb, var(--card-bg) 96%, transparent)
    );
  backdrop-filter: blur(8px);
  -webkit-backdrop-filter: blur(8px);
  box-shadow:
    0 12px 34px var(--access-soft-shadow),
    inset 0 1px 0 var(--access-glass-highlight);
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto;
  align-items: center;
  gap: 2rem;
  overflow: hidden;
  position: relative;
  isolation: isolate;
}

.access-state-glow {
  position: absolute;
  inset: -35% auto auto -8%;
  width: 22rem;
  height: 22rem;
  border-radius: 999px;
  background: radial-gradient(
    circle,
    color-mix(in srgb, var(--primary-color) 8%, transparent) 0%,
    transparent 66%
  );
  opacity: 0.45;
  pointer-events: none;
  z-index: -1;
}

.cnpj-access-state--warning {
  --access-accent: var(--amber-500);
  --access-accent-strong: color-mix(in srgb, var(--amber-500) 78%, var(--text-color-85));
}

.cnpj-access-state--error {
  --access-accent: var(--color-error);
  --access-accent-strong: color-mix(in srgb, var(--color-error) 82%, var(--text-color-85));
}

.access-state-icon {
  width: 4.5rem;
  height: 4.5rem;
  border-radius: 14px;
  display: grid;
  place-items: center;
  background:
    linear-gradient(
      145deg,
      color-mix(in srgb, var(--access-accent) 11%, var(--card-bg)),
      color-mix(in srgb, var(--access-accent) 4%, transparent)
    );
  border: 1px solid color-mix(in srgb, var(--access-accent) 20%, var(--tabs-border));
  color: var(--access-accent-strong);
  font-size: 1.75rem;
  box-shadow: inset 0 1px 0 var(--access-glass-highlight);
}

.cnpj-access-state--warning .access-state-icon {
  --access-accent: var(--amber-500);
  --access-accent-strong: color-mix(in srgb, var(--amber-500) 78%, var(--text-color-85));
  background:
    linear-gradient(
      145deg,
      color-mix(in srgb, var(--access-accent) 11%, var(--card-bg)),
      color-mix(in srgb, var(--access-accent) 4%, transparent)
    );
  border-color: color-mix(in srgb, var(--access-accent) 22%, var(--tabs-border));
  color: var(--access-accent-strong);
}

.cnpj-access-state--error .access-state-icon {
  --access-accent: var(--color-error);
  --access-accent-strong: color-mix(in srgb, var(--color-error) 82%, var(--text-color-85));
  background:
    linear-gradient(
      145deg,
      color-mix(in srgb, var(--access-accent) 11%, var(--card-bg)),
      color-mix(in srgb, var(--access-accent) 4%, transparent)
    );
  border-color: color-mix(in srgb, var(--access-accent) 22%, var(--tabs-border));
  color: var(--access-accent-strong);
}

.access-state-copy {
  min-width: 0;
  max-width: 58rem;
}

.access-state-meta {
  display: flex;
  align-items: center;
  gap: 0.85rem;
  margin-bottom: 0.65rem;
}

.access-state-kicker {
  margin: 0;
  color: var(--text-muted);
  font-size: 0.75rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.08em;
}

.access-state-badge {
  height: 1.65rem;
  padding: 0 0.65rem;
  border-radius: 999px;
  border: 1px solid color-mix(in srgb, var(--access-accent) 28%, transparent);
  background: color-mix(in srgb, var(--access-accent) 7%, transparent);
  color: var(--text-secondary);
  display: inline-flex;
  align-items: center;
  font-size: 0.72rem;
  font-weight: 800;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.cnpj-access-state--error .access-state-badge {
  border-color: color-mix(in srgb, var(--access-accent) 28%, transparent);
  background: color-mix(in srgb, var(--access-accent) 7%, transparent);
  color: var(--text-secondary);
}

.access-state-copy h2 {
  margin: 0;
  color: color-mix(in srgb, var(--text-color-85) 85%, transparent);
  font-size: 2.05rem;
  font-weight: 800;
  letter-spacing: 0;
}

.access-state-copy p:not(.access-state-kicker) {
  max-width: 46rem;
  margin: 0.65rem 0 0;
  color: var(--text-secondary);
  font-size: 0.98rem;
  line-height: 1.65;
}

.access-state-query {
  display: inline-flex;
  align-items: center;
  gap: 0.85rem;
  margin-top: 1rem;
}

.access-state-query span {
  color: var(--text-muted);
  font-size: 0.72rem;
  font-weight: 800;
  text-transform: uppercase;
  letter-spacing: 0.06em;
}

.access-state-query strong {
  color: color-mix(in srgb, var(--text-color-85) 85%, transparent);
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", monospace;
  font-size: 0.92rem;
  font-weight: 800;
  letter-spacing: 0;
}

.access-state-action {
  height: 2.75rem;
  padding: 0 1rem;
  border: 1px solid color-mix(in srgb, var(--primary-color) 22%, var(--tabs-border));
  border-radius: 10px;
  background:
    linear-gradient(
      180deg,
      color-mix(in srgb, var(--primary-color) 8%, var(--card-bg)),
      color-mix(in srgb, var(--primary-color) 4%, transparent)
    );
  color: color-mix(in srgb, var(--text-color-85) 85%, transparent);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 0.5rem;
  font-weight: 700;
  cursor: pointer;
  white-space: nowrap;
  box-shadow: inset 0 1px 0 var(--access-glass-highlight);
}

.access-state-action i {
  color: var(--primary-color);
}

.access-state-action:hover {
  transform: translateY(-1px);
  background:
    linear-gradient(
      180deg,
      color-mix(in srgb, var(--primary-color) 10%, var(--card-bg)),
      color-mix(in srgb, var(--primary-color) 5%, transparent)
    );
}

/* ── CARD MESTRE DE DADOS (ABAS + CONTEÚDO UNIFICADOS - OPÇÃO B) ── */
.detail-tabs {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background: var(--tabs-bg);
  border: 1px solid var(--tabs-border);
  border-top: none; /* Fundido com o header acima */
  border-radius: 0 0 12px 12px; /* Apenas cantos inferiores */
  box-shadow: none;
  margin-bottom: 2rem;
}

/* Removemos a redundância de cards aninhados para um visual cleaner */
.detail-tabs :deep(.shadow-card) {
  border: none !important;
  box-shadow: none !important;
  background: transparent !important;
  padding: 0 !important;
}

:deep(.p-tabview) {
  display: flex;
  flex-direction: column;
  height: 100%;
}

:deep(.p-tabview-panels) {
  flex: 1;
  overflow: hidden !important; /* Estabiliza o container para evitar flashes de scroll do pai */
  padding: 0;
  background: transparent !important;
}

/* ── ANIMAÇÃO DE ENTRADA DO CONTEÚDO (PADRÃO PREMIUM) ── */
:deep(.p-tabview-panel) {
  height: 100%;
  overflow: hidden; /* Evita scrollbar temporaria durante a animacao de entrada da aba */
  background: transparent !important;
  animation: tabContentEntry 0.4s cubic-bezier(0.4, 0, 0.2, 1);
}

@keyframes tabContentEntry {
  from {
    opacity: 0;
    transform: translateY(15px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

:deep(.p-tabview-nav) {
  background: var(--establishment-header-bg) !important;
  border-top: 3px solid
    color-mix(in srgb, var(--primary-color) 40%, var(--tabs-border));
  border-bottom: 1px solid var(--tabs-border);
  padding: 0.5rem 1.25rem 0;
  display: flex;
  flex-wrap: nowrap;
  min-width: max-content;
}

:deep(.p-tabview-nav-container),
:deep(.p-tabview-nav-content) {
  overflow-x: auto !important;
  overflow-y: hidden !important;
  scrollbar-width: thin;
  scrollbar-color: color-mix(in srgb, var(--text-secondary) 45%, transparent)
    transparent;
}

:deep(.p-tabview-nav-container::-webkit-scrollbar),
:deep(.p-tabview-nav-content::-webkit-scrollbar) {
  height: 6px;
}

:deep(.p-tabview-nav-container::-webkit-scrollbar-track),
:deep(.p-tabview-nav-content::-webkit-scrollbar-track) {
  background: transparent;
}

:deep(.p-tabview-nav-container::-webkit-scrollbar-thumb),
:deep(.p-tabview-nav-content::-webkit-scrollbar-thumb) {
  background: color-mix(in srgb, var(--text-secondary) 35%, transparent);
  border-radius: 999px;
}

/* Reset de indicadores padrão do PrimeVue */
:deep(.p-tabview-ink-bar) {
  display: none !important;
}

:deep(.p-tabview-nav li) {
  border: none !important;
  background: transparent !important;
  flex: 0 0 auto;
}

:deep(.p-tabview-nav li .p-tabview-nav-link) {
  background: transparent !important;
  font-size: 0.75rem;
  font-weight: 700;
  min-width: 9.5rem;
  min-height: 2.75rem;
  padding: 0.35rem 1rem !important;
  gap: 0.5rem;
  align-items: center;
  justify-content: center;
  /* Transição cirúrgica: apenas no que importa, sem animar bordas (evita o flash) */
  transition:
    color 0.2s,
    background-color 0.2s;
  color: var(--text-secondary) !important;
  text-transform: uppercase !important;
  letter-spacing: 0.04em;
  border: none !important;
  border-bottom: 3px solid transparent !important;
  margin-bottom: -1px !important;
}

:deep(.p-tabview-nav li .p-tabview-nav-link span) {
  display: inline-block;
  line-height: 1.1;
  text-align: left;
  white-space: normal;
  max-width: 7.25rem;
}

/* Estado Ativo Cirúrgico (Sem Linha Dupla e Sem Flash) */
:deep(.p-tabview-nav li.p-highlight .p-tabview-nav-link),
:deep(.p-tabview-nav li .p-tabview-nav-link[aria-selected="true"]) {
  background: color-mix(
    in srgb,
    var(--primary-color) 10%,
    transparent
  ) !important;
  color: var(--primary-color) !important;
  position: relative;
  border: 0 !important;
  border-bottom: 3px solid transparent !important;
  border-width: 0 !important;
  box-shadow: none !important;
  outline: none !important;
  border-radius: 8px 8px 0 0;
  /* Garante que a transição de borda seja instantânea */
  transition: none !important;
}

:deep(.p-tabview-nav li .p-tabview-nav-link:focus),
:deep(.p-tabview-nav li .p-tabview-nav-link:active) {
  box-shadow: none !important;
  outline: none !important;
  border-bottom-color: transparent !important;
}

/* O INDICADOR: Pílula flutuante centralizada */
:deep(.p-tabview-nav li.p-highlight .p-tabview-nav-link::after) {
  content: "";
  position: absolute;
  bottom: 0px;
  left: 20%;
  width: 60%;
  height: 4px;
  background: var(--primary-color) !important;
  border-radius: 99px;
  box-shadow: 0 0 10px color-mix(in srgb, var(--primary-color) 50%, transparent);
  transition: all 0.3s ease;
}

.tab-icon {
  font-size: 0.8rem;
}

/* ── PLACEHOLDER E CONTEÚDO ──────────────────────────── */
:deep(.p-tabview-panels) {
  padding: 0 !important;
  background: transparent !important;
}

.tab-content {
  padding: 1rem;
  min-height: calc(
    100vh - 450px
  ); /* Garante que a aba tenha uma altura mínima respeitável */
}

.detail-tab-enter {
  animation: detailTabEnter 0.32s ease-out;
}

@keyframes detailTabEnter {
  from {
    opacity: 0;
    transform: translateY(10px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

/* ── GLOBAL LOADING OVERLAY (PREMIUM & ESTÁVEL) ── */
.global-loading-overlay {
  position: fixed;
  inset: 0;
  z-index: 9999;
  background: color-mix(in srgb, var(--bg-color) 72%, transparent);
  backdrop-filter: blur(2px);
  -webkit-backdrop-filter: blur(2px);
  display: flex;
  align-items: center;
  justify-content: center;
  pointer-events: all;

  /* Ajuste de contexto de layout: compensa sidebar e navbar */
  padding-left: var(--sidebar-width, 280px);
  padding-top: 56px;

  /* Sincronização com as transições do layout global */
  transition:
    padding-left 0.35s cubic-bezier(0.4, 0, 0.2, 1),
    opacity 0.18s ease;
}

.loader-content {
  display: inline-flex;
  align-items: center;
  gap: 0.75rem;
  padding: 0.9rem 1.1rem;
  border: 1px solid var(--card-border);
  border-radius: 10px;
  background: var(--card-bg);
  color: var(--text-color-85);
  box-shadow: 0 12px 28px color-mix(in srgb, var(--text-color-85) 12%, transparent);
  font-size: 0.9rem;
  font-weight: 600;
}

.loader-content i {
  color: var(--primary-color);
  font-size: 1rem;
}

/* Transição suave */
.fade-blur-enter-active,
.fade-blur-leave-active {
  transition: opacity 0.18s ease;
}

.fade-blur-enter-from,
.fade-blur-leave-to {
  opacity: 0;
}
</style>

<style>
/* Estado de erro nos tabs — não-scoped para alcançar componentes filhos */
.tab-placeholder--error .placeholder-icon,
.tab-placeholder--error i {
  color: var(--red-400, #f87171) !important;
}
.tab-placeholder--error p {
  color: var(--text-color-85);
  opacity: 0.75;
}
</style>
