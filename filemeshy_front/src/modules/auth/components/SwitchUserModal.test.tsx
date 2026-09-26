import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

const switchUserMock = vi.fn()
vi.mock('@/modules/auth/hooks/useAuth', () => ({ useAuth: () => ({ switchUser: switchUserMock }) }))
vi.mock('@/ui/toast/CustomToast', () => ({ toast: { success: vi.fn(), error: vi.fn() } }))

import SwitchUserModal from './SwitchUserModal'

const pwd = () => document.querySelector('input[type="password"]') as HTMLInputElement

describe('SwitchUserModal', () => {
  it('al reabrir, email/password/error quedan vacíos y el email recibe foco', async () => {
    switchUserMock.mockRejectedValue(new Error('credenciales malas'))
    const user = userEvent.setup()
    const { rerender } = render(<SwitchUserModal isOpen onClose={() => {}} />)
    await user.type(screen.getByPlaceholderText('usuario@empresa.com'), 'a@b.com')
    await user.type(pwd(), 'secreto')
    fireEvent.submit(pwd().closest('form')!)
    expect(await screen.findByText('credenciales malas')).toBeInTheDocument()

    rerender(<SwitchUserModal isOpen={false} onClose={() => {}} />)
    expect(screen.queryByPlaceholderText('usuario@empresa.com')).toBeNull()
    rerender(<SwitchUserModal isOpen onClose={() => {}} />)

    expect(screen.getByPlaceholderText('usuario@empresa.com')).toHaveValue('')
    expect(pwd()).toHaveValue('')
    expect(screen.queryByText('credenciales malas')).toBeNull()
    await waitFor(() => expect(screen.getByPlaceholderText('usuario@empresa.com')).toHaveFocus())
  })
})

describe('SwitchUserModal labels asociados', () => {
  it('Correo y Contraseña se asocian a sus controles', () => {
    render(<SwitchUserModal isOpen onClose={() => {}} />)
    expect(screen.getByLabelText('Correo')).toBe(screen.getByPlaceholderText('usuario@empresa.com'))
    expect(screen.getByLabelText('Contraseña')).toHaveAttribute('type', 'password')
  })
})
