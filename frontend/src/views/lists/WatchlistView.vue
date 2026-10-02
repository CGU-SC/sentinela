<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { useRouter } from "vue-router";
import { useFarmaciaListsStore } from "@/stores/farmaciaLists";
import { useFilterStore } from "@/stores/filters";
import { useGeoStore } from "@/stores/geo";
import { useNotaTecnicaConfigStore } from "@/stores/notaTecnicaConfig";
import { useFormatting } from "@/composables/useFormatting";
import { useFilterParameters } from "@/composables/useFilterParameters";
import { usePdfExport } from "@/composables/usePdfExport";
import { loadCnpjPdfReportData } from "@/composables/useCnpjPdfReportData";
import { API_ENDPOINTS } from "@/config/api";
import { requestResumo } from "@/stores/analytics";
import { getApiErrorMessage } from "@/utils/apiErrors";
import { convertDocxToPdf, downloadBlobFromResponse } from "@/utils/download";
import { filterActionTooltip } from "@/config/filterTooltipConfig";
import ExportMenuButton from "@/views/components/common/ExportMenuButton.vue";
import ObservationDialog from "@/views/components/cnpj/ObservationDialog.vue";
import EvidenciasPanel from "@/views/components/evidencias/EvidenciasPanel.vue";
import NotaTecnicaRegionalDialog from "@/views/components/nota-tecnica/NotaTecnicaRegionalDialog.vue";
import { useToast } from "primevue/usetoast";
import { useEvidenciasStore } from "@/stores/evidencias";
import { dataHoraCurta } from "@/utils/evidencias";
import { usePeriodoAnalise } from "@/composables/usePeriodoAnalise";
import MonthRangePicker from "@/views/components/common/MonthRangePicker.vue";
import OptionPicker from "@/views/components/common/OptionPicker.vue";
import { analysisTooltip } from "@/config/analysisTooltipConfig";
import { AUDIT_THRESHOLDS } from "@/config/riskConfig";
import { CRM_ALERTA_BADGE_TONS } from "@/config/colors";
import { useMetodologiaConfigStore } from "@/stores/metodologiaConfig";
import { useThemeStore } from "@/stores/theme";

const router = useRouter();
const evidenciasStore = useEvidenciasStore();
const farmaciaLists = useFarmaciaListsStore();
const filterStore = useFilterStore();
const geoStore = useGeoStore();
const notaTecnicaConfig = useNotaTecnicaConfigStore();
const toast = useToast();
const { formatCurrencyFull, formatNumberFull, formatarData, formatTitleCase } = useFormatting();
const { getApiParams } = useFilterParameters();
const { exportCnpjPdf } = usePdfExport();
const watchlistAnalytics = ref([]);
const watchlistLoading = ref(false);
const watchlistError = ref(null);
const showObsDialog = ref(false);
const obsTarget = ref(null);
const copiedCnpj = ref(null);
const exportingReportCnpj = ref(null);
const generatingNoteCnpj = ref(null);
const regionalDialogVisible = ref(false);
const pendingNoteItem = ref(null);

const formatCnpj = (v) => {
  if (!v) return "—";
  const clean = v.replace(/\D/g, "");
  if (clean.length !== 14) return v;
  return clean.replace(/^(\d{2})(\d{3})(\d{3})(\d{4})(\d{2})$/, "$1.$2.$3/$4-$5");
};

const formatDate = (iso) => {
  if (!iso) return "—";
  return new Date(iso).toLocaleDateString("pt-BR", {
    day: "2-digit", month: "2-digit", year: "numeric",
  });
};

const formatPeriodMonth = (date) => {
  const value = date instanceof Date ? date : new Date(date);
  if (Number.isNaN(value.getTime())) return "—";

  const months = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"];
  return `${months[value.getMonth()]}/${value.getFullYear()}`;
};

const monitoredCnpjs = computed(() =>
  farmaciaLists.interesse.map((item) => item.cnpj).filter(Boolean),
);

const monitoredCnpjsKey = computed(() => monitoredCnpjs.value.join("|"));
const periodKey = computed(() =>
  Array.isArray(filterStore.periodo)
    ? filterStore.periodo.map((date) => date?.getTime?.() ?? String(date ?? "")).join("|")
    : "",
);
// Chip de período: o mesmo seletor do filtro "Período de análise" da sidebar.
const {
  PERIODO_MIN,
  PERIODO_MAX,
  periodoAtalhos,
  periodoSelecionado,
  periodoAtalhoAtivo,
  aplicarPeriodo,
  aplicarAtalhoPeriodo,
} = usePeriodoAnalise();

const periodoAnaliseLabel = computed(() => {
  const [inicio, fim] = Array.isArray(filterStore.periodo) ? filterStore.periodo : [];
  if (!inicio || !fim) return "Período não definido";

  return `${formatPeriodMonth(inicio)} - ${formatPeriodMonth(fim)}`;
});

async function fetchWatchlistAnalytics() {
  if (!monitoredCnpjs.value.length) {
    watchlistAnalytics.value = [];
    watchlistError.value = null;
    return;
  }

  const { inicio, fim } = getApiParams();
  const params = { cnpjs: [...monitoredCnpjs.value] };
  if (inicio) params.data_inicio = inicio;
  if (fim) params.data_fim = fim;

  watchlistLoading.value = true;
  watchlistError.value = null;
  try {
    // Seção cnpjs só com os CNPJs monitorados (o backend exige o filtro).
    const data = await requestResumo(params, ["cnpjs"]);
    watchlistAnalytics.value = data.resultado_cnpjs;
  } catch (error) {
    console.error("Erro ao buscar dados da lista de interesse:", error);
    watchlistAnalytics.value = [];
    watchlistError.value = "Não foi possível carregar os indicadores da lista.";
  } finally {
    watchlistLoading.value = false;
  }
}

watch([monitoredCnpjsKey, periodKey], fetchWatchlistAnalytics, { immediate: true });

function isPreferencesUnavailable(error) {
  return error?.response?.status === 503 && error?.config?.url === API_ENDPOINTS.preferences;
}

async function carregarRegional({ force = false, reportarErroPreferencias = false } = {}) {
  try {
    await notaTecnicaConfig.ensureLoaded({ force });
  } catch (error) {
    // O aviso persistente das preferências já explica esta mesma falha.
    if (isPreferencesUnavailable(error) && !reportarErroPreferencias) return;
    toast.add({
      severity: "warn",
      summary: "Regional da Nota Técnica",
      detail: isPreferencesUnavailable(error)
        ? "Não foi possível carregar a regional porque as preferências continuam indisponíveis."
        : error?.response?.data?.detail || "Não foi possível carregar a configuração da Nota Técnica.",
      life: 6000,
    });
  }
}

onMounted(() => {
  farmaciaLists.loadRecoveryOptions();
  carregarRegional();
});

// Map O(1): cnpj → dados analíticos da consulta dedicada da lista
const analyticsMap = computed(() => {
  const map = new Map();
  for (const e of watchlistAnalytics.value) {
    map.set(e.cnpj, e);
  }
  return map;
});

// Classificação de risco da matriz (matriz_risco_dinamica): CRÍTICO, ATENÇÃO ou NORMAL.
// "Sem dados" agrupa as farmácias sem movimentação no período.
const CLASSES_RISCO = Object.freeze([
  { value: 'CRÍTICO', label: 'Crítico', cor: 'var(--risk-critical)' },
  { value: 'ATENÇÃO', label: 'Atenção', cor: 'var(--risk-medium)' },
  { value: 'NORMAL', label: 'Normal', cor: 'var(--risk-indicator-normal)' },
  { value: 'SEM_DADOS', label: 'Sem dados', cor: 'var(--text-muted)' },
]);
const CLASSE_POR_VALOR = new Map(CLASSES_RISCO.map((c) => [c.value, c]));
function classeDaFarmacia(item) {
  if (item.classificacao) {
    if (!CLASSE_POR_VALOR.has(item.classificacao)) {
      throw new Error(`Classificação de risco desconhecida: ${item.classificacao}`);
    }
    return item.classificacao;
  }
  return 'SEM_DADOS';
}
function corDaClasse(classificacao) {
  return CLASSE_POR_VALOR.get(classificacao)?.cor ?? 'var(--text-muted)';
}
function faixaPerc(valor) {
  return valor >= 50 ? 'is-alto' : valor >= 20 ? 'is-medio' : 'is-baixo';
}

// Lista enriquecida — une store + analytics + geo
const listaEnriquecida = computed(() =>
  farmaciaLists.interesse.map((item) => {
    const a = analyticsMap.value.get(item.cnpj) ?? {};
    return {
      ...item,
      razaoSocial:    item.razaoSocial || a.razao_social || '—',
      municipio:      a.municipio || '—',
      uf:             a.uf || '—',
      percValSemComp: a.percValSemComp ?? null,
      scoreRisco:     a.score_risco_final ?? null,
      classificacao:  a.classificacao_risco ?? null,
      totalMov:       a.totalMov ?? null,
      valSemComp:     a.valSemComp ?? null,
    };
  })
);

// ── Ordenação da tabela ──────────────────────────────────────────────────────
// Colunas ordenáveis: `valor` devolve o que comparar (texto ou número; null = sem
// dado, sempre no fim); `inicial` é o sentido do primeiro clique (números e datas
// começam do maior para o menor). Sem coluna escolhida (3º clique) vale a ordem da lista.
const COLUNAS_ORDENAVEIS = Object.freeze({
  estabelecimento: { valor: (item) => (item.razaoSocial === '—' ? null : item.razaoSocial), inicial: 'asc' },
  localizacao: { valor: (item) => (item.municipio === '—' ? null : `${item.municipio} ${item.uf}`), inicial: 'asc' },
  risco: { valor: (item) => item.scoreRisco, inicial: 'desc' },
  percentual: { valor: (item) => item.percValSemComp, inicial: 'desc' },
  valSemComp: { valor: (item) => item.valSemComp, inicial: 'desc' },
  totalMov: { valor: (item) => item.totalMov, inicial: 'desc' },
  evidencias: { valor: (item) => evidenciasStore.contar(item.cnpj), inicial: 'desc' },
  adicionadoEm: { valor: (item) => (item.adicionadoEm ? new Date(item.adicionadoEm).getTime() : null), inicial: 'desc' },
});
// Padrão: maior valor sem comprovação primeiro, para os piores casos abrirem a lista.
const ordenacao = ref({ coluna: 'valSemComp', sentido: 'desc' });
const comparadorTexto = new Intl.Collator('pt-BR', { sensitivity: 'base', numeric: true });

/** 1º clique: sentido inicial da coluna; 2º: inverte; 3º: volta à ordem da lista. */
function ordenarPor(coluna) {
  const config = COLUNAS_ORDENAVEIS[coluna];
  if (!config) throw new Error(`Coluna não ordenável: ${coluna}`);
  const atual = ordenacao.value;
  if (atual.coluna !== coluna) {
    ordenacao.value = { coluna, sentido: config.inicial };
  } else if (atual.sentido === config.inicial) {
    ordenacao.value = { coluna, sentido: config.inicial === 'asc' ? 'desc' : 'asc' };
  } else {
    ordenacao.value = { coluna: null, sentido: null };
  }
}

