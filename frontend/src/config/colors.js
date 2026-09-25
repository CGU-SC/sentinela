/**
 * Paleta de cores do sistema Sentinela.
 * Fonte única de verdade — todos os outros módulos importam daqui.
 * Valores baseados em Tailwind CSS v3.
 *
 * NUNCA defina cores hex em outros arquivos de config ou componentes.
 * Adicione aqui e exporte o token correto.
 */

// ── Paleta base ───────────────────────────────────────────────────────────────
// Tokens nomeados por família + escala. Apenas os tons em uso no sistema.
export const PALETTE = {
  red: {
    300: "#fca5a5",
    400: "#f87171",
    500: "#ef4444",
    600: "#dc2626",
    700: "#b91c1c",
    800: "#991b1b",
  },
  orange: { 400: "#fb923c", 500: "#f97316" },
  amber: { 400: "#fbbf24", 500: "#f59e0b", 600: "#d97706" },
  green: { 300: "#86efac", 400: "#4ade80", 500: "#22c55e", 600: "#16a34a" },
  emerald: { 300: "#6ee7b7", 400: "#34d399", 500: "#10b981", 600: "#059669" },
  blue: { 500: "#3b82f6", 600: "#2563eb" },
  indigo: { 500: "#6366f1", 600: "#4f46e5" },
  violet: { 400: "#a78bfa", 500: "#8b5cf6", 600: "#7c3aed" },
  fuchsia: { 400: "#e879f9", 500: "#d946ef", 600: "#c026d5" },
  rose: { 500: "#f43f5e", 600: "#e11d48" },
  slate: { 200: "#e2e8f0", 400: "#94a3b8", 500: "#64748b", 800: "#1e293b" },
  zinc: { 100: "#f4f4f5" },
};

// ── Cores semânticas de risco ─────────────────────────────────────────────────
// Usadas em badges, tabelas, CSS (via v-bind) e configurações de limiar.
export const RISK_COLORS = {
  CRITICAL: PALETTE.red[800], // Conservando o Dark/Seriedade
  HIGH: PALETTE.rose[600], // '#e11d48' - O seu novo vermelho Premium
  MEDIUM: PALETTE.amber[500], // '#f59e0b'
  LOW: PALETTE.amber[500],
};

// ── Séries de dados — light / dark ────────────────────────────────────────────
// Par regular (verde) / irregular (vermelho) para Volume Financeiro e similares.
export const CHART_SERIES = {
  dark: {
    green: PALETTE.green[500], // '#22c55e'
    greenGrad: PALETTE.green[400], // '#4ade80'
    red: PALETTE.red[500], // '#ef4444'
    redGrad: PALETTE.red[400], // '#f87171'
  },
  light: {
    green: PALETTE.emerald[500], // '#10b981'
    greenGrad: PALETTE.emerald[400], // '#34d399'
    red: PALETTE.rose[600], // '#e11d48' - Premium
    redGrad: PALETTE.rose[500], // '#f43f5e' - Premium
  },
};

// ── Escala de cor do mapa de risco (VisualMap ECharts + PDF) ─────────────────
// Fonte única de verdade. Formato `pieces` do ECharts — breakpoints explícitos.
// `color`: fill do município. `borderColor`: borda ao selecionar.
// Dois temas: `light` usa tons suaves (fundo branco aguenta); `dark` usa tons mais
// saturados/luminosos para furar o fundo escuro.
// Regra de contraste:
//   Light — borda 2 tons mais escura que o fill até 55%; pivot para mais clara em 56%+
//           (fills muito escuros absorvem bordas escuras — precisam de contraste inverso)
//   Dark  — 0–31%: borda escura (mesmo princípio do light)
//            32%+: borda luminosa/brilhante — fill escuro sobre fundo escuro do mapa
//            56%+: orange-glow intencional nos fills críticos (efeito premium de perigo)
export const MAP_VISUAL_SCALE = {
  light: [
    { max: 2, color: "#ffedd5", borderColor: "#fb923c" }, // 0–2%
    { min: 2, max: 5, color: "#fed7aa", borderColor: "#f97316" }, // 2–5%
    { min: 5, max: 10, color: "#fdba74", borderColor: "#ea580c" }, // 5–10%
    { min: 10, max: 15, color: "#fb923c", borderColor: "#c2410c" }, // 10–15%
    { min: 15, max: 20, color: "#fca5a5", borderColor: "#dc2626" }, // 15–20%
    { min: 20, max: 30, color: "#f87171", borderColor: "#b91c1c" }, // 20–30%
    { min: 30, max: 40, color: "#ef4444", borderColor: "#b91c1c" }, // 30–40%
    { min: 40, max: 55, color: "#dc2626", borderColor: "#991b1b" }, // 40–55%
    { min: 55, max: 65, color: "#c81e1e", borderColor: "#ef4444" }, // 55–65%  ← pivot: borda mais clara
    { min: 65, max: 75, color: "#b91c1c", borderColor: "#ef4444" }, // 65–75%
    { min: 75, max: 85, color: "#991b1b", borderColor: "#ef4444" }, // 75–85%
    { min: 85, color: "#7f1d1d", borderColor: "#ef4444" }, // 85–100%
  ],
  dark: [
    { max: 2, color: "#fed7aa", borderColor: "#ea580c" }, // 0–2%
    { min: 2, max: 5, color: "#fdba74", borderColor: "#c2410c" }, // 2–5%
    { min: 5, max: 10, color: "#fb923c", borderColor: "#9a3412" }, // 5–10%
    { min: 10, max: 15, color: "#f97316", borderColor: "#7c2d12" }, // 10–15%
    { min: 15, max: 20, color: "#f87171", borderColor: "#991b1b" }, // 15–20%
    { min: 20, max: 30, color: "#ef4444", borderColor: "#991b1b" }, // 20–30%
    { min: 30, max: 40, color: "#dc2626", borderColor: "#f97316" }, // 30–40%  ← pivot: borda luminosa
    { min: 40, max: 55, color: "#c81e1e", borderColor: "#f97316" }, // 40–55%
    { min: 55, max: 65, color: "#b91c1c", borderColor: "#f97316" }, // 55–65%  ← orange-glow
    { min: 65, max: 75, color: "#991b1b", borderColor: "#f97316" }, // 65–75%
    { min: 75, max: 85, color: "#7f1d1d", borderColor: "#f97316" }, // 75–85%  ← glow mais forte
    { min: 85, color: "#450a0a", borderColor: "#f97316" }, // 85–100%
  ],
};

