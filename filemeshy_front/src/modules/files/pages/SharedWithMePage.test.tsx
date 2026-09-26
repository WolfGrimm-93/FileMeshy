import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import SharedWithMePage from './SharedWithMePage'
import { sharesService } from '../services/shares.service'
import type { PublicShareResponse, SharedWithMeItem } from '../types'

vi.mock('../services/shares.service', () => ({
  sharesService: {
    listSharedWithMe: vi.fn(),
    getShared: vi.fn(),
    getSharedDownloadUrl: vi.fn(),
  },
}))
vi.mock('@/ui/toast/CustomToast', () => ({ toast: { error: vi.fn(), success: vi.fn() } }))

const svc = vi.mocked(sharesService)

function item(id: string, name: string, type: 'file' | 'folder'): SharedWithMeItem {
  return {
    share_id: id, resource_type: type, resource_name: name, permission: 'view',
    shared_by_email: 'a@b.c', created_at: '2024-01-01T00:00:00Z', expires_at: null,
  } as SharedWithMeItem
}

const folderContent = (name: string): PublicShareResponse =>
  ({ type: 'folder', name, folder_id: 'x', folders: [{ id: 'f1', name: 'Sub' }], files: [] }) as unknown as PublicShareResponse

beforeEach(() => {
  svc.listSharedWithMe.mockReset()
  svc.getShared.mockReset()
})
afterEach(() => vi.unstubAllGlobals())

describe('SharedWithMePage', () => {
  it('lista los shares al montar (una sola llamada)', async () => {
    svc.listSharedWithMe.mockResolvedValueOnce([item('s1', 'Docs', 'folder')])
    render(<SharedWithMePage />)
    expect(screen.getByText('Cargando...')).toBeInTheDocument()
    expect(await screen.findByText('Docs')).toBeInTheDocument()
    expect(svc.listSharedWithMe).toHaveBeenCalledTimes(1)
  })

  it('carpeta: navega a subcarpeta, al cerrar y abrir otra empieza en la raíz', async () => {
    svc.listSharedWithMe.mockResolvedValueOnce([item('s1', 'Docs', 'folder'), item('s2', 'Fotos', 'folder')])
    svc.getShared.mockResolvedValue(folderContent('x'))
    render(<SharedWithMePage />)
    await screen.findByText('Docs')

    fireEvent.click(screen.getAllByText('Ver')[0])
    await waitFor(() => expect(svc.getShared).toHaveBeenCalledWith('s1', undefined))
    fireEvent.doubleClick(await screen.findByText('Sub'))
    await waitFor(() => expect(svc.getShared).toHaveBeenLastCalledWith('s1', 'f1'))
    expect(await screen.findByText('Subcarpeta')).toBeInTheDocument()

    fireEvent.click(screen.getByLabelText('Cerrar'))
    expect(screen.queryByText('Subcarpeta')).not.toBeInTheDocument()

    svc.getShared.mockClear()
    fireEvent.click(screen.getAllByText('Ver')[1])
    await waitFor(() => expect(svc.getShared).toHaveBeenCalledTimes(1))
    expect(svc.getShared).toHaveBeenCalledWith('s2', undefined)
    expect(screen.queryByText('Subcarpeta')).not.toBeInTheDocument()
  })

  it('archivo: Descargar usa location.assign con la URL del share', async () => {
    const assign = vi.fn()
    vi.stubGlobal('location', { assign })
    svc.listSharedWithMe.mockResolvedValueOnce([item('s1', 'a.zip', 'file')])
    svc.getShared.mockResolvedValueOnce({
      type: 'file', name: 'a.zip', size_bytes: 1, mime_type: 'application/zip', download_url: 'http://x/dl',
    })
    render(<SharedWithMePage />)
    await screen.findByText('a.zip')
    fireEvent.click(screen.getByText('Descargar'))
    await waitFor(() => expect(assign).toHaveBeenCalledWith('http://x/dl'))
  })

  it('Expira usa parseo tolerante: "+00:00Z" se muestra y basura da "—"', async () => {
    svc.listSharedWithMe.mockResolvedValueOnce([
      { ...item('s1', 'a.zip', 'file'), expires_at: '2026-09-25T11:30:49+00:00Z' },
      { ...item('s2', 'b.zip', 'file'), expires_at: 'basura' },
    ])
    const { container } = render(<SharedWithMePage />)
    await screen.findByText('a.zip')
    expect(container.textContent).toMatch(/2026/)
    expect(container.textContent).not.toContain('Invalid Date')
    expect(screen.getByText('—')).toBeInTheDocument()
  })
})
