<script setup>
/**
 * Seletor de intervalo de meses: botão com o período atual que abre um painel
 * com atalhos à esquerda e dois anos lado a lado (grade de 12 meses cada).
 * Dois cliques escolhem o intervalo (início e fim); passar o mouse entre os
 * cliques pré-visualiza o intervalo. Teclado: setas movem, Enter seleciona,
 * Esc fecha.
 *
 * Competências no formato AAAAMM (número). O componente não guarda o período:
 * emite `select-range` / `select-atalho` e o pai decide.
 */
import { computed, nextTick, ref } from 'vue';
import OverlayPanel from 'primevue/overlaypanel';
import { MONTH_LABELS } from '@/config/constants';

const props = defineProps({
  /** Texto do botão (ex.: "Período da análise · 01/2020 – 12/2024"). */
  rotulo: { type: String, required: true },
  /** Intervalo exibido hoje (destacado ao abrir). */
  inicio: { type: Number, default: null },
  fim: { type: Number, default: null },
  /** Limites da base (AAAAMM). */
  min: { type: Number, required: true },
  max: { type: Number, required: true },
  /**
   * Atalhos: [{ value, label, grade? }]. Com `grade: true` o item não fecha o
   * painel: indica a escolha livre na grade (ex.: "Período personalizado").
   */
  atalhos: { type: Array, default: () => [] },
  atalhoAtivo: { type: String, default: null },
  /** Ícone de calendário à esquerda do texto do botão. */
  mostrarIcone: { type: Boolean, default: true },
  disabled: { type: Boolean, default: false },
});
const emit = defineEmits(['select-range', 'select-atalho']);

const painel = ref(null);
const grade = ref(null);
const anoEsquerda = ref(null);
const ancora = ref(null); // 1º clique
const sobre = ref(null); // mês sob o mouse/foco (pré-visualização)
// Atalho de escolha livre clicado: fica marcado e a grade começa limpa.
const atalhoGrade = ref(null);

const anoMin = computed(() => Math.floor(props.min / 100));
const anoMax = computed(() => Math.floor(props.max / 100));
const anos = computed(() => [anoEsquerda.value, anoEsquerda.value + 1]);

function comp(ano, mes) {
  return ano * 100 + mes;
}
function indice(c) {
  return Math.floor(c / 100) * 12 + (c % 100) - 1;
}
function doIndice(i) {
  return Math.floor(i / 12) * 100 + (i % 12) + 1;
}
function fmt(c) {
  return `${String(c % 100).padStart(2, '0')}/${Math.floor(c / 100)}`;
}
function foraDaBase(c) {
  return c < props.min || c > props.max;
}
function limitarAnoEsquerda(ano) {
  // Sempre dois anos visíveis dentro da base.
  return Math.max(anoMin.value, Math.min(ano, anoMax.value - 1));
}

const faixa = computed(() => {
  if (ancora.value != null) {
    const outro = sobre.value ?? ancora.value;
    return [Math.min(ancora.value, outro), Math.max(ancora.value, outro)];
  }
  if (atalhoGrade.value != null) return null;
  if (props.inicio != null && props.fim != null) return [props.inicio, props.fim];
  return null;
});
function estado(c) {
  const f = faixa.value;
  return {
    'is-fora': foraDaBase(c),
    'is-faixa': !!f && c >= f[0] && c <= f[1],
    'is-inicio': !!f && c === f[0],
    'is-fim': !!f && c === f[1],
    'is-ancora': ancora.value === c,
    'is-previa': ancora.value != null,
  };
}

function abrir(event) {
  if (props.disabled) return;
  ancora.value = null;
  sobre.value = null;
  atalhoGrade.value = null;
  anoEsquerda.value = limitarAnoEsquerda(Math.floor((props.inicio ?? props.max) / 100));
  painel.value.toggle(event);
}
function aoMostrar() {
  nextTick(() => focar(props.inicio ?? props.max));
}

