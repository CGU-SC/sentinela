<script setup>
import { computed, ref, watch } from 'vue';
import { useRoute } from 'vue-router';
import { storeToRefs } from 'pinia';
import { useCnpjDetailStore } from '@/stores/cnpjDetail';
import { useFilterStore } from '@/stores/filters';
import { useFormatting } from '@/composables/useFormatting';
import { useStableTabState } from '@/composables/useStableTabState';
import { INDICATOR_GROUPS } from '@/config/riskConfig';
import { GENERIC_INDICATOR_DETAIL_KEYS } from '@/config/indicatorDetailConfig';
import {
  INDICATOR_COLUMN_TOOLTIP_COPY,
  INDICATOR_TABLE_TOOLTIP_COPY,
  INDICATOR_TOOLTIP_COPY,
} from '@/config/indicatorTooltipConfig';
import ClinicalIncompatibilityDialog from './ClinicalIncompatibilityDialog.vue';
import GeographicDispersionDialog from './GeographicDispersionDialog.vue';
import IndicatorDetailDialog from './IndicatorDetailDialog.vue';
import TabPlaceholder from './TabPlaceholder.vue';

const { formatCurrencyFull, formatarData, toLocalISO } = useFormatting();
const route = useRoute();
const cnpjDetailStore = useCnpjDetailStore();
const filterStore = useFilterStore();
const { indicadoresData, indicadoresLoading, indicadoresLoaded, indicadoresError } = storeToRefs(cnpjDetailStore);
const showGeographicDialog = ref(false);
const showClinicalDialog = ref(false);
const showGenericIndicatorDialog = ref(false);
const selectedGenericIndicatorKey = ref(null);
const loadingGenericIndicatorKey = ref(null);
const loadingSpecialIndicatorKey = ref(null);

const formattedPeriod = computed(() => {
  const [start, end] = filterStore.periodo ?? [];
  if (!start || !end) return null;
  return { start: formatarData(toLocalISO(start)), end: formatarData(toLocalISO(end)) };
});

// ── Cache de Dados para Transição Suave ──────────────────
const {
  cachedData: cachedIndicadoresData,
  isRefreshing,
} = useStableTabState(indicadoresData, indicadoresLoading, indicadoresError);
// Inicializa o filtro a partir do localStorage (persistência)
const showOnlyHighRisk = ref(localStorage.getItem('sentinela_indicators_filter_only_risky') === 'true');

// Salva no localStorage sempre que o filtro for alterado
watch(showOnlyHighRisk, (newVal) => {
  localStorage.setItem('sentinela_indicators_filter_only_risky', newVal);
});

// ── Banner de hint de interatividade ─────────────────────
// ── Helpers de indicadores ────────────────────────────────
function getIndicadorStatus(indicadorData) {
  const status = indicadorData?.status;
  if (status === 'CRÍTICO' || status === 'CRITICO') {
    return { label: 'CRÍTICO', color: 'var(--risk-indicator-critical)', severity: 'danger' };
  }
  if (status === 'ATENÇÃO' || status === 'ATENCAO') {
    return { label: 'ATENÇÃO', color: 'var(--risk-indicator-warning)', severity: 'warning' };
  }
  if (status === 'NORMAL') {
    return { label: 'NORMAL', color: 'var(--risk-indicator-normal)', severity: 'success' };
  }
  return { label: 'SEM DADOS', color: 'var(--text-muted)', severity: 'secondary' };
}

function formatIndicadorValue(valor, formato) {
  if (valor == null) return '—';
  if (formato === 'pct')  return valor.toFixed(2) + '%';
  if (formato === 'pct3') return valor.toFixed(3) + '%';
  if (formato === 'val')  return formatCurrencyFull(valor);
  return valor.toFixed(2);
}

function escapeTooltipHtml(value) {
  return String(value).replace(/[&<>"']/g, (character) => ({
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    '"': '&quot;',
    "'": '&#39;',
  })[character]);
}

function renderTooltipSection(section) {
  const content = section.items
    ? `<ul>${section.items.map((item) => `<li>${escapeTooltipHtml(item)}</li>`).join('')}</ul>`
    : section.formula
      ? `<div class="indicator-tooltip-formula"><span>Fórmula</span><strong>${escapeTooltipHtml(section.formula)}</strong></div>`
      : section.value != null
        ? `<div class="indicator-tooltip-value"><strong>${escapeTooltipHtml(section.value)}</strong></div>`
        : `<p>${escapeTooltipHtml(section.text)}</p>`;

  return `
    <section class="indicator-tooltip-section">
      <strong class="indicator-tooltip-section-label">${escapeTooltipHtml(section.label)}</strong>
      ${content}
    </section>
  `;
}

function createIndicatorHtmlTooltip(copy) {
  if (!copy?.title || !copy?.intro || !Array.isArray(copy.sections)) {
    throw new Error('Texto de tooltip de indicador incompleto.');
  }

  return {
    value: `
      <div class="indicator-tooltip-content">
        <div class="indicator-tooltip-heading">
          <i class="pi pi-info-circle" aria-hidden="true"></i>
          <span>${escapeTooltipHtml(copy.title)}</span>
        </div>
        <p class="indicator-tooltip-intro">${escapeTooltipHtml(copy.intro)}</p>
        <div class="indicator-tooltip-sections">
          ${copy.sections.map(renderTooltipSection).join('')}
        </div>
      </div>
    `,
    escape: false,
    class: 'indicator-info-tooltip',
    showDelay: 120,
    hideDelay: 80,
  };
}

const tableHelpTooltip = createIndicatorHtmlTooltip(INDICATOR_TABLE_TOOLTIP_COPY);

