import { beforeEach, describe, expect, it, vi } from 'vitest';
import axios from 'axios';
import { requestResumo } from '@/stores/analytics';
import { INDICATOR_GROUPS } from '@/config/riskConfig';
import { loadCnpjPdfReportData } from '../useCnpjPdfReportData';

vi.mock('axios', () => ({ default: { get: vi.fn() } }));
vi.mock('@/stores/analytics', () => ({ requestResumo: vi.fn() }));

function mockReportResponses({
  bootstrap = { cnpj_data: {}, cadastro: {}, geo_data: {} },
  evolucao = { semestres: [] },
  indicadores = { indicadores: {} },
  crmData = { summary: {}, crms_interesse: [] },
  falecidos = { summary: {}, transacoes: [] },
} = {}) {
  axios.get.mockImplementation(async (url) => {
    if (url.endsWith('/bootstrap')) return { data: bootstrap };
    if (url.endsWith('/evolucao')) return { data: evolucao };
    if (url.endsWith('/indicadores')) return { data: indicadores };
    if (url.endsWith('/crm-data')) return { data: crmData };
    if (url.endsWith('/falecidos')) return { data: falecidos };
    throw new Error('Endpoint inesperado: ' + url);
  });
}

describe('loadCnpjPdfReportData', () => {
  beforeEach(() => { axios.get.mockReset(); requestResumo.mockReset(); });

  it('recusa CNPJ fora do formato sem iniciar consultas', async () => {
    await expect(loadCnpjPdfReportData({ cnpj: '123', geoStore: {} }))
      .rejects.toThrow('CNPJ invalido para geracao do relatorio PDF.');
    await expect(loadCnpjPdfReportData({ cnpj: null, geoStore: {} }))
      .rejects.toThrow('CNPJ invalido para geracao do relatorio PDF.');
    expect(axios.get).not.toHaveBeenCalled();
    expect(requestResumo).not.toHaveBeenCalled();
  });

  it('monta um relatório a partir dos contratos das APIs e agrupa transações por CPF', async () => {
    const bootstrap = {
      cnpj_data: { razao_social: 'Farmácia Exemplo' },
      cadastro: { situacao_rf: 'Ativa' },
      geo_data: { sg_uf: 'SP', id_regiao_saude: 3550001 },
    };
    const crmDoctor = {
      nu_estabelecimentos: 3,
      competencia_nu_estabelecimentos: '202401',
      vl_total_prescricoes: 120,
      flag_robo: 1,
    };
    const transaction = {
      cpf: '12345678900',
      nome_falecido: 'JOAO DA SILVA',
      municipio_falecido: 'SAO PAULO',
      uf_falecido: 'SP',
      dt_obito: '2020-01-01',
      dt_nascimento: '1940-01-01',
      valor_total_autorizacao: 15,
      dias_apos_obito: 10,
    };
    axios.get.mockImplementation(async (url) => {
      if (url.endsWith('/bootstrap')) return { data: bootstrap };
      if (url.endsWith('/evolucao')) return { data: { semestres: [] } };
      if (url.endsWith('/indicadores')) return { data: { indicadores: {} } };
      if (url.endsWith('/crm-data')) return { data: { summary: {}, crms_interesse: [crmDoctor] } };
      if (url.endsWith('/falecidos')) return { data: { summary: {}, transacoes: [transaction, { ...transaction, valor_total_autorizacao: 5 }] } };
      throw new Error('Endpoint inesperado: ' + url);
    });
    requestResumo.mockResolvedValue({ resultado_municipios: [{ id_ibge7: 3550308 }] });
    const geoStore = { qtdMunicipiosPorRegiao: vi.fn(() => 39) };
    const formatTitleCase = (value) => value?.toLowerCase().replace(/\b\w/g, (letter) => letter.toUpperCase()) || '';
    const formatarData = (value) => 'formatada:' + value;

    const result = await loadCnpjPdfReportData({
      cnpj: '12.345.678/0001-99',
      inicio: '2024-01-01',
      fim: '2024-06-30',
      volumeAtipicoPercentual: 35,
      geoStore,
      formatTitleCase,
      formatarData,
    });

    expect(result.cnpj).toBe('12345678000199');
    expect(result.qtdMunicipiosRegiao).toBe(39);
    expect(result.resultadoMunicipios).toEqual([{ id_ibge7: 3550308 }]);
    expect(result.reportData.crm.kpis.valorTop1).toBe(120);
    expect(result.reportData.crm.kpis.qtdPrescrIntensivaLocal).toBe(1);
    expect(result.reportData.falecidos.agrupados).toHaveLength(1);
    expect(result.reportData.falecidos.agrupados[0].total_valor).toBe(20);
    expect(result.reportData.falecidos.agrupados[0].nome).toBe('Joao Da Silva');
    expect(requestResumo).toHaveBeenCalledWith(
      { uf: 'SP', regiao_id: 3550001, data_inicio: '2024-01-01', data_fim: '2024-06-30' },
      ['municipios'],
    );
    const evolutionCall = axios.get.mock.calls.find(([url]) => url.endsWith('/evolucao'));
    expect(evolutionCall[1].params).toEqual({
      data_inicio: '2024-01-01',
      data_fim: '2024-06-30',
      volume_atipico_limite: 35,
    });
  });

  it('exercita indicadores críticos, valores ausentes e contratos opcionais sem filtros nem região', async () => {
    const indicadorEntries = {};
    for (const group of INDICATOR_GROUPS) {
      for (const indicator of group.indicators) {
        indicadorEntries[indicator.key] = { status: 'ATENCAO', valor: 1, risco_reg: 1 };
      }
    }
    indicadorEntries.percentual_nao_comprovacao = { status: 'CRÍTICO', valor: 40, risco_reg: null };
    indicadorEntries.falecidos = { status: 'CRITICO', valor: 20, risco_reg: 2.56, med_reg: 10 };
    indicadorEntries.teto = { status: 'CRÍTICO', valor: 5, risco_reg: 5.2 };
    indicadorEntries.alto_custo = { status: null, valor: 1, risco_reg: 99 };
    mockReportResponses({
      bootstrap: { cnpj_data: {}, cadastro: {}, geo_data: {}, qtd_municipios_regiao: 0 },
      indicadores: { indicadores: indicadorEntries },
      crmData: {
        summary: {
          pct_concentracao_top1: 12,
          pct_concentracao_top5: 34,
          qtd_alertas_cnpj_multiplo: 2,
          qtd_dias_alertas_cnpj_multiplo: 3,
        },
        crms_interesse: [
          {
            nu_estabelecimentos: 71,
            competencia_nu_estabelecimentos: '202401',
            flag_robo: 1,
            flag_robo_oculto: 1,
            flag_crm_exclusivo: 1,
            alerta_concentracao_unico_crm: true,
            flag_crm_invalido: 1,
            flag_prescricao_antes_registro: 1,
            alerta5_geografico: true,
          },
          {
            nu_estabelecimentos: 1,
            competencia_nu_estabelecimentos: '202402',
            vl_total_prescricoes: 8,
            flag_robo: 0,
            flag_robo_oculto: 0,
            flag_crm_exclusivo: 0,
            alerta_concentracao_unico_crm: false,
            flag_crm_invalido: 0,
            flag_prescricao_antes_registro: 0,
            alerta5_geografico: false,
          },
        ],
      },
      falecidos: {
        summary: {},
        transacoes: [
          { cpf: '1', nome_falecido: null, valor_total_autorizacao: 0, dias_apos_obito: 0 },
          { cpf: '1', nome_falecido: 'NOME', valor_total_autorizacao: 7, dias_apos_obito: 4 },
          { cpf: '2', nome_falecido: '', valor_total_autorizacao: null, dias_apos_obito: null },
        ],
      },
    });

    const result = await loadCnpjPdfReportData({
      cnpj: '12345678000199',
      geoStore: {},
      formatTitleCase: () => '',
      formatarData: () => null,
    });

    expect(result.qtdMunicipiosRegiao).toBe(0);
    expect(result.resultadoMunicipios).toEqual([]);
    expect(requestResumo).not.toHaveBeenCalled();
    expect(axios.get.mock.calls.find(([url]) => url.endsWith('/bootstrap'))[1].params).toEqual({});
    expect(result.reportData.indicadores.pontosCriticos.map(({ key }) => key)).toEqual([
      'percentual_nao_comprovacao', 'teto', 'falecidos',
    ]);
    expect(result.reportData.indicadores.pontosCriticos[0].riscoReg).toBeNull();
    expect(result.reportData.crm.kpis).toMatchObject({
      concentracaoTop1: 12,
      concentracaoTop5: 34,
      valorTop1: 0,
      valorTop5: 8,
      qtdPrescrIntensivaLocal: 1,
      qtdPrescrIntensivaOcultos: 1,
      qtdCrmExclusivo: 1,
      qtdLancamentosAgrupados: 1,
      totalIrregularesCfm: 2,
      qtdCrmInvalido: 1,
      qtdPrescrAntesRegistro: 1,
      qtdAcima400km: 1,
      totalSurtosCnpj: 2,
      diasComSurtosCnpj: 3,
      qtdMultiFarmacia: 1,
    });
    expect(result.reportData.falecidos.agrupados).toMatchObject([
      { cpf: '1', nome: 'Nao Identificado', total_valor: 7, max_dias: 4 },
      { cpf: '2', nome: 'Nao Identificado', total_valor: 0, max_dias: 0 },
    ]);
  });

  it('gera resumo com listas CRM e transações vazias', async () => {
    mockReportResponses();

    const result = await loadCnpjPdfReportData({ cnpj: '12345678000199' });

    expect(result.reportData.crm.crmsInteresse).toEqual([]);
    expect(result.reportData.crm.kpis).toMatchObject({ valorTop1: 0, valorTop5: 0 });
    expect(result.reportData.falecidos.agrupados).toEqual([]);
    expect(result.reportData.indicadores.pontosCriticos).toEqual([]);
  });

  it('ordena indicadores críticos sem risco regional usando zero para comparar', async () => {
    const indicadores = {};
    for (const group of INDICATOR_GROUPS) {
      for (const indicator of group.indicators) {
        indicadores[indicator.key] = { status: 'ATENCAO', valor: 1, risco_reg: 1 };
      }
    }
    indicadores.percentual_nao_comprovacao = { status: 'CRITICO', valor: 40, risco_reg: null };
    indicadores.falecidos = { status: 'CRITICO', valor: 10, risco_reg: null };
    indicadores.teto = { status: 'CRITICO', valor: 5, risco_reg: null };
    mockReportResponses({ indicadores: { indicadores } });

    const result = await loadCnpjPdfReportData({ cnpj: '12345678000199' });

    expect(result.reportData.indicadores.pontosCriticos.map(({ key }) => key)).toEqual([
      'percentual_nao_comprovacao', 'falecidos', 'teto',
    ]);
    expect(result.reportData.indicadores.pontosCriticos.slice(1).every(({ riscoReg }) => riscoReg === null)).toBe(true);
  });

  it('preserva a ordem de configuração quando todos os riscos regionais empatam', async () => {
    const indicadores = {};
    for (const group of INDICATOR_GROUPS) {
      for (const indicator of group.indicators) {
        indicadores[indicator.key] = { status: 'CRITICO', valor: 1, risco_reg: 2.5 };
      }
    }
    mockReportResponses({ indicadores: { indicadores } });

    const result = await loadCnpjPdfReportData({ cnpj: '12345678000199' });
    const ordemConfigurada = INDICATOR_GROUPS.flatMap(({ indicators: items }) => items.map(({ key }) => key));

    expect(result.reportData.indicadores.pontosCriticos.map(({ key }) => key)).toEqual(ordemConfigurada);
    expect(result.reportData.indicadores.pontosCriticos.every(({ riscoReg }) => riscoReg === 2.5)).toBe(true);
  });

  it('mantém percentual de não comprovação em primeiro mesmo se a configuração o listar depois', async () => {
    const originalGroups = [...INDICATOR_GROUPS];
    const percentageGroup = INDICATOR_GROUPS.find(({ indicators }) => (
      indicators.some(({ key }) => key === 'percentual_nao_comprovacao')
    ));
    const indicators = {};
    for (const group of INDICATOR_GROUPS) {
      for (const indicator of group.indicators) {
        indicators[indicator.key] = { status: 'ATENCAO', valor: 1, risco_reg: 1 };
      }
    }
    indicators.percentual_nao_comprovacao = { status: 'CRITICO', valor: 40, risco_reg: 1 };
    indicators.teto = { status: 'CRITICO', valor: 5, risco_reg: 5 };
    indicators.falecidos = { status: 'CRITICO', valor: 10, risco_reg: 3 };

    try {
      INDICATOR_GROUPS.splice(
        0,
        INDICATOR_GROUPS.length,
        ...originalGroups.filter((group) => group !== percentageGroup),
        percentageGroup,
      );
      mockReportResponses({ indicadores: { indicadores: indicators } });

      const result = await loadCnpjPdfReportData({ cnpj: '12345678000199' });

      expect(result.reportData.indicadores.pontosCriticos.map(({ key }) => key)).toEqual([
        'percentual_nao_comprovacao', 'teto', 'falecidos',
      ]);
    } finally {
      INDICATOR_GROUPS.splice(0, INDICATOR_GROUPS.length, ...originalGroups);
    }
  });

  it.each([
    ['evolucao.semestres', { semestres: null }, 'evolucao.semestres deve ser uma lista'],
    ['indicadores.indicadores', { indicadores: [] }, 'indicadores.indicadores obrigatorio'],
    ['crm-data.summary', { summary: null, crms_interesse: [] }, 'crm-data.summary obrigatorio'],
    ['crm-data.crms_interesse', { summary: {}, crms_interesse: {} }, 'crm-data.crms_interesse deve ser uma lista'],
    ['falecidos.summary', { summary: null, transacoes: [] }, 'falecidos.summary obrigatorio'],
    ['falecidos.transacoes', { summary: {}, transacoes: {} }, 'falecidos.transacoes deve ser uma lista'],
  ])('falha cedo quando o contrato %s está inválido', async (field, invalidValue, message) => {
    const options = {};
    if (field.startsWith('evolucao')) options.evolucao = invalidValue;
    if (field.startsWith('indicadores')) options.indicadores = invalidValue;
    if (field === 'crm-data.summary') options.crmData = invalidValue;
    if (field === 'crm-data.crms_interesse') options.crmData = invalidValue;
    if (field === 'falecidos.summary') options.falecidos = invalidValue;
    if (field === 'falecidos.transacoes') options.falecidos = invalidValue;
    mockReportResponses(options);
    await expect(loadCnpjPdfReportData({ cnpj: '12345678000199' })).rejects.toThrow(message);
  });

  it.each(['nu_estabelecimentos', 'competencia_nu_estabelecimentos'])(
    'exige %s em cada CRM de interesse', async (field) => {
      mockReportResponses({
        crmData: {
          summary: {},
          crms_interesse: [{ nu_estabelecimentos: 1, competencia_nu_estabelecimentos: '202401', [field]: null }],
        },
      });
      await expect(loadCnpjPdfReportData({ cnpj: '12345678000199' }))
        .rejects.toThrow(`crms_interesse[0].${field} obrigatorio`);
    },
  );
});
