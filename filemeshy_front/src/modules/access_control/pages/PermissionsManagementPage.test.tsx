import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, act } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'

const roles = vi.hoisted(() => ({ list: vi.fn() }))
const assign = vi.hoisted(() => ({ getForRole: vi.fn(), updateForRole: vi.fn() }))
vi.mock('../services/roles.service', () => ({ rolesService: roles }))
vi.mock('../services/permissions-assignment.service', async (orig) => ({
  ...(await orig<typeof import('../services/permissions-assignment.service')>()),
  permissionsAssignmentService: assign,
}))
vi.mock('@/modules/auth/hooks/useAuth', () => ({ useAuth: () => ({ user: { role: 'SUPER_ADMIN' } }) }))
const toastMock = vi.hoisted(() => ({ error: vi.fn(), success: vi.fn() }))
vi.mock('sonner', () => ({ toast: toastMock }))
vi.mock('../components/RolePermissionsEditor', () => ({
  default: ({ permissions, onChange }: { permissions: Record<string, string[]>; onChange: (p: Record<string, string[]>) => void }) => (
    <div>
      <span data-testid="perms">{JSON.stringify(permissions)}</span>
      <button type="button" onClick={() => onChange({ ...permissions, users: ['view'] })}>agregar-users</button>
    </div>
  ),
}))

import PermissionsManagementPage from './PermissionsManagementPage'

const catalog = [
  { id: 'p-files', permission_code: 'files.view' },
  { id: 'p-users', permission_code: 'users.view' },
]

beforeEach(() => {
  vi.clearAllMocks()
  roles.list.mockResolvedValue({
    items: [
      { id: 'r1', display_name: 'Rol Uno', is_system: false },
      { id: 'r2', display_name: 'Rol Dos', is_system: false },
    ],
  })
  assign.getForRole.mockImplementation(async (id: string) => ({
    catalog,
    assigned_permission_ids: id === 'r1' ? ['p-files'] : [],
  }))
  assign.updateForRole.mockResolvedValue({})
})

describe('PermissionsManagementPage', () => {
  it('selecciona el primer rol, carga catálogo/asignados y al cambiar de rol recarga', async () => {
    const user = userEvent.setup()
    render(<MemoryRouter><PermissionsManagementPage /></MemoryRouter>)
    await waitFor(() => expect(screen.getByTestId('perms')).toHaveTextContent('{"files":["view"]}'))
    expect(assign.getForRole).toHaveBeenCalledWith('r1')
    await user.click(screen.getByRole('button', { name: /Rol Dos/ }))
    await waitFor(() => expect(screen.getByTestId('perms')).toHaveTextContent('{}'))
    expect(assign.getForRole).toHaveBeenCalledWith('r2')
  })

  it('guardar manda los ids correctos', async () => {
    const user = userEvent.setup()
    render(<MemoryRouter><PermissionsManagementPage /></MemoryRouter>)
    await screen.findByText('agregar-users')
    await user.click(screen.getByText('agregar-users'))
    await user.click(screen.getByRole('button', { name: /Guardar cambios/ }))
    await waitFor(() => expect(assign.updateForRole).toHaveBeenCalledWith('r1', ['p-files', 'p-users']))
    expect(toastMock.success).toHaveBeenCalled()
  })

  it('si falla la carga de otro rol no muestra los permisos del anterior ni permite guardar; volver al anterior funciona', async () => {
    const user = userEvent.setup()
    assign.getForRole.mockImplementation(async (id: string) => {
      if (id === 'r2') throw new Error('falla')
      return { catalog, assigned_permission_ids: ['p-files'] }
    })
    render(<MemoryRouter><PermissionsManagementPage /></MemoryRouter>)
    await waitFor(() => expect(screen.getByTestId('perms')).toHaveTextContent('{"files":["view"]}'))
    await user.click(screen.getByRole('button', { name: /Rol Dos/ }))
    await waitFor(() => expect(toastMock.error).toHaveBeenCalled())
    expect(screen.queryByTestId('perms')).toBeNull()
    expect(screen.queryByRole('button', { name: /Guardar cambios/ })).toBeNull()
    expect(assign.updateForRole).not.toHaveBeenCalled()
    await user.click(screen.getByRole('button', { name: /Rol Uno/ }))
    await waitFor(() => expect(screen.getByTestId('perms')).toHaveTextContent('{"files":["view"]}'))
    expect(screen.getByRole('button', { name: /Guardar cambios/ })).toBeEnabled()
  })

  it('A cargado, elegir B (pendiente) y volver a A: spinner (no editor viejo) y una respuesta tardía de B se descarta', async () => {
    const user = userEvent.setup()
    let resolveB!: (v: unknown) => void
    let resolveA2!: (v: unknown) => void
    let calls = 0
    assign.getForRole.mockImplementation((id: string) => {
      if (id === 'r2') return new Promise((r) => { resolveB = r })
      calls++
      if (calls === 1) return Promise.resolve({ catalog, assigned_permission_ids: ['p-files'] })
      return new Promise((r) => { resolveA2 = r }) // recarga de A, controlada
    })
    render(<MemoryRouter><PermissionsManagementPage /></MemoryRouter>)
    await waitFor(() => expect(screen.getByTestId('perms')).toHaveTextContent('{"files":["view"]}'))
    await user.click(screen.getByRole('button', { name: /Rol Dos/ }))
    await user.click(screen.getByRole('button', { name: /Rol Uno/ }))
    // Mientras se recarga A no debe verse el editor con datos previos
    expect(screen.queryByTestId('perms')).toBeNull()
    expect(screen.queryByRole('button', { name: /Guardar cambios/ })).toBeNull()
    await act(async () => { resolveA2({ catalog, assigned_permission_ids: ['p-users'] }) })
    await waitFor(() => expect(screen.getByTestId('perms')).toHaveTextContent('{"users":["view"]}'))
    // B resuelve tarde: no cambia el editor de A
    await act(async () => { resolveB({ catalog, assigned_permission_ids: ['p-files', 'p-users'] }) })
    expect(screen.getByTestId('perms')).toHaveTextContent('{"users":["view"]}')
    await user.click(screen.getByRole('button', { name: /Guardar cambios/ }))
    await waitFor(() => expect(assign.updateForRole).toHaveBeenCalledWith('r1', ['p-users']))
  })
})
