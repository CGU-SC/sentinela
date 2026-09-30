<script>
import { createRespostaCache as criarCacheModulo } from '@/utils/respostaCache';

// Respostas dos modais guardadas entre aberturas (chave inclui a versão do cache).
const historicoCache = criarCacheModulo(20);
const atuacaoCache = criarCacheModulo(40);
</script>

<script setup>
/**
 * Histórico completo de um CRM (clique numa linha do ranking de /analises).
 *
 * Indicadores, pontos de atenção, tabela de farmácias e mapa de calor usam o
 * período filtrado; a linha do tempo mostra todo o histórico.
 * Filtros do próprio modal (não mexem nos filtros da página): período e uma
 * farmácia (só uma por vez: dias de farmácias diferentes não se somam).
 * Dados: GET /analytics/crm-medico-historico.
 */
import { computed, onBeforeUnmount, ref, watch } from 'vue';
import { useRouter } from 'vue-router';
import axios from 'axios';
import Dialog from 'primevue/dialog';
import Dropdown from 'primevue/dropdown';
import Paginator from 'primevue/paginator';
import { use } from 'echarts/core';
import { CanvasRenderer } from 'echarts/renderers';
import { BarChart, HeatmapChart, LineChart, ScatterChart } from 'echarts/charts';
import {
  DataZoomComponent,
  GridComponent,
  MarkLineComponent,
  TooltipComponent,
  VisualMapComponent,
} from 'echarts/components';
import VChart from 'vue-echarts';
import { API_ENDPOINTS } from '@/config/api';
import { CRM_ALERTA_ICONES, analysisTooltip, crmAlturaAtuacao, crmFaixaPorTaxa } from '@/config/analysisTooltipConfig';
import { CRM_FARMACIA_SERIES, CRM_HEATMAP_TAXA_RAMP, CRM_TAXA_P95_TONS, DATA_NEUTRAL } from '@/config/colors';
import { useChartTheme } from '@/config/chartTheme';
import { useThemeStore } from '@/stores/theme';
import { useFormatting } from '@/composables/useFormatting';
import CrmAtuacaoDialog from '@/views/components/cnpj/CrmAtuacaoDialog.vue';
import MonthRangePicker from '@/views/components/common/MonthRangePicker.vue';
import { AUDIT_PERIOD } from '@/config/constants';

use([
  CanvasRenderer, BarChart, LineChart, ScatterChart, HeatmapChart,
  GridComponent, TooltipComponent, DataZoomComponent,
  MarkLineComponent, VisualMapComponent,
]);

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  /** Linha do ranking: { id_medico, no_medico, nu_crm, sg_uf } */
  medico: { type: Object, default: null },
  dataInicio: { type: String, default: null },
  dataFim: { type: String, default: null },
  /** Versão do cache de dados: entra na chave das respostas guardadas. */
  cacheVersion: { type: String, default: null },
});
const emit = defineEmits(['update:modelValue']);

const router = useRouter();
const themeStore = useThemeStore();
const { chartTheme } = useChartTheme();
const { formatNumberFull, formatarData, formatTitleCase, formatCnpj } = useFormatting();

const TOP_FARMACIAS_GRAFICO = 5;
const TOP_FARMACIAS_CALOR = 15;

// Respostas guardadas (historicoCache/atuacaoCache, no <script> do módulo) por
// médico + período + farmácia + versão do cache: fechar e reabrir o modal, ou
// voltar a um filtro já visto, não refaz a consulta.
const dados = ref(null);
const carregando = ref(false);
const erro = ref(null);
let controller = null;

const tema = computed(() => (themeStore.isDark ? 'dark' : 'light'));
const cores = computed(() => CRM_FARMACIA_SERIES[tema.value]);
const corOutras = computed(() => CRM_FARMACIA_SERIES.outras[tema.value]);
const corTaxa = computed(() => DATA_NEUTRAL[tema.value].line);

const infoTooltip = analysisTooltip('crmHistorico');
const atencaoTooltip = analysisTooltip('crmHistoricoAtencao');
const atuacaoTooltip = analysisTooltip('crmHistoricoAtuacao');
const filtrosTooltip = analysisTooltip('crmHistoricoFiltros');

// ── Filtros do modal ──────────────────────────────────────────────────────────
// Atalhos do seletor de período; intervalo escolhido na grade = "personalizado".
const PERIODO_ATALHOS = [
  { value: 'analise', label: 'Período da análise' },
  { value: 'completo', label: 'Histórico completo' },
  { value: 'ultimos12', label: 'Últimos 12 meses de atuação' },
  { value: 'personalizado', label: 'Período personalizado', grade: true },
];
const COMP_MIN_BASE = AUDIT_PERIOD.START_YEAR * 100 + AUDIT_PERIOD.START_MONTH + 1;
const COMP_MAX_BASE = AUDIT_PERIOD.END_YEAR * 100 + AUDIT_PERIOD.END_MONTH + 1;
const periodoModo = ref('analise');
const personalizado = ref(null); // { inicio, fim } em AAAAMM
const farmaciaFiltro = ref(null); // id_cnpj
// Cadastro das farmácias já vistas nas respostas (nome da farmácia filtrada
// mesmo quando ela não atuou no período escolhido).
const farmaciasConhecidas = ref(new Map());
const ultimaCompetencia = ref(null); // último mês com prescrição do médico
const jaExibido = ref(false);

function resetFiltros() {
  periodoModo.value = 'analise';
  personalizado.value = null;
  farmaciaFiltro.value = null;
  farmaciasConhecidas.value = new Map();
  ultimaCompetencia.value = null;
}
function isoInicio(comp) {
  return `${Math.floor(comp / 100)}-${String(comp % 100).padStart(2, '0')}-01`;
}
function isoFim(comp) {
  const ano = Math.floor(comp / 100);
  const mes = comp % 100;
  const ultimoDia = new Date(Date.UTC(ano, mes, 0)).getUTCDate();
  return `${ano}-${String(mes).padStart(2, '0')}-${String(ultimoDia).padStart(2, '0')}`;
}

const periodoConsulta = computed(() => {
  switch (periodoModo.value) {
    case 'analise':
      return { valido: true, inicio: props.dataInicio, fim: props.dataFim };
    case 'completo':
      return { valido: true, inicio: null, fim: null };
    case 'ultimos12': {
      const fim = ultimaCompetencia.value;
      if (!fim) return { valido: false, motivo: null };
      return { valido: true, inicio: isoInicio(compDoIndice(indiceMes(fim) - 11)), fim: isoFim(fim) };
    }
    case 'personalizado': {
      const faixa = personalizado.value;
      if (!faixa || faixa.inicio > faixa.fim) throw new Error('Período personalizado do histórico sem intervalo válido.');
      return { valido: true, inicio: isoInicio(faixa.inicio), fim: isoFim(faixa.fim) };
    }
    default:
      throw new Error(`Período do histórico inválido: ${periodoModo.value}`);
  }
});
function escolherPeriodo(faixa) {
  personalizado.value = faixa;
  periodoModo.value = 'personalizado';
}
function escolherAtalhoPeriodo(valor) {
  periodoModo.value = valor;
}
// Botão do seletor: atalho (quando houver) + intervalo exibido.
const periodoCompsExibido = computed(() => (
  dados.value
    ? { inicio: compDaData(dados.value.periodo_inicio), fim: compDaData(dados.value.periodo_fim) }
    : null
));
const periodoRotulo = computed(() => {
  const atalho = PERIODO_ATALHOS.find((a) => a.value === periodoModo.value);
  if (!atalho) throw new Error(`Período do histórico sem atalho: ${periodoModo.value}`);
  const faixa = periodoModo.value === 'personalizado' ? personalizado.value : periodoCompsExibido.value;
  const intervalo = faixa ? `${formatComp(faixa.inicio)} – ${formatComp(faixa.fim)}` : '';
  return intervalo ? `${atalho.label} · ${intervalo}` : atalho.label;
});

