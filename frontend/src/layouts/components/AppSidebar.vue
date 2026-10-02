<script setup>
import { computed, ref, watch, onMounted, onBeforeUnmount } from "vue";
import { useRoute } from "vue-router";
import {
  FILTER_DEFAULTS,
  FILTER_ALL_VALUE,
  ANALYSIS_YEARS,
  TIMING,
} from "@/config/constants";
import { useFilterStore } from "@/stores/filters";
import { useGeoStore } from "@/stores/geo";
import { usePeriodoAnalise } from "@/composables/usePeriodoAnalise";
import {
  FILTER_OPTIONS,
  POPULACAO_MUNICIPIO_ATALHOS,
  SEQ_DIAS_ATALHOS,
  SEQ_SEVERIDADES,
  SEQ_TIPOS,
} from "@/config/filterOptions";
import { filterActionTooltip, filterTooltip } from "@/config/filterTooltipConfig";
import Button from "primevue/button";
import Checkbox from "primevue/checkbox";
import Dropdown from "primevue/dropdown";
import InputText from "primevue/inputtext";
import AutoComplete from "primevue/autocomplete";
import DataIntegrityBanner from "@/layouts/components/DataIntegrityBanner.vue";
import MonthRangePicker from "@/views/components/common/MonthRangePicker.vue";
import NumberRangePicker from "@/views/components/common/NumberRangePicker.vue";
import OptionPicker from "@/views/components/common/OptionPicker.vue";

const props = defineProps({
  activeModule: { type: String, required: true },
});

const filterStore = useFilterStore();
const filtersLocked = computed(() => filterStore.filtersLocked);
const geoStore = useGeoStore();
const route = useRoute();

// ── Opções dos Selects ───────────────────────────────────────────────────────
const ufOptions = computed(() => geoStore.ufs);
const regiaoSaudeOptions = computed(() =>
  geoStore.regioesPorUF(filterStore.selectedUF),
);
const unidadePfOptions = computed(() =>
  geoStore.jurisdicoesPorFiltro(
    filterStore.selectedUF,
    filterStore.selectedRegiaoSaude,
    filterStore.selectedMunicipio,
  ),
);
const municipioOptions = computed(() =>
  geoStore.municipiosPorFiltro(
    filterStore.selectedUF,
    filterStore.selectedRegiaoSaude,
    filterStore.selectedUnidadePf,
  ),
);

// ── Watches de cascata: reseta filtros dependentes quando pai muda ───────────
watch(
  () => filterStore.selectedUF,
  (newUF) => {
    const regioesDisponiveis = geoStore.regioesPorUF(newUF);
    if (!regioesDisponiveis.some(r => r.value === filterStore.selectedRegiaoSaude)) {
      filterStore.selectedRegiaoSaude = "Todos";
    }
    const unidadesDisponiveis = geoStore.jurisdicoesPorFiltro(
      newUF,
      filterStore.selectedRegiaoSaude,
      filterStore.selectedMunicipio,
    );
    if (!unidadesDisponiveis.includes(filterStore.selectedUnidadePf)) {
      filterStore.selectedUnidadePf = "Todos";
    }
    const municipiosDisponiveis = geoStore.municipiosPorFiltro(
      newUF,
      filterStore.selectedRegiaoSaude,
      filterStore.selectedUnidadePf,
    );
    if (
      !municipiosDisponiveis.some(
        (m) => m.value === filterStore.selectedMunicipio,
      )
    ) {
      filterStore.selectedMunicipio = "Todos";
    }
  },
);

watch(
  () => filterStore.selectedRegiaoSaude,
  (newRegiao) => {
    const unidadesDisponiveis = geoStore.jurisdicoesPorFiltro(
      filterStore.selectedUF,
      newRegiao,
      filterStore.selectedMunicipio,
    );
    if (!unidadesDisponiveis.includes(filterStore.selectedUnidadePf)) {
      filterStore.selectedUnidadePf = "Todos";
    }
    const municipiosDisponiveis = geoStore.municipiosPorFiltro(
      filterStore.selectedUF,
      newRegiao,
      filterStore.selectedUnidadePf,
    );
    if (
      !municipiosDisponiveis.some(
        (m) => m.value === filterStore.selectedMunicipio,
      )
    ) {
      filterStore.selectedMunicipio = "Todos";
    }
  },
);

watch(
  () => filterStore.selectedMunicipio,
  (newMun) => {
    const unidadesDisponiveis = geoStore.jurisdicoesPorFiltro(
      filterStore.selectedUF,
      filterStore.selectedRegiaoSaude,
      newMun,
    );
    if (!unidadesDisponiveis.includes(filterStore.selectedUnidadePf)) {
      filterStore.selectedUnidadePf = "Todos";
    }
  },
);

watch(
  () => filterStore.selectedUnidadePf,
  (newUnidade) => {
    const municipiosDisponiveis = geoStore.municipiosPorFiltro(
      filterStore.selectedUF,
      filterStore.selectedRegiaoSaude,
      newUnidade,
    );
    if (
      !municipiosDisponiveis.some(
        (m) => m.value === filterStore.selectedMunicipio,
      )
    ) {
      filterStore.selectedMunicipio = "Todos";
    }
  },
);

const situacaoOptions = FILTER_OPTIONS.situacao;
const msOptions = FILTER_OPTIONS.ms;
const porteOptions = FILTER_OPTIONS.porte;
const grandeRedeOptions = FILTER_OPTIONS.grandeRede;
const parTeiaOptions = FILTER_OPTIONS.parTeia;
const socioBeneficioOptions = FILTER_OPTIONS.socioBeneficio;
const socioEsocialOptions = FILTER_OPTIONS.socioEsocial;
const clusterOptions = FILTER_OPTIONS.cluster;
const rfaOptions = FILTER_OPTIONS.rfa;

const filterTooltips = Object.freeze({
  clearAll: filterActionTooltip(
    "Limpar todos os filtros",
    "Remove os filtros aplicados e restaura os valores padrão.",
    "pi-eraser",
  ),
  clear: filterActionTooltip(
    "Limpar filtro",
    "Restaura este filtro ao valor padrão.",
    "pi-eraser",
  ),
  clearSearch: filterActionTooltip(
    "Limpar busca",
    "Remove o texto digitado na busca de filtros.",
    "pi-times",
  ),
  establishment: filterTooltip("estabelecimento"),
  uf: filterTooltip("uf"),
  regiao: filterTooltip("regiao"),
  municipio: filterTooltip("municipio"),
  unidadePf: filterTooltip("unidadePf"),
  situacao: filterTooltip("situacao"),
  ms: filterTooltip("ms"),
  porte: filterTooltip("porte"),
  grandeRede: filterTooltip("grandeRede"),
  percentual: filterTooltip("percentual"),
  periodo: filterTooltip("periodo"),
  valorMin: filterTooltip("valorMin"),
  populacaoMunicipio: filterTooltip("populacaoMunicipio"),
  parTeia: filterTooltip("parTeia"),
  cnaeIncompativel: filterTooltip("cnaeIncompativel"),
  socioIdadeAtipica: filterTooltip("socioIdadeAtipica"),
  socioFalecido: filterTooltip("socioFalecido"),
  socioBeneficio: filterTooltip("socioBeneficio"),
  socioEsocial: filterTooltip("socioEsocial"),
  dispersaoUfSemFronteira: filterTooltip("dispersaoUfSemFronteira"),
  volumeAtipico: filterTooltip("volumeAtipico"),
  seq: filterTooltip("seq"),
});

const activeFiltersTooltip = computed(() =>
  filterActionTooltip(
    "Filtros ativos",
    `Existem ${activeFilterCount.value} filtro${activeFilterCount.value === 1 ? "" : "s"} ativo${activeFilterCount.value === 1 ? "" : "s"}. Clique para abrir a sidebar e revisar a seleção.`,
    "pi-filter",
  ),
);

const panelTooltip = computed(() =>
  filterActionTooltip(
    isCollapsed.value ? "Abrir painel" : "Fechar painel",
    isCollapsed.value
      ? "Exibe a sidebar com os filtros de pesquisa."
      : "Oculta a sidebar com os filtros de pesquisa.",
    isCollapsed.value ? "pi-angle-right" : "pi-angle-left",
  ),
);

const lockTooltip = computed(() =>
  filterActionTooltip(
    isSidebarLocked.value ? "Sidebar travada" : "Travar sidebar",
    isSidebarLocked.value
      ? "A sidebar permanece aberta ou fechada até ser destravada."
      : "Mantém a sidebar na posição atual durante a navegação.",
    isSidebarLocked.value ? "pi-lock" : "pi-lock-open",
  ),
);


// ── Autocomplete de Estabelecimento (CNPJ / Razão Social) ───────────────────
const cnpjSuggestions = ref([]);

function searchEstabelecimento(event) {
  const q = (event.query || "").trim().toLowerCase();
  if (q.length < 2) {
    cnpjSuggestions.value = [];
    return;
  }
  const lista = geoStore.cnpjLookup;
  const numericQ = q.replace(/\D/g, "");
  // Divide a query em tokens e exige que TODOS estejam presentes (qualquer ordem)
  const tokens = q.split(/\s+/).filter(Boolean);
  cnpjSuggestions.value = lista
    .filter((e) => {
      if (numericQ.length >= 4 && e.cnpj?.includes(numericQ)) return true;
      const nome = e.razao_social?.toLowerCase() ?? "";
      return tokens.every((t) => nome.includes(t));
    })
    .slice(0, 40)
    .map((e) => ({
      label: e.razao_social,
      cnpj: e.cnpj,
      municipio: e.municipio,
      uf: e.uf,
    }));
}

function onEstabelecimentoSelect(event) {
  // Ao selecionar uma sugestão, preenche com o CNPJ completo
  filterStore.selectedCnpjRaiz = event.value.cnpj;
}

// ── Controle collapse/lock da sidebar ───────────────────────────────────────
const isCollapsed = computed({
  get: () => filterStore.sidebarCollapsed,
  set: (val) => {
    filterStore.sidebarCollapsed = val;
  },
});

const isSidebarLocked = computed({
  get: () => filterStore.sidebarLocked,
  set: (val) => {
    filterStore.sidebarLocked = val;
  },
});

const toggleSidebarLock = () => {
  isSidebarLocked.value = !isSidebarLocked.value;
};

// ── Rotas que bloqueiam todos os filtros e colapsam a sidebar ────────────────
const LOCKED_ROUTES = ["/listas"];
const isLockedRoute = (path) => LOCKED_ROUTES.some((r) => path.startsWith(r));

// Em telas de detalhe de CNPJ apenas o Período de Análise fica disponível
const isEstabelecimentoRoute = computed(() =>
  route.path.startsWith("/estabelecimentos/"),
);
const isWatchlistRoute = computed(() => route.path.startsWith("/listas"));
const isDetailLimitedRoute = computed(
  () => isEstabelecimentoRoute.value,
);
const isPeriodOnlyRoute = computed(
  () => isWatchlistRoute.value,
);

// Bloqueia todos os filtros exceto o Período (usado pelo template em cada seção)
const allFiltersLocked = computed(
  () => filtersLocked.value || isPeriodOnlyRoute.value || isDetailLimitedRoute.value,
);

watch(
  () => route.path,
  (path) => {
    const locked = isLockedRoute(path);
    const isHome = path === "/";
    const isEstab = path.startsWith("/estabelecimentos/");
    filterStore.filtersLocked = locked;
    if (!filterStore.sidebarLocked) {
      filterStore.sidebarCollapsed = locked || isHome || isEstab;
    }
  },
  { immediate: true },
);

// ── Operações de filtro ──────────────────────────────────────────────────────
const limparFiltros = () => {
  filterStore.resetFilters();
  filterStore.selectedCnpjRaiz = "";
  resetYears();
};

const applyPercentualNaoComprovacao = () => {
  filterStore.percentualNaoComprovacaoFilter = [
    ...filterStore.percentualNaoComprovacaoRange,
  ];
};

// Faixa do % de não comprovação (seletor com atalhos + faixa personalizada).
const percentualAtalhos = [
  { value: "todos", label: "Todos (0% a 100%)", faixa: [0, 100] },
  ...[10, 20, 40, 60, 80].map((v) => ({ value: `min-${v}`, label: `≥ ${v}%`, faixa: [v, 100] })),
];
const percentualRotulo = computed(() => {
  const [inicio, fim] = filterStore.percentualNaoComprovacaoRange;
  if (fim === 100 && inicio > 0) return `≥ ${inicio}%`;
  return `${inicio}% a ${fim}%`;
});
function aplicarFaixaPercentual(faixa) {
  filterStore.percentualNaoComprovacaoRange = faixa;
  applyPercentualNaoComprovacao();
}

const applyValorMinSemComp = () => {
  filterStore.valorMinSemCompFilter = filterStore.valorMinSemComp;
};

// Valor mínimo sem comprovação (seletor com atalhos + valor personalizado).
const formatarReais = (valor) =>
  valor.toLocaleString("pt-BR", { style: "currency", currency: "BRL", maximumFractionDigits: 0 });
const valorMinAtalhos = [
  { value: "sem-minimo", label: "Sem valor mínimo", faixa: [0] },
  ...[100000, 300000, 500000].map((v) => ({ value: `min-${v}`, label: `≥ ${formatarReais(v)}`, faixa: [v] })),
];
const valorMinRotulo = computed(() => (
  filterStore.valorMinSemComp > 0 ? `≥ ${formatarReais(filterStore.valorMinSemComp)}` : "Sem valor mínimo"
));
function aplicarValorMin([valor]) {
  filterStore.valorMinSemComp = valor;
  applyValorMinSemComp();
}

