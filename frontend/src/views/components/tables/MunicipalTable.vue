<script setup>
import { computed, ref, watch } from "vue";
import { useAnalyticsStore } from "@/stores/analytics";
import { useFilterStore } from "@/stores/filters";
import { useRiskMetrics } from "@/composables/useRiskMetrics";
import { useFormatting } from "@/composables/useFormatting";
import { useTableAggregation } from "@/composables/useTableAggregation";
import { useDelayedLoading } from "@/composables/useDelayedLoading";
import { storeToRefs } from "pinia";
import DataTable from "primevue/datatable";
import Column from "primevue/column";
import Tag from "primevue/tag";
import TableFooter from "@/views/components/common/TableFooter.vue";

// Paginação no cliente (o rodapé padrão controla a página da DataTable).
const LINHAS_POR_PAGINA = 20;
const paginaFirst = ref(0);

const analyticsStore = useAnalyticsStore();
const filterStore = useFilterStore();
const { resultadoMunicipios, isLoading } = storeToRefs(analyticsStore);
const { getRiskClass } = useRiskMetrics();
const { formatBRL, formatNumber, formatPercent } = useFormatting();

// Mantém os dados anteriores visíveis durante o re-fetch, evitando flash de tabela vazia
const cachedMunicipios = ref(resultadoMunicipios.value);
const showRefreshing = useDelayedLoading(isLoading);
watch([resultadoMunicipios, isLoading], ([newData, loading]) => {
  if (newData?.length > 0 && !loading) cachedMunicipios.value = newData;
}, { immediate: true });

// Agregação de rodapé
const { totals } = useTableAggregation(cachedMunicipios, {
  sums: ["cnpjs", "valSemComp", "totalMov", "qtdeSemComp", "totalQtde"],
  percents: [
    {
      field: "percValSemComp",
      numerator: "valSemComp",
      denominator: "totalMov",
    },
    {
      field: "percQtdeSemComp",
      numerator: "qtdeSemComp",
      denominator: "totalQtde",
    },
  ],
});

const tableFooter = computed(() => {
  const t = totals.value;
  if (!Object.keys(t).length) return {};
  return {
    cnpjs: formatNumber(t.cnpjs),
    percValSemComp: formatPercent(t.percValSemComp),
    valSemComp: formatBRL(t.valSemComp),
    totalMov: formatBRL(t.totalMov),
    percQtdeSemComp: formatPercent(t.percQtdeSemComp),
    qtdeSemComp: formatNumber(t.qtdeSemComp),
    totalQtde: formatNumber(t.totalQtde),
  };
});

const onRowSelect = (event) => {
  const { id_ibge7 } = event.data;
  if (id_ibge7 == null) throw new Error("Municipio sem id_ibge7 no resultado analitico.");
  filterStore.selectedMunicipio = String(id_ibge7);
};

let _lastHoveredRow = null;
const onTableHover = (e) => {
  const row = e.target.closest('tr[data-p-selectable-row="true"]');
  if (row === _lastHoveredRow) return;
  _lastHoveredRow = row;
  filterStore.hoveredMunicipioName = row
    ? (row.cells[1]?.textContent?.trim() ?? null)
    : null;
};
const onTableLeave = () => {
  _lastHoveredRow = null;
  filterStore.hoveredMunicipioName = null;
};
</script>

