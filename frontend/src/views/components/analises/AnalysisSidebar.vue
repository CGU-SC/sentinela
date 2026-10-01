<script setup>
import { computed } from 'vue';
import { storeToRefs } from 'pinia';
import InputSwitch from 'primevue/inputswitch';
import {
  CRM_ANTES_INSCRICAO_INDISPONIVEL_TOOLTIP,
  analysisTooltip,
} from '@/config/analysisTooltipConfig';
import {
  CRM_SEQUENCIA_SEVERIDADES, CRM_SITUACAO_CFM_OPCOES, CRM_UF_ATALHOS, CRM_UFS, crmFaixasDoGrupo,
} from '@/config/crmFiltrosMedico';
import { useCrmFiltrosMedicoStore } from '@/stores/crmFiltrosMedico';
import MultiOptionPicker from '@/views/components/common/MultiOptionPicker.vue';
import OptionPicker from '@/views/components/common/OptionPicker.vue';
import CrmFiltroFaixa from './CrmFiltroFaixa.vue';

const props = defineProps({
  /** Texto digitado na busca de médico (estado mantido pela AnalysesView). */
  searchQuery: { type: String, required: true },
  searchDisabled: { type: Boolean, default: false },
});
const emit = defineEmits(['search']);

const filtrosStore = useCrmFiltrosMedicoStore();
const { situacaoCfm, ufsCrm, antesInscricao, sequenciaSeveridadeMin, qtdAtivos: qtdFiltrosCadastro, antesInscricaoDisponivel } = storeToRefs(filtrosStore);

// A busca conta como filtro do painel e também é apagada pelo "Limpar".
const temBusca = computed(() => props.searchQuery.trim() !== '');
const qtdAtivos = computed(() => qtdFiltrosCadastro.value + (temBusca.value ? 1 : 0));
function limparTudo() {
  filtrosStore.limpar();
  if (temBusca.value) emit('search', '');
}

const FAIXAS_PRODUCAO = crmFaixasDoGrupo('producao');

/** Texto do botão "UF do CRM": Todas, a região do atalho, as siglas (até 3) ou a contagem. */
const ufRotulo = computed(() => {
  const ufs = ufsCrm.value;
  if (!ufs.length) return 'Todas';
  const regiao = CRM_UF_ATALHOS.find((a) => a.selecao.length === ufs.length && a.selecao.every((uf) => ufs.includes(uf)));
  if (regiao) return regiao.label;
  return ufs.length <= 3 ? [...ufs].sort().join(', ') : `${ufs.length} UFs`;
});
const FAIXAS_ATUACAO = crmFaixasDoGrupo('atuacao');
const FAIXAS_SEQUENCIA = crmFaixasDoGrupo('sequencia');
const sequenciaTooltip = analysisTooltip('crmFiltroSequenciaSeveridade');

const buscaTooltip = analysisTooltip('crmFiltroBusca');
const painelTooltip = analysisTooltip('crmFiltrosMedico');
const situacaoTooltip = analysisTooltip('crmFiltroSituacaoCfm');
const ufTooltip = analysisTooltip('crmFiltroUfCrm');
const antesTooltip = analysisTooltip('crmFiltroAntesInscricao');
</script>

