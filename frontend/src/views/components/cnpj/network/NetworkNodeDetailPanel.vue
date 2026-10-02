<script setup>
import { computed, ref } from "vue";
import { useRouter } from "vue-router";
import {
  formatCnaeEvidence,
  formatCpfCnpj,
  formatSocietyDate,
} from "@/utils/network/networkFormatters";
import { useStatusClass } from "@/composables/useStatusClass";
import { useToast } from "primevue/usetoast";
import { useFarmaciaListsStore } from "@/stores/farmaciaLists";
import ObservationDialog from "@/views/components/cnpj/ObservationDialog.vue";

const props = defineProps({
  node: {
    type: Object,
    required: true,
  },
  typeLabels: {
    type: Object,
    required: true,
  },
  copiedKey: {
    type: [String, Number, null],
    default: null,
  },
  canExpand: {
    type: Boolean,
    default: false,
  },
  isExpanding: {
    type: Boolean,
    default: false,
  },
  isExpanded: {
    type: Boolean,
    default: false,
  },
  expansionLabel: {
    type: String,
    default: "",
  },
});

const emit = defineEmits(["close", "copy", "expand"]);
const router = useRouter();
const { situacaoRfClass, conexaoMsClass } = useStatusClass();

const nodeTitle = computed(
  () =>
    props.node.nome_socio ||
    props.node.nome_fantasia ||
    props.node.razao_social ||
    props.node.fullLabel,
);

const documentLabel = computed(() =>
  String(props.node.id || "").replace(/\D/g, "").length === 11 ? "CPF" : "CNPJ",
);

const percentualNaoComprovacao = computed(() => {
  if (props.node.type !== "PJ_FARMACIA_POPULAR") return null;
  const value = Number(props.node.percentual_nao_comprovacao);
  if (!Number.isFinite(value)) {
    throw new Error(
      `Farmacia Popular ${props.node.id || ""} sem percentual de nao comprovacao.`,
    );
  }
  return `${value.toLocaleString("pt-BR", {
    minimumFractionDigits: 1,
    maximumFractionDigits: 1,
  })}%`;
});

const criticidadeNaoComprovacao = computed(() => {
  if (props.node.type !== "PJ_FARMACIA_POPULAR") return null;
  const criticidade = props.node.criticidade_nao_comprovacao;
  if (!["CRÍTICO", "ATENÇÃO", "NORMAL"].includes(criticidade)) {
    throw new Error(
      `Farmacia Popular ${props.node.id || ""} sem criticidade valida.`,
    );
  }
  return criticidade;
});

const criticidadeClass = computed(() => {
  if (criticidadeNaoComprovacao.value === "CRÍTICO") return "status-danger";
  if (criticidadeNaoComprovacao.value === "ATENÇÃO") return "status-warn";
  if (criticidadeNaoComprovacao.value === "NORMAL") return "status-success";
  return "status-secondary";
});

const conexaoMs = computed(() => {
  if (props.node.type !== "PJ_FARMACIA_POPULAR") return null;
  if (!["Ativa", "Inativa"].includes(props.node.conexao_ms)) {
    throw new Error(
      `Farmacia Popular ${props.node.id || ""} sem Conexao MS valida.`,
    );
  }
  return props.node.conexao_ms;
});

const formatStatusBadge = (value) => String(value).toLocaleUpperCase("pt-BR");

