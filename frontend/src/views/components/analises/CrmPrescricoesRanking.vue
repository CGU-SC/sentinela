<script setup>
import { computed } from 'vue';
import DataTable from 'primevue/datatable';
import Column from 'primevue/column';
import { useFormatting } from '@/composables/useFormatting';
import { useFrozenData } from '@/composables/useFrozenData';
import { analysisTooltip } from '@/config/analysisTooltipConfig';
import { CRM_DAILY_RATE_HIGHLIGHT_THRESHOLD } from '@/config/riskConfig';

const props = defineProps({
  rows: { type: Array, default: () => [] },
  isLoading: { type: Boolean, default: false },
  isPageLoading: { type: Boolean, default: false },
  escopo: { type: String, default: 'Brasil' },
  error: { type: String, default: null },
  pageError: { type: String, default: null },
  totalRecords: { type: Number, default: 0 },
  first: { type: Number, default: 0 },
  pageSize: { type: Number, default: 25 },
  sortField: { type: String, default: 'taxa_prescricoes_dia' },
  sortOrder: { type: String, default: 'desc' },
  isRefreshing: { type: Boolean, default: false },
  isStale: { type: Boolean, default: false },
  farmaciasFiltradas: { type: Boolean, default: false },
});

const emit = defineEmits(['page', 'sort', 'select-medico']);
const snapshot = useFrozenData(
  () => ({
    rows: props.rows,
    escopo: props.escopo,
    totalRecords: props.totalRecords,
    first: props.first,
    pageSize: props.pageSize,
    sortField: props.sortField,
    sortOrder: props.sortOrder,
    farmaciasFiltradas: props.farmaciasFiltradas,
  }),
  computed(() => props.isRefreshing),
);
const rankingInfoTooltip = computed(() => analysisTooltip('crmRanking', {
  extraSections: snapshot.value.farmaciasFiltradas
    ? [{
      label: 'Farmácias filtradas',
      text: 'Com filtros de farmácia, entram os médicos que prescreveram em pelo menos uma farmácia filtrada do escopo em algum mês do período. Taxa e meses (inclusive os de taxa elevada) são os mesmos do ranking sem filtro (todas as prescrições do médico no escopo); a coluna Farmácias filtradas mostra quantas prescrições ocorreram nessas farmácias e a participação delas no total do médico.',
    }]
    : [],
}));
const { formatNumberFull, formatTitleCase } = useFormatting();
const highRateTooltip = `Taxa de pelo menos ${CRM_DAILY_RATE_HIGHLIGHT_THRESHOLD} prescrições por dia no período selecionado. Destaque visual, sem classificação de irregularidade.`;

function isHighDailyRate(row) {
  return Number(row.taxa_prescricoes_dia) >= CRM_DAILY_RATE_HIGHLIGHT_THRESHOLD;
}

function formatPercent(value) {
  return value == null ? '—' : `${Number(value).toFixed(1).replace('.', ',')}%`;
}

function doctorLabel(row) {
  return row.no_medico ? formatTitleCase(row.no_medico) : 'Médico não localizado';
}

function crmLabel(row) {
  if (row.nu_crm == null) return `CRM ${row.id_medico}`;
  return `CRM ${formatNumberFull(row.nu_crm)}${row.sg_uf ? `/${row.sg_uf}` : ''}`;
}

function onRowClick(event) {
  if (!props.isRefreshing && !props.isStale) emit('select-medico', event.data);
}

function onSort(event) {
  if (!props.isRefreshing && !props.isStale) emit('sort', event);
}

function onPage(event) {
  if (!props.isRefreshing && !props.isStale) emit('page', event);
}
</script>

