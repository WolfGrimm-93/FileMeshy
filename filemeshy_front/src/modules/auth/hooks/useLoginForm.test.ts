import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { renderHook, act, waitFor } from '@testing-library/react'

const loginMock = vi.fn()
vi.mock('./useAuth', () => ({ useAuth: () => ({ login: loginMock }) }))
const navigateMock = vi.fn()
vi.mock('react-router-dom', () => ({ useNavigate: () => navigateMock }))
vi.mock('@/ui/toast/CustomToast', () => ({
  toast: { error: vi.fn(), dismiss: vi.fn(), success: vi.fn() },
}))
vi.mock('../services/auth.service', () => ({
  authService: {
    getTurnstileConfig: vi.fn(async () => ({ enabled: true, site_key: 'k' })),
    verifyTwoFactorLogin: vi.fn(),
  },
}))
vi.mock('@/shared/config/env', () => ({
  getTenantSlug: () => 'demo',
  setTenantSlug: vi.fn(),
}))

import { useLoginForm } from './useLoginForm'
import { toast } from '@/ui/toast/CustomToast'

const change = (name: string, value: string) =>
  ({ target: { name, value } }) as React.ChangeEvent<HTMLInputElement>
const submitEvent = () => ({ preventDefault: () => {} }) as React.FormEvent

async function fillForm(result: { current: ReturnType<typeof useLoginForm> }) {
  act(() => result.current.handleChange(change('email', 'A@b.com')))
  act(() => result.current.handleChange(change('password', 'secreto1')))
}

beforeEach(() => {
  vi.clearAllMocks()
  vi.spyOn(console, 'error').mockImplementation(() => {})
  loginMock.mockResolvedValue({ user: {} })
})
afterEach(() => vi.unstubAllGlobals())

describe('useLoginForm.handleSubmit', () => {
  it('envía remember_me actual si se tilda DESPUÉS de tipear (BUG deps)', async () => {
    const { result } = renderHook(() => useLoginForm())
    await fillForm(result)
    act(() => result.current.setRememberMe(true))
    await act(async () => { await result.current.handleSubmit(submitEvent()) })
    expect(loginMock).toHaveBeenCalledWith(
      expect.objectContaining({ email: 'a@b.com', remember_me: true }),
    )
  })

  it('con CAPTCHA resuelto DESPUÉS de tipear envía turnstile_token y no muestra toast (BUG deps)', async () => {
    vi.stubGlobal('location', { hostname: 'app.example.com' })
    const { result } = renderHook(() => useLoginForm())
    await waitFor(() => expect(result.current.turnstileConfig?.enabled).toBe(true))
    await fillForm(result)
    // Sin token: bloquea
    await act(async () => { await result.current.handleSubmit(submitEvent()) })
    expect(toast.error).toHaveBeenCalledWith(expect.stringContaining('CAPTCHA'), expect.anything())
    expect(loginMock).not.toHaveBeenCalled()
    vi.mocked(toast.error).mockClear()
    // Se resuelve el CAPTCHA después
    act(() => result.current.setTurnstileToken('tok-123'))
    await act(async () => { await result.current.handleSubmit(submitEvent()) })
    expect(toast.error).not.toHaveBeenCalled()
    expect(loginMock).toHaveBeenCalledWith(expect.objectContaining({ turnstile_token: 'tok-123' }))
  })
})
