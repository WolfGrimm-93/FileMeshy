import { useState } from 'react'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import TagsModal, { type TagsTarget } from './TagsModal'
import { tagsService } from '../services/tags.service'
import { filesService } from '../services/files.service'
import { foldersService } from '../services/folders.service'

vi.mock('../services/tags.service', () => ({ tagsService: { list: vi.fn(), create: vi.fn(), remove: vi.fn() } }))
vi.mock('../services/files.service', () => ({ filesService: { setTags: vi.fn() } }))
vi.mock('../services/folders.service', () => ({ foldersService: { setTags: vi.fn() } }))
vi.mock('@/ui/toast/CustomToast', () => ({ toast: { error: vi.fn(), success: vi.fn() } }))

const A: TagsTarget = { id: 'idA', type: 'file', currentTagIds: ['t1'] }
const B: TagsTarget = { id: 'idB', type: 'folder', currentTagIds: [] }
const tags = [
  { id: 't1', name: 'Urgente', color: '#ef4444' },
  { id: 't2', name: 'Personal', color: '#22c55e' },
]

function Harness({ onSaved }: { onSaved: () => void }) {
  const [target, setTarget] = useState<TagsTarget | null>(null)
  return (
    <>
      <button onClick={() => setTarget(A)}>abrirA</button>
      <button onClick={() => setTarget(B)}>abrirB</button>
      <TagsModal target={target} onClose={() => setTarget(null)} onSaved={onSaved} />
    </>
  )
}

// Un tag está seleccionado cuando su botón lleva la clase ring-2
const isSelected = (name: string) => screen.getByText(name).closest('button')!.className.includes('ring-2')

beforeEach(() => {
  vi.clearAllMocks()
  vi.mocked(tagsService.list).mockResolvedValue(tags as never)
})

describe('TagsModal', () => {
  it('una carga por apertura; la selección se sincroniza con el target y se limpia al reabrir', async () => {
    render(<Harness onSaved={vi.fn()} />)
    fireEvent.click(screen.getByText('abrirA'))
    expect(screen.getByText('Cargando etiquetas...')).toBeInTheDocument()
    await screen.findByText('Urgente')
    expect(tagsService.list).toHaveBeenCalledTimes(1)
    expect(isSelected('Urgente')).toBe(true)
    expect(isSelected('Personal')).toBe(false)

    fireEvent.click(screen.getByText('Personal')) // edita la selección
    fireEvent.change(screen.getByPlaceholderText('Nombre de la etiqueta'), { target: { value: 'borrador' } })
    fireEvent.click(screen.getByText('Cancelar'))

    fireEvent.click(screen.getByText('abrirB'))
    expect(screen.getByText('Cargando etiquetas...')).toBeInTheDocument() // sin flash de datos viejos
    await screen.findByText('Urgente')
    expect(tagsService.list).toHaveBeenCalledTimes(2)
    expect(isSelected('Urgente')).toBe(false)
    expect(isSelected('Personal')).toBe(false)
    expect((screen.getByPlaceholderText('Nombre de la etiqueta') as HTMLInputElement).value).toBe('')
  })

  it('guardar en archivo llama filesService.setTags con id y selección', async () => {
    const onSaved = vi.fn()
    vi.mocked(filesService.setTags).mockResolvedValueOnce(undefined as never)
    render(<Harness onSaved={onSaved} />)
    fireEvent.click(screen.getByText('abrirA'))
    await screen.findByText('Personal')
    fireEvent.click(screen.getByText('Personal'))
    fireEvent.click(screen.getByText('Guardar'))
    await waitFor(() => expect(filesService.setTags).toHaveBeenCalledWith('idA', ['t1', 't2']))
    expect(onSaved).toHaveBeenCalledOnce()
    expect(foldersService.setTags).not.toHaveBeenCalled()
  })

  it('guardar en carpeta llama foldersService.setTags', async () => {
    vi.mocked(foldersService.setTags).mockResolvedValueOnce(undefined as never)
    render(<Harness onSaved={vi.fn()} />)
    fireEvent.click(screen.getByText('abrirB'))
    await screen.findByText('Personal')
    fireEvent.click(screen.getByText('Guardar'))
    await waitFor(() => expect(foldersService.setTags).toHaveBeenCalledWith('idB', []))
  })

  it('crear etiqueta la agrega y la selecciona', async () => {
    vi.mocked(tagsService.create).mockResolvedValueOnce({ id: 't3', name: 'Nueva', color: '#ef4444' } as never)
    render(<Harness onSaved={vi.fn()} />)
    fireEvent.click(screen.getByText('abrirB'))
    await screen.findByText('Personal')
    fireEvent.change(screen.getByPlaceholderText('Nombre de la etiqueta'), { target: { value: ' Nueva ' } })
    fireEvent.click(screen.getByText('Crear'))
    await waitFor(() => expect(tagsService.create).toHaveBeenCalledWith('Nueva', '#ef4444'))
    expect(await screen.findByText('Nueva')).toBeInTheDocument()
    expect(isSelected('Nueva')).toBe(true)
  })
})
