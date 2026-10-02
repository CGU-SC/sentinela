<script setup>
import { computed } from 'vue';
import { storeToRefs } from 'pinia';
import Button from 'primevue/button';
import {
  analysisTooltip,
} from '@/config/analysisTooltipConfig';
import { filterActionTooltip } from '@/config/filterTooltipConfig';
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
const { situacaoCfm, ufsCrm, sequenciaSeveridadeMin, qtdAtivos: qtdFiltrosCadastro } = storeToRefs(filtrosStore);

// A busca conta como filtro do painel e também é apagada pelo "Limpar Filtros".
const temBusca = computed(() => props.searchQuery.trim() !== '');
const qtdAtivos = computed(() => qtdFiltrosCadastro.value + (temBusca.value ? 1 : 0));
function limparTudo() {
  filtrosStore.limpar();
  if (temBusca.value) emit('search', '');
}

const FAIXAS_PRODUCAO = crmFaixasDoGrupo('producao');

/**
 * Texto do botão "UF do CRM": Todas, a região do atalho, as siglas (até 3),
 * "Todas exceto …" quando faltam até 3 UFs, ou a contagem.
 */
const ufRotulo = computed(() => {
  const ufs = ufsCrm.value;
  if (!ufs.length) return 'Todas';
  const regiao = CRM_UF_ATALHOS.find((a) => a.selecao.length === ufs.length && a.selecao.every((uf) => ufs.includes(uf)));
  if (regiao) return regiao.label;
  if (ufs.length <= 3) return [...ufs].sort().join(', ');
  const fora = CRM_UFS.filter((uf) => !ufs.includes(uf));
  if (fora.length <= 3) return `Todas exceto ${fora.join(', ')}`;
  return `${ufs.length} UFs`;
});
const FAIXAS_SEQUENCIA = crmFaixasDoGrupo('sequencia');
const sequenciaTooltip = analysisTooltip('crmFiltroSequenciaSeveridade');

const limparTooltip = filterActionTooltip('Limpar filtro', 'Restaura este filtro ao valor padrão.', 'pi-eraser');
const buscaTooltip = analysisTooltip('crmFiltroBusca');
const painelTooltip = analysisTooltip('crmFiltrosMedico');
const situacaoTooltip = analysisTooltip('crmFiltroSituacaoCfm');
const ufTooltip = analysisTooltip('crmFiltroUfCrm');
</script>