function ariaOrdenacao(coluna) {
  if (ordenacao.value.coluna !== coluna) return 'none';
  return ordenacao.value.sentido === 'asc' ? 'ascending' : 'descending';
}

function iconeOrdenacao(coluna) {
  if (ordenacao.value.coluna !== coluna) return 'pi-sort-alt';
  return ordenacao.value.sentido === 'asc' ? 'pi-sort-amount-up-alt' : 'pi-sort-amount-down';
}

const listaOrdenada = computed(() => {
  const { coluna, sentido } = ordenacao.value;
  if (!coluna) return listaEnriquecida.value;
  const { valor } = COLUNAS_ORDENAVEIS[coluna];
  const fator = sentido === 'asc' ? 1 : -1;
  // Valor calculado uma vez por linha; a ordem da lista desempata (ordenação estável).
  return listaEnriquecida.value
    .map((item, indice) => ({ item, indice, chave: valor(item) }))
    .sort((a, b) => {
      if (a.chave == null || b.chave == null) {
        if (a.chave == null && b.chave == null) return a.indice - b.indice;
        return a.chave == null ? 1 : -1; // sem dado sempre no fim
      }
      const comparacao = typeof a.chave === 'string'
        ? comparadorTexto.compare(a.chave, b.chave)
        : a.chave - b.chave;
      return comparacao !== 0 ? comparacao * fator : a.indice - b.indice;
    })
    .map((entrada) => entrada.item);
});

const totalBadge = computed(() => farmaciaLists.interesse.length);

// Destaque de alto valor sem comprovação: mesmo limite (configuração metodológica)
// e mesma cor da coluna "Sem comprovar" de /estabelecimentos.
const metodologiaConfig = useMetodologiaConfigStore();
const themeStore = useThemeStore();
const auditHighValue = computed(() =>
  metodologiaConfig.loaded ? metodologiaConfig.auditHighValue : AUDIT_THRESHOLDS.HIGH_VALUE,
);
const alertaCorVars = computed(() => ({
  "--alerta-cor": CRM_ALERTA_BADGE_TONS[themeStore.isDark ? "dark" : "light"].cor,
}));
onMounted(() => {
  metodologiaConfig.ensureLoaded().catch((error) => {
    console.warn("[WatchlistView] Não foi possível carregar a configuração metodológica.", error);
  });
});
const listaPronta = computed(() => farmaciaLists.loadState === "ready" && totalBadge.value > 0);
const tituloTooltip = analysisTooltip("listaInteresse");

// ── Busca, filtros e agrupamento (sobre os dados já carregados) ─────────────
const busca = ref("");
const campoBusca = ref(null);
const filtroClasses = ref([]);
const filtroUf = ref(null);
const soComEvidencias = ref(false);
const soComObservacao = ref(false);
const agruparPor = ref(null);
const densidade = ref("confortavel");

const AGRUPAMENTOS = Object.freeze([
  { value: null, label: "Sem agrupamento" },
  { value: "uf", label: "UF" },
  { value: "classificacao", label: "Classificação de risco" },
]);

const normalizarTexto = (texto) => String(texto ?? "")
  .normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase();

const temFiltro = computed(() => Boolean(
  busca.value.trim() || filtroClasses.value.length || filtroUf.value
  || soComEvidencias.value || soComObservacao.value,
));

function limparFiltros() {
  busca.value = "";
  filtroClasses.value = [];
  filtroUf.value = null;
  soComEvidencias.value = false;
  soComObservacao.value = false;
}

function alternarClasse(valor) {
  filtroClasses.value = filtroClasses.value.includes(valor)
    ? filtroClasses.value.filter((v) => v !== valor)
    : [...filtroClasses.value, valor];
}

const opcoesUf = computed(() => {
  const ufs = [...new Set(listaEnriquecida.value.map((item) => item.uf).filter((uf) => uf && uf !== "—"))].sort();
  return [{ value: null, label: "Todas as UFs" }, ...ufs.map((uf) => ({ value: uf, label: uf }))];
});

// Contagem por classificação sobre a lista inteira (os chips mostram o todo, não o recorte).
const composicaoRisco = computed(() => {
  const qtd = new Map(CLASSES_RISCO.map((c) => [c.value, 0]));
  if (!watchlistLoading.value) {
    for (const item of listaEnriquecida.value) qtd.set(classeDaFarmacia(item), qtd.get(classeDaFarmacia(item)) + 1);
  }
  return CLASSES_RISCO.map((c) => ({ ...c, qtd: qtd.get(c.value) }));
});

const listaFiltrada = computed(() => {
  const termo = normalizarTexto(busca.value.trim());
  const digitos = busca.value.replace(/\D/g, "");
  return listaOrdenada.value.filter((item) => {
    if (filtroClasses.value.length && !filtroClasses.value.includes(classeDaFarmacia(item))) return false;
    if (filtroUf.value && item.uf !== filtroUf.value) return false;
    if (soComEvidencias.value && !evidenciasStore.contar(item.cnpj)) return false;
    if (soComObservacao.value && !item.observacao) return false;
    if (!termo) return true;
    if (digitos.length >= 3 && item.cnpj.includes(digitos)) return true;
    return normalizarTexto(`${item.razaoSocial} ${item.municipio} ${item.uf} ${item.observacao ?? ""}`).includes(termo);
  });
});

// Linhas da tabela: farmácias e, com agrupamento, uma linha de grupo (com subtotal) antes de cada grupo.
const linhasTabela = computed(() => {
  const linhas = [];
  const farmacia = (item, posicao) => ({ tipo: "farmacia", chave: item.cnpj, item, posicao });
  if (!agruparPor.value) {
    listaFiltrada.value.forEach((item, i) => linhas.push(farmacia(item, i + 1)));
    return linhas;
  }
  const chaveDoGrupo = agruparPor.value === "uf"
    ? (item) => (item.uf && item.uf !== "—" ? item.uf : "Sem UF")
    : (item) => classeDaFarmacia(item);
  const grupos = new Map();
  for (const item of listaFiltrada.value) {
    const chave = chaveDoGrupo(item);
    if (!grupos.has(chave)) grupos.set(chave, []);
    grupos.get(chave).push(item);
  }
  const ordem = agruparPor.value === "uf"
    ? [...grupos.keys()].sort((a, b) => (a === "Sem UF") - (b === "Sem UF") || a.localeCompare(b, "pt-BR"))
    : CLASSES_RISCO.map((c) => c.value).filter((v) => grupos.has(v));
  let posicao = 0;
  for (const chave of ordem) {
    const itens = grupos.get(chave);
    const comDados = itens.filter((item) => item.valSemComp != null);
    linhas.push({
      tipo: "grupo",
      chave: `grupo:${chave}`,
      rotulo: agruparPor.value === "uf" ? chave : CLASSE_POR_VALOR.get(chave).label,
      qtd: itens.length,
      valSemComp: comDados.length ? comDados.reduce((soma, item) => soma + Number(item.valSemComp), 0) : null,
    });
    for (const item of itens) linhas.push(farmacia(item, ++posicao));
  }
  return linhas;
});

// Visão de trabalho de cada auditor (ordenação, filtros, agrupamento e densidade),
// lembrada neste navegador. A busca não é lembrada: cada visita começa sem texto.
const VISAO_STORAGE = "sentinela_listas_visao";
function restaurarVisao() {
  let salva = null;
  try { salva = JSON.parse(localStorage.getItem(VISAO_STORAGE) ?? "null"); } catch { return; }
  if (!salva || typeof salva !== "object") return;
  if (salva.ordenacao?.coluna === null || COLUNAS_ORDENAVEIS[salva.ordenacao?.coluna]) {
    if (salva.ordenacao.coluna === null || ["asc", "desc"].includes(salva.ordenacao.sentido)) {
      ordenacao.value = { coluna: salva.ordenacao.coluna, sentido: salva.ordenacao.coluna === null ? null : salva.ordenacao.sentido };
    }
  }
  if (Array.isArray(salva.filtroClasses)) filtroClasses.value = salva.filtroClasses.filter((v) => CLASSE_POR_VALOR.has(v));
  if (typeof salva.filtroUf === "string") filtroUf.value = salva.filtroUf;
  soComEvidencias.value = salva.soComEvidencias === true;
  soComObservacao.value = salva.soComObservacao === true;
  if (AGRUPAMENTOS.some((a) => a.value === salva.agruparPor)) agruparPor.value = salva.agruparPor;
  if (["confortavel", "compacta"].includes(salva.densidade)) densidade.value = salva.densidade;
}
restaurarVisao();
watch([ordenacao, filtroClasses, filtroUf, soComEvidencias, soComObservacao, agruparPor, densidade], () => {
  const visao = {
    ordenacao: ordenacao.value,
    filtroClasses: filtroClasses.value,
    filtroUf: filtroUf.value,
    soComEvidencias: soComEvidencias.value,
    soComObservacao: soComObservacao.value,
    agruparPor: agruparPor.value,
    densidade: densidade.value,
  };
  try { localStorage.setItem(VISAO_STORAGE, JSON.stringify(visao)); } catch { /* preferência só do navegador */ }
}, { deep: true });

// UF salva que não existe mais na lista: o filtro é solto em vez de esconder tudo.
watch(opcoesUf, (opcoes) => {
  if (filtroUf.value && !watchlistLoading.value && listaEnriquecida.value.some((i) => i.uf !== "—")
    && !opcoes.some((o) => o.value === filtroUf.value)) filtroUf.value = null;
});

// Atalho "/" foca a busca (fora de campos de texto).
function atalhoBusca(evento) {
  if (evento.key !== "/" || evento.ctrlKey || evento.metaKey || evento.altKey) return;
  const alvo = evento.target;
  if (alvo instanceof HTMLElement && (alvo.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(alvo.tagName))) return;
  if (!campoBusca.value) return;
  evento.preventDefault();
  campoBusca.value.focus();
}
onMounted(() => window.addEventListener("keydown", atalhoBusca));
onBeforeUnmount(() => window.removeEventListener("keydown", atalhoBusca));

