import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { AxiosError } from 'axios'
import PublicSharePage from './PublicSharePage'
import { sharesService } from '../services/shares.service'
import type { PublicShareResponse } from '../types'

vi.mock('../services/shares.service', () => ({
  sharesService: { getPublicShare: vi.fn(), getPublicDownloadUrl: vi.fn() },
}))
vi.mock('../components/PreviewModal', () => ({ default: () => null }))
vi.mock('@/ui/toast/CustomToast', () => ({ toast: { error: vi.fn(), success: vi.fn() } }))

const getShare = vi.mocked(sharesService.getPublicShare)

function unauthorized() {
  return new AxiosError('401', 'ERR', undefined, undefined, { status: 401 } as never)
}

const folderShare = {
  type: 'folder', name: 'Compartida', folder_id: 'root',
  folders: [{ id: 'f1', name: 'Sub' }], files: [],
} as unknown as PublicShareResponse

const fileShare: PublicShareResponse = {
  type: 'file', name: 'doc.zip', size_bytes: 10, mime_type: 'application/zip', download_url: 'http://x/preview',
}

function renderPage() {
  return render(
    <MemoryRouter initialEntries={['/compartido/tok']}>
      <Routes><Route path="/compartido/:token" element={<PublicSharePage />} /></Routes>
    </MemoryRouter>,
  )
}

beforeEach(() => getShare.mockReset())
afterEach(() => vi.unstubAllGlobals())

describe('PublicSharePage', () => {
  it('muestra "Cargando..." y luego el contenido en éxito', async () => {
    getShare.mockResolvedValueOnce(folderShare)
    renderPage()
    expect(screen.getByText('Cargando...')).toBeInTheDocument()
    expect(await screen.findByText('Compartida')).toBeInTheDocument()
    expect(getShare).toHaveBeenCalledWith('tok', undefined, { password: undefined })
  })

  it('401 lleva a la pantalla de contraseña y el éxito con contraseña reintenta y luego la reusa al navegar', async () => {
    getShare.mockRejectedValueOnce(unauthorized())
    renderPage()
    expect(await screen.findByText('Enlace protegido')).toBeInTheDocument()

    getShare.mockResolvedValueOnce(folderShare)
    fireEvent.change(screen.getByPlaceholderText('Contraseña'), { target: { value: 'secreto' } })
    fireEvent.click(screen.getByText('Acceder'))
    expect(await screen.findByText('Compartida')).toBeInTheDocument()
    expect(getShare).toHaveBeenLastCalledWith('tok', undefined, { password: 'secreto' })

    // Navegar a una subcarpeta reusa la contraseña verificada (ref)
    getShare.mockResolvedValueOnce(folderShare)
    fireEvent.doubleClick(screen.getByText('Sub'))
    await waitFor(() => expect(getShare).toHaveBeenCalledTimes(3))
    expect(getShare).toHaveBeenLastCalledWith('tok', 'f1', { password: 'secreto' })
    expect(await screen.findByText('Compartida')).toBeInTheDocument()
  })

  it('contraseña incorrecta muestra el error en el formulario', async () => {
    getShare.mockRejectedValueOnce(unauthorized())
    renderPage()
    await screen.findByText('Enlace protegido')
    getShare.mockRejectedValueOnce(unauthorized())
    fireEvent.change(screen.getByPlaceholderText('Contraseña'), { target: { value: 'mal' } })
    fireEvent.click(screen.getByText('Acceder'))
    expect(await screen.findByText('Contraseña incorrecta')).toBeInTheDocument()
  })

  it('otro error lleva a "Enlace no disponible"', async () => {
    getShare.mockRejectedValueOnce(new Error('404'))
    renderPage()
    expect(await screen.findByText('Enlace no disponible')).toBeInTheDocument()
  })

  it('Descargar pide una URL forzada y navega con location.assign', async () => {
    const assign = vi.fn()
    vi.stubGlobal('location', { assign })
    getShare.mockResolvedValueOnce(fileShare)
    renderPage()
    await screen.findByText('doc.zip')
    getShare.mockResolvedValueOnce({ ...fileShare, download_url: 'http://x/forced' } as PublicShareResponse)
    fireEvent.click(screen.getByText('Descargar'))
    await waitFor(() => expect(assign).toHaveBeenCalledWith('http://x/forced'))
    expect(getShare).toHaveBeenLastCalledWith('tok', undefined, { forceDownload: true, password: undefined })
  })
})
