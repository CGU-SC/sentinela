<script setup>
import { computed } from "vue";
import { useFormatting } from "@/composables/useFormatting";
import { CRM_KPI_THRESHOLDS } from "@/config/riskConfig";

const props = defineProps({
  kpiData: { type: Object, required: true },
  activeKpiFilter: { type: String, default: null },
});

const emit = defineEmits(['kpi-click']);

const { formatCurrencyFull, formatNumberFull } = useFormatting();
const formatPct = (val) => val != null ? `${Number(val).toFixed(2).replace('.', ',')}%` : "0,00%";

const escapeTooltipHtml = (value) => String(value).replace(/[&<>"']/g, (character) => ({
  '&': '&amp;',
  '<': '&lt;',
  '>': '&gt;',
  '"': '&quot;',
  "'": '&#39;',
}[character]));

const createCrmKpiTooltip = (title, body, note) => ({
  value: `
    <div class="crm-profile-tooltip-content">
      <div class="crm-profile-tooltip-heading">
        <i class="pi pi-info-circle" aria-hidden="true"></i>
        <span>${escapeTooltipHtml(title)}</span>
      </div>
      <p class="crm-profile-tooltip-body">${escapeTooltipHtml(body)}</p>
      <div class="crm-profile-tooltip-note">
        <strong>Como interpretar</strong>
        <span>${escapeTooltipHtml(note)}</span>
      </div>
    </div>
  `,
  escape: false,
  class: 'crm-profile-info-tooltip',
  showDelay: 120,
  hideDelay: 80,
});

const plural = (n, singular, pluralForm) => `${formatNumberFull(n)} ${Number(n) === 1 ? singular : pluralForm}`;

function concentracaoTone(valor, limites) {
  if (valor > limites.critico) return 'critico';
  if (valor > limites.atencao) return 'medio';
  return null;
}

/**
 * Cards em duas linhas temáticas. Cor apenas na bolinha do título, com as mesmas
 * cores da coluna Status/Alertas da tabela; cards de alerta zerados ficam apagados.
 */
