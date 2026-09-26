<script setup>
import { computed, nextTick, onMounted, ref } from 'vue';
import { useRouter } from 'vue-router';
import { useToast } from 'primevue/usetoast';
import { useFilterStore } from '@/stores/filters';
import { useFarmaciaListsStore } from '@/stores/farmaciaLists';
import { useCnpjDetailStore } from '@/stores/cnpjDetail';
import { useMetodologiaConfigStore } from '@/stores/metodologiaConfig';
import { useFrozenData } from '@/composables/useFrozenData';
import { useFormatting } from '@/composables/useFormatting';
import { useStatusClass } from '@/composables/useStatusClass';
import { extractCnpjRaiz } from '@/composables/useParsing';
import { FILTER_OPTIONS } from '@/config/filterOptions';
import { AUDIT_THRESHOLDS, indicadorExtraColumns } from '@/config/riskConfig';
import { GENERIC_INDICATOR_DETAIL_KEYS } from '@/config/indicatorDetailConfig';
import DataTable from 'primevue/datatable';
import Column from 'primevue/column';
import Tag from 'primevue/tag';
import IndicatorDetailDialog from '@/views/components/cnpj/IndicatorDetailDialog.vue';
import GeographicDispersionDialog from '@/views/components/cnpj/GeographicDispersionDialog.vue';
import ClinicalIncompatibilityDialog from '@/views/components/cnpj/ClinicalIncompatibilityDialog.vue';
import ObservationDialog from '@/views/components/cnpj/ObservationDialog.vue';
import { createCnpjPerfSession, logCnpjPerf } from '@/utils/cnpjPerfLogger';
import { establishmentTableTooltip, establishmentRiskTooltip } from '@/config/establishmentTableTooltipConfig';

const props = defineProps({
  /** Array de IndicadorCnpjRowSchema */
  cnpjs: { type: Array, default: () => [] },
  /** Formato de valor: 'pct' | 'pct3' | 'val' | 'dec' */
  formato: { type: String, default: 'dec' },
  /** Chave do indicador */
  indicadorKey: { type: String, default: null },
  isLoading: { type: Boolean, default: false },
  indicadorLabel: { type: String, default: 'Indicador' },
  /**
   * Quando true, a tabela assume sua altura natural em vez de reservar
   * espaco para 20 linhas. Usado em modais/containers com altura limitada.
   * Aplicado via CSS variable `--risk-table-min-h` que sobrescreve o
   * min-height do .p-datatable-wrapper.
   */
  compact: { type: Boolean, default: false },
  totalRecords: { type: Number, default: 0 },
  first: { type: Number, default: 0 },
  rows: { type: Number, default: 20 },
  sortField: { type: String, default: 'val_sem_comp' },
  sortOrder: { type: Number, default: -1 },
  tableKpis: { type: Object, default: null },
  selectedRegiaoNome: { type: String, default: null },
  selectedMunicipioNome: { type: String, default: null },
});

const emit = defineEmits(['lazy-load', 'clear-regiao-filter', 'clear-municipio-filter']);
const metodologiaConfig = useMetodologiaConfigStore();
const auditHighValue = computed(() =>
  metodologiaConfig.loaded
    ? metodologiaConfig.auditHighValue
    : AUDIT_THRESHOLDS.HIGH_VALUE,
);

// `pt` (passthrough) do PrimeVue DataTable para sobrescrever o
// min-height do .p-datatable-wrapper via inline style. Aplicado
// diretamente no DOM gerado pelo PrimeVue, sem depender de CSS
// variable, heranca ou cascata — funciona mesmo com Teleport e
// Shadow DOM.
// Quando `compact=true` (usado em modais/containers com altura
// limitada), a tabela assume sua altura natural. Default preserva
// o comportamento atual (reserva espaco para 20 linhas) na
// EstablishmentsView.
const dataTablePt = computed(() => ({
  wrapper: {
    style: {
      minHeight: props.compact ? '0' : 'calc(20 * 2.625rem)',
    },
  },
}));

onMounted(() => {
  metodologiaConfig.ensureLoaded().catch((error) => {
    console.warn('[EstablishmentRiskTable] Não foi possível carregar a configuração metodológica.', error);
  });
});

const router = useRouter();
const toast = useToast();
const filterStore = useFilterStore();
const farmaciaLists = useFarmaciaListsStore();
const cnpjDetailStore = useCnpjDetailStore();
const { formatCurrencyFull, toLocalISO } = useFormatting();
const { conexaoMsClass } = useStatusClass();
const copiedKey = ref(null);
const showObservationDialog = ref(false);
const observationCnpj = ref('');
const observationEntityName = ref('');

// ── Detalhamento de Indicador por linha ──────────────────
const showGenericDetailDialog = ref(false);
const showGeographicDetailDialog = ref(false);
const showClinicalDetailDialog = ref(false);
const detailCnpj = ref('');
const loadingDetailCnpj = ref(null);
const detailPerfSession = ref(null);

const canShowDetailButton = computed(() => {
  const key = props.indicadorKey;
  return key === 'dispersao_geografica'
    || key === 'incompatibilidade_patologica'
    || GENERIC_INDICATOR_DETAIL_KEYS.includes(key);
});

function waitForDialogPaint() {
  return nextTick().then(() => new Promise((resolve) => {
    requestAnimationFrame(() => {
      requestAnimationFrame(resolve);
    });
  }));
}

