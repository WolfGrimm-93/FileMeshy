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
import type { DirectoryListing, FileOut } from '../types'

export interface ListFilesParams {
  /** Carpeta a listar. Omitido = raíz. Ignorado si `q` viene seteado. */
  folderId?: string
  /** Búsqueda por nombre en TODO el árbol del usuario (ignora folderId). */
  q?: string
  /** Listar la papelera del usuario en vez del árbol activo. */
  trash?: boolean
}

class FilesService {
  private basePath = '/files'

  async list(params: ListFilesParams = {}): Promise<DirectoryListing> {
    const query: Record<string, string | boolean> = {}
    if (params.folderId) query.folder_id = params.folderId
    if (params.q) query.q = params.q
    if (params.trash) query.trash = true

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

  async remove(fileId: string): Promise<void> {
    await axiosInstance.delete(`${this.basePath}/${fileId}`)
  }

  async restore(fileId: string): Promise<FileOut> {
    const response = await axiosInstance.post<FileOut>(`${this.basePath}/${fileId}/restore`)
    return response.data
  }
}

export const filesService = new FilesService()
