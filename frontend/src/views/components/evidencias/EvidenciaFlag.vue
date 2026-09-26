<script setup>
import { computed, nextTick, ref } from 'vue';
import OverlayPanel from 'primevue/overlaypanel';
import { useToast } from 'primevue/usetoast';
import { useEvidenciasStore } from '@/stores/evidencias';
import { dataHoraCurta, tipoEvidencia } from '@/utils/evidencias';

/**
 * Marca (ou edita) um item da Cronologia como evidência.
 * variant="button": botão com texto, no cabeçalho dos painéis.
 * variant="icon": só a bandeira, nas linhas do Raio-X.
 */
const props = defineProps({
  // { cnpj, tipo, dt_janela, hora, num_autorizacao }
  alvo: { type: Object, required: true },
  // Retrato do item no momento da marcação (chamado só ao marcar).
  snapshot: { type: Function, required: true },
  descricao: { type: String, required: true },
  razaoSocial: { type: String, default: '' },
  variant: { type: String, default: 'button', validator: (v) => ['button', 'icon'].includes(v) },
});

const store = useEvidenciasStore();
const notaId = `evid-nota-${Math.random().toString(36).slice(2, 10)}`;
const toast = useToast();
const panel = ref(null);
const notaInput = ref(null);
const nota = ref('');
const salvando = ref(false);

const alvoNormalizado = computed(() => ({
  cnpj: props.alvo.cnpj,
  tipo: props.alvo.tipo,
  dt_janela: String(props.alvo.dt_janela).slice(0, 10),
  hora: props.alvo.tipo === 'dia' ? null : props.alvo.hora,
  num_autorizacao: props.alvo.tipo === 'autorizacao' ? String(props.alvo.num_autorizacao) : null,
}));

const indisponivel = computed(() => store.loadState !== 'ready');
const evidencia = computed(() => (indisponivel.value ? null : store.encontrar(alvoNormalizado.value)));
const marcado = computed(() => Boolean(evidencia.value));
const tipoLabel = computed(() => tipoEvidencia(props.alvo.tipo).label.toLowerCase());

const ariaLabel = computed(() => {
  if (indisponivel.value) return 'Cesta de evidências indisponível';
  return marcado.value
    ? `Evidência marcada: ${props.descricao}. Editar nota ou remover`
    : `Marcar ${props.descricao} como evidência`;
});

async function abrir(event) {
  if (indisponivel.value) {
    toast.add({
      severity: 'error',
      summary: 'Cesta de evidências indisponível',
      detail: store.error || 'A cesta ainda não foi carregada.',
      life: 6000,
    });
    return;
  }
  nota.value = evidencia.value?.nota ?? '';
  panel.value.toggle(event);
  await nextTick();
  notaInput.value?.focus();
}

function fechar() {
  panel.value?.hide();
}

async function salvar() {
  if (salvando.value) return;
  salvando.value = true;
  try {
    if (evidencia.value) {
      await store.atualizarNota(evidencia.value.id, nota.value);
      toast.add({ severity: 'success', summary: 'Nota atualizada', detail: props.descricao, life: 2500 });
    } else {
      const { farmaciaAdicionada } = await store.marcar(
        { ...alvoNormalizado.value, snapshot: props.snapshot(), nota: nota.value },
        { razaoSocial: props.razaoSocial },
      );
      toast.add({
        severity: 'success',
        summary: 'Evidência marcada',
        detail: farmaciaAdicionada
          ? `${props.descricao}. A farmácia também foi adicionada às Farmácias Monitoradas.`
          : props.descricao,
        life: farmaciaAdicionada ? 6000 : 2500,
      });
    }
    fechar();
  } catch (error) {
    toast.add({ severity: 'error', summary: 'Evidência não salva', detail: error.message, life: 8000 });
  } finally {
    salvando.value = false;
  }
}

async function remover() {
  if (salvando.value || !evidencia.value) return;
  salvando.value = true;
  try {
    await store.remover(evidencia.value.id);
    toast.add({ severity: 'info', summary: 'Evidência removida', detail: props.descricao, life: 2500 });
    fechar();
  } catch (error) {
    toast.add({ severity: 'error', summary: 'Evidência não removida', detail: error.message, life: 8000 });
  } finally {
    salvando.value = false;
  }
}