async function openDetailForRow(cnpj) {
  if (!cnpj || loadingDetailCnpj.value) return;
  const key = props.indicadorKey;
  if (!key) return;

  const cleanCnpj = String(cnpj).replace(/\D/g, '');
  const perfSession = createCnpjPerfSession(cleanCnpj);
  detailPerfSession.value = perfSession;
  loadingDetailCnpj.value = cleanCnpj;
  detailCnpj.value = cleanCnpj;

  const [start, end] = filterStore.periodo ?? [];
  const inicio = start ? toLocalISO(start) : null;
  const fim = end ? toLocalISO(end) : null;
  const baseDetail = {
    origem: 'establishments_table',
    indicador: key,
    periodo_inicio: inicio,
    periodo_fim: fim,
  };

  logCnpjPerf(perfSession, 'indicator_detail_button_clicked', baseDetail);

  try {
    if (key === 'dispersao_geografica') {
      logCnpjPerf(perfSession, 'indicator_detail_requests_started', {
        ...baseDetail,
        tipo_modal: 'geografico',
        chamadas: 2,
        endpoints: ['geografico/origem-uf', 'geografico/benchmark-local'],
      });
      await Promise.all([
        cnpjDetailStore.fetchGeograficoOrigemUf(cleanCnpj, inicio, fim),
        cnpjDetailStore.fetchGeograficoBenchmarkLocal(cleanCnpj, inicio, fim),
      ]);
      logCnpjPerf(perfSession, 'indicator_detail_requests_finished', {
        ...baseDetail,
        tipo_modal: 'geografico',
        chamadas: 2,
      });
      showGeographicDetailDialog.value = true;
      logCnpjPerf(perfSession, 'indicator_detail_dialog_state_set', {
        ...baseDetail,
        tipo_modal: 'geografico',
      });
      await waitForDialogPaint();
      logCnpjPerf(perfSession, 'indicator_detail_dialog_painted', {
        ...baseDetail,
        tipo_modal: 'geografico',
      });
    } else if (key === 'incompatibilidade_patologica') {
      logCnpjPerf(perfSession, 'indicator_detail_requests_started', {
        ...baseDetail,
        tipo_modal: 'clinico',
        chamadas: 3,
        endpoints: [
          'indicadores/benchmark-local',
          'indicadores/evolucao-benchmark',
          'clinico/incompatibilidades',
        ],
      });
      await Promise.all([
        cnpjDetailStore.fetchIndicadorBenchmarkLocal(cleanCnpj, key, inicio, fim),
        cnpjDetailStore.fetchIndicadorEvolucaoBenchmark(cleanCnpj, key, inicio, fim),
        cnpjDetailStore.fetchIncompatibilidadePatologica(cleanCnpj, inicio, fim),
      ]);
      logCnpjPerf(perfSession, 'indicator_detail_requests_finished', {
        ...baseDetail,
        tipo_modal: 'clinico',
        chamadas: 3,
      });
      showClinicalDetailDialog.value = true;
      logCnpjPerf(perfSession, 'indicator_detail_dialog_state_set', {
        ...baseDetail,
        tipo_modal: 'clinico',
      });
      await waitForDialogPaint();
      logCnpjPerf(perfSession, 'indicator_detail_dialog_painted', {
        ...baseDetail,
        tipo_modal: 'clinico',
      });
    } else if (GENERIC_INDICATOR_DETAIL_KEYS.includes(key)) {
      logCnpjPerf(perfSession, 'indicator_detail_requests_started', {
        ...baseDetail,
        tipo_modal: 'generico',
        chamadas: 2,
        endpoints: ['indicadores/benchmark-local', 'indicadores/evolucao-benchmark'],
      });
      const [b, e] = await Promise.all([
        cnpjDetailStore.fetchIndicadorBenchmarkLocal(cleanCnpj, key, inicio, fim),
        cnpjDetailStore.fetchIndicadorEvolucaoBenchmark(cleanCnpj, key, inicio, fim),
      ]);
      logCnpjPerf(perfSession, 'indicator_detail_requests_finished', {
        ...baseDetail,
        tipo_modal: 'generico',
        chamadas: 2,
        benchmark_ok: Boolean(b),
        evolucao_ok: Boolean(e),
      });
      if (!b || !e) {
        logCnpjPerf(perfSession, 'indicator_detail_data_unavailable', {
          ...baseDetail,
          tipo_modal: 'generico',
          benchmark_ok: Boolean(b),
          evolucao_ok: Boolean(e),
        });
        return;
      }
      showGenericDetailDialog.value = true;
      logCnpjPerf(perfSession, 'indicator_detail_dialog_state_set', {
        ...baseDetail,
        tipo_modal: 'generico',
      });
      await waitForDialogPaint();
      logCnpjPerf(perfSession, 'indicator_detail_dialog_painted', {
        ...baseDetail,
        tipo_modal: 'generico',
      });
    }
  } catch (error) {
    logCnpjPerf(perfSession, 'indicator_detail_failed', {
      ...baseDetail,
      erro: error?.message || String(error),
    });
    throw error;
  } finally {
    loadingDetailCnpj.value = null;
  }
}
const loadingRef = computed(() => props.isLoading);
const tableSnapshot = useFrozenData(
  () => ({
    cnpjs: props.cnpjs,
    totalRecords: props.totalRecords,
    first: props.first,
    rows: props.rows,
    sortField: props.sortField,
    sortOrder: props.sortOrder,
    tableKpis: props.tableKpis,
  }),
  loadingRef,
);

const extraColumns = computed(() => {
  return props.indicadorKey ? (indicadorExtraColumns[props.indicadorKey] || []) : [];
});

function formatValueExtra(valor, type) {
  if (valor == null) return '—';
  if (type === 'currency' || type === 'val') return formatCurrencyFull(valor);
  if (type === 'val_compact')                return formatCurrencyCompact(valor);
  if (type === 'number') return valor.toString();
  if (type === 'percentage' || type === 'pct') return valor.toFixed(2) + '%';
  return valor;
}

function formatValue(valor) {
  if (valor == null) return '—';
  const fmt = props.formato;
  if (fmt === 'pct')         return valor.toFixed(2) + '%';
  if (fmt === 'pct3')        return valor.toFixed(3) + '%';
  if (fmt === 'val')         return formatCurrencyFull(valor);
  if (fmt === 'val_compact') return formatCurrencyCompact(valor);
  return valor.toFixed(2);
}

