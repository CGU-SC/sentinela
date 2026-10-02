<script setup>
import { computed, ref } from 'vue';
import Dialog from 'primevue/dialog';
import { use } from 'echarts/core';
import { CanvasRenderer } from 'echarts/renderers';
import { BarChart, LineChart, ScatterChart } from 'echarts/charts';
import {
  GridComponent,
  LegendComponent,
  MarkLineComponent,
  TooltipComponent,
} from 'echarts/components';
import VChart from 'vue-echarts';
import { useFormatting } from '@/composables/useFormatting';
import { useChartTheme } from '@/config/chartTheme';
import { useThemeStore } from '@/stores/theme';
import { CRM_TAXA_P95_TONS, DATA_NEUTRAL } from '@/config/colors';
import { crmFaixaP95 } from '@/config/analysisTooltipConfig';

use([CanvasRenderer, BarChart, LineChart, ScatterChart, GridComponent, LegendComponent, TooltipComponent, MarkLineComponent]);

/**
 * Detalhe mensal da atuação de um CRM na farmácia: taxa diária do CRM na
 * farmácia (padrão) ou volume/valor, participação no movimento mensal da
 * farmácia, P95 nacional do mês, meses com alertas e 1ª inscrição no CFM.
 * A cor da barra é sempre a faixa do ×P95 do mês (mesma regra da linha do
 * tempo de /analises); meses com alerta ganham um marcador acima da barra.
 */
const props = defineProps({
  modelValue: { type: Boolean, default: false },
  medico: { type: Object, default: null },
  cnpj: { type: String, required: true },
  periodo: { type: Object, default: null },
  serieFarmacia: { type: Array, default: () => [] },
});
const emit = defineEmits(['update:modelValue']);

const themeStore = useThemeStore();
const { formatCurrencyFull, formatNumberFull, formatTitleCase, formatarData } = useFormatting();
const { chartTheme } = useChartTheme();

const COR_INSCRICAO = '#f59e0b';
const tema = computed(() => (themeStore.isDark ? 'dark' : 'light'));
const coresDados = computed(() => DATA_NEUTRAL[tema.value]);
const tonsP95 = computed(() => CRM_TAXA_P95_TONS[tema.value]);

const METRICAS = Object.freeze({
  taxa: { serie: 'Taxa diária do CRM', botao: 'Taxa diária' },
  qtd: { serie: 'Autorizações do CRM', botao: 'Autorizações' },
  valor: { serie: 'Valor do CRM', botao: 'Valor (R$)' },
});
const metrica = ref('taxa');

function competenciaToIndex(comp) {
  return Math.floor(comp / 100) * 12 + (comp % 100) - 1;
}
function indexToCompetencia(idx) {
  return Math.floor(idx / 12) * 100 + (idx % 12) + 1;
}
function formatCompetencia(comp) {
  return `${String(comp % 100).padStart(2, '0')}/${Math.floor(comp / 100)}`;
}
function competenciaDeData(value) {
  const text = String(value ?? '');
  const match = text.match(/^(\d{4})-(\d{2})/) || text.match(/^\d{2}\/(\d{2})\/(\d{4})/);
  if (!match) return null;
  return text.includes('/') ? Number(match[2]) * 100 + Number(match[1]) : Number(match[1]) * 100 + Number(match[2]);
}

const meses = computed(() => {
  if (!props.periodo || !props.medico) return [];
  const inicio = competenciaToIndex(props.periodo.inicio);
  const fim = competenciaToIndex(props.periodo.fim);
  const serieCrm = new Map(props.medico.serie_mensal_atuacao.map(p => [Number(p.competencia), p]));
  const serieFarm = new Map(props.serieFarmacia.map(p => [Number(p.competencia), p]));
  const lista = [];
  for (let idx = inicio; idx <= fim; idx += 1) {
    const comp = indexToCompetencia(idx);
    const crm = serieCrm.get(comp);
    const farm = serieFarm.get(comp);
    if (crm && !(Number(crm.dias) > 0 && Number(crm.p95_taxa_dia) > 0)) {
      throw new Error(`Contrato inválido na atuação do CRM: mês ${comp} sem dias ou P95.`);
    }
    lista.push({
      comp,
      label: formatCompetencia(comp),
      ativo: Boolean(crm),
      dias: crm ? Number(crm.dias) : 0,
      taxa: crm ? Number(crm.taxa_prescricoes_dia) : 0,
      p95: crm ? Number(crm.p95_taxa_dia) : null,
      razao: crm ? Number(crm.razao_p95) : null,
      faixa: crm ? crmFaixaP95(crm) : null,
      qtd: crm ? Number(crm.qtd) : 0,
      valor: crm ? Number(crm.valor) : 0,
      qtdBrasil: crm ? Number(crm.qtd_brasil) : 0,
      farmQtd: farm ? Number(farm.qtd) : 0,
      farmValor: farm ? Number(farm.valor) : 0,
    });
  }
  return lista;
});

