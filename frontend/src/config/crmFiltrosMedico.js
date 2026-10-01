/**
 * Filtros de médico da página de Análises (grupo "Cadastro CFM").
 * Os valores seguem o contrato de /crm-prescricoes-analise e /crm-prescricoes-mensal
 * (situacao_cfm, uf_crm, antes_inscricao).
 */

import { CRM_EXCLUSIVIDADE_THRESHOLDS } from '@/config/riskConfig';

export const CRM_SITUACAO_CFM_OPCOES = Object.freeze([
  Object.freeze({ value: null, label: 'Todos' }),
  Object.freeze({ value: 'localizado', label: 'Localizado' }),
  Object.freeze({ value: 'nao_localizado', label: 'Não localizado' }),
]);

/** Rótulo do chip de cada situação ativa. */
export const CRM_SITUACAO_CFM_CHIP = Object.freeze({
  localizado: 'Localizado no CFM',
  nao_localizado: 'Não localizado no CFM',
});

/** UFs aceitas em uf_crm (UF do próprio id_medico, ex.: "123/SC"). */
export const CRM_UFS = Object.freeze([
  'AC', 'AL', 'AM', 'AP', 'BA', 'CE', 'DF', 'ES', 'GO', 'MA', 'MG', 'MS', 'MT', 'PA',
  'PB', 'PE', 'PI', 'PR', 'RJ', 'RN', 'RO', 'RR', 'RS', 'SC', 'SE', 'SP', 'TO',
]);

/** Atalhos do seletor "UF do CRM": grandes regiões do IBGE (vazio = todas). */
export const CRM_UF_ATALHOS = Object.freeze([
  Object.freeze({ value: 'todas', label: 'Todas', selecao: Object.freeze([]) }),
  Object.freeze({ value: 'norte', label: 'Norte', selecao: Object.freeze(['AC', 'AM', 'AP', 'PA', 'RO', 'RR', 'TO']) }),
  Object.freeze({ value: 'nordeste', label: 'Nordeste', selecao: Object.freeze(['AL', 'BA', 'CE', 'MA', 'PB', 'PE', 'PI', 'RN', 'SE']) }),
  Object.freeze({ value: 'centro-oeste', label: 'Centro-Oeste', selecao: Object.freeze(['DF', 'GO', 'MS', 'MT']) }),
  Object.freeze({ value: 'sudeste', label: 'Sudeste', selecao: Object.freeze(['ES', 'MG', 'RJ', 'SP']) }),
  Object.freeze({ value: 'sul', label: 'Sul', selecao: Object.freeze(['PR', 'RS', 'SC']) }),
]);

export const CRM_ANTES_INSCRICAO_CHIP = 'Prescreveu antes da 1ª inscrição';

/**
 * Severidade mínima das autorizações em sequência (único CRM): id_severidade
 * dos alertas (1 alta, 2 grave, 3 crítica, 4 extrema). null = sem filtro.
 * `chip` só para as opções que filtram.
 */
export const CRM_SEQUENCIA_SEVERIDADES = Object.freeze([
  Object.freeze({ value: null, label: 'Qualquer' }),
  Object.freeze({ value: 1, label: 'Alta ou pior', chip: 'Sequência alta ou pior' }),
  Object.freeze({ value: 2, label: 'Grave ou pior', chip: 'Sequência grave ou pior' }),
  Object.freeze({ value: 3, label: 'Crítica ou pior', chip: 'Sequência crítica ou pior' }),
  Object.freeze({ value: 4, label: 'Extrema', chip: 'Sequência extrema' }),
]);

/** Atalho "a partir de" de uma faixa aberta (NumberRangePicker modo aberto). */
function atalhoMinimo(valor, rotulo) {
  return Object.freeze({ value: `min-${valor}`, label: `≥ ${rotulo}`, faixa: Object.freeze([valor, null]) });
}

/**
 * Filtros de faixa dos médicos (NumberRangePicker modo aberto).
 * `grupo`: bloco do painel; `param`: prefixo dos parâmetros da API (_min / _max);
 * `passo`: ajuste dos botões − e +; `max`: teto aceito (Infinity = sem teto);
 * `sufixo`: unidade exibida junto do número; `atalhos`: à esquerda do painel.
 *
 * - producao: números do médico no recorte da página (colunas TAXA / DIA e
 *   PRODUÇÃO do ranking); na aba Por mês valem para cada mês.
 * - atuacao: exclusividade na farmácia principal, nº de farmácias e nº de
 *   municípios onde atuou, nacionais, no período.
 * - sequencia: dias com autorizações em sequência (único CRM) no período,
 *   contados na severidade mínima escolhida (CRM_SEQUENCIA_SEVERIDADES).
 */