function formatCurrencyCompact(valor) {
  if (valor == null) return '—';

  const numericValue = Number(valor);
  if (!Number.isFinite(numericValue)) return '—';

  const absValue = Math.abs(numericValue);
  const compactRules = [
    { limit: 1_000_000_000, divisor: 1_000_000_000, suffix: 'bi' },
    { limit: 1_000_000, divisor: 1_000_000, suffix: 'mi' },
    { limit: 1_000, divisor: 1_000, suffix: 'k' },
  ];
  const rule = compactRules.find(item => absValue >= item.limit);

  if (!rule) return formatCurrencyFull(numericValue);

  const scaledValue = numericValue / rule.divisor;
  const formattedValue = scaledValue.toLocaleString('pt-BR', {
    minimumFractionDigits: 0,
    maximumFractionDigits: Math.abs(scaledValue) < 10 ? 1 : 0,
  });

  return `R$ ${formattedValue}${rule.suffix}`;
}

function benchmarkLabel(row) {
  return String(row?.benchmark_escopo ?? '').toUpperCase() === 'UF' ? 'UF' : 'região';
}

function benchmarkValue(row) {
  return row?.med_benchmark ?? row?.med_reg;
}

function statusClass(status) {
  switch (status) {
    case 'CRÍTICO': return 'status-danger';
    case 'ATENÇÃO':  return 'status-warn';
    case 'NORMAL':   return 'status-success';
    default:         return 'status-secondary';
  }
}

function goToDetail(event) {
  if (event.originalEvent?.target?.closest('.clickable-badge, .copy-btn, .row-action-btn')) return;
  router.push({ name: 'EstablishmentDetail', params: { cnpj: event.data.cnpj } });
}

async function toggleFavoriteForRow(row) {
  const saved = await farmaciaLists.toggleInteresse(row.cnpj, row.razao_social);
  // null = remoção cancelada pelo usuário no diálogo de evidências.
  if (saved === false && farmaciaLists.loadState === 'ready') {
    toast.add({
      severity: 'error',
      summary: 'Favorito não alterado',
      detail: farmaciaLists.error || 'Não foi possível salvar a alteração.',
      life: 5000,
    });
  }
}

function openObservationForRow(row) {
  if (!farmaciaLists.canEdit || !farmaciaLists.isInteresse(row.cnpj)) return;
  observationCnpj.value = String(row.cnpj);
  observationEntityName.value = row.razao_social || row.cnpj;
  showObservationDialog.value = true;
}

function copyAndSignal(text, key) {
  if (!text) return;
  navigator.clipboard.writeText(text);
  copiedKey.value = key;
  setTimeout(() => {
    if (copiedKey.value === key) copiedKey.value = null;
  }, 2000);
}

function normalizeToOption(options, raw) {
  return options.find(o => o.toLowerCase() === raw?.toLowerCase()) ?? raw;
}

function applyFilter(field, value) {
  if (field === 'grandeRede') {
    const valStr = typeof value === 'boolean' ? (value ? 'Sim' : 'Não') : value;
    filterStore.selectedGrandeRede = normalizeToOption(FILTER_OPTIONS.grandeRede, valStr);
  }
  if (field === 'conexaoMS') {
    const valStr = typeof value === 'boolean' ? (value ? 'Ativa' : 'Inativa') : value;
    filterStore.selectedMS = normalizeToOption(FILTER_OPTIONS.ms, valStr);
  }
}

function onLazyLoad(event) {
  emit('lazy-load', event);
}

const tableFooter = computed(() => {
  const totalSemComprovacao = Number(tableSnapshot.value.tableKpis?.total_sem_comprovacao ?? 0);
  const totalMov = Number(tableSnapshot.value.tableKpis?.total_mov ?? 0);

  return {
    totalSemComprovacao: formatCurrencyCompact(totalSemComprovacao),
    totalSemComprovacaoFull: formatCurrencyFull(totalSemComprovacao),
    totalMov: formatCurrencyCompact(totalMov),
    totalMovFull: formatCurrencyFull(totalMov),
  };
});

const indicatorColumnHeader = computed(() => {
  const label = props.indicadorLabel?.trim() || 'Indicador';
  if (label.toLowerCase() === 'crescimento semestral atípico') return 'Crescimento Semestral';
  if (label.toLowerCase() === 'dispersão interestadual') return 'Vendas para Outras UFs';
  return label;
});
</script>

