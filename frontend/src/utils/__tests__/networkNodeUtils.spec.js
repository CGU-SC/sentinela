import { describe, expect, it } from 'vitest'

import {
  buildNetworkNodeLabel,
  buildNetworkNodeVisualData,
  getNetworkRiskBorderColor,
  getNodeClasses,
  isCadunicoPersonNode,
  isCompanyNodeInactive,
  isDeceasedPersonNode,
  isEsocialPersonNode,
  isParCompanyNode,
  isSeguroDefesoPersonNode,
  isTruthyFlag,
  normalizeSearchText,
  truncateLabel,
} from '@/utils/network/networkNodeUtils'

describe('networkNodeUtils', () => {
  it('normaliza texto para busca e reconhece situações cadastrais inativas', () => {
    expect(normalizeSearchText('  FARMÁCIA Popular / LTDA. ')).toBe('farmaciapopularltda')
    expect(normalizeSearchText(null)).toBe('')
    for (const status of ['BAIXADA', 'INAPTA', 'SUSPENSA', 'NULA', 'INATIVA']) {
      expect(isCompanyNodeInactive({ type: 'PJ', situacao_rf: status })).toBe(true)
    }
    expect(isCompanyNodeInactive({ type: 'PF', situacao_rf: 'BAIXADA' })).toBe(false)
    expect(isCompanyNodeInactive(null)).toBe(false)
    expect(isCompanyNodeInactive({ type: 'PJ', situacao_rf: 'ATIVA' })).toBe(false)
    expect(isCompanyNodeInactive({ type: 'PJ' })).toBe(false)
  })

  it('interpreta flags booleanas e textuais apenas nos tipos de entidade aplicáveis', () => {
    expect(['1', 'true', 't', 'sim', 'yes'].every(isTruthyFlag)).toBe(true)
    expect(isTruthyFlag(' no ')).toBe(false)
    expect(isTruthyFlag(0)).toBe(false)
    expect(isTruthyFlag(1)).toBe(true)
    expect(isTruthyFlag(false)).toBe(false)

    const person = {
      is_falecido: 'sim',
      is_cadunico: 'true',
      is_esocial: 1,
      is_seguro_defeso: 'yes',
    }
    expect(isDeceasedPersonNode(person)).toBe(true)
    expect(isCadunicoPersonNode(person)).toBe(true)
    expect(isEsocialPersonNode(person)).toBe(true)
    expect(isSeguroDefesoPersonNode(person)).toBe(true)
    expect(isDeceasedPersonNode({ type: 'PJ', is_falecido: true })).toBe(false)
    expect(isDeceasedPersonNode({ type: '', is_falecido: 'TRUE' })).toBe(true)
    expect(isParCompanyNode({ type: 'PJ', is_par: '1' })).toBe(true)
    expect(isParCompanyNode({ type: 'PF', is_par: true })).toBe(false)
    expect(isParCompanyNode(undefined)).toBe(false)
  })

  it('combina classes de estado sem incluir classes vazias', () => {
    expect(getNodeClasses({
      type: 'PJ',
      situacao_rf: 'INAPTA',
      is_par: true,
    })).toBe('inactive-company par-company')
    expect(getNodeClasses({
      type: 'PF',
      is_falecido: true,
      is_cadunico: true,
      is_esocial: true,
      is_seguro_defeso: true,
    })).toBe('cadunico-pf esocial-pf seguro-defeso-pf deceased-pf')
    expect(getNodeClasses({ type: 'PJ', situacao_rf: 'ATIVA' })).toBe('')
  })

  it('trunca rótulos, formata risco e exige criticidade conhecida', () => {
    expect(truncateLabel(null, 5)).toBe('—')
    expect(truncateLabel('Sentinela', 5)).toBe('Senti…')
    expect(truncateLabel('Alvo', 4)).toBe('Alvo')
    expect(truncateLabel('Alvo', 0)).toBe('…')
    expect(getNetworkRiskBorderColor('CRÍTICO')).toBeTruthy()
    expect(getNetworkRiskBorderColor('ATENÇÃO')).toBeTruthy()
    expect(getNetworkRiskBorderColor('NORMAL')).toBeTruthy()
    expect(() => getNetworkRiskBorderColor('DESCONHECIDO')).toThrow('Criticidade de nao comprovacao invalida na teia.')
  })

  it('adiciona percentual formatado apenas aos nós de Farmácia Popular', () => {
    expect(buildNetworkNodeLabel({ type: 'PJ', label: 'Empresa Exemplo' }, 30)).toBe('Empresa Exemplo')
    expect(buildNetworkNodeLabel({ type: 'PJ_FARMACIA_POPULAR', id: '123', label: 'Farmácia Central', percentual_nao_comprovacao: 12.34 }, 20))
      .toBe('Farmácia Central\n12,3% não comp.')
    expect(() => buildNetworkNodeLabel({ type: 'PJ_FARMACIA_POPULAR', id: '123', label: 'Central' }, 20))
      .toThrow('Farmacia Popular 123 sem percentual de nao comprovacao.')
    expect(() => buildNetworkNodeLabel({ type: 'PJ_FARMACIA_POPULAR', label: 'Central' }, 20))
      .toThrow('Farmacia Popular  sem percentual de nao comprovacao.')
    expect(buildNetworkNodeVisualData({
      type: 'PJ_FARMACIA_POPULAR',
      id: '456',
      label: 'Farmácia do Bairro',
      percentual_nao_comprovacao: 90,
      criticidade_nao_comprovacao: 'CRÍTICO',
      conexao_ms: true,
    }, 40)).toMatchObject({
      fullLabel: 'Farmácia do Bairro',
      percentual_nao_comprovacao: 90,
      conexao_ms: true,
      risk_border_color: getNetworkRiskBorderColor('CRÍTICO'),
    })
    expect(buildNetworkNodeVisualData({ type: 'PJ', label: 'Empresa' }, 20).risk_border_color).toBeNull()
    expect(buildNetworkNodeVisualData(undefined, 20)).toMatchObject({ label: '—', risk_border_color: null })
  })
})