// População do município (seletor com atalhos de porte + faixa aberta).
const formatarHabitantes = (valor) => Number(valor).toLocaleString("pt-BR", { maximumFractionDigits: 0 });
const populacaoRotulo = computed(() => {
  const [min, max] = filterStore.populacaoMunicipio;
  const atalho = POPULACAO_MUNICIPIO_ATALHOS.find((a) => a.faixa[0] === min && a.faixa[1] === max);
  if (atalho) return atalho.label;
  if (max === null) return `≥ ${formatarHabitantes(min)} hab.`;
  if (min === null) return `≤ ${formatarHabitantes(max)} hab.`;
  return `${formatarHabitantes(min)} a ${formatarHabitantes(max)} hab.`;
});
function aplicarPopulacao([min, max]) {
  filterStore.populacaoMunicipio = [min, max];
}

// Autorizações em sequência na farmácia (tipo + severidade mínima + faixa de dias).
const seqDiasRotulo = computed(() => {
  const [min, max] = filterStore.seqDias;
  const atalho = SEQ_DIAS_ATALHOS.find((a) => a.faixa[0] === min && a.faixa[1] === max);
  if (atalho) return atalho.label;
  const fmt = (v) => Number(v).toLocaleString("pt-BR");
  if (min !== null && min === max) return `= ${fmt(min)}`;
  if (max === null) return `≥ ${fmt(min)}`;
  if (min === null) return `≤ ${fmt(max)}`;
  return `${fmt(min)} a ${fmt(max)}`;
});
const seqAtivo = computed(() => isFilterActive("seqSeveridade") || isFilterActive("seqDias"));
function limparSeq() {
  filterStore.seqTipo = FILTER_DEFAULTS.SEQ_TIPO;
  filterStore.seqSeveridade = FILTER_DEFAULTS.SEQ_SEVERIDADE;
  filterStore.seqDias = [...FILTER_DEFAULTS.SEQ_DIAS_RANGE];
}

// Aumento semestral atípico (seletor de limite único; [0] = desligado).
const formatarPercentual = (valor) => `${Number(valor).toLocaleString("pt-BR")}%`;
const volumeAtipicoAtalhos = [
  { value: "desligado", label: "Desligado", faixa: [0] },
  ...[50, 500, 1000, 1500].map((v) => ({ value: `min-${v}`, label: `≥ ${formatarPercentual(v)}`, faixa: [v] })),
];
const volumeAtipicoValor = computed(() => (
  filterStore.volumeAtipicoEnabled ? [filterStore.volumeAtipicoPercentualFilter] : [0]
));
const volumeAtipicoRotulo = computed(() => (
  filterStore.volumeAtipicoEnabled ? `≥ ${formatarPercentual(filterStore.volumeAtipicoPercentualFilter)}` : "Desligado"
));
function aplicarVolumeAtipico([valor]) {
  if (valor === 0) {
    clearVolumeAtipico();
    return;
  }
  filterStore.volumeAtipicoEnabled = true;
  filterStore.volumeAtipicoPercentual = valor;
  filterStore.volumeAtipicoPercentualFilter = valor;
}

function clearVolumeAtipico() {
  filterStore.volumeAtipicoEnabled = FILTER_DEFAULTS.VOLUME_ATIPICO_ENABLED;
  filterStore.volumeAtipicoPercentual =
    FILTER_DEFAULTS.VOLUME_ATIPICO_PERCENTUAL;
  filterStore.volumeAtipicoPercentualFilter =
    FILTER_DEFAULTS.VOLUME_ATIPICO_PERCENTUAL;
}

// Vendas para UFs sem fronteira (seletor de limite único; [0] = desligado).
const dispersaoUfAtalhos = [
  { value: "desligado", label: "Desligado", faixa: [0] },
  ...[10, 20, 30, 50].map((v) => ({ value: `min-${v}`, label: `≥ ${v}%`, faixa: [v] })),
];
const dispersaoUfValor = computed(() => (
  filterStore.dispersaoUfSemFronteiraEnabled ? [filterStore.dispersaoUfSemFronteiraPercentual] : [0]
));
const dispersaoUfRotulo = computed(() => (
  filterStore.dispersaoUfSemFronteiraEnabled ? `≥ ${filterStore.dispersaoUfSemFronteiraPercentual}%` : "Desligado"
));
function aplicarDispersaoUf([valor]) {
  if (valor === 0) {
    clearDispersaoUfSemFronteira();
    return;
  }
  filterStore.dispersaoUfSemFronteiraEnabled = true;
  filterStore.dispersaoUfSemFronteiraPercentual = valor;
}

function clearDispersaoUfSemFronteira() {
  filterStore.dispersaoUfSemFronteiraEnabled =
    FILTER_DEFAULTS.DISPERSAO_UF_SEM_FRONTEIRA_ENABLED;
  filterStore.dispersaoUfSemFronteiraPercentual =
    FILTER_DEFAULTS.DISPERSAO_UF_SEM_FRONTEIRA_PERCENTUAL;
}

// Força foco no campo de busca do Dropdown ao abrir
const onDropdownShow = () => {
  setTimeout(() => {
    const input = document.querySelector(".p-dropdown-filter");
    if (input) input.focus();
  }, TIMING.DROPDOWN_FOCUS_DELAY);
};

// Detecta se o valor do filtro mudou em relação ao padrão
const isFilterActive = (field) => {
  const value = filterStore[field];
  const mapStoreToConstants = {
    selectedUF: FILTER_DEFAULTS.UF,
    selectedRegiaoSaude: FILTER_DEFAULTS.REGIAO,
    selectedMunicipio: FILTER_DEFAULTS.MUNICIPIO,
    selectedUnidadePf: FILTER_DEFAULTS.UNIDADE_PF,
    selectedSituacao: FILTER_DEFAULTS.SITUACAO,
    selectedMS: FILTER_DEFAULTS.MS,
    selectedPorte: FILTER_DEFAULTS.PORTE,
    selectedGrandeRede: FILTER_DEFAULTS.GRANDE_REDE,
    selectedParTeia: FILTER_DEFAULTS.PAR_TEIA,
    selectedSocioBeneficio: FILTER_DEFAULTS.SOCIO_BENEFICIO,
    selectedSocioEsocial: FILTER_DEFAULTS.SOCIO_ESOCIAL,
    selectedCnaeIncompativel: FILTER_DEFAULTS.CNAE_INCOMPATIVEL,
    selectedSocioIdadeAtipica: FILTER_DEFAULTS.SOCIO_IDADE_ATIPICA,
    selectedSocioFalecido: FILTER_DEFAULTS.SOCIO_FALECIDO,
    selectedCnpjRaiz: "",
    percentualNaoComprovacaoRange: FILTER_DEFAULTS.PERCENTUAL_RANGE,
    valorMinSemComp: FILTER_DEFAULTS.VALOR_MIN,
    populacaoMunicipio: FILTER_DEFAULTS.POPULACAO_MUNICIPIO_RANGE,
    seqSeveridade: FILTER_DEFAULTS.SEQ_SEVERIDADE,
    seqDias: FILTER_DEFAULTS.SEQ_DIAS_RANGE,
    volumeAtipicoEnabled: FILTER_DEFAULTS.VOLUME_ATIPICO_ENABLED,
    volumeAtipicoPercentual: FILTER_DEFAULTS.VOLUME_ATIPICO_PERCENTUAL,
    dispersaoUfSemFronteiraEnabled: FILTER_DEFAULTS.DISPERSAO_UF_SEM_FRONTEIRA_ENABLED,
    dispersaoUfSemFronteiraPercentual: FILTER_DEFAULTS.DISPERSAO_UF_SEM_FRONTEIRA_PERCENTUAL,
    clusterSelection: FILTER_DEFAULTS.CLUSTER,
    rfaSelection: FILTER_DEFAULTS.RFA,
    searchTarget: FILTER_DEFAULTS.SEARCH,
    sliderValue: FILTER_DEFAULTS.SLIDER_INDEX_RANGE,
  };
  const defaultValue = mapStoreToConstants[field];
  if (field === "volumeAtipicoPercentual") {
    return filterStore.volumeAtipicoEnabled && value !== defaultValue;
  }
  if (field === "dispersaoUfSemFronteiraPercentual") {
    return filterStore.dispersaoUfSemFronteiraEnabled && value !== defaultValue;
  }
  if (Array.isArray(value))
    return JSON.stringify(value) !== JSON.stringify(defaultValue);
  return value !== defaultValue;
};

const periodFilterLocked = computed(
  () => filtersLocked.value && !isPeriodOnlyRoute.value,
);
const volumeAtipicoFilterLocked = computed(
  () => filtersLocked.value || isPeriodOnlyRoute.value,
);

const activeFilterCount = computed(() => {
  const fields = [
    "selectedUF",
    "selectedRegiaoSaude",
    "selectedMunicipio",
    "selectedUnidadePf",
    "selectedSituacao",
    "selectedMS",
    "selectedPorte",
    "selectedGrandeRede",
    "selectedParTeia",
    "selectedSocioBeneficio",
    "selectedSocioEsocial",
    "selectedCnaeIncompativel",
    "selectedSocioIdadeAtipica",
    "selectedSocioFalecido",
    "dispersaoUfSemFronteiraEnabled",
    "selectedCnpjRaiz",
    "percentualNaoComprovacaoRange",
    "valorMinSemComp",
    "populacaoMunicipio",
    "volumeAtipicoEnabled",
    "seqSeveridade",
    "seqDias",
    "sliderValue",
    "clusterSelection",
    "rfaSelection",
    "searchTarget",
  ];
  return fields.filter((f) => isFilterActive(f)).length;
});

const countActiveFilters = (fields) =>
  fields.filter((field) => isFilterActive(field)).length;

const generalFilterCount = computed(() =>
  countActiveFilters([
    "selectedUF",
    "selectedRegiaoSaude",
    "selectedMunicipio",
    "selectedUnidadePf",
    "selectedSituacao",
    "selectedMS",
    "selectedPorte",
    "selectedGrandeRede",
    "selectedCnpjRaiz",
    "sliderValue",
    "percentualNaoComprovacaoRange",
    "valorMinSemComp",
    "populacaoMunicipio",
  ]),
);

const integrityFilterCount = computed(() =>
  countActiveFilters([
    "selectedParTeia",
    "selectedSocioBeneficio",
    "selectedSocioEsocial",
    "selectedCnaeIncompativel",
    "selectedSocioIdadeAtipica",
    "selectedSocioFalecido",
    "dispersaoUfSemFronteiraEnabled",
    "volumeAtipicoEnabled",
    "seqSeveridade",
    "seqDias",
  ]),
);


// ── Período de análise (seletor de meses) ────────────────────────────────────
// Atalhos, intervalo e aplicação ficam em usePeriodoAnalise (o chip de período de
// /listas usa o mesmo seletor).
const {
  timeSliderValue,
  applySliderPeriod,
  resetYears,
  PERIODO_MIN,
  PERIODO_MAX,
  periodoAtalhos,
  periodoSelecionado,
  periodoAtalhoAtivo,
  periodoRotulo,
  aplicarPeriodo,
  aplicarAtalhoPeriodo,
} = usePeriodoAnalise();

onMounted(() => applySliderPeriod(timeSliderValue.value));

// Limpa o filtro de período — para a animação sem restaurar o range salvo,
// depois delega ao resetYears para restaurar o padrão.
const clearPeriodFilter = () => {
  filterStore.resetAnimationPreview();
  resetYears();
};

// Para o play e reseta preload ao navegar para outra rota
watch(
  () => route.path,
  () => {
    filterStore.resetAnimationPreview();
  },
);

// Limpa o intervalo ao desmontar o componente
onBeforeUnmount(() => {
  filterStore.resetAnimationPreview();
});