function escolher(c) {
  if (foraDaBase(c)) return;
  if (ancora.value == null) {
    ancora.value = c;
    sobre.value = c;
    return;
  }
  const inicio = Math.min(ancora.value, c);
  const fim = Math.max(ancora.value, c);
  ancora.value = null;
  sobre.value = null;
  atalhoGrade.value = null;
  painel.value.hide();
  emit('select-range', { inicio, fim });
}
function escolherAtalho(atalho) {
  ancora.value = null;
  sobre.value = null;
  if (atalho.grade) {
    // Escolha livre: marca o item, limpa a grade e leva o foco a ela.
    atalhoGrade.value = atalho.value;
    focar(props.inicio ?? props.max);
    return;
  }
  painel.value.hide();
  emit('select-atalho', atalho.value);
}
function navegarAno(delta) {
  anoEsquerda.value = limitarAnoEsquerda(anoEsquerda.value + delta);
}

function focar(c) {
  const alvo = Math.max(props.min, Math.min(props.max, c));
  const ano = Math.floor(alvo / 100);
  if (ano < anoEsquerda.value) anoEsquerda.value = limitarAnoEsquerda(ano);
  else if (ano > anoEsquerda.value + 1) anoEsquerda.value = limitarAnoEsquerda(ano - 1);
  nextTick(() => {
    grade.value?.querySelector(`[data-comp="${alvo}"]`)?.focus();
  });
}
// Grade de 3 linhas x 4 meses por ano: ←/→ andam 1 mês, ↑/↓ andam 4.
const PASSOS = { ArrowLeft: -1, ArrowRight: 1, ArrowUp: -4, ArrowDown: 4 };
function aoTeclar(event, c) {
  const passo = PASSOS[event.key];
  if (!passo) return;
  event.preventDefault();
  const destino = doIndice(indice(c) + passo);
  if (ancora.value != null) sobre.value = destino;
  focar(destino);
}
</script>

<template>
  <button
    type="button"
    class="rp-gatilho"
    :disabled="disabled"
    aria-haspopup="dialog"
    @click="abrir"
  >
    <i v-if="mostrarIcone" class="pi pi-calendar rp-gatilho-icone" aria-hidden="true" />
    <span class="rp-gatilho-texto">{{ rotulo }}</span>
    <i class="pi pi-chevron-down rp-gatilho-seta" aria-hidden="true" />
  </button>

  <OverlayPanel ref="painel" class="rp-painel" :dismissable="true" @show="aoMostrar">
    <div class="rp-corpo" role="dialog" aria-label="Escolher período">
      <ul v-if="atalhos.length" class="rp-atalhos">
        <li v-for="a in atalhos" :key="a.value">
          <button
            type="button"
            class="rp-atalho"
            :class="{ 'is-ativo': atalhoGrade != null ? a.value === atalhoGrade : a.value === atalhoAtivo }"
            :aria-pressed="atalhoGrade != null ? a.value === atalhoGrade : a.value === atalhoAtivo"
            @click="escolherAtalho(a)"
          >
            {{ a.label }}
            <i v-if="a.grade" class="pi pi-angle-right rp-atalho-seta" aria-hidden="true" />
          </button>
        </li>
      </ul>

      <div class="rp-conteudo">
        <div ref="grade" class="mrp-anos" @mouseleave="ancora != null && (sobre = ancora)">
          <section v-for="(ano, i) in anos" :key="ano" class="mrp-ano">
            <header class="mrp-ano-cabecalho">
              <button
                v-if="i === 0"
                type="button"
                class="mrp-nav"
                :disabled="anoEsquerda <= anoMin"
                aria-label="Ano anterior"
                @click="navegarAno(-1)"
              ><i class="pi pi-chevron-left" aria-hidden="true" /></button>
              <span class="mrp-ano-titulo">{{ ano }}</span>
              <button
                v-if="i === 1"
                type="button"
                class="mrp-nav"
                :disabled="anoEsquerda + 1 >= anoMax"
                aria-label="Próximo ano"
                @click="navegarAno(1)"
              ><i class="pi pi-chevron-right" aria-hidden="true" /></button>
            </header>
            <div class="mrp-meses" role="grid">
              <button
                v-for="(nome, m) in MONTH_LABELS"
                :key="m"
                type="button"
                class="mrp-mes"
                :class="estado(comp(ano, m + 1))"
                :data-comp="comp(ano, m + 1)"
                :disabled="foraDaBase(comp(ano, m + 1))"
                :aria-label="fmt(comp(ano, m + 1))"
                :aria-pressed="estado(comp(ano, m + 1))['is-faixa']"
                @click="escolher(comp(ano, m + 1))"
                @mouseenter="ancora != null && (sobre = comp(ano, m + 1))"
                @focus="ancora != null && (sobre = comp(ano, m + 1))"
                @keydown="aoTeclar($event, comp(ano, m + 1))"
              >{{ nome.charAt(0) + nome.slice(1).toLowerCase() }}</button>
            </div>
          </section>
        </div>
        <p class="rp-dica" aria-live="polite">
          <template v-if="ancora != null">
            Início em <strong>{{ fmt(ancora) }}</strong> · clique no mês final
            <span v-if="sobre != null && sobre !== ancora"> ({{ fmt(Math.min(ancora, sobre)) }} – {{ fmt(Math.max(ancora, sobre)) }})</span>
          </template>
          <template v-else>Clique no mês inicial e depois no final</template>
        </p>
      </div>
    </div>
  </OverlayPanel>