let chaveCarregada = null;
async function carregar() {
  if (!props.medico?.id_medico) return;
  const periodo = periodoConsulta.value;
  if (!periodo.valido) return;
  const params = { id_medico: props.medico.id_medico };
  if (periodo.inicio) params.data_inicio = periodo.inicio;
  if (periodo.fim) params.data_fim = periodo.fim;
  if (farmaciaFiltro.value != null) params.id_cnpj = farmaciaFiltro.value;
  const chave = JSON.stringify(params);
  if (chave === chaveCarregada) return;
  chaveCarregada = chave;
  controller?.abort();
  const requestController = new AbortController();
  controller = requestController;
  const chaveCache = props.cacheVersion ? `${props.cacheVersion}|${chave}` : null;
  const guardada = chaveCache ? historicoCache.get(chaveCache) : undefined;
  if (!guardada) carregando.value = true;
  try {
    const data = guardada ?? (await axios.get(API_ENDPOINTS.analyticsCrmMedicoHistorico, {
      params,
      signal: requestController.signal,
    })).data;
    if (controller !== requestController) return;
    if ((data.id_cnpj_filtro ?? null) !== (params.id_cnpj ?? null)) {
      throw new Error('Contrato inválido em crm-medico-historico: farmácia filtrada diferente da solicitada.');
    }
    const conhecidas = new Map(farmaciasConhecidas.value);
    for (const f of data.farmacias) conhecidas.set(f.id_cnpj, f);
    farmaciasConhecidas.value = conhecidas;
    if (data.id_cnpj_filtro == null && data.meses.length) {
      ultimaCompetencia.value = data.meses[data.meses.length - 1].competencia;
    }
    erro.value = null;
    dados.value = data;
    if (chaveCache && !guardada) historicoCache.set(chaveCache, data);
  } catch (err) {
    if (axios.isCancel(err) || controller !== requestController) return;
    const status = err?.response?.status;
    const detalhe = err?.response?.data?.detail;
    dados.value = null;
    erro.value = status === 404
      ? (farmaciaFiltro.value != null ? 'Este CRM não tem prescrições na farmácia escolhida.' : 'Este CRM não tem prescrições registradas.')
      : status === 503
        ? (detalhe || 'Os dados de prescrições por médico não estão disponíveis. Sincronize os módulos CRM.')
        : status === 422 && typeof detalhe === 'string'
          ? detalhe
          : 'Não foi possível carregar o histórico deste CRM.';
  } finally {
    if (controller === requestController) {
      controller = null;
      carregando.value = false;
      jaExibido.value = true;
    }
  }
}

watch(
  () => [props.modelValue, props.medico?.id_medico],
  ([aberto]) => {
    controller?.abort();
    controller = null;
    chaveCarregada = null;
    carregando.value = false;
    jaExibido.value = false;
    dados.value = null;
    erro.value = null;
    resetFiltros();
    if (aberto) carregar();
  },
  { immediate: true },
);
// Filtros do modal e período da página (no modo "Período da análise").
watch(
  () => [periodoConsulta.value.valido, periodoConsulta.value.inicio, periodoConsulta.value.fim, farmaciaFiltro.value],
  () => { if (props.modelValue) carregar(); },
);
onBeforeUnmount(() => controller?.abort());

function filtrarFarmacia(idCnpj) {
  farmaciaFiltro.value = farmaciaFiltro.value === idCnpj ? null : idCnpj;
}

function fechar() {
  atuacaoController?.abort();
  atuacao.value = null;
  atuacaoCarregando.value = null;
  emit('update:modelValue', false);
}

// ── Formatação ────────────────────────────────────────────────────────────────
function formatComp(comp) {
  if (!comp) return '—';
  return `${String(comp % 100).padStart(2, '0')}/${Math.floor(comp / 100)}`;
}
function formatDecimal(valor, casas = 2) {
  if (valor == null) return '—';
  return Number(valor).toLocaleString('pt-BR', { minimumFractionDigits: casas, maximumFractionDigits: casas });
}
function formatPct(valor) {
  return valor == null ? '—' : `${formatDecimal(valor, 1)}%`;
}
function indiceMes(comp) {
  return Math.floor(comp / 100) * 12 + (comp % 100) - 1;
}
function compDoIndice(idx) {
  return Math.floor(idx / 12) * 100 + (idx % 12) + 1;
}
function mesesEntre(inicio, fim) {
  const lista = [];
  for (let i = indiceMes(inicio); i <= indiceMes(fim); i += 1) lista.push(compDoIndice(i));
  return lista;
}
function compDaData(iso) {
  if (!iso) return null;
  const [ano, mes] = iso.split('-').map(Number);
  return ano * 100 + mes;
}

// ── Cabeçalho ─────────────────────────────────────────────────────────────────
const titulo = computed(() => {
  const nome = dados.value?.no_medico ?? props.medico?.no_medico;
  return nome ? formatTitleCase(nome) : 'Médico não localizado no cadastro do CFM';
});
const registro = computed(() => {
  const d = dados.value ?? props.medico;
  if (!d) return '';
  return d.nu_crm ? `CRM ${d.nu_crm}/${d.sg_uf ?? ''}` : `CRM ${d.id_medico}`;
});
const periodoTexto = computed(() => (
  dados.value ? `${formatarData(dados.value.periodo_inicio)} a ${formatarData(dados.value.periodo_fim)}` : ''
));

// ── Indicadores ───────────────────────────────────────────────────────────────
const kpis = computed(() => {
  const k = dados.value?.kpis;
  if (!k) return [];
  if (filtroAtivo.value != null) {
    // Farmácia filtrada: números dela; taxa elevada continua a do total do médico.
    return [
      {
        label: 'Prescrições na farmácia',
        value: formatNumberFull(k.nu_prescricoes),
        detail: `${formatNumberFull(k.qtd_dias_com_prescricao)} dias com prescrição`,
      },
      { label: 'Taxa diária na farmácia', value: formatDecimal(k.taxa_prescricoes_dia) },
      {
        label: 'Meses ativos na farmácia',
        value: formatNumberFull(k.qtd_meses_ativos),
        detail: `${formatNumberFull(k.qtd_meses_alta_intensidade)} com taxa elevada (total do médico)`,
      },
      { label: 'Participação no total do médico', value: formatPct(k.percentual_farmacia_principal) },
      {
        label: 'Pior mês na farmácia',
        value: k.pior_mes_competencia
          ? `${formatDecimal(k.pior_mes_taxa_prescricoes_dia)}/dia em ${formatComp(k.pior_mes_competencia)}`
          : '—',
        detail: k.pior_mes_competencia ? `${formatNumberFull(k.pior_mes_prescricoes)} prescrições` : null,
      },
    ];
  }
  return [
    {
      label: 'Prescrições',
      value: formatNumberFull(k.nu_prescricoes),
      detail: `${formatNumberFull(k.qtd_dias_com_prescricao)} dias com prescrição`,
    },
    { label: 'Taxa diária', value: formatDecimal(k.taxa_prescricoes_dia) },
    {
      label: 'Meses ativos',
      value: formatNumberFull(k.qtd_meses_ativos),
      detail: `${formatNumberFull(k.qtd_meses_alta_intensidade)} meses com taxa elevada · ${formatPct(k.percentual_meses_alta_intensidade)}`,
    },
    { label: '3 principais farmácias', value: formatPct(k.percentual_top3_farmacias) },
    {
      // Pior mes = maior taxa diaria do periodo (P95 do mes como referencia).
      label: 'Pior mês (taxa diária)',
      value: k.pior_mes_competencia
        ? `${formatDecimal(k.pior_mes_taxa_prescricoes_dia)}/dia em ${formatComp(k.pior_mes_competencia)}`
        : '—',
      detail: k.pior_mes_competencia
        ? `${formatNumberFull(k.pior_mes_prescricoes)} prescrições · P95 do mês ${formatDecimal(k.pior_mes_p95_taxa_dia)}`
        : null,
    },
  ];
});

// ── Farmácias (cor segue a farmácia: as 5 maiores do período) ────────────────
const farmacias = computed(() => dados.value?.farmacias ?? []);
// Farmácia filtrada na resposta exibida (null = todas).
const filtroAtivo = computed(() => dados.value?.id_cnpj_filtro ?? null);
function cadastroFarmacia(idCnpj) {
  const f = farmaciasConhecidas.value.get(idCnpj);
  if (!f) throw new Error(`Farmácia ${idCnpj} sem cadastro nas respostas do histórico.`);
  return f;
}
const opcoesFarmacia = computed(() => (
  [...farmaciasConhecidas.value.values()]
    .filter((f) => farmacias.value.some((x) => x.id_cnpj === f.id_cnpj) || f.id_cnpj === farmaciaFiltro.value)
    .map((f) => ({
      value: f.id_cnpj,
      label: `${nomeFarmacia(f)} · ${f.cnpj ? formatCnpj(f.cnpj) : f.id_cnpj}${f.municipio ? ` · ${formatTitleCase(f.municipio)}/${f.uf ?? ''}` : ''}`,
    }))
));
const corPorFarmacia = computed(() => {
  const mapa = new Map();
  farmacias.value.slice(0, TOP_FARMACIAS_GRAFICO).forEach((f, i) => mapa.set(f.id_cnpj, cores.value[i]));
  return mapa;
});
function nomeFarmacia(f) {
  return f?.razao_social ? formatTitleCase(f.razao_social) : formatCnpj(f?.cnpj ?? '');
}
const legenda = computed(() => {
  if (filtroAtivo.value != null) {
    return [{ nome: nomeFarmacia(cadastroFarmacia(filtroAtivo.value)), cor: corPorFarmacia.value.get(filtroAtivo.value) ?? corOutras.value }];
  }
  const itens = farmacias.value.slice(0, TOP_FARMACIAS_GRAFICO).map((f) => ({
    nome: nomeFarmacia(f),
    cor: corPorFarmacia.value.get(f.id_cnpj),
  }));
  if (farmacias.value.length > TOP_FARMACIAS_GRAFICO || outrasForaDoPeriodo.value) {
    itens.push({ nome: 'Outras farmácias', cor: corOutras.value });
  }
  return itens;
});
const outrasForaDoPeriodo = computed(() => (
  (dados.value?.farmacia_mes ?? []).some((r) => !corPorFarmacia.value.has(r.id_cnpj))
));

