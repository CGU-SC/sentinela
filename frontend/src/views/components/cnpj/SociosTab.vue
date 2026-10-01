<script setup>
import { ref, computed } from "vue";
import { storeToRefs } from "pinia";
import { useCnpjDetailStore } from "@/stores/cnpjDetail";
import { useFormatting } from "@/composables/useFormatting";
import TabPlaceholder from "./TabPlaceholder.vue";
import { useThemeStore } from "@/stores/theme";
import { DATA_NEUTRAL } from "@/config/colors";

const cnpjDetailStore = useCnpjDetailStore();
const themeStore = useThemeStore();
// Cor de dados neutra (azul-aço), a mesma da barra "Participação no valor" do Perfil de CRMs.
const dataColorVars = computed(() => ({ "--data-color": DATA_NEUTRAL[themeStore.isDark ? "dark" : "light"].strong }));
const { sociosData, sociosLoading, sociosError, dadosCadastro } = storeToRefs(cnpjDetailStore);
const { formatarData, formatPercent, formatTitleCase, formatCurrencyFull } = useFormatting();

const mostrarApenasAtivos = ref(false);

const socios = computed(() => {
  const lista = sociosData.value?.socios || [];
  if (mostrarApenasAtivos.value) {
    return lista.filter(s => !s.data_exclusao_sociedade);
  }
  return lista;
});

const dataProcessamento = computed(() => sociosData.value?.data_processamento || null);

const formatCpfCnpj = (v) => {
  if (!v) return "—";
  const clean = v.replace(/\D/g, "");
  if (clean.length === 11) {
    return clean.replace(/^(\d{3})(\d{3})(\d{3})(\d{2})$/, "$1.$2.$3-$4");
  }
  if (clean.length === 14) {
    return clean.replace(/^(\d{2})(\d{3})(\d{3})(\d{4})(\d{2})$/, "$1.$2.$3/$4-$5");
  }
  return v;
};

const formatTipoSocio = (v) => {
  if (v === "PF") return "Pessoa Física";
  if (v === "PJ") return "Pessoa Jurídica";
  if (v === "ES" || v === "EX") return "PF/PJ DOMICILIADO NO EXTERIOR";
  return v;
};

// Determina se o sócio ainda é ativo (sem data de exclusão)
const isAtivo = (socio) => !socio.data_exclusao_sociedade;

const calcularIdade = (dataNasc) => {
  if (!dataNasc) return null;
  const hoje = new Date();
  const nasc = new Date(dataNasc);
  let idade = hoje.getFullYear() - nasc.getFullYear();
  const m = hoje.getMonth() - nasc.getMonth();
  if (m < 0 || (m === 0 && hoje.getDate() < nasc.getDate())) {
    idade--;
  }
  return idade;
};

const copiedKey = ref(null);

const copyAndSignal = (text, key) => {
  if (!text) return;
  navigator.clipboard.writeText(text);
  copiedKey.value = key;
  setTimeout(() => {
    if (copiedKey.value === key) copiedKey.value = null;
  }, 2000);
};

</script>

