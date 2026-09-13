/**
 * Modal de compartir por link (Hito 2) — lista los shares existentes de un
 * archivo/carpeta y permite crear uno nuevo (con o sin expiración) o revocar
 * uno activo. Ver contrato de API en filemeshy_back (implementado en paralelo).
 */
import { useCallback, useEffect, useState } from 'react'
import { Ban, Copy, Link2 } from 'lucide-react'
import { Modal } from '@/ui/modals/Modal'
import { Button } from '@/ui/buttons/Button'
import { Badge } from '@/ui/badges/Badge'
import { Input } from '@/ui/inputs/Input'
import { toast } from '@/ui/toast/CustomToast'
import { extractErrorMessage } from '@/shared/utils/errors'
import { useAuth } from '@/modules/auth/hooks/useAuth'
import { Permission } from '@/app/routes'
import { sharesService } from '../services/shares.service'
import type { ShareOut } from '../types'

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
      setNoExpiration(true)
      setExpiresAt('')
      loadShares()
    } else {
      setShares([])
    }
  }, [target, loadShares])

  const handleCreate = async () => {
    if (!target) return
    setCreating(true)
    try {
      const params = {
        expiresAt: noExpiration ? null : expiresAt ? new Date(expiresAt).toISOString() : null,
      }
      if (target.type === 'file') {
        await sharesService.createForFile(target.id, params)
      } else {
        await sharesService.createForFolder(target.id, params)
      }
      toast.success('Link creado correctamente')
      setNoExpiration(true)
      setExpiresAt('')
      await loadShares()
    } catch (error: unknown) {
      toast.error(extractErrorMessage(error, 'Error al crear el link'))
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

  const handleCopy = async (token: string) => {
    const url = `${window.location.origin}/compartido/${token}`
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

  return (
    <Modal isOpen={!!target} onClose={onClose} title={`Compartir "${target.name}"`} size="lg">
      <div className="space-y-6">
        {hasPermission(Permission.CREATE_SHARES) && (
          <div className="space-y-3 rounded-lg border border-gray-200 p-4 dark:border-gray-700">
            <h3 className="text-sm font-semibold text-gray-900 dark:text-white">Crear nuevo link</h3>

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

            <Button
              variant="primary"
              leftIcon={<Link2 className="size-4" />}
              onClick={handleCreate}
              isLoading={creating}
              loadingText="Creando..."
            >
              Crear link
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
                const url = `${window.location.origin}/compartido/${share.token}`
                return (
                  <li
                    key={share.id}
                    className="flex flex-col gap-2 rounded-lg border border-gray-200 p-3 dark:border-gray-700 sm:flex-row sm:items-center sm:justify-between"
                  >
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-sm font-medium text-gray-900 dark:text-white">{url}</p>
                      <p className="text-xs text-gray-500 dark:text-gray-400">
                        {share.expires_at
                          ? `Expira: ${new Date(share.expires_at).toLocaleString('es-ES')}`
                          : 'No expira'}
                      </p>
                    </div>

                    <div className="flex shrink-0 items-center gap-2">
                      {statusBadge(status)}
                      <Button
                        variant="ghost"
                        size="sm"
                        leftIcon={<Copy className="size-3.5" />}
                        onClick={() => handleCopy(share.token)}
                      >
                        Copiar
                      </Button>
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
