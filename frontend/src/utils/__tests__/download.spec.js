import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import {
  convertDocxToPdf,
  createPdfObjectUrlFromDesktopFile,
  downloadBlobFromResponse,
  getFilenameFromContentDisposition,
  openDownloadedFile,
  saveBlobOrDownload,
} from '@/utils/download'

describe('download utilities', () => {
  let originalPywebview
  let originalCreateObjectUrl
  let originalRevokeObjectUrl

  beforeEach(() => {
    originalPywebview = Object.getOwnPropertyDescriptor(window, 'pywebview')
    originalCreateObjectUrl = window.URL.createObjectURL
    originalRevokeObjectUrl = window.URL.revokeObjectURL
    window.URL.createObjectURL = vi.fn(() => 'blob:sentinela')
    window.URL.revokeObjectURL = vi.fn()
    delete window.pywebview
  })

  afterEach(() => {
    if (originalPywebview) Object.defineProperty(window, 'pywebview', originalPywebview)
    else delete window.pywebview
    if (originalCreateObjectUrl) window.URL.createObjectURL = originalCreateObjectUrl
    else delete window.URL.createObjectURL
    if (originalRevokeObjectUrl) window.URL.revokeObjectURL = originalRevokeObjectUrl
    else delete window.URL.revokeObjectURL
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  function setDesktopApi(api) {
    Object.defineProperty(window, 'pywebview', {
      configurable: true,
      value: { api },
    })
  }

  it('extrai filename RFC 5987, filename comum, decodifica e higieniza caminhos', () => {
    expect(getFilenameFromContentDisposition("attachment; filename*=UTF-8''Nota%20T%C3%A9cnica.docx"))
      .toBe('Nota Técnica.docx')
    expect(getFilenameFromContentDisposition('attachment; filename="relatorio:final.pdf"')).toBe('relatorio_final.pdf')
    expect(getFilenameFromContentDisposition('attachment; filename="%ZZ.pdf"')).toBe('%ZZ.pdf')
    expect(getFilenameFromContentDisposition('attachment; filename="   "')).toBe(null)
    expect(getFilenameFromContentDisposition(null)).toBe(null)
    expect(getFilenameFromContentDisposition('attachment; name="arquivo.pdf"')).toBe(null)
    expect(getFilenameFromContentDisposition("attachment; filename*=UTF-8''; filename=\"relatorio.pdf\""))
      .toBe('relatorio.pdf')
  })

  it('abre arquivo e converte DOCX no desktop, propagando erros do contrato', async () => {
    const openFile = vi.fn().mockResolvedValue({ ok: true, opened: true })
    const convert = vi.fn().mockResolvedValue({ ok: true, path: 'nota.pdf' })
    setDesktopApi({ open_file: openFile, convert_docx_to_pdf: convert })
    await expect(openDownloadedFile('nota.docx')).resolves.toEqual({ ok: true, opened: true })
    await expect(convertDocxToPdf('nota.docx')).resolves.toEqual({ ok: true, path: 'nota.pdf' })
    expect(openFile).toHaveBeenCalledWith('nota.docx')
    expect(convert).toHaveBeenCalledWith('nota.docx')

    openFile.mockResolvedValueOnce({ ok: false, error: 'Arquivo ausente' })
    convert.mockResolvedValueOnce({ ok: false })
    await expect(openDownloadedFile('missing')).rejects.toThrow('Arquivo ausente')
    await expect(convertDocxToPdf('invalid')).rejects.toThrow('Nao foi possivel converter o DOCX para PDF.')
    openFile.mockResolvedValueOnce({ ok: false })
    await expect(openDownloadedFile('invalid')).rejects.toThrow('Nao foi possivel abrir o arquivo.')
  })

  it('informa indisponibilidade de funções nativas no navegador', async () => {
    await expect(openDownloadedFile('a.pdf')).rejects.toThrow('Abertura nativa de arquivo indisponivel.')
    await expect(convertDocxToPdf('a.docx')).rejects.toThrow('Conversao DOCX/PDF indisponivel no modo atual.')
    await expect(createPdfObjectUrlFromDesktopFile('a.pdf')).rejects.toThrow('Visualizacao nativa de PDF indisponivel.')
    setDesktopApi({})
    await expect(openDownloadedFile('a.pdf')).rejects.toThrow('Abertura nativa de arquivo indisponivel.')
    await expect(convertDocxToPdf('a.docx')).rejects.toThrow('Conversao DOCX/PDF indisponivel no modo atual.')
    await expect(createPdfObjectUrlFromDesktopFile('a.pdf')).rejects.toThrow('Visualizacao nativa de PDF indisponivel.')
  })

  it('lê o PDF desktop em base64, cria blob e retorna a URL local', async () => {
    setDesktopApi({ read_pdf_base64: vi.fn().mockResolvedValue({ ok: true, base64: 'JVBERi0x', id: 'report' }) })
    const result = await createPdfObjectUrlFromDesktopFile('report.pdf')
    expect(result).toMatchObject({ ok: true, id: 'report', url: 'blob:sentinela' })
    expect(window.URL.createObjectURL).toHaveBeenCalledWith(expect.objectContaining({ type: 'application/pdf' }))

    window.pywebview.api.read_pdf_base64.mockResolvedValueOnce({ ok: false })
    await expect(createPdfObjectUrlFromDesktopFile('missing.pdf')).rejects.toThrow('Nao foi possivel ler o PDF salvo.')
    window.pywebview.api.read_pdf_base64.mockResolvedValueOnce({ ok: true, base64: 'JVBERi0x' })
    await expect(createPdfObjectUrlFromDesktopFile('valid.pdf')).resolves.toMatchObject({ ok: true })
    window.pywebview.api.read_pdf_base64.mockResolvedValueOnce({ ok: true })
    await expect(createPdfObjectUrlFromDesktopFile('empty.pdf')).resolves.toMatchObject({ ok: true, url: 'blob:sentinela' })
  })

  it('salva blobs pela API desktop com nome seguro e payload base64', async () => {
    const saveFile = vi.fn().mockResolvedValue({ ok: true, path: 'C:/saved/file.pdf' })
    setDesktopApi({ save_file: saveFile })
    const result = await saveBlobOrDownload(new Blob(['sentinela']), 'relatorio:final.pdf')

    expect(result).toEqual({ ok: true, path: 'C:/saved/file.pdf', desktop: true })
    expect(saveFile).toHaveBeenCalledWith('relatorio_final.pdf', expect.any(String))
    expect(atob(saveFile.mock.calls[0][1])).toBe('sentinela')

    saveFile.mockResolvedValueOnce({ ok: false, error: 'Sem permissão' })
    await expect(saveBlobOrDownload(new Blob(['x']), 'arquivo.pdf')).rejects.toThrow('Sem permissão')
    saveFile.mockResolvedValueOnce({ ok: false })
    await expect(saveBlobOrDownload(new Blob(['x']), 'arquivo.pdf'))
      .rejects.toThrow('Nao foi possivel salvar o arquivo.')
  })

  it('valida leituras desktop inválidas e usa o nome seguro padrão no navegador', async () => {
    setDesktopApi({ read_pdf_base64: vi.fn().mockResolvedValue({ ok: false }) })
    await expect(createPdfObjectUrlFromDesktopFile('missing.pdf')).rejects.toThrow('Nao foi possivel ler o PDF salvo.')

    const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})
    delete window.pywebview
    await expect(saveBlobOrDownload(new Blob(['documento']), '   '))
      .resolves.toEqual({ ok: true, filename: 'download', desktop: false })
    await expect(saveBlobOrDownload(new Blob(['documento']), ''))
      .resolves.toEqual({ ok: true, filename: 'download', desktop: false })
    expect(click).toHaveBeenCalledTimes(2)
  })

  it('propaga as duas falhas possíveis ao transformar um blob em base64 desktop', async () => {
    setDesktopApi({ save_file: vi.fn() })
    vi.stubGlobal('FileReader', class {
      readAsDataURL() { this.result = 'data:application/pdf,'; this.onload() }
    })
    await expect(saveBlobOrDownload(new Blob(['x']), 'a.pdf'))
      .rejects.toThrow('Conteudo do arquivo invalido para salvamento.')

    vi.stubGlobal('FileReader', class {
      constructor() { this.error = new Error('leitura interrompida') }
      readAsDataURL() { this.onerror() }
    })
    await expect(saveBlobOrDownload(new Blob(['x']), 'a.pdf')).rejects.toThrow('leitura interrompida')

    vi.stubGlobal('FileReader', class {
      readAsDataURL() { this.onload() }
    })
    await expect(saveBlobOrDownload(new Blob(['x']), 'a.pdf'))
      .rejects.toThrow('Conteudo do arquivo invalido para salvamento.')

    vi.stubGlobal('FileReader', class {
      readAsDataURL() { this.onerror() }
    })
    await expect(saveBlobOrDownload(new Blob(['x']), 'a.pdf')).rejects.toThrow('Erro ao ler arquivo.')
  })

  it('faz download no navegador e usa nome alternativo quando o cabeçalho não tem filename', async () => {
    const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})
    const response = {
      blob: vi.fn().mockResolvedValue(new Blob(['documento'])),
      headers: { get: vi.fn().mockReturnValue(null) },
    }

    await expect(downloadBlobFromResponse(response, 'exportacao.xlsx'))
      .resolves.toEqual({ ok: true, filename: 'exportacao.xlsx', desktop: false })
    expect(response.blob).toHaveBeenCalledOnce()
    expect(click).toHaveBeenCalledOnce()
    expect(window.URL.createObjectURL).toHaveBeenCalledOnce()
    expect(window.URL.revokeObjectURL).toHaveBeenCalledWith('blob:sentinela')
  })
})