// Tipos de alerta de cada mês nesta farmácia (vêm na própria série mensal).
const alertasPorMes = computed(() => {
  const mapa = new Map();
  for (const p of props.medico?.serie_mensal_atuacao ?? []) {
    const tipos = {
      unico: Boolean(p.alerta_sequencia_unico),
      multi: Boolean(p.alerta_sequencia_multiplos),
      geo: Boolean(p.alerta_distancia),
    };
    if (tipos.unico || tipos.multi || tipos.geo) mapa.set(Number(p.competencia), tipos);
  }
  return mapa;
});

const kpis = computed(() => {
  const m = props.medico;
  if (!m) return [];
  const ativos = meses.value.filter(x => x.qtd > 0);
  const pico = ativos.reduce((max, x) => (x.qtd > (max?.qtd ?? -1) ? x : max), null);
  const totalQtd = ativos.reduce((acc, x) => acc + x.qtd, 0);
  const inicio = Number(m.competencia_inicio_atuacao);
  const fim = Number(m.competencia_fim_atuacao);
  return [
    { label: 'Período de atuação', value: inicio === fim ? formatCompetencia(inicio) : `${formatCompetencia(inicio)} – ${formatCompetencia(fim)}` },
    { label: 'Meses com movimento', value: formatNumberFull(Number(m.qtd_meses_atuacao)) },
    { label: 'Mês de pico', value: pico ? `${pico.label} · ${formatNumberFull(pico.qtd)} autorizações` : '—' },
    { label: 'Média nos meses ativos', value: ativos.length ? `${formatNumberFull(Math.round(totalQtd / ativos.length))} autorizações` : '—' },
    { label: 'Meses com taxa elevada', value: `${formatNumberFull(ativos.filter(x => x.faixa).length)} de ${formatNumberFull(ativos.length)}` },
    { label: 'Valor total', value: formatCurrencyFull(m.vl_total_prescricoes) },
  ];
});

const titulo = computed(() => {
  const m = props.medico;
  if (!m) return '';
  return m.no_medico ? `${m.id_medico} · ${formatTitleCase(m.no_medico)}` : `${m.id_medico} · Não localizado na base do CFM`;
});

// Tom da faixa (chave do crmFaixaP95 → CRM_TAXA_P95_TONS); faixa sem chave = sem cor.
function tomDaFaixa(faixa) {
  if (!faixa?.chave) return null;
  // 'media-forte' → mediaForte, 'muito-forte' → muitoForte
  const tom = tonsP95.value[faixa.chave.replace(/-(\w)/g, (_, letra) => letra.toUpperCase())];
  if (!tom) throw new Error(`Faixa de ×P95 sem tom: ${faixa.chave}`);
  return tom;
}
function corDaBarra(d) {
  return tomDaFaixa(d.faixa) ?? coresDados.value.strong;
}

