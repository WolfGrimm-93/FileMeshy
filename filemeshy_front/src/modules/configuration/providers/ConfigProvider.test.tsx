import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, act } from '@testing-library/react'
import { useContext } from 'react'

let currentUser: { id: string } | null = null
vi.mock('@/modules/auth/hooks/useAuth', () => ({ useAuth: () => ({ user: currentUser }) }))
const cfg = vi.hoisted(() => ({ getPublicConfig: vi.fn(), clearCache: vi.fn() }))
vi.mock('../services/config.service', () => ({ configService: cfg }))
vi.mock('../services/admin-configuration.service', () => ({
  adminConfigurationService: { getConfigVersion: vi.fn().mockRejectedValue(new Error('sin sesión')) },
}))

import { ConfigProvider } from './ConfigProvider'
import { ConfigContext } from './configContext'

const Probe = () => {
  const ctx = useContext(ConfigContext)!
  return <div data-testid="name">{(ctx.config as unknown as { name?: string } | null)?.name ?? 'none'}</div>
}
const ui = () => <ConfigProvider><Probe /></ConfigProvider>

beforeEach(() => {
  vi.clearAllMocks()
  currentUser = null
})

describe('ConfigProvider', () => {
  it('primer render carga una vez sin clearCache; cambios de userId refrescan', async () => {
    cfg.getPublicConfig.mockResolvedValueOnce({ name: 'inicial' })
    const { rerender } = render(ui())
    await waitFor(() => expect(screen.getByTestId('name')).toHaveTextContent('inicial'))
    expect(cfg.getPublicConfig).toHaveBeenCalledTimes(1)
    expect(cfg.clearCache).not.toHaveBeenCalled()

    // null -> A (login): refresca
    cfg.getPublicConfig.mockResolvedValueOnce({ name: 'tenant-A' })
    currentUser = { id: 'A' }
    rerender(ui())
    await waitFor(() => expect(screen.getByTestId('name')).toHaveTextContent('tenant-A'))
    expect(cfg.clearCache).toHaveBeenCalledTimes(1)

    // A -> B: refresca
    cfg.getPublicConfig.mockResolvedValueOnce({ name: 'tenant-B' })
    currentUser = { id: 'B' }
    await act(async () => { rerender(ui()) })
    await waitFor(() => expect(screen.getByTestId('name')).toHaveTextContent('tenant-B'))
    expect(cfg.clearCache).toHaveBeenCalledTimes(2)

    // B -> null (logout): no refresca
    currentUser = null
    rerender(ui())
    expect(cfg.clearCache).toHaveBeenCalledTimes(2)
  })
})