// ── Exportação da lista (Excel / CSV) ────────────────────────────────────────
// O arquivo é montado no backend a partir da lista salva e do período de análise:
// mesmos números da tabela, ordenados pelo valor sem comprovação.
const exportLoading = ref(false);
const EXPORT_FORMATS = Object.freeze({
  xlsx: { label: "Excel", extension: "xlsx", icon: "pi-file-excel" },
  csv: { label: "CSV", extension: "csv", icon: "pi-file" },
});
const exportTooltip = filterActionTooltip(
  "Exportar farmácias monitoradas",
  "Baixa a lista com os números do período de análise, ordenada pelo valor sem comprovação. O Excel traz a planilha formatada, com totais e a aba de critérios; o CSV traz só os dados.",
  "pi-download",
);
const exportacao = computed(() => {
  const { inicio, fim } = getApiParams();
  const pronta = farmaciaLists.loadState === "ready";
  const motivo = !pronta
    ? "Lista indisponível."
    : !totalBadge.value
      ? "Nenhuma farmácia na lista."
      : !inicio || !fim
        ? "Período de análise não definido."
        : `Lista de ${totalBadge.value} ${totalBadge.value === 1 ? "farmácia" : "farmácias"} no período de análise.`;
  return {
    itens: [{
      label: `Farmácias monitoradas (${formatNumberFull(totalBadge.value)})`,
      items: [
        { label: "Excel (.xlsx) · planilha formatada", icon: "pi pi-file-excel", command: () => exportarLista("xlsx") },
        { label: "CSV (.csv) · texto simples", icon: "pi pi-file", command: () => exportarLista("csv") },
      ],
    }],
    carregando: exportLoading.value,
    desabilitado: !pronta || !totalBadge.value || !inicio || !fim,
    motivo,
    tooltip: exportTooltip,
  };
});

async function exportarLista(formato) {
  if (exportLoading.value) return;
  const format = EXPORT_FORMATS[formato];
  if (!format) throw new Error(`Formato de exportação desconhecido: ${formato}`);
  const { inicio, fim } = getApiParams();
  if (!inicio || !fim) throw new Error("Exportação da lista sem período de análise.");
  exportLoading.value = true;
  try {
    const response = await fetch(API_ENDPOINTS.analyticsListaInteresseExport, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ formato, data_inicio: inicio, data_fim: fim }),
    });
    if (!response.ok) {
      throw new Error(
        await getApiErrorMessage(response, `Falha HTTP ${response.status} ao gerar o ${format.label} da lista.`),
      );
    }
    const downloadResult = await downloadBlobFromResponse(response, `farmacias_monitoradas.${format.extension}`);
    if (downloadResult?.desktop) {
      toast.add({
        group: "download",
        severity: "success",
        summary: `${format.label} da lista salvo`,
        detail: `Arquivo salvo em notas_tecnicas\\${downloadResult.filename}.`,
        data: { path: downloadResult.path, icon: format.icon },
      });
    } else {
      toast.add({ severity: "success", summary: `${format.label} da lista baixado`, detail: downloadResult?.filename, life: 4000 });
    }
  } catch (error) {
    toast.add({ severity: "error", summary: "Falha na exportação", detail: error.message || `Não foi possível salvar o ${format.label}.`, life: 7000 });
  } finally {
    exportLoading.value = false;
  }
}

/**
 * Totalizador da lista no período de análise. Soma só as farmácias com dados no
 * período: as demais ficam fora e a faixa avisa quantas entraram, para o total
 * nunca parecer completo quando não é. Sem indicadores (carregando ou erro) os
 * valores ficam nulos e a faixa mostra "—", nunca zero.
 */
const totaisLista = computed(() => {
  const total = listaFiltrada.value.length;
  if (watchlistLoading.value || watchlistError.value) {
    return { total, comDados: null, totalMov: null, valSemComp: null, perc: null };
  }
  let comDados = 0;
  let totalMov = 0;
  let valSemComp = 0;
  for (const item of listaFiltrada.value) {
    if (item.totalMov == null || item.valSemComp == null) continue;
    comDados += 1;
    totalMov += Number(item.totalMov);
    valSemComp += Number(item.valSemComp);
  }
  if (!comDados) return { total, comDados, totalMov: null, valSemComp: null, perc: null };
  return { total, comDados, totalMov, valSemComp, perc: totalMov > 0 ? (valSemComp / totalMov) * 100 : null };
});
const regionalLabel = computed(() => {
  if (farmaciaLists.loadState === 'error') return 'Regional da NT indisponível';
  if (!notaTecnicaConfig.loaded) return notaTecnicaConfig.loading
    ? 'Carregando regional da NT...'
    : 'Regional da NT indisponível';
  return notaTecnicaConfig.selectedRegionalLabel || 'Regional da NT não definida';
});

async function tentarCarregarNovamente() {
  await farmaciaLists.loadFromBackend();
  if (farmaciaLists.loadState === 'ready') {
    await carregarRegional({ force: true, reportarErroPreferencias: true });
  }
}

function remover(cnpj) {
  farmaciaLists.toggleInteresse(cnpj, "");
}

function descricaoCopia(source) {
  const copy = farmaciaLists.recoveryOptions[source];
  const evidence = copy.evidencias_count === null
    ? 'somente a lista'
    : `${copy.evidencias_count} evidência(s) no backup de evidências`;
  return `${copy.watchlist_count} farmácia(s), ${evidence}`;
}

async function restaurarArquivo(source) {
  const copy = farmaciaLists.recoveryOptions[source];
  const includeEvidenceBackup = copy.evidencias_backup_valid;
  const cestaIlegivel = Boolean(farmaciaLists.recoveryOptions.principal?.evidencias_error);
  const details = !includeEvidenceBackup
    ? 'Esta cópia restaura somente a lista. Ela não recupera evidências; as evidências atuais serão mantidas.'
    : cestaIlegivel
      ? 'A cesta de evidências atual não pôde ser lida: ela será arquivada e substituída pelo backup de evidências, que pode ser de outro momento.'
      : 'As evidências ausentes serão recuperadas do backup de evidências, que pode ser de outro momento. As evidências atuais serão mantidas.';
  // Cópia separada: farmácias com evidências atuais que não estão na cópia continuam na lista.
  const mantidas = copy.farmacias_mantidas_count > 0
    ? ` ${copy.farmacias_mantidas_count} farmácia(s) com evidências atuais que não estão nesta cópia continuarão na lista.`
    : '';
  if (window.confirm(`Restaurar ${descricaoCopia(source)}? ${details}${mantidas} Os arquivos atuais serão preservados antes da restauração.`)) {
    if (await farmaciaLists.restoreFromFile(source, includeEvidenceBackup)) {
      await carregarRegional({ force: true, reportarErroPreferencias: true });
    }
  }
}

function nomeRemovida(item) {
  return item.razaoSocial ? formatTitleCase(item.razaoSocial) : formatCnpj(item.cnpj);
}

async function desfazerRemocao(item) {
  if (await farmaciaLists.desfazerRemocao(item.cnpj)) {
    toast.add({
      severity: "success",
      summary: "Remoção desfeita",
      detail: item.evidencias_count > 0
        ? `${nomeRemovida(item)} voltou à lista com ${item.evidencias_count} evidência(s).`
        : `${nomeRemovida(item)} voltou à lista.`,
      life: 4000,
    });
  }
}

async function restaurarLocal() {
  if (window.confirm(`Restaurar ${farmaciaLists.localSnapshot.length} farmácia(s) da cópia local desta janela? Esta cópia contém somente a lista e não recupera evidências.`)) {
    if (await farmaciaLists.restoreFromLocal()) {
      await carregarRegional({ force: true, reportarErroPreferencias: true });
    }
  }
}

function abrirEstabelecimento(cnpj) {
  router.push(`/estabelecimentos/${cnpj}`);
}

async function copyCnpj(cnpj) {
  await navigator.clipboard.writeText(cnpj);
  copiedCnpj.value = cnpj;
  window.setTimeout(() => {
    if (copiedCnpj.value === cnpj) copiedCnpj.value = null;
  }, 1400);
}

async function gerarRelatorio(item) {
  if (exportingReportCnpj.value) return;

  exportingReportCnpj.value = item.cnpj;
  try {
    const { inicio, fim, volumeAtipicoPercentual } = getApiParams();
    const payload = await loadCnpjPdfReportData({
      cnpj: item.cnpj,
      inicio,
      fim,
      volumeAtipicoPercentual,
      geoStore,
      formatTitleCase,
      formatarData,
    });

    const downloadResult = await exportCnpjPdf({
      ...payload,
      geoStore,
      formatCurrencyFull,
      formatNumberFull,
      formatarData,
    });
    if (downloadResult?.desktop) {
      toast.add({
        group: "download",
        severity: "success",
        summary: "Relatório PDF salvo",
        detail: `Arquivo salvo em notas_tecnicas\\${downloadResult.filename}.`,
        data: { path: downloadResult.path, previewPath: downloadResult.path },
      });
    }
  } catch (error) {
    console.error("Erro ao gerar Relatório PDF:", error);
    toast.add({
      severity: "error",
      summary: "Erro ao gerar Relatório PDF",
      detail: error?.message || "Não foi possível gerar o arquivo.",
      life: 8000,
    });
  } finally {
    exportingReportCnpj.value = null;
  }
}

function buildNotaTecnicaUrl(cnpj, dadosNota = {}) {
  const { inicio, fim } = getApiParams();
  const params = new URLSearchParams({
    data_inicio: inicio,
    data_fim: fim,
    regional_codigo: notaTecnicaConfig.selectedRegionalCodigo,
  });
  if (dadosNota.numeroNota) params.set("numero_nota", dadosNota.numeroNota);
  if (dadosNota.numeroProcesso) params.set("numero_processo", dadosNota.numeroProcesso);
  if (dadosNota.assinantesTecnicos?.length) {
    params.set("assinantes_tecnicos", JSON.stringify(dadosNota.assinantesTecnicos));
  }
  return `${API_ENDPOINTS.analyticsNotaTecnica(cnpj)}?${params.toString()}`;
}

async function gerarNotaTecnica(item, { skipRegionalCheck = false, dadosNota = {} } = {}) {
  if (generatingNoteCnpj.value) return;

  try {
    if (!skipRegionalCheck) {
      await notaTecnicaConfig.ensureLoaded();
      pendingNoteItem.value = item;
      regionalDialogVisible.value = true;
      return;
    }

    generatingNoteCnpj.value = item.cnpj;
    const url = buildNotaTecnicaUrl(item.cnpj, dadosNota);
    const response = await fetch(url);
    if (!response.ok) {
      throw new Error(
        await getApiErrorMessage(response, "Erro ao gerar nota técnica"),
      );
    }

    const downloadResult = await downloadBlobFromResponse(response, `Nota_Tecnica_${item.cnpj}.docx`);
    if (downloadResult?.desktop) {
      let previewPath = null;
      if (dadosNota.gerarPdf !== false) {
        try {
          const previewResult = await convertDocxToPdf(downloadResult.path);
          previewPath = previewResult.path;
        } catch (error) {
          toast.add({
            severity: "warn",
            summary: "Pre-visualizacao indisponivel",
            detail: error?.message || "A Nota Tecnica foi salva, mas nao foi possivel gerar a versao PDF para visualizacao.",
            life: 12000,
          });
        }
      }

      toast.add({
        group: "download",
        severity: "success",
        summary: "Nota Técnica salva",
        detail: `Arquivo salvo em notas_tecnicas\\${downloadResult.filename}.`,
        data: { path: downloadResult.path, previewPath },
      });
    }
  } catch (error) {
    console.error("Erro ao gerar Nota Técnica:", error);
    toast.add({
      severity: "error",
      summary: "Erro ao gerar Nota Técnica",
      detail: error?.message || "Não foi possível gerar o arquivo.",
      life: 8000,
    });
  } finally {
    generatingNoteCnpj.value = null;
  }
}