// === ORGANIZAÇÃO DA SIDEBAR: ACORDEÃO + BUSCA ===
// Índice declarativo dos filtros. Cada entrada é usada para:
//   1) control de visibilidade via busca (v-show)
//   2) badge de matches por seção durante a busca
//   3) restrição dos filtros contextuais à rota que os exibe
const FILTER_INDEX = [
  { id: "uf", section: "geral", label: "UF", keywords: "unidade federativa estado sg sigla" },
  { id: "regiao", section: "geral", label: "Região de Saúde", keywords: "regiao saude id regiao saude id_regiao_saude" },
  { id: "municipio", section: "geral", label: "Município", keywords: "municipio cidade id ibge ibge7" },
  { id: "unidadePf", section: "geral", label: "Jurisdição PF", keywords: "jurisdicao da pf unidade pf delegacia policia federal regional" },
  { id: "situacao", section: "geral", label: "Situação RF", keywords: "situacao rf receita federal ativa baixada inapta" },
  { id: "ms", section: "geral", label: "Conexão MS", keywords: "ms ministerio saude tipo estabelecimento" },
  { id: "porte", section: "geral", label: "Porte CNPJ", keywords: "porte empresa tamanho" },
  { id: "grandeRede", section: "geral", label: "Grande Rede", keywords: "grande rede bandeira franquia" },
  { id: "cnpjRaiz", section: "geral", label: "Estabelecimento", keywords: "cnpj raiz cnpj_raiz matriz grupo empresarial razao social nome fantasia farmacia" },
  { id: "parTeia", section: "integridade", label: "CNPJs com PAR", keywords: "par teia socios rede societaria cnpj cpf" },
  { id: "cnaeIncompativel", section: "integridade", label: "CNPJ com CNAE Incompatível", keywords: "cnae incompativel atividade economica incompatibilidade" },
  { id: "socioIdadeAtipica", section: "integridade", label: "Sócio < 21 anos ou > 80 anos", keywords: "idade atipica socio jovem idoso 21 80 anos" },
  { id: "socioFalecido", section: "integridade", label: "Sócio ativo falecido", keywords: "socio falecido obito morte cpf base obitos" },
  { id: "socioBeneficio", section: "integridade", label: "Sócio no CadÚnico/Defeso", keywords: "socio beneficio bolsa familia cadunico seguro defeso pobreza" },
  { id: "socioEsocial", section: "integridade", label: "Sócio com Vínculo eSocial", keywords: "socio esocial vinculo emprego clt vinculo trabalhista" },
  { id: "dispersaoUf", section: "integridade", label: "Vendas para UFs sem Fronteira", keywords: "dispersao uf sem fronteira geografica distancia venda autorizado" },
  { id: "volumeAtipico", section: "integridade", label: "Aumento Semestral Atípico", keywords: "volume atipico crescimento semestral faturamento auditoria aumento anomalo" },
  { id: "seq", section: "integridade", label: "Autorizações em sequência", keywords: "sequencia rajada surto unico multiplos crms autorizacoes minutos alerta severidade" },
  { id: "percentual", section: "geral", label: "% de não comprovação", keywords: "percentual nao comprovacao risco faixa auditoria" },
  { id: "slider", section: "geral", label: "Período de Análise", keywords: "periodo slider semestral mensal tempo data" },
  { id: "populacao", section: "geral", label: "População do município", keywords: "populacao habitantes municipio porte pequeno medio grande metropole ibge" },
  { id: "valorMin", section: "geral", label: "Valor Mínimo sem Comprovação", keywords: "valor minimo sem comprovacao reais auditoria financeiro ticket" },
  { id: "busca", section: "geral", label: "Busca Alvo", keywords: "cpf/cnpj alvo busca id cnpj pesquisar rede", routes: ["/alvos/cluster", "/alvos/rede"] },
  { id: "cluster", section: "geral", label: "Target Cluster", keywords: "cluster agrupamento kmeans segmento", routes: ["/alvos/cluster"] },
  { id: "rfa", section: "geral", label: "Risco (RFA)", keywords: "rfa receita federal ativos cnae", routes: ["/alvos/cluster"] },
];

const FILTER_INDEX_BY_ID = new Map(FILTER_INDEX.map((filter) => [filter.id, filter]));

const collapsedSections = ref(new Set(["integridade"]));
const sidebarSearch = ref("");

// IDs válidos de seção. Usado pelo acordeão exclusivo: ao abrir uma seção,
// as demais são marcadas como fechadas (Set contém os IDs colapsados).
const SECTION_IDS = ["geral", "integridade"];

const toggleSection = (id) => {
  const isOpen = !collapsedSections.value.has(id);
  if (isOpen) {
    // Fecha este. Mantém os outros estados.
    const next = new Set(collapsedSections.value);
    next.add(id);
    collapsedSections.value = next;
  } else {
    // Abre este e fecha os outros (acordeão exclusivo).
    collapsedSections.value = new Set(
      SECTION_IDS.filter((sid) => sid !== id),
    );
  }
};

const isSectionCollapsed = (id) => effectiveCollapsed.value.has(id);

// === BUSCA ===
const normalize = (s) =>
  (s || "")
    .toLowerCase()
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "");

// Busca só ativa a partir de 2 caracteres para evitar matches em 1 letra
// (que retorna ruído em quase todos os grupos).
const searchTerm = computed(() => {
  const term = normalize(sidebarSearch.value.trim());
  return term.length >= 2 ? term : "";
});

const filterMatchesSearch = (filterMeta) => {
  if (!searchTerm.value) return true;
  const haystack = normalize(`${filterMeta.label} ${filterMeta.keywords}`);
  return haystack.includes(searchTerm.value);
};

const isFilterAvailable = (filterMeta) =>
  !filterMeta.routes || filterMeta.routes.includes(route.path);

const shouldShowFilter = (filterId) => {
  const meta = FILTER_INDEX_BY_ID.get(filterId);
  if (!meta) throw new Error(`Filtro ausente do índice de busca: ${filterId}`);
  return isFilterAvailable(meta) && filterMatchesSearch(meta);
};

const shouldDisplayFilter = (sectionId, filterId) => {
  if (isSectionCollapsed(sectionId)) return false;
  return shouldShowFilter(filterId);
};

// Grupos de cada seção (subtítulos na barra). O subtítulo aparece quando algum
// filtro do grupo está visível (seção aberta, filtro disponível e dentro da busca).
const FILTER_GROUPS = Object.freeze({
  periodoValores: ["slider", "percentual", "valorMin"],
  territorio: ["uf", "regiao", "municipio", "unidadePf", "populacao"],
  estabelecimento: ["situacao", "ms", "porte", "grandeRede", "cnpjRaiz"],
  empresa: ["parTeia", "cnaeIncompativel"],
  socios: ["socioIdadeAtipica", "socioFalecido", "socioBeneficio", "socioEsocial"],
  vendas: ["dispersaoUf", "volumeAtipico", "seq"],
});
const shouldDisplayGroup = (sectionId, groupId) => {
  const filtros = FILTER_GROUPS[groupId];
  if (!filtros) throw new Error(`Grupo de filtros desconhecido: ${groupId}`);
  return filtros.some((filterId) => shouldDisplayFilter(sectionId, filterId));
};

const sectionMatchCount = (sectionId) =>
  FILTER_INDEX.filter(
    (f) => f.section === sectionId && isFilterAvailable(f) && filterMatchesSearch(f),
  ).length;

const shouldShowSection = (sectionId) => {
  if (!searchTerm.value) return true;
  return sectionMatchCount(sectionId) > 0;
};

// `collapsedSections` é o estado MANUAL do acordeão. `effectiveCollapsed`
// é o estado EFETIVO usado pelo template: durante a busca, força a abertura
// de qualquer seção que tenha matches (suspende o acordeão).
const effectiveCollapsed = computed(() => {
  if (!searchTerm.value) return collapsedSections.value;
  const result = new Set(collapsedSections.value);
  for (const id of SECTION_IDS) {
    if (sectionMatchCount(id) > 0) {
      result.delete(id);
    }
  }
  return result;
});

const clearSearch = () => {
  sidebarSearch.value = "";
};
</script>