<template>
  <aside class="analysis-selector">
    <div class="selector-header">
      <i class="pi pi-chart-bar selector-header-icon" />
      <span class="selector-header-label">Análises disponíveis</span>
    </div>

    <div class="selector-groups">
      <div class="selector-group">
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
          <i class="pi pi-info-circle filtro-info help-icon" v-tooltip.left="painelTooltip" tabindex="0" aria-label="Sobre os filtros dos médicos" />
        </div>
        <div class="filtro-bloco">
          <div class="filtro-bloco-titulo"><i class="pi pi-id-card" aria-hidden="true" />Cadastro CFM</div>

          <div class="filtro filtro-busca-bloco" :class="{ 'is-ativo': temBusca }">
            <div class="filtro-rotulo">
              <label for="filtro-busca-medico">Buscar médico</label>
              <i class="pi pi-info-circle filtro-info help-icon" v-tooltip.left="buscaTooltip" tabindex="0" aria-label="Sobre a busca de médico" />
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

          <div class="filtro" :class="{ 'is-ativo': situacaoCfm !== null }">
            <div class="filtro-rotulo">
              <span id="filtro-situacao-cfm">Situação no CFM</span>
              <i class="pi pi-info-circle filtro-info help-icon" v-tooltip.left="situacaoTooltip" tabindex="0" aria-label="Sobre a situação no CFM" />
              <button
                v-if="situacaoCfm !== null"
                type="button"
                class="filtro-limpar"
                aria-label="Limpar o filtro situação no CFM"
                v-tooltip.left="limparTooltip"
                @click="filtrosStore.setSituacaoCfm(null)"
              >
                <i class="pi pi-eraser" aria-hidden="true" />
              </button>
            </div>
            <div class="filtro-picker" aria-labelledby="filtro-situacao-cfm">
              <OptionPicker
                :valor="situacaoCfm"
                :opcoes="CRM_SITUACAO_CFM_OPCOES"
                rotulo-acessivel="Situação no CFM"
                @select="filtrosStore.setSituacaoCfm($event)"
              />
            </div>
          </div>

          <div class="filtro" :class="{ 'is-ativo': ufsCrm.length > 0 }">
            <div class="filtro-rotulo">
              <span id="filtro-uf-crm">UF do CRM</span>
              <i class="pi pi-info-circle filtro-info help-icon" v-tooltip.left="ufTooltip" tabindex="0" aria-label="Sobre a UF do CRM" />
              <button
                v-if="ufsCrm.length > 0"
                type="button"
                class="filtro-limpar"
                aria-label="Limpar o filtro UF do CRM"
                v-tooltip.left="limparTooltip"
                @click="filtrosStore.setUfsCrm([])"
              >
                <i class="pi pi-eraser" aria-hidden="true" />
              </button>
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
        </div>

        <div class="filtro-bloco">
          <div class="filtro-bloco-titulo"><i class="pi pi-chart-bar" aria-hidden="true" />Produção e atuação</div>
          <CrmFiltroFaixa v-for="tipo in FAIXAS_PRODUCAO" :key="tipo" :tipo="tipo" />
        </div>

        <div class="filtro-bloco">
          <div class="filtro-bloco-titulo"><i class="pi pi-bolt" aria-hidden="true" />Autorizações em sequência</div>
          <div class="filtro" :class="{ 'is-ativo': sequenciaSeveridadeMin !== null }">
            <div class="filtro-rotulo">
              <span>Severidade mínima</span>
              <i class="pi pi-info-circle filtro-info help-icon" v-tooltip.left="sequenciaTooltip" tabindex="0" aria-label="Sobre as autorizações em sequência" />
              <button
                v-if="sequenciaSeveridadeMin !== null"
                type="button"
                class="filtro-limpar"
                aria-label="Limpar o filtro severidade mínima"
                v-tooltip.left="limparTooltip"
                @click="filtrosStore.setSequenciaSeveridadeMin(null)"
              >
                <i class="pi pi-eraser" aria-hidden="true" />
              </button>
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

        <!-- Mesmo botão da barra de filtros da esquerda (AppSidebar). -->
        <div class="filtros-rodape">
          <Button
            :label="qtdAtivos > 0 ? `Limpar Filtros (${qtdAtivos})` : 'Limpar Filtros'"
            icon="pi pi-undo"
            outlined
            :severity="qtdAtivos > 0 ? 'warn' : 'secondary'"
            class="w-full clear-filters-btn"
            :class="{ 'filters-active': qtdAtivos > 0 }"
            @click="limparTudo"
          />
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
.filtro-info { color: var(--text-muted); font-size: 0.8rem; opacity: 0.75; cursor: help; }
.filtro-info:hover, .filtro-info:focus-visible { opacity: 1; }
/* Mesma caixa dos seletores (.rp-gatilho): fundo, raio, recuo e tamanho do texto. */
.filtro-busca { display: flex; align-items: center; gap: 0.45rem; box-sizing: border-box; height: 34px; padding: 0 0.7rem; border: 1px solid var(--card-border); border-radius: 6px; background: var(--card-bg); color: var(--text-muted); transition: border-color 0.15s ease; }
.filtro-busca:focus-within { border-color: var(--primary-color); }
.filtro-busca.is-disabled { opacity: 0.6; }
.filtro-busca > .pi { font-size: 0.75rem; }
.filtro-busca input { width: 100%; min-width: 0; padding: 0; border: 0; outline: 0; background: transparent; color: var(--text-color-85); font: inherit; font-size: 0.8125rem; font-weight: 400; }
.filtro-busca input::placeholder { color: var(--text-muted); }
.filtro-busca button { display: inline-flex; align-items: center; justify-content: center; flex-shrink: 0; width: 18px; height: 18px; padding: 0; border: 0; background: transparent; color: var(--color-error); opacity: 0.7; cursor: pointer; }
.filtro-busca button.is-hidden { visibility: hidden; }
.filtro-busca button .pi { font-size: 0.72rem; }
.filtro-busca button:hover, .filtro-busca button:focus-visible { opacity: 1; }
.filtro-busca button:focus-visible { outline: 2px solid var(--color-error); outline-offset: 2px; border-radius: 3px; }
/* Grupo de filtros sem caixa (mesmo padrão da barra da esquerda, AppSidebar
   .filter-group-title): subtítulo com ícone e linha fina; 20px entre filtros,
   16px do subtítulo ao primeiro filtro e 24px entre grupos. */
