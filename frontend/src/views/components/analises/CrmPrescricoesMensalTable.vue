<script setup>
/**
 * Aba "Por mês" do ranking de médicos: uma linha por médico e mês,
 * paginada e ordenada no servidor (GET /crm-prescricoes-mensal).
 */
import { computed } from 'vue';
import DataTable from 'primevue/datatable';
import Column from 'primevue/column';
import { useFormatting } from '@/composables/useFormatting';
import { CRM_DAILY_RATE_HIGHLIGHT_THRESHOLD } from '@/config/riskConfig';
import { CRM_RANKING_PAGE_SIZE_OPTIONS, CRM_RANKING_DEFAULT_PAGE_SIZE } from '@/config/constants';
import { analysisTooltip, CRM_NAO_LOCALIZADO_ICONE, CRM_NAO_LOCALIZADO_TOOLTIP } from '@/config/analysisTooltipConfig';
import HighlightedText from '@/views/components/common/HighlightedText.vue';
import { destaqueBuscaMedico } from '@/utils/crmBusca';
import CrmAlertasBadge from './CrmAlertasBadge.vue';
import TableFooter from '@/views/components/common/TableFooter.vue';

const props = defineProps({
  rows: { type: Array, default: () => [] },
  totalRecords: { type: Number, default: 0 },
  first: { type: Number, default: 0 },
  pageSize: { type: Number, default: CRM_RANKING_DEFAULT_PAGE_SIZE },
  sortField: { type: String, default: 'razao_p95' },
  sortOrder: { type: String, default: 'desc' },
  isLoading: { type: Boolean, default: false },
  appliedQuery: { type: String, default: '' },
  /** Pontos de atenção por id_medico (ícone de alertas). */
  alertas: { type: Object, required: true },
  alertasPeriodo: { type: String, required: true },
  alertasErro: { type: String, default: null },
});
const emit = defineEmits(['page', 'sort', 'select-medico']);

const { formatNumberFull, formatTitleCase } = useFormatting();
const alertasTooltip = analysisTooltip('crmRankingAlertas');
function isHighDailyRate(row) {
  return Number(row.taxa_prescricoes_dia) >= CRM_DAILY_RATE_HIGHLIGHT_THRESHOLD;
}

function formatDecimal(value, casas = 2) {
  return Number(value).toLocaleString('pt-BR', { minimumFractionDigits: casas, maximumFractionDigits: casas });
}
function formatComp(comp) {
  return `${String(comp % 100).padStart(2, '0')}/${Math.floor(comp / 100)}`;
}
// "800 sc" ou "CRM-SC 800" destacam "800/SC" na linha do CRM.
const destaque = computed(() => destaqueBuscaMedico(props.appliedQuery));
const naoLocalizadoTooltip = CRM_NAO_LOCALIZADO_TOOLTIP;
const naoLocalizadoIcone = CRM_NAO_LOCALIZADO_ICONE;
function doctorLabel(row) {
  if (!row.localizado_cfm) return 'Não localizado no CFM';
  if (!row.no_medico) throw new Error(`Contrato inválido: médico ${row.id_medico} localizado no CFM sem nome.`);
  return formatTitleCase(row.no_medico);
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
    :sort-field="sortField"
    :sort-order="sortOrder === 'asc' ? 1 : -1"
    class="enterprise-table com-rodape crm-ranking-table crm-mensal-table clickable-rows"
    @row-click="onRowClick"
    @sort="onSort"
    @page="onPage"
  >
    <Column header-class="col-alertas" body-class="col-alertas">
      <template #header>
        <span class="alertas-cabecalho">
          ALERTAS
          <i class="pi pi-info-circle info-icon help-icon" v-tooltip.top="alertasTooltip" tabindex="0" aria-label="Como ler a coluna de alertas" />
        </span>
      </template>
      <template #body="{ data }">
        <CrmAlertasBadge
          v-if="alertas[data.id_medico]?.length"
          :pontos="alertas[data.id_medico]"
          :periodo="alertasPeriodo"
          :competencia="data.competencia"
          :nome-medico="doctorLabel(data)"
          @abrir="!isLoading && emit('select-medico', data)"
        />
        <span v-else-if="!(data.id_medico in alertas) && !alertasErro" class="alertas-carregando" role="status" aria-label="Carregando alertas" />
      </template>
    </Column>
    <Column header="MÉDICO / CRM" header-class="col-doctor" body-class="col-doctor">
      <template #body="{ data }">
        <span v-if="!data.localizado_cfm" class="doctor-nao-localizado" v-tooltip.bottom="naoLocalizadoTooltip">
          <i :class="['pi', naoLocalizadoIcone]" aria-hidden="true" />Não localizado no CFM
        </span>
        <span v-else class="doctor-name"><HighlightedText :text="doctorLabel(data)" :query="destaque.nome" /></span>
        <span class="doctor-crm"><HighlightedText :text="crmLabel(data)" :query="destaque.crm" /></span>
      </template>
    </Column>
    <Column field="taxa_prescricoes_dia" header="TAXA / DIA" sortable header-class="col-number col-rate" body-class="col-number col-rate rate-cell">
      <template #body="{ data }">
        <span
          class="rate-value"
          :class="{ 'rate-value--high': isHighDailyRate(data) }"
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
    <template #footer>
      <TableFooter
        :first="first"
        :rows="pageSize"
        :total-records="totalRecords"
        :rows-per-page-options="CRM_RANKING_PAGE_SIZE_OPTIONS"
        :unidade="['linha', 'linhas']"
        :disabled="isLoading"
        @page="onPage"
      />
    </template>
  </DataTable>
</template>

<style scoped>
.crm-mensal-table :deep(.col-comp) { width: 7.5rem; }
.crm-mensal-table :deep(.col-p95) { width: 9rem; }
.p95-elevada { color: var(--risk-high); font-weight: 600; }
</style>
