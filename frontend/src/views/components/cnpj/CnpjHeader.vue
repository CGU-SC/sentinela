<script setup>
import { ref, computed } from "vue";
import { useFrozenData } from "@/composables/useFrozenData";

import { useRiskMetrics } from "@/composables/useRiskMetrics";
import { useFormatting } from "@/composables/useFormatting";
import { useStatusClass } from "@/composables/useStatusClass";
import { useCnpjNavStore } from "@/stores/cnpjNav";
import { useFarmaciaListsStore } from "@/stores/farmaciaLists";
import { useToggleInteresse } from "@/composables/useToggleInteresse";
import { useEvidenciasStore } from "@/stores/evidencias";
import { useFilterStore } from "@/stores/filters";
import { useGeoStore } from "@/stores/geo";
import { useRouter } from "vue-router";
import { extractCnpjRaiz } from "@/composables/useParsing";
import { MONTH_LABELS } from "@/config/constants";
import { integrityAlertTooltip } from "@/config/integrityAlertTooltipConfig";
import {
  cnpjHeroTextTooltip,
  cnpjHeroTooltip,
} from "@/config/cnpjHeroTooltipConfig";
import ObservationDialog from "./ObservationDialog.vue";
import IntegrityAlertsDialog from "./IntegrityAlertsDialog.vue";
import CnpjCadastroDialog from "./CnpjCadastroDialog.vue";
import CnpjTerritoryMap from "./CnpjTerritoryMap.vue";
import RedeEstabelecimentosDialog from "./RedeEstabelecimentosDialog.vue";

const cnpjNav = useCnpjNavStore();
const farmaciaLists = useFarmaciaListsStore();
const toggleInteresse = useToggleInteresse();
const evidenciasStore = useEvidenciasStore();
const qtdEvidencias = computed(() => evidenciasStore.contar(String(props.cnpj).replace(/\D/g, "")));
const geoStore = useGeoStore();

const qtdMunicipiosRegiao = computed(() =>
  props.qtdMunicipiosRegiao ?? geoStore.qtdMunicipiosPorRegiao(props.geoData?.id_regiao_saude),
);

const { getRiskClass } = useRiskMetrics();
const { formatCurrencyFull, formatNumberFull } = useFormatting();
const { situacaoRfClass, conexaoMsClass } = useStatusClass();

const formatPopulacao = (n) => {
  if (n == null) return "—";
  if (n >= 1_000_000)
    return `${(n / 1_000_000).toFixed(2).replace(".", ",")} M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1).replace(".", ",")} mil`;
  return n.toLocaleString("pt-BR");
};

const props = defineProps({
  cnpj:          { type: String,  required: true },
  cnpjData:      { type: Object,  default: null },
  geoData:       { type: Object,  default: null },
  qtdMunicipiosRegiao: { type: Number,  default: null },
  cadastro:      { type: Object,  default: null },
  isExporting:   { type: Boolean, default: false },
  isPreparingPdf: { type: Boolean, default: false },
  isGeneratingNote: { type: Boolean, default: false },
  isPreparingNote: { type: Boolean, default: false },
  // Totais recalculados para o período de análise selecionado.
  // Quando presentes, sobrepõem os valores globais do cnpjData.
  periodSummary: { type: Object,  default: null },  // { totalMov, valSemComp, percValSemComp }
  periodLoading: { type: Boolean, default: false },
  integrityAlerts: { type: Object, default: null },
  integrityAlertsLoading: { type: Boolean, default: false },
  integrityAlertsError: { type: String, default: null },
  noteReadiness: { type: Object, default: null },
  noteReadinessLoading: { type: Boolean, default: false },
  noteReadinessError: { type: String, default: null },
  pdfReadiness: { type: Object, default: null },
  pdfReadinessLoading: { type: Boolean, default: false },
  pdfReadinessError: { type: String, default: null },
});

const emit = defineEmits(["export", "generateNote", "navigate-section"]);

const copied = ref(false);
const copyCnpj = () => {
  if (navigator.clipboard) {
    navigator.clipboard.writeText(props.cnpj);
    copied.value = true;
    setTimeout(() => {
      copied.value = false;
    }, 2000);
  }
};

const filterStore = useFilterStore();

// ── Cache de Valores para Transição Suave ──────────────────
// Mantém os valores anteriores visíveis durante o loading do novo período,
// evitando o "piscando" ou volta brusca para os valores globais.
const displaySummary = useFrozenData(
  () => props.periodSummary || {
    valSemComp: props.cnpjData?.valSemComp ?? 0,
    totalMov: props.cnpjData?.totalMov ?? 0,
    percValSemComp: props.cnpjData?.percValSemComp ?? 0
  },
  () => props.periodLoading,
  { deep: true }
);

const displayValSemComp     = computed(() => displaySummary.value?.valSemComp ?? 0);
const displayTotalMov       = computed(() => displaySummary.value?.totalMov ?? 0);
const displayPercValSemComp = computed(() => displaySummary.value?.percValSemComp ?? 0);

const hasRiskScore = computed(() => props.cnpjData?.score_risco_final != null);
const risco = computed(() => displayPercValSemComp.value);

const riskPanelClass = computed(() => {
  if (!hasRiskScore.value) return "";
  const rc = getRiskClass(risco.value);
  return rc === 'risk-critical' ? 'risk-high' : rc;
});

const riskScoreDisplay = computed(() => {
  if (!hasRiskScore.value) return "—";
  return Number(props.cnpjData.score_risco_final).toFixed(1);
});

const riskScoreBadge = computed(() => {
  if (hasRiskScore.value) {
    return props.cnpjData?.classificacao_risco?.replace("RISCO ", "") ?? "";
  }
  return displayTotalMov.value === 0 ? "Sem movimentação" : "Não calculado";
});

const formatPeriodMonth = (date) => {
  const normalized = date instanceof Date ? date : new Date(date);
  if (Number.isNaN(normalized.getTime())) return null;
  return `${MONTH_LABELS[normalized.getMonth()].toLowerCase()}/${normalized.getFullYear()}`;
};

const analysisPeriodLabel = computed(() => {
  const [start, end] = filterStore.periodo ?? [];
  const startLabel = formatPeriodMonth(start);
  const endLabel = formatPeriodMonth(end);
  if (!startLabel || !endLabel) return "Período não definido";
  return `${startLabel} - ${endLabel}`;
});

// Classificação de badges — delegada ao composable useStatusClass
const conexaoMsClassComp = computed(() =>
  conexaoMsClass(props.cnpjData?.is_conexao_ativa),
);
const situacaoRfClassComp = computed(() =>
  situacaoRfClass(props.cnpjData?.situacao_rf),
);

const nomeFantasia = computed(() => props.cadastro?.nome_fantasia ?? null);
const razaoSocial = computed(
  () => props.cadastro?.razao_social ?? props.cnpjData?.razao_social ?? null,
);

const tituloDisplay = computed(() => {
  const nome = nomeFantasia.value ?? razaoSocial.value;
  if (!nome) return "—";
  return nome.length > 50 ? nome.slice(0, 50) + "..." : nome;
});
const tituloTooltip = computed(() => {
  const nome = nomeFantasia.value ?? razaoSocial.value;
  return nome && nome.length > 50 ? nome : null;
});

const subtituloDisplay = computed(() => {
  if (!nomeFantasia.value) return null; // sem fantasia, título já é a razão social
  const nome = razaoSocial.value;
  if (!nome) return null;
  return nome.length > 60 ? nome.slice(0, 60) + "..." : nome;
});
const subtituloTooltip = computed(() => {
  if (!nomeFantasia.value) return null;
  const nome = razaoSocial.value;
  return nome && nome.length > 60 ? nome : null;
});

const nomeCompletoHtmlTooltip = computed(() =>
  tituloTooltip.value
    ? cnpjHeroTextTooltip(
        "Nome do estabelecimento",
        "Nome fantasia completo registrado para o estabelecimento.",
        tituloTooltip.value,
      )
    : null,
);

