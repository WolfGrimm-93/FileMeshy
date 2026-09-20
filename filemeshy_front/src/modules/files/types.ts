/**
 * Tipos del módulo de Archivos — mirror exacto del contrato de backend
 * (ver filemeshy_back, mismo contrato acordado en paralelo).
 */

export interface FolderOut {
  id: string
  name: string
  parent_id: string | null
  owner_id: string
  created_at: string
  updated_at: string
  deleted_at: string | null
  is_favorite: boolean
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

export interface ShareOut {
  id: string
  token: string
  file_id: string | null
  folder_id: string | null
  created_by_id: string
  expires_at: string | null
  revoked_at: string | null
  created_at: string
  is_active: boolean
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
