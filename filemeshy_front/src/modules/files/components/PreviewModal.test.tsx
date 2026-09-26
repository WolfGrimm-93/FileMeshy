import { render, screen, waitFor } from '@testing-library/react'
import PreviewModal, { type PreviewTarget } from './PreviewModal'
import { filesService } from '../services/files.service'

vi.mock('../services/files.service', () => ({ filesService: { getOfficePreviewUrl: vi.fn() } }))

const office = (fileId: string): PreviewTarget => ({
  name: `${fileId}.docx`,
  mimeType: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
  downloadUrl: 'http://x/dl',
  fileId,
})
const png: PreviewTarget = { name: 'img.png', mimeType: 'image/png', downloadUrl: 'http://x/img.png' }

const getOffice = vi.mocked(filesService.getOfficePreviewUrl)

beforeEach(() => getOffice.mockReset())

describe('PreviewModal', () => {
  it('no monta nada sin target', () => {
    const { baseElement } = render(<PreviewModal target={null} onClose={() => {}} />)
    expect(baseElement.querySelector('[role="dialog"]')).not.toBeInTheDocument()
  })

  it('imagen: no llama al backend de Office', () => {
    render(<PreviewModal target={png} onClose={() => {}} />)
    expect(screen.getByAltText('img.png')).toBeInTheDocument()
    expect(getOffice).not.toHaveBeenCalled()
  })

  it('Office: muestra loading y luego el iframe con la URL convertida', async () => {
    getOffice.mockResolvedValueOnce('http://x/preview.pdf')
    render(<PreviewModal target={office('f1')} onClose={() => {}} />)
    expect(screen.getByText('Generando vista previa...')).toBeInTheDocument()
    expect(getOffice).toHaveBeenCalledWith('f1')
    const frame = await screen.findByTitle('f1.docx')
    expect(frame).toHaveAttribute('src', 'http://x/preview.pdf')
  })

  it('Office: error del backend muestra el mensaje y el botón de descarga', async () => {
    getOffice.mockRejectedValueOnce(new Error('x'))
    render(<PreviewModal target={office('f1')} onClose={() => {}} />)
    expect(await screen.findByText('No se pudo generar la vista previa de este documento.')).toBeInTheDocument()
    expect(screen.getByText('Descargar archivo original')).toBeInTheDocument()
  })

  it('cambiar de archivo Office no muestra el preview del anterior y hace una llamada por archivo', async () => {
    getOffice.mockResolvedValueOnce('http://x/one.pdf')
    const { rerender } = render(<PreviewModal target={office('f1')} onClose={() => {}} />)
    await screen.findByTitle('f1.docx')

    let resolveTwo!: (u: string) => void
    getOffice.mockReturnValueOnce(new Promise((r) => { resolveTwo = r }))
    rerender(<PreviewModal target={office('f2')} onClose={() => {}} />)
    expect(screen.getByText('Generando vista previa...')).toBeInTheDocument()
    expect(document.querySelector('iframe')).toBeNull()
    resolveTwo('http://x/two.pdf')
    await waitFor(() => expect(screen.getByTitle('f2.docx')).toHaveAttribute('src', 'http://x/two.pdf'))
    expect(getOffice).toHaveBeenCalledTimes(2)
  })

  it('reabrir el mismo archivo Office no muestra la URL vieja mientras recarga', async () => {
    getOffice.mockResolvedValueOnce('http://x/one.pdf')
    const { rerender } = render(<PreviewModal target={office('f1')} onClose={() => {}} />)
    await screen.findByTitle('f1.docx')
    rerender(<PreviewModal target={null} onClose={() => {}} />)

    getOffice.mockReturnValueOnce(new Promise(() => {}))
    rerender(<PreviewModal target={office('f1')} onClose={() => {}} />)
    expect(screen.getByText('Generando vista previa...')).toBeInTheDocument()
    expect(document.querySelector('iframe')).toBeNull()
  })
})