async function onRegionalSavedForList(dadosNota) {
  if (!pendingNoteItem.value) return;
  const item = pendingNoteItem.value;
  pendingNoteItem.value = null;
  await gerarNotaTecnica(item, { skipRegionalCheck: true, dadosNota });
}

function setRegionalDialogVisible(visible) {
  regionalDialogVisible.value = visible;
  if (!visible) pendingNoteItem.value = null;
}

// ── Evidências: o painel da farmácia abre pela coluna "Evidências" da tabela ──
const painelEvidCnpj = ref(null);

onMounted(() => {
  evidenciasStore.painelAberto = false;
  evidenciasStore.garantirCarregado();
});

const nomePorCnpj = computed(() => {
  const map = new Map();
  for (const item of listaEnriquecida.value) map.set(item.cnpj, item.razaoSocial);
  return map;
});

function nomeFarmacia(cnpj) {
  const nome = nomePorCnpj.value.get(cnpj);
  return nome && nome !== "—" ? nome : formatCnpj(cnpj);
}

function abrirEvidenciasDaFarmacia(cnpj) {
  painelEvidCnpj.value = cnpj;
  evidenciasStore.painelAberto = true;
}

function editarObservacao(item) {
  obsTarget.value = item;
  showObsDialog.value = true;
}

function formatPerc(v) {
  if (v == null) return '—';
  return `${Number(v).toLocaleString('pt-BR', { minimumFractionDigits: 1, maximumFractionDigits: 1 })}%`;
}

function formatScore(v) {
  if (v == null) return '—';
  return Number(v).toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}
</script>

