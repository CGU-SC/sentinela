<script setup>
/**
 * Aba "Por mês" do ranking de médicos: uma linha por médico e mês,
 * paginada e ordenada no servidor (GET /crm-prescricoes-mensal).
 */
import DataTable from 'primevue/datatable';
import Column from 'primevue/column';
import { useFormatting } from '@/composables/useFormatting';
import { CRM_DAILY_RATE_HIGHLIGHT_THRESHOLD } from '@/config/riskConfig';
import HighlightedText from '@/views/components/common/HighlightedText.vue';

const props = defineProps({
  rows: { type: Array, default: () => [] },
  totalRecords: { type: Number, default: 0 },
  first: { type: Number, default: 0 },
  pageSize: { type: Number, default: 25 },
  sortField: { type: String, default: 'razao_p95' },
  sortOrder: { type: String, default: 'desc' },
  isLoading: { type: Boolean, default: false },
  appliedQuery: { type: String, default: '' },
});
const emit = defineEmits(['page', 'sort', 'select-medico']);

const { formatNumberFull, formatTitleCase } = useFormatting();
// Mesmo destaque da coluna TAXA / DIA da aba Resumo, aplicado à taxa do mês.
const highRateTooltip = `Taxa de pelo menos ${CRM_DAILY_RATE_HIGHLIGHT_THRESHOLD} prescrições por dia no mês. Destaque visual, sem classificação de irregularidade.`;
function isHighDailyRate(row) {
  return Number(row.taxa_prescricoes_dia) >= CRM_DAILY_RATE_HIGHLIGHT_THRESHOLD;
}

function formatDecimal(value, casas = 2) {
  return Number(value).toLocaleString('pt-BR', { minimumFractionDigits: casas, maximumFractionDigits: casas });
}
function formatComp(comp) {
  return `${String(comp % 100).padStart(2, '0')}/${Math.floor(comp / 100)}`;
}
function doctorLabel(row) {
  return row.no_medico ? formatTitleCase(row.no_medico) : 'Médico não localizado';
}
function crmLabel(row) {
  if (row.nu_crm == null) return `CRM ${row.id_medico}`;
  return `CRM ${row.nu_crm}${row.sg_uf ? `/${row.sg_uf}` : ''}`;
}
function rowKey(row) {
  return `${row.id_medico}|${row.competencia}`;
}

function onRowClick(event) {
  if (!props.isLoading) emit('select-medico', event.data);
}
function onSort(event) {
  if (!props.isLoading) emit('sort', event);
}
function onPage(event) {
  if (!props.isLoading) emit('page', event);
}
</script>

<template>
  <DataTable
    :key="`${sortField}:${sortOrder}`"
    :value="rows"
    :data-key="rowKey"
    size="small"
    lazy
    paginator
    :first="first"
    :rows="pageSize"
    :total-records="totalRecords"
    :rows-per-page-options="[25, 50, 100]"
    :sort-field="sortField"
    :sort-order="sortOrder === 'asc' ? 1 : -1"
    class="enterprise-table crm-ranking-table crm-mensal-table clickable-rows"
    @row-click="onRowClick"
    @sort="onSort"
    @page="onPage"
  >
    <Column header="POS." header-class="col-rank" body-class="col-rank">
      <template #body="{ data }">{{ data.rank }}</template>
    </Column>
    <Column header="MÉDICO / CRM" header-class="col-doctor" body-class="col-doctor">
      <template #body="{ data }">
        <span class="doctor-name"><HighlightedText :text="doctorLabel(data)" :query="appliedQuery" /></span>
        <span class="doctor-crm"><HighlightedText :text="crmLabel(data)" :query="appliedQuery" /></span>
      </template>
    </Column>
    <Column field="taxa_prescricoes_dia" header="TAXA / DIA" sortable header-class="col-number col-rate" body-class="col-number col-rate rate-cell">
      <template #body="{ data }">
        <span
          class="rate-value"
          :class="{ 'rate-value--high': isHighDailyRate(data) }"
          v-tooltip.bottom="isHighDailyRate(data) ? highRateTooltip : null"
        >{{ formatDecimal(data.taxa_prescricoes_dia) }}</span>
      </template>
    </Column>
    <Column field="nu_prescricoes" header="PRODUÇÃO" sortable header-class="col-number col-production" body-class="col-number col-production">
      <template #body="{ data }">
        <span class="metric-main">{{ formatNumberFull(data.nu_prescricoes) }} prescrições</span>
        <span class="metric-detail">{{ formatNumberFull(data.qtd_dias_com_prescricao) }} {{ data.qtd_dias_com_prescricao === 1 ? 'dia' : 'dias' }} com prescrição</span>
      </template>
    </Column>
    <Column field="competencia" header="COMPETÊNCIA" sortable header-class="col-number col-comp" body-class="col-number col-comp">
      <template #body="{ data }">
        <span class="metric-main">{{ formatComp(data.competencia) }}</span>
      </template>
    </Column>
    <Column field="razao_p95" header="×P95 / P95 DO MÊS" sortable header-class="col-number col-p95" body-class="col-number col-p95">
      <template #body="{ data }">
        <span class="metric-main" :class="{ 'p95-elevada': data.taxa_elevada }">{{ formatDecimal(data.razao_p95, 1) }}×</span>
        <span class="metric-detail">P95 {{ formatDecimal(data.p95_taxa_dia) }}</span>
      </template>
    </Column>
  </DataTable>
</template>

<style scoped>
.crm-mensal-table :deep(.col-comp) { width: 7.5rem; }
.crm-mensal-table :deep(.col-p95) { width: 9rem; }
.p95-elevada { color: var(--risk-high); font-weight: 600; }
</style>
