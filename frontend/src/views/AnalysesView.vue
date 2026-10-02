<script setup>
import { computed, onScopeDispose, ref, watch } from 'vue';
import { storeToRefs } from 'pinia';
import { useFilterStore } from '@/stores/filters';
import { useCrmPrescricoesAnalysisStore } from '@/stores/crmPrescricoesAnalysis';
import { useCrmPrescricoesMensalStore } from '@/stores/crmPrescricoesMensal';
import { useGeoStore } from '@/stores/geo';
import { useFetchAnalytics } from '@/composables/useFetchAnalytics';
import { getCrmMapLevel, useCrmPrescricoesAnalysis } from '@/composables/useCrmPrescricoesAnalysis';
import { ANALISES_HIDDEN_KPI_LABELS } from '@/config/constants';

import AnalysisSidebar from './components/analises/AnalysisSidebar.vue';
import { filterActionTooltip } from '@/config/filterTooltipConfig';
import { TIMING } from '@/config/constants';
import CrmPrescricoesMap from './components/analises/CrmPrescricoesMap.vue';
import CrmPrescricoesRanking from './components/analises/CrmPrescricoesRanking.vue';
import CrmHistoricoDialog from './components/analises/CrmHistoricoDialog.vue';
import KpiSection from './components/KpiSection.vue';

const filterStore = useFilterStore();
const geoStore = useGeoStore();
useFetchAnalytics({ secoes: ['kpis'], includeFatorRisco: false, includeNationalContext: false });

// Nivel do mapa derivado dos filtros (fonte unica): muda junto com UF/regiao/
// municipio, sem estado intermediario incoerente nos pedidos.
const mapLevel = computed(() => getCrmMapLevel(filterStore));
const navigationError = ref(null);
const {
  mapResponse,
  rankingResponse,
  rankingResponseKey,
  activeKey,
  isMapLoading,
  isRankingLoading,
  isRankingPageLoading,
  mapError,
  rankingError,
  rankingPageError,
  rankingPage,
  rankingPageSize,
  rankingSortField,
  rankingSortOrder,
  rankingSearch,
  rankingResponseSearch,
  fetchRankingPage,
} = useCrmPrescricoesAnalysis(mapLevel);
const searchInput = ref(rankingSearch.value);

// ── Abas mensais do ranking ("Por mês" e "Linha do tempo") ────────────────────
const analysisStore = useCrmPrescricoesAnalysisStore();
const mensalStore = useCrmPrescricoesMensalStore();
const {
  tab: rankingTab,
  mensalResponse,
  mensalLoading,
  mensalError,
  mensalPage,
  mensalPageSize,
  mensalSortField,
  mensalSortOrder,
  mensalSearch,
  serieResponse,
  serieLoading,
  serieError,
  alertas,
  alertasPeriodo,
  alertasErro,
} = storeToRefs(mensalStore);

