import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, fireEvent, act } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'

const navigateMock = vi.hoisted(() => vi.fn())
vi.mock('react-router-dom', async (orig) => ({
  ...(await orig<typeof import('react-router-dom')>()),
  useNavigate: () => navigateMock,
}))

const svc = vi.hoisted(() => ({
  requestPasswordReset: vi.fn(),
  verifyCode: vi.fn(),
  confirmPasswordReset: vi.fn(),
  validateEmail: (e: string) => /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(e),
  validateCode: (c: string) => /^\d{6}$/.test(c),
  validatePassword: () => ({ valid: true }),
}))
vi.mock('@/modules/auth/services/password-reset.service', () => ({
  passwordResetService: svc,
  PASSWORD_RESET_ERROR_CODES: {
    SESSION_NOT_FOUND: 'session_not_found', SESSION_EXPIRED: 'session_expired',
    INVALID_CODE: 'invalid_code', MAX_ATTEMPTS_EXCEEDED: 'max_attempts_exceeded',
    CODE_EXPIRED: 'code_expired', INVALID_TOKEN: 'invalid_token', TOKEN_EXPIRED: 'token_expired',
    TOKEN_ALREADY_USED: 'token_already_used', INVALID_PASSWORD: 'invalid_password',
    PASSWORD_REUSED: 'password_reused', USER_NOT_FOUND: 'user_not_found',
  },
}))
vi.mock('@/ui/toast/CustomToast', () => ({ toast: { error: vi.fn(), success: vi.fn() } }))

import { ResetPassword } from './ResetPasswordPage'

async function goToCodeStep() {
  const user = userEvent.setup()
  render(<MemoryRouter><ResetPassword /></MemoryRouter>)
  await user.type(screen.getByPlaceholderText('tu@email.com'), 'a@b.com')
  await user.click(screen.getByRole('button', { name: /enviar|solicitar|código/i }))
  const input = await screen.findByPlaceholderText('123456')
  return { user, input }
}

beforeEach(() => {
  vi.clearAllMocks()
  localStorage.clear()
  svc.requestPasswordReset.mockResolvedValue({ expires_in_minutes: 15 })
})

describe('ResetPassword auto-submit del código', () => {
  it('6 dígitos llama verifyCode UNA vez con el código', async () => {
    svc.verifyCode.mockResolvedValue(undefined)
    const { user, input } = await goToCodeStep()
    await user.type(input, '123456')
    await waitFor(() => expect(svc.verifyCode).toHaveBeenCalledTimes(1))
    expect(svc.verifyCode).toHaveBeenCalledWith('123456')
  })

  it('menos de 6 dígitos no verifica', async () => {
    const { user, input } = await goToCodeStep()
    await user.type(input, '12345')
    expect(svc.verifyCode).not.toHaveBeenCalled()
  })

  it('un error no-sesión no reintenta solo (ni al insistir con más dígitos)', async () => {
    svc.verifyCode.mockRejectedValue(new Error('invalid_code: Código incorrecto'))
    const { user, input } = await goToCodeStep()
    await user.type(input, '123456')
    await waitFor(() => expect(svc.verifyCode).toHaveBeenCalledTimes(1))
    await user.type(input, '7')
    await new Promise((r) => setTimeout(r, 50))
    expect(svc.verifyCode).toHaveBeenCalledTimes(1)
  })

  it('pegar los 6 dígitos de una vez (un solo onChange) verifica UNA vez', async () => {
    svc.verifyCode.mockResolvedValue(undefined)
    const { user, input } = await goToCodeStep()
    await user.click(input)
    await user.paste('123456')
    await waitFor(() => expect(svc.verifyCode).toHaveBeenCalledTimes(1))
    expect(svc.verifyCode).toHaveBeenCalledWith('123456')
  })

  it('no dispara otra verificación mientras hay una en curso (isLoading)', async () => {
    svc.verifyCode.mockReturnValue(new Promise(() => {})) // nunca resuelve
    const { user, input } = await goToCodeStep()
    await user.type(input, '123456')
    await waitFor(() => expect(svc.verifyCode).toHaveBeenCalledTimes(1))
    // borrar un dígito y reescribirlo mientras la primera sigue pendiente
    await user.type(input, '{Backspace}')
    await user.type(input, '6')
    await new Promise((r) => setTimeout(r, 30))
    expect(svc.verifyCode).toHaveBeenCalledTimes(1)
  })

  it('tras un error de verificación se puede reintentar escribiendo otro código (una vez más)', async () => {
    svc.verifyCode.mockRejectedValue(new Error('invalid_code: Código incorrecto'))
    const { user, input } = await goToCodeStep()
    await user.type(input, '123456')
    await waitFor(() => expect(svc.verifyCode).toHaveBeenCalledTimes(1))
    await waitFor(() => expect(input).toHaveValue(''))
    await user.type(input, '123457')
    await waitFor(() => expect(svc.verifyCode).toHaveBeenCalledTimes(2))
    expect(svc.verifyCode).toHaveBeenLastCalledWith('123457')
  })

  it('tras un error se puede pegar el MISMO código y se auto-envía, sin doble envío', async () => {
    svc.verifyCode.mockRejectedValue(new Error('invalid_code: Código incorrecto'))
    const { user, input } = await goToCodeStep()
    await user.click(input)
    await user.paste('123456')
    await waitFor(() => expect(svc.verifyCode).toHaveBeenCalledTimes(1))
    await waitFor(() => expect(input).toHaveValue(''))
    await user.click(input)
    await user.paste('123456')
    await waitFor(() => expect(svc.verifyCode).toHaveBeenCalledTimes(2))
    await new Promise((r) => setTimeout(r, 30))
    expect(svc.verifyCode).toHaveBeenCalledTimes(2)
  })
})

