import { beforeEach, describe, expect, it, vi } from 'vitest';

const mocks = vi.hoisted(() => {
  const instances = [];
  const autoTable = vi.fn();
  const saveBlobOrDownload = vi.fn();
  const get = vi.fn();
  class MockPdf {
    constructor() {
      this.pages = 1;
      this.lastAutoTable = { finalY: 60 };
      this.internal = {
        pageSize: { getWidth: () => 210, getHeight: () => 297 },
        getNumberOfPages: () => this.pages,
      };
      for (const name of [
        'addFileToVFS', 'addFont', 'addImage', 'addPage', 'line', 'rect', 'roundedRect', 'setDrawColor',
        'setFillColor', 'setLineDashPattern', 'setLineWidth', 'setPage', 'setTextColor', 'text',
      ]) this[name] = vi.fn();
      this.addPage = vi.fn(() => { this.pages += 1; });
      this.splitTextToSize = vi.fn((value) => [String(value)]);
      this.getTextWidth = vi.fn((value) => String(value).length);
      this.output = vi.fn(() => new Blob(['pdf']));
      this.setFont = vi.fn();
      this.setFontSize = vi.fn();
      instances.push(this);
    }
  }
  return { MockPdf, instances, autoTable, saveBlobOrDownload, get };
});

vi.mock('jspdf', () => ({ default: mocks.MockPdf }));
vi.mock('jspdf-autotable', () => ({ default: (...args) => mocks.autoTable(...args) }));
vi.mock('axios', () => ({ default: { get: (...args) => mocks.get(...args) } }));
vi.mock('@/utils/download', () => ({ saveBlobOrDownload: (...args) => mocks.saveBlobOrDownload(...args) }));
vi.mock('@/composables/usePdfExport', () => ({
  loadFontsInto: vi.fn(async () => ({ inter: false, primeicons: false })),
}));

import { buscarEvidenciasCompletas, gerarPdfHistoricoCrm } from '@/composables/usePdfCrmHistorico';
import { CRM_EVIDENCIA_ABAS } from '@/config/crmEvidencias';

const FMT = {
  numero: (n) => String(n),
  data: (d) => d,
  decimal: (v, casas = 2) => Number(v).toFixed(casas),
  pct: (v) => `${v}%`,
  cnpj: (v) => v,
  titulo: (v) => v,
};

function linhaUnico(i) {
  return {
    cnpj: `0000000000${i}`, razao_social: `Farmácia ${i}`, municipio: 'X', uf: 'SC',
    dt: '2024-01-10', hr_janela: 9, dt_ini_hora: '2024-01-10T09:00:00', dt_fim_hora: '2024-01-10T09:30:00',
    nu_autorizacoes: 5, nu_minutos: 30, taxa_hora: 10, id_severidade: 3,
  };
}

function respostaEvidencias(tipo, total, linhasPorPagina, pagina) {
  const aba = CRM_EVIDENCIA_ABAS.find((a) => a.tipo === tipo);
  const linhas = Array.from({ length: linhasPorPagina }, (_, i) => linhaUnico(i + (pagina - 1) * 100));
  return {
    data: {
      tipo,
      id_cnpj: null,
      id_ibge7: null,
      total,
      page: pagina,
      page_size: 100,
      resumo_unico: { qtd_alertas: 3, qtd_dias: 2, qtd_farmacias: 1, pior_severidade: 3, por_severidade: {} },
      resumo_multiplos: { qtd_alertas: 0, qtd_dias: 0, qtd_farmacias: 0, pior_severidade: null, por_severidade: {} },
      resumo_distancia: { qtd_pares: 0, qtd_meses: 0, maior_distancia_km: null },
      [aba.linhas]: linhas,
    },
  };
}

function snapshotBase(extra = {}) {
  return {
    medico: { titulo: 'Médico X', registro: 'CRM 37105/SC', meta: 'CRM 37105/SC', maisMedicos: null, localizadoCfm: true },
    filtros: { periodo: 'Período da análise', municipio: null, farmacia: null },
    kpis: [{ label: 'Prescrições', value: '10', detail: '3 dias com prescrição' }],
    pontosAtencao: [{ codigo: 'x', titulo: 'Autorizações em sequência', detalhe: 'Detalhe' }],
    farmacias: [{
      id_cnpj: 1, nome: 'Farmácia A', cnpj: '00000000000001', municipio: 'Cidade', uf: 'SC',
      situacao_rf: 'Ativa', conexao_ativa: true, nu_prescricoes: 10, percentual_prescricoes: 100,
    }],
    atuacao: new Map([[1, { periodo: '01/2024 – 02/2024', meses: '2 meses', total: 2, divisores: [], barras: [{ x: 0, altura: 0.5 }] }]]),
    linhaDoTempo: null,
    calor: null,
    capa: { prescricoes: 10, mesesAltaIntensidade: 2, farmacias: 1, pontosAtencao: 1 },
    evidencias: {
      idMedico: '37105/SC', dataInicio: '2024-01-01', dataFim: '2024-02-29', idCnpj: null, idIbge7: null, temEvidencias: false,
    },
    fmt: FMT,
    ...extra,
  };
}

