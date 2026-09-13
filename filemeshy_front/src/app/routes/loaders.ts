/**
 * Route Loaders para React Router v7
 * Pre-carga y validación de datos antes de renderizar componentes
 */

import { redirect } from 'react-router-dom'
import { authService, type User } from '@/modules/auth/services/auth.service'
import { useAuthStore } from '@/modules/auth/store/authStore'
import { useModulesStore } from '@/shared/feature-flags/modulesStore'
import { loadValidPermissionsFromAPI } from '@/modules/access_control/utils/permissions-mapper'
import { hasPermission, type PermissionType } from './routes.config'

// ==================== TIPOS ====================

export interface LoaderData {
  user?: User
  permissions?: PermissionType[]
  [key: string]: unknown
}

// ==================== AUTH LOADER ====================

/**
 * Loader para verificar autenticación
 * Usado en rutas privadas
 * 
 * IMPORTANTE: Este es el ÚNICO lugar que llama a /auth/me
 * AuthProvider solo restaura la sesión (refresca token con cookie)
 */
export async function authLoader(): Promise<LoaderData> {
  // IMPORTANTE: Esperar a que termine la restauración de sesión
  // Esto asegura que el token ha sido refrescado con la cookie
  await authService.waitForSessionRestore()
  
  // Verificar si hay token en memoria (NO desde el store)
  // Porque en este punto, el store aún no tiene user (se carga con getCurrentUser)
  const hasAccessToken = !!authService.getAccessToken()
  
  if (!hasAccessToken) {
    // Redirigir a login si no hay token
    console.log('❌ No hay token en memoria, redirigiendo a login')
    throw redirect('/login')
  }

  // Obtener usuario actual - Llamada SINGLETON que se ejecuta UNA SOLA VEZ
  // Incluso si múltiples loaders llaman esto, solo se hace una petición a /auth/me
  //
  // BUG DE REVISIÓN CORREGIDO (verificación Docker+Playwright, sección 5): este loader es el
  // ÚNICO lugar que arma al usuario en el flujo normal de arranque (AuthProvider deliberadamente
  // no lo hace) -- antes NUNCA esperaba (ni llamaba) a loadValidPermissionsFromAPI(), así que
  // store.setUser() de abajo siempre normalizaba contra el fallback estático de
  // permissions-mapper.ts, sin importar qué agregara el backend a la BD. En paralelo con
  // getCurrentUser() -- ver permissions-mapper.ts::loadValidPermissionsFromAPI, cachea la
  // promesa por pestaña, así que solo pesa en la primera navegación de la sesión.
  const [user] = await Promise.all([
    authService.getCurrentUser(),
    loadValidPermissionsFromAPI(),
  ])

  if (!user) {
    await authService.logout()
    throw redirect('/login')
  }

  // Actualizar store con el usuario (para que los componentes lo vean)
  const store = useAuthStore.getState()
  const authUser = {
    id: user.id,
    first_name: user.first_name,
    last_name: user.last_name,
    email: user.email,
    role: user.role,
    permissions: new Set(user.permissions || []),
    avatar: user.avatar,
    theme: user.theme,
  }
  store.setUser(authUser)

  return {
    user,
    permissions: (user.permissions || []) as PermissionType[],
  }
}

// ==================== PUBLIC LOADER ====================

/**
 * Loader para rutas públicas restringidas (login)
 * Redirige al dashboard si ya está autenticado
 */
export async function publicLoader(): Promise<null> {
  // Esperar restauración de sesión (igual que authLoader)
  await authService.waitForSessionRestore()

  // Verificar token en memoria (fuente de verdad, no el store)
  const hasAccessToken = !!authService.getAccessToken()

  if (hasAccessToken) {
    throw redirect('/dashboard')
  }

  return null
}

/**
 * Loader para reset-password
 * Redirige al dashboard si ya está autenticado (no necesita resetear)
 */
export async function resetPasswordLoader(): Promise<null> {
  await authService.waitForSessionRestore()
  if (authService.getAccessToken()) {
    throw redirect('/dashboard')
  }
  return null
}

// ==================== PERMISSION LOADER ====================

/**
 * Factory para crear loaders que verifican permisos
 * @param requiredPermissions - Array de permisos requeridos
 */
export function requirePermissions(requiredPermissions: PermissionType[]) {
  return async function permissionLoader(): Promise<LoaderData> {
    // Primero verificar autenticación
    const authData = await authLoader()
    
    const userPermissions = authData.permissions || []
    
    // Verificar permisos
    if (!hasPermission(requiredPermissions, userPermissions)) {
      // Redirigir a página de no autorizado
      throw redirect('/unauthorized')
    }

    return authData
  }
}

// ==================== DATA LOADERS ====================

/**
 * Loader para Dashboard
 * Pre-carga estadísticas básicas
 */
export async function dashboardLoader(): Promise<LoaderData> {
  const authData = await authLoader()
  
  // Aquí podrías pre-cargar datos del dashboard
  // Por ejemplo: estadísticas, notificaciones, etc.
  
  return {
    ...authData,
    // stats: await fetchDashboardStats(),
  }
}

/**
 * Loader genérico para rutas con permisos
 * @param permissions - Permisos requeridos
 */
export function createProtectedLoader(permissions: PermissionType[]) {
  return async function protectedLoader(): Promise<LoaderData> {
    return requirePermissions(permissions)()
  }
}

// ==================== MODULE LOADER (Iniciativa A) ====================

/**
 * Loader para rutas privadas de módulos activables/desactivables (ej.
 * Integraciones, Soporte). Verifica auth +
 * permisos (igual que requirePermissions) y además el flag del módulo en
 * useModulesStore -- si está apagado, redirige a /modulo-no-disponible
 * en vez de renderizar la página (el 403 real ya lo hace el backend).
 */
export function requireModule(moduleKey: string, requiredPermissions: PermissionType[] = []) {
  return async function moduleLoader(): Promise<LoaderData> {
    const authData = await authLoader()

    if (requiredPermissions.length > 0 && !hasPermission(requiredPermissions, authData.permissions || [])) {
      throw redirect('/unauthorized')
    }

    if (!useModulesStore.getState().isModuleEnabled(moduleKey)) {
      throw redirect('/modulo-no-disponible')
    }

    return authData
  }
}

/**
 * Igual que requireModule pero sin exigir autenticación -- para rutas públicas
 * de un módulo activable (ej. /soporte, formulario público de tickets).
 */
export function requireModulePublic(moduleKey: string) {
  return async function publicModuleLoader(): Promise<null> {
    if (!useModulesStore.getState().isModuleEnabled(moduleKey)) {
      throw redirect('/modulo-no-disponible')
    }
    return null
  }
}

// ==================== ERROR LOADER ====================

/**
 * Loader que siempre falla (para testing de error boundaries)
 */
export async function errorLoader(): Promise<never> {
  throw new Error('This is a test error from loader')
}

// ==================== HELPER FUNCTIONS ====================

/**
 * Extrae el usuario del loader data
 */
export function getUserFromLoader(data: LoaderData) {
  return data.user
}

/**
 * Extrae los permisos del loader data
 */
export function getPermissionsFromLoader(data: LoaderData): PermissionType[] {
  return data.permissions || []
}
