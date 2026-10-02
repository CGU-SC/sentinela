<script setup>
/**
 * Mini gráfico de barras mensais de um CRM: uma barra por mês com prescrição,
 * num eixo de `total` meses, com tooltip em cada barra.
 *
 * É o mesmo desenho na "Linha do tempo" do ranking de /analises e nas colunas
 * "Atuação na farmácia" (histórico do CRM e CRMs de interesse do
 * estabelecimento). Só os meses com prescrição viram elemento (posicionados
 * por percentual): listas longas não criam um elemento por mês vazio.
 *
 * Quem chama decide a escala: `altura` é a fração (0 a 1) da altura do gráfico;
 * o mínimo visível (1,5/16 ≈ 3 px) é aplicado aqui. A cor vem da faixa do ×P95
 * (crmFaixaP95 → CRM_TAXA_P95_TONS).
 */
import { computed } from 'vue';
import { CRM_TAXA_P95_TONS, DATA_NEUTRAL } from '@/config/colors';
import { useThemeStore } from '@/stores/theme';

const props = defineProps({
  /** Número de meses do eixo. */
  total: { type: Number, required: true },
  /** Barras: [{ x, altura, cortada, faixa, tooltip }]; x = índice do mês no eixo (base 0). */
  barras: { type: Array, required: true },
  /** Índices (x) dos meses de janeiro, para a linha divisória de ano. */
  divisores: { type: Array, default: () => [] },
  /** Descrição do gráfico para leitores de tela. */
  rotulo: { type: String, default: null },
});

const ALTURA_MINIMA = 1.5 / 16;
const themeStore = useThemeStore();
const cores = computed(() => {
  const tema = themeStore.isDark ? 'dark' : 'light';
  const tons = CRM_TAXA_P95_TONS[tema];
  return {
    '--cbm-neutra': DATA_NEUTRAL[tema].strong,
    '--cbm-leve': tons.leve,
    '--cbm-media': tons.media,
    '--cbm-media-forte': tons.mediaForte,
    '--cbm-forte': tons.forte,
    '--cbm-muito-forte': tons.muitoForte,
    '--cbm-extrema': tons.extrema,
  };
});
const largura = computed(() => `${100 / props.total}%`);
function esquerda(x) {
  return `${(x / props.total) * 100}%`;
}
function altura(barra) {
  return `${Math.max(ALTURA_MINIMA, Math.min(1, barra.altura)) * 100}%`;
}
</script>

<template>
  <span class="cbm" :style="cores" :role="rotulo ? 'img' : null" :aria-label="rotulo">
    <span
      v-for="x in divisores"
      :key="`ano-${x}`"
      class="cbm-ano"
      :style="{ left: esquerda(x) }"
      aria-hidden="true"
    />
    <span
      v-for="barra in barras"
      :key="barra.x"
      class="cbm-mes"
      :style="{ left: esquerda(barra.x), width: largura }"
      v-tooltip.top="barra.tooltip"
    >
      <span
        class="cbm-barra"
        :class="[barra.faixa ? `is-${barra.faixa}` : null, { 'is-cortada': barra.cortada }]"
        :style="{ height: altura(barra) }"
      />
    </span>
  </span>
</template>

<style scoped>
.cbm { position: relative; display: block; height: 34px; border-bottom: 1px solid var(--card-border); }
.cbm-ano { position: absolute; top: 0; bottom: 0; width: 0; border-left: 1px solid color-mix(in srgb, var(--card-border) 70%, transparent); pointer-events: none; }
.cbm-mes { position: absolute; top: 0; bottom: 0; display: flex; align-items: flex-end; justify-content: center; }
.cbm-mes:hover { background: color-mix(in srgb, var(--text-color) 8%, transparent); }
.cbm-barra { position: relative; width: 72%; max-width: 10px; border-radius: 1px 1px 0 0; background: var(--cbm-neutra); }
/* Mês acima do teto da escala: barra cheia com marca escura no topo. */
.cbm-barra.is-cortada::after { content: ''; position: absolute; top: 0; left: 0; right: 0; height: 3px; background: var(--text-color); opacity: .55; }
.cbm-barra.is-leve { background: var(--cbm-leve); }
.cbm-barra.is-media { background: var(--cbm-media); }
.cbm-barra.is-media-forte { background: var(--cbm-media-forte); }
.cbm-barra.is-forte { background: var(--cbm-forte); }
.cbm-barra.is-muito-forte { background: var(--cbm-muito-forte); }
.cbm-barra.is-extrema { background: var(--cbm-extrema); }
</style>
