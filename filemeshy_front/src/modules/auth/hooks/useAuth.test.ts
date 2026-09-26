import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderHook, act } from '@testing-library/react'

// Servicios mockeados; el store de zustand es el REAL para comprobar el estado final
vi.mock('../services/auth.service', () => ({
  MAX_SESSION_SLOTS: 4,
  authService: {
    login: vi.fn(),
    logout: vi.fn(),
    refreshToken: vi.fn(),
    getCurrentUser: vi.fn(),
    restoreSession: vi.fn(),
    getActiveSlot: vi.fn(),
    getSessionEpoch: vi.fn(),
    pauseCurrentSession: vi.fn(),
    resumePreviousSession: vi.fn(),
    hasPausedSession: vi.fn(),
    closeActiveSessionOnBackend: vi.fn(),
  },
}))
const callOrder: string[] = []
vi.mock('@/modules/access_control/utils/permissions-mapper', () => ({
  loadValidPermissionsFromAPI: vi.fn(async () => { callOrder.push('permisos') }),
  normalizePermissions: (p: string[]) => p,
}))

import { useAuth } from './useAuth'
import { useAuthStore, type AuthUser } from '../store/authStore'
import { authService } from '../services/auth.service'
import { loadValidPermissionsFromAPI } from '@/modules/access_control/utils/permissions-mapper'

const svc = vi.mocked(authService)

const backendUser = (id: string) => ({
  id, first_name: 'N', last_name: id, email: `${id}@x.com`, role: 'USER',
  permissions: ['files.view'], avatar: undefined, theme: 'light' as const,
})
const storeUser = (id: string): AuthUser => ({ ...backendUser(id), permissions: new Set(['files.view']) })

beforeEach(() => {
  vi.clearAllMocks()
  callOrder.length = 0
  useAuthStore.setState({ user: null, isAuthenticated: false, initialized: false, pausedUsers: [] })
  svc.getActiveSlot.mockReturnValue(0)
  svc.getSessionEpoch.mockReturnValue(1)
  svc.pauseCurrentSession.mockResolvedValue(undefined as never)
  svc.logout.mockResolvedValue(undefined as never)
  vi.spyOn(console, 'error').mockImplementation(() => {})
  vi.spyOn(console, 'log').mockImplementation(() => {})
})

describe('useAuth.login', () => {
  it('sin 2FA carga permisos ANTES de store.login y guarda permissions como Set', async () => {
    svc.login.mockResolvedValue({ user: backendUser('a') } as never)
    const origLogin = useAuthStore.getState().login
    useAuthStore.setState({ login: (u) => { callOrder.push('store.login'); origLogin(u) } })
    const { result } = renderHook(() => useAuth())
    await act(async () => { await result.current.login({ email: 'a', password: 'b' } as never) })
    expect(callOrder).toEqual(['permisos', 'store.login'])
    const u = useAuthStore.getState().user!
    expect(u.permissions).toBeInstanceOf(Set)
    expect(u.permissions.has('files.view')).toBe(true)
    expect(useAuthStore.getState().isAuthenticated).toBe(true)
    useAuthStore.setState({ login: origLogin })
  })

  it('con requires_2fa retorna la respuesta sin tocar el store', async () => {
    const resp = { requires_2fa: true }
    svc.login.mockResolvedValue(resp as never)
    const { result } = renderHook(() => useAuth())
    let out: unknown
    await act(async () => { out = await result.current.login({} as never) })
    expect(out).toBe(resp)
    expect(useAuthStore.getState().user).toBeNull()
    expect(loadValidPermissionsFromAPI).not.toHaveBeenCalled()
  })
})

