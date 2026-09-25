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
import { useFormatting } from "@/composables/useFormatting";
import { useSliderPeriodLogic } from "@/composables/useSliderPeriodLogic";
import { useFilterParameters } from "@/composables/useFilterParameters";
import { FILTER_OPTIONS } from "@/config/filterOptions";
import { filterActionTooltip, filterTooltip } from "@/config/filterTooltipConfig";
import Button from "primevue/button";
import Checkbox from "primevue/checkbox";
import Dropdown from "primevue/dropdown";
import Slider from "primevue/slider";
import InputText from "primevue/inputtext";
import AutoComplete from "primevue/autocomplete";
import DataIntegrityBanner from "@/layouts/components/DataIntegrityBanner.vue";

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
  parTeia: filterTooltip("parTeia"),
  cnaeIncompativel: filterTooltip("cnaeIncompativel"),
  socioIdadeAtipica: filterTooltip("socioIdadeAtipica"),
  socioFalecido: filterTooltip("socioFalecido"),
  socioBeneficio: filterTooltip("socioBeneficio"),
  socioEsocial: filterTooltip("socioEsocial"),
  dispersaoUfSemFronteira: filterTooltip("dispersaoUfSemFronteira"),
  volumeAtipico: filterTooltip("volumeAtipico"),
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

const { formatBRL: formatCurrency } = useFormatting();

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

const stepPercStart = (delta) => {
  const [s, e] = filterStore.percentualNaoComprovacaoRange;
  const newS = Math.max(0, Math.min(e - 1, s + delta));
  if (newS === s) return;
  filterStore.percentualNaoComprovacaoRange = [newS, e];
  applyPercentualNaoComprovacao();
};

const stepPercEnd = (delta) => {
  const [s, e] = filterStore.percentualNaoComprovacaoRange;
  const newE = Math.max(s + 1, Math.min(100, e + delta));
  if (newE === e) return;
  filterStore.percentualNaoComprovacaoRange = [s, newE];
  applyPercentualNaoComprovacao();
};

const applyValorMinSemComp = () => {
  filterStore.valorMinSemCompFilter = filterStore.valorMinSemComp;
};

const valorMinQuickSelect = [100000, 300000, 500000];

const formatValorChip = (v) =>
  v >= 1000000 ? `R$${v / 1000000}M` : `R$${v / 1000}k`;

const setValorMin = (v) => {
  filterStore.valorMinSemComp = v;
  applyValorMinSemComp();
};

const stepValorMin = (delta) => {
  const next = Math.max(0, Math.min(FILTER_DEFAULTS.VALOR_MAX, filterStore.valorMinSemComp + delta));
  filterStore.valorMinSemComp = next;
  applyValorMinSemComp();
};

const volumeAtipicoQuickSelect = [50, 500, 1000, 1500];

const clampVolumeAtipico = (value) => {
  const numeric = Number(value) || FILTER_DEFAULTS.VOLUME_ATIPICO_PERCENTUAL;
  return Math.max(
    FILTER_DEFAULTS.VOLUME_ATIPICO_MIN,
    Math.min(FILTER_DEFAULTS.VOLUME_ATIPICO_MAX, numeric),
  );
};

const applyVolumeAtipico = () => {
  filterStore.volumeAtipicoEnabled = true;
  const clamped = clampVolumeAtipico(
    filterStore.volumeAtipicoPercentual,
  );
  filterStore.volumeAtipicoPercentual = clamped;
  filterStore.volumeAtipicoPercentualFilter = clamped;
};

const setVolumeAtipico = (value) => {
  filterStore.volumeAtipicoEnabled = true;
  const clamped = clampVolumeAtipico(value);
  filterStore.volumeAtipicoPercentual = clamped;
  filterStore.volumeAtipicoPercentualFilter = clamped;
};

const stepVolumeAtipico = (delta) => {
  filterStore.volumeAtipicoEnabled = true;
  const clamped = clampVolumeAtipico(
    filterStore.volumeAtipicoPercentual + delta,
  );
  filterStore.volumeAtipicoPercentual = clamped;
  filterStore.volumeAtipicoPercentualFilter = clamped;
};