// Tabela paginada (sem rolagem interna, para nao disputar a rolagem do modal).
const FARMACIAS_POR_PAGINA = 10;
const farmaciasInicio = ref(0);
const farmaciasPagina = computed(() => (
  farmacias.value.slice(farmaciasInicio.value, farmaciasInicio.value + FARMACIAS_POR_PAGINA)
));
// Volta à 1ª página ao trocar de médico ou de período (não ao filtrar farmácia).
watch(
  () => [dados.value?.id_medico, dados.value?.periodo_inicio, dados.value?.periodo_fim],
  () => { farmaciasInicio.value = 0; },
);

// ── Coluna "Atuação na farmácia" (mesma da tabela de CRMs do CNPJ) ────────────
// Eixo comum a todas as farmácias: do primeiro ao último mês com prescrição do
// CRM no período filtrado, para os mini gráficos ficarem alinhados no tempo.
const dataColorVars = computed(() => ({
  '--data-color': DATA_NEUTRAL[tema.value].strong,
  '--data-color-soft': DATA_NEUTRAL[tema.value].soft,
  '--p95-leve': CRM_TAXA_P95_TONS[tema.value].leve,
  '--p95-media': CRM_TAXA_P95_TONS[tema.value].media,
  '--p95-forte': CRM_TAXA_P95_TONS[tema.value].forte,
}));
const eixoAtuacao = computed(() => {
  const lista = farmacias.value;
  if (!lista.length) return null;
  const inicio = Math.min(...lista.map((f) => indiceMes(f.primeira_competencia)));
  const fim = Math.max(...lista.map((f) => indiceMes(f.ultima_competencia)));
  return { inicio, total: fim - inicio + 1 };
});
const atuacaoPorFarmacia = computed(() => {
  const mapa = new Map();
  const eixo = eixoAtuacao.value;
  const d = dados.value;
  if (!eixo || !d) return mapa;
  const compInicio = compDaData(d.periodo_inicio);
  const compFim = compDaData(d.periodo_fim);
  const mesPorCompetencia = new Map(d.meses.map((m) => [m.competencia, m]));
  const seriePorFarmacia = new Map();
  for (const r of d.farmacia_mes) {
    if (r.competencia < compInicio || r.competencia > compFim) continue;
    if (!seriePorFarmacia.has(r.id_cnpj)) seriePorFarmacia.set(r.id_cnpj, []);
    seriePorFarmacia.get(r.id_cnpj).push(r);
  }
  for (const f of farmacias.value) {
    const serie = seriePorFarmacia.get(f.id_cnpj);
    if (!serie?.length) {
      throw new Error(`Contrato inválido em crm-medico-historico: farmácia ${f.id_cnpj} sem meses em farmacia_mes no período.`);
    }
    // Altura: ×P95 nacional do mês da taxa diária do CRM nesta farmácia, na
    // mesma escala para todas as farmácias (teto em crmAlturaAtuacao); cor:
    // faixa do ×P95 (regra da linha do tempo).
    const barras = serie.map((p) => {
      const dias = Number(p.qtd_dias_com_prescricao);
      if (!(dias > 0)) {
        throw new Error(`Contrato inválido em crm-medico-historico: farmácia ${f.id_cnpj} sem dias em ${p.competencia}.`);
      }
      const mes = mesPorCompetencia.get(p.competencia);
      if (!mes) {
        throw new Error(`Contrato inválido em crm-medico-historico: mês ${p.competencia} sem P95 em meses.`);
      }
      const taxa = Number(p.nu_prescricoes) / dias;
      const altura = crmAlturaAtuacao(taxa / Number(mes.p95_taxa_dia));
      return {
        x: indiceMes(p.competencia) - eixo.inicio,
        h: Math.max(1.5, altura.fracao * 16),
        cortada: altura.cortada,
        faixa: crmFaixaPorTaxa(taxa, mes.p95_taxa_dia)?.chave ?? null,
      };
    });
    const inicio = f.primeira_competencia;
    const fim = f.ultima_competencia;
    const meses = Number(f.qtd_meses);
    mapa.set(f.id_cnpj, {
      periodo: inicio === fim ? formatComp(inicio) : `${formatComp(inicio)} – ${formatComp(fim)}`,
      meses: `${meses} ${meses === 1 ? 'mês' : 'meses'}`,
      total: eixo.total,
      barras,
    });
  }
  return mapa;
});

// Clique na célula: abre o detalhe mensal da atuação (o mesmo modal da aba
// Autorizações do estabelecimento), com os dados de /crm/medico-atuacao.
const atuacao = ref(null);
const atuacaoCarregando = ref(null);
const atuacaoErro = ref(null);
let atuacaoController = null;
const atuacaoVisivel = computed({
  get: () => atuacao.value !== null,
  set: (visivel) => { if (!visivel) atuacao.value = null; },
});

async function abrirAtuacao(f) {
  if (!f?.cnpj || !props.medico?.id_medico) return;
  atuacaoController?.abort();
  const requestController = new AbortController();
  atuacaoController = requestController;
  atuacaoCarregando.value = f.id_cnpj;
  atuacaoErro.value = null;
  try {
    // Mesmo período exibido na tabela do histórico (filtro do modal), e não o
    // período da página.
    if (!dados.value) throw new Error('Histórico do CRM ainda não carregado.');
    const params = { data_inicio: dados.value.periodo_inicio, data_fim: dados.value.periodo_fim };
    const chaveCache = props.cacheVersion
      ? `${props.cacheVersion}|${JSON.stringify([f.cnpj, props.medico.id_medico, params])}`
      : null;
    let data = chaveCache ? atuacaoCache.get(chaveCache) : undefined;
    if (!data) {
      ({ data } = await axios.get(
        API_ENDPOINTS.analyticsCrmMedicoAtuacao(f.cnpj, props.medico.id_medico),
        { params, signal: requestController.signal },
      ));
      if (chaveCache) atuacaoCache.set(chaveCache, data);
    }
    if (requestController !== atuacaoController || !props.modelValue) return;
    atuacao.value = {
      medico: data.medico,
      cnpj: data.cnpj,
      periodo: { inicio: data.competencia_inicio_periodo, fim: data.competencia_fim_periodo },
      serieFarmacia: data.serie_mensal_farmacia,
    };
  } catch (err) {
    if (axios.isCancel(err) || requestController !== atuacaoController || !props.modelValue) return;
    const detalhe = err?.response?.data?.detail;
    atuacaoErro.value = `Não foi possível abrir a atuação em ${nomeFarmacia(f)}${detalhe ? `: ${detalhe}` : '.'}`;
  } finally {
    if (requestController === atuacaoController) atuacaoCarregando.value = null;
  }
}
watch(dados, () => {
  atuacaoController?.abort();
  atuacao.value = null;
  atuacaoCarregando.value = null;
  atuacaoErro.value = null;
});
watch(() => props.modelValue, (aberto) => {
  if (!aberto) {
    atuacaoController?.abort();
    atuacao.value = null;
    atuacaoCarregando.value = null;
    atuacaoErro.value = null;
  }
});
onBeforeUnmount(() => atuacaoController?.abort());

function abrirFarmacia(f) {
  if (!f?.cnpj) return;
  fechar();
  router.push(`/estabelecimentos/${f.cnpj}`);
}

// ── Linha do tempo (dois painéis, mesmo eixo de meses) ───────────────────────
const linhaDoTempo = computed(() => {
  const d = dados.value;
  if (!d?.meses?.length) return null;
  const meses = mesesEntre(d.meses[0].competencia, d.meses[d.meses.length - 1].competencia);
  const porMes = new Map(d.meses.map((m) => [m.competencia, m]));
  const topIds = filtroAtivo.value != null
    ? [filtroAtivo.value]
    : farmacias.value.slice(0, TOP_FARMACIAS_GRAFICO).map((f) => f.id_cnpj);
  const series = new Map(topIds.map((id) => [id, new Map()]));
  const outras = new Map();
  for (const r of d.farmacia_mes) {
    const alvo = series.get(r.id_cnpj) ?? outras;
    alvo.set(r.competencia, (alvo.get(r.competencia) ?? 0) + r.nu_prescricoes);
  }
  return { meses, porMes, topIds, series, outras };
});