function onKeydown(event) {
  if (event.key === 'Enter' && (event.ctrlKey || event.metaKey)) {
    event.preventDefault();
    salvar();
  }
}
</script>

<template>
  <button
    type="button"
    :class="['evid-flag', `evid-flag--${variant}`, { 'is-marcado': marcado }]"
    :aria-label="ariaLabel"
    :aria-pressed="marcado"
    :disabled="salvando"
    @click.stop="abrir"
  >
    <i :class="['pi', marcado ? 'pi-flag-fill' : 'pi-flag']" aria-hidden="true" />
    <span v-if="variant === 'button'">{{ marcado ? 'Evidência marcada' : 'Marcar evidência' }}</span>
  </button>

  <OverlayPanel ref="panel" class="evid-flag-panel" :dismissable="true">
    <form class="evid-form" @submit.prevent="salvar" @click.stop>
      <header class="evid-form-header">
        <i class="pi pi-flag-fill" aria-hidden="true" />
        <div>
          <h4>{{ marcado ? 'Evidência marcada' : `Marcar ${tipoLabel} como evidência` }}</h4>
          <p>{{ descricao }}</p>
        </div>
      </header>
      <label class="evid-form-label" :for="notaId">
        Nota do auditor <span>(opcional)</span>
      </label>
      <textarea
        :id="notaId"
        ref="notaInput"
        v-model="nota"
        class="evid-form-textarea"
        rows="3"
        maxlength="2000"
        placeholder="Ex.: rajada de autorizações com 6 CRMs em 1 hora"
        @keydown="onKeydown"
      />
      <p v-if="marcado" class="evid-form-meta">Marcada em {{ dataHoraCurta(evidencia.criado_em) }}</p>
      <footer class="evid-form-actions">
        <button v-if="marcado" type="button" class="evid-btn evid-btn--danger" :disabled="salvando" @click="remover">
          <i class="pi pi-trash" aria-hidden="true" />
          Remover
        </button>
        <span class="evid-form-spacer" />
        <button type="button" class="evid-btn" :disabled="salvando" @click="fechar">Cancelar</button>
        <button type="submit" class="evid-btn evid-btn--primary" :disabled="salvando">
          <i v-if="salvando" class="pi pi-spin pi-spinner" aria-hidden="true" />
          {{ marcado ? 'Salvar nota' : 'Marcar' }}
        </button>
      </footer>
    </form>
  </OverlayPanel>
</template>

<style scoped>
.evid-flag {
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
  border: 1px solid var(--card-border);
  background: transparent;
  color: var(--text-muted);
  cursor: pointer;
  font-family: inherit;
  transition: color 0.15s ease, border-color 0.15s ease, background 0.15s ease;
}

.evid-flag:hover:not(:disabled),
.evid-flag:focus-visible {
  color: var(--evidence-color);
  border-color: color-mix(in srgb, var(--evidence-color) 55%, transparent);
  outline: none;
}

.evid-flag:focus-visible {
  box-shadow: 0 0 0 2px color-mix(in srgb, var(--evidence-color) 35%, transparent);
}

.evid-flag:disabled {
  cursor: wait;
  opacity: 0.6;
}

.evid-flag.is-marcado {
  color: var(--evidence-color);
  border-color: color-mix(in srgb, var(--evidence-color) 45%, transparent);
  background: color-mix(in srgb, var(--evidence-color) 10%, transparent);
}

.evid-flag--button {
  height: 30px;
  padding: 0 0.75rem;
  border-radius: 8px;
  font-size: 0.76rem;
  font-weight: 600;
  white-space: nowrap;
  /* Não marcado: ação disponível, já na cor de evidência. */
  color: var(--evidence-color);
  border-color: color-mix(in srgb, var(--evidence-color) 45%, transparent);
  background: color-mix(in srgb, var(--evidence-color) 8%, transparent);
}

