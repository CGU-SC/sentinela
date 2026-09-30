<script setup>
import { computed, ref, watch } from 'vue';
import { useCnpjDetailStore } from '@/stores/cnpjDetail';
import { useFilterStore } from '@/stores/filters';
import { useFormatting } from '@/composables/useFormatting';
import { useStableTabState } from '@/composables/useStableTabState';
import TabPlaceholder from './TabPlaceholder.vue';
import { useThemeStore } from '@/stores/theme';
import { DATA_NEUTRAL } from '@/config/colors';

const props = defineProps({
  cnpj: { type: String, required: true },
  periodSummary: { type: Object, default: null },
  periodLoading: { type: Boolean, default: false },
});

const cnpjDetailStore = useCnpjDetailStore();
const themeStore = useThemeStore();
// Cor de dados neutra (azul-aço), a mesma da barra "Participação no valor" do Perfil de CRMs.
const dataColorVars = computed(() => ({ '--data-color': DATA_NEUTRAL[themeStore.isDark ? 'dark' : 'light'].strong }));
const filterStore = useFilterStore();
const { formatCurrencyFull: _fmt, formatarData, toLocalISO } = useFormatting();

const formattedPeriod = computed(() => {
  const [start, end] = filterStore.periodo ?? [];
  if (!start || !end) return null;
  return { start: formatarData(toLocalISO(start)), end: formatarData(toLocalISO(end)) };
});

// Wrapper null-safe
const fmt = (val) => (val === null || val === undefined) ? '—' : _fmt(val);
const fmtPct = (val) => (val === null || val === undefined) ? '—' : val.toFixed(2) + '%';

const loading = computed(() => cnpjDetailStore.movimentacaoLoading);
const loaded  = computed(() => cnpjDetailStore.movimentacaoLoaded);
const error   = computed(() => cnpjDetailStore.movimentacaoError);
const data    = computed(() => cnpjDetailStore.movimentacaoData);
const {
  cachedData: cachedMovimentacaoData,
  isRefreshing,
} = useStableTabState(data, loading, error);
const rows    = computed(() => cachedMovimentacaoData.value?.rows ?? []);
const summary = computed(() => cachedMovimentacaoData.value?.summary ?? null);
const noMovementInPeriod = computed(() =>
  !props.periodLoading &&
  Boolean(props.periodSummary) &&
  Number(props.periodSummary.totalMov ?? 0) === 0
);

// ── Agrupa linhas em seções por GTIN ─────────────────────────────────────────
const sections = computed(() => {
  const result = [];
  let cur = null;

  for (const row of rows.value) {
    if (row.tipo_linha === 'header_medicamento') {
      if (cur) result.push(cur);
      cur = { gtin: row.gtin, medicamento: '', rows: [], subtotal: null };
    } else if (row.tipo_linha === 'resumo_parcial' && cur) {
      cur.subtotal = row;
      // Resumo parcial também contém o nome limpo caso não tenha havido vendas no período exibido (raro)
      if (!cur.medicamento) cur.medicamento = row.medicamento;
    } else if (cur && (row.tipo_linha === 'venda_normal' || row.tipo_linha === 'venda_irregular')) {
      // Captura o nome limpo diretamente da linha de venda
      if (!cur.medicamento) cur.medicamento = row.medicamento;
      cur.rows.push(row);
    } else if (cur && row.tipo_linha !== 'header_colunas') {
      cur.rows.push(row);
    }
  }
  if (cur) result.push(cur);
  return result;
});

// ── Estado de expansão ────────────────────────────────────────────────────────
const _expanded = ref(new Set());
const expanded = computed({
  get: () => _expanded.value,
  set: (v) => { _expanded.value = v; }
});

// ── Filtro: exibir apenas linhas irregulares ─────────────────────────────────
const hasIrregular = (section) =>
  (section.subtotal?.vendas_irregular ?? 0) > 0 ||
  section.rows.some(r => r.tipo_linha === 'venda_irregular');

const showOnlyIrregular = ref(true);

// Quando os dados carregam, abre automaticamente os GTINs irregulares
watch(sections, (newSections) => {
  const irregulares = new Set(
    newSections.filter(s => hasIrregular(s)).map(s => s.gtin)
  );
  _expanded.value = irregulares;
}, { immediate: true });

function toggle(gtin) {
  const next = new Set(_expanded.value);
  next.has(gtin) ? next.delete(gtin) : next.add(gtin);
  _expanded.value = next;
}
function expandAll()   { _expanded.value = new Set(sections.value.map(s => s.gtin)); }
function collapseAll() { _expanded.value = new Set(); }

const copyToClipboard = (text) => {
  if (!text) return;
  navigator.clipboard.writeText(text);
};

const splitNotas = (notas) => String(notas || '')
  .split(';')
  .map(nota => nota.trim())
  .filter(Boolean);

const notasPreview = (notas) => {
  const partes = splitNotas(notas);
  if (!partes.length) return '—';
  return partes.length === 1 ? partes[0] : `${partes[0]} (+${partes.length - 1})`;
};

const notasTooltip = (notas) => splitNotas(notas).join('\n') || '—';

// ── Expansão local de linhas (Exibir mais) ───────────────────────────────────
const _rowsExpanded = ref(new Set());
const isRowsExpanded = (gtin) => _rowsExpanded.value.has(gtin);
const toggleRowsExpanded = (gtin) => {
  const next = new Set(_rowsExpanded.value);
  next.has(gtin) ? next.delete(gtin) : next.add(gtin);
  _rowsExpanded.value = next;
};


const filteredRows = (sectionRows) => {
  // Agora não filtramos as linhas individualmente. 
  // O filtro "Apenas Irregulares" agora atua no nível do GRUPO (GTIN).
  return sectionRows;
};

// ── Filtro de Substância Ativa via Tabela de Risco ──────────────────────────
const selectedSubstance = ref(null);