// Favoritar a farmácia (lista de interesse / Farmácias monitoradas), como na
// tabela de /estabelecimentos. Vale para as farmácias do programa na teia e para a
// farmácia central (PJ_ALVO, o CNPJ em análise).
const TIPOS_FAVORITAVEIS = new Set(["PJ_FARMACIA_POPULAR", "PJ_ALVO"]);
const podeFavoritar = computed(() => TIPOS_FAVORITAVEIS.has(props.node.type));
const farmaciaLists = useFarmaciaListsStore();
const toast = useToast();
const cnpjFarmacia = computed(() => String(props.node.id || "").replace(/\D/g, ""));
const ehFavorita = computed(() => farmaciaLists.isInteresse(cnpjFarmacia.value));
async function alternarFavorita() {
  if (!podeFavoritar.value) {
    throw new Error(`Nó ${props.node.type} não pode ser favoritado.`);
  }
  const nome = props.node.razao_social || props.node.nome_fantasia || cnpjFarmacia.value;
  const salvou = await farmaciaLists.toggleInteresse(cnpjFarmacia.value, nome);
  // null = remoção cancelada pelo usuário no diálogo de evidências.
  if (salvou === false && farmaciaLists.loadState === "ready") {
    toast.add({
      severity: "error",
      summary: "Favorito não alterado",
      detail: farmaciaLists.error || "Não foi possível salvar a alteração.",
      life: 5000,
    });
  }
}

// Anotação da farmácia favorita (o mesmo diálogo da tabela de /estabelecimentos).
const observacao = computed(() => farmaciaLists.getObservacao(cnpjFarmacia.value));
const mostrarObservacao = ref(false);
const nomeFarmacia = computed(() => props.node.razao_social || props.node.nome_fantasia || cnpjFarmacia.value);
function abrirObservacao() {
  if (!farmaciaLists.canEdit || !ehFavorita.value) return;
  mostrarObservacao.value = true;
}

function openEstablishmentDetail() {
  if (props.node.type !== "PJ_FARMACIA_POPULAR") {
    throw new Error("Detalhamento disponível apenas para Farmácia Popular.");
  }
  router.push(`/estabelecimentos/${String(props.node.id).replace(/\D/g, "")}`);
}
</script>

