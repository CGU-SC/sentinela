<script setup>
import { computed, ref, watch } from "vue";
import TabPlaceholder from './TabPlaceholder.vue';
import { storeToRefs } from 'pinia';
import { useCnpjDetailStore } from '@/stores/cnpjDetail';
import { useStableTabState } from '@/composables/useStableTabState';

import CRMKpiGrid from './CRMKpiGrid.vue';
import CRMCronologia from './CRMCronologia.vue';
import CRMPrescritoresTable from './CRMPrescritoresTable.vue';
import MortalityTab from './MortalityTab.vue';
import { useFilterStore } from "@/stores/filters";
import { useFormatting } from "@/composables/useFormatting";
import { useFilterParameters } from "@/composables/useFilterParameters";

const { formatarData, toLocalISO } = useFormatting();

const formattedPeriod = computed(() => {
  const [start, end] = filterStore.periodo ?? [];
  if (!start || !end) return null;
  return { start: formatarData(toLocalISO(start)), end: formatarData(toLocalISO(end)) };
});

const props = defineProps({
  cnpj: { type: String, required: true },
  isActive: { type: Boolean, default: false },
  periodSummary: { type: Object, default: null },
  periodLoading: { type: Boolean, default: false },
  razaoSocial: { type: String, default: '' },
});

const cnpjDetailStore = useCnpjDetailStore();
const { prescritoresData, prescritoresLoading, prescritoresError, activeCrmViewMode, indicadoresData, indicadoresLoadedKey, indicadoresLoading, indicadoresError } = storeToRefs(cnpjDetailStore);
// ── Flicker-Free Cache ────────────────────────────────────────────────────
const filterStore = useFilterStore();
const { getApiParams } = useFilterParameters();
const {
  cachedData: cachedPrescritoresData,
  isRefreshing,
} = useStableTabState(prescritoresData, prescritoresLoading, prescritoresError);



// ── Estado de Navegação (Agora via Store) ─────────────────────────────────
const activeKpiFilter = ref(null);
const mortalityTabRef = ref(null);
const openedCrmViews = ref(new Set(['medicos', activeCrmViewMode.value]));

function markCrmViewOpened(mode) {
  if (!mode) return;
  openedCrmViews.value = new Set([...openedCrmViews.value, mode]);
}

function hasOpenedCrmView(mode) {
  return openedCrmViews.value.has(mode);
}

function loadCurrentViewIfActive() {
  if (!props.isActive) return;
  const { inicio, fim } = getApiParams();
  cnpjDetailStore.ensureTabData('indicadores', props.cnpj, inicio, fim);
  if (['cronologia', 'falecidos'].includes(activeCrmViewMode.value)) {
    cnpjDetailStore.ensureTabData('autorizacoes', props.cnpj, inicio, fim);
  }
}

watch(activeCrmViewMode, (mode) => {
  markCrmViewOpened(mode);
}, { immediate: true });

watch(activeCrmViewMode, () => {
  loadCurrentViewIfActive();
});

watch(() => props.cnpj, () => {
  openedCrmViews.value = new Set(['medicos', activeCrmViewMode.value]);
});

watch(() => props.isActive, (active) => {
  if (!active) return;
  loadCurrentViewIfActive();
});

// ── Dados Base ────────────────────────────────────────────────────────────
const summary = computed(() => cachedPrescritoresData.value?.summary || {});
const crmsInteresse = computed(() => cachedPrescritoresData.value?.crms_interesse || []);
// Eixo de tempo comum da coluna "Atuação na farmácia" (competências YYYYMM).
const periodoCompetencias = computed(() => {
  if (!crmsInteresse.value.length) return null;
  const inicio = summary.value.competencia_inicio_periodo;
  const fim = summary.value.competencia_fim_periodo;
  if (inicio == null || fim == null) {
    throw new Error('Contrato inválido em crm-data: summary sem competencia_inicio_periodo/competencia_fim_periodo.');
  }
  return { inicio: Number(inicio), fim: Number(fim) };
});
const serieMensalFarmacia = computed(() => {
  if (!crmsInteresse.value.length) return [];
  const serie = summary.value.serie_mensal_farmacia;
  if (!Array.isArray(serie)) {
    throw new Error('Contrato inválido em crm-data: summary sem serie_mensal_farmacia.');
  }
  return serie;
});
const noMovementInPeriod = computed(() =>
  !props.periodLoading &&
  Boolean(props.periodSummary) &&
  Number(props.periodSummary.totalMov ?? 0) === 0
);

function requireLoadedSummaryNumber(field) {
  if (!cachedPrescritoresData.value) return 0;
  if (summary.value[field] == null) {
    throw new Error(`Contrato invalido em crm-data: summary.${field} obrigatorio.`);
  }
  return Number(summary.value[field]);
}