const totalItensGeral = computed(() => {
  return sections.value.reduce((acc, s) => acc + (s.subtotal?.vendas ?? 0), 0);
});

const totalItensIrregulares = computed(() => {
  return sections.value.reduce((acc, s) => acc + (s.subtotal?.vendas_irregular ?? 0), 0);
});

const visibleSections = computed(() => {
  let filtered = sections.value;
  
  if (showOnlyIrregular.value) {
    filtered = filtered.filter(s => hasIrregular(s));
  }
  
  if (selectedSubstance.value) {
    filtered = filtered.filter(s => {
      const rawName = s.medicamento || '';
      const cleanName = rawName.split(/\s\d/)[0].trim();
      return cleanName === selectedSubstance.value;
    });
  }
  
  const query = searchRanking.value.trim().toLowerCase();
  if (query) {
    filtered = filtered.filter(s => {
      const matchName = (s.medicamento || '').toLowerCase().includes(query);
      const matchGtin = String(s.gtin).includes(query);
      return matchName || matchGtin;
    });
  }
  
  // Ordenar sempre do pior GTIN (maior prejuízo) para o menor
  return filtered.sort((a, b) => {
    const valA = a.subtotal?.valor_irregular ?? 0;
    const valB = b.subtotal?.valor_irregular ?? 0;
    return valB - valA;
  });
});

const getVisibleRows = (section) => {
  const fRows = filteredRows(section.rows);
  if (isRowsExpanded(section.gtin)) return fRows;
  return fRows.slice(0, 2);
};

const showMoreRanking = ref(false);
const searchRanking = ref('');

const parseDateSortValue = (value) => {
  if (!value) return null;
  if (value instanceof Date) {
    const time = value.getTime();
    return Number.isNaN(time) ? null : time;
  }

  const text = String(value).trim();
  if (!text || text === '-' || text === '—') return null;

  const brDate = text.match(/^(\d{2})\/(\d{2})\/(\d{4})/);
  if (brDate) {
    const [, day, month, year] = brDate;
    return new Date(Number(year), Number(month) - 1, Number(day)).getTime();
  }

  const isoDate = text.match(/^(\d{4})-(\d{2})-(\d{2})/);
  if (isoDate) {
    const [, year, month, day] = isoDate;
    return new Date(Number(year), Number(month) - 1, Number(day)).getTime();
  }

  const parsed = Date.parse(text);
  return Number.isNaN(parsed) ? null : parsed;
};

const formatPeriodDateLabel = (value) => {
  if (value instanceof Date) {
    const day = String(value.getDate()).padStart(2, '0');
    const month = String(value.getMonth() + 1).padStart(2, '0');
    return `${day}/${month}/${value.getFullYear()}`;
  }
  return String(value);
};

const pickPeriodBoundary = (current, value, direction) => {
  const time = parseDateSortValue(value);
  if (time === null) return current;
  if (!current || (direction === 'min' ? time < current.time : time > current.time)) {
    return { time, label: formatPeriodDateLabel(value) };
  }
  return current;
};

const rankingData = computed(() => {
  const groups = {};
  
  sections.value.forEach(s => {
    const st = s.subtotal;
    if (!st) return;
    
    // Heurística de limpeza: pegar o nome até o primeiro número (dosagem)
    // Se houver um campo substancia no futuro, trocar aqui.
    const rawName = s.medicamento || 'SUBSTÂNCIA NÃO IDENTIFICADA';
    const cleanName = rawName.split(/\s\d/)[0].trim(); 
    
    if (!groups[cleanName]) {
      groups[cleanName] = {
        substancia: cleanName,
        valor_total: 0,
        prejuizo: 0,
        qtd_total: 0,
        qtd_irreg: 0,
        gtins: new Set(),
        gtinRegCount: 0,
        gtinIrrCount: 0,
        firstGtin: s.gtin, // Para o link de scroll (primeiro da lista)
        minStart: null,
        maxEnd: null
      };
    }
    
    const g = groups[cleanName];
    g.valor_total += st.valor;
    g.prejuizo += (st.valor_irregular || 0);
    g.qtd_total += st.vendas;
    g.qtd_irreg += (st.vendas_irregular || 0);
    g.gtins.add(s.gtin);
    
    if (hasIrregular(s)) {
      g.gtinIrrCount++;
    } else {
      g.gtinRegCount++;
    }
    
    const irrRows = s.rows.filter(r => r.tipo_linha === 'venda_irregular');
    irrRows.forEach((row) => {
      g.minStart = pickPeriodBoundary(g.minStart, row.periodo_inicio_irregular, 'min');
      g.maxEnd = pickPeriodBoundary(g.maxEnd, row.periodo_final, 'max');
    });
  });

  return Object.values(groups)
    .map(g => ({
      ...g,
      periodo: (g.minStart && g.maxEnd) ? `${g.minStart.label} a ${g.maxEnd.label}` : '—',
      gtinCount: g.gtins.size,
      ticket: g.qtd_total > 0 ? (g.valor_total / g.qtd_total) : 0,
      peso: (g.prejuizo / (summary.value?.valor_irregular || 1)) * 100
    }))
    .sort((a, b) => b.prejuizo - a.prejuizo);
});

const filteredRankingData = computed(() => {
  const query = searchRanking.value.trim().toLowerCase();
  if (!query) return rankingData.value;
  
  return rankingData.value.filter(item => {
    const matchName = item.substancia.toLowerCase().includes(query);
    const matchGtin = Array.from(item.gtins).some(gtin => String(gtin).includes(query));
    return matchName || matchGtin;
  });
});

const visibleRanking = computed(() => {
  if (showMoreRanking.value) return filteredRankingData.value;
  return filteredRankingData.value.slice(0, 5);
});

const filterBySubstance = (substancia) => {
  if (selectedSubstance.value === substancia) {
    selectedSubstance.value = null; // Remove o filtro
  } else {
    selectedSubstance.value = substancia;
  }
};