<template>
  <section class="crm-ranking-panel" :class="{ 'is-refreshing': isRefreshing }">
    <header class="ranking-header">
      <div class="ranking-heading">
        <i class="pi pi-list" aria-hidden="true" />
        <div>
          <div class="ranking-title-row">
            <h2>Ranking de médicos por taxa diária</h2>
            <i class="pi pi-info-circle info-icon" v-tooltip.bottom="rankingInfoTooltip" aria-label="Como ler o ranking" />
          </div>
          <span v-if="error && snapshot.rows.length" class="ranking-status--error" role="alert" v-tooltip.bottom="error">
            Falha ao atualizar · resultado anterior exibido
          </span>
          <span v-else>{{ snapshot.escopo }} · {{ formatNumberFull(snapshot.totalRecords) }} médicos no recorte</span>
        </div>
      </div>
    </header>

    <div v-if="error && !snapshot.rows.length && !isLoading" class="ranking-state ranking-state--error">
      <i class="pi pi-database" />
      <div>
        <strong>Ranking indisponível no momento</strong>
        <span>{{ error }}</span>
      </div>
    </div>
    <div v-else-if="isLoading" class="ranking-state">
      <i class="pi pi-spin pi-spinner" />
      <span>Calculando ranking...</span>
    </div>
    <div v-else-if="!snapshot.rows.length" class="ranking-state">
      <i class="pi pi-info-circle" />
      <span>Nenhum médico encontrado para os filtros atuais.</span>
    </div>
    <div v-else class="ranking-table-wrap" :aria-busy="isRefreshing">
      <DataTable
        :key="`${snapshot.sortField}:${snapshot.sortOrder}:${pageError ?? ''}`"
        :value="snapshot.rows"
        data-key="id_medico"
        size="small"
        lazy
        paginator
        :first="snapshot.first"
        :rows="snapshot.pageSize"
        :total-records="snapshot.totalRecords"
        :rows-per-page-options="[25, 50, 100]"
        :sort-field="snapshot.sortField"
        :sort-order="snapshot.sortOrder === 'asc' ? 1 : -1"
        :class="['enterprise-table', 'crm-ranking-table', 'clickable-rows', { 'is-stale': isStale }]"
        @row-click="onRowClick"
        @sort="onSort"
        @page="onPage"
      >
        <Column header="POS." header-class="col-rank" body-class="col-rank">
          <template #body="{ data }">
            <button type="button" class="rank-button" :aria-label="`Abrir histórico de ${doctorLabel(data)}`" :disabled="isRefreshing || isStale" @click.stop="emit('select-medico', data)">
              {{ data.rank }}
            </button>
          </template>
        </Column>
        <Column field="no_medico" header="MÉDICO / CRM" sortable header-class="col-doctor" body-class="col-doctor">
          <template #body="{ data }">
            <span class="doctor-name">{{ doctorLabel(data) }}</span>
            <span class="doctor-crm">{{ crmLabel(data) }}</span>
          </template>
        </Column>
        <Column field="taxa_prescricoes_dia" header="TAXA / DIA" sortable header-class="col-number col-rate" body-class="col-number col-rate rate-cell">
          <template #body="{ data }">
            <span
              class="rate-value"
              :class="{ 'rate-value--high': isHighDailyRate(data) }"
              v-tooltip.bottom="isHighDailyRate(data) ? highRateTooltip : null"
            >{{ Number(data.taxa_prescricoes_dia).toFixed(2).replace('.', ',') }}</span>
          </template>
        </Column>
        <Column field="nu_prescricoes" header="PRODUÇÃO" sortable header-class="col-number col-production" body-class="col-number col-production">
          <template #body="{ data }">
            <span class="metric-main">{{ formatNumberFull(data.nu_prescricoes) }} prescrições</span>
            <span class="metric-detail">{{ formatNumberFull(data.qtd_dias_com_prescricao) }} dias com prescrição</span>
          </template>
        </Column>
        <Column field="percentual_meses_alta_intensidade" header="MESES COM TAXA ELEVADA" sortable header-class="col-number col-months" body-class="col-number col-months">
          <template #body="{ data }">
            <span class="metric-main">{{ formatPercent(data.percentual_meses_alta_intensidade) }}</span>
            <span class="metric-detail">{{ formatNumberFull(data.qtd_meses_alta_intensidade) }} de {{ formatNumberFull(data.qtd_meses_ativos) }} meses</span>
          </template>
        </Column>
        <Column v-if="snapshot.farmaciasFiltradas" field="nu_prescricoes_farmacias_filtradas" header="FARMÁCIAS FILTRADAS" sortable header-class="col-number col-filtered" body-class="col-number col-filtered">
          <template #body="{ data }">
            <span class="metric-main">{{ formatNumberFull(data.nu_prescricoes_farmacias_filtradas) }} prescrições</span>
            <span class="metric-detail">{{ formatPercent(data.percentual_prescricoes_farmacias_filtradas) }} do total</span>
          </template>
        </Column>
      </DataTable>
      <div v-if="isPageLoading" class="ranking-table-loading" role="status" aria-label="Atualizando ranking">
        <i class="pi pi-spin pi-spinner" aria-hidden="true" />
      </div>
    </div>

    <div v-if="pageError && snapshot.rows.length" class="ranking-page-error" role="alert">
      <i class="pi pi-exclamation-circle" />
      <span>{{ pageError }}</span>
    </div>
  </section>
</template>

