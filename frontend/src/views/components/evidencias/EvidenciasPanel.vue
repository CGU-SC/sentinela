<script setup>
import { computed, nextTick, ref, watch } from 'vue';
import { useRouter } from 'vue-router';
import Sidebar from 'primevue/sidebar';
import { useToast } from 'primevue/usetoast';
import { useEvidenciasStore } from '@/stores/evidencias';
import { API_ENDPOINTS } from '@/config/api';
import { downloadBlobFromResponse } from '@/utils/download';
import { getApiErrorMessage } from '@/utils/apiErrors';
import {
  TIPO_EVIDENCIA_OPCOES,
  dataHoraCurta,
  quandoEvidencia,
  resumoEvidencia,
  tipoEvidencia,
} from '@/utils/evidencias';

/**
 * Painel lateral com as evidências de UMA farmácia.
 * contexto="farmacia": aberto na tela do estabelecimento.
 * contexto="listas": aberto em /listas, sem sair da lista.
 */
const props = defineProps({
  cnpj: { type: String, required: true },
  razaoSocial: { type: String, default: '' },
  contexto: { type: String, default: 'farmacia', validator: (v) => ['farmacia', 'listas'].includes(v) },
});

const store = useEvidenciasStore();
const router = useRouter();
const toast = useToast();

const cnpjDigits = computed(() => props.cnpj.replace(/\D/g, ''));
const filtroTipo = ref(null);
const editandoId = ref(null);
const notaRascunho = ref('');
const removendoId = ref(null);
const ocupadoId = ref(null);
const editorRef = ref(null);
const exportando = ref(false);

const visivel = computed({
  get: () => store.painelAberto,
  set: (valor) => { store.painelAberto = valor; },
});

const todas = computed(() => store.listarDoCnpj(cnpjDigits.value));
const lista = computed(() => (filtroTipo.value
  ? todas.value.filter((ev) => ev.tipo === filtroTipo.value)
  : todas.value));

const contagemPorTipo = computed(() => {
  const contagem = { dia: 0, hora: 0, autorizacao: 0 };
  for (const ev of todas.value) contagem[ev.tipo] += 1;
  return contagem;
});

watch(visivel, (aberto) => {
  if (aberto) store.garantirCarregado();
  else cancelarEdicao();
});

watch(cnpjDigits, () => {
  filtroTipo.value = null;
  cancelarEdicao();
});

function rotuloFiltro(opcao) {
  if (!opcao.value) return `${opcao.label} (${todas.value.length})`;
  return `${opcao.label} (${contagemPorTipo.value[opcao.value]})`;
}

async function editarNota(ev) {
  removendoId.value = null;
  editandoId.value = ev.id;
  notaRascunho.value = ev.nota || '';
  await nextTick();
  editorRef.value?.[0]?.focus();
}

function cancelarEdicao() {
  editandoId.value = null;
  notaRascunho.value = '';
  removendoId.value = null;
}

async function salvarNota(ev) {
  ocupadoId.value = ev.id;
  try {
    await store.atualizarNota(ev.id, notaRascunho.value);
    cancelarEdicao();
  } catch (error) {
    toast.add({ severity: 'error', summary: 'Nota não salva', detail: error.message, life: 7000 });
  } finally {
    ocupadoId.value = null;
  }
}

async function remover(ev) {
  ocupadoId.value = ev.id;
  try {
    await store.remover(ev.id);
    removendoId.value = null;
    toast.add({ severity: 'info', summary: 'Evidência removida', detail: quandoEvidencia(ev), life: 2500 });
  } catch (error) {
    toast.add({ severity: 'error', summary: 'Evidência não removida', detail: error.message, life: 7000 });
  } finally {
    ocupadoId.value = null;
  }
}

async function abrir(ev) {
  visivel.value = false;
  // Em /listas a tela do CNPJ ainda não está aberta: a navegação fica pendente até ela carregar.
  await store.irPara(ev, router, props.contexto === 'farmacia' ? cnpjDigits.value : null);
}