<template>
  <div class="socios-tab tab-content" :style="dataColorVars">

    <!-- ── Estados sem dados: fora do card ──────────────────────────────── -->
    <div
      v-if="sociosLoading && !sociosData && !sociosError"
      class="socios-initial-loading-sentinel"
      aria-hidden="true"
    />

    <TabPlaceholder
      v-else-if="sociosError"
      variant="error"
      icon="pi-exclamation-circle"
      title="Erro ao carregar"
      :description="sociosError"
    />

    <TabPlaceholder
      v-else-if="socios.length === 0"
      icon="pi-users"
      title="Quadro societário não encontrado"
      description="Nenhum dado societário disponível para este estabelecimento na base atual."
    />

    <!-- ── Card com dados: só renderiza quando há sócios ─────────────────── -->
    <div v-else class="socios-card animate-fade-in">
      <div class="section-header">
        <div class="header-left">
          <i class="pi pi-users" />
          <div class="header-text">
            <h2 class="title">
              QUADRO SOCIETÁRIO
              <span v-if="dadosCadastro?.natureza_juridica" class="natureza-badge-inline">
                {{ formatTitleCase(dadosCadastro.natureza_juridica) }}
              </span>
            </h2>
            <p class="subtitle">Sócios e administradores registrados na Receita Federal.</p>
          </div>
        </div>
        
        <div class="header-right">
          <div class="header-item filter-switch-group-horizontal" @click="mostrarApenasAtivos = !mostrarApenasAtivos">
            <span class="label">APENAS ATIVOS</span>
            <div class="custom-switch compact" :class="{ 'active': mostrarApenasAtivos }">
              <div class="switch-slider"></div>
            </div>
          </div>
          <div class="header-divider"></div>
          <div class="header-item">
            <span class="label">Capital Social</span>
            <span class="value">{{ formatCurrencyFull(dadosCadastro?.capital_social || 0) }}</span>
          </div>
          <div class="header-divider"></div>
          <div class="header-item help-icon-host" v-tooltip.top="'Data da última sincronização com a base oficial da Receita Federal.'">
            <span class="label">Atualização <i class="pi pi-info-circle help-icon" aria-hidden="true" /></span>
            <span class="value value-muted">{{ formatarData(dataProcessamento) }}</span>
          </div>
        </div>
      </div>
      

      


      <div class="table-wrapper">
        <table class="premium-table">
          <thead>
            <tr>
              <th>Sócio / Nome Empresarial</th>
              <th class="col-center">CPF / CNPJ</th>
              <th>Qualificação</th>
              <th>Localização</th>
              <th class="col-center">Participação</th>
              <th class="col-center">Entrada</th>
              <th class="col-center">Saída / Situação</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="s in socios" :key="s.cpf_cnpj_socio" :class="{ 'row-inactive': !isAtivo(s) }">
              <td>
                <div class="socio-name">
                  <div class="name-row">
                    <span class="main-name">{{ s.nome_socio || 'NOME NÃO INFORMADO' }}</span>
                    <span v-if="s.is_falecido" class="deceased-badge-inline" v-tooltip.top="'Sócio consta como falecido na base unificada.'">
                      <i class="pi pi-exclamation-triangle" /> FALECIDO
                    </span>
                    <span v-if="s.is_cadunico" class="cadunico-badge-inline" v-tooltip.top="'Sócio consta como inscrito no Cadastro Único.'">
                      <i class="pi pi-id-card" /> CADÚNICO
                    </span>
                    <span v-if="s.is_esocial" class="esocial-badge-inline" v-tooltip.top="'Sócio com vínculo trabalhista em outro CNPJ.'">
                      <i class="pi pi-briefcase" /> ESOCIAL
                    </span>
                    <span v-if="s.is_seguro_defeso" class="seguro-defeso-badge-inline" v-tooltip.top="'Sócio beneficiário do Seguro Defeso.'">
                      <i class="pi pi-wallet" /> SEGURO DEFESO
                    </span>
                    <i :class="['pi', copiedKey === s.cpf_cnpj_socio + '-name' ? 'pi-check text-success' : 'pi-copy', 'copy-btn']" 
                       @click="copyAndSignal(s.nome_socio, s.cpf_cnpj_socio + '-name')" 
                       v-tooltip.top="'Copiar Nome'" />
                  </div>
                  
                  <div class="socio-meta">
                    <span v-if="s.indicador_socio" class="socio-type">{{ formatTipoSocio(s.indicador_socio) }}</span>
                    <span v-if="s.data_nascimento_socio" class="socio-age" v-tooltip.top="formatarData(s.data_nascimento_socio)">
                      • {{ calcularIdade(s.data_nascimento_socio) }} anos
                    </span>
                  </div>
                  
                  <!-- Representante Legal (Se houver) -->
                  <div v-if="s.cpf_representante" class="representante-info" v-tooltip.top="'Representante Legal'">
                    <i class="pi pi-user-edit" />
                    <div class="rep-content">
                      <div class="rep-name-row">
                        <span class="rep-name">{{ s.nome_representante || 'REPRESENTANTE S/ NOME' }}</span>
                        <i :class="['pi', copiedKey === s.cpf_cnpj_socio + '-rep-name' ? 'pi-check text-success' : 'pi-copy', 'copy-btn small']" 
                           @click="copyAndSignal(s.nome_representante, s.cpf_cnpj_socio + '-rep-name')" 
                           v-tooltip.top="'Copiar Nome do Rep.'" />
                      </div>
                      <span class="rep-meta">
                        <span class="rep-cpf-row">
                          {{ formatCpfCnpj(s.cpf_representante) }}
                          <i :class="['pi', copiedKey === s.cpf_cnpj_socio + '-rep-cpf' ? 'pi-check text-success' : 'pi-copy', 'copy-btn small']" 
                             @click="copyAndSignal(s.cpf_representante, s.cpf_cnpj_socio + '-rep-cpf')" 
                             v-tooltip.top="'Copiar CPF'" />
                        </span>
                        <span v-if="s.descricao_qualificacao_representante"> • {{ s.descricao_qualificacao_representante }} <span v-if="s.id_qualificacao_representante">({{ s.id_qualificacao_representante }})</span></span>
                        <span v-if="s.data_nascimento_representante"> • {{ calcularIdade(s.data_nascimento_representante) }} anos</span>
                      </span>
                    </div>
                  </div>
                </div>
              </td>
              <td class="col-center font-mono">
                <div class="cpf-cell-content">
                  {{ formatCpfCnpj(s.cpf_cnpj_socio) }}
                  <i :class="['pi', copiedKey === s.cpf_cnpj_socio + '-cpf' ? 'pi-check text-success' : 'pi-copy', 'copy-btn']" 
                     @click="copyAndSignal(s.cpf_cnpj_socio, s.cpf_cnpj_socio + '-cpf')" 
                     v-tooltip.top="'Copiar CPF/CNPJ'" />
                </div>
              </td>
              <td class="qualificacao-cell">
                {{ s.descricao_qualificacao || '—' }}
              </td>
              <td class="location-cell">
                <div v-if="s.municipio" class="location-wrapper">
                  <i class="pi pi-map-marker" />
                  <span>{{ formatTitleCase(s.municipio) }} / {{ s.uf }}</span>
                </div>
                <span v-else>—</span>
              </td>
              <td class="col-center">
                <div class="pct-container" v-if="s.percentual_qualificacao > 0">
                  <div class="pct-bar-bg">
                    <div class="pct-bar-fill" :style="{ width: s.percentual_qualificacao + '%' }"></div>
                  </div>
                  <span class="pct-val">{{ formatPercent(s.percentual_qualificacao) }}</span>
                </div>
                <span v-else>—</span>
              </td>
              <td class="col-center">{{ formatarData(s.data_entrada_sociedade) }}</td>
              <td class="col-center">
                <span v-if="s.data_exclusao_sociedade" class="status-badge inactive">
                  Saída em {{ formatarData(s.data_exclusao_sociedade) }}
                </span>
                <span v-else-if="s.is_falecido" class="status-badge deceased">
                  <i class="pi pi-exclamation-circle" /> Falecido
                </span>
                <span v-else class="status-badge active">Ativo</span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>

