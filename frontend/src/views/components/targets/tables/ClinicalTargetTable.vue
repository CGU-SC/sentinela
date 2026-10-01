<script setup>
import { computed, onMounted, ref } from 'vue';
import { useRouter } from 'vue-router';
import { useMetodologiaConfigStore } from '@/stores/metodologiaConfig';
import { useFrozenData } from '@/composables/useFrozenData';
import { useFormatting } from '@/composables/useFormatting';
import { useStatusClass } from '@/composables/useStatusClass';
import { AUDIT_THRESHOLDS } from '@/config/riskConfig';
import DataTable from 'primevue/datatable';
import Column from 'primevue/column';
import Button from 'primevue/button';
import Tag from 'primevue/tag';
import TableFooter from '@/views/components/common/TableFooter.vue';

const props = defineProps({
  targetMeta: { type: Object, required: true },
  rows: { type: Array, default: () => [] },
  loading: { type: Boolean, default: false },
  totalRecords: { type: Number, default: 0 },
  first: { type: Number, default: 0 },
  rowsPerPage: { type: Number, default: 20 },
  sortField: { type: String, default: 'valor_incompativel' },
  sortOrder: { type: Number, default: -1 },
  sourceNotice: { type: String, default: null },
});

const emit = defineEmits(['lazy-load', 'open-incompatibility']);
const router = useRouter();
const metodologiaConfig = useMetodologiaConfigStore();
const { formatCurrencyFull, formatTitleCase } = useFormatting();
const { conexaoMsClass } = useStatusClass();
const copiedKey = ref(null);
const auditHighValue = computed(() =>
  metodologiaConfig.loaded
    ? metodologiaConfig.auditHighValue
    : AUDIT_THRESHOLDS.HIGH_VALUE,
);
const loadingRef = computed(() => props.loading);
const tableSnapshot = useFrozenData(
  () => ({
    rows: props.rows,
    totalRecords: props.totalRecords,
    first: props.first,
    rowsPerPage: props.rowsPerPage,
    sortField: props.sortField,
    sortOrder: props.sortOrder,
  }),
  loadingRef,
);

onMounted(() => {
  metodologiaConfig.ensureLoaded().catch((error) => {
    console.warn('[ClinicalTargetTable] Não foi possível carregar a configuração metodológica.', error);
  });
});

function formatInteger(value) {
  if (value == null) return '—';
  return Number(value).toLocaleString('pt-BR', { maximumFractionDigits: 0 });
}

