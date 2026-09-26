import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import PlatformTenantsPage from './PlatformTenantsPage'
import { tenantsService, type TenantListItem } from '../services/tenants.service'

vi.mock('../services/tenants.service', () => ({
  tenantsService: { list: vi.fn(), create: vi.fn(), update: vi.fn() },
}))
vi.mock('../services/platformAdmin.api', () => ({ getPlatformErrorMessage: () => 'error' }))
vi.mock('@/ui/toast/CustomToast', () => ({ toast: { error: vi.fn(), success: vi.fn() } }))
// El formulario real no es el foco: un botón que dispara onSubmit con un payload fijo
vi.mock('../components/CreateTenantModal', () => ({
  CreateTenantModal: ({ isOpen, onSubmit }: { isOpen: boolean; onSubmit: (p: unknown) => Promise<void> }) =>
    isOpen ? <button onClick={() => onSubmit({ slug: 'nuevo' })}>enviar-tenant</button> : null,
}))
vi.mock('../components/TenantCredentialsModal', () => ({ TenantCredentialsModal: () => null }))

const svc = vi.mocked(tenantsService)
const tenant = (slug: string): TenantListItem => ({
  id: slug, slug, schema_name: slug, company_name: `Empresa ${slug}`, plan: 'basic', is_active: true,
  created_at: '2024-01-01T00:00:00Z',
})

function renderPage() {
  return render(<MemoryRouter><PlatformTenantsPage /></MemoryRouter>)
}

beforeEach(() => vi.clearAllMocks())

describe('PlatformTenantsPage', () => {
  it('carga una vez al montar y lista los tenants', async () => {
    svc.list.mockResolvedValueOnce([tenant('acme')])
    const { container } = renderPage()
    expect(container.querySelector('.animate-spin')).toBeInTheDocument()
    expect(await screen.findByText('Empresa acme')).toBeInTheDocument()
    expect(svc.list).toHaveBeenCalledTimes(1)
  })

  it('error del servicio muestra "No se pudo cargar" (distinto de lista vacía)', async () => {
    svc.list.mockRejectedValueOnce(new Error('500'))
    renderPage()
    expect(await screen.findByText('No se pudo cargar')).toBeInTheDocument()
    expect(screen.queryByText('Todavía no hay tenants')).not.toBeInTheDocument()
  })

  it('Reintentar tras un error vuelve a listar y limpia el error', async () => {
    svc.list.mockRejectedValueOnce(new Error('500'))
    renderPage()
    await screen.findByText('No se pudo cargar')
    svc.list.mockResolvedValueOnce([tenant('acme')])
    fireEvent.click(screen.getByText('Reintentar'))
    expect(await screen.findByText('Empresa acme')).toBeInTheDocument()
    expect(svc.list).toHaveBeenCalledTimes(2)
  })

  it('lista vacía muestra el EmptyState de vacío', async () => {
    svc.list.mockResolvedValueOnce([])
    renderPage()
    expect(await screen.findByText('Todavía no hay tenants')).toBeInTheDocument()
  })

  it('crear un tenant llama al servicio y recarga la lista', async () => {
    svc.list.mockResolvedValueOnce([tenant('acme')])
    svc.create.mockResolvedValueOnce({} as never)
    renderPage()
    await screen.findByText('Empresa acme')
    svc.list.mockResolvedValueOnce([tenant('acme'), tenant('nuevo')])
    fireEvent.click(screen.getAllByText('Crear tenant')[0])
    fireEvent.click(screen.getByText('enviar-tenant'))
    await waitFor(() => expect(svc.create).toHaveBeenCalledWith({ slug: 'nuevo' }))
    expect(await screen.findByText('Empresa nuevo')).toBeInTheDocument()
    expect(svc.list).toHaveBeenCalledTimes(2)
  })

  it('Actualizar recarga la lista', async () => {
    svc.list.mockResolvedValue([tenant('acme')])
    renderPage()
    await screen.findByText('Empresa acme')
    fireEvent.click(screen.getByText('Actualizar'))
    await waitFor(() => expect(svc.list).toHaveBeenCalledTimes(2))
  })
})
