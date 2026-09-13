/**
 * Public Layout Component
 * Layout para rutas públicas (login, reset password, etc.)
 */

import { Outlet } from 'react-router-dom'
import { useSEO } from '../hooks/useSEO'

export function PublicLayout() {
  // Aplicar SEO automático
  useSEO()

  return <Outlet />
}
