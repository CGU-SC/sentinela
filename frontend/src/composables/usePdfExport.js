import { ref } from 'vue';
import jsPDF from 'jspdf';
import autoTable from 'jspdf-autotable';
import { INDICATOR_GROUPS, RISK_COLORS_RGB } from '@/config/riskConfig';
import { MAP_VISUAL_SCALE } from '@/config/colors.js';
import { saveBlobOrDownload } from '@/utils/download';


// ── PrimeIcons codepoints ──────────────────────────────────
const PI = {
  SHIELD:              0xe9b9,
  CHART_LINE:          0xe98b,
  CHART_BAR:           0xe96d,
  TABLE:               0xe969,
  EXCLAMATION_TRIANGLE:0xe922,
  CHECK_CIRCLE:        0xe90a,
  TIMES_CIRCLE:        0xe90c,
  BUILDING:            0xe9cf,
  MONEY_BILL:          0xe974,
  PERCENTAGE:          0xe9be,
  MAP_MARKER:          0xe968,
  USERS:               0xe941,
  FILE_PDF:            0xe98d,
  GLOBE:               0xe94f,
  COMPASS:             0xe9ab,
  SHARE_ALT:           0xe93f,
  MAP:                 0xe9c2,
  SITEMAP:             0xe93e,
};