const clearVolumeAtipico = () => {
  filterStore.volumeAtipicoEnabled = FILTER_DEFAULTS.VOLUME_ATIPICO_ENABLED;
  filterStore.volumeAtipicoPercentual =
    FILTER_DEFAULTS.VOLUME_ATIPICO_PERCENTUAL;
  filterStore.volumeAtipicoPercentualFilter =
    FILTER_DEFAULTS.VOLUME_ATIPICO_PERCENTUAL;
};

const dispersaoUfQuickSelect = [10, 20, 30, 50];

const clampDispersaoUfSemFronteira = (value) => {
  const numeric = Number(value) || FILTER_DEFAULTS.DISPERSAO_UF_SEM_FRONTEIRA_PERCENTUAL;
  return Math.max(
    FILTER_DEFAULTS.DISPERSAO_UF_SEM_FRONTEIRA_MIN,
    Math.min(FILTER_DEFAULTS.DISPERSAO_UF_SEM_FRONTEIRA_MAX, numeric),
  );
};

const applyDispersaoUfSemFronteira = () => {
  filterStore.dispersaoUfSemFronteiraEnabled = true;
  filterStore.dispersaoUfSemFronteiraPercentual = clampDispersaoUfSemFronteira(
    filterStore.dispersaoUfSemFronteiraPercentual,
  );
};

const setDispersaoUfSemFronteira = (value) => {
  filterStore.dispersaoUfSemFronteiraEnabled = true;
  filterStore.dispersaoUfSemFronteiraPercentual =
    clampDispersaoUfSemFronteira(value);
};

const stepDispersaoUfSemFronteira = (delta) => {
  filterStore.dispersaoUfSemFronteiraEnabled = true;
  filterStore.dispersaoUfSemFronteiraPercentual =
    clampDispersaoUfSemFronteira(
      filterStore.dispersaoUfSemFronteiraPercentual + delta,
    );
};

const clearDispersaoUfSemFronteira = () => {
  filterStore.dispersaoUfSemFronteiraEnabled =
    FILTER_DEFAULTS.DISPERSAO_UF_SEM_FRONTEIRA_ENABLED;
  filterStore.dispersaoUfSemFronteiraPercentual =
    FILTER_DEFAULTS.DISPERSAO_UF_SEM_FRONTEIRA_PERCENTUAL;
};

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
    "volumeAtipicoEnabled",
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
  ]),
);


// ── Período de análise (slider) ──────────────────────────────────────────────
const displayYears = computed(() => ANALYSIS_YEARS.filter((y) => y >= 2020));

const {
  availableMonths,
  timeSliderValue,
  applySliderPeriod,
  toggleYear,
  isYearActive,
  isYearDisabled,
  resetYears,
  startMonthLabel,
  endMonthLabel,
} = useSliderPeriodLogic();

const { getApiParams } = useFilterParameters();

// Move a ponta inicial do slider em `delta` meses (+1 ou -1)
const stepStart = (delta) => {
  filterStore.resetAnimationPreview();
  const [s, e] = timeSliderValue.value;
  const newS = Math.max(0, Math.min(e - 1, s + delta));
  if (newS === s) return;
  timeSliderValue.value = [newS, e];
  applySliderPeriod([newS, e]);
};

// Move a ponta final do slider em `delta` meses (+1 ou -1)
const stepEnd = (delta) => {
  filterStore.resetAnimationPreview();
  const [s, e] = timeSliderValue.value;
  const newE = Math.max(s + 1, Math.min(availableMonths.length - 1, e + delta));
  if (newE === e) return;
  timeSliderValue.value = [s, newE];
  applySliderPeriod([s, newE]);
};

onMounted(() => applySliderPeriod(timeSliderValue.value));

const toggleAnalysisYear = (year) => {
  filterStore.resetAnimationPreview();
  toggleYear(year);
};

