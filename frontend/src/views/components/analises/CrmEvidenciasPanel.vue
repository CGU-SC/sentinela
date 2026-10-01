<script>
import { createRespostaCache } from '@/utils/respostaCache';

// Respostas guardadas por médico + período + farmácia + aba + filtros + página +
// versão do cache: voltar a uma aba ou página já vista não refaz a consulta.
const evidenciasCache = createRespostaCache(60);
</script>

<script setup>
/**
 * Painel "Evidências" do histórico do CRM (/analises): os alertas do médico em
 * todas as farmácias, uma linha por janela, em três abas (sequências do próprio
 * CRM, sequências com múltiplos CRMs e farmácias distantes). Mesmos alertas do
 * painel do CRM na aba Autorizações do estabelecimento.
 *
 * Carrega só quando o painel aparece na tela; respeita o período exibido e a
 * farmácia filtrada no topo do modal. A aba ativa é do pai (v-model:aba), para
 * os pontos de atenção levarem direto à evidência.
 */
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue';
import axios from 'axios';
import { useToast } from 'primevue/usetoast';
import { API_ENDPOINTS } from '@/config/api';
import { analysisTooltip } from '@/config/analysisTooltipConfig';
import { CRM_SEVERIDADE_SEQUENCIA_CORES } from '@/config/colors';
import {
  CRM_EVIDENCIAS_PAGE_SIZE,
  CRM_EVIDENCIA_ABAS,
  CRM_EVIDENCIA_ORDENACAO_PADRAO,
  CRM_EVIDENCIA_SEVERIDADES,
  CRM_EVIDENCIA_SEVERIDADE_LABEL,
} from '@/config/crmEvidencias';
import { useFormatting } from '@/composables/useFormatting';
import { downloadBlobFromResponse } from '@/utils/download';
import { getApiErrorMessage } from '@/utils/apiErrors';
import ExportMenuButton from '@/views/components/common/ExportMenuButton.vue';
import TableFooter from '@/views/components/common/TableFooter.vue';
import CrmJanelaAutorizacoesDialog from '@/views/components/analises/CrmJanelaAutorizacoesDialog.vue';

const props = defineProps({
  idMedico: { type: String, required: true },
  /** Período exibido pelo modal (ISO); null = sem limite naquele lado. */
  dataInicio: { type: String, default: null },
  dataFim: { type: String, default: null },
  /** Farmácia filtrada no topo do modal (id_cnpj) ou null. */
  idCnpj: { type: Number, default: null },
  /** Município filtrado no topo do modal (id_ibge7) ou null. */
  idIbge7: { type: Number, default: null },
  cacheVersion: { type: String, default: null },
  /** Aba ativa: unico | multiplos | distancia. */
  aba: { type: String, required: true },
});
const emit = defineEmits(['update:aba']);

const toast = useToast();
const { formatNumberFull, formatarData, formatTitleCase, formatCnpj, formatCurrencyFull } = useFormatting();

const painelTooltip = analysisTooltip('crmHistoricoEvidencias');
const abaConfig = computed(() => {
  const config = CRM_EVIDENCIA_ABAS.find((a) => a.tipo === props.aba);
  if (!config) throw new Error(`Aba de evidências desconhecida: ${props.aba}`);
  return config;
});
const abaTooltips = Object.fromEntries(CRM_EVIDENCIA_ABAS.map((a) => [a.tipo, analysisTooltip(a.tooltip)]));

// ── Filtros de cada aba (ordenação, severidade e página) ─────────────────────
function filtrosIniciais() {
  return Object.fromEntries(CRM_EVIDENCIA_ABAS.map((a) => [a.tipo, {
    campo: CRM_EVIDENCIA_ORDENACAO_PADRAO[a.tipo].campo,
    ordem: CRM_EVIDENCIA_ORDENACAO_PADRAO[a.tipo].ordem,
    severidade: null,
    pagina: 1,
  }]));
}
const filtros = reactive(filtrosIniciais());
const filtroAtual = computed(() => filtros[props.aba]);
// Na primeira resposta de cada médico/período/farmácia, uma aba vazia cede o
// lugar à primeira aba com evidências (depois, a escolha é sempre do usuário).
let escolherAbaComDados = true;

// Outro médico, período, município ou farmácia: recomeça na primeira página, sem filtros.
watch(
  () => [props.idMedico, props.dataInicio, props.dataFim, props.idCnpj, props.idIbge7],
  () => {
    Object.assign(filtros, filtrosIniciais());
    escolherAbaComDados = true;
  },
);

