/**
 * Hook personalizado de autenticación
 * 
 * Integra authService + authStore para una API simple y consistente
 * Maneja auto-refresh, sesión persistente y limpieza
 */
import { useCallback } from 'react'
import { useAuthStore, type AuthUser } from '../store/authStore'
import { authService, MAX_SESSION_SLOTS, type LoginCredentials, type LoginResult, type LoginResponse } from '../services/auth.service'
import { loadValidPermissionsFromAPI } from '@/modules/access_control/utils/permissions-mapper'

export const useAuth = () => {
  const store = useAuthStore()
  const { user, isAuthenticated, hasPermission, hasRole, pausedUsers } = store

  /**
   * Iniciar sesión
   */
  const login = useCallback(async (credentials: LoginCredentials): Promise<LoginResult> => {
    try {
      const response = await authService.login(credentials)

      // Si el backend pide 2FA, retornar sin guardar en store
      if ('requires_2fa' in response) {
        return response
      }

      // BUG DE REVISIÓN CORREGIDO (verificación Docker+Playwright, sección 5): antes se llamaba
      // fire-and-forget DESPUÉS de setLoginRef -- el usuario ya quedaba normalizado (y un
      // permiso válido pero recién agregado al backend, descartado) contra el fallback estático
      // ANTES de que esta respuesta llegara, y nada volvía a re-normalizarlo después. Esperarla
      // ANTES de armar/guardar authUser asegura que store.login() (que normaliza de forma
      // síncrona) ya vea el catálogo real de la BD. Cacheada por pestaña (ver
      // permissions-mapper.ts), así que si authLoader ya la disparó antes, esto no repite la
      // llamada de red.
      await loadValidPermissionsFromAPI()

      // Login normal: guardar usuario en store
      const authUser = {
        id: response.user.id,
        first_name: response.user.first_name,
        last_name: response.user.last_name,
        email: response.user.email,
        role: response.user.role,
        permissions: new Set(response.user.permissions),
        avatar: response.user.avatar,
        theme: response.user.theme,
      }
      useAuthStore.getState().login(authUser)

      return response
    } catch (error) {
      console.error('❌ Error en login:', error)
      throw error
    }
  }, []) // Sin dependencias - usa useAuthStore.getState() (acciones estables del store)

  /**
   * Cerrar sesión
   */
  const logout = useCallback(async () => {
    try {
      // Limpiar auto-refresh y notificar backend
      await authService.logout()
    } finally {
      // Limpiar store siempre
      useAuthStore.getState().logout()
    }
  }, []) // Sin dependencias - usa useAuthStore.getState() (acciones estables del store)

  /**
   * Cambiar de usuario (temporal), sin cerrar la sesión actual.
   *
   * Pausa la sesión activa (queda intacta, recuperable) y loguea al usuario
   * nuevo encima -- ni logout() ni cleanupAllExceptSettings() corren, así que
   * los filtros / lo que sea que estaba haciendo el usuario anterior no se
   * pierde. Si el login del usuario nuevo falla (credenciales
   * incorrectas, 2FA no soportado acá), se deshace el pause automáticamente
   * y la sesión original queda como si nada hubiera pasado.
   */
  const switchUser = useCallback(async (credentials: LoginCredentials): Promise<LoginResponse> => {
    const previousUser = useAuthStore.getState().user
    if (!previousUser) {
      throw new Error('No hay una sesión activa para pausar')
    }

    // Tope de slots apilados (0 = base, hasta MAX_SESSION_SLOTS - 1 = última
    // pausada admitida) -- el backend lo rechaza igual con 400 si se lo
    // salteara, pero este chequeo evita mandar un login que sabemos que va a
    // fallar y da un error legible en la UI en vez de un 400 crudo.
    if (authService.getActiveSlot() >= MAX_SESSION_SLOTS - 1) {
      throw new Error(
        `Ya alcanzaste el máximo de ${MAX_SESSION_SLOTS} sesiones apiladas. Volvé a alguna antes de cambiar de usuario de nuevo.`
      )
    }

    // Async: espera cualquier refresh en vuelo del usuario que se pausa,
    // para que esa respuesta tardía no pise el token/cookie del usuario
    // nuevo cuando resuelva (hallazgo de auditoría, ver auth.service.ts).
    await authService.pauseCurrentSession()
    useAuthStore.getState().pushPausedUser(previousUser)
    const epochAfterPause = authService.getSessionEpoch()

    // Antes de que authService.login() resuelva con éxito, todavía no se
    // comprometió nada en el backend -- deshacer el pause es 100% seguro. Una
    // vez que el login del usuario nuevo tuvo éxito (su cookie/token ya están
    // escritos), "deshacer" dejaría la UI mostrando al usuario viejo con la
    // sesión real ya siendo la del nuevo -- peor que no deshacer nada.
    let committed = false
    const undoPause = () => {
      if (committed) return
      // Si otra operación (ej. un "Volver" hecho a mano mientras este login
      // seguía en vuelo) ya movió la pila, no pisarla con un segundo resume.
      if (authService.getSessionEpoch() !== epochAfterPause) return
      authService.resumePreviousSession()
      useAuthStore.getState().popPausedUser()
    }

    try {
      const response = await authService.login(credentials)

      if ('requires_2fa' in response) {
        // No soportado en el cambio rápido de usuario (v1) -- esa cuenta
        // necesita el login completo de /login, con su paso de TOTP.
        // undoPause() lo hace el catch de abajo -- no duplicarlo acá.
        throw new Error('Esa cuenta tiene verificación en dos pasos activada. Cerrá sesión e iniciá sesión normal para usarla.')
      }

      committed = true

      // A partir de acá el backend YA autenticó al usuario nuevo -- no hay
      // vuelta atrás segura, así que nada de lo que sigue puede dejar sin
      // actualizar el store (eso reproduciría el hallazgo original por otra
      // vía: token real de B, store todavía mostrando a A). loadValidPermissionsFromAPI()
      // ya se traga sus propios errores (cae al catálogo estático), pero se
      // envuelve igual por las dudas -- que falle no debe frenar el swap.
      try {
        await loadValidPermissionsFromAPI()
      } catch {
        // No bloqueante -- ver comentario arriba.
      }

      if (authService.getSessionEpoch() !== epochAfterPause) {
        // La sesión activa cambió por otra vía mientras este login estaba en
        // curso (ej. alguien ya hizo "Volver" antes de que este terminara) --
        // no pisar lo que sea que haya quedado activo ahora.
        return response
      }

      const authUser: AuthUser = {
        id: response.user.id,
        first_name: response.user.first_name,
        last_name: response.user.last_name,
        email: response.user.email,
        role: response.user.role,
        permissions: new Set(response.user.permissions),
        avatar: response.user.avatar,
        theme: response.user.theme,
      }
      useAuthStore.getState().login(authUser)

      return response
    } catch (error) {
      undoPause()
      throw error
    }
  }, [])

  /**
   * Obtener usuario actual del backend
   */
  const fetchCurrentUser = useCallback(async () => {
    try {
      const user = await authService.getCurrentUser()
      
      // Mapear usuario del backend al formato del store
      const authUser = {
        id: user.id,
        first_name: user.first_name,
        last_name: user.last_name,
        email: user.email,
        role: user.role,
        permissions: new Set(user.permissions),
        avatar: user.avatar,
        theme: user.theme,
      }
      
      useAuthStore.getState().login(authUser)
      return user
    } catch (error) {
      console.error('Error al obtener usuario:', error)
      useAuthStore.getState().logout()
      throw error
    }
  }, []) // Sin dependencias - usa useAuthStore.getState() (acciones estables del store)

  /**
   * Volver a la sesión pausada más reciente (la que quedó debajo al usar
   * switchUser). El usuario restaurado se toma del caché local (no hace
   * falta pedirlo de nuevo), pero SÍ hay una llamada de red: cerrar la
   * sesión temporal que se abandona en el backend antes de restaurar la
   * pausada -- ver closeActiveSessionOnBackend en auth.service.ts para el
   * motivo (evita que esa sesión quede viva y pueda "resucitar" sola vía
   * un refresh futuro, en web).
   */
  const returnToPreviousUser = useCallback(async (): Promise<boolean> => {
    if (!authService.hasPausedSession()) return false

    await authService.closeActiveSessionOnBackend()

    const restored = authService.resumePreviousSession()
    if (!restored) return false

    const previousUser = useAuthStore.getState().popPausedUser()
    if (previousUser) {
      useAuthStore.getState().login(previousUser)
    } else {
      // No debería pasar (pause y push de usuario siempre van juntos), pero
      // por las dudas: sin el usuario cacheado, pedirlo de nuevo al backend.
      await fetchCurrentUser()
    }
    return true
  }, [fetchCurrentUser])

  /**
   * Refrescar token manualmente (normalmente automático)
   */
  const refreshToken = useCallback(async () => {
    try {
      await authService.refreshToken()
    } catch (error) {
      console.error('Error al refrescar token:', error)
      // Si falla, hacer logout
      useAuthStore.getState().logout()
      throw error
    }
  }, []) // Sin dependencias - usa useAuthStore.getState() (acciones estables del store)

  /**
   * Restaurar sesión al cargar la app
   * Si hay un token válido en memoria o cookie, obtener usuario
   */
  const restoreSession = useCallback(async () => {
    try {
      // Usar el nuevo método centralizado de authService
      const restored = await authService.restoreSession()
      
      if (restored) {
        // Si se restauró exitosamente, obtener usuario -- en paralelo con el catálogo de
        // permisos válidos, y esperar AMBOS antes de normalizar (mismo bug/fix que login()
        // arriba y loaders.ts::authLoader -- ver comentario ahí).
        const [user] = await Promise.all([
          authService.getCurrentUser(),
          loadValidPermissionsFromAPI(),
        ])
        const authUser = {
          id: user.id,
          first_name: user.first_name,
          last_name: user.last_name,
          email: user.email,
          role: user.role,
          permissions: new Set(user.permissions),
          avatar: user.avatar,
          theme: user.theme,
        }
        useAuthStore.getState().login(authUser)

        console.log('✅ Sesión restaurada y usuario cargado')
      } else {
        console.log('ℹ️ No hay sesión para restaurar')
        useAuthStore.getState().logout()
      }
    } catch (error) {
      console.log('❌ Error restaurando sesión:', error)
      useAuthStore.getState().logout()
    }
  }, []) // Sin dependencias - usa useAuthStore.getState()

  return {
    // Estado
    user,
    isAuthenticated,

    // Métodos
    login,
    logout,
    refreshToken,
    fetchCurrentUser,
    restoreSession,

    // Cambio de usuario temporal (ver switchUser/returnToPreviousUser arriba)
    switchUser,
    returnToPreviousUser,
    pausedUsers,
    hasPausedSession: pausedUsers.length > 0,

    // Helpers de permisos
    hasPermission,
    hasRole,
  }
}