const chartOption = computed(() => {
  const lt = linhaDoTempo.value;
  if (!lt) return {};
  const c = chartTheme.value;
  const d = dados.value;
  const rotulos = lt.meses.map(formatComp);
  const superficie = themeStore.isDark ? '#1e1e1e' : '#ffffff';
  const compInscricao = compDaData(d.dt_primeira_inscricao);
  const inscricaoNoEixo = compInscricao && lt.meses.includes(compInscricao) ? formatComp(compInscricao) : null;

  const barra = (nome, cor, valores, extra = {}) => ({
    name: nome,
    type: 'bar',
    stack: 'farmacias',
    xAxisIndex: 0,
    yAxisIndex: 0,
    barMaxWidth: 14,
    itemStyle: { color: cor, borderColor: superficie, borderWidth: 1 },
    emphasis: { focus: 'series' },
    data: lt.meses.map((m) => valores.get(m) ?? null),
    ...extra,
  });

  const filtrada = filtroAtivo.value != null;
  const barras = lt.topIds.map((id) => barra(
    nomeFarmacia(cadastroFarmacia(id)),
    corPorFarmacia.value.get(id) ?? corOutras.value,
    lt.series.get(id),
  ));
  if (!filtrada) barras.push(barra('Outras farmácias', corOutras.value, lt.outras));
  const nomeTaxa = filtrada ? 'Taxa diária na farmácia' : 'Taxa diária';
  const nomeAlta = filtrada ? 'Mês com taxa elevada (total do médico)' : 'Mês com taxa elevada';
  // Marca a 1ª inscrição no CFM na primeira série.
  if (inscricaoNoEixo) {
    barras[0].markLine = {
      silent: true,
      symbol: 'none',
      lineStyle: { color: c.muted, type: 'dashed', width: 1.5 },
      label: { formatter: '1ª inscrição CFM', color: c.muted, fontSize: 10, position: 'insideEndTop' },
      data: [{ xAxis: inscricaoNoEixo }],
    };
  }

  const taxa = lt.meses.map((m) => {
    const mes = lt.porMes.get(m);
    return mes ? Number(mes.taxa_prescricoes_dia.toFixed(2)) : null;
  });
  const p95 = lt.meses.map((m) => {
    const mes = lt.porMes.get(m);
    return mes ? Number(mes.p95_taxa_dia.toFixed(2)) : null;
  });
  const alta = lt.meses.map((m, i) => (lt.porMes.get(m)?.alta_intensidade ? [i, taxa[i]] : null)).filter(Boolean);
  const corAlerta = themeStore.isDark ? '#e66767' : '#d03b3b';

  return {
    backgroundColor: 'transparent',
    animationDuration: 300,
    axisPointer: { link: [{ xAxisIndex: 'all' }] },
    tooltip: {
      trigger: 'axis',
      confine: true,
      backgroundColor: c.tooltip,
      borderColor: c.tooltipBorder,
      textStyle: { color: c.tooltipText, fontSize: 12 },
      formatter: (params) => {
        const idx = params[0]?.dataIndex;
        const comp = lt.meses[idx];
        const mes = lt.porMes.get(comp);
        if (!mes) return `<strong>${formatComp(comp)}</strong><div style="opacity:.7;margin-top:6px">Sem prescrições</div>`;
        const linha = (r, v) => `<div style="display:flex;justify-content:space-between;gap:18px;margin:3px 0"><span style="opacity:.72">${r}</span><span>${v}</span></div>`;
        const farm = params
          .filter((p) => p.seriesType === 'bar' && p.value)
          .map((p) => linha(`${p.marker}${p.seriesName}`, formatNumberFull(p.value)))
          .join('');
        return `<div style="min-width:240px">
          <div style="font-weight:600;margin-bottom:6px">${formatComp(comp)}${mes.alta_intensidade ? ' · <span style="color:' + corAlerta + '">taxa elevada' + (filtrada ? ' (total do médico)' : '') + '</span>' : ''}</div>
          <div style="display:flex;justify-content:space-between;align-items:baseline;gap:18px;margin:2px 0 8px;padding:6px 8px;border-radius:6px;background:${mes.alta_intensidade ? corAlerta + '22' : c.axisShadow}">
            <span style="font-weight:600">${nomeTaxa}</span>
            <span><strong style="font-size:16px;font-weight:600;color:${mes.alta_intensidade ? corAlerta : c.tooltipText}">${formatDecimal(mes.taxa_prescricoes_dia)}</strong><span style="opacity:.72"> /dia${filtrada ? '' : ` · ${formatDecimal(mes.taxa_prescricoes_dia / mes.p95_taxa_dia, 1)}× o P95`}</span></span>
          </div>
          ${linha('Prescrições', formatNumberFull(mes.nu_prescricoes))}
          ${linha('Dias com prescrição', formatNumberFull(mes.qtd_dias_com_prescricao))}
          ${linha('P95 nacional do mês', formatDecimal(mes.p95_taxa_dia))}
          ${filtrada ? '' : linha('Farmácias / UFs', `${mes.qtd_farmacias} / ${mes.qtd_ufs}`)}
          <div style="border-top:1px solid ${c.tooltipBorder};margin-top:6px;padding-top:4px">${farm}</div>
        </div>`;
      },
    },
    grid: [
      // Dois paineis da mesma altura: prescricoes (em cima) e taxa diaria.
      { left: 56, right: 18, top: 18, height: '39%' },
      { left: 56, right: 18, top: '51%', height: '39%' },
    ],
    xAxis: [0, 1].map((gi) => ({
      type: 'category',
      gridIndex: gi,
      data: rotulos,
      boundaryGap: true,
      axisLine: { lineStyle: { color: c.border } },
      axisTick: { show: false },
      axisLabel: { show: gi === 1, color: c.muted, fontSize: 10 },
    })),
    yAxis: [
      {
        gridIndex: 0,
        name: 'Prescrições',
        nameTextStyle: { color: c.muted, fontSize: 10, align: 'left' },
        axisLabel: { color: c.muted, fontSize: 10 },
        splitLine: { lineStyle: { color: c.grid } },
      },
      {
        gridIndex: 1,
        name: 'Taxa diária',
        nameTextStyle: { color: c.muted, fontSize: 10, align: 'left' },
        axisLabel: { color: c.muted, fontSize: 10 },
        splitLine: { lineStyle: { color: c.grid } },
      },
    ],
    dataZoom: [
      // Sem dataZoom 'inside': mesmo desligado para a roda, ele captura o
      // evento e impede a rolagem do modal. Zoom so pela barra de baixo.
      {
        type: 'slider', xAxisIndex: [0, 1], bottom: 4, height: 16,
        borderColor: c.border, textStyle: { color: c.muted, fontSize: 10 },
      },
    ],
    series: [
      ...barras,
      {
        name: 'P95 nacional do mês',
        type: 'line',
        xAxisIndex: 1,
        yAxisIndex: 1,
        symbol: 'none',
        connectNulls: false,
        lineStyle: { color: c.muted, width: 1.5, type: 'dashed' },
        data: p95,
      },
      {
        name: nomeTaxa,
        type: 'line',
        xAxisIndex: 1,
        yAxisIndex: 1,
        symbol: 'none',
        connectNulls: false,
        lineStyle: { color: corTaxa.value, width: 2 },
        data: taxa,
      },
      {
        name: nomeAlta,
        type: 'scatter',
        xAxisIndex: 1,
        yAxisIndex: 1,
        symbolSize: 8,
        itemStyle: { color: corAlerta, borderColor: superficie, borderWidth: 2 },
        data: alta,
      },
    ],
  };
});

// ── Mapa de calor farmácia x mês (período filtrado) ──────────────────────────
const calor = computed(() => {
  const d = dados.value;
  // Com farmácia filtrada vira uma linha só (repetiria a linha do tempo).
  if (!d || !farmacias.value.length || filtroAtivo.value != null) return null;
  const meses = mesesEntre(compDaData(d.periodo_inicio), compDaData(d.periodo_fim))
    .filter((m) => m >= d.meses[0].competencia && m <= d.meses[d.meses.length - 1].competencia);
  if (!meses.length) return null;
  const linhas = farmacias.value.slice(0, TOP_FARMACIAS_CALOR);
  const idxMes = new Map(meses.map((m, i) => [m, i]));
  const idxFarm = new Map(linhas.map((f, i) => [f.id_cnpj, i]));
  // Celula = taxa diaria do medico nesta farmacia no mes (prescricoes / dias).
  const pontos = [];
  let minimo = Infinity;
  let maximo = 0;
  for (const r of d.farmacia_mes) {
    const x = idxMes.get(r.competencia);
    const y = idxFarm.get(r.id_cnpj);
    if (x == null || y == null || !r.qtd_dias_com_prescricao) continue;
    const taxa = r.nu_prescricoes / r.qtd_dias_com_prescricao;
    pontos.push([x, y, Number(taxa.toFixed(2)), r.nu_prescricoes, r.qtd_dias_com_prescricao]);
    minimo = Math.min(minimo, taxa);
    maximo = Math.max(maximo, taxa);
  }
  if (!pontos.length) return null;
  return { meses, linhas, pontos, minimo, maximo, omitidas: farmacias.value.length - linhas.length };
});