function requireCrmAlertCount(m, field) {
  if (m[field] == null) {
    throw new Error(`Contrato invalido em crm-data: ${field} obrigatorio para ${m.id_medico}.`);
  }
  return Number(m[field]);
}

// ── KPIs (mantidos aqui para defineExpose) ────────────────────────────────
const concentracaoTop1 = computed(() => summary.value.pct_concentracao_top1 || 0);
const concentracaoTop5 = computed(() => summary.value.pct_concentracao_top5 || 0);

const valorTop1 = computed(() => crmsInteresse.value.length > 0 ? crmsInteresse.value[0].vl_total_prescricoes || 0 : 0);
const valorTop5 = computed(() => crmsInteresse.value.slice(0, 5).reduce((acc, curr) => acc + (curr.vl_total_prescricoes || 0), 0));

const doctorsIntensivaLocal  = computed(() => crmsInteresse.value.filter(m => m.flag_robo > 0));
const doctorsIntensivaBrasil = computed(() => crmsInteresse.value.filter(m => m.flag_robo_oculto > 0));
const qtdPrescrIntensivaLocal   = computed(() => doctorsIntensivaLocal.value.length);
const qtdPrescrIntensivaOcultos = computed(() => doctorsIntensivaBrasil.value.length);
const qtdPrescrIntensivaTotal   = computed(() => {
  const ids = new Set([...doctorsIntensivaLocal.value.map(m => m.id_medico), ...doctorsIntensivaBrasil.value.map(m => m.id_medico)]);
  return ids.size;
});

const qtdCrmInvalido          = computed(() => crmsInteresse.value.filter(m => m.flag_crm_invalido > 0).length);
const qtdPrescrAntesRegistro  = computed(() => crmsInteresse.value.filter(m => m.flag_prescricao_antes_registro > 0).length);
const totalIrregularesCfm     = computed(() => qtdCrmInvalido.value + qtdPrescrAntesRegistro.value);
const indicadorCrmsIrregulares = computed(() => {
  const { inicio, fim } = getApiParams();
  const requestKey = `${props.cnpj.replace(/\D/g, '').padStart(14, '0')}|${inicio || ''}|${fim || ''}`;
  if (indicadoresLoadedKey.value !== requestKey) return null;
  const indicador = indicadoresData.value?.indicadores?.crms_irregulares;
  if (indicador?.valor == null || indicador?.valor_financeiro == null) {
    throw new Error('Contrato inválido: indicador de CRMs irregulares sem percentual ou valor financeiro.');
  }
  return indicador;
});
const pctFraudeCrm            = computed(() => indicadorCrmsIrregulares.value?.valor ?? null);
const valorFraudeCrm          = computed(() => indicadorCrmsIrregulares.value?.valor_financeiro ?? null);

const qtdCrmExclusivo         = computed(() => crmsInteresse.value.filter(m => m.flag_crm_exclusivo > 0).length);
const qtdLancamentosAgrupados = computed(() => crmsInteresse.value.filter(m => m.alerta_concentracao_unico_crm).length);
const totalSurtosCnpj         = computed(() => requireLoadedSummaryNumber('qtd_alertas_cnpj_multiplo'));
const diasComSurtosCnpj       = computed(() => requireLoadedSummaryNumber('qtd_dias_alertas_cnpj_multiplo'));
const qtdAcima400km           = computed(() => crmsInteresse.value.filter(m => m.alerta5_geografico).length);

// Objeto passado como prop para CRMKpiGrid
const kpiData = computed(() => ({
  concentracaoTop1: concentracaoTop1.value,
  concentracaoTop5: concentracaoTop5.value,
  valorTop1: valorTop1.value,
  valorTop5: valorTop5.value,
  idTop1Prescritor: summary.value.id_top1_prescritor,
  qtdPrescrIntensivaTotal: qtdPrescrIntensivaTotal.value,
  qtdPrescrIntensivaLocal: qtdPrescrIntensivaLocal.value,
  qtdPrescrIntensivaOcultos: qtdPrescrIntensivaOcultos.value,
  qtdLancamentosAgrupados: qtdLancamentosAgrupados.value,
  qtdCrmExclusivo: qtdCrmExclusivo.value,
  totalIrregularesCfm: totalIrregularesCfm.value,
  qtdCrmInvalido: qtdCrmInvalido.value,
  qtdPrescrAntesRegistro: qtdPrescrAntesRegistro.value,
  valorFraudeCrm: valorFraudeCrm.value,
  pctFraudeCrm: pctFraudeCrm.value,
  indicadorCrmCarregando: indicadoresLoading.value,
  indicadorCrmErro: Boolean(indicadoresError.value),
  qtdAcima400km: qtdAcima400km.value,
  totalSurtosCnpj: totalSurtosCnpj.value,
  diasComSurtosCnpj: diasComSurtosCnpj.value,
}));