<style scoped>
.crm-ranking-panel { background: var(--card-bg); border: 1px solid var(--card-border); border-radius: 12px; overflow: hidden; transition: border-color .18s ease; }
.crm-ranking-panel.is-refreshing { border-color: color-mix(in srgb, var(--primary-color) 24%, var(--card-border)); }
.ranking-header { display: flex; align-items: center; padding: .85rem 1.15rem; border-bottom: 1px solid var(--tabs-border); }
.ranking-heading { display: flex; align-items: center; gap: .75rem; min-width: 0; }
.ranking-heading > i { color: var(--primary-color); font-size: 1rem; flex-shrink: 0; }
.ranking-heading > div { min-width: 0; }
.ranking-title-row { display: flex; align-items: center; gap: .4rem; }
.ranking-title-row h2 { margin: 0; color: var(--text-color-85); font-size: .82rem; font-weight: 600; line-height: 1.1; text-transform: uppercase; letter-spacing: .05em; }
.ranking-heading span { display: block; margin-top: .16rem; color: var(--text-muted); font-size: .68rem; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.ranking-heading .ranking-status--error { color: var(--risk-high); }
.info-icon { color: var(--text-muted); font-size: .8rem; opacity: .7; }
.info-icon:hover { opacity: 1; }
.ranking-state { min-height: 180px; display: flex; align-items: center; justify-content: center; gap: .6rem; color: var(--text-muted); font-size: .8rem; }
.ranking-state i { color: var(--primary-color); }
.ranking-state--error { text-align: left; }
.ranking-state--error strong, .ranking-state--error span { display: block; }
.ranking-state--error strong { color: var(--text-color-85); font-size: .82rem; font-weight: 600; }
.ranking-state--error span { margin-top: .25rem; font-size: .72rem; }
.ranking-table-wrap { position: relative; overflow-x: auto; }
.crm-ranking-table { font-family: inherit; }
.crm-ranking-table.is-stale { pointer-events: none; }
.crm-ranking-table :deep(.p-datatable-table) { width: max(100%, 44rem); table-layout: fixed; }
.crm-ranking-table:has(.col-filtered) :deep(.p-datatable-table) { width: calc(max(100%, 44rem) + 11.25rem); }
.crm-ranking-table :deep(.p-datatable-thead > tr > th) { white-space: normal; vertical-align: bottom; line-height: 1.25; }
.crm-ranking-table :deep(.p-datatable-thead > tr > th .p-column-header-content) { gap: .3rem; }
.crm-ranking-table :deep(.p-datatable-thead > tr > th.col-number .p-column-header-content) { justify-content: flex-end; }
.crm-ranking-table :deep(.p-datatable-tbody > tr > td) { padding: .65rem .8rem; vertical-align: middle; overflow: hidden; }
.crm-ranking-panel:not(.is-refreshing) .crm-ranking-table:not(.is-stale) :deep(.p-datatable-tbody > tr) { cursor: pointer; }
.crm-ranking-table :deep(.col-number) { text-align: right; }
.crm-ranking-table :deep(.col-rank) { width: 3rem; color: var(--text-muted); }
.crm-ranking-table :deep(.col-rate) { width: 6.5rem; }
.crm-ranking-table :deep(.col-production) { width: 10.5rem; }
.crm-ranking-table :deep(.col-months) { width: 10rem; }
.crm-ranking-table :deep(.col-filtered) { width: 11.25rem; }
.metric-main, .metric-detail { display: block; white-space: nowrap; }
.metric-main, .metric-detail, .doctor-name, .doctor-crm { overflow: hidden; text-overflow: ellipsis; }
.metric-main { color: var(--text-color-85); font-weight: 500; }
.metric-detail { margin-top: .15rem; color: var(--text-muted); font-size: .68rem; }
.doctor-name, .doctor-crm { display: block; }
.doctor-name { color: var(--text-color-85); font-weight: 500; }
.doctor-crm { margin-top: .16rem; color: var(--text-muted); font-size: .68rem; }
.rate-value { display: inline-block; color: var(--text-color-85); font-weight: 500; }
.rate-value--high { padding: .18rem .38rem; margin: -.18rem -.38rem; border-radius: 5px; background: color-mix(in srgb, var(--risk-high) 12%, var(--card-bg)); color: var(--risk-high); font-weight: 600; }
.rank-button { padding: .12rem .25rem; margin: -.12rem -.25rem; border: 0; border-radius: 4px; background: transparent; color: inherit; font: inherit; cursor: pointer; }
.rank-button:focus-visible { outline: 2px solid var(--primary-color); outline-offset: 2px; }
.rank-button:disabled { cursor: default; }
.ranking-table-loading { position: absolute; inset: 0; display: flex; align-items: center; justify-content: center; background: color-mix(in srgb, var(--card-bg) 72%, transparent); color: var(--text-muted); font-size: .9rem; pointer-events: none; }
.ranking-page-error { display: flex; align-items: center; gap: .45rem; padding: .55rem 1rem; border-top: 1px solid color-mix(in srgb, var(--risk-high) 25%, var(--tabs-border)); color: var(--risk-high); font-size: .7rem; }
</style>
