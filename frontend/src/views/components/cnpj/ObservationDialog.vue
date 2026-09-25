<script setup>
import { computed, ref, watch } from "vue";
import Dialog from "primevue/dialog";
import Textarea from "primevue/textarea";
import { useFarmaciaListsStore } from "@/stores/farmaciaLists";

const props = defineProps({
  visible: { type: Boolean, default: false },
  cnpj: { type: String, required: true },
  entityName: { type: String, default: "farmacia" },
});

const emit = defineEmits(["update:visible"]);
const farmaciaLists = useFarmaciaListsStore();
const tempObs = ref("");
const shouldSelectOnFocus = ref(false);

const dialogVisible = computed({
  get: () => props.visible,
  set: (value) => emit("update:visible", value),
});

watch(
  () => [props.visible, props.cnpj],
  ([visible]) => {
    if (!visible) return;

    tempObs.value = farmaciaLists.getObservacao(props.cnpj);
    shouldSelectOnFocus.value = true;
  },
  { immediate: true },
);

function selectTextareaOnFocus(event) {
  if (!shouldSelectOnFocus.value) return;

  event.target.select();
  shouldSelectOnFocus.value = false;
}

const saveObs = async () => {
  if (await farmaciaLists.setObservacao(props.cnpj, tempObs.value)) {
    dialogVisible.value = false;
  }
};
</script>

<template>
  <Dialog
    v-model:visible="dialogVisible"
    modal
    header="Observação da Farmácia"
    :style="{ width: '450px' }"
    class="obs-dialog-custom"
  >
    <div class="p-fluid">
      <div class="field mb-4">
        <label for="obs" class="block font-semibold mb-2" style="font-size: 0.9rem; color: var(--text-color-85)">
          Sua anotação para {{ entityName }}:
        </label>
        <Textarea
          id="obs"
          v-model="tempObs"
          rows="5"
          autoResize
          autofocus
          placeholder="Digite aqui os motivos do interesse ou observações importantes..."
          class="custom-textarea"
          @focus="selectTextareaOnFocus"
        />
      </div>
    </div>
    <template #footer>
      <div class="dialog-footer-actions">
        <button class="footer-btn footer-btn--cancel" @click="dialogVisible = false">Cancelar</button>
        <button class="footer-btn footer-btn--save" :disabled="!farmaciaLists.canEdit" @click="saveObs">Salvar Observação</button>
      </div>
    </template>
  </Dialog>
</template>

<style scoped>
.dialog-footer-actions {
  display: flex;
  justify-content: flex-end;
  gap: 0.75rem;
  padding-top: 1rem;
}

.footer-btn {
  padding: 0.5rem 1.25rem;
  border-radius: 8px;
  font-size: 0.85rem;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s ease;
  border: 1px solid transparent;
}

.footer-btn--cancel {
  background: transparent;
  color: var(--text-muted);
}

.footer-btn--cancel:hover {
  background: rgba(0,0,0,0.05);
}

.footer-btn--save {
  position: relative;
  overflow: hidden;
  background: color-mix(in srgb, var(--primary-color) 12%, transparent);
  border-color: color-mix(in srgb, var(--primary-color) 75%, transparent);
  color: var(--primary-color);
  backdrop-filter: blur(10px);
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, 0.14),
    0 8px 22px color-mix(in srgb, var(--primary-color) 12%, transparent);
}

.footer-btn--save:hover {
  background: color-mix(in srgb, var(--primary-color) 18%, transparent);
  border-color: var(--primary-color);
  transform: translateY(-1px);
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, 0.18),
    0 10px 26px color-mix(in srgb, var(--primary-color) 18%, transparent);
}

.footer-btn--save:focus-visible {
  outline: none;
  box-shadow:
    0 0 0 2px color-mix(in srgb, var(--primary-color) 35%, transparent),
    0 10px 26px color-mix(in srgb, var(--primary-color) 18%, transparent);
}

.custom-textarea {
  background: var(--bg-secondary);
  border: 1px solid var(--establishment-header-border);
  border-radius: 8px;
  color: var(--text-color-85);
  padding: 0.75rem;
  font-family: inherit;
  font-size: 0.9rem;
}

.custom-textarea:focus {
  border-color: var(--primary-color);
  box-shadow: 0 0 0 2px color-mix(in srgb, var(--primary-color) 20%, transparent);
}

</style>
