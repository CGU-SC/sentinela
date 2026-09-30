<script setup>
/**
 * Seletor numérico: faixa (ex.: % de não comprovação, "De" / "Até") ou limite
 * único (`unico`, ex.: valor mínimo sem comprovação, "A partir de"). Botão com
 * o valor atual que abre um painel com atalhos à esquerda e o valor
 * personalizado à direita (campos com − e +). O valor personalizado só é
 * aplicado no botão Aplicar ou com Enter, para não disparar uma consulta a
 * cada número.
 *
 * O componente não guarda o valor: emite `select-range` e o pai decide.
 * Botão e painel: assets/styles/range-picker.css (mesmo visual do MonthRangePicker).
 */
import { computed, nextTick, ref } from 'vue';
import OverlayPanel from 'primevue/overlaypanel';

const props = defineProps({
  /** Valor aplicado hoje: [inicio, fim] (faixa) ou [limite] (unico). */
  valor: { type: Array, required: true },
  /** Limite único ("A partir de") em vez de faixa. */
  unico: { type: Boolean, default: false },
  min: { type: Number, required: true },
  max: { type: Number, required: true },
  passo: { type: Number, default: 1 },
  /** Prefixo/sufixo exibidos junto dos campos (ex.: "R$", "%"). */
  prefixo: { type: String, default: '' },
  sufixo: { type: String, default: '' },
  /** Formata um número para mensagens e pré-visualização. */
  formatar: { type: Function, default: null },
  rotuloPersonalizado: { type: String, default: 'Faixa personalizada' },
  rotuloCampo: { type: String, default: 'A partir de' },
  /** Atalhos: [{ value, label, faixa: [inicio, fim] ou [limite] }]. */
  atalhos: { type: Array, default: () => [] },
  /** Texto do botão. */
  rotulo: { type: String, required: true },
  disabled: { type: Boolean, default: false },
  icone: { type: String, default: 'pi-percentage' },
});
const emit = defineEmits(['select-range']);

const painel = ref(null);
const campoInicio = ref(null);
const inicio = ref(props.valor[0]);
const fim = ref(props.unico ? null : props.valor[1]);
const editando = ref(false); // valor personalizado alterado e ainda não aplicado

function fmt(v) {
  return props.formatar ? props.formatar(v) : `${props.prefixo}${v}${props.sufixo}`;
}
function iguais(a, b) {
  return a.length === b.length && a.every((v, i) => v === b[i]);
}
const atalhoAtivo = computed(() => {
  if (editando.value) return 'personalizado';
  return props.atalhos.find((x) => iguais(x.faixa, props.valor))?.value ?? 'personalizado';
});
const erro = computed(() => {
  const limites = `Use valores entre ${fmt(props.min)} e ${fmt(props.max)}.`;
  if (props.unico) {
    if (inicio.value === '' || !Number.isFinite(Number(inicio.value))) return 'Informe o valor.';
    const a = Number(inicio.value);
    return a < props.min || a > props.max ? limites : null;
  }
  if (inicio.value === '' || fim.value === '') return 'Informe os dois valores.';
  const a = Number(inicio.value);
  const b = Number(fim.value);
  if (!Number.isFinite(a) || !Number.isFinite(b)) return 'Informe os dois valores.';
  if (a < props.min || b > props.max) return limites;
  if (a >= b) return 'O início deve ser menor que o fim.';
  return null;
});
const dica = computed(() => {
  if (erro.value) return erro.value;
  return props.unico
    ? `A partir de ${fmt(Number(inicio.value))} · clique em Aplicar (ou Enter).`
    : 'Ajuste os valores e clique em Aplicar (ou Enter).';
});