function columnTooltip(key) {
  const copy = INDICATOR_COLUMN_TOOLTIP_COPY[key];
  if (!copy) throw new Error(`Texto de tooltip de coluna não encontrado: ${key}`);
  return createIndicatorHtmlTooltip(copy);
}

function indicatorTooltip(indicator) {
  const copy = INDICATOR_TOOLTIP_COPY[indicator?.key];
  if (!copy) throw new Error(`Texto de tooltip de indicador não encontrado: ${indicator?.key}`);
  return createIndicatorHtmlTooltip(copy);
}

function valorFinanceiroTooltip(indicadorData, indicator) {
  if (indicadorData?.valor_financeiro == null) return null;
  const copy = INDICATOR_TOOLTIP_COPY[indicator?.key];
  if (!copy?.financialMeaning) {
    throw new Error(`Contexto financeiro de tooltip não encontrado: ${indicator?.key}`);
  }

  return createIndicatorHtmlTooltip({
    title: 'Valor financeiro associado',
    intro: `Montante em reais relacionado ao indicador ${copy.title.toLowerCase()} no período analisado.`,
    sections: [
      { label: 'Valor', value: formatCurrencyFull(indicadorData.valor_financeiro) },
      { label: 'O que representa', text: copy.financialMeaning + '.' },
    ],
  });
}

function normalizeCnpj(value) {
  return String(value ?? '').replace(/\D/g, '');
}

async function openGeographicDialog() {
  const cnpj = normalizeCnpj(route.params.cnpj);
  if (!cnpj) return;
  const [start, end] = filterStore.periodo ?? [];
  const inicio = start ? toLocalISO(start) : null;
  const fim = end ? toLocalISO(end) : null;
  loadingSpecialIndicatorKey.value = 'dispersao_geografica';
  try {
    await Promise.all([
      cnpjDetailStore.fetchGeograficoOrigemUf(cnpj, inicio, fim),
      cnpjDetailStore.fetchGeograficoBenchmarkLocal(cnpj, inicio, fim),
    ]);
    showGeographicDialog.value = true;
  } finally {
    if (loadingSpecialIndicatorKey.value === 'dispersao_geografica') {
      loadingSpecialIndicatorKey.value = null;
    }
  }
}

async function openClinicalDialog() {
  const cnpj = normalizeCnpj(route.params.cnpj);
  if (!cnpj) return;
  const [start, end] = filterStore.periodo ?? [];
  const inicio = start ? toLocalISO(start) : null;
  const fim = end ? toLocalISO(end) : null;
  loadingSpecialIndicatorKey.value = 'incompatibilidade_patologica';
  try {
    await Promise.all([
      cnpjDetailStore.fetchIndicadorBenchmarkLocal(cnpj, 'incompatibilidade_patologica', inicio, fim),
      cnpjDetailStore.fetchIndicadorEvolucaoBenchmark(cnpj, 'incompatibilidade_patologica', inicio, fim),
      cnpjDetailStore.fetchIncompatibilidadePatologica(cnpj, inicio, fim),
    ]);
    showClinicalDialog.value = true;
  } finally {
    if (loadingSpecialIndicatorKey.value === 'incompatibilidade_patologica') {
      loadingSpecialIndicatorKey.value = null;
    }
  }
}

function canDetailIndicator(key, indicadorData = null) {
  if (key === 'dispersao_geografica') return true;
  if (key === 'incompatibilidade_patologica') return true;
  if (GENERIC_INDICATOR_DETAIL_KEYS.includes(key)) return true;
  return false;
}

function openIndicatorDetail(key) {
  if (key === 'dispersao_geografica') {
    void openGeographicDialog();
    return;
  }
  if (key === 'incompatibilidade_patologica') {
    void openClinicalDialog();
    return;
  }
  if (GENERIC_INDICATOR_DETAIL_KEYS.includes(key)) {
    loadGenericIndicatorDetail(key);
  }
}

async function loadGenericIndicatorDetail(key) {
  const cnpj = normalizeCnpj(route.params.cnpj);
  if (!cnpj) return;
  const indicatorKey = String(key ?? '').trim();
  if (!indicatorKey) return;
  loadingGenericIndicatorKey.value = indicatorKey;
  try {
    const [start, end] = filterStore.periodo ?? [];
    const inicio = start ? toLocalISO(start) : null;
    const fim = end ? toLocalISO(end) : null;
    const [benchmarkData, evolutionData] = await Promise.all([
      cnpjDetailStore.fetchIndicadorBenchmarkLocal(cnpj, indicatorKey, inicio, fim),
      cnpjDetailStore.fetchIndicadorEvolucaoBenchmark(cnpj, indicatorKey, inicio, fim),
    ]);
    if (!benchmarkData || !evolutionData) return;
    selectedGenericIndicatorKey.value = indicatorKey;
    showGenericIndicatorDialog.value = true;
  } finally {
    if (loadingGenericIndicatorKey.value === indicatorKey) {
      loadingGenericIndicatorKey.value = null;
    }
  }
}

// ── Pontos críticos (resumo de auditoria) ────────────────
const pontosCriticos = computed(() => {
  if (!cachedIndicadoresData.value?.indicadores) return [];
  const result = [];
  for (const grupo of INDICATOR_GROUPS) {
    for (const ind of grupo.indicators) {
      const d = cachedIndicadoresData.value.indicadores[ind.key];
      if (!d || d.valor == null) continue;
      const status = getIndicadorStatus(d);
      const riscoReg = d.risco_reg != null ? Math.round(d.risco_reg * 10) / 10 : null;

      if (status.label === 'CRÍTICO') {
        result.push({
          key:     ind.key,
          label:   ind.label,
          formato: ind.formato,
          riscoReg,
          valor:   d.valor,
          medReg:  d.med_reg,
        });
      }
    }
  }
  return result.sort((a, b) => {
    if (a.key === 'percentual_nao_comprovacao') return -1;
    if (b.key === 'percentual_nao_comprovacao') return 1;
    return (b.riscoReg ?? 0) - (a.riscoReg ?? 0);
  });
});

