import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { nextTick } from 'vue';
import {
  analysisPageEntry,
  beginAnalysisPageNavigation,
  dismissAnalysisPageNavigation,
  prepareAnalysisPage,
  revealAnalysisPage,
} from '../prepareAnalysisPage';
import { TIMING } from '@/config/constants';

const mocks = vi.hoisted(() => ({}));

vi.mock('@/stores/analytics', () => ({
  useAnalyticsStore: () => mocks.analytics,
  buildAnalyticsParams: (params) => ({ ...params }),
}));
vi.mock('@/stores/crmPrescricoesAnalysis', () => ({ useCrmPrescricoesAnalysisStore: () => mocks.crm }));
vi.mock('@/stores/filters', () => ({ useFilterStore: () => mocks.filters }));
vi.mock('@/stores/geo', () => ({ useGeoStore: () => mocks.geo }));
vi.mock('@/stores/municipalMap', () => ({ useMunicipalMapStore: () => mocks.municipalMap }));
vi.mock('@/stores/riskIndicators', () => ({ useRiskIndicatorsStore: () => mocks.risk }));
vi.mock('@/stores/crmFiltrosMedico', () => ({ useCrmFiltrosMedicoStore: () => mocks.crmFilters }));
vi.mock('../useCrmPrescricoesAnalysis', () => ({
  buildCrmAnalysisParams: () => mocks.crmParams,
  getCrmMapLevel: () => 'uf',
}));
vi.mock('../echartsMaps', () => ({ ensureBrasilUfMap: () => mocks.ensureMap() }));

function makeStores() {
  const filters = {
    sidebarLocked: true,
    sidebarCollapsed: false,
    isPeriodoValido: true,
    apiParams: { uf: 'SP', idIbge7: null },
    apiParamsKey: 'filters-1',
    indicadoresApiParams: { uf: 'SP' },
    indicadoresTabelaApiParams: { uf: 'SP' },
  };
  const analytics = {
    error: null,
    resultadoMunicipios: [{ id_ibge7: 3550308 }],
    isDashboardFresh: vi.fn(() => true),
    fetchDashboardSummary: vi.fn(async () => {}),
  };
  const geo = {
    municipiosGeoJson: { features: [{}] },
    localidades: [{ id_ibge7: 3550308 }],
    loadMunicipiosGeo: vi.fn(async function () { this.municipiosGeoJson = { features: [{}] }; }),
    fetchLocalidades: vi.fn(async function () { this.localidades = [{ id_ibge7: 3550308 }]; }),
  };
  const municipalMap = {
    loadedKey: null,
    error: null,
    useDashboardRows: vi.fn(function (key) { this.loadedKey = key; }),
    load: vi.fn(async function (key) { this.loadedKey = key; }),
  };
  const risk = {
    selectedRiskIndicator: null,
    summaryParamsKey: null,
    summaryError: null,
    tableParamsKey: null,
    tableError: null,
    cnpjsRows: 25,
    cnpjsSortField: 'razao_social',
    cnpjsSortOrder: 1,
    loadPreferences: vi.fn(async () => {}),
    fetchRiskIndicatorSummary: vi.fn(async function (indicator, params) {
      this.summaryParamsKey = JSON.stringify({ indicador: indicator, params });
    }),
    fetchRiskIndicatorEstablishments: vi.fn(async function (indicator, params, state) {
      this.tableParamsKey = JSON.stringify({
        indicador: indicator,
        params,
        page: state.page,
        pageSize: this.cnpjsRows,
        sortField: this.cnpjsSortField,
        sortOrder: this.cnpjsSortOrder,
      });
    }),
  };
  const crm = {
    activeKey: null,
    mapResponse: null,
    rankingResponse: null,
    rankingResponseKey: null,
    mapError: null,
    rankingError: null,
    activate: vi.fn(async function (params) {
      const key = JSON.stringify(params);
      this.activeKey = key;
      this.mapResponse = {};
      this.rankingResponse = {};
      this.rankingResponseKey = key;
    }),
  };
  Object.assign(mocks, {
    filters,
    analytics,
    geo,
    municipalMap,
    risk,
    crm,
    crmFilters: { apiParams: {} },
    crmParams: { uf: 'SP', map_level: 'uf' },
    ensureMap: vi.fn(async () => {}),
  });
}

