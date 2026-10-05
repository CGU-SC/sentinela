import { describe, expect, it } from 'vitest';
import { useStatusClass } from '../useStatusClass';

describe('useStatusClass', () => {
  it('normaliza situação cadastral antes de escolher a classe', () => {
    const status = useStatusClass();
    expect(status.situacaoRfClass(' ativa ')).toBe('status-success');
    expect(status.situacaoRfClass('Baixada')).toBe('status-danger');
    expect(status.situacaoRfClass(null)).toBe('status-secondary');
  });

  it('classifica os valores explícitos da conexão MS', () => {
    const status = useStatusClass();
    expect(status.conexaoMsClass(true)).toBe('status-success');
    expect(status.conexaoMsClass('Ativa')).toBe('status-success');
    expect(status.conexaoMsClass(false)).toBe('status-danger');
    expect(status.conexaoMsClass('Inativa')).toBe('status-danger');
    expect(status.conexaoMsClass(null)).toBe('status-secondary');
  });
});