function formatTaxa(v) {
  return Number(v).toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

const chartOption = computed(() => {
  const c = chartTheme.value;
  const dados = meses.value;
  const modo = metrica.value;
  const porTaxa = modo === 'taxa';
  const porValor = modo === 'valor';
  const valorDe = (d) => (porTaxa ? d.taxa : porValor ? d.valor : d.qtd);
  const nomeBarra = METRICAS[modo].serie;
  const nomeLinha = porTaxa ? 'P95 nacional do mês' : '% da farmácia no mês';
  const nomeAlerta = 'Mês com alerta de sequência ou distância';
  const inscricao = props.medico?.dt_inscricao_crm ? competenciaDeData(props.medico.dt_inscricao_crm) : null;
  const labelInscricao = inscricao != null ? formatCompetencia(inscricao) : null;
  const inscricaoNoEixo = labelInscricao && dados.some(d => d.label === labelInscricao);
  const alertaMes = dados.filter(d => d.ativo && alertasPorMes.value.has(d.comp));

  return {
    backgroundColor: 'transparent',
    animationDuration: 300,
    textStyle: { color: c.text },
    legend: {
      top: 0,
      right: 8,
      textStyle: { color: c.muted, fontSize: 11 },
      itemWidth: 12,
      itemHeight: 8,
      data: [
        { name: nomeBarra, itemStyle: { color: coresDados.value.strong } },
        { name: nomeLinha },
        ...(alertaMes.length ? [{ name: nomeAlerta }] : []),
      ],
    },
    grid: { top: 36, right: porTaxa ? 24 : 56, bottom: 36, left: 64 },
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'shadow', shadowStyle: { color: c.axisShadow } },
      backgroundColor: c.tooltip,
      borderColor: c.tooltipBorder,
      textStyle: { color: c.tooltipText, fontSize: 12 },
      formatter: (params) => {
        const d = dados[params[0]?.dataIndex];
        if (!d) return '';
        if (!d.ativo) {
          return `<div style="min-width:200px"><div style="font-weight:600;margin-bottom:6px">${d.label}</div><div style="opacity:.7">Sem prescrições do CRM nesta farmácia.</div></div>`;
        }
        const pct = d.farmQtd > 0 ? (d.qtd / d.farmQtd) * 100 : 0;
        const al = alertasPorMes.value.get(d.comp);
        const linhas = [
          ['Taxa diária na farmácia', `${formatTaxa(d.taxa)}/dia em ${d.dias} ${d.dias === 1 ? 'dia' : 'dias'}`],
          ['×P95 nacional do mês', `${d.razao.toLocaleString('pt-BR', { maximumFractionDigits: 1 })}× (P95 ${formatTaxa(d.p95)})`],
          ['Autorizações do CRM', formatNumberFull(d.qtd)],
          ['Valor do CRM', formatCurrencyFull(d.valor)],
          ['% das autorizações da farmácia', `${pct.toFixed(1).replace('.', ',')}%`],
          ['Autorizações do CRM no Brasil', formatNumberFull(d.qtdBrasil)],
        ];
        const faixaHtml = d.faixa
          ? ` · <span style="color:${tomDaFaixa(d.faixa) ?? c.tooltipText}">taxa elevada (${d.faixa.rotulo})</span>`
          : '';
        const alertasHtml = al
          ? `<div style="margin-top:8px;padding-top:8px;border-top:1px solid ${c.tooltipBorder};font-size:11px;">
               ${al.unico ? '<div>▼ Autorizações em sequência · Único CRM</div>' : ''}
               ${al.multi ? '<div>▼ Autorizações em sequência · Múltiplos CRMs</div>' : ''}
               ${al.geo ? '<div>▼ Distância &gt; 400 km</div>' : ''}
             </div>`
          : '';
        return `<div style="min-width:260px">
          <div style="font-weight:600;margin-bottom:6px">${d.label}${faixaHtml}</div>
          ${linhas.map(([k, v]) => `<div style="display:flex;justify-content:space-between;gap:16px"><span style="opacity:.7">${k}</span><span style="font-weight:600">${v}</span></div>`).join('')}
          ${alertasHtml}
        </div>`;
      },
    },
    xAxis: {
      type: 'category',
      data: dados.map(d => d.label),
      axisLine: { lineStyle: { color: c.border } },
      axisTick: { show: false },
      axisLabel: { color: c.muted, fontSize: 10 },
    },
    yAxis: [
      {
        type: 'value',
        axisLabel: {
          color: c.muted,
          fontSize: 10,
          formatter: (v) => (porValor ? `R$ ${formatNumberFull(v)}` : porTaxa ? `${formatNumberFull(v)}/dia` : formatNumberFull(v)),
        },
        splitLine: { lineStyle: { color: c.grid } },
      },
      {
        type: 'value',
        show: !porTaxa,
        min: 0,
        max: 100,
        axisLabel: { color: c.muted, fontSize: 10, formatter: '{value}%' },
        splitLine: { show: false },
      },
    ],
    series: [
      {
        name: nomeBarra,
        type: 'bar',
        barMaxWidth: 28,
        itemStyle: { color: coresDados.value.strong, borderRadius: [3, 3, 0, 0] },
        data: dados.map(d => ({ value: valorDe(d), itemStyle: { color: corDaBarra(d) } })),
        markLine: inscricaoNoEixo
          ? {
              symbol: 'none',
              silent: true,
              lineStyle: { color: COR_INSCRICAO, type: 'dashed', width: 1.5 },
              label: { formatter: '1ª inscrição no CRM', color: COR_INSCRICAO, fontSize: 10, position: 'insideEndTop' },
              data: [{ xAxis: labelInscricao }],
            }
          : undefined,
      },
      porTaxa
        ? {
            name: nomeLinha,
            type: 'line',
            step: 'middle',
            connectNulls: true,
            symbol: 'none',
            lineStyle: { color: coresDados.value.line, width: 1.5, type: 'dashed' },
            itemStyle: { color: coresDados.value.line },
            data: dados.map(d => (d.p95 != null ? Number(d.p95.toFixed(2)) : null)),
          }
        : {
            name: nomeLinha,
            type: 'line',
            yAxisIndex: 1,
            smooth: 0.25,
            symbol: 'none',
            lineStyle: { color: coresDados.value.line, width: 2, type: 'dashed' },
            itemStyle: { color: coresDados.value.line },
            data: dados.map(d => {
              const base = porValor ? d.farmValor : d.farmQtd;
              const parte = porValor ? d.valor : d.qtd;
              return base > 0 ? Number(((parte / base) * 100).toFixed(2)) : 0;
            }),
          },
      {
        // Marcador (triângulo para baixo) acima da barra dos meses com alerta.
        name: nomeAlerta,
        type: 'scatter',
        symbol: 'triangle',
        symbolRotate: 180,
        symbolSize: 9,
        symbolOffset: [0, -9],
        silent: true,
        z: 5,
        itemStyle: { color: c.text },
        data: alertaMes.map(d => [d.label, valorDe(d)]),
      },
    ],
  };
});

