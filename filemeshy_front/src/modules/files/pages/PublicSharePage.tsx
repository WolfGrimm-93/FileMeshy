/**
 * PÁGINA PÚBLICA: `/compartido/:token` (Hito 2)
 *
 * Sin autenticación — no vive dentro de ProtectedLayout ni tiene
 * sidebar/navbar. Consume GET /public/shares/{token} directo (sin
 * Authorization, ver axiosInstance: las rutas /public/ nunca llevan token ni
 * disparan refresh). Si el share es de archivo, muestra nombre/tamaño +
 * descarga + preview inline si aplica. Si es de carpeta, mini-explorador de
 * solo lectura navegando con `?path=`.
 */
import { useCallback, useEffect, useState } from 'react'
import { useParams, useSearchParams } from 'react-router-dom'
import { ChevronRight, Download, File as FileIcon, Folder, Home } from 'lucide-react'
import { Button } from '@/ui/buttons/Button'
import { toast } from '@/ui/toast/CustomToast'
import { formatBytes } from '@/shared/utils/downloadFile'
import { extractErrorMessage } from '@/shared/utils/errors'
import { sharesService } from '../services/shares.service'
import PreviewModal, { type PreviewTarget } from '../components/PreviewModal'
import type { FileOut, PublicShareResponse } from '../types'

function isPreviewable(mimeType: string): boolean {
  return mimeType.startsWith('image/') || mimeType === 'application/pdf'
}