function formatDecimal(value, digits = 2) {
  if (value == null) return '—';
  return Number(value).toLocaleString('pt-BR', {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}

function formatPercent(value) {
  if (value == null) return '—';
  return `${formatDecimal(Number(value) * 100, 2)}%`;
}

function formatTableText(value) {
  return formatTitleCase(value) || 'â€”';
}

function goToEstabelecimento(event) {
  if (event.originalEvent?.target?.closest('.copy-btn')) return;
  const row = event.data;
  if (!row?.cnpj) return;
  router.push({ path: `/estabelecimentos/${row.cnpj}`, query: { s: 'indicadores' } });
}

function copyAndSignal(text, key) {
  if (!text) return;
  navigator.clipboard.writeText(text);
  copiedKey.value = key;
  setTimeout(() => {
    if (copiedKey.value === key) copiedKey.value = null;
  }, 1200);
}

function openIncompatibilityDialog(event, cnpj) {
  event.stopPropagation();
  if (!cnpj) return;
  emit('open-incompatibility', cnpj);
}

</script>

<template>
  <section class="target-table-card">
    <div class="section-header">
      <div class="section-icon-box">
        <i class="pi pi-list" />
      </div>
      <div class="section-title-block">
        <h2>Farmácias do alvo</h2>
        <span>{{ targetMeta.tableSubtitle }}</span>
      </div>
    </div>

    <DataTable
      :value="tableSnapshot.rows"
      size="small"
      class="enterprise-table com-rodape target-table ind-cnpj-table clickable-rows"
      lazy
      paginator
      :first="tableSnapshot.first"
      :rows="tableSnapshot.rowsPerPage"
      :totalRecords="tableSnapshot.totalRecords"
      :sortField="tableSnapshot.sortField"
      :sortOrder="tableSnapshot.sortOrder"
      @page="emit('lazy-load', $event)"
      @sort="emit('lazy-load', $event)"
      @row-click="goToEstabelecimento"
    >
      <Column
        field="razao_social"
        header="Razão Social"
        sortable
        headerClass="col-name"
        bodyClass="col-name"
      >
        <template #body="{ data }">
          <div class="razao-block">
            <span
              class="razao-social-cell"
              v-tooltip.top="formatTableText(data.razao_social)"
            >{{ formatTableText(data.razao_social) }}</span>
            <span class="cnpj-row">
              <span
                v-tooltip.top="data.is_matriz ? 'Matriz' : 'Filial'"
                :class="data.is_matriz ? 'tipo-badge matriz' : 'tipo-badge filial'"
              >
                <i :class="data.is_matriz ? 'pi pi-home' : 'pi pi-building'" />
              </span>
              <span class="cnpj-text">{{ data.cnpj }}</span>
              <i
                :class="['pi', copiedKey === data.cnpj + '-cnpj' ? 'pi-check text-success' : 'pi-copy', 'copy-btn']"
                v-tooltip.top="'Copiar CNPJ'"
                @click.stop="copyAndSignal(data.cnpj, data.cnpj + '-cnpj')"
              />
            </span>
          </div>
        </template>
      </Column>
      <Column
        field="municipio"
        header="Município"
        sortable
        headerClass="col-location"
        bodyClass="col-location"
      >
        <template #body="{ data }">
          <div class="loc-block">
            <span
              class="municipio-text"
              v-tooltip.top="formatTableText(data.municipio)"
            >{{ formatTableText(data.municipio) }}</span>
            <span class="uf-tag">{{ data.uf }}</span>
          </div>
        </template>
      </Column>
      <Column field="ano_base" header="Ano" sortable headerClass="col-year" bodyClass="col-year">
        <template #body="{ data }">
          <span class="year-cell">{{ data.ano_base }}</span>
        </template>
      </Column>
      <Column field="casos_observados" header="CPFs únicos" sortable headerClass="col-metric" bodyClass="col-metric">
        <template #body="{ data }">
          <div class="metric-stack align-right">
            <span class="metric-main">Observados {{ formatInteger(data.casos_observados) }}</span>
            <span class="metric-sub">Esperados {{ formatInteger(data.casos_esperados) }} | Razão {{ formatDecimal(data.razao_observado_esperado, 2) }}</span>
          </div>
        </template>
      </Column>
      <Column field="valor_incompativel" :header="targetMeta.valueHeader" sortable headerClass="col-money" bodyClass="col-money">
        <template #body="{ data }">
          <div class="metric-stack align-right">
            <span
              class="metric-main"
              :class="{ 'high-value-audit': data.valor_incompativel >= auditHighValue }"
            >{{ formatCurrencyFull(data.valor_incompativel) }}</span>
            <span class="metric-sub">Part. Município {{ formatPercent(data.participacao_municipio) }}</span>
          </div>
        </template>
      </Column>
      <Column
        field="is_conexao_ativa"
        header="Conexão MS"
        headerClass="col-badge-filter"
        bodyClass="col-badge-filter"
      >
        <template #body="{ data }">
          <Tag
            :value="data.is_conexao_ativa ? 'Ativa' : 'Inativa'"
            :class="conexaoMsClass(data.is_conexao_ativa)"
            v-tooltip.top="'Conexão com o Ministério da Saúde: ' + (data.is_conexao_ativa ? 'Ativa' : 'Inativa')"
          />
        </template>
      </Column>
      <Column
        header="Ações"
        headerClass="col-action"
        bodyClass="col-action"
      >
        <template #body="{ data }">
          <Button
            icon="pi pi-search"
            class="detail-btn"
            severity="secondary"
            text
            rounded
            v-tooltip.top="'Vendas com incompatibilidade clínica/patológica'"
            @click="openIncompatibilityDialog($event, data.cnpj)"
          />
        </template>
      </Column>

      <template #empty>
        <div class="target-table-empty">
          {{ sourceNotice || 'Nenhuma farmácia encontrada para o alvo selecionado.' }}
        </div>
      </template>
      <template #footer>
        <TableFooter
          :first="tableSnapshot.first"
          :rows="tableSnapshot.rowsPerPage"
          :total-records="tableSnapshot.totalRecords"
          :unidade="['estabelecimento', 'estabelecimentos']"
          @page="emit('lazy-load', $event)"
        />
      </template>
    </DataTable>
  </section>
</template>

<style scoped>
.target-table-card {
  overflow: hidden;
  background: var(--card-bg);
  border: 1px solid var(--card-border);
  border-radius: 8px;
  box-shadow: var(--shadow-sm);
}

.section-header {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 0.85rem 1rem;
  border-bottom: 1px solid var(--card-border);
}

.section-icon-box {
  width: 2rem;
  height: 2rem;
  border-radius: 8px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  background: color-mix(in srgb, var(--primary-color) 12%, transparent);
  color: var(--primary-color);
  flex-shrink: 0;
}

.section-title-block {
  min-width: 0;
}

.section-title-block h2 {
  margin: 0;
  color: var(--text-color-85);
  font-size: 0.82rem;
  font-weight: 600;
  letter-spacing: 0.05em;
  text-transform: uppercase;
}

.section-title-block span {
  display: block;
  margin-top: 0.15rem;
  color: var(--text-muted);
  font-size: 0.7rem;
}

.target-table {
  border: none;
}

.razao-block {
  display: flex;
  flex-direction: column;
  gap: 0.2rem;
  min-width: 0;
  overflow: hidden;
}

.razao-social-cell {
  cursor: default;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  color: var(--text-color-85);
  font-size: 0.86rem;
  font-weight: 600;
  line-height: 1.15;
  text-transform: none;
}

.cnpj-row {
  display: inline-flex;
  align-items: center;
  gap: 0.32rem;
  min-width: 0;
  color: var(--text-muted);
  line-height: 1.1;
}

.tipo-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 1.25rem;
  height: 1.25rem;
  border-radius: 6px;
  flex-shrink: 0;
  font-size: 0.68rem;
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
  font-size: 0.78rem;
  color: var(--text-muted);
  letter-spacing: 0.01em;
}

.copy-btn {
  display: inline-flex;
  justify-content: center;
  width: 1.4rem;
  flex-shrink: 0;
  font-size: 0.76rem;
  color: var(--text-muted);
  cursor: pointer;
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
  color: var(--text-color-85);
  line-height: 1.15;
  text-transform: none;
}

.uf-tag {
  display: inline-flex;
  align-items: center;
  width: fit-content;
  max-width: 100%;
  padding: 0.08rem 0.34rem;
  border-radius: 4px;
  background: color-mix(in srgb, var(--primary-color) 14%, transparent);
  color: var(--primary-color);
  font-size: 0.66rem;
  font-weight: 600;
  letter-spacing: 0.04em;
  text-transform: uppercase;
}

.metric-stack {
  display: flex;
  flex-direction: column;
  gap: 0.18rem;
  min-width: 0;
}

.metric-stack.align-right {
  align-items: flex-end;
  text-align: right;
}

.metric-main {
  color: var(--text-color-85);
  font-size: 0.8rem;
  font-weight: 600;
  line-height: 1.12;
}

.high-value-audit {
  padding: 0.15rem 0.65rem;
  display: inline-flex;
  align-items: center;
  justify-content: flex-end;
  color: var(--risk-high);
  background: color-mix(in srgb, var(--risk-high) 10%, transparent);
  border-left: 3px solid var(--risk-high);
  border-radius: 0 6px 6px 0;
  font-size: 0.75rem;
  font-weight: 600;
}

.metric-sub {
  color: var(--text-muted);
  font-size: 0.68rem;
  line-height: 1.1;
  white-space: nowrap;
}

.target-table-empty {
  padding: 1rem;
  color: var(--text-muted);
  text-align: center;
  font-size: 0.78rem;
}

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

:deep(.ind-cnpj-table .p-datatable-thead > tr > th:first-child),
:deep(.ind-cnpj-table .p-datatable-tbody > tr > td:first-child) {
  padding-left: 1.25rem;
}

:deep(.ind-cnpj-table .p-datatable-thead > tr > th:last-child),
:deep(.ind-cnpj-table .p-datatable-tbody > tr > td:last-child) {
  padding-right: 1.25rem;
}

:deep(.ind-cnpj-table .p-datatable-tbody > tr > td) {
  color: var(--text-color-85) !important;
}

:deep(.ind-cnpj-table .col-name) {
  width: 27%;
}

:deep(.ind-cnpj-table .col-location) {
  width: 13%;
}

:deep(.ind-cnpj-table .col-year) {
  width: 7%;
  text-align: center;
}

.year-cell {
  color: var(--text-color-85);
  font-size: 0.8rem;
  font-weight: 600;
  line-height: 1.12;
}

:deep(.ind-cnpj-table .col-badge-filter) {
  width: 9%;
  text-align: center;
  padding-left: 0.25rem;
  padding-right: 0.25rem;
}

:deep(.ind-cnpj-table .col-action) {
  width: 5%;
  text-align: center;
  padding-left: 0.1rem;
  padding-right: 0.1rem;
}

:deep(.ind-cnpj-table .col-metric) {
  width: 19%;
  text-align: right;
}

:deep(.ind-cnpj-table .col-money) {
  width: 20%;
  text-align: right;
}

:deep(.ind-cnpj-table .col-metric .p-column-header-content),
:deep(.ind-cnpj-table .col-money .p-column-header-content) {
  justify-content: flex-end;
}

:deep(.ind-cnpj-table .col-year .p-column-header-content) {
  justify-content: center;
}

:deep(.ind-cnpj-table .col-badge-filter .p-column-header-content) {
  justify-content: center;
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

:deep(.ind-cnpj-table .detail-btn.p-button) {
  width: 1.75rem;
  height: 1.75rem;
  padding: 0;
}

:deep(.ind-cnpj-table .detail-btn.p-button:focus),
:deep(.ind-cnpj-table .detail-btn.p-button:active),
:deep(.ind-cnpj-table .detail-btn.p-button.p-focus) {
  outline: none !important;
  box-shadow: none !important;
}

:deep(.ind-cnpj-table .detail-btn.p-button:focus-visible) {
  box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--primary-color) 48%, transparent) !important;
}

:deep(.target-table .p-datatable-thead > tr > th) {
  background: var(--card-bg);
  color: var(--text-muted);
  border-color: var(--card-border);
  font-size: 0.68rem;
  font-weight: 600;
  letter-spacing: 0.05em;
  text-transform: uppercase;
}

:deep(.target-table .p-datatable-tbody > tr > td) {
  background: var(--card-bg);
  color: var(--text-color-85);
  border-color: var(--card-border);
  font-size: 0.76rem;
  text-transform: none;
}

:deep(.p-tag) {
  padding: 0.2rem 0.5rem;
  border-radius: 6px;
  font-weight: 600;
  font-size: 0.65rem;
  border: 1px solid transparent;
}

:deep(.p-tag-value),
:deep(.p-tag) {
  text-transform: uppercase !important;
  letter-spacing: 0.03em;
}
</style>