<template>
  <div
    class="table-section shadow-card modern-scroll-card"
    :class="{ 'is-refreshing': showRefreshing }"
    @mouseover="onTableHover"
    @mouseleave="onTableLeave"
  >
    <div class="section-header">
      <div class="header-icon-box">
        <i class="pi pi-map-marker"></i>
      </div>
      <div class="header-text-box">
        <h3>Análise por município</h3>
        <span class="subtitle"
          >{{
            filterStore.selectedUF === "Todos"
              ? "Brasil"
              : filterStore.selectedUF
          }}
          — {{ cachedMunicipios.length }} Municípios</span
        >
      </div>
      <div class="spacer"></div>
    </div>

    <DataTable
      :value="cachedMunicipios"
      size="small"
      stripedRows
      removableSort
      paginator
      v-model:first="paginaFirst"
      :rows="LINHAS_POR_PAGINA"
      selectionMode="single"
      @row-click="onRowSelect"
      sortField="valSemComp"
      :sortOrder="-1"
      class="custom-table enterprise-table com-rodape clickable-rows"
    >
      <Column field="uf" header="UF" sortable style="width: 5%">
        <template #footer>TOTAL</template>
      </Column>

      <Column
        field="municipio"
        header="Município"
        sortable
        style="width: 15%"
      ></Column>

      <Column field="cnpjs" header="Qtde CNPJs" sortable style="width: 10%">
        <template #body="slotProps">
          <span>{{ formatNumber(slotProps.data.cnpjs) }}</span>
        </template>
        <template #footer>{{ tableFooter.cnpjs }}</template>
      </Column>

      <Column
        field="percValSemComp"
        header="% Valor sem Comprovação"
        sortable
        style="width: 12%"
      >
        <template #body="slotProps">
          <Tag
            :value="formatPercent(slotProps.data.percValSemComp)"
            :class="getRiskClass(slotProps.data.percValSemComp)"
          />
        </template>
        <template #footer>{{ tableFooter.percValSemComp }}</template>
      </Column>

      <Column
        field="valSemComp"
        header="Valor sem Comprovação"
        sortable
        style="width: 15%"
      >
        <template #body="slotProps">
          <span>{{ formatBRL(slotProps.data.valSemComp) }}</span>
        </template>
        <template #footer>{{ tableFooter.valSemComp }}</template>
      </Column>

      <Column
        field="totalMov"
        header="Valor Total Vendas"
        sortable
        style="width: 15%"
      >
        <template #body="slotProps">
          <span>{{ formatBRL(slotProps.data.totalMov) }}</span>
        </template>
        <template #footer>{{ tableFooter.totalMov }}</template>
      </Column>

      <Column
        field="percQtdeSemComp"
        header="% Qtde s/ Comp"
        sortable
        style="width: 12%"
      >
        <template #body="slotProps">
          <Tag
            :value="formatPercent(slotProps.data.percQtdeSemComp)"
            :class="getRiskClass(slotProps.data.percQtdeSemComp)"
          />
        </template>
        <template #footer>{{ tableFooter.percQtdeSemComp }}</template>
      </Column>
      <template #footer>
        <TableFooter
          :first="paginaFirst"
          :rows="LINHAS_POR_PAGINA"
          :total-records="cachedMunicipios.length"
          :unidade="['município', 'municípios']"
          @page="paginaFirst = $event.first"
        />
      </template>
    </DataTable>
  </div>
</template>

<style scoped>
.table-section {
  display: flex;
  flex-direction: column;
  transition: opacity 0.25s ease;
}

.modern-scroll-card {
  border: 1px solid var(--card-border);
  background: var(--card-bg);
}

.section-header {
  padding: 1.25rem 1.5rem;
  display: flex;
  align-items: center;
  gap: 1rem;
  border-bottom: 1px solid var(--tabs-border);
}

.header-icon-box {
  width: 42px;
  height: 42px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: color-mix(in srgb, var(--accent-indigo) 10%, transparent);
  color: var(--accent-indigo);
  border-radius: 10px;
  font-size: 1.25rem;
}

.header-text-box h3 {
  margin: 0;
  font-size: 1.1rem;
  font-weight: 700;
  letter-spacing: -0.01em;
}

.subtitle {
  font-size: 0.85rem;
  color: var(--text-muted, #64748b);
}

.spacer {
  flex: 1;
}

.is-refreshing {
  opacity: 0.45;
  pointer-events: none;
}

:deep(.clickable-rows .p-datatable-tbody > tr) {
  cursor: pointer;
}

/* Garante que o cabeçalho da tabela fique fixo ao rolar */
:deep(.p-datatable-thead) {
  position: sticky;
  top: 0;
  z-index: 10;
}

:deep(.p-datatable-wrapper) {
  border-radius: 0 0 12px 12px;
}

/* Estilização moderna da scrollbar */
:deep(.p-datatable-wrapper::-webkit-scrollbar) {
  width: 8px;
}
:deep(.p-datatable-wrapper::-webkit-scrollbar-track) {
  background: var(--bg-color, #f8fafc);
}
:deep(.p-datatable-wrapper::-webkit-scrollbar-thumb) {
  background: var(--scrollbar-thumb);
  border-radius: 10px;
}
:deep(.p-datatable-wrapper::-webkit-scrollbar-thumb:hover) {
  background: #cbd5e1;
}

/* light/dark automático via var(--accent-indigo) — override removido */

/* RESET DE CAIXA ALTA FORÇADA */
:deep(.p-datatable-tbody td),
:deep(.p-tag-value),
:deep(.p-tag) {
  text-transform: none !important;
  font-variant: normal !important;
}
</style>