const taxaSelecionada = ref(null);
watch(calor, () => { taxaSelecionada.value = null; });
const calorEscala = computed(() => {
  const h = calor.value;
  if (!h) return null;
  const minimo = Math.floor(h.minimo * 10) / 10;
  const maximo = Math.max(Math.ceil(h.maximo * 10) / 10, minimo + 0.1);
  return { minimo, maximo, meiaFaixa: (maximo - minimo) * 0.015 };
});
const calorAltura = computed(() => `${Math.max(160, (calor.value?.linhas.length ?? 0) * 24 + 54)}px`);

const calorOption = computed(() => {
  const h = calor.value;
  if (!h) return {};
  const c = chartTheme.value;
  const rampa = CRM_HEATMAP_TAXA_RAMP[tema.value];
  const pontosDestacados = taxaSelecionada.value == null
    ? []
    : h.pontos.filter((p) => Math.abs(p[2] - taxaSelecionada.value) <= calorEscala.value.meiaFaixa);
  const nomes = h.linhas.map((f) => {
    const nome = nomeFarmacia(f);
    return nome.length > 34 ? `${nome.slice(0, 33)}…` : nome;
  });
  return {
    backgroundColor: 'transparent',
    animation: false,
    tooltip: {
      confine: true,
      backgroundColor: c.tooltip,
      borderColor: c.tooltipBorder,
      textStyle: { color: c.tooltipText, fontSize: 12 },
      formatter: (p) => {
        const f = h.linhas[p.value[1]];
        return `<div style="font-weight:600">${nomeFarmacia(f)}</div>
          <div style="opacity:.72;margin:2px 0 6px">${f.municipio ? formatTitleCase(f.municipio) : ''}${f.uf ? '/' + f.uf : ''}</div>
          ${formatComp(h.meses[p.value[0]])}: ${formatNumberFull(p.value[3])} prescrições em ${formatNumberFull(p.value[4])}
          ${p.value[4] === 1 ? 'dia' : 'dias'} = <strong>${formatDecimal(p.value[2], 1)}/dia</strong>`;
      },
    },
    grid: { left: 230, right: 18, top: 8, bottom: 28 },
    xAxis: {
      type: 'category',
      data: h.meses.map(formatComp),
      axisLabel: { color: c.muted, fontSize: 10 },
      axisLine: { lineStyle: { color: c.border } },
      axisTick: { show: false },
      splitArea: { show: false },
    },
    yAxis: {
      type: 'category',
      data: nomes,
      inverse: true,
      axisLabel: { color: c.text, fontSize: 11 },
      axisLine: { show: false },
      axisTick: { show: false },
    },
    visualMap: [
      {
        seriesIndex: 0,
        min: calorEscala.value.minimo,
        max: calorEscala.value.maximo,
        dimension: 2,
        show: false,
        inRange: { color: rampa },
      },
      {
        seriesIndex: 1,
        min: calorEscala.value.minimo,
        max: calorEscala.value.maximo,
        dimension: 2,
        show: false,
        inRange: { color: [tema.value === 'dark' ? rampa.at(-1) : rampa[0]] },
      },
    ],
    series: [
      {
        type: 'heatmap',
        data: h.pontos,
        itemStyle: { borderColor: c.tooltipSolid, borderWidth: 2, borderRadius: 2 },
        emphasis: { itemStyle: { borderColor: c.text, borderWidth: 1 } },
      },
      {
        type: 'heatmap',
        silent: true,
        data: pontosDestacados,
        itemStyle: {
          opacity: 0.28,
          borderColor: c.tooltipSolid,
          borderWidth: 2,
          borderRadius: 2,
        },
      },
    ],
  };
});
</script>

