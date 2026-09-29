import { nextTick, reactive } from 'vue';
import { registerMap } from 'echarts/core';
import { useAnalyticsStore, buildAnalyticsParams } from '@/stores/analytics';
import { useCrmPrescricoesAnalysisStore } from '@/stores/crmPrescricoesAnalysis';
import { useFilterStore } from '@/stores/filters';
import { useGeoStore } from '@/stores/geo';
import { useMunicipalMapStore } from '@/stores/municipalMap';
import { useRiskIndicatorsStore } from '@/stores/riskIndicators';
import { getCrmMapLevel } from '@/composables/useCrmPrescricoesAnalysis';
import { TIMING } from '@/config/constants';

export const ANALYSIS_PAGE_PATHS = ['/municipios', '/estabelecimentos', '/analises'];

export const analysisPageEntry = reactive({
  pendingPath: null,
  preparedPath: null,
  errorPath: null,
  errorMessage: null,
});

let nationalGeoPromise = null;
let preparationSequence = 0;
let sidebarPromise = null;
let sidebarPath = null;

export function beginAnalysisPageNavigation(path) {
  if (!ANALYSIS_PAGE_PATHS.includes(path)) return;
  preparationSequence += 1;
  analysisPageEntry.pendingPath = path;
  analysisPageEntry.errorPath = null;
  analysisPageEntry.errorMessage = null;
  sidebarPath = path;
  sidebarPromise = settleSidebarBeforeReveal(useFilterStore());
}

export function dismissAnalysisPageNavigation() {
  preparationSequence += 1;
  analysisPageEntry.pendingPath = null;
  analysisPageEntry.errorPath = null;
  analysisPageEntry.errorMessage = null;
  sidebarPath = null;
  sidebarPromise = null;
}

export async function revealAnalysisPage(path) {
  if (analysisPageEntry.pendingPath !== path || analysisPageEntry.preparedPath !== path) return;
  const sequence = preparationSequence;
  await nextTick();
  await new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve)));
  if (sequence === preparationSequence && analysisPageEntry.pendingPath === path) {
    analysisPageEntry.pendingPath = null;
    sidebarPath = null;
    sidebarPromise = null;
  }
}

async function settleSidebarBeforeReveal(filterStore) {
  if (filterStore.sidebarLocked) return;
  const main = document.querySelector('.main-container');
  const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  if (filterStore.sidebarCollapsed) filterStore.sidebarCollapsed = false;
  await nextTick();

  if (!main || reducedMotion) return;
  const targetLeft = parseFloat(getComputedStyle(main.parentElement).getPropertyValue('--sidebar-width'));
  const actualLeft = main.getBoundingClientRect().left;
  if (Math.abs(actualLeft - targetLeft) < 1) return;
  await new Promise((resolve) => {
    let timeoutId;
    const finish = () => {
      main.removeEventListener('transitionend', onTransitionEnd);
      clearTimeout(timeoutId);
      resolve();
    };
    const onTransitionEnd = (event) => {
      if (event.target === main && event.propertyName === 'margin-left') finish();
    };
    main.addEventListener('transitionend', onTransitionEnd);
    timeoutId = window.setTimeout(finish, TIMING.SIDEBAR_MOTION_MS * 1.25);
  });
}

async function ensureNationalGeo() {
  if (window.__brasilUfRegistered) return;
  if (!nationalGeoPromise) {
    nationalGeoPromise = fetch('/geo/brasil-uf.json')
      .then(async (response) => {
        if (!response.ok) throw new Error('Não foi possível carregar o mapa do Brasil.');
        const geo = await response.json();
        if (geo?.type !== 'FeatureCollection' || !Array.isArray(geo.features) || !geo.features.length) {
          throw new Error('GeoJSON nacional sem territórios válidos.');
        }
        registerMap('brasil-uf', geo);
        window.__brasilUfRegistered = true;
      })
      .finally(() => { nationalGeoPromise = null; });
  }
  await nationalGeoPromise;
}

async function ensureGeo() {
  const geoStore = useGeoStore();
  const jobs = [];
  if (!geoStore.municipiosGeoJson) jobs.push(geoStore.loadMunicipiosGeo());
  if (!geoStore.localidades.length) jobs.push(geoStore.fetchLocalidades());
  await Promise.all(jobs);
  if (!Array.isArray(geoStore.municipiosGeoJson?.features) || !geoStore.municipiosGeoJson.features.length) {
    throw new Error('O mapa municipal não foi carregado.');
  }
  if (!Array.isArray(geoStore.localidades) || !geoStore.localidades.length) {
    throw new Error('As localidades não foram carregadas.');
  }
}

async function ensureDashboard(filterStore) {
  const analyticsStore = useAnalyticsStore();
  const key = JSON.stringify(buildAnalyticsParams(filterStore.apiParams));
  if (analyticsStore.lastParamsHash !== key || analyticsStore.error) {
    await analyticsStore.fetchDashboardSummary({ ...filterStore.apiParams });
  }
  if (analyticsStore.lastParamsHash !== key || analyticsStore.error
    || !Array.isArray(analyticsStore.resultadoMunicipios)) {
    throw new Error(analyticsStore.error || 'O resumo dos dados não ficou pronto.');
  }
  return key;
}