export const CRM_FAIXAS = Object.freeze({
  taxaDia: Object.freeze({
    grupo: 'producao',
    param: 'taxa_dia',
    label: 'Taxa diária',
    chip: 'Taxa/dia',
    casas: 2,
    passo: 1,
    max: Infinity,
    sufixo: '',
    todas: 'Todas',
    tooltip: 'crmFiltroTaxaDia',
    atalhos: Object.freeze([
      Object.freeze({ value: 'todas', label: 'Todas', faixa: Object.freeze([null, null]) }),
      ...[5, 10, 20, 30].map((v) => atalhoMinimo(v, String(v))),
    ]),
  }),
  prescricoes: Object.freeze({
    grupo: 'producao',
    param: 'prescricoes',
    label: 'Total de prescrições',
    chip: 'Prescrições',
    casas: 0,
    passo: 500,
    max: Infinity,
    sufixo: '',
    todas: 'Todos',
    tooltip: 'crmFiltroPrescricoes',
    atalhos: Object.freeze([
      Object.freeze({ value: 'todas', label: 'Todos', faixa: Object.freeze([null, null]) }),
      ...[1000, 5000, 10000, 50000].map((v) => atalhoMinimo(v, v.toLocaleString('pt-BR'))),
    ]),
  }),
  exclusividade: Object.freeze({
    grupo: 'atuacao',
    param: 'exclusividade',
    label: 'Exclusividade na farmácia principal',
    chip: 'Exclusividade',
    casas: 2,
    passo: 5,
    max: 100,
    sufixo: '%',
    todas: 'Todas',
    tooltip: 'crmFiltroExclusividade',
    atalhos: Object.freeze([
      Object.freeze({ value: 'todas', label: 'Todas', faixa: Object.freeze([null, null]) }),
      // Mesmos cortes que destacam a coluna Exclusividade na aba CRMs do estabelecimento.
      atalhoMinimo(CRM_EXCLUSIVIDADE_THRESHOLDS.atencao, `${CRM_EXCLUSIVIDADE_THRESHOLDS.atencao}% (atenção)`),
      atalhoMinimo(CRM_EXCLUSIVIDADE_THRESHOLDS.alto, `${CRM_EXCLUSIVIDADE_THRESHOLDS.alto}% (alto)`),
      atalhoMinimo(95, '95%'),
      Object.freeze({ value: 'unica', label: '100% (uma farmácia)', faixa: Object.freeze([100, null]) }),
    ]),
  }),
  farmacias: Object.freeze({
    grupo: 'atuacao',
    param: 'farmacias',
    label: 'Nº de farmácias onde atuou',
    chip: 'Farmácias',
    casas: 0,
    passo: 1,
    max: Infinity,
    sufixo: '',
    todas: 'Todas',
    tooltip: 'crmFiltroFarmacias',
    atalhos: Object.freeze([
      Object.freeze({ value: 'todas', label: 'Todas', faixa: Object.freeze([null, null]) }),
      Object.freeze({ value: 'uma', label: '1 (uma farmácia)', faixa: Object.freeze([1, 1]) }),
      Object.freeze({ value: 'ate-5', label: 'Até 5', faixa: Object.freeze([null, 5]) }),
      ...[50, 100, 300].map((v) => atalhoMinimo(v, String(v))),
    ]),
  }),
  municipios: Object.freeze({
    grupo: 'atuacao',
    param: 'municipios',
    label: 'Nº de municípios onde atuou',
    chip: 'Municípios',
    casas: 0,
    passo: 1,
    max: Infinity,
    sufixo: '',
    todas: 'Todos',
    tooltip: 'crmFiltroMunicipios',
    atalhos: Object.freeze([
      Object.freeze({ value: 'todos', label: 'Todos', faixa: Object.freeze([null, null]) }),
      Object.freeze({ value: 'um', label: '1 (um município)', faixa: Object.freeze([1, 1]) }),
      Object.freeze({ value: 'ate-3', label: 'Até 3', faixa: Object.freeze([null, 3]) }),
      ...[10, 30, 60].map((v) => atalhoMinimo(v, String(v))),
    ]),
  }),
  sequenciaDias: Object.freeze({
    grupo: 'sequencia',
    param: 'sequencia_dias',
    label: 'Dias com sequência',
    chip: 'Dias em sequência',
    casas: 0,
    passo: 1,
    max: Infinity,
    sufixo: '',
    todas: 'Todos',
    tooltip: 'crmFiltroSequenciaDias',
    atalhos: Object.freeze([
      Object.freeze({ value: 'todos', label: 'Todos', faixa: Object.freeze([null, null]) }),
      Object.freeze({ value: 'com', label: '≥ 1 (com sequência)', faixa: Object.freeze([1, null]) }),
      ...[10, 50, 100].map((v) => atalhoMinimo(v, String(v))),
    ]),
  }),
});

/** Tipos de faixa de um bloco do painel, na ordem da config. */
export function crmFaixasDoGrupo(grupo) {
  return Object.keys(CRM_FAIXAS).filter((tipo) => CRM_FAIXAS[tipo].grupo === grupo);
}