// Participacao de medicos anomalos entre os ativos no mapa nacional de CRMs.
// Faixas fixas preservam o significado das cores ao trocar o periodo.
export const CRM_ANOMALY_MAP_SCALE = {
  light: [
    { gte: 0, lt: 0.05, label: '0–<0,05%', color: '#ffedd5', borderColor: '#fb923c' },
    { gte: 0.05, lt: 0.1, label: '0,05–<0,10%', color: '#fed7aa', borderColor: '#f97316' },
    { gte: 0.1, lt: 0.2, label: '0,10–<0,20%', color: '#fdba74', borderColor: '#ea580c' },
    { gte: 0.2, lt: 0.4, label: '0,20–<0,40%', color: '#fb923c', borderColor: '#c2410c' },
    { gte: 0.4, lt: 0.8, label: '0,40–<0,80%', color: '#f87171', borderColor: '#b91c1c' },
    { gte: 0.8, label: '≥0,80%', color: '#dc2626', borderColor: '#991b1b' },
  ],
  dark: [
    { gte: 0, lt: 0.05, label: '0–<0,05%', color: '#fed7aa', borderColor: '#ea580c' },
    { gte: 0.05, lt: 0.1, label: '0,05–<0,10%', color: '#fdba74', borderColor: '#c2410c' },
    { gte: 0.1, lt: 0.2, label: '0,10–<0,20%', color: '#fb923c', borderColor: '#9a3412' },
    { gte: 0.2, lt: 0.4, label: '0,20–<0,40%', color: '#f97316', borderColor: '#7c2d12' },
    { gte: 0.4, lt: 0.8, label: '0,40–<0,80%', color: '#ef4444', borderColor: '#991b1b' },
    { gte: 0.8, label: '≥0,80%', color: '#b91c1c', borderColor: '#f97316' },
  ],
};

export const GEOGRAPHIC_DISTRIBUTION_SCALE = [
  { min: 0, max: 2, color: "#FAF6F6", borderColor: "#D4B3B3" },
  { min: 2, max: 5, color: "#FCE8E8", borderColor: "#E7A8A8" },
  { min: 5, max: 10, color: "#F9CACA", borderColor: "#DA7E7E" },
  { min: 10, max: 20, color: "#F59C9C", borderColor: "#C95C5C" },
  { min: 20, max: 35, color: "#EB6A6A", borderColor: "#A63A3A" },
  { min: 35, color: "#C81E1E", borderColor: "#7F1D1D" },
];

// ── Constantes de tooltip ECharts ─────────────────────────────────────────────
// Sombra do axisPointer — usada em todos os gráficos ECharts do projeto.
export const CHART_TOOLTIP_SHADOW = "rgba(255, 255, 255, 0.04)";

// ── Acentos do RiskAnalysisChart (barras violeta + linha vermelha) ────────────
export const CHART_RISK_ACCENTS = {
  dark: { bar: PALETTE.violet[500], barGrad: PALETTE.violet[400] }, // '#8b5cf6', '#a78bfa'
  light: { bar: PALETTE.violet[600], barGrad: PALETTE.violet[500] }, // '#7c3aed', '#8b5cf6'
};

// ── Acentos do UfAnalysisChart (índigo + esmeralda + azul + vermelho + laranja) ─
export const CHART_UF_ACCENTS = {
  dark: {
    bar1: PALETTE.indigo[500], // '#6366f1'
    bar1Grad: PALETTE.indigo[500] + "44",
    bar2: PALETTE.emerald[500], // '#10b981'
    bar2Grad: PALETTE.emerald[500] + "44",
    area: PALETTE.blue[500], // '#3b82f6'
    areaGrad: PALETTE.blue[500] + "08",
    barRed: PALETTE.red[500], // '#ef4444'
    barOrange: PALETTE.orange[500], // '#f97316'
  },
  light: {
    bar1: PALETTE.indigo[600], // '#4f46e5'
    bar1Grad: PALETTE.indigo[600] + "22",
    bar2: PALETTE.emerald[600], // '#059669'
    bar2Grad: PALETTE.emerald[600] + "22",
    area: PALETTE.blue[600], // '#2563eb'
    areaGrad: PALETTE.blue[600] + "08",
    barRed: PALETTE.red[500], // '#ef4444' (igual em ambos os modos)
    barOrange: PALETTE.orange[500], // '#f97316' (igual em ambos os modos)
  },
};

// Escala contínua da taxa diária de prescrições na análise geográfica de CRMs.
export const CRM_PRESCRICOES_SCALE = {
  dark: [PALETTE.blue[500], PALETTE.indigo[500], PALETTE.violet[500], PALETTE.fuchsia[500]],
  light: [PALETTE.blue[600], PALETTE.indigo[600], PALETTE.violet[600], PALETTE.fuchsia[600]],
};