.evid-flag--button:hover:not(:disabled),
.evid-flag--button:focus-visible {
  border-color: var(--evidence-color);
  background: color-mix(in srgb, var(--evidence-color) 16%, transparent);
}

/* Marcado: sólido, inconfundível. */
.evid-flag--button.is-marcado,
.evid-flag--button.is-marcado:hover:not(:disabled),
.evid-flag--button.is-marcado:focus-visible {
  color: var(--card-bg);
  border-color: var(--evidence-color);
  background: var(--evidence-color);
}

.evid-flag--button.is-marcado:hover:not(:disabled) {
  background: color-mix(in srgb, var(--evidence-color) 88%, black);
}

.evid-flag--button i {
  font-size: 0.8rem;
}

.evid-flag--icon {
  width: 26px;
  height: 26px;
  justify-content: center;
  padding: 0;
  border-radius: 6px;
  border-color: transparent;
}

.evid-flag--icon i {
  font-size: 0.78rem;
}

:deep(.evid-flag-panel.p-overlaypanel) {
  width: 360px;
  background: var(--card-bg);
  border: 1px solid var(--card-border);
  border-radius: 12px;
  box-shadow: var(--tooltip-shadow);
}

:deep(.evid-flag-panel .p-overlaypanel-content) {
  padding: 0;
}

.evid-form {
  display: flex;
  flex-direction: column;
  gap: 0.6rem;
  padding: 1rem;
  color: var(--text-color-85);
}

.evid-form-header {
  display: flex;
  align-items: flex-start;
  gap: 0.65rem;
}

.evid-form-header > i {
  margin-top: 0.2rem;
  color: var(--evidence-color);
  font-size: 0.9rem;
}

.evid-form-header h4 {
  margin: 0;
  font-size: 0.88rem;
  font-weight: 600;
}

.evid-form-header p {
  margin: 0.15rem 0 0;
  font-size: 0.76rem;
  color: var(--text-muted);
}

.evid-form-label {
  font-size: 0.72rem;
  font-weight: 500;
  color: var(--text-color-85);
}

.evid-form-label span {
  color: var(--text-muted);
  font-weight: 400;
}

.evid-form-textarea {
  width: 100%;
  box-sizing: border-box;
  resize: vertical;
  min-height: 72px;
  padding: 0.55rem 0.65rem;
  border: 1px solid var(--card-border);
  border-radius: 8px;
  background: var(--bg-color);
  color: var(--text-color);
  font-family: inherit;
  font-size: 0.8rem;
  line-height: 1.45;
}

.evid-form-textarea:focus {
  outline: none;
  border-color: var(--evidence-color);
  box-shadow: 0 0 0 2px color-mix(in srgb, var(--evidence-color) 25%, transparent);
}

.evid-form-meta {
  margin: 0;
  font-size: 0.7rem;
  color: var(--text-muted);
}

.evid-form-actions {
  display: flex;
  align-items: center;
  gap: 0.45rem;
  margin-top: 0.2rem;
}

.evid-form-spacer {
  flex: 1;
}

.evid-btn {
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
  height: 30px;
  padding: 0 0.8rem;
  border-radius: 7px;
  border: 1px solid var(--card-border);
  background: transparent;
  color: var(--text-color-85);
  font-family: inherit;
  font-size: 0.76rem;
  font-weight: 500;
  cursor: pointer;
}

.evid-btn:hover:not(:disabled) {
  border-color: var(--text-muted);
}

.evid-btn:disabled {
  opacity: 0.6;
  cursor: wait;
}

.evid-btn--primary {
  border-color: var(--evidence-color);
  background: var(--evidence-color);
  color: var(--card-bg);
}

.evid-btn--primary:hover:not(:disabled) {
  border-color: var(--evidence-color);
  background: color-mix(in srgb, var(--evidence-color) 88%, black);
}

.evid-btn--danger {
  color: var(--risk-critical);
  border-color: color-mix(in srgb, var(--risk-critical) 35%, transparent);
}

.evid-btn--danger:hover:not(:disabled) {
  border-color: var(--risk-critical);
}
</style>
