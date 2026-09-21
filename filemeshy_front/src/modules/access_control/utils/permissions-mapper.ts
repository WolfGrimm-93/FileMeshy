/**
 * Validador y gestor de permisos para el frontend.
 *
 * FILOSOFÍA: El frontend NO debe ser inteligente con permisos.
 *
 *   Backend envía  → permisos en formato canónico (resource.action)
 *   Backend decide → quién tiene qué permiso (toda la lógica)
 *   Frontend hace  → validación + almacenamiento + consulta
 *
 * PROHIBIDO EN ESTE ARCHIVO:
 *   - Mapear formatos (OAuth → custom, legacy → custom, etc.)
 *   - Inferir permisos (write → edit, create → edit, etc.)
 *   - Aceptar permisos del backend sin validación
 *   - Deducir lógica de negocio desde los permisos
 *
 * PERMITIDO:
 *   - Validación contra whitelist (VALID_PERMISSIONS)
 *   - Normalización (string[] → Set)
 *   - Consulta simple (has, hasAll, hasAny)
 *
 * SINCRONIZACIÓN:
 *   VALID_PERMISSIONS se carga dinámicamente desde GET /permissions/available
 *   al iniciar la sesión (ver loadValidPermissionsFromAPI).
 *   El Set estático de abajo es el FALLBACK usado si la API no está disponible.
 *   Al agregar permisos nuevos al backend, agregar también al fallback.
 *
 *   Archivos que deben mantenerse en sync con CANONICAL_PERMISSIONS del backend:
 *     - Este archivo (fallback estático)
 *     - src/app/routes/routes.config.ts (objeto Permission)
 */

/**
 * Fallback estático de permisos válidos.
 * Se usa si GET /permissions/available falla o aún no ha respondido.
 *
 * ⚠️ Al agregar permisos al backend (CANONICAL_PERMISSIONS + migración),
 *    agregar también aquí para mantener el fallback actualizado.
 */
const VALID_PERMISSIONS = new Set<string>([
  // Dashboard
  'dashboard.view',

  // Archivos
  'files.view',
  'files.upload',
  'files.download',
  'files.delete',
  'files.rename',
  'files.move',

  // Carpetas
  'folders.create',
  'folders.view',
  'folders.delete',
  'folders.rename',
  'folders.move',

  // Compartir
  'shares.create',
  'shares.revoke',
  'shares.manage',

  // Usuarios
  'users.view',
  'users.create',
  'users.edit',
  'users.delete',
  'users.manage_roles',

  // Configuración
  'settings.view',
  'settings.edit_email',
  'settings.edit_system',

  // Workspace (config de "empresa" conservada como base de organización)
  'workspace.manage',

  // Logs de auditoría
  'logs.view',

  // Acceso administrativo
  'admin.manage',

  // Permisos (catálogo + asignación rol<->permiso)
  'permissions.manage',

  // Cuotas de almacenamiento por usuario
  'storage_quotas.view',
  'storage_quotas.manage',

  // Backups (Postgres + MinIO)
  'backups.view',
])

/**
 * Normaliza permisos: valida y guarda en Set para búsqueda rápida.
 * 
 * ✅ SIN mapeos (backend ya hizo eso)
 * ✅ SIN inferencias (write ≠ edit, es responsabilidad del backend)
 * ✅ SIN aceptación de desconocidos (rechaza permisos inválidos)
 * 
 * @param backendPermissions - Array de permisos recibidos del backend
 * @returns Set de permisos válidos normalizados
 */
export function normalizePermissions(backendPermissions: string[]): Set<string> {
  const normalized = new Set<string>()
  const invalidPermissions: string[] = []

  for (const perm of backendPermissions) {
    if (VALID_PERMISSIONS.has(perm)) {
      normalized.add(perm)
    } else {
      invalidPermissions.push(perm)
    }
  }
  if (invalidPermissions.length > 0) {
    console.error(
      `⚠️ ${invalidPermissions.length} permisos inválidos encontrados:`,
      invalidPermissions
    )
  }

  return normalized
}

/**
 * Verifica si el usuario tiene un permiso específico.
 * 
 * @param userPermissions - Set de permisos del usuario (normalizado)
 * @param requiredPermission - Permiso a verificar
 * @returns true si el usuario tiene el permiso
 * 
 * @example
 * hasPermission(userPerms, 'files.view')    // ✅
 * hasPermission(userPerms, 'files.invalid') // ❌
 */
export function hasPermission(
  userPermissions: Set<string>,
  requiredPermission: string
): boolean {
  return userPermissions.has(requiredPermission)
}

/**
 * Verifica si el usuario tiene TODOS los permisos requeridos.
 * 
 * @param userPermissions - Set de permisos del usuario
 * @param requiredPermissions - Array de permisos requeridos
 * @returns true si tiene todos
 * 
 * @example
 * hasAllPermissions(userPerms, ['files.view', 'files.upload']) // ✅ si tiene ambos
 */