// "Por mês": acompanha filtros (mesma chave do ranking), busca e versão do cache.
// Com a aba fechada, é pré-carregada em segundo plano depois do ranking (para não
// disputar com ele), como o Resumo: ao abrir a aba os dados já estão prontos.
watch(
  () => [rankingTab.value, activeKey.value, rankingSearch.value, analysisStore.cacheVersion, isRankingLoading.value],
  ([tab, , , , rankingCarregando]) => {
    if (!analysisStore.activeParams || analysisStore.cacheVersion === null) return;
    if (tab !== 'mes' && rankingCarregando) return;
    mensalStore.activateMensal(analysisStore.activeParams, rankingSearch.value, analysisStore.cacheVersion);
  },
  { immediate: true },
);
// "Linha do tempo": série dos médicos da página exibida do ranking, com os
// mesmos filtros da resposta (rankingResponseKey = JSON dos parâmetros).
// Pré-carregada em segundo plano em qualquer aba (é barata: só a página
// exibida), como o "Por mês": ao abrir a aba as barras já estão prontas.
watch(
  () => [rankingResponse.value, rankingResponseKey.value, analysisStore.cacheVersion],
  ([response, responseKey, version]) => {
    if (!response?.ranking?.length || !responseKey || version === null) return;
    mensalStore.loadSerie(JSON.parse(responseKey), response.ranking.map((r) => r.id_medico), version);
  },
  { immediate: true },
);
// Ícone de alertas: pontos de atenção dos médicos exibidos na aba ativa.
watch(
  () => [rankingTab.value, rankingResponse.value, rankingResponseKey.value, mensalResponse.value, analysisStore.cacheVersion],
  ([tab, response, responseKey, mensal, version]) => {
    if (version === null) return;
    if (tab === 'mes') {
      if (mensal?.linhas?.length && analysisStore.activeParams) {
        mensalStore.loadAlertas(analysisStore.activeParams, mensal.linhas.map((l) => l.id_medico), version);
      }
      return;
    }
    if (response?.ranking?.length && responseKey) {
      mensalStore.loadAlertas(JSON.parse(responseKey), response.ranking.map((r) => r.id_medico), version);
    }
  },
  { immediate: true },
);
const alertasProps = computed(() => ({
  porMedico: alertas.value,
  periodo: alertasPeriodo.value,
  erro: alertasErro.value,
}));
const mensalProps = computed(() => ({
  response: mensalResponse.value,
  loading: mensalLoading.value,
  error: mensalError.value,
  first: (mensalPage.value - 1) * mensalPageSize.value,
  pageSize: mensalPageSize.value,
  sortField: mensalSortField.value,
  sortOrder: mensalSortOrder.value,
  appliedQuery: mensalSearch.value,
}));
const serieProps = computed(() => ({
  response: serieResponse.value,
  loading: serieLoading.value,
  error: serieError.value,
}));
function onMensalPage(event) {
  const rows = event.rows ?? mensalPageSize.value;
  const page = Math.floor((event.first ?? 0) / rows) + 1;
  mensalStore.loadMensal(analysisStore.activeParams, analysisStore.cacheVersion, page, rows, mensalSortField.value, mensalSortOrder.value);
}
function onMensalSort(event) {
  if (!event.sortField || ![1, -1].includes(event.sortOrder)) return;
  mensalStore.loadMensal(
    analysisStore.activeParams, analysisStore.cacheVersion, 1, mensalPageSize.value,
    event.sortField, event.sortOrder === 1 ? 'asc' : 'desc',
  );
}
// Painel lateral (filtros dos médicos): fecha pelo ícone do cabeçalho e reabre pela
// faixa estreita que fica no lugar, como a barra de filtros da esquerda. Atalho:
// Ctrl+Alt+B (Ctrl+B é da barra da esquerda). O estado fica salvo no navegador.
const LATERAL_STORAGE = 'sentinela_analises_lateral_recolhida';
function lateralSalva() {
  try { return localStorage.getItem(LATERAL_STORAGE) === 'true'; } catch { return false; }
}
const lateralRecolhida = ref(lateralSalva());
function alternarLateral() {
  lateralRecolhida.value = !lateralRecolhida.value;
  try { localStorage.setItem(LATERAL_STORAGE, String(lateralRecolhida.value)); } catch { /* preferência só do navegador */ }
}
const lateralTooltip = computed(() => filterActionTooltip(
  lateralRecolhida.value ? 'Abrir painel' : 'Fechar painel',
  lateralRecolhida.value ? 'Exibe as análises disponíveis e os filtros dos médicos. Atalho: Ctrl+Alt+B.' : 'Oculta as análises disponíveis e os filtros dos médicos. Atalho: Ctrl+Alt+B.',
  lateralRecolhida.value ? 'pi-angle-double-left' : 'pi-angle-double-right',
));
const lateralMotion = `${TIMING.SIDEBAR_MOTION_MS}ms`;
function atalhoLateral(evento) {
  if (evento.code !== 'KeyB' || !evento.ctrlKey || !evento.altKey || evento.shiftKey || evento.metaKey) return;
  if (evento.target instanceof HTMLElement && evento.target.isContentEditable) return;
  evento.preventDefault();
  alternarLateral();
}
window.addEventListener('keydown', atalhoLateral);
onScopeDispose(() => window.removeEventListener('keydown', atalhoLateral));

let searchTimer = null;
onScopeDispose(() => clearTimeout(searchTimer));