<template>
  <!-- BOTÃO DE LIMPAR TODOS OS FILTROS (ALÇA) -->
  <button
    v-if="activeFilterCount > 0"
    class="sidebar-clear-btn"
    @click="filterStore.resetFilters()"
    v-tooltip.right="filterTooltips.clearAll"
    aria-label="Limpar todos os filtros"
  >
    <i class="pi pi-eraser"></i>
  </button>

  <!-- BOTÃO DE FILTROS ATIVOS (ALÇA) -->
  <button
    v-if="activeFilterCount > 0"
    class="sidebar-filter-count-btn"
    @click="isCollapsed = false"
    v-tooltip.right="activeFiltersTooltip"
  >
    <i class="pi pi-filter"></i>
    <span class="filter-count-badge">{{ activeFilterCount }}</span>
  </button>

  <!-- BOTÃO FLUTUANTE (ALÇA) — Segue a borda da sidebar -->
  <button
    class="sidebar-float-btn"
    @click="isCollapsed = !isCollapsed"
    v-tooltip.right="panelTooltip"
  >
    <i :class="isCollapsed ? 'pi pi-angle-right' : 'pi pi-angle-left'"></i>
  </button>

  <!-- BOTÃO DE CADEADO -->
  <button
    class="sidebar-lock-btn"
    :class="{ locked: isSidebarLocked }"
    @click="toggleSidebarLock"
    v-tooltip.right="lockTooltip"
  >
    <i :class="isSidebarLocked ? 'pi pi-lock' : 'pi pi-lock-open'"></i>
  </button>

  <!-- BARRA LATERAL -->
  <aside class="admin-sidebar">
    <DataIntegrityBanner />

    <div class="sidebar-content">
      <div class="sidebar-title-simple">
        <i class="pi pi-sliders-h"></i>
        <span>FILTROS DE PESQUISA</span>
      </div>

      <!-- BUSCA DE FILTROS -->
      <div class="sidebar-search" :class="{ 'has-value': sidebarSearch }">
        <i class="pi pi-search sidebar-search-icon"></i>
        <input
          v-model="sidebarSearch"
          type="text"
          class="sidebar-search-input"
          placeholder="Buscar filtro..."
          aria-label="Buscar filtro"
        />
        <button
          v-if="sidebarSearch"
          class="sidebar-search-clear"
          @click="clearSearch"
          v-tooltip.bottom="filterTooltips.clearSearch"
          aria-label="Limpar busca"
        >
          <i class="pi pi-times"></i>
        </button>
      </div>

      <!-- BANNER DE FILTROS BLOQUEADOS -->
      <div v-if="allFiltersLocked" class="filters-locked-banner">
        <i class="pi pi-lock" />
        <span v-if="isDetailLimitedRoute">
          Período e Aumento Semestral Atípico estão disponíveis nesta tela
        </span>
        <span v-else-if="isPeriodOnlyRoute"
          >Apenas o Período de Análise está disponível nesta tela</span
        >
        <span v-else>Filtros indisponíveis nesta tela</span>
      </div>

      <button
        v-show="shouldShowSection('geral')"
        class="sidebar-section-heading"
        :class="{ collapsed: isSectionCollapsed('geral'), searching: !!searchTerm }"
        @click="toggleSection('geral')"
        :aria-expanded="!isSectionCollapsed('geral')"
        aria-controls="sidebar-section-geral"
      >
        <span><i class="pi pi-th-large"></i> Geral</span>
        <small v-if="searchTerm">{{ sectionMatchCount('geral') }}</small>
        <small v-else-if="generalFilterCount">{{ generalFilterCount }}</small>
        <i class="pi pi-chevron-down sidebar-section-chevron"></i>
      </button>

      <!-- FILTROS GLOBAIS -->
      <div v-show="!isSectionCollapsed('geral')" class="sidebar-section-body">
      <div v-show="shouldDisplayGroup('geral', 'periodoValores')" class="filter-group-title"><i class="pi pi-filter" aria-hidden="true" />Período e valores</div>
      <div
        v-show="shouldDisplayFilter('geral', 'slider')"
        class="filter-section"
        :class="{ 'filter-locked-alt': periodFilterLocked }"
      >
        <label class="filter-label" style="pointer-events: auto">
          Período de análise
          <i
            class="pi pi-info-circle filter-info-icon help-icon"
            role="img"
            tabindex="0"
            aria-label="Explicação do filtro Período de Análise"
            v-tooltip.right="filterTooltips.periodo"
          />
          <button
            v-if="isFilterActive('sliderValue')"
            class="filter-clear-btn"
            @click="clearPeriodFilter"
            v-tooltip.right="filterTooltips.clear"
          >
            <i class="pi pi-eraser" />
          </button>
        </label>
        <div
          class="slider-container"
          :class="{
            'filter-locked': periodFilterLocked,
            'filter-active-box': isFilterActive('sliderValue'),
          }"
        >
          <MonthRangePicker
            :rotulo="periodoRotulo"
            :inicio="periodoSelecionado.inicio"
            :fim="periodoSelecionado.fim"
            :min="PERIODO_MIN"
            :max="PERIODO_MAX"
            :atalhos="periodoAtalhos"
            :atalho-ativo="periodoAtalhoAtivo"
            :disabled="periodFilterLocked"
            @select-range="aplicarPeriodo"
            @select-atalho="aplicarAtalhoPeriodo"
          />
        </div>
      </div>

      <div
        v-show="shouldDisplayFilter('geral', 'percentual')"
        class="filter-section"
        :class="{ 'filter-locked': allFiltersLocked }"
      >
        <label class="filter-label">
          % de não comprovação
          <i
            class="pi pi-info-circle filter-info-icon help-icon"
            role="img"
            tabindex="0"
            aria-label="Explicação do filtro de percentual de não comprovação"
            v-tooltip.right="filterTooltips.percentual"
          />
          <button
            v-if="isFilterActive('percentualNaoComprovacaoRange')"
            class="filter-clear-btn"
            @click="
              () => {
                filterStore.percentualNaoComprovacaoRange = [0, 100];
                applyPercentualNaoComprovacao();
              }
            "
            v-tooltip.right="filterTooltips.clear"
          >
            <i class="pi pi-eraser" />
          </button>
        </label>
        <div
          class="slider-container"
          :class="{
            'filter-active-box': isFilterActive(
              'percentualNaoComprovacaoRange',
            ),
          }"
        >
          <NumberRangePicker
            :mostrar-icone="false"
            :valor="filterStore.percentualNaoComprovacaoRange"
            :min="0"
            :max="100"
            sufixo="%"
            :atalhos="percentualAtalhos"
            :rotulo="percentualRotulo"
            :disabled="allFiltersLocked"
            @select-range="aplicarFaixaPercentual"
          />
        </div>
      </div>

      <div
        v-show="shouldDisplayFilter('geral', 'valorMin')"
        class="filter-section"
        :class="{ 'filter-locked': allFiltersLocked }"
      >
        <label class="filter-label">
          Valor mínimo sem comprovação
          <i
            class="pi pi-info-circle filter-info-icon help-icon"
            role="img"
            tabindex="0"
            aria-label="Explicação do filtro Valor mínimo sem comprovação"
            v-tooltip.right="filterTooltips.valorMin"
          />
          <button
            v-if="isFilterActive('valorMinSemComp')"
            class="filter-clear-btn"
            @click="
              () => {
                filterStore.valorMinSemComp = 0;
                applyValorMinSemComp();
              }
            "
            v-tooltip.right="filterTooltips.clear"
          >
            <i class="pi pi-eraser" />
          </button>
        </label>
        <div
          class="slider-container"
          :class="{ 'filter-active-box': isFilterActive('valorMinSemComp') }"
        >
          <NumberRangePicker
            icone="pi-dollar"
            unico
            :valor="[filterStore.valorMinSemComp]"
            :min="0"
            :max="FILTER_DEFAULTS.VALOR_MAX"
            :passo="10000"
            prefixo="R$"
            :formatar="formatarReais"
            rotulo-personalizado="Valor personalizado"
            rotulo-campo="A partir de"
            :atalhos="valorMinAtalhos"
            :rotulo="valorMinRotulo"
            :disabled="allFiltersLocked"
            @select-range="aplicarValorMin"
          />
        </div>
      </div>

      <div v-show="shouldDisplayGroup('geral', 'territorio')" class="filter-group-title"><i class="pi pi-globe" aria-hidden="true" />Território</div>
      <div
        v-show="shouldDisplayFilter('geral', 'uf')"
        class="filter-section"
        :class="{ 'filter-locked': allFiltersLocked }"
      >
        <label class="filter-label">
          UF
          <i
            class="pi pi-info-circle filter-info-icon help-icon"
            role="img"
            tabindex="0"
            aria-label="Explicação do filtro UF"
            v-tooltip.right="filterTooltips.uf"
          />
          <button
            v-if="isFilterActive('selectedUF')"
            class="filter-clear-btn"
            @click="filterStore.selectedUF = FILTER_ALL_VALUE"
            v-tooltip.right="filterTooltips.clear"
          >
            <i class="pi pi-eraser" />
          </button>
        </label>
        <div class="filter-campo-icone">
        <i class="pi pi-map filter-campo-icone-i" aria-hidden="true" />
        <Dropdown
          v-model="filterStore.selectedUF"
          :options="ufOptions"
          placeholder="Estado"
          class="w-full filter-input"
          panelClass="sidebar-panel"
          :class="{ 'filter-active': isFilterActive('selectedUF') }"
        />
        </div>
      </div>

      <div
        v-show="shouldDisplayFilter('geral', 'regiao')"
        class="filter-section"
        :class="{ 'filter-locked': allFiltersLocked }"
      >
        <label class="filter-label">
          Região de saúde
          <i
            class="pi pi-info-circle filter-info-icon help-icon"
            role="img"
            tabindex="0"
            aria-label="Explicação do filtro Região de Saúde"
            v-tooltip.right="filterTooltips.regiao"
          />
          <button
            v-if="isFilterActive('selectedRegiaoSaude')"
            class="filter-clear-btn"
            @click="filterStore.selectedRegiaoSaude = FILTER_ALL_VALUE"
            v-tooltip.right="filterTooltips.clear"
          >
            <i class="pi pi-eraser" />
          </button>
        </label>
        <Dropdown
          v-model="filterStore.selectedRegiaoSaude"
          :options="regiaoSaudeOptions"
          optionLabel="label"
          optionValue="value"
          placeholder="Região"
          filter
          reset-filter-on-hide
          auto-option-focus
          filter-match-mode="contains"
          @show="onDropdownShow"
          :virtualScrollerOptions="{ itemSize: 32 }"
          panelClass="sidebar-panel"
          class="w-full filter-input"
          :class="{ 'filter-active': isFilterActive('selectedRegiaoSaude') }"
        />
      </div>

      <div
        v-show="shouldDisplayFilter('geral', 'municipio')"
        class="filter-section"
        :class="{ 'filter-locked': allFiltersLocked }"
      >
        <label class="filter-label">
          Município
          <i
            class="pi pi-info-circle filter-info-icon help-icon"
            role="img"
            tabindex="0"
            aria-label="Explicação do filtro Município"
            v-tooltip.right="filterTooltips.municipio"
          />
          <button
            v-if="isFilterActive('selectedMunicipio')"
            class="filter-clear-btn"
            @click="filterStore.selectedMunicipio = FILTER_ALL_VALUE"
            v-tooltip.right="filterTooltips.clear"
          >
            <i class="pi pi-eraser" />
          </button>
        </label>
        <div class="filter-campo-icone">
        <i class="pi pi-map-marker filter-campo-icone-i" aria-hidden="true" />
        <Dropdown
          v-model="filterStore.selectedMunicipio"
          :options="municipioOptions"
          placeholder="Município"
          filter
          optionLabel="label"
          optionValue="value"
          reset-filter-on-hide
          auto-option-focus
          filter-match-mode="contains"
          @show="onDropdownShow"
          :virtualScrollerOptions="{ itemSize: 32 }"
          panelClass="sidebar-panel"
          class="w-full filter-input"
          :class="{ 'filter-active': isFilterActive('selectedMunicipio') }"
        />
        </div>
      </div>

      <div
        v-show="shouldDisplayFilter('geral', 'unidadePf')"
        class="filter-section"
        :class="{ 'filter-locked': allFiltersLocked }"
      >
        <label class="filter-label">
          Jurisdição PF
          <i
            class="pi pi-info-circle filter-info-icon help-icon"
            role="img"
            tabindex="0"
            aria-label="Explicação do filtro Jurisdição PF"
            v-tooltip.right="filterTooltips.unidadePf"
          />
          <button
            v-if="isFilterActive('selectedUnidadePf')"
            class="filter-clear-btn"
            @click="filterStore.selectedUnidadePf = FILTER_ALL_VALUE"
            v-tooltip.right="filterTooltips.clear"
          >
            <i class="pi pi-eraser" />
          </button>
        </label>
        <div class="filter-campo-icone">
        <i class="pi pi-shield filter-campo-icone-i" aria-hidden="true" />
        <Dropdown
          v-model="filterStore.selectedUnidadePf"
          :options="unidadePfOptions"
          placeholder="Delegacia / Unidade PF"
          filter
          reset-filter-on-hide
          auto-option-focus
          filter-match-mode="contains"
          @show="onDropdownShow"
          :virtualScrollerOptions="{ itemSize: 32 }"
          class="w-full filter-input"
          panelClass="sidebar-panel"
          :class="{ 'filter-active': isFilterActive('selectedUnidadePf') }"
        />
        </div>
      </div>

      <div
        v-show="shouldDisplayFilter('geral', 'populacao')"
        class="filter-section"
        :class="{ 'filter-locked': allFiltersLocked }"
      >
        <label class="filter-label">
          População do município
          <i
            class="pi pi-info-circle filter-info-icon help-icon"
            role="img"
            tabindex="0"
            aria-label="Explicação do filtro População do município"
            v-tooltip.right="filterTooltips.populacaoMunicipio"
          />
          <button
            v-if="isFilterActive('populacaoMunicipio')"
            class="filter-clear-btn"
            @click="aplicarPopulacao([null, null])"
            v-tooltip.right="filterTooltips.clear"
          >
            <i class="pi pi-eraser" />
          </button>
        </label>
        <div
          class="slider-container"
          :class="{ 'filter-active-box': isFilterActive('populacaoMunicipio') }"
        >
          <NumberRangePicker
            icone="pi-users"
            aberto
            :valor="filterStore.populacaoMunicipio"
            :min="0"
            :max="Infinity"
            :passo="10000"
            :formatar="formatarHabitantes"
            sufixo="hab."
            :atalhos="POPULACAO_MUNICIPIO_ATALHOS"
            :rotulo="populacaoRotulo"
            :disabled="allFiltersLocked"
            @select-range="aplicarPopulacao"
          />
        </div>
      </div>

      <div v-show="shouldDisplayGroup('geral', 'estabelecimento')" class="filter-group-title"><i class="pi pi-building" aria-hidden="true" />Estabelecimento</div>
      <div v-show="!isSectionCollapsed('geral')" class="grid-filters" :class="{ 'filter-locked': allFiltersLocked }">
        <div v-show="shouldDisplayFilter('geral', 'situacao')" class="filter-section">
          <label class="filter-label">
            Situação RF
            <i
              class="pi pi-info-circle filter-info-icon help-icon"
              role="img"
              tabindex="0"
              aria-label="Explicação do filtro Situação RF"
              v-tooltip.right="filterTooltips.situacao"
            />
            <button
              v-if="isFilterActive('selectedSituacao')"
              class="filter-clear-btn"
              @click="filterStore.selectedSituacao = FILTER_ALL_VALUE"
              v-tooltip.right="filterTooltips.clear"
            >
              <i class="pi pi-eraser" />
            </button>
          </label>
          <Dropdown
            v-model="filterStore.selectedSituacao"
            :options="situacaoOptions"
            class="w-full filter-input"
            panelClass="sidebar-panel"
            :class="{ 'filter-active': isFilterActive('selectedSituacao') }"
          />
        </div>
        <div v-show="shouldDisplayFilter('geral', 'ms')" class="filter-section">
          <label class="filter-label">
            Conexão MS
            <i
              class="pi pi-info-circle filter-info-icon help-icon"
              role="img"
              tabindex="0"
              aria-label="Explicação do filtro Conexão MS"
              v-tooltip.right="filterTooltips.ms"
            />
            <button
              v-if="isFilterActive('selectedMS')"
              class="filter-clear-btn"
              @click="filterStore.selectedMS = FILTER_ALL_VALUE"
              v-tooltip.right="filterTooltips.clear"
            >
              <i class="pi pi-eraser" />
            </button>
          </label>
          <Dropdown
            v-model="filterStore.selectedMS"
            :options="msOptions"
            class="w-full filter-input"
            panelClass="sidebar-panel"
            :class="{ 'filter-active': isFilterActive('selectedMS') }"
          />
        </div>
      </div>

      <div v-show="!isSectionCollapsed('geral')" class="grid-filters" :class="{ 'filter-locked': allFiltersLocked }">
        <div v-show="shouldDisplayFilter('geral', 'porte')" class="filter-section">
          <label class="filter-label">
            Porte CNPJ
            <i
              class="pi pi-info-circle filter-info-icon help-icon"
              role="img"
              tabindex="0"
              aria-label="Explicação do filtro Porte CNPJ"
              v-tooltip.right="filterTooltips.porte"
            />
            <button
              v-if="isFilterActive('selectedPorte')"
              class="filter-clear-btn"
              @click="filterStore.selectedPorte = FILTER_ALL_VALUE"
              v-tooltip.right="filterTooltips.clear"
            >
              <i class="pi pi-eraser" />
            </button>
          </label>
          <Dropdown
            v-model="filterStore.selectedPorte"
            :options="porteOptions"
            class="w-full filter-input"
            panelClass="sidebar-panel"
            :class="{ 'filter-active': isFilterActive('selectedPorte') }"
          />
        </div>
        <div v-show="shouldDisplayFilter('geral', 'grandeRede')" class="filter-section">
          <label class="filter-label">
            Grande rede
            <i
              class="pi pi-info-circle filter-info-icon help-icon"
              role="img"
              tabindex="0"
              aria-label="Explicação do filtro Grande Rede"
              v-tooltip.right="filterTooltips.grandeRede"
            />
            <button
              v-if="isFilterActive('selectedGrandeRede')"
              class="filter-clear-btn"
              @click="filterStore.selectedGrandeRede = FILTER_ALL_VALUE"
              v-tooltip.right="filterTooltips.clear"
            >
              <i class="pi pi-eraser" />
            </button>
          </label>
          <Dropdown
            v-model="filterStore.selectedGrandeRede"
            :options="grandeRedeOptions"
            class="w-full filter-input"
            panelClass="sidebar-panel"
            :class="{ 'filter-active': isFilterActive('selectedGrandeRede') }"
          />
        </div>
      </div>

      <div
        v-show="shouldDisplayFilter('geral', 'cnpjRaiz')"
        class="filter-section"
        :class="{ 'filter-locked': allFiltersLocked }"
      >
        <label class="filter-label">
          Estabelecimento
          <i
            class="pi pi-info-circle filter-info-icon help-icon"
            role="img"
            tabindex="0"
            aria-label="Explicação do filtro Estabelecimento"
            v-tooltip.right="filterTooltips.establishment"
          />
          <button
            v-if="isFilterActive('selectedCnpjRaiz')"
            class="filter-clear-btn"
            @click="filterStore.selectedCnpjRaiz = ''"
            v-tooltip.right="filterTooltips.clear"
          >
            <i class="pi pi-eraser" />
          </button>
        </label>
        <div class="filter-campo-icone">
        <i class="pi pi-search filter-campo-icone-i" aria-hidden="true" />
        <AutoComplete
          v-model="filterStore.selectedCnpjRaiz"
          :suggestions="cnpjSuggestions"
          optionLabel="label"
          @complete="searchEstabelecimento"
          @option-select="onEstabelecimentoSelect"
          placeholder="CNPJ ou razão social..."
          class="w-full filter-input estabelecimento-ac"
          :class="{ 'filter-active': isFilterActive('selectedCnpjRaiz') }"
          :delay="200"
          :forceSelection="false"
          panelClass="sidebar-ac-panel"
          :pt="{ input: { maxlength: 60 } }"
        >
          <template #option="{ option }">
            <div class="ac-option">
              <span class="ac-razao">{{ option.label }}</span>
              <div class="ac-meta">
                <span class="ac-cnpj">{{ option.cnpj }}</span>
                <span v-if="option.municipio" class="ac-loc"
                  >{{ option.municipio }}/{{ option.uf }}</span
                >
              </div>
            </div>
          </template>
        </AutoComplete>
        </div>
      </div>

      <!-- FILTROS CONTEXTUAIS -->
      <div
        v-if="route.path === '/alvos/cluster' || route.path === '/alvos/rede'"
        class="dynamic-filters-box"
        :class="{ 'filter-locked': allFiltersLocked }"
      >
        <div v-if="route.path === '/alvos/cluster'" class="contextual-filters">
          <div v-show="shouldDisplayFilter('geral', 'busca')" class="filter-section mini">
            <label class="filter-label sm">
              Busca alvo
              <button
                v-if="isFilterActive('searchTarget')"
                class="filter-clear-btn"
                @click="filterStore.searchTarget = ''"
                v-tooltip.right="filterTooltips.clear"
              >
                <i class="pi pi-eraser" />
              </button>
            </label>
            <InputText
              v-model="filterStore.searchTarget"
              placeholder="ID/CNPJ..."
              class="w-full filter-input sm"
              :class="{ 'filter-active': isFilterActive('searchTarget') }"
            />
          </div>
          <div v-show="shouldDisplayFilter('geral', 'cluster')" class="filter-section mini">
            <label class="filter-label sm">
              Target cluster
              <button
                v-if="isFilterActive('clusterSelection')"
                class="filter-clear-btn"
                @click="filterStore.clusterSelection = FILTER_ALL_VALUE"
                v-tooltip.right="filterTooltips.clear"
              >
                <i class="pi pi-eraser" />
              </button>
            </label>
            <Dropdown
              v-model="filterStore.clusterSelection"
              :options="clusterOptions"
              class="w-full filter-input sm"
              panelClass="sidebar-panel"
              :class="{ 'filter-active': isFilterActive('clusterSelection') }"
            />
          </div>
          <div v-show="shouldDisplayFilter('geral', 'rfa')" class="filter-section mini">
            <label class="filter-label sm">
              Risco (RFA)
              <button
                v-if="isFilterActive('rfaSelection')"
                class="filter-clear-btn"
                @click="filterStore.rfaSelection = FILTER_ALL_VALUE"
                v-tooltip.right="filterTooltips.clear"
              >
                <i class="pi pi-eraser" />
              </button>
            </label>
            <Dropdown
              v-model="filterStore.rfaSelection"
              :options="rfaOptions"
              class="w-full filter-input sm"
              panelClass="sidebar-panel"
              :class="{ 'filter-active': isFilterActive('rfaSelection') }"
            />
          </div>
        </div>

        <div v-if="route.path === '/alvos/rede'" class="contextual-filters">
          <div v-show="shouldDisplayFilter('geral', 'busca')" class="filter-section mini">
            <label class="filter-label sm">
              CPF/CNPJ alvo
              <button
                v-if="isFilterActive('searchTarget')"
                class="filter-clear-btn"
                @click="filterStore.searchTarget = ''"
                v-tooltip.right="filterTooltips.clear"
              >
                <i class="pi pi-eraser" />
              </button>
            </label>
            <InputText
              v-model="filterStore.searchTarget"
              placeholder="Pesquisar rede..."
              class="w-full filter-input sm"
            />
          </div>
        </div>

      </div>
      </div>

      <button
        v-show="shouldShowSection('integridade')"
        class="sidebar-section-heading"
        :class="{ collapsed: isSectionCollapsed('integridade'), searching: !!searchTerm }"
        @click="toggleSection('integridade')"
        :aria-expanded="!isSectionCollapsed('integridade')"
        aria-controls="sidebar-section-integridade"
      >
        <small v-if="searchTerm">{{ sectionMatchCount('integridade') }}</small>
        <small v-else-if="integrityFilterCount">{{ integrityFilterCount }}</small>
        <span><i class="pi pi-bell"></i> Alertas</span>
        <i class="pi pi-chevron-down sidebar-section-chevron"></i>
      </button>

      <div v-show="shouldDisplayGroup('integridade', 'empresa')" class="filter-group-title"><i class="pi pi-briefcase" aria-hidden="true" />Empresa</div>
      <div
        v-show="shouldDisplayFilter('integridade', 'parTeia')"
        class="filter-section"
        :class="{ 'filter-locked': allFiltersLocked }"
      >
        <label class="filter-label">
          CNPJs com PAR
          <i
            class="pi pi-info-circle filter-info-icon help-icon"
            v-tooltip.right="filterTooltips.parTeia"
          />
          <button
            v-if="isFilterActive('selectedParTeia')"
            class="filter-clear-btn"
            @click="filterStore.selectedParTeia = FILTER_ALL_VALUE"
            v-tooltip.right="filterTooltips.clear"
          >
            <i class="pi pi-eraser" />
          </button>
        </label>
        <Dropdown
          v-model="filterStore.selectedParTeia"
          :options="parTeiaOptions"
          optionLabel="label"
          optionValue="value"
          class="w-full filter-input"
          panelClass="sidebar-panel"
          :class="{ 'filter-active': isFilterActive('selectedParTeia') }"
        />
      </div>

      <div
        v-show="shouldDisplayFilter('integridade', 'cnaeIncompativel')"
        class="filter-section"
        :class="{ 'filter-locked': allFiltersLocked }"
      >
        <!-- Sem título: o próprio texto da caixa nomeia o filtro; ajuda e borracha ficam na mesma linha. -->
        <div class="filter-checkbox-wrapper checkbox-linha" :class="{ 'filter-active-box': isFilterActive('selectedCnaeIncompativel') }">
          <label class="checkbox-label">
            <Checkbox
              v-model="filterStore.selectedCnaeIncompativel"
              class="filter-checkbox"
              binary
            />
            <span>CNPJ com CNAE incompatível</span>
          </label>
          <i
            class="pi pi-info-circle filter-info-icon help-icon"
            v-tooltip.right="filterTooltips.cnaeIncompativel"
          />
          <button
            v-if="isFilterActive('selectedCnaeIncompativel')"
            class="filter-clear-btn"
            @click="filterStore.selectedCnaeIncompativel = false"
            v-tooltip.right="filterTooltips.clear"
          >
            <i class="pi pi-eraser" />
          </button>
        </div>
      </div>

      <div v-show="shouldDisplayGroup('integridade', 'socios')" class="filter-group-title"><i class="pi pi-users" aria-hidden="true" />Sócios</div>
      <div
        v-show="shouldDisplayFilter('integridade', 'socioIdadeAtipica')"
        class="filter-section"
        :class="{ 'filter-locked': allFiltersLocked }"
      >
        <!-- Sem título: o próprio texto da caixa nomeia o filtro; ajuda e borracha ficam na mesma linha. -->
        <div class="filter-checkbox-wrapper checkbox-linha" :class="{ 'filter-active-box': isFilterActive('selectedSocioIdadeAtipica') }">
          <label class="checkbox-label">
            <Checkbox
              v-model="filterStore.selectedSocioIdadeAtipica"
              class="filter-checkbox"
              binary
            />
            <span>Sócio &lt; 21 anos ou &gt; 80 anos</span>
          </label>
          <i
            class="pi pi-info-circle filter-info-icon help-icon"
            v-tooltip.right="filterTooltips.socioIdadeAtipica"
          />
          <button
            v-if="isFilterActive('selectedSocioIdadeAtipica')"
            class="filter-clear-btn"
            @click="filterStore.selectedSocioIdadeAtipica = false"
            v-tooltip.right="filterTooltips.clear"
          >
            <i class="pi pi-eraser" />
          </button>
        </div>
      </div>

      <div
        v-show="shouldDisplayFilter('integridade', 'socioFalecido')"
        class="filter-section"
        :class="{ 'filter-locked': allFiltersLocked }"
      >
        <!-- Sem título: o próprio texto da caixa nomeia o filtro; ajuda e borracha ficam na mesma linha. -->
        <div class="filter-checkbox-wrapper checkbox-linha" :class="{ 'filter-active-box': isFilterActive('selectedSocioFalecido') }">
          <label class="checkbox-label">
            <Checkbox
              v-model="filterStore.selectedSocioFalecido"
              class="filter-checkbox"
              binary
            />
            <span>Sócio ativo falecido</span>
          </label>
          <i
            class="pi pi-info-circle filter-info-icon help-icon"
            v-tooltip.right="filterTooltips.socioFalecido"
          />
          <button
            v-if="isFilterActive('selectedSocioFalecido')"
            class="filter-clear-btn"
            @click="filterStore.selectedSocioFalecido = false"
            v-tooltip.right="filterTooltips.clear"
          >
            <i class="pi pi-eraser" />
          </button>
        </div>
      </div>

      <div
        v-show="shouldDisplayFilter('integridade', 'socioBeneficio')"
        class="filter-section"
        :class="{ 'filter-locked': allFiltersLocked }"
      >
        <label class="filter-label">
          Sócio no CadÚnico/Defeso
          <i
            class="pi pi-info-circle filter-info-icon help-icon"
            v-tooltip.right="filterTooltips.socioBeneficio"
          />
          <button
            v-if="isFilterActive('selectedSocioBeneficio')"
            class="filter-clear-btn"
            @click="filterStore.selectedSocioBeneficio = FILTER_ALL_VALUE"
            v-tooltip.right="filterTooltips.clear"
          >
            <i class="pi pi-eraser" />
          </button>
        </label>
        <Dropdown
          v-model="filterStore.selectedSocioBeneficio"
          :options="socioBeneficioOptions"
          optionLabel="label"
          optionValue="value"
          class="w-full filter-input"
          panelClass="sidebar-panel"
          :class="{ 'filter-active': isFilterActive('selectedSocioBeneficio') }"
        />
      </div>

      <div
        v-show="shouldDisplayFilter('integridade', 'socioEsocial')"
        class="filter-section"
        :class="{ 'filter-locked': allFiltersLocked }"
      >
        <label class="filter-label">
          Sócio com vínculo eSocial
          <i
            class="pi pi-info-circle filter-info-icon help-icon"
            v-tooltip.right="filterTooltips.socioEsocial"
          />
          <button
            v-if="isFilterActive('selectedSocioEsocial')"
            class="filter-clear-btn"
            @click="filterStore.selectedSocioEsocial = FILTER_ALL_VALUE"
            v-tooltip.right="filterTooltips.clear"
          >
            <i class="pi pi-eraser" />
          </button>
        </label>
        <Dropdown
          v-model="filterStore.selectedSocioEsocial"
          :options="socioEsocialOptions"
          optionLabel="label"
          optionValue="value"
          class="w-full filter-input"
          panelClass="sidebar-panel"
          :class="{ 'filter-active': isFilterActive('selectedSocioEsocial') }"
        />
      </div>

      <div v-show="shouldDisplayGroup('integridade', 'vendas')" class="filter-group-title"><i class="pi pi-shopping-cart" aria-hidden="true" />Vendas</div>
      <div
        v-show="shouldDisplayFilter('integridade', 'dispersaoUf')"
        class="filter-section"
        :class="{ 'filter-locked': allFiltersLocked }"
      >
        <label class="filter-label">
          Vendas para UFs sem fronteira
          <i
            class="pi pi-info-circle filter-info-icon help-icon"
            v-tooltip.right="filterTooltips.dispersaoUfSemFronteira"
          />
          <button
            v-if="isFilterActive('dispersaoUfSemFronteiraEnabled')"
            class="filter-clear-btn"
            @click="clearDispersaoUfSemFronteira"
            v-tooltip.right="filterTooltips.clear"
          >
            <i class="pi pi-eraser" />
          </button>
        </label>
        <div
          class="slider-container"
          :class="{ 'filter-active-box': isFilterActive('dispersaoUfSemFronteiraEnabled') }"
        >
          <NumberRangePicker
            :limpavel="false"
            :mostrar-icone="false"
            unico
            :valor="dispersaoUfValor"
            :sugestao="filterStore.dispersaoUfSemFronteiraEnabled ? null : [FILTER_DEFAULTS.DISPERSAO_UF_SEM_FRONTEIRA_PERCENTUAL]"
            :min="FILTER_DEFAULTS.DISPERSAO_UF_SEM_FRONTEIRA_MIN"
            :max="FILTER_DEFAULTS.DISPERSAO_UF_SEM_FRONTEIRA_MAX"
            sufixo="%"
            rotulo-personalizado="Mínimo personalizado"
            :atalhos="dispersaoUfAtalhos"
            :rotulo="dispersaoUfRotulo"
            :disabled="allFiltersLocked"
            @select-range="aplicarDispersaoUf"
          />
        </div>
      </div>

      <div
        v-show="shouldDisplayFilter('integridade', 'volumeAtipico')"
        class="filter-section"
        :class="{ 'filter-locked': volumeAtipicoFilterLocked }"
      >
        <label class="filter-label">
          Aumento semestral atípico
          <i
            class="pi pi-info-circle filter-info-icon help-icon"
            v-tooltip.right="filterTooltips.volumeAtipico"
          />
          <button
            v-if="isFilterActive('volumeAtipicoEnabled')"
            class="filter-clear-btn"
            @click="clearVolumeAtipico"
            v-tooltip.right="filterTooltips.clear"
          >
            <i class="pi pi-eraser" />
          </button>
        </label>
        <div
          class="slider-container"
          :class="{ 'filter-active-box': isFilterActive('volumeAtipicoEnabled') }"
        >
          <NumberRangePicker
            :limpavel="false"
            :mostrar-icone="false"
            unico
            :valor="volumeAtipicoValor"
            :sugestao="filterStore.volumeAtipicoEnabled ? null : [FILTER_DEFAULTS.VOLUME_ATIPICO_PERCENTUAL]"
            :min="FILTER_DEFAULTS.VOLUME_ATIPICO_MIN"
            :max="FILTER_DEFAULTS.VOLUME_ATIPICO_MAX"
            :passo="10"
            :formatar="formatarPercentual"
            sufixo="%"
            rotulo-personalizado="Mínimo personalizado"
            :atalhos="volumeAtipicoAtalhos"
            :rotulo="volumeAtipicoRotulo"
            :disabled="volumeAtipicoFilterLocked"
            @select-range="aplicarVolumeAtipico"
          />
        </div>
      </div>

      <div
        v-show="shouldDisplayFilter('integridade', 'seq')"
        class="filter-section"
        :class="{ 'filter-locked': allFiltersLocked }"
      >
        <label class="filter-label">
          Autorizações em sequência
          <i
            class="pi pi-info-circle filter-info-icon help-icon"
            role="img"
            tabindex="0"
            aria-label="Explicação do filtro Autorizações em sequência"
            v-tooltip.right="filterTooltips.seq"
          />
          <button
            v-if="seqAtivo"
            class="filter-clear-btn"
            @click="limparSeq"
            v-tooltip.right="filterTooltips.clear"
          >
            <i class="pi pi-eraser" />
          </button>
        </label>
        <div class="slider-container seq-filtro" :class="{ 'filter-active-box': seqAtivo }">
          <span class="seq-filtro-rotulo">Tipo</span>
          <OptionPicker
            :valor="filterStore.seqTipo"
            :opcoes="SEQ_TIPOS"
            rotulo-acessivel="Tipo das autorizações em sequência"
            :disabled="allFiltersLocked"
            @select="filterStore.seqTipo = $event"
          />
          <span class="seq-filtro-rotulo">Severidade mínima</span>
          <OptionPicker
            :valor="filterStore.seqSeveridade"
            :opcoes="SEQ_SEVERIDADES"
            rotulo-acessivel="Severidade mínima das autorizações em sequência"
            :disabled="allFiltersLocked"
            @select="filterStore.seqSeveridade = $event"
          />
          <span class="seq-filtro-rotulo">Dias com sequência</span>
          <NumberRangePicker
            :mostrar-icone="false"
            aberto
            :valor="filterStore.seqDias"
            :min="0"
            :max="Infinity"
            :passo="1"
            :formatar="(v) => Number(v).toLocaleString('pt-BR')"
            :atalhos="SEQ_DIAS_ATALHOS"
            :rotulo="seqDiasRotulo"
            :disabled="allFiltersLocked"
            @select-range="filterStore.seqDias = $event"
          />
        </div>
      </div>

      <div class="sidebar-spacer"></div>
    </div>

    <div class="sidebar-footer">
      <Button
        :label="
          activeFilterCount > 0
            ? `Limpar Filtros (${activeFilterCount})`
            : 'Limpar Filtros'
        "
        icon="pi pi-undo"
        outlined
        :severity="activeFilterCount > 0 ? 'warn' : 'secondary'"
        @click="limparFiltros"
        class="w-full clear-filters-btn"
        :class="{ 'filters-active': activeFilterCount > 0 }"
        :disabled="allFiltersLocked"
      />
    </div>
  </aside>
