<script setup>
import { computed, ref } from 'vue';
import DataTable from 'primevue/datatable';
import Column from 'primevue/column';
import Tag from 'primevue/tag';
import { useFormatting } from '@/composables/useFormatting';
import { useRiskMetrics } from '@/composables/useRiskMetrics';
import { useDelayedLoading } from '@/composables/useDelayedLoading';
import TableFooter from '@/views/components/common/TableFooter.vue';

// Paginação no cliente (o rodapé padrão controla a página da DataTable).
const LINHAS_POR_PAGINA_OPCOES = [25, 50, 100];
const paginaFirst = ref(0);
const paginaRows = ref(LINHAS_POR_PAGINA_OPCOES[0]);
function mudarPagina(evento) {
  paginaRows.value = evento.rows;
  paginaFirst.value = evento.first;
}

const props = defineProps({
  municipios: { type: Array, default: () => [] },
  participationRows: { type: Array, default: () => [] },
  isLoading: { type: Boolean, default: false },
  isStale: { type: Boolean, default: false },
  error: { type: String, default: null },
  selectedIbge7: { type: Number, default: null },
  metricMode: { type: String, default: 'audit' },
  metricLabel: { type: String, default: 'Percentual não comprovação' },
  selectedRegiaoNome: { type: String, default: null },
});

const emit = defineEmits(['select-municipio', 'clear-regiao-filter']);

const loadingRef = computed(() => props.isLoading);
const showRefreshing = useDelayedLoading(loadingRef);
const { formatBRL, formatNumberFull, formatPercent, formatTitleCase } = useFormatting();
const { getRiskClass } = useRiskMetrics();

const displayedMunicipios = computed(() => {
  if (props.selectedIbge7 == null) return props.municipios;

  const selectedFromCurrent = props.municipios.filter(
    (row) => Number(row.id_ibge7) === Number(props.selectedIbge7)
  );
  if (selectedFromCurrent.length) return selectedFromCurrent;

  return props.participationRows.filter(
    (row) => Number(row.id_ibge7) === Number(props.selectedIbge7)
  );
});

const selectedMunicipio = computed(() => {
  if (props.selectedIbge7 == null) return null;
  return props.municipios.find((row) => Number(row.id_ibge7) === Number(props.selectedIbge7))
    ?? props.participationRows.find((row) => Number(row.id_ibge7) === Number(props.selectedIbge7))
    ?? null;
});

const totals = computed(() => {
  return displayedMunicipios.value.reduce((acc, row) => {
    acc.cnpjs += Number(row.cnpjs ?? row.total_cnpjs ?? 0);
    acc.criticos += Number(row.total_critico ?? 0);
    acc.valSemComp += Number(row.valSemComp ?? 0);
    acc.totalMov += Number(row.totalMov ?? 0);
    return acc;
  }, { cnpjs: 0, criticos: 0, valSemComp: 0, totalMov: 0 });
});

const participationTotalMov = computed(() => {
  const rows = props.participationRows.length ? props.participationRows : displayedMunicipios.value;
  return rows.reduce((total, row) => total + Number(row.totalMov ?? 0), 0);
});

const participationScopeLabel = computed(() => (
  props.selectedRegiaoNome ? 'da Região' : 'da UF'
));

const footer = computed(() => ({
  cnpjs: formatNumberFull(totals.value.cnpjs),
  criticos: formatNumberFull(totals.value.criticos),
  valSemComp: formatBRL(totals.value.valSemComp),
  totalMov: formatBRL(totals.value.totalMov),
  percValSemComp: totals.value.totalMov > 0
    ? formatPercent((totals.value.valSemComp / totals.value.totalMov) * 100)
    : formatPercent(0),
  participacao: participationTotalMov.value > 0
    ? formatPercent((totals.value.totalMov / participationTotalMov.value) * 100)
    : formatPercent(0),
}));

const defaultSortField = computed(() => 'valSemComp');

function getCnpjs(row) {
  return Number(row.cnpjs ?? row.total_cnpjs ?? 0);
}

function getCriticos(row) {
  return Number(row.total_critico ?? 0);
}

function getValorPercent(row) {
  return Number(row.percValSemComp ?? 0);
}

function getIndicadorPercent(row) {
  return Number(row.pct_critico ?? 0);
}

