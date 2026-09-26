import { describe, it, expect, vi, beforeEach } from 'vitest'
import { AxiosError, type InternalAxiosRequestConfig } from 'axios'

const authMock = vi.hoisted(() => ({
  refreshToken: vi.fn(),
  getAccessToken: vi.fn(() => null),
  clearAutoRefresh: vi.fn(),
  setAccessToken: vi.fn(),
  discardPausedSessions: vi.fn(),
  getActiveSlot: vi.fn(() => 0),
}))
vi.mock('@/modules/auth/services/auth.service', () => ({ authService: authMock }))

import axiosInstance from './axios'

// Adaptador que responde siempre 401 con un detail, sin red real
function fail401(detail: string) {
  axiosInstance.defaults.adapter = async (config: InternalAxiosRequestConfig) => {
    throw new AxiosError('Request failed with status code 401', 'ERR_BAD_REQUEST', config, {}, {
      status: 401, statusText: 'Unauthorized', headers: {}, config, data: { detail },
    })
  }
}

beforeEach(() => {
  vi.clearAllMocks()
  authMock.refreshToken.mockRejectedValue(new Error('Refresh token no encontrado'))
})

describe('interceptor de respuesta', () => {
  it('401 del login 2FA NO dispara refresh y propaga el detail real', async () => {
    fail401('Código incorrecto. Ingresa un código TOTP o un código de respaldo válido.')
    await expect(axiosInstance.post('/auth/2fa/verify-login', { code: '000000' })).rejects.toMatchObject({
      response: { status: 401, data: { detail: expect.stringContaining('Código incorrecto') } },
    })
    expect(authMock.refreshToken).not.toHaveBeenCalled()
  })

  it('un 401 en una ruta protegida normal sí intenta refresh', async () => {
    fail401('Token expirado')
    await expect(axiosInstance.get('/files')).rejects.toBeDefined()
    expect(authMock.refreshToken).toHaveBeenCalledTimes(1)
  })
})

describe('interceptor: rutas de autenticación', () => {
  const noRefresh = [
    '/auth/login', '/auth/register', '/auth/password-reset/request', '/auth/password-reset/verify',
    '/auth/password-reset/confirm', '/auth/logout', '/auth/refresh', '/auth/2fa/verify-login',
  ]
  it.each(noRefresh)('401 en %s no dispara refresh', async (url) => {
    fail401('Credenciales inválidas')
    await expect(axiosInstance.post(url, {})).rejects.toMatchObject({ response: { status: 401 } })
    expect(authMock.refreshToken).not.toHaveBeenCalled()
  })

  it.each(['/auth/2fa/enable', '/auth/2fa/disable'])('401 de código incorrecto en %s no refresca', async (url) => {
    fail401('Código incorrecto. Ingresa un código TOTP o un código de respaldo válido.')
    await expect(axiosInstance.post(url, { code: '000000' })).rejects.toMatchObject({ response: { status: 401 } })
    expect(authMock.refreshToken).not.toHaveBeenCalled()
  })

  it.each(['/auth/2fa/enable', '/auth/2fa/disable'])('401 por token vencido en %s sí refresca', async (url) => {
    fail401('Token expirado')
    await expect(axiosInstance.post(url, { code: '000000' })).rejects.toBeDefined()
    expect(authMock.refreshToken).toHaveBeenCalledTimes(1)
  })

  it('/auth/2fa/verify (prefijo de verify-login) NO queda exento del refresh', async () => {
    fail401('Token expirado')
    await expect(axiosInstance.get('/auth/2fa/verify')).rejects.toBeDefined()
    expect(authMock.refreshToken).toHaveBeenCalledTimes(1)
  })
})