function abrirFarmacia() {
  visivel.value = false;
  router.push({ name: 'EstablishmentDetail', params: { cnpj: cnpjDigits.value } });
}

function irParaListas() {
  visivel.value = false;
  router.push({ path: '/listas', query: { aba: 'evidencias', cnpj: cnpjDigits.value } });
}

async function exportarExcel() {
  if (exportando.value || todas.value.length === 0) return;
  exportando.value = true;
  try {
    const response = await fetch(API_ENDPOINTS.evidenciasExportar(cnpjDigits.value));
    if (!response.ok) {
      throw new Error(await getApiErrorMessage(response, `Falha HTTP ${response.status} ao gerar o Excel das evidências.`));
    }
    const resultado = await downloadBlobFromResponse(response, `evidencias_${cnpjDigits.value}.xlsx`);
    if (resultado?.desktop) {
      toast.add({
        group: 'download',
        severity: 'success',
        summary: 'Excel das evidências salvo',
        detail: `Arquivo salvo em notas_tecnicas\\${resultado.filename}.`,
        data: { path: resultado.path, icon: 'pi-file-excel' },
      });
    } else {
      toast.add({ severity: 'success', summary: 'Excel das evidências baixado', detail: resultado?.filename, life: 4000 });
    }
  } catch (error) {
    toast.add({ severity: 'error', summary: 'Falha na exportação', detail: error.message, life: 7000 });
  } finally {
    exportando.value = false;
  }
}

function onEditorKeydown(event, ev) {
  if (event.key === 'Escape') {
    event.stopPropagation();
    cancelarEdicao();
  } else if (event.key === 'Enter' && (event.ctrlKey || event.metaKey)) {
    event.preventDefault();
    salvarNota(ev);
  }
}
</script>