// Filtra os grupos conforme o toggle de risco
const filteredGroups = computed(() => {
  if (!showOnlyHighRisk.value) return INDICATOR_GROUPS;

  return INDICATOR_GROUPS.map(grupo => {
    const indicators = grupo.indicators.filter(ind => {
      const d = cachedIndicadoresData.value?.indicadores?.[ind.key];
      if (!d || d.valor == null) return false;
      const status = getIndicadorStatus(d);
      return status.label !== 'NORMAL';
    });
    return { ...grupo, indicators };
  }).filter(grupo => grupo.indicators.length > 0);
});

defineExpose({
  getIndicadoresData: () => cachedIndicadoresData.value?.indicadores ?? {},
  getPontosCriticos: () => pontosCriticos.value,
});

function riscoPillStyle(indicadorData) {
  const s = getIndicadorStatus(indicadorData);
  const c = s.color;
  return { 
    background: `color-mix(in srgb, ${c} 15%, transparent)`, 
    color: c 
  };
}

function riscoTextStyle(indicadorData) {
  const s = getIndicadorStatus(indicadorData);
  return { color: s.color };
}
</script>

<template>
  <div class="tab-content indicadores-tab" :class="{ 'is-refreshing': isRefreshing }">

    <div
      v-if="indicadoresLoading && !cachedIndicadoresData && !indicadoresError"
      class="indicadores-initial-loading-sentinel"
      aria-hidden="true"
    />

    <TabPlaceholder
      v-else-if="indicadoresError"
      variant="error"
      icon="pi-exclamation-circle"
      title="Erro ao carregar"
      :description="indicadoresError"
    />

    <TabPlaceholder
      v-else-if="indicadoresLoaded && !Object.keys(cachedIndicadoresData?.indicadores ?? {}).length"
      variant="info"
      icon="pi-chart-bar"
      title="Sem movimentação no período"
    >
      <template #description>
        Não foram encontradas movimentações financeiras para este CNPJ no período de <u>{{ formattedPeriod?.start }}</u> até <u>{{ formattedPeriod?.end }}</u>.
      </template>
    </TabPlaceholder>

    <template v-else-if="cachedIndicadoresData">

      <div class="ind-section">
        <div class="ind-card">
        <div class="section-title">
          <div class="title-main">
            <i class="pi pi-table" />
            <span>Indicadores de Risco</span>
            <span
              class="detail-hint-badge"
              v-tooltip.top="tableHelpTooltip"
            >
              <span class="detail-hint-badge__dot" aria-hidden="true" />
              <i class="pi pi-chart-scatter" />
              <span class="detail-hint-badge__label">Detalhamento</span>
            </span>
          </div>
          <div class="title-actions">
            <div class="risk-toggle-pill" :class="{ 'active': showOnlyHighRisk }" @click="showOnlyHighRisk = !showOnlyHighRisk">
              <div class="risk-icon-wrap">
                <i class="pi" :class="showOnlyHighRisk ? 'pi-filter-fill' : 'pi-filter'" />
                <span v-if="showOnlyHighRisk" class="risk-ping" />
              </div>
              <span>Somente itens com risco</span>
            </div>
          </div>
        </div>


        <div class="ind-table-wrap">
        <table class="ind-table">
          <colgroup>
            <col style="width:28%" />
            <col style="width:9%" />
            <col style="width:9%" />
            <col style="width:9%" />
            <col style="width:9%" />
            <col style="width:9%" />
            <col style="width:9%" />
            <col style="width:9%" />
            <col style="width:9%" />
          </colgroup>
          <thead class="ind-thead">
            <tr>
              <th>Indicador</th>
              <th>
                <span class="ind-heading-with-tooltip">
                  <span>Farmácia</span>
                  <i
                    class="pi pi-info-circle ind-header-info-icon"
                    role="img"
                    tabindex="0"
                    aria-label="Explicação da coluna Farmácia"
                    v-tooltip.top="columnTooltip('farmacia')"
                  />
                </span>
              </th>
              <th>
                <span class="ind-heading-with-tooltip">
                  <span>Mediana Região</span>
                  <i
                    class="pi pi-info-circle ind-header-info-icon"
                    role="img"
                    tabindex="0"
                    aria-label="Explicação da coluna Mediana Região"
                    v-tooltip.top="columnTooltip('medianaRegiao')"
                  />
                </span>
              </th>
              <th>
                <span class="ind-heading-with-tooltip">
                  <span>Mediana UF</span>
                  <i
                    class="pi pi-info-circle ind-header-info-icon"
                    role="img"
                    tabindex="0"
                    aria-label="Explicação da coluna Mediana UF"
                    v-tooltip.top="columnTooltip('medianaUf')"
                  />
                </span>
              </th>
              <th>
                <span class="ind-heading-with-tooltip">
                  <span>Mediana Nacional</span>
                  <i
                    class="pi pi-info-circle ind-header-info-icon"
                    role="img"
                    tabindex="0"
                    aria-label="Explicação da coluna Mediana Nacional"
                    v-tooltip.top="columnTooltip('medianaNacional')"
                  />
                </span>
              </th>
              <th>
                <span class="ind-heading-with-tooltip">
                  <span>Risco Região</span>
                  <i
                    class="pi pi-info-circle ind-header-info-icon"
                    role="img"
                    tabindex="0"
                    aria-label="Explicação da coluna Risco Região"
                    v-tooltip.top="columnTooltip('riscoRegiao')"
                  />
                </span>
              </th>
              <th>
                <span class="ind-heading-with-tooltip">
                  <span>Risco UF</span>
                  <i
                    class="pi pi-info-circle ind-header-info-icon"
                    role="img"
                    tabindex="0"
                    aria-label="Explicação da coluna Risco UF"
                    v-tooltip.top="columnTooltip('riscoUf')"
                  />
                </span>
              </th>
              <th>
                <span class="ind-heading-with-tooltip">
                  <span>Risco Nacional</span>
                  <i
                    class="pi pi-info-circle ind-header-info-icon"
                    role="img"
                    tabindex="0"
                    aria-label="Explicação da coluna Risco Nacional"
                    v-tooltip.left="columnTooltip('riscoNacional')"
                  />
                </span>
              </th>
              <th>
                <span class="ind-heading-with-tooltip">
                  <span>Status</span>
                  <i
                    class="pi pi-info-circle ind-header-info-icon"
                    role="img"
                    tabindex="0"
                    aria-label="Explicação da coluna Status"
                    v-tooltip.left="columnTooltip('status')"
                  />
                </span>
              </th>
            </tr>
          </thead>
          <tbody>
            <template v-for="grupo in filteredGroups" :key="grupo.id">
              <tr class="ind-group-row">
                <td colspan="9">{{ grupo.label }}</td>
              </tr>
              <tr
                v-for="ind in grupo.indicators"
                :key="ind.key"
                class="ind-data-row"
                :class="{
                  'is-clickable': canDetailIndicator(ind.key, cachedIndicadoresData.indicadores[ind.key]),
                  'is-detail-disabled': ind.key === 'percentual_nao_comprovacao',
                }"
                @click="canDetailIndicator(ind.key, cachedIndicadoresData.indicadores[ind.key]) && openIndicatorDetail(ind.key)"
              >
                <td class="ind-nome-cell">
                  <div class="ind-nome-inner">
                    <span>{{ ind.label }}</span>
                    <i
                      class="pi pi-info-circle ind-info-icon"
                      role="img"
                      tabindex="0"
                      :aria-label="`Explicação do indicador ${ind.label}`"
                      v-tooltip.right="indicatorTooltip(ind)"
                    />
                    
                  </div>
                </td>

                <template v-if="cachedIndicadoresData.indicadores[ind.key]?.valor != null">
                  <td class="ind-val-cell">
                    <div class="ind-value-inner">
                      <span v-if="ind.key === 'volume_atipico'">
                        {{ formatCurrencyFull(cachedIndicadoresData.indicadores[ind.key].valor_aumento_atipico) }}
                      </span>
                      <span v-else>
                        {{ formatIndicadorValue(cachedIndicadoresData.indicadores[ind.key].valor, ind.formato) }}
                      </span>
                      <i
                        v-if="valorFinanceiroTooltip(cachedIndicadoresData.indicadores[ind.key], ind)"
                        class="pi pi-info-circle ind-finance-icon"
                        role="img"
                        tabindex="0"
                        aria-label="Explicação do valor financeiro associado"
                        v-tooltip.top="valorFinanceiroTooltip(cachedIndicadoresData.indicadores[ind.key], ind)"
                      />
                    </div>
                  </td>
                  <td class="ind-med-cell">{{ formatIndicadorValue(cachedIndicadoresData.indicadores[ind.key].med_reg, ind.formato) }}</td>
                  <td class="ind-med-cell ind-secondary-cell"><span class="ind-muted-text">{{ formatIndicadorValue(cachedIndicadoresData.indicadores[ind.key].med_uf,  ind.formato) }}</span></td>
                  <td class="ind-med-cell ind-secondary-cell"><span class="ind-muted-text">{{ formatIndicadorValue(cachedIndicadoresData.indicadores[ind.key].med_br,  ind.formato) }}</span></td>
                  <td class="ind-risco-cell">
                    <span
                      class="ind-risco-pill"
                      :style="riscoPillStyle(cachedIndicadoresData.indicadores[ind.key])"
                    >{{ cachedIndicadoresData.indicadores[ind.key].risco_reg != null ? cachedIndicadoresData.indicadores[ind.key].risco_reg.toFixed(1) + 'x' : '—' }}</span>
                  </td>
                  <td class="ind-risco-cell ind-secondary-cell">
                    <span class="ind-risco-muted" :style="riscoTextStyle(cachedIndicadoresData.indicadores[ind.key])">{{ cachedIndicadoresData.indicadores[ind.key].risco_uf != null ? cachedIndicadoresData.indicadores[ind.key].risco_uf.toFixed(1) + 'x' : '—' }}</span>
                  </td>
                  <td class="ind-risco-cell ind-secondary-cell">
                    <span class="ind-risco-muted" :style="riscoTextStyle(cachedIndicadoresData.indicadores[ind.key])">{{ cachedIndicadoresData.indicadores[ind.key].risco_br != null ? cachedIndicadoresData.indicadores[ind.key].risco_br.toFixed(1) + 'x' : '—' }}</span>
                  </td>
                  <td class="ind-status-cell">
                    <span
                      class="ind-status-pill"
                      :style="riscoPillStyle(cachedIndicadoresData.indicadores[ind.key])"
                    >{{ getIndicadorStatus(cachedIndicadoresData.indicadores[ind.key]).label }}</span>
                  </td>
                </template>
                <template v-else>
                  <td colspan="8" class="ind-sem-dados">SEM DADOS</td>
                </template>
              </tr>
            </template>
          </tbody>
        </table>
        </div><!-- ind-table-wrap -->
      </div><!-- ind-card -->
      </div><!-- ind-section -->
    </template>

    <GeographicDispersionDialog
      v-model="showGeographicDialog"
      :cnpj="normalizeCnpj(route.params.cnpj)"
    />
    <ClinicalIncompatibilityDialog
      v-model="showClinicalDialog"
      :cnpj="normalizeCnpj(route.params.cnpj)"
    />
    <IndicatorDetailDialog
      v-model="showGenericIndicatorDialog"
      :cnpj="normalizeCnpj(route.params.cnpj)"
      :indicator-key="selectedGenericIndicatorKey"
    />

    <transition name="ind-overlay-fade">
      <div v-if="loadingGenericIndicatorKey || loadingSpecialIndicatorKey" class="ind-loading-overlay" aria-live="polite" aria-busy="true">
        <div class="ind-loading-overlay__box">
          <i class="pi pi-spin pi-spinner" />
          <span>Carregando detalhamento...</span>
        </div>
      </div>
    </transition>

  </div>
