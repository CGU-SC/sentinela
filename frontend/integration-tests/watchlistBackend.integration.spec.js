import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

import { useEvidenciasStore } from '../src/stores/evidencias'
import { useFarmaciaListsStore } from '../src/stores/farmaciaLists'

const CNPJ = '12345678000195'
const evidencePayload = {
  cnpj: CNPJ,
  tipo: 'dia',
  dt_janela: '2026-10-05',
  snapshot: { horario: '08:15', valor: 125.5 },
  nota: '  Conferir no sistema integrado  ',
}

describe('integração HTTP Pinia → FastAPI de preferências e evidências', () => {
  beforeEach(() => {
    localStorage.clear()
    setActivePinia(createPinia())
  })

  afterEach(() => {
    localStorage.clear()
  })

  it('persiste e relê a lista e as evidências pelo contrato HTTP real', async () => {
    const farmaciaLists = useFarmaciaListsStore()
    await farmaciaLists.loadFromBackend()
    expect(farmaciaLists.loadState).toBe('ready')
    expect(farmaciaLists.interesse).toEqual([])

    const evidencias = useEvidenciasStore()
    await evidencias.garantirCarregado()
    expect(evidencias.loadState).toBe('ready')
    expect(evidencias.itens).toEqual([])

    const criada = await evidencias.marcar(evidencePayload, {
      razaoSocial: 'Farmácia de Integração',
    })

    expect(criada.farmaciaAdicionada).toBe(true)
    expect(criada.evidencia).toMatchObject({
      cnpj: CNPJ,
      tipo: 'dia',
      dt_janela: evidencePayload.dt_janela,
      nota: 'Conferir no sistema integrado',
    })
    expect(farmaciaLists.isInteresse(CNPJ)).toBe(true)
    expect(evidencias.contar(CNPJ)).toBe(1)

    setActivePinia(createPinia())
    const listaRecarregada = useFarmaciaListsStore()
    await listaRecarregada.loadFromBackend()
    const evidenciasRecarregadas = useEvidenciasStore()
    await evidenciasRecarregadas.garantirCarregado()

    expect(listaRecarregada.loadState).toBe('ready')
    expect(listaRecarregada.interesse).toContainEqual(expect.objectContaining({
      cnpj: CNPJ,
      razaoSocial: 'Farmácia de Integração',
    }))
    expect(evidenciasRecarregadas.loadState).toBe('ready')
    expect(evidenciasRecarregadas.listarDoCnpj(CNPJ)).toHaveLength(1)
    expect(evidenciasRecarregadas.listarDoCnpj(CNPJ)[0]).toMatchObject({
      id: criada.evidencia.id,
      nota: 'Conferir no sistema integrado',
    })

    await expect(evidenciasRecarregadas.marcar(evidencePayload))
      .rejects.toThrow('Este item já está na cesta de evidências.')
    expect(evidenciasRecarregadas.contar(CNPJ)).toBe(1)
  })
})