<template>
  <div class="lists-view">
    <!-- Barra de comando: título, período e exportação numa linha só -->
    <header class="lists-barra">
      <div class="lists-titulo">
        <i class="pi pi-bookmark" aria-hidden="true" />
        <h2>Farmácias monitoradas</h2>
        <span v-if="totalBadge > 0" class="lists-contagem">{{ formatNumberFull(totalBadge) }}</span>
        <i
          class="pi pi-info-circle help-icon"
          role="img"
          tabindex="0"
          aria-label="Sobre as farmácias monitoradas"
          v-tooltip.bottom="tituloTooltip"
        />
      </div>
      <div class="lists-barra-acoes">
        <span v-if="watchlistLoading" class="lists-estado" role="status">
          <i class="pi pi-spin pi-spinner" aria-hidden="true" /> Atualizando indicadores…
        </span>
        <span v-else-if="watchlistError" class="lists-estado lists-estado--erro" role="alert">
          <i class="pi pi-exclamation-circle" aria-hidden="true" /> {{ watchlistError }}
          <button type="button" class="lists-link" @click="fetchWatchlistAnalytics">Tentar de novo</button>
        </span>
        <span class="period-chip-picker" v-tooltip.bottom="'Período de análise · clique para alterar'">
          <MonthRangePicker
            :rotulo="`Período: ${periodoAnaliseLabel}`"
            :inicio="periodoSelecionado.inicio"
            :fim="periodoSelecionado.fim"
            :min="PERIODO_MIN"
            :max="PERIODO_MAX"
            :atalhos="periodoAtalhos"
            :atalho-ativo="periodoAtalhoAtivo"
            @select-range="aplicarPeriodo"
            @select-atalho="aplicarAtalhoPeriodo"
          />
        </span>
        <ExportMenuButton :exportacao="exportacao" menu-id="lista-interesse-export-menu" />
      </div>
    </header>

    <div v-if="farmaciaLists.ultimaRemocao.length || farmaciaLists.ultimaRemocaoError" class="lists-undo" role="status">
      <i class="pi pi-undo" aria-hidden="true" />
      <span v-if="farmaciaLists.ultimaRemocaoError">{{ farmaciaLists.ultimaRemocaoError }}</span>
      <template v-else>
        <span v-for="item in farmaciaLists.ultimaRemocao" :key="item.cnpj" class="lists-undo-item">
          {{ nomeRemovida(item) }} removida da lista{{ item.evidencias_count ? ` (${item.evidencias_count} evidência(s))` : '' }}.
          <button type="button" class="lists-undo-btn" :disabled="!farmaciaLists.canEdit"
            @click="desfazerRemocao(item)">Desfazer</button>
        </span>
      </template>
    </div>

    <section v-if="farmaciaLists.loadState === 'error' || farmaciaLists.error || farmaciaLists.recoveryError ||
      farmaciaLists.localRecoveryAvailable || farmaciaLists.recoveryAvailable"
      class="preferences-recovery" aria-label="Estado das Farmácias Monitoradas">
      <div class="preferences-recovery-copy">
        <i class="pi pi-shield" aria-hidden="true" />
        <div>
          <p v-if="farmaciaLists.loadState === 'error'">Não foi possível abrir sua lista. Nenhum favorito foi apagado por esta tela.</p>
          <p v-else-if="farmaciaLists.error">{{ farmaciaLists.error }}</p>
          <p v-else-if="farmaciaLists.recoveryError">{{ farmaciaLists.recoveryError }}</p>
          <p v-else>Há cópias da sua lista e das evidências disponíveis para conferência e recuperação.</p>
          <p v-if="farmaciaLists.recoveryOptions?.principal?.evidencias_error">
            Não foi possível conferir as evidências atuais: {{ farmaciaLists.recoveryOptions.principal.evidencias_error }}
          </p>
          <template v-for="source in ['backup', 'corrupt']" :key="source">
            <p v-if="farmaciaLists.recoveryOptions?.[source]?.error || farmaciaLists.recoveryOptions?.[source]?.evidencias_error">
              Cópia {{ source === 'backup' ? 'de segurança' : 'isolada' }} indisponível ou incompleta:
              {{ farmaciaLists.recoveryOptions[source].error || farmaciaLists.recoveryOptions[source].evidencias_error }}
            </p>
          </template>
          <span>A restauração só acontece após sua confirmação. Os arquivos atuais são preservados.</span>
        </div>
      </div>
      <div class="preferences-recovery-actions">
        <button v-if="farmaciaLists.loadState === 'error'" type="button" :disabled="farmaciaLists.saving"
          @click="tentarCarregarNovamente">Tentar carregar novamente</button>
        <button v-if="farmaciaLists.recoveryOptions?.backup?.valid && farmaciaLists.recoveryOptions.backup.watchlist_count > 0"
          type="button" :disabled="farmaciaLists.saving"
          @click="restaurarArquivo('backup')">
          Restaurar backup ({{ descricaoCopia('backup') }})
        </button>
        <button v-if="farmaciaLists.recoveryOptions?.corrupt?.valid && farmaciaLists.recoveryOptions.corrupt.watchlist_count > 0"
          type="button" :disabled="farmaciaLists.saving"
          @click="restaurarArquivo('corrupt')">
          Restaurar cópia isolada ({{ descricaoCopia('corrupt') }})
        </button>
        <button v-if="farmaciaLists.localRecoveryAvailable && farmaciaLists.loadState === 'ready'"
          type="button" :disabled="farmaciaLists.saving" @click="restaurarLocal">
          Restaurar cópia local ({{ farmaciaLists.localSnapshot.length }})
        </button>
      </div>
    </section>

    <div class="lists-card" :class="{ 'is-compacta': densidade === 'compacta' }" :style="alertaCorVars">
      <template v-if="listaPronta">
        <!-- Totais do recorte exibido + composição por classificação de risco (clicável) -->
        <div class="lists-totais" role="group" aria-label="Totais das farmácias exibidas no período de análise">
          <div class="lists-total">
            <span class="lists-total-rotulo">Farmácias</span>
            <span class="lists-total-valor">
              {{ formatNumberFull(totaisLista.total) }}<span v-if="temFiltro" class="lists-total-de"> de {{ formatNumberFull(totalBadge) }}</span>
            </span>
          </div>
          <div class="lists-total">
            <span class="lists-total-rotulo">Total movimentado</span>
            <span v-if="watchlistLoading" class="sk sk-total" aria-hidden="true" />
            <span v-else class="lists-total-valor">{{ totaisLista.totalMov != null ? formatCurrencyFull(totaisLista.totalMov) : '—' }}</span>
          </div>
          <div class="lists-total">
            <span class="lists-total-rotulo">Valor sem comprovação</span>
            <span v-if="watchlistLoading" class="sk sk-total" aria-hidden="true" />
            <span v-else class="lists-total-valor lists-total-valor--alerta">{{ totaisLista.valSemComp != null ? formatCurrencyFull(totaisLista.valSemComp) : '—' }}</span>
          </div>
          <div class="lists-total">
            <span class="lists-total-rotulo">% sem comprovação</span>
            <span v-if="watchlistLoading" class="sk sk-total sk-total--curto" aria-hidden="true" />
            <span v-else class="lists-total-valor">{{ totaisLista.perc != null ? formatPerc(totaisLista.perc) : '—' }}</span>
          </div>

          <div class="lists-risco" role="group" aria-label="Filtrar por classificação de risco">
            <span class="lists-total-rotulo">Classificação de risco</span>
            <div class="risco-barra" aria-hidden="true">
              <span
                v-for="classe in composicaoRisco.filter((c) => c.qtd > 0)"
                :key="classe.value"
                class="risco-segmento"
                :class="{ 'is-apagado': filtroClasses.length && !filtroClasses.includes(classe.value) }"
                :style="{ flexGrow: classe.qtd, background: classe.cor }"
              />
            </div>
            <div class="risco-chips">
              <button
                v-for="classe in composicaoRisco"
                :key="classe.value"
                type="button"
                class="risco-chip"
                :class="{ 'is-ativo': filtroClasses.includes(classe.value) }"
                :aria-pressed="filtroClasses.includes(classe.value)"
                :disabled="classe.qtd === 0"
                @click="alternarClasse(classe.value)"
              >
                <span class="risco-ponto" :style="{ background: classe.cor }" aria-hidden="true" />
                {{ classe.label }}
                <span class="risco-qtd">{{ classe.qtd }}</span>
              </button>
            </div>
          </div>

          <span
            v-if="totaisLista.comDados !== null && totaisLista.comDados < totaisLista.total"
            class="lists-totais-aviso"
            role="status"
          >
            <i class="pi pi-info-circle" aria-hidden="true" />
            {{ totaisLista.comDados }} de {{ totaisLista.total }} com dados no período; as demais não entram nas somas.
          </span>
        </div>

        <!-- Busca, filtros rápidos e agrupamento: tudo sobre os dados já carregados -->
        <div class="lists-ferramentas">
          <label class="lists-busca" :class="{ 'tem-valor': busca }">
            <i class="pi pi-search" aria-hidden="true" />
            <input
              ref="campoBusca"
              v-model="busca"
              type="search"
              placeholder="Buscar nome, CNPJ, município ou observação"
              aria-label="Buscar na lista"
              @keydown.esc="busca = ''"
            />
            <kbd v-if="!busca" class="lists-busca-atalho" aria-hidden="true">/</kbd>
            <button v-else type="button" class="lists-busca-limpar" aria-label="Limpar busca" @click="busca = ''">
              <i class="pi pi-times" aria-hidden="true" />
            </button>
          </label>

          <div class="lists-filtro" :class="{ 'is-ativo': filtroUf !== null }">
            <OptionPicker
              :valor="filtroUf"
              :opcoes="opcoesUf"
              rotulo-acessivel="Filtrar por UF"
              @select="filtroUf = $event"
            />
          </div>
          <button
            type="button"
            class="lists-chave"
            :class="{ 'is-ativo': soComEvidencias }"
            :aria-pressed="soComEvidencias"
            @click="soComEvidencias = !soComEvidencias"
          >
            <i class="pi pi-flag" aria-hidden="true" /> Com evidências
          </button>
          <button
            type="button"
            class="lists-chave"
            :class="{ 'is-ativo': soComObservacao }"
            :aria-pressed="soComObservacao"
            @click="soComObservacao = !soComObservacao"
          >
            <i class="pi pi-comment" aria-hidden="true" /> Com observação
          </button>
          <button v-if="temFiltro" type="button" class="lists-link" @click="limparFiltros">
            Limpar filtros
          </button>

          <div class="lists-ferramentas-fim">
            <span class="lists-rotulo-campo" id="rotulo-agrupar">Agrupar por</span>
            <div class="lists-filtro" :class="{ 'is-ativo': agruparPor !== null }">
              <OptionPicker
                :valor="agruparPor"
                :opcoes="AGRUPAMENTOS"
                rotulo-acessivel="Agrupar a tabela por"
                @select="agruparPor = $event"
              />
            </div>
            <button
              type="button"
              class="lists-icone-btn"
              :aria-pressed="densidade === 'compacta'"
              :aria-label="densidade === 'compacta' ? 'Usar linhas confortáveis' : 'Usar linhas compactas'"
              v-tooltip.top="densidade === 'compacta' ? 'Linhas confortáveis' : 'Linhas compactas'"
              @click="densidade = densidade === 'compacta' ? 'confortavel' : 'compacta'"
            >
              <i :class="['pi', densidade === 'compacta' ? 'pi-bars' : 'pi-align-justify']" aria-hidden="true" />
            </button>
          </div>
        </div>
      </template>

      <div class="lists-content">
        <!-- Carregando a lista: linhas-esqueleto no lugar da tabela -->
        <div v-if="farmaciaLists.loadState === 'loading'" class="lists-esqueleto" role="status" aria-label="Carregando as farmácias monitoradas">
          <div v-for="n in 6" :key="n" class="lists-esqueleto-linha">
            <span class="sk sk-nome" /><span class="sk sk-num" /><span class="sk sk-num" /><span class="sk sk-num" /><span class="sk sk-obs" />
          </div>
        </div>
        <div v-else-if="farmaciaLists.loadState === 'error'" class="empty-state" role="status">
          <i class="pi pi-exclamation-triangle empty-icon" aria-hidden="true" />
          <p>Lista indisponível</p>
          <span>Use as opções de recuperação acima para abrir ou restaurar a lista.</span>
        </div>
        <div v-else-if="farmaciaLists.interesse.length === 0" class="empty-state">
          <i class="pi pi-bookmark empty-icon" aria-hidden="true" />
          <p>Nenhuma farmácia monitorada ainda</p>
          <span>Abra o detalhe de um estabelecimento e clique no ícone de estrela para acompanhá-lo aqui.</span>
          <button type="button" class="lists-botao" @click="router.push('/estabelecimentos')">
            Ir para Estabelecimentos
            <i class="pi pi-arrow-right" aria-hidden="true" />
          </button>
        </div>
        <div v-else-if="listaFiltrada.length === 0" class="empty-state">
          <i class="pi pi-filter-slash empty-icon" aria-hidden="true" />
          <p>Nenhuma farmácia com estes filtros</p>
          <span>{{ totalBadge }} {{ totalBadge === 1 ? 'farmácia está' : 'farmácias estão' }} na lista, mas nenhuma passa pela busca e pelos filtros atuais.</span>
          <button type="button" class="lists-botao" @click="limparFiltros">Limpar filtros</button>
        </div>

        <table v-else class="lists-table">
          <thead>
            <tr>
              <th class="col-num">#</th>
              <th class="col-estab" :aria-sort="ariaOrdenacao('estabelecimento')">
                <button type="button" class="th-ordenar" :class="{ 'is-ativo': ordenacao.coluna === 'estabelecimento' }" @click="ordenarPor('estabelecimento')">
                  <span>Estabelecimento</span>
                  <i :class="['pi', iconeOrdenacao('estabelecimento')]" aria-hidden="true" />
                </button>
              </th>
              <th class="col-risco" :aria-sort="ariaOrdenacao('risco')">
                <button type="button" class="th-ordenar" :class="{ 'is-ativo': ordenacao.coluna === 'risco' }" @click="ordenarPor('risco')">
                  <span>Risco</span>
                  <i :class="['pi', iconeOrdenacao('risco')]" aria-hidden="true" />
                </button>
              </th>
              <th class="col-perc col-right" :aria-sort="ariaOrdenacao('percentual')">
                <button type="button" class="th-ordenar" :class="{ 'is-ativo': ordenacao.coluna === 'percentual' }" @click="ordenarPor('percentual')">
                  <span>% sem comp.</span>
                  <i :class="['pi', iconeOrdenacao('percentual')]" aria-hidden="true" />
                </button>
              </th>
              <th class="col-valor col-right" :aria-sort="ariaOrdenacao('valSemComp')">
                <button type="button" class="th-ordenar" :class="{ 'is-ativo': ordenacao.coluna === 'valSemComp' }" @click="ordenarPor('valSemComp')">
                  <span>Valor sem comp.</span>
                  <i :class="['pi', iconeOrdenacao('valSemComp')]" aria-hidden="true" />
                </button>
              </th>
              <th class="col-valor col-right" :aria-sort="ariaOrdenacao('totalMov')">
                <button type="button" class="th-ordenar" :class="{ 'is-ativo': ordenacao.coluna === 'totalMov' }" @click="ordenarPor('totalMov')">
                  <span>Total mov.</span>
                  <i :class="['pi', iconeOrdenacao('totalMov')]" aria-hidden="true" />
                </button>
              </th>
              <th class="col-evid" :aria-sort="ariaOrdenacao('evidencias')">
                <button type="button" class="th-ordenar" :class="{ 'is-ativo': ordenacao.coluna === 'evidencias' }" @click="ordenarPor('evidencias')">
                  <span>Evidências</span>
                  <i :class="['pi', iconeOrdenacao('evidencias')]" aria-hidden="true" />
                </button>
              </th>
              <th class="col-obs">Observação</th>
              <th class="col-actions"><span class="sr-only">Ações</span></th>
            </tr>
          </thead>
          <tbody>
            <template v-for="linha in linhasTabela" :key="linha.chave">
              <tr v-if="linha.tipo === 'grupo'" class="grupo-linha">
                <td :colspan="9">
                  <span class="grupo-nome">{{ linha.rotulo }}</span>
                  <span class="grupo-dado">{{ linha.qtd }} {{ linha.qtd === 1 ? 'farmácia' : 'farmácias' }}</span>
                  <span v-if="linha.valSemComp !== null && !watchlistLoading" class="grupo-dado">
                    {{ formatCurrencyFull(linha.valSemComp) }} sem comprovação
                  </span>
                </td>
              </tr>
              <tr
                v-else
                class="clickable-row"
                :class="{ 'is-sem-dados': !watchlistLoading && !watchlistError && linha.item.totalMov == null }"
                tabindex="0"
                @click="abrirEstabelecimento(linha.item.cnpj)"
                @keydown.enter.self="abrirEstabelecimento(linha.item.cnpj)"
                @keydown.space.self.prevent="abrirEstabelecimento(linha.item.cnpj)"
              >
                <td class="col-num">{{ linha.posicao }}</td>
                <td class="col-estab">
                  <div class="estab">
                    <span class="estab-nome" v-tooltip.top="linha.item.razaoSocial">{{ linha.item.razaoSocial }}</span>
                    <span class="estab-meta">
                      <span class="estab-cnpj">{{ formatCnpj(linha.item.cnpj) }}</span>
                      <button
                        type="button"
                        class="copy-btn"
                        @click.stop="copyCnpj(linha.item.cnpj)"
                        v-tooltip.top="copiedCnpj === linha.item.cnpj ? 'CNPJ copiado' : 'Copiar CNPJ'"
                        aria-label="Copiar CNPJ"
                      >
                        <i :class="copiedCnpj === linha.item.cnpj ? 'pi pi-check' : 'pi pi-copy'" aria-hidden="true" />
                      </button>
                    </span>
                    <span class="estab-meta estab-meta--sec">
                      <span v-if="linha.item.municipio !== '—'" class="estab-local">{{ linha.item.municipio }}/{{ linha.item.uf }}</span>
                      <span v-if="linha.item.municipio !== '—'" class="estab-sep" aria-hidden="true">·</span>
                      <span class="estab-desde">na lista desde {{ formatDate(linha.item.adicionadoEm) }}</span>
                    </span>
                  </div>
                </td>
                <td class="col-risco">
                  <span v-if="watchlistLoading" class="sk sk-num" aria-hidden="true" />
                  <span v-else-if="linha.item.scoreRisco != null" class="risco" :style="{ '--risco-cor': corDaClasse(linha.item.classificacao) }">
                    <span class="risco-score">{{ formatScore(linha.item.scoreRisco) }}</span>
                    <span v-if="linha.item.classificacao" class="risco-classe">{{ linha.item.classificacao }}</span>
                  </span>
                  <span v-else-if="!watchlistError && linha.item.totalMov == null" class="tag-sem-dados">Sem dados no período</span>
                  <span v-else class="col-vazio">—</span>
                </td>
                <td class="col-perc col-right">
                  <span v-if="watchlistLoading" class="sk sk-num" aria-hidden="true" />
                  <span v-else-if="linha.item.percValSemComp != null" class="perc" :class="faixaPerc(linha.item.percValSemComp)">
                    <span class="perc-valor">{{ formatPerc(linha.item.percValSemComp) }}</span>
                    <span class="perc-trilha" aria-hidden="true">
                      <span class="perc-barra" :style="{ width: `${Math.min(100, Math.max(0, linha.item.percValSemComp))}%` }" />
                    </span>
                  </span>
                  <span v-else class="col-vazio">—</span>
                </td>
                <td class="col-valor col-right col-destaque">
                  <span v-if="watchlistLoading" class="sk sk-num" aria-hidden="true" />
                  <span
                    v-else-if="linha.item.valSemComp != null"
                    :class="{ 'high-value-audit': linha.item.valSemComp >= auditHighValue }"
                  >{{ formatCurrencyFull(linha.item.valSemComp) }}</span>
                  <template v-else>—</template>
                </td>
                <td class="col-valor col-right">
                  <span v-if="watchlistLoading" class="sk sk-num" aria-hidden="true" />
                  <template v-else>{{ linha.item.totalMov != null ? formatCurrencyFull(linha.item.totalMov) : '—' }}</template>
                </td>
                <td class="col-evid">
                  <button
                    v-if="evidenciasStore.contar(linha.item.cnpj) > 0"
                    type="button"
                    class="evid-count-btn"
                    :aria-label="`Abrir as ${evidenciasStore.contar(linha.item.cnpj)} evidências de ${linha.item.razaoSocial}`"
                    v-tooltip.top="`Última marcação em ${dataHoraCurta(evidenciasStore.ultimaEm(linha.item.cnpj))}`"
                    @click.stop="abrirEvidenciasDaFarmacia(linha.item.cnpj)"
                  >
                    <i class="pi pi-flag-fill" aria-hidden="true" />
                    <span class="evid-count-num">{{ evidenciasStore.contar(linha.item.cnpj) }}</span>
                  </button>
                  <span v-else-if="evidenciasStore.loadState === 'error'" class="col-vazio" v-tooltip.top="'Cesta de evidências indisponível'">?</span>
                  <span v-else class="col-vazio">—</span>
                </td>
                <td class="col-obs">
                  <button
                    type="button"
                    class="obs-btn"
                    :class="{ 'is-vazia': !linha.item.observacao }"
                    :aria-label="linha.item.observacao ? `Editar a observação de ${linha.item.razaoSocial}` : `Adicionar observação a ${linha.item.razaoSocial}`"
                    v-tooltip.top="linha.item.observacao || 'Adicionar observação'"
                    @click.stop="editarObservacao(linha.item)"
                  >
                    <span v-if="linha.item.observacao" class="obs-texto">{{ linha.item.observacao }}</span>
                    <span v-else class="obs-adicionar"><i class="pi pi-plus" aria-hidden="true" /> Adicionar observação</span>
                  </button>
                </td>
                <td class="col-actions">
                  <div class="action-btns">
                    <button
                      type="button"
                      class="action-btn open"
                      aria-label="Abrir detalhamento"
                      @click.stop="abrirEstabelecimento(linha.item.cnpj)"
                      v-tooltip.top="'Abrir detalhamento'"
                    >
                      <i class="pi pi-arrow-up-right" aria-hidden="true" />
                    </button>
                    <button
                      type="button"
                      class="action-btn report"
                      :class="{ 'is-busy': exportingReportCnpj === linha.item.cnpj }"
                      aria-label="Gerar relatório PDF"
                      @click.stop="gerarRelatorio(linha.item)"
                      :disabled="!!exportingReportCnpj"
                      v-tooltip.top="'Gerar relatório PDF'"
                    >
                      <i :class="exportingReportCnpj === linha.item.cnpj ? 'pi pi-spin pi-spinner' : 'pi pi-file-pdf'" aria-hidden="true" />
                    </button>
                    <button
                      type="button"
                      class="action-btn note"
                      :class="{ 'is-busy': generatingNoteCnpj === linha.item.cnpj }"
                      aria-label="Gerar Nota Técnica"
                      @click.stop="gerarNotaTecnica(linha.item)"
                      :disabled="!!generatingNoteCnpj"
                      v-tooltip.top="`Gerar Nota Técnica · ${regionalLabel}`"
                    >
                      <i :class="generatingNoteCnpj === linha.item.cnpj ? 'pi pi-spin pi-spinner' : 'pi pi-book'" aria-hidden="true" />
                    </button>
                    <button
                      type="button"
                      class="action-btn remove"
                      aria-label="Remover da lista"
                      @click.stop="remover(linha.item.cnpj)"
                      :disabled="!farmaciaLists.canEdit"
                      v-tooltip.top="'Remover da lista'"
                    >
                      <i class="pi pi-trash" aria-hidden="true" />
                    </button>
                  </div>
                </td>
              </tr>
            </template>
          </tbody>
        </table>
      </div><!-- /lists-content -->

      <footer v-if="listaPronta" class="lists-rodape">
        <span>
          <template v-if="temFiltro">Exibindo {{ formatNumberFull(listaFiltrada.length) }} de {{ formatNumberFull(totalBadge) }} farmácias</template>
          <template v-else>{{ formatNumberFull(totalBadge) }} {{ totalBadge === 1 ? 'farmácia' : 'farmácias' }}</template>
        </span>
        <!-- Regional emissora: configuração das Notas Técnicas, fora da área de filtros -->
        <button
          type="button"
          class="lists-link"
          :disabled="!notaTecnicaConfig.loaded"
          v-tooltip.top="'Regional emissora usada ao gerar as Notas Técnicas. Clique para alterar.'"
          @click="regionalDialogVisible = true"
        >
          <i class="pi pi-building" aria-hidden="true" /> Regional das Notas Técnicas: {{ regionalLabel }}
        </button>
      </footer>
    </div><!-- /lists-card -->

    <EvidenciasPanel
      v-if="painelEvidCnpj"
      :cnpj="painelEvidCnpj"
      :razao-social="nomeFarmacia(painelEvidCnpj)"
      contexto="listas"
    />
    <ObservationDialog
      v-if="obsTarget"
      v-model:visible="showObsDialog"
      :cnpj="obsTarget.cnpj"
      :entity-name="obsTarget.razaoSocial || formatCnpj(obsTarget.cnpj)"
    />
    <NotaTecnicaRegionalDialog
      :visible="regionalDialogVisible"
      :continue-label="pendingNoteItem ? 'Gerar Nota Técnica' : 'Salvar dados'"
      @update:visible="setRegionalDialogVisible"
      @saved="onRegionalSavedForList"
    />
  </div>