<template>
  <transition name="slide-in">
    <div v-if="node" class="node-detail-panel">
      <div class="panel-header">
        <div
          class="panel-type-badge"
          :class="{ 'pharmacy-program-badge': node.type === 'PJ_FARMACIA_POPULAR' }"
          :style="{ background: typeLabels[node.type]?.color }"
        >
          <i
            v-if="node.type === 'PJ_FARMACIA_POPULAR'"
            class="pi pi-building"
          />
          {{ typeLabels[node.type]?.label || node.type }}
        </div>
        <button class="close-btn" @click="emit('close')">
          <i class="pi pi-times" />
        </button>
      </div>

      <div class="panel-names">
        <h3 class="panel-main-name">{{ nodeTitle }}</h3>
        <div v-if="node.nome_fantasia && node.razao_social" class="panel-sub-name">
          {{ node.razao_social }}
        </div>
      </div>

      <div class="panel-id">
        <span class="panel-id-label">{{ documentLabel }}</span>
        <span class="panel-id-value">{{ formatCpfCnpj(node.id) }}</span>
        <i
          :class="[
            'pi',
            copiedKey === node.id ? 'pi-check' : 'pi-copy',
            'copy-btn',
            copiedKey === node.id ? 'text-success' : '',
          ]"
          v-tooltip.top="'Copiar'"
          @click="emit('copy', node.id, node.id)"
        />
      </div>

      <div class="panel-fields">
        <div v-if="node.municipio" class="panel-field">
          <i class="pi pi-map-marker" />
          <span>{{ node.municipio }} / {{ node.uf }}</span>
        </div>

        <div
          v-if="node.type === 'PJ_FARMACIA_POPULAR'"
          class="panel-field risk-field"
        >
          <i class="pi pi-chart-line" />
          <span>Sem comp.</span>
          <strong>{{ percentualNaoComprovacao }}</strong>
          <span class="panel-status-badge" :class="criticidadeClass">
            {{ formatStatusBadge(criticidadeNaoComprovacao) }}
          </span>
        </div>

        <div
          v-if="node.type === 'PJ_FARMACIA_POPULAR'"
          class="panel-field ms-field"
        >
          <i class="pi pi-link" />
          <span>Conexão MS</span>
          <span class="panel-status-badge" :class="conexaoMsClass(conexaoMs)">
            {{ formatStatusBadge(conexaoMs) }}
          </span>
        </div>

        <div v-if="node.situacao_rf" class="panel-field rf-field">
          <i class="pi pi-info-circle" />
          <span>Situação RF</span>
          <span
            class="panel-status-badge"
            :class="situacaoRfClass(node.situacao_rf)"
          >
            {{ formatStatusBadge(node.situacao_rf) }}
          </span>
        </div>

        <div
          v-if="node.type === 'PF' && node.is_falecido"
          class="panel-field deceased-field"
        >
          <i class="pi pi-times-circle" />
          <span>Falecido</span>
          <span class="deceased-badge">Óbito</span>
        </div>

        <div
          v-if="node.type === 'PF' && node.is_cadunico"
          class="panel-field cadunico-field"
        >
          <i class="pi pi-id-card" />
          <span>CadÚnico</span>
          <span class="cadunico-badge">Inscrito</span>
        </div>

        <div
          v-if="node.type === 'PF' && node.is_esocial"
          class="panel-field esocial-field"
        >
          <i class="pi pi-briefcase" />
          <span>eSocial</span>
          <span class="esocial-badge">Vinculo em outro CNPJ</span>
        </div>

        <div
          v-if="node.type === 'PF' && node.is_seguro_defeso"
          class="panel-field seguro-defeso-field"
        >
          <i class="pi pi-wallet" />
          <span>Seguro Defeso</span>
          <span class="seguro-defeso-badge">Beneficiário</span>
        </div>

        <div
          v-if="node.type !== 'PF' && node.is_cnae_farmacia_ausente"
          class="panel-field cnae-alert-field"
        >
          <i class="pi pi-exclamation-triangle" />
          <span>CNAE farmácia</span>
          <span class="cnae-alert-badge">Ausente</span>
        </div>

        <div
          v-if="
            node.type !== 'PF' &&
            (node.id_cnae_principal || node.cnaes_secundarios.length > 0)
          "
          class="cnae-evidence"
        >
          <div class="cnae-evidence-row">
            <span>Principal</span>
            <strong>
              {{ formatCnaeEvidence(node.id_cnae_principal, node.cnae_principal) }}
            </strong>
          </div>
          <div
            v-for="cnae in node.cnaes_secundarios"
            :key="cnae.id_cnae"
            class="cnae-evidence-row"
          >
            <span>Secundário</span>
            <strong>
              {{ formatCnaeEvidence(cnae.id_cnae, cnae.descricao) }}
            </strong>
          </div>
        </div>

        <div
          v-if="node.type !== 'PF' && node.is_par"
          class="panel-field par-alert-field"
        >
          <i class="pi pi-shield" />
          <span>PAR</span>
          <span class="par-alert-badge">{{ node.qtd_processos_par || 1 }} registro(s)</span>
        </div>

        <div
          v-if="node.type !== 'PF' && node.is_par"
          class="par-evidence"
        >
          <div v-if="node.par_situacoes" class="par-evidence-row">
            <span>Situação</span>
            <strong>{{ node.par_situacoes }}</strong>
          </div>
          <div class="par-evidence-row">
            <span>Primeira instauração</span>
            <strong>{{ formatSocietyDate(node.par_primeira_instauracao) }}</strong>
          </div>
          <div class="par-evidence-row">
            <span>Última instauração</span>
            <strong>{{ formatSocietyDate(node.par_ultima_instauracao) }}</strong>
          </div>
          <div class="par-evidence-row">
            <span>Última conclusão</span>
            <strong>{{ formatSocietyDate(node.par_ultima_conclusao) }}</strong>
          </div>
        </div>

      </div>

      <div v-if="node.societyLinks?.length" class="panel-relationships">
        <div class="panel-section-title">Vínculos societários</div>
        <div
          v-for="link in node.societyLinks"
          :key="link.id"
          class="relationship-card"
        >
          <div class="relationship-header">
            <span class="relationship-name">{{ link.otherName }}</span>
            <span
              class="panel-status-badge relationship-status"
              :class="link.is_ativo ? 'status-success' : 'status-danger'"
            >
              {{ link.is_ativo ? "ATIVO" : "INATIVO" }}
            </span>
          </div>

          <div class="relationship-meta">
            <span>{{ formatCpfCnpj(link.otherId) }}</span>
            <span v-if="link.label">{{ link.label }}</span>
          </div>

          <div class="relationship-dates">
            <div>
              <span class="field-label">Entrada</span>
              <span class="field-value">
                {{ formatSocietyDate(link.data_entrada_sociedade) }}
              </span>
            </div>
            <div>
              <span class="field-label">Saída</span>
              <span class="field-value">
                {{ formatSocietyDate(link.data_exclusao_sociedade) }}
              </span>
            </div>
          </div>
        </div>
      </div>

      <div v-if="canExpand" class="panel-actions mt-3">
        <button
          class="panel-action-btn"
          :disabled="isExpanding || isExpanded"
          @click="emit('expand', node.id)"
        >
          <i :class="isExpanding ? 'pi pi-spin pi-spinner' : 'pi pi-plus-circle'" />
          <span>{{ expansionLabel }}</span>
        </button>
      </div>

      <div v-if="podeFavoritar" class="panel-actions panel-actions--farmacia">
        <button
          type="button"
          class="panel-action-btn favorite-btn"
          :class="{ 'is-favorite': ehFavorita }"
          :aria-pressed="ehFavorita"
          :disabled="!farmaciaLists.canEdit"
          v-tooltip.top="ehFavorita ? 'Remover das Farmácias monitoradas' : 'Adicionar às Farmácias monitoradas'"
          @click="alternarFavorita"
        >
          <i :class="ehFavorita ? 'pi pi-star-fill' : 'pi pi-star'" aria-hidden="true" />
          <span>{{ ehFavorita ? "Favorita" : "Favoritar" }}</span>
        </button>
        <button
          v-if="ehFavorita"
          type="button"
          class="panel-action-btn observation-btn"
          :class="{ 'has-observation': Boolean(observacao) }"
          :aria-label="`${observacao ? 'Editar' : 'Adicionar'} anotação para ${nomeFarmacia}`"
          :disabled="!farmaciaLists.canEdit"
          v-tooltip.top="observacao ? `Anotação: ${observacao}` : 'Adicionar anotação'"
          @click="abrirObservacao"
        >
          <i :class="observacao ? 'pi pi-comment' : 'pi pi-pencil'" aria-hidden="true" />
        </button>
        <button
          v-if="node.type === 'PJ_FARMACIA_POPULAR'"
          type="button"
          class="panel-action-btn detail-btn"
          @click="openEstablishmentDetail"
        >
          <i class="pi pi-external-link" />
          <span>Abrir detalhamento</span>
        </button>
      </div>

      <ObservationDialog
        v-if="podeFavoritar && ehFavorita"
        v-model:visible="mostrarObservacao"
        :cnpj="cnpjFarmacia"
        :entity-name="nomeFarmacia"
      />

      <div class="panel-hint">
        <i class="pi pi-mouse" /> Clique no fundo para fechar
      </div>
    </div>
  </transition>
