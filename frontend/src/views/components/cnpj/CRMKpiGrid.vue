<script setup>
import { useFormatting } from "@/composables/useFormatting";

const props = defineProps({
  kpiData: { type: Object, required: true },
  activeKpiFilter: { type: String, default: null },
});

const emit = defineEmits(['kpi-click']);

const { formatCurrencyFull } = useFormatting();
const formatPct = (val) => val != null ? `${Number(val).toFixed(2)}%` : "0.00%";

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

const crmKpiTooltips = Object.freeze({
  top1: createCrmKpiTooltip(
    'Top 1 CRM — volume financeiro',
    'Percentual do valor total de autorizações da farmácia concentrado no prescritor com maior participação financeira no período selecionado.',
    'O valor de apoio identifica o CRM líder e o montante associado às suas autorizações.'
  ),
  top5: createCrmKpiTooltip(
    'Top 5 CRMs — volume financeiro',
    'Percentual do volume financeiro acumulado pelos cinco prescritores com maior valor autorizado no estabelecimento.',
    'O percentual mostra quanto do volume financeiro do estabelecimento está concentrado nos cinco principais prescritores.'
  ),
  agrupamento: createCrmKpiTooltip(
    'Autorizações em Sequência (Único CRM)',
    'Quantidade de ocorrências em que o mesmo CRM registrou muitas autorizações em sequência em um intervalo de tempo muito curto.',
    'Clique no card para filtrar a tabela pelos médicos relacionados e consultar os episódios detalhados.'
  ),
  intensiva: createCrmKpiTooltip(
    'Mais de 30 prescrições por dia',
    'Quantidade de médicos cuja média diária de prescrições ultrapassou 30 autorizações. O indicador considera a atuação local e a atuação do CRM em todo o Brasil no Farmácia Popular.',
    'O apoio do card separa as ocorrências identificadas nesta unidade das encontradas no Brasil.'
  ),
  exclusivo: createCrmKpiTooltip(
    'CRMs exclusivos',
    'Quantidade de médicos cujas autorizações no Farmácia Popular foram registradas exclusivamente neste estabelecimento no conjunto de registros analisado.',
    'A linha de apoio informa a proporção de exclusividade local associada ao indicador.'
  ),
  fraudeCrm: createCrmKpiTooltip(
    'Fraudes CRM',
    'Quantidade de CRMs com inconsistência cadastral ou temporal na base do Conselho Federal de Medicina: CRM não localizado ou prescrição anterior ao registro oficial.',
    'O valor financeiro em destaque representa o montante associado às ocorrências identificadas.'
  ),
  distancia: createCrmKpiTooltip(
    'Distância superior a 400 km',
    'Quantidade de médicos associados a prescrições em estabelecimentos separados por mais de 400 quilômetros.',
    'O card sinaliza o volume de prescritores relacionados; as evidências geográficas podem ser consultadas na tabela.'
  ),
  surtosCnpj: createCrmKpiTooltip(
    'Autorizações em Sequência (Múltiplos CRMs)',
    'Quantidade de ocorrências em que a farmácia registrou muitas autorizações em sequência com participação de alguns CRMs.',
    'A linha de apoio informa em quantos dias distintos esse padrão foi identificado.'
  ),
});
</script>

