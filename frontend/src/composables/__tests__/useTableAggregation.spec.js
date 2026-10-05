import { describe, expect, it } from 'vitest';
import { computed, ref } from 'vue';
import { useTableAggregation } from '../useTableAggregation';

describe('useTableAggregation', () => {
  it('recalcula totais e percentuais quando as linhas reativas mudam', () => {
    const rows = ref([
      { vendas: 30, irregular: 5 },
      { vendas: 70, irregular: 15 },
    ]);
    const { totals } = useTableAggregation(rows, {
      sums: ['vendas', 'irregular'],
      percents: [{ field: 'percentual', numerator: 'irregular', denominator: 'vendas' }],
    });
    expect(totals.value).toEqual({ vendas: 100, irregular: 20, percentual: 20 });
    rows.value = [{ vendas: 0, irregular: 8 }];
    expect(totals.value.percentual).toBe(0);
    expect(totals.value.irregular).toBe(8);
  });

  it('retorna objeto vazio para tabela sem linhas', () => {
    expect(useTableAggregation(ref([]), { sums: ['vendas'] }).totals.value).toEqual({});
    expect(useTableAggregation(computed(() => null), { sums: ['vendas'] }).totals.value).toEqual({});
  });

  it('trata campos ausentes e denominadores nulos como zero', () => {
    const rows = ref([{ vendas: null, irregular: undefined }, { vendas: 0, irregular: 3 }]);
    const { totals } = useTableAggregation(rows, {
      sums: ['vendas', 'irregular'],
      percents: [{ field: 'percentual', numerator: 'irregular', denominator: 'vendas' }],
    });
    expect(totals.value).toEqual({ vendas: 0, irregular: 3, percentual: 0 });
  });

  it('usa zero quando numerador ou denominador não fazem parte das somas', () => {
    const rows = ref([{ receita: 12, quantidade: 3 }]);
    const { totals: numeratorMissing } = useTableAggregation(rows, {
      sums: ['receita'],
      percents: [{ field: 'taxa', numerator: 'quantidade', denominator: 'receita' }],
    });
    const { totals: denominatorMissing } = useTableAggregation(rows, {
      sums: ['quantidade'],
      percents: [{ field: 'taxa', numerator: 'quantidade', denominator: 'receita' }],
    });

    expect(numeratorMissing.value.taxa).toBe(0);
    expect(denominatorMissing.value.taxa).toBe(0);
  });

  it('aceita schema sem percentuais para uma tabela que tem linhas', () => {
    const { totals } = useTableAggregation(ref([{ vendas: 18 }]), { sums: ['vendas'] });
    expect(totals.value).toEqual({ vendas: 18 });
  });
});
