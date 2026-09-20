import './assets/index.css'
import { RouterProvider, createBrowserRouter, Navigate } from 'react-router-dom'
import { lazy } from 'react'
import { setNavigate } from './shared/utils/navigation'
import { RootLayout, ProtectedLayout, PublicLayout } from './app/layout'
import { RootErrorBoundary } from './app/components'
import {
  authLoader,
  publicLoader,
  resetPasswordLoader,
  requirePermissions,
  dashboardLoader
} from './app/routes/loaders'
import { Permission } from './app/routes'

// Páginas públicas — import directo (sin lazy) para carga inmediata
import { LoginPage } from './modules/auth/pages/LoginPage'
import { ResetPassword } from './modules/auth/pages/ResetPasswordPage'
import { AboutPage } from './modules/platform/pages/AboutPage'
import { TermsPage } from './modules/platform/pages/TermsPage'
import { PrivacyPage } from './modules/platform/pages/PrivacyPage'
const ForbiddenPage = lazy(() => import('./modules/access_control/guards/ForbiddenPage').then(m => ({ default: m.default })))
const ModuloNoDisponiblePage = lazy(() => import('./modules/configuration/pages/ModuloNoDisponiblePage').then(m => ({ default: m.default })))
const DashboardPage = lazy(() => import('./modules/dashboard/pages/DashboardPage'))

// Archivos
const FilesPage = lazy(() => import('./modules/files/pages/FilesPage'))
const PublicSharePage = lazy(() => import('./modules/files/pages/PublicSharePage'))
const SharedWithMePage = lazy(() => import('./modules/files/pages/SharedWithMePage'))

// Usuarios
const UsuariosPage = lazy(() => import('./modules/users/pages/UsuariosPage'))
const UserCreatePage = lazy(() => import('./modules/users/pages').then(m => ({ default: m.UserCreatePage })))
const UserEditPage = lazy(() => import('./modules/users/pages').then(m => ({ default: m.UserEditPage })))
const UserDetailPage = lazy(() => import('./modules/users/pages').then(m => ({ default: m.UserDetailPage })))

// Roles
const RolesManagementPage = lazy(() => import('./modules/access_control/pages/RolesManagementPage'))
const PermissionsManagementPage = lazy(() => import('./modules/access_control/pages/PermissionsManagementPage'))
const RoleCreatePage = lazy(() => import('./modules/access_control/pages/RoleCreatePage'))
const RoleDetailPage = lazy(() => import('./modules/access_control/pages/RoleDetailPage'))
const RoleEditPage = lazy(() => import('./modules/access_control/pages/RoleEditPage'))

// Cuotas de almacenamiento
const StorageQuotasPage = lazy(() => import('./modules/storage_quota/pages/StorageQuotasPage'))

// Configuración
const ConfiguracionPage = lazy(() => import('./modules/configuration/pages/ConfiguracionPage'))

// Sistema
const LogsPage = lazy(() => import('./modules/audit/pages/LogsPage'))
const PreferenciasPage = lazy(() => import('./modules/preferencias/pages/PreferenciasPage'))
const NotificacionesPage = lazy(() => import('./modules/notifications/pages/NotificacionesPage'))

// Otros
const NotFoundPage = lazy(() => import('./modules/platform/pages/NotFoundPage'))
const UnauthorizedPage = lazy(() => import('./modules/auth/pages/UnauthorizedPage'))

// ==================== ROUTER CONFIGURATION ====================

// const LoadingFallback = () => <FullScreenLoader message="Cargando aplicación..." />

