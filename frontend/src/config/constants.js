/**
 * Constantes globais do Projeto Sentinela.
 * Fonte única de verdade para datas, módulos, filtros, timing e configurações de UI.
 */

// ─────────────────────────────────────────────────────────────
// PERÍODO DE AUDITORIA
// Alterar aqui reflete em: slider, filtros, geração de meses e defaults.
// ─────────────────────────────────────────────────────────────
export const AUDIT_PERIOD = {
    START_YEAR:       2015,
    START_MONTH:      6,    // Julho (0-indexed) — início do programa
    END_YEAR:         2024,
    END_MONTH:        11,   // Dezembro (0-indexed)
    TOTAL_MONTHS:     114,  // Jul/2015 a Dez/2024
    SLIDER_MAX_INDEX: 113,  // 0-indexed → TOTAL_MONTHS - 1
};

export const MONTH_LABELS = ['JAN', 'FEV', 'MAR', 'ABR', 'MAI', 'JUN', 'JUL', 'AGO', 'SET', 'OUT', 'NOV', 'DEZ'];

/** Anos disponíveis para atalho rápido no filtro de período. */
export const ANALYSIS_YEARS = Array.from(
    { length: AUDIT_PERIOD.END_YEAR - AUDIT_PERIOD.START_YEAR + 1 },
    (_, i) => AUDIT_PERIOD.START_YEAR + i
);

/**
 * Gera a lista de meses disponíveis para o filtro temporal.
 * Usa AUDIT_PERIOD como fonte única — sem magic numbers.
 */
const generateAvailableMonths = () => {
    const months = [];
    for (let y = AUDIT_PERIOD.START_YEAR; y <= AUDIT_PERIOD.END_YEAR; y++) {
        const startMonth = (y === AUDIT_PERIOD.START_YEAR) ? AUDIT_PERIOD.START_MONTH : 0;
        for (let m = startMonth; m <= AUDIT_PERIOD.END_MONTH; m++) {
            months.push({
                label: `${MONTH_LABELS[m].toLowerCase()}/${y}`,
                date:  new Date(y, m, 1)
            });
        }
    }
    return months;
};

export const AVAILABLE_MONTHS = generateAvailableMonths();

// ─────────────────────────────────────────────────────────────
// FILTROS
// ─────────────────────────────────────────────────────────────

/** Valor padrão para filtros de seleção — evita a string 'Todos' hardcoded. */
export const FILTER_ALL_VALUE = 'Todos';

export const FILTER_DEFAULTS = {
    UF:               FILTER_ALL_VALUE,
    REGIAO:           FILTER_ALL_VALUE,
    MUNICIPIO:        FILTER_ALL_VALUE,
    UNIDADE_PF:       FILTER_ALL_VALUE,
    SITUACAO:         FILTER_ALL_VALUE,
    MS:               FILTER_ALL_VALUE,
    PORTE:            FILTER_ALL_VALUE,
    GRANDE_REDE:      FILTER_ALL_VALUE,
    PAR_TEIA:         FILTER_ALL_VALUE,
    SOCIO_BENEFICIO:  FILTER_ALL_VALUE,
    SOCIO_ESOCIAL:    FILTER_ALL_VALUE,
    CNAE_INCOMPATIVEL: false,
    SOCIO_IDADE_ATIPICA: false,
    SOCIO_FALECIDO: false,
    PERCENTUAL_RANGE: [0, 100],
    VALOR_MIN:        0,
    VALOR_MAX:        1000000,
    VOLUME_ATIPICO_ENABLED: false,
    VOLUME_ATIPICO_PERCENTUAL: 50,
    VOLUME_ATIPICO_MIN: 40,
    VOLUME_ATIPICO_MAX: 2000,
    DISPERSAO_UF_SEM_FRONTEIRA_ENABLED: false,
    DISPERSAO_UF_SEM_FRONTEIRA_PERCENTUAL: 10,
    DISPERSAO_UF_SEM_FRONTEIRA_MIN: 1,
    DISPERSAO_UF_SEM_FRONTEIRA_MAX: 100,
    CLUSTER:          FILTER_ALL_VALUE,
    STATUS:           FILTER_ALL_VALUE,
    RFA:              FILTER_ALL_VALUE,
    SEARCH:           '',
    DATE_RANGE:       [
        new Date(AUDIT_PERIOD.START_YEAR, AUDIT_PERIOD.START_MONTH, 1),
        new Date(AUDIT_PERIOD.END_YEAR,   AUDIT_PERIOD.END_MONTH,   31)
    ],
    SLIDER_INDEX_RANGE: [0, AUDIT_PERIOD.SLIDER_MAX_INDEX],
};

/** Atalhos rápidos do slider de % de não-comprovação. */
export const PERCENTUAL_QUICK_SELECT = [10, 20, 30, 40, 50, 60, 70, 80, 90, 100];

/** Comprimento do CNPJ raiz (primeiros 8 dígitos). */
export const CNPJ_RAIZ_LENGTH = 8;

/** Filtros suportados pelos agregados gerenciais da análise de CRMs. */
export const CRM_ANALYSIS_ALLOWED_QUERY_PARAMS = Object.freeze([
    'data_inicio',
    'data_fim',
    'uf',
    'regiao_id',
    'id_ibge7',
]);

export const CRM_ANALYSIS_FILTER_SCOPE_NOTICE =
    'Mapa e ranking de CRMs consideram apenas período e localização. Os demais filtros ativos continuam aplicados somente aos indicadores gerais.';

// ─────────────────────────────────────────────────────────────
// TIMING (ms)
// Centraliza todos os delays/debounces/intervalos do sistema.
// ─────────────────────────────────────────────────────────────
export const TIMING = {
    RELOAD_DELAY:          800,  // Aguarda antes de recarregar a página pós-sync
    POLL_INTERVAL:        1000,  // Intervalo de polling do status de cache
    DROPDOWN_FOCUS_DELAY:   50,  // Delay para focar o input do dropdown
    FILTER_DEBOUNCE:       200,  // Debounce da persistência de filtros no localStorage
};

// ─────────────────────────────────────────────────────────────
// KPIs
// ─────────────────────────────────────────────────────────────

/** Mapeamento de labels vindos do backend para labels exibidos na UI. */
export const KPI_LABEL_MAP = {
    'QTDE DE MEDICAMENTOS':   'Nº MEDICAMENTOS',
    'VALOR TOTAL DE VENDAS':  'VALOR DAS VENDAS',
    'VALOR SEM COMPROVAÇÃO':  'SEM COMPROVAÇÃO',
};

/** Ordem de exibição dos KPIs no dashboard. */
export const KPI_PRIORITY_ORDER = [
    'MUNICÍPIOS',
    'CNPJS',
    'VALOR DAS VENDAS',
    'SEM COMPROVAÇÃO',
    '% SEM COMPROVAÇÃO',
    'Nº MEDICAMENTOS',
];

/** KPIs mantidos no dashboard, mas ocultos na tela de estabelecimentos. */
export const ESTABLISHMENTS_HIDDEN_KPI_LABELS = [KPI_LABEL_MAP['QTDE DE MEDICAMENTOS']];