<style scoped>
.socios-tab {
  height: 100%;
}

.socios-card {
  display: flex;
  flex-direction: column;
  gap: 1.5rem;
  background: var(--card-bg);
  border: 1px solid var(--card-border);
  border-radius: 12px;
  padding: 1.25rem;
  min-height: 20rem;
  backdrop-filter: blur(10px);
  -webkit-backdrop-filter: blur(10px);
  box-shadow: 0 2px 8px rgba(0,0,0,0.06);
}

.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0.5rem 0;
  border-bottom: 1px solid var(--tabs-border);
  margin-bottom: 0.75rem;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 1rem;
}

.header-left i {
  font-size: 1rem;
  color: var(--primary-color);
}

.title {
  margin: 0;
  font-size: 0.85rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: var(--text-color-85);
  opacity: 0.90;
}

.subtitle {
  margin: 0.2rem 0 0 0;
  font-size: 0.85rem;
  color: var(--text-muted);
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.natureza-badge-inline {
  display: inline-flex;
  align-items: center;
  margin-left: 0.75rem;
  padding: 0.25rem 0.75rem;
  background: color-mix(in srgb, var(--primary-color) 15%, transparent);
  border: 1px solid color-mix(in srgb, var(--primary-color) 40%, transparent);
  border-radius: 6px;
  color: var(--primary-color);
  font-size: 0.85rem;
  font-weight: 700;
  text-transform: none; /* Mantém o Title Case */
  letter-spacing: 0;
  vertical-align: middle;
  box-shadow: 0 1px 2px rgba(0,0,0,0.05);
}

.data-ref {
  background: color-mix(in srgb, var(--text-muted) 10%, transparent);
  color: var(--text-secondary);
  padding: 0.1rem 0.4rem;
  border-radius: 4px;
  font-size: 0.7rem;
  font-weight: 600;
  border: 1px solid color-mix(in srgb, var(--text-muted) 20%, transparent);
  cursor: help;
}

.header-badge {
  background: color-mix(in srgb, var(--primary-color) 15%, transparent);
  color: var(--primary-color);
  padding: 0.4rem 0.8rem;
  border-radius: 99px;
  font-size: 0.75rem;
  font-weight: 600;
  border: 1px solid color-mix(in srgb, var(--primary-color) 30%, transparent);
}

/* Tabela Premium */
.table-wrapper {
  overflow-x: auto;
}

.premium-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.9rem;
  table-layout: fixed; /* Força larguras fixas */
}

