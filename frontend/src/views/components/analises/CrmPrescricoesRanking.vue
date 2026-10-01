<script setup>
import { computed } from 'vue';
import DataTable from 'primevue/datatable';
import Column from 'primevue/column';
import { useFormatting } from '@/composables/useFormatting';
import { useFrozenData } from '@/composables/useFrozenData';
import {
  analysisTooltip, crmMesTooltip, crmFaixaP95, CRM_NAO_LOCALIZADO_ICONE, CRM_NAO_LOCALIZADO_TOOLTIP,
} from '@/config/analysisTooltipConfig';
import { DATA_NEUTRAL, CRM_TAXA_P95_TONS, CRM_ALERTA_BADGE_TONS } from '@/config/colors';
import { CRM_DAILY_RATE_HIGHLIGHT_THRESHOLD } from '@/config/riskConfig';
import { CRM_RANKING_PAGE_SIZE_OPTIONS, CRM_RANKING_DEFAULT_PAGE_SIZE } from '@/config/constants';
import { useThemeStore } from '@/stores/theme';
import HighlightedText from '@/views/components/common/HighlightedText.vue';
import { destaqueBuscaMedico } from '@/utils/crmBusca';
import CrmPrescricoesMensalTable from './CrmPrescricoesMensalTable.vue';
import CrmAlertasBadge from './CrmAlertasBadge.vue';
import TableFooter from '@/views/components/common/TableFooter.vue';

const props = defineProps({
  rows: { type: Array, default: () => [] },
  isLoading: { type: Boolean, default: false },
  isPageLoading: { type: Boolean, default: false },
  escopo: { type: String, default: 'Brasil' },
  error: { type: String, default: null },
  pageError: { type: String, default: null },
  totalRecords: { type: Number, default: 0 },
  first: { type: Number, default: 0 },
  pageSize: { type: Number, default: CRM_RANKING_DEFAULT_PAGE_SIZE },
  sortField: { type: String, default: 'taxa_prescricoes_dia' },
  sortOrder: { type: String, default: 'desc' },
  isRefreshing: { type: Boolean, default: false },
  isStale: { type: Boolean, default: false },
  farmaciasFiltradas: { type: Boolean, default: false },
  appliedQuery: { type: String, default: '' },
  /** Aba ativa: 'resumo' | 'linha' | 'mes' */
  tab: { type: String, default: 'resumo' },
  /** Aba "Por mês": { response, loading, error, first, pageSize, sortField, sortOrder, appliedQuery } */
  mensal: { type: Object, required: true },
  /** Aba "Linha do tempo": { response, loading, error } da série mensal da página */
  serie: { type: Object, required: true },
  /** Ícone de alertas: { porMedico: { id_medico: pontos[] }, periodo: { inicio, fim } | null, erro } */
  alertas: { type: Object, required: true },
});

const emit = defineEmits(['page', 'sort', 'select-medico', 'update:tab', 'mensal-page', 'mensal-sort']);

const TABS = [
  { value: 'resumo', label: 'Resumo' },
  { value: 'linha', label: 'Linha do tempo' },
  { value: 'mes', label: 'Por mês' },
];
const themeStore = useThemeStore();
const dataColorVars = computed(() => {
  const tema = themeStore.isDark ? 'dark' : 'light';
  const cores = DATA_NEUTRAL[tema];
  const tons = CRM_TAXA_P95_TONS[tema];
  return {
    '--data-color': cores.strong,
    '--data-color-soft': cores.soft,
    '--p95-leve': tons.leve,
    '--p95-media': tons.media,
    '--p95-forte': tons.forte,
  };
});
// Mesmo vermelho pastel da coluna ALERTAS, usado no selo "Não localizado no CFM"
// e no destaque da TAXA / DIA (também na aba "Por mês", componente filho).
const alertaCorVars = computed(() => ({
  '--alerta-cor': CRM_ALERTA_BADGE_TONS[themeStore.isDark ? 'dark' : 'light'].cor,
}));
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
const mensalInfoTooltip = analysisTooltip('crmRankingMensal');
const alertasTooltip = analysisTooltip('crmRankingAlertas');
const linhaTempoTooltip = analysisTooltip('crmRankingLinhaTempo');
const headerInfoTooltip = computed(() => (props.tab === 'mes' ? mensalInfoTooltip : rankingInfoTooltip.value));
const { formatNumberFull, formatTitleCase } = useFormatting();

