/**
 * Wrapper delgado sobre `store/uploadsStore.ts` (Zustand, global) -- mantiene
 * la MISMA firma pública que la versión original (Ronda 1) para no romper a
 * sus dos consumidores actuales (`UploadModal.tsx` y el drag&drop directo de
 * `FilesPage.tsx`): `{ items, isUploading, uploadFiles, resetItems }`.
 *
 * El estado real ahora vive en el store global (no en un `useState` local)
 * para que una subida grande (multipart) siga en curso aunque el usuario
 * cierre el modal o navegue a otra página -- ver `uploadsStore.ts` para el
 * porqué. `items` acá reexpone el tipo enriquecido del store (más estados:
 * 'waiting_admission', 'paused', 'processing', 'infected', etc. -- ver
 * `UploadItem` en el store) en vez del tipo chico original de 4 estados.
 */
import { useCallback } from 'react'
import { useUploadsStore, type UploadItem } from '../store/uploadsStore'
import type { FileOut } from '../types'

export type { UploadItem }

/**
 * Bloqueo de cierre del modal -- SOLO aplica al camino simple (<=100MB, ver
 * `SIMPLE_BLOCKING_STATUSES`). Ahí no hay panel flotante alternativo y la
 * subida es cuestión de segundos, así que forzar a esperar visible es un
 * costo bajo y evita perder de vista un archivo a punto de terminar --
 * mismo criterio que tenía el `isUploading` original de Ronda 1, sin tocar.
 *
 * El camino multipart es justo lo opuesto (puede tardar horas): el motor
 * (`uploadsStore.ts`) corre en el store global, independiente del modal --
 * cerrarlo NO cancela nada, y `UploadsTray.tsx` (panel flotante montado en
 * `MainLayout.tsx`) existe PRECISAMENTE para que el usuario pueda cerrar el
 * modal y seguir navegando mientras la subida sigue en curso. Bloquear el
 * cierre ahí contradecía el propósito de la feature -- hallazgo real de la
 * fase de Pruebas (Ronda 9): con throttling real, ni la X, ni Escape, ni el
 * backdrop, ni navegar a otra página funcionaban mientras un archivo grande
 * seguía en 'uploading' (el overlay del modal interceptaba los clics).
 * Corregido acotando el bloqueo a `kind === 'simple'` -- ningún estado del
 * camino multipart bloquea el cierre.
 */
const SIMPLE_BLOCKING_STATUSES = new Set<UploadItem['status']>(['pending', 'uploading'])

const TERMINAL_STATUSES = new Set<UploadItem['status']>(['done', 'error', 'aborted', 'infected'])

export function useFileUpload(folderId: string | undefined, onUploaded: (file: FileOut) => void) {
  const items = useUploadsStore((state) => state.items)
  const uploadFilesAction = useUploadsStore((state) => state.uploadFiles)
  const retryItem = useUploadsStore((state) => state.retryItem)
  const abortItem = useUploadsStore((state) => state.abortItem)
  const dismissItem = useUploadsStore((state) => state.dismissItem)

  const isUploading = items.some((item) => item.kind === 'simple' && SIMPLE_BLOCKING_STATUSES.has(item.status))

  const uploadFiles = useCallback(
    (files: File[]) => {
      uploadFilesAction(files, folderId, onUploaded)
    },
    [uploadFilesAction, folderId, onUploaded]
  )

  /** Ya no "vacía" el store global (otras vistas podrían tener items en curso) --
   *  solo destierra del panel los que ya llegaron a un estado terminal, mismo
   *  efecto visual que el `resetItems` original al cerrar el modal. */
  const resetItems = useCallback(() => {
    items.filter((item) => TERMINAL_STATUSES.has(item.status)).forEach((item) => dismissItem(item.id))
  }, [items, dismissItem])

  return { items, isUploading, uploadFiles, resetItems, retryItem, abortItem, dismissItem }
}