function fechar() {
  emit('update:modelValue', false);
}
</script>

<template>
  <Dialog
    :visible="modelValue"
    modal
    dismissableMask
    class="crm-atuacao-dialog"
    :style="{ width: '94vw', maxWidth: '1600px' }"
    @update:visible="emit('update:modelValue', $event)"
  >
    <template #header>
      <div class="atuacao-dialog-header">
        <span class="atuacao-dialog-eyebrow">Atuação na farmácia</span>
        <span class="atuacao-dialog-title">{{ titulo }}</span>
      </div>
    </template>

    <div v-if="medico" class="atuacao-dialog-body">
      <div class="atuacao-kpis">
        <div v-for="kpi in kpis" :key="kpi.label" class="atuacao-kpi">
          <span class="atuacao-kpi-label">{{ kpi.label }}</span>
          <span class="atuacao-kpi-value">{{ kpi.value }}</span>
        </div>
      </div>

      <div class="atuacao-toolbar">
        <div class="atuacao-metrica" role="radiogroup" aria-label="Métrica do gráfico">
          <button
            v-for="(m, chave) in METRICAS"
            :key="chave"
            type="button"
            role="radio"
            :aria-checked="metrica === chave"
            :class="{ 'is-active': metrica === chave }"
            @click="metrica = chave"
          >{{ m.botao }}</button>
        </div>
        <div class="atuacao-legenda">
          <span class="legenda-tons">
            <i class="legenda-cor" :style="{ background: tonsP95.leve }" />
            <i class="legenda-cor" :style="{ background: tonsP95.media }" />
            <i class="legenda-cor" :style="{ background: tonsP95.mediaForte }" />
            <i class="legenda-cor" :style="{ background: tonsP95.forte }" />
            <i class="legenda-cor" :style="{ background: tonsP95.muitoForte }" />
            <i class="legenda-cor" :style="{ background: tonsP95.extrema }" />
            ×P95 do mês: um tom a cada 1×, de 1,5× a 6,5×, e o mais marcado acima de 6,5×
          </span>
          <span><i class="legenda-marcador" aria-hidden="true">▼</i> Mês com alerta de sequência ou distância</span>
          <span v-if="medico.dt_inscricao_crm"><i class="legenda-cor is-inscricao" /> 1ª inscrição: {{ formatarData(medico.dt_inscricao_crm) }}</span>
        </div>
      </div>

      <VChart class="atuacao-chart" :option="chartOption" autoresize />

      <p class="atuacao-nota">
        <template v-if="metrica === 'taxa'">
          Taxa diária = prescrições do CRM nesta farmácia ÷ dias com prescrição nela no mês. A linha tracejada é o P95 nacional do mês.
        </template>
        <template v-else>
          A linha mostra a parcela das autorizações (ou do valor) da farmácia no mês que foi atribuída a este CRM.
        </template>
        A cor da barra segue a taxa diária em todas as métricas. O tooltip de cada mês traz também o volume do mesmo CRM no Brasil.
      </p>
    </div>

    <template #footer>
      <button type="button" class="atuacao-fechar" @click="fechar">Fechar</button>
    </template>
  </Dialog>