<template>
  <div class="alerts-kpi-grid animate-fade-in">
    <!-- Concentração TOP 1 -->
    <div
      class="alert-kpi-card"
      :class="[
        kpiData.concentracaoTop1 > 40 ? 'highlight-red' : kpiData.concentracaoTop1 > 20 ? 'highlight-orange' : '',
        activeKpiFilter === 'top1' ? 'kpi-active' : '',
      ]"
      @click="emit('kpi-click', 'top1')"
    >
      <div class="alert-kpi-header">
        <span class="alert-kpi-label">TOP 1 CRM - VOLUME R$</span>
        <i
          class="pi pi-info-circle kpi-info-icon"
          v-tooltip.top="crmKpiTooltips.top1"
          tabindex="0"
          aria-label="Informações sobre Top 1 CRM — volume financeiro"
        />
      </div>
      <div class="alert-kpi-body">
        <span class="alert-kpi-val">{{ formatPct(kpiData.concentracaoTop1) }}</span>
        <span class="alert-kpi-hint">
          CRM: {{ kpiData.idTop1Prescritor || 'ND' }}
          <strong style="color: var(--text-color-85)"> · {{ formatCurrencyFull(kpiData.valorTop1) }}</strong>
        </span>
      </div>
    </div>

    <!-- Concentração TOP 5 -->
    <div
      class="alert-kpi-card"
      :class="[
        kpiData.concentracaoTop5 > 70 ? 'highlight-red' : kpiData.concentracaoTop5 > 50 ? 'highlight-orange' : '',
        activeKpiFilter === 'top5' ? 'kpi-active' : '',
      ]"
      @click="emit('kpi-click', 'top5')"
    >
      <div class="alert-kpi-header">
        <span class="alert-kpi-label">TOP 5 CRMs - VOLUME R$</span>
        <i
          class="pi pi-info-circle kpi-info-icon"
          v-tooltip.top="crmKpiTooltips.top5"
          tabindex="0"
          aria-label="Informações sobre Top 5 CRMs — volume financeiro"
        />
      </div>
      <div class="alert-kpi-body">
        <span class="alert-kpi-val">{{ formatPct(kpiData.concentracaoTop5) }}</span>
        <span class="alert-kpi-hint">
          <strong style="color: var(--text-color-85)">{{ formatCurrencyFull(kpiData.valorTop5) }}</strong>
        </span>
      </div>
    </div>

    <!-- Agrupamento de Lançamentos -->
    <div
      class="alert-kpi-card"
      :class="[
        kpiData.qtdLancamentosAgrupados > 0 ? 'highlight-violet' : 'kpi-disabled',
        activeKpiFilter === 'agrupamento' ? 'kpi-active' : '',
      ]"
      @click="emit('kpi-click', 'agrupamento')"
    >
      <div class="alert-kpi-header">
        <span class="alert-kpi-label">Autorizações em Sequência (Único CRM)</span>
        <i
          class="pi pi-info-circle kpi-info-icon"
          v-tooltip.top="crmKpiTooltips.agrupamento"
          tabindex="0"
          aria-label="Informações sobre autorizações em sequência por um único CRM"
        />
      </div>
      <div class="alert-kpi-body">
        <span class="alert-kpi-val">{{ kpiData.qtdLancamentosAgrupados }}</span>
        <span class="alert-kpi-hint">Muitas Autorizações em Intervalo Curto</span>
      </div>
    </div>

    <!-- Prescrição Intensiva -->
    <div
      class="alert-kpi-card"
      :class="[
        kpiData.qtdPrescrIntensivaTotal > 0 ? 'highlight-red' : 'kpi-disabled',
        activeKpiFilter === 'intensiva' ? 'kpi-active' : '',
      ]"
      @click="emit('kpi-click', 'intensiva')"
    >
      <div class="alert-kpi-header">
        <span class="alert-kpi-label">>30 PRESCRIÇÕES/DIA</span>
        <i
          class="pi pi-info-circle kpi-info-icon"
          v-tooltip.left="crmKpiTooltips.intensiva"
          tabindex="0"
          aria-label="Informações sobre mais de 30 prescrições por dia"
        />
      </div>
      <div class="alert-kpi-body">
        <span class="alert-kpi-val">{{ kpiData.qtdPrescrIntensivaTotal }}</span>
        <span class="alert-kpi-hint">
          {{ kpiData.qtdPrescrIntensivaLocal }} local · {{ kpiData.qtdPrescrIntensivaOcultos }} Brasil
        </span>
      </div>
    </div>

    <!-- CRMs Exclusivos -->
    <div
      class="alert-kpi-card"
      :class="[
        kpiData.qtdCrmExclusivo > 0 ? 'highlight-purple' : 'kpi-disabled',
        activeKpiFilter === 'exclusivo' ? 'kpi-active' : '',
      ]"
      @click="emit('kpi-click', 'exclusivo')"
    >
      <div class="alert-kpi-header">
        <span class="alert-kpi-label">CRMs EXCLUSIVOS</span>
        <i
          class="pi pi-info-circle kpi-info-icon"
          v-tooltip.top="crmKpiTooltips.exclusivo"
          tabindex="0"
          aria-label="Informações sobre CRMs exclusivos"
        />
      </div>
      <div class="alert-kpi-body">
        <span class="alert-kpi-val">{{ kpiData.qtdCrmExclusivo }}</span>
        <span class="alert-kpi-hint">100% de exclusividade local</span>
      </div>
    </div>

    <!-- Fraudes CRM -->
    <div
      class="alert-kpi-card"
      :class="[
        kpiData.totalIrregularesCfm > 0 ? 'highlight-red highlight-fraude' : 'kpi-disabled',
        activeKpiFilter === 'fraude_crm' ? 'kpi-active' : '',
      ]"
      @click="emit('kpi-click', 'fraude_crm')"
    >
      <div class="alert-kpi-header">
        <span class="alert-kpi-label">FRAUDES CRM</span>
        <i
          class="pi pi-info-circle kpi-info-icon"
          v-tooltip.top="crmKpiTooltips.fraudeCrm"
          tabindex="0"
          aria-label="Informações sobre fraudes CRM"
        />
      </div>
      <div class="alert-kpi-body">
        <div class="alert-kpi-val-row">
          <span class="alert-kpi-val">{{ kpiData.totalIrregularesCfm }}</span>
          <span class="alert-kpi-val-sub">{{ kpiData.qtdCrmInvalido }} Não localizados | {{ kpiData.qtdPrescrAntesRegistro }} Irregulares</span>
        </div>
        <span class="alert-kpi-hint">
          <strong style="color: var(--risk-high)">
            {{ formatCurrencyFull(kpiData.valorFraudeCrm) }} ({{ formatPct(kpiData.pctFraudeCrm) }})
          </strong>
          da produção
        </span>
      </div>
    </div>

    <!-- Alerta >400km -->
    <div
      class="alert-kpi-card"
      :class="[
        kpiData.qtdAcima400km > 0 ? 'highlight-purple-geo' : 'kpi-disabled',
        activeKpiFilter === 'distancia' ? 'kpi-active' : '',
      ]"
      @click="emit('kpi-click', 'distancia')"
    >
      <div class="alert-kpi-header">
        <span class="alert-kpi-label">DISTÂNCIA (>400KM)</span>
        <i
          class="pi pi-info-circle kpi-info-icon"
          v-tooltip.top="crmKpiTooltips.distancia"
          tabindex="0"
          aria-label="Informações sobre distância superior a 400 quilômetros"
        />
      </div>
      <div class="alert-kpi-body">
        <span class="alert-kpi-val">{{ kpiData.qtdAcima400km }}</span>
        <span class="alert-kpi-hint">Prescrições em Locais Distantes</span>
      </div>
    </div>

    <!-- Surtos de Lançamento (Geral CNPJ) -->
    <div
      class="alert-kpi-card"
      :class="[
        kpiData.totalSurtosCnpj > 0 ? 'highlight-amber' : 'kpi-disabled',
        activeKpiFilter === 'surtos_cnpj' ? 'kpi-active' : '',
      ]"
      @click="emit('kpi-click', 'surtos_cnpj')"
    >
      <div class="alert-kpi-header">
        <span class="alert-kpi-label">Autorizações em Sequência (Múltiplos CRMs)</span>
        <i
          class="pi pi-info-circle kpi-info-icon"
          v-tooltip.left="crmKpiTooltips.surtosCnpj"
          tabindex="0"
          aria-label="Informações sobre autorizações em sequência por múltiplos CRMs"
        />
      </div>
      <div class="alert-kpi-body">
        <span class="alert-kpi-val">{{ kpiData.totalSurtosCnpj }}</span>
        <span class="alert-kpi-hint">Registros em {{ kpiData.diasComSurtosCnpj }} dias distintos</span>
      </div>
    </div>
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

