<script setup>
/**
 * RegionalMunicipalityTable.vue
 * Exibe o resumo dos municípios da Região de Saúde selecionada:
 * população, quantidade de farmácias e densidade (hab/farmácia).
 */
import { computed, ref, watch } from 'vue';
import { useFormatting } from '@/composables/useFormatting';
import { useRiskMetrics } from '@/composables/useRiskMetrics';
import DataTable from 'primevue/datatable';
import Column from 'primevue/column';
import Tag from 'primevue/tag';
import TableFooter from '@/views/components/common/TableFooter.vue';

const props = defineProps({
  municipios: { type: Array, default: () => [] },
  municipioAtual: { type: String, default: null },
  ufAtual: { type: String, default: null },
  regiaoNome: { type: String, default: '' },
  selectedFilter: { type: [String, Number], default: null },
});

const emits = defineEmits(['select-municipio']);

const { formatBRL, formatPercent } = useFormatting();
const { getRiskClass } = useRiskMetrics();

const ROWS_PER_PAGE = 10;
const first = ref(0);

// Replica a ordenação padrão da tabela para calcular em qual página o município selecionado está
const sortedMunicipios = computed(() =>
  [...props.municipios].sort((a, b) => (b.valSemComp || 0) - (a.valSemComp || 0))
);

watch(() => props.selectedFilter, (newVal) => {
  if (!newVal) return;
  const idx = sortedMunicipios.value.findIndex(m => Number(m.id_ibge7) === Number(newVal));
  if (idx >= 0) {
    first.value = Math.floor(idx / ROWS_PER_PAGE) * ROWS_PER_PAGE;
  }
});

function rowClass(data) {
  // 1. Prioridade total para a Seleção Ativa (Filtro Cruzado)
  const isSelected = props.selectedFilter && Number(data.id_ibge7) === Number(props.selectedFilter);
  if (isSelected) return 'row-selected';

  // 2. Destaque do Município Sede apenas se não houver filtro ativo
  const isHome = !props.selectedFilter && 
                 props.municipioAtual &&
                 data.municipio?.toUpperCase() === props.municipioAtual?.toUpperCase() &&
                 data.uf?.toUpperCase() === props.ufAtual?.toUpperCase();

  if (isHome) return 'row-highlight';
  return '';
}

function onRowClick(event) {
  emits('select-municipio', event.data.id_ibge7, event.data.municipio);
}

const totals = computed(() => {
  const pop      = props.municipios.reduce((s, m) => s + (m.populacao      || 0), 0);
  const far      = props.municipios.reduce((s, m) => s + (m.qtd_farmacias  || 0), 0);
  const totalMov = props.municipios.reduce((s, m) => s + (m.totalMov       || 0), 0);
  const valSem   = props.municipios.reduce((s, m) => s + (m.valSemComp     || 0), 0);
  const dens     = far > 0 ? pop / far : 0;
  const perc     = totalMov > 0 ? (valSem / totalMov) * 100 : 0;
  return { pop, far, dens: Math.round(dens), totalMov, valSem, perc };
});
import { useFilterStore } from '@/stores/filters';
const filterStore = useFilterStore();

let _lastHoveredRow = null;
const onTableHover = (e) => {
  const row = e.target.closest('.p-datatable-tbody > tr');
  if (row === _lastHoveredRow) return;
  _lastHoveredRow = row;
  const cell = row?.cells[0]; // Primeira coluna é o Nome do Município
  filterStore.hoveredMunicipioName = cell ? cell.textContent?.trim() : null;
};
const onTableLeave = () => {
  _lastHoveredRow = null;
  filterStore.hoveredMunicipioName = null;
};
</script>

