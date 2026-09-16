import axios from "axios";
import { API_ENDPOINTS } from "@/config/api";
import { INDICATOR_GROUPS } from "@/config/riskConfig";

function normalizeCnpj(value) {
  return String(value ?? "").replace(/\D/g, "");
}

function assertObject(value, label) {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new Error(`Contrato invalido para relatorio PDF: ${label} obrigatorio.`);
  }
  return value;
}

function assertArray(value, label) {
  if (!Array.isArray(value)) {
    throw new Error(`Contrato invalido para relatorio PDF: ${label} deve ser uma lista.`);
  }
  return value;
}

function buildParams({ inicio, fim, volumeAtipicoPercentual } = {}) {
  const params = {};
  if (inicio) params.data_inicio = inicio;
  if (fim) params.data_fim = fim;
  if (volumeAtipicoPercentual !== null && volumeAtipicoPercentual !== undefined) {
    params.volume_atipico_limite = volumeAtipicoPercentual;
  }
  return params;
}

function buildPontosCriticos(indicadores) {
  const result = [];
  for (const grupo of INDICATOR_GROUPS) {
    for (const ind of grupo.indicators) {
      const d = indicadores[ind.key];
      if (!d || d.valor == null) continue;
      const status = String(d.status ?? "").toUpperCase();
      if (status !== "CRÍTICO" && status !== "CRITICO") continue;
      const riscoReg = d.risco_reg != null ? Math.round(Number(d.risco_reg) * 10) / 10 : null;
      result.push({
        key: ind.key,
        label: ind.label,
        formato: ind.formato,
        riscoReg,
        valor: d.valor,
        medReg: d.med_reg,
      });
    }
  }
  return result.sort((a, b) => {
    if (a.key === "percentual_nao_comprovacao") return -1;
    if (b.key === "percentual_nao_comprovacao") return 1;
    return (b.riscoReg ?? 0) - (a.riscoReg ?? 0);
  });
}

function buildCrmKpis(crmData) {
  const summary = assertObject(crmData.summary, "crm-data.summary");
  const crmsInteresse = assertArray(crmData.crms_interesse, "crm-data.crms_interesse");
  crmsInteresse.forEach((crm, index) => {
    ["nu_estabelecimentos", "competencia_nu_estabelecimentos"].forEach((field) => {
      if (crm?.[field] === undefined || crm?.[field] === null) {
        throw new Error(`Contrato invalido em crm-data: crms_interesse[${index}].${field} obrigatorio.`);
      }
    });
  });
  const valorTop1 = crmsInteresse.length > 0 ? Number(crmsInteresse[0].vl_total_prescricoes || 0) : 0;
  const valorTop5 = crmsInteresse.slice(0, 5).reduce((acc, curr) => acc + Number(curr.vl_total_prescricoes || 0), 0);
  const doctorsIntensivaLocal = crmsInteresse.filter((m) => Number(m.flag_robo || 0) > 0);
  const doctorsIntensivaBrasil = crmsInteresse.filter((m) => Number(m.flag_robo_oculto || 0) > 0);

  return {
    concentracaoTop1: Number(summary.pct_concentracao_top1 || 0),
    concentracaoTop5: Number(summary.pct_concentracao_top5 || 0),
    valorTop1,
    valorTop5,
    qtdPrescrIntensivaLocal: doctorsIntensivaLocal.length,
    qtdPrescrIntensivaOcultos: doctorsIntensivaBrasil.length,
    qtdCrmExclusivo: crmsInteresse.filter((m) => Number(m.flag_crm_exclusivo || 0) > 0).length,
    qtdLancamentosAgrupados: crmsInteresse.filter((m) => Boolean(m.alerta_concentracao_unico_crm)).length,
    totalIrregularesCfm:
      crmsInteresse.filter((m) => Number(m.flag_crm_invalido || 0) > 0).length +
      crmsInteresse.filter((m) => Number(m.flag_prescricao_antes_registro || 0) > 0).length,
    qtdCrmInvalido: crmsInteresse.filter((m) => Number(m.flag_crm_invalido || 0) > 0).length,
    qtdPrescrAntesRegistro: crmsInteresse.filter((m) => Number(m.flag_prescricao_antes_registro || 0) > 0).length,
    qtdAcima400km: crmsInteresse.filter((m) => Boolean(m.alerta5_geografico)).length,
    totalSurtosCnpj: Number(summary.qtd_alertas_cnpj_multiplo || 0),
    diasComSurtosCnpj: Number(summary.qtd_dias_alertas_cnpj_multiplo || 0),
    qtdMultiFarmacia: crmsInteresse.filter((m) => Number(m.nu_estabelecimentos) > 70).length,
  };
}

