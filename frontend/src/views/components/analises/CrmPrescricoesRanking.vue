<script setup>
import { useFormatting } from '@/composables/useFormatting';

defineProps({
  rows: { type: Array, default: () => [] },
  isLoading: { type: Boolean, default: false },
  escopo: { type: String, default: 'Brasil' },
  error: { type: String, default: null },
});

const { formatNumberFull, formatTitleCase } = useFormatting();

function doctorLabel(row) {
  return row.no_medico ? formatTitleCase(row.no_medico) : 'Médico não localizado';
}

function crmLabel(row) {
  if (row.nu_crm == null) return `ID ${row.id_medico}`;
  return `CRM ${formatNumberFull(row.nu_crm)}${row.sg_uf ? `/${row.sg_uf}` : ''}`;
}
</script>

<template>
  <section class="crm-ranking-panel">
    <header class="ranking-header">
      <div>
        <h2>Ranking de médicos por taxa diária</h2>
        <span>Maiores taxas no escopo atual · {{ escopo }}</span>
      </div>
      <i class="pi pi-sort-amount-down" />
    </header>

    <div v-if="error && !isLoading" class="ranking-state ranking-state--error">
      <i class="pi pi-database" />
      <div>
        <strong>Ranking indisponível no momento</strong>
        <span>Os dados aparecerão após a sincronização do módulo de prescrições.</span>
      </div>
    </div>
    <div v-else-if="isLoading" class="ranking-state">
      <i class="pi pi-spin pi-spinner" />
      <span>Calculando ranking...</span>
    </div>
    <div v-else-if="!rows.length" class="ranking-state">
      <i class="pi pi-info-circle" />
      <span>Nenhum médico encontrado para os filtros atuais.</span>
    </div>
    <div v-else class="ranking-table-wrap">
      <table class="ranking-table">
        <thead>
          <tr>
            <th>POS.</th>
            <th>MÉDICO / REGISTRO</th>
            <th>TAXA / DIA</th>
            <th>PRESCRIÇÕES</th>
            <th>MESES ATIVOS</th>
            <th>MESES ANÔMALOS</th>
            <th>% MESES ANÔMALOS</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in rows" :key="row.id_medico">
            <td class="rank-cell">{{ row.rank }}</td>
            <td>
              <span class="doctor-name">{{ doctorLabel(row) }}</span>
              <span class="doctor-crm">{{ crmLabel(row) }}</span>
            </td>
            <td class="rate-cell">{{ Number(row.taxa_prescricoes_dia).toFixed(2).replace('.', ',') }}</td>
            <td>{{ formatNumberFull(row.nu_prescricoes) }}</td>
            <td>{{ formatNumberFull(row.qtd_meses_ativos) }}</td>
            <td>{{ formatNumberFull(row.qtd_meses_anomalos) }}</td>
            <td>{{ row.percentual_meses_anomalos == null ? '—' : `${Number(row.percentual_meses_anomalos).toFixed(1).replace('.', ',')}%` }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </section>
</template>

<style scoped>
.crm-ranking-panel { background: var(--card-bg); border: 1px solid var(--card-border); border-radius: 12px; overflow: hidden; }
.ranking-header { display: flex; align-items: center; justify-content: space-between; gap: 1rem; padding: .9rem 1.15rem; border-bottom: 1px solid var(--tabs-border); }
.ranking-header h2 { margin: 0; color: var(--text-color-85); font-size: .84rem; font-weight: 600; }
.ranking-header span { display: block; margin-top: .2rem; color: var(--text-muted); font-size: .68rem; }
.ranking-header > i { color: var(--primary-color); }
.ranking-state { min-height: 180px; display: flex; align-items: center; justify-content: center; gap: .6rem; color: var(--text-muted); font-size: .8rem; }
.ranking-state i { color: var(--primary-color); }
.ranking-state--error { text-align: left; }
.ranking-state--error strong, .ranking-state--error span { display: block; }
.ranking-state--error strong { color: var(--text-color-85); font-size: .82rem; font-weight: 600; }
.ranking-state--error span { margin-top: .25rem; font-size: .72rem; }
.ranking-table-wrap { max-height: 520px; overflow: auto; }
.ranking-table { width: 100%; border-collapse: collapse; color: var(--text-color-85); font-size: .76rem; }
.ranking-table th { position: sticky; top: 0; z-index: 1; padding: .65rem .8rem; background: var(--table-header-bg); color: var(--text-muted); font-size: .62rem; font-weight: 600; letter-spacing: .04em; text-align: left; white-space: nowrap; }
.ranking-table td { padding: .62rem .8rem; border-top: 1px solid var(--tabs-border); vertical-align: middle; }
.ranking-table tbody tr:hover { background: color-mix(in srgb, var(--primary-color) 6%, var(--card-bg)); }
.ranking-table th:nth-child(n+3), .ranking-table td:nth-child(n+3) { text-align: right; }
.rank-cell { color: var(--text-muted); font-variant-numeric: tabular-nums; }
.doctor-name, .doctor-crm { display: block; }
.doctor-name { color: var(--text-color-85); font-weight: 600; }
.doctor-crm { margin-top: .16rem; color: var(--text-muted); font-size: .68rem; }
.rate-cell { color: var(--primary-color); font-weight: 600; font-variant-numeric: tabular-nums; }
</style>
