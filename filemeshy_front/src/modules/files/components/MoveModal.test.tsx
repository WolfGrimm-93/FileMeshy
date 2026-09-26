import { useState } from 'react'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import MoveModal, { type MoveTarget } from './MoveModal'
import { filesService } from '../services/files.service'
import { foldersService } from '../services/folders.service'

vi.mock('../services/files.service', () => ({ filesService: { list: vi.fn(), move: vi.fn(), copy: vi.fn() } }))
vi.mock('../services/folders.service', () => ({ foldersService: { move: vi.fn(), copy: vi.fn() } }))
vi.mock('@/ui/toast/CustomToast', () => ({ toast: { error: vi.fn(), success: vi.fn() } }))

const A: MoveTarget = { id: 'idA', name: 'a.txt', type: 'file', currentFolderId: null }
const B: MoveTarget = { id: 'idB', name: 'b.txt', type: 'file', currentFolderId: null }

const list = vi.mocked(filesService.list)

function Harness({ onMoved }: { onMoved: () => void }) {
  const [target, setTarget] = useState<MoveTarget | null>(null)
  return (
    <>
      <button onClick={() => setTarget(A)}>abrirA</button>
      <button onClick={() => setTarget(B)}>abrirB</button>
      <MoveModal target={target} onClose={() => setTarget(null)} onMoved={onMoved} />
    </>
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  list.mockImplementation(async (params) =>
    params?.folderId
      ? { breadcrumb: [{ id: 'fx', name: 'Docs' }], folders: [], files: [] }
      : { breadcrumb: [], folders: [{ id: 'fx', name: 'Docs' }], files: [] } as never,
  )
})