</template>

<style scoped>
/* Autorizações em sequência: tipo, severidade e dias, empilhados. */
/* Um filtro só com três campos: recuados sob o título e ligados por uma linha-guia
   à esquerda (laranja quando o filtro tem valor), para não parecerem três filtros. */
.slider-container.seq-filtro { display: flex; flex-direction: column; gap: 0.35rem; margin-left: 0.15rem; padding: 0.1rem 0 0.1rem 0.65rem; border-left: 2px solid var(--sidebar-border); transition: border-color 0.15s ease; }
.slider-container.seq-filtro.filter-active-box { border-left-color: var(--primary-color); }
.seq-filtro :deep(.rp-gatilho) { width: 100%; }
.seq-filtro-rotulo { color: var(--text-muted); font-size: 0.75rem; font-weight: 500; }
.seq-filtro-rotulo + .rp-gatilho, .seq-filtro-rotulo:not(:first-child) { margin-top: 0.15rem; }

/* SIDEBAR */
/* Campos da barra com o mesmo fundo dela (só a borda os desenha). Redefinido só
   aqui: o token global continua valendo para os campos do restante da página. */
.admin-sidebar {
  --sidebar-input-bg: var(--sidebar-bg);
  position: fixed;
  top: 56px;
  left: 0;
  z-index: 200;
  width: var(--sidebar-width);
  background: var(--sidebar-bg) !important;
  color: var(--sidebar-text);
  transition: width var(--sidebar-motion-duration) cubic-bezier(0.4, 0, 0.2, 1);
  will-change: width;
  display: flex;
  flex-direction: column;
  height: calc(100vh - 56px);
  border-right: 1px solid var(--sidebar-border);
  overflow: hidden;
}