</template>

<style scoped>
.lists-view {
  padding: 1.5rem 2rem 2rem;
  display: flex;
  flex-direction: column;
  gap: 1rem;
  max-width: 98%;
  margin: 0 auto;
}

/* ── Barra de comando ─────────────────────────────────────────────────── */
.lists-barra {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 0.75rem 1.5rem;
}
.lists-titulo {
  display: flex;
  align-items: center;
  gap: 0.65rem;
  min-width: 0;
}
.lists-titulo > .pi-bookmark {
  color: var(--primary-color);
  font-size: 1.1rem;
}
.lists-titulo h2 {
  margin: 0;
  color: var(--text-color);
  font-size: 1.25rem;
  font-weight: 600;
  line-height: 1.2;
}
.lists-contagem {
  padding: 0.1rem 0.55rem;
  border-radius: 999px;
  background: color-mix(in srgb, var(--primary-color) 14%, transparent);
  color: var(--primary-color);
  font-size: 0.78rem;
  font-weight: 600;
}
.lists-barra-acoes {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 0.65rem;
}
.lists-estado {
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
  color: var(--text-muted);
  font-size: 0.76rem;
}
.lists-estado--erro { color: var(--risk-critical); }

/* Texto-ação: desfazer filtros, tentar de novo, regional das Notas Técnicas. */
.lists-link {
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
  padding: 0.2rem 0.3rem;
  border: 0;
  border-radius: 5px;
  background: transparent;
  color: var(--primary-color);
  font: inherit;
  font-size: 0.76rem;
  font-weight: 500;
  cursor: pointer;
}
.lists-link:hover:not(:disabled) { background: color-mix(in srgb, var(--primary-color) 10%, transparent); }
.lists-link:focus-visible { outline: 2px solid color-mix(in srgb, var(--primary-color) 70%, transparent); outline-offset: 1px; }
.lists-link:disabled { cursor: not-allowed; opacity: 0.6; }
.lists-link .pi { font-size: 0.72rem; }

/* Chip de período: é o gatilho do seletor de meses (mesmo componente da sidebar). */
.period-chip-picker { display: inline-flex; }
.period-chip-picker :deep(.rp-gatilho) {
  gap: 0.45rem;
  min-height: 0;
  height: 2.125rem;
  padding: 0 0.75rem;
  border-radius: 8px;
  border: 1px solid color-mix(in srgb, var(--primary-color) 30%, transparent);
  background: color-mix(in srgb, var(--primary-color) 8%, transparent);
  color: var(--primary-color);
  font-size: 0.75rem;
  font-weight: 500;
  white-space: nowrap;
}
.period-chip-picker :deep(.rp-gatilho:hover),
.period-chip-picker :deep(.rp-gatilho:focus-visible) {
  border-color: var(--primary-color);
  background: color-mix(in srgb, var(--primary-color) 14%, transparent);
}
.period-chip-picker :deep(.rp-gatilho-icone) { color: var(--primary-color); font-size: 0.78rem; }
.period-chip-picker :deep(.rp-gatilho-seta) { margin-left: 0.1rem; color: var(--primary-color); font-size: 0.58rem; }

/* ── Avisos (desfazer remoção, recuperação) ───────────────────────────── */
.lists-undo {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 0.35rem 0.9rem;
  padding: 0.45rem 0.8rem;
  border: 1px solid var(--card-border);
  border-radius: 10px;
  background: var(--card-bg);
  color: var(--text-color-85);
  font-size: 0.8rem;
}
.lists-undo > i { color: var(--text-muted); font-size: 0.8rem; }
.lists-undo-item { display: inline-flex; align-items: center; gap: 0.4rem; }
.lists-undo-btn {
  padding: 0.15rem 0.45rem;
  border: 0;
  border-radius: 6px;
  background: transparent;
  color: var(--primary-color);
  font: inherit;
  font-weight: 600;
  cursor: pointer;
}
.lists-undo-btn:hover:not(:disabled) { background: color-mix(in srgb, var(--primary-color) 10%, transparent); }
.lists-undo-btn:focus-visible { outline: 2px solid var(--primary-color); outline-offset: 1px; }
.lists-undo-btn:disabled { cursor: not-allowed; opacity: 0.5; }

.preferences-recovery {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 1rem;
  padding: 0.9rem 1.1rem;
  border: 1px solid var(--risk-high);
  border-radius: 12px;
  background: color-mix(in srgb, var(--risk-high) 8%, var(--card-bg));
  color: var(--text-color-85);
}
.preferences-recovery-copy { display: flex; align-items: flex-start; gap: 0.7rem; min-width: 0; }
.preferences-recovery-copy > i { color: var(--risk-high); margin-top: 0.1rem; }
.preferences-recovery-copy p { margin: 0 0 0.2rem; font-size: 0.85rem; }
.preferences-recovery-copy span { font-size: 0.75rem; opacity: 0.8; }
.preferences-recovery-actions { display: flex; flex-wrap: wrap; gap: 0.5rem; }
.preferences-recovery-actions button {
  cursor: pointer;
  border: 1px solid var(--card-border);
  border-radius: 8px;
  background: var(--card-bg);
  color: var(--text-color-85);
  padding: 0.45rem 0.75rem;
  font-size: 0.78rem;
}
.preferences-recovery-actions button:hover:not(:disabled) { border-color: var(--primary-color); }
.preferences-recovery-actions button:focus-visible { outline: 2px solid var(--primary-color); outline-offset: 2px; }
.preferences-recovery-actions button:disabled { cursor: not-allowed; opacity: 0.5; }

