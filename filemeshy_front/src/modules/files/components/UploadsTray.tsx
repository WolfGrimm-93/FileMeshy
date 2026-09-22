/**
 * Panel flotante global de "Subidas en curso" -- montado UNA sola vez en
 * `app/layout/MainLayout.tsx` (fuera de `FilesPage`/`UploadModal`) para que
 * una subida grande (multipart) siga visible aunque el usuario cierre el
 * modal de subida o navegue a otra página de la app. Solo desaparece si
 * cierra la pestaña -- eso lo cubre la reanudación (banners de sesión
 * guardada más abajo), no este panel en sí.
 *
 * Decisión de UX (no estaba especificada en el pedido, documentada acá):
 * solo muestra items `kind: 'multipart'` -- las subidas chicas (<=100MB) ya
 * se ven bien resueltas dentro del propio `UploadModal` mientras está
 * abierto y terminan en segundos/minutos, así que duplicarlas acá sería
 * ruido. Las multipart sí lo necesitan porque pueden tardar horas y el
 * usuario razonablemente quiere seguir navegando la app mientras tanto.
 */
import { useEffect, useRef, useState } from 'react'
import { Upload, ChevronDown, ChevronUp, X, RotateCcw, FolderOpen } from 'lucide-react'
import { Button } from '@/ui/buttons/Button'
import { Progress } from '@/ui/progress/Progress'
import { formatBytes } from '@/shared/utils/downloadFile'
import { useUploadsStore } from '../store/uploadsStore'
import { uploadStatusLabel, progressBarVariant, canRetryItem, canAbortItem } from '../lib/uploadItemPresentation'

/** Cuánto queda visible un item "Completado" antes de desaparecer solo del panel
 *  (no del backend, es puramente UI) -- da feedback sin acumular basura visual. */
const DONE_AUTO_DISMISS_MS = 6000

const DISMISSIBLE_STATUSES = new Set(['done', 'error', 'infected', 'aborted'])