const selectedUf = computed(() => filterStore.selectedUF !== 'Todos' ? filterStore.selectedUF : null);
const selectedRegiaoId = computed(() => filterStore.selectedRegiaoSaude !== 'Todos' ? filterStore.selectedRegiaoSaude : null);
const selectedMunicipioIbge7 = computed(() => {
  const value = filterStore.selectedMunicipio;
  return value && value !== 'Todos' ? Number(value) : null;
});
const selectedMunicipioNome = computed(() => {
  if (selectedMunicipioIbge7.value == null) return null;
  const nome = geoStore.getMunicipioNomeByIbge7(selectedMunicipioIbge7.value);
  if (!nome) throw new Error('Municipio selecionado sem nome no contrato de localidades.');
  return nome;
});
const selectedRegiaoNome = computed(() => {
  if (selectedRegiaoId.value == null) return null;
  const nome = geoStore.getRegiaoNomeById(selectedRegiaoId.value);
  if (!nome) throw new Error('Regiao de saude selecionada sem nome no contrato de localidades.');
  return nome;
});
const mapData = computed(() => mapResponse.value?.mapa ?? []);
const ranking = computed(() => rankingResponse.value?.ranking ?? []);
const rankingTotal = computed(() => rankingResponse.value?.qtd_medicos ?? 0);
const rankingFirst = computed(() => (rankingPage.value - 1) * rankingPageSize.value);
// "Só fixados" na resposta exibida: nº de médicos fixados pedidos (null = sem o recorte).
const rankingFixados = computed(() => {
  if (!rankingResponse.value || !rankingResponseKey.value) return null;
  const ids = JSON.parse(rankingResponseKey.value).ids_fixados;
  return ids ? ids.split(',').length : null;
});
const rankingInitialLoading = computed(() => isRankingLoading.value && ranking.value.length === 0);
const rankingPageLoading = computed(() => isRankingPageLoading.value && ranking.value.length > 0);
const rankingIsStale = computed(() => Boolean(
  rankingResponse.value && (
    rankingResponseKey.value !== activeKey.value
    || rankingResponseSearch.value !== rankingSearch.value
    || searchInput.value.trim() !== rankingSearch.value
  ),
));

// Na aba "Por mês" a busca só alimenta a consulta mensal (watcher acima); o
// ranking do Resumo é refeito com a busca ao voltar para as outras abas.
function aplicarBusca(query) {
  if (rankingTab.value === 'mes') {
    analysisStore.setRankingSearch(query);
    return;
  }
  fetchRankingPage(1, rankingPageSize.value, rankingSortField.value, rankingSortOrder.value, query);
}
watch(rankingTab, (tab) => {
  if (tab === 'mes' || !rankingResponse.value || rankingResponseSearch.value === rankingSearch.value) return;
  fetchRankingPage(1, rankingPageSize.value, rankingSortField.value, rankingSortOrder.value, rankingSearch.value);
});

function onRankingSearch(value) {
  searchInput.value = value;
  clearTimeout(searchTimer);
  const query = value.trim();
  if (query === rankingSearch.value) return;
  if (!query) {
    aplicarBusca('');
    return;
  }
  searchTimer = setTimeout(() => aplicarBusca(query), 350);
}

function onSelectUf(uf) {
  navigationError.value = null;
  filterStore.selectedUF = uf;
  filterStore.selectedRegiaoSaude = 'Todos';
  filterStore.selectedMunicipio = 'Todos';
}

function onSelectMunicipio(idIbge7) {
  navigationError.value = null;
  if (idIbge7 == null) {
    filterStore.selectedMunicipio = 'Todos';
    return;
  }
  const regionId = geoStore.getRegiaoByIbge7(idIbge7);
  if (regionId == null) {
    navigationError.value = 'Não foi possível localizar a Região de Saúde deste município.';
    return;
  }
  filterStore.selectedMunicipio = String(idIbge7);
  filterStore.selectedRegiaoSaude = String(regionId);
}

function goBack() {
  navigationError.value = null;
  if (mapLevel.value === 'regiao') {
    filterStore.selectedRegiaoSaude = 'Todos';
    filterStore.selectedMunicipio = 'Todos';
    return;
  }
  filterStore.selectedUF = 'Todos';
  filterStore.selectedRegiaoSaude = 'Todos';
  filterStore.selectedMunicipio = 'Todos';
}

