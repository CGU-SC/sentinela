import { describe, expect, it } from 'vitest';
import { extractCnpjFilter, extractCnpjRaiz, parseMunicipio } from '../useParsing';

describe('useParsing', () => {
  it('interpreta município com UF sem alterar entradas simples ou numéricas', () => {
    expect(parseMunicipio('Goiânia|GO')).toBe('Goiânia');
    expect(parseMunicipio('Cruzeiro do Sul')).toBe('Cruzeiro do Sul');
    expect(parseMunicipio(1200013)).toBe('1200013');
    expect(parseMunicipio('')).toBe('');
    expect(parseMunicipio(null)).toBe('');
  });

  it('extrai raiz e normaliza filtros completos sem pontuação', () => {
    expect(extractCnpjRaiz('12.345.678/0001-99')).toBe('12345678');
    expect(extractCnpjRaiz('')).toBe(null);
    expect(extractCnpjFilter('12.345.678')).toBe('12345678');
    expect(extractCnpjFilter('12.345.678/0001-99')).toBe('12345678000199');
    expect(extractCnpjFilter('1234567')).toBe(null);
    expect(extractCnpjFilter(null)).toBe(null);
    expect(extractCnpjRaiz(null)).toBe(null);
  });
});