const razaoSocialCompletaHtmlTooltip = computed(() =>
  subtituloTooltip.value
    ? cnpjHeroTextTooltip(
        "Razão social",
        "Razão social completa registrada para o estabelecimento.",
        subtituloTooltip.value,
      )
    : null,
);

const formatRank = (rank) => {
  if (rank == null) return "—";
  return `${rank}º`;
};

const formatCnpj = (v) => {
  if (!v) return "—";
  const clean = v.replace(/\D/g, "");
  if (clean.length !== 14) return v;
  return clean.replace(
    /^(\d{2})(\d{3})(\d{3})(\d{4})(\d{2})$/,
    "$1.$2.$3/$4-$5",
  );
};

// ── Formatação Robusta de Endereço ────────────────────────
const formattedFullAddress = computed(() => {
  const c = props.cadastro;
  if (!c || !c.logradouro) return null;

  // 1. Parte Principal: Tipo + Logradouro + Número
  let main = [c.tipo_logradouro, c.logradouro].filter(Boolean).join(" ");
  if (c.numero && c.numero !== "None") main += `, ${c.numero}`;

  // 2. Complemento (se existir)
  if (c.complemento && c.complemento !== "None" && c.complemento !== "null") {
    main += ` - ${c.complemento}`;
  }

  // 3. Bairro e CEP
  const parts = [main];
  if (c.bairro && c.bairro !== "None") parts.push(c.bairro);
  if (c.cep && c.cep !== "None") parts.push(`CEP: ${c.cep}`);

  return parts.filter(Boolean).join(" · ");
});

const router = useRouter();

const showRedeDialog = ref(false);

const openRedeDialog = () => {
  if (props.cnpjData?.qtd_estabelecimentos_rede > 1) {
    showRedeDialog.value = true;
  }
};

const redeDialogCnpjRaiz = computed(() =>
  extractCnpjRaiz(props.cnpj ?? "")
);

const redeBadgeHtmlTooltip = computed(() => {
  const quantidade = props.cnpjData?.qtd_estabelecimentos_rede ?? 0;
  return cnpjHeroTooltip("rede", {
    detail: quantidade > 1
      ? `Ação disponível: consultar os ${quantidade} estabelecimentos identificados.`
      : "Ação disponível: nenhum outro estabelecimento foi identificado na rede.",
  });
});

const ministerioSaudeHtmlTooltip = computed(() =>
  cnpjHeroTooltip("ministerioSaude", {
    detail: `Conexão: ${props.cnpjData?.is_conexao_ativa ? "Ativa" : "Inativa"}.`,
  }),
);

const receitaFederalHtmlTooltip = computed(() =>
  cnpjHeroTooltip("receitaFederal", {
    detail: `Situação cadastral: ${props.cnpjData?.situacao_rf ?? "Não informada"}.`,
  }),
);

const showObsDialog = ref(false);
const openObsDialog = () => {
  showObsDialog.value = true;
};

const showCadastroDialog = ref(false);
const openCadastroDialog = () => {
  showCadastroDialog.value = true;
};

const hasObservacao = computed(() => !!farmaciaLists.getObservacao(props.cnpj));
const showIntegrityDialog = ref(false);

const integrityAlertTypes = computed(() => {
  const alerts = props.integrityAlerts?.alertas ?? [];
  const unique = [];
  const seen = new Set();

  alerts.forEach((alert) => {
    if (seen.has(alert.tipo)) return;
    seen.add(alert.tipo);
    unique.push(alert);
  });

  return unique.slice(0, 3);
});

const integrityStatus = computed(() => {
  if (props.integrityAlertsLoading) return "loading";
  if (props.integrityAlertsError) return "error";
  if ((props.integrityAlerts?.total ?? 0) > 0) return "alerts";
  return "clear";
});

const openIntegrityDialog = () => {
  if ((props.integrityAlerts?.total ?? 0) > 0) {
    showIntegrityDialog.value = true;
  }
};

const noteMissingModules = computed(() =>
  (props.noteReadiness?.missing_modules ?? [])
    .map((module) => module.label)
    .filter(Boolean),
);

const isNoteReady = computed(() => props.noteReadiness?.ready === true);
const isNotePreparable = computed(() => props.noteReadiness?.preparable === true);

const isNoteButtonDisabled = computed(() =>
  props.isGeneratingNote
  || props.isPreparingNote
  || props.noteReadinessLoading
  || (!isNoteReady.value && !isNotePreparable.value),
);

const noteTooltip = computed(() => {
  if (props.isPreparingNote) return "Preparando dados da Nota Técnica";
  if (props.isGeneratingNote) return "Gerando Nota Técnica";
  if (props.noteReadinessLoading || !props.noteReadiness) {
    return "Verificando módulos da Nota Técnica";
  }
  if (isNoteReady.value) return "Gerar Nota Técnica";
  if (isNotePreparable.value) return "Preparar dados e gerar Nota Técnica";
  if (noteMissingModules.value.length) {
    return `Nota Técnica indisponível. Módulos pendentes: ${noteMissingModules.value.join(", ")}.`;
  }
  return props.noteReadinessError || "Nota Técnica indisponível";
});
const pdfMissingModules = computed(() =>
  (props.pdfReadiness?.missing_modules ?? [])
    .map((module) => module.label)
    .filter(Boolean),
);

const isPdfReady = computed(() => props.pdfReadiness?.ready === true);
const isPdfPreparable = computed(() => props.pdfReadiness?.preparable === true);

const isPdfButtonDisabled = computed(() =>
  props.isExporting
  || props.isPreparingPdf
  || props.pdfReadinessLoading
  || (!isPdfReady.value && !isPdfPreparable.value),
);

const pdfTooltip = computed(() => {
  if (props.isPreparingPdf) return "Preparando dados do Relatório PDF";
  if (props.isExporting) return "Gerando Relatório PDF";
  if (props.pdfReadinessLoading || !props.pdfReadiness) {
    return "Verificando módulos do Relatório PDF";
  }
  if (isPdfReady.value) return "Gerar Relatório PDF";
  if (isPdfPreparable.value) return "Preparar dados e gerar Relatório PDF";
  if (pdfMissingModules.value.length) {
    return `Relatório PDF indisponível. Módulos pendentes: ${pdfMissingModules.value.join(", ")}.`;
  }
  return props.pdfReadinessError || "Relatório PDF indisponível";
});

const pdfHtmlTooltip = computed(() =>
  cnpjHeroTooltip("pdf", { detail: pdfTooltip.value }),
);

const noteHtmlTooltip = computed(() =>
  cnpjHeroTooltip("notaTecnica", { detail: noteTooltip.value }),
);

const interesseHtmlTooltip = computed(() =>
  cnpjHeroTooltip("listaInteresse", {
    detail: farmaciaLists.isInteresse(props.cnpj)
      ? "Remover este estabelecimento da lista."
      : "Adicionar este estabelecimento à lista.",
  }),
);

const evidenciasHtmlTooltip = computed(() =>
  cnpjHeroTooltip("evidencias", {
    detail: evidenciasStore.loadState === "error"
      ? "Cesta de evidências indisponível."
      : qtdEvidencias.value === 0
        ? "Nenhuma evidência marcada."
        : `${qtdEvidencias.value} ${qtdEvidencias.value === 1 ? "item marcado" : "itens marcados"}.`,
  }),
);

const observacaoHtmlTooltip = computed(() =>
  cnpjHeroTooltip("observacao", {
    detail: hasObservacao.value
      ? "Editar a observação registrada."
      : "Adicionar uma observação ao estabelecimento.",
  }),
);

const heroTooltips = Object.freeze({
  back: cnpjHeroTooltip("back"),
  copyCnpj: cnpjHeroTooltip("copyCnpj"),
  cadastro: cnpjHeroTooltip("cadastro"),
  rankRegiao: cnpjHeroTooltip("rankRegiao"),
  rankMunicipio: cnpjHeroTooltip("rankMunicipio"),
});
</script>