@media (prefers-reduced-motion: reduce) {
  .admin-sidebar { transition-duration: 0ms; }
}

/* A barra é escura nos dois temas. No tema claro, os tokens de texto da página são
   feitos para fundo claro e ficariam ilegíveis aqui (títulos azul-escuros, valores
   quase invisíveis): dentro da barra eles passam a valer para fundo escuro. Os
   painéis dos seletores abrem fora da barra e seguem com os tokens da página. */
:global(:root:not(.dark-mode) .admin-sidebar) {
  --text-color: var(--sidebar-text-strong);
  --text-color-85: color-mix(in srgb, var(--sidebar-text-strong) 85%, transparent);
  --text-secondary: color-mix(in srgb, var(--sidebar-text-strong) 70%, transparent);
  --text-muted: var(--sidebar-text);
}

/* BOTÃO FLUTUANTE DE LIMPAR TODOS OS FILTROS */
.sidebar-clear-btn {
  position: fixed;
  top: calc(50% - 90px);
  left: var(--sidebar-width);
  transform: translateY(-50%);
  z-index: 240;
  will-change: left;
  width: 20px;
  height: 36px;
  background: color-mix(in srgb, var(--risk-high) 12%, var(--sidebar-bg));
  border: 1px solid color-mix(in srgb, var(--risk-high) 55%, transparent);
  border-left: none;
  border-radius: 0 8px 8px 0;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--risk-high);
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  box-shadow: 4px 0 10px rgba(0, 0, 0, 0.1);
}

.sidebar-clear-btn:hover {
  width: 28px;
  background: color-mix(in srgb, var(--risk-high) 22%, var(--sidebar-bg));
  box-shadow: 6px 0 15px rgba(0, 0, 0, 0.15);
}

.sidebar-clear-btn i {
  font-size: 0.8rem;
}

/* BOTÃO FLUTUANTE DE CONTADOR DE FILTROS ATIVOS */
.sidebar-filter-count-btn {
  position: fixed;
  top: calc(50% - 48px);
  left: var(--sidebar-width);
  transform: translateY(-50%);
  z-index: 250;
  will-change: left;
  width: 20px;
  height: 36px;
  background: color-mix(in srgb, var(--primary-color) 12%, var(--sidebar-bg));
  border: 1px solid var(--primary-color);
  border-left: none;
  border-radius: 0 8px 8px 0;
  cursor: pointer;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 0.15rem;
  color: var(--primary-color);
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  box-shadow: 4px 0 10px rgba(0, 0, 0, 0.1);
}

.sidebar-filter-count-btn:hover {
  width: 28px;
  box-shadow: 6px 0 15px rgba(0, 0, 0, 0.15);
}

.sidebar-filter-count-btn i {
  font-size: 0.65rem;
}

.filter-count-badge {
  font-size: 0.62rem;
  font-weight: 600;
  line-height: 1;
}

/* BOTÃO FLUTUANTE DE REABERTURA */
.sidebar-float-btn {
  position: fixed;
  top: 50%;
  left: var(--sidebar-width);
  transform: translateY(-50%);
  z-index: 250;
  will-change: left;
  width: 20px;
  height: 48px;
  background: color-mix(in srgb, var(--sidebar-bg) 80%, white);
  border: 1px solid var(--sidebar-border);
  border-left: none;
  border-radius: 0 8px 8px 0;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--text-muted);
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  box-shadow: 4px 0 10px rgba(0, 0, 0, 0.1);
}

.sidebar-float-btn:hover {
  width: 28px;
  box-shadow: 6px 0 15px rgba(0, 0, 0, 0.15);
}

.sidebar-float-btn i {
  font-size: 0.8rem;
}

/* BOTÃO DE CADEADO */
.sidebar-lock-btn {
  position: fixed;
  top: calc(50% + 48px);
  left: var(--sidebar-width);
  transform: translateY(-50%);
  z-index: 300;
  will-change: left;
  width: 20px;
  height: 36px;
  background: color-mix(in srgb, var(--sidebar-bg) 80%, white);
  border: 1px solid var(--sidebar-border);
  border-left: none;
  border-radius: 0 8px 8px 0;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--primary-color);
  cursor: pointer;
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  box-shadow: 4px 0 10px rgba(0, 0, 0, 0.1);
}

.sidebar-lock-btn:hover {
  width: 28px;
  box-shadow: 6px 0 15px rgba(0, 0, 0, 0.15);
}

.sidebar-lock-btn.locked {
  opacity: 1;
  color: var(--primary-color);
  background: color-mix(in srgb, var(--primary-color) 12%, var(--sidebar-bg));
}

.sidebar-lock-btn i {
  font-size: 0.8rem;
}

.sidebar-title-simple {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0.5rem;
  font-size: 0.6875rem;
  font-weight: 600;
  color: var(--text-color-85);
  opacity: 0.85;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  padding: 0.2rem 0.5rem 0.3rem;
  margin-bottom: 0rem;
  border-bottom: 1px solid var(--sidebar-border);
}

.sidebar-title-simple i {
  font-size: 0.8rem;
}


.sidebar-content {
  flex: 1;
  padding: 0.75rem 0.5rem;
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
  overflow-y: auto;
  overflow-x: hidden;
  scrollbar-color: color-mix(in srgb, var(--sidebar-bg) 70%, var(--sidebar-text)) var(--sidebar-bg) !important;
  scrollbar-width: thin !important;
  --scrollbar-track: var(--sidebar-bg);
  --scrollbar-thumb: rgba(255, 255, 255, 0.15);
  --scrollbar-thumb-hover: rgba(255, 255, 255, 0.3);
}

.sidebar-content::-webkit-scrollbar {
  width: 4px;
}
.sidebar-content:hover {
  scrollbar-color: color-mix(in srgb, var(--sidebar-bg) 58%, var(--sidebar-text)) var(--sidebar-bg) !important;
}
.sidebar-content::-webkit-scrollbar-track {
  background: var(--sidebar-bg);
}
.sidebar-content::-webkit-scrollbar-thumb {
  background: color-mix(in srgb, var(--sidebar-bg) 70%, var(--sidebar-text)) !important;
  border-radius: 4px;
}
.sidebar-content::-webkit-scrollbar-thumb:hover {
  background: color-mix(in srgb, var(--sidebar-bg) 58%, var(--sidebar-text)) !important;
}


.sidebar-footer {
  padding: 1rem;
}
.sidebar-spacer {
  flex: 1;
}

.sidebar-section-heading {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: flex-start;
  gap: 0.4rem;
  min-height: 2rem;
  width: 100%;
  padding: 0.35rem 0.45rem 0.2rem 0.45rem;
  background: var(--sidebar-heading-tint);
  border: 0;
  color: var(--text-secondary);
  font-size: 0.6875rem;
  font-weight: 600;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  text-align: left;
  cursor: pointer;
  border-radius: 6px;
  transition: background 0.18s ease, color 0.18s ease;
}

.sidebar-section-heading:hover {
  background: var(--sidebar-heading-hover);
  color: var(--sidebar-text);
}

.sidebar-section-heading:focus-visible {
  outline: 2px solid var(--primary-color);
  outline-offset: 1px;
}

.sidebar-section-heading:first-of-type {
  border-top: 0;
}

.sidebar-section-heading span {
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
  min-width: 0;
}

.sidebar-section-heading span > i {
  color: var(--sidebar-heading-icon);
  font-size: 0.72rem;
  opacity: 0.85;
}

.sidebar-section-heading small {
  position: absolute;
  right: 1.8rem;
  top: 50%;
  transform: translateY(-50%);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 1.15rem;
  height: 1.15rem;
  padding: 0 0.32rem;
  border-radius: 999px;
  background: color-mix(in srgb, var(--sidebar-heading-icon) 18%, var(--sidebar-bg));
  color: var(--sidebar-heading-icon);
  font-size: 0.62rem;
  font-weight: 600;
  letter-spacing: 0;
}