</template>

<style scoped>
/* ── INDICADORES ─────────────────────────────────────── */
.indicadores-tab {
  display: flex;
  flex-direction: column;
  gap: 1.5rem;
}

.indicadores-tab.is-refreshing {
  opacity: 0.6;
  pointer-events: none;
  transition: opacity 0.2s ease;
}

.section-title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0.5rem 0;
  border-bottom: 1px solid var(--tabs-border);
  margin-bottom: 0.75rem;
}

.title-main {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}

.title-main i {
  font-size: 1rem;
  color: var(--primary-color);
}

.ind-loading-overlay {
  position: fixed;
  inset: 0;
  z-index: 1200;
  display: flex;
  align-items: center;
  justify-content: center;
  background: color-mix(in srgb, var(--bg-color) 72%, transparent);
  backdrop-filter: blur(2px);
}

.ind-loading-overlay__box {
  display: inline-flex;
  align-items: center;
  gap: 0.75rem;
  padding: 0.9rem 1.1rem;
  border: 1px solid var(--card-border);
  border-radius: 10px;
  background: var(--card-bg);
  color: var(--text-color-85);
  box-shadow: 0 12px 28px color-mix(in srgb, var(--text-color-85) 12%, transparent);
}

.ind-loading-overlay__box i {
  font-size: 1rem;
  color: var(--primary-color);
}

