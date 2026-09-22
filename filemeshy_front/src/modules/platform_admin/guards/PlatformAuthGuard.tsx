/**
 * Guard del panel de plataforma.
 *
 * NO usa el sistema de loaders/RBAC normal de la app (`authLoader`,
 * `requirePermissions`, ver `app/routes/loaders.ts`) -- ese guarda contra
 * el usuario logueado de un tenant, y este panel es intencionalmente ajeno
 * a esa identidad (ver contrato de la Ronda 8). Chequea únicamente si
 * `platformAuthStore` tiene una key guardada; no valida que la key sea
 * REALMENTE correcta (eso ya lo hace `platformAdmin.api.ts` en cada
 * request, limpiando la key en 401/403) -- solo evita que se renderice la
 * tabla de tenants sin haber pasado nunca por el login.
 */
import type { ReactNode } from 'react'
import { Navigate } from 'react-router-dom'
import { usePlatformAuthStore } from '../store/platformAuthStore'

interface PlatformAuthGuardProps {
  children: ReactNode
}

export function PlatformAuthGuard({ children }: PlatformAuthGuardProps) {
  const key = usePlatformAuthStore((s) => s.key)

  if (!key) {
    return <Navigate to="/plataforma/login" replace />
  }

  return <>{children}</>
}