<template>
  <aside class="analysis-selector">
    <div class="selector-header">
      <i class="pi pi-chart-bar selector-header-icon" />
      <span class="selector-header-label">Análises</span>
    </div>

    <div class="selector-groups">
      <div class="selector-group">
        <div class="group-title">Análises disponíveis</div>

        <router-link
          to="/analises"
          class="analysis-btn analysis-btn--active"
          aria-current="page"
        >
          <span class="analysis-btn-label">Análise de CRMs</span>
        </router-link>
      </div>

      <section class="selector-group filtros-medico" aria-labelledby="filtros-medico-titulo">
        <div class="filtros-cabecalho">
          <span id="filtros-medico-titulo" class="group-title">Filtros dos médicos</span>
          <i class="pi pi-info-circle filtro-info" v-tooltip.left="painelTooltip" tabindex="0" aria-label="Sobre os filtros dos médicos" />
        </div>
        <div class="filtros-status">
          <span>{{ qtdAtivos ? `${qtdAtivos} ${qtdAtivos === 1 ? 'ativo' : 'ativos'}` : 'Nenhum ativo' }}</span>
          <button type="button" class="filtros-limpar" :disabled="!qtdAtivos" @click="limparTudo">
            <i class="pi pi-eraser" aria-hidden="true" />Limpar
          </button>
        </div>

        <div class="filtro filtro-busca-bloco">
          <div class="filtro-rotulo">
            <label for="filtro-busca-medico">Buscar médico</label>
            <i class="pi pi-info-circle filtro-info" v-tooltip.left="buscaTooltip" tabindex="0" aria-label="Sobre a busca de médico" />
          </div>
          <div class="filtro-busca" :class="{ 'is-disabled': searchDisabled }">
            <i class="pi pi-search" aria-hidden="true" />
            <input
              id="filtro-busca-medico"
              type="text"
              role="searchbox"
              :value="searchQuery"
              maxlength="120"
              placeholder="Nome, CRM ou CRM/UF"
              :disabled="searchDisabled"
              @input="emit('search', $event.target.value)"
            />
            <button
              type="button"
              aria-label="Limpar busca de médico"
              :aria-hidden="!temBusca"
              :disabled="!temBusca"
              :class="{ 'is-hidden': !temBusca }"
              @click="emit('search', '')"
            >
              <i class="pi pi-eraser" aria-hidden="true" />
            </button>
          </div>
        </div>

        <div class="filtro-bloco">
          <div class="filtro-bloco-titulo"><i class="pi pi-id-card" aria-hidden="true" />Cadastro CFM</div>

          <div class="filtro">
            <div class="filtro-rotulo">
              <span id="filtro-situacao-cfm">Situação no CFM</span>
              <i class="pi pi-info-circle filtro-info" v-tooltip.left="situacaoTooltip" tabindex="0" aria-label="Sobre a situação no CFM" />
            </div>
            <div class="filtro-segmentos" role="radiogroup" aria-labelledby="filtro-situacao-cfm">
              <button
                v-for="opcao in CRM_SITUACAO_CFM_OPCOES"
                :key="opcao.label"
                type="button"
                role="radio"
                class="filtro-segmento"
                :class="{ 'is-active': situacaoCfm === opcao.value }"
                :aria-checked="situacaoCfm === opcao.value"
                @click="filtrosStore.setSituacaoCfm(opcao.value)"
              >{{ opcao.label }}</button>
            </div>
          </div>

          <div class="filtro">
            <div class="filtro-rotulo">
              <span id="filtro-uf-crm">UF do CRM</span>
              <i class="pi pi-info-circle filtro-info" v-tooltip.left="ufTooltip" tabindex="0" aria-label="Sobre a UF do CRM" />
            </div>
            <div class="filtro-picker" aria-labelledby="filtro-uf-crm">
              <MultiOptionPicker
                :valor="ufsCrm"
                :opcoes="CRM_UFS"
                :atalhos="CRM_UF_ATALHOS"
                :rotulo="ufRotulo"
                nome-plural="UFs"
                @select="filtrosStore.setUfsCrm($event)"
              />
            </div>
          </div>

          <div class="filtro filtro--switch">
            <div class="filtro-rotulo">
              <label for="filtro-antes-inscricao">Prescreveu antes da 1ª inscrição</label>
              <i class="pi pi-info-circle filtro-info" v-tooltip.left="antesTooltip" tabindex="0" aria-label="Sobre prescrições antes da inscrição" />
            </div>
            <span v-tooltip.left="antesInscricaoDisponivel ? null : CRM_ANTES_INSCRICAO_INDISPONIVEL_TOOLTIP">
              <InputSwitch
                input-id="filtro-antes-inscricao"
                :model-value="antesInscricao"
                :disabled="!antesInscricaoDisponivel"
                @update:model-value="filtrosStore.setAntesInscricao($event)"
              />
            </span>
          </div>
        </div>

        <div class="filtro-bloco">
          <div class="filtro-bloco-titulo"><i class="pi pi-chart-bar" aria-hidden="true" />Produção</div>
          <CrmFiltroFaixa v-for="tipo in FAIXAS_PRODUCAO" :key="tipo" :tipo="tipo" />
        </div>

        <div class="filtro-bloco">
          <div class="filtro-bloco-titulo"><i class="pi pi-building" aria-hidden="true" />Atuação nas farmácias</div>
          <CrmFiltroFaixa v-for="tipo in FAIXAS_ATUACAO" :key="tipo" :tipo="tipo" />
        </div>

        <div class="filtro-bloco">
          <div class="filtro-bloco-titulo"><i class="pi pi-bolt" aria-hidden="true" />Autorizações em sequência</div>
          <div class="filtro">
            <div class="filtro-rotulo">
              <span>Severidade mínima</span>
              <i class="pi pi-info-circle filtro-info" v-tooltip.left="sequenciaTooltip" tabindex="0" aria-label="Sobre as autorizações em sequência" />
            </div>
            <div class="filtro-picker">
              <OptionPicker
                :valor="sequenciaSeveridadeMin"
                :opcoes="CRM_SEQUENCIA_SEVERIDADES"
                rotulo-acessivel="Severidade mínima das autorizações em sequência"
                @select="filtrosStore.setSequenciaSeveridadeMin($event)"
              />
            </div>
          </div>
          <CrmFiltroFaixa v-for="tipo in FAIXAS_SEQUENCIA" :key="tipo" :tipo="tipo" />
        </div>
      </section>
    </div>
  </aside>