const grupos = computed(() => {
  const k = props.kpiData;
  const crmIrregularHint = k.valorFraudeCrm != null && k.pctFraudeCrm != null
    ? `${formatCurrencyFull(k.valorFraudeCrm)} (${formatPct(k.pctFraudeCrm)}) das vendas monitoradas`
    : k.indicadorCrmErro ? 'Falha ao carregar indicador financeiro'
      : k.indicadorCrmCarregando ? 'Carregando indicador financeiro…' : 'Indicador financeiro indisponível';

  return [
    {
      id: 'perfil',
      titulo: 'Perfil dos prescritores',
      cards: [
        {
          key: 'top1',
          label: 'Top 1 CRM · valor',
          value: formatPct(k.concentracaoTop1),
          hint: `${k.idTop1Prescritor || 'ND'} · ${formatCurrencyFull(k.valorTop1)}`,
          tone: concentracaoTone(k.concentracaoTop1, CRM_KPI_THRESHOLDS.concentracaoTop1),
          enabled: true,
          tooltip: createCrmKpiTooltip(
            'Top 1 CRM — valor',
            'Percentual do valor total de autorizações da farmácia concentrado no prescritor de maior participação no período selecionado.',
            `A bolinha fica laranja acima de ${CRM_KPI_THRESHOLDS.concentracaoTop1.atencao}% e vermelha acima de ${CRM_KPI_THRESHOLDS.concentracaoTop1.critico}%. A linha de apoio identifica o CRM e o valor associado.`
          ),
        },
        {
          key: 'top5',
          label: 'Top 5 CRMs · valor',
          value: formatPct(k.concentracaoTop5),
          hint: formatCurrencyFull(k.valorTop5),
          tone: concentracaoTone(k.concentracaoTop5, CRM_KPI_THRESHOLDS.concentracaoTop5),
          enabled: true,
          tooltip: createCrmKpiTooltip(
            'Top 5 CRMs — valor',
            'Percentual do valor total de autorizações da farmácia concentrado nos cinco prescritores de maior participação.',
            `A bolinha fica laranja acima de ${CRM_KPI_THRESHOLDS.concentracaoTop5.atencao}% e vermelha acima de ${CRM_KPI_THRESHOLDS.concentracaoTop5.critico}%.`
          ),
        },
        {
          key: 'exclusivo',
          label: 'CRMs exclusivos',
          value: formatNumberFull(k.qtdCrmExclusivo),
          hint: 'com todas as autorizações nesta farmácia',
          tone: k.qtdCrmExclusivo > 0 ? 'exclusivo' : null,
          enabled: k.qtdCrmExclusivo > 0,
          tooltip: createCrmKpiTooltip(
            'CRMs exclusivos',
            'Quantidade de médicos cujas autorizações no Farmácia Popular foram todas registradas neste estabelecimento.',
            'Clique no card para filtrar a tabela por esses médicos.'
          ),
        },
        {
          key: 'fraude_crm',
          label: 'CRMs irregulares',
          value: formatNumberFull(k.totalIrregularesCfm),
          hint: crmIrregularHint,
          tone: (k.totalIrregularesCfm > 0 || k.valorFraudeCrm > 0) ? 'critico' : null,
          enabled: k.totalIrregularesCfm > 0 || k.valorFraudeCrm > 0,
          tooltip: createCrmKpiTooltip(
            'CRMs irregulares',
            `Médicos com inconsistência no CFM no detalhamento de prescritores: ${plural(k.qtdCrmInvalido, 'CRM não localizado', 'CRMs não localizados')} e ${plural(k.qtdPrescrAntesRegistro, 'CRM com venda anterior ao registro', 'CRMs com venda anterior ao registro')}.`,
            'O valor e o percentual vêm do indicador completo de CRMs irregulares da matriz de risco; a lista de médicos da tabela é um detalhamento e não compõe, sozinha, o total financeiro.'
          ),
        },
      ],
    },
    {
      id: 'lancamento',
      titulo: 'Padrões de lançamento',
      cards: [
        {
          key: 'agrupamento',
          label: 'Sequência · Único CRM',
          value: formatNumberFull(k.qtdLancamentosAgrupados),
          hint: 'médicos com autorizações em sequência',
          tone: k.qtdLancamentosAgrupados > 0 ? 'unico' : null,
          enabled: k.qtdLancamentosAgrupados > 0,
          tooltip: createCrmKpiTooltip(
            'Autorizações em Sequência (Único CRM)',
            'Quantidade de médicos que registraram muitas autorizações em sequência, em intervalo de tempo muito curto, com o próprio CRM.',
            'Clique no card para filtrar a tabela pelos médicos relacionados e consultar os episódios detalhados.'
          ),
        },
        {
          key: 'surtos_cnpj',
          label: 'Sequência · Múltiplos CRMs',
          value: formatNumberFull(k.totalSurtosCnpj),
          hint: `em ${plural(k.diasComSurtosCnpj, 'dia distinto', 'dias distintos')}`,
          tone: k.totalSurtosCnpj > 0 ? 'multi' : null,
          enabled: k.totalSurtosCnpj > 0,
          tooltip: createCrmKpiTooltip(
            'Autorizações em Sequência (Múltiplos CRMs)',
            'Quantidade de episódios em que a farmácia registrou muitas autorizações em sequência com participação de diferentes CRMs.',
            'A linha de apoio informa em quantos dias distintos esse padrão foi identificado.'
          ),
        },
        {
          key: 'intensiva',
          label: 'Mais de 30 presc./dia',
          value: formatNumberFull(k.qtdPrescrIntensivaTotal),
          hint: `${formatNumberFull(k.qtdPrescrIntensivaLocal)} local · ${formatNumberFull(k.qtdPrescrIntensivaOcultos)} Brasil`,
          tone: k.qtdPrescrIntensivaTotal > 0 ? 'critico' : null,
          enabled: k.qtdPrescrIntensivaTotal > 0,
          tooltip: createCrmKpiTooltip(
            'Mais de 30 prescrições por dia',
            'Quantidade de médicos cuja média diária de prescrições ultrapassou 30 autorizações, nesta farmácia (local) ou considerando todo o Brasil no Farmácia Popular.',
            'A linha de apoio separa as ocorrências nesta unidade das encontradas apenas no Brasil.'
          ),
        },
        {
          key: 'distancia',
          label: 'Distância > 400 km',
          value: formatNumberFull(k.qtdAcima400km),
          hint: 'médicos com prescrições em locais distantes',
          tone: k.qtdAcima400km > 0 ? 'geo' : null,
          enabled: k.qtdAcima400km > 0,
          tooltip: createCrmKpiTooltip(
            'Distância superior a 400 km',
            'Quantidade de médicos associados a prescrições em estabelecimentos separados por mais de 400 quilômetros em intervalo incompatível.',
            'As evidências geográficas podem ser consultadas na tabela, abrindo o detalhe do médico.'
          ),
        },
      ],
    },
  ];
});

function onCardClick(card) {
  if (card.enabled) emit('kpi-click', card.key);
}
</script>

<template>
  <div class="kpi-groups animate-fade-in">
    <section v-for="grupo in grupos" :key="grupo.id" class="kpi-group" :aria-label="grupo.titulo">
      <div class="alerts-kpi-grid">
        <div
          v-for="(card, idx) in grupo.cards"
          :key="card.key"
          class="alert-kpi-card"
          :class="{ 'kpi-disabled': !card.enabled, 'kpi-active': activeKpiFilter === card.key }"
          :role="card.enabled ? 'button' : undefined"
          :tabindex="card.enabled ? 0 : undefined"
          :aria-pressed="card.enabled ? activeKpiFilter === card.key : undefined"
          @click="onCardClick(card)"
          @keydown.enter.prevent="onCardClick(card)"
          @keydown.space.prevent="onCardClick(card)"
        >
          <div class="alert-kpi-header">
            <span v-if="card.tone" class="kpi-dot" :class="`tone-${card.tone}`" aria-hidden="true" />
            <span class="alert-kpi-label">{{ card.label }}</span>
            <i
              class="pi pi-info-circle kpi-info-icon"
              v-tooltip="{ ...card.tooltip, ...(idx === grupo.cards.length - 1 ? { position: 'left' } : { position: 'top' }) }"
              tabindex="0"
              :aria-label="`Informações sobre ${card.label}`"
              @click.stop
            />
          </div>
          <span class="alert-kpi-val">{{ card.value }}</span>
          <span class="alert-kpi-hint">{{ card.hint }}</span>
        </div>
      </div>
    </section>
  </div>
