import jsPDF from 'jspdf';
import autoTable from 'jspdf-autotable';
import axios from 'axios';
import { API_ENDPOINTS } from '@/config/api';
import {
  CRM_FARMACIA_SERIES,
  CRM_HEATMAP_TAXA_RAMP,
  CRM_SEVERIDADE_SEQUENCIA_CORES,
  DATA_NEUTRAL,
} from '@/config/colors';
import {
  CRM_EVIDENCIA_ABAS,
  CRM_EVIDENCIA_ORDENACAO_PADRAO,
  CRM_EVIDENCIA_SEVERIDADE_LABEL,
} from '@/config/crmEvidencias';
import { saveBlobOrDownload } from '@/utils/download';
import { loadFontsInto } from '@/composables/usePdfExport';
import { CRM_ATUACAO_TETO_P95 } from '@/config/analysisTooltipConfig';

/**
 * Relatório PDF do "Histórico do CRM" (modal de /analises), em tema escuro e no
 * padrão visual do Relatório PDF da farmácia (jsPDF + jspdf-autotable, vetorial).
 *
 * O modal entrega o próprio estado já calculado (KPIs, pontos de atenção, tabela
 * de farmácias, linha do tempo, mapa de calor). As evidências são buscadas
 * integralmente aqui, aba por aba e página por página, com os mesmos parâmetros
 * do painel, porque o painel mostra só uma página por vez.
 */

// Máximo de linhas por página aceito por crm-medico-evidencias (le=100 no backend).
const PAGINA_EVIDENCIAS = 100;
const MAX_PAGINAS_EVIDENCIAS = 500;

const hexToRgb = (hex) => [
  parseInt(hex.slice(1, 3), 16),
  parseInt(hex.slice(3, 5), 16),
  parseInt(hex.slice(5, 7), 16),
];

/** Logo da CGU para a capa. Sem logo não há capa: a falha aparece, sem fallback silencioso. */
async function buscarLogoCgu() {
  const res = await fetch(`/img/logo_cgu.png?v=${Date.now()}`);
  if (!res.ok) throw new Error(`Logo da CGU indisponível (HTTP ${res.status}).`);
  const blob = await res.blob();
  return await new Promise((resolve, reject) => {
    const leitor = new FileReader();
    leitor.onload = () => resolve(leitor.result);
    leitor.onerror = reject;
    leitor.readAsDataURL(blob);
  });
}

// Paleta do tema escuro (mesma família do relatório da farmácia).
const BG = [15, 23, 42];
const CARD = [30, 41, 59];
const CARD_ALT = [24, 34, 52];
const BORDER = [51, 65, 85];
const TEXT = [226, 232, 240];
const MUTED = [148, 163, 184];
const DIM = [100, 116, 139];
const ACCENT = [99, 102, 241];
// Cores de dados vêm da configuração do gráfico, como no modal.
const AZUL = hexToRgb(CRM_FARMACIA_SERIES.dark[0]);
const NEUTRO = hexToRgb(DATA_NEUTRAL.dark.strong);
const RAMP = CRM_HEATMAP_TAXA_RAMP.dark.map(hexToRgb);
const ALERTA = RAMP[4];
const VERDE = [16, 185, 129];

const pageW = 210;
const pageH = 297;
const margin = 14;
const contentW = pageW - margin * 2;
const TOPO_CONTEUDO = 24;
const RODAPE_LIMITE = pageH - 14;

const hora = (iso) => (iso ? String(iso).slice(11, 16) : '—');
const competenciaTexto = (comp) => `${String(comp % 100).padStart(2, '0')}/${Math.floor(comp / 100)}`;

/**
 * Busca todas as linhas das três abas de evidências com os filtros do modal.
 * Sem limite silencioso: se a paginação não fechar com o total, falha visivelmente.
 */
export async function buscarEvidenciasCompletas({ idMedico, dataInicio, dataFim, idCnpj, idIbge7 }) {
  const base = { id_medico: idMedico };
  if (dataInicio) base.data_inicio = dataInicio;
  if (dataFim) base.data_fim = dataFim;
  if (idCnpj != null) base.id_cnpj = idCnpj;
  if (idIbge7 != null) base.id_ibge7 = idIbge7;

  const resultado = {};
  for (const aba of CRM_EVIDENCIA_ABAS) {
    const ordem = CRM_EVIDENCIA_ORDENACAO_PADRAO[aba.tipo];
    const linhas = [];
    let resumo = null;
    for (let pagina = 1; ; pagina += 1) {
      if (pagina > MAX_PAGINAS_EVIDENCIAS) {
        throw new Error(`Evidências do CRM acima do limite de paginação (aba ${aba.tipo}).`);
      }
      const { data } = await axios.get(API_ENDPOINTS.analyticsCrmMedicoEvidencias, {
        params: {
          ...base,
          tipo: aba.tipo,
          sort_field: ordem.campo,
          sort_order: ordem.ordem,
          page: pagina,
          page_size: PAGINA_EVIDENCIAS,
        },
      });
      if (
        data.tipo !== aba.tipo
        || (data.id_cnpj ?? null) !== (idCnpj ?? null)
        || (data.id_ibge7 ?? null) !== (idIbge7 ?? null)
        || !Array.isArray(data[aba.linhas])
        || !Number.isInteger(data.total)
      ) {
        throw new Error(`Contrato inválido em crm-medico-evidencias (aba ${aba.tipo}).`);
      }
      resumo = data[aba.resumo];
      const pagLinhas = data[aba.linhas];
      linhas.push(...pagLinhas);
      if (linhas.length >= data.total) break;
      if (!pagLinhas.length) {
        throw new Error(`Evidências do CRM incompletas na aba ${aba.tipo}: ${linhas.length} de ${data.total} linhas.`);
      }
    }
    resultado[aba.tipo] = { resumo, linhas };
  }
  return resultado;
}