// ── Filtros de KPI ────────────────────────────────────────────────────────
const kpiFilters = {
  top1:        (m) => m.id_medico === crmsInteresse.value[0]?.id_medico,
  top5:        (m) => crmsInteresse.value.slice(0, 5).some(t => t.id_medico === m.id_medico),
  agrupamento: (m) => !!m.alerta_concentracao_unico_crm,
  intensiva:   (m) => m.flag_robo > 0 || m.flag_robo_oculto > 0,
  exclusivo:   (m) => m.flag_crm_exclusivo > 0,
  fraude_crm:  (m) => m.flag_crm_invalido > 0 || m.flag_prescricao_antes_registro > 0,
  distancia:   (m) => !!m.alerta5_geografico,
  surtos_cnpj: (m) => requireCrmAlertCount(m, 'qtd_alertas_crm_multiplos') > 0,
};

const kpiFilterLabels = {
  top1:        "Concentração TOP 1",
  top5:        "Concentração TOP 5",
  agrupamento: "Autorizações em Sequência (Único CRM)",
  intensiva:   ">30 Prescrições/Dia",
  exclusivo:   "CRM Exclusivo",
  fraude_crm:  "Fraudes CRM",
  distancia:   "Distância (>400km)",
  surtos_cnpj: "Autorizações em Sequência (Múltiplos CRMs)",
};

function setKpiFilter(key) {
  activeKpiFilter.value = activeKpiFilter.value === key ? null : key;
}

function clearFilters() {
  activeKpiFilter.value = null;
}

defineExpose({
  getSummary: () => summary.value,
  getCrmsInteresse: () => crmsInteresse.value,
  getKpis: () => ({
    concentracaoTop1: concentracaoTop1.value,
    concentracaoTop5: concentracaoTop5.value,
    qtdLancamentosAgrupados: qtdLancamentosAgrupados.value,
    qtdPrescrIntensivaLocal: qtdPrescrIntensivaLocal.value,
    qtdPrescrIntensivaOcultos: qtdPrescrIntensivaOcultos.value,
    qtdCrmExclusivo: qtdCrmExclusivo.value,
    totalIrregularesCfm: totalIrregularesCfm.value,
    qtdCrmInvalido: qtdCrmInvalido.value,
    qtdPrescrAntesRegistro: qtdPrescrAntesRegistro.value,
    valorTop1: valorTop1.value,
    valorTop5: valorTop5.value,
    qtdAcima400km: qtdAcima400km.value,
    totalSurtosCnpj: totalSurtosCnpj.value,
    diasComSurtosCnpj: diasComSurtosCnpj.value,
  }),
  hasFalecidosData: () => mortalityTabRef.value?.hasData?.() ?? false,
  getFalecidosSummary: () => mortalityTabRef.value?.getSummary?.() ?? null,
  getFalecidosAgrupados: () => mortalityTabRef.value?.getAgrupados?.() ?? [],
  getFalecidosRanking: () => mortalityTabRef.value?.getRanking?.() ?? [],
});
</script>