<template>
  <div class="ind-table-card">
    <div class="section-header">
      <div class="header-icon-box">
        <i class="pi pi-list" />
      </div>
      <div class="header-text-box">
        <h3>Farmácias por Indicador</h3>
        <span class="subtitle">
          {{ indicadorLabel }} — {{ tableSnapshot.totalRecords }} estabelecimentos
        </span>
      </div>
      <div v-if="selectedRegiaoNome || selectedMunicipioNome" class="header-filter-chips">
        <div v-if="selectedRegiaoNome" class="scope-filter-chip">
          <i class="pi pi-directions" />
          <span>Região: <strong>{{ selectedRegiaoNome }}</strong></span>
          <button class="chip-clear" aria-label="Limpar Região" @click="$emit('clear-regiao-filter')" v-tooltip.top="establishmentTableTooltip('clearRegion')">
            <i class="pi pi-times" />
          </button>
        </div>

        <div v-if="selectedMunicipioNome" class="scope-filter-chip">
          <i class="pi pi-map-marker" />
          <span>Município: <strong>{{ selectedMunicipioNome }}</strong></span>
          <button class="chip-clear" aria-label="Limpar Município" @click="$emit('clear-municipio-filter')" v-tooltip.top="establishmentTableTooltip('clearMunicipality')">
            <i class="pi pi-times" />
          </button>
        </div>
      </div>
    </div>

    <DataTable
      :value="tableSnapshot.cnpjs"
      size="small"
      stripedRows
      removableSort
      paginator
      lazy
      :first="tableSnapshot.first"
      :rows="tableSnapshot.rows"
      :totalRecords="tableSnapshot.totalRecords"
      :sortField="tableSnapshot.sortField"
      :sortOrder="tableSnapshot.sortOrder"
      :pt="dataTablePt"
      class="enterprise-table ind-cnpj-table clickable-rows"
      @page="onLazyLoad"
      @sort="onLazyLoad"
      @row-click="goToDetail"
    >
      <!-- Razão Social + CNPJ + Município -->
      <Column
        field="razao_social"
        sortable
        headerClass="col-name"
        bodyClass="col-name"
      >
        <template #header>
          <span v-tooltip.top="establishmentTableTooltip('nameColumn')">Razão Social</span>
        </template>
        <template #body="{ data }">
          <div class="razao-block">
            <span class="razao-nome-row">
              <span
                v-tooltip.top="establishmentTableTooltip(data.is_matriz ? 'matrix' : 'branch')"
                :class="data.is_matriz ? 'tipo-badge matriz' : 'tipo-badge filial'"
              >
                <i :class="data.is_matriz ? 'pi pi-home' : 'pi pi-building'" />
              </span>
              <span
                class="razao-social-cell"
                v-tooltip.top="data.razao_social != null ? establishmentTableTooltip('pharmacyName', data.razao_social) : null"
              >{{ data.razao_social ?? '—' }}</span>
            </span>
            <span class="cnpj-row">
              <span class="cnpj-text" v-tooltip.top="establishmentTableTooltip('cnpjValue', data.cnpj)">{{ data.cnpj }}</span>
              <i
                :class="['pi', copiedKey === data.cnpj + '-cnpj' ? 'pi-check text-success' : 'pi-copy', 'copy-btn']"
                v-tooltip.top="establishmentTableTooltip('copyCnpj')"
                @click.stop="copyAndSignal(data.cnpj, data.cnpj + '-cnpj')"
              />
            </span>
            <span class="loc-inline-row">
              <span class="loc-place">
                <span
                  class="municipio-inline-text"
                  v-tooltip.top="data.municipio != null ? establishmentTableTooltip('municipality', data.municipio) : null"
                >{{ data.municipio ?? '—' }}</span>
                <span class="uf-tag" v-tooltip.top="establishmentTableTooltip('stateValue', data.uf)">{{ data.uf }}</span>
              </span>
              <span
                class="row-actions"
                :class="{ 'row-actions--with-detail': canShowDetailButton }"
              >
                <button
                  v-if="canShowDetailButton"
                  type="button"
                  class="row-action-btn detail-action-btn"
                  :class="{ 'is-loading': loadingDetailCnpj === String(data.cnpj).replace(/\D/g, '') }"
                  :aria-label="`Ver detalhamento do indicador para ${data.razao_social || data.cnpj}`"
                  :disabled="Boolean(loadingDetailCnpj)"
                  v-tooltip.top="establishmentTableTooltip('indicatorDetails')"
                  @click.stop="openDetailForRow(data.cnpj)"
                >
                  <i :class="loadingDetailCnpj === String(data.cnpj).replace(/\D/g, '') ? 'pi pi-spin pi-spinner' : 'pi pi-chart-bar'" aria-hidden="true" />
                  <span>Ver indicador</span>
                </button>
                <button
                  type="button"
                  class="row-action-btn favorite-action-btn"
                  :class="{ 'is-favorite': farmaciaLists.isInteresse(data.cnpj) }"
                  :aria-label="`${farmaciaLists.isInteresse(data.cnpj) ? 'Remover dos' : 'Adicionar aos'} favoritos: ${data.razao_social || data.cnpj}`"
                  :aria-pressed="farmaciaLists.isInteresse(data.cnpj)"
                  :disabled="!farmaciaLists.canEdit"
                  v-tooltip.top="establishmentTableTooltip(farmaciaLists.isInteresse(data.cnpj) ? 'favoriteRemove' : 'favoriteAdd')"
                  @click.stop="toggleFavoriteForRow(data)"
                >
                  <i :class="farmaciaLists.isInteresse(data.cnpj) ? 'pi pi-star-fill' : 'pi pi-star'" aria-hidden="true" />
                </button>
                <button
                  v-if="farmaciaLists.isInteresse(data.cnpj)"
                  type="button"
                  class="row-action-btn observation-action-btn"
                  :class="{ 'has-observation': Boolean(farmaciaLists.getObservacao(data.cnpj)) }"
                  :aria-label="`${farmaciaLists.getObservacao(data.cnpj) ? 'Editar' : 'Adicionar'} anotação para ${data.razao_social || data.cnpj}`"
                  :disabled="!farmaciaLists.canEdit"
                  v-tooltip.top="establishmentTableTooltip(farmaciaLists.getObservacao(data.cnpj) ? 'observationEdit' : 'observationAdd')"
                  @click.stop="openObservationForRow(data)"
                >
                  <i :class="farmaciaLists.getObservacao(data.cnpj) ? 'pi pi-comment' : 'pi pi-pencil'" aria-hidden="true" />
                </button>
              </span>
            </span>
          </div>
        </template>
        <template #footer>
          <span class="table-total-label">TOTAL</span>
        </template>
      </Column>

      <!-- Colunas Dinâmicas Extras (Configuradas por Indicador) -->
      <Column
        v-for="col in extraColumns"
        :key="col.field"
        :field="`detalhes_extras.${col.field}`"
        :sortField="col.sortable ? col.sortField || col.field : undefined"
        :header="col.header"
        :sortable="col.sortable || false"
        headerClass="col-extra"
        bodyClass="col-extra"
        :style="{ minWidth: col.minWidth, width: col.width }"
      >
        <template #body="{ data }">
          <div :class="`text-${col.align || 'right'}`">
            {{ formatValueExtra(data.detalhes_extras?.[col.field], col.type) }}
          </div>
        </template>
        <template #footer>
          <span class="table-total-value">—</span>
        </template>
      </Column>

      <!-- Valor do indicador + Mediana regional -->
      <Column
        field="valor"
        sortable
        headerClass="col-indicator"
        bodyClass="col-indicator"
      >
        <template #header>
          <span class="indicator-column-title" v-tooltip.top="establishmentTableTooltip('indicatorColumn', indicatorColumnHeader)">
            {{ indicatorColumnHeader }}
          </span>
        </template>
        <template #body="{ data }">
          <div class="indicator-cell" :class="{ muted: data.valor == null }">
            <span class="indicator-value">{{ formatValue(data.valor) }}</span>
            <span class="indicator-median">{{ benchmarkLabel(data) }} {{ formatValue(benchmarkValue(data)) }}</span>
          </div>
        </template>
      </Column>

      <Column
        field="risco_benchmark"
        sortable
        headerClass="col-risk"
        bodyClass="col-risk"
      >
        <template #header>
          <span v-tooltip.top="establishmentTableTooltip('riskColumn')">Risco</span>
        </template>
        <template #body="{ data }">
          <div
            class="risk-cell"
            :class="{ muted: data.risco_benchmark == null }"
            v-tooltip.top="establishmentRiskTooltip({
              indicator: indicadorLabel,
              value: formatValue(data.valor),
              median: formatValue(benchmarkValue(data)),
              scope: benchmarkLabel(data),
              ratio: data.risco_benchmark,
              status: data.status,
            })"
          >
            <span
              v-if="data.risco_benchmark != null"
              class="risk-value"
              :class="statusClass(data.status)"
            >
              {{ data.risco_benchmark.toFixed(1) }}x
            </span>
            <span v-else>—</span>
            <span
              v-if="data.status"
              class="risk-status"
              :class="statusClass(data.status)"
            >
              {{ data.status }}
            </span>
          </div>
        </template>
      </Column>

      <!-- Valor Movimentado -->
      <Column
        field="valor_movimentado"
        header="Total Vendas"
        sortable
        headerClass="col-movement"
        bodyClass="col-movement"
      >
        <template #body="{ data }">
          <span
            class="movement-value"
            v-tooltip.top="data.valor_movimentado != null ? establishmentTableTooltip('totalSales', formatCurrencyFull(data.valor_movimentado)) : null"
          >
            {{ formatCurrencyCompact(data.valor_movimentado) }}
          </span>
        </template>
        <template #footer>
          <span
            class="movement-value table-total-movement"
            v-tooltip.top="establishmentTableTooltip('totalSalesFooter', tableFooter.totalMovFull)"
          >{{ tableFooter.totalMov }}</span>
        </template>
      </Column>

      <!-- Não Comprovação -->
      <Column
        field="val_sem_comp"
        header="Sem Comprovar"
        sortable
        headerClass="col-noncomp"
        bodyClass="col-noncomp"
      >
        <template #body="{ data }">
          <div class="noncomp-cell" :class="{ muted: data.val_sem_comp == null }">
            <span
              class="noncomp-value"
              :class="{ 'high-value-audit': data.val_sem_comp >= auditHighValue }"
              v-tooltip.top="data.val_sem_comp != null ? establishmentTableTooltip('unverifiedSales', formatCurrencyFull(data.val_sem_comp)) : null"
            >
              {{ formatCurrencyCompact(data.val_sem_comp) }}
            </span>
            <span v-if="data.perc_val_sem_comp != null" class="noncomp-percent">
              {{ data.perc_val_sem_comp.toFixed(2) }}%
            </span>
          </div>
        </template>
        <template #footer>
          <div class="noncomp-cell table-total-cell">
            <span
              class="noncomp-value"
              v-tooltip.top="establishmentTableTooltip('unverifiedSalesFooter', tableFooter.totalSemComprovacaoFull)"
            >{{ tableFooter.totalSemComprovacao }}</span>
          </div>
        </template>
      </Column>

      <!-- Grande Rede -->
      <Column
        field="is_grande_rede"
        header="Grande Rede"
        headerClass="col-network-flag"
        bodyClass="col-network-flag"
      >
        <template #body="{ data }">
          <Tag
            :value="data.is_grande_rede ? 'Sim' : 'Não'"
            :class="[data.is_grande_rede ? 'status-info' : 'status-secondary', 'clickable-badge']"
            v-tooltip.top="establishmentTableTooltip('largeNetworkFilter', data.is_grande_rede ? 'Sim' : 'Não')"
            @click.stop="applyFilter('grandeRede', data.is_grande_rede)"
          />
        </template>
      </Column>

      <!-- Estabelecimentos da Rede -->
      <Column
        field="qtd_estabelecimentos_rede"
        header="Estab. Rede"
        headerClass="col-network-count"
        bodyClass="col-network-count"
      >
        <template #body="{ data }">
          <Tag
            v-if="data.qtd_estabelecimentos_rede > 1"
            :value="String(data.qtd_estabelecimentos_rede)"
            class="status-info clickable-badge"
            v-tooltip.top="establishmentTableTooltip('networkEstablishments', data.qtd_estabelecimentos_rede)"
            @click.stop="filterStore.selectedCnpjRaiz = extractCnpjRaiz(data.cnpj)"
          />
          <Tag
            v-else-if="data.qtd_estabelecimentos_rede === 1"
            value="1"
            class="status-secondary"
          />
          <span v-else class="network-count-muted">—</span>
        </template>
      </Column>

      <!-- Conexão MS -->
      <Column
        field="is_conexao_ativa"
        header="Conexão MS"
        headerClass="col-badge-filter"
        bodyClass="col-badge-filter"
      >
        <template #body="{ data }">
          <Tag
            :value="data.is_conexao_ativa ? 'Ativa' : 'Inativa'"
            :class="[conexaoMsClass(data.is_conexao_ativa), 'clickable-badge']"
            v-tooltip.top="establishmentTableTooltip('ministryConnectionFilter', data.is_conexao_ativa ? 'Ativa' : 'Inativa')"
            @click.stop="applyFilter('conexaoMS', data.is_conexao_ativa)"
          />
        </template>
      </Column>

    </DataTable>

    <ObservationDialog
      v-if="observationCnpj"
      v-model:visible="showObservationDialog"
      :cnpj="observationCnpj"
      :entity-name="observationEntityName"
    />

    <!-- Dialogs de detalhamento (reutilizam os mesmos da aba Indicadores) -->
    <IndicatorDetailDialog
      v-if="canShowDetailButton && !['dispersao_geografica','incompatibilidade_patologica'].includes(indicadorKey)"
      v-model="showGenericDetailDialog"
      :cnpj="detailCnpj"
      :indicator-key="indicadorKey"
      :perf-session="detailPerfSession"
    />
    <GeographicDispersionDialog
      v-if="indicadorKey === 'dispersao_geografica'"
      v-model="showGeographicDetailDialog"
      :cnpj="detailCnpj"
    />
    <ClinicalIncompatibilityDialog
      v-if="indicadorKey === 'incompatibilidade_patologica'"
      v-model="showClinicalDetailDialog"
      :cnpj="detailCnpj"
    />

    <!-- Overlay de loading do detalhamento -->
    <transition name="detail-overlay-fade">
      <div v-if="loadingDetailCnpj" class="detail-loading-overlay" aria-live="polite" aria-busy="true">
        <div class="detail-loading-overlay__box">
          <i class="pi pi-spin pi-spinner" />
          <span>Carregando detalhamento...</span>
        </div>
      </div>
    </transition>

  </div>
