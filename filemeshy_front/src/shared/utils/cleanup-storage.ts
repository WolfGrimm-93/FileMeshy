/**
 * Limpieza y migracion de localStorage
 *
 * - Remueve datos antiguos de versiones anteriores
 * - Migra keys sin prefijo al prefijo actual "filemeshy_" -- necesario porque
 *   las cookies (no localStorage) se comparten por dominio SIN distinguir
 *   puerto: en un equipo con otro proyecto corriendo en paralelo en
 *   localhost (otro puerto), un nombre generico como "refresh_token" puede
 *   chocar. Aunque localStorage si se aisla por origen (no tiene ese riesgo),
 *   se namespacea igual para que TODAS las keys de la app sean inconfundibles.
 */

/**
 * Migra keys antiguas sin prefijo a las nuevas con prefijo "filemeshy_".
 * Solo migra si la key nueva no existe aun (evita sobreescribir datos
 * actuales).
 */
export const migrateStorageKeys = () => {
  const keyMigrations: Record<string, string> = {
    // Sin ningun prefijo (muy antiguas)
    'reset_password_email_temp': 'filemeshy_reset_password_email_temp',
    'theme': 'filemeshy_theme',
    'language': 'filemeshy_language',
    // Zustand stores, sin prefijo
    'user-preferences': 'filemeshy_user-preferences',

    // Sin ningun prefijo, encontradas al namespacear todo
    'sidebar-state': 'filemeshy_sidebar_state',
    'config_active_tab': 'filemeshy_config_active_tab',
  }

  let migratedCount = 0

  Object.entries(keyMigrations).forEach(([oldKey, newKey]) => {
    const oldValue = localStorage.getItem(oldKey)
    if (oldValue !== null && localStorage.getItem(newKey) === null) {
      localStorage.setItem(newKey, oldValue)
      localStorage.removeItem(oldKey)
      migratedCount++
    } else if (oldValue !== null) {
      // La nueva key ya existe, solo limpiar la vieja
      localStorage.removeItem(oldKey)
    }
  })

  if (migratedCount > 0) {
    console.log(`Migracion: ${migratedCount} keys migradas al prefijo filemeshy_`)
  }
}

export const cleanupOldStorage = () => {
  // Primero migrar keys al nuevo formato
  migrateStorageKeys()

  // Lista de keys antiguas que deben ser removidas
  const keysToRemove = [
    'auth-storage',           // Zustand persist antiguo
    'filemeshy_token',        // Token antiguo
    'filemeshy_refresh_token', // Refresh token antiguo
    'user',                   // Usuario antiguo
    'token',                  // Token generico
    'refresh_token',          // Refresh token generico
    'cart-storage',           // Carrito antiguo con persist
    'resetPasswordState',     // Estado de reset password (sesion)
    'auth-store',             // Auth store antiguo
  ]

  let removedCount = 0

  keysToRemove.forEach(key => {
    if (localStorage.getItem(key)) {
      localStorage.removeItem(key)
      removedCount++
    }
  })

  if (removedCount > 0) {
    console.log(`Limpieza: Se removieron ${removedCount} items antiguos de localStorage`)
  }
}

/**
 * Limpiar localStorage EXCEPTO tema, idioma y el device_id del equipo
 * Al logout: limpia datos sensibles pero mantiene preferencias de usuario.
 * filemeshy_device_id se preserva porque identifica al equipo fisico
 * (no al usuario que inicio sesion) ante el backend.
 */
export const cleanupAllExceptSettings = () => {
  // Guardar las preferencias que queremos mantener
  const theme = localStorage.getItem('filemeshy_theme')
  const language = localStorage.getItem('filemeshy_language')
  const deviceId = localStorage.getItem('filemeshy_device_id')

  // Limpiar todo
  localStorage.clear()

  // Restaurar solo las preferencias
  if (theme) localStorage.setItem('filemeshy_theme', theme)
  if (language) localStorage.setItem('filemeshy_language', language)
  if (deviceId) localStorage.setItem('filemeshy_device_id', deviceId)

  console.log('localStorage limpio. Preferencias mantenidas')
}
