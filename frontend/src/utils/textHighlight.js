// Portado de NuvoInvest/frontend/app/utils/textHighlight.ts.
import { normalizeSearchText } from './searchNormalization';

function normalizedCharacters(text) {
  const result = [];
  let offset = 0;
  let pendingSpace = null;

  for (const character of text) {
    const start = offset;
    offset += character.length;
    const normalized = normalizeSearchText(character);

    if (!normalized) {
      if (/\s/u.test(character) && result.length > 0) {
        pendingSpace = { value: ' ', start, end: offset };
      }
      continue;
    }

    if (pendingSpace) {
      result.push(pendingSpace);
      pendingSpace = null;
    }
    for (const normalizedCharacter of normalized) {
      result.push({ value: normalizedCharacter, start, end: offset });
    }
  }

  return result;
}

export function highlightSegments(text, query) {
  const normalizedQuery = normalizeSearchText(query);
  if (!normalizedQuery) return [{ text, matched: false }];

  const characters = normalizedCharacters(text);
  const normalizedText = characters.map((character) => character.value).join('');
  const index = normalizedText.indexOf(normalizedQuery);
  if (index === -1) return [{ text, matched: false }];

  const first = characters[index];
  const last = characters[index + normalizedQuery.length - 1];
  if (!first || !last) return [{ text, matched: false }];

  const segments = [];
  if (first.start > 0) segments.push({ text: text.slice(0, first.start), matched: false });
  segments.push({ text: text.slice(first.start, last.end), matched: true });
  if (last.end < text.length) segments.push({ text: text.slice(last.end), matched: false });
  return segments;
}