.ind-overlay-fade-enter-active,
.ind-overlay-fade-leave-active {
  transition: opacity 0.18s ease;
}

.ind-overlay-fade-enter-from,
.ind-overlay-fade-leave-to {
  opacity: 0;
}

.title-main > span {
  font-size: 0.85rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: var(--text-color-85);
  opacity: 0.85;
}

/* Badge de Detalhamento */
.detail-hint-badge {
  --detail-hint-accent: var(--risk-medium);
  position: relative;
  overflow: hidden;
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
  padding: 0.25rem 0.65rem;
  border: 1px solid color-mix(in srgb, var(--detail-hint-accent) 36%, var(--tabs-border));
  border-radius: 20px;
  background: color-mix(in srgb, var(--detail-hint-accent) 7%, transparent);
  color: var(--text-color-85) !important;
  font-size: 0.68rem !important;
  font-weight: 700 !important;
  letter-spacing: 0.03em !important;
  text-transform: uppercase !important;
  cursor: default;
  user-select: none;
  z-index: 1;
}

.detail-hint-badge::before {
  content: '';
  position: absolute;
  inset: 0;
  padding: 1px;
  border-radius: inherit;
  background:
    conic-gradient(
      from 0deg,
      transparent 0deg,
      transparent 238deg,
      color-mix(in srgb, var(--detail-hint-accent) 15%, transparent) 252deg,
      var(--detail-hint-accent) 275deg,
      color-mix(in srgb, var(--detail-hint-accent) 18%, transparent) 302deg,
      transparent 326deg,
      transparent 360deg
    );
  opacity: 0;
  pointer-events: none;
  -webkit-mask:
    linear-gradient(#000 0 0) content-box,
    linear-gradient(#000 0 0);
  -webkit-mask-composite: xor;
  mask:
    linear-gradient(#000 0 0) content-box,
    linear-gradient(#000 0 0);
  mask-composite: exclude;
  animation: dhb-orbit-border 5s ease-out 1;
}

.detail-hint-badge::after {
  content: '';
  position: absolute;
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: var(--detail-hint-accent);
  box-shadow: 0 0 8px color-mix(in srgb, var(--detail-hint-accent) 70%, transparent);
  offset-path: inset(2px round 18px);
  offset-distance: 0%;
  opacity: 0;
  pointer-events: none;
  animation: dhb-orbit-dot 5s ease-out 1;
}

.detail-hint-badge__dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--detail-hint-accent);
  flex-shrink: 0;
  box-shadow: 0 0 6px color-mix(in srgb, var(--detail-hint-accent) 60%, transparent);
}

.detail-hint-badge i {
  color: var(--detail-hint-accent);
  font-size: 0.75rem;
}

@keyframes dhb-orbit-border {
  0% {
    opacity: 0;
    transform: rotate(0deg);
  }
  10%,
  78% {
    opacity: 1;
  }
  100% {
    opacity: 0;
    transform: rotate(2turn);
  }
}

@keyframes dhb-orbit-dot {
  0% {
    opacity: 0;
    offset-distance: 0%;
  }
  12%,
  78% {
    opacity: 1;
  }
  100% {
    opacity: 0;
    offset-distance: 100%;
  }
}

.risk-toggle-pill {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.35rem 0.85rem;
  background: var(--card-bg);
  border: 1px solid var(--tabs-border);
  border-radius: 99px;
  cursor: pointer;
  font-size: 0.72rem;
  font-weight: 700;
  color: var(--text-muted);
  transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1);
  user-select: none;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.1);
}

