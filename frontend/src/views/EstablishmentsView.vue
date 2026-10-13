<script setup>
import { computed, onMounted, ref } from 'vue';
import { storeToRefs } from 'pinia';
import { useFilterStore } from '@/stores/filters';
import { useRiskIndicatorsStore } from '@/stores/riskIndicators';
import { useGeoStore } from '@/stores/geo';
import { useFetchAnalytics } from '@/composables/useFetchAnalytics';
import { useRiskIndicatorAnalysis } from '@/composables/useRiskIndicatorAnalysis';
import { INDICATOR_GROUPS } from '@/config/riskConfig';
import { ESTABLISHMENTS_HIDDEN_KPI_LABELS, TIMING } from '@/config/constants';
import { filterActionTooltip } from '@/config/filterTooltipConfig';

import RiskIndicatorSelector from './components/risk-indicators/RiskIndicatorSelector.vue';
import EstablishmentRiskMap from './components/establishments/EstablishmentRiskMap.vue';
import EstablishmentRiskTable from './components/establishments/EstablishmentRiskTable.vue';
import KpiSection from './components/KpiSection.vue';

const filterStore = useFilterStore();
const riskIndicatorsStore = useRiskIndicatorsStore();
const geoStore = useGeoStore();
const {
  selectedRiskIndicator, kpis, cnpjKpis, municipios, cnpjs, cnpjsTotal, cnpjsPage, cnpjsRows,
  cnpjsSortField, cnpjsSortOrder, isLoading, isTableLoading, summaryError, tableError
} = storeToRefs(riskIndicatorsStore);
const { fetchRiskIndicator, fetchRiskIndicatorEstablishmentsPage } = useRiskIndicatorAnalysis();
useFetchAnalytics({ secoes: ['kpis'], includeFatorRisco: false, includeNationalContext: false });

const INDICATOR_PANEL_STORAGE = 'sentinela_estabelecimentos_painel_indicadores_recolhido';

function indicadorPainelSalvo() {
  try {
    return localStorage.getItem(INDICATOR_PANEL_STORAGE) === 'true';
  } catch {
    return false;
  }
}

const indicadorPainelRecolhido = ref(indicadorPainelSalvo());

function alternarPainelIndicadores() {
  indicadorPainelRecolhido.value = !indicadorPainelRecolhido.value;
  try {
    localStorage.setItem(INDICATOR_PANEL_STORAGE, String(indicadorPainelRecolhido.value));
  } catch {
    // A preferência continua funcionando durante a sessão mesmo sem armazenamento local.
  }
}

const indicadorPainelTooltip = computed(() => filterActionTooltip(
  indicadorPainelRecolhido.value ? 'Abrir painel' : 'Fechar painel',
  indicadorPainelRecolhido.value
    ? 'Exibe novamente os indicadores de risco.'
    : 'Oculta os indicadores de risco para ampliar a área de análise.',
  indicadorPainelRecolhido.value ? 'pi-angle-double-left' : 'pi-angle-double-right',
));

const indicadorPainelMotion = `${TIMING.SIDEBAR_MOTION_MS}ms`;

// Metadados do indicador ativo (label, formato, metodologia)
const activeRiskIndicatorMeta = computed(() => {
  if (!selectedRiskIndicator.value) return null;
  for (const grupo of INDICATOR_GROUPS) {
    const ind = grupo.indicators.find(i => i.key === selectedRiskIndicator.value);
    if (ind) return ind;
  }
  return null;
});

const activeUf = computed(() => filterStore.selectedUF);

// ── Seleção de município no mapa ──────────────────────────────────────────────
// ── Seleção de município no mapa ──────────────────────────────────────────────
// ── Seleção de município no mapa ──────────────────────────────────────────────
const selectedMunicipioIbge7 = computed(() => {
  const val = filterStore.selectedMunicipio;
  return (val && val !== 'Todos') ? Number(val) : null;
});

function onSelectMunicipio(ibge7) {
  if (!ibge7) {
    filterStore.selectedMunicipio = 'Todos';
    return;
  }
  
  // Sincroniza apenas o ID do município. 
  // NÃO atualizamos a Região de Saúde aqui para evitar que o mapa perca o contexto do resto do estado.
  filterStore.selectedMunicipio = String(ibge7);
}

function clearMunicipioFilter() {
  filterStore.selectedMunicipio = 'Todos';
}

function clearRegiaoFilter() {
  filterStore.selectedRegiaoSaude = 'Todos';
}

function onSelectUf(uf) {
  filterStore.selectedMunicipio = 'Todos';
  filterStore.selectedRegiaoSaude = 'Todos';
  filterStore.selectedUF = uf;
}

