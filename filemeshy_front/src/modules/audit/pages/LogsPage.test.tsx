import { render, screen, fireEvent, waitFor, act } from '@testing-library/react'
import LogsPage from './LogsPage'
import { auditLogService } from '../services/auditLog.service'

vi.mock('../services/auditLog.service', () => ({
  auditLogService: { getLogs: vi.fn(), getStats: vi.fn(), getLogDetail: vi.fn() },
}))
vi.mock('sonner', () => ({ toast: { error: vi.fn(), success: vi.fn(), info: vi.fn() } }))

const getLogs = vi.mocked(auditLogService.getLogs)

const logRow = (id: string) => ({
  id, user_id: 'u', user_email: `${id}@x.com`, action: 'CREATE', table_name: 'files', record_id: 'r',
  ip_address: '1.1.1.1', endpoint: '/x', method: 'POST', created_at: '2024-01-01T00:00:00Z',
})

beforeEach(() => {
  getLogs.mockReset()
  vi.mocked(auditLogService.getStats).mockResolvedValue({ total_logs: 0, by_action: {}, top_tables: [] } as never)
})

describe('LogsPage carga', () => {
  it('carga al montar con skip 0 y limit 50 (una sola llamada) y muestra "Cargando logs..." antes', async () => {
    let resolve!: (v: never) => void
    getLogs.mockReturnValueOnce(new Promise((r) => { resolve = r as never }))
    render(<LogsPage />)
    expect(screen.getByText('Cargando logs...')).toBeInTheDocument()
    await act(async () => { resolve({ logs: [logRow('1')], total: 1 } as never) })
    expect(await screen.findByText('1@x.com')).toBeInTheDocument()
    expect(getLogs).toHaveBeenCalledTimes(1)
    // Por defecto el período es "hoy": start_date viene seteado, sin end_date
    expect(getLogs).toHaveBeenCalledWith({
      action: undefined, table_name: undefined, start_date: expect.any(String), end_date: undefined,
      search: undefined, skip: 0, limit: 50,
    })
  })

  it('Actualizar vuelve a cargar y muestra el estado de carga', async () => {
    getLogs.mockResolvedValueOnce({ logs: [logRow('1')], total: 1 } as never)
    render(<LogsPage />)
    await screen.findByText('1@x.com')
    let resolve!: (v: never) => void
    getLogs.mockReturnValueOnce(new Promise((r) => { resolve = r as never }))
    fireEvent.click(screen.getByText('Actualizar'))
    expect(await screen.findByText('Cargando logs...')).toBeInTheDocument()
    await act(async () => { resolve({ logs: [logRow('2')], total: 1 } as never) })
    expect(await screen.findByText('2@x.com')).toBeInTheDocument()
    expect(getLogs).toHaveBeenCalledTimes(2)
  })

  it('la búsqueda (debounce) llama una vez con search y skip 0', async () => {
    getLogs.mockResolvedValue({ logs: [logRow('1')], total: 1 } as never)
    render(<LogsPage />)
    await screen.findByText('1@x.com')
    fireEvent.change(screen.getByPlaceholderText('Buscar por usuario, endpoint...'), { target: { value: 'ana' } })
    await waitFor(() => expect(getLogs).toHaveBeenCalledTimes(2))
    expect(getLogs).toHaveBeenLastCalledWith(expect.objectContaining({ search: 'ana', skip: 0, limit: 50 }))
    await new Promise((r) => setTimeout(r, 400))
    expect(getLogs).toHaveBeenCalledTimes(2)
  })

  it('cambiar de página pide skip = (pagina-1)*limit; cambiar tamaño vuelve a la página 1', async () => {
    getLogs.mockResolvedValue({ logs: [logRow('1')], total: 500 } as never)
    render(<LogsPage />)
    await screen.findByText('1@x.com')
    fireEvent.click(screen.getByRole('button', { name: '2' }))
    await waitFor(() => expect(getLogs).toHaveBeenCalledTimes(2))
    expect(getLogs).toHaveBeenLastCalledWith(expect.objectContaining({ skip: 50, limit: 50 }))

    fireEvent.click(screen.getByRole('button', { name: '100' }))
    await waitFor(() => expect(getLogs).toHaveBeenCalledTimes(3))
    expect(getLogs).toHaveBeenLastCalledWith(expect.objectContaining({ skip: 0, limit: 100 }))
    await new Promise((r) => setTimeout(r, 50))
    expect(getLogs).toHaveBeenCalledTimes(3)
  })

  it('un error deja de mostrar "Cargando logs..."', async () => {
    getLogs.mockRejectedValueOnce(new Error('x'))
    render(<LogsPage />)
    expect(await screen.findByText('No se encontraron registros')).toBeInTheDocument()
  })

  it('la columna Fecha/Hora muestra el texto aunque created_at llegue con +00:00Z y "—" si no parsea', async () => {
    getLogs.mockResolvedValueOnce({
      logs: [
        { ...logRow('1'), created_at: '2026-09-25T11:30:49+00:00Z' },
        { ...logRow('2'), created_at: 'basura' },
      ],
      total: 2,
    } as never)
    render(<LogsPage />)
    await screen.findByText('1@x.com')
    expect(screen.getByText(/2026/)).toBeInTheDocument()
    expect(screen.getByText('—', { selector: 'div' })).toBeInTheDocument()
  })
})