</template>

<style scoped>
/* ── Botão de Detalhamento ───────────────────────── */
.detail-action-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 0.3rem;
  box-sizing: border-box;
  width: 6.3rem;
  height: 28px;
  padding: 0 0.35rem;
  border: 1px solid color-mix(in srgb, var(--primary-color) 30%, var(--card-border));
  border-radius: 7px;
  background: color-mix(in srgb, var(--primary-color) 6%, var(--card-bg));
  color: var(--primary-color);
  cursor: pointer;
  font-size: 0.75rem;
  white-space: nowrap;
  transition: background 0.15s ease, border-color 0.15s ease, transform 0.15s ease, box-shadow 0.15s ease;
}

.detail-action-btn:hover {
  background: color-mix(in srgb, var(--primary-color) 14%, var(--card-bg));
  border-color: var(--primary-color);
  transform: translateY(-1px);
  box-shadow: 0 3px 8px color-mix(in srgb, var(--primary-color) 22%, transparent);
}

.detail-action-btn.is-loading {
  opacity: 0.6;
  pointer-events: none;
  cursor: default;
}

.detail-action-btn span {
  font-size: 0.65rem;
}

.row-actions {
  display: grid;
  grid-template-columns: 28px 28px;
  align-items: center;
  gap: 0.25rem;
  flex: 0 0 auto;
  margin-left: auto;
}

