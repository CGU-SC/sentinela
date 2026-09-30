<script setup>
/**
 * Ícone de alertas de um CRM no ranking de /analises: triângulo + número de
 * pontos de atenção, com tooltip HTML listando todos. Clique abre o histórico.
 */
import { computed } from 'vue';
import { crmAlertasTooltip } from '@/config/analysisTooltipConfig';
import { CRM_ALERTA_BADGE_TONS } from '@/config/colors';
import { useThemeStore } from '@/stores/theme';

const props = defineProps({
  pontos: { type: Array, required: true },
  /** Texto do período dos alertas (ex.: "01/2020 a 12/2024"). */
  periodo: { type: String, required: true },
  /** Aba "Por mês": competência da linha (o tooltip marca os alertas que a incluem). */
  competencia: { type: Number, default: null },
  nomeMedico: { type: String, required: true },
});
const emit = defineEmits(['abrir']);

const themeStore = useThemeStore();
const coresVars = computed(() => {
  const tons = CRM_ALERTA_BADGE_TONS[themeStore.isDark ? 'dark' : 'light'];
  return { '--alerta-cor': tons.cor, '--alerta-numero': tons.numero };
});

const tooltip = computed(() => crmAlertasTooltip(props.pontos, {
  periodo: props.periodo,
  competencia: props.competencia,
}));
</script>

<template>
  <button
    type="button"
    class="crm-alertas"
    :style="coresVars"
    :aria-label="`${pontos.length} ${pontos.length === 1 ? 'ponto de atenção' : 'pontos de atenção'} de ${nomeMedico}. Abrir histórico.`"
    v-tooltip.right="tooltip"
    @click.stop="emit('abrir')"
    @keydown.enter.stop
  >
    <i class="pi pi-exclamation-triangle" aria-hidden="true" />
    <span class="crm-alertas-numero">{{ pontos.length }}</span>
  </button>
</template>

<style scoped>
.crm-alertas {
  position: relative;
  display: inline-flex;
  flex-shrink: 0;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  padding: 0;
  border: 1px solid color-mix(in srgb, var(--alerta-cor) 30%, transparent);
  border-radius: 7px;
  background: color-mix(in srgb, var(--alerta-cor) 9%, transparent);
  color: var(--alerta-cor);
  cursor: pointer;
  transition: background .15s ease, border-color .15s ease;
}
.crm-alertas .pi { font-size: .8rem; }
.crm-alertas:hover,
.crm-alertas:focus-visible {
  border-color: color-mix(in srgb, var(--alerta-cor) 55%, transparent);
  background: color-mix(in srgb, var(--alerta-cor) 16%, transparent);
  outline: none;
}
.crm-alertas:focus-visible { box-shadow: 0 0 0 2px color-mix(in srgb, var(--alerta-cor) 35%, transparent); }
.crm-alertas-numero {
  position: absolute;
  top: -7px;
  right: -7px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 16px;
  height: 16px;
  padding: 0 4px;
  border: 2px solid var(--card-bg);
  border-radius: 999px;
  background: var(--alerta-cor);
  color: var(--alerta-numero);
  font-size: .58rem;
  font-weight: 600;
  line-height: 1;
}
</style>