</template>

<style scoped>
.animate-fade-in {
  animation: fadeIn 0.3s ease-out;
}
@keyframes fadeIn {
  from { opacity: 0; transform: translateY(10px); }
  to { opacity: 1; transform: translateY(0); }
}

.kpi-groups { display: flex; flex-direction: column; gap: 0.75rem; }
.kpi-group { display: flex; flex-direction: column; }

.alerts-kpi-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 0.75rem;
}

.alert-kpi-card {
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
  padding: 0.8rem 1rem;
  background: var(--card-bg);
  border: 1px solid var(--card-border);
  border-radius: 10px;
  cursor: pointer;
  user-select: none;
  transition: border-color 0.15s ease, background 0.15s ease;
}
.alert-kpi-card:hover {
  border-color: color-mix(in srgb, var(--text-color-85) 30%, var(--card-border));
}
.alert-kpi-card:focus-visible {
  outline: 2px solid color-mix(in srgb, var(--text-color-85) 45%, transparent);
  outline-offset: 2px;
}
.alert-kpi-card.kpi-active {
  border-color: color-mix(in srgb, var(--text-color-85) 60%, transparent);
  background: color-mix(in srgb, var(--text-color-85) 4%, var(--card-bg));
}
.alert-kpi-card.kpi-disabled {
  cursor: default;
  opacity: 0.45;
}
.alert-kpi-card.kpi-disabled:hover { border-color: var(--card-border); }

.alert-kpi-header {
  display: flex;
  align-items: center;
  gap: 0.45rem;
}
.kpi-dot {
  width: 8px;
  height: 8px;
  flex-shrink: 0;
  border-radius: 50%;
}
.kpi-dot.tone-critico { background: var(--risk-critical); }
.kpi-dot.tone-medio { background: var(--risk-medium); }
.kpi-dot.tone-unico { background: #f59e0b; }
.kpi-dot.tone-multi { background: #8b5cf6; }
.kpi-dot.tone-geo { background: #14b8a6; }
.kpi-dot.tone-exclusivo { background: #3b82f6; }

.alert-kpi-label {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 0.68rem;
  font-weight: 600;
  color: var(--text-secondary);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}
.kpi-info-icon {
  flex-shrink: 0;
  font-size: 0.78rem;
  color: var(--text-muted);
  cursor: help;
  outline: none;
  transition: color 0.15s;
}
.kpi-info-icon:hover { color: var(--text-color-85); }
.kpi-info-icon:focus-visible {
  outline: 2px solid color-mix(in srgb, var(--text-color-85) 45%, transparent);
  outline-offset: 2px;
  border-radius: 50%;
}

.alert-kpi-val {
  font-size: 1.35rem;
  font-weight: 600;
  line-height: 1.1;
  color: var(--text-color);
}
.alert-kpi-hint {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 0.72rem;
  color: var(--text-muted);
}

:global(.p-tooltip.crm-profile-info-tooltip) {
  max-width: min(360px, calc(100vw - 2rem));
  padding: 0;
  background: var(--tooltip-bg);
  border: 1px solid var(--tooltip-border);
  border-radius: 9px;
  box-shadow: var(--tooltip-shadow);
}

:global(.crm-profile-tooltip-content) {
  display: flex;
  width: min(330px, calc(100vw - 2rem));
  flex-direction: column;
  gap: 0.62rem;
  padding: 0.75rem 0.85rem;
  line-height: 1.42;
}

:global(.crm-profile-tooltip-heading) {
  display: flex;
  align-items: center;
  gap: 0.45rem;
  color: var(--text-color-85);
  font-size: 0.8rem;
  font-weight: 700;
  letter-spacing: 0.025em;
}

:global(.crm-profile-tooltip-heading i) {
  flex-shrink: 0;
  color: var(--risk-medium);
  font-size: 0.8rem;
}

:global(.crm-profile-tooltip-body) {
  margin: 0;
  color: var(--text-secondary);
  font-size: 0.72rem;
}

:global(.crm-profile-tooltip-note) {
  display: flex;
  flex-direction: column;
  gap: 0.2rem;
  padding-top: 0.55rem;
  border-top: 1px solid var(--tabs-border);
  color: var(--text-secondary);
  font-size: 0.68rem;
}

:global(.crm-profile-tooltip-note strong) {
  color: var(--risk-medium);
  font-size: 0.65rem;
  font-weight: 700;
  letter-spacing: 0.04em;
  text-transform: uppercase;
}
</style>
