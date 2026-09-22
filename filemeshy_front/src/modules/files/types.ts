/**
 * Tipos del módulo de Archivos — mirror exacto del contrato de backend
 * (ver filemeshy_back, mismo contrato acordado en paralelo).
 */

export interface TagOut {
  id: string
  name: string
  color: string | null
}

export interface FolderOut {
  id: string
  name: string
  parent_id: string | null
  owner_id: string
  created_at: string
  updated_at: string
  deleted_at: string | null
  is_favorite: boolean
  tags: TagOut[]
}

export interface FileOut {
  id: string
  name: string
  folder_id: string | null
  owner_id: string
  size_bytes: number
  mime_type: string
  created_at: string
  updated_at: string
  deleted_at: string | null
  is_favorite: boolean
  tags: TagOut[]
  /**
   * Ronda 6 -- solo viene con `GET /files?q=...` y una búsqueda activa, para
   * distinguir un resultado que matcheó por CONTENIDO del archivo (no solo
   * por nombre) y así no confundir al usuario con un nombre que no tiene
   * relación aparente con lo buscado. `undefined`/`null` cuando no hay
   * búsqueda activa o el backend todavía no lo soporta -- la UI debe
   * degradar bien en ese caso (sin mostrar ningún indicador).
   */
  matched_by?: 'name' | 'content' | 'both'
  /**
   * Ronda 9 (subida resumable) -- estado del escaneo antivirus asíncrono
   * para archivos subidos por el camino nuevo de
   * `POST /uploads/{session_id}/complete`. `undefined` en archivos subidos
   * por el camino viejo (`POST /files/upload`, escanea SÍNCRONO desde
   * Ronda 7, nunca crea el `File` en estado distinto de 'clean') -- la UI
   * debe tratar `undefined` igual que `'clean'` (nunca bloquear ni mostrar
   * "procesando" para archivos que no lo tienen).
   *
   * OJO 1 (verificado leyendo `filemeshy_back/app/files/repository.py`,
   * `CRUDFile.get`/`get_active` -- código real de los otros 2 agentes de
   * esta ronda): el filtro `scan_status == 'clean'` es GLOBAL para toda
   * lectura por id, `GET /files/{id}` incluido -- ni el propio dueño puede
   * leer un archivo 'pending'/'infected'/'scan_failed' por ahí, le da 404
   * igual que si no existiera. Por eso la señal PRIMARIA para resolver
   * "procesando" no es pollear ese endpoint (un 404 ahí es ambiguo, no
   * distingue "sigue escaneando" de "lo marcaron infectado"), sino las
   * notificaciones que crea `app/worker/tasks/av_scan.py` al resolver
   * (`extra_data.file_id` + `severity`) -- ver
   * `store/uploadsStore.ts::pollProcessingItems`, que además usa
   * `GET /files/{id}` como señal secundaria (solo puede confirmar 'clean',
   * nunca "infectado").
   *
   * OJO 2: a esta fecha `app/files/schemas.py::FileOut` (el schema Pydantic
   * real) TODAVÍA no declara este campo -- aunque `complete_upload()` cree
   * el `File` con `scan_status='pending'`, la respuesta de `/complete` lo va
   * a omitir del JSON hasta que se agregue ahí (haciendo que hoy, en la
   * práctica, todo archivo multipart complete "directo a `done`" en vez de
   * mostrar "procesando" -- degradación segura gracias al `undefined` de
   * arriba, pero vale la pena que quede corregido en el backend).
   *
   * `'scan_failed'` (visto en `av_scan.py`) -- el AV no pudo confirmar tras
   * varios reintentos (servicio caído, no necesariamente malicioso). Queda
   * en el union por completitud del contrato, aunque -- mismo OJO 1 de
   * arriba -- nunca llega 200 con este valor desde `GET /files/{id}`; se
   * resuelve por notificación (`severity: 'warning'`).
   */
  scan_status?: 'pending' | 'clean' | 'infected' | 'scan_failed'
}

/**
 * Ronda 4 -- una versión histórica de un archivo (`GET /files/{id}/versions`).
 * `created_by_email` viene `null` cuando el backend no puede resolver el
 * usuario que la subió (ej. usuario borrado), mismo criterio que otros
 * campos "resueltos" opcionales del contrato (ver `shared_by_email` en
 * `ShareOut`).
 */
export interface FileVersionOut {
  id: string
  version_number: number
  size_bytes: number
  mime_type: string
  created_at: string
  created_by_email: string | null
}

export interface BreadcrumbItem {
  id: string
  name: string
}

export interface DirectoryListing {
  folders: FolderOut[]
  files: FileOut[]
  breadcrumb: BreadcrumbItem[]
}

/** Permiso otorgado por un share -- los links públicos son siempre 'view' (no aplica selector ahí). */
export type SharePermission = 'view' | 'edit'

export interface ShareOut {
  id: string
  /** `null` en un share dirigido a un usuario (Ronda 3) -- nunca tiene link público. */
  token: string | null
  file_id: string | null
  folder_id: string | null
  created_by_id: string
  expires_at: string | null
  revoked_at: string | null
  created_at: string
  is_active: boolean
  permission: SharePermission
  /** Nunca se devuelve la password ni su hash -- solo si el share tiene una seteada. */
  has_password: boolean
  /** No nulo cuando el share fue dirigido a un usuario puntual (no es un link público). */
  shared_with_user_id: string | null
  shared_with_email: string | null
  /**
   * Estos tres SIEMPRE vienen `null` salvo en `GET /shares/with-me` -- ahí el
   * backend los resuelve (nombre del recurso + email de quien compartió,
   * ver `_share_to_out(..., with_resource_info=True)` en filemeshy_back)
   * porque esa pantalla necesita mostrar algo más que UUIDs pelados. El
   * backend NO tiene un `shared_by_name` -- solo el email.
   */
  resource_name: string | null
  resource_type: 'file' | 'folder' | null
  shared_by_email: string | null
}

/**
 * Ronda 3 -- shape que usa el frontend para listar `GET /shares/with-me` en
 * `SharedWithMePage`. El backend responde `ShareOut[]` crudo (con `id`, no
 * `share_id`, y sin garantía de tipos en los campos opcionales de arriba) --
 * `shares.service.ts::listSharedWithMe()` lo mapea explícitamente a este
 * tipo, nunca se consume el `ShareOut` crudo directo en la UI.
 */
export interface SharedWithMeItem {
  /** Mapeado desde `ShareOut.id` -- el backend nunca manda un campo `share_id`. */
  share_id: string
  resource_type: 'file' | 'folder'
  resource_name: string
  permission: SharePermission
  shared_by_email: string
  created_at: string
  expires_at: string | null
}

export interface PublicShareFile {
  type: 'file'
  name: string
  size_bytes: number
  mime_type: string
  download_url: string
}

export interface PublicShareFolder {
  type: 'folder'
  name: string
  folder_id: string
  folders: FolderOut[]
  files: FileOut[]
}

export type PublicShareResponse = PublicShareFile | PublicShareFolder
