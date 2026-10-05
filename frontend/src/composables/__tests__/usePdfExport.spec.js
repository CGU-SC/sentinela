import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { INDICATOR_GROUPS } from '@/config/riskConfig';

const pdfMocks = vi.hoisted(() => {
  const instances = [];
  const autoTable = vi.fn();
  const saveBlobOrDownload = vi.fn();
  class MockPdf {
    constructor(options) {
      this.options = options;
      this.currentFont = { fontName: 'helvetica', fontStyle: 'normal' };
      this.currentFontSize = 10;
      this.internal = { pageSize: { getWidth: () => 210, getHeight: () => 297 } };
      this.lastAutoTable = { finalY: 100 };
      for (const name of [
        'addFileToVFS', 'addFont', 'addImage', 'addPage', 'circle', 'line', 'lines',
        'rect', 'roundedRect', 'setDrawColor', 'setFillColor', 'setLineJoin',
        'setLineWidth', 'setTextColor', 'text',
      ]) this[name] = vi.fn();
      this.getFont = vi.fn(() => this.currentFont);
      this.getFontSize = vi.fn(() => this.currentFontSize);
      this.getTextWidth = vi.fn((value) => String(value).length);
      this.setFont = vi.fn((fontName, fontStyle) => { this.currentFont = { fontName, fontStyle }; });
      this.setFontSize = vi.fn((size) => { this.currentFontSize = size; });
      this.splitTextToSize = vi.fn((value) => [String(value)]);
      this.output = vi.fn(() => new Blob(['pdf']));
      instances.push(this);
    }
  }
  return { MockPdf, instances, autoTable, saveBlobOrDownload };
});

vi.mock('jspdf', () => ({ default: pdfMocks.MockPdf }));
vi.mock('jspdf-autotable', () => ({ default: (...args) => pdfMocks.autoTable(...args) }));
vi.mock('@/utils/download', () => ({ saveBlobOrDownload: (...args) => pdfMocks.saveBlobOrDownload(...args) }));

import { usePdfExport } from '../usePdfExport';