.risk-toggle-pill:hover {
  border-color: var(--primary-color);
  background: color-mix(in srgb, var(--primary-color) 8%, var(--card-bg));
  color: var(--text-color-85);
  transform: translateY(-1px);
}

.risk-toggle-pill.active {
  background: color-mix(in srgb, var(--risk-indicator-warning) 18%, var(--card-bg));
  border-color: var(--risk-indicator-warning);
  color: var(--risk-indicator-warning);
  box-shadow: 0 0 12px color-mix(in srgb, var(--risk-indicator-warning) 25%, transparent);
  animation: risk-pulse 2s infinite ease-in-out;
}

.risk-icon-wrap {
  position: relative;
  display: flex;
  align-items: center;
}

.risk-ping {
  position: absolute;
  top: -2px;
  right: -4px;
  width: 6px;
  height: 6px;
  background: var(--risk-indicator-critical);
  border-radius: 50%;
  border: 1px solid var(--card-bg);
  box-shadow: 0 0 4px var(--risk-indicator-critical);
}

@keyframes risk-pulse {
  0% { transform: scale(1); box-shadow: 0 0 8px color-mix(in srgb, var(--risk-indicator-warning) 15%, transparent); }
  50% { transform: scale(1.02); box-shadow: 0 0 15px color-mix(in srgb, var(--risk-indicator-warning) 35%, transparent); }
  100% { transform: scale(1); box-shadow: 0 0 8px color-mix(in srgb, var(--risk-indicator-warning) 15%, transparent); }
}

/* Resumo de auditoria */
/* Novo Card de Auditoria Premiun */
.audit-card-new {
  background: var(--card-bg);
  border: 1px solid var(--card-border);
  border-radius: 12px;
  padding: 0.75rem 1rem;
  margin-bottom: 0.4rem;
  position: relative;
  overflow: hidden;
  box-shadow: 0 2px 8px rgba(0,0,0,0.05);
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
}

.audit-card-new.is-collapsed {
  box-shadow: 0 1px 4px rgba(0,0,0,0.04);
}

.audit-card-new::before {
  content: '';
  position: absolute;
  top: 0;
  left: 0;
  width: 4px;
  height: 100%;
  background: var(--risk-indicator-critical);
  opacity: 0.8;
}

.audit-card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 0px; /* Removido para transição */
  padding-bottom: 0px; /* Removido para transição */
  border-bottom: 1px solid transparent;
  transition: all 0.3s ease;
}

/* Quando expandido, recupera as margens e borda */
.audit-card-new:not(.is-collapsed) .audit-card-header {
  margin-bottom: 0.75rem;
  padding-bottom: 0.5rem;
  border-bottom: 1px solid color-mix(in srgb, var(--risk-indicator-critical) 20%, transparent);
}

.audit-header-actions {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  color: var(--risk-indicator-critical);
  font-weight: 700;
  font-size: 0.75rem;
}

.audit-expand-label {
  text-transform: uppercase;
  letter-spacing: 0.05em;
  opacity: 0.8;
}

.audit-title-wrap {
  display: flex;
  gap: 0.6rem;
  align-items: center;
}

.audit-shield-icon {
  font-size: 1.1rem;
  color: var(--risk-indicator-critical);
  background: color-mix(in srgb, var(--risk-indicator-critical) 10%, transparent);
  padding: 0.4rem;
  border-radius: 8px;
}

.audit-title-text h3 {
  margin: 0;
  font-size: 1.0rem;
  font-weight: 600;
  color: var(--text-color-85);
  opacity: 0.85;
}

.audit-title-text p {
  margin: 0;
  font-size: 0.78rem;
  color: var(--text-secondary);
}

.audit-card-body {
  display: flex;
  flex-direction: column;
  gap: 0.4rem;
}

.audit-row-new {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0.4rem 0.8rem;
  background: transparent;
  border: none;
  border-bottom: 1px solid var(--tabs-border);
  border-radius: 0;
  transition: all 0.2s ease;
}

.audit-row-new:last-child {
  border-bottom: none;
}

.audit-row-new:hover {
  background: var(--table-hover);
  transform: translateX(4px);
}

.audit-item-main {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

.audit-item-label {
  font-size: 0.8rem;
  font-weight: 500;
  color: var(--text-color-85);
}

.audit-item-data {
  display: flex;
  align-items: center;
  gap: 0.4rem;
}

.audit-badge-val {
  background: color-mix(in srgb, var(--risk-indicator-critical) 12%, transparent);
  color: var(--risk-indicator-critical);
  font-size: 0.7rem;
  font-weight: 800;
  padding: 0.05rem 0.4rem;
  border-radius: 4px;
}

.audit-item-desc {
  font-size: 0.7rem;
  color: var(--text-secondary);
}

.audit-item-stats {
  display: flex;
  gap: 1rem;
}

.stat-mini {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
}

.stat-mini .s-label {
  font-size: 0.6rem;
  font-weight: 600;
  text-transform: uppercase;
  color: var(--text-color-85);
  opacity: 0.8;
}

/* Transição Slide */
.audit-slide-enter-active,
.audit-slide-leave-active {
  transition: all 0.3s ease-out;
  max-height: 1000px;
}

.audit-slide-enter-from,
.audit-slide-leave-to {
  max-height: 0;
  opacity: 0;
  margin-top: 0;
  transform: translateY(-8px);
}

.stat-mini .s-val {
  font-size: 0.8rem;
  font-weight: 600;
  color: var(--text-color-85);
}

.ind-section {
  margin-top: 0;
}

.ind-card {
  background: var(--card-bg);
  border: 1px solid var(--card-border);
  border-radius: 12px;
  padding: 1.25rem 1.25rem 0 1.25rem;
  box-shadow: 0 2px 8px rgba(0,0,0,0.06);
  overflow: hidden;
}

.ind-card .section-title {
  margin-bottom: 1rem;
}

.ind-table-wrap {
  overflow-x: auto;
  margin: 0 -1.25rem;
}

.ind-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.8rem;
}