.premium-table th {
  text-align: left;
  padding: 0.85rem 1rem;
  font-size: 0.75rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--text-secondary);
  border-bottom: 2px solid var(--tabs-border);
}

/* Definindo larguras para cada coluna */
.premium-table th:nth-child(1) { width: 25%; } /* Sócio */
.premium-table th:nth-child(2) { width: 15%; } /* CPF/CNPJ */
.premium-table th:nth-child(3) { width: 13%; } /* Qualificação */
.premium-table th:nth-child(4) { width: 12%; } /* Localização */
.premium-table th:nth-child(5) { width: 10%; } /* Participação */
.premium-table th:nth-child(6) { width: 10%; } /* Entrada */
.premium-table th:nth-child(7) { width: 15%; } /* Saída / Situação */

.premium-table td {
  padding: 0.85rem 1rem;
  border-bottom: 1px solid var(--tabs-border);
  color: var(--text-color-85);
  opacity: 0.90;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.premium-table tbody tr {
  background: transparent !important;
}

.premium-table tbody tr:hover {
  background: var(--table-hover) !important;
}

.row-inactive {
  opacity: 0.8;
  background: color-mix(in srgb, var(--color-error) 4%, var(--bg-color)) !important;
  color: color-mix(in srgb, var(--color-error) 40%, var(--text-color-85));
}

.row-inactive .main-name {
  color: color-mix(in srgb, var(--color-error) 60%, var(--text-color-85));
  text-decoration: line-through rgba(239, 68, 68, 0.3);
}

.col-center { 
  text-align: center !important; 
}
.font-mono { 
  font-family: var(--font-mono, monospace); 
  font-size: 0.8rem; 
  letter-spacing: -0.02em;
}

.socio-name {
  font-size: 0.85rem;
  font-weight: 600;
  display: flex;
  flex-direction: column;
  text-transform: none !important;
}

.socio-type {
  font-size: 0.7rem;
  color: var(--text-muted);
  font-weight: 500;
  text-transform: uppercase;
  letter-spacing: 0.02em;
  margin-top: 0.1rem;
}

.socio-meta {
  display: flex;
  align-items: center;
  gap: 0.3rem;
  margin-top: 0.1rem;
}

.name-row, .rep-name-row, .cpf-cell-content, .rep-cpf-row {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.cpf-cell-content {
  justify-content: center;
}

.rep-cpf-row {
  display: inline-flex;
  gap: 0.3rem;
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

.copy-btn.small {
  font-size: 0.6rem;
  width: 1rem;
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

.socio-age {
  font-size: 0.7rem;
  color: var(--text-muted);
  font-weight: 500;
}

/* Representante Legal */
.representante-info {
  margin-top: 0.6rem;
  padding: 0.5rem;
  background: color-mix(in srgb, var(--primary-color) 5%, transparent);
  border-radius: 6px;
  display: flex;
  gap: 0.6rem;
  align-items: flex-start;
  border-left: 3px solid var(--primary-color);
}

.representante-info i {
  color: var(--primary-color);
  font-size: 0.85rem;
  margin-top: 2px;
}

.rep-content {
  display: flex;
  flex-direction: column;
}

.rep-name {
  font-size: 0.75rem;
  font-weight: 700;
  color: var(--text-primary);
  text-transform: none !important;
}

.rep-meta {
  font-size: 0.7rem;
  color: var(--text-secondary);
  line-height: 1.4;
}

.qualificacao-cell {
  font-size: 0.85rem;
  color: var(--text-secondary);
  text-transform: none !important;
}

.location-cell {
  font-size: 0.85rem;
  color: var(--text-secondary);
  min-width: 120px;
  text-transform: none !important;
}

.location-wrapper {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  opacity: 0.85;
}

.location-wrapper i {
  font-size: 0.75rem;
  color: var(--primary-color);
  opacity: 0.7;
}

/* Barra de Percentual */
.pct-container {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.3rem;
  min-width: 80px;
}

.pct-bar-bg {
  width: 100%;
  height: 4px;
  background: var(--tabs-border);
  border-radius: 2px;
  overflow: hidden;
}

.pct-bar-fill {
  height: 100%;
  background: var(--data-color);
  border-radius: 2px;
  transition: width 1s ease-out;
}

.pct-val {
  font-size: 0.8rem;
  font-weight: 500;
  color: var(--text-color-85);
}

/* Badges de Status */
.status-badge {
  font-size: 0.75rem;
  font-weight: 700;
  padding: 0.25rem 0.6rem;
  border-radius: 4px;
  display: inline-block;
}

.status-badge.active {
  background: rgba(16, 185, 129, 0.1);
  color: #10b981;
  border: 1px solid rgba(16, 185, 129, 0.2);
}

.status-badge.inactive {
  background: rgba(239, 68, 68, 0.1);
  color: #ef4444;
  border: 1px solid rgba(239, 68, 68, 0.2);
}

.status-badge.deceased {
  background: rgba(148, 163, 184, 0.1);
  color: #94a3b8;
  border: 1px solid rgba(148, 163, 184, 0.2);
  display: inline-flex;
  align-items: center;
  gap: 0.3rem;
}

.deceased-badge-inline {
  display: inline-flex;
  align-items: center;
  gap: 0.3rem;
  font-size: 0.65rem;
  font-weight: 600;
  color: var(--risk-critical);
  background: color-mix(in srgb, var(--risk-critical) 10%, transparent);
  border: 1px solid color-mix(in srgb, var(--risk-critical) 30%, transparent);
  padding: 0.1rem 0.4rem;
  border-radius: 4px;
  margin-left: 0.5rem;
}

.cadunico-badge-inline {
  display: inline-flex;
  align-items: center;
  gap: 0.3rem;
  padding: 0.1rem 0.4rem;
  border: 1px solid color-mix(in srgb, var(--risk-medium) 30%, transparent);
  border-radius: 4px;
  margin-left: 0.5rem;
  background: color-mix(in srgb, var(--risk-medium) 10%, transparent);
  color: var(--risk-medium);
  font-size: 0.65rem;
  font-weight: 600;
}

.esocial-badge-inline {
  display: inline-flex;
  align-items: center;
  gap: 0.3rem;
  padding: 0.1rem 0.4rem;
  border: 1px solid color-mix(in srgb, var(--primary-color) 30%, transparent);
  border-radius: 4px;
  margin-left: 0.5rem;
  background: color-mix(in srgb, var(--primary-color) 10%, transparent);
  color: var(--primary-color);
  font-size: 0.65rem;
  font-weight: 600;
}

.seguro-defeso-badge-inline {
  display: inline-flex;
  align-items: center;
  gap: 0.3rem;
  padding: 0.1rem 0.4rem;
  border: 1px solid color-mix(in srgb, var(--status-info) 30%, transparent);
  border-radius: 4px;
  margin-left: 0.5rem;
  background: color-mix(in srgb, var(--status-info) 10%, transparent);
  color: var(--status-info);
  font-size: 0.65rem;
  font-weight: 600;
}

/* States */
.loading-state, .error-state, .empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 1rem;
  padding: 4rem 0;
  color: var(--text-muted);
}

.error-state i { color: var(--risk-critical); font-size: 2rem; }
.empty-state i { font-size: 2rem; opacity: 0.5; }

.animate-fade-in {
  animation: fadeIn 0.4s ease-out;
}

@keyframes fadeIn {
  from { opacity: 0; transform: translateY(10px); }
  to { opacity: 1; transform: translateY(0); }
}

.header-right {
  display: flex;
  align-items: center;
  gap: 1.5rem;
}

.header-item {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 0.1rem;
}

.header-item .label {
  font-size: 0.6rem;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.04em;
  font-weight: 700;
}

.header-item .value {
  font-size: 0.95rem;
  font-weight: 700;
  color: var(--primary-color);
}

.header-item .value.value-muted {
  color: var(--text-color-85);
  opacity: 0.75;
}

.filter-switch-group-horizontal {
  display: flex;
  align-items: center;
  gap: 0.8rem;
  cursor: pointer;
  padding: 0.4rem 0.6rem;
  border-radius: 8px;
  transition: all 0.2s;
  user-select: none;
}

.filter-switch-group-horizontal:hover {
  background: rgba(255, 255, 255, 0.03);
}

.custom-switch {
  width: 40px;
  height: 20px;
  background: #334155;
  border-radius: 99px;
  position: relative;
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
}

.custom-switch.active {
  background: var(--primary-color);
}

.switch-slider {
  width: 14px;
  height: 14px;
  background: white;
  border-radius: 50%;
  position: absolute;
  top: 3px;
  left: 3px;
  transition: transform 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  box-shadow: 0 2px 4px rgba(0,0,0,0.3);
}

.custom-switch.active .switch-slider {
  transform: translateX(20px);
}

.header-divider {
  width: 1px;
  height: 1.8rem;
  background: var(--tabs-border);
  opacity: 0.5;
}
</style>