</template>

<style scoped>
.atuacao-dialog-header { display: flex; flex-direction: column; gap: 0.15rem; }
.atuacao-dialog-eyebrow {
  font-size: 0.66rem;
  font-weight: 600;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--text-muted);
}
.atuacao-dialog-title { font-size: 1rem; font-weight: 600; color: var(--text-color); }
.atuacao-dialog-body { display: flex; flex-direction: column; gap: 1rem; }
.atuacao-kpis {
  display: grid;
  grid-template-columns: repeat(6, minmax(0, 1fr));
  gap: 0.75rem;
}
.atuacao-kpi {
  display: flex;
  flex-direction: column;
  gap: 0.3rem;
  padding: 0.7rem 0.9rem;
  border: 1px solid var(--card-border);
  border-radius: 10px;
  background: color-mix(in srgb, var(--text-color) 3%, transparent);
}
.atuacao-kpi-label {
  font-size: 0.64rem;
  font-weight: 600;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--text-muted);
}
.atuacao-kpi-value { font-size: 0.92rem; font-weight: 600; color: var(--text-color); }
.atuacao-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
  flex-wrap: wrap;
}
.atuacao-metrica {
  display: inline-flex;
  gap: 2px;
  padding: 3px;
  border: 1px solid var(--card-border);
  border-radius: 9px;
}
.atuacao-metrica button {
  min-height: 30px;
  padding: 0 0.9rem;
  border: 0;
  border-radius: 7px;
  background: transparent;
  color: var(--text-secondary);
  font: inherit;
  font-size: 0.74rem;
  font-weight: 600;
  cursor: pointer;
}
.atuacao-metrica button.is-active {
  background: color-mix(in srgb, var(--primary-color) 18%, transparent);
  color: var(--primary-color);
}
.atuacao-metrica button:focus-visible {
  outline: 2px solid color-mix(in srgb, var(--primary-color) 70%, transparent);
  outline-offset: 2px;
}
.atuacao-legenda {
  display: flex;
  align-items: center;
  gap: 1.1rem;
  font-size: 0.72rem;
  color: var(--text-secondary);
}
.atuacao-legenda span { display: inline-flex; align-items: center; gap: 0.4rem; }
.legenda-cor { width: 10px; height: 10px; border-radius: 2px; display: inline-block; }
.atuacao-legenda .legenda-tons { gap: 0.2rem; }
.legenda-tons .legenda-cor:last-of-type { margin-right: 0.25rem; }
.legenda-marcador { font-style: normal; font-size: 0.62rem; color: var(--text-color); }
.legenda-cor.is-inscricao { background: var(--risk-medium); height: 2px; }
.atuacao-chart { width: 100%; height: 360px; }
.atuacao-nota { margin: 0; font-size: 0.72rem; color: var(--text-muted); }
.atuacao-fechar {
  min-height: 34px;
  padding: 0 1.1rem;
  border: 1px solid var(--card-border);
  border-radius: 8px;
  background: transparent;
  color: var(--text-color);
  font: inherit;
  font-size: 0.8rem;
  font-weight: 500;
  cursor: pointer;
}
.atuacao-fechar:hover { border-color: var(--primary-color); color: var(--primary-color); }
</style>