/* Cabeçalho fixo */
.ind-thead th {
  position: sticky;
  top: 0;
  z-index: 2;
  text-align: center;
  padding: 0.75rem 0.75rem;
  background: transparent;
  color: var(--text-secondary);
  font-size: 0.72rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  border-bottom: 2px solid var(--tabs-border);
  white-space: nowrap;
}

.ind-thead th:first-child { text-align: left; }

.ind-heading-with-tooltip {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 0.35rem;
}

.ind-header-info-icon {
  color: var(--risk-medium);
  cursor: help;
  font-size: 0.7rem;
  transition: color 0.15s ease, transform 0.15s ease;
}

.ind-header-info-icon:hover,
.ind-header-info-icon:focus-visible {
  color: var(--primary-color);
  transform: translateY(-1px);
}

.ind-header-info-icon:focus-visible,
.ind-info-icon:focus-visible,
.ind-finance-icon:focus-visible {
  outline: 2px solid color-mix(in srgb, var(--primary-color) 65%, transparent);
  outline-offset: 3px;
  border-radius: 50%;
}

/* Linha de grupo - Estilo Relatório de Mesa (Refinado) */
.ind-group-row td {
  padding: 1rem 1rem 0.35rem 1rem;
  font-size: 0.72rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--primary-color);
  opacity: 0.85;
  background: transparent !important;
  border-top: 2px solid var(--primary-color) !important;
  border-bottom: none !important;
}

/* Linha de dados - Corrigindo Uniformidade do Hover */
.ind-data-row td {
  padding: 0.65rem 0.75rem;
  border-bottom: 1px solid var(--tabs-border);
  vertical-align: middle;
  text-transform: none;
  color: var(--text-color-85);
  background: transparent; /* Garante que a célula seja transparente à base do TR */
  transition: background 0.15s ease;
}

.ind-data-row:hover td {
  background: var(--table-hover) !important;
}

.ind-data-row.is-clickable {
  cursor: pointer;
}

.ind-data-row.is-detail-disabled {
  cursor: not-allowed;
}

.ind-data-row.is-clickable:hover td {
  background: color-mix(in srgb, var(--primary-color) 8%, var(--table-hover)) !important;
}

.ind-data-row.is-detail-disabled:hover td {
  background: color-mix(in srgb, var(--text-color-85) 3%, var(--table-hover)) !important;
}

.ind-data-row.is-detail-disabled .ind-nome-inner {
  color: var(--text-color-85);
}

/* Célula do nome */
.ind-nome-cell {
  font-size: 0.85rem;
  font-weight: 400;
}

.ind-nome-inner {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  white-space: nowrap;
}

/* Células de valor e mediana */
.ind-val-cell {
  text-align: center;
}

.ind-value-inner {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 0.35rem;
}

.ind-finance-icon {
  color: var(--text-muted);
  cursor: pointer;
  flex-shrink: 0;
  font-size: 0.68rem;
  transition: color 0.15s ease;
}

.ind-finance-icon:hover {
  color: var(--text-color-85);
}

.ind-med-cell {
  text-align: center;
}

/* Colunas coadjuvantes — Mediana UF/BR e Risco UF/BR */
.ind-secondary-cell {
  font-size: 0.74rem;
}

.ind-muted-text {
  color: var(--text-color-85);
  opacity: 0.7;
}

.ind-risco-muted {
  font-size: 0.74rem;
  font-weight: 600;
  color: var(--text-color-85);
  opacity: 0.7; /* Transparência age na span e não na TD */
}


/* Células de risco */
.ind-risco-cell {
  text-align: center;
}

.ind-risco-pill {
  display: inline-block;
  padding: 0.15rem 0.55rem;
  border-radius: 99px;
  font-size: 0.72rem;
  font-weight: 700;
  letter-spacing: 0.02em;
  min-width: 3.2rem;
  text-align: center;
}

/* Célula de status */
.ind-status-cell { text-align: center; }

.ind-status-pill {
  display: inline-block;
  padding: 0.2rem 0.6rem;
  border-radius: 99px;
  font-size: 0.65rem;
  font-weight: 700;
  letter-spacing: 0.05em;
  white-space: nowrap;
}

/* Info icon */
.ind-info-icon {
  font-size: 0.7rem;
  color: var(--text-muted); /* Usamos a cor muted em vez de opacidade */
  cursor: pointer;
  flex-shrink: 0;
  transition: color 0.15s;
}
.ind-info-icon:hover { color: var(--text-color-85); }

.ind-action-btn {
  position: relative;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 3.9rem;
  height: 1.55rem;
  padding: 0 0.55rem;
  border: 1px solid color-mix(in srgb, var(--risk-indicator-warning) 58%, var(--card-border));
  border-radius: 999px;
  background: color-mix(in srgb, var(--risk-indicator-warning) 14%, var(--card-bg));
  color: var(--risk-indicator-warning);
  cursor: pointer;
  flex-shrink: 0;
  box-shadow: 0 0 0 1px color-mix(in srgb, var(--risk-indicator-warning) 12%, transparent);
  transition:
    transform 0.15s ease,
    border-color 0.15s ease,
    background 0.15s ease,
    color 0.15s ease;
}

