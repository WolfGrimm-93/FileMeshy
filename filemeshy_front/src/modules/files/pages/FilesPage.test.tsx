import { render, screen, fireEvent, waitFor, act } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import FilesPage from './FilesPage'
import { filesService } from '../services/files.service'
import type { DirectoryListing } from '../types'

vi.mock('../services/files.service', () => ({
  filesService: { list: vi.fn(), getDownloadUrl: vi.fn() },
}))
vi.mock('../services/folders.service', () => ({ foldersService: {} }))
vi.mock('@/modules/auth/hooks/useAuth', () => ({
  useAuth: () => ({ hasPermission: () => true }),
}))
vi.mock('../hooks/useFileUpload', () => {
  const stable = {
    items: [], isUploading: false, uploadFiles: vi.fn(), resetItems: vi.fn(),
    retryItem: vi.fn(), abortItem: vi.fn(), dismissItem: vi.fn(),
  }
  return { useFileUpload: () => stable }
})
vi.mock('@/ui/toast/CustomToast', () => ({ toast: { error: vi.fn(), success: vi.fn() } }))

const listMock = vi.mocked(filesService.list)

function listing(fileName: string): DirectoryListing {
  return {
    breadcrumb: [],
    folders: [],
    files: [
      {
        id: `id-${fileName}`, name: fileName, folder_id: null, owner_id: 'u', size_bytes: 10,
        mime_type: 'text/plain', created_at: '2024-01-01T00:00:00Z', updated_at: '2024-01-01T00:00:00Z',
        deleted_at: null, is_favorite: false, tags: [],
      },
    ],
  } as DirectoryListing
}

function deferred<T>() {
  let resolve!: (v: T) => void
  const promise = new Promise<T>((r) => { resolve = r })
  return { promise, resolve }
}

function renderPage(initial = '/') {
  return render(<MemoryRouter initialEntries={[initial]}><FilesPage /></MemoryRouter>)
}

beforeEach(() => {
  localStorage.clear()
  listMock.mockReset()
})

describe('FilesPage carga del listado', () => {
  it('carga al montar mostrando el spinner inicial y luego los archivos', async () => {
    const d = deferred<DirectoryListing>()
    listMock.mockReturnValueOnce(d.promise)
    renderPage('/?folder=abc')
    expect(screen.getByText('Cargando archivos...')).toBeInTheDocument()
    expect(listMock).toHaveBeenCalledTimes(1)
    expect(listMock.mock.calls[0][0]).toMatchObject({ folderId: 'abc', trash: false, sortBy: 'name', sortDir: 'asc' })
    await act(async () => { d.resolve(listing('a.txt')) })
    expect(await screen.findByText('a.txt')).toBeInTheDocument()
  })

  it('cambiar el filtro de favoritos vuelve a listar con los args correctos y muestra loading', async () => {
    listMock.mockResolvedValueOnce(listing('a.txt'))
    const { container } = renderPage()
    await screen.findByText('a.txt')

    const d = deferred<DirectoryListing>()
    listMock.mockReturnValueOnce(d.promise)
    fireEvent.click(screen.getByText('Favoritos'))
    await waitFor(() => expect(listMock).toHaveBeenCalledTimes(2))
    expect(listMock.mock.calls[1][0]).toMatchObject({ favoritesOnly: true })
    expect(container.querySelector('.opacity-70')).toBeInTheDocument()
    expect(screen.getByText('a.txt')).toBeInTheDocument() // conserva los datos previos mientras carga

    await act(async () => { d.resolve(listing('b.txt')) })
    expect(await screen.findByText('b.txt')).toBeInTheDocument()
    expect(container.querySelector('.opacity-70')).not.toBeInTheDocument()
  })

  it('la búsqueda (debounce) llama list una vez con q y sin folderId', async () => {
    listMock.mockResolvedValue(listing('a.txt'))
    renderPage('/?folder=abc')
    await screen.findByText('a.txt')
    fireEvent.change(screen.getByPlaceholderText(/Buscar archivos/), { target: { value: ' foo ' } })
    await waitFor(() => expect(listMock).toHaveBeenCalledTimes(2))
    expect(listMock.mock.calls[1][0]).toMatchObject({ q: 'foo', folderId: undefined })
    await new Promise((r) => setTimeout(r, 400))
    expect(listMock).toHaveBeenCalledTimes(2)
  })

  it('la papelera lista con trash=true', async () => {
    listMock.mockResolvedValue(listing('a.txt'))
    renderPage()
    await screen.findByText('a.txt')
    fireEvent.click(screen.getByText('Papelera'))
    await waitFor(() => expect(listMock).toHaveBeenCalledTimes(2))
    expect(listMock.mock.calls[1][0]).toMatchObject({ trash: true })
  })

  it('un error de carga deja de mostrar el spinner inicial', async () => {
    listMock.mockRejectedValueOnce(new Error('boom'))
    renderPage()
    await waitFor(() => expect(screen.queryByText('Cargando archivos...')).not.toBeInTheDocument())
  })

  it('Copiar abre el modal en modo copiar preseleccionando la carpeta actual del archivo', async () => {
    const data = listing('a.txt')
    data.files[0].folder_id = 'carpeta-1'
    listMock.mockResolvedValue(data)
    renderPage('/?folder=carpeta-1')
    await screen.findByText('a.txt')
    listMock.mockClear()
    fireEvent.click(document.querySelector('button[aria-haspopup="true"]')!)
    fireEvent.click(await screen.findByText('Copiar'))
    expect(await screen.findByText('Copiar aquí')).toBeInTheDocument()
    await waitFor(() => expect(listMock).toHaveBeenCalledWith({ folderId: 'carpeta-1' }))
  })

  it('la columna de fecha usa parseo tolerante: "+00:00Z" se muestra y basura da "—" (nunca "Invalid Date")', async () => {
    const data = listing('a.txt')
    data.files[0].updated_at = '2026-09-25T11:30:49+00:00Z'
    data.files.push({ ...data.files[0], id: 'id-b', name: 'b.txt', updated_at: 'basura' })
    listMock.mockResolvedValue(data)
    const { container } = renderPage()
    await screen.findByText('a.txt')
    expect(container.textContent).toMatch(/2026/)
    expect(container.textContent).not.toContain('Invalid Date')
    expect(screen.getByText('—')).toBeInTheDocument()
  })
})