/* ── Card da mesa de trabalho ─────────────────────────────────────────── */
.lists-card {
  --linha-padding: 0.7rem;
  display: flex;
  flex-direction: column;
  background: var(--card-bg);
  border: 1px solid var(--card-border);
  border-radius: 12px;
  overflow: hidden;
}
.lists-card.is-compacta { --linha-padding: 0.38rem; }

/* Totais do recorte + composição de risco */
.lists-totais {
  display: flex;
  align-items: flex-start;
  flex-wrap: wrap;
  gap: 1rem 2.5rem;
  padding: 1rem 1.25rem;
  border-bottom: 1px solid var(--card-border);
}
.lists-total {
  display: flex;
  flex-direction: column;
  gap: 0.3rem;
  min-width: 0;
}
.lists-total-rotulo {
  color: var(--text-muted);
  font-size: 0.68rem;
  font-weight: 500;
  letter-spacing: 0.05em;
  text-transform: uppercase;
  white-space: nowrap;
}
.lists-total-valor {
  color: var(--text-color);
  font-size: 1.15rem;
  font-weight: 600;
  line-height: 1.15;
  white-space: nowrap;
}
.lists-total-de {
  color: var(--text-muted);
  font-size: 0.8rem;
  font-weight: 500;
}
.lists-total-valor--alerta { color: var(--risk-critical); }
.lists-totais-aviso {
  display: inline-flex;
  align-items: center;
  flex-basis: 100%;
  gap: 0.35rem;
  color: var(--text-muted);
  font-size: 0.72rem;
}

.lists-risco {
  display: flex;
  flex-direction: column;
  gap: 0.4rem;
  min-width: 18rem;
  margin-left: auto;
}
.risco-barra {
  display: flex;
  gap: 2px;
  height: 6px;
  border-radius: 3px;
  overflow: hidden;
  background: color-mix(in srgb, var(--text-color) 8%, transparent);
}
.risco-segmento { flex-basis: 0; min-width: 4px; transition: opacity 0.18s ease; }
.risco-segmento.is-apagado { opacity: 0.25; }
.risco-chips { display: flex; flex-wrap: wrap; gap: 0.3rem; }
.risco-chip {
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
  height: 1.6rem;
  padding: 0 0.5rem;
  border: 1px solid var(--card-border);
  border-radius: 999px;
  background: transparent;
  color: var(--text-secondary);
  font: inherit;
  font-size: 0.72rem;
  font-weight: 500;
  cursor: pointer;
  transition: border-color 0.15s ease, background 0.15s ease, color 0.15s ease;
}
.risco-chip:hover:not(:disabled) { border-color: color-mix(in srgb, var(--text-color) 35%, var(--card-border)); color: var(--text-color); }
.risco-chip:focus-visible { outline: 2px solid color-mix(in srgb, var(--primary-color) 70%, transparent); outline-offset: 1px; }
.risco-chip.is-ativo {
  border-color: var(--primary-color);
  background: color-mix(in srgb, var(--primary-color) 12%, transparent);
  color: var(--text-color);
}
.risco-chip:disabled { cursor: default; opacity: 0.45; }
.risco-ponto { width: 7px; height: 7px; border-radius: 50%; flex-shrink: 0; }
.risco-qtd { color: var(--text-muted); }

/* Busca, filtros e agrupamento */
.lists-ferramentas {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 0.5rem;
  padding: 0.65rem 1.25rem;
  border-bottom: 1px solid var(--card-border);
  background: color-mix(in srgb, var(--text-color) 2%, transparent);
}
.lists-ferramentas-fim {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin-left: auto;
}
.lists-rotulo-campo { color: var(--text-muted); font-size: 0.74rem; font-weight: 500; white-space: nowrap; }
.lists-busca {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  flex: 0 1 22rem;
  min-width: 14rem;
  height: 2rem;
  padding: 0 0.6rem;
  border: 1px solid var(--card-border);
  border-radius: 6px;
  background: var(--card-bg);
  color: var(--text-muted);
  cursor: text;
  transition: border-color 0.15s ease;
}
.lists-busca:hover { border-color: color-mix(in srgb, var(--text-color) 28%, var(--card-border)); }
.lists-busca:focus-within,
.lists-busca.tem-valor { border-color: var(--primary-color); }
.lists-busca > .pi { font-size: 0.8rem; }
.lists-busca input {
  flex: 1;
  min-width: 0;
  padding: 0;
  border: 0;
  outline: 0;
  background: transparent;
  color: var(--text-color-85);
  font: inherit;
  font-size: 0.8125rem;
}
.lists-busca input::placeholder { color: var(--text-muted); }
.lists-busca input::-webkit-search-cancel-button { display: none; }
.lists-busca-atalho {
  padding: 0 0.35rem;
  border: 1px solid var(--card-border);
  border-radius: 4px;
  color: var(--text-muted);
  font: inherit;
  font-size: 0.68rem;
  line-height: 1.25rem;
}
.lists-busca-limpar {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 1.25rem;
  height: 1.25rem;
  padding: 0;
  border: 0;
  border-radius: 4px;
  background: transparent;
  color: var(--text-muted);
  cursor: pointer;
}
.lists-busca-limpar:hover { color: var(--text-color); background: color-mix(in srgb, var(--text-color) 10%, transparent); }
.lists-busca-limpar .pi { font-size: 0.65rem; }

.lists-filtro :deep(.rp-gatilho) {
  height: 2rem;
  min-height: 2rem;
  padding: 0 0.6rem;
  color: var(--text-muted);
  font-size: 0.8125rem;
  font-weight: 400;
}
.lists-filtro.is-ativo :deep(.rp-gatilho) {
  border-color: var(--primary-color);
  background: color-mix(in srgb, var(--primary-color) 10%, transparent);
  color: var(--text-color-85);
}
.lists-chave {
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
  height: 2rem;
  padding: 0 0.65rem;
  border: 1px solid var(--card-border);
  border-radius: 6px;
  background: var(--card-bg);
  color: var(--text-muted);
  font: inherit;
  font-size: 0.8125rem;
  cursor: pointer;
  white-space: nowrap;
  transition: border-color 0.15s ease, background 0.15s ease, color 0.15s ease;
}
.lists-chave:hover { border-color: color-mix(in srgb, var(--text-color) 28%, var(--card-border)); color: var(--text-color-85); }
.lists-chave:focus-visible,
.lists-icone-btn:focus-visible { outline: 2px solid color-mix(in srgb, var(--primary-color) 70%, transparent); outline-offset: 1px; }
.lists-chave.is-ativo {
  border-color: var(--primary-color);
  background: color-mix(in srgb, var(--primary-color) 10%, transparent);
  color: var(--text-color-85);
}
.lists-chave .pi { font-size: 0.74rem; }
.lists-chave.is-ativo .pi { color: var(--primary-color); }
.lists-icone-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 2rem;
  height: 2rem;
  padding: 0;
  border: 1px solid var(--card-border);
  border-radius: 6px;
  background: var(--card-bg);
  color: var(--text-muted);
  cursor: pointer;
  transition: border-color 0.15s ease, color 0.15s ease;
}
.lists-icone-btn:hover { border-color: color-mix(in srgb, var(--text-color) 28%, var(--card-border)); color: var(--text-color-85); }
.lists-icone-btn .pi { font-size: 0.8rem; }

/* ── Tabela ───────────────────────────────────────────────────────────── */
/* Rola dentro do card: totais, busca e cabeçalho das colunas ficam sempre à vista. */
.lists-content {
  max-height: max(20rem, calc(100vh - 23rem));
  overflow: auto;
  scrollbar-width: thin;
  scrollbar-color: color-mix(in srgb, var(--text-color) 22%, transparent) transparent;
}
.lists-table {
  width: 100%;
  min-width: 1180px;
  border-collapse: separate;
  border-spacing: 0;
  table-layout: fixed;
}
.lists-table th {
  position: sticky;
  top: 0;
  z-index: 2;
  padding: 0.6rem 0.9rem;
  border-bottom: 1px solid var(--card-border);
  background: color-mix(in srgb, var(--card-bg) 88%, var(--card-border));
  color: var(--text-secondary);
  font-size: 0.68rem;
  font-weight: 500;
  letter-spacing: 0.05em;
  text-align: left;
  text-transform: uppercase;
  white-space: nowrap;
}
.lists-table th.col-right { text-align: right; }
.lists-table th.col-num { width: 44px; }
.lists-table th.col-risco { width: 9%; }
.lists-table th.col-perc { width: 10%; }
.lists-table th.col-valor { width: 12%; }
.lists-table th.col-evid { width: 7%; }
.lists-table th.col-obs { width: 17%; }
.lists-table th.col-actions { width: 150px; }

.lists-table td {
  padding: var(--linha-padding) 0.9rem;
  border-bottom: 1px solid var(--card-border);
  color: var(--text-color-85);
  font-size: 0.8125rem;
  vertical-align: middle;
}
.lists-table tbody tr:last-child td { border-bottom: 0; }
/* Mesma cor de hover das tabelas de /estabelecimentos (.enterprise-table). */
.lists-table tbody tr.clickable-row:hover { background: var(--table-hover); }
.clickable-row { cursor: pointer; }
.clickable-row:focus-visible {
  outline: 2px solid color-mix(in srgb, var(--primary-color) 70%, transparent);
  outline-offset: -2px;
  background: var(--table-hover);
}
.col-right { text-align: right; }
.col-vazio { color: var(--text-muted); opacity: 0.6; }
td.col-num { color: var(--text-muted); font-size: 0.74rem; }
td.col-valor { color: var(--text-secondary); font-weight: 400; white-space: nowrap; }
td.col-destaque { color: var(--text-color); font-weight: 600; }
tr.is-sem-dados .estab-nome { color: var(--text-secondary); }

/* Cabeçalho ordenável: o botão ocupa a célula e herda a tipografia do cabeçalho. */
.th-ordenar {
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
  max-width: 100%;
  padding: 0;
  border: 0;
  background: transparent;
  color: inherit;
  font: inherit;
  letter-spacing: inherit;
  text-transform: inherit;
  white-space: nowrap;
  cursor: pointer;
}
.th-ordenar .pi { font-size: 0.7rem; opacity: 0.45; }
.th-ordenar:hover,
.th-ordenar:focus-visible { color: var(--text-color); }
.th-ordenar:hover .pi,
.th-ordenar:focus-visible .pi { opacity: 0.85; }
.th-ordenar:focus-visible {
  outline: 2px solid color-mix(in srgb, var(--primary-color) 70%, transparent);
  outline-offset: 3px;
  border-radius: 3px;
}
.th-ordenar.is-ativo { color: var(--primary-color); }
.th-ordenar.is-ativo .pi { opacity: 1; }