<template>
  <div class="detail-header-new shadow-sm">
    <!-- Área Central: Razão Social e Localização -->
    <div class="header-main-info" v-if="cnpjData">
      <div class="title-group">
        <div class="razao-social-row">
          <div class="titulo-group">
            <div class="titulo-row">
              <button
                class="back-btn"
                @click="router.back()"
                v-tooltip.bottom="heroTooltips.back"
              >
                <i class="pi pi-arrow-left" />
              </button>
              <h1 class="razao-social-new" v-tooltip.bottom="nomeCompletoHtmlTooltip">
                {{ tituloDisplay }}
              </h1>
              <div
                class="cnpj-copy-wrap-new"
                v-tooltip.bottom="heroTooltips.copyCnpj"
                @click="copyCnpj"
              >
                <span class="cnpj-text">{{ formatCnpj(props.cnpj) }}</span>
                <i
                  :class="[
                    'pi',
                    copied ? 'pi-check text-green-400' : 'pi-copy',
                  ]"
                />
              </div>
              <button
                v-if="cadastro || cnpjData"
                type="button"
                class="cnpj-cadastro-btn-new"
                @click="openCadastroDialog"
                v-tooltip.bottom="heroTooltips.cadastro"
                aria-label="Dados Cadastrais"
              >
                <i class="pi pi-id-card" />
              </button>
            </div>
            <span
              v-if="subtituloDisplay"
              class="razao-social-sub"
              v-tooltip.bottom="razaoSocialCompletaHtmlTooltip"
            >
              {{ subtituloDisplay }}
            </span>
          </div>
        </div>
        <!-- NOVO: Linha de Endereço e Geolocalização -->
        <div class="address-row-new" v-if="cadastro && formattedFullAddress">
          <span class="address-text">
            <i class="pi pi-home" />
            {{ formattedFullAddress }}
          </span>
        </div>

        <!-- Linha 1: Localização -->
        <div class="location-chips">
          <span class="loc-text">
            <i class="pi pi-map-marker" />
            {{ geoData?.no_municipio ?? cnpjData.municipio }},
            {{ geoData?.sg_uf ?? cnpjData.uf }}
          </span>
          <span class="loc-separator">·</span>
          <span class="loc-text"
            >Região {{ geoData?.no_regiao_saude ?? "Não Identificada" }}</span
          >
        </div>

        <!-- Linha 2: Risco | Status Cadastral -->
        <div class="status-chips-row">
          <!-- Estabelecimentos (sempre visível; clicável quando há mais de 1 na rede) -->
          <div
            v-if="cnpjData.qtd_estabelecimentos_rede >= 1"
            class="institution-chip status-info"
            :class="{ 'clickable-badge': cnpjData.qtd_estabelecimentos_rede > 1 }"
            v-tooltip.bottom-right="redeBadgeHtmlTooltip"
            @click="openRedeDialog"
          >
            <span class="institution-label">Estabelecimentos</span>
            <span class="institution-value">{{
              cnpjData.qtd_estabelecimentos_rede
            }}</span>
          </div>

          <!-- Ministério da Saúde -->
          <div
            class="institution-chip"
            :class="conexaoMsClassComp"
            v-tooltip.bottom="ministerioSaudeHtmlTooltip"
          >
            <span class="institution-label">Ministério da Saúde</span>
            <span class="institution-value">{{
              props.cnpjData?.is_conexao_ativa ? "Ativa" : "Inativa"
            }}</span>
          </div>

          <!-- Receita Federal -->
          <div
            class="institution-chip"
            :class="situacaoRfClassComp"
            v-tooltip.bottom="receitaFederalHtmlTooltip"
          >
            <span class="institution-label">Receita Federal</span>
            <span class="institution-value">{{
              cnpjData.situacao_rf ?? "—"
            }}</span>
          </div>
        </div>
      </div>

      <div class="header-right-col">
        <div
          class="risk-context-panel"
          :class="riskPanelClass"
        >
          <CnpjTerritoryMap
            v-if="geoData"
            :geo-data="geoData"
            :risk-class="riskPanelClass"
          />
          <div class="risk-context-content">
            <div
              class="rcp-period"
              :class="{ 'rcp-period--loading': periodLoading && !filterStore.isAnimating }"
            >
              <i :class="periodLoading && !filterStore.isAnimating ? 'pi pi-spin pi-spinner' : 'pi pi-calendar'" />
              <span class="rcp-period-label">Período analisado</span>
              <span class="rcp-period-value">{{ analysisPeriodLabel }}</span>
            </div>
            <div class="rcp-metrics">
              <div class="rcp-score-row">
                <div class="rcp-item">
                  <span class="rcp-label">Score de Risco</span>
                  <span class="rcp-value" :class="{ 'rcp-value--neutral': !hasRiskScore }">
                    {{ riskScoreDisplay }}
                    <span class="rcp-badge">{{ riskScoreBadge }}</span>
                  </span>
                </div>
              </div>
              <div
                class="rcp-progress-wrap"
                :class="{ 'kpi-refreshing': periodLoading && !filterStore.isAnimating }"
              >
                <div class="rcp-progress-header">
                  <span class="rcp-pct-inline">{{ displayPercValSemComp.toFixed(2) }}% <span class="rcp-pct-label">sem comprovação</span></span>
                </div>
                <div class="rcp-progress-track">
                  <div
                    class="rcp-progress-fill"
                    :style="{ width: `${Math.min(displayPercValSemComp, 100)}%` }"
                  />
                </div>
              </div>
              <div
                class="rcp-financials"
                :class="{ 'kpi-refreshing': periodLoading && !filterStore.isAnimating }"
              >
                <div class="rcp-item">
                  <span class="rcp-label">Sem Comprovação</span>
                  <span class="rcp-value">{{ formatCurrencyFull(displayValSemComp) }}</span>
                </div>
                <div class="rcp-divider" />
                <div class="rcp-item">
                  <span class="rcp-label">Total Movimentado</span>
                  <span class="rcp-value">{{ formatCurrencyFull(displayTotalMov) }}</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <button
      v-if="cnpjData"
      class="integrity-strip"
      :class="[
        `integrity-strip--${integrityStatus}`,
        { 'integrity-strip--clickable': integrityStatus === 'alerts' },
      ]"
      type="button"
      :disabled="integrityStatus !== 'alerts'"
      @click="openIntegrityDialog"
    >
      <span class="integrity-strip-title">
        <i
          :class="integrityAlertsLoading
            ? 'pi pi-spin pi-spinner'
            : integrityStatus === 'clear'
              ? 'pi pi-check-circle'
              : integrityStatus === 'error'
                ? 'pi pi-times-circle'
                : 'pi pi-shield'"
        />
        Alertas
      </span>

      <template v-if="integrityStatus === 'loading'">
        <span class="integrity-strip-message">Verificando bases de integridade</span>
      </template>

      <template v-else-if="integrityStatus === 'error'">
        <span class="integrity-strip-message">Informações indisponíveis</span>
      </template>

      <template v-else-if="integrityStatus === 'clear'">
        <span class="integrity-strip-message">Nenhum alerta identificado</span>
      </template>

      <template v-else>
        <span
          v-for="alert in integrityAlertTypes"
          :key="alert.tipo"
          class="integrity-preview"
          :class="`integrity-preview--${alert.severidade}`"
          role="img"
          tabindex="0"
          :aria-label="`Explicação do alerta ${alert.titulo}`"
          v-tooltip.top="integrityAlertTooltip(alert)"
        >
          {{ alert.titulo }}
          <i class="pi pi-info-circle integrity-preview-info" aria-hidden="true" />
        </span>
        <span class="integrity-strip-action">
          Ver detalhes
          <i class="pi pi-arrow-right" />
        </span>
      </template>
    </button>

    <!-- Painel de Rankings e Estatísticas -->
    <div class="header-ranking-panel" v-if="cnpjData">
      <div class="ranking-grid-new">
        <div class="rank-stat">
          <i class="pi pi-globe gold" />
          <div class="rank-details">
            <span class="rank-label">Rank Nacional</span>
            <span class="rank-val"
              >{{ formatRank(cnpjData.rank_nacional) }}
              <small v-if="cnpjData.total_nacional != null">/ {{ cnpjData.total_nacional }}</small></span
            >
          </div>
        </div>
        <div class="rank-stat">
          <i class="pi pi-compass silver" />
          <div class="rank-details">
            <span class="rank-label">Rank Estadual</span>
            <span class="rank-val"
              >{{ formatRank(cnpjData.rank_uf) }}
              <small v-if="cnpjData.total_uf != null">/ {{ cnpjData.total_uf }}</small></span
            >
          </div>
        </div>
        <div class="rank-stat">
          <i class="pi pi-share-alt bronze" />
          <div class="rank-details">
            <span class="rank-label">Rank Regional</span>
            <span class="rank-val"
              >{{ formatRank(cnpjData.rank_regiao_saude) }}
              <small v-if="cnpjData.total_regiao_saude != null">/ {{ cnpjData.total_regiao_saude }}</small></span
            >
          </div>
        </div>
        <div class="rank-stat">
          <i class="pi pi-building neutral" />
          <div class="rank-details">
            <span class="rank-label">Rank Municipal</span>
            <span class="rank-val"
              >{{ formatRank(cnpjData.rank_municipio) }}
              <small v-if="cnpjData.total_municipio != null">/ {{ cnpjData.total_municipio }}</small></span
            >
          </div>
        </div>
        <div class="rank-stat" v-if="qtdMunicipiosRegiao">
          <i class="pi pi-map" style="color: #34d399" />
          <div class="rank-details">
            <span class="rank-label">Munic. da Região</span>
            <span class="rank-val">{{ qtdMunicipiosRegiao }}</span>
          </div>
        </div>
        <div
          class="rank-stat rank-stat--clickable"
          v-if="cnpjData.total_regiao_saude != null"
          v-tooltip.top="heroTooltips.rankRegiao"
          @click="cnpjNav.navigateToRegiao(null)"
        >
          <i
            class="pi pi-sitemap"
            style="color: var(--text-muted); opacity: 0.8"
          />
          <div class="rank-details">
            <span class="rank-label">Estab. Região</span>
            <span class="rank-val">{{ cnpjData.total_regiao_saude }}</span>
          </div>
        </div>
        <div
          class="rank-stat rank-stat--clickable"
          v-if="cnpjData.total_municipio != null"
          v-tooltip.top="heroTooltips.rankMunicipio"
          @click="
            cnpjNav.navigateToRegiao(
              {
                id_ibge7: geoData?.id_ibge7,
                municipio: geoData?.no_municipio ?? cnpjData.municipio,
              },
            )
          "
        >
          <i class="pi pi-building" style="color: #a78bfa" />
          <div class="rank-details">
            <span class="rank-label">Estab. Município</span>
            <span class="rank-val">{{ cnpjData.total_municipio }}</span>
          </div>
        </div>
        <div class="rank-stat" v-if="geoData?.nu_populacao">
          <i class="pi pi-users" style="color: #60a5fa" />
          <div class="rank-details">
            <span class="rank-label">Pop. Município</span>
            <span class="rank-val">{{
              formatPopulacao(geoData.nu_populacao)
            }}</span>
          </div>
        </div>
      </div>
      <div class="list-actions list-actions--vertical">
          <button
            class="list-btn list-btn--icon-only list-btn--export"
            :class="{ 'list-btn--loading': isExporting || isPreparingPdf }"
            @click="emit('export')"
            :disabled="isPdfButtonDisabled"
            v-tooltip.bottom="pdfHtmlTooltip"
          >
            <i :class="(isExporting || isPreparingPdf || pdfReadinessLoading) ? 'pi pi-spin pi-spinner' : 'pi pi-file-pdf'" />
          </button>
          <button
            class="list-btn list-btn--icon-only list-btn--note"
            :class="{ 'list-btn--loading': isGeneratingNote || isPreparingNote }"
            @click="emit('generateNote')"
            :disabled="isNoteButtonDisabled"
            v-tooltip.bottom="noteHtmlTooltip"
          >
            <i :class="(isGeneratingNote || isPreparingNote || noteReadinessLoading) ? 'pi pi-spin pi-spinner' : 'pi pi-book'" />
          </button>
          <button
            class="list-btn list-btn--icon-only"
            :class="farmaciaLists.isInteresse(cnpj) ? 'list-btn--interesse-active' : 'list-btn--interesse'"
            @click="toggleInteresse(cnpj, cnpjData.razao_social)"
            :disabled="!farmaciaLists.canEdit"
            v-tooltip.bottom="interesseHtmlTooltip"
          >
            <i :class="farmaciaLists.isInteresse(cnpj) ? 'pi pi-star-fill' : 'pi pi-star'" />
          </button>
          <button
            class="list-btn list-btn--icon-only list-btn--evid"
            :class="{ 'list-btn--evid-active': qtdEvidencias > 0 }"
            type="button"
            :aria-label="`Evidências (${qtdEvidencias})`"
            @click="evidenciasStore.painelAberto = true"
            v-tooltip.bottom="evidenciasHtmlTooltip"
          >
            <i :class="qtdEvidencias > 0 ? 'pi pi-flag-fill' : 'pi pi-flag'" />
            <span v-if="qtdEvidencias > 0" class="list-btn-count">{{ qtdEvidencias }}</span>
          </button>
          <button
            v-if="farmaciaLists.isInteresse(cnpj)"
            class="list-btn list-btn--icon-only list-btn--obs"
            :class="{ 'list-btn--obs-active': hasObservacao }"
            @click="openObsDialog"
            :disabled="!farmaciaLists.canEdit"
            v-tooltip.bottom="observacaoHtmlTooltip"
          >
            <i :class="hasObservacao ? 'pi pi-comment' : 'pi pi-pencil'" />
          </button>
        </div>
    </div>

    <div class="header-loading" v-else>
      <i class="pi pi-spin pi-spinner" /> Carregando perfil do
      estabelecimento...
    </div>

    <ObservationDialog
      v-model:visible="showObsDialog"
      :cnpj="cnpj"
      :entity-name="tituloDisplay"
    />
    <CnpjCadastroDialog
      v-model:visible="showCadastroDialog"
      :cnpj="cnpj"
      :cadastro="cadastro"
      :cnpj-data="cnpjData"
      :geo-data="geoData"
    />
    <IntegrityAlertsDialog
      v-model:visible="showIntegrityDialog"
      :data="integrityAlerts"
      @navigate="emit('navigate-section', $event)"
    />
    <RedeEstabelecimentosDialog
      v-model:visible="showRedeDialog"
      :cnpj-raiz="redeDialogCnpjRaiz"
      :cnpj-origem="cnpj"
    />
  </div>