<template>
  <Dialog
    :visible="modelValue && jaExibido"
    modal
    maximizable
    dismissableMask
    class="crm-historico-dialog"
    :style="{ width: '94vw', maxWidth: '1500px' }"
    @update:visible="$event ? emit('update:modelValue', true) : fechar()"
  >
    <template #header>
      <div class="hist-header">
        <span class="hist-eyebrow">
          Histórico do CRM
          <i class="pi pi-info-circle hist-info" v-tooltip.bottom="infoTooltip" aria-label="Como ler o histórico" />
        </span>
        <span class="hist-title">{{ titulo }}</span>
        <div class="hist-meta">
          <span>{{ registro }}</span>
          <span v-if="dados?.dt_primeira_inscricao">1ª inscrição no CFM: {{ formatarData(dados.dt_primeira_inscricao) }}</span>
          <span v-if="periodoTexto">Período: {{ periodoTexto }}</span>
          <span v-if="dados && !dados.localizado_cfm" class="hist-badge hist-badge--alerta">
            <i class="pi pi-exclamation-triangle" /> Não localizado no cadastro do CFM
          </span>
        </div>
        <div class="hist-filtros">
          <div class="hist-filtro">
            <span>Período</span>
            <MonthRangePicker
              :rotulo="periodoRotulo"
              :inicio="periodoCompsExibido?.inicio ?? null"
              :fim="periodoCompsExibido?.fim ?? null"
              :min="COMP_MIN_BASE"
              :max="COMP_MAX_BASE"
              :atalhos="PERIODO_ATALHOS"
              :atalho-ativo="periodoModo"
              @select-range="escolherPeriodo"
              @select-atalho="escolherAtalhoPeriodo"
            />
          </div>
          <label class="hist-filtro hist-filtro--farmacia">
            <span>Farmácia</span>
            <Dropdown
              v-model="farmaciaFiltro"
              :options="opcoesFarmacia"
              option-label="label"
              option-value="value"
              filter
              show-clear
              placeholder="Todas as farmácias"
              empty-filter-message="Nenhuma farmácia encontrada"
              class="hist-filtro-campo"
              aria-label="Filtrar por farmácia"
            />
          </label>
          <i
            class="pi pi-info-circle hist-info"
            v-tooltip.bottom="filtrosTooltip"
            aria-label="Como funcionam os filtros do histórico"
          />
          <span v-if="carregando" class="hist-filtro-status"><i class="pi pi-spin pi-spinner" aria-hidden="true" /> Atualizando…</span>
          <span v-else-if="periodoConsulta.motivo" class="hist-filtro-status hist-filtro-status--erro">{{ periodoConsulta.motivo }}</span>
        </div>
      </div>
    </template>

    <div v-if="erro" class="hist-estado hist-estado--erro">
      <i class="pi pi-exclamation-circle" /> {{ erro }}
    </div>

    <div v-else-if="dados" class="hist-body" :class="{ 'is-atualizando': carregando }" :aria-busy="carregando">
      <!-- Indicadores do período -->
      <div class="hist-kpis">
        <div v-for="kpi in kpis" :key="kpi.label" class="hist-kpi">
          <span class="hist-kpi-label">{{ kpi.label }}</span>
          <span class="hist-kpi-value">{{ kpi.value }}</span>
          <span v-if="kpi.detail" class="hist-kpi-detail">{{ kpi.detail }}</span>
        </div>
      </div>

      <!-- Pontos de atenção -->
      <section class="hist-panel">
        <header class="hist-panel-header">
          <h3>Pontos de atenção</h3>
          <i class="pi pi-info-circle hist-info" v-tooltip.bottom="atencaoTooltip" aria-label="Como os pontos são calculados" />
        </header>
        <ul v-if="dados.pontos_atencao.length" class="hist-atencao">
          <li v-for="p in dados.pontos_atencao" :key="p.codigo">
            <i class="pi" :class="CRM_ALERTA_ICONES[p.codigo]" aria-hidden="true" />
            <div>
              <strong>{{ p.titulo }}</strong>
              <span>{{ p.detalhe }}</span>
            </div>
          </li>
        </ul>
        <p v-else class="hist-vazio">Nenhum ponto de atenção no período.</p>
      </section>

      <!-- Linha do tempo -->
      <section class="hist-panel">
        <header class="hist-panel-header">
          <h3>Linha do tempo mensal</h3>
          <span class="hist-panel-sub">histórico completo{{ filtroAtivo != null ? ' · somente a farmácia filtrada' : '' }}</span>
        </header>
        <div class="hist-legenda">
          <span v-for="item in legenda" :key="item.nome" class="hist-legenda-item">
            <i class="hist-swatch" :style="{ backgroundColor: item.cor }" aria-hidden="true" />{{ item.nome }}
          </span>
          <span class="hist-legenda-item">
            <i class="hist-swatch hist-swatch--linha" :style="{ backgroundColor: corTaxa }" aria-hidden="true" />{{ filtroAtivo != null ? 'Taxa diária na farmácia' : 'Taxa diária' }}
          </span>
          <span class="hist-legenda-item">
            <i class="hist-swatch hist-swatch--tracejada" aria-hidden="true" />P95 nacional do mês
          </span>
          <span class="hist-legenda-item">
            <i class="hist-swatch hist-swatch--ponto" aria-hidden="true" />{{ filtroAtivo != null ? 'Mês com taxa elevada (total do médico)' : 'Mês com taxa elevada' }}
          </span>
        </div>
        <VChart class="hist-chart" :option="chartOption" autoresize />
      </section>

      <!-- Farmácias -->
      <section class="hist-panel">
        <header class="hist-panel-header">
          <h3>Farmácias onde atuou</h3>
          <span class="hist-panel-sub">período filtrado · clique para abrir o estabelecimento · <i class="pi pi-filter" aria-hidden="true" /> filtra o histórico pela farmácia</span>
        </header>
        <p v-if="atuacaoErro" class="hist-atuacao-erro" role="alert">
          <i class="pi pi-exclamation-triangle" aria-hidden="true" />{{ atuacaoErro }}
        </p>
        <div class="hist-tabela-wrap">
          <table class="hist-tabela">
            <colgroup>
              <col class="c-nome"><col class="c-local"><col class="c-sit"><col class="c-ms">
              <col class="c-num"><col class="c-num"><col class="c-atuacao">
            </colgroup>
            <thead>
              <tr>
                <th>FARMÁCIA</th><th>MUNICÍPIO / UF</th><th>SITUAÇÃO RF</th><th>CONEXÃO MS</th>
                <th>PRESCRIÇÕES</th><th>% DO TOTAL</th>
                <th class="th-atuacao">
                  ATUAÇÃO NA FARMÁCIA
                  <i
                    class="pi pi-info-circle hist-info"
                    v-tooltip.top="atuacaoTooltip"
                    tabindex="0"
                    aria-label="Informações sobre a atuação na farmácia"
                  />
                </th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="f in farmaciasPagina"
                :key="f.id_cnpj"
                :class="{ 'is-filtrada': f.id_cnpj === filtroAtivo }"
                tabindex="0"
                @click="abrirFarmacia(f)"
                @keydown.enter="abrirFarmacia(f)"
              >
                <td>
                  <span class="hist-farm">
                    <i
                      class="hist-swatch"
                      :style="{ backgroundColor: corPorFarmacia.get(f.id_cnpj) ?? corOutras }"
                      aria-hidden="true"
                    />
                    <span class="hist-farm-identidade">
                      <span class="hist-farm-nome">{{ nomeFarmacia(f) }}</span>
                      <span class="hist-farm-cnpj">{{ formatCnpj(f.cnpj ?? '') }}</span>
                      <i class="pi pi-arrow-up-right hist-farm-abrir" aria-hidden="true" />
                    </span>
                    <button
                      type="button"
                      class="hist-farm-filtrar"
                      :class="{ 'is-ativo': f.id_cnpj === farmaciaFiltro }"
                      :aria-pressed="f.id_cnpj === farmaciaFiltro"
                      :aria-label="f.id_cnpj === farmaciaFiltro ? `Remover filtro de ${nomeFarmacia(f)}` : `Filtrar o histórico por ${nomeFarmacia(f)}`"
                      v-tooltip.top="f.id_cnpj === farmaciaFiltro ? 'Remover filtro' : 'Filtrar o histórico por esta farmácia'"
                      @click.stop="filtrarFarmacia(f.id_cnpj)"
                      @keydown.enter.stop
                    >
                      <i class="pi" :class="f.id_cnpj === farmaciaFiltro ? 'pi-filter-slash' : 'pi-filter'" aria-hidden="true" />
                    </button>
                  </span>
                </td>
                <td>
                  {{ f.municipio ? formatTitleCase(f.municipio) : '—' }}{{ f.uf ? ` / ${f.uf}` : '' }}
                  <span v-if="f.fora_uf_crm" class="hist-badge">fora da UF do CRM</span>
                </td>
                <td>{{ f.situacao_rf ?? '—' }}</td>
                <td>{{ f.conexao_ativa == null ? '—' : f.conexao_ativa ? 'Ativa' : 'Inativa' }}</td>
                <td class="num hist-numero">{{ formatNumberFull(f.nu_prescricoes) }}</td>
                <td class="num hist-participacao">
                  <span class="hist-numero">{{ formatPct(f.percentual_prescricoes) }}</span>
                  <span class="hist-participacao-trilha" aria-hidden="true">
                    <span
                      class="hist-participacao-barra"
                      :style="{
                        width: `${f.percentual_prescricoes}%`,
                        backgroundColor: corPorFarmacia.get(f.id_cnpj) ?? corOutras,
                      }"
                    />
                  </span>
                </td>
                <td class="atuacao-cell" :style="dataColorVars">
                  <button
                    v-if="atuacaoPorFarmacia.get(f.id_cnpj)"
                    type="button"
                    class="atuacao-btn"
                    :class="{ 'is-loading': atuacaoCarregando === f.id_cnpj }"
                    :disabled="!f.cnpj"
                    :aria-label="`Abrir detalhe mensal da atuação em ${nomeFarmacia(f)}`"
                    @click.stop="abrirAtuacao(f)"
                    @keydown.enter.stop
                  >
                    <i
                      class="pi atuacao-expand-icon"
                      :class="atuacaoCarregando === f.id_cnpj ? 'pi-spin pi-spinner' : 'pi-window-maximize'"
                      aria-hidden="true"
                    />
                    <span class="atuacao-texto">
                      <span class="atuacao-periodo">{{ atuacaoPorFarmacia.get(f.id_cnpj).periodo }}</span>
                      <span class="atuacao-meses">{{ atuacaoPorFarmacia.get(f.id_cnpj).meses }}</span>
                    </span>
                    <svg
                      class="atuacao-spark"
                      :viewBox="`0 0 ${atuacaoPorFarmacia.get(f.id_cnpj).total} 16`"
                      preserveAspectRatio="none"
                      role="img"
                      :aria-label="`Taxa diária mensal em ${nomeFarmacia(f)}: ${atuacaoPorFarmacia.get(f.id_cnpj).periodo}, ${atuacaoPorFarmacia.get(f.id_cnpj).meses}`"
                    >
                      <line class="atuacao-base" x1="0" y1="15.75" :x2="atuacaoPorFarmacia.get(f.id_cnpj).total" y2="15.75" />
                      <rect
                        v-for="barra in atuacaoPorFarmacia.get(f.id_cnpj).barras"
                        :key="barra.x"
                        class="atuacao-bar"
                        :class="barra.faixa ? `is-p95-${barra.faixa}` : null"
                        :x="barra.x + 0.1"
                        :y="16 - barra.h"
                        width="0.8"
                        :height="barra.h"
                      />
                      <rect
                        v-for="barra in atuacaoPorFarmacia.get(f.id_cnpj).barras.filter((b) => b.cortada)"
                        :key="`corte-${barra.x}`"
                        class="atuacao-corte"
                        :x="barra.x + 0.1"
                        y="0"
                        width="0.8"
                        height="1.4"
                      />
                    </svg>
                  </button>
                </td>
              </tr>
              <tr v-if="!farmacias.length"><td colspan="7" class="hist-vazio">Sem prescrições no período filtrado.</td></tr>
            </tbody>
          </table>
        </div>
        <!-- enterprise-table: mesmo estilo de paginador da tabela de /estabelecimentos (claro e escuro). -->
        <div v-if="farmacias.length > FARMACIAS_POR_PAGINA" class="enterprise-table">
          <Paginator
            :first="farmaciasInicio"
            :rows="FARMACIAS_POR_PAGINA"
            :total-records="farmacias.length"
            class="hist-paginator"
            @page="farmaciasInicio = $event.first"
          />
        </div>
      </section>

      <!-- Mapa de calor -->
      <section v-if="calor" class="hist-panel">
        <header class="hist-panel-header">
          <h3>Taxa diária por farmácia e mês</h3>
          <span class="hist-panel-sub">
            prescrições ÷ dias com prescrição na farmácia · período filtrado ·
            {{ calor.linhas.length }} farmácias com mais prescrições{{ calor.omitidas ? ` (mais ${calor.omitidas} na tabela)` : '' }}
            · escala do próprio médico
          </span>
        </header>
        <VChart class="hist-calor" :style="{ height: calorAltura }" :option="calorOption" autoresize />
        <div class="hist-calor-controle">
          <div class="hist-calor-controle-cabecalho">
            <span>Escala da taxa diária</span>
            <span v-if="taxaSelecionada != null" class="hist-calor-controle-valor">
              {{ formatDecimal(taxaSelecionada, 1) }} presc./dia
              <button type="button" class="hist-calor-limpar" @click="taxaSelecionada = null">Limpar seleção</button>
            </span>
            <span v-else class="hist-calor-controle-instrucao">Arraste o marcador para destacar uma faixa</span>
          </div>
          <input
            type="range"
            class="hist-calor-slider"
            :min="calorEscala.minimo"
            :max="calorEscala.maximo"
            step="0.1"
            :value="taxaSelecionada ?? calorEscala.minimo"
            :style="{ '--heatmap-gradient': `linear-gradient(90deg, ${CRM_HEATMAP_TAXA_RAMP[tema].join(', ')})` }"
            aria-label="Destacar faixa da taxa diária no heatmap"
            @input="taxaSelecionada = Number($event.target.value)"
          />
          <div class="hist-calor-controle-limites">
            <span>{{ formatDecimal(calor.minimo, 1) }} presc./dia</span>
            <span>{{ formatDecimal(calor.maximo, 1) }} presc./dia</span>
          </div>
        </div>
      </section>
    </div>

    <!-- Detalhe mensal da atuação (o Dialog do PrimeVue é teleportado para o body). -->
    <CrmAtuacaoDialog
      v-if="atuacao"
      v-model="atuacaoVisivel"
      :medico="atuacao.medico"
      :cnpj="atuacao.cnpj"
      :periodo="atuacao.periodo"
      :serie-farmacia="atuacao.serieFarmacia"
    />

    <template #footer>
      <button type="button" class="hist-fechar" @click="fechar">Fechar</button>
    </template>
  </Dialog>

  <Transition name="detail-overlay-fade">
    <div v-if="modelValue && carregando" class="detail-loading-overlay" aria-live="polite" aria-busy="true">
      <div class="detail-loading-overlay__box">
        <i class="pi pi-spin pi-spinner" aria-hidden="true" />
        <span>Carregando detalhamento...</span>
      </div>
    </div>
  </Transition>