describe('useAuth.switchUser', () => {
  it('sin sesión activa lanza', async () => {
    const { result } = renderHook(() => useAuth())
    await expect(result.current.switchUser({} as never)).rejects.toThrow(/No hay una sesión activa/)
  })

  it('en el tope de slots lanza y no pausa', async () => {
    useAuthStore.setState({ user: storeUser('a') })
    svc.getActiveSlot.mockReturnValue(3)
    const { result } = renderHook(() => useAuth())
    await expect(result.current.switchUser({} as never)).rejects.toThrow(/máximo de 4/)
    expect(svc.pauseCurrentSession).not.toHaveBeenCalled()
  })

  it('éxito: push del previo y login del nuevo', async () => {
    useAuthStore.setState({ user: storeUser('a'), isAuthenticated: true })
    svc.login.mockResolvedValue({ user: backendUser('b') } as never)
    const { result } = renderHook(() => useAuth())
    await act(async () => { await result.current.switchUser({} as never) })
    const s = useAuthStore.getState()
    expect(s.user!.id).toBe('b')
    expect(s.pausedUsers.map((u) => u.id)).toEqual(['a'])
    expect(svc.resumePreviousSession).not.toHaveBeenCalled()
  })

  it('si el login falla se deshace el pause', async () => {
    useAuthStore.setState({ user: storeUser('a'), isAuthenticated: true })
    svc.login.mockRejectedValue(new Error('credenciales'))
    const { result } = renderHook(() => useAuth())
    await act(async () => { await expect(result.current.switchUser({} as never)).rejects.toThrow('credenciales') })
    expect(svc.resumePreviousSession).toHaveBeenCalledTimes(1)
    expect(useAuthStore.getState().pausedUsers).toEqual([])
    expect(useAuthStore.getState().user!.id).toBe('a')
  })

  it('si pide 2FA se deshace el pause y lanza', async () => {
    useAuthStore.setState({ user: storeUser('a'), isAuthenticated: true })
    svc.login.mockResolvedValue({ requires_2fa: true } as never)
    const { result } = renderHook(() => useAuth())
    await act(async () => { await expect(result.current.switchUser({} as never)).rejects.toThrow(/dos pasos/) })
    expect(svc.resumePreviousSession).toHaveBeenCalledTimes(1)
    expect(useAuthStore.getState().pausedUsers).toEqual([])
  })

  it('tras committed un error tardío NO deshace', async () => {
    useAuthStore.setState({ user: storeUser('a'), isAuthenticated: true })
    svc.login.mockResolvedValue({ user: backendUser('b') } as never)
    const orig = useAuthStore.getState().login
    useAuthStore.setState({ login: () => { throw new Error('tardío') } })
    const { result } = renderHook(() => useAuth())
    await act(async () => { await expect(result.current.switchUser({} as never)).rejects.toThrow('tardío') })
    expect(svc.resumePreviousSession).not.toHaveBeenCalled()
    expect(useAuthStore.getState().pausedUsers.map((u) => u.id)).toEqual(['a'])
    useAuthStore.setState({ login: orig })
  })

  it('si el epoch cambió no pisa el store', async () => {
    useAuthStore.setState({ user: storeUser('a'), isAuthenticated: true })
    svc.getSessionEpoch.mockReturnValueOnce(1).mockReturnValue(2)
    svc.login.mockResolvedValue({ user: backendUser('b') } as never)
    const { result } = renderHook(() => useAuth())
    await act(async () => { await result.current.switchUser({} as never) })
    expect(useAuthStore.getState().user!.id).toBe('a')
  })
})