const pctIrregular = (section) => {
  const st = section.subtotal;
  if (!st || !st.valor) return 0;
  return ((st.valor_irregular ?? 0) / st.valor * 100);
};


</script>

<template>
  <div class="mov-tab" :class="{ 'is-refreshing': isRefreshing }" :style="dataColorVars">

    <!-- ── ESTADO: Erro ──────────────────────────────────────────────────── -->
    <TabPlaceholder
      v-if="error"
      variant="error"
      icon="pi-exclamation-circle"
      title="Erro ao carregar"
      :description="error"
    />

    <!-- ── ESTADO: Carregamento inicial silencioso ──────────────────────────── -->
    <div
      v-else-if="!loaded && !cachedMovimentacaoData"
      class="mov-initial-loading-sentinel"
      aria-hidden="true"
    />

    <TabPlaceholder
      v-else-if="noMovementInPeriod"
      variant="info"
      icon="pi-chart-bar"
      title="Sem movimentação no período"
    >
      <template #description>
        Não foram encontradas movimentações financeiras para este CNPJ no período de <u>{{ formattedPeriod?.start }}</u> até <u>{{ formattedPeriod?.end }}</u>.
      </template>
    </TabPlaceholder>

    <!-- ── ESTADO: Sem dados ───────────────────────────────────────────────── -->
    <TabPlaceholder
      v-else-if="loaded && !rows.length"
      variant="info"
      icon="pi-chart-bar"
      title="Sem movimentação no período"
    >
      <template #description>
        Não foram encontradas movimentações financeiras para este CNPJ no período de <u>{{ formattedPeriod?.start }}</u> até <u>{{ formattedPeriod?.end }}</u>.
      </template>
    </TabPlaceholder>

    <!-- ── ESTADO: Dados carregados ───────────────────────────────────────── -->
    <template v-else-if="cachedMovimentacaoData && rows.length">


      <!-- Card de Ranking de Substâncias -->
      <div class="mov-ranking-card" v-if="rankingData.length">
        <div class="ranking-header">
          <div class="rh-left">
            <i class="pi pi-chart-bar" />
            <span class="rh-title">Análise de Risco por Princípio Ativo</span>
            <span class="rh-sub">Somatório de valores sem comprovação fiscal</span>
          </div>
          <div class="rh-right">
             <div class="rank-search-wrapper">
                <i class="pi pi-search" />
                <input type="text" v-model="searchRanking" class="rank-search-input" placeholder="Buscar princípio ativo ou GTIN..." />
             </div>
          </div>
        </div>
        
        <div class="ranking-table-wrapper">
          <table class="ranking-table">
            <colgroup>
              <col style="width: 25%;">
              <col style="width: 12%;">
              <col style="width: 12%;">
              <col style="width: 20%;">
              <col style="width: 9%;">
              <col style="width: 17%;">
              <col style="width: 5%;">
            </colgroup>
            <thead>
              <tr>
                  <th>Princípio Ativo</th>
                  <th>Período sem Comprovação</th>
                  <th class="text-right">Caixas Vendidas (Total/Irregular)</th>
                  <th class="text-right">Valor (Total/Irregular)</th>
                  <th class="text-right">Ticket Médio</th>
                  <th class="text-right" v-tooltip.top="'Percentual que o valor não comprovado desta substância representa em relação ao valor total sem comprovação de todos os itens do CNPJ.'">
                    Representatividade
                  </th>
                  <th class="text-center">Detalhes</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="item in visibleRanking" :key="item.substancia" :class="{'active-row': selectedSubstance === item.substancia}">
                <td>
                  <div class="rank-med-cell">
                    <span class="rank-nome">{{ item.substancia }}</span>
                    <span class="rank-gtin">
                      {{ item.gtinCount }} {{ item.gtinCount > 1 ? 'GTINs' : 'GTIN' }}
                      <span v-if="item.gtinCount > 0" class="rank-gtin-split" style="margin-left: 3px; opacity: 0.9; font-weight: 600; font-size: 0.65rem;">
                        (<span style="color: color-mix(in srgb, var(--primary-color) 80%, black);" v-tooltip.top="'GTINs 100% regulares'">{{ item.gtinRegCount }}</span> / <span style="color: var(--risk-high);" v-tooltip.top="'GTINs com irregularidades'">{{ item.gtinIrrCount }}</span>)
                      </span>
                    </span>
                  </div>
                </td>
                <td class="rank-periodo">{{ item.periodo }}</td>
                <td class="text-right">
                  <span class="r-val-tot">{{ item.qtd_total }}</span> 
                  <span class="r-sep">/</span> 
                  <span class="r-val-irreg">{{ item.qtd_irreg }}</span>
                </td>
                <td class="text-right">
                  <span class="r-val-tot">{{ fmt(item.valor_total) }}</span>
                  <span class="r-sep">/</span>
                  <span class="r-val-irreg">{{ fmt(item.prejuizo) }}</span>
                </td>
                <td class="text-right">{{ fmt(item.ticket) }}</td>
                <td class="text-right">
                  <div class="rank-peso-container">
                    <div class="rank-peso-track">
                      <div class="rank-peso-bar" :style="{ width: item.peso + '%' }"></div>
                    </div>
                    <span class="rank-peso-txt">{{ item.peso.toFixed(1) }}%</span>
                  </div>
                </td>
                <td class="text-center">
                  <button class="rank-goto-btn" :class="{ 'is-active': selectedSubstance === item.substancia }" @click="filterBySubstance(item.substancia)" v-tooltip.top="selectedSubstance === item.substancia ? 'Remover filtro e mostrar todos' : 'Filtrar GTINs desta substância'">
                    <i :class="selectedSubstance === item.substancia ? 'pi pi-filter-slash' : 'pi pi-filter'" />
                  </button>
                </td>
              </tr>
              <!-- Linhas vazias de preenchimento para evitar Layout Shift -->
              <tr v-for="i in Math.max(0, (!showMoreRanking ? 5 : 0) - visibleRanking.length)" :key="'empty-' + i" class="empty-rank-row">
                <td>
                  <div class="rank-med-cell">
                    <span class="rank-nome">&nbsp;</span>
                    <span class="rank-gtin">&nbsp;</span>
                  </div>
                </td>
                <td></td><td></td><td></td><td></td><td></td><td></td>
              </tr>
            </tbody>
            <tfoot>
              <tr>
                <td>{{ searchRanking ? 'TOTAL (FILTRADO)' : 'TOTAL GERAL' }}</td>
                <td></td>
                <td class="text-right">
                  <span class="r-val-tot">{{ searchRanking ? filteredRankingData.reduce((a, item) => a + item.qtd_total, 0).toLocaleString('pt-BR') : totalItensGeral.toLocaleString('pt-BR') }}</span> 
                  <span class="r-sep">/</span> 
                  <span class="r-val-irreg">{{ searchRanking ? filteredRankingData.reduce((a, item) => a + item.qtd_irreg, 0).toLocaleString('pt-BR') : totalItensIrregulares.toLocaleString('pt-BR') }}</span>
                </td>
                <td class="text-right">
                  <span class="r-val-tot">{{ searchRanking ? fmt(filteredRankingData.reduce((a, item) => a + item.valor_total, 0)) : fmt(summary?.valor_total) }}</span>
                  <span class="r-sep">/</span>
                  <span class="r-val-irreg">{{ searchRanking ? fmt(filteredRankingData.reduce((a, item) => a + item.prejuizo, 0)) : fmt(summary?.valor_irregular) }}</span>
                </td>
                <td class="text-right">{{ searchRanking ? fmt((filteredRankingData.reduce((a, item) => a + item.valor_total, 0) / (filteredRankingData.reduce((a, item) => a + item.qtd_total, 0) || 1))) : fmt((summary?.valor_total / (totalItensGeral || 1)) || 0) }}</td>
                <td class="text-right"><span class="rank-peso-txt">100.0%</span></td>
                <td></td>
              </tr>
            </tfoot>
          </table>
        </div>

        <div class="ranking-footer">
          <button class="ranking-more-btn" :style="{ visibility: filteredRankingData.length > 5 ? 'visible' : 'hidden' }" @click="showMoreRanking = !showMoreRanking">
            {{ showMoreRanking ? 'Recolher Ranking' : (searchRanking ? `Ver todos os ${filteredRankingData.length} resultados` : `Ver todos os ${filteredRankingData.length} medicamentos críticos`) }}
            <i class="pi" :class="showMoreRanking ? 'pi-angle-up' : 'pi-angle-down'" />
          </button>
        </div>
      </div>

      <!-- Card Mestre de Detalhamento -->
      <div class="mov-main-card" id="detalhamento-card">
        <div class="main-card-header">
          <div class="mch-left">
            <i class="pi pi-list" />
            <span class="mch-title">Detalhamento por GTIN</span>
            <div class="mch-filter-tag" :class="{'is-empty': visibleSections.length === 0}" v-if="selectedSubstance || searchRanking.trim()">
              <span v-if="selectedSubstance">Filtrado: {{ visibleSections.length }} itens de <strong>{{ selectedSubstance }}</strong></span>
              <span v-else>Filtrado: <strong>{{ searchRanking }}</strong> ({{ visibleSections.length }} itens)</span>
              <button class="clear-filter-btn" @click="() => { selectedSubstance = null; searchRanking = '' }" v-tooltip.top="'Limpar filtros e exibir tudo'">
                <i class="pi pi-times" />
              </button>
            </div>
            <span class="mch-count" v-else>{{ visibleSections.length }} de {{ sections.length }} itens</span>
          </div>
          
          <div class="mch-actions">
            <button class="tb-btn" :class="{ 'tb-btn-active': showOnlyIrregular }" @click="showOnlyIrregular = !showOnlyIrregular" v-tooltip.top="'Exibe o histórico completo apenas de medicamentos com irregularidades'">
              <i :class="showOnlyIrregular ? 'pi pi-filter-fill' : 'pi pi-filter'" />
              {{ showOnlyIrregular ? 'Exibir Irregulares' : 'Todos' }}
            </button>
            <div class="mch-divider" />
            <button class="tb-btn" @click="expandAll" v-tooltip.top="'Expandir todos os medicamentos'"><i class="pi pi-plus-circle" /></button>
            <button class="tb-btn" @click="collapseAll" v-tooltip.top="'Recolher todos'"><i class="pi pi-minus-circle" /></button>
          </div>
        </div>

        <div class="mov-body">
          <div v-for="section in visibleSections" :key="section.gtin" :id="'gtin-' + section.gtin" class="gtin-accordion" :class="{ 'is-expanded': expanded.has(section.gtin), 'has-irregular': hasIrregular(section) }">

          <button class="gtin-header" @click="toggle(section.gtin)">
            <i class="pi header-chevron" :class="expanded.has(section.gtin) ? 'pi-chevron-down' : 'pi-chevron-right'" />
            <span class="gtin-badge" @click.stop="copyToClipboard(section.gtin)" v-tooltip.top="'Clique para copiar o GTIN'">
              {{ section.gtin }}
              <i class="pi pi-copy gtin-copy-icon" />
            </span>
            <span class="gtin-nome">{{ section.medicamento }}</span>
            <div class="header-kpis" @click.stop>
              <span class="hk-item">
                <span class="hk-label">Sem Comprovação</span>
                <span class="hk-val" :class="(section.subtotal?.valor_irregular ?? 0) > 0 ? 'hk-irreg' : ''">{{ fmt(section.subtotal?.valor_irregular) }}</span>
              </span>
              <span v-if="hasIrregular(section)" class="hk-badge-irreg">{{ fmtPct(pctIrregular(section)) }} irreg.</span>
              <span v-else class="hk-badge-ok">Regular</span>
            </div>
          </button>

          <div class="gtin-content" v-show="expanded.has(section.gtin)">
            <div class="gtin-col-headers">
              <div class="gcol gcol-date">1ª Venda</div>
              <div class="gcol gcol-date">Início Irreg.</div>
              <div class="gcol gcol-date">Última Venda</div>
              <div class="gcol gcol-num">Est. Ini.</div>
              <div class="gcol gcol-num">Est. Fin.</div>
              <div class="gcol gcol-num">Caixas Vendidas (Tot/Irr)</div>
              <div class="gcol gcol-cur">Valor (Tot/Irr)</div>
              <div class="gcol gcol-nf">Notas Fiscais</div>
            </div>

            <div v-for="(row, ri) in getVisibleRows(section)" :key="ri" class="gtin-row" :class="{ 'row-irregular': row.tipo_linha === 'venda_irregular', 'row-normal': row.tipo_linha === 'venda_normal' }">
              <div class="gcol gcol-date">{{ row.periodo_inicial ?? '—' }}</div>
              <div class="gcol gcol-date">{{ row.periodo_inicio_irregular ?? '—' }}</div>
              <div class="gcol gcol-date">{{ row.periodo_final ?? '—' }}</div>
              <div class="gcol gcol-num">{{ row.estoque_inicial?.toLocaleString('pt-BR') ?? '—' }}</div>
              <div class="gcol gcol-num">{{ row.estoque_final?.toLocaleString('pt-BR') ?? '—' }}</div>
              <div class="gcol gcol-num">
                <span class="r-val-tot">{{ row.vendas?.toLocaleString('pt-BR') ?? '—' }}</span>
                <span class="r-sep">/</span>
                <span :class="(row.vendas_irregular ?? 0) > 0 ? 'cell-irreg-num' : ''">{{ row.vendas_irregular?.toLocaleString('pt-BR') ?? '—' }}</span>
              </div>
              <div class="gcol gcol-cur">
                <span class="r-val-tot">{{ fmt(row.valor) }}</span>
                <span class="r-sep">/</span>
                <span :class="(row.valor_irregular ?? 0) > 0 ? 'cell-irreg-cur' : ''">{{ fmt(row.valor_irregular) }}</span>
              </div>
              <div class="gcol gcol-nf" v-tooltip.top="notasTooltip(row.notas)"><span class="nf-text">{{ notasPreview(row.notas) }}</span></div>
            </div>

            <div v-if="section.subtotal" class="gtin-subtotal">
              <div class="gcol gcol-date sub-label">Resumo Parcial</div>
              <div class="gcol gcol-date"></div><div class="gcol gcol-date"></div><div class="gcol gcol-num"></div>
              <div class="gcol gcol-num">{{ section.subtotal.estoque_final?.toLocaleString('pt-BR') ?? '—' }}</div>
              <div class="gcol gcol-num">
                <span class="r-val-tot">{{ section.subtotal.vendas?.toLocaleString('pt-BR') ?? '—' }}</span>
                <span class="r-sep">/</span>
                <span :class="(section.subtotal.vendas_irregular ?? 0) > 0 ? 'cell-irreg-num' : ''">{{ section.subtotal.vendas_irregular?.toLocaleString('pt-BR') ?? '—' }}</span>
              </div>
              <div class="gcol gcol-cur">
                <span class="r-val-tot">{{ fmt(section.subtotal.valor) }}</span>
                <span class="r-sep">/</span>
                <span :class="(section.subtotal.valor_irregular ?? 0) > 0 ? 'cell-irreg-cur' : ''">{{ fmt(section.subtotal.valor_irregular) }}</span>
              </div>
              <div class="gcol gcol-nf"></div>
            </div>

            <!-- Botão Exibir Mais / Recolher (Movido para DEPOIS do footer do gtin-subtotal) -->
            <div v-if="filteredRows(section.rows).length > 2" class="rows-pagination-row">
              <button class="rows-pagination-btn" @click="toggleRowsExpanded(section.gtin)">
                <template v-if="!isRowsExpanded(section.gtin)">
                  <i class="pi pi-angle-double-down" /> 
                  Exibir mais {{ filteredRows(section.rows).length - 2 }} registros
                </template>
                <template v-else>
                  <i class="pi pi-angle-double-up" /> 
                  Recolher registros
                </template>
              </button>
            </div>
          </div>
        </div>

        <div class="gtin-grand-total" v-if="summary">
          <span class="grand-label">TOTAL GERAL</span>
          <span class="grand-sep">—</span>
          <span class="grand-item"><span class="grand-sub">Total:</span><span class="grand-val">{{ fmt(summary.valor_total) }}</span></span>
          <span class="grand-sep">|</span>
          <span class="grand-item"><span class="grand-sub">Sem Comprovação:</span><span class="grand-val grand-irreg">{{ fmt(summary.valor_irregular) }}</span></span>
          <span class="grand-sep">|</span>
          <span class="grand-item"><span class="grand-sub">%:</span><span class="grand-val" :class="summary.pct_irregular > 0 ? 'grand-irreg' : ''">{{ fmtPct(summary.pct_irregular) }}</span></span>
        </div>
      </div>
    </div>
  </template>
