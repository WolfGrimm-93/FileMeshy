import { useState } from 'react'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import RenameModal, { type RenameTarget } from './RenameModal'
import { filesService } from '../services/files.service'
import { foldersService } from '../services/folders.service'

vi.mock('../services/files.service', () => ({ filesService: { rename: vi.fn() } }))
vi.mock('../services/folders.service', () => ({ foldersService: { rename: vi.fn() } }))
vi.mock('@/ui/toast/CustomToast', () => ({ toast: { error: vi.fn(), success: vi.fn() } }))

const A: RenameTarget = { id: 'idA', name: 'a.txt', type: 'file' }
const B: RenameTarget = { id: 'idB', name: 'carpeta', type: 'folder' }

function Harness({ onRenamed }: { onRenamed: () => void }) {
  const [target, setTarget] = useState<RenameTarget | null>(null)
  return (
    <>
      <button onClick={() => setTarget(A)}>abrirA</button>
      <button onClick={() => setTarget(B)}>abrirB</button>
      <RenameModal target={target} onClose={() => setTarget(null)} onRenamed={onRenamed} />
    </>
  )
}

const input = () => screen.getByLabelText('Nuevo nombre') as HTMLInputElement

beforeEach(() => vi.clearAllMocks())

describe('RenameModal', () => {
  it('abrir con A, editar, cerrar, abrir con B -> campo limpio con el nombre de B', () => {
    render(<Harness onRenamed={vi.fn()} />)
    fireEvent.click(screen.getByText('abrirA'))
    expect(input().value).toBe('a.txt')
    fireEvent.change(input(), { target: { value: 'editado' } })
    fireEvent.click(screen.getByText('Cancelar'))
    expect(screen.queryByLabelText('Nuevo nombre')).not.toBeInTheDocument()
    fireEvent.click(screen.getByText('abrirB'))
    expect(input().value).toBe('carpeta')
  })

  it('reabrir el mismo target descarta la edición previa', () => {
    render(<Harness onRenamed={vi.fn()} />)
    fireEvent.click(screen.getByText('abrirA'))
    fireEvent.change(input(), { target: { value: 'editado' } })
    fireEvent.click(screen.getByText('Cancelar'))
    fireEvent.click(screen.getByText('abrirA'))
    expect(input().value).toBe('a.txt')
  })

  it('guardar archivo llama filesService.rename con id y nombre recortado', async () => {
    const onRenamed = vi.fn()
    vi.mocked(filesService.rename).mockResolvedValueOnce(undefined as never)
    render(<Harness onRenamed={onRenamed} />)
    fireEvent.click(screen.getByText('abrirA'))
    fireEvent.change(input(), { target: { value: '  nuevo.txt ' } })
    fireEvent.click(screen.getByText('Guardar'))
    await waitFor(() => expect(filesService.rename).toHaveBeenCalledWith('idA', 'nuevo.txt'))
    await waitFor(() => expect(onRenamed).toHaveBeenCalledWith(A, 'nuevo.txt'))
    expect(screen.queryByLabelText('Nuevo nombre')).not.toBeInTheDocument()
  })

  it('guardar carpeta llama foldersService.rename', async () => {
    vi.mocked(foldersService.rename).mockResolvedValueOnce(undefined as never)
    render(<Harness onRenamed={vi.fn()} />)
    fireEvent.click(screen.getByText('abrirB'))
    fireEvent.change(input(), { target: { value: 'otra' } })
    fireEvent.click(screen.getByText('Guardar'))
    await waitFor(() => expect(foldersService.rename).toHaveBeenCalledWith('idB', 'otra'))
  })
})