function returnMapToUf() {
  filterStore.selectedMunicipio = 'Todos';
  filterStore.selectedRegiaoSaude = 'Todos';
}

function clearMapGeography() {
  filterStore.selectedMunicipio = 'Todos';
  filterStore.selectedRegiaoSaude = 'Todos';
  filterStore.selectedUF = 'Todos';
}

// Em indicadores, o fetch traz a UF/Região inteira (para o mapa ficar colorido).
// Filtramos localmente para que os KPIs e a Tabela reflitam apenas a seleção atual.
const displayedKpis = computed(() => {
  if (!kpis.value) return null;
  if (selectedMunicipioIbge7.value && cnpjKpis.value) {
    return { ...kpis.value, ...cnpjKpis.value };
  }

  const regiao = filterStore.selectedRegiaoSaude;
  const ibge7 = selectedMunicipioIbge7.value;

  // Se não houver filtro geográfico extra, retorna o consolidado da UF (que veio da API)
  if ((!regiao || regiao === 'Todos') && !ibge7) return kpis.value;

  // Caso contrário, calculamos os numéricos de status contando diretamente as farmácias já filtradas (Tabela)
  // Isso garante precisão 100% igual ao que o usuário vê na lista.
  const arr = displayedCnpjs.value;
  const total_critico = arr.filter(c => c.status === 'CRÍTICO').length;
  const total_atencao = arr.filter(c => c.status === 'ATENÇÃO').length;
  const total_normal = arr.filter(c => c.status === 'NORMAL').length;
  const total_sem_dados = arr.filter(c => c.status === 'SEM DADOS').length;

  const total_com_dados = total_critico + total_atencao + total_normal;
  const pct_acima_limiar = total_com_dados > 0
    ? ((total_critico + total_atencao) / total_com_dados) * 100
    : null;

  return {
    ...kpis.value, // Mantemos a mediana regional, já que é o Benchmark de comparação
    total_critico,
    total_atencao,
    total_normal,
    total_sem_dados,
    pct_acima_limiar
  };
});

const displayedCnpjs = computed(() => {
  let list = cnpjs.value || [];
  const ibge7 = selectedMunicipioIbge7.value;
  const regiao = filterStore.selectedRegiaoSaude;

  if (ibge7) {
    list = list.filter(c => Number(c.id_ibge7) === ibge7);
  } else if (regiao && regiao !== 'Todos') {
    list = list.filter(c => geoStore.getRegiaoByIbge7(c.id_ibge7) === regiao);
  }
  return list;
});

const selectedMunicipioNome = computed(() => {
  const code = filterStore.selectedMunicipio;
  if (!code || code === 'Todos') return null;
  const nome = geoStore.getMunicipioNomeByIbge7(code);
  if (!nome) throw new Error('Municipio selecionado sem nome no contrato de localidades.');
  return nome;
});

const selectedRegiaoNome = computed(() => {
  const code = filterStore.selectedRegiaoSaude;
  if (!code || code === 'Todos') return null;
  const nome = geoStore.getRegiaoNomeById(code);
  if (!nome) throw new Error('Regiao de saude selecionada sem nome no contrato de localidades.');
  return nome;
});

function onRiskIndicatorSelect(key) {
  fetchRiskIndicator(key);
}

function onCnpjTableLazy(event) {
  if (!selectedRiskIndicator.value) return;
  const rows = event.rows ?? cnpjsRows.value;
  const first = event.first ?? 0;
  fetchRiskIndicatorEstablishmentsPage(selectedRiskIndicator.value, {
    page: Math.floor(first / rows) + 1,
    pageSize: rows,
    sortField: event.sortField ?? cnpjsSortField.value,
    sortOrder: event.sortOrder ?? cnpjsSortOrder.value,
  });
}

// O fetch automático inicial agora é tratado pelo watch(immediate: true) no useRiskIndicatorAnalysis.js
</script>