describe('MoveModal', () => {
  it('una carga por apertura; reabrir con otro target vuelve a la raíz', async () => {
    render(<Harness onMoved={vi.fn()} />)
    fireEvent.click(screen.getByText('abrirA'))
    await waitFor(() => expect(list).toHaveBeenCalledTimes(1))
    expect(list).toHaveBeenLastCalledWith({ folderId: undefined })

    fireEvent.click(await screen.findByText('Docs'))
    await waitFor(() => expect(list).toHaveBeenLastCalledWith({ folderId: 'fx' }))
    expect(list).toHaveBeenCalledTimes(2)
    fireEvent.click(screen.getByText('Cancelar'))

    list.mockClear()
    fireEvent.click(screen.getByText('abrirB'))
    await waitFor(() => expect(list).toHaveBeenCalledTimes(1))
    expect(list).toHaveBeenCalledWith({ folderId: undefined })
    expect(await screen.findByText('Docs')).toBeInTheDocument() // raíz: subcarpeta listada, sin breadcrumb viejo
  })

  it('mostrar spinner mientras carga', async () => {
    let resolve!: (v: never) => void
    list.mockReturnValueOnce(new Promise((r) => { resolve = r as never }))
    const { baseElement } = render(<Harness onMoved={vi.fn()} />)
    fireEvent.click(screen.getByText('abrirA'))
    expect(baseElement.querySelector('.animate-spin')).toBeInTheDocument()
    resolve({ breadcrumb: [], folders: [], files: [] } as never)
    expect(await screen.findByText('No hay subcarpetas acá')).toBeInTheDocument()
  })

  it('confirmar mueve al destino elegido con el id del target', async () => {
    const onMoved = vi.fn()
    vi.mocked(filesService.move).mockResolvedValueOnce(undefined as never)
    render(<Harness onMoved={onMoved} />)
    fireEvent.click(screen.getByText('abrirA'))
    fireEvent.click(await screen.findByText('Docs'))
    await waitFor(() => expect(list).toHaveBeenCalledTimes(2))
    fireEvent.click(screen.getByText('Mover aquí'))
    await waitFor(() => expect(filesService.move).toHaveBeenCalledWith('idA', 'fx'))
    expect(onMoved).toHaveBeenCalledWith(A, 'fx')
    expect(foldersService.move).not.toHaveBeenCalled()
  })

  it('si falla el listado del destino no muestra carpetas del destino anterior y permite reintentar', async () => {
    list.mockReset()
    list.mockResolvedValueOnce({ breadcrumb: [], folders: [{ id: 'fx', name: 'Docs' }], files: [] } as never)
    render(<Harness onMoved={vi.fn()} />)
    fireEvent.click(screen.getByText('abrirA'))
    const docs = await screen.findByText('Docs')
    list.mockRejectedValueOnce(new Error('boom'))
    fireEvent.click(docs)
    // la carpeta 'Docs' (raíz) desaparece: la navegación a fx falló
    expect(await screen.findByText(/No se pudo cargar/)).toBeInTheDocument()
    expect(screen.queryByText('Docs', { selector: 'span.truncate' })).not.toBeInTheDocument()
    expect(screen.getByText('Mover aquí').closest('button')).toBeDisabled()

    list.mockResolvedValueOnce({ breadcrumb: [{ id: 'fx', name: 'Docs' }], folders: [], files: [] } as never)
    fireEvent.click(screen.getByText('Reintentar'))
    expect(await screen.findByText('No hay subcarpetas acá')).toBeInTheDocument()
    expect(screen.getByText('Mover aquí').closest('button')).not.toBeDisabled()
  })

  describe('modo copiar', () => {
    const inFolder: MoveTarget = { id: 'idC', name: 'c.txt', type: 'file', currentFolderId: 'fx' }

    function CopyHarness({ onMoved }: { onMoved: () => void }) {
      const [target, setTarget] = useState<MoveTarget | null>(null)
      return (
        <>
          <button onClick={() => setTarget(inFolder)}>abrirC</button>
          <MoveModal mode="copy" target={target} onClose={() => setTarget(null)} onMoved={onMoved} />
        </>
      )
    }

    it('preselecciona la carpeta actual y copiar ahí envía esa carpeta', async () => {
      const onMoved = vi.fn()
      vi.mocked(filesService.copy).mockResolvedValueOnce(undefined as never)
      render(<CopyHarness onMoved={onMoved} />)
      fireEvent.click(screen.getByText('abrirC'))
      await waitFor(() => expect(list).toHaveBeenCalledWith({ folderId: 'fx' }))
      await screen.findByText('No hay subcarpetas acá')
      fireEvent.click(screen.getByText('Copiar aquí'))
      await waitFor(() => expect(filesService.copy).toHaveBeenCalledWith('idC', 'fx'))
      expect(filesService.move).not.toHaveBeenCalled()
      expect(onMoved).toHaveBeenCalledWith(inFolder, 'fx')
    })

    it('elegir la raíz envía null explícito', async () => {
      vi.mocked(filesService.copy).mockResolvedValueOnce(undefined as never)
      render(<CopyHarness onMoved={vi.fn()} />)
      fireEvent.click(screen.getByText('abrirC'))
      await screen.findByText('No hay subcarpetas acá')
      fireEvent.click(screen.getByText('Raíz'))
      await screen.findByText('Docs')
      fireEvent.click(screen.getByText('Copiar aquí'))
      await waitFor(() => expect(filesService.copy).toHaveBeenCalledWith('idC', null))
    })

    it('carpeta: usa foldersService.copy', async () => {
      vi.mocked(foldersService.copy).mockResolvedValueOnce(undefined as never)
      const folderTarget: MoveTarget = { id: 'idD', name: 'd', type: 'folder', currentFolderId: null }
      function H() {
        const [t, setT] = useState<MoveTarget | null>(folderTarget)
        return <MoveModal mode="copy" target={t} onClose={() => setT(null)} onMoved={() => {}} />
      }
      render(<H />)
      await screen.findByText('Docs')
      fireEvent.click(await screen.findByText('Docs'))
      await waitFor(() => expect(list).toHaveBeenLastCalledWith({ folderId: 'fx' }))
      await screen.findByText('No hay subcarpetas acá')
      fireEvent.click(screen.getByText('Copiar aquí'))
      await waitFor(() => expect(foldersService.copy).toHaveBeenCalledWith('idD', 'fx'))
    })
  })
})