</template>

<style scoped>
.node-detail-panel {
  position: absolute;
  top: 1rem;
  right: 1rem;
  z-index: 1000;
  width: 280px;
  background: color-mix(in srgb, var(--card-bg) 92%, transparent);
  backdrop-filter: blur(10px);
  -webkit-backdrop-filter: blur(10px);
  border: 1px solid var(--tabs-border);
  border-radius: 12px;
  padding: 1.25rem;
  display: flex;
  flex-direction: column;
  gap: 0.8rem;
  max-height: calc(100% - 2rem);
  overflow-y: auto;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.25);
  pointer-events: auto;
}

.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.risk-field strong {
  margin-left: auto;
  font-weight: 600;
  color: var(--text-color-85);
}

.panel-status-badge {
  margin-left: auto;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 0.16rem 0.42rem;
  border-radius: 4px;
  font-size: 0.58rem;
  font-weight: 600;
  line-height: 1;
  text-transform: uppercase;
}

.risk-field .panel-status-badge,
.ms-field .panel-status-badge,
.rf-field .panel-status-badge {
  width: 3.75rem;
  flex-shrink: 0;
}

.panel-type-badge {
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
  font-size: 0.62rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: #fff;
  padding: 0.2rem 0.6rem;
  border-radius: 99px;
}

