/**
 * PÁGINA PÚBLICA: `/compartido/:token` (Hito 2 + Ronda 3: links con contraseña)
 *
 * Sin autenticación — no vive dentro de ProtectedLayout ni tiene
 * sidebar/navbar. Consume GET /public/shares/{token} directo (sin
 * Authorization, ver axiosInstance: las rutas /public/ nunca llevan token ni
 * disparan refresh). Si el share es de archivo, muestra nombre/tamaño +
 * descarga + preview inline si aplica. Si es de carpeta, mini-explorador de
 * solo lectura navegando con `?path=`.
 *
 * Contraseña (Ronda 3): no se indica de antemano si el link la requiere --
 * se intenta cargar sin contraseña y, si el backend responde 401 (ver
 * `_verify_share_password` en filemeshy_back), se muestra un formulario
 * pidiéndola. El backend la espera como header `X-Share-Password` (NUNCA
 * query param, ver `shares.service.ts`). Una vez que un intento funciona, la
 * contraseña se guarda en un ref del componente (nunca en localStorage --
 * vive solo mientras dura esta pestaña) para reusarla al navegar subcarpetas
 * y al descargar archivos dentro del share.
 */
import { useCallback, useEffect, useRef, useState, type FormEvent } from 'react'
import { useParams, useSearchParams } from 'react-router-dom'
import axios from 'axios'
import { ChevronRight, Download, File as FileIcon, Folder, Home, Lock } from 'lucide-react'
import { Button } from '@/ui/buttons/Button'
import { PasswordInput } from '@/ui/inputs/Input'
import { toast } from '@/ui/toast/CustomToast'
import { formatBytes } from '@/shared/utils/downloadFile'
import { extractErrorMessage } from '@/shared/utils/errors'
import { sharesService } from '../services/shares.service'
import PreviewModal, { type PreviewTarget } from '../components/PreviewModal'
import type { FileOut, PublicShareResponse } from '../types'

// Ronda 5: video y audio se agregan acá porque solo dependen de la URL de
// descarga presignada que ya devuelve el backend (sin auth extra, igual que
// imagen/PDF) -- Office queda afuera porque su preview requiere el endpoint
// autenticado `GET /files/{id}/preview` (`getOfficePreviewUrl`), que no
// existe en el flujo público sin sesión.
const PREVIEWABLE_VIDEO_MIME_TYPES = new Set(['video/mp4', 'video/webm', 'video/ogg'])
const PREVIEWABLE_AUDIO_MIME_TYPES = new Set(['audio/mpeg', 'audio/wav', 'audio/ogg'])

function isPreviewable(mimeType: string): boolean {
  return (
    mimeType.startsWith('image/') ||
    mimeType === 'application/pdf' ||
    PREVIEWABLE_VIDEO_MIME_TYPES.has(mimeType) ||
    PREVIEWABLE_AUDIO_MIME_TYPES.has(mimeType)
  )
}

type FetchOutcome = 'ok' | 'unauthorized' | 'error'