function getParticipacao(row) {
  if (!participationTotalMov.value) return 0;
  return (Number(row.totalMov ?? 0) / participationTotalMov.value) * 100;
}

const tableRows = computed(() => displayedMunicipios.value.map((row) => ({
  ...row,
  participacao_recorte: getParticipacao(row),
})));

function rowClass(row) {
  return Number(row.id_ibge7) === Number(props.selectedIbge7) ? 'row-selected' : '';
}

function onRowClick(event) {
  if (props.isStale) return;
  const id = event.data?.id_ibge7;
  if (id == null) throw new Error('Municipio sem id_ibge7 no resultado analitico.');
  emit('select-municipio', Number(id) === Number(props.selectedIbge7) ? null : Number(id));
}
</script>

<template>
  <section class="municipal-table-card" :class="{ 'is-refreshing': showRefreshing, 'is-stale': isStale }">
    <div class="table-header">
      <div class="header-main">
        <i class="pi pi-list" />
      <div>
          <h2>Ranking municipal</h2>
          <span v-if="error" class="table-status-error" role="alert">{{ error }}</span>
          <span v-else-if="showRefreshing" role="status">Atualizando resultados</span>
          <span v-else>{{ metricLabel }} — {{ displayedMunicipios.length }} municípios no recorte atual</span>
        </div>
      </div>

      <div v-if="selectedRegiaoNome || selectedMunicipio" class="header-filter-chips">
        <div v-if="selectedRegiaoNome" class="scope-filter-chip">
          <i class="pi pi-directions" />
          <span>Região: <strong>{{ formatTitleCase(selectedRegiaoNome) }}</strong></span>
          <button
            type="button"
            class="chip-clear"
            :disabled="isStale"
            @click="emit('clear-regiao-filter')"
            v-tooltip.bottom="'Limpar região'"
          >
            <i class="pi pi-times" />
          </button>
        </div>

        <div v-if="selectedMunicipio" class="scope-filter-chip">
          <i class="pi pi-map-marker" />
          <span>Município: <strong>{{ formatTitleCase(selectedMunicipio.municipio) }}</strong></span>
          <button
            type="button"
            class="chip-clear"
            :disabled="isStale"
            @click="emit('select-municipio', null)"
            v-tooltip.bottom="'Limpar município'"
          >
            <i class="pi pi-times" />
          </button>
        </div>
      </div>
    </div>

    <DataTable
      :value="tableRows"
      size="small"
      removableSort
      paginator
      v-model:first="paginaFirst"
      :rows="paginaRows"
      :sortField="defaultSortField"
      :sortOrder="-1"
      class="municipal-table"
      :class="['enterprise-table', 'com-rodape', 'municipal-risk-table', 'clickable-rows']"
      :rowClass="rowClass"
      @row-click="onRowClick"
    >
      <Column field="municipio" header="Município" sortable headerClass="col-municipio" bodyClass="col-municipio">
        <template #body="{ data }">
          <div class="municipio-cell">
            <span class="municipio-text">{{ formatTitleCase(data.municipio) }}</span>
            <span class="uf-tag">{{ data.uf }}</span>
          </div>
        </template>
        <template #footer>Total</template>
      </Column>

      <Column field="cnpjs" header="Estab." sortable headerClass="col-count" bodyClass="col-count">
        <template #body="{ data }">
          {{ formatNumberFull(getCnpjs(data)) }}
        </template>
        <template #footer>{{ footer.cnpjs }}</template>
      </Column>

      <Column
        v-if="metricMode === 'indicator'"
        field="total_critico"
        header="Críticas"
        sortable
        headerClass="col-count"
        bodyClass="col-count"
      >
        <template #body="{ data }">
          {{ formatNumberFull(getCriticos(data)) }}
        </template>
        <template #footer>{{ footer.criticos }}</template>
      </Column>

      <Column
        v-if="metricMode === 'indicator'"
        field="pct_critico"
        header="% Críticas"
        sortable
        headerClass="col-percent"
        bodyClass="col-percent"
      >
        <template #body="{ data }">
          <Tag
            :value="formatPercent(getIndicadorPercent(data))"
            :class="getRiskClass(getIndicadorPercent(data))"
          />
        </template>
        <template #footer>
          {{ totals.cnpjs > 0 ? formatPercent((totals.criticos / totals.cnpjs) * 100) : formatPercent(0) }}
        </template>
      </Column>

      <Column
        field="participacao_recorte"
        header="Participação"
        headerClass="col-participation"
        bodyClass="col-participation"
        sortable
      >
        <template #body="{ data }">
          <div class="participation-cell">
            <span>{{ formatPercent(data.participacao_recorte) }}</span>
            <small>{{ participationScopeLabel }}</small>
          </div>
        </template>
        <template #footer>{{ footer.participacao }}</template>
      </Column>

      <Column
        field="percValSemComp"
        header="% Sem Comprovar"
        sortable
        headerClass="col-percent"
        bodyClass="col-percent"
      >
        <template #body="{ data }">
          <Tag
            :value="formatPercent(getValorPercent(data))"
            :class="getRiskClass(getValorPercent(data))"
          />
        </template>
        <template #footer>{{ footer.percValSemComp }}</template>
      </Column>

      <Column
        field="valSemComp"
        header="Sem Comprovar"
        sortable
        headerClass="col-money"
        bodyClass="col-money"
      >
        <template #body="{ data }">
          {{ formatBRL(data.valSemComp ?? 0) }}
        </template>
        <template #footer>{{ footer.valSemComp }}</template>
      </Column>

      <Column
        field="totalMov"
        header="Total Vendas"
        sortable
        headerClass="col-money"
        bodyClass="col-money"
      >
        <template #body="{ data }">
          {{ formatBRL(data.totalMov ?? 0) }}
        </template>
        <template #footer>{{ footer.totalMov }}</template>
      </Column>

      <template #footer>
        <TableFooter
          :first="paginaFirst"
          :rows="paginaRows"
          :total-records="tableRows.length"
          :rows-per-page-options="LINHAS_POR_PAGINA_OPCOES"
          :unidade="['município', 'municípios']"
          @page="mudarPagina"
        />
      </template>
    </DataTable>
  </section>