/* Linha de grupo (agrupar por UF ou por classificação) */
.grupo-linha td {
  padding: 0.45rem 0.9rem;
  background: color-mix(in srgb, var(--text-color) 4%, var(--card-bg));
  color: var(--text-secondary);
  font-size: 0.76rem;
}
.grupo-nome { margin-right: 0.75rem; color: var(--text-color); font-weight: 600; }
.grupo-dado + .grupo-dado::before { content: "·"; margin: 0 0.5rem; color: var(--text-muted); }

/* Estabelecimento: nome e, abaixo, CNPJ, município e data de inclusão */
.estab { display: flex; flex-direction: column; gap: 0.12rem; min-width: 0; }
.estab-nome {
  overflow: hidden;
  color: var(--text-color);
  font-weight: 500;
  line-height: 1.25;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.estab-meta {
  display: flex;
  align-items: center;
  gap: 0.3rem;
  min-width: 0;
  overflow: hidden;
  color: var(--text-muted);
  font-size: 0.72rem;
  white-space: nowrap;
}
.estab-meta--sec { gap: 0.35rem; }
.estab-local { overflow: hidden; color: var(--text-secondary); text-overflow: ellipsis; }
.estab-desde { flex-shrink: 0; }
.estab-sep { opacity: 0.6; }
.is-compacta .estab-desde,
.is-compacta .estab-local + .estab-sep { display: none; }
.copy-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  width: 18px;
  height: 18px;
  padding: 0;
  border: 0;
  border-radius: 4px;
  background: transparent;
  color: var(--text-muted);
  cursor: pointer;
  opacity: 0;
  transition: opacity 0.15s ease, color 0.15s ease, background 0.15s ease;
}
.clickable-row:hover .copy-btn,
.copy-btn:focus-visible { opacity: 1; }
.copy-btn:hover,
.copy-btn:focus-visible {
  outline: none;
  background: color-mix(in srgb, var(--primary-color) 10%, transparent);
  color: var(--primary-color);
}
.copy-btn i { font-size: 0.66rem; }

/* Risco: score e classificação na cor da classe */
.risco { display: inline-flex; align-items: center; gap: 0.5rem; color: var(--risco-cor); }
.risco-score { font-weight: 600; }
.risco-classe {
  padding: 0.08rem 0.35rem;
  border-radius: 4px;
  background: color-mix(in srgb, var(--risco-cor) 12%, transparent);
  font-size: 0.64rem;
  font-weight: 600;
  letter-spacing: 0.03em;
}
.tag-sem-dados {
  padding: 0.1rem 0.4rem;
  border: 1px solid var(--card-border);
  border-radius: 4px;
  color: var(--text-muted);
  font-size: 0.68rem;
  white-space: nowrap;
}

/* % sem comprovação: número e barra proporcional */
.perc { display: inline-flex; flex-direction: column; align-items: flex-end; gap: 0.25rem; --perc-cor: var(--text-secondary); }
.perc.is-alto { --perc-cor: var(--risk-critical); }
.perc.is-medio { --perc-cor: var(--risk-medium); }
.perc-valor { color: var(--perc-cor); font-weight: 600; }
.perc-trilha {
  width: 4.5rem;
  height: 3px;
  border-radius: 2px;
  overflow: hidden;
  background: color-mix(in srgb, var(--text-color) 10%, transparent);
}
.perc-barra { display: block; height: 100%; border-radius: 2px; background: var(--perc-cor); }
.is-compacta .perc-trilha { display: none; }

/* Alto valor sem comprovação (mesmo destaque da tabela de /estabelecimentos) */
.high-value-audit {
  display: inline-flex;
  align-items: center;
  justify-content: flex-end;
  padding: 0.1rem 0.5rem;
  border-left: 3px solid var(--alerta-cor);
  border-radius: 0 6px 6px 0;
  background: color-mix(in srgb, var(--alerta-cor) 10%, transparent);
  color: var(--alerta-cor);
  font-weight: 600;
  line-height: 1.2;
}

/* Evidências */
.evid-count-btn {
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
  height: 1.6rem;
  padding: 0 0.5rem;
  border: 1px solid color-mix(in srgb, var(--evidence-color) 35%, transparent);
  border-radius: 6px;
  background: color-mix(in srgb, var(--evidence-color) 8%, transparent);
  color: var(--evidence-color);
  font-family: inherit;
  cursor: pointer;
}
.evid-count-btn:hover,
.evid-count-btn:focus-visible { border-color: var(--evidence-color); outline: none; }
.evid-count-btn i { font-size: 0.66rem; }
.evid-count-num { font-size: 0.78rem; font-weight: 600; }

/* Observação: o texto é o próprio botão de edição */
.obs-btn {
  display: block;
  width: 100%;
  padding: 0.2rem 0.4rem;
  margin: -0.2rem -0.4rem;
  border: 1px solid transparent;
  border-radius: 6px;
  background: transparent;
  color: var(--text-secondary);
  font: inherit;
  font-size: 0.78rem;
  line-height: 1.35;
  text-align: left;
  cursor: text;
  transition: border-color 0.15s ease, background 0.15s ease;
}
.obs-btn:hover,
.obs-btn:focus-visible {
  outline: none;
  border-color: color-mix(in srgb, var(--primary-color) 45%, transparent);
  background: color-mix(in srgb, var(--primary-color) 6%, transparent);
}
.obs-texto {
  display: -webkit-box;
  overflow: hidden;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
  line-clamp: 2;
}
.is-compacta .obs-texto { -webkit-line-clamp: 1; line-clamp: 1; }
.obs-adicionar {
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
  color: var(--text-muted);
  opacity: 0;
  transition: opacity 0.15s ease;
}
.obs-adicionar .pi { font-size: 0.62rem; }
.clickable-row:hover .obs-adicionar,
.clickable-row:focus-within .obs-adicionar { opacity: 1; }

/* Ações da linha */
.col-actions { text-align: center; }
.action-btns { display: flex; justify-content: flex-end; gap: 0.3rem; }
.action-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  border: 1px solid var(--tabs-border);
  border-radius: 6px;
  background: color-mix(in srgb, var(--text-color-85) 3%, transparent);
  color: var(--text-color-85);
  font-size: 0.74rem;
  cursor: pointer;
  transition: border-color 0.15s ease, background 0.15s ease, color 0.15s ease, opacity 0.15s ease;
}
.action-btn:disabled { cursor: wait; opacity: 0.45; }
/* Neutras em repouso: só o ícone, em cinza. A cor e a borda de cada ação aparecem com
   o mouse (ou o foco do teclado) na linha; a ação em andamento fica sempre destacada. */
.lists-table tbody tr:not(:hover):not(:focus-within) .action-btn:not(.is-busy) {
  border-color: transparent;
  background: transparent;
  color: var(--text-muted);
  opacity: 0.6;
}
.action-btn.is-busy { opacity: 1; }
.action-btn:focus-visible { outline: 2px solid color-mix(in srgb, var(--primary-color) 70%, transparent); outline-offset: 1px; }
.action-btn.open:hover {
  border-color: var(--primary-color);
  background: color-mix(in srgb, var(--primary-color) 8%, transparent);
  color: var(--primary-color);
}
.action-btn.report {
  border-color: color-mix(in srgb, var(--primary-color) 30%, transparent);
  background: color-mix(in srgb, var(--primary-color) 8%, transparent);
  color: var(--primary-color);
}
.action-btn.report:hover {
  border-color: var(--primary-color);
  background: color-mix(in srgb, var(--primary-color) 16%, transparent);
}
.action-btn.note {
  --btn-note-color: #a855f7;
  border-color: color-mix(in srgb, var(--btn-note-color) 30%, transparent);
  background: color-mix(in srgb, var(--btn-note-color) 8%, transparent);
  color: var(--btn-note-color);
}
.action-btn.note:hover {
  border-color: var(--btn-note-color);
  background: color-mix(in srgb, var(--btn-note-color) 16%, transparent);
}
.action-btn.remove:hover {
  border-color: var(--risk-critical);
  background: color-mix(in srgb, var(--risk-critical) 8%, transparent);
  color: var(--risk-critical);
}

/* ── Rodapé do card ───────────────────────────────────────────────────── */
.lists-rodape {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 0.5rem 1rem;
  padding: 0.5rem 1.25rem;
  border-top: 1px solid var(--card-border);
  color: var(--text-muted);
  font-size: 0.74rem;
}

/* ── Estados ──────────────────────────────────────────────────────────── */
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 0.5rem;
  padding: 4.5rem 2rem;
  color: var(--text-muted);
  text-align: center;
}
.empty-icon { margin-bottom: 0.4rem; font-size: 2rem; opacity: 0.7; }
.empty-state p { margin: 0; color: var(--text-color-85); font-size: 0.95rem; font-weight: 500; }
.empty-state span { max-width: 34rem; font-size: 0.8rem; line-height: 1.45; }
.lists-botao {
  display: inline-flex;
  align-items: center;
  gap: 0.45rem;
  height: 2.125rem;
  margin-top: 0.6rem;
  padding: 0 0.9rem;
  border: 1px solid var(--primary-color);
  border-radius: 8px;
  background: color-mix(in srgb, var(--primary-color) 10%, transparent);
  color: var(--primary-color);
  font: inherit;
  font-size: 0.78rem;
  font-weight: 600;
  cursor: pointer;
  transition: background 0.15s ease;
}
.lists-botao:hover { background: color-mix(in srgb, var(--primary-color) 18%, transparent); }
.lists-botao:focus-visible { outline: 2px solid var(--primary-color); outline-offset: 2px; }
.lists-botao .pi { font-size: 0.7rem; }

/* Esqueleto: enquanto a lista ou os indicadores carregam */
.sk {
  display: inline-block;
  height: 0.7rem;
  border-radius: 4px;
  background: linear-gradient(90deg,
    color-mix(in srgb, var(--text-color) 7%, transparent),
    color-mix(in srgb, var(--text-color) 14%, transparent),
    color-mix(in srgb, var(--text-color) 7%, transparent));
  background-size: 200% 100%;
  animation: sk-brilho 1.3s linear infinite;
}
.sk-num { width: 4.5rem; }
.sk-nome { width: 16rem; }
.sk-obs { width: 11rem; }
.sk-total { width: 9rem; height: 1.15rem; }
.sk-total--curto { width: 4rem; }
.lists-esqueleto { display: flex; flex-direction: column; }
.lists-esqueleto-linha {
  display: flex;
  align-items: center;
  gap: 3rem;
  padding: 1.05rem 1.25rem;
  border-bottom: 1px solid var(--card-border);
}
.lists-esqueleto-linha:last-child { border-bottom: 0; }
.lists-esqueleto-linha .sk-nome { margin-right: auto; }
@keyframes sk-brilho { from { background-position: 200% 0; } to { background-position: -200% 0; } }
@media (prefers-reduced-motion: reduce) {
  .sk { animation: none; }
}

/* Rótulo só para leitores de tela (cabeçalho da coluna de ações). */
.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  margin: -1px;
  padding: 0;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  white-space: nowrap;
  border: 0;
}
</style>
