<script setup>
/**
 * Rodapé padrão das tabelas paginadas: contagem à esquerda ("1–7 de 71
 * janelas") e navegação à direita (Primeira, Anterior, "Página X de Y",
 * Próxima, Última: botões com ícone e legenda, para a área de clique ser
 * ampla), com seletor de linhas por página opcional.
 *
 * Tem sempre a mesma altura e fica sempre visível (com uma página só, a
 * navegação aparece desabilitada), para a tela não se deslocar.
 *
 * Emite `page` com { first, rows, page, pageCount } (page começa em 0), o mesmo
 * formato do evento de página do PrimeVue: nas DataTable entra no slot #footer
 * e chama o mesmo tratador de página da tela; o paginador embutido fica oculto
 * pela classe `com-rodape` (assets/styles/components.css).
 */
import { computed } from 'vue';

const props = defineProps({
  /** Índice (base 0) do primeiro registro da página. */
  first: { type: Number, required: true },
  /** Linhas por página. */
  rows: { type: Number, required: true },
  totalRecords: { type: Number, required: true },
  /** Nome do registro: [singular, plural]. */
  unidade: { type: Array, default: () => ['registro', 'registros'] },
  /** Texto extra depois da contagem (ex.: "severidade Extrema"). */
  detalhe: { type: String, default: '' },
  /** Opções do seletor de linhas por página (vazio = sem seletor). */
  rowsPerPageOptions: { type: Array, default: () => [] },
  disabled: { type: Boolean, default: false },
});
const emit = defineEmits(['page']);

const fmt = (n) => Number(n).toLocaleString('pt-BR');
const pageCount = computed(() => Math.max(1, Math.ceil(props.totalRecords / props.rows)));
const page = computed(() => Math.min(pageCount.value - 1, Math.floor(props.first / props.rows)));
const contagem = computed(() => {
  const total = props.totalRecords;
  const nome = total === 1 ? props.unidade[0] : props.unidade[1];
  if (!total) return `0 ${props.unidade[1]}`;
  const ultimo = Math.min(total, props.first + props.rows);
  return `${fmt(props.first + 1)}–${fmt(ultimo)} de ${fmt(total)} ${nome}`;
});
const naPrimeira = computed(() => page.value === 0);
const naUltima = computed(() => page.value >= pageCount.value - 1);

function ir(novaPagina, rows = props.rows) {
  const contagemPaginas = Math.max(1, Math.ceil(props.totalRecords / rows));
  const alvo = Math.min(Math.max(0, novaPagina), contagemPaginas - 1);
  emit('page', { first: alvo * rows, rows, page: alvo, pageCount: contagemPaginas });
}
function mudarLinhas(evento) {
  const rows = Number(evento.target.value);
  // Mantém à vista o primeiro registro da página atual.
  ir(Math.floor(props.first / rows), rows);
}
</script>

<template>
  <nav class="table-footer" aria-label="Paginação da tabela">
    <span class="tf-contagem" aria-live="polite">
      {{ contagem }}<template v-if="detalhe"> · {{ detalhe }}</template>
    </span>

    <div class="tf-controles">
      <label v-if="rowsPerPageOptions.length" class="tf-linhas">
        <span>Linhas</span>
        <select :value="rows" :disabled="disabled" @change="mudarLinhas">
          <option v-for="opcao in rowsPerPageOptions" :key="opcao" :value="opcao">{{ opcao }}</option>
        </select>
      </label>

      <div class="tf-navegacao">
        <button type="button" class="tf-botao" :disabled="disabled || naPrimeira" aria-label="Primeira página" @click="ir(0)">
          <i class="pi pi-angle-double-left" aria-hidden="true" /><span>Primeira</span>
        </button>
        <button type="button" class="tf-botao" :disabled="disabled || naPrimeira" aria-label="Página anterior" @click="ir(page - 1)">
          <i class="pi pi-angle-left" aria-hidden="true" /><span>Anterior</span>
        </button>
        <span class="tf-pagina">Página {{ fmt(page + 1) }} de {{ fmt(pageCount) }}</span>
        <button type="button" class="tf-botao" :disabled="disabled || naUltima" aria-label="Próxima página" @click="ir(page + 1)">
          <span>Próxima</span><i class="pi pi-angle-right" aria-hidden="true" />
        </button>
        <button type="button" class="tf-botao" :disabled="disabled || naUltima" aria-label="Última página" @click="ir(pageCount - 1)">
          <span>Última</span><i class="pi pi-angle-double-right" aria-hidden="true" />
        </button>
      </div>
    </div>
  </nav>
</template>

<style scoped>
.table-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
  box-sizing: border-box;
  height: 2.5rem;
  padding: 0 .65rem;
  border-top: 1px solid color-mix(in srgb, var(--tabs-border) 65%, transparent);
  background: color-mix(in srgb, var(--text-color) 2%, var(--card-bg));
  color: var(--text-secondary);
  font-size: .74rem;
  font-weight: 400;
}
.tf-contagem { min-width: 0; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.tf-controles { display: flex; align-items: center; gap: 1rem; flex-shrink: 0; }
.tf-linhas { display: inline-flex; align-items: center; gap: .4rem; color: var(--text-muted); }
.tf-linhas select {
  height: 1.7rem;
  padding: 0 .35rem;
  border: 1px solid var(--card-border);
  border-radius: 6px;
  background: var(--card-bg);
  color: var(--text-color);
  font: inherit;
  cursor: pointer;
}
.tf-linhas select:focus-visible { outline: 2px solid var(--primary-color); outline-offset: 1px; }
.tf-navegacao { display: inline-flex; align-items: center; gap: .35rem; }
.tf-pagina { padding: 0 .6rem; color: var(--text-color-85); white-space: nowrap; }
.tf-botao {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: .3rem;
  height: 1.8rem;
  padding: 0 .65rem;
  border: 1px solid var(--card-border);
  border-radius: 6px;
  background: var(--card-bg);
  color: var(--text-color-85);
  font: inherit;
  font-weight: 500;
  white-space: nowrap;
  cursor: pointer;
  transition: color .15s ease, border-color .15s ease, background .15s ease;
}
.tf-botao .pi { font-size: .78rem; }
.tf-botao:hover:not(:disabled) { color: var(--primary-color); border-color: color-mix(in srgb, var(--primary-color) 45%, transparent); background: color-mix(in srgb, var(--primary-color) 8%, transparent); }
.tf-botao:focus-visible { outline: 2px solid var(--primary-color); outline-offset: 1px; }
.tf-botao:disabled { opacity: .4; cursor: default; }
</style>
