import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

const auth = vi.hoisted(() => ({
  getSecurityPolicies: vi.fn(),
  get2FAStatus: vi.fn(),
  changePassword: vi.fn(),
}))
const users = vi.hoisted(() => ({ getUserSessions: vi.fn(), revokeUserSession: vi.fn(), revokeAllUserSessions: vi.fn() }))
vi.mock('@/modules/auth/services/auth.service', () => ({ authService: auth }))
vi.mock('@/modules/users/services/user.service', () => ({ userService: users }))
// Usuario estable entre renders (como en el store real)
let currentUser = { id: 'u1' }
vi.mock('@/modules/auth/hooks/useAuth', () => ({ useAuth: () => ({ user: currentUser }) }))
const toastMock = vi.hoisted(() => ({ error: vi.fn(), success: vi.fn() }))
vi.mock('@/ui/toast/CustomToast', () => ({ toast: toastMock }))

import SeguridadComponent from './SeguridadComponent'

const basePolicies = {
  min_password_length: 8, require_uppercase: true, require_lowercase: true,
  require_numbers: true, require_special_chars: false,
}
const session = { id: 's1', device_name: 'Chrome en Linux', device_type: 'desktop', ip_address: '1.2.3.4', last_activity: '2026-01-01T00:00:00Z' }

beforeEach(() => {
  vi.clearAllMocks()
  currentUser = { id: 'u1' }
  vi.spyOn(console, 'error').mockImplementation(() => {})
  auth.getSecurityPolicies.mockResolvedValue(basePolicies)
  auth.get2FAStatus.mockResolvedValue({ enabled: true, backup_codes_remaining: 3 })
  users.getUserSessions.mockResolvedValue({ items: [session] })
})

async function typeNew(pw: string) {
  const user = userEvent.setup()
  render(<SeguridadComponent />)
  const input = await screen.findByPlaceholderText('Ingresa tu nueva contraseña')
  if (pw) await user.type(input, pw)
  return user
}

describe('SeguridadComponent fortaleza de contraseña', () => {
  const cases: [string, string, number][] = [
    ['abc', 'Falta: Mínimo 8 caracteres, Una mayúscula, Un número', 0],
    ['abcdefgh1', 'Falta: Una mayúscula', 40],
    ['Abcdefg1', 'Contraseña aceptable', 70],
    ['Abcdefghijk1', '✓ Contraseña fuerte', 80],
  ]
  it.each(cases)('"%s" -> %s', async (pw, message, strength) => {
    await typeNew(pw)
    expect(screen.getByText(message)).toBeInTheDocument()
    const bar = document.querySelector('[style*="width"]') as HTMLElement
    expect(bar.style.width).toBe(`${strength}%`)
  })

  it('respeta las políticas del backend (carácter especial obligatorio)', async () => {
    auth.getSecurityPolicies.mockResolvedValue({ ...basePolicies, require_special_chars: true })
    await typeNew('Abcdefg1')
    expect(screen.getByText('Falta: Un carácter especial')).toBeInTheDocument()
  })

  it('con fortaleza suficiente cambia la contraseña y con débil no', async () => {
    const user = await typeNew('abc')
    await user.type(screen.getByPlaceholderText('Ingresa tu contraseña actual'), 'vieja')
    await user.type(screen.getByPlaceholderText('Confirma tu nueva contraseña'), 'abc')
    expect(screen.getByRole('button', { name: /Cambiar Contraseña|Actualizar/i })).toBeDisabled()
  })
})

describe('SeguridadComponent carga', () => {
  it('Promise.allSettled: si falla una promesa igual muestra el resto', async () => {
    users.getUserSessions.mockRejectedValue(new Error('sin sesiones'))
    render(<SeguridadComponent />)
    expect(await screen.findByText('Activo')).toBeInTheDocument()
    expect(screen.getByText('No hay sesiones activas')).toBeInTheDocument()
  })

  it('muestra las sesiones con device_name', async () => {
    render(<SeguridadComponent />)
    expect(await screen.findByText('Chrome en Linux')).toBeInTheDocument()
    await waitFor(() => expect(users.getUserSessions).toHaveBeenCalledWith('u1'))
    expect(users.getUserSessions).toHaveBeenCalledTimes(1)
  })
})

describe('SeguridadComponent cambio de usuario', () => {
  it('al cambiar userId muestra loading y luego los datos del nuevo, sin los del anterior', async () => {
    const { rerender } = render(<SeguridadComponent />)
    expect(await screen.findByText('Chrome en Linux')).toBeInTheDocument()
    let resolve!: (v: unknown) => void
    users.getUserSessions.mockReturnValueOnce(new Promise((r) => { resolve = r }))
    currentUser = { id: 'u2' }
    rerender(<SeguridadComponent />)
    expect(document.querySelector('.animate-spin')).not.toBeNull()
    expect(screen.queryByText('Chrome en Linux')).toBeNull()
    resolve({ items: [{ ...session, id: 's2', device_name: 'Safari en Mac' }] })
    expect(await screen.findByText('Safari en Mac')).toBeInTheDocument()
    expect(screen.queryByText('Chrome en Linux')).toBeNull()
    expect(users.getUserSessions).toHaveBeenLastCalledWith('u2')
  })
})

describe('SeguridadComponent labels asociados', () => {
  it('los labels de contraseña se asocian a sus inputs', async () => {
    render(<SeguridadComponent />)
    await screen.findByPlaceholderText('Ingresa tu nueva contraseña')
    expect(screen.getByLabelText('Contraseña Actual')).toBe(screen.getByPlaceholderText('Ingresa tu contraseña actual'))
    expect(screen.getByLabelText('Nueva Contraseña')).toBe(screen.getByPlaceholderText('Ingresa tu nueva contraseña'))
    expect(screen.getByLabelText('Confirmar Nueva Contraseña')).toBe(screen.getByPlaceholderText('Confirma tu nueva contraseña'))
  })
})
