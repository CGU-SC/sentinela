<script setup>
/**
 * Autorizações de uma janela de sequência (painel "Evidências" do histórico do
 * CRM, /analises): todas as autorizações da farmácia no intervalo da janela,
 * com as do CRM consultado destacadas. Mesma fonte da Cronologia do
 * estabelecimento (Raio-X), sem sair da página.
 */
import { computed, ref, watch } from 'vue';
import { useRouter } from 'vue-router';
import axios from 'axios';
import Dialog from 'primevue/dialog';
import { useToast } from 'primevue/usetoast';
import { API_ENDPOINTS } from '@/config/api';
import { CRM_SEVERIDADE_SEQUENCIA_CORES } from '@/config/colors';
import { CRM_EVIDENCIA_ABAS, CRM_EVIDENCIA_SEVERIDADE_LABEL } from '@/config/crmEvidencias';
import { useFormatting } from '@/composables/useFormatting';
import { useEvidenciasStore } from '@/stores/evidencias';

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  /**
   * Linha do painel de evidências + contexto:
   * { tipo, id_medico, id_cnpj, cnpj, razao_social, municipio, uf, dt,
   *   hr_janela, dt_ini_hora, dt_fim_hora, id_severidade }
   */
  janela: { type: Object, default: null },
});
const emit = defineEmits(['update:modelValue']);

const router = useRouter();
const toast = useToast();
const evidenciasStore = useEvidenciasStore();
const { formatNumberFull, formatarData, formatTitleCase, formatCnpj, formatCurrencyFull } = useFormatting();

const dados = ref(null);
const carregando = ref(false);
const erro = ref(null);
const somenteDoCrm = ref(false);
let controller = null;

async function carregar() {
  const j = props.janela;
  if (!j) return;
  controller?.abort();
  const requestController = new AbortController();
  controller = requestController;
  carregando.value = true;
  erro.value = null;
  dados.value = null;
  somenteDoCrm.value = false;
  try {
    const { data } = await axios.get(API_ENDPOINTS.analyticsCrmEvidenciaAutorizacoes, {
      params: { id_cnpj: j.id_cnpj, id_medico: j.id_medico, inicio: j.dt_ini_hora, fim: j.dt_fim_hora },
      signal: requestController.signal,
    });
    if (controller !== requestController) return;
    if (data.id_cnpj !== j.id_cnpj || !Array.isArray(data.autorizacoes)) {
      throw new Error('Contrato inválido em crm-medico-evidencias/autorizacoes: farmácia diferente da solicitada.');
    }
    dados.value = data;
  } catch (err) {
    if (axios.isCancel(err) || controller !== requestController) return;
    const detalhe = err?.response?.data?.detail;
    erro.value = typeof detalhe === 'string' ? detalhe : (err?.message || 'Não foi possível carregar as autorizações da janela.');
  } finally {
    if (controller === requestController) {
      controller = null;
      carregando.value = false;
    }
  }
}
watch(() => [props.modelValue, props.janela], ([aberto]) => { if (aberto) carregar(); }, { immediate: true });

const tipoLabel = computed(() => CRM_EVIDENCIA_ABAS.find((a) => a.tipo === props.janela?.tipo)?.label ?? '');
const corSeveridade = computed(() => {
  const cor = CRM_SEVERIDADE_SEQUENCIA_CORES[props.janela?.id_severidade];
  if (!cor) throw new Error(`Severidade sem cor: ${props.janela?.id_severidade}`);
  return cor;
});
const autorizacoes = computed(() => {
  const lista = dados.value?.autorizacoes ?? [];
  return somenteDoCrm.value ? lista.filter((a) => a.do_crm) : lista;
});
const kpis = computed(() => {
  const d = dados.value;
  if (!d) return [];
  return [
    { label: 'Autorizações na janela', value: formatNumberFull(d.qtd_autorizacoes) },
    { label: 'Deste CRM', value: formatNumberFull(d.qtd_autorizacoes_crm), destaque: true },
    { label: 'CRMs na janela', value: formatNumberFull(d.qtd_crms) },
    { label: 'Valor autorizado', value: formatCurrencyFull(d.valor_total) },
  ];
});

function hora(iso, segundos = false) {
  return iso ? String(iso).slice(11, segundos ? 19 : 16) : '—';
}
function nomeMedico(a) {
  return a.no_medico ? formatTitleCase(a.no_medico) : 'Médico não localizado no CFM';
}