// ── Aba "Por mês" ────────────────────────────────────────────────────────────
const mensalRows = computed(() => props.mensal.response?.linhas ?? []);
const mensalTotal = computed(() => props.mensal.response?.qtd_linhas ?? 0);
const mensalInitialLoading = computed(() => props.mensal.loading && !props.mensal.response);

// ── Aba "Linha do tempo": eixo comum (meses do período) e barras por médico ──
const eixo = computed(() => {
  const meses = props.serie.response?.meses;
  if (!meses?.length) return null;
  const indice = new Map(meses.map((m, i) => [m.competencia, i]));
  const anos = [];
  for (const m of meses) {
    const ano = Math.floor(m.competencia / 100);
    const ultimo = anos[anos.length - 1];
    if (ultimo?.ano === ano) ultimo.meses += 1;
    else anos.push({ ano, meses: 1 });
  }
  return { meses, indice, anos };
});
const barrasPorMedico = computed(() => {
  const mapa = new Map();
  const e = eixo.value;
  if (!e) return mapa;
  for (const medico of props.serie.response.medicos) {
    const celulas = e.meses.map((m) => ({
      competencia: m.competencia,
      inicioAno: m.competencia % 100 === 1,
      ponto: null,
    }));
    // Escala do próprio médico (como em "Farmácias onde atuou"): a barra mais
    // alta é o mês de maior taxa diária dele; a cor indica taxa elevada.
    const maximo = Math.max(...medico.meses.map((p) => Number(p.taxa_prescricoes_dia)));
    for (const ponto of medico.meses) {
      const i = e.indice.get(ponto.competencia);
      if (i === undefined) {
        throw new Error(`Contrato inválido em crm-prescricoes-serie-mensal: mês ${ponto.competencia} fora do período.`);
      }
      celulas[i].ponto = ponto;
      celulas[i].altura = `${(Number(ponto.taxa_prescricoes_dia) / maximo) * 100}%`;
      celulas[i].tooltip = crmMesTooltip(ponto, e.meses[i].p95_taxa_dia);
      celulas[i].faixa = crmFaixaP95(ponto)?.chave ?? null;
    }
    mapa.set(medico.id_medico, celulas);
  }
  return mapa;
});
function isHighDailyRate(row) {
  return Number(row.taxa_prescricoes_dia) >= CRM_DAILY_RATE_HIGHLIGHT_THRESHOLD;
}

