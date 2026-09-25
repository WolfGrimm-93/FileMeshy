import { render, screen, fireEvent } from '@testing-library/react'
import { FileUpload } from './FileUpload'

// File con tamaño simulado (sin alocar memoria real)
function fileOfSize(name: string, size: number) {
  const f = new File(['x'], name)
  Object.defineProperty(f, 'size', { value: size })
  return f
}

function selectFiles(container: HTMLElement, files: File[]) {
  const input = container.querySelector('input[type="file"]') as HTMLInputElement
  fireEvent.change(input, { target: { files } })
}

const MB = 1024 * 1024

describe('FileUpload', () => {
  it('maxSize finito muestra el rótulo con el número', () => {
    render(<FileUpload maxSize={10} />)
    expect(screen.getByText('Tamaño máximo: 10MB')).toBeInTheDocument()
  })

  it.each([[Infinity], [NaN], [undefined]])('maxSize=%s no muestra rótulo con número', (maxSize) => {
    render(<FileUpload maxSize={maxSize} />)
    expect(screen.queryByText(/Tamaño máximo/)).not.toBeInTheDocument()
    expect(document.body.textContent).not.toMatch(/\d+MB/)
  })

  it('un archivo sobre el tope muestra error y NO llama onFilesSelected', () => {
    const onFilesSelected = vi.fn()
    const { container } = render(<FileUpload maxSize={10} onFilesSelected={onFilesSelected} />)
    selectFiles(container, [fileOfSize('grande.bin', 11 * MB)])
    expect(screen.getByText('El archivo grande.bin excede el tamaño máximo de 10MB')).toBeInTheDocument()
    expect(onFilesSelected).not.toHaveBeenCalled()
  })

  it('un archivo dentro del tope se acepta', () => {
    const onFilesSelected = vi.fn()
    const { container } = render(<FileUpload maxSize={10} onFilesSelected={onFilesSelected} />)
    const ok = fileOfSize('ok.bin', 5 * MB)
    selectFiles(container, [ok])
    expect(onFilesSelected).toHaveBeenCalledWith([ok])
  })

  it('sin tope (undefined) acepta un archivo de 20 GB sin error', () => {
    const onFilesSelected = vi.fn()
    const { container } = render(<FileUpload onFilesSelected={onFilesSelected} />)
    selectFiles(container, [fileOfSize('enorme.bin', 20 * 1024 * MB)])
    expect(onFilesSelected).toHaveBeenCalledOnce()
    expect(screen.queryByText(/excede/)).not.toBeInTheDocument()
  })
})
