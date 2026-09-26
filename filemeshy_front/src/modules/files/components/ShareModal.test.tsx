import { useState } from 'react'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import ShareModal, { type ShareTarget } from './ShareModal'
import { sharesService } from '../services/shares.service'
import type { ShareOut } from '../types'

vi.mock('../services/shares.service', () => ({
  sharesService: {
    listForFile: vi.fn(), listForFolder: vi.fn(), createForFile: vi.fn(), createForFolder: vi.fn(), revoke: vi.fn(),
  },
}))
vi.mock('@/modules/auth/hooks/useAuth', () => ({ useAuth: () => ({ hasPermission: () => true }) }))
vi.mock('@/ui/toast/CustomToast', () => ({ toast: { error: vi.fn(), success: vi.fn() } }))

const A: ShareTarget = { id: 'idA', name: 'a.txt', type: 'file' }
const B: ShareTarget = { id: 'idB', name: 'carpeta', type: 'folder' }
const svc = vi.mocked(sharesService)

const share = (token: string): ShareOut => ({
  id: `s-${token}`, token, file_id: null, folder_id: null, created_by_id: 'u', expires_at: null, revoked_at: null,
  created_at: '2024-01-01T00:00:00Z', is_active: true, permission: 'view', has_password: false,
  shared_with_user_id: null, shared_with_email: null,
} as unknown as ShareOut)

function Harness() {
  const [target, setTarget] = useState<ShareTarget | null>(null)
  return (
    <>
      <button onClick={() => setTarget(A)}>abrirA</button>
      <button onClick={() => setTarget(B)}>abrirB</button>
      <ShareModal target={target} onClose={() => setTarget(null)} />
    </>
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  svc.listForFile.mockResolvedValue([share('tokA')])
  svc.listForFolder.mockResolvedValue([share('tokB')])
})

describe('ShareModal', () => {
  it('una carga por apertura; reabrir con otro target resetea el formulario y la lista', async () => {
    render(<Harness />)
    fireEvent.click(screen.getByText('abrirA'))
    expect(await screen.findByText(/tokA/)).toBeInTheDocument()
    expect(svc.listForFile).toHaveBeenCalledTimes(1)
    expect(svc.listForFile).toHaveBeenCalledWith('idA')

    fireEvent.click(screen.getByText('Compartir con alguien'))
    fireEvent.change(screen.getByLabelText('Email de la persona'), { target: { value: 'x@y.com' } })
    fireEvent.click(screen.getByLabelText('Cerrar'))

    fireEvent.click(screen.getByText('abrirB'))
    expect(screen.queryByText(/tokA/)).not.toBeInTheDocument()
    expect(await screen.findByText(/tokB/)).toBeInTheDocument()
    expect(svc.listForFolder).toHaveBeenCalledTimes(1)
    expect(svc.listForFolder).toHaveBeenCalledWith('idB')
    expect(screen.getByText('Link público').closest('button')).toHaveAttribute('aria-pressed', 'true')
    expect(screen.queryByLabelText('Email de la persona')).not.toBeInTheDocument()
  })

  it('crear link llama al servicio con el id y recarga la lista', async () => {
    svc.createForFile.mockResolvedValueOnce(share('nuevo'))
    render(<Harness />)
    fireEvent.click(screen.getByText('abrirA'))
    await screen.findByText(/tokA/)
    fireEvent.click(screen.getByText('Crear link'))
    await waitFor(() => expect(svc.createForFile).toHaveBeenCalledWith('idA', { expiresAt: null }))
    await waitFor(() => expect(svc.listForFile).toHaveBeenCalledTimes(2))
  })

  it('compartir con alguien envía email y permiso', async () => {
    svc.createForFolder.mockResolvedValueOnce(share('u'))
    render(<Harness />)
    fireEvent.click(screen.getByText('abrirB'))
    await screen.findByText(/tokB/)
    fireEvent.click(screen.getByText('Compartir con alguien'))
    fireEvent.change(screen.getByLabelText('Email de la persona'), { target: { value: ' p@q.com ' } })
    fireEvent.click(screen.getByRole('button', { name: 'Compartir' }))
    await waitFor(() =>
      expect(svc.createForFolder).toHaveBeenCalledWith('idB', { expiresAt: null, sharedWithEmail: 'p@q.com', permission: 'view' }),
    )
  })

  it('los labels del formulario están asociados a su control (contraseña y sin expiración)', async () => {
    render(<Harness />)
    fireEvent.click(screen.getByText('abrirA'))
    await screen.findByText(/tokA/)
    const password = screen.getByLabelText('Contraseña (opcional)') as HTMLInputElement
    expect(password.type).toBe('password')
    expect(screen.getByLabelText('Sin expiración')).toBeChecked()
  })

  it('la expiración del share usa parseo tolerante ("+00:00Z" legible, basura "—")', async () => {
    svc.listForFile.mockResolvedValue([
      { ...share('tokA'), expires_at: '2999-09-25T11:30:49+00:00Z' },
      { ...share('tokB'), expires_at: 'basura' },
    ])
    const { baseElement } = render(<Harness />)
    fireEvent.click(screen.getByText('abrirA'))
    await screen.findByText(/tokA/)
    expect(baseElement.textContent).toMatch(/Expira: .*2999/)
    expect(baseElement.textContent).toContain('Expira: —')
    expect(baseElement.textContent).not.toContain('Invalid Date')
  })
})
