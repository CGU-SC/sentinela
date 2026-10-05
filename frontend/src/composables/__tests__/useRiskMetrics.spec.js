import { describe, expect, it } from 'vitest';
import { RISK_COLORS, RISK_CSS_CLASSES, RISK_THRESHOLDS } from '@/config/riskConfig';
import { useRiskMetrics } from '../useRiskMetrics';

describe('useRiskMetrics', () => {
  it('classifica os valores nos limites configurados', () => {
    const risk = useRiskMetrics();
    const { MEDIUM, HIGH, CRITICAL } = RISK_THRESHOLDS;
    expect(risk.getRiskLabel(MEDIUM)).toBe('Baixo');
    expect(risk.getRiskLabel(MEDIUM + 0.01)).toBe('Médio');
    expect(risk.getRiskLabel(HIGH + 0.01)).toBe('Alto');
    expect(risk.getRiskLabel(CRITICAL + 0.01)).toBe('Crítico');
    expect(risk.getRiskSeverity(HIGH + 0.01)).toBe('danger');
    expect(risk.getRiskSeverity(MEDIUM + 0.01)).toBe('warn');
    expect(risk.getRiskSeverity(MEDIUM)).toBe('success');
  });

  it('mantém classes e cores alinhadas com a configuração central', () => {
    const risk = useRiskMetrics();
    expect(risk.getRiskClass(100)).toBe(RISK_CSS_CLASSES.CRITICAL);
    expect(risk.getRiskColor(100)).toBe(RISK_COLORS.CRITICAL);
    expect(risk.getRiskClass(0)).toBe(RISK_CSS_CLASSES.LOW);
    expect(risk.getRiskColor(0)).toBe(RISK_COLORS.LOW);
  });

  it('aplica todos os níveis de risco em labels, severidades, classes e cores', () => {
    const risk = useRiskMetrics();
    const { MEDIUM, HIGH, CRITICAL } = RISK_THRESHOLDS;
    const levels = [
      [MEDIUM, 'Baixo', 'success', RISK_CSS_CLASSES.LOW, RISK_COLORS.LOW],
      [MEDIUM + 0.01, 'Médio', 'warn', RISK_CSS_CLASSES.MEDIUM, RISK_COLORS.MEDIUM],
      [HIGH + 0.01, 'Alto', 'danger', RISK_CSS_CLASSES.HIGH, RISK_COLORS.HIGH],
      [CRITICAL + 0.01, 'Crítico', 'danger', RISK_CSS_CLASSES.CRITICAL, RISK_COLORS.CRITICAL],
    ];
    for (const [value, label, severity, className, color] of levels) {
      expect(risk.getRiskLabel(value)).toBe(label);
      expect(risk.getRiskSeverity(value)).toBe(severity);
      expect(risk.getRiskClass(value)).toBe(className);
      expect(risk.getRiskColor(value)).toBe(color);
    }
  });
});