</template>

<style scoped>
/* ── CABEÇALHO RESUMO (SOLTO) ────────────────── */
.detail-header-new {
  background: var(--establishment-header-bg);
  padding: 1rem 2rem 0.75rem;
  border: 1px solid var(--establishment-header-border);
  border-bottom: none; /* Fundido com o TabView abaixo */
  border-radius: 12px 12px 0 0; /* Apenas cantos superiores */
  display: flex;
  flex-direction: column;
  gap: 1rem;
  flex-shrink: 0;
  box-shadow: none;
  z-index: 10;
  position: relative;
  overflow: hidden;
}

.detail-header-new::after {
  content: "";
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  height: 2px;
  background: linear-gradient(90deg, var(--primary-color), transparent);
  opacity: 0.3;
}

.integrity-strip {
  display: flex;
  align-items: center;
  min-height: 36px;
  gap: 0.55rem;
  width: 100%;
  padding: 0.35rem 0.65rem;
  border: 1px solid var(--card-border);
  border-radius: 6px;
  background: color-mix(in srgb, var(--text-muted) 4%, transparent);
  color: var(--text-muted);
  text-align: left;
}

.integrity-strip:disabled {
  opacity: 1;
}

.integrity-strip--clickable {
  cursor: pointer;
}

.integrity-strip--clickable:hover {
  border-color: color-mix(in srgb, var(--primary-color) 35%, var(--card-border));
  background: color-mix(in srgb, var(--primary-color) 5%, transparent);
}