.ind-action-btn span {
  position: relative;
  z-index: 1;
  font-size: 0.68rem;
  font-weight: 600;
  line-height: 1;
}

.ind-action-btn::after {
  content: "";
  position: absolute;
  inset: -3px;
  border: 1px solid color-mix(in srgb, var(--risk-indicator-warning) 58%, transparent);
  border-radius: 999px;
  opacity: 0;
  pointer-events: none;
  animation: geoActionPulse 2.4s ease-out infinite;
}

.ind-action-btn:hover {
  transform: translateY(-1px);
  border-color: color-mix(in srgb, var(--risk-indicator-warning) 80%, var(--card-border));
  background: color-mix(in srgb, var(--risk-indicator-warning) 22%, var(--card-bg));
  color: var(--risk-indicator-warning);
  box-shadow:
    0 0 0 1px color-mix(in srgb, var(--risk-indicator-warning) 22%, transparent),
    0 8px 18px color-mix(in srgb, var(--risk-indicator-warning) 22%, transparent);
}

.ind-action-btn:focus-visible {
  outline: 2px solid color-mix(in srgb, var(--risk-indicator-warning) 62%, transparent);
  outline-offset: 2px;
}

@keyframes geoActionPulse {
  0% {
    opacity: 0.75;
    transform: scale(0.94);
  }
  70%,
  100% {
    opacity: 0;
    transform: scale(1.35);
  }
}

@media (prefers-reduced-motion: reduce) {
  .ind-action-btn::after {
    animation: none;
  }
}

/* Sem dados */
.ind-sem-dados {
  text-align: center;
  color: var(--text-muted);
  font-size: 0.75rem;
  font-weight: 600;
  padding: 0.75rem;
}

.tab-placeholder {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 4rem 2rem;
  gap: 1rem;
  color: var(--text-muted);
  text-align: center;
}
.placeholder-icon {
  font-size: 2.5rem;
  color: var(--sidebar-border);
  opacity: 0.7;
}

:global(.p-tooltip.indicator-info-tooltip) {
  max-width: min(360px, calc(100vw - 2rem));
  width: auto;
  padding: 0;
  background: var(--tooltip-bg);
  border: 1px solid var(--tooltip-border);
  border-radius: 9px;
  box-shadow: var(--tooltip-shadow);
}

:global(.p-tooltip.indicator-info-tooltip .p-tooltip-text) {
  width: 100%;
  padding: 0;
  white-space: normal;
}

:global(.indicator-tooltip-content) {
  display: flex;
  width: min(330px, calc(100vw - 2rem));
  flex-direction: column;
  gap: 0.62rem;
  padding: 0.75rem 0.85rem;
  color: var(--text-color-85);
  line-height: 1.42;
  overflow-wrap: anywhere;
}

:global(.indicator-tooltip-heading) {
  display: flex;
  align-items: center;
  gap: 0.45rem;
  color: var(--text-color-85);
  font-size: 0.8rem;
  font-weight: 700;
  letter-spacing: 0.02em;
}

:global(.indicator-tooltip-heading i) {
  flex-shrink: 0;
  color: var(--risk-medium);
  font-size: 0.8rem;
}

:global(.indicator-tooltip-intro) {
  margin: 0;
  color: var(--text-secondary);
  font-size: 0.72rem;
}

:global(.indicator-tooltip-sections) {
  display: flex;
  flex-direction: column;
  gap: 0.65rem;
}

:global(.indicator-tooltip-section) {
  display: flex;
  flex-direction: column;
  gap: 0.3rem;
  padding-top: 0.55rem;
  border-top: 1px solid var(--tabs-border);
}

:global(.indicator-tooltip-section:first-child) {
  padding-top: 0;
  border-top: 0;
}

:global(.indicator-tooltip-section-label) {
  color: var(--risk-medium);
  font-size: 0.67rem;
  font-weight: 700;
  letter-spacing: 0.045em;
  text-transform: uppercase;
}

:global(.indicator-tooltip-section p) {
  margin: 0;
  color: var(--text-secondary);
  font-size: 0.72rem;
}

:global(.indicator-tooltip-section ul) {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
  margin: 0;
  padding-left: 1rem;
  color: var(--text-secondary);
  font-size: 0.72rem;
}

:global(.indicator-tooltip-section li::marker) {
  color: var(--risk-medium);
}

:global(.indicator-tooltip-formula) {
  display: flex;
  flex-direction: column;
  gap: 0.16rem;
  padding: 0.45rem 0.55rem;
  border: 1px solid var(--tabs-border);
  border-radius: 6px;
  background: color-mix(in srgb, var(--card-bg) 70%, transparent);
}

:global(.indicator-tooltip-formula span) {
  color: var(--text-muted);
  font-size: 0.6rem;
  font-weight: 700;
  letter-spacing: 0.05em;
  text-transform: uppercase;
}

:global(.indicator-tooltip-formula strong) {
  color: var(--text-color-85);
  font-size: 0.7rem;
  font-weight: 600;
}

:global(.indicator-tooltip-value) {
  display: flex;
  padding: 0.45rem 0.55rem;
  border: 1px solid var(--tabs-border);
  border-radius: 6px;
  background: color-mix(in srgb, var(--card-bg) 70%, transparent);
}

:global(.indicator-tooltip-value strong) {
  color: var(--text-color-85);
  font-size: 0.7rem;
  font-weight: 600;
}


</style>
