import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Routes, Route } from 'react-router-dom'

const svc = vi.hoisted(() => ({
  getUserSessions: vi.fn(),
  overrides: vi.fn(),
  updateOverrides: vi.fn(),
  fetchUser: vi.fn(),
}))
vi.mock('@/modules/users/services/user.service', () => ({
  userService: { getUserSessions: svc.getUserSessions, revokeUserSession: vi.fn(), revokeAllUserSessions: vi.fn(), uploadAvatar: vi.fn() },
}))
vi.mock('@/modules/access_control/services/roles.service', () => ({
  rolesService: { getSummary: vi.fn().mockResolvedValue([]) },
}))
vi.mock('@/modules/access_control/services/user-permission-overrides.service', () => ({
  userPermissionOverridesService: { getForUser: svc.overrides, updateForUser: svc.updateOverrides },
}))
vi.mock('@/modules/access_control/hooks/useAvailablePermissions', () => ({
  useAvailablePermissions: () => ({
    available: { files: ['view', 'edit'] },
    resource_labels: { files: 'Archivos' },
    action_labels: { view: 'Ver', edit: 'Editar' },
  }),
}))
const store = { fetchUser: svc.fetchUser, deleteUser: vi.fn(), updateUser: vi.fn() }
vi.mock('@/modules/users/store/userStore', () => ({ useUserStore: () => store }))
vi.mock('@/modules/auth/hooks/useAuth', () => ({ useAuth: () => ({ user: { id: 'admin', role: 'SUPER_ADMIN' }, logout: vi.fn() }) }))
const toastMock = vi.hoisted(() => ({ error: vi.fn(), success: vi.fn() }))
vi.mock('@/ui/toast/CustomToast', () => ({ toast: toastMock }))

import UserDetailPage from './UserDetailPage'

const target = {
  id: 'u9', first_name: 'Luis', last_name: 'Gómez', email: 'l@x.com', role: 'USER', role_id: 'r-user',
  is_active: true, permissions: ['files.view'], created_at: '2026-01-01T00:00:00Z', phone: null,
}
const catalog = [
  { id: 'p-view', permission_code: 'files.view' },
  { id: 'p-edit', permission_code: 'files.edit' },
]
const sessionRow = (over = {}) => ({
  id: 's1', user_id: 'u9', ip_address: '9.9.9.9', user_agent: 'Mozilla/5.0 (X11; Linux) Chrome/120',
  created_at: '2026-01-01T00:00:00Z', last_activity: '2026-01-01T00:00:00Z', expires_at: '2999-01-01T00:00:00Z', is_active: true, ...over,
})

const renderAt = (tab: string) =>
  render(
    <MemoryRouter initialEntries={[`/usuarios/u9?tab=${tab}`]}>
      <Routes><Route path="/usuarios/:id" element={<UserDetailPage />} /></Routes>
    </MemoryRouter>,
  )

beforeEach(() => {
  vi.clearAllMocks()
  svc.fetchUser.mockResolvedValue(target)
  svc.overrides.mockResolvedValue({ catalog, role_permission_ids: ['p-view'] })
  svc.updateOverrides.mockResolvedValue({})
  svc.getUserSessions.mockResolvedValue({ items: [sessionRow()] })
})

describe('UserDetailPage sesiones', () => {
  it('abrir la pestaña Sesiones muestra loading y luego la lista', async () => {
    let resolve!: (v: unknown) => void
    svc.getUserSessions.mockReturnValue(new Promise((r) => { resolve = r }))
    renderAt('sessions')
    await screen.findByText('Sesiones Activas (0)')
    expect(document.querySelector('.animate-spin')).not.toBeNull()
    resolve({ items: [sessionRow()] })
    expect(await screen.findByText('IP: 9.9.9.9')).toBeInTheDocument()
    expect(document.querySelector('.animate-spin')).toBeNull()
  })

  it('usa device_name del backend si existe y cae al parseo local si no', async () => {
    svc.getUserSessions.mockResolvedValue({
      items: [
        sessionRow({ id: 'a', device_name: 'Firefox en Ubuntu', ip_address: '1.1.1.1' }),
        sessionRow({ id: 'b', ip_address: '2.2.2.2' }),
      ],
    })
    renderAt('sessions')
    expect(await screen.findByText('Firefox en Ubuntu')).toBeInTheDocument()
    expect(screen.getByText('Chrome en Linux')).toBeInTheDocument()
  })
})

describe('UserDetailPage sesiones con fecha inválida', () => {
  it('una expires_at que no parsea se muestra como cerrada, sin romper', async () => {
    svc.getUserSessions.mockResolvedValue({ items: [sessionRow({ expires_at: 'basura' })] })
    renderAt('sessions')
    expect(await screen.findByText('Cerrada')).toBeInTheDocument()
    expect(screen.queryByText('Activa')).toBeNull()
  })
})

describe('UserDetailPage sesiones (reingreso a la pestaña)', () => {
  it('al salir y volver a Sesiones muestra loading y luego los datos nuevos, no los viejos', async () => {
    const user = userEvent.setup()
    svc.getUserSessions.mockResolvedValueOnce({ items: [sessionRow({ ip_address: '1.1.1.1' })] })
    renderAt('sessions')
    expect(await screen.findByText('IP: 1.1.1.1')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: /Información/ }))
    let resolve!: (v: unknown) => void
    svc.getUserSessions.mockReturnValueOnce(new Promise((r) => { resolve = r }))
    await user.click(screen.getByRole('button', { name: /Sesiones/ }))
    expect(document.querySelector('.animate-spin')).not.toBeNull()
    expect(screen.queryByText('IP: 1.1.1.1')).toBeNull()
    resolve({ items: [sessionRow({ ip_address: '2.2.2.2' })] })
    expect(await screen.findByText('IP: 2.2.2.2')).toBeInTheDocument()
  })
})

describe('UserDetailPage permisos', () => {
  it('"Editar permisos" queda deshabilitado hasta que carguen los overrides y luego guarda los ids correctos', async () => {
    let resolve!: (v: unknown) => void
    svc.overrides.mockReturnValue(new Promise((r) => { resolve = r }))
    const user = userEvent.setup()
    renderAt('rol')
    const editBtn = await screen.findByRole('button', { name: /Editar permisos/ })
    expect(editBtn).toBeDisabled()
    resolve({ catalog, role_permission_ids: ['p-view'] })
    await waitFor(() => expect(editBtn).toBeEnabled())
    await user.click(editBtn)
    await user.click(screen.getAllByRole('checkbox')[2]) // acción 'edit' (0 = grupo, 1 = view)
    await user.click(screen.getByRole('button', { name: /Guardar/ }))
    await waitFor(() => expect(svc.updateOverrides).toHaveBeenCalledWith('u9', ['p-edit'], []))
  })
})