async function ensureMunicipalPage(filterStore, dashboardKey) {
  const analyticsStore = useAnalyticsStore();
  const municipalMapStore = useMunicipalMapStore();
  const riskStore = useRiskIndicatorsStore();
  const mapParams = buildAnalyticsParams({ ...filterStore.apiParams, idIbge7: null });
  const mapKey = JSON.stringify(mapParams);
  const jobs = [];
  if (mapKey === dashboardKey) {
    municipalMapStore.useDashboardRows(mapKey, analyticsStore.resultadoMunicipios);
  } else {
    jobs.push(municipalMapStore.load(mapKey, mapParams));
  }
  const indicator = riskStore.selectedRiskIndicator;
  let key = null;
  if (indicator) {
    const params = { ...filterStore.indicadoresApiParams };
    key = JSON.stringify({ indicador: indicator, params });
    if (riskStore.summaryParamsKey !== key || riskStore.summaryError) {
      jobs.push(riskStore.fetchRiskIndicatorSummary(indicator, params));
    }
  }
  await Promise.all(jobs);
  if (municipalMapStore.loadedKey !== mapKey || municipalMapStore.error) {
    throw new Error(municipalMapStore.error || 'O mapa municipal não ficou pronto.');
  }
  if (indicator && (riskStore.summaryParamsKey !== key || riskStore.summaryError)) {
    throw new Error(riskStore.summaryError || 'A análise municipal do indicador não ficou pronta.');
  }
}

async function ensureEstablishmentsPage(filterStore) {
  const riskStore = useRiskIndicatorsStore();
  const indicator = riskStore.selectedRiskIndicator;
  if (!indicator) return;
  const summaryParams = { ...filterStore.indicadoresApiParams };
  const tableParams = { ...filterStore.indicadoresTabelaApiParams };
  const summaryKey = JSON.stringify({ indicador: indicator, params: summaryParams });
  const tableKey = JSON.stringify({
    indicador: indicator,
    params: tableParams,
    page: 1,
    pageSize: riskStore.cnpjsRows,
    sortField: riskStore.cnpjsSortField,
    sortOrder: riskStore.cnpjsSortOrder,
  });
  await Promise.all([
    riskStore.summaryParamsKey === summaryKey && !riskStore.summaryError
      ? Promise.resolve()
      : riskStore.fetchRiskIndicatorSummary(indicator, summaryParams),
    riskStore.tableParamsKey === tableKey && !riskStore.tableError
      ? Promise.resolve()
      : riskStore.fetchRiskIndicatorEstablishments(indicator, tableParams, { page: 1 }),
  ]);
  if (riskStore.summaryParamsKey !== summaryKey || riskStore.summaryError) {
    throw new Error(riskStore.summaryError || 'O mapa dos estabelecimentos não ficou pronto.');
  }
  if (riskStore.tableParamsKey !== tableKey || riskStore.tableError) {
    throw new Error(riskStore.tableError || 'A tabela dos estabelecimentos não ficou pronta.');
  }
}

async function ensureAnalysesPage(filterStore) {
  const crmStore = useCrmPrescricoesAnalysisStore();
  const params = { ...buildAnalyticsParams(filterStore.apiParams), map_level: getCrmMapLevel(filterStore) };
  const key = JSON.stringify(params);
  await crmStore.activate(params);
  if (crmStore.activeKey !== key || !crmStore.mapResponse || !crmStore.rankingResponse
    || crmStore.rankingResponseKey !== key || crmStore.mapError || crmStore.rankingError) {
    throw new Error(crmStore.mapError || crmStore.rankingError || 'A análise de prescrições não ficou pronta.');
  }
}

export async function prepareAnalysisPage(path) {
  if (!ANALYSIS_PAGE_PATHS.includes(path)) return;
  const filterStore = useFilterStore();
  if (analysisPageEntry.pendingPath !== path) beginAnalysisPageNavigation(path);
  const sequence = preparationSequence;
  const filterKey = filterStore.apiParamsKey;
  analysisPageEntry.errorPath = null;
  analysisPageEntry.errorMessage = null;
  const layoutReady = sidebarPath === path && sidebarPromise
    ? sidebarPromise
    : settleSidebarBeforeReveal(filterStore);

  try {
    if (!filterStore.isPeriodoValido) throw new Error('Selecione um período válido para abrir esta análise.');
    const common = [ensureGeo(), ensureNationalGeo(), ensureDashboard(filterStore)];
    if (path !== '/analises') common.push(useRiskIndicatorsStore().loadPreferences());
    const [, , dashboardKey] = await Promise.all(common);
    if (path === '/municipios') await ensureMunicipalPage(filterStore, dashboardKey);
    if (path === '/estabelecimentos') await ensureEstablishmentsPage(filterStore);
    if (path === '/analises') await ensureAnalysesPage(filterStore);
    if (filterStore.apiParamsKey !== filterKey) {
      throw new Error('Os filtros mudaram durante a navegação. Abra a página novamente.');
    }
    if (sequence !== preparationSequence) return;
    await layoutReady;
    if (sequence !== preparationSequence) return;
    analysisPageEntry.preparedPath = path;
  } catch (error) {
    if (sequence === preparationSequence) {
      analysisPageEntry.errorPath = path;
      analysisPageEntry.errorMessage = error instanceof Error ? error.message : String(error);
    }
    throw error;
  }
}