function buildFalecidosAgrupados(falecidosData, { formatTitleCase, formatarData }) {
  const transacoes = assertArray(falecidosData.transacoes, "falecidos.transacoes");
  const grupos = new Map();
  for (const t of transacoes) {
    if (!grupos.has(t.cpf)) {
      grupos.set(t.cpf, {
        cpf: t.cpf,
        nome: formatTitleCase(t.nome_falecido) || "Nao Identificado",
        municipio: formatTitleCase(t.municipio_falecido),
        uf: t.uf_falecido,
        dt_obito: formatarData(t.dt_obito),
        dt_nascimento: formatarData(t.dt_nascimento),
        outros_cnpj: t.outros_estabelecimentos,
        transacoes: [],
        total_valor: 0,
        max_dias: 0,
      });
    }
    const grupo = grupos.get(t.cpf);
    grupo.transacoes.push({ ...t, nome_falecido: formatTitleCase(t.nome_falecido) });
    grupo.total_valor += Number(t.valor_total_autorizacao || 0);
    grupo.max_dias = Math.max(grupo.max_dias, Number(t.dias_apos_obito || 0));
  }
  return [...grupos.values()];
}

async function fetchMunicipiosRegiao({ geoData, inicio, fim }) {
  if (!geoData?.sg_uf || !geoData?.id_regiao_saude) {
    return [];
  }
  const params = {
    uf: geoData.sg_uf,
    regiao_id: geoData.id_regiao_saude,
  };
  if (inicio) params.data_inicio = inicio;
  if (fim) params.data_fim = fim;

  const { data } = await axios.get(API_ENDPOINTS.analyticsResumo, { params });
  return assertArray(data?.resultado_municipios, "analytics/resumo.resultado_municipios");
}

export async function loadCnpjPdfReportData({
  cnpj,
  inicio = null,
  fim = null,
  volumeAtipicoPercentual = null,
  geoStore,
  formatTitleCase,
  formatarData,
}) {
  const clean = normalizeCnpj(cnpj);
  if (clean.length !== 14) {
    throw new Error("CNPJ invalido para geracao do relatorio PDF.");
  }

  const baseParams = buildParams({ inicio, fim });
  const { data: bootstrap } = await axios.get(API_ENDPOINTS.analyticsCnpjBootstrap(clean), { params: baseParams });

  const cnpjData = assertObject(bootstrap?.cnpj_data, "bootstrap.cnpj_data");
  const cadastro = assertObject(bootstrap?.cadastro, "bootstrap.cadastro");
  const geoData = assertObject(bootstrap?.geo_data, "bootstrap.geo_data");
  const qtdMunicipiosRegiao =
    bootstrap?.qtd_municipios_regiao ??
    geoStore?.qtdMunicipiosPorRegiao?.(geoData.id_regiao_saude) ??
    null;

  const [evolucao, indicadoresResponse, crmData, falecidosData, resultadoMunicipios] = await Promise.all([
    axios
      .get(API_ENDPOINTS.analyticsEvolucao(clean), {
        params: buildParams({ inicio, fim, volumeAtipicoPercentual }),
      })
      .then((response) => response.data),
    axios
      .get(API_ENDPOINTS.analyticsIndicadores(clean), { params: baseParams })
      .then((response) => response.data),
    axios
      .get(API_ENDPOINTS.analyticsCrmData(clean), { params: baseParams })
      .then((response) => response.data),
    axios
      .get(API_ENDPOINTS.analyticsFalecidos(clean), { params: baseParams })
      .then((response) => response.data),
    fetchMunicipiosRegiao({ geoData, inicio, fim }),
  ]);

  const semestres = assertArray(evolucao?.semestres, "evolucao.semestres");
  const indicadores = assertObject(indicadoresResponse?.indicadores, "indicadores.indicadores");
  assertObject(crmData?.summary, "crm-data.summary");
  assertArray(crmData?.crms_interesse, "crm-data.crms_interesse");
  assertObject(falecidosData?.summary, "falecidos.summary");
  assertArray(falecidosData?.transacoes, "falecidos.transacoes");

  return {
    cnpjData,
    geoData,
    cadastro,
    cnpj: clean,
    qtdMunicipiosRegiao,
    resultadoMunicipios,
    reportData: {
      evolucao: {
        ...evolucao,
        semestres,
      },
      indicadores: {
        indicadores,
        pontosCriticos: buildPontosCriticos(indicadores),
      },
      crm: {
        summary: crmData.summary,
        crmsInteresse: crmData.crms_interesse,
        kpis: buildCrmKpis(crmData),
      },
      falecidos: {
        summary: falecidosData.summary,
        agrupados: buildFalecidosAgrupados(falecidosData, { formatTitleCase, formatarData }),
      },
    },
  };
}