// Modal de histórico do CRM (clique numa linha do ranking), no período filtrado.
const historicoAberto = ref(false);
const historicoMedico = ref(null);
const historicoPeriodo = computed(() => ({
  inicio: filterStore.apiParams?.inicio ?? null,
  fim: filterStore.apiParams?.fim ?? null,
}));
function abrirHistorico(row) {
  historicoMedico.value = row;
  historicoAberto.value = true;
}

function onRankingPage(event) {
  const rows = event.rows ?? rankingPageSize.value;
  const first = event.first ?? 0;
  const page = Math.floor(first / rows) + 1;
  fetchRankingPage(page, rows, rankingSortField.value, rankingSortOrder.value);
}

function onRankingSort(event) {
  if (!event.sortField || ![1, -1].includes(event.sortOrder)) return;
  fetchRankingPage(1, rankingPageSize.value, event.sortField, event.sortOrder === 1 ? 'asc' : 'desc');
}
</script>

<template>
  <div class="analises-page">
    <div class="analises-main">
      <KpiSection :hidden-labels="ANALISES_HIDDEN_KPI_LABELS" />

      <div class="analises-layout">
        <main class="analysis-panel">
          <div v-if="navigationError" class="analysis-error analysis-error--navigation">
            <i class="pi pi-exclamation-circle" />
            <span>{{ navigationError }}</span>
          </div>

          <CrmPrescricoesMap
            :map-level="mapLevel"
            :map-data="mapData"
            :uf="selectedUf"
            :regiao-id="selectedRegiaoId"
            :selected-ibge7="selectedMunicipioIbge7"
            :selected-regiao-nome="selectedRegiaoNome"
            :selected-municipio-nome="selectedMunicipioNome"
            :qtd-medicos="mapResponse?.qtd_medicos ?? 0"
            :map-meta="mapResponse"
            :is-loading="isMapLoading"
            :error="mapError"
            @select-uf="onSelectUf"
            @select-municipio="onSelectMunicipio"
            @back="goBack"
          />

          <CrmPrescricoesRanking
            :rows="ranking"
            :escopo="rankingResponse?.escopo ?? 'Brasil'"
            :is-loading="rankingInitialLoading"
            :error="rankingError"
            :page-error="rankingPageError"
            :is-page-loading="rankingPageLoading"
            :is-refreshing="isRankingLoading"
            :is-stale="rankingIsStale"
            :farmacias-filtradas="rankingResponse?.filtro_farmacias_ativo ?? false"
            :total-records="rankingTotal"
            :first="rankingFirst"
            :page-size="rankingPageSize"
            :sort-field="rankingSortField"
            :sort-order="rankingSortOrder"
            :applied-query="rankingResponseSearch"
            :fixados-pedidos="rankingFixados"
            :tab="rankingTab"
            :mensal="mensalProps"
            :serie="serieProps"
            :alertas="alertasProps"
            @update:tab="mensalStore.setTab"
            @mensal-page="onMensalPage"
            @mensal-sort="onMensalSort"
            @page="onRankingPage"
            @sort="onRankingSort"
            @select-medico="abrirHistorico"
          />
        </main>

        <div class="analises-lateral" :class="{ 'is-recolhida': lateralRecolhida }" :style="{ '--lateral-motion': lateralMotion }">
          <div class="lateral-trilho" :inert="!lateralRecolhida || undefined">
            <div class="lateral-trilho-card">
              <button
                type="button"
                class="lateral-icon-btn"
                aria-expanded="false"
                aria-label="Abrir painel de análises"
                aria-keyshortcuts="Control+Alt+B"
                v-tooltip.left="lateralTooltip"
                @click="alternarLateral"
              >
                <i class="pi pi-angle-double-left" aria-hidden="true" />
              </button>
            </div>
          </div>
          <div class="analises-lateral-clip" :inert="lateralRecolhida || undefined">
            <AnalysisSidebar
              :search-query="searchInput"
              :search-disabled="rankingInitialLoading"
              @search="onRankingSearch"
            >
              <template #header-acoes>
                <button
                  type="button"
                  class="lateral-icon-btn"
                  aria-expanded="true"
                  aria-label="Fechar painel de análises"
                  aria-keyshortcuts="Control+Alt+B"
                  v-tooltip.bottom="lateralTooltip"
                  @click="alternarLateral"
                >
                  <i class="pi pi-angle-double-right" aria-hidden="true" />
                </button>
              </template>
            </AnalysisSidebar>
          </div>
        </div>
      </div>
    </div>

    <CrmHistoricoDialog
      v-model="historicoAberto"
      :medico="historicoMedico"
      :data-inicio="historicoPeriodo.inicio"
      :data-fim="historicoPeriodo.fim"
      :cache-version="analysisStore.cacheVersion"
    />
  </div>
