/**
 * Servicio de shares (compartir por link) — creación/listado/revocación
 * autenticadas para archivos y carpetas, más los endpoints públicos que
 * consume la página `/compartido/:token` (sin sesión).
 *
 * Usa axiosInstance directo (no apiClient), mismo motivo que
 * files.service.ts / folders.service.ts: el backend responde JSON plano.
 */
import axiosInstance from '@/shared/config/axios'
import type { FileOut, PublicShareResponse, ShareOut, SharedWithMeItem, SharePermission } from '../types'

export interface CreateShareParams {
  /** `null`/omitido = no expira. */
  expiresAt?: string | null
  /** Solo aplica a links públicos (sin `sharedWithEmail`). Vacío/omitido = sin contraseña. */
  password?: string
  /** Omitido = 'view' (los links públicos son siempre 'view', el backend lo asume igual). */
  permission?: SharePermission
  /** Si viene, el share queda dirigido a esa persona (sin link público) -- ver `SharedWithMeItem`. */
  sharedWithEmail?: string
}

class SharesService {
  async createForFile(fileId: string, params: CreateShareParams = {}): Promise<ShareOut> {
    const response = await axiosInstance.post<ShareOut>(`/files/${fileId}/shares`, {
      expires_at: params.expiresAt ?? null,
      ...(params.password ? { password: params.password } : {}),
      ...(params.permission ? { permission: params.permission } : {}),
      ...(params.sharedWithEmail ? { shared_with_email: params.sharedWithEmail } : {}),
    })
    return response.data
  }

  async createForFolder(folderId: string, params: CreateShareParams = {}): Promise<ShareOut> {
    const response = await axiosInstance.post<ShareOut>(`/folders/${folderId}/shares`, {
      expires_at: params.expiresAt ?? null,
      ...(params.password ? { password: params.password } : {}),
      ...(params.permission ? { permission: params.permission } : {}),
      ...(params.sharedWithEmail ? { shared_with_email: params.sharedWithEmail } : {}),
    })
    return response.data
  }

  async listForFile(fileId: string): Promise<ShareOut[]> {
    const response = await axiosInstance.get<ShareOut[]>(`/files/${fileId}/shares`)
    return response.data
  }

  async listForFolder(folderId: string): Promise<ShareOut[]> {
    const response = await axiosInstance.get<ShareOut[]>(`/folders/${folderId}/shares`)
    return response.data
  }

  async revoke(shareId: string): Promise<void> {
    await axiosInstance.delete(`/shares/${shareId}`)
  }

  // ---------------------------------------------------------------------
  // Ronda 3 — "Compartido conmigo" (autenticados, consumidos por
  // SharedWithMePage) y acceso/edición autenticada a un share dirigido.
  // ---------------------------------------------------------------------

  /**
   * Shares dirigidos al usuario actual (por `shared_with_email`). El backend
   * responde `ShareOut[]` CRUDO -- mismo schema que `listForFile`/`listForFolder`,
   * con `id` (no `share_id`) y `resource_name`/`resource_type`/`shared_by_email`
   * solo resueltos acá (ver docstring de `ShareOut` en filemeshy_back). Se
   * mapea EXPLÍCITAMENTE a `SharedWithMeItem` acá -- nunca se expone el
   * `ShareOut` crudo a `SharedWithMePage` (hallazgo de la revisión
   * adversarial: usar `item.share_id` sobre el shape crudo daba siempre
   * `undefined`, y ese `undefined` mandado como UUID a los endpoints de
   * descarga/subida rompía con 422 de Pydantic).
   */
  async listSharedWithMe(): Promise<SharedWithMeItem[]> {
    const response = await axiosInstance.get<ShareOut[]>('/shares/with-me')
    return response.data.map((share) => ({
      share_id: share.id,
      resource_type: share.resource_type ?? (share.file_id ? 'file' : 'folder'),
      resource_name: share.resource_name ?? '(sin nombre)',
      permission: share.permission,
      shared_by_email: share.shared_by_email ?? '(email no disponible)',
      created_at: share.created_at,
      expires_at: share.expires_at,
    }))
  }

  /** Mismo shape que `getPublicShare` pero autenticado, sin token en la URL. */
  async getShared(
    shareId: string,
    path?: string,
    options: { forceDownload?: boolean } = {}
  ): Promise<PublicShareResponse> {
    const response = await axiosInstance.get<PublicShareResponse>(`/shares/${shareId}`, {
      params: {
        ...(path ? { path } : {}),
        ...(options.forceDownload ? { force_download: true } : {}),
      },
    })
    return response.data
  }

  async getSharedDownloadUrl(
    shareId: string,
    fileId: string,
    options: { forceDownload?: boolean } = {}
  ): Promise<string> {
    const response = await axiosInstance.get<{ download_url: string }>(
      `/shares/${shareId}/download/${fileId}`,
      { params: options.forceDownload ? { force_download: true } : undefined }
    )
    return response.data.download_url
  }

  /** Solo válido si el share tiene `permission: 'edit'` y apunta a una carpeta. Devuelve el `FileOut` recién creado. */
  async uploadToSharedFolder(shareId: string, file: File): Promise<FileOut> {
    const form = new FormData()
    form.append('file', file)
    const response = await axiosInstance.post<FileOut>(`/shares/${shareId}/files`, form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    return response.data
  }

  /** Solo válido si el share tiene `permission: 'edit'` y apunta a un archivo. Devuelve el `FileOut` actualizado. */
  async replaceSharedFileContent(shareId: string, file: File): Promise<FileOut> {
    const form = new FormData()
    form.append('file', file)
    const response = await axiosInstance.put<FileOut>(`/shares/${shareId}/content`, form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    return response.data
  }

  // ---------------------------------------------------------------------
  // Públicos (sin sesión) — consumidos por PublicSharePage
  // ---------------------------------------------------------------------

  async getPublicShare(
    token: string,
    path?: string,
    options: { forceDownload?: boolean; password?: string } = {}
  ): Promise<PublicShareResponse> {
    const response = await axiosInstance.get<PublicShareResponse>(`/public/shares/${token}`, {
      params: {
        ...(path ? { path } : {}),
        ...(options.forceDownload ? { force_download: true } : {}),
      },
      // La contraseña de un link protegido viaja como header (nunca query param) --
      // ver `_verify_share_password` en filemeshy_back, que lee `X-Share-Password`.
      ...(options.password ? { headers: { 'X-Share-Password': options.password } } : {}),
    })
    return response.data
  }

  async getPublicDownloadUrl(
    token: string,
    fileId: string,
    options: { forceDownload?: boolean; password?: string } = {}
  ): Promise<string> {
    const response = await axiosInstance.get<{ download_url: string }>(
      `/public/shares/${token}/download/${fileId}`,
      {
        params: options.forceDownload ? { force_download: true } : undefined,
        ...(options.password ? { headers: { 'X-Share-Password': options.password } } : {}),
      }
    )
    return response.data.download_url
  }
}

export const sharesService = new SharesService()