.filtro-bloco { display: flex; flex-direction: column; gap: 1.25rem; margin: 0 0.75rem 1.5rem; }
.filtros-cabecalho + .filtro-bloco { margin-top: 0.5rem; }
.filtro-bloco-titulo { display: flex; align-items: center; gap: 0.5rem; margin-bottom: -0.25rem; color: color-mix(in srgb, var(--primary-color) 15%, #78716c); font-size: 0.875rem; font-weight: 600; line-height: 1.2; white-space: nowrap; }
.filtro-bloco-titulo::after { content: ""; flex: 1; height: 1px; background: var(--card-border); }
.filtro-bloco-titulo .pi { font-size: 0.78rem; }
.filtro { display: flex; flex-direction: column; gap: 0.4rem; }
/* Título do filtro: texto principal do tema a 70% (o mesmo da sidebar esquerda). */
.filtro-rotulo { display: flex; align-items: center; gap: 0.35rem; color: color-mix(in srgb, var(--text-color) 70%, transparent); font-size: 0.8125rem; font-weight: 500; }
.filtro-rotulo label { cursor: pointer; }
/* Botão do seletor ocupa a largura do bloco, como os filtros de faixa. */
.filtro-picker :deep(.rp-gatilho) { width: 100%; color: var(--text-color-85); font-size: 0.8125rem; font-weight: 400; }
/* Hover neutro, a mesma cor da barra de filtros da esquerda (AppSidebar): borda
   clareada com o cinza do texto. Filtro ativo e campo em foco continuam na cor primária. */
.filtro:not(.is-ativo) :deep(.rp-gatilho:not(:disabled):hover),
.filtro-busca-bloco:not(.is-ativo) .filtro-busca:not(.is-disabled):not(:focus-within):hover { border-color: color-mix(in srgb, var(--sidebar-text) 28%, var(--sidebar-border)); }

/* Filtro ligado (também nos filtros de faixa, por :deep): rótulo e campo na cor
   primária, como no modal Histórico do CRM, e borracha para voltar ao padrão. */
/* Filtro sem valor ("Todos", "Todas"...): texto do campo apagado; com valor, claro. */
.filtro:not(.is-ativo) :deep(.rp-gatilho) { color: var(--text-muted); }
.filtro.is-ativo :deep(.filtro-rotulo > span),
.filtro.is-ativo :deep(.filtro-rotulo > label) { color: var(--primary-color); }
.filtro.is-ativo :deep(.rp-gatilho),
.filtro-busca-bloco.is-ativo .filtro-busca { border-color: var(--primary-color); background: color-mix(in srgb, var(--primary-color) 10%, transparent); }
.filtro :deep(.filtro-limpar) { display: inline-flex; align-items: center; justify-content: center; flex-shrink: 0; width: 14px; height: 14px; margin-left: auto; padding: 0; border: none; background: none; color: var(--color-error); opacity: 0.7; cursor: pointer; transition: opacity 0.15s; }
.filtro :deep(.filtro-limpar:hover), .filtro :deep(.filtro-limpar:focus-visible) { opacity: 1; }
.filtro :deep(.filtro-limpar:focus-visible) { outline: 2px solid var(--color-error); outline-offset: 2px; border-radius: 3px; }
.filtro :deep(.filtro-limpar .pi) { font-size: 0.75rem; }

/* Botão "Limpar Filtros": mesmo estilo do da barra de filtros da esquerda (AppSidebar). */
.filtros-rodape { padding: 0.25rem 0.75rem 0.75rem; }
:deep(.clear-filters-btn.p-button) { height: 2.125rem; padding: 0 0.75rem; justify-content: center; gap: 0.45rem; background: transparent !important; transition: all 0.2s ease !important; }
/* Tamanho alinhado aos campos de filtro (34px de altura, texto de 12,5px);
   ícone e texto juntos no centro. */
:deep(.clear-filters-btn.p-button .p-button-label) { flex: 0 0 auto; font-size: 0.78rem; font-weight: 600; }
:deep(.clear-filters-btn.p-button .p-button-icon) { margin: 0; font-size: 0.78rem; }
:deep(.clear-filters-btn.p-button:hover) { background: transparent !important; border-color: color-mix(in srgb, var(--primary-color) 50%, transparent) !important; color: var(--primary-color) !important; }
:deep(.clear-filters-btn.p-button:focus),
:deep(.clear-filters-btn.p-button:active) { outline: none !important; box-shadow: none !important; }
:deep(.clear-filters-btn.p-button:focus-visible) { box-shadow: 0 0 0 2px var(--primary-color) !important; }
:deep(.filters-active.p-button) { position: relative; overflow: hidden; background: color-mix(in srgb, var(--primary-color) 12%, transparent) !important; border-color: var(--primary-color) !important; color: var(--primary-color) !important; }
:deep(.filters-active.p-button::after) { content: ""; position: absolute; top: 0; left: -100%; width: 100%; height: 100%; background: linear-gradient(90deg, transparent, rgba(255, 255, 255, 0.1), rgba(255, 255, 255, 0.2), rgba(255, 255, 255, 0.1), transparent); animation: shimmer-sweep 3s infinite ease-in-out; }
:deep(.filters-active.p-button .p-button-icon) { animation: icon-spin-subtle 3s infinite ease-in-out; }
@keyframes shimmer-sweep { 0% { left: -100%; } 20% { left: 100%; } 100% { left: 100%; } }
@keyframes icon-spin-subtle { 0%, 75% { transform: rotate(0deg); } 90% { transform: rotate(-360deg); } 100% { transform: rotate(-360deg); } }

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
