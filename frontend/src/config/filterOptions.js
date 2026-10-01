export const SOCIO_BENEFICIO_FILTER_OPTIONS = [
  { label: 'Sem filtro', value: 'Todos' },
  { label: 'Sócio direto', value: 'direto' },
  { label: 'Sócio N3', value: 'n3' },
  { label: 'Sócio direto ou N3', value: 'direto_n3' },
];

export const SOCIO_ESOCIAL_FILTER_OPTIONS = [
  { label: 'Sem filtro', value: 'Todos' },
  { label: 'Sócio direto', value: 'direto' },
  { label: 'Sócio N3', value: 'n3' },
  { label: 'Sócio direto ou N3', value: 'direto_n3' },
];

/**
 * Atalhos do filtro "População do município" (porte do município, IBGE).
 * Faixas inclusivas em habitantes; null = sem limite.
 */
export const POPULACAO_MUNICIPIO_ATALHOS = Object.freeze([
  Object.freeze({ value: 'todos', label: 'Todos', faixa: Object.freeze([null, null]) }),
  Object.freeze({ value: 'pequeno', label: 'Pequeno porte (até 50 mil)', faixa: Object.freeze([null, 50000]) }),
  Object.freeze({ value: 'medio', label: 'Médio porte (50 mil a 100 mil)', faixa: Object.freeze([50001, 100000]) }),
  Object.freeze({ value: 'grande', label: 'Grande porte (100 mil a 900 mil)', faixa: Object.freeze([100001, 900000]) }),
  Object.freeze({ value: 'metropole', label: 'Metrópole (acima de 900 mil)', faixa: Object.freeze([900001, null]) }),
]);

/** Tipo das autorizações em sequência na farmácia (valores de seq_tipo na API). */
export const SEQ_TIPOS = Object.freeze([
  Object.freeze({ value: 'qualquer', label: 'Qualquer (único ou múltiplos)' }),
  Object.freeze({ value: 'unico', label: 'Único CRM' }),
  Object.freeze({ value: 'multiplo', label: 'Múltiplos CRMs' }),
]);

/**
 * Autorizações em sequência na farmácia: severidade mínima
 * dos alertas (1 alta, 2 grave, 3 crítica, 4 extrema; null = desligado).
 */
export const SEQ_SEVERIDADES = Object.freeze([
  Object.freeze({ value: null, label: 'Desligado' }),
  Object.freeze({ value: 1, label: 'Alta ou pior' }),
  Object.freeze({ value: 2, label: 'Grave ou pior' }),
  Object.freeze({ value: 3, label: 'Crítica ou pior' }),
  Object.freeze({ value: 4, label: 'Extrema' }),
]);

/** Atalhos de dias com sequência na farmácia; null = sem limite. */
export const SEQ_DIAS_ATALHOS = Object.freeze([
  Object.freeze({ value: 'todos', label: 'Todos', faixa: Object.freeze([null, null]) }),
  Object.freeze({ value: 'com', label: '≥ 1 (com sequência)', faixa: Object.freeze([1, null]) }),
  ...[10, 50, 100, 365].map((v) => Object.freeze({ value: `min-${v}`, label: `≥ ${v}`, faixa: Object.freeze([v, null]) })),
]);

export const FILTER_OPTIONS = {
  situacao: ['Todos', 'Ativa', 'Baixada', 'Suspensa', 'Inapta'],
  ms:       ['Todos', 'Ativa', 'Inativa'],
  porte:      ['Todos', 'Microempresa (ME)', 'Empresa de Pequeno Porte (EPP)', 'Demais'],
  grandeRede: ['Todos', 'Sim', 'Não'],
  parTeia: [
    { label: 'Sem filtro', value: 'Todos' },
    { label: 'CNPJ Nível 2 da Teia com PAR', value: 'n2' },
    { label: 'CNPJ Nível 4 da Teia com PAR', value: 'n4' },
    { label: 'Qualquer CNPJ com PAR', value: 'qualquer' },
  ],
  socioBeneficio: SOCIO_BENEFICIO_FILTER_OPTIONS,
  socioEsocial: SOCIO_ESOCIAL_FILTER_OPTIONS,
  cluster:  ['Todos', 'Cluster 0 - Risco Crítico', 'Cluster 1 - Risco Alto', 'Cluster 2 - Risco Médio', 'Cluster 3 - Risco Baixo'],
  rfa:      ['Todos', 'Acima de R$ 1 Mi', 'Entre R$ 500k e R$ 1 Mi', 'Até R$ 500k'],
};