.integrity-strip--clear {
  color: var(--risk-low);
}

.integrity-strip--error {
  color: var(--risk-critical);
}

.integrity-strip-title {
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
  flex-shrink: 0;
  font-size: 0.68rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.integrity-strip-message {
  font-size: 0.75rem;
  color: var(--text-muted);
}

.integrity-preview {
  display: inline-flex;
  align-items: center;
  min-height: 24px;
  padding: 0.2rem 0.42rem;
  border: 1px solid var(--card-border);
  border-radius: 4px;
  font-size: 0.71rem;
  font-weight: 600;
  white-space: nowrap;
}

.integrity-preview-info {
  margin-left: 0.3rem;
  color: currentColor;
  font-size: 0.66rem;
  opacity: 0.75;
}

.integrity-preview:focus-visible {
  outline: 2px solid var(--primary-color);
  outline-offset: 2px;
}

.integrity-preview--critico {
  color: var(--risk-high);
  border-color: color-mix(in srgb, var(--risk-high) 30%, transparent);
  background: color-mix(in srgb, var(--risk-high) 9%, transparent);
}

.integrity-preview--atencao {
  color: var(--risk-medium);
  border-color: color-mix(in srgb, var(--risk-medium) 30%, transparent);
  background: color-mix(in srgb, var(--risk-medium) 9%, transparent);
}

.integrity-strip-action {
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
  margin-left: auto;
  color: var(--primary-color);
  font-size: 0.7rem;
  font-weight: 600;
  white-space: nowrap;
}

.header-right-col {
  display: flex;
  flex-direction: row;
  align-items: stretch;
  gap: 0;
  flex-shrink: 0;
}

.list-actions {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.list-btn {
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
  padding: 0.35rem 0.8rem;
  font-size: 0.75rem;
  font-weight: 700;
  border-radius: 8px; /* Padronizado para 8px */
  border: 1px solid;
  cursor: pointer;
  transition: all 0.2s ease;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  backdrop-filter: blur(8px); /* Efeito Vidro Central */
  position: relative;
  overflow: hidden;
}

.list-btn--icon-only {
  width: 34px;
  height: 34px;
  padding: 0;
  justify-content: center;
}

.list-btn--icon-only i {
  font-size: 1rem;
}

.list-btn--export {
  color: var(--primary-color);
  border-color: color-mix(in srgb, var(--primary-color) 30%, transparent);
  background: color-mix(in srgb, var(--primary-color) 8%, transparent);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.1);
}
.list-btn--export:hover:not(:disabled) {
  background: color-mix(in srgb, var(--primary-color) 15%, transparent);
  border-color: var(--primary-color);
  box-shadow: 0 4px 12px
    color-mix(in srgb, var(--primary-color) 25%, transparent);
}
.list-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

/* Efeito de carregamento ativo para os botões de relatório/nota */
.list-btn--loading:disabled {
  opacity: 1 !important;
  cursor: wait !important;
}

.list-btn--export.list-btn--loading {
  --btn-glow-color: var(--primary-color);
  animation: list-btn-glow-pulse 1.8s infinite ease-in-out;
  border-color: var(--primary-color) !important;
}

.list-btn--note.list-btn--loading {
  --btn-glow-color: var(--btn-note-color, #a855f7);
  animation: list-btn-glow-pulse 1.8s infinite ease-in-out;
  border-color: var(--btn-note-color, #a855f7) !important;
}

@keyframes list-btn-glow-pulse {
  0%, 100% {
    box-shadow: 
      0 0 4px color-mix(in srgb, var(--btn-glow-color) 40%, transparent),
      0 0 0 0 color-mix(in srgb, var(--btn-glow-color) 30%, transparent);
    transform: scale(1);
  }
  50% {
    box-shadow: 
      0 0 12px color-mix(in srgb, var(--btn-glow-color) 70%, transparent),
      0 0 0 8px color-mix(in srgb, var(--btn-glow-color) 0%, transparent);
    transform: scale(1.04);
  }
}

.list-btn--note {
  --btn-note-color: #a855f7;
  color: var(--btn-note-color);
  border-color: color-mix(in srgb, var(--btn-note-color) 30%, transparent);
  background: color-mix(in srgb, var(--btn-note-color) 8%, transparent);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.1);
}
.list-btn--note:hover {
  background: color-mix(in srgb, var(--btn-note-color) 15%, transparent);
  border-color: var(--btn-note-color);
  box-shadow: 0 4px 12px
    color-mix(in srgb, var(--btn-note-color) 25%, transparent);
}

.list-btn--interesse {
  color: var(--primary-color);
  border-color: color-mix(in srgb, var(--primary-color) 30%, transparent);
  background: color-mix(in srgb, var(--primary-color) 8%, transparent);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.1);
}
.list-btn--interesse:hover {
  background: color-mix(in srgb, var(--primary-color) 15%, transparent);
  border-color: var(--primary-color);
  box-shadow: 0 4px 12px
    color-mix(in srgb, var(--primary-color) 25%, transparent);
}
.list-btn--interesse-active {
  color: #fff;
  border-color: var(--primary-color);
  background: var(
    --primary-color
  ); /* Sólido para destaque conforme padrão do tema */
  box-shadow: 0 4px 12px
    color-mix(in srgb, var(--primary-color) 30%, transparent);
  font-weight: 700;
}
.list-btn--interesse-active:hover {
  background: color-mix(in srgb, var(--primary-color) 85%, black);
  border-color: color-mix(in srgb, var(--primary-color) 85%, black);
}

.list-btn--evid {
  color: var(--text-muted);
  border-color: color-mix(in srgb, var(--text-muted) 30%, transparent);
  background: color-mix(in srgb, var(--text-muted) 8%, transparent);
  opacity: 0.8;
}
.list-btn--evid:hover {
  color: var(--evidence-color);
  border-color: var(--evidence-color);
  opacity: 1;
}
.list-btn--evid-active {
  color: var(--evidence-color);
  border-color: color-mix(in srgb, var(--evidence-color) 45%, transparent);
  background: color-mix(in srgb, var(--evidence-color) 10%, transparent);
  opacity: 1;
}
.list-btn-count {
  position: absolute;
  top: 1px;
  right: 3px;
  font-size: 0.58rem;
  font-weight: 600;
  letter-spacing: 0;
  line-height: 1;
}

.list-btn--obs {
  --btn-obs-color: var(--text-muted);
  color: var(--btn-obs-color);
  border-color: color-mix(in srgb, var(--btn-obs-color) 30%, transparent);
  background: color-mix(in srgb, var(--btn-obs-color) 8%, transparent);
  opacity: 0.8;
}

.list-btn--obs:hover {
  background: color-mix(in srgb, var(--btn-obs-color) 15%, transparent);
  border-color: var(--btn-obs-color);
  opacity: 1;
}

.list-btn--obs-active {
  --btn-obs-active-color: #3b82f6;
  color: var(--btn-obs-active-color);
  border-color: color-mix(in srgb, var(--btn-obs-active-color) 40%, transparent);
  background: color-mix(in srgb, var(--btn-obs-active-color) 12%, transparent);
  opacity: 1;
  box-shadow: 0 0 10px color-mix(in srgb, var(--btn-obs-active-color) 20%, transparent);
}

.risk-chip {
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  font-size: 0.72rem;
  cursor: default;
}

.risk-chip i {
  color: inherit;
}

.risk-chip.risk-high {
  color: var(--risk-high);
  border-color: color-mix(in srgb, var(--risk-high) 30%, transparent);
  background: color-mix(in srgb, var(--risk-high) 10%, transparent);
}

.risk-chip.risk-critical {
  color: var(--risk-critical);
  border-color: color-mix(in srgb, var(--risk-critical) 30%, transparent);
  background: color-mix(in srgb, var(--risk-critical) 10%, transparent);
}

.risk-chip.risk-medium {
  color: var(--risk-medium);
  border-color: color-mix(in srgb, var(--risk-medium) 30%, transparent);
  background: color-mix(in srgb, var(--risk-medium) 10%, transparent);
}

.risk-chip.risk-low {
  color: var(--risk-low);
  border-color: color-mix(in srgb, var(--risk-low) 30%, transparent);
  background: color-mix(in srgb, var(--risk-low) 10%, transparent);
}

.cnpj-copy-wrap-new {
  background: var(--establishment-header-bg);
  min-height: 34px;
  padding: 0.5rem 1rem;
  border-radius: 6px;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 0.6rem;
  transition: all 0.2s ease-in-out;
  border: 1px solid var(--establishment-header-border) !important;
}

.cnpj-copy-wrap-new:hover {
  background: var(--establishment-header-bg) !important;
  border-color: var(--text-muted) !important;
  transform: translateY(-1px);
}

.cnpj-text {
  font-family: "Inter", sans-serif;
  font-size: 0.78rem;
  font-weight: 600;
  color: var(--text-secondary);
}

.cnpj-copy-wrap-new i {
  font-size: 0.78rem;
  color: var(--text-muted);
}

.header-icon-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 34px;
  height: 34px;
  padding: 0;
  border-radius: 6px;
  border: 1px solid var(--establishment-header-border);
  background: var(--establishment-header-bg);
  color: var(--text-muted);
  cursor: pointer;
  transition: all 0.2s ease;
  flex-shrink: 0;
  position: relative;
}

