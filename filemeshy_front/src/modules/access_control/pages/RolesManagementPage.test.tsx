import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

const roles = vi.hoisted(() => ({ list: vi.fn(), canModifyRole: vi.fn(), canDeleteRole: vi.fn(), delete: vi.fn() }))
vi.mock('../services/roles.service', () => ({ rolesService: roles }))
vi.mock('@/modules/auth/hooks/useAuth', () => ({ useAuth: () => ({ user: { role: 'SUPER_ADMIN' } }) }))
vi.mock('sonner', () => ({ toast: { error: vi.fn(), success: vi.fn() } }))

import RolesManagementPage from './RolesManagementPage'

const renderPage = () => render(<MemoryRouter><RolesManagementPage /></MemoryRouter>)

beforeEach(() => {
  vi.clearAllMocks()
  vi.spyOn(console, 'error').mockImplementation(() => {})
})

describe('RolesManagementPage', () => {
  it('403 activa la pantalla de acceso denegado', async () => {
    roles.list.mockRejectedValue({ response: { status: 403 } })
    renderPage()
    expect(await screen.findByText('Acceso Denegado')).toBeInTheDocument()
  })

  it('carga los roles y los muestra', async () => {
    roles.list.mockResolvedValue({
      items: [{ id: 'r1', name: 'AUDITOR', display_name: 'Auditor Pro', is_active: true, is_system: false, created_at: '2026-01-01T00:00:00Z', permissions: {} }],
    })
    renderPage()
    expect(await screen.findByText('Auditor Pro')).toBeInTheDocument()
    expect(roles.list).toHaveBeenCalledWith({ skip: 0, limit: 100, include_system: true })
  })
})
