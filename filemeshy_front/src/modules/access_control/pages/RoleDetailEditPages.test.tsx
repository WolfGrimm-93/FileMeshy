import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Routes, Route } from 'react-router-dom'

const roles = vi.hoisted(() => ({ getById: vi.fn(), canDeleteRole: vi.fn(), canModifyRole: vi.fn(() => true), delete: vi.fn() }))
const assign = vi.hoisted(() => ({ getForRole: vi.fn(), updateForRole: vi.fn() }))
vi.mock('../services/roles.service', () => ({ rolesService: roles }))
vi.mock('../services/permissions-assignment.service', async (orig) => ({
  ...(await orig<typeof import('../services/permissions-assignment.service')>()),
  permissionsAssignmentService: assign,
}))
let authRole = 'SUPER_ADMIN'
vi.mock('@/modules/auth/hooks/useAuth', () => ({ useAuth: () => ({ user: { role: authRole } }) }))
const toastMock = vi.hoisted(() => ({ error: vi.fn(), success: vi.fn() }))
vi.mock('sonner', () => ({ toast: toastMock }))
vi.mock('../components/RolePermissionsEditor', () => ({ default: () => <div>editor</div> }))

import RoleDetailPage from './RoleDetailPage'
import RoleEditPage from './RoleEditPage'

const catalog = [{ id: 'p1', permission_code: 'files.view', permission_name: 'Ver archivos', permission_category: 'files', resource: 'files', is_system: true, is_active: true }]
const role = { id: 'r1', name: 'AUDITOR', display_name: 'Auditor Pro', is_active: true, is_system: false, permissions: {}, users_count: 0 }

const renderAt = (path: string, el: React.ReactElement, routePath: string) =>
  render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path={routePath} element={el} />
        <Route path="/roles" element={<div>LISTA_ROLES</div>} />
      </Routes>
    </MemoryRouter>,
  )

beforeEach(() => {
  vi.clearAllMocks()
  authRole = 'SUPER_ADMIN'
  roles.getById.mockResolvedValue(role)
  roles.canDeleteRole.mockReturnValue(true)
  assign.getForRole.mockResolvedValue({ role_id: 'r1', role_name: 'AUDITOR', assigned_permission_ids: ['p1'], catalog })
  vi.spyOn(console, 'error').mockImplementation(() => {})
})

describe('RoleDetailPage', () => {
  it('muestra loading y luego el rol', async () => {
    renderAt('/roles/r1', <RoleDetailPage />, '/roles/:id')
    expect(screen.getByText('Cargando rol...')).toBeInTheDocument()
    expect((await screen.findAllByText('Auditor Pro')).length).toBeGreaterThan(0)
    expect(roles.getById).toHaveBeenCalledTimes(1)
  })

  it('un error navega a /roles', async () => {
    roles.getById.mockRejectedValue(new Error('boom'))
    renderAt('/roles/r1', <RoleDetailPage />, '/roles/:id')
    expect(await screen.findByText('LISTA_ROLES')).toBeInTheDocument()
    expect(toastMock.error).toHaveBeenCalled()
  })
})

describe('RoleDetailPage accesibilidad', () => {
  it('cada término (dt) queda asociado a su valor (dd)', async () => {
    renderAt('/roles/r1', <RoleDetailPage />, '/roles/:id')
    await screen.findAllByText('Auditor Pro')
    const pairs: [string, string][] = [['Nombre Interno', 'AUDITOR'], ['Nombre para Mostrar', 'Auditor Pro'], ['Descripción', 'Sin descripción']]
    for (const [term, value] of pairs) {
      const dt = screen.getByText(term)
      expect(dt.tagName).toBe('DT')
      expect(dt.nextElementSibling?.tagName).toBe('DD')
      expect(dt.nextElementSibling).toHaveTextContent(value)
    }
  })
})

describe('RoleEditPage', () => {
  it('carga el rol y rellena el formulario', async () => {
    renderAt('/roles/r1/editar', <RoleEditPage />, '/roles/:id/editar')
    expect(await screen.findByText(/Modifica la información del rol Auditor Pro/)).toBeInTheDocument()
    expect(screen.getByDisplayValue('Auditor Pro')).toBeInTheDocument()
  })

  it('un no-SUPER_ADMIN es enviado a /roles', async () => {
    authRole = 'ADMIN'
    renderAt('/roles/r1/editar', <RoleEditPage />, '/roles/:id/editar')
    expect(await screen.findByText('LISTA_ROLES')).toBeInTheDocument()
    await waitFor(() => expect(toastMock.error).toHaveBeenCalledWith('Solo SUPER_ADMIN puede modificar roles'))
  })

  it('un error de carga navega a /roles', async () => {
    roles.getById.mockRejectedValue(new Error('boom'))
    renderAt('/roles/r1/editar', <RoleEditPage />, '/roles/:id/editar')
    expect(await screen.findByText('LISTA_ROLES')).toBeInTheDocument()
  })
})
