/**
 * Lógica de subida de archivos (items, progreso, llamada a filesService.upload)
 * extraída de UploadModal para poder reusarla también desde el drag&drop
 * directo sobre la ventana en FilesPage, sin duplicarla.
 */
import { useCallback, useState } from 'react'
import { toast } from '@/ui/toast/CustomToast'
import { extractErrorMessage } from '@/shared/utils/errors'
import { filesService } from '../services/files.service'
import type { FileOut } from '../types'

export interface UploadItem {
  id: string
  file: File
  progress: number
  status: 'pending' | 'uploading' | 'done' | 'error'
  error?: string
}

export function useFileUpload(folderId: string | undefined, onUploaded: (file: FileOut) => void) {
  const [items, setItems] = useState<UploadItem[]>([])

  const isUploading = items.some((i) => i.status === 'uploading' || i.status === 'pending')

  const uploadOne = useCallback(
    async (item: UploadItem) => {
      setItems((prev) => prev.map((i) => (i.id === item.id ? { ...i, status: 'uploading' } : i)))
      try {
        const uploaded = await filesService.upload(item.file, folderId, (percent) => {
          setItems((prev) => prev.map((i) => (i.id === item.id ? { ...i, progress: percent } : i)))
        })
        setItems((prev) => prev.map((i) => (i.id === item.id ? { ...i, status: 'done', progress: 100 } : i)))
        onUploaded(uploaded)
      } catch (error: unknown) {
        const message = extractErrorMessage(error, 'Error al subir el archivo')
        setItems((prev) => prev.map((i) => (i.id === item.id ? { ...i, status: 'error', error: message } : i)))
        toast.error(`${item.file.name}: ${message}`)
      }
    },
    [folderId, onUploaded]
  )

  const uploadFiles = useCallback(
    (files: File[]) => {
      const newItems: UploadItem[] = files.map((file) => ({
        id: `${file.name}-${file.size}-${Date.now()}-${Math.random().toString(36).slice(2)}`,
        file,
        progress: 0,
        status: 'pending',
      }))
      setItems((prev) => [...prev, ...newItems])
      newItems.forEach((item) => {
        void uploadOne(item)
      })
    },
    [uploadOne]
  )

  const resetItems = useCallback(() => setItems([]), [])

  return { items, isUploading, uploadFiles, resetItems }
}
