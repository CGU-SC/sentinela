<script setup>
/**
 * Seletor de uma opção: botão com o valor atual que abre um painel com a
 * lista de opções; clicar numa opção aplica e fecha.
 *
 * Mesmo visual do NumberRangePicker / MultiOptionPicker
 * (assets/styles/range-picker.css). O componente não guarda o valor: emite
 * `select` com o value da opção e o pai decide.
 */
import { computed, ref } from 'vue';
import OverlayPanel from 'primevue/overlaypanel';

const props = defineProps({
  /** Valor aplicado hoje (value de uma das opções). */
  valor: { type: [String, Number], default: null },
  /** Opções: [{ value, label }]. */
  opcoes: { type: Array, required: true },
  /** Nome do controle, para leitores de tela. */
  rotuloAcessivel: { type: String, required: true },
  disabled: { type: Boolean, default: false },
});
const emit = defineEmits(['select']);

const painel = ref(null);
const atual = computed(() => {
  const opcao = props.opcoes.find((o) => o.value === props.valor);
  if (!opcao) throw new Error(`OptionPicker: valor sem opção correspondente: ${props.valor}`);
  return opcao;
});

function abrir(event) {
  if (!props.disabled) painel.value.toggle(event);
}
function escolher(opcao) {
  painel.value.hide();
  if (opcao.value !== props.valor) emit('select', opcao.value);
}
</script>

<template>
  <button
    type="button"
    class="rp-gatilho"
    :disabled="disabled"
    aria-haspopup="listbox"
    :aria-label="`${rotuloAcessivel}: ${atual.label}`"
    @click="abrir"
  >
    <span class="rp-gatilho-texto">{{ atual.label }}</span>
    <i class="pi pi-chevron-down rp-gatilho-seta" aria-hidden="true" />
  </button>

  <OverlayPanel ref="painel" class="rp-painel" :dismissable="true">
    <ul class="rp-atalhos op-lista" role="listbox" :aria-label="rotuloAcessivel">
      <li v-for="o in opcoes" :key="String(o.value)">
        <button
          type="button"
          role="option"
          class="rp-atalho"
          :class="{ 'is-ativo': o.value === valor }"
          :aria-selected="o.value === valor"
          @click="escolher(o)"
        >{{ o.label }}</button>
      </li>
    </ul>
  </OverlayPanel>
</template>

<style>
/* Lista sozinha no painel: sem a borda que separa atalhos do conteúdo. */
/* Fora de .rp-corpo: sem isto a lista herdava 16px do body. */
.op-lista { border-right: 0; font-size: .8125rem; }
</style>
