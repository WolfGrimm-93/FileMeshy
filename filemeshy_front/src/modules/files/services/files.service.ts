/**
 * Servicio de archivos — listado (explorador), subida con progreso real,
 * descarga, rename/move y soft-delete/restore.
 *
 * Usa axiosInstance directo (no apiClient) por el mismo motivo que
 * folders.service.ts: el backend responde JSON plano, sin envolver en
 * {status, data}.
 */
import axiosInstance from '@/shared/config/axios'
import type { AxiosProgressEvent } from 'axios'
import type { DirectoryListing, FileOut, FileVersionOut } from '../types'

export type FilesSortBy = 'name' | 'created_at' | 'updated_at' | 'size_bytes'
export type FilesSortDir = 'asc' | 'desc'

export interface ListFilesParams {
  /** Carpeta a listar. Omitido = raíz. Ignorado si `q` viene seteado. */
  folderId?: string
  /** Búsqueda por nombre en TODO el árbol del usuario (ignora folderId). */
  q?: string
  /** Listar la papelera del usuario en vez del árbol activo. */
  trash?: boolean
  /** Campo de orden. Omitido = orden default del backend (nombre asc). */
  sortBy?: FilesSortBy
  /** Dirección del orden. Omitido = orden default del backend (asc). */
  sortDir?: FilesSortDir
  /** Listar únicamente favoritos (archivos y carpetas marcadas). */
  favoritesOnly?: boolean
}

class FilesService {
  private basePath = '/files'

  async list(params: ListFilesParams = {}): Promise<DirectoryListing> {
    const query: Record<string, string | boolean> = {}
    if (params.folderId) query.folder_id = params.folderId
    if (params.q) query.q = params.q
    if (params.trash) query.trash = true
    if (params.sortBy) query.sort_by = params.sortBy
    if (params.sortDir) query.sort_dir = params.sortDir
    if (params.favoritesOnly) query.favorites_only = true

    const response = await axiosInstance.get<DirectoryListing>(this.basePath, { params: query })
    return response.data
  }

  async upload(
    file: File,
    folderId: string | undefined,
    onProgress?: (percent: number) => void
  ): Promise<FileOut> {
    const form = new FormData()
    form.append('file', file)
    if (folderId) form.append('folder_id', folderId)

    const response = await axiosInstance.post<FileOut>(`${this.basePath}/upload`, form, {
      headers: { 'Content-Type': 'multipart/form-data' },
      onUploadProgress: (event: AxiosProgressEvent) => {
        if (!onProgress || !event.total) return
        onProgress(Math.round((event.loaded / event.total) * 100))
      },
    })
    return response.data
  }

  async get(fileId: string): Promise<FileOut> {
    const response = await axiosInstance.get<FileOut>(`${this.basePath}/${fileId}`)
    return response.data
  }

  async getDownloadUrl(fileId: string, options: { forceDownload?: boolean } = {}): Promise<string> {
    const response = await axiosInstance.get<{ download_url: string }>(
      `${this.basePath}/${fileId}/download`,
      { params: options.forceDownload ? { force_download: true } : undefined }
    )
    return response.data.download_url
  }

  async rename(fileId: string, name: string): Promise<FileOut> {
    const response = await axiosInstance.patch<FileOut>(`${this.basePath}/${fileId}`, { name })
    return response.data
  }

  async move(fileId: string, folderId: string | null): Promise<FileOut> {
    const response = await axiosInstance.patch<FileOut>(`${this.basePath}/${fileId}`, {
      folder_id: folderId,
    })
    return response.data
  }

  async setFavorite(fileId: string, isFavorite: boolean): Promise<FileOut> {
    const response = await axiosInstance.patch<FileOut>(`${this.basePath}/${fileId}`, {
      is_favorite: isFavorite,
    })
    return response.data
  }

  /** Reemplaza el set completo de etiquetas del archivo. */
  async setTags(fileId: string, tagIds: string[]): Promise<FileOut> {
    const response = await axiosInstance.put<FileOut>(`${this.basePath}/${fileId}/tags`, {
      tag_ids: tagIds,
    })
    return response.data
  }

  async copy(fileId: string, folderId?: string | null): Promise<FileOut> {
    // Contrato del backend: campo AUSENTE = misma carpeta del original; `null` explícito = raíz;
    // un id = esa carpeta. Por eso `undefined` NO se colapsa a null (copiaba siempre a la raíz).
    const body = folderId === undefined ? {} : { folder_id: folderId }
    const response = await axiosInstance.post<FileOut>(`${this.basePath}/${fileId}/copy`, body)
    return response.data
  }

  async remove(fileId: string): Promise<void> {
    await axiosInstance.delete(`${this.basePath}/${fileId}`)
  }

  async restore(fileId: string): Promise<FileOut> {
    const response = await axiosInstance.post<FileOut>(`${this.basePath}/${fileId}/restore`)
    return response.data
  }

  /**
   * Ronda 4 -- sube una nueva versión del contenido de un archivo existente
   * (mismo patrón multipart + progreso que `upload()`, pero contra el
   * subrecurso `/versions` en vez de `/upload`). El backend devuelve el
   * `FileOut` actualizado (tamaño/mime/updated_at ya reflejan la versión
   * nueva).
   */
  async uploadNewVersion(
    fileId: string,
    file: File,
    onProgress?: (percent: number) => void
  ): Promise<FileOut> {
    const form = new FormData()
    form.append('file', file)

    const response = await axiosInstance.post<FileOut>(`${this.basePath}/${fileId}/versions`, form, {
      headers: { 'Content-Type': 'multipart/form-data' },
      onUploadProgress: (event: AxiosProgressEvent) => {
        if (!onProgress || !event.total) return
        onProgress(Math.round((event.loaded / event.total) * 100))
      },
    })
    return response.data
  }

  /** Ronda 4 -- historial de versiones del archivo, más reciente primero. */
  async listVersions(fileId: string): Promise<FileVersionOut[]> {
    const response = await axiosInstance.get<FileVersionOut[]>(`${this.basePath}/${fileId}/versions`)
    return response.data
  }

  /** Ronda 4 -- restaura una versión anterior como la versión activa del archivo. */
  async restoreVersion(fileId: string, versionId: string): Promise<FileOut> {
    const response = await axiosInstance.post<FileOut>(
      `${this.basePath}/${fileId}/versions/${versionId}/restore`
    )
    return response.data
  }

  /**
   * Ronda 5 -- pide la URL de preview (PDF ya convertido) de un documento de
   * Office (docx/xlsx/pptx). La conversión no está cacheada la primera vez,
   * así que el request puede tardar unos segundos: se usa un timeout generoso
   * del lado del cliente (bastante mayor a un GET normal) en vez del default
   * de `axiosInstance`, para no cortar la espera mientras el backend todavía
   * está convirtiendo.
   *
   * Contrato real confirmado por red contra el backend (revisión adversarial,
   * 2026-09-20): `GET /files/{id}/preview` devuelve `PreviewUrlResponse` =
   * `{ preview_url: string, mime_type: string }` -- OJO, es `preview_url`,
   * no `url` (bug detectado en la ronda de feedback: leer el campo
   * equivocado deja `undefined` pasar silenciosamente como si fuera una URL
   * válida más adelante en `PreviewModal`).
   */
  async getOfficePreviewUrl(fileId: string): Promise<string> {
    const response = await axiosInstance.get<{ preview_url: string; mime_type: string }>(
      `${this.basePath}/${fileId}/preview`,
      { timeout: 40_000 }
    )
    return response.data.preview_url
  }
}

export const filesService = new FilesService()