<template>
  <div class="table-section" @mouseover="onTableHover" @mouseleave="onTableLeave">
    <div class="section-header">
      <i class="pi pi-map-marker section-icon"></i>
      <div class="header-text-box">
        <div class="title-with-filter">
          <h3 class="section-title-text">MUNICÍPIOS DA REGIÃO {{ regiaoNome?.toUpperCase() }} - {{ ufAtual }}</h3>
          <div v-if="selectedFilter" class="active-filter-tag">
            <span class="filter-label">Filtro:</span>
            <span class="filter-value">{{ municipios.find(m => m.id_ibge7 === selectedFilter)?.municipio?.toUpperCase() || 'FILTRO ATIVO' }}</span>
            <button 
              class="filter-clear-btn" 
              title="Limpar Filtro"
              @click="emits('select-municipio', selectedFilter)"
            >
              <i class="pi pi-times" />
            </button>
          </div>
        </div>
        <p class="subtitle">{{ municipios.length }} municípios na região</p>
      </div>
    </div>

    <DataTable
      :value="municipios"
      size="small"
      removableSort
      paginator
      :rows="ROWS_PER_PAGE"
      v-model:first="first"
      sortField="valSemComp"
      :sortOrder="-1"
      :row-class="rowClass"
      class="custom-table enterprise-table com-rodape clickable-rows"
      @row-click="onRowClick"
    >

      <Column field="municipio" header="Município" sortable style="width: 25%; text-transform: none">
        <template #footer>
          {{ municipios.length }} Municípios
        </template>
      </Column>

      <Column field="populacao" header="População" sortable style="width: 10%">
        <template #body="{ data }">
          {{ (data.populacao || 0).toLocaleString('pt-BR') }}
        </template>
        <template #footer>
          {{ totals.pop.toLocaleString('pt-BR') }}
        </template>
      </Column>

      <Column field="qtd_farmacias" header="Farm." sortable style="width: 7%" class="align-center">
        <template #body="{ data }">
          <span class="badge-count">{{ data.qtd_farmacias }}</span>
        </template>
        <template #footer>
          {{ totals.far }}
        </template>
      </Column>


      <Column field="totalMov" header="Vendas" sortable style="width: 15%">
        <template #body="{ data }">
          {{ formatBRL(data.totalMov) }}
        </template>
        <template #footer>
          {{ formatBRL(totals.totalMov) }}
        </template>
      </Column>

      <Column field="valSemComp" header="Valor s/ C." sortable style="width: 15%">
        <template #body="{ data }">
          {{ formatBRL(data.valSemComp) }}
        </template>
        <template #footer>
          {{ formatBRL(totals.valSem) }}
        </template>
      </Column>

      <Column field="percValSemComp" header="% s/ C." sortable style="width: 12%">
        <template #body="{ data }">
          <Tag :value="formatPercent(data.percValSemComp)" :class="getRiskClass(data.percValSemComp)" />
        </template>
        <template #footer>
          {{ formatPercent(totals.perc) }}
        </template>
      </Column>
      <template #footer>
        <TableFooter
          :first="first"
          :rows="ROWS_PER_PAGE"
          :total-records="municipios.length"
          :unidade="['município', 'municípios']"
          @page="first = $event.first"
        />
      </template>
    </DataTable>
  </div>
</template>

<style scoped>
.table-section {
  display: flex;
  flex-direction: column;
  background: var(--card-bg);
  border: 1px solid var(--card-border);
  border-radius: 12px;
  padding: 1.25rem;
  box-shadow: 0 4px 15px rgba(0,0,0,0.1);
}

.section-header {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 0.5rem 0;
  border-bottom: 1px solid var(--tabs-border);
  margin-bottom: 1rem;
}

.section-icon {
  font-size: 1rem;
  color: var(--primary-color);
}

.header-text-box {
  display: flex;
  flex-direction: column;
}

.header-text-box h3 {
  margin: 0;
  padding: 0;
}

.header-text-box p {
  margin: 0;
  padding: 0;
}

.section-title-text {
  font-size: 0.85rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--text-color-85);
  line-height: 1.2;
  opacity: 0.85;
}

.title-with-filter {
  display: flex;
  align-items: center;
  gap: 1rem;
  min-height: 28px; /* Reserva o espaço para evitar o "salto" no layout */
}

.active-filter-tag {
  display: inline-flex;
  align-items: center;
  gap: 0.5rem;
  background: color-mix(in srgb, var(--primary-color) 12%, var(--card-bg));
  border: 1px solid color-mix(in srgb, var(--primary-color) 40%, transparent);
  padding: 0 0.75rem;
  height: 28px;
  border-radius: 6px;
  animation: fadeIn 0.2s ease-out;
  box-shadow: 0 0 0 3px color-mix(in srgb, var(--primary-color) 10%, transparent);
}

.filter-label {
  font-size: 0.65rem;
  font-weight: 700;
  text-transform: uppercase;
  color: var(--primary-color);
  letter-spacing: 0.06em;
}

.filter-value {
  font-size: 0.8rem;
  font-weight: 700;
  color: var(--primary-color);
  letter-spacing: 0.02em;
}

.filter-clear-btn {
  background: transparent;
  border: none;
  cursor: pointer;
  padding: 0 0.15rem;
  display: flex;
  align-items: center;
  transition: all 0.15s ease;
  color: var(--primary-color);
  opacity: 0.7;
}

.filter-clear-btn:hover {
  color: var(--risk-high);
  opacity: 1;
  transform: scale(1.15);
}

