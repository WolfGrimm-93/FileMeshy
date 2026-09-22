/**
 * Persistencia de sesiones de subida resumable en IndexedDB.
 *
 * Por qué IndexedDB y no localStorage: localStorage tiene límites chicos
 * (~5-10MB totales del origen) y es síncrono (bloquea el hilo principal) --
 * acá solo guardamos metadata (nombre, tamaño, partes confirmadas), nunca
 * el archivo en sí, pero igual preferimos IndexedDB por ser la herramienta
 * pensada para esto y no competir por cuota con el resto de la app.
 *
 * Por qué NO se usó la librería `idb`: la superficie necesaria acá es
 * chica (un solo object store, cuatro operaciones: get/put/getAll/delete)
 * -- un wrapper propio de la API nativa envuelto en promesas es más simple
 * que sumar una dependencia nueva a mitad de una ronda de trabajo paralela.
 * Documentado también en el reporte final del agente.
 *
 * El archivo (`File`) del browser NUNCA se guarda acá -- no es serializable
 * de forma útil y further, tras un reload la referencia al archivo en disco
 * se pierde igual (limitación del browser, no de esta implementación). Por
 * eso "reanudar" exige que el usuario vuelva a seleccionar el mismo archivo
 * -- ver `multipartUploader.ts` y `uploadsStore.ts`.
 */

const DB_NAME = 'filemeshy_uploads'
const DB_VERSION = 1
const STORE_NAME = 'sessions'

export interface StoredUploadSession {
  /** `upload_session_id` que devuelve el backend -- primary key del store. */
  sessionId: string
  fileName: string
  sizeBytes: number
  mimeType: string
  folderId: string | undefined
  partSizeBytes: number
  totalParts: number
  /** part_number -> etag, solo partes YA confirmadas por el backend (PUT exitoso). */
  confirmedParts: Record<number, string>
  createdAt: number
  updatedAt: number
}

let dbPromise: Promise<IDBDatabase> | null = null

function openDb(): Promise<IDBDatabase> {
  if (dbPromise) return dbPromise

  dbPromise = new Promise((resolve, reject) => {
    if (typeof indexedDB === 'undefined') {
      reject(new Error('IndexedDB no está disponible en este navegador'))
      return
    }

    const request = indexedDB.open(DB_NAME, DB_VERSION)

    request.onupgradeneeded = () => {
      const db = request.result
      if (!db.objectStoreNames.contains(STORE_NAME)) {
        db.createObjectStore(STORE_NAME, { keyPath: 'sessionId' })
      }
    }

    request.onsuccess = () => resolve(request.result)
    request.onerror = () => reject(request.error ?? new Error('No se pudo abrir IndexedDB'))
  })

  // Si falla la apertura, no cachear la promesa rota -- permite reintentar
  // en la próxima llamada en vez de quedar rota para siempre en esta pestaña.
  dbPromise.catch(() => {
    dbPromise = null
  })

  return dbPromise
}

function runRequest<T>(request: IDBRequest<T>): Promise<T> {
  return new Promise((resolve, reject) => {
    request.onsuccess = () => resolve(request.result)
    request.onerror = () => reject(request.error ?? new Error('Error de IndexedDB'))
  })
}

export async function saveUploadSession(session: StoredUploadSession): Promise<void> {
  const db = await openDb()
  const tx = db.transaction(STORE_NAME, 'readwrite')
  tx.objectStore(STORE_NAME).put(session)
  await new Promise<void>((resolve, reject) => {
    tx.oncomplete = () => resolve()
    tx.onerror = () => reject(tx.error ?? new Error('Error al guardar sesión de subida'))
  })
}

export async function getUploadSession(sessionId: string): Promise<StoredUploadSession | undefined> {
  const db = await openDb()
  const tx = db.transaction(STORE_NAME, 'readonly')
  return runRequest(tx.objectStore(STORE_NAME).get(sessionId))
}

export async function listUploadSessions(): Promise<StoredUploadSession[]> {
  const db = await openDb()
  const tx = db.transaction(STORE_NAME, 'readonly')
  const result = await runRequest(tx.objectStore(STORE_NAME).getAll())
  return result ?? []
}

export async function deleteUploadSession(sessionId: string): Promise<void> {
  const db = await openDb()
  const tx = db.transaction(STORE_NAME, 'readwrite')
  tx.objectStore(STORE_NAME).delete(sessionId)
  await new Promise<void>((resolve, reject) => {
    tx.oncomplete = () => resolve()
    tx.onerror = () => reject(tx.error ?? new Error('Error al borrar sesión de subida'))
  })
}

/** Marca una parte como confirmada (PUT exitoso + ETag) y persiste de inmediato. */
export async function markPartConfirmed(sessionId: string, partNumber: number, etag: string): Promise<void> {
  const session = await getUploadSession(sessionId)
  if (!session) return
  session.confirmedParts[partNumber] = etag
  session.updatedAt = Date.now()
  await saveUploadSession(session)
}