export default function PublicSharePage() {
  const { token } = useParams<{ token: string }>()
  const [searchParams, setSearchParams] = useSearchParams()
  const path = searchParams.get('path')

  const [data, setData] = useState<PublicShareResponse | null>(null)
  // Resultado del último intento de carga, atado a la clave (token+path) que lo produjo:
  // `loading` y `notFound` se derivan de él, sin setState síncrono dentro de efectos.
  const [outcome, setOutcome] = useState<{ key: string; failed: boolean } | null>(null)
  const requestKey = `${token ?? ''}|${path ?? ''}`
  const loading = !!token && outcome?.key !== requestKey
  const notFound = !token || (outcome?.key === requestKey && outcome.failed)
  const [previewTarget, setPreviewTarget] = useState<PreviewTarget | null>(null)

  // Contraseña del link (si aplica) -- ref (no state) para no forzar un
  // re-render ni volver a disparar el efecto de carga cuando se confirma,
  // y para que nunca termine persistida (localStorage, etc.), solo en
  // memoria mientras dura esta pestaña.
  const verifiedPasswordRef = useRef<string | undefined>(undefined)

  const [passwordRequired, setPasswordRequired] = useState(false)
  const [passwordInput, setPasswordInput] = useState('')
  const [passwordError, setPasswordError] = useState<string | null>(null)
  const [verifyingPassword, setVerifyingPassword] = useState(false)

  const applyResponse = useCallback((response: PublicShareResponse) => {
    setData(response)
    // Punto 3 del contrato: si el share es de archivo y el mime es
    // imagen/PDF, mostrar el mismo PreviewModal del Hito 2 (reusado, sin
    // duplicar lógica de qué tipos son previsualizables).
    if (response.type === 'file' && isPreviewable(response.mime_type)) {
      setPreviewTarget({ name: response.name, mimeType: response.mime_type, downloadUrl: response.download_url })
    } else {
      setPreviewTarget(null)
    }
  }, [])

  // Intenta cargar el share con la contraseña dada (o sin ninguna). Devuelve
  // el resultado en vez de decidir qué pantalla mostrar -- eso lo maneja
  // cada caller (`load`, disparado por el efecto/navegación, y el submit del
  // formulario de contraseña), que necesitan loaders/mensajes distintos.
  const attemptFetch = useCallback(
    async (passwordAttempt?: string): Promise<FetchOutcome> => {
      if (!token) return 'error'
      try {
        const response = await sharesService.getPublicShare(token, path ?? undefined, {
          password: passwordAttempt,
        })
        applyResponse(response)
        verifiedPasswordRef.current = passwordAttempt
        setPasswordRequired(false)
        return 'ok'
      } catch (error: unknown) {
        if (axios.isAxiosError(error) && error.response?.status === 401) {
          setPasswordRequired(true)
          setData(null)
          return 'unauthorized'
        }
        return 'error'
      }
    },
    [token, path, applyResponse]
  )

  useEffect(() => {
    if (!token) return
    let cancelled = false
    attemptFetch(verifiedPasswordRef.current).then((result) => {
      if (!cancelled) setOutcome({ key: requestKey, failed: result === 'error' })
    })
    return () => {
      cancelled = true
    }
  }, [token, requestKey, attemptFetch])

  const handleNavigate = (folderId: string | null) => {
    if (folderId) setSearchParams({ path: folderId })
    else setSearchParams({})
  }

  const handlePasswordSubmit = async (e: FormEvent) => {
    e.preventDefault()
    if (!passwordInput.trim()) return
    setVerifyingPassword(true)
    setPasswordError(null)
    const outcome = await attemptFetch(passwordInput)
    if (outcome === 'unauthorized') {
      setPasswordError('Contraseña incorrecta')
    } else if (outcome === 'error') {
      toast.error('Error al validar la contraseña')
    }
    setVerifyingPassword(false)
  }

  const handleFileOpen = async (file: FileOut) => {
    if (!token) return
    const previewable = isPreviewable(file.mime_type)
    try {
      const url = await sharesService.getPublicDownloadUrl(token, file.id, {
        forceDownload: !previewable,
        password: verifiedPasswordRef.current,
      })
      if (previewable) {
        setPreviewTarget({ name: file.name, mimeType: file.mime_type, downloadUrl: url })
      } else {
        window.location.assign(url)
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

  if (passwordRequired) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-gray-50 p-4 dark:bg-gray-950">
        <div className="w-full max-w-sm rounded-xl border border-border bg-card p-8 shadow-xs">
          <Lock className="mx-auto mb-4 size-10 text-gray-400" strokeWidth={1.5} />
          <h1 className="mb-1 text-center text-xl font-bold text-foreground">Enlace protegido</h1>
          <p className="mb-6 text-center text-sm text-muted-foreground">
            Este enlace requiere una contraseña para acceder.
          </p>
          <form onSubmit={handlePasswordSubmit} className="space-y-3">
            <PasswordInput
              value={passwordInput}
              onChange={(e) => {
                setPasswordInput(e.target.value)
                setPasswordError(null)
              }}
              placeholder="Contraseña"
              error={passwordError ?? undefined}
              variant="outlined"
              autoFocus
            />
            <Button
              type="submit"
              variant="primary"
              fullWidth
              isLoading={verifyingPassword}
              loadingText="Verificando..."
            >
              Acceder
            </Button>
          </form>
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
                    const forced = await sharesService.getPublicShare(token!, path ?? undefined, {
                      forceDownload: true,
                      password: verifiedPasswordRef.current,
                    })
                    if (forced.type === 'file') {
                      window.location.assign(forced.download_url)
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