async function abrirNoEstabelecimento() {
  const j = props.janela;
  try {
    emit('update:modelValue', false);
    await evidenciasStore.abrirNaCronologia({ cnpj: j.cnpj, date: j.dt, hour: j.hr_janela ?? 'all', autorizacao: null }, router);
  } catch (err) {
    toast.add({ severity: 'error', summary: 'Não foi possível abrir o estabelecimento', detail: err.message, life: 6000 });
  }
}
</script>

<template>
  <Dialog
    :visible="modelValue"
    modal
    dismissableMask
    class="crm-janela-dialog"
    :style="{ width: '72vw', maxWidth: '1060px' }"
    @update:visible="emit('update:modelValue', $event)"
  >
    <template #header>
      <div v-if="janela" class="jan-header">
        <span class="jan-eyebrow">Autorizações da janela · {{ tipoLabel }}</span>
        <span class="jan-title">{{ janela.razao_social ? formatTitleCase(janela.razao_social) : formatCnpj(janela.cnpj) }}</span>
        <div class="jan-meta">
          <span>{{ formatCnpj(janela.cnpj) }} · {{ formatTitleCase(janela.municipio) }}/{{ janela.uf }}</span>
          <span><i class="pi pi-calendar" aria-hidden="true" /> {{ formatarData(janela.dt) }}</span>
          <span><i class="pi pi-clock" aria-hidden="true" /> {{ hora(janela.dt_ini_hora) }}–{{ hora(janela.dt_fim_hora) }}</span>
          <span class="jan-sev" :style="{ '--sev-cor': corSeveridade }">{{ CRM_EVIDENCIA_SEVERIDADE_LABEL[janela.id_severidade] }}</span>
        </div>
      </div>
    </template>

    <p v-if="erro" class="jan-erro" role="alert"><i class="pi pi-exclamation-triangle" aria-hidden="true" /> {{ erro }}</p>
    <p v-else-if="carregando || !dados" class="jan-vazio"><i class="pi pi-spin pi-spinner" aria-hidden="true" /> Carregando autorizações…</p>
    <div v-else class="jan-corpo">
      <div class="jan-kpis">
        <div v-for="k in kpis" :key="k.label" class="jan-kpi" :class="{ 'is-destaque': k.destaque }">
          <span class="jan-kpi-label">{{ k.label }}</span>
          <span class="jan-kpi-value">{{ k.value }}</span>
        </div>
      </div>

      <div class="jan-barra">
        <span class="jan-legenda"><span class="jan-marca" aria-hidden="true" /> autorização deste CRM ({{ janela.id_medico }})</span>
        <label class="jan-toggle">
          <input v-model="somenteDoCrm" type="checkbox" />
          Somente deste CRM
        </label>
      </div>

      <p v-if="!autorizacoes.length" class="jan-vazio">Nenhuma autorização na janela.</p>
      <div v-else class="jan-tabela-wrap">
        <table class="jan-tabela">
          <thead>
            <tr>
              <th class="c-hora">Horário</th>
              <th class="c-aut">Autorização</th>
              <th>Médico</th>
              <th class="c-crm">CRM</th>
              <th class="num c-valor">Valor</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="a in autorizacoes" :key="a.num_autorizacao" :class="{ 'is-do-crm': a.do_crm }">
              <td class="jan-numero">{{ hora(a.data_hora, true) }}</td>
              <td class="jan-numero">{{ a.num_autorizacao }}</td>
              <td>
                {{ nomeMedico(a) }}
                <span v-if="a.do_crm" class="jan-tag">este CRM</span>
              </td>
              <td class="jan-numero">{{ a.id_medico }}</td>
              <td class="num jan-numero">{{ a.valor_pago == null ? '—' : formatCurrencyFull(a.valor_pago) }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <template #footer>
      <div class="jan-rodape">
        <button type="button" class="jan-link" :disabled="!janela" @click="abrirNoEstabelecimento">
          <i class="pi pi-external-link" aria-hidden="true" /> Abrir na Cronologia do estabelecimento
        </button>
        <button type="button" class="jan-fechar" @click="emit('update:modelValue', false)">Fechar</button>
      </div>
    </template>
  </Dialog>
</template>

<style scoped>
.jan-header { display: flex; flex-direction: column; gap: .2rem; }
.jan-eyebrow { font-size: .66rem; font-weight: 600; letter-spacing: .08em; text-transform: uppercase; color: var(--text-muted); }
.jan-title { font-size: 1.02rem; font-weight: 600; color: var(--text-color); }
.jan-meta { display: flex; flex-wrap: wrap; align-items: center; gap: .3rem 1rem; font-size: .74rem; color: var(--text-secondary); }
.jan-meta .pi { font-size: .7rem; color: var(--text-muted); margin-right: .15rem; }
.jan-sev { display: inline-flex; padding: .08rem .5rem; border: 1px solid color-mix(in srgb, var(--sev-cor) 40%, transparent); border-radius: 999px; background: color-mix(in srgb, var(--sev-cor) 14%, transparent); color: var(--sev-cor); font-size: .66rem; font-weight: 600; }

.jan-corpo { display: flex; flex-direction: column; gap: .75rem; }
.jan-kpis { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: .6rem; }
.jan-kpi { display: flex; flex-direction: column; gap: .3rem; padding: .6rem .8rem; border: 1px solid var(--card-border); border-radius: 10px; background: color-mix(in srgb, var(--text-color) 3%, transparent); }
.jan-kpi.is-destaque { border-color: color-mix(in srgb, var(--primary-color) 45%, transparent); background: color-mix(in srgb, var(--primary-color) 8%, transparent); }
.jan-kpi-label { font-size: .62rem; font-weight: 600; letter-spacing: .06em; text-transform: uppercase; color: var(--text-muted); }
.jan-kpi-value { font-size: .92rem; font-weight: 600; color: var(--text-color); }
.jan-kpi.is-destaque .jan-kpi-value { color: var(--primary-color); }

.jan-barra { display: flex; align-items: center; justify-content: space-between; gap: .8rem; flex-wrap: wrap; font-size: .72rem; color: var(--text-secondary); }
.jan-legenda { display: inline-flex; align-items: center; gap: .4rem; }
.jan-marca { width: 3px; height: .9rem; border-radius: 2px; background: var(--primary-color); }
.jan-toggle { display: inline-flex; align-items: center; gap: .35rem; cursor: pointer; user-select: none; }
.jan-toggle input { accent-color: var(--primary-color); }

.jan-tabela-wrap { max-height: 52vh; overflow: auto; border: 1px solid var(--tabs-border); border-radius: 8px; }
.jan-tabela { width: 100%; border-collapse: collapse; font-size: .74rem; color: var(--text-color-85); }
.jan-tabela th { position: sticky; top: 0; z-index: 1; padding: .55rem .7rem; border-bottom: 1px solid color-mix(in srgb, var(--tabs-border) 65%, transparent); background: color-mix(in srgb, var(--text-color) 2%, var(--card-bg)); color: var(--text-muted); font-size: .6rem; font-weight: 600; letter-spacing: .04em; text-align: left; text-transform: uppercase; }
.jan-tabela th.num, .jan-tabela td.num { text-align: right; }
.jan-tabela td { padding: .5rem .7rem; border-top: 1px solid color-mix(in srgb, var(--tabs-border) 65%, transparent); }
.jan-tabela tbody tr:hover { background: var(--table-hover); }
.jan-tabela tr.is-do-crm { background: color-mix(in srgb, var(--primary-color) 7%, transparent); box-shadow: inset 3px 0 0 var(--primary-color); }
.jan-tabela tr.is-do-crm td { color: var(--text-color); }
.jan-tabela .c-hora { width: 6.5rem; }
.jan-tabela .c-aut { width: 11rem; }
.jan-tabela .c-crm { width: 7.5rem; }
.jan-tabela .c-valor { width: 8rem; }
.jan-numero { white-space: nowrap; }
.jan-tag { display: inline-flex; margin-left: .4rem; padding: .02rem .4rem; border-radius: 999px; background: color-mix(in srgb, var(--primary-color) 16%, transparent); color: var(--primary-color); font-size: .6rem; font-weight: 600; }

.jan-vazio { margin: 0; font-size: .76rem; color: var(--text-muted); }
.jan-erro { display: flex; align-items: center; gap: .45rem; margin: 0; font-size: .76rem; color: var(--color-error); }

.jan-rodape { display: flex; align-items: center; justify-content: space-between; gap: .8rem; width: 100%; }
.jan-link { display: inline-flex; align-items: center; gap: .4rem; padding: .45rem .2rem; border: 0; background: transparent; color: var(--primary-color); font: inherit; font-size: .76rem; font-weight: 500; cursor: pointer; }
.jan-link:hover:not(:disabled), .jan-link:focus-visible { text-decoration: underline; outline: none; }
.jan-link .pi { font-size: .72rem; }
.jan-fechar { padding: .5rem 1rem; border: 1px solid var(--card-border); border-radius: 8px; background: var(--card-bg); color: var(--text-color); font: inherit; font-size: .78rem; font-weight: 600; cursor: pointer; }
.jan-fechar:hover, .jan-fechar:focus-visible { border-color: var(--primary-color); outline: none; }
</style>