describe('ResetPassword sessionExpired', () => {
  beforeEach(() => { svc.verifyCode.mockResolvedValue(undefined) })
  it('tras expirar y pedir un código nuevo el auto-submit vuelve a funcionar', async () => {
    vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval', 'setTimeout', 'clearTimeout', 'Date'] })
    try {
      render(<MemoryRouter><ResetPassword /></MemoryRouter>)
      const typeInto = (el: HTMLElement, value: string) => fireEvent.change(el, { target: { value } })
      typeInto(screen.getByPlaceholderText('tu@email.com'), 'a@b.com')
      fireEvent.click(screen.getByRole('button', { name: /enviar|solicitar|código/i }))
      await act(async () => { await vi.advanceTimersByTimeAsync(0) })
      expect(screen.getByPlaceholderText('123456')).toBeInTheDocument()
      // Pasan los 15 minutos: expira, vuelve al paso email
      await act(async () => { await vi.advanceTimersByTimeAsync(15 * 60 * 1000 + 2000) })
      expect(screen.getByPlaceholderText('tu@email.com')).toBeInTheDocument()
      // Nuevo intento: pide otro código y escribe 6 dígitos
      typeInto(screen.getByPlaceholderText('tu@email.com'), 'a@b.com')
      fireEvent.click(screen.getByRole('button', { name: /enviar|solicitar|código/i }))
      await act(async () => { await vi.advanceTimersByTimeAsync(0) })
      typeInto(screen.getByPlaceholderText('123456'), '123456')
      await act(async () => { await vi.advanceTimersByTimeAsync(50) })
      expect(svc.verifyCode).toHaveBeenCalledTimes(1)
      expect(svc.verifyCode).toHaveBeenCalledWith('123456')
    } finally {
      vi.useRealTimers()
    }
  })

  const expireAndReturnToEmail = async () => {
    const typeInto = (el: HTMLElement, value: string) => fireEvent.change(el, { target: { value } })
    typeInto(screen.getByPlaceholderText('tu@email.com'), 'a@b.com')
    fireEvent.click(screen.getByRole('button', { name: /enviar|solicitar|código/i }))
    await act(async () => { await vi.advanceTimersByTimeAsync(0) })
    await act(async () => { await vi.advanceTimersByTimeAsync(15 * 60 * 1000 + 1000) })
    expect(screen.getByPlaceholderText('tu@email.com')).toBeInTheDocument()
  }

  it('la redirección a "/" tras expirar se cancela si el usuario pide un código nuevo', async () => {
    vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval', 'setTimeout', 'clearTimeout', 'Date'] })
    try {
      render(<MemoryRouter><ResetPassword /></MemoryRouter>)
      await expireAndReturnToEmail()
      fireEvent.change(screen.getByPlaceholderText('tu@email.com'), { target: { value: 'a@b.com' } })
      fireEvent.click(screen.getByRole('button', { name: /enviar|solicitar|código/i }))
      await act(async () => { await vi.advanceTimersByTimeAsync(3000) })
      expect(navigateMock).not.toHaveBeenCalled()
    } finally {
      vi.useRealTimers()
    }
  })

  it('sin intervención, la redirección a "/" ocurre a los 2 s; y no ocurre si se desmonta', async () => {
    vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval', 'setTimeout', 'clearTimeout', 'Date'] })
    try {
      const first = render(<MemoryRouter><ResetPassword /></MemoryRouter>)
      await expireAndReturnToEmail()
      first.unmount()
      await act(async () => { await vi.advanceTimersByTimeAsync(3000) })
      expect(navigateMock).not.toHaveBeenCalled()

      render(<MemoryRouter><ResetPassword /></MemoryRouter>)
      await expireAndReturnToEmail()
      await act(async () => { await vi.advanceTimersByTimeAsync(2500) })
      expect(navigateMock).toHaveBeenCalledWith('/')
    } finally {
      vi.useRealTimers()
    }
  })
})