</template>

<style>
/* Grade de meses (botão e painel: assets/styles/range-picker.css). OverlayPanel é teleportado para o body: estilos sem scoped, prefixados. */
.mrp-anos { display: flex; gap: 1.25rem; }
.mrp-ano { display: flex; flex-direction: column; gap: .45rem; }
.mrp-ano-cabecalho { display: flex; align-items: center; justify-content: center; position: relative; min-height: 1.75rem; }
.mrp-ano-titulo { font-size: .82rem; font-weight: 600; color: var(--text-color); }
.mrp-nav { position: absolute; top: 0; display: inline-flex; align-items: center; justify-content: center; width: 1.75rem; height: 1.75rem; border: 0; border-radius: 6px; background: transparent; color: var(--text-muted); cursor: pointer; }
.mrp-ano:first-child .mrp-nav { left: 0; }
.mrp-ano:last-child .mrp-nav { right: 0; }
.mrp-nav:hover:not(:disabled), .mrp-nav:focus-visible { background: color-mix(in srgb, var(--text-color) 7%, transparent); color: var(--text-color); outline: none; }
.mrp-nav:disabled { opacity: .3; cursor: default; }
.mrp-meses { display: grid; grid-template-columns: repeat(4, 3.1rem); row-gap: .3rem; }
.mrp-mes { height: 2rem; padding: 0; border: 0; border-radius: 0; background: transparent; color: var(--text-color); font: inherit; font-size: .74rem; cursor: pointer; }
.mrp-mes:hover:not(:disabled) { background: color-mix(in srgb, var(--text-color) 7%, transparent); border-radius: 6px; }
.mrp-mes:focus-visible { outline: 2px solid color-mix(in srgb, var(--primary-color) 70%, transparent); outline-offset: -2px; border-radius: 6px; }
.mrp-mes.is-faixa { background: color-mix(in srgb, var(--primary-color) 14%, transparent); color: var(--text-color); border-radius: 0; }
.mrp-mes.is-faixa.is-previa { background: color-mix(in srgb, var(--primary-color) 9%, transparent); }
.mrp-mes.is-inicio, .mrp-mes.is-fim, .mrp-mes.is-ancora { background: var(--primary-color); color: var(--card-bg); font-weight: 600; }
.mrp-mes.is-inicio { border-top-left-radius: 6px; border-bottom-left-radius: 6px; }
.mrp-mes.is-fim { border-top-right-radius: 6px; border-bottom-right-radius: 6px; }
/* Início/fim na borda da linha da grade: arredonda para não "vazar". */
.mrp-mes.is-faixa:nth-child(4n+1) { border-top-left-radius: 6px; border-bottom-left-radius: 6px; }
.mrp-mes.is-faixa:nth-child(4n) { border-top-right-radius: 6px; border-bottom-right-radius: 6px; }
.mrp-mes:disabled { color: var(--text-muted); opacity: .35; cursor: default; }
</style>