.panel-type-badge.pharmacy-program-badge {
  min-height: 2rem;
  padding: 0.38rem 0.72rem;
  border: 1px solid color-mix(in srgb, var(--status-success) 45%, var(--tabs-border));
  border-radius: 6px;
  background: color-mix(in srgb, var(--status-success) 10%, var(--card-bg)) !important;
  color: var(--status-success);
  box-shadow: 0 4px 14px
    color-mix(in srgb, var(--status-success) 10%, transparent);
}

.panel-type-badge.pharmacy-program-badge i {
  font-size: 0.78rem;
}

.close-btn {
  background: transparent;
  border: none;
  color: var(--text-muted);
  cursor: pointer;
  font-size: 0.75rem;
  padding: 0.2rem;
  border-radius: 4px;
  transition: color 0.2s;
}

.close-btn:hover {
  color: var(--text-color-85);
}

.panel-names {
  display: flex;
  flex-direction: column;
  gap: 0.2rem;
}

.panel-main-name {
  margin: 0;
  font-size: 1rem;
  font-weight: 600;
  color: var(--text-color-85);
  line-height: 1.2;
}

.panel-sub-name {
  font-size: 0.75rem;
  font-weight: 500;
  color: var(--text-muted);
  line-height: 1.3;
  opacity: 0.8;
}

.panel-id {
  font-size: 0.75rem;
  color: var(--text-muted);
  background: var(--bg-secondary);
  border-radius: 6px;
  padding: 0.3rem 0.5rem;
  display: flex;
  align-items: center;
  gap: 0.4rem;
}

.panel-id-label {
  font-size: 0.65rem;
  font-weight: 600;
  color: var(--text-muted);
  opacity: 0.7;
  flex-shrink: 0;
}

.panel-id-value {
  flex: none;
}

.copy-btn {
  font-size: 0.85rem;
  cursor: pointer;
  color: var(--text-muted);
  opacity: 0.4;
  transition: all 0.2s;
  width: 1.4rem;
  display: inline-flex;
  justify-content: center;
  flex-shrink: 0;
}

.copy-btn.text-success {
  color: #10b981 !important;
  opacity: 1 !important;
}

.copy-btn:hover {
  opacity: 1 !important;
  color: var(--primary-color);
  transform: scale(1.1);
}

.copy-btn:active {
  transform: scale(0.9);
}

.panel-fields,
.panel-relationships {
  display: flex;
  flex-direction: column;
}

.panel-fields {
  gap: 0.5rem;
}

.panel-relationships {
  gap: 0.45rem;
}

.panel-section-title {
  font-size: 0.6rem;
  text-transform: uppercase;
  font-weight: 600;
  color: var(--text-muted);
  letter-spacing: 0.03em;
}

.relationship-card {
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
  padding: 0.55rem;
  background: var(--bg-secondary);
  border: 1px solid color-mix(in srgb, var(--tabs-border) 72%, transparent);
  border-radius: 6px;
}

.relationship-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 0.5rem;
}

.relationship-name {
  min-width: 0;
  color: var(--text-color-85);
  font-size: 0.74rem;
  font-weight: 650;
  line-height: 1.25;
  overflow-wrap: anywhere;
}

.relationship-status {
  flex-shrink: 0;
  margin-left: 0;
}

.relationship-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 0.35rem;
  color: var(--text-muted);
  font-size: 0.65rem;
  font-weight: 500;
}

.relationship-dates {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 0.45rem;
}

.relationship-dates > div {
  display: flex;
  flex-direction: column;
  gap: 0.08rem;
}