describe('usePdfExport', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.spyOn(console, 'error').mockImplementation(() => {});
    pdfMocks.instances.length = 0;
    pdfMocks.saveBlobOrDownload.mockResolvedValue({ ok: true, path: 'sentinela.pdf' });
    pdfMocks.autoTable.mockImplementation((pdf, options) => {
      const parse = options.didParseCell;
      const cell = (section, index, raw, status = 'body') => {
        if (!parse) return;
        const cells = [];
        cells[1] = { raw: status };
        const data = { section, column: { index }, cell: { raw, styles: {} }, row: { cells } };
        parse(data);
      };
      const columns = options.head?.[0]?.length;
      if (columns === 6 && parse) {
        cell('head', 0, 'Semestre');
        cell('foot', 5, 'TOTAL');
        for (const value of ['+2.0pp', '-3.0pp', '0.0pp']) cell('body', 5, value);
        cell('body', 4, '6.0%');
        cell('body', 4, '2.0%');
      } else if (columns === 4 && parse) {
        for (let index = 0; index < columns; index += 1) cell('head', index, 'Header');
      } else if (columns === 9 && parse) {
        for (let index = 0; index < columns; index += 1) cell('head', index, 'Header');
        cell('body', 2, 12);
        cell('body', 5, '1.0x');
        for (const status of ['CRÍTICO', 'ATENÇÃO', 'NORMAL', 'OUTRO']) cell('body', 8, status);
      } else if (columns === 7 && parse) {
        for (let index = 0; index < columns; index += 1) cell('head', index, 'Header');
        cell('body', 1, 'Alerta', 'Alerta');
        cell('body', 1, 'Regular', 'Regular');
        cell('body', 4, 'R$ 10,00', 'Alerta');
        cell('body', 4, 'R$ 10,00', 'Regular');
      }
      pdf.lastAutoTable = { finalY: 280 };
    });
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  function successfulFetch(url) {
    if (url.startsWith('/fonts/')) {
      const bytes = new Uint8Array(8193);
      return Promise.resolve({ ok: true, arrayBuffer: async () => bytes.buffer });
    }
    return Promise.resolve({ ok: true, blob: async () => new Blob(['logo']) });
  }

  function buildReportData({ noCriticalPoints = false } = {}) {
    const indicators = {};
    for (const group of INDICATOR_GROUPS) {
      for (const indicator of group.indicators) {
        indicators[indicator.key] = {
          valor: indicator.key === 'teto' ? null : 2.5,
          med_reg: indicator.key === 'ticket_medio' ? null : 1.5,
          med_uf: 2,
          med_br: 3,
          risco_reg: 1.25,
          risco_uf: null,
          risco_br: 2,
          status: indicator.key === 'percentual_nao_comprovacao' ? 'CRITICO'
            : indicator.key === 'falecidos' ? 'ATENÇÃO' : 'NORMAL',
          valor_financeiro: indicator.key === 'crms_irregulares' ? 125 : 0,
        };
      }
    }
    return {
      evolucao: { semestres: [
        { semestre: '2022-S1', total: 100, regular: 80, irregular: 20, pct_irregular: 20 },
        { semestre: '2022-S2', total: 120, regular: 100, irregular: 20, pct_irregular: 10 },
        { semestre: '2023-S1', total: 0, regular: 0, irregular: 0, pct_irregular: 25 },
        { semestre: '2023-S2', total: 60, regular: 45, irregular: 15, pct_irregular: 25 },
      ] },
      indicadores: {
        indicadores: indicators,
        pontosCriticos: noCriticalPoints ? [] : [
          { key: 'pct', label: 'Percentual', formato: 'pct', riscoReg: 1.25, valor: 12.345, medReg: 8 },
          { key: 'pct3', label: 'Falecidos', formato: 'pct3', riscoReg: null, valor: 0.125, medReg: null },
          { key: 'val', label: 'Ticket', formato: 'val', riscoReg: 2.1, valor: 30, medReg: 20 },
          { key: 'decimal', label: 'Decimal', formato: 'dec', riscoReg: 1, valor: 1.236, medReg: 1 },
        ],
      },
      crm: {
        summary: {
          id_top1_prescritor: '123/SC', pct_concentracao_top1: 30, pct_concentracao_top5: 60,
          qtd_alertas_cnpj_multiplo: 2, qtd_dias_alertas_cnpj_multiplo: 1,
        },
        crmsInteresse: [
          {
            id_medico: 'CRM1', nu_estabelecimentos: 80, competencia_nu_estabelecimentos: '202401',
            vl_total_prescricoes: 1000, nu_prescricoes: 12, pct_participacao: 75, nu_prescricoes_dia: 80,
            flag_robo: 1, flag_robo_oculto: 1, flag_crm_exclusivo: 1, alerta_concentracao_unico_crm: true,
            alerta_concentracao_multiplos_crms: true, flag_crm_invalido: 1, flag_prescricao_antes_registro: 1,
            alerta5_geografico: true,
          },
          {
            id_medico: 'CRM2', nu_estabelecimentos: 12, competencia_nu_estabelecimentos: '202312',
            vl_total_prescricoes: 250, nu_prescricoes: 4, pct_participacao: 15, nu_prescricoes_dia: 2,
            flag_robo: 0, flag_robo_oculto: 1, flag_crm_exclusivo: 0, alerta_concentracao_unico_crm: false,
            alerta_concentracao_multiplos_crms: false, flag_crm_invalido: 0, flag_prescricao_antes_registro: 0,
            alerta5_geografico: false,
          },
          {
            id_medico: 'CRM3', nu_estabelecimentos: 1, competencia_nu_estabelecimentos: '202311',
            vl_total_prescricoes: 50, nu_prescricoes: 1, pct_participacao: 5, nu_prescricoes_dia: 1,
            flag_robo: 0, flag_robo_oculto: 0, flag_crm_exclusivo: 0, alerta_concentracao_unico_crm: false,
            alerta_concentracao_multiplos_crms: false, flag_crm_invalido: 0, flag_prescricao_antes_registro: 0,
            alerta5_geografico: false,
          },
          {
            id_medico: 'CRM4', nu_estabelecimentos: 8, competencia_nu_estabelecimentos: '202310',
            vl_total_prescricoes: 25, nu_prescricoes: 1, pct_participacao: 2, nu_prescricoes_dia: 0.5,
            flag_robo: 0, flag_robo_oculto: 0, flag_crm_exclusivo: 0, alerta_concentracao_unico_crm: false,
            alerta_concentracao_multiplos_crms: false, flag_crm_invalido: 0, flag_prescricao_antes_registro: 0,
            alerta5_geografico: false,
          },
        ],
        kpis: {
          concentracaoTop1: 30, concentracaoTop5: 60, valorTop1: 1000, valorTop5: 1300,
          qtdLancamentosAgrupados: 1, qtdPrescrIntensivaLocal: 1, qtdPrescrIntensivaOcultos: 0,
          qtdMultiFarmacia: 1, totalIrregularesCfm: 2, qtdAcima400km: 1,
        },
      },
      falecidos: {
        summary: {
          cpfs_distintos: 1, total_autorizacoes: 3, valor_total: 60, media_dias: 160,
          max_dias: 400, pct_faturamento: 0.02, cpfs_multi_cnpj: 1, pct_multi_cnpj: 1,
        },
        agrupados: [{
          cpf: '12345678900', nome: 'João Silva', municipio: 'São Paulo', uf: 'SP', dt_obito: '01/01/2020',
          transacoes: [
            { dias_apos_obito: 400, num_autorizacao: 'A1', dt_obito: '2020-01-01', data_autorizacao: '2021-02-05', fonte_obito: 'SIM', valor_total_autorizacao: 30 },
            { dias_apos_obito: 50, num_autorizacao: 'A2', dt_obito: '2020-01-01', data_autorizacao: '2020-02-20', fonte_obito: null, valor_total_autorizacao: 20 },
            { dias_apos_obito: null, dt_obito: null, data_autorizacao: null, valor_total_autorizacao: 10 },
          ],
        }],
      },
    };
  }

  function buildInput(overrides = {}) {
    const targetId = 3550308;
    const neighborId = 3550407;
    const square = (offset = 0) => [[
      [offset, 0], [offset + 1, 0], [offset + 1, 1], [offset, 1], [offset, 0],
    ]];
    const geoJson = { type: 'FeatureCollection', features: [
      { type: 'Feature', properties: { id: targetId }, geometry: { type: 'Polygon', coordinates: square(0) } },
      { type: 'Feature', properties: { id: neighborId }, geometry: { type: 'MultiPolygon', coordinates: [square(2), square(4)] } },
      { type: 'Feature', properties: { id: 3550506 }, geometry: { type: 'Point', coordinates: [6, 1] } },
    ] };
    return {
      cnpjData: {
        razao_social: 'Farmácia Central', municipio: 'São Paulo', uf: 'SP', percValSemComp: 25,
        score_risco_final: 2.5, classificacao_risco: 'Crítico', valSemComp: 1200, totalMov: 5000,
        rank_nacional: 1, total_nacional: 100, rank_uf: null, total_uf: null,
        rank_regiao_saude: 5, total_regiao_saude: 20, rank_municipio: 7, total_municipio: 15,
      },
      geoData: {
        id_ibge7: targetId, id_regiao_saude: 3550001, sg_uf: 'SP', no_municipio: 'São Paulo',
        no_regiao_saude: 'Região Metropolitana', nu_populacao: 1200000,
      },
      cadastro: { tipo_logradouro: 'Rua', logradouro: 'Central', numero: '10', bairro: 'Centro', cep: '01000000' },
      cnpj: '12345678000199', qtdMunicipiosRegiao: 39,
      reportData: buildReportData(),
      geoStore: {
        getMunicipiosGeoByUF: vi.fn(() => geoJson),
        localidades: [
          { id_regiao_saude: 3550001, sg_uf: 'SP', id_ibge7: targetId },
          { id_regiao_saude: 3550001, sg_uf: 'SP', id_ibge7: neighborId },
          { id_regiao_saude: 3550001, sg_uf: 'SP', id_ibge7: 3550506 },
        ],
      },
      resultadoMunicipios: [
        { id_ibge7: targetId, percValSemComp: 25 },
        { id_ibge7: neighborId, percValSemComp: 8 },
      ],
      formatCurrencyFull: (value) => `R$ ${Number(value).toFixed(2)}`,
      formatNumberFull: (value) => Number(value).toLocaleString('pt-BR'),
      formatarData: (value) => value ? `data:${value}` : '—',
      ...overrides,
    };
  }

  it('rejeita um relatório sem o contrato obrigatório e encerra o estado de exportação', async () => {
    const report = usePdfExport();
    vi.spyOn(console, 'error').mockImplementation(() => {});
    await expect(report.exportCnpjPdf({ reportData: {} }))
      .rejects.toThrow('Payload do relatorio PDF sem evolucao.semestres.');
    expect(report.isExporting.value).toBe(false);
  });

  it('exige o payload do relatório', async () => {
    const report = usePdfExport();
    vi.spyOn(console, 'error').mockImplementation(() => {});
    await expect(report.exportCnpjPdf({ reportData: null }))
      .rejects.toThrow('Payload do relatorio PDF ausente.');
    expect(report.isExporting.value).toBe(false);
  });

  it('gera as páginas financeiras, territoriais, de indicadores, CRMs e falecidos', async () => {
    vi.stubGlobal('fetch', vi.fn(successfulFetch));
    const report = usePdfExport();
    const input = buildInput();
    input.reportData.crm.kpis.qtdPrescrIntensivaOcultos = 1;
    const result = await report.exportCnpjPdf(input);

    expect(result).toEqual({ ok: true, path: 'sentinela.pdf' });
    expect(report.isExporting.value).toBe(false);
    expect(pdfMocks.instances).toHaveLength(1);
    expect(pdfMocks.instances[0].addImage).toHaveBeenCalledOnce();
    expect(pdfMocks.instances[0].addPage).toHaveBeenCalled();
    expect(pdfMocks.autoTable).toHaveBeenCalledTimes(5);
    expect(pdfMocks.saveBlobOrDownload).toHaveBeenCalledWith(expect.any(Blob), expect.stringMatching(/^Sentinela_Farm_cia_Central_\d{4}-\d{2}-\d{2}\.pdf$/));
  });

  it('usa fontes padrão e encerra a geração sem mapas, itens de alerta ou pontos críticos', async () => {
    vi.spyOn(console, 'warn').mockImplementation(() => {});
    vi.stubGlobal('fetch', vi.fn(async (url) => ({ ok: false, status: 404 })));
    const input = buildInput({
      geoStore: null,
      qtdMunicipiosRegiao: null,
      resultadoMunicipios: null,
      geoData: { nu_populacao: null },
      reportData: {
        ...buildReportData({ noCriticalPoints: true }),
        crm: { summary: {}, crmsInteresse: [], kpis: {} },
        falecidos: { summary: {}, agrupados: [] },
      },
    });
    const report = usePdfExport();
    await expect(report.exportCnpjPdf(input)).resolves.toEqual({ ok: true, path: 'sentinela.pdf' });
    expect(report.isExporting.value).toBe(false);
    expect(pdfMocks.instances[0].addImage).not.toHaveBeenCalled();
    expect(pdfMocks.autoTable).toHaveBeenCalledTimes(2);
    expect(console.warn).toHaveBeenCalledTimes(2);
  });

  it('desenha polígonos multiparte, lida com risco ausente e com percentual acima da escala', async () => {
    vi.stubGlobal('fetch', vi.fn(successfulFetch));
    const input = buildInput();
    input.cnpjData.percValSemComp = 5;
    input.cnpjData.score_risco_final = null;
    input.geoData.nu_populacao = 10000;
    input.geoStore.localidades = [{ id_regiao_saude: 3550001, sg_uf: 'SP', id_ibge7: 3550308 }];
    input.geoStore.getMunicipiosGeoByUF.mockReturnValue({
      type: 'FeatureCollection',
      features: [{
        type: 'Feature',
        properties: { id: 3550308 },
        geometry: { type: 'MultiPolygon', coordinates: [
          [[[2, 3], [2, 3], [2, 3]]],
          [[[2, 3], [2, 3], [2, 3]]],
        ] },
      }],
    });
    input.resultadoMunicipios = [{ id_ibge7: 3550308, percValSemComp: null }];
    await expect(usePdfExport().exportCnpjPdf(input)).resolves.toEqual({ ok: true, path: 'sentinela.pdf' });
    expect(pdfMocks.instances[0].lines).toHaveBeenCalled();
  });

  it('usa escala baixa, rótulos cadastrais ausentes e retorna cedo quando o GeoJSON não tem feições', async () => {
    vi.stubGlobal('fetch', vi.fn(successfulFetch));
    const input = buildInput();
    input.cnpjData.percValSemComp = null;
    input.cnpjData.score_risco_final = null;
    input.cnpjData.classificacao_risco = null;
    input.cnpjData.total_regiao_saude = null;
    input.cnpjData.total_municipio = null;
    input.geoData = { id_ibge7: 3550308, id_regiao_saude: 3550001, sg_uf: 'SP', nu_populacao: 500 };
    input.cadastro = {};
    input.qtdMunicipiosRegiao = null;
    input.geoStore.localidades = [{ id_regiao_saude: 3550001, sg_uf: 'SP', id_ibge7: 3550308 }];
    input.geoStore.getMunicipiosGeoByUF.mockReturnValue({ type: 'FeatureCollection', features: [] });
    input.resultadoMunicipios = null;
    input.reportData.crm.summary.id_top1_prescritor = null;
    Object.assign(input.reportData.crm.kpis, {
      concentracaoTop1: 10,
      concentracaoTop5: 40,
      qtdLancamentosAgrupados: 0,
      qtdPrescrIntensivaLocal: 0,
      qtdPrescrIntensivaOcultos: 0,
      qtdMultiFarmacia: 0,
      totalIrregularesCfm: 0,
      qtdAcima400km: 0,
    });
    input.reportData.indicadores.indicadores.crms_irregulares.valor_financeiro = 0;
    Object.assign(input.reportData.falecidos.summary, {
      cpfs_distintos: 0, total_autorizacoes: 0, valor_total: 0, media_dias: 0,
      max_dias: 0, pct_faturamento: 0, cpfs_multi_cnpj: 0, pct_multi_cnpj: 0,
    });

    await expect(usePdfExport().exportCnpjPdf(input)).resolves.toEqual({ ok: true, path: 'sentinela.pdf' });
  });

  it('trata campos cadastrais nulos, região sem municípios e geometria não poligonal', async () => {
    vi.stubGlobal('fetch', vi.fn(successfulFetch));
    const input = buildInput();
    input.cnpjData.razao_social = null;
    input.cnpjData.municipio = null;
    input.cnpjData.uf = null;
    input.cnpjData.percValSemComp = Number.NaN;
    input.cnpjData.classificacao_risco = null;
    input.geoData = {
      id_ibge7: 3550308,
      id_regiao_saude: 3550001,
      sg_uf: 'SP',
      no_municipio: null,
      no_regiao_saude: null,
      nu_populacao: null,
    };
    input.cadastro = {
      tipo_logradouro: null,
      logradouro: 'Central',
      numero: 'None',
      bairro: 'None',
      cep: 'None',
    };
    input.geoStore.localidades = [
      { id_regiao_saude: 3550001, sg_uf: 'RJ', id_ibge7: 3550308 },
      { id_regiao_saude: 9999999, sg_uf: 'SP', id_ibge7: 3550407 },
    ];
    input.geoStore.getMunicipiosGeoByUF.mockReturnValue({
      type: 'FeatureCollection',
      features: [{
        type: 'Feature',
        properties: { id: 3550308 },
        geometry: { type: 'Point', coordinates: [0, 0] },
      }],
    });
    input.reportData.evolucao.semestres.push({
      semestre: null,
      total: null,
      regular: null,
      irregular: null,
      pct_irregular: 0,
    });
    input.resultadoMunicipios = [{ id_ibge7: 3550308, percValSemComp: Number.NaN }];
    Object.assign(input.reportData.crm.kpis, { concentracaoTop1: 45, concentracaoTop5: 75 });
    input.reportData.falecidos.agrupados[0].municipio = null;
    input.reportData.falecidos.agrupados[0].uf = null;

    await expect(usePdfExport().exportCnpjPdf(input)).resolves.toEqual({ ok: true, path: 'sentinela.pdf' });
    expect(pdfMocks.instances[0].lines).not.toHaveBeenCalled();
    expect(pdfMocks.saveBlobOrDownload.mock.calls[0][1]).toMatch(/^Sentinela_12345678000199_\d{4}-\d{2}-\d{2}\.pdf$/);
  });

  it('continua a exportação quando a busca de fontes e imagem rejeita', async () => {
    vi.spyOn(console, 'warn').mockImplementation(() => {});
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('offline')));

    await expect(usePdfExport().exportCnpjPdf(buildInput({
      geoStore: null,
      reportData: {
        ...buildReportData({ noCriticalPoints: true }),
        crm: { summary: {}, crmsInteresse: [], kpis: {} },
        falecidos: { summary: {}, agrupados: [] },
      },
    }))).resolves.toEqual({ ok: true, path: 'sentinela.pdf' });
    expect(console.warn).toHaveBeenCalledTimes(2);
    expect(pdfMocks.saveBlobOrDownload).toHaveBeenCalledOnce();
  });

  it('aceita mapas sem GeoJSON/localidades e KPIs CRM zerados', async () => {
    vi.stubGlobal('fetch', vi.fn(successfulFetch));
    const input = buildInput({
      geoStore: {
        getMunicipiosGeoByUF: vi.fn(() => ({})),
      },
    });
    input.reportData.crm.summary.id_top1_prescritor = null;
    Object.assign(input.reportData.crm.kpis, {
      concentracaoTop1: 20,
      concentracaoTop5: 50,
      valorTop1: 0,
      valorTop5: 0,
      qtdLancamentosAgrupados: 0,
      qtdPrescrIntensivaLocal: 0,
      qtdPrescrIntensivaOcultos: 0,
      qtdMultiFarmacia: 0,
      totalIrregularesCfm: 0,
      qtdAcima400km: 0,
    });

    await expect(usePdfExport().exportCnpjPdf(input)).resolves.toEqual({ ok: true, path: 'sentinela.pdf' });
    expect(input.geoStore.getMunicipiosGeoByUF).toHaveBeenCalledWith('SP');
    expect(pdfMocks.saveBlobOrDownload).toHaveBeenCalledOnce();
  });

  it('reseta o estado quando o salvamento falha depois de gerar o PDF', async () => {
    vi.stubGlobal('fetch', vi.fn(successfulFetch));
    vi.spyOn(console, 'error').mockImplementation(() => {});
    pdfMocks.saveBlobOrDownload.mockRejectedValueOnce(new Error('Falha no destino'));
    const report = usePdfExport();

    await expect(report.exportCnpjPdf(buildInput())).rejects.toThrow('Falha no destino');
    expect(report.isExporting.value).toBe(false);
    expect(console.error).toHaveBeenCalledWith(
      '[usePdfExport] Critical failure during PDF generation:',
      expect.any(Error),
    );
  });

  it('falha visivelmente diante de contratos incompletos e competência CRM inválida', async () => {
    vi.stubGlobal('fetch', vi.fn(successfulFetch));
    const report = usePdfExport();
    const missingIndicators = buildInput({ reportData: { ...buildReportData(), indicadores: {} } });
    await expect(report.exportCnpjPdf(missingIndicators)).rejects.toThrow('Payload do relatorio PDF sem indicadores.indicadores.');
    expect(report.isExporting.value).toBe(false);

    const missingFalecidos = buildInput({ reportData: { ...buildReportData(), falecidos: {} } });
    await expect(report.exportCnpjPdf(missingFalecidos)).rejects.toThrow('Payload do relatorio PDF sem dados de falecidos.');

    const missingCrm = buildInput({ reportData: { ...buildReportData(), crm: {} } });
    await expect(report.exportCnpjPdf(missingCrm)).rejects.toThrow('Payload do relatorio PDF sem dados de CRM.');

    const missingOfficialStatus = buildInput();
    missingOfficialStatus.reportData.indicadores.indicadores.percentual_nao_comprovacao.status = null;
    await expect(report.exportCnpjPdf(missingOfficialStatus))
      .rejects.toThrow('Indicador percentual_nao_comprovacao sem status oficial retornado pela API.');

    const invalidMonth = buildInput();
    invalidMonth.reportData.crm.crmsInteresse[0].competencia_nu_estabelecimentos = '202413';
    await expect(report.exportCnpjPdf(invalidMonth)).rejects.toThrow('Competência mensal inválida em CRM CRM1.');

    const invalidCompetence = buildInput();
    invalidCompetence.reportData.crm.crmsInteresse[0].competencia_nu_estabelecimentos = 'data';
    await expect(report.exportCnpjPdf(invalidCompetence)).rejects.toThrow('Competência mensal inválida em CRM CRM1.');

    const missingCrmFinancials = buildInput();
    missingCrmFinancials.reportData.indicadores.indicadores.crms_irregulares.valor_financeiro = null;
    await expect(report.exportCnpjPdf(missingCrmFinancials))
      .rejects.toThrow('Relatório PDF sem percentual ou valor financeiro do indicador de CRMs irregulares.');
    expect(report.isExporting.value).toBe(false);
  });
});