</template>

<style scoped>
.analises-page { --indicator-selector-width: 250px; --lateral-trilho-width: 44px; display: flex; flex-direction: column; gap: 1rem; width: 100%; }
.analises-main { min-width: 0; width: 100%; display: flex; flex-direction: column; gap: 1rem; }
.analises-layout { display: flex; align-items: flex-start; gap: 1rem; width: 100%; }

/* Painel lateral recolhível: a área encolhe por cima do conteúdo (largura fixa),
   como a barra de filtros da esquerda — nada se reorganiza durante a animação. */
.analises-lateral {
  display: flex;
  align-self: stretch;
  flex-shrink: 0;
}
.analises-lateral-clip {
  width: var(--indicator-selector-width);
  overflow-x: clip;
  transition: width var(--lateral-motion) cubic-bezier(0.4, 0, 0.2, 1);
}
.analises-lateral-clip > :deep(*) {
  width: var(--indicator-selector-width);
  opacity: 1;
  transition: opacity calc(var(--lateral-motion) * 0.6) ease-out calc(var(--lateral-motion) * 0.5);
}
.analises-lateral.is-recolhida .analises-lateral-clip { width: 0; }
.analises-lateral.is-recolhida .analises-lateral-clip > :deep(*) {
  opacity: 0;
  pointer-events: none;
  transition: opacity calc(var(--lateral-motion) * 0.45) ease-in 0ms;
}

/* Faixa do painel recolhido: cresce enquanto o painel encolhe (a largura total anima
   de 250px para 44px) e só mostra o botão depois de o painel sair. */
.lateral-trilho {
  width: 0;
  flex-shrink: 0;
  overflow-x: clip;
  transition: width var(--lateral-motion) cubic-bezier(0.4, 0, 0.2, 1);
}
.analises-lateral.is-recolhida .lateral-trilho { width: var(--lateral-trilho-width); }
.lateral-trilho-card {
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
.analises-lateral.is-recolhida .lateral-trilho-card {
  opacity: 1;
  pointer-events: auto;
  transition: opacity calc(var(--lateral-motion) * 0.6) ease-out calc(var(--lateral-motion) * 0.5);
}

/* Botão do painel (cabeçalho e faixa): destaque primary, como o cadeado travado da barra da esquerda. */
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
.lateral-icon-btn:hover {
  background: color-mix(in srgb, var(--primary-color) 24%, transparent);
}
.lateral-icon-btn .pi { font-size: 0.8rem; }
.lateral-icon-btn:focus-visible { outline: 2px solid color-mix(in srgb, var(--primary-color) 70%, transparent); outline-offset: 1px; }

@media (prefers-reduced-motion: reduce) {
  .analises-lateral-clip,
  .analises-lateral-clip > :deep(*),
  .lateral-trilho,
  .lateral-trilho-card { transition-duration: 0ms; transition-delay: 0ms; }
}
.analysis-panel { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 1rem; padding-bottom: 1rem; }
.analysis-error { min-height: 180px; padding: 2rem; display: flex; align-items: center; justify-content: center; gap: .8rem; border: 1px solid color-mix(in srgb, var(--risk-high) 35%, var(--card-border)); border-radius: 12px; background: color-mix(in srgb, var(--risk-high) 7%, var(--card-bg)); color: var(--text-muted); text-align: left; }
.analysis-error > i { color: var(--risk-high); font-size: 1.35rem; }
.analysis-error strong, .analysis-error span { display: block; }
.analysis-error strong { color: var(--text-color-85); font-size: .84rem; font-weight: 600; }
.analysis-error span { margin-top: .25rem; font-size: .75rem; }
.analysis-error--navigation { min-height: auto; padding: .75rem 1rem; justify-content: flex-start; }
</style>