<template>
  <Sidebar v-model:visible="visivel" position="right" class="evid-sidebar" :show-close-icon="false">
    <template #header>
      <div class="evid-sb-header">
        <div class="evid-sb-title">
          <i class="pi pi-flag-fill" aria-hidden="true" />
          <div>
            <h3>Evidências <span class="evid-sb-count">{{ todas.length }}</span></h3>
            <p v-if="razaoSocial">{{ razaoSocial }}</p>
          </div>
        </div>
        <button type="button" class="evid-sb-close" aria-label="Fechar painel de evidências" @click="visivel = false">
          <i class="pi pi-times" aria-hidden="true" />
        </button>
      </div>
    </template>

    <div class="evid-sb-body">
      <div v-if="store.loadState === 'loading' || store.loadState === 'idle'" class="evid-sb-state" role="status">
        <i class="pi pi-spin pi-spinner" aria-hidden="true" />
        <p>Carregando evidências...</p>
      </div>

      <div v-else-if="store.loadState === 'error'" class="evid-sb-state is-error" role="alert">
        <i class="pi pi-exclamation-triangle" aria-hidden="true" />
        <p>{{ store.error }}</p>
        <button type="button" class="evid-sb-btn" @click="store.carregar()">Tentar novamente</button>
      </div>

      <div v-else-if="todas.length === 0" class="evid-sb-state">
        <i class="pi pi-flag" aria-hidden="true" />
        <p>Nenhuma evidência marcada nesta farmácia.</p>
        <span>
          Em <strong>Análise de Autorizações › Cronologia</strong>, use “Marcar evidência” nos painéis do dia e da hora,
          ou a bandeira em cada linha do Raio-X.
        </span>
      </div>

      <template v-else>
        <div class="evid-sb-filtros" role="radiogroup" aria-label="Filtrar evidências por tipo">
          <button
            v-for="opcao in TIPO_EVIDENCIA_OPCOES"
            :key="String(opcao.value)"
            type="button"
            role="radio"
            :aria-checked="filtroTipo === opcao.value"
            :class="['evid-sb-filtro', { 'is-active': filtroTipo === opcao.value }]"
            @click="filtroTipo = opcao.value"
          >{{ rotuloFiltro(opcao) }}</button>
        </div>

        <p v-if="lista.length === 0" class="evid-sb-vazio">Nenhuma evidência deste tipo.</p>

        <ol class="evid-sb-lista">
          <li v-for="ev in lista" :key="ev.id" class="evid-item" :class="{ 'is-busy': ocupadoId === ev.id }">
            <div class="evid-item-head">
              <span class="evid-item-tipo">
                <i :class="['pi', tipoEvidencia(ev.tipo).icon]" aria-hidden="true" />
                {{ tipoEvidencia(ev.tipo).label }}
              </span>
              <span class="evid-item-quando">{{ quandoEvidencia(ev) }}</span>
              <span class="evid-item-acoes">
                <button type="button" class="evid-icon-btn" :aria-label="`Abrir na Cronologia: ${quandoEvidencia(ev)}`" @click="abrir(ev)">
                  <i class="pi pi-arrow-up-right" aria-hidden="true" />
                </button>
                <button type="button" class="evid-icon-btn" :aria-label="`Editar nota: ${quandoEvidencia(ev)}`" @click="editarNota(ev)">
                  <i class="pi pi-pencil" aria-hidden="true" />
                </button>
                <button
                  type="button"
                  class="evid-icon-btn is-danger"
                  :aria-label="`Remover evidência: ${quandoEvidencia(ev)}`"
                  @click="removendoId = ev.id; editandoId = null"
                >
                  <i class="pi pi-trash" aria-hidden="true" />
                </button>
              </span>
            </div>

            <p class="evid-item-resumo">{{ resumoEvidencia(ev) }}</p>

            <div v-if="editandoId === ev.id" class="evid-item-editor">
              <textarea
                ref="editorRef"
                v-model="notaRascunho"
                rows="3"
                maxlength="2000"
                aria-label="Nota do auditor"
                placeholder="Nota do auditor"
                @keydown="onEditorKeydown($event, ev)"
              />
              <div class="evid-item-editor-acoes">
                <button type="button" class="evid-sb-btn" @click="cancelarEdicao">Cancelar</button>
                <button type="button" class="evid-sb-btn is-primary" :disabled="ocupadoId === ev.id" @click="salvarNota(ev)">Salvar nota</button>
              </div>
            </div>
            <p v-else-if="ev.nota" class="evid-item-nota">{{ ev.nota }}</p>
            <p v-else class="evid-item-nota is-vazia">Sem nota</p>

            <div v-if="removendoId === ev.id" class="evid-item-confirma" role="alert">
              <span>Remover esta evidência?</span>
              <button type="button" class="evid-sb-btn" @click="removendoId = null">Cancelar</button>
              <button type="button" class="evid-sb-btn is-danger" :disabled="ocupadoId === ev.id" @click="remover(ev)">Remover</button>
            </div>

            <span class="evid-item-meta">Marcada em {{ dataHoraCurta(ev.criado_em) }}</span>
          </li>
        </ol>
      </template>
    </div>

    <footer class="evid-sb-footer">
      <button
        type="button"
        class="evid-sb-btn evid-sb-export"
        :disabled="exportando || store.loadState !== 'ready' || todas.length === 0"
        @click="exportarExcel"
      >
        <i :class="['pi', exportando ? 'pi-spin pi-spinner' : 'pi-file-excel']" aria-hidden="true" />
        Exportar Excel
      </button>
      <button v-if="contexto === 'listas'" type="button" class="evid-sb-link" @click="abrirFarmacia">
        Abrir a farmácia
        <i class="pi pi-arrow-right" aria-hidden="true" />
      </button>
      <button v-else type="button" class="evid-sb-link" @click="irParaListas">
        Ver todas as evidências em Listas
        <i class="pi pi-arrow-right" aria-hidden="true" />
      </button>
    </footer>
  </Sidebar>