function ordenar(campo) {
  const f = filtroAtual.value;
  if (f.campo === campo) f.ordem = f.ordem === 'desc' ? 'asc' : 'desc';
  else { f.campo = campo; f.ordem = 'desc'; }
  f.pagina = 1;
}
function iconeOrdem(campo) {
  const f = filtroAtual.value;
  if (f.campo !== campo) return 'pi-sort-alt';
  return f.ordem === 'desc' ? 'pi-sort-amount-down' : 'pi-sort-amount-up-alt';
}
function ariaOrdem(campo) {
  const f = filtroAtual.value;
  if (f.campo !== campo) return 'none';
  return f.ordem === 'desc' ? 'descending' : 'ascending';
}
function alternarSeveridade(id) {
  const f = filtroAtual.value;
  f.severidade = f.severidade === id ? null : id;
  f.pagina = 1;
}

// ── Carga (só depois que o painel aparece na tela) ───────────────────────────
const raiz = ref(null);
const visivel = ref(false);
let observador = null;
onMounted(() => {
  observador = new IntersectionObserver((entradas) => {
    if (entradas.some((e) => e.isIntersecting)) {
      visivel.value = true;
      observador?.disconnect();
      observador = null;
    }
  }, { rootMargin: '200px' });
  observador.observe(raiz.value);
});

const dados = ref(null);
const carregando = ref(false);
const erro = ref(null);
let controller = null;

const parametros = computed(() => {
  const f = filtroAtual.value;
  const params = {
    id_medico: props.idMedico,
    tipo: props.aba,
    sort_field: f.campo,
    sort_order: f.ordem,
    page: f.pagina,
    page_size: CRM_EVIDENCIAS_PAGE_SIZE,
  };
  if (props.dataInicio) params.data_inicio = props.dataInicio;
  if (props.dataFim) params.data_fim = props.dataFim;
  if (props.idCnpj != null) params.id_cnpj = props.idCnpj;
  if (props.idIbge7 != null) params.id_ibge7 = props.idIbge7;
  if (f.severidade != null) params.severidade = f.severidade;
  return params;
});

async function carregar() {
  if (!visivel.value) return;
  const params = parametros.value;
  const chave = JSON.stringify(params);
  const chaveCache = props.cacheVersion ? `${props.cacheVersion}|${chave}` : null;
  controller?.abort();
  const guardada = chaveCache ? evidenciasCache.get(chaveCache) : undefined;
  if (guardada) {
    dados.value = guardada;
    erro.value = null;
    carregando.value = false;
    irParaAbaComDados();
    return;
  }
  const requestController = new AbortController();
  controller = requestController;
  carregando.value = true;
  try {
    const { data } = await axios.get(API_ENDPOINTS.analyticsCrmMedicoEvidencias, { params, signal: requestController.signal });
    if (controller !== requestController) return;
    if (
      data.tipo !== params.tipo
      || (data.id_cnpj ?? null) !== (params.id_cnpj ?? null)
      || (data.id_ibge7 ?? null) !== (params.id_ibge7 ?? null)
      || !Array.isArray(data[abaConfig.value.linhas])
    ) {
      throw new Error('Contrato inválido em crm-medico-evidencias: aba, farmácia ou município diferente do solicitado.');
    }
    dados.value = data;
    erro.value = null;
    if (chaveCache) evidenciasCache.set(chaveCache, data);
    irParaAbaComDados();
  } catch (err) {
    if (axios.isCancel(err) || controller !== requestController) return;
    const detalhe = err?.response?.data?.detail;
    dados.value = null;
    erro.value = typeof detalhe === 'string' ? detalhe : (err?.message || 'Não foi possível carregar as evidências deste CRM.');
  } finally {
    if (controller === requestController) {
      controller = null;
      carregando.value = false;
    }
  }
}
watch([visivel, parametros], carregar, { immediate: true });
onBeforeUnmount(() => {
  controller?.abort();
  observador?.disconnect();
});

