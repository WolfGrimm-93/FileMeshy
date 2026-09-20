/**
 * Servicio de etiquetas (tags) — CRUD simple, sin soft-delete.
 *
 * Usa axiosInstance directo (no apiClient): mismo motivo que
 * files.service.ts/folders.service.ts, el backend responde JSON plano.
 */
import axiosInstance from '@/shared/config/axios'
import type { TagOut } from '../types'

class TagsService {
  private basePath = '/tags'

  /** Lista únicamente las etiquetas del usuario actual. */
  async list(): Promise<TagOut[]> {
    const response = await axiosInstance.get<TagOut[]>(this.basePath)
    return response.data
  }

  async create(name: string, color?: string): Promise<TagOut> {
    const response = await axiosInstance.post<TagOut>(this.basePath, {
      name,
      ...(color ? { color } : {}),
    })
    return response.data
  }

  async rename(tagId: string, changes: { name?: string; color?: string }): Promise<TagOut> {
    const response = await axiosInstance.patch<TagOut>(`${this.basePath}/${tagId}`, changes)
    return response.data
  }

  async remove(tagId: string): Promise<void> {
    await axiosInstance.delete(`${this.basePath}/${tagId}`)
  }
}

export const tagsService = new TagsService()