</template>

<style scoped>
:global(.evid-sidebar) {
  width: 460px !important;
  background: var(--card-bg) !important;
  border-left: 1px solid var(--card-border) !important;
  padding: 0 !important;
}

:global(.evid-sidebar .p-sidebar-header) {
  padding: 0 !important;
  border-bottom: 1px solid var(--card-border) !important;
}

:global(.evid-sidebar .p-sidebar-content) {
  padding: 0 !important;
  display: flex;
  flex-direction: column;
  overflow: hidden !important;
}

.evid-sb-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
  width: 100%;
  padding: 1rem 1.25rem;
}

.evid-sb-title {
  display: flex;
  align-items: flex-start;
  gap: 0.65rem;
  min-width: 0;
}

.evid-sb-title > i {
  margin-top: 0.25rem;
  color: var(--evidence-color);
}

.evid-sb-title h3 {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin: 0;
  font-size: 1rem;
  font-weight: 600;
  color: var(--text-color-85);
}

.evid-sb-title p {
  margin: 0.15rem 0 0;
  font-size: 0.76rem;
  color: var(--text-muted);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 340px;
}

.evid-sb-count {
  padding: 0.05rem 0.5rem;
  border-radius: 999px;
  font-size: 0.72rem;
  font-weight: 500;
  color: var(--evidence-color);
  background: color-mix(in srgb, var(--evidence-color) 12%, transparent);
}

.evid-sb-close {
  width: 30px;
  height: 30px;
  border: none;
  border-radius: 6px;
  background: transparent;
  color: var(--text-muted);
  cursor: pointer;
}

.evid-sb-close:hover {
  background: var(--surface-hover);
  color: var(--text-color);
}

.evid-sb-body {
  flex: 1;
  overflow-y: auto;
  padding: 1rem 1.25rem;
}

.evid-sb-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.6rem;
  padding: 3rem 1rem;
  text-align: center;
  color: var(--text-muted);
}

.evid-sb-state > i { font-size: 1.6rem; }
.evid-sb-state p { margin: 0; font-size: 0.88rem; color: var(--text-color-85); }
.evid-sb-state span { font-size: 0.78rem; line-height: 1.5; }
.evid-sb-state.is-error > i { color: var(--risk-critical); }

.evid-sb-filtros {
  display: flex;
  flex-wrap: wrap;
  gap: 0.35rem;
  margin-bottom: 0.9rem;
}

.evid-sb-filtro {
  height: 28px;
  padding: 0 0.7rem;
  border-radius: 999px;
  border: 1px solid var(--card-border);
  background: transparent;
  color: var(--text-muted);
  font-family: inherit;
  font-size: 0.74rem;
  cursor: pointer;
}

.evid-sb-filtro:hover { color: var(--text-color-85); }

.evid-sb-filtro.is-active {
  color: var(--evidence-color);
  border-color: color-mix(in srgb, var(--evidence-color) 50%, transparent);
  background: color-mix(in srgb, var(--evidence-color) 10%, transparent);
}

.evid-sb-vazio {
  margin: 1rem 0;
  font-size: 0.8rem;
  color: var(--text-muted);
}

.evid-sb-lista {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 0.6rem;
}

.evid-item {
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
  padding: 0.7rem 0.8rem;
  border: 1px solid var(--card-border);
  border-radius: 10px;
  background: color-mix(in srgb, var(--card-bg) 92%, var(--card-border));
}

.evid-item.is-busy { opacity: 0.6; }

.evid-item-head {
  display: flex;
  align-items: center;
  gap: 0.55rem;
}

.evid-item-tipo {
  display: inline-flex;
  align-items: center;
  gap: 0.3rem;
  padding: 0.08rem 0.45rem;
  border-radius: 5px;
  font-size: 0.68rem;
  font-weight: 500;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: var(--text-muted);
  background: color-mix(in srgb, var(--text-muted) 12%, transparent);
}