// ── Dados exibidos ───────────────────────────────────────────────────────────
// Resumos das três abas vêm em toda resposta (contadores das abas).
const contagemAba = (tipo) => {
  if (!dados.value) return null;
  const config = CRM_EVIDENCIA_ABAS.find((a) => a.tipo === tipo);
  const resumo = dados.value[config.resumo];
  return tipo === 'distancia' ? resumo.qtd_pares : resumo.qtd_alertas;
};
function irParaAbaComDados() {
  if (!escolherAbaComDados) return;
  escolherAbaComDados = false;
  if (contagemAba(props.aba) !== 0) return;
  const comDados = CRM_EVIDENCIA_ABAS.find((a) => contagemAba(a.tipo) > 0);
  if (comDados) emit('update:aba', comDados.tipo);
}
const resumo = computed(() => (dados.value && dados.value.tipo === props.aba ? dados.value[abaConfig.value.resumo] : null));
const linhas = computed(() => (dados.value && dados.value.tipo === props.aba ? dados.value[abaConfig.value.linhas] : []));
const ehSequencia = computed(() => props.aba !== 'distancia');
// Linhas em branco que completam a página: a tabela tem sempre a mesma altura.
const linhasEmBranco = computed(() => Math.max(0, CRM_EVIDENCIAS_PAGE_SIZE - linhas.value.length));
const colunasTabela = computed(() => ({ unico: 8, multiplos: 10, distancia: 5 }[props.aba]));
const unidadeRodape = computed(() => (ehSequencia.value ? ['janela', 'janelas'] : ['par', 'pares']));
const detalheRodape = computed(() => (
  filtroAtual.value.severidade != null ? `severidade ${CRM_EVIDENCIA_SEVERIDADE_LABEL[filtroAtual.value.severidade]}` : ''
));
const mensagemVazia = computed(() => (
  filtroAtual.value.severidade != null ? 'Nenhuma janela com esta severidade.' : abaConfig.value.vazio
));
const resumoTexto = computed(() => {
  const r = resumo.value;
  if (!r) return '';
  if (!ehSequencia.value) {
    const km = r.maior_distancia_km == null ? null : `${formatNumberFull(Math.round(r.maior_distancia_km))} km`;
    return [plural(r.qtd_pares, 'par', 'pares'), plural(r.qtd_meses, 'mês', 'meses'), km && `maior distância: ${km}`].filter(Boolean).join(' · ');
  }
  const pior = r.pior_severidade ? CRM_EVIDENCIA_SEVERIDADE_LABEL[r.pior_severidade] : null;
  return [
    plural(r.qtd_alertas, 'janela', 'janelas'),
    plural(r.qtd_dias, 'dia', 'dias'),
    plural(r.qtd_farmacias, 'farmácia', 'farmácias'),
    pior && `pior: ${pior}`,
  ].filter(Boolean).join(' · ');
});
const chipsSeveridade = computed(() => {
  const r = resumo.value;
  if (!r || !ehSequencia.value) return [];
  return CRM_EVIDENCIA_SEVERIDADES.map((s) => ({ ...s, qtd: r.por_severidade[String(s.id)] ?? 0 }));
});

function plural(n, um, varios) {
  return `${formatNumberFull(n)} ${n === 1 ? um : varios}`;
}
function hora(iso) {
  return iso ? String(iso).slice(11, 16) : '—';
}
function decimal(valor, casas = 1) {
  if (valor == null) return '—';
  return Number(valor).toLocaleString('pt-BR', { minimumFractionDigits: casas, maximumFractionDigits: casas });
}
function competencia(comp) {
  return `${String(comp % 100).padStart(2, '0')}/${Math.floor(comp / 100)}`;
}
function corSeveridade(id) {
  const cor = CRM_SEVERIDADE_SEQUENCIA_CORES[id];
  if (!cor) throw new Error(`Severidade sem cor: ${id}`);
  return cor;
}
function nomeFarmacia(nome, cnpj) {
  return nome ? formatTitleCase(nome) : formatCnpj(cnpj);
}

// Autorizações de uma janela (modal sobre o histórico, sem sair da página).
const janelaAberta = ref(false);
const janela = ref(null);
function abrirJanela(linha) {
  janela.value = { ...linha, tipo: props.aba, id_medico: props.idMedico };
  janelaAberta.value = true;
}

function mudarAba(tipo) {
  escolherAbaComDados = false;
  if (tipo !== props.aba) emit('update:aba', tipo);
}