export default function UploadsTray() {
  const items = useUploadsStore((state) => state.items)
  const resumableSessions = useUploadsStore((state) => state.resumableSessions)
  const scanForResumableSessions = useUploadsStore((state) => state.scanForResumableSessions)
  const resumeSession = useUploadsStore((state) => state.resumeSession)
  const discardResumableSession = useUploadsStore((state) => state.discardResumableSession)
  const retryItem = useUploadsStore((state) => state.retryItem)
  const abortItem = useUploadsStore((state) => state.abortItem)
  const dismissItem = useUploadsStore((state) => state.dismissItem)

  const [collapsed, setCollapsed] = useState(false)
  const scheduledDismissRef = useRef<Set<string>>(new Set())
  const fileInputRefs = useRef<Map<string, HTMLInputElement>>(new Map())

  const trayItems = items.filter((item) => item.kind === 'multipart')

  // Al montar la app (una sola vez -- este componente vive en MainLayout, no se
  // desmonta al navegar) buscamos sesiones guardadas de una pestaña/PC anterior
  // que nadie retomó todavía.
  useEffect(() => {
    void scanForResumableSessions()
  }, [scanForResumableSessions])

  useEffect(() => {
    trayItems.forEach((item) => {
      if (item.status === 'done' && !scheduledDismissRef.current.has(item.id)) {
        scheduledDismissRef.current.add(item.id)
        setTimeout(() => dismissItem(item.id), DONE_AUTO_DISMISS_MS)
      }
    })
  }, [trayItems, dismissItem])

  const handleResumeFileChange = (sessionId: string, file: File | undefined) => {
    if (!file) return
    void resumeSession(sessionId, file, () => {})
  }

  if (trayItems.length === 0 && resumableSessions.length === 0) return null

  const totalCount = trayItems.length + resumableSessions.length

  return (
    <div className="fixed bottom-4 right-4 z-40 w-full max-w-sm print:hidden">
      <div className="rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 shadow-2xl overflow-hidden">
        <button
          type="button"
          onClick={() => setCollapsed((c) => !c)}
          className="flex w-full items-center justify-between gap-2 px-4 py-3 bg-gray-50 dark:bg-gray-800 border-b border-gray-200 dark:border-gray-700"
        >
          <span className="flex items-center gap-2 text-sm font-semibold text-gray-900 dark:text-white">
            <Upload className="size-4" />
            Subidas en curso ({totalCount})
          </span>
          {collapsed ? (
            <ChevronUp className="size-4 text-gray-400" />
          ) : (
            <ChevronDown className="size-4 text-gray-400" />
          )}
        </button>

        {!collapsed && (
          <ul className="max-h-96 overflow-y-auto divide-y divide-gray-100 dark:divide-gray-800">
            {resumableSessions.map((session) => (
              <li key={session.sessionId} className="p-3 space-y-2">
                <div className="flex items-center gap-2">
                  <FolderOpen className="size-4 text-brand-500 shrink-0" />
                  <span className="flex-1 truncate text-sm font-medium text-gray-900 dark:text-white">
                    {session.fileName}
                  </span>
                  <span className="text-xs text-gray-500 dark:text-gray-400 shrink-0">
                    {formatBytes(session.sizeBytes)}
                  </span>
                </div>
                <p className="text-xs text-gray-500 dark:text-gray-400">
                  Subida sin terminar de una sesión anterior -- seleccioná el mismo archivo para reanudarla.
                </p>
                <div className="flex gap-2">
                  <input
                    type="file"
                    className="hidden"
                    ref={(el) => {
                      if (el) fileInputRefs.current.set(session.sessionId, el)
                      else fileInputRefs.current.delete(session.sessionId)
                    }}
                    onChange={(e) => handleResumeFileChange(session.sessionId, e.target.files?.[0])}
                  />
                  <Button
                    size="sm"
                    variant="secondary"
                    onClick={() => fileInputRefs.current.get(session.sessionId)?.click()}
                  >
                    Reanudar
                  </Button>
                  <Button size="sm" variant="ghost" onClick={() => void discardResumableSession(session.sessionId)}>
                    Descartar
                  </Button>
                </div>
              </li>
            ))}

            {trayItems.map((item) => (
              <li key={item.id} className="p-3 space-y-1.5">
                <div className="flex items-center gap-2">
                  <span className="flex-1 truncate text-sm font-medium text-gray-900 dark:text-white">
                    {item.fileName}
                  </span>
                  <span className="text-xs text-gray-500 dark:text-gray-400 shrink-0">
                    {formatBytes(item.sizeBytes)}
                  </span>
                  {canRetryItem(item) && (
                    <button
                      type="button"
                      title="Reintentar"
                      onClick={() => retryItem(item.id)}
                      className="shrink-0 text-brand-600 hover:text-brand-700 dark:text-brand-400"
                    >
                      <RotateCcw className="size-3.5" />
                    </button>
                  )}
                  {canAbortItem(item) && (
                    <button
                      type="button"
                      title="Cancelar subida"
                      onClick={() => abortItem(item.id)}
                      className="shrink-0 text-gray-400 hover:text-red-600 dark:hover:text-red-400"
                    >
                      <X className="size-3.5" />
                    </button>
                  )}
                  {DISMISSIBLE_STATUSES.has(item.status) && (
                    <button
                      type="button"
                      title="Ocultar"
                      onClick={() => dismissItem(item.id)}
                      className="shrink-0 text-gray-400 hover:text-gray-600 dark:hover:text-gray-300"
                    >
                      <X className="size-3.5" />
                    </button>
                  )}
                </div>
                <Progress value={item.status === 'done' ? 100 : item.progress} size="sm" variant={progressBarVariant(item)} />
                <p
                  className={`text-xs ${
                    item.status === 'infected'
                      ? 'text-red-600 dark:text-red-400 font-medium'
                      : 'text-gray-500 dark:text-gray-400'
                  }`}
                >
                  {uploadStatusLabel(item)}
                </p>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  )
}