</template>

<style scoped>
.analysis-selector {
  width: var(--indicator-selector-width, 260px);
  flex-shrink: 0;
  position: sticky;
  top: 0;
  min-height: calc(100dvh - 56px - 1.25rem);
  display: flex;
  flex-direction: column;
  gap: 0;
  background: var(--card-bg);
  border: 1px solid var(--card-border);
  border-radius: 8px;
  overflow: visible;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
  align-self: start;
}

.selector-header {
  display: flex;
  align-items: center;
  gap: 0.6rem;
  padding: 0.9rem 1rem;
  border-bottom: 1px solid var(--card-border);
  background: var(--sidebar-heading-tint);
}

.selector-header-icon {
  font-size: 0.9rem;
  color: var(--sidebar-heading-icon);
}

.selector-header-label {
  font-size: 0.75rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--text-color-85);
  opacity: 0.85;
}

.selector-groups {
  display: flex;
  flex-direction: column;
  padding: 0.5rem 0;
}

.selector-group {
  display: flex;
  flex-direction: column;
}

.group-title {
  padding: 0.6rem 1rem 0.25rem;
  font-size: 0.7rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.07em;
  color: color-mix(in srgb, var(--primary-color) 15%, #78716c);
}

.analysis-btn {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  padding: 0.5rem 1rem;
  min-height: 2.4rem;
  background: transparent;
  border: none;
  text-decoration: none;
  cursor: pointer;
  text-align: left;
  color: var(--text-color-85);
  opacity: 1;
  min-width: 0;
}

.analysis-btn--active {
  background: color-mix(in srgb, var(--primary-color) 12%, var(--card-bg));
  box-shadow: inset 1px 0 0 var(--primary-color);
}

/* ── Filtros dos médicos ─────────────────────────────────────────────────── */
.filtros-medico { margin-top: 0.35rem; border-top: 1px solid var(--card-border); }
.filtros-cabecalho { display: flex; align-items: center; justify-content: space-between; padding-right: 1rem; }
.filtro-info { color: var(--text-muted); font-size: 0.75rem; opacity: 0.75; cursor: help; }
.filtro-info:hover, .filtro-info:focus-visible { opacity: 1; }
.filtros-status { display: flex; align-items: center; justify-content: space-between; padding: 0 1rem 0.5rem; color: var(--text-muted); font-size: 0.7rem; }
.filtros-limpar { display: inline-flex; align-items: center; gap: 0.3rem; padding: 0.15rem 0.35rem; border: 0; border-radius: 5px; background: transparent; color: var(--color-error); font: inherit; font-size: 0.7rem; font-weight: 500; cursor: pointer; }
.filtros-limpar .pi { font-size: 0.7rem; }
.filtros-limpar:hover:not(:disabled), .filtros-limpar:focus-visible { background: color-mix(in srgb, var(--color-error) 10%, transparent); }
.filtros-limpar:disabled { color: var(--text-muted); opacity: 0.5; cursor: default; }
.filtro-busca-bloco { margin: 0 0.75rem 0.75rem; }
.filtro-busca { display: flex; align-items: center; gap: 0.45rem; box-sizing: border-box; height: 34px; padding: 0.35rem 0.55rem; border: 1px solid var(--card-border); border-radius: 7px; color: var(--text-muted); }
.filtro-busca:focus-within { border-color: var(--primary-color); }
.filtro-busca.is-disabled { opacity: 0.6; }
.filtro-busca > .pi { font-size: 0.75rem; }
.filtro-busca input { width: 100%; min-width: 0; padding: 0; border: 0; outline: 0; background: transparent; color: var(--text-color-85); font: inherit; font-size: 0.73rem; }
.filtro-busca input::placeholder { color: var(--text-muted); }
.filtro-busca button { display: inline-flex; align-items: center; justify-content: center; flex-shrink: 0; width: 18px; height: 18px; padding: 0; border: 0; background: transparent; color: var(--color-error); opacity: 0.7; cursor: pointer; }
.filtro-busca button.is-hidden { visibility: hidden; }
.filtro-busca button .pi { font-size: 0.72rem; }
.filtro-busca button:hover, .filtro-busca button:focus-visible { opacity: 1; }
.filtro-busca button:focus-visible { outline: 2px solid var(--color-error); outline-offset: 2px; border-radius: 3px; }
.filtro-bloco { display: flex; flex-direction: column; gap: 0.85rem; margin: 0 0.75rem 0.75rem; padding: 0.7rem 0.7rem 0.8rem; border: 1px solid var(--card-border); border-radius: 8px; background: color-mix(in srgb, var(--text-color) 2%, transparent); }
.filtro-bloco-titulo { display: flex; align-items: center; gap: 0.4rem; color: var(--text-color-85); font-size: 0.72rem; font-weight: 600; }
.filtro-bloco-titulo .pi { color: var(--primary-color); font-size: 0.75rem; }
.filtro { display: flex; flex-direction: column; gap: 0.4rem; }
.filtro--switch { flex-direction: row; align-items: center; justify-content: space-between; gap: 0.5rem; }
.filtro-rotulo { display: flex; align-items: center; gap: 0.35rem; color: var(--text-secondary); font-size: 0.7rem; font-weight: 500; }
.filtro-rotulo label { cursor: pointer; }
/* Largura pelo texto: "Não localizado" é bem maior que "Todos". */
.filtro-segmentos { display: flex; gap: 2px; padding: 2px; border: 1px solid var(--card-border); border-radius: 7px; }
.filtro-segmento { border: 0; background: transparent; color: var(--text-secondary); font: inherit; font-weight: 500; cursor: pointer; transition: background 0.15s ease, color 0.15s ease, box-shadow 0.15s ease; }
.filtro-segmento { flex: 1 1 auto; min-height: 26px; padding: 0 0.4rem; border-radius: 5px; font-size: 0.68rem; white-space: nowrap; }
/* Botão do seletor ocupa a largura do bloco, como os filtros de faixa. */
.filtro-picker :deep(.rp-gatilho) { width: 100%; color: var(--sidebar-text); }
.filtro-segmento:hover { color: var(--text-color-85); background: color-mix(in srgb, var(--text-color-85) 6%, transparent); }
.filtro-segmento:focus-visible { outline: 2px solid color-mix(in srgb, var(--primary-color) 70%, transparent); outline-offset: 1px; }
.filtro-segmento.is-active { color: var(--primary-color); background: color-mix(in srgb, var(--primary-color) 16%, transparent); box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--primary-color) 45%, transparent); font-weight: 600; }

.analysis-btn-label {
  font-size: 0.78rem;
  font-weight: 600;
  line-height: 1.2;
  color: var(--primary-color);
  flex: 1;
  min-width: 0;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
</style>