/** Leva o painel à vista, já na aba pedida (pontos de atenção do histórico). */
function mostrarAba(tipo) {
  if (!CRM_EVIDENCIA_ABAS.some((a) => a.tipo === tipo)) throw new Error(`Aba de evidências desconhecida: ${tipo}`);
  mudarAba(tipo);
  visivel.value = true;
  nextTick(() => raiz.value?.scrollIntoView({ behavior: 'smooth', block: 'start' }));
}
defineExpose({ mostrarAba });
// Teclado nas abas (setas), padrão de tablist.
function teclaAba(evento, indice) {
  const delta = evento.key === 'ArrowRight' ? 1 : evento.key === 'ArrowLeft' ? -1 : 0;
  if (!delta) return;
  evento.preventDefault();
  const proxima = CRM_EVIDENCIA_ABAS[(indice + delta + CRM_EVIDENCIA_ABAS.length) % CRM_EVIDENCIA_ABAS.length];
  mudarAba(proxima.tipo);
  nextTick(() => raiz.value?.querySelector(`[data-aba="${proxima.tipo}"]`)?.focus());
}

// ── Exportação (Excel com as três evidências completas) ──────────────────────
const exportando = ref(false);
async function exportarExcel() {
  if (exportando.value) return;
  const params = { id_medico: props.idMedico };
  if (props.dataInicio) params.data_inicio = props.dataInicio;
  if (props.dataFim) params.data_fim = props.dataFim;
  if (props.idCnpj != null) params.id_cnpj = props.idCnpj;
  if (props.idIbge7 != null) params.id_ibge7 = props.idIbge7;
  exportando.value = true;
  try {
    const response = await fetch(API_ENDPOINTS.analyticsCrmMedicoEvidenciasExport(params));
    if (!response.ok) {
      throw new Error(await getApiErrorMessage(response, `Falha HTTP ${response.status} ao gerar o Excel das evidências.`));
    }
    const resultado = await downloadBlobFromResponse(response, `crm_evidencias_${props.idMedico.replace('/', '_')}.xlsx`);
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
  } catch (err) {
    toast.add({ severity: 'error', summary: 'Falha na exportação', detail: err.message || 'Não foi possível gerar o Excel.', life: 7000 });
  } finally {
    exportando.value = false;
  }
}
const semEvidencias = computed(() => (
  dados.value != null
  && dados.value.resumo_unico.qtd_alertas === 0
  && dados.value.resumo_multiplos.qtd_alertas === 0
  && dados.value.resumo_distancia.qtd_pares === 0
));
const exportacao = computed(() => ({
  itens: [{
    label: 'Evidências do CRM',
    items: [{ label: 'Excel (.xlsx) · uma aba por evidência', icon: 'pi pi-file-excel', command: exportarExcel }],
  }],
  carregando: exportando.value,
  desabilitado: dados.value == null || semEvidencias.value,
  motivo: semEvidencias.value ? 'Não há evidências no período.' : null,
  tooltip: null,
}));
</script>

