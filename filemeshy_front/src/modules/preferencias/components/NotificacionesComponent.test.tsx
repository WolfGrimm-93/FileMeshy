import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

const prefs = vi.hoisted(() => ({ getMyPreferences: vi.fn(), updateMyPreferences: vi.fn() }))
vi.mock('@/modules/configuration/services/user-preferences.service', () => ({ userPreferencesService: prefs }))
vi.mock('@/modules/auth/hooks/useAuth', () => ({ useAuth: () => ({ user: { email: 'yo@x.com' } }) }))
const toastMock = vi.hoisted(() => ({ error: vi.fn(), success: vi.fn() }))
vi.mock('@/ui/toast/CustomToast', () => ({ toast: toastMock }))

import NotificacionesComponent from './NotificacionesComponent'

// Los toggles son los dos primeros botones (sin nombre accesible); "activo" = clase bg-brand-600
const toggles = () => screen.getAllByRole('button').slice(0, 2)
const isOn = (el: HTMLElement) => el.className.includes('bg-brand-600')

beforeEach(() => {
  vi.clearAllMocks()
  vi.spyOn(console, 'error').mockImplementation(() => {})
  prefs.getMyPreferences.mockResolvedValue({ email_notifications: true, system_notifications: false })
  prefs.updateMyPreferences.mockResolvedValue({})
})

describe('NotificacionesComponent', () => {
  it('los toggles reflejan getMyPreferences y muestra el email', async () => {
    render(<NotificacionesComponent />)
    await screen.findByText('Guardar Preferencias')
    const [email, system] = toggles()
    expect(isOn(email)).toBe(true)
    expect(isOn(system)).toBe(false)
    expect(screen.getByText('yo@x.com')).toBeInTheDocument()
  })

  it('un click cambia el estado y guardar llama updateMyPreferences(formData)', async () => {
    const onSave = vi.fn()
    const user = userEvent.setup()
    render(<NotificacionesComponent onSave={onSave} />)
    await screen.findByText('Guardar Preferencias')
    await user.click(toggles()[1])
    expect(isOn(toggles()[1])).toBe(true)
    await user.click(screen.getByText('Guardar Preferencias'))
    await waitFor(() =>
      expect(prefs.updateMyPreferences).toHaveBeenCalledWith({ email_notifications: true, system_notifications: true }),
    )
    await waitFor(() => expect(onSave).toHaveBeenCalled())
    expect(toastMock.success).toHaveBeenCalled()
    expect(prefs.getMyPreferences).toHaveBeenCalledTimes(2) // recarga tras guardar
  })

  it('error al cargar muestra toast', async () => {
    prefs.getMyPreferences.mockRejectedValue(new Error('x'))
    render(<NotificacionesComponent />)
    await waitFor(() => expect(toastMock.error).toHaveBeenCalled())
  })
})
