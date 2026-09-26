import { render, screen, act } from '@testing-library/react'
import { Outlet } from 'react-router-dom'

// Se enruta con un memory router (en jsdom, createBrowserRouter dispararía los loaders al importar
// y dependería de window.location) sin tocar la definición de rutas real de App.tsx.
vi.mock('react-router-dom', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-router-dom')>()
  return {
    ...actual,
    createBrowserRouter: (routes: Parameters<typeof actual.createMemoryRouter>[0]) =>
      actual.createMemoryRouter(routes, { initialEntries: ['/login'] }),
  }
})

// Loader lento: nunca resuelve hasta que el test lo libera
let releasePublicLoader!: () => void
vi.mock('./app/routes/loaders', () => ({
  publicLoader: () => new Promise((resolve) => { releasePublicLoader = () => resolve(null) }),
  authLoader: () => null,
  resetPasswordLoader: () => null,
  requirePermissions: () => () => null,
  dashboardLoader: () => null,
}))
vi.mock('./app/layout', () => ({
  RootLayout: () => <div data-testid="root-layout"><Outlet /></div>,
  ProtectedLayout: () => <Outlet />,
  PublicLayout: () => <Outlet />,
}))
vi.mock('./app/components', () => ({ RootErrorBoundary: () => null }))
vi.mock('./modules/auth/pages/LoginPage', () => ({ LoginPage: () => <p>pantalla-login</p> }))
vi.mock('./modules/auth/pages/ResetPasswordPage', () => ({ ResetPassword: () => null }))
vi.mock('./modules/platform/pages/AboutPage', () => ({ AboutPage: () => null }))
vi.mock('./modules/platform/pages/TermsPage', () => ({ TermsPage: () => null }))
vi.mock('./modules/platform/pages/PrivacyPage', () => ({ PrivacyPage: () => null }))
vi.mock('./modules/platform_admin/guards/PlatformAuthGuard', () => ({ PlatformAuthGuard: () => null }))

describe('App: carga inicial del router', () => {
  it('con un loader lento no emite el warning de HydrateFallback y luego renderiza la ruta', async () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {})
    const { default: App } = await import('./App')
    render(<App />)

    // Mientras el loader está pendiente aún no se muestra la pantalla
    expect(screen.queryByText('pantalla-login')).not.toBeInTheDocument()
    const hydrationWarnings = warn.mock.calls.filter((c) => String(c[0]).includes('HydrateFallback'))
    expect(hydrationWarnings).toEqual([])

    await act(async () => { releasePublicLoader() })
    expect(await screen.findByText('pantalla-login')).toBeInTheDocument()
    warn.mockRestore()
  })
})