<template>
  <section ref="raiz" class="hist-panel ev-panel" aria-labelledby="ev-titulo" :style="{ '--ev-linhas': CRM_EVIDENCIAS_PAGE_SIZE }">
    <header class="ev-header">
      <div class="ev-titulo">
        <h3 id="ev-titulo">Evidências</h3>
        <i class="pi pi-info-circle hist-info help-icon" v-tooltip.bottom="painelTooltip" aria-label="Como ler as evidências" />
        <span class="hist-panel-sub">uma linha por janela · {{ idCnpj != null ? 'somente a farmácia filtrada' : idIbge7 != null ? 'somente as farmácias do município filtrado' : 'todas as farmácias' }}</span>
      </div>
      <ExportMenuButton :exportacao="exportacao" menu-id="crm-evidencias-export" />
    </header>

    <div class="ev-abas" role="tablist" aria-label="Tipo de evidência">
      <button
        v-for="(a, i) in CRM_EVIDENCIA_ABAS"
        :key="a.tipo"
        type="button"
        role="tab"
        class="ev-aba"
        :class="{ 'is-ativa': a.tipo === aba }"
        :data-aba="a.tipo"
        :aria-selected="a.tipo === aba"
        :tabindex="a.tipo === aba ? 0 : -1"
        @click="mudarAba(a.tipo)"
        @keydown="teclaAba($event, i)"
      >
        <i class="pi" :class="a.icone" aria-hidden="true" />
        {{ a.label }}
        <span v-if="contagemAba(a.tipo) != null" class="ev-aba-qtd" :class="{ 'is-zero': contagemAba(a.tipo) === 0 }">
          {{ formatNumberFull(contagemAba(a.tipo)) }}
        </span>
        <i class="pi pi-info-circle ev-aba-info help-icon" v-tooltip.top="abaTooltips[a.tipo]" aria-hidden="true" @click.stop />
      </button>
    </div>

    <div role="tabpanel" class="ev-conteudo" :class="{ 'is-atualizando': carregando && dados }" :aria-busy="carregando">
      <div v-if="erro" class="ev-estado" role="alert"><p class="ev-erro"><i class="pi pi-exclamation-triangle" aria-hidden="true" /> {{ erro }}</p></div>
      <div v-else-if="!dados" class="ev-estado"><p class="hist-vazio"><i class="pi pi-spin pi-spinner" aria-hidden="true" /> Carregando evidências…</p></div>
      <template v-else>
        <div class="ev-resumo">
          <span class="ev-resumo-texto">{{ resumoTexto }}</span>
          <div v-if="chipsSeveridade.length" class="ev-severidades" role="group" aria-label="Filtrar por severidade">
            <button
              v-for="s in chipsSeveridade"
              :key="s.id"
              type="button"
              class="ev-sev-chip"
              :class="{ 'is-ativo': filtroAtual.severidade === s.id }"
              :style="{ '--sev-cor': corSeveridade(s.id) }"
              :aria-pressed="filtroAtual.severidade === s.id"
              :disabled="s.qtd === 0 && filtroAtual.severidade !== s.id"
              @click="alternarSeveridade(s.id)"
            >
              <span class="ev-sev-ponto" aria-hidden="true" />{{ s.label }}
              <span class="ev-sev-qtd">{{ formatNumberFull(s.qtd) }}</span>
            </button>
          </div>
        </div>

        <div class="ev-moldura">
        <div class="ev-tabela-wrap">
          <p v-if="!linhas.length" class="ev-vazio-sobre">{{ mensagemVazia }}</p>
          <!-- Sequências (único e múltiplos CRMs) -->
          <table v-if="ehSequencia" class="ev-tabela">
            <thead>
              <tr>
                <th class="c-data" :aria-sort="ariaOrdem('data')">
                  <button type="button" class="ev-ordem" @click="ordenar('data')">Data <i class="pi" :class="iconeOrdem('data')" aria-hidden="true" /></button>
                </th>
                <th class="c-farm">Farmácia</th>
                <th class="c-hora">Horário</th>
                <th class="num" :aria-sort="ariaOrdem('autorizacoes')">
                  <button type="button" class="ev-ordem" @click="ordenar('autorizacoes')">
                    {{ aba === 'multiplos' ? 'Aut. do CRM' : 'Autorizações' }} <i class="pi" :class="iconeOrdem('autorizacoes')" aria-hidden="true" />
                  </button>
                </th>
                <th v-if="aba === 'multiplos'" class="num">Total da janela</th>
                <th v-if="aba === 'multiplos'" class="num">CRMs</th>
                <th class="num">Janela</th>
                <th class="num" :aria-sort="ariaOrdem('taxa_hora')">
                  <button type="button" class="ev-ordem" @click="ordenar('taxa_hora')">Taxa/hora <i class="pi" :class="iconeOrdem('taxa_hora')" aria-hidden="true" /></button>
                </th>
                <th class="c-sev" :aria-sort="ariaOrdem('severidade')">
                  <button type="button" class="ev-ordem" @click="ordenar('severidade')">Severidade <i class="pi" :class="iconeOrdem('severidade')" aria-hidden="true" /></button>
                </th>
                <th class="c-acao"><span class="sr-only">Autorizações da janela</span></th>
              </tr>
            </thead>
            <tbody>
              <!-- A linha inteira abre as autorizações da janela (o botão à direita faz o mesmo). -->
              <tr
                v-for="(l, i) in linhas"
                :key="`${l.id_cnpj}-${l.dt_ini_hora}-${i}`"
                class="ev-linha-clicavel"
                tabindex="0"
                @click="abrirJanela(l)"
                @keydown.enter="abrirJanela(l)"
              >
                <td class="ev-numero">{{ formatarData(l.dt) }}</td>
                <td>
                  <span class="ev-farm-nome">{{ nomeFarmacia(l.razao_social, l.cnpj) }}</span>
                  <span class="ev-farm-sub">{{ formatCnpj(l.cnpj) }} · {{ formatTitleCase(l.municipio) }}/{{ l.uf }}</span>
                </td>
                <td class="ev-numero">{{ hora(l.dt_ini_hora) }}–{{ hora(l.dt_fim_hora) }}</td>
                <td class="num ev-numero ev-destaque">{{ formatNumberFull(aba === 'multiplos' ? l.nu_autorizacoes_crm : l.nu_autorizacoes) }}</td>
                <td v-if="aba === 'multiplos'" class="num ev-numero">{{ formatNumberFull(l.nu_autorizacoes_total) }}</td>
                <td v-if="aba === 'multiplos'" class="num ev-numero">{{ l.nu_crms == null ? '—' : formatNumberFull(l.nu_crms) }}</td>
                <td class="num ev-numero">{{ l.nu_minutos == null ? '—' : `${formatNumberFull(l.nu_minutos)} min` }}</td>
                <td class="num ev-numero">{{ decimal(l.taxa_hora) }}</td>
                <td>
                  <span class="ev-sev" :style="{ '--sev-cor': corSeveridade(l.id_severidade) }">
                    {{ CRM_EVIDENCIA_SEVERIDADE_LABEL[l.id_severidade] }}
                  </span>
                </td>
                <td class="c-acao">
                  <button
                    type="button"
                    class="ev-abrir"
                    v-tooltip.left="'Ver as autorizações desta janela'"
                    :aria-label="`Ver as autorizações da janela de ${formatarData(l.dt)} em ${nomeFarmacia(l.razao_social, l.cnpj)}`"
                    @click.stop="abrirJanela(l)"
                    @keydown.enter.stop
                  >
                    <i class="pi pi-list" aria-hidden="true" />
                  </button>
                </td>
              </tr>
              <tr v-for="n in linhasEmBranco" :key="`branco-${n}`" class="ev-linha-branca" aria-hidden="true"><td :colspan="colunasTabela" /></tr>
            </tbody>
          </table>

          <!-- Farmácias distantes -->
          <table v-else class="ev-tabela">
            <thead>
              <tr>
                <th class="c-mes" :aria-sort="ariaOrdem('data')">
                  <button type="button" class="ev-ordem" @click="ordenar('data')">Mês <i class="pi" :class="iconeOrdem('data')" aria-hidden="true" /></button>
                </th>
                <th>Farmácia A</th>
                <th>Farmácia B</th>
                <th class="num c-dist" :aria-sort="ariaOrdem('distancia')">
                  <button type="button" class="ev-ordem" @click="ordenar('distancia')">Distância <i class="pi" :class="iconeOrdem('distancia')" aria-hidden="true" /></button>
                </th>
                <th class="num c-valor">Valor autorizado</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(l, i) in linhas" :key="`${l.competencia}-${l.cnpj_a}-${l.cnpj_b}-${i}`">
                <td class="ev-numero">{{ competencia(l.competencia) }}</td>
                <td v-for="lado in ['a', 'b']" :key="lado">
                  <span class="ev-farm-nome">{{ nomeFarmacia(l[`razao_social_${lado}`], l[`cnpj_${lado}`]) }}</span>
                  <span class="ev-farm-sub">
                    {{ formatTitleCase(l[`no_municipio_${lado}`]) }}/{{ l[`sg_uf_${lado}`] }}
                    · {{ l[`nu_prescricoes_${lado}`] == null ? '—' : formatNumberFull(l[`nu_prescricoes_${lado}`]) }} presc.
                    <template v-if="l[`dt_ini_${lado}`]"> · {{ formatarData(l[`dt_ini_${lado}`]) }} a {{ formatarData(l[`dt_fim_${lado}`]) }}</template>
                  </span>
                </td>
                <td class="num"><span class="ev-km">{{ formatNumberFull(Math.round(l.distancia_km)) }} km</span></td>
                <td class="num ev-numero">{{ l.vl_autorizacoes_total == null ? '—' : formatCurrencyFull(l.vl_autorizacoes_total) }}</td>
              </tr>
              <tr v-for="n in linhasEmBranco" :key="`branco-${n}`" class="ev-linha-branca" aria-hidden="true"><td :colspan="colunasTabela" /></tr>
            </tbody>
          </table>
        </div>
        <!-- Rodapé sempre presente, dentro da moldura da tabela (altura fixa). -->
        <TableFooter
          :first="(filtroAtual.pagina - 1) * CRM_EVIDENCIAS_PAGE_SIZE"
          :rows="CRM_EVIDENCIAS_PAGE_SIZE"
          :total-records="dados.total"
          :unidade="unidadeRodape"
          :detalhe="detalheRodape"
          :disabled="carregando"
          @page="filtroAtual.pagina = $event.page + 1"
        />
        </div>
      </template>
    </div>
    <CrmJanelaAutorizacoesDialog v-model="janelaAberta" :janela="janela" />
  </section>