<template>
  <div class="indicadores-page">
    <div class="indicadores-main">
      <KpiSection :hidden-labels="ESTABLISHMENTS_HIDDEN_KPI_LABELS" />

    <div class="indicadores-layout">

    <!-- Painel principal de análise -->
    <div class="analysis-panel">

      <!-- Estado vazio: nenhum indicador selecionado -->
      <div v-if="!selectedRiskIndicator && !isLoading" class="empty-state">
        <div class="empty-icon-wrap">
          <i class="pi pi-shield empty-icon" />
        </div>
        <h2 class="empty-title">Selecione um Indicador</h2>
        <p class="empty-desc">
          Escolha um dos 16 indicadores de risco no painel à direita para visualizar
          o desempenho das farmácias no escopo atual dos filtros.
        </p>
        <div class="empty-groups">
          <span v-for="grupo in INDICATOR_GROUPS" :key="grupo.id" class="empty-group-chip">
            {{ grupo.label }}
          </span>
        </div>
      </div>

      <!-- Conteúdo (carregado ou carregando) -->
      <template v-else>

        <!-- Mapa -->
        <EstablishmentRiskMap
          :map-data="municipios"
          :active-uf="activeUf"
          :is-loading="isLoading"
          :error="summaryError"
          :kpis="displayedKpis"
          :formato="activeRiskIndicatorMeta?.formato ?? 'dec'"
          :indicador-label="activeRiskIndicatorMeta?.label ?? ''"
          :selected-ibge7="selectedMunicipioIbge7"
          :selected-regiao="filterStore.selectedRegiaoSaude"
          :selected-municipio-nome="selectedMunicipioNome"
          :selected-regiao-nome="selectedRegiaoNome"
          @select-municipio="onSelectMunicipio"
          @select-uf="onSelectUf"
          @back-to-uf="returnMapToUf"
          @clear-geography="clearMapGeography"
        />

        <!-- Tabela ranqueada de CNPJs -->
        <EstablishmentRiskTable
          :cnpjs="displayedCnpjs"
          :formato="activeRiskIndicatorMeta?.formato ?? 'dec'"
          :indicador-key="selectedRiskIndicator"
          :indicador-label="activeRiskIndicatorMeta?.label ?? ''"
          :is-loading="isTableLoading"
          :error="tableError"
          :total-records="cnpjsTotal"
          :first="(cnpjsPage - 1) * cnpjsRows"
          :rows="cnpjsRows"
          :sort-field="cnpjsSortField"
          :sort-order="cnpjsSortOrder"
          :table-kpis="cnpjKpis"
          :selected-regiao-nome="selectedRegiaoNome"
          :selected-municipio-nome="selectedMunicipioNome"
          @lazy-load="onCnpjTableLazy"
          @clear-regiao-filter="clearRegiaoFilter"
          @clear-municipio-filter="clearMunicipioFilter"
        />

      </template>
    </div>

    <!-- Painel lateral de seleção de indicadores (direita) -->
    <div
      class="indicadores-lateral"
      :class="{ 'is-recolhida': indicadorPainelRecolhido }"
      :style="{ '--lateral-motion': indicadorPainelMotion }"
    >
      <div class="indicadores-trilho" :inert="!indicadorPainelRecolhido || undefined">
        <div class="indicadores-trilho-card">
          <button
            type="button"
            class="lateral-icon-btn"
            aria-expanded="false"
            aria-label="Abrir painel de indicadores"
            v-tooltip.left="indicadorPainelTooltip"
            @click="alternarPainelIndicadores"
          >
            <i class="pi pi-angle-double-left" aria-hidden="true" />
          </button>
        </div>
      </div>

      <div class="indicadores-lateral-clip" :inert="indicadorPainelRecolhido || undefined">
        <RiskIndicatorSelector @select="onRiskIndicatorSelect">
          <template #header-actions>
            <button
              type="button"
              class="lateral-icon-btn"
              aria-expanded="true"
              aria-label="Fechar painel de indicadores"
              v-tooltip.bottom="indicadorPainelTooltip"
              @click="alternarPainelIndicadores"
            >
              <i class="pi pi-angle-double-right" aria-hidden="true" />
            </button>
          </template>
        </RiskIndicatorSelector>
      </div>
    </div>
    </div>
    </div>
  </div>
</template>

<style scoped>
.indicadores-page {
  --indicator-selector-width: 250px;
  --lateral-trilho-width: 44px;
  display: flex;
  flex-direction: column;
  gap: 1rem;
  width: 100%;
}

