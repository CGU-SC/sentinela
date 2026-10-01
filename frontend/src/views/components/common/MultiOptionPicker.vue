<script setup>
/**
 * Seletor de várias opções (ex.: UFs): botão com o valor atual que abre um
 * painel com atalhos à esquerda (aplicam na hora) e a grade de opções à
 * direita. A seleção manual só é aplicada no botão Aplicar (ou Enter), para
 * não disparar uma consulta a cada opção marcada.
 *
 * Mesmo visual do NumberRangePicker / MonthRangePicker
 * (assets/styles/range-picker.css). O componente não guarda o valor: emite
 * `select` com a lista ordenada e o pai decide.
 */
import { computed, ref } from 'vue';
import OverlayPanel from 'primevue/overlaypanel';

const props = defineProps({
  /** Opções selecionadas hoje (vazio = todas / sem filtro). */
  valor: { type: Array, required: true },
  /** Todas as opções possíveis, na ordem da grade. */
  opcoes: { type: Array, required: true },
  /** Atalhos: [{ value, label, selecao: [...] }]; selecao vazia = todas. */
  atalhos: { type: Array, default: () => [] },
  /** Texto do botão. */
  rotulo: { type: String, required: true },
  /** Nome das opções no plural, para a contagem ("3 UFs selecionadas"). */
  nomePlural: { type: String, default: 'opções' },
  colunas: { type: Number, default: 6 },
  disabled: { type: Boolean, default: false },
});
const emit = defineEmits(['select']);

const painel = ref(null);
const rascunho = ref(new Set());

function ordenada(lista) {
  return [...lista].sort((a, b) => props.opcoes.indexOf(a) - props.opcoes.indexOf(b));
}
function mesmaSelecao(a, b) {
  return a.length === b.length && a.every((v) => b.includes(v));
}
const atalhoAtivo = computed(() => props.atalhos.find((a) => mesmaSelecao(a.selecao, props.valor))?.value ?? null);
const alterado = computed(() => !mesmaSelecao([...rascunho.value], props.valor));
const resumo = computed(() => {
  const n = rascunho.value.size;
  return n ? `${n} ${n === 1 ? 'selecionada' : 'selecionadas'}` : `Nenhuma marcada = todas as ${props.nomePlural}`;
});

function abrir(event) {
  if (props.disabled) return;
  rascunho.value = new Set(props.valor);
  painel.value.toggle(event);
}
function aplicarSelecao(lista) {
  painel.value.hide();
  const nova = ordenada(lista);
  if (mesmaSelecao(nova, props.valor)) return;
  emit('select', nova);
}
function alternar(opcao) {
  const nova = new Set(rascunho.value);
  if (nova.has(opcao)) nova.delete(opcao);
  else nova.add(opcao);
  rascunho.value = nova;
}
function limparRascunho() {
  rascunho.value = new Set();
}
function aplicar() {
  aplicarSelecao([...rascunho.value]);
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
    <span class="rp-gatilho-texto">{{ rotulo }}</span>
    <i class="pi pi-chevron-down rp-gatilho-seta" aria-hidden="true" />
  </button>

  <OverlayPanel ref="painel" class="rp-painel" :dismissable="true">
    <div class="rp-corpo" role="dialog" :aria-label="`Escolher ${nomePlural}`">
      <ul v-if="atalhos.length" class="rp-atalhos">
        <li v-for="a in atalhos" :key="a.value">
          <button
            type="button"
            class="rp-atalho"
            :class="{ 'is-ativo': a.value === atalhoAtivo }"
            :aria-pressed="a.value === atalhoAtivo"
            @click="aplicarSelecao(a.selecao)"
          >{{ a.label }}</button>
        </li>
      </ul>

      <form class="rp-conteudo mop-conteudo" @submit.prevent="aplicar" @keydown.enter.prevent="aplicar">
        <div class="mop-grade" role="group" :aria-label="nomePlural" :style="{ gridTemplateColumns: `repeat(${colunas}, minmax(0, 1fr))` }">
          <button
            v-for="opcao in opcoes"
            :key="opcao"
            type="button"
            class="mop-opcao"
            :class="{ 'is-ativa': rascunho.has(opcao) }"
            :aria-pressed="rascunho.has(opcao)"
            @click="alternar(opcao)"
          >{{ opcao }}</button>
        </div>
        <div class="mop-rodape">
          <span class="mop-resumo">{{ resumo }}</span>
          <button type="button" class="mop-limpar" :disabled="!rascunho.size" @click="limparRascunho">Limpar</button>
        </div>
        <button type="submit" class="mop-aplicar" :disabled="!alterado">Aplicar</button>
        <p class="rp-dica">Marque as opções e clique em Aplicar (ou Enter).</p>
      </form>
    </div>
  </OverlayPanel>
</template>

<style>
/* Grade de opções (botão e painel: assets/styles/range-picker.css). Sem scoped:
   o OverlayPanel é teleportado para o body; classes prefixadas com mop-. */
.mop-conteudo { min-width: 16rem; }
.mop-grade { display: grid; gap: 4px; }
.mop-opcao { min-height: 1.9rem; padding: 0 .3rem; border: 1px solid var(--card-border); border-radius: 6px; background: transparent; color: var(--text-secondary); font: inherit; font-size: .72rem; font-weight: 500; cursor: pointer; transition: background .15s ease, color .15s ease, border-color .15s ease; }
.mop-opcao:hover { color: var(--text-color); background: color-mix(in srgb, var(--text-color) 6%, transparent); }
.mop-opcao:focus-visible { outline: 2px solid color-mix(in srgb, var(--primary-color) 60%, transparent); outline-offset: 1px; }
.mop-opcao.is-ativa { border-color: transparent; background: color-mix(in srgb, var(--primary-color) 16%, transparent); color: var(--primary-color); box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--primary-color) 45%, transparent); font-weight: 600; }
.mop-rodape { display: flex; align-items: center; justify-content: space-between; gap: .5rem; }
.mop-resumo { color: var(--text-muted); font-size: .7rem; }
.mop-limpar { padding: .15rem .4rem; border: 0; border-radius: 5px; background: transparent; color: var(--color-error); font: inherit; font-size: .7rem; font-weight: 500; cursor: pointer; }
.mop-limpar:hover:not(:disabled) { background: color-mix(in srgb, var(--color-error) 10%, transparent); }
.mop-limpar:disabled { color: var(--text-muted); opacity: .5; cursor: default; }
.mop-aplicar { align-self: flex-end; min-height: 2rem; padding: 0 1rem; border: 0; border-radius: 6px; background: var(--primary-color); color: var(--card-bg); font: inherit; font-size: .76rem; font-weight: 600; cursor: pointer; }
.mop-aplicar:disabled { opacity: .45; cursor: default; }
.mop-aplicar:focus-visible { outline: 2px solid color-mix(in srgb, var(--primary-color) 60%, transparent); outline-offset: 2px; }
</style>