.panel-field {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-size: 0.78rem;
  color: var(--text-secondary);
}

.panel-field i {
  color: var(--primary-color);
  font-size: 0.75rem;
  flex-shrink: 0;
}

.cadunico-field {
  color: color-mix(in srgb, var(--primary-color) 75%, var(--text-color-85));
}

.cadunico-field i {
  color: var(--primary-color);
}

.cadunico-badge,
.esocial-badge,
.seguro-defeso-badge,
.cnae-alert-badge,
.par-alert-badge,
.deceased-badge {
  margin-left: auto;
  padding: 0.1rem 0.42rem;
  border-radius: 999px;
  font-size: 0.62rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.02em;
}

.cadunico-badge {
  border: 1px solid color-mix(in srgb, var(--primary-color) 42%, transparent);
  background: color-mix(in srgb, var(--primary-color) 16%, transparent);
  color: color-mix(in srgb, var(--primary-color) 82%, var(--text-color-85));
}

.esocial-field {
  color: color-mix(in srgb, var(--status-success) 78%, var(--text-color-85));
}

.esocial-field i {
  color: var(--status-success);
}

.esocial-badge {
  border: 1px solid color-mix(in srgb, var(--status-success) 44%, transparent);
  background: color-mix(in srgb, var(--status-success) 14%, transparent);
  color: color-mix(in srgb, var(--status-success) 86%, var(--text-color-85));
}

.seguro-defeso-field {
  color: color-mix(in srgb, var(--status-info) 78%, var(--text-color-85));
}

.seguro-defeso-field i {
  color: var(--status-info);
}

.seguro-defeso-badge {
  border: 1px solid color-mix(in srgb, var(--status-info) 44%, transparent);
  background: color-mix(in srgb, var(--status-info) 14%, transparent);
  color: color-mix(in srgb, var(--status-info) 86%, var(--text-color-85));
}