function formatPercent(value) {
  return value == null ? '—' : `${Number(value).toFixed(1).replace('.', ',')}%`;
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

function onRowClick(event) {
  if (!props.isRefreshing && !props.isStale) emit('select-medico', event.data);
}

function onSort(event) {
  if (!props.isRefreshing && !props.isStale) emit('sort', event);
}

function onPage(event) {
  if (!props.isRefreshing && !props.isStale) emit('page', event);
}

// Período dos alertas (resposta do backend), ex.: "01/2020 a 12/2024".
function mesAnoIso(iso) {
  const [ano, mes] = String(iso).split('-');
  return `${mes}/${ano}`;
}
const alertasPeriodoTexto = computed(() => (
  props.alertas.periodo ? `${mesAnoIso(props.alertas.periodo.inicio)} a ${mesAnoIso(props.alertas.periodo.fim)}` : ''
));
function abrirPorAlerta(row) {
  if (!props.isRefreshing && !props.isStale) emit('select-medico', row);
}

const subtitulo = computed(() => {
  if (props.tab === 'mes') {
    const r = props.mensal.response;
    if (!r) return snapshot.value.escopo;
    return `${r.escopo} · ${formatNumberFull(r.qtd_linhas)} ${props.mensal.appliedQuery ? 'meses encontrados' : 'linhas médico × mês'}`;
  }
  return `${snapshot.value.escopo} · ${formatNumberFull(snapshot.value.totalRecords)} ${props.appliedQuery ? 'médicos encontrados' : 'médicos no recorte'}`;
});
</script>

<template>
  <section
    class="crm-ranking-panel"
    :class="{ 'is-refreshing': isRefreshing }"
    :style="[{ '--ranking-page-size': snapshot.pageSize }, alertaCorVars]"
  >
    <header class="ranking-header">
      <div class="ranking-heading">
        <i class="pi pi-list" aria-hidden="true" />
        <div>
          <div class="ranking-title-row">
            <h2>Ranking de médicos por taxa diária</h2>
            <i class="pi pi-info-circle info-icon" v-tooltip.bottom="headerInfoTooltip" aria-label="Como ler o ranking" />
          </div>
          <span v-if="tab !== 'mes' && error && snapshot.rows.length" class="ranking-status--error" role="alert" v-tooltip.bottom="error">
            Falha ao atualizar · resultado anterior exibido
          </span>
          <span v-else-if="tab === 'mes' && mensal.error && mensal.response" class="ranking-status--error" role="alert" v-tooltip.bottom="mensal.error">
            Falha ao atualizar · resultado anterior exibido
          </span>
          <span v-else>{{ subtitulo }}</span>
        </div>
      </div>
      <div class="ranking-tabs" role="tablist" aria-label="Visões do ranking">
        <button
          v-for="opcao in TABS"
          :key="opcao.value"
          type="button"
          role="tab"
          class="ranking-tab"
          :class="{ 'is-active': tab === opcao.value }"
          :aria-selected="tab === opcao.value"
          @click="emit('update:tab', opcao.value)"
        >{{ opcao.label }}</button>
      </div>
    </header>

    <template v-if="tab === 'mes'">
      <div v-if="mensal.error && !mensal.response && !mensal.loading" class="ranking-state ranking-state--error">
        <i class="pi pi-database" />
        <div>
          <strong>Visão mensal indisponível no momento</strong>
          <span>{{ mensal.error }}</span>
        </div>
      </div>
      <div v-else-if="mensalInitialLoading || !mensal.response" class="ranking-state">
        <i class="pi pi-spin pi-spinner" />
        <span>Calculando meses...</span>
      </div>
      <div v-else-if="!mensalRows.length" class="ranking-state ranking-state--vazio">
        <i class="pi pi-info-circle" />
        <span v-if="mensal.appliedQuery">
          Nenhum médico encontrado para o termo “<HighlightedText :text="mensal.appliedQuery" :query="mensal.appliedQuery" />”
        </span>
        <span v-else>Nenhum mês com prescrição para os filtros atuais.</span>
      </div>
      <div v-else class="ranking-table-wrap" :aria-busy="mensal.loading">
        <CrmPrescricoesMensalTable
          :rows="mensalRows"
          :total-records="mensalTotal"
          :first="mensal.first"
          :page-size="mensal.pageSize"
          :sort-field="mensal.sortField"
          :sort-order="mensal.sortOrder"
          :is-loading="mensal.loading"
          :applied-query="mensal.appliedQuery"
          :alertas="alertas.porMedico"
          :alertas-periodo="alertasPeriodoTexto"
          :alertas-erro="alertas.erro"
          @page="emit('mensal-page', $event)"
          @sort="emit('mensal-sort', $event)"
          @select-medico="emit('select-medico', $event)"
        />
        <div v-if="mensal.loading" class="ranking-table-loading" role="status" aria-label="Atualizando visão mensal">
          <i class="pi pi-spin pi-spinner" aria-hidden="true" />
        </div>
      </div>
      <div v-if="mensal.error && mensal.response" class="ranking-page-error" role="alert">
        <i class="pi pi-exclamation-circle" />
        <span>{{ mensal.error }}</span>
      </div>
    </template>

    <div v-else-if="error && !snapshot.rows.length && !isLoading" class="ranking-state ranking-state--error">
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
    <div v-else-if="!snapshot.rows.length" class="ranking-state ranking-state--vazio">
      <i class="pi pi-info-circle" />
      <span v-if="appliedQuery">
        Nenhum médico encontrado para o termo “<HighlightedText :text="appliedQuery" :query="appliedQuery" />”
      </span>
      <span v-else>Nenhum médico encontrado para os filtros atuais.</span>
    </div>
    <div v-else class="ranking-table-wrap" :aria-busy="isRefreshing">
      <DataTable
        :key="`${tab}:${snapshot.sortField}:${snapshot.sortOrder}:${pageError ?? ''}`"
        :value="snapshot.rows"
        data-key="id_medico"
        size="small"
        lazy
        paginator
        :first="snapshot.first"
        :rows="snapshot.pageSize"
        :total-records="snapshot.totalRecords"
        :sort-field="snapshot.sortField"
        :sort-order="snapshot.sortOrder === 'asc' ? 1 : -1"
        :class="['enterprise-table', 'com-rodape', 'crm-ranking-table', 'clickable-rows', { 'is-stale': isStale, 'is-linha': tab === 'linha' }]"
        @row-click="onRowClick"
        @sort="onSort"
        @page="onPage"
      >
        <Column header-class="col-alertas" body-class="col-alertas">
          <template #header>
            <span class="alertas-cabecalho">
              ALERTAS
              <i class="pi pi-info-circle info-icon" v-tooltip.top="alertasTooltip" tabindex="0" aria-label="Como ler a coluna de alertas" />
            </span>
          </template>
          <template #body="{ data }">
            <CrmAlertasBadge
              v-if="alertas.porMedico[data.id_medico]?.length"
              :pontos="alertas.porMedico[data.id_medico]"
              :periodo="alertasPeriodoTexto"
              :nome-medico="doctorLabel(data)"
              @abrir="abrirPorAlerta(data)"
            />
            <span v-else-if="!(data.id_medico in alertas.porMedico) && !alertas.erro" class="alertas-carregando" role="status" aria-label="Carregando alertas" />
          </template>
        </Column>
        <Column field="no_medico" header="MÉDICO / CRM" sortable header-class="col-doctor" body-class="col-doctor">
          <template #body="{ data }">
            <span v-if="!data.localizado_cfm" class="doctor-nao-localizado" v-tooltip.bottom="naoLocalizadoTooltip">
              <i :class="['pi', naoLocalizadoIcone]" aria-hidden="true" />Não localizado no CFM
            </span>
            <span v-else class="doctor-name"><HighlightedText :text="doctorLabel(data)" :query="destaque.nome" /></span>
            <span class="doctor-crm"><HighlightedText :text="crmLabel(data)" :query="destaque.crm" /></span>
          </template>
        </Column>
        <Column v-if="tab === 'resumo'" field="taxa_prescricoes_dia" header="TAXA / DIA" sortable header-class="col-number col-rate" body-class="col-number col-rate rate-cell">
          <template #body="{ data }">
            <span
              class="rate-value"
              :class="{ 'rate-value--high': isHighDailyRate(data) }"
            >{{ Number(data.taxa_prescricoes_dia).toFixed(2).replace('.', ',') }}</span>
          </template>
        </Column>
        <Column v-if="tab === 'resumo'" field="nu_prescricoes" header="PRODUÇÃO" sortable header-class="col-number col-production" body-class="col-number col-production">
          <template #body="{ data }">
            <span class="metric-main">{{ formatNumberFull(data.nu_prescricoes) }} prescrições</span>
            <span class="metric-detail">{{ formatNumberFull(data.qtd_dias_com_prescricao) }} dias com prescrição</span>
          </template>
        </Column>
        <Column v-if="tab === 'linha'" header-class="col-linha" body-class="col-linha">
          <template #header>
            <div class="lt-header">
              <span class="lt-header-title">
                TAXA DIÁRIA MENSAL
                <i
                  class="pi pi-info-circle info-icon"
                  v-tooltip.top="linhaTempoTooltip"
                  tabindex="0"
                  aria-label="Como ler a linha do tempo"
                />
              </span>
              <span v-if="eixo" class="lt-anos" aria-hidden="true">
                <span v-for="a in eixo.anos" :key="a.ano" :style="{ flexGrow: a.meses }">{{ a.ano }}</span>
              </span>
            </div>
          </template>
          <template #body="{ data }">
            <div v-if="barrasPorMedico.get(data.id_medico)" class="lt-bars" :style="dataColorVars">
              <span
                v-for="celula in barrasPorMedico.get(data.id_medico)"
                :key="celula.competencia"
                class="lt-mes"
                :class="{ 'is-ano': celula.inicioAno }"
                v-tooltip.top="celula.tooltip ?? null"
              >
                <span
                  v-if="celula.ponto"
                  class="lt-bar"
                  :class="celula.faixa ? `is-p95-${celula.faixa}` : null"
                  :style="{ height: celula.altura }"
                />
              </span>
            </div>
            <div v-else class="lt-placeholder" :class="{ 'is-loading': serie.loading }" aria-hidden="true" />
          </template>
        </Column>
        <Column v-if="tab === 'resumo'" field="percentual_meses_alta_intensidade" header="MESES COM TAXA ELEVADA" sortable header-class="col-number col-months" body-class="col-number col-months">
          <template #body="{ data }">
            <span class="metric-main">{{ formatPercent(data.percentual_meses_alta_intensidade) }}</span>
            <span class="metric-detail">{{ formatNumberFull(data.qtd_meses_alta_intensidade) }} de {{ formatNumberFull(data.qtd_meses_ativos) }} meses</span>
          </template>
        </Column>
        <Column v-if="tab === 'resumo' && snapshot.farmaciasFiltradas" field="nu_prescricoes_farmacias_filtradas" header="FARMÁCIAS FILTRADAS" sortable header-class="col-number col-filtered" body-class="col-number col-filtered">
          <template #body="{ data }">
            <span class="metric-main">{{ formatNumberFull(data.nu_prescricoes_farmacias_filtradas) }} prescrições</span>
            <span class="metric-detail">{{ formatPercent(data.percentual_prescricoes_farmacias_filtradas) }} do total</span>
          </template>
        </Column>
        <template #footer>
          <TableFooter
            :first="snapshot.first"
            :rows="snapshot.pageSize"
            :total-records="snapshot.totalRecords"
            :rows-per-page-options="CRM_RANKING_PAGE_SIZE_OPTIONS"
            :unidade="['médico', 'médicos']"
            :disabled="isRefreshing || isStale"
            @page="onPage"
          />
        </template>
      </DataTable>
      <div v-if="isPageLoading" class="ranking-table-loading" role="status" aria-label="Atualizando ranking">
        <i class="pi pi-spin pi-spinner" aria-hidden="true" />
      </div>
    </div>

    <div v-if="tab !== 'mes' && pageError && snapshot.rows.length" class="ranking-page-error" role="alert">
      <i class="pi pi-exclamation-circle" />
      <span>{{ pageError }}</span>
    </div>
    <div v-if="tab === 'linha' && serie.error && snapshot.rows.length" class="ranking-page-error" role="alert">
      <i class="pi pi-exclamation-circle" />
      <span>{{ serie.error }}</span>
    </div>
    <div v-if="alertas.erro" class="ranking-page-error" role="alert">
      <i class="pi pi-exclamation-circle" />
      <span>Alertas dos médicos indisponíveis: {{ alertas.erro }}</span>
    </div>
  </section>
</template>

<style scoped>
.crm-ranking-panel { --ranking-row-height: 3.6rem; --ranking-column-header-height: 3.3125rem; --ranking-paginator-height: 4.35rem; background: var(--card-bg); border: 1px solid var(--card-border); border-radius: 12px; overflow: hidden; transition: border-color .18s ease; }
.crm-ranking-panel.is-refreshing { border-color: color-mix(in srgb, var(--primary-color) 24%, var(--card-border)); }
.ranking-header { display: flex; align-items: center; gap: .75rem; padding: .85rem 1.15rem; border-bottom: 1px solid var(--tabs-border); }
.ranking-heading { display: flex; flex: 1; align-items: center; gap: .75rem; min-width: 0; }
.ranking-heading > i { color: var(--primary-color); font-size: 1rem; flex-shrink: 0; }
.ranking-heading > div { min-width: 0; }
.ranking-title-row { display: flex; align-items: center; gap: .4rem; }
.ranking-title-row h2 { margin: 0; color: var(--text-color-85); font-size: .82rem; font-weight: 600; line-height: 1.1; text-transform: uppercase; letter-spacing: .05em; }
.ranking-heading span { display: block; margin-top: .16rem; color: var(--text-muted); font-size: .68rem; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.ranking-heading .ranking-status--error { color: var(--risk-high); }
/* :deep: também no cabeçalho da tabela da aba "Por mês". */
.crm-ranking-panel :deep(.info-icon) { color: var(--text-muted); font-size: .8rem; opacity: .7; }
.crm-ranking-panel :deep(.info-icon:hover) { opacity: 1; }
.ranking-state { min-height: calc(var(--ranking-column-header-height) + var(--ranking-page-size) * var(--ranking-row-height) + var(--ranking-paginator-height)); display: flex; align-items: center; justify-content: center; gap: .6rem; color: var(--text-muted); font-size: .8rem; }
/* Sem resultados: card baixo, para a mensagem ficar à vista sem rolar a página. */
.ranking-state--vazio { min-height: 12rem; }
.ranking-state i { color: var(--primary-color); }
.ranking-state--error { text-align: left; }
.ranking-state--error strong, .ranking-state--error span { display: block; }
.ranking-state--error strong { color: var(--text-color-85); font-size: .82rem; font-weight: 600; }
.ranking-state--error span { margin-top: .25rem; font-size: .72rem; }
.ranking-table-wrap { position: relative; overflow-x: auto; }
.crm-ranking-table { font-family: inherit; }
.crm-ranking-table.is-stale { pointer-events: none; }
.crm-ranking-table :deep(.p-datatable-wrapper) { min-height: calc(var(--ranking-column-header-height) + var(--ranking-page-size) * var(--ranking-row-height)); }
.crm-ranking-table :deep(.p-datatable-table) { width: max(100%, 45.75rem); table-layout: fixed; }
.crm-ranking-table:has(.col-filtered) :deep(.p-datatable-table) { width: calc(max(100%, 45.75rem) + 11.25rem); }
.crm-ranking-table :deep(.p-datatable-tbody > tr) { height: var(--ranking-row-height); }
.crm-ranking-table :deep(.p-datatable-thead > tr > th) { white-space: normal; vertical-align: bottom; line-height: 1.25; }
/* Mesma altura de cabeçalho nas três abas (duas linhas de título). */
.crm-ranking-panel :deep(.crm-ranking-table .p-datatable-thead > tr) { height: var(--ranking-column-header-height); }
.crm-ranking-table :deep(.p-datatable-thead > tr > th .p-column-header-content) { gap: .3rem; }
.crm-ranking-table :deep(.p-datatable-thead > tr > th.col-number .p-column-header-content) { justify-content: flex-end; }
.crm-ranking-table :deep(.p-datatable-tbody > tr > td) { padding: .65rem .8rem; vertical-align: middle; overflow: hidden; }
.crm-ranking-panel:not(.is-refreshing) .crm-ranking-table:not(.is-stale) :deep(.p-datatable-tbody > tr) { cursor: pointer; }
.crm-ranking-table :deep(.col-number) { text-align: right; }
.crm-ranking-table :deep(.col-rate) { width: 6.5rem; }
.crm-ranking-table :deep(.col-production) { width: 10.5rem; }
.crm-ranking-table :deep(.col-months) { width: 10rem; }
.crm-ranking-table :deep(.col-filtered) { width: 11.25rem; }
/* :deep: também valem para a tabela da aba "Por mês" (componente filho). */
.crm-ranking-panel :deep(.metric-main), .crm-ranking-panel :deep(.metric-detail) { display: block; white-space: nowrap; }
.crm-ranking-panel :deep(.metric-main), .crm-ranking-panel :deep(.metric-detail),
.crm-ranking-panel :deep(.doctor-name), .crm-ranking-panel :deep(.doctor-crm) { overflow: hidden; text-overflow: ellipsis; }
.crm-ranking-panel :deep(.metric-main) { color: var(--text-color-85); font-weight: 500; }
.crm-ranking-panel :deep(.metric-detail) { margin-top: .15rem; color: var(--text-muted); font-size: .68rem; }
.crm-ranking-panel :deep(.doctor-name), .crm-ranking-panel :deep(.doctor-crm) { display: block; white-space: nowrap; }
.crm-ranking-panel :deep(.doctor-name) { color: var(--text-color-85); font-weight: 500; }
.crm-ranking-panel :deep(.doctor-crm) { margin-top: .16rem; color: var(--text-muted); font-size: .68rem; }
/* CRM fora do cadastro do CFM: selo no lugar do nome (também na aba "Por mês"). */
.crm-ranking-panel :deep(.doctor-nao-localizado) { display: inline-flex; align-items: center; gap: .3rem; max-width: 100%; padding: .12rem .45rem; border-radius: 5px; background: color-mix(in srgb, var(--alerta-cor) 12%, var(--card-bg)); color: var(--alerta-cor); font-size: .7rem; font-weight: 600; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.crm-ranking-panel :deep(.doctor-nao-localizado .pi) { font-size: .72rem; }

/* Coluna de alertas (também na aba "Por mês"). */
.crm-ranking-panel :deep(.col-alertas) { width: 4.75rem; text-align: center; }
.crm-ranking-panel :deep(th.col-alertas .p-column-header-content) { justify-content: center; }
.crm-ranking-panel :deep(.alertas-cabecalho) { display: inline-flex; align-items: center; gap: .3rem; }
.crm-ranking-panel :deep(.alertas-carregando) { display: inline-block; width: 8px; height: 8px; border-radius: 50%; background: var(--text-muted); opacity: .35; animation: alertas-pulso 1s ease-in-out infinite alternate; }
@keyframes alertas-pulso { from { opacity: .15; } to { opacity: .5; } }

/* Abas */
.ranking-tabs { display: inline-flex; flex-shrink: 0; gap: 2px; padding: 3px; border: 1px solid var(--card-border); border-radius: 9px; background: color-mix(in srgb, var(--text-color) 4%, transparent); }
.ranking-tab { min-height: 28px; padding: 0 .75rem; border: 0; border-radius: 7px; background: transparent; color: var(--text-secondary); font: inherit; font-size: .72rem; font-weight: 600; cursor: pointer; white-space: nowrap; transition: background .15s ease, color .15s ease, box-shadow .15s ease; }
.ranking-tab:hover { color: var(--text-color-85); background: color-mix(in srgb, var(--text-color-85) 6%, transparent); }
.ranking-tab:focus-visible { outline: 2px solid color-mix(in srgb, var(--primary-color) 70%, transparent); outline-offset: 2px; }
.ranking-tab.is-active { color: var(--primary-color); background: color-mix(in srgb, var(--primary-color) 16%, transparent); box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--primary-color) 45%, transparent); }

/* Linha do tempo */
.crm-ranking-table.is-linha :deep(.p-datatable-table) { width: max(100%, 57.75rem); }
.crm-ranking-table.is-linha :deep(.col-doctor) { width: 15rem; }
.crm-ranking-table :deep(.col-linha) { width: auto; }
.crm-ranking-table :deep(th.col-linha .p-column-header-content) { display: block; }
.lt-header { display: flex; flex-direction: column; gap: .12rem; }
.lt-header-title { display: inline-flex; align-items: center; gap: .3rem; }
.lt-anos { display: flex; color: var(--text-muted); font-size: .6rem; font-weight: 500; line-height: 1; letter-spacing: 0; }
.lt-anos > span { flex-basis: 0; min-width: 0; padding-left: .2rem; border-left: 1px solid var(--card-border); overflow: hidden; white-space: nowrap; }
.lt-bars { position: relative; display: flex; align-items: flex-end; height: 34px; border-bottom: 1px solid var(--card-border); }
.lt-mes { position: relative; display: flex; flex: 1 1 0; align-items: flex-end; justify-content: center; min-width: 0; height: 100%; }
.lt-mes.is-ano:not(:first-child) { box-shadow: inset 1px 0 0 color-mix(in srgb, var(--card-border) 70%, transparent); }
.lt-mes:hover { background: color-mix(in srgb, var(--text-color) 6%, transparent); }
.lt-bar { width: 72%; max-width: 10px; min-height: 1.5px; border-radius: 1px 1px 0 0; background: var(--data-color); }
.lt-bar.is-p95-leve { background: var(--p95-leve); }
.lt-bar.is-p95-media { background: var(--p95-media); }
.lt-bar.is-p95-forte { background: var(--p95-forte); }
.lt-placeholder { height: 34px; border-bottom: 1px solid var(--card-border); }
.lt-placeholder.is-loading { background: linear-gradient(90deg, transparent, color-mix(in srgb, var(--text-color) 6%, transparent), transparent); background-size: 200% 100%; animation: lt-shimmer 1.2s linear infinite; }
@keyframes lt-shimmer { from { background-position: 200% 0; } to { background-position: -200% 0; } }
/* :deep: também vale para a aba "Por mês" (componente filho). */
.crm-ranking-panel :deep(.rate-value) { display: inline-block; color: var(--text-color-85); font-weight: 500; }
.crm-ranking-panel :deep(.rate-value--high) { padding: .18rem .38rem; margin: -.18rem -.38rem; border-radius: 5px; background: color-mix(in srgb, var(--alerta-cor) 12%, var(--card-bg)); color: var(--alerta-cor); font-weight: 600; }
.ranking-table-loading { position: absolute; inset: 0; display: flex; align-items: center; justify-content: center; background: color-mix(in srgb, var(--card-bg) 72%, transparent); color: var(--text-muted); font-size: .9rem; pointer-events: none; }
.ranking-page-error { display: flex; align-items: center; gap: .45rem; padding: .55rem 1rem; border-top: 1px solid color-mix(in srgb, var(--risk-high) 25%, var(--tabs-border)); color: var(--risk-high); font-size: .7rem; }
</style>
