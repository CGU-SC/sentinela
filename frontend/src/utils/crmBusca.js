import { normalizeSearchText } from './searchNormalization';

// Mesma leitura do termo que o backend faz em crm_analysis._parse_busca_crm.
const UFS_CRM = new Set([
  'AC', 'AL', 'AM', 'AP', 'BA', 'CE', 'DF', 'ES', 'GO', 'MA', 'MG', 'MS', 'MT', 'PA',
  'PB', 'PE', 'PI', 'PR', 'RJ', 'RN', 'RO', 'RR', 'RS', 'SC', 'SE', 'SP', 'TO',
]);
const BUSCA_CRM_RE = /^(?:crm[\s/-]*)?(?:(?<n1>\d+)[\s/-]*(?<u1>[a-z]{2})|(?<u2>[a-z]{2})[\s/-]*(?<n2>\d+)|(?<n3>\d+))$/;

/**
 * Interpreta a busca do ranking de médicos como CRM.
 * Aceita "800", "CRM 800", "800/SC", "800-SC", "800 SC", "CRM-SC 800", "SC/800"...
 * @param {string} query
 * @returns {{ numero: string, uf: string|null } | null} null quando é busca por nome.
 */
export function parseBuscaCrm(query) {
  const match = BUSCA_CRM_RE.exec(normalizeSearchText(query ?? ''));
  if (!match) return null;
  const { n1, n2, n3, u1, u2 } = match.groups;
  if (n3) return { numero: n3, uf: null };
  const uf = (u1 || u2).toUpperCase();
  if (!UFS_CRM.has(uf)) return null;
  return { numero: n1 || n2, uf };
}

/**
 * Termos de destaque das linhas "nome" e "CRM" da coluna MÉDICO / CRM, no
 * formato exibido ("CRM 800/SC"), qualquer que seja a forma digitada.
 * @param {string} query
 * @returns {{ nome: string, crm: string }}
 */
export function destaqueBuscaMedico(query) {
  const crm = parseBuscaCrm(query);
  if (!crm) return { nome: query, crm: query };
  return { nome: '', crm: crm.uf ? `${crm.numero}/${crm.uf}` : crm.numero };
}