.cnae-alert-field {
  color: color-mix(in srgb, #ef4444 76%, var(--text-color-85));
}

.cnae-alert-field i {
  color: #ef4444;
}

.cnae-alert-badge {
  border: 1px solid color-mix(in srgb, #ef4444 44%, transparent);
  background: color-mix(in srgb, #ef4444 14%, transparent);
  color: color-mix(in srgb, #ef4444 84%, var(--text-color-85));
}

.cnae-evidence {
  display: grid;
  gap: 0.35rem;
  margin-top: -0.1rem;
  padding: 0.55rem 0.6rem;
  border: 1px solid color-mix(in srgb, #ef4444 22%, transparent);
  border-radius: 8px;
  background: color-mix(in srgb, #ef4444 7%, transparent);
}

.cnae-evidence-row {
  display: grid;
  gap: 0.12rem;
}

.par-alert-field {
  color: color-mix(in srgb, #dc2626 78%, var(--text-color-85));
}

.par-alert-field i {
  color: #dc2626;
}

.par-alert-badge {
  border: 1px solid color-mix(in srgb, #dc2626 44%, transparent);
  background: color-mix(in srgb, #dc2626 14%, transparent);
  color: color-mix(in srgb, #dc2626 86%, var(--text-color-85));
}

.par-evidence {
  display: grid;
  gap: 0.38rem;
  margin-top: -0.1rem;
  padding: 0.55rem 0.6rem;
  border: 1px solid color-mix(in srgb, #dc2626 22%, transparent);
  border-radius: 8px;
  background: color-mix(in srgb, #dc2626 7%, transparent);
}

.par-evidence-row {
  display: grid;
  gap: 0.12rem;
}

.par-evidence-row span {
  color: var(--text-muted);
  font-size: 0.58rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.par-evidence-row strong {
  color: var(--text-color-85);
  font-size: 0.7rem;
  line-height: 1.3;
  overflow-wrap: anywhere;
}

.cnae-evidence-row span {
  color: var(--text-muted);
  font-size: 0.58rem;
  font-weight: 800;
  letter-spacing: 0.04em;
  text-transform: uppercase;
}

.cnae-evidence-row strong {
  color: var(--text-secondary);
  font-size: 0.7rem;
  font-weight: 650;
  line-height: 1.25;
}

.deceased-field {
  color: color-mix(in srgb, #94a3b8 78%, var(--text-color-85));
}

.deceased-field i {
  color: #94a3b8;
}

.deceased-badge {
  border: 1px solid color-mix(in srgb, #94a3b8 44%, transparent);
  background: color-mix(in srgb, #94a3b8 15%, transparent);
  color: color-mix(in srgb, #94a3b8 86%, var(--text-color-85));
}

.field-label {
  font-size: 0.6rem;
  text-transform: uppercase;
  font-weight: 500;
  color: var(--text-muted);
  letter-spacing: 0.02em;
}

.field-value {
  font-size: 0.75rem;
  font-weight: 600;
  color: var(--text-color-85);
  line-height: 1.2;
}

.mt-1 {
  margin-top: 0.25rem;
}

.mt-3 {
  margin-top: 0.75rem;
}

.panel-hint {
  font-size: 0.65rem;
  color: var(--text-muted);
  opacity: 0.6;
  display: flex;
  align-items: center;
  gap: 0.3rem;
  margin-top: auto;
}

.panel-action-btn {
  width: 100%;
  min-height: 2.25rem;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 0.45rem;
  border: 1px solid color-mix(in srgb, var(--primary-color) 45%, var(--tabs-border));
  border-radius: 6px;
  background: color-mix(in srgb, var(--primary-color) 9%, var(--card-bg));
  color: var(--primary-color);
  font: inherit;
  font-size: 0.72rem;
  font-weight: 600;
  cursor: pointer;
  transition:
    background 0.18s,
    border-color 0.18s;
}

.panel-action-btn:hover:not(:disabled) {
  background: color-mix(in srgb, var(--primary-color) 16%, var(--card-bg));
  border-color: var(--primary-color);
}

.panel-action-btn:focus-visible {
  outline: 2px solid var(--primary-color);
  outline-offset: 2px;
}

/* Farmácia Popular: Favoritar ao lado de Abrir detalhamento. */
/* Farmácia: "Abrir detalhamento" na primeira linha; Favoritar e a anotação abaixo. */
.panel-actions--farmacia {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
}
.panel-actions--farmacia .panel-action-btn { white-space: nowrap; }
.panel-actions--farmacia .detail-btn { flex: 1 0 100%; order: -1; }
.panel-actions--farmacia .favorite-btn {
  flex: 1 1 auto;
  width: auto;
  padding: 0 0.8rem;
  border-color: var(--tabs-border);
  background: var(--card-bg);
  color: var(--text-color-85);
}
.panel-actions--farmacia .favorite-btn:hover:not(:disabled) {
  border-color: var(--primary-color);
  background: color-mix(in srgb, var(--primary-color) 10%, var(--card-bg));
}
.panel-actions--farmacia .observation-btn {
  flex: 0 0 2.25rem;
  width: 2.25rem;
  padding: 0;
  border-color: var(--tabs-border);
  background: var(--card-bg);
  color: var(--text-muted);
}
.panel-actions--farmacia .observation-btn:hover:not(:disabled),
.panel-actions--farmacia .observation-btn.has-observation {
  border-color: color-mix(in srgb, var(--primary-color) 55%, var(--tabs-border));
  color: var(--primary-color);
}
.panel-actions--farmacia .favorite-btn.is-favorite {
  border-color: color-mix(in srgb, var(--primary-color) 55%, var(--tabs-border));
  background: color-mix(in srgb, var(--primary-color) 12%, var(--card-bg));
  color: var(--primary-color);
}

.panel-action-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.slide-in-enter-active,
.slide-in-leave-active {
  transition:
    opacity 0.25s,
    transform 0.25s;
}

.slide-in-enter-from,
.slide-in-leave-to {
  opacity: 0;
  transform: translateX(20px);
}
</style>