// Handler do @slideend do Slider — extraído do template para evitar o auto-unwrap
// de refs pelo Vue no contexto inline, que causava "Cannot set properties of null".
const onSliderEnd = () => {
  filterStore.resetAnimationPreview();
  applySliderPeriod(timeSliderValue.value);
};

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
  { id: "percentual", section: "geral", label: "% de não comprovação", keywords: "percentual nao comprovacao risco faixa auditoria" },
  { id: "slider", section: "geral", label: "Período de Análise", keywords: "periodo slider semestral mensal tempo data" },
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
      <div
        v-show="shouldDisplayFilter('geral', 'uf')"
        class="filter-section"
        :class="{ 'filter-locked': allFiltersLocked }"
      >
        <label class="filter-label">
          UF
          <i
            class="pi pi-info-circle filter-info-icon"
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
        <Dropdown
          v-model="filterStore.selectedUF"
          :options="ufOptions"
          placeholder="Estado"
          class="w-full filter-input"
          panelClass="sidebar-panel"
          :class="{ 'filter-active': isFilterActive('selectedUF') }"
        />
      </div>

      <div
        v-show="shouldDisplayFilter('geral', 'regiao')"
        class="filter-section"
        :class="{ 'filter-locked': allFiltersLocked }"
      >
        <label class="filter-label">
          Região de Saúde
          <i
            class="pi pi-info-circle filter-info-icon"
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
            class="pi pi-info-circle filter-info-icon"
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

      <div
        v-show="shouldDisplayFilter('geral', 'unidadePf')"
        class="filter-section"
        :class="{ 'filter-locked': allFiltersLocked }"
      >
        <label class="filter-label">
          Jurisdição PF
          <i
            class="pi pi-info-circle filter-info-icon"
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

      <div v-show="!isSectionCollapsed('geral')" class="grid-filters" :class="{ 'filter-locked': allFiltersLocked }">
        <div v-show="shouldDisplayFilter('geral', 'situacao')" class="filter-section">
          <label class="filter-label">
            Situação RF
            <i
              class="pi pi-info-circle filter-info-icon"
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
              class="pi pi-info-circle filter-info-icon"
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
              class="pi pi-info-circle filter-info-icon"
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
            Grande Rede
            <i
              class="pi pi-info-circle filter-info-icon"
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
            class="pi pi-info-circle filter-info-icon"
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

      <div
        v-show="shouldDisplayFilter('geral', 'percentual')"
        class="filter-section"
        :class="{ 'filter-locked': allFiltersLocked }"
      >
        <label class="filter-label">
          % de não comprovação
          <i
            class="pi pi-info-circle filter-info-icon"
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
          <div class="perc-chips">
            <button
              v-for="v in [10, 20, 40, 60, 80]"
              :key="v"
              class="perc-chip"
              :class="{
                'perc-chip-active':
                  filterStore.percentualNaoComprovacaoRange[0] === v,
              }"
              @click="
                () => {
                  filterStore.percentualNaoComprovacaoRange = [v, 100];
                  applyPercentualNaoComprovacao();
                }
              "
            >
              {{ v }}%
            </button>
          </div>
          <div class="period-steppers">
            <div class="period-stepper-group">
              <button
                class="period-step-btn"
                :disabled="filterStore.percentualNaoComprovacaoRange[0] === 0"
                @click="stepPercStart(-1)"
              >
                <i class="pi pi-chevron-left" />
              </button>
              <span class="period-step-label"
                >{{ filterStore.percentualNaoComprovacaoRange[0] }}%</span
              >
              <button
                class="period-step-btn"
                :disabled="
                  filterStore.percentualNaoComprovacaoRange[0] >=
                  filterStore.percentualNaoComprovacaoRange[1] - 1
                "
                @click="stepPercStart(1)"
              >
                <i class="pi pi-chevron-right" />
              </button>
            </div>
            <div class="period-stepper-group">
              <button
                class="period-step-btn"
                :disabled="
                  filterStore.percentualNaoComprovacaoRange[1] <=
                  filterStore.percentualNaoComprovacaoRange[0] + 1
                "
                @click="stepPercEnd(-1)"
              >
                <i class="pi pi-chevron-left" />
              </button>
              <span class="period-step-label"
                >{{ filterStore.percentualNaoComprovacaoRange[1] }}%</span
              >
              <button
                class="period-step-btn"
                :disabled="filterStore.percentualNaoComprovacaoRange[1] === 100"
                @click="stepPercEnd(1)"
              >
                <i class="pi pi-chevron-right" />
              </button>
            </div>
          </div>
          <Slider
            v-model="filterStore.percentualNaoComprovacaoRange"
            range
            class="w-full"
            @slideend="applyPercentualNaoComprovacao"
          />
        </div>
      </div>

      <div
        v-show="shouldDisplayFilter('geral', 'slider')"
        class="filter-section"
        :class="{ 'filter-locked-alt': periodFilterLocked }"
      >
        <label class="filter-label" style="pointer-events: auto">
          Período de Análise
          <i
            class="pi pi-info-circle filter-info-icon"
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
          <div class="perc-chips" style="margin-bottom: 0.5rem">
            <button
              v-for="year in displayYears"
              :key="year"
              class="perc-chip"
              :class="{
                'perc-chip-active': isYearActive(year),
                'perc-chip-disabled': isYearDisabled(year),
              }"
              :disabled="isYearDisabled(year) || periodFilterLocked"
              @click="toggleAnalysisYear(year)"
            >
              {{ year }}
            </button>
          </div>
          <div class="period-steppers">
            <div class="period-stepper-group">
              <button
                class="period-step-btn"
                :disabled="timeSliderValue[0] === 0 || periodFilterLocked"
                @click="stepStart(-1)"
              >
                <i class="pi pi-chevron-left" />
              </button>
              <span class="period-step-label">{{ startMonthLabel }}</span>
              <button
                class="period-step-btn"
                :disabled="
                  timeSliderValue[0] >= timeSliderValue[1] - 1 ||
                  periodFilterLocked
                "
                @click="stepStart(1)"
              >
                <i class="pi pi-chevron-right" />
              </button>
            </div>
            <div class="period-stepper-group">
              <button
                class="period-step-btn"
                :disabled="
                  timeSliderValue[1] <= timeSliderValue[0] + 1 ||
                  periodFilterLocked
                "
                @click="stepEnd(-1)"
              >
                <i class="pi pi-chevron-left" />
              </button>
              <span class="period-step-label">{{ endMonthLabel }}</span>
              <button
                class="period-step-btn"
                :disabled="
                  timeSliderValue[1] === availableMonths.length - 1 ||
                  periodFilterLocked
                "
                @click="stepEnd(1)"
              >
                <i class="pi pi-chevron-right" />
              </button>
            </div>
          </div>
          <div class="slider-wrapper">
            <Slider
              v-model="timeSliderValue"
              range
              :min="0"
              :max="availableMonths.length - 1"
              class="w-full time-slider"
              :disabled="periodFilterLocked"
              @slideend="onSliderEnd"
            />
          </div>
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
            class="pi pi-info-circle filter-info-icon"
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
          <div class="perc-chips" style="grid-template-columns: repeat(3, 1fr)">
            <button
              v-for="v in valorMinQuickSelect"
              :key="v"
              class="perc-chip"
              :class="{ 'perc-chip-active': filterStore.valorMinSemComp === v }"
              @click="setValorMin(v)"
            >
              {{ formatValorChip(v) }}
            </button>
          </div>
          <div class="period-steppers">
            <div class="period-stepper-group">
              <button
                class="period-step-btn"
                :disabled="filterStore.valorMinSemComp <= 0"
                @click="stepValorMin(-10000)"
              >
                <i class="pi pi-chevron-left" />
              </button>
              <span class="period-step-label">{{ formatCurrency(filterStore.valorMinSemComp) }}</span>
              <button
                class="period-step-btn"
                :disabled="filterStore.valorMinSemComp >= FILTER_DEFAULTS.VALOR_MAX"
                @click="stepValorMin(10000)"
              >
                <i class="pi pi-chevron-right" />
              </button>
            </div>
          </div>
          <Slider
            v-model="filterStore.valorMinSemComp"
            :min="0"
            :max="FILTER_DEFAULTS.VALOR_MAX"
            :step="1000"
            class="w-full"
            @slideend="applyValorMinSemComp"
          />
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
              Busca Alvo
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
              Target Cluster
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
              CPF/CNPJ Alvo
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

      <div
        v-show="shouldDisplayFilter('integridade', 'parTeia')"
        class="filter-section"
        :class="{ 'filter-locked': allFiltersLocked }"
      >
        <label class="filter-label">
          CNPJs com PAR
          <i
            class="pi pi-info-circle filter-info-icon"
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
        <label class="filter-label">
          CNPJ com CNAE Incompatível
          <i
            class="pi pi-info-circle filter-info-icon"
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
        </label>
        <div class="filter-checkbox-wrapper" :class="{ 'filter-active-box': isFilterActive('selectedCnaeIncompativel') }">
          <label class="checkbox-label">
            <Checkbox
              v-model="filterStore.selectedCnaeIncompativel"
              class="filter-checkbox"
              binary
            />
            <span>Apenas CNPJs com CNAE incompatível</span>
          </label>
        </div>
      </div>

      <div
        v-show="shouldDisplayFilter('integridade', 'socioIdadeAtipica')"
        class="filter-section"
        :class="{ 'filter-locked': allFiltersLocked }"
      >
        <label class="filter-label">
          Sócio &lt; 21 anos ou &gt; 80 anos
          <i
            class="pi pi-info-circle filter-info-icon"
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
        </label>
        <div class="filter-checkbox-wrapper" :class="{ 'filter-active-box': isFilterActive('selectedSocioIdadeAtipica') }">
          <label class="checkbox-label">
            <Checkbox
              v-model="filterStore.selectedSocioIdadeAtipica"
              class="filter-checkbox"
              binary
            />
            <span>Apenas sócios &lt; 21 ou &gt; 80 anos</span>
          </label>
        </div>
      </div>

      <div
        v-show="shouldDisplayFilter('integridade', 'socioFalecido')"
        class="filter-section"
        :class="{ 'filter-locked': allFiltersLocked }"
      >
        <label class="filter-label">
          Sócio ativo falecido
          <i
            class="pi pi-info-circle filter-info-icon"
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
        </label>
        <div class="filter-checkbox-wrapper" :class="{ 'filter-active-box': isFilterActive('selectedSocioFalecido') }">
          <label class="checkbox-label">
            <Checkbox
              v-model="filterStore.selectedSocioFalecido"
              class="filter-checkbox"
              binary
            />
            <span>Apenas CNPJs com sócio falecido</span>
          </label>
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
            class="pi pi-info-circle filter-info-icon"
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
            class="pi pi-info-circle filter-info-icon"
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

      <div
        v-show="shouldDisplayFilter('integridade', 'dispersaoUf')"
        class="filter-section"
        :class="{ 'filter-locked': allFiltersLocked }"
      >
        <label class="filter-label">
          Vendas para UFs sem fronteira
          <i
            class="pi pi-info-circle filter-info-icon"
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
          <div class="perc-chips" style="grid-template-columns: repeat(4, 1fr); margin-bottom: 0.5rem">
            <button
              v-for="value in dispersaoUfQuickSelect"
              :key="value"
              class="perc-chip"
              :class="{
                active:
                  filterStore.dispersaoUfSemFronteiraEnabled &&
                  filterStore.dispersaoUfSemFronteiraPercentual === value,
              }"
              @click="setDispersaoUfSemFronteira(value)"
            >
              {{ value }}%
            </button>
          </div>

          <div class="period-steppers">
            <button
              class="period-step-btn"
              @click="stepDispersaoUfSemFronteira(-1)"
              :disabled="
                filterStore.dispersaoUfSemFronteiraPercentual <=
                FILTER_DEFAULTS.DISPERSAO_UF_SEM_FRONTEIRA_MIN
              "
            >
              <i class="pi pi-minus" />
            </button>
            <span class="period-label percent-label">
              mínimo {{ filterStore.dispersaoUfSemFronteiraPercentual }}%
            </span>
            <button
              class="period-step-btn"
              @click="stepDispersaoUfSemFronteira(1)"
              :disabled="
                filterStore.dispersaoUfSemFronteiraPercentual >=
                FILTER_DEFAULTS.DISPERSAO_UF_SEM_FRONTEIRA_MAX
              "
            >
              <i class="pi pi-plus" />
            </button>
          </div>

          <Slider
            v-model="filterStore.dispersaoUfSemFronteiraPercentual"
            :min="FILTER_DEFAULTS.DISPERSAO_UF_SEM_FRONTEIRA_MIN"
            :max="FILTER_DEFAULTS.DISPERSAO_UF_SEM_FRONTEIRA_MAX"
            :step="1"
            class="custom-slider"
            @slideend="applyDispersaoUfSemFronteira"
          />
        </div>
      </div>

      <div
        v-show="shouldDisplayFilter('integridade', 'volumeAtipico')"
        class="filter-section"
        :class="{ 'filter-locked': volumeAtipicoFilterLocked }"
      >
        <label class="filter-label">
          Aumento Semestral Atípico
          <i
            class="pi pi-info-circle filter-info-icon"
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
          <div
            class="perc-chips"
            style="grid-template-columns: repeat(4, 1fr); margin-bottom: 0.5rem"
          >
            <button
              v-for="value in volumeAtipicoQuickSelect"
              :key="value"
              class="perc-chip"
              :class="{
                'perc-chip-active':
                  filterStore.volumeAtipicoEnabled &&
                  filterStore.volumeAtipicoPercentual === value,
              }"
              @click="setVolumeAtipico(value)"
            >
              {{ value }}%
            </button>
          </div>
          <div class="period-steppers">
            <div class="period-stepper-group">
              <button
                class="period-step-btn"
                :disabled="
                  filterStore.volumeAtipicoPercentual <=
                  FILTER_DEFAULTS.VOLUME_ATIPICO_MIN
                "
                @click="stepVolumeAtipico(-10)"
              >
                <i class="pi pi-chevron-left" />
              </button>
              <span class="period-step-label">
                {{ filterStore.volumeAtipicoPercentual }}%
              </span>
              <button
                class="period-step-btn"
                :disabled="
                  filterStore.volumeAtipicoPercentual >=
                  FILTER_DEFAULTS.VOLUME_ATIPICO_MAX
                "
                @click="stepVolumeAtipico(10)"
              >
                <i class="pi pi-chevron-right" />
              </button>
            </div>
          </div>
          <Slider
            v-model="filterStore.volumeAtipicoPercentual"
            :min="FILTER_DEFAULTS.VOLUME_ATIPICO_MIN"
            :max="FILTER_DEFAULTS.VOLUME_ATIPICO_MAX"
            :step="10"
            class="w-full"
            @slideend="applyVolumeAtipico"
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
/* SIDEBAR */
.admin-sidebar {
  position: fixed;
  top: 56px;
  left: 0;
  z-index: 200;
  width: var(--sidebar-width);
  background: var(--sidebar-bg) !important;
  color: var(--sidebar-text);
  transition: width 0.35s cubic-bezier(0.4, 0, 0.2, 1);
  will-change: width;
  display: flex;
  flex-direction: column;
  height: calc(100vh - 56px);
  border-right: 1px solid var(--sidebar-border);
  overflow: hidden;
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
  font-weight: 800;
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
  font-size: 0.72rem;
  font-weight: 800;
  color: var(--sidebar-text);
  opacity: 0.45;
  letter-spacing: 0.12em;
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
.sidebar-divider {
  border: 0;
  border-top: 1px solid var(--sidebar-border);
  opacity: 0.5;
  margin: 0.5rem 0;
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
  background: color-mix(in srgb, var(--primary-color) 6%, transparent);
  border: 0;
  color: var(--sidebar-text);
  font-size: 0.64rem;
  font-weight: 800;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  text-align: left;
  cursor: pointer;
  border-radius: 6px;
  transition: background 0.18s ease, color 0.18s ease;
}

.sidebar-section-heading:hover {
  background: color-mix(in srgb, var(--primary-color) 8%, transparent);
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

.sidebar-section-heading > i {
  color: var(--primary-color);
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
  background: color-mix(in srgb, var(--primary-color) 16%, var(--sidebar-bg));
  color: var(--primary-color);
  font-size: 0.62rem;
  font-weight: 800;
  letter-spacing: 0;
}

.sidebar-section-heading.searching {
  color: var(--sidebar-text);
}

.sidebar-section-heading.searching small {
  background: color-mix(in srgb, var(--primary-color) 26%, var(--sidebar-bg));
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
  border-color: color-mix(in srgb, var(--primary-color) 40%, var(--sidebar-border));
}

.sidebar-search:focus-within {
  border-color: var(--primary-color);
  background: var(--sidebar-input-bg);
  box-shadow: 0 0 0 1px var(--primary-color),
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
  font-size: 0.75rem;
  font-family: inherit;
  letter-spacing: 0.01em;
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

.filter-section {
  padding: 0.35rem 0.48rem;
  border-radius: 7px;
  border-left: 2px solid transparent;
  background: transparent;
  transition:
    background 0.16s ease,
    border-color 0.16s ease;
}

.filter-section:hover {
  background: color-mix(in srgb, var(--sidebar-text) 4%, transparent);
}

.filter-section:has(.filter-active),
.filter-section:has(.filter-active-box) {
  border-left-color: var(--primary-color);
  background: color-mix(in srgb, var(--primary-color) 8%, transparent);
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

.filter-label {
  display: flex;
  align-items: center;
  gap: 0.25rem;
  font-size: 0.65rem;
  font-weight: 700;
  text-transform: uppercase;
  margin-bottom: 0.5rem;
  color: var(--sidebar-text);
  letter-spacing: 0.5px;
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
  font-size: 0.68rem;
  color: var(--sidebar-text);
  opacity: 0.55;
  cursor: help;
}

.filter-info-icon:hover {
  opacity: 0.9;
  color: var(--primary-color);
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
  font-size: 0.75rem;
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

:deep(.filter-input .p-dropdown-label),
:deep(.filter-input .p-dropdown-trigger) {
  background: transparent !important;
  color: inherit !important;
}

:global(.admin-sidebar .p-dropdown.p-focus),
:global(.admin-sidebar .p-inputtext:not(.p-dropdown-label):focus),
:global(.admin-sidebar .filter-active.p-dropdown),
:global(.admin-sidebar .filter-active.p-inputtext:not(.p-dropdown-label)) {
  border: 2px solid color-mix(in srgb, var(--primary-color) 50%, transparent) !important;
  background: rgba(255, 255, 255, 0.03) !important;
  box-shadow: 0 0 0 2px
    color-mix(in srgb, var(--primary-color) 15%, transparent) !important;
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

:global(.sidebar-panel .p-dropdown-items .p-dropdown-item) {
  color: var(--sidebar-text) !important;
  font-size: 0.8rem;
}

:global(
  .sidebar-panel
    .p-dropdown-items
    .p-dropdown-item:not(.p-highlight):not(.p-disabled):hover
) {
  background: var(--sidebar-input-bg) !important;
  color: var(--sidebar-text) !important;
}

:global(.sidebar-panel .p-dropdown-items .p-dropdown-item.p-highlight) {
  background: color-mix(
    in srgb,
    var(--primary-color) 20%,
    transparent
  ) !important;
  color: var(--primary-color) !important;
}

:global(.sidebar-panel .p-dropdown-header) {
  background: var(--sidebar-bg) !important;
  border-bottom: 1px solid var(--sidebar-border) !important;
}

:global(.sidebar-panel .p-dropdown-filter-container .p-inputtext) {
  background: var(--sidebar-input-bg) !important;
  color: var(--sidebar-text) !important;
}

/* SLIDERS */
.slider-container {
  padding: 0.5rem 0.2rem;
}

.slider-values {
  display: flex;
  justify-content: space-between;
  font-size: 0.65rem;
  font-weight: 700;
  margin-bottom: 0.4rem;
  color: var(--sidebar-text);
}

.perc-chips {
  display: grid;
  grid-template-columns: repeat(5, 1fr);
  gap: 0.3rem;
  margin-bottom: 0.5rem;
}

.perc-chip {
  font-size: 0.68rem;
  font-weight: 700;
  padding: 0.28rem 0;
  border-radius: 6px;
  border: 1px solid var(--sidebar-border);
  color: var(--sidebar-text);
  background: var(--sidebar-input-bg);
  cursor: pointer;
  transition: all 0.2s ease;
  font-family: inherit;
}

.perc-chip:hover {
  border-color: var(--primary-color);
  color: var(--primary-color);
  background: color-mix(in srgb, var(--primary-color) 8%, transparent);
}

.perc-chip:focus {
  outline: none;
}

.perc-chip-active {
  border-color: var(--primary-color) !important;
  color: var(--primary-color) !important;
  background: color-mix(
    in srgb,
    var(--primary-color) 14%,
    transparent
  ) !important;
  box-shadow: 0 0 6px color-mix(in srgb, var(--primary-color) 20%, transparent);
}

.perc-chip-disabled {
  opacity: 0.25;
  cursor: not-allowed;
  pointer-events: none;
}

.slider-wrapper {
  position: relative;
  margin-top: 8px;
}

.filter-input {
  margin-bottom: 4px !important;
}

.period-steppers {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 4px;
  gap: 0.25rem;
}

.period-stepper-group {
  display: flex;
  align-items: center;
  gap: 2px;
  flex: 1;
}

.period-step-label {
  font-size: 0.68rem;
  font-weight: 600;
  color: var(--sidebar-text);
  background: var(--sidebar-input-bg);
  border: 1px solid var(--sidebar-border);
  border-radius: 4px;
  padding: 2px 6px;
  min-width: 62px;
  flex: 1;
  text-align: center;
  white-space: nowrap;
}

.period-step-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 20px;
  height: 20px;
  padding: 0;
  border: 1px solid var(--sidebar-border);
  border-radius: 4px;
  background: var(--sidebar-input-bg);
  color: var(--text-muted);
  cursor: pointer;
  transition:
    background 0.15s,
    color 0.15s,
    border-color 0.15s;
  flex-shrink: 0;
}

.period-step-btn i {
  font-size: 0.55rem;
}

.period-step-btn:hover:not(:disabled) {
  background: color-mix(
    in srgb,
    var(--primary-color) 12%,
    var(--sidebar-input-bg)
  );
  border-color: var(--primary-color);
  color: var(--primary-color);
}

.period-step-btn:disabled {
  opacity: 0.3;
  cursor: not-allowed;
}

:deep(.p-slider) {
  background: var(--sidebar-border);
  height: 4px !important;
}

:deep(.p-slider .p-slider-range) {
  background: var(--sidebar-border) !important;
}

:deep(.p-slider-handle) {
  border: 2px solid var(--accent-indigo) !important;
  background: var(--sidebar-bg) !important;
  width: 14px !important;
  height: 14px !important;
  margin-top: -6px !important;
  transition:
    background 0.2s,
    box-shadow 0.2s;
}

:deep(.p-slider:not(.p-disabled) .p-slider-handle:hover) {
  background: var(--accent-indigo) !important;
  box-shadow: 0 0 0 6px
    color-mix(in srgb, var(--accent-indigo) 20%, transparent) !important;
}

.filter-active-box :deep(.p-slider-handle) {
  border-color: var(--primary-color) !important;
}

.filter-active-box :deep(.p-slider:not(.p-disabled) .p-slider-handle:hover) {
  background: var(--primary-color) !important;
  box-shadow: 0 0 0 6px
    color-mix(in srgb, var(--primary-color) 20%, transparent) !important;
}

/* FILTROS ATIVOS */
.filter-active-box {
  background: color-mix(
    in srgb,
    var(--primary-color) 12%,
    transparent
  ) !important;
  border-radius: 4px;
}

/* BOTÃO LIMPAR FILTROS */
:deep(.clear-filters-btn.p-button) {
  background: transparent !important;
  transition: all 0.2s ease !important;
}

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
  margin-bottom: 0.4rem;
}

:deep(.filter-input.sm .p-inputtext),
:deep(.filter-input.sm .p-dropdown-label) {
  padding: 0.5rem;
  font-size: 0.8rem;
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
  font-size: 0.75rem;
  background: var(--sidebar-input-bg) !important;
  border-color: var(--sidebar-border) !important;
  color: var(--sidebar-text) !important;
}

:global(.admin-sidebar .estabelecimento-ac .p-autocomplete-input:focus) {
  border: 2px solid color-mix(in srgb, var(--primary-color) 50%, transparent) !important;
  background: rgba(255, 255, 255, 0.03) !important;
  box-shadow: 0 0 0 2px
    color-mix(in srgb, var(--primary-color) 15%, transparent) !important;
  outline: none !important;
}

:global(
  .admin-sidebar .filter-active.estabelecimento-ac .p-autocomplete-input
) {
  border: 2px solid color-mix(in srgb, var(--primary-color) 50%, transparent) !important;
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
  padding: 0.5rem 0;
}

.checkbox-label {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-size: 0.875rem;
  color: var(--text-color);
  cursor: pointer;
  user-select: none;
  transition: color 0.2s ease;
}

.checkbox-label span {
  color: var(--sidebar-text);
  font-weight: 400;
}

.checkbox-label:hover {
  color: var(--primary-color);
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

:global(.checkbox-label:hover .filter-checkbox.p-checkbox .p-checkbox-box) {
  border-color: color-mix(in srgb, var(--primary-color) 55%, var(--sidebar-border));
  background: color-mix(in srgb, var(--sidebar-input-bg) 86%, var(--primary-color));
}

:global(.filter-checkbox.p-checkbox.p-highlight .p-checkbox-box),
:global(.filter-checkbox.p-checkbox-checked .p-checkbox-box) {
  border-color: var(--primary-color);
  background: var(--primary-color);
}

:global(.filter-checkbox.p-checkbox .p-checkbox-icon) {
  color: var(--color-on-primary, #ffffff);
}

:global(.filter-checkbox.p-checkbox.p-focus .p-checkbox-box),
:global(.filter-checkbox.p-checkbox:has(.p-checkbox-input:focus-visible) .p-checkbox-box) {
  outline: 2px solid var(--primary-color);
  outline-offset: 2px;
}


</style>