.row-actions--with-detail {
  grid-template-columns: 6.3rem 28px 28px;
}

.row-action-btn {
  opacity: 0;
  pointer-events: none;
}

.favorite-action-btn,
.observation-action-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  box-sizing: border-box;
  flex: 0 0 28px;
  width: 28px;
  height: 28px;
  padding: 0;
  border: 1px solid var(--card-border);
  border-radius: 7px;
  background: var(--card-bg);
  color: var(--text-muted);
  cursor: pointer;
  transition: opacity 0.15s ease, color 0.15s ease, border-color 0.15s ease;
}

.favorite-action-btn.is-favorite {
  opacity: 1;
  pointer-events: auto;
  color: var(--primary-color);
  border-color: color-mix(in srgb, var(--primary-color) 40%, var(--card-border));
}

.observation-action-btn {
  opacity: 1;
  pointer-events: auto;
}

.observation-action-btn.has-observation {
  color: var(--primary-color);
  border-color: color-mix(in srgb, var(--primary-color) 40%, var(--card-border));
  background: color-mix(in srgb, var(--primary-color) 8%, var(--card-bg));
}

:deep(.ind-cnpj-table .p-datatable-tbody > tr:hover) .row-action-btn,
:deep(.ind-cnpj-table .p-datatable-tbody > tr:has(.row-action-btn:focus-visible)) .row-action-btn {
  opacity: 1;
  pointer-events: auto;
}

.row-action-btn:focus-visible {
  opacity: 1;
  pointer-events: auto;
  outline: 2px solid var(--primary-color);
  outline-offset: 2px;
}

.favorite-action-btn:hover,
.observation-action-btn:hover {
  color: var(--primary-color);
  border-color: var(--primary-color);
}

.row-action-btn:disabled {
  cursor: not-allowed;
}

/* Overlay de loading do detalhamento */
.detail-loading-overlay {
  position: fixed;
  inset: 0;
  z-index: 1200;
  display: flex;
  align-items: center;
  justify-content: center;
  background: color-mix(in srgb, var(--bg-color) 72%, transparent);
  backdrop-filter: blur(2px);
}

.detail-loading-overlay__box {
  display: inline-flex;
  align-items: center;
  gap: 0.75rem;
  padding: 0.9rem 1.1rem;
  border: 1px solid var(--card-border);
  border-radius: 10px;
  background: var(--card-bg);
  color: var(--text-color-85);
  box-shadow: 0 12px 28px color-mix(in srgb, var(--text-color-85) 12%, transparent);
  font-size: 0.86rem;
  font-weight: 600;
}

.detail-loading-overlay__box i {
  color: var(--primary-color);
  font-size: 1rem;
}

.detail-overlay-fade-enter-active,
.detail-overlay-fade-leave-active {
  transition: opacity 0.18s ease;
}

.detail-overlay-fade-enter-from,
.detail-overlay-fade-leave-to {
  opacity: 0;
}

.ind-table-card {
  background: var(--card-bg);
  border: 1px solid var(--card-border);
  border-radius: 12px;
  overflow: hidden;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.08);
  transition: opacity 0.3s ease;
}

.section-header {
  display: flex;
  align-items: center;
  gap: 1rem;
  padding: 1.25rem 1.5rem;
  border-bottom: 1px solid var(--tabs-border);
}

.header-text-box {
  flex: 1;
  min-width: 0;
}

.header-filter-chips {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  flex-wrap: wrap;
  gap: 0.5rem;
  margin-left: auto;
  min-width: 0;
}