.alerts-kpi-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 1rem;
  margin-bottom: 0;
}

.alert-kpi-card {
  padding: 0.9rem 1.1rem;
  background: var(--card-bg);
  border: 1px solid var(--card-border);
  border-left: 4px solid var(--card-border);
  border-radius: 12px;
  transition: all 0.2s ease;
  cursor: pointer;
  user-select: none;
}

.alert-kpi-card:hover {
  transform: translateY(-2px);
  box-shadow: 0 4px 15px rgba(0, 0, 0, 0.08);
}

.alert-kpi-card.highlight-red:hover {
  border-color: color-mix(in srgb, var(--risk-high) 45%, var(--card-border));
  box-shadow: 0 8px 16px -8px color-mix(in srgb, var(--risk-high) 20%, transparent);
}
.alert-kpi-card.highlight-orange:hover {
  border-color: color-mix(in srgb, var(--risk-medium) 45%, var(--card-border));
  box-shadow: 0 8px 16px -8px color-mix(in srgb, var(--risk-medium) 20%, transparent);
}
.alert-kpi-card.highlight-violet:hover {
  border-color: color-mix(in srgb, #818cf8 45%, var(--card-border));
  box-shadow: 0 8px 16px -8px color-mix(in srgb, #818cf8 20%, transparent);
}
.alert-kpi-card.highlight-purple:hover {
  border-color: color-mix(in srgb, #3b82f6 45%, var(--card-border));
  box-shadow: 0 8px 16px -8px color-mix(in srgb, #3b82f6 20%, transparent);
}
.alert-kpi-card.highlight-amber:hover {
  border-color: color-mix(in srgb, #f59e0b 45%, var(--card-border));
  box-shadow: 0 8px 16px -8px color-mix(in srgb, #f59e0b 20%, transparent);
}
.alert-kpi-card.highlight-purple-geo:hover {
  border-color: color-mix(in srgb, #8b5cf6 45%, var(--card-border));
  box-shadow: 0 8px 16px -8px color-mix(in srgb, #8b5cf6 20%, transparent);
}

.alert-kpi-card.kpi-disabled {
  cursor: default;
  pointer-events: none;
  opacity: 0.45;
}

.alert-kpi-card.kpi-active {
  transform: translateY(-3px) scale(1.01);
  z-index: 2;
  border-left-width: 6px !important;
}

.alert-kpi-card.highlight-red.kpi-active {
  background: color-mix(in srgb, var(--risk-high) 10%, var(--card-bg));
  border-color: var(--risk-high) !important;
  box-shadow: 0 0 25px -5px color-mix(in srgb, var(--risk-high) 60%, transparent), 0 10px 30px rgba(0, 0, 0, 0.2);
}
.alert-kpi-card.highlight-orange.kpi-active {
  background: color-mix(in srgb, var(--risk-medium) 10%, var(--card-bg));
  border-color: var(--risk-medium) !important;
  box-shadow: 0 0 25px -5px color-mix(in srgb, var(--risk-medium) 60%, transparent), 0 10px 30px rgba(0, 0, 0, 0.2);
}
.alert-kpi-card.highlight-violet.kpi-active {
  background: color-mix(in srgb, #818cf8 10%, var(--card-bg));
  border-color: #818cf8 !important;
  box-shadow: 0 0 25px -5px color-mix(in srgb, #818cf8 60%, transparent), 0 10px 30px rgba(0, 0, 0, 0.2);
}
.alert-kpi-card.highlight-purple.kpi-active {
  background: color-mix(in srgb, #3b82f6 10%, var(--card-bg));
  border-color: #3b82f6 !important;
  box-shadow: 0 0 25px -5px color-mix(in srgb, #3b82f6 60%, transparent), 0 10px 30px rgba(0, 0, 0, 0.2);
}
.alert-kpi-card.highlight-amber.kpi-active {
  background: color-mix(in srgb, #f59e0b 10%, var(--card-bg));
  border-color: #f59e0b !important;
  box-shadow: 0 0 25px -5px color-mix(in srgb, #f59e0b 60%, transparent), 0 10px 30px rgba(0, 0, 0, 0.2);
}
.alert-kpi-card.highlight-purple-geo.kpi-active {
  background: color-mix(in srgb, #8b5cf6 10%, var(--card-bg));
  border-color: #8b5cf6 !important;
  box-shadow: 0 0 25px -5px color-mix(in srgb, #8b5cf6 60%, transparent), 0 10px 30px rgba(0, 0, 0, 0.2);
}

.highlight-red {
  background: linear-gradient(to top, color-mix(in srgb, var(--risk-high) 15%, var(--card-bg)) 0%, var(--card-bg) 80%);
  border: 1px solid color-mix(in srgb, var(--risk-high) 15%, var(--card-border));
  border-left: 4px solid var(--risk-high) !important;
}
.highlight-orange {
  background: linear-gradient(to top, color-mix(in srgb, var(--risk-medium) 15%, var(--card-bg)) 0%, var(--card-bg) 80%);
  border: 1px solid color-mix(in srgb, var(--risk-medium) 15%, var(--card-border));
  border-left: 4px solid var(--risk-medium) !important;
}
.highlight-purple {
  background: linear-gradient(to top, color-mix(in srgb, #3b82f6 15%, var(--card-bg)) 0%, var(--card-bg) 80%);
  border: 1px solid color-mix(in srgb, #3b82f6 15%, var(--card-border));
  border-left: 4px solid #3b82f6 !important;
}
.highlight-purple-geo {
  background: linear-gradient(to top, color-mix(in srgb, #8b5cf6 15%, var(--card-bg)) 0%, var(--card-bg) 80%);
  border: 1px solid color-mix(in srgb, #8b5cf6 15%, var(--card-border));
  border-left: 4px solid #8b5cf6 !important;
}
.highlight-amber {
  background: linear-gradient(to top, color-mix(in srgb, #f59e0b 15%, var(--card-bg)) 0%, var(--card-bg) 80%);
  border: 1px solid color-mix(in srgb, #f59e0b 15%, var(--card-border));
  border-left: 4px solid #f59e0b !important;
}
.highlight-violet {
  background: linear-gradient(to top, color-mix(in srgb, #818cf8 15%, var(--card-bg)) 0%, var(--card-bg) 80%);
  border: 1px solid color-mix(in srgb, #818cf8 15%, var(--card-border));
  border-left: 4px solid #818cf8 !important;
}

.alert-kpi-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.alert-kpi-label {
  flex: 1;
  min-width: 0;
  font-size: 0.7rem;
  font-weight: 600;
  color: var(--text-secondary);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  line-height: 1.2;
  opacity: 0.85;
}
.kpi-info-icon {
  font-size: 0.8rem;
  color: var(--text-muted);
  cursor: help;
  outline: none;
  transition: color 0.15s;
}
.kpi-info-icon:hover { color: var(--primary-color); }
.kpi-info-icon:focus-visible {
  outline: 2px solid color-mix(in srgb, var(--primary-color) 70%, transparent);
  outline-offset: 2px;
  border-radius: 50%;
}

.alert-kpi-body {
  display: flex;
  flex-direction: column;
  gap: 0.2rem;
}
.alert-kpi-val-row {
  display: flex;
  align-items: baseline;
  gap: 0.5rem;
}
.alert-kpi-val {
  font-size: 1.15rem;
  font-weight: 600;
  color: var(--text-color-85);
  line-height: 1;
}
.alert-kpi-val-sub {
  font-size: 0.7rem;
  font-weight: 500;
  color: var(--text-color-85);
  opacity: 0.85;
}
.alert-kpi-hint {
  font-size: 0.72rem;
  color: var(--text-muted);
  font-weight: 400;
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