function abrir(event) {
  if (props.disabled) return;
  inicio.value = props.valor[0];
  fim.value = props.unico ? null : props.valor[1];
  editando.value = false;
  painel.value.toggle(event);
}
function aplicarFaixa(faixa) {
  painel.value.hide();
  editando.value = false;
  if (iguais(faixa, props.valor)) return;
  emit('select-range', [...faixa]);
}
function escolherAtalho(atalho) {
  aplicarFaixa(atalho.faixa);
}
function focarPersonalizado() {
  editando.value = true;
  nextTick(() => campoInicio.value?.focus());
}
function ajustar(campo, delta) {
  editando.value = true;
  const alvo = campo === 'inicio' ? inicio : fim;
  const atual = Number(alvo.value);
  const base = Number.isFinite(atual) ? atual : (campo === 'inicio' ? props.min : props.max);
  alvo.value = Math.max(props.min, Math.min(props.max, base + delta * props.passo));
}
function aplicarPersonalizado() {
  if (erro.value) return;
  aplicarFaixa(props.unico ? [Number(inicio.value)] : [Number(inicio.value), Number(fim.value)]);
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
    <i class="pi rp-gatilho-icone" :class="icone" aria-hidden="true" />
    <span class="rp-gatilho-texto">{{ rotulo }}</span>
    <i class="pi pi-chevron-down rp-gatilho-seta" aria-hidden="true" />
  </button>

  <OverlayPanel ref="painel" class="rp-painel" :dismissable="true">
    <div class="rp-corpo" role="dialog" aria-label="Escolher faixa">
      <ul class="rp-atalhos">
        <li v-for="a in atalhos" :key="a.value">
          <button
            type="button"
            class="rp-atalho"
            :class="{ 'is-ativo': a.value === atalhoAtivo }"
            :aria-pressed="a.value === atalhoAtivo"
            @click="escolherAtalho(a)"
          >{{ a.label }}</button>
        </li>
        <li>
          <button
            type="button"
            class="rp-atalho"
            :class="{ 'is-ativo': atalhoAtivo === 'personalizado' }"
            :aria-pressed="atalhoAtivo === 'personalizado'"
            @click="focarPersonalizado"
          >
            {{ rotuloPersonalizado }}
            <i class="pi pi-angle-right rp-atalho-seta" aria-hidden="true" />
          </button>
        </li>
      </ul>

      <form class="rp-conteudo nrp-faixa" @submit.prevent="aplicarPersonalizado">
        <div class="nrp-campos">
          <label class="nrp-campo">
            <span>{{ unico ? rotuloCampo : 'De' }}</span>
            <span class="nrp-entrada">
              <button type="button" class="nrp-passo" aria-label="Diminuir o início" @click="ajustar('inicio', -1)">
                <i class="pi pi-minus" aria-hidden="true" />
              </button>
              <span v-if="prefixo" class="nrp-unidade">{{ prefixo }}</span>
              <input
                ref="campoInicio"
                v-model.number="inicio"
                type="number"
                inputmode="numeric"
                :min="min"
                :max="max"
                :step="passo"
                class="nrp-numero"
                :class="{ 'nrp-numero--largo': unico }"
                :aria-label="unico ? rotuloCampo : 'Valor inicial'"
                @input="editando = true"
              />
              <span v-if="sufixo" class="nrp-unidade">{{ sufixo }}</span>
              <button type="button" class="nrp-passo" aria-label="Aumentar o início" @click="ajustar('inicio', 1)">
                <i class="pi pi-plus" aria-hidden="true" />
              </button>
            </span>
          </label>
          <label v-if="!unico" class="nrp-campo">
            <span>Até</span>
            <span class="nrp-entrada">
              <button type="button" class="nrp-passo" aria-label="Diminuir o fim" @click="ajustar('fim', -1)">
                <i class="pi pi-minus" aria-hidden="true" />
              </button>
              <span v-if="prefixo" class="nrp-unidade">{{ prefixo }}</span>
              <input
                v-model.number="fim"
                type="number"
                inputmode="numeric"
                :min="min"
                :max="max"
                :step="passo"
                class="nrp-numero"
                aria-label="Valor final"
                @input="editando = true"
              />
              <span v-if="sufixo" class="nrp-unidade">{{ sufixo }}</span>
              <button type="button" class="nrp-passo" aria-label="Aumentar o fim" @click="ajustar('fim', 1)">
                <i class="pi pi-plus" aria-hidden="true" />
              </button>
            </span>
          </label>
        </div>
        <button type="submit" class="nrp-aplicar" :disabled="!!erro">Aplicar</button>
        <p class="rp-dica" :class="{ 'is-erro': !!erro }" aria-live="polite">{{ dica }}</p>
      </form>
    </div>
  </OverlayPanel>
</template>

<style>
/* Faixa personalizada (botão e painel: assets/styles/range-picker.css). */
.nrp-faixa { min-width: 15rem; }
.nrp-campos { display: flex; flex-direction: column; gap: .6rem; }
.nrp-campo { display: flex; flex-direction: column; gap: .25rem; font-size: .62rem; font-weight: 600; letter-spacing: .06em; text-transform: uppercase; color: var(--text-muted); }
.nrp-entrada { display: flex; align-items: center; gap: .35rem; }
.nrp-numero { width: 4.5rem; height: 2rem; padding: 0 .5rem; border: 1px solid var(--card-border); border-radius: 6px; background: var(--card-bg); color: var(--text-color); font: inherit; font-size: .8rem; text-align: right; -moz-appearance: textfield; appearance: textfield; }
.nrp-numero--largo { width: 7.5rem; }
.nrp-numero::-webkit-outer-spin-button, .nrp-numero::-webkit-inner-spin-button { -webkit-appearance: none; margin: 0; }
.nrp-numero:focus-visible { outline: 2px solid color-mix(in srgb, var(--primary-color) 60%, transparent); outline-offset: 1px; }
.nrp-unidade { color: var(--text-muted); font-size: .76rem; text-transform: none; letter-spacing: 0; }
.nrp-passo { display: inline-flex; align-items: center; justify-content: center; width: 2rem; height: 2rem; padding: 0; border: 1px solid var(--card-border); border-radius: 6px; background: transparent; color: var(--text-secondary); cursor: pointer; }
.nrp-passo .pi { font-size: .65rem; }
.nrp-passo:hover, .nrp-passo:focus-visible { border-color: var(--primary-color); color: var(--primary-color); outline: none; }
.nrp-aplicar { align-self: flex-end; min-height: 2rem; padding: 0 1rem; border: 0; border-radius: 6px; background: var(--primary-color); color: var(--card-bg); font: inherit; font-size: .76rem; font-weight: 600; cursor: pointer; }
.nrp-aplicar:disabled { opacity: .45; cursor: default; }
.nrp-aplicar:focus-visible { outline: 2px solid color-mix(in srgb, var(--primary-color) 60%, transparent); outline-offset: 2px; }
</style>
