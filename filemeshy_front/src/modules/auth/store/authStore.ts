/**
 * Store de autenticación con Zustand
 * 
 * SEGURIDAD:
 * - NO persiste datos sensibles en localStorage (token, user)
 * - Token almacenado solo en memoria (auth.service.ts)
 * - Refresh token en httpOnly cookie (gestionado por backend)
 * - Solo persiste flags de sesión para mejorar UX
 * 
 * PERMISOS:
 * - Backend envía permisos ya NORMALIZADOS (formato canónico)
 * - Frontend: solo almacena en Set y consulta
 * - SIN mapeos, SIN inferencias
 */
import { create } from 'zustand'
import { normalizePermissions } from '@/modules/access_control/utils/permissions-mapper'

// Usuario del store (mapea desde User del backend)
export interface AuthUser {
  id: string  // UUID v7 (Backend usa UUID, no integer)
  first_name: string
  last_name: string
  email: string
  role: string
  permissions: Set<string>  // Permisos normalizados (canónicos)
  avatar?: string
  theme?: 'light' | 'dark' | 'auto'
}

interface AuthState {
  // State (NO persistido)
  user: AuthUser | null
  isAuthenticated: boolean
  initialized: boolean  // Flag para evitar llamadas duplicadas a /auth/me
  // Pila de usuarios pausados por "Cambiar de usuario" (mas reciente = ultimo
  // elemento). Solo guarda los datos para mostrar en el banner/UI -- los
  // tokens de cada uno viven en auth.service.ts, en la pila paralela
  // pausedSessions, mantenida en sync por useAuth.switchUser/returnToPreviousUser.
  pausedUsers: AuthUser[]

  // Actions
  setUser: (user: AuthUser | null) => void
  login: (user: AuthUser) => void
  logout: () => void
  markInitialized: () => void  // Marcar como inicializado
  hasPermission: (permission: string) => boolean
  hasRole: (role: string) => boolean
  getFullName: () => string
  pushPausedUser: (user: AuthUser) => void
  popPausedUser: () => AuthUser | undefined
  clearPausedUsers: () => void
}

export const useAuthStore = create<AuthState>((set, get) => ({
  // Initial state
  user: null,
  isAuthenticated: false,
  initialized: false,  // NO inicializado hasta que se cargue /auth/me
  pausedUsers: [],

  // Actions
  setUser: (user) => {
    if (user) {
      // Normalizar permisos (backend ya los envía canónicos, pero validamos)
      const normalizedPermissions = normalizePermissions(Array.from(user.permissions))
      const userWithNormalizedPermissions = {
        ...user,
        permissions: new Set(normalizedPermissions)
      }
      set({ user: userWithNormalizedPermissions, isAuthenticated: true, initialized: true })
    } else {
      set({ user: null, isAuthenticated: false, initialized: true })
    }
  },
  
  login: (user) => {
    // Normalizar permisos (validación y conversión a Set)
    const normalizedPermissions = normalizePermissions(Array.from(user.permissions))
    const userWithNormalizedPermissions = {
      ...user,
      permissions: new Set(normalizedPermissions)
    }
    set({
      user: userWithNormalizedPermissions, 
      isAuthenticated: true,
      initialized: true 
    })
  },
  
  logout: () =>
    set({
      user: null,
      isAuthenticated: false,
      initialized: true,  // Se sigue considerando inicializado, solo que sin usuario
      // Un logout real cierra todo -- no debe quedar nada para "volver" despues.
      pausedUsers: [],
    }),

  markInitialized: () =>
    set({ initialized: true }),

  pushPausedUser: (user) =>
    set(state => ({ pausedUsers: [...state.pausedUsers, user] })),

  popPausedUser: () => {
    const { pausedUsers } = get()
    if (pausedUsers.length === 0) return undefined
    const last = pausedUsers[pausedUsers.length - 1]
    set({ pausedUsers: pausedUsers.slice(0, -1) })
    return last
  },

  clearPausedUsers: () => set({ pausedUsers: [] }),
  
  hasPermission: (permission) => {
    const { user } = get()
    if (!user) return false
    
    // Super admin tiene todos los permisos
    if (user.permissions.has('admin.manage')) return true
    
    return user.permissions.has(permission)
  },
  
  hasRole: (role) => {
    const { user } = get()
    if (!user) return false
    
    return user.role === role
  },
  
  getFullName: () => {
    const { user } = get()
    if (!user) return ''
    
    return `${user.first_name} ${user.last_name}`.trim()
  },
}))

/**
 * POLÍTICA DE ALMACENAMIENTO:
 * 
 * ✅ EN MEMORIA (este store):
 *    - user: datos del usuario actual
 *    - isAuthenticated: estado de sesión
 * 
 * ✅ EN MEMORIA (auth.service.ts):
 *    - accessToken: token JWT (duración corta: 30 min)
 * 
 * ✅ EN httpOnly COOKIE (backend):
 *    - refreshToken: token para renovar sesión (duración larga: 7 días)
 * 
 * ✅ EN localStorage (solo):
 *    - theme: preferencia de tema (light/dark/auto)
 *    - language: idioma seleccionado
 * 
 * ❌ NUNCA en localStorage:
 *    - tokens, user data, credentials, sensitive data
 */