export default function PublicSharePage() {
  const { token } = useParams<{ token: string }>()
  const [searchParams, setSearchParams] = useSearchParams()
  const path = searchParams.get('path')

  const [data, setData] = useState<PublicShareResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [notFound, setNotFound] = useState(false)
  const [previewTarget, setPreviewTarget] = useState<PreviewTarget | null>(null)

  const load = useCallback(async () => {
    if (!token) {
      setNotFound(true)
      setLoading(false)
      return
    }
    setLoading(true)
    setNotFound(false)
    try {
      const response = await sharesService.getPublicShare(token, path ?? undefined)
      setData(response)

      // Punto 3 del contrato: si el share es de archivo y el mime es
      // imagen/PDF, mostrar el mismo PreviewModal del Hito 2 (reusado, sin
      // duplicar lógica de qué tipos son previsualizables).
      if (response.type === 'file' && isPreviewable(response.mime_type)) {
        setPreviewTarget({ name: response.name, mimeType: response.mime_type, downloadUrl: response.download_url })
      } else {
        setPreviewTarget(null)
      }
    } catch {
      setNotFound(true)
    } finally {
      setLoading(false)
    }
  }, [token, path])

  useEffect(() => {
    load()
  }, [load])

  const handleNavigate = (folderId: string | null) => {
    if (folderId) setSearchParams({ path: folderId })
    else setSearchParams({})
  }

  const handleFileOpen = async (file: FileOut) => {
    if (!token) return
    const previewable = isPreviewable(file.mime_type)
    try {
      const url = await sharesService.getPublicDownloadUrl(token, file.id, {
        forceDownload: !previewable,
      })
      if (previewable) {
        setPreviewTarget({ name: file.name, mimeType: file.mime_type, downloadUrl: url })
      } else {
        window.location.href = url
      }
    } catch (error: unknown) {
      toast.error(extractErrorMessage(error, 'Error al abrir el archivo'))
    }
  }

  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-gray-50 dark:bg-gray-950">
        <div className="flex flex-col items-center gap-4">
          <div className="size-10 animate-spin rounded-full border-4 border-brand-500 border-t-transparent" />
          <p className="text-sm text-muted-foreground">Cargando...</p>
        </div>
      </div>
    )
  }

  if (notFound || !data) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-gray-50 p-4 dark:bg-gray-950">
        <div className="w-full max-w-sm text-center">
          <h1 className="mb-2 text-2xl font-bold text-foreground">Enlace no disponible</h1>
          <p className="text-sm text-muted-foreground">
            Este enlace no existe o ya no está disponible.
          </p>
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-gray-50 dark:bg-gray-950">
      <div className="mx-auto max-w-3xl px-4 py-10 sm:px-6">
        {data.type === 'file' ? (
          <div className="rounded-xl border border-border bg-card p-8 text-center shadow-xs">
            <FileIcon className="mx-auto mb-4 size-16 text-gray-400" strokeWidth={1.5} />
            <h1 className="mb-1 text-xl font-bold text-foreground wrap-break-word">{data.name}</h1>
            <p className="mb-6 text-sm text-muted-foreground">{formatBytes(data.size_bytes)}</p>
            <div className="flex flex-wrap items-center justify-center gap-3">
              <Button
                variant="primary"
                leftIcon={<Download className="size-4" />}
                onClick={async () => {
                  // Forzar attachment incluso para imagen/PDF -- el download_url que ya
                  // tenemos en `data` es el de preview (sin forzar), pedimos uno nuevo.
                  try {
                    const forced = await sharesService.getPublicShare(token!, path ?? undefined, { forceDownload: true })
                    if (forced.type === 'file') {
                      window.location.href = forced.download_url
                    }
                  } catch (error: unknown) {
                    toast.error(extractErrorMessage(error, 'No se pudo descargar el archivo'))
                  }
                }}
              >
                Descargar
              </Button>
              {isPreviewable(data.mime_type) && (
                <Button
                  variant="secondary"
                  onClick={() =>
                    setPreviewTarget({ name: data.name, mimeType: data.mime_type, downloadUrl: data.download_url })
                  }
                >
                  Vista previa
                </Button>
              )}
            </div>
          </div>
        ) : (
          <div className="rounded-xl border border-border bg-card shadow-xs">
            <div className="flex items-center gap-2 border-b border-border p-4 text-sm text-gray-600 dark:text-gray-400">
              <button
                type="button"
                onClick={() => handleNavigate(null)}
                className={`flex items-center gap-1 rounded-sm px-1.5 py-0.5 hover:bg-gray-100 dark:hover:bg-gray-800 ${
                  !path ? 'font-semibold text-brand-600 dark:text-brand-400' : ''
                }`}
              >
                <Home className="size-3.5" />
                {data.name}
              </button>
              {path && (
                <span className="flex items-center gap-1">
                  <ChevronRight className="size-3.5 text-gray-400" />
                  <span className="font-semibold text-brand-600 dark:text-brand-400">Subcarpeta</span>
                </span>
              )}
            </div>

            {data.folders.length === 0 && data.files.length === 0 ? (
              <div className="p-10 text-center text-sm text-muted-foreground">Esta carpeta está vacía.</div>
            ) : (
              <ul className="divide-y divide-border">
                {[...data.folders]
                  .sort((a, b) => a.name.localeCompare(b.name))
                  .map((folder) => (
                    <li
                      key={folder.id}
                      className="flex cursor-pointer select-none items-center gap-3 px-4 py-3 hover:bg-gray-50 dark:hover:bg-gray-900"
                      onDoubleClick={() => handleNavigate(folder.id)}
                      title="Doble clic para entrar"
                    >
                      <Folder className="size-5 shrink-0 text-brand-500" />
                      <span className="truncate text-sm font-medium text-gray-900 dark:text-white">{folder.name}</span>
                    </li>
                  ))}
                {[...data.files]
                  .sort((a, b) => a.name.localeCompare(b.name))
                  .map((file) => (
                    <li
                      key={file.id}
                      className="flex cursor-pointer select-none items-center gap-3 px-4 py-3 hover:bg-gray-50 dark:hover:bg-gray-900"
                      onDoubleClick={() => handleFileOpen(file)}
                      title="Doble clic para abrir"
                    >
                      <FileIcon className="size-5 shrink-0 text-gray-400" />
                      <span className="min-w-0 flex-1 truncate text-sm font-medium text-gray-900 dark:text-white">
                        {file.name}
                      </span>
                      <span className="shrink-0 text-xs text-muted-foreground">{formatBytes(file.size_bytes)}</span>
                    </li>
                  ))}
              </ul>
            )}
          </div>
        )}
      </div>

      <PreviewModal target={previewTarget} onClose={() => setPreviewTarget(null)} />
    </div>
  )
}
