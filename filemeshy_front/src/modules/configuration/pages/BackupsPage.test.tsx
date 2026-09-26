import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'

const backups = vi.hoisted(() => ({ list: vi.fn(), runNow: vi.fn() }))
vi.mock('../services/backups.service', () => ({ backupsService: backups }))
vi.mock('@/modules/auth/hooks/useAuth', () => ({ useAuth: () => ({ hasPermission: () => true }) }))
const toastMock = vi.hoisted(() => ({ error: vi.fn(), success: vi.fn(), warning: vi.fn() }))
vi.mock('@/ui/toast/CustomToast', () => ({ toast: toastMock }))

import BackupsPage from './BackupsPage'

beforeEach(() => {
  vi.clearAllMocks()
})

describe('BackupsPage', () => {
  it('error del servicio muestra toast', async () => {
    backups.list.mockRejectedValue(new Error('x'))
    render(<BackupsPage />)
    await waitFor(() => expect(toastMock.error).toHaveBeenCalledWith('Error al cargar el historial de backups'))
  })

  it('carga el historial una vez al montar y lo muestra', async () => {
    backups.list.mockResolvedValue([
      { id: 'b1', backup_type: 'postgres', status: 'success', started_at: '2026-01-01T00:00:00Z', finished_at: '2026-01-01T00:01:05Z', size_bytes: 1024, error_message: null },
    ])
    render(<BackupsPage />)
    expect(await screen.findByText('1m 5s')).toBeInTheDocument()
    expect(backups.list).toHaveBeenCalledTimes(1)
  })
})