.header-icon-btn:hover {
  border-color: var(--primary-color);
  color: var(--primary-color);
  transform: translateY(-1px);
}

.cnpj-cadastro-btn-new {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 34px;
  min-height: 34px;
  height: 34px;
  padding: 0;
  border-radius: 6px;
  border: 1px solid var(--establishment-header-border) !important;
  background: var(--establishment-header-bg);
  color: var(--text-secondary);
  font-family: "Inter", sans-serif;
  font-size: 0.78rem;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s ease-in-out;
  flex-shrink: 0;
}

.cnpj-cadastro-btn-new i {
  font-size: 0.85rem;
  color: var(--text-muted);
  transition: transform 0.2s ease;
}

.cnpj-cadastro-btn-new:hover {
  background: var(--establishment-header-bg) !important;
  border-color: var(--text-muted) !important;
  transform: translateY(-1px);
}

.cnpj-cadastro-btn-new:hover i {
  transform: scale(1.15);
}

.cnpj-cadastro-btn-new:active {
  transform: translateY(0);
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.05);
}

.header-icon-btn i {
  font-size: 0.85rem;
}

.header-main-info {
  display: flex;
  justify-content: space-between;
  align-items: stretch;
  gap: 2rem;
  min-width: 0;
}

.title-group {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  min-width: 0;
  flex: 1;
}

.razao-social-row {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  flex-wrap: nowrap;
}

.titulo-group {
  display: flex;
  flex-direction: column;
  gap: 0.1rem;
}

.titulo-row {
  display: flex;
  align-items: center;
  gap: 0.6rem;
}

.razao-social-sub {
  font-size: 0.78rem;
  font-weight: 500;
  color: var(--text-secondary);
  opacity: 0.7;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.razao-social-new {
  font-size: 1.4rem;
  font-weight: 700;
  margin: 0;
  line-height: 1.2;
  letter-spacing: -0.02em;
  color: var(--establishment-header-text);
  white-space: nowrap;
  flex-shrink: 0;
}

.location-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
}

.loc-text {
  display: inline-flex;
  align-items: center;
  gap: 0.3rem;
  font-size: 0.8rem;
  font-weight: 500;
  color: var(--text-color-85);
  opacity: 0.8;
}

.loc-text i {
  font-size: 0.75rem;
}

.address-row-new {
  display: flex;
  align-items: center;
  gap: 1.25rem;
}

.address-text {
  font-size: 0.82rem;
  font-weight: 500;
  color: var(--text-color-85);
  display: flex;
  align-items: center;
  gap: 0.4rem;
  opacity: 0.8;
}

.address-text i {
  font-size: 0.75rem;
  color: var(--primary-color);
  opacity: 0.7;
}

.sep-dot {
  margin: 0 0.1rem;
  opacity: 0.4;
}

.loc-separator {
  color: var(--text-color-85);
  opacity: 0.4;
  font-size: 0.85rem;
}

/* mantido para os risk-chips que ainda usam loc-chip como base */
.loc-chip {
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
  padding: 0.2rem 0.65rem;
  border: 1px solid color-mix(in srgb, var(--primary-color) 15%, transparent);
  border-radius: 6px;
  font-size: 0.8rem;
  font-weight: 600;
  color: var(--text-secondary);
  cursor: default;
}

.header-kpis-new {
  display: flex;
  align-items: center;
  gap: 0.75rem; /* Reduzido de 1.25rem */
}

/* Cápsula Unificada de Risco */
.kpi-pill-group {
  display: flex;
  align-items: center;
  padding: 0.3rem 0.45rem;
  background: var(--establishment-header-bg);
  border: 1px solid var(--card-border);
  border-radius: 12px;
  position: relative;
  overflow: hidden;
  transition: all 0.3s ease, opacity 0.25s ease;
}

.kpi-pill-group.kpi-refreshing,
.pill-item.kpi-refreshing {
  opacity: 0.8 !important; /* Menos opaco para manter legibilidade */
  filter: blur(1.2px);     /* Blur sutil para indicar atualização em curso */
  pointer-events: none;
  transition: all 0.3s ease;
}

/* Barra de acento no rodapé (Opção 2 — Bottom-up) */
.kpi-pill-group::before {
  content: "";
  position: absolute;
  bottom: 0;
  left: 0;
  right: 0;
  height: 3px;
  background: color-mix(in srgb, var(--accent, transparent) 55%, transparent);
  border-radius: 0 0 12px 12px;
}

/* Cores dinâmicas — acento + gradiente Bottom-up por nível de risco */
.kpi-pill-group.risk-high {
  --accent: var(--risk-high);
  background: linear-gradient(
    to top,
    color-mix(in srgb, var(--risk-high) 10%, var(--establishment-header-bg)) 0%,
    var(--establishment-header-bg) 75%
  ) !important;
  border-color: color-mix(
    in srgb,
    var(--risk-high) 20%,
    var(--card-border)
  ) !important;
  color: inherit !important;
}
.kpi-pill-group.risk-critical {
  --accent: var(--risk-critical);
  background: linear-gradient(
    to top,
    color-mix(in srgb, var(--risk-critical) 10%, var(--establishment-header-bg))
      0%,
    var(--establishment-header-bg) 75%
  ) !important;
  border-color: color-mix(
    in srgb,
    var(--risk-critical) 20%,
    var(--card-border)
  ) !important;
  color: inherit !important;
}
.kpi-pill-group.risk-medium {
  --accent: var(--risk-medium);
  background: linear-gradient(
    to top,
    color-mix(in srgb, var(--risk-medium) 10%, var(--establishment-header-bg))
      0%,
    var(--establishment-header-bg) 75%
  ) !important;
  border-color: color-mix(
    in srgb,
    var(--risk-medium) 20%,
    var(--card-border)
  ) !important;
  color: inherit !important;
}
.kpi-pill-group.risk-low {
  --accent: var(--risk-low);
  background: linear-gradient(
    to top,
    color-mix(in srgb, var(--risk-low) 10%, var(--establishment-header-bg)) 0%,
    var(--establishment-header-bg) 75%
  ) !important;
  border-color: color-mix(
    in srgb,
    var(--risk-low) 20%,
    var(--card-border)
  ) !important;
  color: inherit !important;
}

