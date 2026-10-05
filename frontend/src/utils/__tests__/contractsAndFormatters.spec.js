import { describe, expect, it } from 'vitest'

import { getApiErrorMessage } from '@/utils/apiErrors'
import { buildHealthRegionGeoJson } from '@/utils/geo/municipalTerritory'
import { formatCpfCnpj, formatCnaeEvidence, formatSocietyDate } from '@/utils/network/networkFormatters'

describe('getApiErrorMessage', () => {
  it('prioriza detalhe textual, mensagens e lista de validação da API', async () => {
    expect(await getApiErrorMessage({ text: async () => '{"detail":"Sem acesso"}' }, 'Falha')).toBe('Sem acesso')
    expect(await getApiErrorMessage({ text: async () => '{"message":"Tente novamente"}' }, 'Falha')).toBe('Tente novamente')
    expect(await getApiErrorMessage({ text: async () => '{"detail":[{"msg":"Campo obrigatório"},422]}' }, 'Falha'))
      .toBe('Campo obrigatório; 422')
  })

  it('usa texto bruto ou mensagem padrão conforme o corpo da resposta', async () => {
    expect(await getApiErrorMessage({ text: async () => 'Erro upstream' }, 'Falha')).toBe('Erro upstream')
    expect(await getApiErrorMessage({ text: async () => ' ' }, 'Falha padrão')).toBe('Falha padrão')
    expect(await getApiErrorMessage({ text: async () => '{"detail":{"reason":"unknown"}}' }, 'Falha padrão')).toBe('Falha padrão')
    expect(await getApiErrorMessage({ text: async () => { throw new Error('corpo indisponível') } }, 'Falha padrão')).toBe('Falha padrão')
  })
})

describe('buildHealthRegionGeoJson', () => {
  const localidades = [
    { id_ibge7: 1100015, id_regiao_saude: 1100001, sg_uf: 'RO', no_regiao_saude: 'Nome não é chave' },
    { id_ibge7: 1100205, id_regiao_saude: 1100002, sg_uf: 'RO' },
    { id_ibge7: 1200013, id_regiao_saude: 1100001, sg_uf: 'AC' },
  ]
  const feature = (id) => ({ type: 'Feature', properties: { id }, geometry: { type: 'Polygon', coordinates: [] } })

  it('seleciona geometrias por UF, id_regiao_saude e id_ibge7', () => {
    const expected = feature(1100015)
    const result = buildHealthRegionGeoJson({
      ufGeoJson: { type: 'FeatureCollection', features: [expected, feature(1100205), feature(1200013)] },
      localidades,
      uf: 'RO',
      regiaoId: 1100001,
    })

    expect(result).toEqual({ type: 'FeatureCollection', features: [expected] })
  })

  it.each([
    [{ ufGeoJson: null, localidades, uf: 'RO', regiaoId: 1100001 }, 'GeoJSON municipal da UF ausente ou invalido.'],
    [{ ufGeoJson: { features: [] }, localidades: [], uf: 'RO', regiaoId: 1100001 }, 'Contrato de localidades indisponivel.'],
    [{ ufGeoJson: { features: [] }, localidades, uf: null, regiaoId: 1100001 }, 'UF e id_regiao_saude sao obrigatorios para montar o territorio.'],
    [{ ufGeoJson: { features: [] }, localidades, uf: 'RO', regiaoId: 999 }, 'Regiao de saude sem municipios no contrato de localidades.'],
    [{ ufGeoJson: { features: [feature(1100205)] }, localidades, uf: 'RO', regiaoId: 1100001 }, 'GeoJSON municipal sem geometrias para a regiao de saude.'],
  ])('falha com contrato territorial incompleto', (input, message) => {
    expect(() => buildHealthRegionGeoJson(input)).toThrow(message)
  })
})

describe('formatadores da teia societária', () => {
  it('formata CPF/CNPJ e preserva identificador com tamanho inesperado', () => {
    expect(formatCpfCnpj('123.456.789-01')).toBe('123.456.789-01')
    expect(formatCpfCnpj('12.345.678/0001-95')).toBe('12.345.678/0001-95')
    expect(formatCpfCnpj('12345')).toBe('12345')
    expect(formatCpfCnpj(null)).toBe('—')
  })

  it('formata datas civis sem converter fuso e preserva formatos não reconhecidos', () => {
    expect(formatSocietyDate('2025-06-07T23:00:00Z')).toBe('07/06/2025')
    expect(formatSocietyDate('data desconhecida')).toBe('data desconhecida')
    expect(formatSocietyDate('')).toBe('—')
  })

  it('combina código CNAE e descrição sem inventar conteúdo ausente', () => {
    expect(formatCnaeEvidence(1234, 'Comércio varejista')).toBe('1234 - Comércio varejista')
    expect(formatCnaeEvidence(null, 'Comércio varejista')).toBe('Não informado - Comércio varejista')
    expect(formatCnaeEvidence(1234, '')).toBe('1234')
  })
})