describe('prepareAnalysisPage', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    makeStores();
    dismissAnalysisPageNavigation();
    analysisPageEntry.preparedPath = null;
    vi.stubGlobal('requestAnimationFrame', (callback) => { callback(); return 1; });
    vi.stubGlobal('matchMedia', vi.fn(() => ({ matches: true })));
    Object.defineProperty(window, 'matchMedia', {
      configurable: true,
      value: vi.fn(() => ({ matches: true })),
    });
  });

  afterEach(() => {
    dismissAnalysisPageNavigation();
    vi.clearAllTimers();
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
    vi.useRealTimers();
  });

  it('ignora caminhos fora das páginas de análise e só inicia navegação reconhecida', async () => {
    await expect(prepareAnalysisPage('/configuracoes')).resolves.toBeUndefined();
    beginAnalysisPageNavigation('/configuracoes');
    expect(analysisPageEntry.pendingPath).toBeNull();
    beginAnalysisPageNavigation('/municipios');
    expect(analysisPageEntry.pendingPath).toBe('/municipios');
  });

  it('falha visivelmente quando o período global é inválido', async () => {
    mocks.filters.isPeriodoValido = false;
    await expect(prepareAnalysisPage('/municipios'))
      .rejects.toThrow('Selecione um período válido para abrir esta análise.');
    expect(analysisPageEntry.errorPath).toBe('/municipios');
    expect(analysisPageEntry.errorMessage).toBe('Selecione um período válido para abrir esta análise.');
  });

  it('prepara a página municipal, carrega recursos geográficos ausentes e revela após duas animações', async () => {
    mocks.geo.municipiosGeoJson = null;
    mocks.geo.localidades = [];
    await prepareAnalysisPage('/municipios');
    expect(mocks.geo.loadMunicipiosGeo).toHaveBeenCalledOnce();
    expect(mocks.geo.fetchLocalidades).toHaveBeenCalledOnce();
    expect(mocks.municipalMap.useDashboardRows).toHaveBeenCalledWith(
      JSON.stringify(mocks.filters.apiParams),
      mocks.analytics.resultadoMunicipios,
    );
    expect(mocks.risk.loadPreferences).toHaveBeenCalledOnce();
    expect(analysisPageEntry.preparedPath).toBe('/municipios');
    await revealAnalysisPage('/municipios');
    expect(analysisPageEntry.pendingPath).toBeNull();
  });

  it('busca mapa municipal separado e resumo do indicador quando os filtros não coincidem', async () => {
    mocks.filters.apiParams.idIbge7 = '3550308';
    mocks.risk.selectedRiskIndicator = 'ticket_medio';
    await prepareAnalysisPage('/municipios');
    expect(mocks.municipalMap.load).toHaveBeenCalledWith(
      JSON.stringify({ ...mocks.filters.apiParams, idIbge7: null }),
      { ...mocks.filters.apiParams, idIbge7: null },
    );
    expect(mocks.risk.fetchRiskIndicatorSummary).toHaveBeenCalledWith('ticket_medio', { uf: 'SP' });
  });

  it('prepara estabelecimentos com e sem indicador e reutiliza resultados atuais', async () => {
    await prepareAnalysisPage('/estabelecimentos');
    expect(mocks.risk.fetchRiskIndicatorSummary).not.toHaveBeenCalled();
    expect(mocks.risk.fetchRiskIndicatorEstablishments).not.toHaveBeenCalled();

    dismissAnalysisPageNavigation();
    mocks.risk.selectedRiskIndicator = 'ticket_medio';
    await prepareAnalysisPage('/estabelecimentos');
    expect(mocks.risk.fetchRiskIndicatorSummary).toHaveBeenCalledOnce();
    expect(mocks.risk.fetchRiskIndicatorEstablishments).toHaveBeenCalledWith(
      'ticket_medio', { uf: 'SP' }, { page: 1 },
    );

    dismissAnalysisPageNavigation();
    await prepareAnalysisPage('/estabelecimentos');
    expect(mocks.risk.fetchRiskIndicatorSummary).toHaveBeenCalledOnce();
    expect(mocks.risk.fetchRiskIndicatorEstablishments).toHaveBeenCalledOnce();
  });

  it('prepara análise de prescrições em paralelo sem carregar preferências dos indicadores', async () => {
    await prepareAnalysisPage('/analises');
    expect(mocks.crm.activate).toHaveBeenCalledWith(mocks.crmParams);
    expect(mocks.risk.loadPreferences).not.toHaveBeenCalled();
    expect(analysisPageEntry.preparedPath).toBe('/analises');
  });

  it('reconstrói a preparação da sidebar quando há navegação pendente sem promessa de transição', async () => {
    analysisPageEntry.pendingPath = '/estabelecimentos';

    await expect(prepareAnalysisPage('/estabelecimentos')).resolves.toBeUndefined();

    expect(analysisPageEntry.preparedPath).toBe('/estabelecimentos');
    expect(mocks.analytics.fetchDashboardSummary).not.toHaveBeenCalled();
  });

  it('valida todos os dados e estados obrigatórios da análise de prescrições', async () => {
    const invalidStates = [
      { apply: (store) => { store.mapResponse = null; }, message: 'A análise de prescrições não ficou pronta.' },
      { apply: (store) => { store.rankingResponse = null; }, message: 'A análise de prescrições não ficou pronta.' },
      { apply: (store, key) => { store.rankingResponseKey = `${key}-stale`; }, message: 'A análise de prescrições não ficou pronta.' },
      { apply: (store) => { store.mapError = 'Falha no mapa de CRMs'; }, message: 'Falha no mapa de CRMs' },
      { apply: (store) => { store.rankingError = 'Falha no ranking de CRMs'; }, message: 'Falha no ranking de CRMs' },
    ];

    for (const { apply, message } of invalidStates) {
      dismissAnalysisPageNavigation();
      makeStores();
      mocks.crm.activate.mockImplementation(async function (params) {
        const key = JSON.stringify(params);
        this.activeKey = key;
        this.mapResponse = {};
        this.rankingResponse = {};
        this.rankingResponseKey = key;
        apply(this, key);
      });
      await expect(prepareAnalysisPage('/analises')).rejects.toThrow(message);
    }
  });

  it('usa fetch do resumo quando os dados estão vencidos e expõe erro de resumo não pronto', async () => {
    mocks.analytics.isDashboardFresh.mockReturnValue(false);
    mocks.analytics.error = 'Falha do resumo';
    await expect(prepareAnalysisPage('/estabelecimentos')).rejects.toThrow('Falha do resumo');
    expect(mocks.analytics.fetchDashboardSummary).toHaveBeenCalledWith(
      mocks.filters.apiParams,
      ['kpis'],
    );
    expect(analysisPageEntry.errorPath).toBe('/estabelecimentos');
  });

  it('mostra erros específicos para geo, mapa, tabela e análise de prescrições', async () => {
    mocks.geo.municipiosGeoJson = null;
    mocks.geo.loadMunicipiosGeo.mockResolvedValueOnce();
    await expect(prepareAnalysisPage('/municipios')).rejects.toThrow('O mapa municipal não foi carregado.');

    dismissAnalysisPageNavigation();
    makeStores();
    mocks.filters.apiParams.idIbge7 = '3550308';
    mocks.municipalMap.load.mockImplementation(async function () { this.error = 'Falha no mapa'; });
    await expect(prepareAnalysisPage('/municipios')).rejects.toThrow('Falha no mapa');

    dismissAnalysisPageNavigation();
    makeStores();
    mocks.risk.selectedRiskIndicator = 'ticket_medio';
    mocks.risk.fetchRiskIndicatorEstablishments.mockImplementation(async function () { this.tableError = 'Falha na tabela'; });
    await expect(prepareAnalysisPage('/estabelecimentos')).rejects.toThrow('Falha na tabela');

    dismissAnalysisPageNavigation();
    makeStores();
    mocks.crm.activate.mockImplementation(async function () { this.activeKey = 'outro'; });
    await expect(prepareAnalysisPage('/analises')).rejects.toThrow('A análise de prescrições não ficou pronta.');
  });

  it('detecta filtros alterados durante a preparação e ignora conclusões obsoletas', async () => {
    mocks.analytics.isDashboardFresh.mockReturnValueOnce(false).mockReturnValue(true);
    mocks.analytics.fetchDashboardSummary.mockImplementation(async () => { mocks.filters.apiParamsKey = 'filters-2'; });
    await expect(prepareAnalysisPage('/estabelecimentos'))
      .rejects.toThrow('Os filtros mudaram durante a navegação. Abra a página novamente.');

    dismissAnalysisPageNavigation();
    makeStores();
    let finish;
    mocks.ensureMap.mockImplementation(() => new Promise((resolve) => { finish = resolve; }));
    const pending = prepareAnalysisPage('/estabelecimentos');
    await Promise.resolve();
    dismissAnalysisPageNavigation();
    finish();
    await pending;
    expect(analysisPageEntry.preparedPath).toBeNull();
  });

  it('aguarda transição da sidebar, ignora eventos irrelevantes e solta a página ao fim', async () => {
    mocks.filters.sidebarLocked = false;
    mocks.filters.sidebarCollapsed = true;
    let transitionHandler;
    const main = {
      parentElement: {},
      getBoundingClientRect: () => ({ left: 20 }),
      addEventListener: vi.fn((_name, handler) => { transitionHandler = handler; }),
      removeEventListener: vi.fn(),
    };
    vi.spyOn(document, 'querySelector').mockReturnValue(main);
    vi.stubGlobal('getComputedStyle', () => ({ getPropertyValue: () => '300px' }));
    window.matchMedia = vi.fn(() => ({ matches: false }));
    beginAnalysisPageNavigation('/municipios');
    await Promise.resolve();
    expect(mocks.filters.sidebarCollapsed).toBe(false);
    expect(transitionHandler).toBeTypeOf('function');

    const preparation = prepareAnalysisPage('/municipios');
    transitionHandler({ target: {}, propertyName: 'margin-left' });
    transitionHandler({ target: main, propertyName: 'opacity' });
    await Promise.resolve();
    transitionHandler({ target: main, propertyName: 'margin-left' });
    await preparation;
    expect(main.removeEventListener).toHaveBeenCalledWith('transitionend', transitionHandler);
    await revealAnalysisPage('/municipios');
    expect(analysisPageEntry.pendingPath).toBeNull();
    await expect(revealAnalysisPage('/municipios')).resolves.toBeUndefined();
  });

  it('retorna sem esperar quando sidebar está bloqueada, já alinhada, sem container ou com motion reduzido', async () => {
    mocks.filters.sidebarLocked = false;
    const querySelector = vi.spyOn(document, 'querySelector').mockReturnValue(null);
    window.matchMedia = vi.fn(() => ({ matches: false }));
    beginAnalysisPageNavigation('/estabelecimentos');
    await expect(prepareAnalysisPage('/estabelecimentos')).resolves.toBeUndefined();

    dismissAnalysisPageNavigation();
    makeStores();
    mocks.filters.sidebarLocked = false;
    mocks.filters.sidebarCollapsed = true;
    const main = {
      parentElement: {},
      getBoundingClientRect: () => ({ left: 300 }),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    };
    querySelector.mockReturnValue(main);
    vi.stubGlobal('getComputedStyle', () => ({ getPropertyValue: () => '300px' }));
    window.matchMedia = vi.fn(() => ({ matches: false }));
    await expect(prepareAnalysisPage('/estabelecimentos')).resolves.toBeUndefined();
    expect(main.addEventListener).not.toHaveBeenCalled();
    expect(mocks.filters.sidebarCollapsed).toBe(false);

    dismissAnalysisPageNavigation();
    makeStores();
    mocks.filters.sidebarLocked = false;
    const reducedMotionMain = { ...main, getBoundingClientRect: () => ({ left: 10 }) };
    querySelector.mockReturnValue(reducedMotionMain);
    vi.stubGlobal('getComputedStyle', () => ({ getPropertyValue: () => '300px' }));
    window.matchMedia = vi.fn(() => ({ matches: true }));
    await expect(prepareAnalysisPage('/estabelecimentos')).resolves.toBeUndefined();
    expect(reducedMotionMain.addEventListener).not.toHaveBeenCalled();
  });

  it('falha quando localidades não aparecem e aplica mensagens padrão dos resumos, mapas e tabelas', async () => {
    mocks.geo.localidades = [];
    mocks.geo.fetchLocalidades.mockResolvedValueOnce();
    await expect(prepareAnalysisPage('/municipios')).rejects.toThrow('As localidades não foram carregadas.');

    dismissAnalysisPageNavigation();
    makeStores();
    mocks.analytics.error = 'Erro persistente no resumo';
    mocks.analytics.isDashboardFresh.mockReturnValue(true);
    await expect(prepareAnalysisPage('/estabelecimentos')).rejects.toThrow('Erro persistente no resumo');
    expect(mocks.analytics.fetchDashboardSummary).toHaveBeenCalledOnce();

    dismissAnalysisPageNavigation();
    makeStores();
    mocks.analytics.isDashboardFresh.mockReturnValue(false);
    await expect(prepareAnalysisPage('/estabelecimentos')).rejects.toThrow('O resumo dos dados não ficou pronto.');

    dismissAnalysisPageNavigation();
    makeStores();
    mocks.filters.apiParams.idIbge7 = '3550308';
    mocks.municipalMap.load.mockImplementation(async function () { this.loadedKey = null; });
    await expect(prepareAnalysisPage('/municipios')).rejects.toThrow('O mapa municipal não ficou pronto.');

    dismissAnalysisPageNavigation();
    makeStores();
    mocks.risk.selectedRiskIndicator = 'ticket_medio';
    mocks.risk.fetchRiskIndicatorSummary.mockImplementation(async function () { this.summaryError = 'Falha no resumo'; });
    await expect(prepareAnalysisPage('/municipios')).rejects.toThrow('Falha no resumo');

    dismissAnalysisPageNavigation();
    makeStores();
    mocks.filters.apiParams.idIbge7 = '3550308';
    mocks.risk.selectedRiskIndicator = 'ticket_medio';
    mocks.risk.fetchRiskIndicatorSummary.mockImplementation(async function () { this.summaryParamsKey = 'stale'; });
    await expect(prepareAnalysisPage('/municipios'))
      .rejects.toThrow('A análise municipal do indicador não ficou pronta.');

    dismissAnalysisPageNavigation();
    makeStores();
    mocks.filters.apiParams.idIbge7 = '3550308';
    mocks.risk.selectedRiskIndicator = 'ticket_medio';
    mocks.risk.summaryParamsKey = JSON.stringify({ indicador: 'ticket_medio', params: { uf: 'SP' } });
    mocks.risk.summaryError = 'Resumo municipal indisponível';
    await expect(prepareAnalysisPage('/municipios')).rejects.toThrow('Resumo municipal indisponível');

    dismissAnalysisPageNavigation();
    makeStores();
    mocks.risk.selectedRiskIndicator = 'ticket_medio';
    mocks.risk.fetchRiskIndicatorSummary.mockImplementation(async function () { this.summaryParamsKey = 'stale'; });
    await expect(prepareAnalysisPage('/estabelecimentos')).rejects.toThrow('O mapa dos estabelecimentos não ficou pronto.');

    dismissAnalysisPageNavigation();
    makeStores();
    mocks.risk.selectedRiskIndicator = 'ticket_medio';
    mocks.risk.fetchRiskIndicatorEstablishments.mockImplementation(async function () { this.tableParamsKey = 'stale'; });
    await expect(prepareAnalysisPage('/estabelecimentos')).rejects.toThrow('A tabela dos estabelecimentos não ficou pronta.');

    dismissAnalysisPageNavigation();
    makeStores();
    mocks.risk.selectedRiskIndicator = 'ticket_medio';
    mocks.risk.summaryParamsKey = JSON.stringify({ indicador: 'ticket_medio', params: { uf: 'SP' } });
    mocks.risk.summaryError = 'Falha resumida do indicador';
    await expect(prepareAnalysisPage('/estabelecimentos')).rejects.toThrow('Falha resumida do indicador');

    dismissAnalysisPageNavigation();
    makeStores();
    mocks.risk.selectedRiskIndicator = 'ticket_medio';
    mocks.risk.summaryParamsKey = JSON.stringify({ indicador: 'ticket_medio', params: { uf: 'SP' } });
    mocks.risk.tableParamsKey = JSON.stringify({
      indicador: 'ticket_medio',
      params: { uf: 'SP' },
      page: 1,
      pageSize: 25,
      sortField: 'razao_social',
      sortOrder: 1,
    });
    mocks.risk.tableError = 'Falha detalhada da tabela';
    await expect(prepareAnalysisPage('/estabelecimentos')).rejects.toThrow('Falha detalhada da tabela');
  });

  it('descarta conclusão após layout e normaliza falha não Error', async () => {
    mocks.filters.sidebarLocked = false;
    let transitionHandler;
    const main = {
      parentElement: {},
      getBoundingClientRect: () => ({ left: 1 }),
      addEventListener: vi.fn((_name, handler) => { transitionHandler = handler; }),
      removeEventListener: vi.fn(),
    };
    vi.spyOn(document, 'querySelector').mockReturnValue(main);
    vi.stubGlobal('getComputedStyle', () => ({ getPropertyValue: () => '500px' }));
    window.matchMedia = vi.fn(() => ({ matches: false }));
    beginAnalysisPageNavigation('/estabelecimentos');
    await Promise.resolve();
    const preparation = prepareAnalysisPage('/estabelecimentos');
    await Promise.resolve();
    dismissAnalysisPageNavigation();
    transitionHandler({ target: main, propertyName: 'margin-left' });
    await expect(preparation).resolves.toBeUndefined();
    expect(analysisPageEntry.preparedPath).toBeNull();

    dismissAnalysisPageNavigation();
    makeStores();
    mocks.geo.municipiosGeoJson = null;
    mocks.geo.loadMunicipiosGeo.mockRejectedValueOnce('erro texto');
    await expect(prepareAnalysisPage('/municipios')).rejects.toBe('erro texto');
    expect(analysisPageEntry.errorMessage).toBe('erro texto');
  });

  it('libera a navegação quando a transição da sidebar termina pelo timeout', async () => {
    mocks.filters.sidebarLocked = false;
    const main = {
      parentElement: {},
      getBoundingClientRect: () => ({ left: 10 }),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    };
    vi.spyOn(document, 'querySelector').mockReturnValue(main);
    vi.stubGlobal('getComputedStyle', () => ({ getPropertyValue: () => '300px' }));
    window.matchMedia = vi.fn(() => ({ matches: false }));
    beginAnalysisPageNavigation('/estabelecimentos');
    await Promise.resolve();

    const preparation = prepareAnalysisPage('/estabelecimentos');
    await vi.advanceTimersByTimeAsync(TIMING.SIDEBAR_MOTION_MS * 1.25 + 1);
    await expect(preparation).resolves.toBeUndefined();
    expect(main.removeEventListener).toHaveBeenCalledWith('transitionend', expect.any(Function));
    await revealAnalysisPage('/estabelecimentos');
    expect(analysisPageEntry.pendingPath).toBeNull();
  });

  it('não registra erro obsoleto quando uma dependência rejeita após dispensar a navegação', async () => {
    let rejectMap;
    mocks.ensureMap.mockImplementation(() => new Promise((resolve, reject) => { rejectMap = reject; }));
    const preparation = prepareAnalysisPage('/estabelecimentos');
    await Promise.resolve();
    dismissAnalysisPageNavigation();
    rejectMap(new Error('falha depois de sair'));
    await expect(preparation).rejects.toThrow('falha depois de sair');
    expect(analysisPageEntry.errorPath).toBeNull();
    expect(analysisPageEntry.errorMessage).toBeNull();
  });

  it('descarta resultado se a navegação mudar enquanto aguarda a transição da sidebar', async () => {
    mocks.filters.sidebarLocked = false;
    let transitionHandler;
    const main = {
      parentElement: {},
      getBoundingClientRect: () => ({ left: 10 }),
      addEventListener: vi.fn((_name, handler) => { transitionHandler = handler; }),
      removeEventListener: vi.fn(),
    };
    vi.spyOn(document, 'querySelector').mockReturnValue(main);
    vi.stubGlobal('getComputedStyle', () => ({ getPropertyValue: () => '300px' }));
    window.matchMedia = vi.fn(() => ({ matches: false }));
    beginAnalysisPageNavigation('/estabelecimentos');
    await nextTick();

    let reads = 0;
    let markDismissed;
    const dismissed = new Promise((resolve) => { markDismissed = resolve; });
    Object.defineProperty(mocks.filters, 'apiParamsKey', {
      configurable: true,
      get() {
        reads += 1;
        if (reads === 2) {
          queueMicrotask(() => {
            dismissAnalysisPageNavigation();
            markDismissed();
          });
        }
        return 'filters-1';
      },
    });
    const preparation = prepareAnalysisPage('/estabelecimentos');
    await dismissed;
    transitionHandler({ target: main, propertyName: 'margin-left' });
    await expect(preparation).resolves.toBeUndefined();
    expect(analysisPageEntry.preparedPath).toBeNull();
  });
});