describe('useAuth.returnToPreviousUser', () => {
  it('false sin sesión pausada', async () => {
    svc.hasPausedSession.mockReturnValue(false)
    const { result } = renderHook(() => useAuth())
    let r = true
    await act(async () => { r = await result.current.returnToPreviousUser() })
    expect(r).toBe(false)
  })

  it('restaura el usuario cacheado', async () => {
    useAuthStore.setState({ user: storeUser('b'), pausedUsers: [storeUser('a')] })
    svc.hasPausedSession.mockReturnValue(true)
    svc.closeActiveSessionOnBackend.mockResolvedValue(undefined as never)
    svc.resumePreviousSession.mockReturnValue(true as never)
    const { result } = renderHook(() => useAuth())
    let r = false
    await act(async () => { r = await result.current.returnToPreviousUser() })
    expect(r).toBe(true)
    expect(useAuthStore.getState().user!.id).toBe('a')
    expect(useAuthStore.getState().pausedUsers).toEqual([])
    expect(svc.getCurrentUser).not.toHaveBeenCalled()
  })

  it('sin cacheado pide el usuario al backend', async () => {
    useAuthStore.setState({ user: storeUser('b'), pausedUsers: [] })
    svc.hasPausedSession.mockReturnValue(true)
    svc.closeActiveSessionOnBackend.mockResolvedValue(undefined as never)
    svc.resumePreviousSession.mockReturnValue(true as never)
    svc.getCurrentUser.mockResolvedValue(backendUser('a') as never)
    const { result } = renderHook(() => useAuth())
    await act(async () => { await result.current.returnToPreviousUser() })
    expect(svc.getCurrentUser).toHaveBeenCalledTimes(1)
    expect(useAuthStore.getState().user!.id).toBe('a')
  })
})

describe('useAuth logout / refresh / fetch / restore', () => {
  it('logout limpia el store aunque authService.logout falle', async () => {
    useAuthStore.setState({ user: storeUser('a'), isAuthenticated: true })
    svc.logout.mockRejectedValue(new Error('red'))
    const { result } = renderHook(() => useAuth())
    await act(async () => { await expect(result.current.logout()).rejects.toThrow('red') })
    expect(useAuthStore.getState().user).toBeNull()
  })

  it('refreshToken con fallo hace logout y relanza', async () => {
    useAuthStore.setState({ user: storeUser('a'), isAuthenticated: true })
    svc.refreshToken.mockRejectedValue(new Error('x'))
    const { result } = renderHook(() => useAuth())
    await act(async () => { await expect(result.current.refreshToken()).rejects.toThrow('x') })
    expect(useAuthStore.getState().isAuthenticated).toBe(false)
  })

  it('fetchCurrentUser: éxito guarda; fallo hace logout y relanza', async () => {
    svc.getCurrentUser.mockResolvedValueOnce(backendUser('z') as never)
    const { result } = renderHook(() => useAuth())
    await act(async () => { await result.current.fetchCurrentUser() })
    expect(useAuthStore.getState().user!.id).toBe('z')
    svc.getCurrentUser.mockRejectedValueOnce(new Error('y'))
    await act(async () => { await expect(result.current.fetchCurrentUser()).rejects.toThrow('y') })
    expect(useAuthStore.getState().user).toBeNull()
  })

  it('restoreSession(false) hace logout; true carga usuario', async () => {
    useAuthStore.setState({ user: storeUser('a'), isAuthenticated: true })
    svc.restoreSession.mockResolvedValueOnce(false as never)
    const { result } = renderHook(() => useAuth())
    await act(async () => { await result.current.restoreSession() })
    expect(useAuthStore.getState().user).toBeNull()
    svc.restoreSession.mockResolvedValueOnce(true as never)
    svc.getCurrentUser.mockResolvedValueOnce(backendUser('q') as never)
    await act(async () => { await result.current.restoreSession() })
    expect(useAuthStore.getState().user!.id).toBe('q')
  })

  it('las acciones conservan identidad estable entre renders', async () => {
    const { result, rerender } = renderHook(() => useAuth())
    const first = result.current
    await act(async () => { useAuthStore.getState().login(storeUser('a')) })
    rerender()
    for (const k of ['login', 'logout', 'switchUser', 'returnToPreviousUser', 'refreshToken', 'fetchCurrentUser', 'restoreSession'] as const) {
      expect(result.current[k]).toBe(first[k])
    }
  })
})