<template>
  <div class="crm-tab-container">
    <div
      v-if="prescritoresLoading && !cachedPrescritoresData && !prescritoresError"
      class="crm-initial-loading-sentinel"
      aria-hidden="true"
    />

    <TabPlaceholder
      v-else-if="prescritoresError"
      variant="error"
      icon="pi-exclamation-circle"
      title="Erro ao carregar"
      :description="prescritoresError"
    />

    <div v-else class="content-wrapper" :class="{ 'is-refreshing': isRefreshing }">
      <div class="view-mode-container animate-fade-in">
        <div class="view-mode-selector">
          <button class="view-mode-btn" :class="{ active: activeCrmViewMode === 'medicos' }" @click="cnpjDetailStore.setCrmViewMode('medicos')">
            <i class="pi pi-users" />
            <span>PERFIL DE CRMs</span>
          </button>
          <button class="view-mode-btn" :class="{ active: activeCrmViewMode === 'cronologia' }" @click="cnpjDetailStore.setCrmViewMode('cronologia')">
            <i class="pi pi-chart-line" />
            <span>LINHA DO TEMPO & RAIO-X</span>
          </button>
          <button class="view-mode-btn" :class="{ active: activeCrmViewMode === 'falecidos' }" @click="cnpjDetailStore.setCrmViewMode('falecidos')">
            <i class="pi pi-exclamation-triangle" />
            <span>FALECIDOS</span>
          </button>
        </div>
      </div>

      <div
        v-if="hasOpenedCrmView('medicos')"
        v-show="activeCrmViewMode === 'medicos'"
        class="medicos-view"
      >
        <TabPlaceholder
          v-if="cachedPrescritoresData && crmsInteresse.length === 0 && noMovementInPeriod"
          variant="info"
          icon="pi-chart-bar"
          title="Sem movimentação no período"
        >
          <template #description>
            Não foram encontradas movimentações financeiras para este CNPJ no período de <u>{{ formattedPeriod?.start }}</u> até <u>{{ formattedPeriod?.end }}</u>.
          </template>
        </TabPlaceholder>

        <TabPlaceholder
          v-else-if="cachedPrescritoresData && crmsInteresse.length === 0"
          variant="info"
          icon="pi-id-card"
          title="Sem prescrições no período"
        >
          <template #description>
            Não foram encontradas prescrições vinculadas a este CNPJ no período de <u>{{ formattedPeriod?.start }}</u> até <u>{{ formattedPeriod?.end }}</u>.
          </template>
        </TabPlaceholder>

        <template v-else>
          <CRMKpiGrid
            :kpi-data="kpiData"
            :active-kpi-filter="activeKpiFilter"
            @kpi-click="setKpiFilter"
          />
          <CRMPrescritoresTable
            :crms-interesse="crmsInteresse"
            :active-kpi-filter="activeKpiFilter"
            :kpi-filters="kpiFilters"
            :kpi-filter-labels="kpiFilterLabels"
            :current-cnpj="cnpj"
            :periodo-competencias="periodoCompetencias"
            :serie-mensal-farmacia="serieMensalFarmacia"
            @clear-filters="clearFilters"
          />
        </template>
      </div>

      <CRMCronologia
        v-if="hasOpenedCrmView('cronologia')"
        v-show="activeCrmViewMode === 'cronologia'"
        :cnpj="cnpj"
        :period-summary="periodSummary"
        :period-loading="periodLoading"
        :razao-social="razaoSocial"
      />

      <MortalityTab
        v-if="hasOpenedCrmView('falecidos')"
        v-show="activeCrmViewMode === 'falecidos'"
        ref="mortalityTabRef"
        :cnpj="cnpj"
        :period-summary="periodSummary"
        :period-loading="periodLoading"
        class="animate-fade-in"
      />
    </div>
  </div>
</template>

<style scoped>
.crm-tab-container {
  display: flex;
  flex-direction: column;
  gap: 1.5rem;
}

.content-wrapper {
  display: flex;
  flex-direction: column;
  gap: 1.25rem;
  width: 100%;
  align-items: stretch;
  transition: opacity 0.25s ease;
}
.content-wrapper.is-refreshing { opacity: 0.45; pointer-events: none; }

.medicos-view {
  display: flex;
  flex-direction: column;
  gap: 1.5rem;
}

.animate-fade-in { animation: fadeIn 0.3s ease-out; }
@keyframes fadeIn { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: translateY(0); } }

.view-mode-container { display: flex; flex-direction: column; align-items: center; margin: 0.5rem 0 1.5rem; padding: 0 1rem; }
.view-mode-selector {
  display: flex;
  background: color-mix(in srgb, var(--card-bg) 40%, transparent);
  backdrop-filter: blur(8px);
  -webkit-backdrop-filter: blur(8px);
  border: 1px solid color-mix(in srgb, white 5%, transparent);
  padding: 4px;
  border-radius: 12px;
  box-shadow: 0 2px 10px rgba(0,0,0,0.1);
  gap: 4px;
}
.view-mode-btn {
  display: flex;
  align-items: center;
  gap: 0.6rem;
  padding: 0.55rem 1.4rem;
  border: none;
  background: transparent;
  color: var(--text-secondary);
  font-size: 0.75rem;
  font-weight: 600;
  border-radius: 9px;
  cursor: pointer;
  transition: all 0.2s ease;
  letter-spacing: 0.02em;
}
.view-mode-btn i { font-size: 1rem; opacity: 0.6; }
.view-mode-btn:hover { color: var(--text-color-85); background: color-mix(in srgb, var(--text-color-85) 5%, transparent); }
.view-mode-btn.active { background: color-mix(in srgb, var(--primary-color) 10%, transparent); color: var(--primary-color); }
:global(.dark-mode) .view-mode-btn.active { background: color-mix(in srgb, var(--primary-color) 12%, transparent); color: white; box-shadow: none; }
.view-mode-btn.active i { opacity: 1; }
</style>
