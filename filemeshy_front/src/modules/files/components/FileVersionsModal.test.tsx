import { useState } from 'react'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import FileVersionsModal, { type FileVersionsTarget } from './FileVersionsModal'
import { filesService } from '../services/files.service'
import type { FileVersionOut } from '../types'

vi.mock('../services/files.service', () => ({
  filesService: { listVersions: vi.fn(), restoreVersion: vi.fn(), uploadNewVersion: vi.fn() },
}))
vi.mock('@/ui/toast/CustomToast', () => ({ toast: { error: vi.fn(), success: vi.fn() } }))

const A: FileVersionsTarget = { id: 'idA', name: 'a.txt' }
const B: FileVersionsTarget = { id: 'idB', name: 'b.txt' }
const list = vi.mocked(filesService.listVersions)

function versions(prefix: string, n: number): FileVersionOut[] {
  return Array.from({ length: n }, (_, i) => ({
    id: `${prefix}${i}`, version_number: n - i, size_bytes: 10, created_at: '2024-01-01T00:00:00Z', created_by_email: `${prefix}@x.com`,
  })) as unknown as FileVersionOut[]
}

function Harness({ onSaved }: { onSaved: () => void }) {
  const [target, setTarget] = useState<FileVersionsTarget | null>(null)
  return (
    <>
      <button onClick={() => setTarget(A)}>abrirA</button>
      <button onClick={() => setTarget(B)}>abrirB</button>
      <FileVersionsModal target={target} onClose={() => setTarget(null)} onSaved={onSaved} />
    </>
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  list.mockImplementation(async (id) => (id === 'idA' ? versions('A', 2) : versions('B', 1)))
})

describe('FileVersionsModal', () => {
  it('una carga por apertura y sin versiones viejas al abrir otro target', async () => {
    render(<Harness onSaved={vi.fn()} />)
    fireEvent.click(screen.getByText('abrirA'))
    expect(screen.getByText('Cargando historial de versiones...')).toBeInTheDocument()
    expect(await screen.findByText('Versión 2')).toBeInTheDocument()
    expect(list).toHaveBeenCalledTimes(1)
    expect(list).toHaveBeenCalledWith('idA')
    fireEvent.click(screen.getByText('Cerrar'))

    let resolveB!: (v: FileVersionOut[]) => void
    list.mockReturnValueOnce(new Promise((r) => { resolveB = r }))
    fireEvent.click(screen.getByText('abrirB'))
    expect(screen.queryByText('Versión 2')).not.toBeInTheDocument()
    expect(screen.getByText('Cargando historial de versiones...')).toBeInTheDocument()
    resolveB(versions('B', 1))
    expect(await screen.findByText('Versión 1')).toBeInTheDocument()
    expect(list).toHaveBeenCalledTimes(2)
    expect(list).toHaveBeenLastCalledWith('idB')
  })

  it('restaurar llama al servicio, recarga el historial y avisa onSaved', async () => {
    const onSaved = vi.fn()
    vi.mocked(filesService.restoreVersion).mockResolvedValueOnce(undefined as never)
    render(<Harness onSaved={onSaved} />)
    fireEvent.click(screen.getByText('abrirA'))
    await screen.findByText('Versión 2')
    fireEvent.click(screen.getByText('Restaurar'))
    await waitFor(() => expect(filesService.restoreVersion).toHaveBeenCalledWith('idA', 'A1'))
    await waitFor(() => expect(onSaved).toHaveBeenCalledOnce())
    expect(list).toHaveBeenCalledTimes(2)
  })
})
