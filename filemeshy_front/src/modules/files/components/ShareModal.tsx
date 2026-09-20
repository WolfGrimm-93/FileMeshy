/**
 * Modal de compartir (Hito 2 + Ronda 3) — lista los shares existentes de un
 * archivo/carpeta y permite crear uno nuevo, en dos modos:
 *
 * - "Link público" (comportamiento original del Hito 2): link con token,
 *   opcionalmente protegido con contraseña, siempre de solo lectura.
 * - "Compartir con alguien" (Ronda 3): share dirigido a un email puntual
 *   (sin link público), con permiso de solo lectura o edición.
 *
 * Ver contrato de API en filemeshy_back (implementado en paralelo).
 */
import { useCallback, useEffect, useState } from 'react'
import { Ban, Copy, Link2, Lock, Mail, UserPlus } from 'lucide-react'
import { Modal } from '@/ui/modals/Modal'
import { Button } from '@/ui/buttons/Button'
import { Badge } from '@/ui/badges/Badge'
import { EmailInput, Input, PasswordInput } from '@/ui/inputs/Input'
import { Select } from '@/ui/inputs/Select'
import { toast } from '@/ui/toast/CustomToast'
import { extractErrorMessage } from '@/shared/utils/errors'
import { useAuth } from '@/modules/auth/hooks/useAuth'
import { Permission } from '@/app/routes'
import { sharesService } from '../services/shares.service'
import type { ShareOut, SharePermission } from '../types'

export interface ShareTarget {
  id: string
  name: string
  type: 'file' | 'folder'
}

interface ShareModalProps {
  target: ShareTarget | null
  onClose: () => void
}

type ShareStatus = 'active' | 'revoked' | 'expired'
type ShareMode = 'link' | 'user'

const PERMISSION_OPTIONS: { value: SharePermission; label: string }[] = [
  { value: 'view', label: 'Solo lectura' },
  { value: 'edit', label: 'Puede editar' },
]

function getShareStatus(share: ShareOut): ShareStatus {
  if (share.revoked_at) return 'revoked'
  if (share.expires_at && new Date(share.expires_at).getTime() <= Date.now()) return 'expired'
  return share.is_active ? 'active' : 'expired'
}

