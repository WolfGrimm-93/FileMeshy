/**
 * Protected Layout Component
 * Layout para rutas privadas que requieren autenticación
 */

import { useEffect } from 'react'
import { Outlet, useNavigate, useLoaderData } from 'react-router-dom'
import MainLayout from './MainLayout'
import { useSEO } from '../hooks/useSEO'
import { useInactivityLogout } from '@/modules/auth/hooks/useInactivityLogout'
import type { LoaderData } from '../routes/loaders'

// Timeouts configurables desde Privacidad
const INACTIVITY_TIMEOUT = 30  // minutos
const MAX_SESSION_HOURS = 8    // horas

export function ProtectedLayout() {
  const navigate = useNavigate()
  const loaderData = useLoaderData() as LoaderData

  // Aplicar SEO automático
  useSEO()

  // Auto-logout por inactividad + duración máxima de sesión
  useInactivityLogout(INACTIVITY_TIMEOUT, MAX_SESSION_HOURS)

  useEffect(() => {
    // Verificar si hay datos del loader
    if (!loaderData?.user) {
      navigate('/login', { replace: true })
    }
  }, [loaderData, navigate])

  if (!loaderData?.user) {
    return null
  }

  return (
    <MainLayout>
      <Outlet />
    </MainLayout>
  )
}