.evid-item-tipo i { font-size: 0.68rem; }

.evid-item-quando {
  font-size: 0.82rem;
  font-weight: 600;
  color: var(--text-color-85);
}

.evid-item-acoes {
  display: inline-flex;
  gap: 0.2rem;
  margin-left: auto;
}

.evid-icon-btn {
  width: 26px;
  height: 26px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border: 1px solid transparent;
  border-radius: 6px;
  background: transparent;
  color: var(--text-muted);
  cursor: pointer;
}

.evid-icon-btn i { font-size: 0.74rem; }

.evid-icon-btn:hover,
.evid-icon-btn:focus-visible {
  color: var(--evidence-color);
  border-color: color-mix(in srgb, var(--evidence-color) 40%, transparent);
  outline: none;
}

.evid-icon-btn.is-danger:hover,
.evid-icon-btn.is-danger:focus-visible {
  color: var(--risk-critical);
  border-color: color-mix(in srgb, var(--risk-critical) 40%, transparent);
}

.evid-item-resumo {
  margin: 0;
  font-size: 0.78rem;
  color: var(--text-color-85);
  line-height: 1.45;
}

.evid-item-nota {
  margin: 0;
  padding: 0.4rem 0.55rem;
  border-left: 2px solid color-mix(in srgb, var(--evidence-color) 60%, transparent);
  font-size: 0.78rem;
  line-height: 1.45;
  color: var(--text-color-85);
  white-space: pre-wrap;
  background: color-mix(in srgb, var(--evidence-color) 5%, transparent);
  border-radius: 0 6px 6px 0;
}

.evid-item-nota.is-vazia {
  border-left-color: var(--card-border);
  background: transparent;
  color: var(--text-muted);
  font-style: italic;
}

.evid-item-editor {
  display: flex;
  flex-direction: column;
  gap: 0.4rem;
}

.evid-item-editor textarea {
  width: 100%;
  box-sizing: border-box;
  resize: vertical;
  padding: 0.5rem 0.6rem;
  border: 1px solid var(--card-border);
  border-radius: 8px;
  background: var(--bg-color);
  color: var(--text-color);
  font-family: inherit;
  font-size: 0.8rem;
  line-height: 1.45;
}

.evid-item-editor textarea:focus {
  outline: none;
  border-color: var(--evidence-color);
}

.evid-item-editor-acoes,
.evid-item-confirma {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 0.4rem;
}

.evid-item-confirma span {
  margin-right: auto;
  font-size: 0.76rem;
  color: var(--risk-critical);
}

.evid-item-meta {
  font-size: 0.68rem;
  color: var(--text-muted);
}

.evid-sb-btn {
  height: 28px;
  padding: 0 0.75rem;
  border-radius: 7px;
  border: 1px solid var(--card-border);
  background: transparent;
  color: var(--text-color-85);
  font-family: inherit;
  font-size: 0.74rem;
  font-weight: 500;
  cursor: pointer;
}

.evid-sb-btn:disabled { opacity: 0.6; cursor: not-allowed; }

.evid-sb-export {
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
  height: 30px;
}
.evid-sb-btn.is-primary { border-color: var(--evidence-color); background: var(--evidence-color); color: var(--card-bg); }
.evid-sb-btn.is-danger { border-color: var(--risk-critical); color: var(--risk-critical); }

.evid-sb-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem;
  padding: 0.8rem 1.25rem;
  border-top: 1px solid var(--card-border);
}

.evid-sb-link {
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
  border: none;
  background: none;
  padding: 0;
  color: var(--evidence-color);
  font-family: inherit;
  font-size: 0.78rem;
  font-weight: 500;
  cursor: pointer;
}

.evid-sb-link:hover { text-decoration: underline; }
.evid-sb-link i { font-size: 0.7rem; }
</style>
