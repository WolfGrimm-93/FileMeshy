/**
 * Servicio de shares (compartir por link) — creación/listado/revocación
 * autenticadas para archivos y carpetas, más los endpoints públicos que
 * consume la página `/compartido/:token` (sin sesión).
 *
 * Usa axiosInstance directo (no apiClient), mismo motivo que
 * files.service.ts / folders.service.ts: el backend responde JSON plano.
 */
import axiosInstance from '@/shared/config/axios'
import type { PublicShareResponse, ShareOut } from '../types'

export interface CreateShareParams {
  /** `null`/omitido = no expira. */
  expiresAt?: string | null
}

class SharesService {
  async createForFile(fileId: string, params: CreateShareParams = {}): Promise<ShareOut> {
    const response = await axiosInstance.post<ShareOut>(`/files/${fileId}/shares`, {
      expires_at: params.expiresAt ?? null,
    })
    return response.data
  }

  async createForFolder(folderId: string, params: CreateShareParams = {}): Promise<ShareOut> {
    const response = await axiosInstance.post<ShareOut>(`/folders/${folderId}/shares`, {
      expires_at: params.expiresAt ?? null,
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
  // Públicos (sin sesión) — consumidos por PublicSharePage
  // ---------------------------------------------------------------------

  async getPublicShare(
    token: string,
    path?: string,
    options: { forceDownload?: boolean } = {}
  ): Promise<PublicShareResponse> {
    const response = await axiosInstance.get<PublicShareResponse>(`/public/shares/${token}`, {
      params: {
        ...(path ? { path } : {}),
        ...(options.forceDownload ? { force_download: true } : {}),
      },
    })
    return response.data
  }

  async getPublicDownloadUrl(
    token: string,
    fileId: string,
    options: { forceDownload?: boolean } = {}
  ): Promise<string> {
    const response = await axiosInstance.get<{ download_url: string }>(
      `/public/shares/${token}/download/${fileId}`,
      { params: options.forceDownload ? { force_download: true } : undefined }
    )
    return response.data.download_url
  }
}

export const sharesService = new SharesService()
