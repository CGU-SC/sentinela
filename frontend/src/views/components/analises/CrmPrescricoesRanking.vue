<script setup>
import { computed } from 'vue';
import Paginator from 'primevue/paginator';
import { useFormatting } from '@/composables/useFormatting';
import { useFrozenData } from '@/composables/useFrozenData';
import { analysisTooltip } from '@/config/analysisTooltipConfig';

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
  // Qualquer busca em andamento (filtro ou pagina): a tabela mantem a versao
  // anterior ate a resposta chegar, como em /estabelecimentos.
  isRefreshing: { type: Boolean, default: false },
  isStale: { type: Boolean, default: false },
  // Filtro de farmacia ativo: mostra as prescricoes nas farmacias filtradas.
  farmaciasFiltradas: { type: Boolean, default: false },
});

const refreshingRef = computed(() => props.isRefreshing);
const snapshot = useFrozenData(
  () => ({
    rows: props.rows,
    escopo: props.escopo,
    totalRecords: props.totalRecords,
    first: props.first,
    pageSize: props.pageSize,
    farmaciasFiltradas: props.farmaciasFiltradas,
  }),
  refreshingRef,
);

const emit = defineEmits(['page', 'select-medico']);
const rankingInfoTooltip = computed(() => analysisTooltip('crmRanking', {
  extraSections: snapshot.value.farmaciasFiltradas
    ? [{
      label: 'Farmácias filtradas',
      text: 'Com filtros de farmácia, entram os médicos que prescreveram em pelo menos uma farmácia filtrada do escopo em algum mês do período. Taxa e meses (inclusive os de taxa elevada) são os mesmos do ranking sem filtro (todas as prescrições do médico no escopo); as duas últimas colunas mostram quanto delas foi nas farmácias filtradas.',
    }]
    : [],
}));

function formatPercent(value) {
  return value == null ? '—' : `${Number(value).toFixed(1).replace('.', ',')}%`;
}
const { formatNumberFull, formatTitleCase } = useFormatting();

function onPage(event) {
  emit('page', event);
}

function doctorLabel(row) {
  return row.no_medico ? formatTitleCase(row.no_medico) : 'Médico não localizado';
}

function crmLabel(row) {
  if (row.nu_crm == null) return `CRM ${row.id_medico}`;
  return `CRM ${formatNumberFull(row.nu_crm)}${row.sg_uf ? `/${row.sg_uf}` : ''}`;
}
</script>

<template>
  <section class="crm-ranking-panel enterprise-table">
    <header class="ranking-header">
      <div>
        <div class="ranking-title-row">
          <h2>Ranking de médicos por taxa diária</h2>
          <i class="pi pi-info-circle info-icon" v-tooltip.bottom="rankingInfoTooltip" aria-label="Como ler o ranking" />
        </div>
        <span v-if="error && snapshot.rows.length" class="ranking-status ranking-status--error" role="alert" :aria-label="`${error} Resultado anterior exibido.`" v-tooltip.bottom="error">
          Falha ao atualizar · resultado anterior exibido
        </span>
        <span v-else-if="isRefreshing && snapshot.rows.length" class="ranking-status" role="status">
          {{ isStale ? 'Atualizando filtros' : 'Atualizando ranking' }} · resultado anterior de {{ snapshot.escopo }} exibido
        </span>
        <span v-else>Maiores taxas · {{ snapshot.escopo }}</span>
      </div>
      <i class="pi pi-sort-amount-down" />
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
    <div
      v-else
      class="ranking-table-wrap"
      :class="{ 'ranking-table-wrap--loading': isPageLoading }"
      :aria-busy="isRefreshing"
    >
      <table class="ranking-table" :class="{ 'ranking-table--filtradas': snapshot.farmaciasFiltradas }">
        <!-- Larguras fixas (table-layout: fixed): nao mudam com o conteudo da pagina. -->
        <colgroup>
          <col class="col-rank">
          <col class="col-doctor">
          <col class="col-rate">
          <col class="col-num">
          <col class="col-num">
          <col class="col-num-sm">
          <col class="col-num">
          <col class="col-num">
          <col v-if="snapshot.farmaciasFiltradas" class="col-num-lg">
          <col v-if="snapshot.farmaciasFiltradas" class="col-num-lg">
        </colgroup>
        <thead>
          <tr>
            <th>POS.</th>
            <th>MÉDICO / REGISTRO</th>
            <th>TAXA / DIA</th>
            <th>PRESCRIÇÕES</th>
            <th>DIAS C/ PRESCRIÇÃO</th>
            <th>MESES ATIVOS</th>
            <th>MESES COM TAXA ELEVADA</th>
            <th>% MESES COM TAXA ELEVADA</th>
            <th v-if="snapshot.farmaciasFiltradas">PRESCR. FARMÁCIAS FILTRADAS</th>
            <th v-if="snapshot.farmaciasFiltradas">% NAS FARMÁCIAS FILTRADAS</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="row in snapshot.rows"
            :key="row.id_medico"
            class="ranking-row"
            tabindex="0"
            :aria-label="`Abrir histórico de ${doctorLabel(row)}`"
            @click="emit('select-medico', row)"
            @keydown.enter="emit('select-medico', row)"
          >
            <td class="rank-cell">{{ row.rank }}</td>
            <td>
              <span class="doctor-name">{{ doctorLabel(row) }}</span>
              <span class="doctor-crm">{{ crmLabel(row) }}</span>
            </td>
            <td class="rate-cell">{{ Number(row.taxa_prescricoes_dia).toFixed(2).replace('.', ',') }}</td>
            <td>{{ formatNumberFull(row.nu_prescricoes) }}</td>
            <td>{{ formatNumberFull(row.qtd_dias_com_prescricao) }}</td>
            <td>{{ formatNumberFull(row.qtd_meses_ativos) }}</td>
            <td>{{ formatNumberFull(row.qtd_meses_alta_intensidade) }}</td>
            <td>{{ `${Number(row.percentual_meses_alta_intensidade).toFixed(1).replace('.', ',')}%` }}</td>
            <td v-if="snapshot.farmaciasFiltradas">{{ formatNumberFull(row.nu_prescricoes_farmacias_filtradas) }}</td>
            <td v-if="snapshot.farmaciasFiltradas">{{ formatPercent(row.percentual_prescricoes_farmacias_filtradas) }}</td>
          </tr>
        </tbody>
      </table>
      <div v-if="isPageLoading" class="ranking-table-loading">
        <i class="pi pi-spin pi-spinner" />
        <span>Carregando página...</span>
      </div>
    </div>

    <div v-if="pageError && snapshot.rows.length" class="ranking-page-error">
      <i class="pi pi-exclamation-circle" />
      <span>{{ pageError }}</span>
    </div>

    <Paginator
      v-if="snapshot.rows.length && snapshot.totalRecords > 0"
      :first="snapshot.first"
      :rows="snapshot.pageSize"
      :total-records="snapshot.totalRecords"
      :rows-per-page-options="[25, 50, 100]"
      :disabled="isRefreshing || !!error || isStale"
      class="crm-ranking-paginator"
      @page="onPage"
    />
  </section>