.sidebar-section-heading.searching {
  color: var(--sidebar-text);
}

.sidebar-section-heading.searching small {
  background: color-mix(in srgb, var(--sidebar-heading-icon) 28%, var(--sidebar-bg));
}

.sidebar-section-chevron {
  margin-left: auto;
  transition: transform 0.22s cubic-bezier(0.4, 0, 0.2, 1), opacity 0.18s ease;
  opacity: 0.55;
}

.sidebar-section-heading:hover .sidebar-section-chevron {
  opacity: 1;
}

.sidebar-section-heading.collapsed .sidebar-section-chevron {
  transform: rotate(-90deg);
}

/* === BUSCA DE FILTROS === */
/* Wrapper que envolve todos os filter-sections de uma seção colapsável.
   Usa flex column com gap para garantir espaçamento consistente entre
   os cards de filtro, mesmo quando dentro do wrapper. */
.sidebar-section-body {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.sidebar-search {
  position: relative;
  display: flex;
  align-items: center;
  flex: 0 0 32px;
  height: 32px;
  min-height: 32px;
  margin: 0.5rem 0.5rem 0.4rem;
  padding: 0 1rem 0 2.4rem;
  background: var(--sidebar-input-bg);
  border: 1px solid color-mix(in srgb, var(--sidebar-border) 80%, transparent);
  border-radius: 8px;
  box-sizing: border-box;
  transition: border-color 0.2s cubic-bezier(0.4, 0, 0.2, 1),
    box-shadow 0.2s cubic-bezier(0.4, 0, 0.2, 1);
}

.sidebar-search:hover {
  border-color: color-mix(in srgb, var(--sidebar-text) 30%, var(--sidebar-border));
}

.sidebar-search:focus-within {
  border-color: color-mix(in srgb, var(--sidebar-text) 45%, var(--sidebar-border));
  background: var(--sidebar-input-bg);
  box-shadow: 0 0 0 1px color-mix(in srgb, var(--sidebar-text) 12%, transparent),
    0 4px 12px rgba(0, 0, 0, 0.05);
}

.sidebar-search.has-value {
  border-color: color-mix(in srgb, var(--primary-color) 55%, transparent);
}

.sidebar-search-icon {
  position: absolute;
  left: 0.85rem;
  top: 50%;
  transform: translateY(-50%);
  font-size: 0.95rem;
  color: var(--text-muted);
  opacity: 0.7;
  pointer-events: none;
}

.sidebar-search-input {
  flex: 1;
  height: 100%;
  background: transparent;
  border: 0;
  outline: none;
  color: var(--sidebar-text);
  font-size: 0.8125rem;
  font-family: inherit;
  min-width: 0;
}

.sidebar-search-input::placeholder {
  color: color-mix(in srgb, var(--text-muted) 80%, transparent);
}

.sidebar-search-clear {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 18px;
  height: 18px;
  margin-left: 0.35rem;
  padding: 0;
  background: color-mix(in srgb, var(--primary-color) 14%, transparent);
  border: 0;
  border-radius: 999px;
  color: var(--primary-color);
  cursor: pointer;
  transition: background 0.18s ease, transform 0.18s ease;
}

.sidebar-search-clear:hover {
  background: color-mix(in srgb, var(--primary-color) 28%, transparent);
  transform: scale(1.08);
}

.sidebar-search-clear i {
  font-size: 0.62rem;
  line-height: 1;
}

/* Recuo vertical curto: com o gap de 0,75rem do contêiner, os filtros ficam a 20px um do outro. */
.filter-section {
  padding: 0.25rem 0.48rem;
  border-left: 2px solid transparent;
}

/* Subtítulo de grupo dentro da seção: texto discreto e linha fina, sem caixa. */
.filter-group-title {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin-top: 0.5rem;
  padding: 0 0.48rem 0 calc(0.48rem + 2px);
  /* Mesma cor do título "Filtros dos médicos" da barra da direita (AnalysisSidebar .group-title). */
  color: color-mix(in srgb, var(--primary-color) 15%, #78716c);
  font-size: 0.875rem;
  font-weight: 600;
  line-height: 1.2;
  white-space: nowrap;
}
/* Ícone do grupo: mesma cor do subtítulo (os campos dos filtros não têm ícone). */
.filter-group-title .pi {
  font-size: 0.78rem;
}
.filter-group-title::after {
  content: "";
  flex: 1;
  height: 1px;
  background: var(--sidebar-border);
}
.sidebar-section-body > .filter-group-title:first-child,
.sidebar-section-heading + .filter-group-title {
  margin-top: 0;
}

/* Filtro com valor: título e borda do campo na cor primária (mesmo padrão da
   barra de filtros dos médicos em /analises); sem fundo colorido no bloco. */
.filter-section:has(.filter-active) > .filter-label,
.filter-section:has(.filter-active-box) > .filter-label {
  color: var(--primary-color);
}

.filter-locked {
  pointer-events: none;
  opacity: 0.38;
  user-select: none;
}

.filter-locked-alt {
  opacity: 0.38;
  user-select: none;
}

.filters-locked-banner {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.6rem 0.8rem;
  margin-bottom: 0.75rem;
  /* Usa o fundo da sidebar para evitar o flash branco em modo light */
  background: color-mix(in srgb, var(--primary-color) 12%, var(--sidebar-bg));
  border: 1px solid color-mix(in srgb, var(--primary-color) 30%, transparent);
  border-radius: 8px;
  font-size: 0.7rem;
  font-weight: 600;
  color: var(--primary-color);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.15);
}

.filters-locked-banner .pi {
  font-size: 0.7rem;
}

/* Título do filtro: 13px, peso 500, caixa normal (grupo: 14px/600; valor do campo: 13px/400). O espaço até o campo é sempre
   0,4rem: os contêineres do campo (.slider-container, .filter-checkbox-wrapper)
   não somam recuo vertical próprio. */
.filter-label {
  display: flex;
  align-items: center;
  gap: 0.25rem;
  font-size: 0.8125rem;
  font-weight: 500;
  line-height: 1.2;
  margin-bottom: 0.4rem;
  /* Texto principal do tema a 70%: abaixo do valor do campo (85%) e sem o tom
     azulado de --text-secondary; o mesmo da barra de filtros dos médicos. */
  color: color-mix(in srgb, var(--text-color) 70%, transparent);
}

.filter-clear-btn {
  margin-left: auto;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 14px;
  height: 14px;
  border: none;
  background: none;
  cursor: pointer;
  padding: 0;
  color: var(--color-error);
  opacity: 0.7;
  transition: opacity 0.15s;
  flex-shrink: 0;
}

.filter-clear-btn:hover {
  opacity: 1;
}
.filter-clear-btn .pi {
  font-size: 0.75rem;
}

.filter-info-icon {
  font-size: 0.8rem;
  color: var(--text-muted);
  opacity: 0.75;
  cursor: help;
}

.filter-info-icon:hover {
  opacity: 1;
}

.grid-filters {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 0.5rem;
}

.grid-filters .filter-section {
  min-width: 0;
}

.grid-filters :deep(.p-dropdown-label) {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* COMPONENTES COMPACTOS DO PRIMEVUE */
:deep(.filter-input .p-inputtext),
:deep(.filter-input .p-dropdown-label),
:deep(.filter-input.p-inputtext) {
  padding: 0.4rem 0.6rem;
  font-size: 0.8125rem;
  font-weight: 400;
  text-transform: none;
}

:deep(.p-dropdown),
:deep(.p-calendar),
:deep(.filter-input.p-inputtext) {
  height: 32px;
  align-items: center;
  box-sizing: border-box;
}

:deep(.filter-input.p-dropdown),
:deep(.filter-input.p-inputtext) {
  background: var(--sidebar-input-bg) !important;
  border-color: var(--sidebar-border) !important;
  color: var(--sidebar-text) !important;
}

/* Hover neutro: só a borda muda (clareada com o cinza do texto); o fundo continua
   o do campo, vencendo o fundo translúcido do hover global do AppLayout. Exclui
   foco e filtro com valor para não sobrepor esses estados. */
:deep(.filter-input.p-dropdown:not(.p-disabled):not(.p-focus):not(.filter-active):hover),
:deep(.filter-input.p-inputtext:not(.p-dropdown-label):not(:focus):not(.filter-active):hover) {
  border-color: color-mix(in srgb, var(--sidebar-text) 28%, var(--sidebar-border)) !important;
  background: var(--sidebar-input-bg) !important;
}

:deep(.filter-input .p-dropdown-label),
:deep(.filter-input .p-dropdown-trigger) {
  background: transparent !important;
  color: inherit !important;
}

/* Seta do dropdown igual à dos seletores (.rp-gatilho-seta): mesmo tamanho,
   mesma distância da borda e mesma opacidade. */
:deep(.filter-input .p-dropdown-trigger) {
  width: 1.85rem;
}
:deep(.filter-input .p-dropdown-trigger-icon) {
  width: 0.65rem;
  height: 0.65rem;
  color: var(--text-muted);
}

/* Estados dos campos da barra (dropdown, texto e autocomplete):
   - padrão: borda da barra, fundo do campo;
   - hover: só a borda clareia (regra "Hover neutro" acima);
   - foco sem valor: borda um degrau mais clara e anel discreto, fundo igual;
   - com valor: borda e fundo suave na cor primária, também com o mouse em cima
     e com o campo em foco (logo depois de escolher um item, o dropdown continua
     em foco e o destaque já tem de aparecer).
   .p-component/:not/:enabled elevam a especificidade sobre as regras globais
   de hover e foco do AppLayout. */
:global(.admin-sidebar .p-dropdown.p-component:not(.p-disabled):not(.filter-active).p-focus),
:global(.admin-sidebar .filter-input.p-inputtext:not(.p-dropdown-label):not(.filter-active):enabled:focus) {
  border: 1px solid color-mix(in srgb, var(--sidebar-text) 45%, var(--sidebar-border)) !important;
  background: var(--sidebar-input-bg) !important;
  box-shadow: 0 0 0 1px color-mix(in srgb, var(--sidebar-text) 10%, transparent) !important;
  outline: none !important;
}
:global(.admin-sidebar .filter-active.p-dropdown),
:global(.admin-sidebar .filter-active.p-inputtext:not(.p-dropdown-label)),
:global(.admin-sidebar .filter-active.p-dropdown.p-component:not(.p-disabled):hover),
:global(.admin-sidebar .filter-active.p-inputtext:not(.p-dropdown-label):enabled:hover) {
  border: 1px solid var(--primary-color) !important;
  background: color-mix(in srgb, var(--primary-color) 10%, var(--sidebar-input-bg)) !important;
  box-shadow: none !important;
  outline: none !important;
}
:global(.admin-sidebar .filter-active.p-dropdown.p-component:not(.p-disabled).p-focus),
:global(.admin-sidebar .filter-active.p-inputtext:not(.p-dropdown-label):enabled:focus) {
  border: 1px solid var(--primary-color) !important;
  background: color-mix(in srgb, var(--primary-color) 10%, var(--sidebar-input-bg)) !important;
  box-shadow: 0 0 0 1px color-mix(in srgb, var(--primary-color) 25%, transparent) !important;
  outline: none !important;
}

:global(.admin-sidebar) .p-inputtext,
:global(.admin-sidebar) .p-dropdown {
  background: var(--sidebar-input-bg) !important;
  border-color: var(--sidebar-border) !important;
  color: var(--sidebar-text) !important;
}

:global(.admin-sidebar) .p-dropdown-label,
:global(.admin-sidebar) .p-dropdown-trigger {
  background: transparent !important;
}

/* PAINEL DOS DROPDOWNS */
:global(.p-dropdown-panel.sidebar-panel) {
  background: var(--sidebar-bg) !important;
  border: 1px solid var(--sidebar-border) !important;
  box-shadow: 0 10px 25px rgba(0, 0, 0, 0.4) !important;
}

/* .p-dropdown-panel no seletor e !important: vence o 0,75rem global do AppLayout. */
:global(.p-dropdown-panel.sidebar-panel .p-dropdown-items .p-dropdown-item) {
  color: var(--text-color-85) !important;
  font-size: 0.8125rem !important;
}

:global(
  .sidebar-panel
    .p-dropdown-items
    .p-dropdown-item:not(.p-highlight):not(.p-disabled):hover,
  .sidebar-panel
    .p-dropdown-items
    .p-dropdown-item:not(.p-highlight):not(.p-disabled):focus,
  .sidebar-panel
    .p-dropdown-items
    .p-dropdown-item:not(.p-highlight):not(.p-disabled).p-focus
) {
  background: var(--sidebar-input-bg) !important;
  color: var(--text-color) !important;
}

:global(.p-dropdown-panel.sidebar-panel .p-dropdown-items li.p-dropdown-item.p-highlight),
:global(
  .p-dropdown-panel.sidebar-panel .p-dropdown-items li.p-dropdown-item.p-highlight.p-focus
),
:global(
  .p-dropdown-panel.sidebar-panel .p-dropdown-items li.p-dropdown-item.p-highlight:hover
) {
  background: color-mix(
    in srgb,
    color-mix(in srgb, var(--primary-color) 15%, #a8a29e) 28%,
    transparent
  ) !important;
  color: var(--text-color) !important;
}

:global(.sidebar-panel .p-dropdown-header) {
  background: var(--sidebar-bg) !important;
  border-bottom: 1px solid var(--sidebar-border) !important;
}

:global(.sidebar-panel .p-dropdown-filter-container .p-inputtext) {
  background: var(--sidebar-input-bg) !important;
  color: var(--sidebar-text) !important;
  border-color: var(--sidebar-border) !important;
}

/* Input de pesquisa dentro do painel do dropdown: foco/hover em stone
   (Tailwind), com especificidade elevada para vencer as globais do AppLayout. */
/* Input de pesquisa dentro do painel do dropdown: mesmo tom da sidebar de
   indicadores (stone + 15% de primary, usado nos títulos de grupo). */
:global(
  .p-dropdown-panel.sidebar-panel
  .p-dropdown-filter-container
  .p-inputtext:enabled:focus
) {
  border-color: color-mix(in srgb, var(--primary-color) 15%, #78716c) !important;
  box-shadow: 0 0 0 1px
    color-mix(in srgb, color-mix(in srgb, var(--primary-color) 15%, #78716c) 25%, transparent) !important;
  outline: none !important;
}

:global(
  .p-dropdown-panel.sidebar-panel
  .p-dropdown-filter-container
  .p-inputtext:enabled:hover:not(:focus)
) {
  border-color: color-mix(in srgb, var(--primary-color) 10%, color-mix(in srgb, #78716c 60%, var(--sidebar-border))) !important;
}

/* SLIDERS */
.slider-container {
  padding: 0;
}


/* Seletores da sidebar (período, faixas, opções): mesmo padrão dos campos. */
.slider-container :deep(.rp-gatilho) {
  width: 100%;
  height: 32px;
  min-height: 32px;
  padding: 0 0.6rem;
  background: var(--sidebar-input-bg);
  border-color: var(--sidebar-border);
  color: var(--text-color-85);
  font-size: 0.8125rem;
  font-weight: 400;
}
.slider-container :deep(.rp-gatilho:not(:disabled):hover) {
  border-color: color-mix(in srgb, var(--sidebar-text) 28%, var(--sidebar-border));
}
.slider-container :deep(.rp-gatilho-seta) {
  color: var(--text-muted);
}
/* Ícone dentro do campo, na cor primária: nos seletores (.rp-gatilho-icone) e, nos
   selects e no campo Estabelecimento, sobreposto à esquerda (.filter-campo-icone). */
.slider-container :deep(.rp-gatilho-icone) {
  color: var(--primary-color);
}
.filter-campo-icone {
  position: relative;
}
.filter-campo-icone-i {
  position: absolute;
  top: 50%;
  left: 0.6rem;
  z-index: 1;
  transform: translateY(-50%);
  color: var(--primary-color);
  font-size: 0.8rem;
  pointer-events: none;
}
.filter-campo-icone :deep(.estabelecimento-ac .p-autocomplete-input),
.filter-campo-icone :deep(.filter-input .p-dropdown-label) {
  padding-left: 1.9rem;
}

.filter-input {
  margin-bottom: 0 !important;
}

/* FILTROS ATIVOS */
/* Seletores (faixa, período, opções) de um filtro com valor. */
.filter-active-box :deep(.rp-gatilho),
.filter-active-box :deep(.rp-gatilho:not(:disabled):hover) {
  border-color: var(--primary-color);
  background: color-mix(in srgb, var(--primary-color) 10%, var(--sidebar-input-bg));
}

/* Valor dentro dos campos: texto principal a 85%, 13px, peso 400 (o mesmo nas
   duas barras de filtros). O texto de exemplo (placeholder) continua apagado. */
:global(.admin-sidebar .filter-input.p-dropdown),
:global(.admin-sidebar .filter-input.p-inputtext:not(.p-dropdown-label)),
:global(.admin-sidebar .estabelecimento-ac .p-autocomplete-input) {
  color: var(--text-color-85) !important;
}
:global(.admin-sidebar .filter-input .p-dropdown-label.p-placeholder) {
  color: var(--text-muted) !important;
}
/* Filtro sem valor ("Todos", "Desligado", período inteiro...): o texto do campo fica
   apagado; só os filtros com valor ficam com o texto claro (e a borda laranja). */
:global(.admin-sidebar .filter-input.p-dropdown:not(.filter-active)) {
  color: var(--text-muted) !important;
}
.slider-container:not(.filter-active-box) :deep(.rp-gatilho) {
  color: var(--text-muted);
}

/* BOTÃO LIMPAR FILTROS */
:deep(.clear-filters-btn.p-button) {
  background: transparent !important;
  transition: all 0.2s ease !important;
  height: 2.125rem;
  padding: 0 0.75rem;
  justify-content: center;
  gap: 0.45rem;
}
/* Tamanho alinhado aos campos de filtro (34px de altura, texto de 12,5px);
   ícone e texto juntos no centro. */
:deep(.clear-filters-btn.p-button .p-button-label) { flex: 0 0 auto; font-size: 0.78rem; font-weight: 600; }
:deep(.clear-filters-btn.p-button .p-button-icon) { margin: 0; font-size: 0.78rem; }

:deep(.clear-filters-btn.p-button:hover) {
  background: transparent !important;
  border-color: color-mix(
    in srgb,
    var(--primary-color) 50%,
    transparent
  ) !important;
  color: var(--primary-color) !important;
}

:deep(.clear-filters-btn.p-button:focus),
:deep(.clear-filters-btn.p-button:active) {
  outline: none !important;
  box-shadow: none !important;
}

:deep(.clear-filters-btn.p-button:focus-visible) {
  box-shadow: 0 0 0 2px var(--primary-color) !important;
}

:deep(.filters-active.p-button) {
  background: color-mix(
    in srgb,
    var(--primary-color) 12%,
    transparent
  ) !important;
  border-color: var(--primary-color) !important;
  color: var(--primary-color) !important;
  position: relative;
  overflow: hidden; /* Necessário para o efeito de brilho (shimmer) */
}

/* Efeito Shimmer (Brilho que atravessa o botão) */
:deep(.filters-active.p-button::after) {
  content: "";
  position: absolute;
  top: 0;
  left: -100%;
  width: 100%;
  height: 100%;
  background: linear-gradient(
    90deg,
    transparent,
    rgba(255, 255, 255, 0.1),
    rgba(255, 255, 255, 0.2),
    rgba(255, 255, 255, 0.1),
    transparent
  );
  animation: shimmer-sweep 3s infinite ease-in-out;
}

/* Animação do Ícone (Micro-interação) */
:deep(.filters-active.p-button .p-button-icon) {
  animation: icon-spin-subtle 3s infinite ease-in-out;
}

@keyframes shimmer-sweep {
  0% {
    left: -100%;
  }
  20% {
    left: 100%;
  } /* Passa rápido no início do ciclo */
  100% {
    left: 100%;
  } /* Fica invisível no resto do tempo */
}

@keyframes icon-spin-subtle {
  0%,
  75% {
    transform: rotate(0deg);
  }
  90% {
    transform: rotate(-360deg);
  }
  100% {
    transform: rotate(-360deg);
  }
}

@keyframes pulse-filter {
  0%,
  100% {
    box-shadow: 0 0 0 0
      color-mix(in srgb, var(--primary-color) 25%, transparent);
  }
  50% {
    box-shadow: 0 0 0 6px
      color-mix(in srgb, var(--primary-color) 0%, transparent);
  }
}

/* FILTROS CONTEXTUAIS */
.dynamic-filters-box {
  margin-top: 0;
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
}

.filter-section.mini {
  margin-bottom: 0.45rem;
  padding: 0;
}

.filter-label.sm {
  font-size: 0.7rem;
  opacity: 0.8;
}

:deep(.filter-input.sm .p-inputtext),
:deep(.filter-input.sm .p-dropdown-label) {
  padding: 0.5rem;
  font-size: 0.8125rem;
}

/* AUTOCOMPLETE DE ESTABELECIMENTO */
:deep(.estabelecimento-ac) {
  width: 100%;
  height: 32px;
  box-sizing: border-box;
}

:deep(.estabelecimento-ac .p-autocomplete-input) {
  width: 100%;
  height: 32px;
  box-sizing: border-box;
  padding: 0.4rem 0.6rem;
  font-size: 0.8125rem;
  font-weight: 400;
  background: var(--sidebar-input-bg) !important;
  border-color: var(--sidebar-border) !important;
  color: var(--sidebar-text) !important;
}

/* Foco do autocomplete de estabelecimento: mesmo tom stone+primary da sidebar
   de indicadores. .estabelecimento-ac e .p-autocomplete sao o MESMO elemento
   (cadeia encadeada); :enabled/:focus elevam especificidade sobre o AppLayout. */
:global(
  .admin-sidebar .estabelecimento-ac.p-autocomplete.p-component .p-autocomplete-input:enabled:focus
) {
  border: 1px solid color-mix(in srgb, var(--sidebar-text) 45%, var(--sidebar-border)) !important;
  background: var(--sidebar-input-bg) !important;
  box-shadow: 0 0 0 1px color-mix(in srgb, var(--sidebar-text) 10%, transparent) !important;
  outline: none !important;
}

:global(
  .admin-sidebar .estabelecimento-ac.p-autocomplete.p-component .p-autocomplete-input:enabled:hover:not(:focus)
) {
  border: 1px solid color-mix(in srgb, var(--sidebar-text) 28%, var(--sidebar-border)) !important;
}

:global(
  .admin-sidebar .filter-active.estabelecimento-ac.p-autocomplete.p-component .p-autocomplete-input,
  .admin-sidebar .filter-active.estabelecimento-ac.p-autocomplete.p-component .p-autocomplete-input:enabled:hover,
  .admin-sidebar .filter-active.estabelecimento-ac.p-autocomplete.p-component .p-autocomplete-input:enabled:focus
) {
  border: 1px solid var(--primary-color) !important;
  background: color-mix(in srgb, var(--primary-color) 10%, var(--sidebar-input-bg)) !important;
}

:global(.sidebar-ac-panel) {
  background: var(--sidebar-bg) !important;
  border: 1px solid var(--sidebar-border) !important;
  box-shadow: 0 10px 25px rgba(0, 0, 0, 0.4) !important;
  border-radius: 8px !important;
  max-height: 280px !important;
}

:global(.sidebar-ac-panel .p-autocomplete-item) {
  padding: 0 !important;
  background: transparent !important;
}

:global(.sidebar-ac-panel .p-autocomplete-item:hover),
:global(.sidebar-ac-panel .p-autocomplete-item.p-highlight) {
  background: color-mix(
    in srgb,
    var(--primary-color) 10%,
    transparent
  ) !important;
}

.ac-option {
  display: flex;
  flex-direction: column;
  padding: 0.45rem 0.75rem;
  gap: 0.15rem;
}

.ac-razao {
  font-size: 0.75rem;
  color: var(--sidebar-text);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 240px;
}

.ac-meta {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.ac-cnpj {
  font-size: 0.65rem;
  color: var(--text-muted);
  letter-spacing: 0.02em;
}

.ac-loc {
  font-size: 0.65rem;
  color: var(--primary-color);
  opacity: 0.75;
}

/* Checkbox Filter Styles */
.filter-checkbox-wrapper {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  padding: 0;
}

/* Caixa sem título: texto, ajuda e borracha na mesma linha. */
.filter-checkbox-wrapper.checkbox-linha {
  flex-direction: row;
  align-items: center;
  gap: 0.25rem;
}

.checkbox-label {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-size: 0.8125rem;
  color: var(--text-color);
  cursor: pointer;
  user-select: none;
  transition: color 0.2s ease;
}

.checkbox-label span {
  color: var(--text-color-85);
  font-weight: 400;
}

.checkbox-label:hover {
  color: var(--sidebar-text);
}

.filter-checkbox {
  width: 1.125rem;
  height: 1.125rem;
  cursor: pointer;
}

:global(.filter-checkbox.p-checkbox .p-checkbox-box) {
  width: 1.125rem;
  height: 1.125rem;
  border-radius: 0.25rem;
  border-color: var(--sidebar-border);
  background: var(--sidebar-input-bg);
  transition:
    background-color 0.2s ease,
    border-color 0.2s ease,
    box-shadow 0.2s ease;
}

/* Só a caixa desmarcada: marcada, o hover não pode apagar o fundo laranja. */
:global(.checkbox-label:hover .filter-checkbox.p-checkbox:not(.p-highlight):not(.p-checkbox-checked) .p-checkbox-box) {
  border-color: color-mix(in srgb, var(--sidebar-text) 45%, var(--sidebar-border));
  background: var(--sidebar-input-bg);
}

:global(.filter-checkbox.p-checkbox.p-highlight .p-checkbox-box),
:global(.filter-checkbox.p-checkbox-checked .p-checkbox-box) {
  border-color: var(--primary-color);
  background: var(--primary-color);
}

:global(.filter-checkbox.p-checkbox .p-checkbox-icon) {
  color: var(--sidebar-bg);
}

:global(.filter-checkbox.p-checkbox.p-focus .p-checkbox-box),
:global(.filter-checkbox.p-checkbox:has(.p-checkbox-input:focus-visible) .p-checkbox-box) {
  outline: 2px solid color-mix(in srgb, var(--sidebar-text) 45%, transparent);
  outline-offset: 2px;
}


</style>