export default function ShareModal({ target, onClose }: ShareModalProps) {
  const { hasPermission } = useAuth()
  const [shares, setShares] = useState<ShareOut[]>([])
  const [loading, setLoading] = useState(false)
  const [creating, setCreating] = useState(false)
  const [noExpiration, setNoExpiration] = useState(true)
  const [expiresAt, setExpiresAt] = useState('')

  const [shareMode, setShareMode] = useState<ShareMode>('link')
  const [password, setPassword] = useState('')
  const [sharedWithEmail, setSharedWithEmail] = useState('')
  const [permission, setPermission] = useState<SharePermission>('view')

  const resetForm = useCallback(() => {
    setNoExpiration(true)
    setExpiresAt('')
    setShareMode('link')
    setPassword('')
    setSharedWithEmail('')
    setPermission('view')
  }, [])

  const loadShares = useCallback(async () => {
    if (!target) return
    setLoading(true)
    try {
      const data =
        target.type === 'file'
          ? await sharesService.listForFile(target.id)
          : await sharesService.listForFolder(target.id)
      setShares(data)
    } catch (error: unknown) {
      toast.error(extractErrorMessage(error, 'Error al cargar los links de este elemento'))
    } finally {
      setLoading(false)
    }
  }, [target])

  useEffect(() => {
    if (target) {
      resetForm()
      loadShares()
    } else {
      setShares([])
    }
  }, [target, loadShares, resetForm])

  const handleCreate = async () => {
    if (!target) return

    const trimmedEmail = sharedWithEmail.trim()
    if (shareMode === 'user' && !trimmedEmail) {
      toast.error('Ingresá el email de la persona con quien compartir')
      return
    }

    setCreating(true)
    try {
      const params = {
        expiresAt: noExpiration ? null : expiresAt ? new Date(expiresAt).toISOString() : null,
        ...(shareMode === 'user'
          ? { sharedWithEmail: trimmedEmail, permission }
          : password.trim()
            ? { password: password.trim() }
            : {}),
      }
      if (target.type === 'file') {
        await sharesService.createForFile(target.id, params)
      } else {
        await sharesService.createForFolder(target.id, params)
      }
      toast.success(shareMode === 'user' ? 'Compartido correctamente' : 'Link creado correctamente')
      resetForm()
      await loadShares()
    } catch (error: unknown) {
      toast.error(extractErrorMessage(error, 'Error al crear el share'))
    } finally {
      setCreating(false)
    }
  }

  const handleRevoke = async (shareId: string) => {
    try {
      await sharesService.revoke(shareId)
      toast.success('Link revocado')
      await loadShares()
    } catch (error: unknown) {
      toast.error(extractErrorMessage(error, 'Error al revocar el link'))
    }
  }

  const handleCopy = async (url: string) => {
    try {
      await navigator.clipboard.writeText(url)
      toast.success('Link copiado al portapapeles')
    } catch (error: unknown) {
      toast.error(extractErrorMessage(error, 'No se pudo copiar el link'))
    }
  }

  if (!target) return null

  const statusBadge = (status: ShareStatus) => {
    if (status === 'active') return <Badge variant="success">Activo</Badge>
    if (status === 'revoked') return <Badge variant="danger">Revocado</Badge>
    return <Badge variant="gray">Expirado</Badge>
  }

  const permissionBadge = (perm: SharePermission) =>
    perm === 'edit' ? <Badge variant="info">Editor</Badge> : <Badge variant="gray">Lector</Badge>

  return (
    <Modal isOpen={!!target} onClose={onClose} title={`Compartir "${target.name}"`} size="lg">
      <div className="space-y-6">
        {hasPermission(Permission.CREATE_SHARES) && (
          <div className="space-y-3 rounded-lg border border-gray-200 p-4 dark:border-gray-700">
            <h3 className="text-sm font-semibold text-gray-900 dark:text-white">Crear nuevo link</h3>

            {/* Modo: link público vs. compartir con alguien puntual */}
            <div className="inline-flex items-center rounded-lg bg-gray-100 p-0.5 dark:bg-gray-800">
              <button
                type="button"
                onClick={() => setShareMode('link')}
                aria-pressed={shareMode === 'link'}
                className={`inline-flex items-center gap-1.5 rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${
                  shareMode === 'link'
                    ? 'bg-white text-brand-600 shadow-sm dark:bg-gray-700 dark:text-brand-400'
                    : 'text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200'
                }`}
              >
                <Link2 className="size-4" />
                Link público
              </button>
              <button
                type="button"
                onClick={() => setShareMode('user')}
                aria-pressed={shareMode === 'user'}
                className={`inline-flex items-center gap-1.5 rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${
                  shareMode === 'user'
                    ? 'bg-white text-brand-600 shadow-sm dark:bg-gray-700 dark:text-brand-400'
                    : 'text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200'
                }`}
              >
                <UserPlus className="size-4" />
                Compartir con alguien
              </button>
            </div>

            <label className="flex items-center gap-2 text-sm text-gray-700 dark:text-gray-300">
              <input
                type="checkbox"
                checked={noExpiration}
                onChange={(e) => setNoExpiration(e.target.checked)}
                className="rounded-sm border-gray-300 text-brand-600 focus:ring-2 focus:ring-brand-500 dark:border-gray-600"
              />
              Sin expiración
            </label>

            {!noExpiration && (
              <Input
                type="datetime-local"
                label="Expira el"
                value={expiresAt}
                onChange={(e) => setExpiresAt(e.target.value)}
              />
            )}

            {shareMode === 'link' ? (
              <div>
                <label className="mb-2 block text-sm font-medium text-gray-700 dark:text-gray-300">
                  Contraseña (opcional)
                </label>
                <PasswordInput
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="Dejar vacío para no proteger el link"
                  variant="outlined"
                />
              </div>
            ) : (
              <>
                <EmailInput
                  label="Email de la persona"
                  value={sharedWithEmail}
                  onChange={(e) => setSharedWithEmail(e.target.value)}
                  placeholder="persona@ejemplo.com"
                />
                <Select
                  label="Permiso"
                  options={PERMISSION_OPTIONS}
                  value={permission}
                  onChange={(e) => setPermission(e.target.value as SharePermission)}
                  placeholder=""
                />
              </>
            )}

            <Button
              variant="primary"
              leftIcon={shareMode === 'link' ? <Link2 className="size-4" /> : <UserPlus className="size-4" />}
              onClick={handleCreate}
              isLoading={creating}
              loadingText={shareMode === 'link' ? 'Creando...' : 'Compartiendo...'}
            >
              {shareMode === 'link' ? 'Crear link' : 'Compartir'}
            </Button>
          </div>
        )}

        <div className="space-y-2">
          <h3 className="text-sm font-semibold text-gray-900 dark:text-white">Links existentes</h3>

          {loading ? (
            <p className="text-sm text-gray-500 dark:text-gray-400">Cargando...</p>
          ) : shares.length === 0 ? (
            <p className="text-sm text-gray-500 dark:text-gray-400">Todavía no hay links para este elemento.</p>
          ) : (
            <ul className="space-y-2">
              {shares.map((share) => {
                const status = getShareStatus(share)
                const isDirectedShare = share.shared_with_user_id !== null
                // Un share dirigido nunca tiene `token` (el backend no genera link público
                // para él, ver ShareCreate) -- acá `token` siempre está presente en la rama
                // contraria, pero el tipo es `string | null` porque ambos casos comparten
                // el mismo ShareOut.
                const url = share.token ? `${window.location.origin}/compartido/${share.token}` : null
                return (
                  <li
                    key={share.id}
                    className="flex flex-col gap-2 rounded-lg border border-gray-200 p-3 dark:border-gray-700 sm:flex-row sm:items-center sm:justify-between"
                  >
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-1.5">
                        {share.has_password && (
                          <Lock
                            className="size-3.5 shrink-0 text-gray-500 dark:text-gray-400"
                            aria-label="Protegido con contraseña"
                          />
                        )}
                        {isDirectedShare ? (
                          <span className="flex min-w-0 items-center gap-1.5 truncate text-sm font-medium text-gray-900 dark:text-white">
                            <Mail className="size-3.5 shrink-0 text-gray-400" />
                            {share.shared_with_email ?? 'Usuario sin email visible'}
                          </span>
                        ) : (
                          <p className="truncate text-sm font-medium text-gray-900 dark:text-white">
                            {url ?? 'Link no disponible'}
                          </p>
                        )}
                      </div>
                      <p className="text-xs text-gray-500 dark:text-gray-400">
                        {share.expires_at
                          ? `Expira: ${new Date(share.expires_at).toLocaleString('es-ES')}`
                          : 'No expira'}
                      </p>
                    </div>

                    <div className="flex shrink-0 flex-wrap items-center gap-2">
                      {statusBadge(status)}
                      {permissionBadge(share.permission)}
                      {!isDirectedShare && url && (
                        <Button
                          variant="ghost"
                          size="sm"
                          leftIcon={<Copy className="size-3.5" />}
                          onClick={() => handleCopy(url)}
                        >
                          Copiar
                        </Button>
                      )}
                      {status === 'active' && hasPermission(Permission.REVOKE_SHARES) && (
                        <Button
                          variant="ghost"
                          size="sm"
                          leftIcon={<Ban className="size-3.5" />}
                          onClick={() => handleRevoke(share.id)}
                        >
                          Revocar
                        </Button>
                      )}
                    </div>
                  </li>
                )
              })}
            </ul>
          )}
        </div>
      </div>
    </Modal>
  )
}