</template>

<style scoped>
.municipal-table-card {
  background: var(--card-bg);
  border: 1px solid var(--card-border);
  border-radius: 12px;
  overflow: hidden;
  transition: border-color 0.18s ease;
}

.municipal-table-card.is-refreshing {
  border-color: color-mix(in srgb, var(--primary-color) 24%, var(--card-border));
}

.municipal-table-card.is-stale :deep(.municipal-risk-table) {
  pointer-events: none;
}

.table-status-error {
  color: var(--risk-indicator-critical) !important;
}

.table-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
  padding: 0.85rem 1.15rem;
  border-bottom: 1px solid var(--tabs-border);
}

.header-main {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  min-width: 0;
}

.header-main > i {
  color: var(--primary-color);
  font-size: 1rem;
  flex-shrink: 0;
}

.header-main h2 {
  margin: 0;
  font-size: 0.82rem;
  font-weight: 600;
  line-height: 1.1;
  color: var(--text-color-85);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.header-main span {
  display: block;
  margin-top: 0.16rem;
  font-size: 0.68rem;
  color: var(--text-muted);
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
  border: 0;
  padding: 0.1rem;
  color: var(--text-muted);
  cursor: pointer;
  border-radius: 999px;
  line-height: 1;
  transition: background 0.16s ease, color 0.16s ease;
}

.chip-clear:hover {
  color: var(--risk-indicator-critical, #ef4444);
  background: color-mix(in srgb, var(--risk-indicator-critical, #ef4444) 12%, transparent);
}

.municipio-cell {
  display: flex;
  flex-direction: column;
  gap: 0.2rem;
  min-width: 0;
  overflow: hidden;
}

.municipio-text {
  font-size: 0.88rem;
  color: var(--text-color-85);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  display: block;
  max-width: 100%;
  text-transform: none !important;
  font-variant: normal !important;
}

.uf-tag {
  display: inline-block;
  align-self: flex-start;
  padding: 0.05rem 0.3rem;
  background: color-mix(in srgb, var(--primary-color) 12%, var(--card-bg));
  color: var(--primary-color);
  border-radius: 4px;
  font-size: 0.78rem;
  font-weight: 600;
  line-height: 1;
}

.participation-cell {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 0.1rem;
}

.participation-cell span {
  color: var(--text-color-85);
  font-size: 0.82rem;
  font-weight: 600;
}

.participation-cell small {
  color: var(--text-muted);
  font-size: 0.62rem;
}

.municipal-table-card :deep(.municipal-risk-table.p-datatable),
.municipal-table-card :deep(.municipal-risk-table .p-datatable-wrapper),
.municipal-table-card :deep(.municipal-risk-table .p-datatable-table),
.municipal-table-card :deep(.municipal-risk-table .p-datatable-thead > tr > th),
.municipal-table-card :deep(.municipal-risk-table .p-datatable-tbody > tr),
.municipal-table-card :deep(.municipal-risk-table .p-datatable-tbody > tr > td),
.municipal-table-card :deep(.municipal-risk-table .p-datatable-tfoot > tr > td),
.municipal-table-card :deep(.municipal-risk-table .p-paginator) {
  background: var(--card-bg) !important;
  color: var(--text-color-85) !important;
  border-color: var(--card-border) !important;
}

.municipal-table-card :deep(.municipal-risk-table .p-datatable-table) {
  table-layout: fixed;
  width: 100%;
}

.municipal-table-card :deep(.municipal-risk-table .p-datatable-tbody > tr) {
  cursor: pointer;
  font-size: 0.75rem;
  transition: background-color 0.15s ease;
}

.municipal-table-card :deep(.municipal-risk-table .p-datatable-tbody > tr:hover > td) {
  background: var(--table-hover) !important;
}

.municipal-table-card :deep(.municipal-risk-table .p-datatable-tbody > tr > td) {
  color: var(--text-color-85) !important;
  overflow: hidden;
  text-transform: none !important;
  font-variant: normal !important;
}

.municipal-table-card :deep(.municipal-risk-table .p-datatable-thead > tr > th) {
  font-size: 0.68rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: var(--table-header-text) !important;
}

.municipal-table-card :deep(.municipal-risk-table .p-datatable-tfoot > tr > td) {
  background: color-mix(in srgb, var(--primary-color) 5%, var(--card-bg)) !important;
  color: var(--text-color-85) !important;
  border-top: 1px solid var(--card-border) !important;
  font-size: 0.68rem;
  font-weight: 600;
}

.municipal-table-card :deep(.municipal-risk-table .p-datatable-thead > tr > th:first-child),
.municipal-table-card :deep(.municipal-risk-table .p-datatable-tbody > tr > td:first-child),
.municipal-table-card :deep(.municipal-risk-table .p-datatable-tfoot > tr > td:first-child) {
  padding-left: 1.25rem;
}

.municipal-table-card :deep(.municipal-risk-table .p-datatable-thead > tr > th:last-child),
.municipal-table-card :deep(.municipal-risk-table .p-datatable-tbody > tr > td:last-child),
.municipal-table-card :deep(.municipal-risk-table .p-datatable-tfoot > tr > td:last-child) {
  padding-right: 1.25rem;
}

.municipal-table-card :deep(.municipal-risk-table .col-municipio) {
  width: 25%;
}

.municipal-table-card :deep(.municipal-risk-table .col-count) {
  width: 9%;
  text-align: center;
}

.municipal-table-card :deep(.municipal-risk-table .col-percent) {
  width: 12%;
  text-align: center;
}

.municipal-table-card :deep(.municipal-risk-table .col-participation) {
  width: 13%;
  text-align: right;
}

.municipal-table-card :deep(.municipal-risk-table .col-money) {
  width: 13%;
  text-align: right;
}

.municipal-table-card :deep(.municipal-risk-table .col-count .p-column-header-content),
.municipal-table-card :deep(.municipal-risk-table .col-percent .p-column-header-content) {
  justify-content: center;
}

.municipal-table-card :deep(.municipal-risk-table .col-participation .p-column-header-content),
.municipal-table-card :deep(.municipal-risk-table .col-money .p-column-header-content) {
  justify-content: flex-end;
}

.municipal-table-card :deep(.municipal-risk-table .p-datatable-thead) {
  position: sticky;
  top: 0;
  z-index: 10;
}

.municipal-table-card :deep(.municipal-risk-table .p-datatable-wrapper) {
  border-radius: 0 0 12px 12px;
}

.municipal-table-card :deep(.municipal-risk-table .p-tag) {
  font-weight: 500;
  text-transform: none;
  border-radius: 6px;
  font-size: 0.65rem;
  padding: 0.2rem 0.5rem;
}

.municipal-table-card :deep(.municipal-risk-table .p-tag-value),
.municipal-table-card :deep(.municipal-risk-table .p-tag) {
  letter-spacing: 0.03em;
}
</style>