.scope-filter-chip {
  display: inline-flex;
  align-items: center;
  gap: 0.45rem;
  max-width: 18rem;
  min-height: 1.8rem;
  padding: 0.35rem 0.7rem;
  background: color-mix(in srgb, var(--risk-indicator-critical, #ef4444) 10%, var(--card-bg));
  border: 1px solid color-mix(in srgb, var(--risk-indicator-critical, #ef4444) 35%, transparent);
  border-radius: 999px;
  font-size: 0.74rem;
  color: var(--text-color-85);
}

.scope-filter-chip span {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.scope-filter-chip i.pi-directions,
.scope-filter-chip i.pi-map-marker {
  color: var(--risk-indicator-critical, #ef4444);
  font-size: 0.72rem;
  flex-shrink: 0;
}

.chip-clear {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  background: none;
  border: none;
  cursor: pointer;
  padding: 0.1rem;
  color: var(--text-muted);
  font-size: 0.65rem;
  border-radius: 4px;
  opacity: 0.7;
  transition: opacity 0.15s ease, color 0.15s ease;
  flex-shrink: 0;
}

.chip-clear:hover {
  opacity: 1;
  color: var(--risk-indicator-critical, #ef4444);
}

.header-icon-box {
  width: 42px;
  height: 42px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: color-mix(in srgb, var(--primary-color) 10%, transparent);
  color: var(--primary-color);
  border-radius: 10px;
  font-size: 1.1rem;
  flex-shrink: 0;
}

.header-text-box h3 {
  margin: 0;
  font-size: 1rem;
  font-weight: 600;
  letter-spacing: -0.01em;
  color: var(--text-color-85);
}

.subtitle {
  font-size: 0.82rem;
  color: var(--text-muted);
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.razao-block {
  display: flex;
  flex-direction: column;
  gap: 0.2rem;
  min-width: 0;
  overflow: hidden;
}

.razao-nome-row {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  min-width: 0;
  overflow: hidden;
}

.razao-social-cell {
  cursor: default;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  display: block;
  max-width: 100%;
  font-size: 0.80rem;
}

.cnpj-row {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  min-width: 0;
}

.loc-inline-row {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  min-width: 0;
  width: 100%;
}

.loc-place {
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
  min-width: 0;
}

.municipio-inline-text {
  flex: 0 1 auto;
  min-width: 0;
  font-size: 0.80rem;
  color: var(--text-muted);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  display: block;
  max-width: 100%;
}

.tipo-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 1.25rem;
  height: 1.25rem;
  border-radius: 6px;
  font-size: 0.68rem;
  flex-shrink: 0;
  backdrop-filter: blur(6px);
  -webkit-backdrop-filter: blur(6px);
}

.tipo-badge.matriz {
  background: color-mix(in srgb, var(--accent-indigo) 18%, transparent);
  border: 1px solid color-mix(in srgb, var(--accent-indigo) 35%, transparent);
  color: var(--accent-indigo);
}

.tipo-badge.filial {
  background: color-mix(in srgb, var(--status-secondary) 12%, transparent);
  border: 1px solid color-mix(in srgb, var(--status-secondary) 20%, transparent);
  color: var(--status-secondary);
}

.cnpj-text {
  font-size: 0.80rem;
  color: var(--text-muted);
  letter-spacing: 0.01em;
  white-space: nowrap;
  flex-shrink: 0;
}

.copy-btn {
  display: inline-flex;
  justify-content: center;
  width: 1.4rem;
  flex-shrink: 0;
  cursor: pointer;
  color: var(--text-muted);
  font-size: 0.85rem;
  opacity: 0.4;
  transition: all 0.2s;
}

.copy-btn.text-success {
  color: var(--status-success) !important;
  opacity: 1 !important;
}

.copy-btn:hover {
  opacity: 1 !important;
  color: var(--primary-color);
  transform: scale(1.1);
}

.copy-btn:active {
  transform: scale(0.9);
}

.loc-block {
  display: flex;
  flex-direction: column;
  gap: 0.2rem;
  min-width: 0;
  overflow: hidden;
}

.municipio-text {
  font-size: 0.88rem;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  display: block;
  max-width: 100%;
}

.uf-tag {
  display: inline-block;
  align-self: flex-start;
  flex-shrink: 0;
  box-sizing: border-box;
  width: 2rem;
  text-align: center;
  padding: 0.05rem 0.3rem;
  background: color-mix(in srgb, var(--primary-color) 12%, var(--card-bg));
  color: var(--primary-color);
  border-radius: 4px;
  font-size: 0.76rem;
  font-weight: 600;
}

.val-cell {
  display: block;
  text-align: right;
}

.indicator-cell {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 0.12rem;
  min-width: 0;
}

.indicator-value {
  display: block;
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 0.86rem;
}

.indicator-median {
  display: block;
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 0.78rem;
  font-weight: 500;
  line-height: 1;
  color: var(--text-muted);
  opacity: 0.72;
}

.risk-cell {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 0.14rem;
  min-width: 0;
}

.risk-value {
  display: block;
  padding: 0 !important;
  background: transparent !important;
  border: 0 !important;
  font-size: 0.88rem;
  font-weight: 600;
  line-height: 1.1;
}

.risk-value.status-danger,
.risk-status.status-danger {
  color: var(--risk-high);
}

.risk-value.status-warn,
.risk-status.status-warn {
  color: var(--risk-medium);
}

.risk-value.status-success,
.risk-status.status-success {
  color: var(--text-muted) !important;
}

.risk-value.status-secondary,
.risk-status.status-secondary {
  color: var(--text-muted);
}

.movement-value {
  display: block;
  max-width: 100%;
  overflow: hidden;
  color: var(--text-color-85);
  font-size: 0.86rem;
  text-align: right;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.risk-status {
  display: block;
  max-width: 100%;
  padding: 0 !important;
  background: transparent !important;
  border: 0 !important;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 0.78rem;
  font-weight: 500;
  line-height: 1;
  letter-spacing: 0.03em;
}

.noncomp-cell {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 0.12rem;
  min-width: 0;
}

.noncomp-value {
  display: block;
  max-width: 100%;
  text-align: right;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  font-size: 0.86rem;
}

.noncomp-percent {
  font-size: 0.78rem;
  font-weight: 600;
  line-height: 1;
  color: var(--text-muted);
  opacity: 0.72;
}

.table-total-label {
  color: var(--text-color-85);
  font-size: 0.72rem;
  font-weight: 800;
  letter-spacing: 0.04em;
}

.table-total-cell .noncomp-value {
  color: var(--text-color-85);
  font-weight: 800;
}

.table-total-cell .noncomp-percent {
  font-weight: 800;
  opacity: 0.9;
}

.table-total-movement {
  font-weight: 800;
}

.network-count-muted {
  display: block;
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 0.62rem;
  font-weight: 500;
  line-height: 1;
  color: var(--text-muted);
}

.muted {
  opacity: 0.45;
}

/* ── Deep overrides da tabela de estabelecimentos por indicador ── */
:deep(.clickable-rows .p-datatable-tbody > tr) {
  cursor: pointer;
  transition: background-color 0.15s ease;
}

:deep(.ind-cnpj-table.p-datatable .p-datatable-tbody > tr) {
  font-size: 0.75rem;
}

:deep(.ind-cnpj-table.p-datatable .p-datatable-tbody) {
  transition: opacity 0.18s ease;
}

:deep(.ind-cnpj-table .p-datatable-table) {
  table-layout: fixed;
  width: 100%;
}

:deep(.ind-cnpj-table .p-datatable-tbody > tr > td) {
  overflow: hidden;
}

:deep(.ind-cnpj-table .col-name) {
}

:deep(.ind-cnpj-table .p-datatable-thead > tr > th:first-child),
:deep(.ind-cnpj-table .p-datatable-tbody > tr > td:first-child) {
  padding-left: 1.25rem;
}

:deep(.ind-cnpj-table .p-datatable-tbody > tr > td) {
  color: var(--text-color-85) !important;
}

:deep(.ind-cnpj-table .col-location) {
  width: 12%;
}

:deep(.ind-cnpj-table .col-indicator) {
  width: 12%;
  text-align: right;
}

:deep(.ind-cnpj-table .col-extra) {
  font-size: 0.86rem;
  text-align: center;
}

:deep(.ind-cnpj-table .col-risk) {
  width: 8%;
  text-align: center;
}

:deep(.ind-cnpj-table .col-movement) {
  width: 11%;
  text-align: right;
}

:deep(.ind-cnpj-table .col-noncomp) {
  width: 12%;
  text-align: right;
}

:deep(.ind-cnpj-table .col-network-flag) {
  width: 7%;
  text-align: center;
  padding-left: 0.25rem;
  padding-right: 0.25rem;
}

:deep(.ind-cnpj-table .col-network-count) {
  width: 7%;
  text-align: center;
  padding-left: 0.25rem;
  padding-right: 0.25rem;
}

:deep(.ind-cnpj-table .col-badge-filter) {
  width: 7%;
  text-align: center;
  padding-left: 0.25rem;
  padding-right: 0.25rem;
}

:deep(.ind-cnpj-table .col-indicator .p-column-header-content),
:deep(.ind-cnpj-table .col-movement .p-column-header-content),
:deep(.ind-cnpj-table .col-noncomp .p-column-header-content) {
  justify-content: flex-end;
}

:deep(.ind-cnpj-table .col-indicator .p-column-title) {
  min-width: 0;
}

.indicator-column-title {
  display: -webkit-box;
  max-width: 100%;
  overflow: hidden;
  text-align: right;
  text-overflow: ellipsis;
  white-space: normal;
  line-height: 1.1;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
}

:deep(.ind-cnpj-table .col-risk .p-column-header-content),
:deep(.ind-cnpj-table .col-extra .p-column-header-content),
:deep(.ind-cnpj-table .col-network-flag .p-column-header-content),
:deep(.ind-cnpj-table .col-network-count .p-column-header-content),
:deep(.ind-cnpj-table .col-badge-filter .p-column-header-content) {
  justify-content: center;
}

:deep(.ind-cnpj-table .col-badge-filter .p-sortable-column-icon) {
  display: none;
}

:deep(.ind-cnpj-table .col-badge-filter .p-tag) {
  max-width: 100%;
  padding-left: 0.38rem;
  padding-right: 0.38rem;
}

:deep(.ind-cnpj-table .col-badge-filter .p-tag-value) {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

:deep(.ind-cnpj-table .col-network-flag .p-tag) {
  max-width: 100%;
  padding-left: 0.38rem;
  padding-right: 0.38rem;
}

:deep(.ind-cnpj-table .col-network-flag .p-tag-value) {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

:deep(.ind-cnpj-table .p-datatable-thead > tr > th) {
  text-transform: uppercase;
  letter-spacing: 0.04em;
  font-size: 0.7rem !important;
}

:deep(.ind-cnpj-table .p-datatable-tfoot > tr > td) {
  color: var(--text-color-85);
  background: color-mix(in srgb, var(--primary-color) 5%, var(--card-bg));
  border-top: 1px solid var(--card-border);
  font-size: 0.72rem;
}

:deep(.p-datatable-thead) {
  position: sticky;
  top: 0;
  z-index: 10;
}

:deep(.p-datatable-wrapper) {
  border-radius: 0 0 12px 12px;
  min-height: var(--risk-table-min-h, calc(20 * 2.625rem));
}

:deep(.p-tag) {
  padding: 0.2rem 0.5rem;
  border-radius: 6px;
  font-weight: 600;
  font-size: 0.65rem;
  border: 1px solid transparent;
}

:deep(.clickable-badge) {
  cursor: pointer;
  transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
}
:deep(.clickable-badge:hover) {
  opacity: 1;
  transform: translateY(-1px);
  filter: brightness(0.95);
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.05);
}

:deep(.p-datatable-tbody td) {
  text-transform: none !important;
  font-variant: normal !important;
}

:deep(.p-tag-value),
:deep(.p-tag) {
  text-transform: uppercase !important;
  letter-spacing: 0.03em;
}

/* DESTAQUE DE ALTO VALOR */
.high-value-audit {
  color: var(--risk-high);
  font-weight: 600;
  font-size: 0.75rem; /* Ajustado para caber na tabela densa de indicadores */
  display: inline-flex;
  align-items: center;
  justify-content: flex-end;
  gap: 0.4rem;
  padding: 0.15rem 0.65rem;
  background: color-mix(in srgb, var(--risk-high) 10%, transparent);
  border-left: 3px solid var(--risk-high);
  border-radius: 0 6px 6px 0;
}
</style>