/* Variante Neutra para Dados de Contexto */
.kpi-pill-group--neutral {
  --accent: var(--primary-color);
  background: linear-gradient(
    to top,
    color-mix(in srgb, var(--primary-color) 8%, var(--establishment-header-bg))
      0%,
    var(--establishment-header-bg) 75%
  ) !important;
  border-color: color-mix(
    in srgb,
    var(--primary-color) 15%,
    var(--card-border)
  ) !important;
  backdrop-filter: blur(4px);
}

.kpi-pill-group--neutral::before {
  opacity: 0.4; /* Barra inferior mais discreta */
}

.pill-item {
  display: flex;
  flex-direction: column;
  padding: 0.15rem 0.5rem; /* Padding horizontal reduzido pela metade */
}

.pill-label {
  font-size: 0.68rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--text-color-85);
  opacity: 0.75;
  margin-bottom: 0.15rem;
}

.pill-value {
  font-size: 0.95rem;
  font-weight: 600;
  font-family: "Inter", sans-serif;
  color: var(--text-color-85);
  line-height: 1.1;
  letter-spacing: -0.02em;
  opacity: 0.7;
}

.pill-value.currency {
  /* Inherits 0.95 from .pill-value now */
}

.pill-divider {
  width: 1px;
  height: 2rem;
  background: var(--card-border);
}

/* Card Neutro */
.kpi-card-neutral {
  display: flex;
  flex-direction: column;
  padding-left: 0.75rem; /* Reduzido de 1.25rem */
  border-left: 1px solid var(--card-border);
}

.pill-value.total {
  /* Inherits 0.95 from .pill-value now */
}

.kpi-card.risk-high .kpi-card-value,
.kpi-card.risk-high .kpi-badge-value {
  color: var(--risk-high);
}
.kpi-card.risk-high {
  border-left-color: var(--risk-high);
}

.kpi-card.risk-critical .kpi-card-value,
.kpi-card.risk-critical .kpi-badge-value {
  color: var(--risk-critical);
}
.kpi-card.risk-critical {
  border-left-color: var(--risk-critical);
}

.kpi-card.risk-medium .kpi-card-value,
.kpi-card.risk-medium .kpi-badge-value {
  color: var(--risk-medium);
}
.kpi-card.risk-medium {
  border-left-color: var(--risk-medium);
}

.kpi-card.risk-low .kpi-card-value,
.kpi-card.risk-low .kpi-badge-value {
  color: var(--risk-low);
}
.kpi-card.risk-low {
  border-left-color: var(--risk-low);
}

/* ── RANKING PANEL ── */
.header-ranking-panel {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 2rem;
  padding-top: 1rem;
  padding-bottom: 0.5rem;
  border-top: 1px solid var(--card-border);
}

.ranking-grid-new {
  display: flex;
  flex: 1;
  min-width: 0;
  justify-content: space-between;
  gap: clamp(0.75rem, 1.2vw, 2.5rem);
}

.rank-stat {
  display: flex;
  align-items: center;
  flex-shrink: 0;
  gap: clamp(0.45rem, 0.7vw, 0.8rem);
  transition: all 0.3s;
}

.rank-stat--clickable {
  cursor: pointer;
  padding: 0.3rem 0;
  border-radius: 8px;
  margin: -0.3rem 0;
}

.rank-stat--clickable:hover {
  background: color-mix(in srgb, #a78bfa 10%, transparent);
  transform: translateY(-1px);
}

.nav-hint {
  font-size: 0.65rem;
  color: #a78bfa;
  opacity: 0;
  transition: opacity 0.2s ease;
}

.rank-stat--clickable:hover .nav-hint {
  opacity: 1;
}

.rank-stat:hover {
  opacity: 1;
  transform: translateY(-1px);
}

.rank-stat.active {
  opacity: 1;
  position: relative;
}

.rank-stat i {
  font-size: 1.25rem;
}

.rank-details {
  display: flex;
  flex-direction: column;
  flex-shrink: 0;
}

.rank-label {
  font-size: 0.6rem;
  font-weight: 600;
  text-transform: uppercase;
  color: var(--establishment-header-text);
  opacity: 0.85;
  letter-spacing: 0.05em;
  white-space: nowrap;
}

.rank-val {
  font-size: 0.9rem;
  font-weight: 700;
  color: var(--establishment-header-text);
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}

.rank-val small {
  font-size: 0.75rem;
  font-weight: 500;
  opacity: 0.8;
}

.pi.gold {
  color: #ffd700;
}
.pi.silver {
  color: #cbd5e1;
}
.pi.bronze {
  color: #fbbf24;
}
.pi.neutral {
  color: #94a3b8;
}

.pi-users-group {
  color: var(--text-muted);
}

/* ── LINHA DE STATUS ── */
.status-chips-row {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}

.status-group {
  display: flex;
  align-items: center;
  gap: 0.4rem;
}

.status-group-divider {
  width: 1px;
  height: 1.2rem;
  background: var(--card-border);
  flex-shrink: 0;
}

/* ── STATUS LABELED ── */
.status-labeled {
  display: flex;
  align-items: center;
  gap: 0.4rem;
}

.status-label-text {
  font-size: 0.72rem;
  font-weight: 500;
  color: var(--text-muted);
  white-space: nowrap;
}

/* ── STATUS CHIPS (Conexão MS / Situação RF) ── */
.status-chip {
  font-size: 0.72rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  gap: 0.3rem;
}

/* chip-* removido — usa classes globais status-* de components.css */

.status-chip i {
  font-size: 13px;
  line-height: 1;
}

/* ── CHIPS COMPOSTOS (estrutura compartilhada) ── */
.compound-chip,
.institution-chip {
  display: flex;
  flex-direction: column;
  justify-content: center;
  gap: 0.15rem;
  padding: 0.3rem 0.7rem;
  border-radius: 8px;
  border: 1px solid transparent;
  cursor: default;
  min-height: 2.4rem; /* altura uniforme para todos os chips */
}

/* ── LABELS INTERNOS (linha de cima — microtype) ── */
.compound-label,
.institution-label {
  font-size: 0.58rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.07em;
  opacity: 0.8;
  line-height: 1;
  display: flex;
  align-items: center;
  gap: 0.25rem;
  white-space: nowrap;
}

.compound-label i,
.institution-label i {
  font-size: 0.58rem; /* icon alinhado com o texto da label */
  line-height: 1;
}

/* ── OVERRIDE STATUS-SECONDARY PARA SOLIDIFICAR CONTRA O HEADER ── */
.institution-chip.status-secondary {
  background: color-mix(
    in srgb,
    var(--text-muted) 14%,
    var(--establishment-header-bg)
  ) !important;
  border-color: color-mix(
    in srgb,
    var(--text-muted) 25%,
    var(--establishment-header-bg)
  ) !important;
}

/* ── BADGE CLICÁVEL (Grande Rede com múltiplos estabelecimentos) ── */
.institution-chip.clickable-badge {
  cursor: pointer;
  user-select: none;
  transition:
    background 0.18s ease,
    border-color 0.18s ease,
    transform 0.18s ease,
    box-shadow 0.18s ease,
    filter 0.18s ease;
}

.institution-chip.clickable-badge:hover {
  transform: translateY(-1px);
  filter: brightness(1.08);
  box-shadow: 0 2px 8px color-mix(in srgb, var(--primary-color) 18%, transparent);
}

.institution-chip.clickable-badge:active {
  transform: translateY(0);
  filter: brightness(0.96);
}

/* ── VALORES INTERNOS (linha de baixo) ── */
.institution-value {
  font-size: 0.78rem;
  font-weight: 800;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  line-height: 1;
  white-space: nowrap;
}

/* ── SCORE COMPOSTO ── */
.compound-values {
  display: flex;
  align-items: center;
  gap: 0.3rem;
  line-height: 1;
}

.compound-score {
  font-size: 0.82rem;
  font-weight: 800;
  letter-spacing: -0.01em;
  line-height: 1;
}

.compound-sep {
  opacity: 0.35;
  font-size: 0.7rem;
}

.compound-class {
  font-size: 0.75rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  line-height: 1;
}

/* ── RISK CONTEXT PANEL ─────────────────────────────────── */
.risk-context-panel {
  display: flex;
  flex-direction: row;
  flex: 1;
  align-self: stretch;
  min-width: 550px;
  border: 1px solid var(--card-border);
  border-left-width: 3px;
  border-left-color: var(--primary-color);
  border-radius: 10px;
  overflow: hidden;
  transition: border-color 0.3s ease;
}

.risk-context-content {
  display: flex;
  min-width: 390px;
  flex: 1;
  flex-direction: column;
}

.risk-context-panel.risk-high    { border-left-color: var(--risk-high); }
.risk-context-panel.risk-critical { border-left-color: var(--risk-critical); }
.risk-context-panel.risk-medium  { border-left-color: var(--risk-medium); }
.risk-context-panel.risk-low     { border-left-color: var(--risk-low); }

.rcp-period {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  padding: 0.25rem 0.65rem 0.23rem 0.7rem;
  background: color-mix(in srgb, var(--primary-color) 5%, var(--establishment-header-bg));
  border-bottom: 1px solid var(--card-border);
  transition: opacity 0.2s ease, filter 0.2s ease;
}

.risk-context-panel.risk-high    .rcp-period { background: color-mix(in srgb, var(--risk-high) 6%, var(--establishment-header-bg)); }
.risk-context-panel.risk-critical .rcp-period { background: color-mix(in srgb, var(--risk-critical) 6%, var(--establishment-header-bg)); }
.risk-context-panel.risk-medium  .rcp-period { background: color-mix(in srgb, var(--risk-medium) 6%, var(--establishment-header-bg)); }
.risk-context-panel.risk-low     .rcp-period { background: color-mix(in srgb, var(--risk-low) 6%, var(--establishment-header-bg)); }

.rcp-period--loading {
  opacity: 0.75;
  filter: saturate(0.7);
}

.rcp-period i {
  font-size: 0.68rem;
  color: var(--primary-color);
  flex-shrink: 0;
}

.risk-context-panel.risk-high    .rcp-period i { color: var(--risk-high); }
.risk-context-panel.risk-critical .rcp-period i { color: var(--risk-critical); }
.risk-context-panel.risk-medium  .rcp-period i { color: var(--risk-medium); }
.risk-context-panel.risk-low     .rcp-period i { color: var(--risk-low); }

.rcp-period-label {
  font-size: 0.64rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.07em;
  color: var(--text-muted);
  white-space: nowrap;
}

.rcp-period-value {
  font-size: 0.82rem;
  font-weight: 600;
  color: var(--establishment-header-text);
  opacity: 1;
  white-space: nowrap;
}

.rcp-metrics {
  display: flex;
  flex-direction: column;
  flex: 1;
  justify-content: flex-start;
  padding: 0.35rem 0.75rem 0.45rem;
  gap: 0;
}

.rcp-financials {
  margin-top: auto;
}

.rcp-item {
  display: flex;
  flex-direction: column;
  padding: 0.08rem 0.65rem;
  transition: opacity 0.25s ease, filter 0.25s ease;
}

.rcp-divider {
  width: 1px;
  height: 1.8rem;
  background: var(--card-border);
  flex-shrink: 0;
  margin: 0 0.1rem;
}

.rcp-label {
  font-size: 0.67rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--text-muted);
  margin-bottom: 0.12rem;
  white-space: nowrap;
}