</div>
</template>

<style scoped>
.mov-tab { padding: 0; display: flex; flex-direction: column; gap: 1.5rem; min-height: 300px; }
.mov-tab.is-refreshing {
  opacity: 0.6;
  pointer-events: none;
  transition: opacity 0.2s ease;
}

/* ── MAIN CARD & TOOLBAR REESTRUTURADA ─────────────────────────────────── */
.mov-main-card {
  background: var(--card-bg);
  border: 1px solid var(--card-border);
  border-radius: 12px;
  overflow: hidden;
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.05);
}

.main-card-header {
  padding: 0.85rem 1.25rem 0.75rem;
  border-bottom: 1px solid var(--tabs-border);
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.mch-left { display: flex; align-items: center; gap: 0.75rem; }
.mch-left i { font-size: 1rem; color: var(--primary-color); }
.mch-title { 
  font-size: 0.85rem; 
  font-weight: 600; 
  color: var(--text-color-85); 
  text-transform: uppercase; 
  letter-spacing: 0.04em; 
  opacity: 0.85;
}
.mch-count { font-size: 0.75rem; color: var(--text-muted); font-weight: 600; margin-left: 0.5rem; }

.mch-filter-tag {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  background: color-mix(in srgb, var(--primary-color) 12%, var(--card-bg));
  border: 1px solid color-mix(in srgb, var(--primary-color) 30%, transparent);
  padding: 0.15rem 0.5rem 0.15rem 0.6rem;
  border-radius: 12px;
  margin-left: 0.5rem;
  font-size: 0.7rem;
  font-weight: 500;
  color: var(--text-primary);
}
.mch-filter-tag strong { font-weight: 700; color: var(--primary-color); }


.clear-filter-btn {
  background: none;
  border: none;
  color: color-mix(in srgb, var(--primary-color) 80%, transparent);
  cursor: pointer;
  padding: 0.2rem;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  transition: all 0.2s;
}
.clear-filter-btn:hover { background: color-mix(in srgb, var(--primary-color) 20%, transparent); color: var(--primary-color); transform: scale(1.1); }

/* Variação visual para Filtro Vazio (Avisar o Usuário) */
.mch-filter-tag.is-empty {
  background: color-mix(in srgb, var(--risk-high) 10%, var(--card-bg)) !important;
  border-color: color-mix(in srgb, var(--risk-high) 30%, transparent) !important;
  color: var(--risk-high) !important;
}
.mch-filter-tag.is-empty strong { color: var(--risk-high) !important; }
.mch-filter-tag.is-empty .clear-filter-btn,
.mch-filter-tag.is-empty .clear-filter-btn i {
  color: color-mix(in srgb, var(--risk-high) 80%, transparent) !important;
}
.mch-filter-tag.is-empty .clear-filter-btn:hover,
.mch-filter-tag.is-empty .clear-filter-btn:hover i {
  background: color-mix(in srgb, var(--risk-high) 15%, transparent) !important;
  color: var(--risk-high) !important;
}

.mch-actions { display: flex; align-items: center; gap: 0.6rem; }
.mch-divider { width: 1px; height: 16px; background: var(--tabs-border); margin: 0 0.2rem; }

.tb-btn {
  background: color-mix(in srgb, var(--text-color-85) 4%, var(--card-bg));
  border: 1px solid var(--card-border);
  color: var(--text-secondary);
  padding: 0.4rem 0.8rem;
  border-radius: 6px;
  font-size: 0.68rem;
  font-weight: 700;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 0.4rem;
  transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
  white-space: nowrap;
}
.tb-btn:hover { 
  background: color-mix(in srgb, var(--primary-color) 8%, var(--card-bg)); 
  border-color: color-mix(in srgb, var(--primary-color) 30%, transparent); 
  color: var(--primary-color);
  transform: translateY(-1px);
}
.tb-btn-active {
  background: color-mix(in srgb, var(--primary-color) 12%, var(--card-bg)) !important;
  border-color: var(--primary-color) !important;
  color: var(--primary-color) !important;
  box-shadow: 0 0 12px -2px color-mix(in srgb, var(--primary-color) 25%, transparent);
}
.tb-btn:active { transform: scale(0.96); }
.mov-body { 
  padding: 1.2rem; 
  display: flex; 
  flex-direction: column; 
  gap: 1rem; 
  min-height: 50vh;
}
.gtin-accordion { 
  border: 1px solid var(--card-border); 
  border-radius: 12px; 
  overflow: hidden; 
  background: var(--card-bg); 
  transition: border-color 0.2s, box-shadow 0.2s; 
}
.gtin-accordion.has-irregular { border-left: 3px solid color-mix(in srgb, var(--risk-high) 60%, transparent); }
.gtin-header { width: 100%; display: flex; align-items: center; gap: 0.65rem; padding: 0.6rem 0.9rem; background: none; border: none; cursor: pointer; text-align: left; color: inherit; transition: background 0.15s; min-height: 46px; }
.gtin-header:hover { background: color-mix(in srgb, var(--text-color-85) 2%, var(--card-bg)); }
.is-expanded .gtin-header { background: var(--card-bg); border-bottom: 1px solid var(--card-border); }
.header-chevron { font-size: 0.7rem; color: var(--text-muted); flex-shrink: 0; transition: transform 0.2s; }
.gtin-badge { 
  display: inline-flex; 
  align-items: center; 
  padding: 0.2rem 0.6rem; 
  border-radius: 4px; 
  background: transparent; 
  color: var(--text-muted); 
  border: 1px solid var(--card-border);
  font-size: 0.82rem; 
  font-weight: 700; 
  letter-spacing: 0.08em; 
  white-space: nowrap; 
  flex-shrink: 0; 
  opacity: 0.85;
  cursor: copy;
  transition: all 0.2s;
}
.gtin-badge:hover {
  background: color-mix(in srgb, var(--primary-color) 6%, transparent);
  border-color: var(--primary-color);
  color: var(--primary-color);
  opacity: 1;
}
.gtin-copy-icon {
  font-size: 0.65rem;
  margin-left: 0.5rem;
  opacity: 0.5;
}
.gtin-nome { font-size: 0.76rem; font-weight: 600; color: var(--text-primary); flex: 1; text-overflow: ellipsis; overflow: hidden; white-space: nowrap; }
.header-kpis { display: flex; align-items: center; gap: 0.5rem; margin-left: auto; flex-shrink: 0; }
.hk-item { display: flex; flex-direction: column; align-items: flex-end; }
.hk-label { font-size: 0.65rem; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.04em; line-height: 1; }
.hk-val { font-size: 0.8rem; font-weight: 600; color: var(--text-primary); white-space: nowrap; }
.hk-irreg { color: var(--text-primary); }
.hk-badge-irreg { padding: 0.15rem 0.55rem; border-radius: 20px; font-size: 0.7rem; font-weight: 700; background: color-mix(in srgb, var(--risk-high) 12%, transparent); color: color-mix(in srgb, var(--risk-high) 80%, transparent); border: 1px solid color-mix(in srgb, var(--risk-high) 25%, transparent); }
.hk-badge-ok { padding: 0.15rem 0.55rem; border-radius: 20px; font-size: 0.7rem; font-weight: 700; background: color-mix(in srgb, #22c55e 10%, transparent); color: #16a34a; border: 1px solid color-mix(in srgb, #22c55e 25%, transparent); }
.gtin-content { overflow-x: auto; }
.gtin-col-headers, .gtin-row, .gtin-subtotal { display: grid; grid-template-columns: 1.1fr 1.1fr 1.1fr 0.9fr 0.9fr 1.6fr 2fr 3.5fr; min-width: 700px; align-items: center; }
.gtin-col-headers { background: var(--card-bg); border-bottom: 1px solid var(--card-border); }
.gcol { padding: 0.38rem 0.55rem; font-size: 0.8rem; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; border-right: 1px solid color-mix(in srgb, var(--card-border) 45%, transparent); }
.gtin-col-headers .gcol { font-weight: 500; text-transform: uppercase; letter-spacing: 0.04em; font-size: 0.72rem; color: var(--text-secondary); opacity: 0.9; }
.gcol-num, .gcol-cur { text-align: right; }
.gcol-irreg-hdr { color: var(--risk-high) !important; font-weight: 600 !important; }
.gtin-row { border-bottom: 1px solid color-mix(in srgb, var(--card-border) 50%, transparent); transition: background 0.12s; }
.row-normal:hover { background: color-mix(in srgb, var(--text-color-85) 3%, var(--card-bg)); }
.row-irregular { background: color-mix(in srgb, var(--risk-high) 8%, var(--card-bg)); }
.cell-irreg-date, .cell-irreg-num, .cell-irreg-cur { color: var(--text-primary); font-weight: 600; }
.nf-text { font-size: 0.76rem; color: var(--text-muted); display: block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 100%; }
.gtin-subtotal { background: var(--card-bg); border-top: 1px dashed color-mix(in srgb, var(--primary-color) 40%, transparent); }
.gtin-subtotal .gcol { font-size: 0.82rem; font-weight: 500; color: var(--text-secondary); padding: 0.45rem 0.55rem; }
.sub-label { font-weight: 500; opacity: 1; font-size: 0.75rem !important; text-transform: uppercase; letter-spacing: 0.03em; color: var(--text-secondary); }
.gtin-grand-total { 
  display: flex; 
  align-items: center; 
  flex-wrap: wrap; 
  gap: 0.6rem; 
  padding: 0.85rem 1.2rem; 
  background: color-mix(in srgb, var(--text-color-85) 3%, var(--card-bg)); 
  border: 1px solid var(--card-border); 
  border-radius: 12px; 
  font-size: 0.78rem; 
}
.grand-label { font-weight: 500; font-size: 0.7rem; text-transform: uppercase; letter-spacing: 0.06em; color: var(--text-primary); }
.grand-sep { color: var(--text-muted); opacity: 0.4; }
.grand-item { display: flex; align-items: center; gap: 0.35rem; }
.grand-sub { font-size: 0.66rem; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.03em; }
.grand-val { font-weight: 500; color: var(--text-primary); }
.grand-irreg { color: var(--risk-high) !important; font-weight: 600; }

.rows-pagination-row {
  background: var(--card-bg);
  border-bottom: 1px solid color-mix(in srgb, var(--card-border) 60%, transparent);
  display: flex;
  justify-content: center;
  padding: 0.35rem 0;
}
.rows-pagination-btn {
  background: none;
  border: none;
  font-size: 0.65rem;
  font-weight: 500;
  color: var(--primary-color);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 0.4rem;
  padding: 0.2rem 1rem;
  border-radius: 4px;
  transition: all 0.2s;
  opacity: 0.85;
}
.rows-pagination-btn:hover {
  opacity: 1;
  background: color-mix(in srgb, var(--primary-color) 8%, transparent);
  letter-spacing: 0.08em;
}
.rows-pagination-btn i {
  font-size: 0.7rem;
}

/* ── ESTILOS DO RANKING ─────────────────────────────────────────────────── */
.rank-peso-txt { font-size: 0.65rem; color: var(--text-muted); min-width: 32px; font-weight: 500;}

.empty-rank-row { pointer-events: none; }

/* ── BOTÕES ────────────────────────────────────────────────────────────── */
.mov-stats-grid { display: flex; flex-direction: column; gap: 1.5rem; }

.mov-ranking-card {
  background: var(--card-bg);
  border: 1px solid var(--card-border);
  border-radius: 12px;
  overflow: hidden;
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.05);
}
.ranking-header {
  padding: 0.85rem 1.25rem;
  border-bottom: 1px solid var(--card-border);
  display: flex;
  align-items: center;
  gap: 0.75rem;
}
.rh-left { display: flex; align-items: center; gap: 0.5rem; flex-wrap: wrap; }
.rh-right {
  display: flex;
  align-items: center;
  gap: 1.25rem;
  margin-left: auto;
}

.rank-search-wrapper {
  position: relative;
  display: flex;
  align-items: center;
}
.rank-search-wrapper i {
  position: absolute;
  left: 0.85rem;
  top: 50%;
  transform: translateY(-50%);
  color: var(--text-muted);
  opacity: 0.7;
  font-size: 0.95rem;
  pointer-events: none;
}
.rank-search-input {
  background: color-mix(in srgb, var(--card-bg) 95%, var(--text-color-85));
  border: 1px solid color-mix(in srgb, var(--card-border) 80%, transparent);
  color: var(--text-primary);
  border-radius: 20px;
  padding: 0.5rem 1rem 0.5rem 2.4rem;
  font-size: 0.8rem;
  width: 280px;
  transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
  font-family: inherit;
  outline: none;
}
.rank-search-input:focus {
  border-color: var(--primary-color);
  box-shadow: 0 0 0 1px var(--primary-color), 0 4px 12px rgba(0,0,0,0.05);
  background: var(--card-bg);
  width: 320px;
}
.rh-left i { font-size: 1rem; color: var(--primary-color); }
.rh-title { 
  font-size: 0.85rem; 
  font-weight: 600; 
  color: var(--text-color-85); 
  text-transform: uppercase; 
  letter-spacing: 0.04em; 
  opacity: 0.85;
}
.rh-sub { font-size: 0.75rem; color: var(--text-muted); font-weight: 400; margin-left: 0.5rem; text-transform: none; letter-spacing: normal; }

.ranking-table-wrapper { overflow-x: auto; padding: 1.25rem 1.25rem 0.5rem; }
.ranking-table { width: 100%; border-collapse: collapse; }
.ranking-table th { 
  background: var(--sidebar-heading-tint); /* mesmo fundo do cabeçalho "Análises" da sidebar de /analises */
  padding: 0.75rem 0.5rem; 
  font-size: 0.72rem; 
  font-weight: 600;
  text-transform: uppercase; 
  letter-spacing: 0.05em;
  color: var(--text-secondary); 
  text-align: left; 
  border-bottom: 1px solid var(--card-border); /* mesma borda do cabeçalho "Análises" */
  opacity: 0.85;
}
.ranking-table td { 
  padding: 0.65rem 1rem; 
  font-size: 0.75rem; 
  color: var(--text-secondary);
  border-bottom: 1px solid var(--tabs-border); 
}
.ranking-table tfoot td { 
  border-top: 2px solid var(--tabs-border); 
  border-bottom: none; 
  background: color-mix(in srgb, var(--text-color-85) 3%, var(--card-bg)); 
  font-weight: 700;
  color: var(--text-primary);
}
.ranking-table tr.active-row {
  background: color-mix(in srgb, var(--text-color-85) 3%, var(--card-bg));
}
.ranking-table tr.active-row td {
  border-bottom: 1px solid color-mix(in srgb, var(--text-color-85) 10%, var(--tabs-border));
}
.ranking-table .text-right { text-align: right !important; }
.ranking-table .text-center { text-align: center !important; }

.rank-med-cell { display: flex; flex-direction: column; gap: 0.1rem; overflow: hidden; }
.rank-gtin { font-size: 0.72rem; color: var(--text-muted); font-weight: 600; }
.rank-nome { font-size: 0.82rem; font-weight: 600; color: var(--text-primary); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.rank-periodo { font-size: 0.68rem; color: var(--text-secondary); }
.rank-prejuizo { color: var(--text-primary); font-weight: 600; font-variant-numeric: tabular-nums; }
.r-val-tot { color: var(--text-muted); }
.r-sep { margin: 0 0.2rem; opacity: 0.3; }
.r-val-irreg { font-weight: 600; color: var(--text-primary); }

.rank-peso-container { display: flex; align-items: center; gap: 0.6rem; }
.rank-peso-track { flex: 1; height: 5px; background: color-mix(in srgb, var(--card-border) 80%, transparent); border-radius: 4px; overflow: hidden; }
.rank-peso-bar { height: 100%; background: var(--data-color); border-radius: 4px; transition: width 0.3s ease; }
.rank-peso-txt { font-size: 0.75rem; font-weight: 700; color: var(--text-secondary); min-width: 42px; text-align: right; }

.rank-goto-btn { 
  background: color-mix(in srgb, var(--text-color-85) 5%, var(--card-bg)); 
  border: 1px solid color-mix(in srgb, var(--text-color-85) 15%, transparent); 
  color: color-mix(in srgb, var(--text-color-85) 70%, transparent); 
  width: 26px; 
  height: 26px; 
  border-radius: 6px; 
  cursor: pointer; 
  display: inline-flex; 
  align-items: center; 
  justify-content: center; 
  transition: all 0.2s; 
}
.rank-goto-btn:hover { background: color-mix(in srgb, var(--primary-color) 10%, transparent); color: var(--primary-color); border-color: color-mix(in srgb, var(--primary-color) 30%, transparent); }
.rank-goto-btn.is-active { background: var(--primary-color) !important; color: var(--card-bg) !important; border-color: var(--primary-color) !important; }

.ranking-footer { padding: 0.7rem; display: flex; justify-content: center; background: color-mix(in srgb, var(--text-color-85) 1%, var(--card-bg)); }
.ranking-more-btn { 
  background: none; 
  border: none; 
  color: color-mix(in srgb, var(--text-color-85) 60%, transparent); 
  font-size: 0.68rem; 
  font-weight: 500; 
  text-transform: uppercase; 
  display: flex; 
  align-items: center; 
  gap: 0.5rem; 
  cursor: pointer;
  padding: 0.3rem 1.5rem;
  border-radius: 20px;
  transition: all 0.2s;
}
.ranking-more-btn:hover { color: var(--primary-color); background: color-mix(in srgb, var(--primary-color) 5%, transparent); letter-spacing: 0.02em; }

@media (max-width: 1200px) {
  .ranking-table th:nth-child(2), .ranking-table td:nth-child(2) { display: none; }
  .ranking-table th:nth-child(3), .ranking-table td:nth-child(3) { display: none; }
}
</style>
