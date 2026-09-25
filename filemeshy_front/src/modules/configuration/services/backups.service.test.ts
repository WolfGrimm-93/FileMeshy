import axiosInstance from '@/shared/config/axios'
import { backupsService } from './backups.service'

vi.mock('@/shared/config/axios', () => ({
  default: { get: vi.fn(), post: vi.fn() },
}))

describe('backupsService.list', () => {
  it('desenvuelve {items,total} y devuelve solo el array items', async () => {
    const items = [{ id: 'a', backup_type: 'postgres', status: 'success' }]
    vi.mocked(axiosInstance.get).mockResolvedValueOnce({ data: { items, total: 1 } })
    const result = await backupsService.list()
    expect(axiosInstance.get).toHaveBeenCalledWith('/admin/backups')
    expect(result).toBe(items)
    expect(Array.isArray(result)).toBe(true)
  })
})
