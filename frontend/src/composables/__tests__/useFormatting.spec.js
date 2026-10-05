import { describe, expect, it } from 'vitest';
import { useFormatting } from '../useFormatting';

describe('useFormatting', () => {
  const formatting = useFormatting();

  it('abrevia valores monetários e quantidades nos limites definidos', () => {
    expect(formatting.formatBRL(999)).toContain('999');
    expect(formatting.formatBRL(1500)).toBe('R$ 1K');
    expect(formatting.formatBRL(927000000)).toBe('R$ 927,0M');
    expect(formatting.formatBRL(1500000000)).toBe('R$ 1,5B');
    expect(formatting.formatNumber(1000000)).toBe('1,0M');
    expect(formatting.formatNumber(1999)).toBe('1K');
  });

  it('formata percentuais, datas locais, título e CNPJ', () => {
    expect(formatting.formatPercent(15.6)).toBe('15,60%');
    expect(formatting.formatPercent(null)).toBe('0,00%');
    expect(formatting.toLocalISO(new Date(2024, 0, 9))).toBe('2024-01-09');
    expect(formatting.toLocalISO('2024-01-09')).toBe(null);
    expect(formatting.formatarData('2024-01-09')).toBe('09/01/2024');
    expect(formatting.formatarData('data')).toBe('data');
    expect(formatting.formatTitleCase('SÃO PAULO - CENTRO')).toBe('São Paulo - Centro');
    expect(formatting.formatCnpj('12345678000199')).toBe('12.345.678/0001-99');
    expect(formatting.formatCnpj('123')).toBe('123');
  });

  it('trata limites, valores nulos e entradas fora do formato', () => {
    expect(formatting.formatBRL(1000)).toBe('R$ 1K');
    expect(formatting.formatBRL(0)).toContain('0');
    expect(formatting.formatNumber(999)).toContain('999');
    expect(formatting.formatNumber(1000)).toBe('1K');
    expect(formatting.formatPercent(undefined)).toBe('0,00%');
    expect(formatting.toLocalISO(null)).toBe(null);
    expect(formatting.formatarData(null)).toBe('—');
    expect(formatting.formatTitleCase('')).toBe('');
    expect(formatting.formatTitleCase(12)).toBe('');
    expect(formatting.formatCnpj(null)).toBe('—');
  });
});
