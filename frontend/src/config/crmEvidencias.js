/**
 * Painel "Evidências" do histórico do CRM (/analises): abas, severidades,
 * ordenações e textos. Mesmos alertas do painel do CRM na aba Autorizações do
 * estabelecimento, em todas as farmácias do médico.
 */

/**
 * Linhas por página das tabelas do painel. As três tabelas ocupam sempre a
 * altura destas linhas (última página e tabela vazia incluídas), para o modal
 * não se deslocar ao trocar de aba, página ou filtro.
 */
export const CRM_EVIDENCIAS_PAGE_SIZE = 7;

/** Severidade dos alertas de sequência (id_severidade da API). */
export const CRM_EVIDENCIA_SEVERIDADES = Object.freeze([
  Object.freeze({ id: 4, label: 'Extrema' }),
  Object.freeze({ id: 3, label: 'Crítica' }),
  Object.freeze({ id: 2, label: 'Grave' }),
  Object.freeze({ id: 1, label: 'Alta' }),
]);
export const CRM_EVIDENCIA_SEVERIDADE_LABEL = Object.freeze(
  Object.fromEntries(CRM_EVIDENCIA_SEVERIDADES.map((s) => [s.id, s.label])),
);

/**
 * Abas do painel. `resumo` é o campo do resumo na resposta; `linhas`, o das
 * linhas da aba; `ordenacoes`, os campos aceitos por sort_field (o primeiro é o
 * padrão da API).
 */
export const CRM_EVIDENCIA_ABAS = Object.freeze([
  Object.freeze({
    tipo: 'unico',
    label: 'Sequências (único CRM)',
    icone: 'pi-bolt',
    resumo: 'resumo_unico',
    linhas: 'linhas_unico',
    tooltip: 'crmEvidenciasUnico',
    vazio: 'Nenhuma sequência de autorizações do próprio CRM no período.',
  }),
  Object.freeze({
    tipo: 'multiplos',
    label: 'Sequências (múltiplos CRMs)',
    icone: 'pi-users',
    resumo: 'resumo_multiplos',
    linhas: 'linhas_multiplos',
    tooltip: 'crmEvidenciasMultiplos',
    vazio: 'O CRM não autorizou em nenhuma sequência com múltiplos CRMs no período.',
  }),
  Object.freeze({
    tipo: 'distancia',
    label: 'Farmácias distantes',
    icone: 'pi-directions',
    resumo: 'resumo_distancia',
    linhas: 'linhas_distancia',
    tooltip: 'crmEvidenciasDistancia',
    vazio: 'Nenhum par de farmácias distantes no mesmo mês no período.',
  }),
]);

/** Ordenação inicial de cada aba (campo da API e sentido). */
export const CRM_EVIDENCIA_ORDENACAO_PADRAO = Object.freeze({
  unico: Object.freeze({ campo: 'data', ordem: 'desc' }),
  multiplos: Object.freeze({ campo: 'data', ordem: 'desc' }),
  distancia: Object.freeze({ campo: 'distancia', ordem: 'desc' }),
});

/** Ponto de atenção do histórico que leva à aba correspondente do painel. */
export const CRM_EVIDENCIA_ABA_DO_PONTO = Object.freeze({
  rajadas_unico: 'unico',
  distancia: 'distancia',
});