const router = createBrowserRouter([
  // ==================== MAIN APP ROUTES ====================
  {
    element: <RootLayout />,
    errorElement: <RootErrorBoundary />,
    children: [
      // ==================== PUBLIC ROUTES ====================
      {
        element: <PublicLayout />,
        children: [
          {
            path: '/login',
            element: <LoginPage />,
            loader: publicLoader,
          },
          {
            path: '/reset-password',
            element: <ResetPassword />,
            loader: resetPasswordLoader,
          },
          {
            path: '/about',
            element: <AboutPage />,
          },
          {
            path: '/terms',
            element: <TermsPage />,
          },
          {
            path: '/privacy',
            element: <PrivacyPage />,
          },
          {
            path: '/compartido/:token',
            element: <PublicSharePage />,
          },
          {
            path: '/unauthorized',
            element: <UnauthorizedPage />,
          },
          {
            path: '/forbidden',
            element: <ForbiddenPage />,
          },
          {
            path: '/modulo-no-disponible',
            element: <ModuloNoDisponiblePage />,
          },
        ],
      },

      // ==================== PROTECTED ROUTES ====================
      {
        element: <ProtectedLayout />,
        loader: authLoader,
        errorElement: <RootErrorBoundary />,
        children: [
          {
            index: true,
            element: <Navigate to="/dashboard" replace />,
          },

          // Dashboard
          {
            path: 'dashboard',
            element: <DashboardPage />,
            loader: dashboardLoader,
          },

          // Archivos
          {
            path: 'archivos',
            element: <FilesPage />,
            loader: requirePermissions([Permission.VIEW_FILES]),
          },
          // Compartido conmigo (Ronda 3) -- mismo permiso que Archivos, ya
          // que es otra vista del mismo módulo de archivos/carpetas.
          {
            path: 'compartido-conmigo',
            element: <SharedWithMePage />,
            loader: requirePermissions([Permission.VIEW_FILES]),
          },

          // Usuarios
          {
            path: 'usuarios',
            element: <UsuariosPage />,
            loader: requirePermissions([Permission.VIEW_USERS]),
          },
          {
            path: 'usuarios/nuevo',
            element: <UserCreatePage />,
            loader: requirePermissions([Permission.CREATE_USERS]),
          },
          {
            path: 'usuarios/:id/editar',
            element: <UserEditPage />,
            loader: requirePermissions([Permission.EDIT_USERS]),
          },
          {
            path: 'usuarios/:id',
            element: <UserDetailPage />,
            loader: requirePermissions([Permission.VIEW_USERS]),
          },

          // Roles (ADMIN/SUPER_ADMIN only)
          {
            path: 'roles',
            element: <RolesManagementPage />,
            loader: requirePermissions([Permission.VIEW_USERS]), // Reuse user permission for now
          },
          {
            path: 'roles/nuevo',
            element: <RoleCreatePage />,
            loader: requirePermissions([Permission.VIEW_USERS]),
          },
          {
            path: 'roles/:id',
            element: <RoleDetailPage />,
            loader: requirePermissions([Permission.VIEW_USERS]),
          },
          {
            path: 'roles/:id/editar',
            element: <RoleEditPage />,
            loader: requirePermissions([Permission.VIEW_USERS]),
          },

          // Permisos (catálogo + asignación rol<->permiso) — ver/editar exige
          // VIEW_USERS igual que Roles; el guardado en sí lo re-valida el
          // backend con permissions.manage (solo SUPER_ADMIN por defecto).
          {
            path: 'permisos',
            element: <PermissionsManagementPage />,
            loader: requirePermissions([Permission.VIEW_USERS]),
          },

          // Sistema
          // Preferencias de usuario (todos los usuarios)
          {
            path: 'preferencias',
            element: <PreferenciasPage />,
            loader: authLoader,
          },
          // Notificaciones
          {
            path: 'notificaciones',
            element: <NotificacionesPage />,
            loader: authLoader,
          },
          {
            path: 'logs',
            element: <LogsPage />,
            loader: requirePermissions([Permission.VIEW_LOGS]),
          },

          // Cuotas de almacenamiento
          {
            path: 'cuotas-almacenamiento',
            element: <StorageQuotasPage />,
            loader: requirePermissions([Permission.VIEW_STORAGE_QUOTAS]),
          },

          // Configuración
          {
            path: 'configuracion',
            element: <ConfiguracionPage />,
            loader: requirePermissions([Permission.VIEW_SETTINGS]),
          },

          // 404 - Debe estar al final
          {
            path: '*',
            element: <NotFoundPage />,
          },
        ],
      },
    ],
  },
])

// Puente de navegación imperativa: permite que stores/servicios/toasts (fuera de React)
// naveguen por el SPA sin recargar. Ver shared/utils/navigation.ts.
setNavigate((to) => { void router.navigate(to) })

// ==================== APP COMPONENT ====================

function App() {
  return <RouterProvider router={router} />
}

export default App
