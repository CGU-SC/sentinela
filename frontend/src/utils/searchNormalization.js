// Adaptado de NuvoInvest/frontend/app/utils/searchNormalization.ts.
const COMBINING_MARKS = /[\u0300-\u036f]/g;
const REPEATED_WHITESPACE = /\s+/g;

export function normalizeSearchText(value) {
  return value
    .normalize('NFKD')
    .replace(COMBINING_MARKS, '')
    .toLocaleLowerCase('pt-BR')
    .replace(REPEATED_WHITESPACE, ' ')
    .trim();
}