/**
 * Gera o PDF do histórico do CRM e o salva (ou baixa, no navegador).
 *
 * @param {object} snapshot Estado já calculado pelo modal (ver CrmHistoricoDialog.vue, exportarPdf).
 * @returns {Promise<object>} Resultado de saveBlobOrDownload ({ desktop, filename, path }).
 */
export async function gerarPdfHistoricoCrm(snapshot) {
  if (!snapshot?.evidencias || !snapshot.capa || !Array.isArray(snapshot.farmacias) || !Array.isArray(snapshot.kpis)) {
    throw new Error('Dados do histórico do CRM incompletos para o PDF.');
  }
  const { medico, filtros, kpis, pontosAtencao, farmacias, atuacao, linhaDoTempo, calor, fmt, evidencias, capa } = snapshot;
  for (const campo of ['prescricoes', 'mesesAltaIntensidade', 'farmacias', 'pontosAtencao']) {
    if (!Number.isFinite(capa[campo])) throw new Error(`Capa do histórico sem ${campo}.`);
  }

  const evidenciasCompletas = evidencias.temEvidencias
    ? await buscarEvidenciasCompletas(evidencias)
    : null;

  const logoDataUrl = await buscarLogoCgu();
  const pdf = new jsPDF({ orientation: 'p', unit: 'mm', format: 'a4' });
  const { inter: hasInter } = await loadFontsInto(pdf);
  const F = hasInter ? 'inter' : 'helvetica';

  const paintCapa = (logo) => {
    pdf.setFillColor(...BG);
    pdf.rect(0, 0, pageW, pageH, 'F');
    pdf.setFillColor(...ACCENT);
    pdf.rect(0, 0, 4, pageH, 'F');
    // Logo da CGU, proporção 700x800 (7:8), como na capa do relatório da farmácia.
    const logoW = 66;
    const logoH = (logoW * 800) / 700;
    pdf.addImage(logo, 'PNG', (pageW - logoW) / 2, 18, logoW, logoH);
    let cy = 18 + logoH + 12;
    pdf.setFont(F, 'bold');
    pdf.setFontSize(26);
    pdf.setTextColor(203, 213, 225);
    pdf.text('SENTINELA', margin + 8, cy);
    const larguraSentinela = pdf.getTextWidth('SENTINELA');
    pdf.setFont(F, 'normal');
    pdf.setFontSize(11);
    pdf.setTextColor(...MUTED);
    pdf.text('/ Sistema de Auditoria Contínua', margin + 8 + larguraSentinela + 3, cy);
    cy += 9;
    pdf.setFont(F, 'bold');
    pdf.setFontSize(14);
    pdf.setTextColor(...MUTED);
    pdf.text('Programa Farmácia Popular do Brasil — PFPB', margin + 8, cy);
    cy += 14;
    pdf.setFontSize(18);
    pdf.setTextColor(...ACCENT);
    pdf.text('Análise de CRM', margin + 8, cy);
    cy += 7;
    pdf.setFont(F, 'normal');
    pdf.setFontSize(10);
    pdf.setTextColor(...MUTED);
    pdf.text('Relatório de atuação em farmácias do Programa Farmácia Popular', margin + 8, cy);
    cy += 12;

    // Card com identificação, filtros e números-resumo.
    const cardX = margin + 8;
    const cardW = contentW - 16;
    const textoX = cardX + 8;
    const textoW = cardW - 16;
    const nomeLinhas = pdf.splitTextToSize(medico.titulo, textoW).slice(0, 2);
    const metaLinhas = pdf.splitTextToSize(medico.meta, textoW);
    // Município e farmácia só aparecem quando há filtro aplicado.
    const linhasFiltro = [`Período: ${filtros.periodo}`];
    if (filtros.municipio != null) linhasFiltro.push(`Município: ${filtros.municipio}`);
    if (filtros.farmacia != null) linhasFiltro.push(`Farmácia: ${filtros.farmacia}`);
    const alerta = capa.pontosAtencao > 0;
    const corBarra = alerta ? ALERTA : VERDE;
    const cardH = 9 + nomeLinhas.length * 6.5 + 3 + metaLinhas.length * 4.2 + 4
      + linhasFiltro.length * 4.2 + 6 + 4 + 17 + 6;
    pdf.setFillColor(...CARD);
    pdf.roundedRect(cardX, cy, cardW, cardH, 3, 3, 'F');
    pdf.setFillColor(...corBarra);
    pdf.roundedRect(cardX, cy, 3.5, cardH, 2, 2, 'F');

    let yy = cy + 9;
    pdf.setFont(F, 'bold');
    pdf.setFontSize(14);
    pdf.setTextColor(...TEXT);
    pdf.text(nomeLinhas, textoX, yy);
    yy += nomeLinhas.length * 6.5 + 3;
    pdf.setFont(F, 'normal');
    pdf.setFontSize(8.5);
    pdf.setTextColor(...MUTED);
    pdf.text(metaLinhas, textoX, yy);
    yy += metaLinhas.length * 4.2 + 4;
    pdf.setFontSize(8);
    linhasFiltro.forEach((linha) => {
      pdf.text(linha, textoX, yy);
      yy += 4.2;
    });
    yy += 2;
    pdf.setDrawColor(...BORDER);
    pdf.setLineWidth(0.25);
    pdf.line(textoX, yy, textoX + textoW, yy);
    yy += 6;

    // Números-resumo em linha: rótulo pequeno e valor em destaque.
    const numeros = [
      { rotulo: 'PRESCRIÇÕES', valor: fmt.numero(capa.prescricoes), cor: TEXT },
      { rotulo: 'MESES COM TAXA ELEVADA', valor: fmt.numero(capa.mesesAltaIntensidade), cor: TEXT },
      { rotulo: 'FARMÁCIAS', valor: fmt.numero(capa.farmacias), cor: TEXT },
      { rotulo: 'PONTOS DE ATENÇÃO', valor: fmt.numero(capa.pontosAtencao), cor: alerta ? ALERTA : TEXT },
    ];
    const colW = textoW / numeros.length;
    numeros.forEach((n, i) => {
      const nx = textoX + i * colW;
      pdf.setFont(F, 'bold');
      pdf.setFontSize(6);
      pdf.setTextColor(...MUTED);
      pdf.text(n.rotulo, nx, yy);
      pdf.setFontSize(14);
      pdf.setTextColor(...n.cor);
      pdf.text(n.valor, nx, yy + 8);
    });

    pdf.setFont(F, 'normal');
    pdf.setFontSize(9);
    pdf.setTextColor(...DIM);
    pdf.text(`Gerado em ${new Date().toLocaleString('pt-BR')}`, margin + 8, pageH - 20);
  };

  const paintPagina = () => {
    pdf.setFillColor(...BG);
    pdf.rect(0, 0, pageW, pageH, 'F');
    pdf.setFont(F, 'bold');
    pdf.setFontSize(7.5);
    pdf.setTextColor(...ACCENT);
    pdf.text('SENTINELA · PFPB · CGU', margin, 9);
    pdf.setFont(F, 'normal');
    pdf.setTextColor(...DIM);
    pdf.text(`Análise de CRM · ${medico.registro}`, pageW - margin, 9, { align: 'right' });
    pdf.setDrawColor(...BORDER);
    pdf.setLineWidth(0.2);
    pdf.line(margin, 12.5, pageW - margin, 12.5);
  };
  const novaPagina = () => {
    pdf.addPage();
    paintPagina();
    return TOPO_CONTEUDO;
  };
  const garantir = (y, altura) => (y + altura > RODAPE_LIMITE ? novaPagina() : y);
  const secao = (y, texto) => {
    const yy = garantir(y, 14);
    pdf.setFont(F, 'bold');
    pdf.setFontSize(9);
    pdf.setTextColor(...TEXT);
    pdf.text(texto.toUpperCase(), margin, yy + 3);
    pdf.setDrawColor(...BORDER);
    pdf.setLineWidth(0.2);
    pdf.line(margin, yy + 5.5, pageW - margin, yy + 5.5);
    return yy + 10;
  };
  const plural = (n, um, varios) => `${fmt.numero(n)} ${n === 1 ? um : varios}`;
  const nomeFarmaciaRelatorio = (razao, cnpj) => (razao ? fmt.titulo(razao) : fmt.cnpj(cnpj ?? ''));
  const tabelaBase = {
    margin: { top: TOPO_CONTEUDO, bottom: 14, left: margin, right: margin },
    styles: {
      font: F, fontSize: 7, cellPadding: 1.8, textColor: TEXT, fillColor: CARD,
      lineColor: BORDER, lineWidth: 0.1, overflow: 'linebreak', valign: 'middle',
    },
    headStyles: { fillColor: BORDER, textColor: TEXT, fontStyle: 'bold', fontSize: 6.8 },
    alternateRowStyles: { fillColor: CARD_ALT },
    // Em página nova criada pela tabela, repinta o fundo escuro antes das células.
    willDrawPage: (data) => { if (data.pageNumber > 1) paintPagina(); },
  };

  // ── Página 1: identificação ──────────────────────────────────────────────────
  paintCapa(logoDataUrl);
  pdf.addPage();
  paintPagina();
  let y = 22;
  pdf.setFont(F, 'bold');
  pdf.setFontSize(7.5);
  pdf.setTextColor(...ACCENT);
  pdf.text('HISTÓRICO DO CRM', margin, y);
  y += 6;
  pdf.setFontSize(18);
  pdf.setTextColor(...TEXT);
  const tituloLinhas = pdf.splitTextToSize(medico.titulo, contentW).slice(0, 2);
  pdf.text(tituloLinhas, margin, y);
  y += tituloLinhas.length * 7.5 + 2;
  pdf.setFont(F, 'normal');
  pdf.setFontSize(8.5);
  pdf.setTextColor(...MUTED);
  const metaLinhas = pdf.splitTextToSize(medico.meta, contentW);
  pdf.text(metaLinhas, margin, y);
  y += metaLinhas.length * 4.2;
  if (medico.maisMedicos) {
    pdf.setTextColor(...MUTED);
    pdf.text(`Mais Médicos · ${medico.maisMedicos}`, margin, y);
    y += 4.2;
  }
  if (!medico.localizadoCfm) {
    pdf.setTextColor(...ALERTA);
    pdf.text('Não localizado no cadastro do CFM', margin, y);
    y += 4.2;
  }
  y += 4;

  // Filtros aplicados e data de geração.
  const linhasFiltro = [
    ['Período', filtros.periodo],
    ['Município', filtros.municipio ?? 'Todos os municípios'],
    ['Farmácia', filtros.farmacia ?? 'Todas as farmácias'],
  ];
  const filtroH = 6 + linhasFiltro.length * 5 + 3;
  pdf.setFillColor(...CARD);
  pdf.roundedRect(margin, y, contentW, filtroH, 2, 2, 'F');
  pdf.setFont(F, 'bold');
  pdf.setFontSize(6.8);
  pdf.setTextColor(...MUTED);
  pdf.text('FILTROS APLICADOS NO MODAL', margin + 4, y + 5);
  linhasFiltro.forEach(([rotulo, valor], i) => {
    const ly = y + 10 + i * 5;
    pdf.setFont(F, 'bold');
    pdf.setFontSize(7.5);
    pdf.setTextColor(...MUTED);
    pdf.text(rotulo, margin + 4, ly);
    pdf.setFont(F, 'normal');
    pdf.setTextColor(...TEXT);
    pdf.text(String(valor), margin + 30, ly);
  });
  pdf.setFont(F, 'normal');
  pdf.setFontSize(6.8);
  pdf.setTextColor(...DIM);
  pdf.text(`Gerado em ${new Date().toLocaleString('pt-BR')}`, pageW - margin - 4, y + 5, { align: 'right' });
  y += filtroH + 6;

  // ── KPIs (3 por linha) ───────────────────────────────────────────────────────
  y = secao(y, 'Indicadores do CRM');
  const kpiW = (contentW - 8) / 3;
  const kpiH = 22;
  kpis.forEach((k, i) => {
    const col = i % 3;
    if (col === 0) y = garantir(y, kpiH + 3);
    const x = margin + col * (kpiW + 4);
    pdf.setFillColor(...CARD);
    pdf.roundedRect(x, y, kpiW, kpiH, 2, 2, 'F');
    pdf.setFillColor(...ACCENT);
    pdf.roundedRect(x, y, 2.5, kpiH, 1, 1, 'F');
    pdf.setFont(F, 'bold');
    pdf.setFontSize(7);
    pdf.setTextColor(...MUTED);
    pdf.text(String(k.label), x + 6, y + 6.5);
    pdf.setFontSize(12.5);
    pdf.setTextColor(...TEXT);
    pdf.text(String(k.value), x + 6, y + 14.5);
    if (k.detail) {
      pdf.setFont(F, 'normal');
      pdf.setFontSize(6.5);
      pdf.setTextColor(...MUTED);
      pdf.text(pdf.splitTextToSize(String(k.detail), kpiW - 8)[0], x + 6, y + 19.5);
    }
    if (col === 2 || i === kpis.length - 1) y += kpiH + 3;
  });
  y += 3;

  // ── Pontos de atenção ────────────────────────────────────────────────────────
  y = secao(y, 'Pontos de atenção');
  if (!pontosAtencao.length) {
    pdf.setFont(F, 'normal');
    pdf.setFontSize(8);
    pdf.setTextColor(...MUTED);
    pdf.text('Nenhum ponto de atenção no período.', margin, y);
    y += 8;
  }
  for (const p of pontosAtencao) {
    const detLinhas = pdf.splitTextToSize(String(p.detalhe ?? ''), contentW - 12);
    const h = 6 + detLinhas.length * 3.6 + 3;
    y = garantir(y, h + 2);
    pdf.setFillColor(...CARD);
    pdf.roundedRect(margin, y, contentW, h, 2, 2, 'F');
    pdf.setFillColor(...ALERTA);
    pdf.roundedRect(margin, y, 2, h, 1, 1, 'F');
    pdf.setFont(F, 'bold');
    pdf.setFontSize(8);
    pdf.setTextColor(...TEXT);
    pdf.text(String(p.titulo), margin + 6, y + 5);
    pdf.setFont(F, 'normal');
    pdf.setFontSize(7);
    pdf.setTextColor(...MUTED);
    pdf.text(detLinhas, margin + 6, y + 9.5);
    y += h + 2;
  }
  y += 3;

  // ── Farmácias onde atuou (tabela completa, com a atuação mensal desenhada) ──
  y = garantir(y, 34);
  y = secao(y, `Farmácias onde atuou · ${farmacias.length}`);
  // Legenda das barras: sem ela a coluna de atuação não se lê.
  const textoLegenda = 'Cada barra é um mês. Altura = vezes o P95 nacional do mês (teto de '
    + `${CRM_ATUACAO_TETO_P95}×). `
    + 'O ano aparece no topo da coluna e a linha vertical marca janeiro.';
  const legendaLinhas = pdf.splitTextToSize(textoLegenda, contentW);
  y = garantir(y, 8 + legendaLinhas.length * 3.2 + 6);
  pdf.setFont(F, 'normal');
  pdf.setFontSize(6.8);
  pdf.setFillColor(...NEUTRO);
  pdf.rect(margin, y + 0.8, 2.5, 2.5, 'F');
  pdf.setTextColor(...MUTED);
  pdf.text('Mês sem taxa elevada', margin + 3.5, y + 2.8);
  pdf.setFillColor(...ALERTA);
  pdf.rect(margin + 36, y + 0.8, 2.5, 2.5, 'F');
  pdf.text('Mês com taxa elevada (acima do P95 do mês)', margin + 39.5, y + 2.8);
  pdf.setFontSize(6.3);
  pdf.setTextColor(...DIM);
  pdf.text(legendaLinhas, margin, y + 6.5);
  y += 8 + legendaLinhas.length * 3.2;

  const larguras = [56, 28, 24, 74];
  const desenharAtuacao = (d) => {
    const f = farmacias[d.row.index];
    const at = f ? atuacao.get(f.id_cnpj) : undefined;
    if (!at) return;
    const { x, y: ty, width, height } = d.cell;
    const pad = 2;
    const faixaAno = 4; // topo reservado para os anos
    const areaW = width - pad * 2;
    const base = ty + height - 1.5;
    const topoBarras = ty + faixaAno;
    const areaH = base - topoBarras;
    const passo = areaW / at.total;
    const barW = Math.max(0.35, passo * 0.7);
    // Linhas de janeiro e rótulo do ano (início do eixo e cada janeiro).
    pdf.setDrawColor(...BORDER);
    pdf.setLineWidth(0.1);
    const rotulosAno = [];
    if (at.eixoInicio % 12 !== 0) rotulosAno.push({ x: 0, ano: Math.floor(at.eixoInicio / 12) });
    for (const div of at.divisores) {
      pdf.line(x + pad + div * passo, ty + 1, x + pad + div * passo, base);
      rotulosAno.push({ x: div, ano: Math.floor((at.eixoInicio + div) / 12) });
    }
    pdf.setFont(F, 'normal');
    pdf.setFontSize(5.5);
    pdf.setTextColor(...MUTED);
    for (const r of rotulosAno) pdf.text(String(r.ano), x + pad + r.x * passo + 0.6, ty + 2.8);
    // Barras: vermelho para taxa elevada, neutro para os demais meses.
    for (const b of at.barras) {
      const bh = Math.max(0.6, b.altura * areaH);
      const bx = x + pad + b.x * passo + (passo - barW) / 2;
      pdf.setFillColor(...(b.faixa ? ALERTA : NEUTRO));
      pdf.rect(bx, base - bh, barW, bh, 'F');
    }
  };
  // Barrinha de progresso: percentual de prescrições da farmácia no total do CRM.
  const desenharProgresso = (d) => {
    const f = farmacias[d.row.index];
    if (!f) return;
    const pct = Math.min(100, Math.max(0, Number(f.percentual_prescricoes) || 0));
    const { x, y: ty, width, height } = d.cell;
    const pad = 2;
    const trilhaW = width - pad * 2;
    const trilhaY = ty + height - 3.2;
    pdf.setFillColor(...BORDER);
    pdf.roundedRect(x + pad, trilhaY, trilhaW, 1.4, 0.7, 0.7, 'F');
    if (pct > 0) {
      pdf.setFillColor(...AZUL);
      pdf.roundedRect(x + pad, trilhaY, Math.max(0.6, trilhaW * (pct / 100)), 1.4, 0.7, 0.7, 'F');
    }
  };
  const corpoFarmacias = farmacias.map((f) => {
    const at = atuacao.get(f.id_cnpj);
    const municipioUf = `${f.municipio ? fmt.titulo(f.municipio) : '—'}${f.uf ? ` / ${f.uf}` : ''}`;
    return [
      `${f.nome}\n${fmt.cnpj(f.cnpj ?? '')}\n${municipioUf}`,
      `${fmt.numero(f.nu_prescricoes)} · ${fmt.pct(f.percentual_prescricoes)}`,
      at ? `${at.periodo}\n${at.meses}` : '—',
      '',
    ];
  });
  // A tabela pede espaço suficiente para pelo menos o cabeçalho e uma linha.
  y = garantir(y, 20);
  autoTable(pdf, {
    ...tabelaBase,
    startY: y,
    head: [['Farmácia / município / UF', 'Prescrições · % do total', 'Período', 'Atuação mensal']],
    body: corpoFarmacias,
    styles: { ...tabelaBase.styles, minCellHeight: 13 },
    columnStyles: Object.fromEntries(larguras.map((w, i) => [i, { cellWidth: w }])),
    didParseCell: (d) => {
      if (d.section === 'body' && d.column.index === 1) {
        d.cell.styles.halign = 'left';
        d.cell.styles.valign = 'top';
      }
    },
    didDrawCell: (d) => {
      if (d.section !== 'body') return;
      if (d.column.index === 1) desenharProgresso(d);
      if (d.column.index === 3) desenharAtuacao(d);
    },
  });
  y = pdf.lastAutoTable.finalY + 6;

  // ── Linha do tempo mensal (taxa diária, P95 nacional e meses em taxa elevada) ─
  if (linhaDoTempo) {
    const chartH = 62;
    // Reserva título + gráfico juntos: o título nunca fica sozinho no fim da página.
    y = garantir(y, chartH + 16);
    y = secao(y, 'Linha do tempo mensal · taxa diária');
    const { meses, porMes } = linhaDoTempo;
    const n = meses.length;
    let yMax = 0;
    for (const comp of meses) {
      const m = porMes.get(comp);
      if (m) yMax = Math.max(yMax, Number(m.taxa_prescricoes_dia), Number(m.p95_taxa_dia));
    }
    yMax = yMax > 0 ? yMax * 1.1 : 1;
    const px = margin + 12;
    const pw = contentW - 14;
    const py = y + 9;
    const ph = chartH - 18;
    const base = py + ph;
    const passo = pw / n;
    const barW = Math.max(0.8, passo * 0.7);

    // Legenda.
    pdf.setFont(F, 'normal');
    pdf.setFontSize(6.8);
    pdf.setFillColor(...AZUL);
    pdf.rect(margin, y + 1, 2.5, 2.5, 'F');
    pdf.setTextColor(...MUTED);
    pdf.text('Taxa diária', margin + 3.5, y + 3);
    pdf.setFillColor(...ALERTA);
    pdf.rect(margin + 28, y + 1, 2.5, 2.5, 'F');
    pdf.text('Taxa elevada (acima do P95 do mês)', margin + 31.5, y + 3);
    pdf.setDrawColor(...MUTED);
    pdf.setLineWidth(0.4);
    pdf.setLineDashPattern([1.2, 0.8], 0);
    pdf.line(margin + 98, y + 2.3, margin + 104, y + 2.3);
    pdf.setLineDashPattern([], 0);
    pdf.text('P95 nacional do mês', margin + 105.5, y + 3);

    // Eixos e rótulo do máximo.
    pdf.setDrawColor(...BORDER);
    pdf.setLineWidth(0.2);
    pdf.line(px, py, px, base);
    pdf.line(px, base, px + pw, base);
    pdf.setTextColor(...DIM);
    pdf.text(fmt.decimal(0, 1), px - 2, base, { align: 'right' });
    pdf.text(fmt.decimal(yMax / 1.1, 1), px - 2, py + 2, { align: 'right' });

    // Barras (taxa diária) e linha do P95.
    const pontosP95 = [];
    meses.forEach((comp, i) => {
      const m = porMes.get(comp);
      if (!m) return;
      const taxa = Number(m.taxa_prescricoes_dia);
      const bh = (taxa / yMax) * ph;
      pdf.setFillColor(...(m.alta_intensidade ? ALERTA : AZUL));
      pdf.rect(px + i * passo + (passo - barW) / 2, base - bh, barW, bh, 'F');
      const p95 = Number(m.p95_taxa_dia);
      pontosP95.push([px + i * passo + passo / 2, base - (p95 / yMax) * ph]);
    });
    pdf.setDrawColor(...MUTED);
    pdf.setLineWidth(0.4);
    pdf.setLineDashPattern([1.2, 0.8], 0);
    for (let i = 1; i < pontosP95.length; i += 1) {
      pdf.line(pontosP95[i - 1][0], pontosP95[i - 1][1], pontosP95[i][0], pontosP95[i][1]);
    }
    pdf.setLineDashPattern([], 0);

    // Rótulos do eixo X (a cada ~12 meses no máximo).
    const salto = Math.max(1, Math.ceil(n / 12));
    pdf.setFontSize(6);
    pdf.setTextColor(...DIM);
    meses.forEach((comp, i) => {
      if (i % salto !== 0) return;
      pdf.text(competenciaTexto(comp), px + i * passo + passo / 2, base + 4, { align: 'center' });
    });
    y += chartH + 6;
  }

  // ── Mapa de calor: farmácia x mês ────────────────────────────────────────────
  if (calor) {
    const labelW = 42;
    const nMeses = calor.meses.length;
    const cellW = (contentW - labelW) / nMeses;
    const cellH = 4;
    const gridH = calor.linhas.length * cellH;
    // Reserva título + grade + legenda juntos (mesma regra da linha do tempo).
    y = garantir(y, gridH + 24);
    y = secao(y, `Taxa diária por farmácia e mês · ${calor.linhas.length} farmácias com mais prescrições`);
    const gy = y + 6;
    const grade = calor.linhas.map(() => new Array(nMeses).fill(null));
    for (const [x, yl, taxa] of calor.pontos) grade[yl][x] = taxa;
    const amplitude = calor.maximo - calor.minimo || 1;
    const salto = Math.max(1, Math.ceil(nMeses / 14));
    pdf.setFont(F, 'normal');
    pdf.setFontSize(5.8);
    pdf.setTextColor(...DIM);
    calor.meses.forEach((comp, i) => {
      if (i % salto === 0) pdf.text(competenciaTexto(comp), margin + labelW + i * cellW, y + 3);
    });
    calor.linhas.forEach((f, r) => {
      const ry = gy + r * cellH;
      pdf.setFontSize(6.5);
      pdf.setTextColor(...MUTED);
      const nome = f.nome.length > 30 ? `${f.nome.slice(0, 29)}…` : f.nome;
      pdf.text(nome, margin, ry + 2.8);
      for (let c = 0; c < nMeses; c += 1) {
        const taxa = grade[r][c];
        if (taxa == null) {
          pdf.setFillColor(...CARD_ALT);
        } else {
          const idx = Math.min(RAMP.length - 1, Math.floor(((taxa - calor.minimo) / amplitude) * RAMP.length));
          pdf.setFillColor(...RAMP[Math.max(0, idx)]);
        }
        pdf.rect(margin + labelW + c * cellW, ry, cellW, cellH - 0.4, 'F');
      }
    });
    const legY = gy + gridH + 4;
    pdf.setFont(F, 'normal');
    pdf.setFontSize(6.8);
    pdf.setTextColor(...MUTED);
    pdf.text(
      `Escala: ${fmt.decimal(calor.minimo, 1)} a ${fmt.decimal(calor.maximo, 1)} prescrições por dia${calor.omitidas ? ` · ${calor.omitidas} farmácia(s) a mais não listadas` : ''}`,
      margin,
      legY + 2,
    );
    y = legY + 8;
  }

  // ── Evidências (as três abas, completas) ─────────────────────────────────────
  y = garantir(y, 34);
  y = secao(y, 'Evidências complementares');
  if (!evidenciasCompletas) {
    pdf.setFont(F, 'normal');
    pdf.setFontSize(8);
    pdf.setTextColor(...MUTED);
    pdf.text('Este CRM não tem evidências no período.', margin, y);
    y += 8;
  } else {
    for (const aba of CRM_EVIDENCIA_ABAS) {
      const { resumo, linhas } = evidenciasCompletas[aba.tipo];
      const resumoTexto = aba.tipo === 'distancia'
        ? [
          plural(resumo.qtd_pares, 'par', 'pares'),
          plural(resumo.qtd_meses, 'mês', 'meses'),
          resumo.maior_distancia_km == null ? null : `maior distância: ${fmt.numero(Math.round(resumo.maior_distancia_km))} km`,
        ].filter(Boolean).join(' · ')
        : [
          plural(resumo.qtd_alertas, 'janela', 'janelas'),
          plural(resumo.qtd_dias, 'dia', 'dias'),
          plural(resumo.qtd_farmacias, 'farmácia', 'farmácias'),
          resumo.pior_severidade ? `pior: ${CRM_EVIDENCIA_SEVERIDADE_LABEL[resumo.pior_severidade]}` : null,
        ].filter(Boolean).join(' · ');
      y = garantir(y, 14);
      pdf.setFont(F, 'bold');
      pdf.setFontSize(8);
      pdf.setTextColor(...TEXT);
      pdf.text(aba.label, margin, y + 3);
      pdf.setFont(F, 'normal');
      pdf.setFontSize(7);
      pdf.setTextColor(...MUTED);
      pdf.text(resumoTexto, margin, y + 7);
      y += 10;

      if (!linhas.length) {
        pdf.setFontSize(7.5);
        pdf.setTextColor(...MUTED);
        pdf.text(aba.vazio, margin, y + 2);
        y += 8;
        continue;
      }

      let head;
      let body;
      let larg;
      let colSeveridade = -1;
      if (aba.tipo === 'unico') {
        head = ['Farmácia', 'Data', 'Janela', 'Autorizações', 'Minutos', 'Taxa/h', 'Severidade'];
        larg = [52, 20, 24, 22, 18, 20, 26];
        colSeveridade = 6;
        body = linhas.map((l) => [
          nomeFarmaciaRelatorio(l.razao_social, l.cnpj),
          fmt.data(l.dt),
          `${hora(l.dt_ini_hora)}–${hora(l.dt_fim_hora)}`,
          fmt.numero(l.nu_autorizacoes),
          l.nu_minutos == null ? '—' : fmt.numero(l.nu_minutos),
          l.taxa_hora == null ? '—' : fmt.decimal(l.taxa_hora, 1),
          CRM_EVIDENCIA_SEVERIDADE_LABEL[l.id_severidade],
        ]);
      } else if (aba.tipo === 'multiplos') {
        head = ['Farmácia', 'Data', 'Janela', 'Aut. do CRM', 'Aut. total', 'CRMs', 'Minutos', 'Taxa/h', 'Severidade'];
        larg = [40, 18, 22, 20, 18, 13, 16, 15, 20];
        colSeveridade = 8;
        body = linhas.map((l) => [
          nomeFarmaciaRelatorio(l.razao_social, l.cnpj),
          fmt.data(l.dt),
          `${hora(l.dt_ini_hora)}–${hora(l.dt_fim_hora)}`,
          fmt.numero(l.nu_autorizacoes_crm),
          fmt.numero(l.nu_autorizacoes_total),
          l.nu_crms == null ? '—' : fmt.numero(l.nu_crms),
          l.nu_minutos == null ? '—' : fmt.numero(l.nu_minutos),
          l.taxa_hora == null ? '—' : fmt.decimal(l.taxa_hora, 1),
          CRM_EVIDENCIA_SEVERIDADE_LABEL[l.id_severidade],
        ]);
      } else {
        head = ['Mês', 'Farmácia A', 'Presc. A', 'Farmácia B', 'Presc. B', 'Distância (km)', 'Valor total (R$)'];
        larg = [14, 46, 16, 46, 16, 22, 22];
        body = linhas.map((l) => [
          competenciaTexto(l.competencia),
          `${nomeFarmaciaRelatorio(l.razao_social_a, l.cnpj_a)}\n${fmt.titulo(l.no_municipio_a)} / ${l.sg_uf_a}`,
          l.nu_prescricoes_a == null ? '—' : fmt.numero(l.nu_prescricoes_a),
          `${nomeFarmaciaRelatorio(l.razao_social_b, l.cnpj_b)}\n${fmt.titulo(l.no_municipio_b)} / ${l.sg_uf_b}`,
          l.nu_prescricoes_b == null ? '—' : fmt.numero(l.nu_prescricoes_b),
          fmt.decimal(l.distancia_km, 0),
          l.vl_autorizacoes_total == null ? '—' : fmt.decimal(l.vl_autorizacoes_total, 2),
        ]);
      }

      autoTable(pdf, {
        ...tabelaBase,
        startY: y,
        head: [head],
        body,
        columnStyles: Object.fromEntries(larg.map((w, i) => [i, { cellWidth: w }])),
        didParseCell: (d) => {
          if (d.section !== 'body' || d.column.index !== colSeveridade) return;
          const id = linhas[d.row.index].id_severidade;
          const cor = CRM_SEVERIDADE_SEQUENCIA_CORES[id];
          if (cor) d.cell.styles.textColor = hexToRgb(cor);
          d.cell.styles.fontStyle = 'bold';
        },
      });
      y = pdf.lastAutoTable.finalY + 8;
    }
  }

  // ── Rodapé em todas as páginas ───────────────────────────────────────────────
  const total = pdf.internal.getNumberOfPages();
  for (let i = 2; i <= total; i += 1) {
    pdf.setPage(i);
    pdf.setFont(F, 'normal');
    pdf.setFontSize(6.8);
    pdf.setTextColor(...DIM);
    pdf.text(
      'Fonte: Sentinela, a partir das autorizações do SAV/PFPB e dos cadastros de profissionais e estabelecimentos.',
      margin,
      pageH - 7,
    );
    pdf.text(`Página ${i} de ${total}`, pageW - margin, pageH - 7, { align: 'right' });
  }

  const nomeArquivo = `Sentinela_Historico_CRM_${evidencias.idMedico.replace('/', '_')}_${new Date().toISOString().slice(0, 10)}.pdf`;
  return await saveBlobOrDownload(pdf.output('blob'), nomeArquivo);
}