.indicadores-main {
  min-width: 0;
  width: 100%;
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.indicadores-layout {
  display: flex;
  align-items: flex-start;
  gap: 1rem;
  width: 100%;
}

.indicadores-lateral {
  display: flex;
  align-self: stretch;
  flex-shrink: 0;
}

.indicadores-lateral-clip {
  width: var(--indicator-selector-width);
  overflow-x: clip;
  transition: width var(--lateral-motion) cubic-bezier(0.4, 0, 0.2, 1);
}

.indicadores-lateral-clip > :deep(*) {
  width: var(--indicator-selector-width);
  opacity: 1;
  transition: opacity calc(var(--lateral-motion) * 0.6) ease-out calc(var(--lateral-motion) * 0.5);
}

.indicadores-lateral.is-recolhida .indicadores-lateral-clip { width: 0; }

.indicadores-lateral.is-recolhida .indicadores-lateral-clip > :deep(*) {
  opacity: 0;
  pointer-events: none;
  transition: opacity calc(var(--lateral-motion) * 0.45) ease-in 0ms;
}

.indicadores-trilho {
  width: 0;
  flex-shrink: 0;
  overflow-x: clip;
  transition: width var(--lateral-motion) cubic-bezier(0.4, 0, 0.2, 1);
}

.indicadores-lateral.is-recolhida .indicadores-trilho { width: var(--lateral-trilho-width); }

.indicadores-trilho-card {
  position: sticky;
  top: 0;
  width: var(--lateral-trilho-width);
  min-height: calc(100dvh - 56px - 1.25rem);
  display: flex;
  flex-direction: column;
  align-items: center;
  padding-top: 0.5rem;
  background: var(--card-bg);
  border: 1px solid var(--card-border);
  border-radius: 8px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
  opacity: 0;
  pointer-events: none;
  transition: opacity calc(var(--lateral-motion) * 0.45) ease-in 0ms;
}

.indicadores-lateral.is-recolhida .indicadores-trilho-card {
  opacity: 1;
  pointer-events: auto;
  transition: opacity calc(var(--lateral-motion) * 0.6) ease-out calc(var(--lateral-motion) * 0.5);
}

.lateral-icon-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  padding: 0;
  border: none;
  border-radius: 6px;
  background: color-mix(in srgb, var(--primary-color) 14%, transparent);
  color: var(--primary-color);
  font-size: 0.95rem;
  cursor: pointer;
  transition: background 0.15s ease, color 0.15s ease;
}

.lateral-icon-btn:hover { background: color-mix(in srgb, var(--primary-color) 24%, transparent); }
.lateral-icon-btn .pi { font-size: 0.8rem; }
.lateral-icon-btn:focus-visible {
  outline: 2px solid color-mix(in srgb, var(--primary-color) 70%, transparent);
  outline-offset: 1px;
}

@media (prefers-reduced-motion: reduce) {
  .indicadores-lateral-clip,
  .indicadores-lateral-clip > :deep(*),
  .indicadores-trilho,
  .indicadores-trilho-card {
    transition-duration: 0ms;
    transition-delay: 0ms;
  }
}

.analysis-panel {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 1rem;
  padding-bottom: 1rem;
}

/* ── Estado vazio ── */
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  text-align: center;
  padding: 4rem 2rem;
  background: var(--card-bg);
  border: 1px solid var(--card-border);
  border-radius: 12px;
  gap: 1rem;
}

.empty-icon-wrap {
  width: 4.5rem;
  height: 4.5rem;
  border-radius: 50%;
  background: color-mix(in srgb, var(--primary-color) 10%, var(--card-bg));
  display: flex;
  align-items: center;
  justify-content: center;
}

.empty-icon {
  font-size: 2rem;
  color: var(--primary-color);
  opacity: 0.7;
}

.empty-title {
  margin: 0;
  font-size: 1.1rem;
  font-weight: 600;
  color: var(--text-color-85);
  opacity: 0.85;
}

.empty-desc {
  margin: 0;
  font-size: 0.85rem;
  color: var(--text-muted);
  max-width: 480px;
  line-height: 1.6;
}

.empty-groups {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  justify-content: center;
  margin-top: 0.5rem;
}

.empty-group-chip {
  padding: 0.25rem 0.75rem;
  background: color-mix(in srgb, var(--primary-color) 8%, var(--card-bg));
  border: 1px solid var(--card-border);
  border-radius: 99px;
  font-size: 0.7rem;
  color: var(--text-color-85);
  opacity: 0.75;
}

/* ── Aviso de Snapshot ── */
.snapshot-notice {
  display: flex;
  align-items: center;
  gap: 1rem;
  padding: 0.85rem 1.25rem;
  background: color-mix(in srgb, var(--accent-indigo) 8%, var(--card-bg));
  border: 1px solid color-mix(in srgb, var(--accent-indigo) 20%, transparent);
  border-left: 4px solid var(--accent-indigo);
  border-radius: 8px;
  margin-bottom: 0.5rem;
  animation: fadeInDown 0.4s ease-out;
}

.snapshot-notice i {
  font-size: 1.25rem;
  color: var(--accent-indigo);
}

.notice-content {
  display: flex;
  flex-direction: column;
  gap: 0.15rem;
}

.notice-content strong {
  font-size: 0.72rem;
  letter-spacing: 0.05em;
  color: var(--accent-indigo);
}

.notice-content span {
  font-size: 0.8rem;
  color: var(--text-muted);
  line-height: 1.4;
}

.notice-content em {
  font-style: normal;
  font-weight: 600;
  color: var(--text-color-85);
}

@keyframes fadeInDown {
  from { opacity: 0; transform: translateY(-10px); }
  to { opacity: 1; transform: translateY(0); }
}
</style>
