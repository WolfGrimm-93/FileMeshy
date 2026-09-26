/**
 * Servicio de carpetas — CRUD + soft-delete/restore.
 *
 * Usa axiosInstance directo (no apiClient): el backend de archivos responde
 * JSON plano (FolderOut), sin envolver en {status, data} como sí lo hace
 * apiClient.get/post/etc. Mismo patrón que user.service.ts.
 */
import axiosInstance from '@/shared/config/axios'
import type { FolderOut } from '../types'

class FoldersService {
  private basePath = '/folders'

  async create(name: string, parentId: string | null): Promise<FolderOut> {
    const response = await axiosInstance.post<FolderOut>(this.basePath, {
      name,
      parent_id: parentId,
    })
    return response.data
  }

  async get(folderId: string): Promise<FolderOut> {
    const response = await axiosInstance.get<FolderOut>(`${this.basePath}/${folderId}`)
    return response.data
  }

  async rename(folderId: string, name: string): Promise<FolderOut> {
    const response = await axiosInstance.patch<FolderOut>(`${this.basePath}/${folderId}`, { name })
    return response.data
  }

  async move(folderId: string, parentId: string | null): Promise<FolderOut> {
    const response = await axiosInstance.patch<FolderOut>(`${this.basePath}/${folderId}`, {
      parent_id: parentId,
    })
    return response.data
  }

  async setFavorite(folderId: string, isFavorite: boolean): Promise<FolderOut> {
    const response = await axiosInstance.patch<FolderOut>(`${this.basePath}/${folderId}`, {
      is_favorite: isFavorite,
    })
    return response.data
  }

  /** Reemplaza el set completo de etiquetas de la carpeta. */
  async setTags(folderId: string, tagIds: string[]): Promise<FolderOut> {
    const response = await axiosInstance.put<FolderOut>(`${this.basePath}/${folderId}/tags`, {
      tag_ids: tagIds,
    })
    return response.data
  }

  async copy(folderId: string, parentId?: string | null): Promise<FolderOut> {
    // Mismo contrato que files: ausente = misma carpeta, null = raíz, id = esa carpeta
    const body = parentId === undefined ? {} : { folder_id: parentId }
    const response = await axiosInstance.post<FolderOut>(`${this.basePath}/${folderId}/copy`, body)
    return response.data
  }

  async remove(folderId: string): Promise<void> {
    await axiosInstance.delete(`${this.basePath}/${folderId}`)
  }

  async restore(folderId: string): Promise<FolderOut> {
    const response = await axiosInstance.post<FolderOut>(`${this.basePath}/${folderId}/restore`)
    return response.data
  }
}

export const foldersService = new FoldersService()