describe('buscarEvidenciasCompletas', () => {
  beforeEach(() => {
    mocks.get.mockReset();
    mocks.saveBlobOrDownload.mockReset();
    mocks.autoTable.mockReset();
    mocks.saveBlobOrDownload.mockResolvedValue({ desktop: false, filename: 'x.pdf' });
  });

  it('percorre todas as páginas de cada aba até fechar o total', async () => {
    mocks.get.mockImplementation(async (_url, { params }) => {
      if (params.tipo === 'unico') return respostaEvidencias('unico', 150, params.page === 1 ? 100 : 50, params.page);
      return respostaEvidencias(params.tipo, 0, 0, 1);
    });

    const resultado = await buscarEvidenciasCompletas({
      idMedico: '37105/SC', dataInicio: '2024-01-01', dataFim: '2024-02-29', idCnpj: null, idIbge7: null,
    });

    const chamadasUnico = mocks.get.mock.calls.filter(([, o]) => o.params.tipo === 'unico');
    expect(chamadasUnico.map(([, o]) => o.params.page)).toEqual([1, 2]);
    expect(chamadasUnico[0][1].params.page_size).toBe(100);
    expect(resultado.unico.linhas).toHaveLength(150);
    expect(resultado.multiplos.linhas).toHaveLength(0);
    expect(resultado.unico.resumo.qtd_alertas).toBe(3);
  });

  it('falha quando a resposta não é da aba pedida', async () => {
    mocks.get.mockResolvedValue(respostaEvidencias('multiplos', 1, 1, 1));
    await expect(buscarEvidenciasCompletas({ idMedico: '37105/SC' }))
      .rejects.toThrow('Contrato inválido em crm-medico-evidencias (aba unico).');
  });

  it('falha quando uma página vem vazia antes do total', async () => {
    mocks.get.mockResolvedValue(respostaEvidencias('unico', 150, 0, 1));
    await expect(buscarEvidenciasCompletas({ idMedico: '37105/SC' }))
      .rejects.toThrow('Evidências do CRM incompletas na aba unico: 0 de 150 linhas.');
  });
});

describe('gerarPdfHistoricoCrm', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response(new Blob(['png'], { type: 'image/png' }), { status: 200 })));
    mocks.get.mockReset();
    mocks.saveBlobOrDownload.mockReset();
    mocks.autoTable.mockReset();
    mocks.saveBlobOrDownload.mockResolvedValue({ desktop: true, filename: 'Sentinela_Historico_CRM_37105_SC_2026-11-16.pdf', path: 'C:/notas/x.pdf' });
  });

  it('gera sem buscar evidências quando o CRM não tem evidências e salva o PDF', async () => {
    const resultado = await gerarPdfHistoricoCrm(snapshotBase());

    expect(mocks.get).not.toHaveBeenCalled();
    expect(mocks.autoTable).toHaveBeenCalledTimes(1); // só a tabela de farmácias
    const [blob, nome] = mocks.saveBlobOrDownload.mock.calls[0];
    expect(blob).toBeInstanceOf(Blob);
    expect(nome).toMatch(/^Sentinela_Historico_CRM_37105_SC_\d{4}-\d{2}-\d{2}\.pdf$/);
    expect(resultado).toEqual({ desktop: true, filename: 'Sentinela_Historico_CRM_37105_SC_2026-11-16.pdf', path: 'C:/notas/x.pdf' });
  });

  it('inclui linha do tempo, mapa de calor e as evidências completas', async () => {
    mocks.get.mockImplementation(async (_url, { params }) => (
      params.tipo === 'unico' ? respostaEvidencias('unico', 2, 2, 1) : respostaEvidencias(params.tipo, 0, 0, 1)
    ));
    const linhaDoTempo = {
      meses: [202401, 202402],
      porMes: new Map([
        [202401, { taxa_prescricoes_dia: 2, p95_taxa_dia: 1.5, alta_intensidade: true, nu_prescricoes: 4, qtd_dias_com_prescricao: 2 }],
        [202402, { taxa_prescricoes_dia: 1, p95_taxa_dia: 1.5, alta_intensidade: false, nu_prescricoes: 2, qtd_dias_com_prescricao: 2 }],
      ]),
    };
    const calor = {
      meses: [202401, 202402],
      linhas: [{ id_cnpj: 1, nome: 'Farmácia A' }],
      pontos: [[0, 0, 2, 4, 2], [1, 0, 1, 2, 2]],
      minimo: 1,
      maximo: 2,
      omitidas: 0,
    };

    await gerarPdfHistoricoCrm(snapshotBase({
      linhaDoTempo,
      calor,
      evidencias: { ...snapshotBase().evidencias, temEvidencias: true },
    }));

    // Farmácias + 3 abas de evidência (a aba "unico" tem linhas; as outras, só o aviso).
    expect(mocks.autoTable).toHaveBeenCalledTimes(2);
    expect(mocks.saveBlobOrDownload).toHaveBeenCalledTimes(1);
  });

  it('falha de forma explícita quando o logo da CGU não carrega', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response(null, { status: 404 })));
    await expect(gerarPdfHistoricoCrm(snapshotBase()))
      .rejects.toThrow('Logo da CGU indisponível (HTTP 404).');
    expect(mocks.saveBlobOrDownload).not.toHaveBeenCalled();
  });

  it('falha de forma explícita quando a capa vem sem os números', async () => {
    await expect(gerarPdfHistoricoCrm(snapshotBase({ capa: { prescricoes: 1 } })))
      .rejects.toThrow('Capa do histórico sem mesesAltaIntensidade.');
  });

  it('falha de forma explícita quando o snapshot vem incompleto', async () => {
    await expect(gerarPdfHistoricoCrm({ evidencias: {} }))
      .rejects.toThrow('Dados do histórico do CRM incompletos para o PDF.');
    expect(mocks.saveBlobOrDownload).not.toHaveBeenCalled();
  });
});