export function hasAllPermissions(
  userPermissions: Set<string>,
  requiredPermissions: string[]
): boolean {
  return requiredPermissions.every((perm) => userPermissions.has(perm))
}

/**
 * Verifica si el usuario tiene ALGUNO de los permisos requeridos.
 * 
 * @param userPermissions - Set de permisos del usuario
 * @param requiredPermissions - Array de permisos requeridos
 * @returns true si tiene al menos uno
 * 
 * @example
 * hasAnyPermission(userPerms, ['admin.manage', 'users.create']) // ✅ si tiene cualquiera
 */
export function hasAnyPermission(
  userPermissions: Set<string>,
  requiredPermissions: string[]
): boolean {
  return requiredPermissions.some((perm) => userPermissions.has(perm))
}

/**
 * Lista todos los permisos válidos (para debugging/admin).
 */
export function getValidPermissions(): string[] {
  return Array.from(VALID_PERMISSIONS).sort()
}

/**
 * Valida si un permiso es válido.
 *
 * @param permission - Permiso a validar
 * @returns true si es válido en formato canónico
 */
export function isValidPermission(permission: string): boolean {
  return VALID_PERMISSIONS.has(permission)
}

// BUG DE REVISIÓN CORREGIDO (verificación Docker+Playwright, sección 5): `loadValidPermissionsFromAPI`
// se llamaba fire-and-forget (sin `await`) DESPUÉS de normalizar/guardar al usuario
// (`authStore.setUser`/`login`, que valida contra `VALID_PERMISSIONS` de forma SÍNCRONA) --
// para el momento en que la respuesta de `/permissions/available` llegaba, el usuario ya había
// sido normalizado contra el fallback estático desactualizado y un permiso válido pero nuevo
// (ej. `storage_quotas.manage`) quedaba descartado para el resto de la sesión, sin que un
// refresh posterior del catálogo lo recuperara -- solo cerrar sesión y volver a entrar lo
// arreglaba. Además, ni `loaders.ts::authLoader` (el ÚNICO lugar que llama a /auth/me en cada
// navegación protegida, según su propio docstring) ni `AuthProvider.tsx` (que restaura el
// token pero deliberadamente NO arma el usuario) llamaban a esta función -- en la práctica el
// catálogo real nunca se cargaba en el flujo de arranque normal (F5 / navegación directa a una
// URL), solo en un login interactivo por formulario.
//
// Fix: `loadValidPermissionsFromAPI` ahora cachea la promesa in-flight/resuelta -- el PRIMER
// llamador de la sesión de pestaña dispara el fetch real; cualquier llamador posterior (cada
// navegación subsiguiente) obtiene la misma promesa ya resuelta, sin costo de red repetido. Los
// call-sites (`authLoader`, `useAuth.ts::login/restoreSession`) ahora la esperan ANTES de
// normalizar, así el catálogo real de la BD manda desde el primer render posible en vez de
// depender de una carrera contra la validación síncrona.
let permissionsCatalogPromise: Promise<void> | null = null

/**
 * Carga los permisos válidos desde el backend y actualiza el Set en memoria.
 *
 * Debe esperarse (`await`) ANTES de normalizar/guardar al usuario (ver
 * `loaders.ts::authLoader` y `useAuth.ts::login/restoreSession`) -- si un caller la llama
 * fire-and-forget, un permiso válido pero recién agregado al backend puede descartarse por la
 * carrera descrita arriba. Si falla, VALID_PERMISSIONS conserva el fallback estático y el
 * próximo llamador (siguiente navegación) puede reintentar -- el fallo no se cachea.
 *
 * Esto evita que se tenga que actualizar el fallback estático manualmente
 * cada vez que se agregan permisos nuevos al backend.
 */
export function loadValidPermissionsFromAPI(): Promise<void> {
  if (!permissionsCatalogPromise) {
    permissionsCatalogPromise = (async () => {
      try {
        // Importación dinámica para evitar dependencia circular con axiosInstance
        const { default: axiosInstance } = await import('@/shared/config/axios')
        const resp = await axiosInstance.get<{
          data: { available: Record<string, string[]> }
        }>('/permissions/available')

        const available = resp.data?.data?.available
        if (!available || typeof available !== 'object') return

        // Reconstruir el Set con los permisos recibidos de la BD
        VALID_PERMISSIONS.clear()
        for (const [resource, actions] of Object.entries(available)) {
          for (const action of actions) {
            VALID_PERMISSIONS.add(`${resource}.${action}`)
          }
        }
      } catch {
        // Silencioso: si falla, el fallback estático ya está cargado -- pero NO cachear el
        // fallo, para que el próximo llamador pueda reintentar.
        permissionsCatalogPromise = null
      }
    })()
  }
  return permissionsCatalogPromise
}

