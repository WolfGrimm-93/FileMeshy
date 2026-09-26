import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'

const roles = vi.hoisted(() => ({
  create: vi.fn(),
  list: vi.fn(),
  validateRoleName: (name: string) =>
    /^[A-Z_]+$/.test(name) && name.length >= 3
      ? { valid: true }
      : { valid: false, error: 'Nombre inválido' },
}))
const assign = vi.hoisted(() => ({ getForRole: vi.fn(), updateForRole: vi.fn() }))
vi.mock('../services/roles.service', () => ({ rolesService: roles }))
vi.mock('../services/permissions-assignment.service', async (orig) => ({
  ...(await orig<typeof import('../services/permissions-assignment.service')>()),
  permissionsAssignmentService: assign,
}))
vi.mock('@/modules/auth/hooks/useAuth', () => ({ useAuth: () => ({ user: { role: 'SUPER_ADMIN' } }) }))
const toastMock = vi.hoisted(() => ({ error: vi.fn(), success: vi.fn(), warning: vi.fn() }))
vi.mock('sonner', () => ({ toast: toastMock }))
const navigateMock = vi.fn()
vi.mock('react-router-dom', async (orig) => ({
  ...(await orig<typeof import('react-router-dom')>()),
  useNavigate: () => navigateMock,
}))
// Editor sustituido por un stub: aquí se prueba la página, no el checklist
vi.mock('../components/RolePermissionsEditor', () => ({
  default: ({ onChange }: { onChange: (p: Record<string, string[]>) => void }) => (
    <button type="button" onClick={() => onChange({ files: ['view'], ghost: ['x'] })}>
      elegir-permisos
    </button>
  ),
}))

import RoleCreatePage from './RoleCreatePage'

const catalog = [
  { id: 'id-files-view', permission_code: 'files.view' },
  { id: 'id-users-view', permission_code: 'users.view' },
]

const renderPage = () => render(<MemoryRouter><RoleCreatePage /></MemoryRouter>)

beforeEach(() => {
  vi.clearAllMocks()
  roles.create.mockResolvedValue({ id: 'new-1' })
  roles.list.mockResolvedValue({ items: [{ id: 'some-role' }] })
  assign.getForRole.mockResolvedValue({ catalog })
})

describe('RoleCreatePage validación del nombre', () => {
  it('nombre inválido muestra error y deshabilita "Crear Rol"', async () => {
    const user = userEvent.setup()
    renderPage()
    const submit = screen.getByRole('button', { name: /Crear Rol/i })
    expect(submit).toBeEnabled()
    await user.type(screen.getByPlaceholderText('AUDITOR'), '12')
    expect(screen.getByText('Nombre inválido')).toBeInTheDocument()
    expect(submit).toBeDisabled()
    await user.clear(screen.getByPlaceholderText('AUDITOR'))
    expect(screen.queryByText('Nombre inválido')).toBeNull()
    expect(submit).toBeEnabled()
  })
})

describe('RoleCreatePage alta atómica', () => {
  async function fillAndSubmit(pick: boolean) {
    const user = userEvent.setup()
    renderPage()
    await user.type(screen.getByPlaceholderText('AUDITOR'), 'auditor')
    await user.type(screen.getByPlaceholderText('Vendedor'), 'Auditor')
    if (pick) await user.click(screen.getByText('elegir-permisos'))
    await user.click(screen.getByRole('button', { name: /Crear Rol/i }))
  }

  it('un solo POST con permission_ids y sin PUT posterior', async () => {
    roles.list.mockResolvedValue({ items: [{ id: 'some-role' }] })
    assign.getForRole.mockResolvedValue({ catalog: [...catalog, { id: 'id-ghost-x', permission_code: 'ghost.x' }] })
    await fillAndSubmit(true)
    await waitFor(() => expect(roles.create).toHaveBeenCalledTimes(1))
    expect(roles.create).toHaveBeenCalledWith(
      expect.objectContaining({ name: 'AUDITOR', permission_ids: ['id-files-view', 'id-ghost-x'] }),
    )
    expect(assign.updateForRole).not.toHaveBeenCalled()
    expect(navigateMock).toHaveBeenCalledWith('/roles/new-1')
  })

  it('catálogo sin un código seleccionado: aviso y no se crea el rol', async () => {
    await fillAndSubmit(true) // catalog no incluye ghost.x
    await waitFor(() => expect(toastMock.error).toHaveBeenCalled())
    expect(toastMock.error.mock.calls[0][0]).toContain('ghost.x')
    expect(roles.create).not.toHaveBeenCalled()
  })

  it('sin permisos elegidos crea el rol sin consultar el catálogo', async () => {
    await fillAndSubmit(false)
    await waitFor(() => expect(roles.create).toHaveBeenCalledTimes(1))
    expect(assign.getForRole).not.toHaveBeenCalled()
  })

  it.each([
    ['409 con detail', { response: { status: 409, data: { detail: 'El rol AUDITOR ya existe' } } }, 'El rol AUDITOR ya existe'],
    ['409 sin detail', { response: { status: 409, data: {} }, message: 'Request failed with status code 409' }, 'Ya existe un rol con ese nombre'],
    ['422 con detail string', { response: { status: 422, data: { detail: 'Permisos inactivos: files.view' } } }, 'Permisos inactivos: files.view'],
    ['422 con detail array', { response: { status: 422, data: { detail: [{ msg: 'permission_ids: demasiados' }] } } }, 'permission_ids: demasiados'],
  ])('%s muestra un mensaje útil, no el genérico de axios', async (_n, err, expected) => {
    roles.create.mockRejectedValue(err)
    await fillAndSubmit(false)
    await waitFor(() => expect(toastMock.error).toHaveBeenCalledWith(expected))
  })

  it('trunca un detail muy largo', async () => {
    roles.create.mockRejectedValue({ response: { status: 422, data: { detail: 'x'.repeat(500) } } })
    await fillAndSubmit(false)
    await waitFor(() => expect(toastMock.error).toHaveBeenCalled())
    expect((toastMock.error.mock.calls[0][0] as string).length).toBeLessThanOrEqual(201)
  })
})

describe('RoleCreatePage descripción', () => {
  it('la descripción tiene 4 filas y su label está asociado', () => {
    renderPage()
    expect(screen.getByLabelText('Descripción')).toHaveAttribute('rows', '4')
  })
})