.rcp-value {
  font-size: 1rem;
  font-weight: 600;
  color: var(--establishment-header-text);
  line-height: 1.1;
  letter-spacing: -0.02em;
  display: flex;
  align-items: baseline;
  gap: 0.3rem;
  white-space: nowrap;
}

.rcp-value--neutral {
  opacity: 0.7;
}

.rcp-badge {
  font-size: 0.6rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--text-muted);
  padding: 0.1rem 0.4rem;
  border-radius: 4px;
  border: 1px solid color-mix(in srgb, var(--text-muted) 30%, transparent);
  background: color-mix(in srgb, var(--text-muted) 8%, transparent);
}

.risk-context-panel.risk-high    .rcp-badge { color: var(--risk-high);     border-color: color-mix(in srgb, var(--risk-high) 35%, transparent);     background: color-mix(in srgb, var(--risk-high) 12%, transparent); }
.risk-context-panel.risk-critical .rcp-badge { color: var(--risk-critical); border-color: color-mix(in srgb, var(--risk-critical) 35%, transparent); background: color-mix(in srgb, var(--risk-critical) 12%, transparent); }
.risk-context-panel.risk-medium  .rcp-badge { color: var(--risk-medium);   border-color: color-mix(in srgb, var(--risk-medium) 35%, transparent);   background: color-mix(in srgb, var(--risk-medium) 12%, transparent); }
.risk-context-panel.risk-low     .rcp-badge { color: var(--risk-low);      border-color: color-mix(in srgb, var(--risk-low) 35%, transparent);      background: color-mix(in srgb, var(--risk-low) 12%, transparent); }

.rcp-score-row {
  display: flex;
  align-items: center;
}

.rcp-score-row .rcp-item {
  padding-left: 0;
}

.rcp-progress-wrap {
  display: flex;
  flex-direction: column;
  gap: 0.28rem;
  transition: opacity 0.25s ease, filter 0.25s ease;
}

.rcp-progress-header {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 0.3rem;
}

.rcp-pct-label {
  font-size: 0.6rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--text-muted);
}

.rcp-progress-track {
  height: 6px;
  background: color-mix(in srgb, var(--text-muted) 18%, transparent);
  border-radius: 999px;
  overflow: hidden;
}

.rcp-progress-fill {
  height: 100%;
  background: var(--primary-color);
  border-radius: 999px;
  transition: width 0.5s ease;
}

.risk-context-panel.risk-high    .rcp-progress-fill { background: var(--risk-high); }
.risk-context-panel.risk-critical .rcp-progress-fill { background: var(--risk-critical); }
.risk-context-panel.risk-medium  .rcp-progress-fill { background: var(--risk-medium); }
.risk-context-panel.risk-low     .rcp-progress-fill { background: var(--risk-low); }

.rcp-pct-inline {
  font-size: 1.1rem;
  font-weight: 600;
  color: var(--text-muted);
  opacity: 0.9;
}

.risk-context-panel.risk-high    .rcp-pct-inline { color: var(--risk-high); }
.risk-context-panel.risk-critical .rcp-pct-inline { color: var(--risk-critical); }
.risk-context-panel.risk-medium  .rcp-pct-inline { color: var(--risk-medium); }
.risk-context-panel.risk-low     .rcp-pct-inline { color: var(--risk-low); }

.rcp-financials {
  display: flex;
  align-items: center;
}

.rcp-financials .rcp-item:first-child {
  padding-left: 0;
}

.list-actions--vertical {
  display: flex;
  flex-direction: row;
  align-items: center;
  gap: 0.5rem;
  padding-left: 1rem;
  margin-left: auto;
  border-left: 1px solid var(--card-border);
}

.back-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 30px;
  height: 30px;
  flex-shrink: 0;
  border-radius: 8px;
  border: 1px solid color-mix(in srgb, var(--text-muted) 25%, transparent);
  background: color-mix(in srgb, var(--text-muted) 6%, transparent);
  color: var(--text-muted);
  cursor: pointer;
  transition: all 0.2s ease;
}

.back-btn i {
  font-size: 0.8rem;
}

.back-btn:hover {
  background: color-mix(in srgb, var(--text-muted) 14%, transparent);
  border-color: color-mix(in srgb, var(--text-muted) 50%, transparent);
  color: var(--text-color-85);
  transform: translateX(-2px);
}
</style>
