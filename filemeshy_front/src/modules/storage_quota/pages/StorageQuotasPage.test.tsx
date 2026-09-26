import { render, screen, fireEvent, waitFor, act } from '@testing-library/react'
import StorageQuotasPage from './StorageQuotasPage'
import { storageQuotaService, type StorageQuotaItem } from '../services/storage-quota.service'

vi.mock('../services/storage-quota.service', () => ({
  storageQuotaService: { getQuotas: vi.fn(), getCapacity: vi.fn(), updateQuota: vi.fn() },
}))
vi.mock('@/modules/auth/hooks/useAuth', () => ({ useAuth: () => ({ hasPermission: () => true }) }))
vi.mock('@/ui/toast/CustomToast', () => ({ toast: { error: vi.fn(), success: vi.fn() } }))

const svc = vi.mocked(storageQuotaService)
const GB = 1024 ** 3
const item = (id: string, limit: number | null): StorageQuotaItem => ({
  user_id: id, email: `${id}@x.com`, first_name: 'Nom', last_name: id, limit_bytes: limit, bytes_used: 0,
})
const response = (items: StorageQuotaItem[], total = items.length, total_pages = 1) =>
  ({ items, total, page: 1, page_size: 50, total_pages }) as never

beforeEach(() => {
  vi.clearAllMocks()
  svc.getCapacity.mockResolvedValue({ total_bytes: 1000 * GB, used_bytes: 100 * GB, free_bytes: 900 * GB })
})

describe('StorageQuotasPage', () => {
  it('carga con skip 0 / limit 50 y lista los usuarios', async () => {
    svc.getQuotas.mockResolvedValueOnce(response([item('u1', 5 * GB)]))
    render(<StorageQuotasPage />)
    expect(await screen.findByText('u1@x.com')).toBeInTheDocument()
    expect(svc.getQuotas).toHaveBeenCalledTimes(1)
    expect(svc.getQuotas).toHaveBeenCalledWith({ skip: 0, limit: 50, search: undefined })
  })

  it('la búsqueda tiene debounce real: una sola petición 300 ms después de la última tecla, en página 1', async () => {
    svc.getQuotas.mockResolvedValue(response([item('u1', 5 * GB)], 120, 3))
    render(<StorageQuotasPage />)
    await screen.findByText('u1@x.com')
    // ir a la página 2 para comprobar que la búsqueda vuelve a la 1
    fireEvent.click(screen.getByRole('button', { name: '2' }))
    await waitFor(() => expect(svc.getQuotas).toHaveBeenLastCalledWith({ skip: 50, limit: 50, search: undefined }))
    svc.getQuotas.mockClear()

    vi.useFakeTimers()
    try {
      const box = screen.getByPlaceholderText('Buscar por nombre o email...') as HTMLInputElement
      fireEvent.change(box, { target: { value: 'a' } })
      fireEvent.change(box, { target: { value: 'an' } })
      fireEvent.change(box, { target: { value: 'ana' } })
      expect(box.value).toBe('ana') // el input responde al instante
      await vi.advanceTimersByTimeAsync(299)
      expect(svc.getQuotas).not.toHaveBeenCalled()
      await act(async () => { await vi.advanceTimersByTimeAsync(2) })
      expect(svc.getQuotas).toHaveBeenCalledTimes(1)
      expect(svc.getQuotas).toHaveBeenCalledWith({ skip: 0, limit: 50, search: 'ana' })
    } finally {
      vi.useRealTimers()
    }
  })

  it('la búsqueda vuelve a listar con el término', async () => {
    svc.getQuotas.mockResolvedValue(response([item('u1', 5 * GB)]))
    render(<StorageQuotasPage />)
    await screen.findByText('u1@x.com')
    fireEvent.change(screen.getByPlaceholderText('Buscar por nombre o email...'), { target: { value: 'ana' } })
    await waitFor(() => expect(svc.getQuotas).toHaveBeenLastCalledWith({ skip: 0, limit: 50, search: 'ana' }))
  })

  it('editar: abre con el límite actual y guardar actualiza la fila', async () => {
    svc.getQuotas.mockResolvedValueOnce(response([item('u1', 5 * GB)]))
    svc.updateQuota.mockResolvedValueOnce(item('u1', 2 * GB))
    render(<StorageQuotasPage />)
    await screen.findByText('u1@x.com')
    fireEvent.click(screen.getByTitle('Editar cuota'))
    const input = screen.getByLabelText('Límite de almacenamiento (GB)') as HTMLInputElement
    expect(input.value).toBe('5')
    fireEvent.change(input, { target: { value: '2' } })
    fireEvent.click(screen.getByText('Guardar'))
    await waitFor(() => expect(svc.updateQuota).toHaveBeenCalledWith('u1', { limit_bytes: 2 * GB }))
    await waitFor(() => expect(screen.queryByLabelText('Límite de almacenamiento (GB)')).not.toBeInTheDocument())
    expect(screen.getAllByText('2 GB').length).toBeGreaterThan(0)
  })

  it('la capacidad total/usada/libre lleva tooltip en GiB (base 1024) sin cambiar la etiqueta visible', async () => {
    svc.getQuotas.mockResolvedValueOnce(response([]))
    render(<StorageQuotasPage />)
    const total = await screen.findByText('1000 GB')
    expect(total).toHaveAttribute('title', '1000 GiB (base 1024)')
    expect(screen.getByText('100 GB')).toHaveAttribute('title', '100 GiB (base 1024)')
    expect(screen.getByText('900 GB')).toHaveAttribute('title', '900 GiB (base 1024)')
  })

  it('al desmontar se cancela el timer del debounce (no hay petición ni setState tardíos)', async () => {
    svc.getQuotas.mockResolvedValue(response([item('u1', 5 * GB)]))
    const { unmount } = render(<StorageQuotasPage />)
    await screen.findByText('u1@x.com')
    svc.getQuotas.mockClear()
    vi.useFakeTimers()
    try {
      const clearSpy = vi.spyOn(globalThis, 'clearTimeout')
      fireEvent.change(screen.getByPlaceholderText('Buscar por nombre o email...'), { target: { value: 'ana' } })
      unmount()
      expect(clearSpy).toHaveBeenCalled()
      expect(vi.getTimerCount()).toBe(0)
      await vi.advanceTimersByTimeAsync(500)
      expect(svc.getQuotas).not.toHaveBeenCalled()
    } finally {
      vi.useRealTimers()
    }
  })
})
