<script setup>
/**
 * Faixa de um filtro numérico dos médicos (/analises). Usa o mesmo seletor
 * do "% de não comprovação" (NumberRangePicker) no modo aberto: atalhos à
 * esquerda, faixa personalizada à direita, lados opcionais (vazio = sem limite).
 * O filtro só é aplicado no botão Aplicar, com Enter ou num atalho.
 */
import { computed } from 'vue';
import { storeToRefs } from 'pinia';
import { analysisTooltip } from '@/config/analysisTooltipConfig';
import { filterActionTooltip } from '@/config/filterTooltipConfig';
import { CRM_FAIXAS } from '@/config/crmFiltrosMedico';
import { formatarValorFaixa, useCrmFiltrosMedicoStore } from '@/stores/crmFiltrosMedico';
import NumberRangePicker from '@/views/components/common/NumberRangePicker.vue';

const props = defineProps({
  /** Chave de CRM_FAIXAS. */
  tipo: { type: String, required: true },
});

const config = CRM_FAIXAS[props.tipo];
if (!config) throw new Error(`Faixa de filtro de médico desconhecida: ${props.tipo}`);
const tooltip = analysisTooltip(config.tooltip);

const filtrosStore = useCrmFiltrosMedicoStore();
const { faixas } = storeToRefs(filtrosStore);
const valor = computed(() => [faixas.value[props.tipo].min, faixas.value[props.tipo].max]);
// Filtro ligado: destaque no rótulo e no campo, e borracha para voltar ao padrão.
const ativo = computed(() => valor.value[0] !== null || valor.value[1] !== null);
const limparTooltip = filterActionTooltip('Limpar filtro', 'Restaura este filtro ao valor padrão.', 'pi-eraser');

function formatar(v) {
  return formatarValorFaixa(props.tipo, v);
}

/** Texto do botão: nome do atalho escolhido, "≥ 30", "≤ 10", "= 7" ou "1.000 a 5.000". */
const rotulo = computed(() => {
  const [min, max] = valor.value;
  if (min === null && max === null) return config.todas;
  const atalho = config.atalhos.find((a) => a.faixa[0] === min && a.faixa[1] === max);
  if (atalho) return atalho.label;
  if (min === max) return `= ${formatar(min)}`;
  if (max === null) return `≥ ${formatar(min)}`;
  if (min === null) return `≤ ${formatar(max)}`;
  return `${formatar(min)} a ${formatar(max)}`;
});

function aplicar([min, max]) {
  filtrosStore.setFaixa(props.tipo, { min, max });
}
</script>

<template>
  <div class="filtro filtro-faixa" :class="{ 'is-ativo': ativo }">
    <div class="filtro-rotulo">
      <span>{{ config.label }}</span>
      <i class="pi pi-info-circle filtro-info help-icon" v-tooltip.left="tooltip" tabindex="0" :aria-label="`Sobre ${config.label.toLowerCase()}`" />
      <button
        v-if="ativo"
        type="button"
        class="filtro-limpar"
        :aria-label="`Limpar o filtro ${config.label.toLowerCase()}`"
        v-tooltip.left="limparTooltip"
        @click="filtrosStore.limparFaixa(tipo)"
      >
        <i class="pi pi-eraser" aria-hidden="true" />
      </button>
    </div>
    <NumberRangePicker
      aberto
      :valor="valor"
      :casas="config.casas"
      :min="0"
      :max="config.max"
      :passo="config.passo"
      :formatar="formatar"
      :sufixo="config.sufixo"
      :atalhos="config.atalhos"
      :rotulo="rotulo"
      :mostrar-icone="false"
      @select-range="aplicar"
    />
  </div>
</template>

<style scoped>
.filtro { display: flex; flex-direction: column; gap: 0.4rem; }
/* Título do filtro: texto principal do tema a 70% (o mesmo da sidebar esquerda). */
.filtro-rotulo { display: flex; align-items: center; gap: 0.35rem; color: color-mix(in srgb, var(--text-color) 70%, transparent); font-size: 0.8125rem; font-weight: 500; }
.filtro-info { color: var(--text-muted); font-size: 0.8rem; opacity: 0.75; cursor: help; }
.filtro-info:hover, .filtro-info:focus-visible { opacity: 1; }
/* Botão do seletor ocupa a largura do bloco, como na barra lateral esquerda. */
/* Mesma altura e recuo dos campos da sidebar esquerda (32px; 0,6rem). */
.filtro-faixa :deep(.rp-gatilho) { width: 100%; height: 32px; min-height: 32px; padding: 0 0.6rem; color: var(--text-color-85); font-size: 0.8125rem; font-weight: 400; }
</style>