</template>

<style scoped>
.ev-header { display: flex; align-items: center; justify-content: space-between; gap: .8rem; flex-wrap: wrap; }
.ev-titulo { display: flex; align-items: baseline; gap: .6rem; flex-wrap: wrap; }
.ev-titulo h3 { margin: 0; font-size: .82rem; font-weight: 600; color: var(--text-color); }
.hist-info { color: var(--text-muted); font-size: .74rem; cursor: help; }
.hist-panel-sub { font-size: .7rem; color: var(--text-muted); }
.hist-vazio { margin: 0; font-size: .76rem; color: var(--text-muted); }
.hist-panel { display: flex; flex-direction: column; gap: .6rem; padding: .85rem 1rem; border: 1px solid var(--card-border); border-radius: 10px; }

/* Abas: mesmo padrão segmentado do painel de alertas da aba Autorizações. */
.ev-abas { display: flex; gap: .35rem; flex-wrap: wrap; padding: .25rem; border: 1px solid var(--tabs-border); border-radius: 9px; background: color-mix(in srgb, var(--text-color) 2%, var(--card-bg)); align-self: flex-start; }
.ev-aba { display: inline-flex; align-items: center; gap: .4rem; padding: .4rem .7rem; border: 0; border-radius: 7px; background: transparent; color: var(--text-secondary); font: inherit; font-size: .74rem; font-weight: 500; cursor: pointer; transition: background .15s ease, color .15s ease; }
.ev-aba:hover { color: var(--text-color); background: color-mix(in srgb, var(--text-color) 6%, transparent); }
.ev-aba:focus-visible { outline: 2px solid var(--primary-color); outline-offset: 1px; }
.ev-aba.is-ativa { background: var(--card-bg); color: var(--text-color); font-weight: 600; box-shadow: 0 1px 2px color-mix(in srgb, var(--text-color) 14%, transparent), inset 0 0 0 1px var(--card-border); }
.ev-aba .pi { font-size: .72rem; }
.ev-aba-qtd { min-width: 1.3rem; padding: .02rem .4rem; border-radius: 999px; background: color-mix(in srgb, var(--risk-critical) 14%, transparent); color: var(--risk-critical); font-size: .66rem; font-weight: 600; text-align: center; }
.ev-aba-qtd.is-zero { background: color-mix(in srgb, var(--text-color) 7%, transparent); color: var(--text-muted); }
.ev-aba-info { font-size: .66rem !important; color: var(--text-muted); opacity: .7; }
.ev-aba-info:hover { opacity: 1; }