.filter-clear-btn i {
  font-size: 0.75rem;
}

@keyframes pulse-mini {
  0%, 100% { box-shadow: 0 0 0 0 color-mix(in srgb, var(--risk-high) 25%, transparent); }
  50%       { box-shadow: 0 0 0 5px color-mix(in srgb, var(--risk-high) 0%, transparent); }
}

@keyframes fadeIn {
  from { opacity: 0; transform: translateX(-10px); }
  to { opacity: 1; transform: translateX(0); }
}

.subtitle {
  font-size: 0.85rem;
  color: var(--text-muted, #64748b);
}

.badge-count {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 0.15rem 0.55rem;
  border-radius: 20px;
  font-size: 0.78rem;
  font-weight: 700;
  background: color-mix(in srgb, var(--primary-color) 12%, transparent);
  color: var(--primary-color);
}

:deep(.p-datatable),
:deep(.p-datatable-wrapper),
:deep(.p-datatable-table),
:deep(.p-datatable-thead > tr > th),
:deep(.p-datatable-tbody > tr > td),
:deep(.p-datatable-tfoot > tr > td) {
  background: var(--card-bg) !important;
  background-color: var(--card-bg) !important;
}

:deep(.p-datatable .p-datatable-thead > tr > th) {
  color: var(--text-secondary) !important;
  font-size: 0.68rem !important;
  font-weight: 600 !important;
  text-transform: uppercase !important;
  letter-spacing: 0.02em !important;
  border-bottom: 2px solid var(--tabs-border) !important;
  padding: 0.6rem 0.5rem !important;
}

:deep(.p-datatable .p-datatable-tbody > tr > td) {
  cursor: pointer;
  border-bottom: 1px solid var(--tabs-border) !important;
  transition: background-color 0.15s ease;
  font-size: 0.8rem !important;
  color: color-mix(in srgb, var(--text-color-85) 85%, transparent) !important;
  padding: 0.55rem 0.5rem !important;
}

:deep(.p-datatable .p-datatable-tbody > tr:hover > td) {
  background: var(--table-hover) !important;
  cursor: pointer;
}

:deep(.p-datatable .p-datatable-tfoot > tr > td) {
  background: var(--table-footer-bg) !important;
  border-top: 2px solid var(--tabs-border) !important;
  font-weight: 600 !important;
  color: color-mix(in srgb, var(--text-color-85) 85%, transparent) !important;
  padding: 0.75rem 1rem !important;
}

:deep(.p-datatable-thead) {
  position: sticky;
  top: 0;
  z-index: 10;
  background: var(--card-bg) !important;
}

/* Destaque do Município da Farmácia Atual (Home) - Apenas quando sem filtro */
:deep(.p-datatable-tbody > tr.row-highlight > td) {
  background-color: color-mix(in srgb, var(--primary-color) 8%, var(--card-bg)) !important;
  color: var(--primary-color) !important;
}

:deep(.p-datatable-tbody > tr.row-highlight > td:first-child) {
  border-left: 4px solid color-mix(in srgb, var(--primary-color) 40%, transparent) !important;
}

/* Destaque da Seleção Ativa (Filtro Cruzado) */
:deep(.p-datatable-tbody > tr.row-selected > td) {
  background-color: color-mix(in srgb, var(--primary-color) 16%, var(--card-bg)) !important;
  color: var(--primary-color) !important;
}

:deep(.p-datatable-tbody > tr.row-selected > td:first-child) {
  border-left: 4px solid var(--primary-color) !important;
}

:deep(.p-datatable-tbody > tr.row-selected td) {
  font-weight: 700;
}

/* Força o alinhamento dos cabeçalhos numéricos */
:deep(.align-right .p-column-header-content) {
  justify-content: flex-end !important;
  text-align: right !important;
}

:deep(.align-center .p-column-header-content) {
  justify-content: center !important;
  text-align: center !important;
}

/* Garante que o corpo e o rodapé sigam a mesma regra */
:deep(.align-right) {
  text-align: right !important;
}

:deep(.align-center) {
  text-align: center !important;
}

/* Padroniza todos os headers para o novo padrão Clean */
:deep(.p-datatable-thead th) {
  padding: 0.75rem 1rem !important;
}

:deep(.p-datatable-wrapper) {
  border-radius: 0 0 12px 12px;
  /* Altura FIXA para 10 linhas (modo small) sem ativar scrollbar */
  height: 495px;
  overflow-y: hidden !important;
}

:deep(.p-datatable-tbody td),
:deep(.p-tag-value),
:deep(.p-tag) {
  text-transform: none !important;
  font-variant: normal !important;
}
</style>
