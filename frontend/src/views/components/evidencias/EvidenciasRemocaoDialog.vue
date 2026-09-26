<script setup>
import { computed } from 'vue';
import { useRouter } from 'vue-router';
import Dialog from 'primevue/dialog';
import { useEvidenciasStore } from '@/stores/evidencias';

/** Confirmação global: remover uma farmácia monitorada que tem evidências. */
const store = useEvidenciasStore();
const router = useRouter();

const pendente = computed(() => store.remocaoPendente);
const visivel = computed({
  get: () => Boolean(pendente.value),
  set: (valor) => { if (!valor) store.responderRemocao(false); },
});

const quantidadeTexto = computed(() => {
  const n = pendente.value?.quantidade ?? 0;
  return `${n} ${n === 1 ? 'evidência marcada' : 'evidências marcadas'}`;
});

function revisar() {
  const cnpj = pendente.value?.cnpj;
  store.responderRemocao(false);
  router.push({ path: '/listas', query: { aba: 'evidencias', cnpj } });
}
</script>

<template>
  <Dialog
    v-model:visible="visivel"
    modal
    :closable="true"
    :draggable="false"
    class="evid-remocao-dialog"
    :style="{ width: '480px' }"
  >
    <template #header>
      <div class="evid-rm-header">
        <i class="pi pi-exclamation-triangle" aria-hidden="true" />
        <span>Remover das Farmácias Monitoradas?</span>
      </div>
    </template>

    <div v-if="pendente" class="evid-rm-body">
      <p class="evid-rm-nome">{{ pendente.nome }}</p>
      <p>
        Esta farmácia tem <strong>{{ quantidadeTexto }}</strong>.
        Toda farmácia com evidências fica na lista, por isso <strong>as evidências também serão excluídas</strong>.
        Essa ação não pode ser desfeita.
      </p>
    </div>

    <template #footer>
      <div class="evid-rm-actions">
        <button type="button" class="evid-rm-btn is-link" @click="revisar">
          <i class="pi pi-flag" aria-hidden="true" />
          Revisar evidências
        </button>
        <span class="evid-rm-spacer" />
        <button type="button" class="evid-rm-btn" @click="store.responderRemocao(false)">Cancelar</button>
        <button type="button" class="evid-rm-btn is-danger" @click="store.responderRemocao(true)">
          Remover farmácia e evidências
        </button>
      </div>
    </template>
  </Dialog>
</template>

<style scoped>
.evid-rm-header {
  display: flex;
  align-items: center;
  gap: 0.6rem;
  font-size: 1rem;
  font-weight: 600;
  color: var(--text-color-85);
}

.evid-rm-header i {
  color: var(--risk-critical);
}

.evid-rm-body {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  font-size: 0.85rem;
  line-height: 1.55;
  color: var(--text-color-85);
}

.evid-rm-body p {
  margin: 0;
}

.evid-rm-body strong {
  font-weight: 600;
}

.evid-rm-nome {
  font-weight: 600;
}

.evid-rm-actions {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  width: 100%;
}

.evid-rm-spacer {
  flex: 1;
}

.evid-rm-btn {
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
  height: 32px;
  padding: 0 0.85rem;
  border-radius: 8px;
  border: 1px solid var(--card-border);
  background: transparent;
  color: var(--text-color-85);
  font-family: inherit;
  font-size: 0.8rem;
  font-weight: 500;
  cursor: pointer;
}

.evid-rm-btn:hover {
  border-color: var(--text-muted);
}

.evid-rm-btn.is-link {
  border-color: transparent;
  padding: 0 0.3rem;
  color: var(--evidence-color);
}

.evid-rm-btn.is-link:hover {
  text-decoration: underline;
}

.evid-rm-btn.is-danger {
  border-color: var(--risk-critical);
  background: var(--risk-critical);
  color: var(--card-bg);
}

.evid-rm-btn.is-danger:hover {
  background: color-mix(in srgb, var(--risk-critical) 88%, black);
}
</style>