.ev-conteudo { display: flex; flex-direction: column; gap: .6rem; transition: opacity .2s ease; }
.ev-conteudo.is-atualizando { opacity: .55; pointer-events: none; }
.ev-erro { display: flex; align-items: center; gap: .45rem; margin: 0; font-size: .76rem; color: var(--color-error); }

/* Alturas fixas: cabeçalho + N linhas (--ev-linhas vem da config), resumo e paginador. */
.ev-panel { --ev-linha: 3.1rem; --ev-cabecalho: 2.1rem; --ev-resumo: 1.75rem; --ev-rodape: 2.5rem; --ev-tabela: calc(var(--ev-cabecalho) + var(--ev-linhas) * var(--ev-linha)); }
.ev-estado { display: flex; align-items: center; justify-content: center; min-height: calc(var(--ev-resumo) + var(--ev-tabela) + var(--ev-rodape) + .6rem + 2px); }
.ev-resumo { display: flex; align-items: center; justify-content: space-between; gap: .8rem; flex-wrap: nowrap; min-height: var(--ev-resumo); }
.ev-resumo-texto { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.ev-severidades { flex-shrink: 0; }
.ev-moldura { border: 1px solid var(--tabs-border); border-radius: 8px; overflow: hidden; }
.ev-tabela-wrap { position: relative; overflow-x: auto; }
.ev-vazio-sobre { position: absolute; inset: var(--ev-cabecalho) 0 0 0; display: flex; align-items: center; justify-content: center; margin: 0; padding: 0 1rem; font-size: .76rem; color: var(--text-muted); text-align: center; pointer-events: none; }
.ev-resumo-texto { font-size: .74rem; color: var(--text-secondary); }
.ev-severidades { display: flex; gap: .35rem; flex-wrap: wrap; }
.ev-sev-chip { display: inline-flex; align-items: center; gap: .35rem; padding: .22rem .55rem; border: 1px solid var(--card-border); border-radius: 999px; background: transparent; color: var(--text-secondary); font: inherit; font-size: .7rem; font-weight: 500; cursor: pointer; transition: border-color .15s ease, background .15s ease, color .15s ease; }
.ev-sev-chip:hover:not(:disabled) { border-color: color-mix(in srgb, var(--sev-cor) 55%, transparent); color: var(--text-color); }
.ev-sev-chip:focus-visible { outline: 2px solid var(--primary-color); outline-offset: 1px; }
.ev-sev-chip.is-ativo { border-color: var(--sev-cor); background: color-mix(in srgb, var(--sev-cor) 14%, transparent); color: var(--text-color); }
.ev-sev-chip:disabled { opacity: .45; cursor: default; }
.ev-sev-ponto { width: .5rem; height: .5rem; border-radius: 50%; background: var(--sev-cor); }
.ev-sev-qtd { color: var(--text-muted); font-weight: 600; }

.ev-tabela { width: 100%; min-width: 62rem; table-layout: fixed; border-collapse: collapse; font-size: .74rem; color: var(--text-color-85); }
.ev-tabela thead tr { height: var(--ev-cabecalho); }
.ev-tabela tbody tr { height: var(--ev-linha); }
.ev-tabela th { padding: 0 .65rem; border-bottom: 1px solid color-mix(in srgb, var(--tabs-border) 65%, transparent); background: color-mix(in srgb, var(--text-color) 2%, var(--card-bg)); color: var(--text-muted); font-size: .6rem; font-weight: 600; letter-spacing: .04em; text-align: left; text-transform: uppercase; white-space: nowrap; }
.ev-tabela th.num, .ev-tabela td.num { text-align: right; }
.ev-tabela td { padding: 0 .65rem; border-top: 1px solid color-mix(in srgb, var(--tabs-border) 65%, transparent); vertical-align: middle; overflow: hidden; }
.ev-tabela tbody tr:not(.ev-linha-branca):hover, .ev-tabela tbody tr.ev-linha-clicavel:focus-visible { background: var(--table-hover); outline: none; }
.ev-tabela tbody tr.ev-linha-clicavel { cursor: pointer; }
.ev-tabela tr.ev-linha-branca td { border-top-color: transparent; }
.ev-tabela .c-data, .ev-tabela .c-mes { width: 7rem; }
.ev-tabela .c-farm { width: 30%; }
.ev-tabela .c-hora { width: 7.5rem; }
.ev-tabela .c-dist { width: 9rem; }
.ev-tabela .c-valor { width: 11rem; }
.ev-tabela .c-sev { width: 7rem; }
.ev-tabela .c-acao { width: 2.6rem; text-align: center; }
.ev-ordem { display: inline-flex; align-items: center; gap: .3rem; padding: 0; border: 0; background: transparent; color: inherit; font: inherit; letter-spacing: inherit; text-transform: inherit; cursor: pointer; }
.ev-ordem:hover, .ev-ordem:focus-visible { color: var(--text-color); outline: none; }
.ev-ordem .pi { font-size: .6rem; }
.ev-numero { white-space: nowrap; }
.ev-destaque { color: var(--text-color); font-weight: 600; }
.ev-farm-nome { display: block; color: var(--text-color); font-weight: 600; font-size: .76rem; line-height: 1.3; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.ev-farm-sub { display: block; margin-top: .1rem; color: var(--text-muted); font-size: .64rem; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.ev-sev { display: inline-flex; align-items: center; padding: .1rem .5rem; border: 1px solid color-mix(in srgb, var(--sev-cor) 40%, transparent); border-radius: 999px; background: color-mix(in srgb, var(--sev-cor) 14%, transparent); color: var(--sev-cor); font-size: .66rem; font-weight: 600; white-space: nowrap; }
.ev-km { display: inline-flex; padding: .1rem .5rem; border-radius: 999px; background: color-mix(in srgb, var(--risk-critical) 12%, transparent); color: var(--risk-critical); font-weight: 600; white-space: nowrap; }
.ev-abrir { display: inline-flex; align-items: center; justify-content: center; width: 26px; height: 26px; padding: 0; border: 1px solid transparent; border-radius: 6px; background: transparent; color: var(--text-muted); cursor: pointer; transition: color .15s ease, border-color .15s ease; }
.ev-abrir:hover, .ev-abrir:focus-visible { border-color: color-mix(in srgb, var(--primary-color) 45%, transparent); color: var(--primary-color); outline: none; }
.ev-abrir .pi { font-size: .72rem; }
.sr-only { position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px; overflow: hidden; clip: rect(0, 0, 0, 0); white-space: nowrap; border: 0; }
</style>