</template>

<style scoped>
.detail-loading-overlay {
  position: fixed;
  inset: 0;
  z-index: 1200;
  display: flex;
  align-items: center;
  justify-content: center;
  background: color-mix(in srgb, var(--bg-color) 72%, transparent);
  backdrop-filter: blur(2px);
}
.detail-loading-overlay__box {
  display: inline-flex;
  align-items: center;
  gap: .75rem;
  padding: .9rem 1.1rem;
  border: 1px solid var(--card-border);
  border-radius: 10px;
  background: var(--card-bg);
  color: var(--text-color-85);
  box-shadow: 0 12px 28px color-mix(in srgb, var(--text-color-85) 12%, transparent);
  font-size: .86rem;
  font-weight: 600;
}
.detail-loading-overlay__box i { color: var(--primary-color); font-size: 1rem; }
.detail-overlay-fade-enter-active, .detail-overlay-fade-leave-active { transition: opacity .18s ease; }
.detail-overlay-fade-enter-from, .detail-overlay-fade-leave-to { opacity: 0; }

.hist-header { display: flex; flex-direction: column; gap: .2rem; }
.hist-eyebrow { display: inline-flex; align-items: center; gap: .4rem; font-size: .66rem; font-weight: 600; letter-spacing: .08em; text-transform: uppercase; color: var(--text-muted); }
.hist-title { font-size: 1.05rem; font-weight: 600; color: var(--text-color); }
.hist-filtros { display: flex; flex-wrap: wrap; align-items: flex-end; gap: .5rem .75rem; margin-top: .55rem; }
.hist-filtro { display: flex; flex-direction: column; gap: .2rem; font-size: .62rem; font-weight: 600; letter-spacing: .06em; text-transform: uppercase; color: var(--text-muted); }
.hist-filtro-campo { min-width: 13rem; font-size: .76rem; }
.hist-filtro--farmacia .hist-filtro-campo { width: min(28rem, 60vw); }
.hist-filtro-campo :deep(.p-dropdown-label) { padding: .4rem .6rem; font-size: .76rem; }
.hist-filtros > .hist-info { margin-bottom: .55rem; }
.hist-filtro-status { display: inline-flex; align-items: center; gap: .35rem; margin-bottom: .5rem; font-size: .72rem; color: var(--text-muted); }
.hist-filtro-status--erro { color: var(--risk-critical); }
.hist-body.is-atualizando { opacity: .55; pointer-events: none; transition: opacity .15s ease; }
.hist-meta { display: flex; flex-wrap: wrap; align-items: center; gap: .35rem 1rem; font-size: .74rem; color: var(--text-secondary); }
.hist-info { font-size: .8rem; color: var(--text-muted); opacity: .7; cursor: default; }
.hist-info:hover { opacity: 1; }
.hist-badge { display: inline-flex; align-items: center; gap: .3rem; margin-left: .35rem; padding: .08rem .45rem; border: 1px solid var(--card-border); border-radius: 999px; font-size: .64rem; color: var(--text-secondary); white-space: nowrap; }
.hist-badge--alerta { margin-left: 0; border-color: color-mix(in srgb, var(--risk-critical) 45%, transparent); color: var(--risk-critical); }

.hist-estado { display: flex; align-items: center; justify-content: center; gap: .5rem; min-height: 260px; color: var(--text-muted); font-size: .82rem; }
.hist-estado--erro { color: var(--risk-critical); }

.hist-body { display: flex; flex-direction: column; gap: 1rem; }
.hist-kpis { display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); gap: .65rem; }
.hist-kpi { display: flex; flex-direction: column; gap: .3rem; padding: .65rem .85rem; border: 1px solid var(--card-border); border-radius: 10px; background: color-mix(in srgb, var(--text-color) 3%, transparent); }
.hist-kpi-label { font-size: .62rem; font-weight: 600; letter-spacing: .06em; text-transform: uppercase; color: var(--text-muted); }
.hist-kpi-value { font-size: .92rem; font-weight: 600; color: var(--text-color); }
.hist-kpi-detail { font-size: .66rem; color: var(--text-muted); }

.hist-panel { display: flex; flex-direction: column; gap: .6rem; padding: .85rem 1rem; border: 1px solid var(--card-border); border-radius: 10px; }
.hist-panel-header { display: flex; align-items: baseline; gap: .6rem; flex-wrap: wrap; }
.hist-panel-header h3 { margin: 0; font-size: .82rem; font-weight: 600; color: var(--text-color); }
.hist-panel-sub { font-size: .7rem; color: var(--text-muted); }
.hist-vazio { margin: 0; font-size: .76rem; color: var(--text-muted); }

.hist-atencao { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: .6rem; margin: 0; padding: 0; list-style: none; }
.hist-atencao li { display: flex; gap: .6rem; padding: .55rem .7rem; border-radius: 8px; background: color-mix(in srgb, var(--risk-critical) 7%, transparent); }
.hist-atencao li > i { margin-top: .12rem; color: var(--risk-critical); }
.hist-atencao strong { display: block; font-size: .76rem; font-weight: 600; color: var(--text-color); }
.hist-atencao span { font-size: .72rem; color: var(--text-secondary); }