function formatPopulacao(n) {
  if (n == null) return '—';
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(2).replace('.', ',')} M`;
  if (n >= 1_000)     return `${(n / 1_000).toFixed(1).replace('.', ',')} mil`;
  return n.toLocaleString('pt-BR');
}

async function ttfToBase64(url) {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  const buf = await res.arrayBuffer();
  const bytes = new Uint8Array(buf);
  let binary = '';
  for (let i = 0; i < bytes.length; i += 8192) {
    binary += String.fromCharCode(...bytes.subarray(i, i + 8192));
  }
  return btoa(binary);
}

async function loadFontsInto(pdf) {
  const results = { inter: false, primeicons: false };
  try {
    const [regular, semibold, bold] = await Promise.all([
      ttfToBase64('/fonts/Inter_18pt-Regular.ttf'),
      ttfToBase64('/fonts/Inter_18pt-SemiBold.ttf'),
      ttfToBase64('/fonts/Inter_18pt-Bold.ttf'),
    ]);
    pdf.addFileToVFS('Inter-Regular.ttf', regular);
    pdf.addFont('Inter-Regular.ttf', 'inter', 'normal');
    pdf.addFileToVFS('Inter-SemiBold.ttf', semibold);
    pdf.addFont('Inter-SemiBold.ttf', 'inter', 'semibold');
    pdf.addFileToVFS('Inter-Bold.ttf', bold);
    pdf.addFont('Inter-Bold.ttf', 'inter', 'bold');
    results.inter = true;
  } catch (e) {
    console.warn('[usePdfExport] Inter not loaded:', e);
  }
  try {
    const b64 = await ttfToBase64('/fonts/primeicons.ttf');
    pdf.addFileToVFS('primeicons.ttf', b64);
    pdf.addFont('primeicons.ttf', 'primeicons', 'normal');
    results.primeicons = true;
  } catch (e) {
    console.warn('[usePdfExport] PrimeIcons not loaded:', e);
  }
  return results;
}

// ── Helpers de cor/risco ───────────────────────────────────
function getOfficialStatus(indicatorKey, indicadorData) {
  if (!indicadorData?.status) {
    throw new Error(`Indicador ${indicatorKey} sem status oficial retornado pela API.`);
  }
  return String(indicadorData.status).toUpperCase();
}

function fmtVal(valor, formato, formatCurrencyFull) {
  if (valor == null) return '—';
  if (formato === 'pct')  return valor.toFixed(2) + '%';
  if (formato === 'pct3') return valor.toFixed(3) + '%';
  if (formato === 'val')  return formatCurrencyFull(valor);
  return valor.toFixed(2);
}

function fmtRisco(v) {
  return v != null ? v.toFixed(1) + 'x' : '—';
}

function formatCompetenciaMes(value, context) {
  const text = String(value);
  if (!/^\d{6}$/.test(text)) {
    throw new Error(`Competência mensal inválida em ${context}.`);
  }
  const month = Number(text.slice(4, 6));
  if (month < 1 || month > 12) {
    throw new Error(`Competência mensal inválida em ${context}.`);
  }
  return `${text.slice(4, 6)}/${text.slice(0, 4)}`;
}

/** Converte hex (#rrggbb) → [r, g, b]. */
function hexToRgb(hex) {
  return [
    parseInt(hex.slice(1, 3), 16),
    parseInt(hex.slice(3, 5), 16),
    parseInt(hex.slice(5, 7), 16),
  ];
}

/**
 * Retorna [r, g, b] para um percentual usando os mesmos breakpoints do ECharts visualMap.
 * Usa a estrutura `pieces` de MAP_VISUAL_SCALE para garantir consistência total com os mapas.
 */
function getScalePiece(perc) {
  if (perc == null) return null;
  const scale = MAP_VISUAL_SCALE.light; // PDF é sempre modo claro
  return scale.find(p => {
    const aboveMin = p.min == null || perc >= p.min;
    const belowMax = p.max == null || perc < p.max;
    return aboveMin && belowMax;
  }) ?? scale[scale.length - 1];
}

function getRiskRgbByPerc(perc) {
  const piece = getScalePiece(perc);
  return piece ? hexToRgb(piece.color) : RISK_COLORS_RGB.NONE;
}

function getRiskBorderRgbByPerc(perc) {
  const piece = getScalePiece(perc);
  return piece ? hexToRgb(piece.borderColor) : [255, 255, 255];
}

/**
 * Desenha o mapa de todos os municípios de uma região de saúde, coloridos por risco.
 */
function drawRegionMap(pdf, geoJson, regionIds, targetIbge7, resultadoMunicipios, x, y, w, h) {
  if (!geoJson?.features || !regionIds?.length) return;

  // Mapeia id_ibge7 → percValSemComp
  const riskMap = {};
  (resultadoMunicipios ?? []).forEach(m => { riskMap[String(m.id_ibge7)] = m.percValSemComp; });

  // Filtra features da região
  const features = regionIds
    .map(id => geoJson.features.find(f => String(f.properties.id) === String(id)))
    .filter(Boolean);
  if (!features.length) return;

  // Bounding box de toda a região
  const allCoords = features.flatMap(f => {
    if (f.geometry.type === 'Polygon') return f.geometry.coordinates[0];
    if (f.geometry.type === 'MultiPolygon') return f.geometry.coordinates.flatMap(p => p[0]);
    return [];
  });
  const lons = allCoords.map(c => c[0]);
  const lats = allCoords.map(c => c[1]);
  const minLon = Math.min(...lons), maxLon = Math.max(...lons);
  const minLat = Math.min(...lats), maxLat = Math.max(...lats);
  const spanLon = maxLon - minLon || 0.001;
  const spanLat = maxLat - minLat || 0.001;

  const pad = 4;
  const scale = Math.min((w - pad * 2) / spanLon, (h - pad * 2) / spanLat);
  const ox = x + pad + ((w - pad * 2) - spanLon * scale) / 2;
  const oy = y + h - pad - ((h - pad * 2) - spanLat * scale) / 2;
  const project = ([lon, lat]) => [ox + (lon - minLon) * scale, oy - (lat - minLat) * scale];

  pdf.setLineJoin('round');

  // Desenha em duas passagens: vizinhos primeiro, alvo por último (para a borda não ser sobreposta)
  let targetFeature = null;
  const noDataFill = [214, 221, 230]; // Voltando para o cinza-azulado neutro

  const drawFeature = (f) => {
    const id = String(f.properties.id);
    const isTarget = id === String(targetIbge7);
    const perc = riskMap[id];
    const hasData = perc != null;

    let fill, stroke, lw;
    if (isTarget) {
      fill   = getRiskRgbByPerc(perc);
      stroke = getRiskBorderRgbByPerc(perc);
      lw     = 0.5;
    } else if (hasData) {
      fill   = getRiskRgbByPerc(perc);
      stroke = [255, 255, 255];
      lw     = 0.15;
    } else {
      fill   = noDataFill;
      stroke = [255, 255, 255];
      lw     = 0.15;
    }

    let rings = [];
    if (f.geometry.type === 'Polygon') rings = [f.geometry.coordinates[0]];
    else if (f.geometry.type === 'MultiPolygon') rings = f.geometry.coordinates.map(p => p[0]);

    for (const ring of rings) {
      const pts = ring.map(project);
      const deltas = [];
      for (let i = 1; i < pts.length; i++) {
        deltas.push([pts[i][0] - pts[i-1][0], pts[i][1] - pts[i-1][1]]);
      }
      pdf.setFillColor(...fill);
      pdf.setDrawColor(...stroke);
      pdf.setLineWidth(lw);
      pdf.lines(deltas, pts[0][0], pts[0][1], [1, 1], 'FD', true);
    }
  };

  for (const f of features) {
    if (String(f.properties.id) === String(targetIbge7)) {
      targetFeature = f;
      continue;
    }
    drawFeature(f);
  }
  if (targetFeature) drawFeature(targetFeature);
}

/**
 * Desenha o polígono de um único município diretamente no PDF (vetor).
 */
function drawMunicipalityPolygon(pdf, geoJson, targetIbge7, x, y, w, h, fillRgb, strokeRgb) {
  if (!geoJson?.features) return;
  const feature = geoJson.features.find(f => String(f.properties.id) === String(targetIbge7));
  if (!feature) return;

  // Suporte a Polygon e MultiPolygon — usa o maior anel
  let rings = [];
  if (feature.geometry.type === 'Polygon') {
    rings = [feature.geometry.coordinates[0]];
  } else if (feature.geometry.type === 'MultiPolygon') {
    rings = feature.geometry.coordinates.map(p => p[0]);
  }
  if (!rings.length) return;

  // Bounding box de todos os aneis
  const allCoords = rings.flat();
  const lons = allCoords.map(c => c[0]);
  const lats = allCoords.map(c => c[1]);
  const minLon = Math.min(...lons), maxLon = Math.max(...lons);
  const minLat = Math.min(...lats), maxLat = Math.max(...lats);
  const spanLon = maxLon - minLon || 0.001;
  const spanLat = maxLat - minLat || 0.001;

  // Escala preservando proporção, com padding interno
  const pad = 4;
  const scaleX = (w - pad * 2) / spanLon;
  const scaleY = (h - pad * 2) / spanLat;
  const scale  = Math.min(scaleX, scaleY);

  // Centraliza dentro da caixa
  const ox = x + pad + ((w - pad * 2) - spanLon * scale) / 2;
  const oy = y + h - pad - ((h - pad * 2) - spanLat * scale) / 2;

  const project = ([lon, lat]) => [
    ox + (lon - minLon) * scale,
    oy - (lat - minLat) * scale,  // lat cresce pra cima, PDF cresce pra baixo
  ];

  pdf.setFillColor(...fillRgb);
  pdf.setDrawColor(...strokeRgb);
  pdf.setLineWidth(0.4);

  for (const ring of rings) {
    const pts = ring.map(project);
    const lines = [];
    for (let i = 1; i < pts.length; i++) {
      lines.push([pts[i][0] - pts[i - 1][0], pts[i][1] - pts[i - 1][1]]);
    }
    pdf.lines(lines, pts[0][0], pts[0][1], [1, 1], 'FD', true);
  }
}

function assertReportData(reportData) {
  if (!reportData || typeof reportData !== 'object') {
    throw new Error('Payload do relatorio PDF ausente.');
  }
  if (!Array.isArray(reportData.evolucao?.semestres)) {
    throw new Error('Payload do relatorio PDF sem evolucao.semestres.');
  }
  if (!reportData.indicadores?.indicadores || typeof reportData.indicadores.indicadores !== 'object') {
    throw new Error('Payload do relatorio PDF sem indicadores.indicadores.');
  }
  if (!reportData.crm?.summary || !Array.isArray(reportData.crm?.crmsInteresse) || !reportData.crm?.kpis) {
    throw new Error('Payload do relatorio PDF sem dados de CRM.');
  }
  if (!reportData.falecidos?.summary || !Array.isArray(reportData.falecidos?.agrupados)) {
    throw new Error('Payload do relatorio PDF sem dados de falecidos.');
  }
}

function drawFinancialChart(pdf, semestres, x, y, w, h, F) {
  pdf.setFillColor(248, 250, 252);
  pdf.setDrawColor(226, 232, 240);
  pdf.setLineWidth(0.25);
  pdf.roundedRect(x, y, w, h, 2, 2, 'FD');

  const plotX = x + 11;
  const plotY = y + 13;
  const plotW = w - 20;
  const plotH = h - 25;
  const maxTotal = Math.max(...semestres.map((s) => Number(s.total || 0)), 1);
  const maxPct = Math.max(...semestres.map((s) => Number(s.pct_irregular || 0)), 10);
  const step = plotW / Math.max(semestres.length, 1);
  const barW = Math.max(2.8, Math.min(7.5, step * 0.42));

  pdf.setFont(F, 'bold');
  pdf.setFontSize(7);
  pdf.setTextColor(30, 41, 59);
  pdf.text('Evolucao semestral: valor comprovado, sem comprovacao e percentual', x + 5, y + 7);

  const legends = [
    { label: 'Comprovado', color: [16, 185, 129] },
    { label: 'Sem comprovacao', color: [239, 68, 68] },
    { label: '% sem comp.', color: [99, 102, 241] },
  ];
  let legendX = x + w - 64;
  pdf.setFont(F, 'normal');
  pdf.setFontSize(5.8);
  for (const item of legends) {
    pdf.setFillColor(...item.color);
    pdf.roundedRect(legendX, y + 4, 2.5, 2.5, 0.5, 0.5, 'F');
    pdf.setTextColor(100, 116, 139);
    pdf.text(item.label, legendX + 3.5, y + 6.2);
    legendX += pdf.getTextWidth(item.label) + 8;
  }

  pdf.setDrawColor(203, 213, 225);
  pdf.setLineWidth(0.2);
  pdf.line(plotX, plotY + plotH, plotX + plotW, plotY + plotH);
  pdf.line(plotX, plotY, plotX, plotY + plotH);

  const linePoints = [];
  semestres.forEach((s, i) => {
    const centerX = plotX + step * i + step / 2;
    const total = Number(s.total || 0);
    const regular = Number(s.regular || 0);
    const irregular = Number(s.irregular || 0);
    const totalH = (total / maxTotal) * plotH;
    const regularH = total > 0 ? totalH * (regular / total) : 0;
    const irregularH = total > 0 ? totalH * (irregular / total) : 0;
    const baseY = plotY + plotH;

    pdf.setFillColor(16, 185, 129);
    pdf.rect(centerX - barW / 2, baseY - regularH, barW, regularH, 'F');
    pdf.setFillColor(239, 68, 68);
    pdf.rect(centerX - barW / 2, baseY - regularH - irregularH, barW, irregularH, 'F');

    const pctY = plotY + plotH - (Number(s.pct_irregular || 0) / maxPct) * plotH;
    linePoints.push([centerX, pctY]);

    pdf.setFontSize(5.3);
    pdf.setFont(F, 'normal');
    pdf.setTextColor(100, 116, 139);
    const label = String(s.semestre ?? '').replace(/^20/, '');
    pdf.text(label, centerX, baseY + 4.2, { align: 'center' });
  });

  if (linePoints.length > 1) {
    pdf.setDrawColor(99, 102, 241);
    pdf.setLineWidth(0.65);
    for (let i = 1; i < linePoints.length; i++) {
      pdf.line(linePoints[i - 1][0], linePoints[i - 1][1], linePoints[i][0], linePoints[i][1]);
    }
  }

  pdf.setFillColor(99, 102, 241);
  for (const [px, py] of linePoints) {
    pdf.circle(px, py, 0.85, 'F');
  }
}

// ── Composable ─────────────────────────────────────────────
export function usePdfExport() {
  const isExporting = ref(false);

  async function exportCnpjPdf({
    cnpjData, geoData, cadastro, cnpj, qtdMunicipiosRegiao,
    reportData, geoStore, resultadoMunicipios, formatCurrencyFull, formatNumberFull, formatarData,
  }) {
    isExporting.value = true;

    try {
      assertReportData(reportData);
      const pdf = new jsPDF({ orientation: 'p', unit: 'mm', format: 'a4' });
      const pageW = pdf.internal.pageSize.getWidth();
      const margin = 14;
      const contentW = pageW - margin * 2;

      // ── Fontes ───────────────────────────────────────────
      const { inter: hasInter, primeicons: hasPrimeicons } = await loadFontsInto(pdf);
      const F = hasInter ? 'inter' : 'helvetica';

      /**
       * Draws a PrimeIcon glyph and returns the horizontal space it occupied
       * (icon width + gap), so callers can offset subsequent text.
       */
      const drawIcon = (codepoint, x, y, { size = 9, color = [255, 255, 255] } = {}) => {
        if (!hasPrimeicons) return 0;
        const prevFont = pdf.getFont();
        const prevSize = pdf.getFontSize();
        pdf.setFont('primeicons', 'normal');
        pdf.setFontSize(size);
        pdf.setTextColor(...color);
        pdf.text(String.fromCodePoint(codepoint), x, y);
        pdf.setFont(prevFont.fontName, prevFont.fontStyle);
        pdf.setFontSize(prevSize);
        return size * 0.38 + 1.5; // approx glyph width + gap
      };

      // ── Helpers visuais ──────────────────────────────────
      const pageHeader = (title, subtitle = '', iconCodepoint = null) => {
        pdf.setFillColor(15, 23, 42);
        pdf.rect(0, 0, pageW, 20, 'F');
        let titleX = margin;
        if (iconCodepoint) {
          titleX += drawIcon(iconCodepoint, margin, 13.5, { size: 10, color: [99, 179, 237] });
        }
        pdf.setFontSize(12);
        pdf.setFont(F, 'bold');
        pdf.setTextColor(255, 255, 255);
        pdf.text(title, titleX, 13);
        if (subtitle) {
          pdf.setFontSize(8);
          pdf.setFont(F, 'normal');
          pdf.setTextColor(100, 116, 139);
          pdf.text(subtitle, pageW - margin, 13, { align: 'right' });
        }
      };

      const sectionTitle = (text, y, color = [30, 41, 59], iconCodepoint = null) => {
        let textX = margin;
        if (iconCodepoint) {
          textX += drawIcon(iconCodepoint, margin, y, { size: 9, color });
        }
        pdf.setFontSize(10);
        pdf.setFont(F, 'bold');
        pdf.setTextColor(...color);
        pdf.text(text, textX, y);
        return y + 7;
      };

      const drawCrmLegend = (items, startY) => {
        if (!items.length) return;

        const labelW = 52;
        const descriptionX = margin + labelW;
        const descriptionW = contentW - labelW - 6;
        const lineHeight = 3.1;

        pdf.setFont(F, 'bold');
        pdf.setFontSize(6.7);
        const measuredRows = items.map(item => {
          const labelLines = pdf.splitTextToSize(item.label, labelW - 6);
          pdf.setFont(F, 'normal');
          const descriptionLines = pdf.splitTextToSize(item.description, descriptionW);
          pdf.setFont(F, 'bold');
          return {
            labelLines,
            descriptionLines,
            height: Math.max(labelLines.length, descriptionLines.length) * lineHeight + 2,
          };
        });

        const titleH = 7;
        const legendH = titleH + measuredRows.reduce((total, row) => total + row.height, 0) + 3;
        let y = startY;
        if (y + legendH > pageH - margin) {
          pdf.addPage();
          pageHeader('Análise de CRMs e Prescritores', cnpjData.razao_social, PI.USERS);
          y = 26;
        }

        pdf.setFillColor(248, 250, 252);
        pdf.setDrawColor(226, 232, 240);
        pdf.setLineWidth(0.3);
        pdf.roundedRect(margin, y, contentW, legendH, 1.5, 1.5, 'FD');

        pdf.setFont(F, 'bold');
        pdf.setFontSize(7.2);
        pdf.setTextColor(30, 41, 59);
        pdf.text('LEGENDA DOS ALERTAS / STATUS E DO NÚMERO DE FARMÁCIAS', margin + 3, y + 4.5);

        let rowY = y + titleH;
        measuredRows.forEach(row => {
          pdf.setFont(F, 'bold');
          pdf.setFontSize(6.7);
          pdf.setTextColor(30, 41, 59);
          pdf.text(row.labelLines, margin + 3, rowY + 3);

          pdf.setFont(F, 'normal');
          pdf.setTextColor(71, 85, 105);
          pdf.text(row.descriptionLines, descriptionX, rowY + 3);
          rowY += row.height;
        });
      };

      // ── PÁGINA CAPA (Início) ──────────────────────────────────
      const fetchBase64 = async (url) => {
        try {
          const res = await fetch(url);
          if (!res.ok) return null;
          const blob = await res.blob();
          return new Promise(resolve => {
            const rd = new FileReader();
            rd.onload = () => resolve(rd.result);
            rd.readAsDataURL(blob);
          });
        } catch(e) { return null; }
      };

      // Usando Date.now() para invalidar o cache forte do navegador (Cache Busting)
      const cguB64 = await fetchBase64(`/img/logo_cgu.png?v=${Date.now()}`);

      const pageH = pdf.internal.pageSize.getHeight();
      pdf.setFillColor(15, 23, 42); 
      pdf.rect(0, 0, pageW, pageH, 'F');
      
      pdf.setFillColor(99, 102, 241); 
      pdf.rect(0, 0, 4, pageH, 'F');

      let currentCY = 8;

      if (cguB64) {
        // Logo oficial, proporção 700x800 (7:8)
        const sizeW = 110;
        const sizeH = 125.7;
        pdf.addImage(cguB64, 'PNG', (pageW - sizeW) / 2, currentCY, sizeW, sizeH);
        currentCY += (sizeH + 10);
      } else {
        currentCY += 50; // Fallback caso não carregue
      }
      
      currentCY += 12; // espaço extra antes do bloco de texto

      pdf.setFont(F, 'bold');
      pdf.setFontSize(28);
      pdf.setTextColor(203, 213, 225);
      pdf.text('SENTINELA', margin + 8, currentCY);
      const sentinelaW = pdf.getTextWidth('SENTINELA');
      pdf.setFont(F, 'normal');
      pdf.setFontSize(12);
      pdf.setTextColor(148, 163, 184);
      pdf.text('/ Sistema de Auditoria Contínua', margin + 8 + sentinelaW + 3, currentCY);

      currentCY += 10;
      pdf.setFont(F, 'bold');
      pdf.setFontSize(16);
      pdf.setTextColor(148, 163, 184);
      pdf.text('Programa Farmácia Popular do Brasil — PFPB', margin + 8, currentCY);

      currentCY += 12;
      pdf.setFont(F, 'bold');
      pdf.setFontSize(18);
      pdf.setTextColor(99, 102, 241);
      pdf.text('Relatório de Análise de Risco', margin + 8, currentCY);

      currentCY += 35;

      // Cor de risco da capa — alinhada com --risk-* do sistema
      const capPerc = cnpjData.percValSemComp ?? 0;
      const capRiskRgb = capPerc >= 20 ? [239, 68,  68 ]   // --risk-critical/high
                       : capPerc >= 5  ? [249, 115, 22 ]   // --risk-medium
                       :                 [16,  185, 129];  // --risk-low

      const cardX = margin + 8;
      const cardW2 = contentW - 16;
      const cardH2 = 52;

      // Card fundo
      pdf.setFillColor(30, 41, 59);
      pdf.roundedRect(cardX, currentCY, cardW2, cardH2, 3, 3, 'F');

      // Borda esquerda colorida pelo risco
      pdf.setFillColor(...capRiskRgb);
      pdf.roundedRect(cardX, currentCY, 3.5, cardH2, 2, 2, 'F');

      // Razão social em destaque
      const cnpjFormatted = cnpj.replace(/^(\d{2})(\d{3})(\d{3})(\d{4})(\d{2})$/, '$1.$2.$3/$4-$5');
      const capRazaoLines = pdf.splitTextToSize(cnpjData.razao_social ?? '—', cardW2 - 55);
      pdf.setFontSize(12);
      pdf.setFont(F, 'bold');
      pdf.setTextColor(148, 163, 184);
      pdf.text(capRazaoLines.slice(0, 2), cardX + 8, currentCY + 12);

      // CNPJ + localidade + região em linha menor
      const capLocal = [
        geoData?.no_municipio ?? cnpjData?.municipio,
        geoData?.sg_uf ?? cnpjData?.uf,
        geoData?.no_regiao_saude ? `Região de Saúde ${geoData.no_regiao_saude}` : null,
      ].filter(Boolean).join('  ·  ');
      const capAddress = cadastro?.logradouro
        ? [
            [cadastro.tipo_logradouro, cadastro.logradouro].filter(Boolean).join(' '),
            cadastro.numero && cadastro.numero !== 'None' ? cadastro.numero : null,
          ].filter(Boolean).join(', ') +
          (cadastro.bairro && cadastro.bairro !== 'None' ? ` · ${cadastro.bairro}` : '') +
          (cadastro.cep && cadastro.cep !== 'None' ? ` · CEP ${cadastro.cep}` : '')
        : null;

      pdf.setFontSize(8.5);
      pdf.setFont(F, 'normal');
      pdf.setTextColor(148, 163, 184);
      pdf.text(`CNPJ ${cnpjFormatted}`, cardX + 8, currentCY + 26);
      pdf.text(capLocal, cardX + 8, currentCY + 33);
      if (capAddress) {
        pdf.setFontSize(7.5);
        pdf.setTextColor(100, 116, 139);
        pdf.text(capAddress, cardX + 8, currentCY + 40);
      }

      // Métricas (% Sem Comp + Score) — tipografia pura, sem card extra
      if (cnpjData.score_risco_final != null) {
        const mx  = cardX + cardW2 - 4; // âncora direita
        const my  = currentCY + 8;

        // % Sem Comprovação
        pdf.setFontSize(6); pdf.setFont(F, 'semibold'); pdf.setTextColor(100, 116, 139);
        pdf.text('% SEM COMPROVAÇÃO', mx, my, { align: 'right' });
        pdf.setFontSize(18); pdf.setFont(F, 'bold'); pdf.setTextColor(...capRiskRgb);
        pdf.text(capPerc.toFixed(1) + '%', mx, my + 10, { align: 'right' });

        // Divisor
        pdf.setDrawColor(51, 65, 85);
        pdf.setLineWidth(0.25);
        pdf.line(mx - 44, my + 13, mx, my + 13);

        // Score
        pdf.setFontSize(6); pdf.setFont(F, 'semibold'); pdf.setTextColor(100, 116, 139);
        pdf.text('SCORE DE RISCO', mx, my + 19, { align: 'right' });
        pdf.setFontSize(18); pdf.setFont(F, 'bold'); pdf.setTextColor(...capRiskRgb);
        pdf.text(cnpjData.score_risco_final.toFixed(1), mx, my + 29, { align: 'right' });
        pdf.setFontSize(7); pdf.setFont(F, 'bold'); pdf.setTextColor(...capRiskRgb);
        pdf.text(cnpjData.classificacao_risco ?? '', mx, my + 34, { align: 'right' });
      }


      pdf.setFont(F, 'normal');
      pdf.setFontSize(9);
      pdf.setTextColor(100, 116, 139); 
      pdf.text(`Gerado em: ${new Date().toLocaleString('pt-BR')}`, margin + 8, pageH - 20);

      pdf.addPage();

      // ── PÁGINA 2 — Identificação (Subsequente Branco) ──────
      // Cor de risco a partir do % sem comprovação
      const perc = cnpjData.percValSemComp ?? 0;
      const riskRgb = perc >= 20 ? [239, 68,  68 ]   // --risk-critical/high
                    : perc >= 5  ? [249, 115, 22 ]   // --risk-medium
                    :              [16,  185, 129];

      // ── Banner escuro ──────────────────────────────
      const headerH = 54;
      pdf.setFillColor(15, 23, 42);
      pdf.rect(0, 0, pageW, headerH, 'F');


      // Branding
      pdf.setFontSize(7.5);
      pdf.setFont(F, 'bold');
      pdf.setTextColor(99, 102, 241);
      pdf.text('SENTINELA · PFPB · CGU', margin, 11);
      pdf.setFontSize(7);
      pdf.setFont(F, 'normal');
      pdf.setTextColor(100, 116, 139);
      pdf.setFontSize(8);
      pdf.text(`Gerado em ${new Date().toLocaleString('pt-BR')}`, pageW - margin, 11, { align: 'right' });

      // Razão social
      const razaoLines = pdf.splitTextToSize(cnpjData.razao_social ?? '—', contentW * 0.78);
      pdf.setFontSize(16);
      pdf.setFont(F, 'bold');
      pdf.setTextColor(148, 163, 184);
      pdf.text(razaoLines.slice(0, 2), margin, 23);

      // CNPJ + localização
      const cnpjFmt = cnpj.replace(/^(\d{2})(\d{3})(\d{3})(\d{4})(\d{2})$/, '$1.$2.$3/$4-$5');
      pdf.setFontSize(8);
      pdf.setFont(F, 'normal');
      pdf.setTextColor(148, 163, 184);
      const locLine = [
        `CNPJ ${cnpjFmt}`,
        geoData?.no_municipio ?? cnpjData?.municipio,
        geoData?.sg_uf ?? cnpjData?.uf,
        geoData?.no_regiao_saude ? `Região de Saúde: ${geoData.no_regiao_saude}` : null,
      ].filter(Boolean).join('  ·  ');
      pdf.text(locLine, margin, 36);

      const address = cadastro?.logradouro
        ? [
            [cadastro.tipo_logradouro, cadastro.logradouro].filter(Boolean).join(' '),
            cadastro.numero && cadastro.numero !== 'None' ? cadastro.numero : null,
          ].filter(Boolean).join(', ') +
          (cadastro.bairro && cadastro.bairro !== 'None' ? ` · ${cadastro.bairro}` : '') +
          (cadastro.cep && cadastro.cep !== 'None' ? ` · CEP ${cadastro.cep}` : '')
        : null;
      if (address) {
        pdf.setFontSize(7.5);
        pdf.setFont(F, 'normal');
        pdf.setTextColor(100, 116, 139);
        pdf.text(address, margin, 44);
      }


      // ── KPI Cards (4: financeiros + score/classificação) ──
      let y = headerH + 10;
      const cardW = (contentW - 12) / 4;
      const cardH = 24;
      const kpiCards = [
        { label: '% SEM COMPROVAÇÃO',    value: `${cnpjData.percValSemComp?.toFixed(2) ?? '—'}%`, accent: riskRgb,        valueColor: riskRgb      },
        { label: 'SCORE DE RISCO',
          value:    cnpjData.score_risco_final != null ? cnpjData.score_risco_final.toFixed(1) : '—',
          sublabel: cnpjData.classificacao_risco ?? '',
          accent:   riskRgb, valueColor: riskRgb },
        { label: 'VALOR SEM COMPROVAÇÃO', value: formatCurrencyFull(cnpjData.valSemComp),          accent: [99, 102, 241], valueColor: [15, 23, 42] },
        { label: 'TOTAL VENDAS',          value: formatCurrencyFull(cnpjData.totalMov),            accent: [71, 85, 105],  valueColor: [15, 23, 42] },
      ];
      kpiCards.forEach((card, i) => {
        const x = margin + i * (cardW + 4);
        pdf.setFillColor(248, 250, 252);
        pdf.roundedRect(x, y, cardW, cardH, 2, 2, 'F');
        pdf.setFillColor(...card.accent);
        pdf.roundedRect(x, y, 2.5, cardH, 1, 1, 'F');
        pdf.setFontSize(7.5); pdf.setFont(F, 'bold'); pdf.setTextColor(100, 116, 139);
        pdf.text(card.label, x + 6, y + 7);
        pdf.setFontSize(13); pdf.setFont(F, 'bold'); pdf.setTextColor(...card.valueColor);
        pdf.text(card.value, x + 6, y + 16);
        if (card.sublabel) {
          pdf.setFontSize(7); pdf.setFont(F, 'bold'); pdf.setTextColor(...card.valueColor);
          pdf.text(card.sublabel, x + 6, y + 21.5);
        }
      });
      y += cardH + 12;

      // ── Rankings ───────────────────────────────────
      pdf.setFontSize(8);
      pdf.setFont(F, 'bold');
      pdf.setTextColor(148, 163, 184);
      pdf.text('RANKINGS DE CRITICIDADE', margin, y);
      pdf.setDrawColor(226, 232, 240);
      pdf.line(margin + 56, y - 1.5, pageW - margin, y - 1.5);
      y += 7;

      const ranks = [
        { label: 'Rank Nacional',  val: cnpjData.rank_nacional,     total: cnpjData.total_nacional,      icon: PI.GLOBE,      iconColor: [253, 224, 71]  },
        { label: 'Rank Estadual',  val: cnpjData.rank_uf,           total: cnpjData.total_uf,            icon: PI.COMPASS,    iconColor: [203, 213, 225] },
        { label: 'Rank Regional',  val: cnpjData.rank_regiao_saude, total: cnpjData.total_regiao_saude,  icon: PI.SHARE_ALT,  iconColor: [251, 191, 36]  },
        { label: 'Rank Municipal', val: cnpjData.rank_municipio,    total: cnpjData.total_municipio,     icon: PI.BUILDING,   iconColor: [148, 163, 184] },
      ];
      const rankColW = contentW / 4;
      ranks.forEach((r, i) => {
        const x = margin + i * rankColW;
        drawIcon(r.icon, x, y + 7, { size: 13, color: r.iconColor });
        const tx = x + 8;
        pdf.setFontSize(8); pdf.setFont(F, 'bold'); pdf.setTextColor(148, 163, 184);
        pdf.text(r.label, tx, y);
        const rankStr = r.val != null ? `${r.val}º` : '—';
        pdf.setFontSize(13); pdf.setFont(F, 'bold'); pdf.setTextColor(15, 23, 42);
        pdf.text(rankStr, tx, y + 9);
        const rankW = pdf.getTextWidth(rankStr);
        pdf.setFontSize(8); pdf.setFont(F, 'normal'); pdf.setTextColor(148, 163, 184);
        pdf.text(`/ ${r.total ?? '—'}`, tx + rankW + 1.5, y + 9);
      });
      y += 22;

      // ── Stats contextuais ──────────────────────────
      const ctxStats = [
        { label: 'Municípios da Região', val: qtdMunicipiosRegiao ?? '—',               icon: PI.MAP,      iconColor: [52, 211, 153]  },
        { label: 'Estab. Região',        val: cnpjData.total_regiao_saude ?? '—',        icon: PI.SITEMAP,  iconColor: [148, 163, 184] },
        { label: 'Estab. Município',     val: cnpjData.total_municipio ?? '—',           icon: PI.BUILDING, iconColor: [167, 139, 250] },
        { label: 'Pop. Município',       val: formatPopulacao(geoData?.nu_populacao),    icon: PI.USERS,    iconColor: [96, 165, 250]  },
      ];
      ctxStats.forEach((s, i) => {
        const x = margin + i * rankColW;
        drawIcon(s.icon, x, y + 7, { size: 13, color: s.iconColor });
        const tx = x + 8;
        pdf.setFontSize(8); pdf.setFont(F, 'bold'); pdf.setTextColor(148, 163, 184);
        pdf.text(s.label, tx, y);
        pdf.setFontSize(12); pdf.setFont(F, 'bold'); pdf.setTextColor(15, 23, 42);
        pdf.text(String(s.val), tx, y + 9);
      });
      y += 20;

      // ── Mapas: Região de Saúde + Município ────────────
      if (geoData?.id_ibge7 && geoData?.sg_uf && geoStore) {
        const geoJson = geoStore.getMunicipiosGeoByUF(geoData.sg_uf);
        if (geoJson) {
          y += 14;
          const mapCardH = 122;
          const mapGap   = 4;
          const mapCardW = (contentW - mapGap) / 2;
          const munLabel = (geoData.no_municipio ?? cnpjData.municipio ?? '').toUpperCase();
          const uf       = (geoData.sg_uf ?? cnpjData.uf ?? '').toUpperCase();
          const regLabel = (geoData.no_regiao_saude ?? '').toUpperCase();

          // IDs dos municípios da região de saúde
          const regionIds = (geoStore.localidades ?? [])
            .filter(l => String(l.id_regiao_saude) === String(geoData.id_regiao_saude) && l.sg_uf === geoData.sg_uf)
            .map(l => l.id_ibge7);

          const mapCards = [
            { x: margin,                    title: `REGIÃO — ${regLabel}`,   type: 'region' },
            { x: margin + mapCardW + mapGap, title: `MUNICÍPIO — ${munLabel}`, type: 'mun'  },
          ];

          for (const card of mapCards) {
            // Fundo
            pdf.setFillColor(248, 250, 252);
            pdf.roundedRect(card.x, y, mapCardW, mapCardH, 3, 3, 'F');
            pdf.setDrawColor(226, 232, 240);
            pdf.setLineWidth(0.3);
            pdf.roundedRect(card.x, y, mapCardW, mapCardH, 3, 3, 'S');

            // Título
            pdf.setFontSize(7); pdf.setFont(F, 'bold'); pdf.setTextColor(148, 163, 184);
            pdf.text(card.title, card.x + mapCardW / 2, y + 6, { align: 'center' });

            // Badge UF
            if (uf) {
              const bW = 10, bH = 5.5, bX = card.x + mapCardW - bW - 3, bY = y + 2;
              pdf.setFillColor(30, 41, 59);
              pdf.roundedRect(bX, bY, bW, bH, 1.5, 1.5, 'F');
              pdf.setFontSize(6); pdf.setFont(F, 'bold'); pdf.setTextColor(203, 213, 225);
              pdf.text(uf, bX + bW / 2, bY + 3.7, { align: 'center' });
            }

            // Mapa
            if (card.type === 'region') {
              drawRegionMap(pdf, geoJson, regionIds, geoData.id_ibge7, resultadoMunicipios,
                card.x + 3, y + 9, mapCardW - 6, mapCardH - 13);
            } else {
              const munPerc    = resultadoMunicipios?.find(m => String(m.id_ibge7) === String(geoData.id_ibge7))?.percValSemComp ?? capPerc;
              const polyFill   = getRiskRgbByPerc(munPerc);
              const polyStroke = getRiskBorderRgbByPerc(munPerc);
              // Reserva rodapé para o badge de % sem comp
              drawMunicipalityPolygon(pdf, geoJson, geoData.id_ibge7,
                card.x + 3, y + 9, mapCardW - 6, mapCardH - 22,
                polyFill, polyStroke);
              // Badge % sem comprovação do município
              const badgeY = y + mapCardH - 14;
              pdf.setFillColor(248, 250, 252);
              pdf.setDrawColor(226, 232, 240);
              pdf.setLineWidth(0.3);
              pdf.roundedRect(card.x + 4, badgeY, mapCardW - 8, 11, 1.5, 1.5, 'FD');
              pdf.setFontSize(6); pdf.setFont(F, 'semibold'); pdf.setTextColor(71, 85, 105);
              pdf.text('% SEM COMPROVAÇÃO NO MUNICÍPIO', card.x + mapCardW / 2, badgeY + 4, { align: 'center' });
              pdf.setFontSize(8); pdf.setFont(F, 'bold'); pdf.setTextColor(...polyStroke);
              pdf.text(munPerc.toFixed(1) + '%', card.x + mapCardW / 2, badgeY + 9, { align: 'center' });
            }
          }
        }
      }

      // ── PÁGINA 2 — Movimentação Financeira ───────────────────
      pdf.addPage();
      pageHeader('Movimentação Financeira', cnpjData.razao_social, PI.CHART_LINE);

      const semestres = reportData.evolucao.semestres;

      let y2 = 26;

      const chartH = 70;
      drawFinancialChart(pdf, semestres, margin, y2, contentW, chartH, F);
      y2 += chartH + 6;

      y2 += 5;
      y2 = sectionTitle('DETALHAMENTO SEMESTRAL', y2, [30, 41, 59], PI.TABLE);

      const semRows = semestres.map((s, i) => {
        let tendencia = '-';
        if (i > 0) {
          const diff = s.pct_irregular - semestres[i - 1].pct_irregular;
          tendencia = diff > 0 ? `+${diff.toFixed(1)}pp` : diff < 0 ? `-${Math.abs(diff).toFixed(1)}pp` : `0.0pp`;
        }
        return [
          s.semestre,
          formatCurrencyFull(s.total),
          formatCurrencyFull(s.regular),
          formatCurrencyFull(s.irregular),
          s.pct_irregular.toFixed(1) + '%',
          tendencia,
        ];
      });

      const totalReg = semestres.reduce((a, s) => a + s.regular, 0);
      const totalIrr = semestres.reduce((a, s) => a + s.irregular, 0);
      const totalAll = semestres.reduce((a, s) => a + s.total, 0);

      autoTable(pdf, {
        startY: y2 + 2,
        head: [['Semestre', 'Total Movimentado', 'Total Comprovado', 'Sem Comprovação', '% Sem Comp', 'Tendência']],
        body: semRows,
        foot: [['TOTAL', formatCurrencyFull(totalAll), formatCurrencyFull(totalReg), formatCurrencyFull(totalIrr), '', '']],
        margin: { left: margin, right: margin },
        styles: { fontSize: 8, cellPadding: 3, font: F, fontStyle: 'semibold' },
        headStyles: { fillColor: [15, 23, 42], textColor: 255, fontStyle: 'bold', fontSize: 7.5 },
        footStyles: { fillColor: [240, 240, 240], textColor: [30, 30, 30], fontStyle: 'bold' },
        alternateRowStyles: { fillColor: [249, 250, 251] },
        columnStyles: {
          0: {},
          1: { halign: 'right' },
          2: { halign: 'right' },
          3: { halign: 'right', textColor: [239, 68, 68] },
          4: { halign: 'center' },
          5: { halign: 'center' },
        },
        didParseCell: (data) => {
          if (data.section === 'head' || data.section === 'foot') {
            const hAligns = ['left', 'right', 'right', 'right', 'center', 'center'];
            data.cell.styles.halign = hAligns[data.column.index];
          }
          if (data.section === 'body' && data.column.index === 5) {
            const v = data.cell.raw;
            if (v?.startsWith('+')) data.cell.styles.textColor = [239, 68, 68];
            else if (v?.startsWith('-')) data.cell.styles.textColor = [16, 185, 129];
            else data.cell.styles.textColor = [150, 150, 150];
          }
          if (data.section === 'body' && data.column.index === 4) {
            const pct = parseFloat(data.cell.raw);
            if (pct > 5) data.cell.styles.textColor = [239, 68, 68];
            else         data.cell.styles.textColor = [30, 41, 59];
          }
        },
      });

      // ── PÁGINA 3 — Indicadores ────────────────────────────
      const indicadores    = reportData.indicadores.indicadores;
      const pontosCriticos = reportData.indicadores.pontosCriticos;

      pdf.addPage();
      pageHeader('Indicadores de Risco', cnpjData.razao_social, PI.SHIELD);

      let y3 = 26;

      // Resumo para Auditoria
      if (pontosCriticos.length) {
        y3 += 5;
        y3 = sectionTitle(`RESUMO PARA AUDITORIA — ${pontosCriticos.length} INDICADOR(ES) CRITICO(S)`, y3, [185, 28, 28], PI.EXCLAMATION_TRIANGLE);

        autoTable(pdf, {
          startY: y3 + 2,
          head: [['Indicador', 'Risco Regional', 'Valor Farmácia', 'Mediana Regional']],
          body: pontosCriticos.map((p) => [
            p.label,
            p.riscoReg != null ? p.riscoReg.toFixed(1) + 'x acima' : '—',
            fmtVal(p.valor, p.formato, formatCurrencyFull),
            fmtVal(p.medReg, p.formato, formatCurrencyFull),
          ]),
          margin: { left: margin, right: margin },
          headStyles: { fillColor: [127, 29, 29], textColor: 255, fontStyle: 'bold', fontSize: 7.5 },
          styles: { fontSize: 8, cellPadding: 3, fillColor: [255, 245, 245] },
          alternateRowStyles: { fillColor: [255, 245, 245] },
          columnStyles: {
            1: { halign: 'center', textColor: [239, 68, 68], fontStyle: 'bold' },
            2: { halign: 'right' },
            3: { halign: 'right', textColor: [100, 100, 100] },
          },
          didParseCell: (data) => {
            if (data.section === 'head') {
              const hAligns = ['left', 'center', 'right', 'right'];
              data.cell.styles.halign = hAligns[data.column.index];
            }
          },
        });

        y3 = pdf.lastAutoTable.finalY + 8;
      }

      y3 += 5;
      y3 = sectionTitle('INDICADORES DE RISCO POR GRUPO', y3, [30, 41, 59], PI.CHART_BAR);

      const indRows = [];
      for (const grupo of INDICATOR_GROUPS) {
        indRows.push([{ content: grupo.label, colSpan: 9, styles: { fontStyle: 'bold', fillColor: [241, 245, 249], textColor: [30, 41, 59], fontSize: 7.5 } }]);
        for (const ind of grupo.indicators) {
          const d = indicadores[ind.key];
          if (!d || d.valor == null) {
            indRows.push([ind.label, { content: 'SEM DADOS', colSpan: 8, styles: { halign: 'center', textColor: [150, 150, 150] } }]);
            continue;
          }
          const status = getOfficialStatus(ind.key, d);
          indRows.push([
            ind.label,
            fmtVal(d.valor,   ind.formato, formatCurrencyFull),
            fmtVal(d.med_reg, ind.formato, formatCurrencyFull),
            fmtVal(d.med_uf,  ind.formato, formatCurrencyFull),
            fmtVal(d.med_br,  ind.formato, formatCurrencyFull),
            fmtRisco(d.risco_reg),
            fmtRisco(d.risco_uf),
            fmtRisco(d.risco_br),
            status,
          ]);
        }
      }

      autoTable(pdf, {
        startY: y3 + 2,
        head: [['Indicador', 'Farmácia', 'Mediana\nRegião ★', 'Mediana\nUF', 'Mediana\nBR', 'Risco\nRegião ★', 'Risco\nUF', 'Risco\nBR', 'Status']],
        body: indRows,
        margin: { left: margin, right: margin },
        styles: { fontSize: 7.5, cellPadding: 2.5, overflow: 'linebreak', font: F, fontStyle: 'semibold' },
        headStyles: { fillColor: [30, 41, 59], textColor: 255, fontStyle: 'bold', fontSize: 7 },
        alternateRowStyles: { fillColor: [255, 255, 255] },
        columnStyles: {
          0: { cellWidth: 48 },
          1: { halign: 'right' },
          2: { halign: 'right' },
          3: { halign: 'right', textColor: [120, 120, 120] },
          4: { halign: 'right', textColor: [120, 120, 120] },
          5: { halign: 'center' },
          6: { halign: 'center', textColor: [120, 120, 120] },
          7: { halign: 'center', textColor: [120, 120, 120] },
          8: { halign: 'center' },
        },
        didParseCell: (data) => {
          const col = data.column.index;
          const hAligns = ['left', 'right', 'right', 'right', 'right', 'center', 'center', 'center', 'center'];

          if (data.section === 'head') {
            data.cell.styles.halign = hAligns[col];
            // Destaque no header das colunas de referência (Mediana Região e Risco Região)
            if (col === 2 || col === 5) {
              data.cell.styles.fillColor = [49, 60, 80];   // slate ligeiramente mais claro
              data.cell.styles.textColor = [199, 210, 254]; // indigo-200 — destaque suave
            }
          }

          if (data.section === 'body') {
            // Fundo levíssimo nas colunas de referência para o body
            if (col === 2 || col === 5) {
              data.cell.styles.fillColor = [248, 248, 255]; // off-white azulado
            }
          }

          if (data.section !== 'body') return;
          const raw = data.cell.raw;
          if (typeof raw !== 'string') return;

          if (col === 8) {
            if      (raw === 'CRÍTICO') { data.cell.styles.textColor = [239, 68, 68];  data.cell.styles.fillColor = [255, 240, 240]; }
            else if (raw === 'ATENÇÃO') { data.cell.styles.textColor = [180, 83,  9];  data.cell.styles.fillColor = [255, 250, 235]; }
            else if (raw === 'NORMAL')  { data.cell.styles.textColor = [5,  150, 105]; }
          }
        },
      });

      // ── PÁGINA 4 — Prescritores ────────────────────────────
      const crmPayload = reportData.crm;
      const summary = crmPayload.summary || {};
      const top20 = (crmPayload.crmsInteresse || []).slice(0, 20);
      const kpis = crmPayload.kpis || {};
      const crmIndicator = reportData.indicadores.indicadores.crms_irregulares;
      if (crmIndicator?.valor == null || crmIndicator?.valor_financeiro == null) {
        throw new Error('Relatório PDF sem percentual ou valor financeiro do indicador de CRMs irregulares.');
      }

      if (top20.length > 0) {
          pdf.addPage();
          pageHeader('Análise de CRMs e Prescritores', cnpjData.razao_social, PI.USERS);

          let y4 = 26;

          // KPI Cards
          // Paleta alinhada com variáveis CSS do sistema:
          // red    = --risk-high/critical (#ef4444)
          // orange = --risk-medium        (#f97316)
          // green  = --risk-low           (#10b981)
          const red    = [239, 68,  68 ];
          const orange = [249, 115, 22 ];
          const green  = [16,  185, 129];
          const summary2 = summary;
          const crmCards = [
            { label: 'TOP 1 CRM - VOLUME R$',         val: fmtVal(kpis.concentracaoTop1, 'pct', formatCurrencyFull),  color: kpis.concentracaoTop1        > 40 ? red : kpis.concentracaoTop1 > 20 ? red : green,    subtitle: `CRM: ${summary2.id_top1_prescritor || 'ND'} · ${formatCurrencyFull(kpis.valorTop1 || 0)}` },
            { label: 'TOP 5 CRMs - VOLUME R$',         val: fmtVal(kpis.concentracaoTop5, 'pct', formatCurrencyFull),  color: kpis.concentracaoTop5        > 70 ? red : kpis.concentracaoTop5 > 50 ? red : green,    subtitle: formatCurrencyFull(kpis.valorTop5 || 0) },
            { label: 'LANÇAMENTOS EM SEQUÊNCIA',        val: String(kpis.qtdLancamentosAgrupados  || 0),               color: kpis.qtdLancamentosAgrupados  > 0  ? red    : green, subtitle: 'Muitas autorizações em intervalo curto' },
            { label: '>30 PRESCRIÇÕES/DIA NESTE CNPJ', val: String(kpis.qtdPrescrIntensivaLocal   || 0),               color: kpis.qtdPrescrIntensivaLocal  > 0  ? red    : green, subtitle: 'Na unidade local' },
            { label: '>30 PRESCRIÇÕES/DIA NO BRASIL',  val: String(kpis.qtdPrescrIntensivaOcultos || 0),               color: kpis.qtdPrescrIntensivaOcultos > 0 ? red    : green, subtitle: 'Soma de todo o Brasil' },
            { label: 'MULTI-FARMÁCIA',                  val: String(kpis.qtdMultiFarmacia          || 0),               color: kpis.qtdMultiFarmacia         > 0  ? red    : green, subtitle: 'CRMs com registro em > 70 farmácias distintas' },
            { label: 'CRMs NO DETALHAMENTO',            val: String(kpis.totalIrregularesCfm       || 0),               color: crmIndicator.valor_financeiro > 0 ? red : green, subtitle: `${formatCurrencyFull(crmIndicator.valor_financeiro)} (${Number(crmIndicator.valor).toFixed(2).replace('.', ',')}%) no indicador` },
            { label: 'DISTÂNCIA (>400KM)',              val: String(kpis.qtdAcima400km             || 0),               color: kpis.qtdAcima400km            > 0  ? orange : green, subtitle: 'Prescrições em locais distantes' },
          ];

          const cW = (contentW - 9) / 4;
          const cH = 20;
          crmCards.forEach((c, i) => {
            const row = Math.floor(i / 4);
            const col = i % 4;
            const x = margin + col * (cW + 3);
            const cy = y4 + row * (cH + 3);

            pdf.setFillColor(248, 250, 252);
            pdf.roundedRect(x, cy, cW, cH, 2, 2, 'F');
            pdf.setFillColor(...c.color);
            pdf.roundedRect(x, cy, 2, cH, 1, 1, 'F');
            pdf.setFontSize(7); pdf.setFont(F, 'bold'); pdf.setTextColor(100, 116, 139);
            const labelLines = pdf.splitTextToSize(c.label.toUpperCase(), cW - 8);
            pdf.text(labelLines.slice(0, 2), x + 4, cy + 6);
            if (c.subtitle) {
              pdf.setFontSize(5.5); pdf.setFont(F, 'normal'); pdf.setTextColor(148, 163, 184);
              pdf.text(c.subtitle, x + 4, cy + 12);
            }
            pdf.setFontSize(12); pdf.setFont(F, 'bold'); pdf.setTextColor(...c.color);
            pdf.text(c.val, x + 4, cy + 17);
          });

          y4 += (cH * 2 + 20);
          y4 = sectionTitle('CRMs DE INTERESSE - DETALHAMENTO', y4, [30, 41, 59], PI.TABLE);

          const crmRows = top20.map(m => {
            const issues = [];
            if (m.flag_robo > 0) issues.push('>30 presc/dia local');
            if (m.flag_robo_oculto > 0 && !m.flag_robo) issues.push('>30 presc/dia Brasil');
            if (m.alerta_concentracao_unico_crm) issues.push('Muitas autorizações em sequência pelo mesmo CRM');
            if (m.alerta_concentracao_multiplos_crms) issues.push('Muitas autorizações em sequência por alguns CRMs');
            if (m.flag_crm_invalido > 0) issues.push('CRM não localizado');
            if (m.flag_prescricao_antes_registro > 0) issues.push('CRM Irregular (Autor. antes do Registro)');
            if (Number(m.nu_estabelecimentos) === 1) issues.push('Exclusivo do CNPJ');
            if (m.alerta5_geografico) issues.push('Distância >400km');

            let alertStr = issues.length > 0 ? issues.join('\n') : 'Regular';
            return [
              m.id_medico,
              alertStr,
              formatNumberFull(m.nu_prescricoes),
              `${formatNumberFull(m.nu_estabelecimentos)}\n${formatCompetenciaMes(m.competencia_nu_estabelecimentos, `CRM ${m.id_medico}`)}`,
              formatCurrencyFull(m.vl_total_prescricoes),
              fmtVal(m.pct_participacao, 'pct', formatCurrencyFull),
              formatNumberFull(m.nu_prescricoes_dia)
            ];
          });

          autoTable(pdf, {
            startY: y4 + 2,
            head: [['Médico/CRM', 'Alertas', 'Nº Aut.', 'Nº Estab.', 'Valor autorizado', 'Part.', 'Presc./dia']],
            body: crmRows,
            margin: { left: margin, right: margin },
            styles: { fontSize: 7, cellPadding: 3, overflow: 'linebreak', font: F, fontStyle: 'normal' },
            headStyles: { fillColor: [30, 41, 59], textColor: 255, fontStyle: 'bold', fontSize: 7.5 },
            alternateRowStyles: { fillColor: [249, 250, 251] },
            columnStyles: {
              0: { cellWidth: 24 },
              1: { cellWidth: 56 },
              2: { halign: 'right' },
              3: { halign: 'center' },
              4: { halign: 'right', textColor: [30, 41, 59] },
              5: { halign: 'center' },
              6: { halign: 'center' }
            },
            didParseCell: (data) => {
              if (data.section === 'head') {
                const hAligns = ['left', 'left', 'right', 'center', 'right', 'center', 'center'];
                data.cell.styles.halign = hAligns[data.column.index];
              }
              if (data.section === 'body') {
                const hasAlert = data.row.cells[1]?.raw !== 'Regular';
                if (data.column.index === 1 && hasAlert) {
                  data.cell.styles.textColor = [239, 68, 68];
                  data.cell.styles.fontStyle = 'normal';
                }
                if (data.column.index === 1 && !hasAlert) {
                  data.cell.styles.fontStyle = 'normal';
                  data.cell.styles.textColor = [150, 150, 150];
                }
                if (data.column.index === 4 && hasAlert) {
                  data.cell.styles.textColor = [239, 68, 68];
                  data.cell.styles.fillColor = [255, 240, 240];
                }
              }
            }
          });

          const crmLegendItems = [];
          if (top20.some(m => m.alerta_concentracao_unico_crm)) {
            crmLegendItems.push({
              label: 'Muitas autorizações em sequência pelo mesmo CRM',
              description: 'Este alerta é gerado quando o mesmo CRM registra várias autorizações de venda em uma janela de tempo muito curta. A análise considera a quantidade de autorizações, a duração do intervalo e a taxa de autorizações por hora. Quanto maior a quantidade registrada em menor tempo, mais atípico é o padrão observado.',
            });
          }
          if (top20.some(m => m.alerta_concentracao_multiplos_crms)) {
            crmLegendItems.push({
              label: 'Muitas autorizações em sequência por alguns CRMs',
              description: 'Este alerta é gerado quando, em uma mesma janela de tempo muito curta, a farmácia registra várias autorizações de venda distribuídas entre diferentes CRMs. A análise considera o volume total de autorizações, a quantidade de CRMs envolvidos, a duração do intervalo e a taxa de autorizações por hora.',
            });
          }
          if (top20.some(m => m.flag_crm_invalido > 0)) {
            crmLegendItems.push({
              label: 'CRM não localizado',
              description: 'O número informado não foi localizado na base oficial consultada do Conselho Federal de Medicina. O resultado deve ser confrontado com outras fontes oficiais, como o RMS, quando aplicável.',
            });
          }
          if (top20.some(m => m.flag_prescricao_antes_registro > 0)) {
            crmLegendItems.push({
              label: 'CRM irregular',
              description: 'A data da autorização de venda é anterior à primeira inscrição do médico na UF do CRM, indicando uma incompatibilidade temporal que deve ser verificada na documentação correspondente.',
            });
          }
          crmLegendItems.push({
            label: 'Nº Estab.',
            description: 'Indica o maior número de estabelecimentos distintos em que o médico/CRM registrou autorizações de venda em uma mesma competência mensal dentro do período analisado. O mês correspondente aparece abaixo do número na tabela. Por exemplo, 20 e 03/2022 significam que aquele CRM registrou autorizações em 20 estabelecimentos distintos no mês de março de 2022. Esse número não representa o total acumulado de estabelecimentos únicos em todo o período.',
          });
          drawCrmLegend(crmLegendItems, pdf.lastAutoTable.finalY + 5);
      }

      // ── PÁGINA 5 — Falecidos ─────────────────────────────
      const falecidosPayload = reportData.falecidos;
      const falecidosSummary = falecidosPayload.summary || {};
      const agrupados = falecidosPayload.agrupados || [];

      if (agrupados.length > 0) {
        const summary = falecidosSummary;

        pdf.addPage();
        pageHeader('Vendas para Pacientes Falecidos', cnpjData.razao_social, PI.EXCLAMATION_TRIANGLE);

        let y5 = 26;

        // KPI cards — cor dinâmica alinhada com --risk-* do sistema:
        // red    = --risk-high/critical | orange = --risk-medium | green = --risk-low
        const fRed    = [239, 68,  68 ];
        const fOrange = [249, 115, 22 ];
        const fGreen  = [16,  185, 129];
        const fKpis = [
          { label: 'CPFs Distintos',       val: String(summary.cpfs_distintos),                                                  color: (summary.cpfs_distintos     || 0) > 0 ? fRed    : fGreen },
          { label: 'Núm. Autorizações',     val: String(summary.total_autorizacoes),                                              color: (summary.total_autorizacoes || 0) > 0 ? fRed    : fGreen },
          { label: 'Prejuízo Estimado',     val: formatCurrencyFull(summary.valor_total),                                         color: (summary.valor_total        || 0) > 0 ? fRed    : fGreen },
          { label: 'Média Dias Pós-Óbito',  val: `${summary.media_dias?.toFixed(1)} dias`,                                       color: (summary.media_dias         || 0) > 0 ? fRed    : fGreen },
          { label: 'Máx. Dias Pós-Óbito',  val: `${summary.max_dias} dias`,                                                      color: (summary.max_dias           || 0) > 0 ? fRed    : fGreen },
          { label: '% do Faturamento',      val: `${(summary.pct_faturamento * 100).toFixed(3)}%`,                               color: (summary.pct_faturamento    || 0) > 0 ? fOrange : fGreen },
          { label: 'CPFs Multi-CNPJ',       val: `${summary.cpfs_multi_cnpj} (${(summary.pct_multi_cnpj * 100).toFixed(1)}%)`,   color: (summary.cpfs_multi_cnpj    || 0) > 0 ? fRed    : fGreen },
        ];

        const fCols = 4;
        const fCardW = (contentW - (fCols - 1) * 3) / fCols;
        const fCardH = 18;
        let maxRow = 0;
        fKpis.forEach((k, i) => {
          const col = i % fCols;
          const row = Math.floor(i / fCols);
          const x = margin + col * (fCardW + 3);
          const fy = y5 + row * (fCardH + 3);
          maxRow = Math.max(maxRow, row);
          pdf.setFillColor(248, 250, 252);
          pdf.roundedRect(x, fy, fCardW, fCardH, 2, 2, 'F');
          pdf.setFillColor(...k.color);
          pdf.roundedRect(x, fy, 2, fCardH, 1, 1, 'F');
          pdf.setFontSize(7); pdf.setFont(F, 'bold'); pdf.setTextColor(100, 116, 139);
          pdf.text(k.label.toUpperCase(), x + 4, fy + 6);
          pdf.setFontSize(12); pdf.setFont(F, 'bold'); pdf.setTextColor(...k.color);
          pdf.text(k.val, x + 4, fy + 14);
        });
        y5 += (maxRow + 1) * (fCardH + 3) + 7;

        y5 = sectionTitle('DETALHAMENTO POR FALECIDO', y5, [30, 41, 59], PI.TABLE);

        const falRows = [];
        for (const g of agrupados) {
          // linha de grupo
          falRows.push([{
            content: `${g.cpf}  —  ${g.nome}  |  ${g.transacoes.length} autorização(ões)  |  Óbito: ${g.dt_obito}`,
            colSpan: 7,
            styles: { fontStyle: 'semibold', fillColor: [241, 245, 249], textColor: [30, 41, 59], fontSize: 7 },
          }]);
          for (const t of g.transacoes) {
            const dias = t.dias_apos_obito ?? 0;
            const diasColor = dias > 365 ? [239, 68, 68] : dias > 30 ? [249, 115, 22] : [234, 179, 8];
            falRows.push([
              t.num_autorizacao ?? '—',
              formatarData(t.dt_obito),
              formatarData(t.data_autorizacao),
              `${g.municipio ?? ''}/${g.uf ?? ''}`,
              t.fonte_obito ?? '—',
              formatCurrencyFull(t.valor_total_autorizacao),
              { content: `${dias}d`, styles: { halign: 'center', textColor: diasColor, fontStyle: 'bold' } },
            ]);
          }
        }

        autoTable(pdf, {
          startY: y5 + 2,
          head: [['Nº Autorização', 'Dt. Óbito', 'Dt. Venda', 'Município/UF', 'Fonte Óbito', 'Valor (R$)', 'Dias Pós-Óbito']],
          body: falRows,
          margin: { left: margin, right: margin },
          styles: { fontSize: 7, cellPadding: 2.5, overflow: 'linebreak', font: F, fontStyle: 'normal' },
          headStyles: { fillColor: [30, 41, 59], textColor: 255, fontStyle: 'bold', fontSize: 7 },
          alternateRowStyles: { fillColor: [255, 255, 255] },
          columnStyles: {
            0: { cellWidth: 30 },
            5: { halign: 'right', fontStyle: 'bold', textColor: [239, 68, 68] },
            6: { halign: 'center' },
          },
        });
      }

      // ── Salvar ────────────────────────────────────────────
      const safeName = (cnpjData.razao_social ?? cnpj).replace(/[^a-zA-Z0-9]/g, '_').slice(0, 30);
      const filename = `Sentinela_${safeName}_${new Date().toISOString().slice(0, 10)}.pdf`;
      return await saveBlobOrDownload(pdf.output('blob'), filename);

    } catch (err) {
      console.error('[usePdfExport] Critical failure during PDF generation:', err);
      throw err;
    } finally {
      isExporting.value = false;
    }
  }

  return { isExporting, exportCnpjPdf };
}