</template>

<style scoped>
.crm-ranking-panel { background: var(--card-bg); border: 1px solid var(--card-border); border-radius: 12px; overflow: hidden; }
.ranking-header { display: flex; align-items: center; justify-content: space-between; gap: 1rem; padding: .9rem 1.15rem; border-bottom: 1px solid var(--tabs-border); }
.ranking-header h2 { margin: 0; color: var(--text-color-85); font-size: .84rem; font-weight: 600; }
.ranking-header span { display: block; margin-top: .2rem; color: var(--text-muted); font-size: .68rem; }
.ranking-header > div { min-width: 0; }
.ranking-header .ranking-status { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.ranking-header .ranking-status--error { color: var(--risk-high); }
.ranking-header > i { color: var(--primary-color); }
.ranking-state { min-height: 180px; display: flex; align-items: center; justify-content: center; gap: .6rem; color: var(--text-muted); font-size: .8rem; }
.ranking-state i { color: var(--primary-color); }
.ranking-state--error { text-align: left; }
.ranking-state--error strong, .ranking-state--error span { display: block; }
.ranking-state--error strong { color: var(--text-color-85); font-size: .82rem; font-weight: 600; }
.ranking-state--error span { margin-top: .25rem; font-size: .72rem; }
.ranking-table-wrap { position: relative; overflow-x: auto; overflow-y: hidden; }
.ranking-table-wrap--loading { cursor: progress; }
.ranking-table-wrap--loading .ranking-table { opacity: .58; }
.ranking-table-loading { position: absolute; inset: 0; display: flex; align-items: center; justify-content: center; gap: .5rem; background: color-mix(in srgb, var(--card-bg) 72%, transparent); color: var(--text-muted); font-size: .76rem; pointer-events: none; }
.ranking-page-error { display: flex; align-items: center; gap: .45rem; padding: .55rem 1rem; border-top: 1px solid color-mix(in srgb, var(--risk-high) 25%, var(--tabs-border)); color: var(--risk-high); font-size: .7rem; }
.ranking-page-error i { flex-shrink: 0; }
.ranking-table { width: 100%; table-layout: fixed; border-collapse: collapse; color: var(--text-color-85); font-size: .76rem; }
.ranking-table { min-width: 63rem; }
.ranking-table--filtradas { min-width: 81rem; }
.ranking-table .col-rank { width: 3.5rem; }
.ranking-table .col-rate { width: 6.5rem; }
.ranking-table .col-num-sm { width: 6.5rem; }
.ranking-table .col-num { width: 8rem; }
.ranking-table .col-num-lg { width: 9rem; }
.ranking-table th { position: static; padding: .65rem .8rem; background: var(--table-header-bg); color: var(--text-muted); font-size: .62rem; font-weight: 600; letter-spacing: .04em; text-align: left; white-space: normal; vertical-align: bottom; line-height: 1.3; }
.ranking-table td { padding: .62rem .8rem; border-top: 1px solid var(--tabs-border); vertical-align: middle; overflow-wrap: anywhere; }
.ranking-table tbody tr:hover, .ranking-table tbody tr:focus-visible { background: color-mix(in srgb, var(--primary-color) 6%, var(--card-bg)); outline: none; }
.ranking-row { cursor: pointer; }
.ranking-table th:nth-child(n+3), .ranking-table td:nth-child(n+3) { text-align: right; }
.rank-cell { color: var(--text-muted); }
.doctor-name, .doctor-crm { display: block; }
.ranking-title-row { display: flex; align-items: center; gap: .4rem; }
.info-icon { display: flex; align-items: center; color: var(--text-muted); font-size: .8rem; line-height: 1; opacity: .6; cursor: default; }
.info-icon:hover { opacity: 1; }
.doctor-name { color: var(--text-color-85); font-weight: 600; }
.doctor-crm { margin-top: .16rem; color: var(--text-muted); font-size: .68rem; }
.rate-cell { color: var(--primary-color); font-weight: 600; }
</style>