.hist-legenda { display: flex; flex-wrap: wrap; gap: .35rem 1rem; font-size: .7rem; color: var(--text-secondary); }
.hist-legenda-item { display: inline-flex; align-items: center; gap: .35rem; }
.hist-swatch { display: inline-block; flex-shrink: 0; width: 10px; height: 10px; border-radius: 2px; }
.hist-swatch--linha { height: 2px; border-radius: 1px; }
.hist-swatch--tracejada { height: 0; border-top: 2px dashed var(--text-muted); border-radius: 0; }
.hist-swatch--ponto { width: 8px; height: 8px; border-radius: 50%; background: var(--risk-critical); }
.hist-chart { width: 100%; height: 540px; }
.hist-calor { width: 100%; }
.hist-calor-controle { display: grid; gap: .4rem; align-self: center; width: min(32rem, 100%); padding-top: .55rem; }
.hist-calor-controle-cabecalho { display: flex; align-items: baseline; justify-content: space-between; gap: 1rem; color: var(--text-secondary); font-size: .7rem; font-weight: 600; }
.hist-calor-controle-valor { display: inline-flex; align-items: baseline; gap: .65rem; font-variant-numeric: tabular-nums; }
.hist-calor-controle-instrucao { color: var(--text-muted); font-weight: 400; }
.hist-calor-limpar { padding: 0; border: 0; background: transparent; color: var(--primary-color); font: inherit; font-weight: 500; cursor: pointer; }
.hist-calor-limpar:hover { text-decoration: underline; text-underline-offset: 2px; }
.hist-calor-limpar:focus-visible { outline: 2px solid var(--primary-color); outline-offset: 3px; border-radius: 2px; }
.hist-calor-slider { display: block; width: 100%; height: 24px; margin: 0; appearance: none; -webkit-appearance: none; background: transparent; cursor: ew-resize; }
.hist-calor-slider::-webkit-slider-runnable-track { height: 14px; border-radius: 5px; background: var(--heatmap-gradient); }
.hist-calor-slider::-webkit-slider-thumb { width: 18px; height: 24px; margin-top: -5px; appearance: none; -webkit-appearance: none; border: 2px solid var(--card-bg); border-radius: 6px; background: var(--text-color); box-shadow: 0 1px 4px color-mix(in srgb, var(--text-color) 35%, transparent); }
.hist-calor-slider::-moz-range-track { height: 14px; border-radius: 5px; background: var(--heatmap-gradient); }
.hist-calor-slider::-moz-range-thumb { width: 16px; height: 20px; border: 2px solid var(--card-bg); border-radius: 6px; background: var(--text-color); box-shadow: 0 1px 4px color-mix(in srgb, var(--text-color) 35%, transparent); }
.hist-calor-slider:focus-visible { outline: 2px solid var(--primary-color); outline-offset: 3px; border-radius: 5px; }
.hist-calor-controle-limites { display: flex; justify-content: space-between; gap: 1rem; color: var(--text-muted); font-size: .7rem; font-variant-numeric: tabular-nums; }

.hist-tabela-wrap { overflow-x: auto; overflow-y: hidden; border: 1px solid var(--tabs-border); border-radius: 8px; }
.hist-paginator { font-size: .74rem; }
.hist-tabela { width: 100%; min-width: 75.5rem; table-layout: fixed; border-collapse: collapse; font-size: .74rem; color: var(--text-color-85); }
.hist-tabela .c-nome { width: 20rem; }
.hist-tabela .c-local { width: 10rem; }
.hist-tabela .c-sit { width: 6.5rem; }
.hist-tabela .c-ms { width: 6rem; }
.hist-tabela .c-num { width: 6.5rem; }
.hist-tabela .c-atuacao { width: auto; }
.hist-tabela th { padding: .65rem .7rem; border-bottom: 1px solid color-mix(in srgb, var(--tabs-border) 65%, transparent); background: color-mix(in srgb, var(--text-color) 2%, var(--card-bg)); color: var(--text-muted); font-size: .6rem; font-weight: 600; letter-spacing: .04em; text-align: left; white-space: normal; vertical-align: bottom; }
.hist-tabela th:nth-child(5), .hist-tabela th:nth-child(6) { text-align: right; }
.hist-tabela th .hist-info { margin-left: .2rem; font-size: .66rem; vertical-align: middle; }
.hist-atuacao-erro { display: flex; align-items: center; gap: .4rem; margin: 0; font-size: .74rem; color: var(--risk-critical); }
.hist-tabela td { padding: .7rem .7rem; border-top: 1px solid color-mix(in srgb, var(--tabs-border) 65%, transparent); vertical-align: middle; overflow-wrap: anywhere; }
.hist-tabela td.num { text-align: right; }
.hist-tabela tbody tr { cursor: pointer; transition: background-color .15s ease; }
.hist-tabela tbody tr.is-filtrada { background: color-mix(in srgb, var(--primary-color) 9%, var(--card-bg)); box-shadow: inset 3px 0 0 var(--primary-color); }
.hist-farm-filtrar { display: inline-flex; align-items: center; justify-content: center; flex-shrink: 0; width: 26px; height: 26px; margin-left: auto; padding: 0; border: 1px solid transparent; border-radius: 6px; background: transparent; color: var(--text-muted); cursor: pointer; opacity: .55; transition: opacity .15s ease, border-color .15s ease, color .15s ease; }
.hist-farm-filtrar .pi { font-size: .72rem; }
.hist-tabela tbody tr:hover .hist-farm-filtrar, .hist-farm-filtrar:focus-visible { opacity: 1; }
.hist-farm-filtrar:hover, .hist-farm-filtrar:focus-visible { border-color: color-mix(in srgb, var(--primary-color) 45%, transparent); color: var(--primary-color); outline: none; }
.hist-farm-filtrar.is-ativo { opacity: 1; color: var(--primary-color); border-color: color-mix(in srgb, var(--primary-color) 45%, transparent); background: color-mix(in srgb, var(--primary-color) 10%, transparent); }
.hist-tabela tbody tr:hover, .hist-tabela tbody tr:focus-visible { background: var(--table-hover); outline: none; }
.hist-farm { display: flex; align-items: flex-start; gap: .5rem; }
.hist-farm .hist-swatch { margin-top: .24rem; }
.hist-farm-identidade { display: block; position: relative; min-width: 0; padding-right: .9rem; }
.hist-farm-nome, .hist-farm-cnpj { display: block; }
.hist-farm-nome { color: var(--text-color); font-size: .78rem; font-weight: 600; line-height: 1.35; }
.hist-farm-cnpj { margin-top: .14rem; color: var(--text-muted); font-size: .63rem; font-variant-numeric: tabular-nums; line-height: 1.2; }
.hist-farm-abrir { position: absolute; top: .2rem; right: 0; color: var(--primary-color); font-size: .58rem; opacity: 0; transform: translate(-2px, 2px); transition: opacity .15s ease, transform .15s ease; }
.hist-tabela tbody tr:hover .hist-farm-abrir, .hist-tabela tbody tr:focus-visible .hist-farm-abrir { opacity: 1; transform: none; }
.hist-numero { font-variant-numeric: tabular-nums; white-space: nowrap; }
.hist-participacao-trilha { display: block; width: 100%; height: 3px; margin-top: .32rem; border-radius: 2px; background: color-mix(in srgb, var(--text-color) 9%, transparent); overflow: hidden; }
.hist-participacao-barra { display: block; height: 100%; border-radius: inherit; }

/* Coluna "Atuação na farmácia": copiada de CRMPrescritoresTable.vue. */
.atuacao-cell { vertical-align: middle; }
.atuacao-btn {
  position: relative;
  display: block;
  width: 100%;
  padding: 0.35rem 0.5rem;
  margin: -0.35rem -0.5rem;
  box-sizing: content-box;
  border: 1px solid transparent;
  border-radius: 8px;
  background: transparent;
  color: inherit;
  font: inherit;
  text-align: left;
  cursor: pointer;
  transition: border-color 0.15s ease, background 0.15s ease;
}
.atuacao-btn:disabled { cursor: default; }
.atuacao-btn:not(:disabled):hover,
.atuacao-btn:focus-visible {
  border-color: color-mix(in srgb, var(--primary-color) 45%, transparent);
  background: color-mix(in srgb, var(--primary-color) 5%, transparent);
  outline: none;
}
.atuacao-expand-icon {
  position: absolute;
  top: 0.35rem;
  right: 0.45rem;
  font-size: 0.62rem;
  color: var(--text-muted);
  opacity: 0;
  transition: opacity 0.15s ease;
}
.atuacao-btn:not(:disabled):hover .atuacao-expand-icon,
.atuacao-btn:focus-visible .atuacao-expand-icon,
.atuacao-btn.is-loading .atuacao-expand-icon { opacity: 1; }
.atuacao-btn .atuacao-texto { padding-right: 1rem; }
.atuacao-texto {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 0.5rem;
  margin-bottom: 0.3rem;
  white-space: nowrap;
}
.atuacao-periodo { font-size: 0.76rem; font-weight: 500; color: var(--text-color-85); }
.atuacao-meses { font-size: 0.7rem; color: var(--text-muted); }
.atuacao-spark { display: block; width: 100%; height: 35px; overflow: visible; }
.atuacao-base { stroke: var(--card-border); stroke-width: 0.5; vector-effect: non-scaling-stroke; }
.atuacao-bar { fill: var(--data-color); }
.atuacao-bar.is-p95-leve { fill: var(--p95-leve); }
.atuacao-bar.is-p95-media { fill: var(--p95-media); }
.atuacao-bar.is-p95-forte { fill: var(--p95-forte); }
/* Mês acima do teto de altura (4× o P95): barra cheia com marca no topo. */
.atuacao-corte { fill: var(--text-color); opacity: 0.55; }

.hist-fechar { min-height: 34px; padding: 0 1.1rem; border: 1px solid var(--card-border); border-radius: 8px; background: transparent; color: var(--text-color); font: inherit; font-size: .8rem; font-weight: 500; cursor: pointer; }
.hist-fechar:hover { border-color: var(--primary-color); color: var(--primary-color); }

@media (max-width: 1100px) {
  .hist-kpis { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .hist-atencao { grid-template-columns: 1fr; }
}
</style>
