import { useEffect, useState } from 'react'
import { Check, Plus, Trash2 } from 'lucide-react'
import { Modal } from '@/ui/modals/Modal'
import { Button } from '@/ui/buttons/Button'
import { Input } from '@/ui/inputs/Input'
import DeleteConfirmDialog from '@/ui/dialogs/DeleteConfirmDialog'
import { toast } from '@/ui/toast/CustomToast'
import { extractErrorMessage } from '@/shared/utils/errors'
import { tagsService } from '../services/tags.service'
import { filesService } from '../services/files.service'
import { foldersService } from '../services/folders.service'
import type { TagOut } from '../types'

export interface TagsTarget {
  id: string
  type: 'file' | 'folder'
  currentTagIds: string[]
}

interface TagsModalProps {
  target: TagsTarget | null
  onClose: () => void
  onSaved: () => void
}

/** Paleta acotada para etiquetas nuevas -- evita que cada usuario tenga que tipear un hex a mano. */
const TAG_COLOR_PALETTE = [
  '#ef4444', // red
  '#f97316', // orange
  '#eab308', // yellow
  '#22c55e', // green
  '#06b6d4', // cyan
  '#3b82f6', // blue
  '#8b5cf6', // purple
  '#ec4899', // pink
]

export default function TagsModal({ target, onClose, onSaved }: TagsModalProps) {
  const [allTags, setAllTags] = useState<TagOut[]>([])
  const [selectedIds, setSelectedIds] = useState<string[]>([])
  const [loadingTags, setLoadingTags] = useState(false)
  const [saving, setSaving] = useState(false)

  const [newTagName, setNewTagName] = useState('')
  const [newTagColor, setNewTagColor] = useState<string>(TAG_COLOR_PALETTE[0])
  const [creating, setCreating] = useState(false)

  // Etiqueta pendiente de confirmación de borrado -- borrar una etiqueta es irreversible y en
  // cascada (la saca de TODOS los archivos/carpetas que la tengan, no solo del elemento
  // actual), así que pasa por el mismo diálogo de confirmación que ya usa el resto del
  // proyecto para acciones irreversibles (ver DeleteConfirmDialog en FilesPage).
  const [deleteConfirmTag, setDeleteConfirmTag] = useState<TagOut | null>(null)

  // Al abrir (cambio de target): sincronizar selección con las tags actuales del elemento
  // y recargar el catálogo completo de etiquetas del usuario -- mismo patrón target-driven
  // que RenameModal/MoveModal.
  useEffect(() => {
    if (!target) return
    setSelectedIds(target.currentTagIds)
    setNewTagName('')
    setNewTagColor(TAG_COLOR_PALETTE[0])

    let cancelled = false
    setLoadingTags(true)
    tagsService
      .list()
      .then((tags) => {
        if (!cancelled) setAllTags(tags)
      })
      .catch((error: unknown) => {
        if (!cancelled) toast.error(extractErrorMessage(error, 'Error al cargar etiquetas'))
      })
      .finally(() => {
        if (!cancelled) setLoadingTags(false)
      })

    return () => {
      cancelled = true
    }
  }, [target])

  const handleClose = () => {
    if (saving || creating) return
    onClose()
  }

  const toggleTag = (tagId: string) => {
    setSelectedIds((prev) => (prev.includes(tagId) ? prev.filter((id) => id !== tagId) : [...prev, tagId]))
  }

  const handleCreateTag = async () => {
    const trimmed = newTagName.trim()
    if (!trimmed) {
      toast.error('El nombre de la etiqueta no puede estar vacío')
      return
    }

    setCreating(true)
    try {
      const tag = await tagsService.create(trimmed, newTagColor)
      setAllTags((prev) => [...prev, tag])
      setSelectedIds((prev) => [...prev, tag.id])
      setNewTagName('')
      toast.success('Etiqueta creada correctamente')
    } catch (error: unknown) {
      toast.error(extractErrorMessage(error, 'Error al crear la etiqueta'))
    } finally {
      setCreating(false)
    }
  }

  const confirmDeleteTag = async () => {
    if (!deleteConfirmTag) return
    const tag = deleteConfirmTag
    try {
      await tagsService.remove(tag.id)
      setAllTags((prev) => prev.filter((t) => t.id !== tag.id))
      setSelectedIds((prev) => prev.filter((id) => id !== tag.id))
      toast.success('Etiqueta eliminada correctamente')
      // El borrado ya se aplicó de verdad contra el backend en este mismo click -- no es
      // parte de un "borrador" que "Cancelar" deba poder descartar. Si no se avisa acá,
      // cerrar el modal con Cancelar deja al listado padre con una etiqueta fantasma que ya
      // no existe en el backend.
      onSaved()
    } catch (error: unknown) {
      toast.error(extractErrorMessage(error, 'Error al eliminar la etiqueta'))
    }
  }

  const handleSubmit = async () => {
    if (!target) return
    setSaving(true)
    try {
      if (target.type === 'folder') {
        await foldersService.setTags(target.id, selectedIds)
      } else {
        await filesService.setTags(target.id, selectedIds)
      }
      toast.success('Etiquetas actualizadas correctamente')
      onSaved()
      onClose()
    } catch (error: unknown) {
      toast.error(extractErrorMessage(error, 'Error al actualizar etiquetas'))
    } finally {
      setSaving(false)
    }
  }

  return (
    <>
      <Modal
        isOpen={!!target}
        onClose={handleClose}
        title="Etiquetas"
        size="sm"
        footer={
          <div className="flex justify-end gap-2">
            <Button variant="ghost" onClick={handleClose} disabled={saving}>
              Cancelar
            </Button>
            <Button
              variant="primary"
              leftIcon={<Check className="size-4" />}
              onClick={handleSubmit}
              isLoading={saving}
              loadingText="Guardando..."
            >
              Guardar
            </Button>
          </div>
        }
      >
        <div className="space-y-4">
          <div>
            <p className="mb-2 text-sm font-medium text-gray-700 dark:text-gray-300">
              Seleccioná las etiquetas para este elemento
            </p>

            {loadingTags ? (
              <p className="text-sm text-gray-500 dark:text-gray-400">Cargando etiquetas...</p>
            ) : allTags.length === 0 ? (
              <p className="text-sm text-gray-500 dark:text-gray-400">Todavía no creaste ninguna etiqueta.</p>
            ) : (
              <div className="flex flex-wrap gap-2">
                {allTags.map((tag) => {
                  const isSelected = selectedIds.includes(tag.id)
                  return (
                    <div key={tag.id} className="relative">
                      <button
                        type="button"
                        onClick={() => toggleTag(tag.id)}
                        style={{ backgroundColor: tag.color ?? undefined }}
                        className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-sm font-medium text-white transition-all ${
                          tag.color ? '' : 'bg-gray-400 dark:bg-gray-600'
                        } ${
                          isSelected
                            ? 'ring-2 ring-offset-2 ring-brand-500 dark:ring-offset-gray-900'
                            : 'opacity-50 hover:opacity-80'
                        }`}
                      >
                        {isSelected && <Check className="size-3.5" />}
                        {tag.name}
                      </button>
                      {/* Siempre visible (no solo al hover): en mobile no hay hover real y
                          navegando con teclado el foco cae en este botón, así que ocultarlo
                          por default lo dejaba inalcanzable sin mouse. */}
                      <button
                        type="button"
                        onClick={() => setDeleteConfirmTag(tag)}
                        title="Eliminar etiqueta"
                        aria-label={`Eliminar etiqueta ${tag.name}`}
                        className="absolute -right-1.5 -top-1.5 flex size-4 items-center justify-center rounded-full bg-gray-700 text-white hover:bg-red-600 focus:outline-hidden focus-visible:ring-2 focus-visible:ring-red-500 focus-visible:ring-offset-1"
                      >
                        <Trash2 className="size-2.5" />
                      </button>
                    </div>
                  )
                })}
              </div>
            )}
          </div>

          <div className="border-t border-gray-200 pt-4 dark:border-gray-700">
            <p className="mb-2 text-sm font-medium text-gray-700 dark:text-gray-300">Crear etiqueta nueva</p>
            <div className="flex items-center gap-2">
              <Input
                value={newTagName}
                onChange={(e) => setNewTagName(e.target.value)}
                placeholder="Nombre de la etiqueta"
                fullWidth
                onKeyDown={(e) => {
                  if (e.key === 'Enter') handleCreateTag()
                }}
              />
              <Button
                variant="secondary"
                leftIcon={<Plus className="size-4" />}
                onClick={handleCreateTag}
                isLoading={creating}
                disabled={creating}
              >
                Crear
              </Button>
            </div>
            <div className="mt-2 flex items-center gap-1.5">
              {TAG_COLOR_PALETTE.map((color) => (
                <button
                  key={color}
                  type="button"
                  onClick={() => setNewTagColor(color)}
                  aria-label={`Color ${color}`}
                  style={{ backgroundColor: color }}
                  className={`size-5 rounded-full transition-transform ${
                    newTagColor === color ? 'scale-110 ring-2 ring-offset-1 ring-gray-900 dark:ring-white' : ''
                  }`}
                />
              ))}
            </div>
          </div>
        </div>
      </Modal>

      <DeleteConfirmDialog
        isOpen={!!deleteConfirmTag}
        onClose={() => setDeleteConfirmTag(null)}
        onConfirm={confirmDeleteTag}
        title="Eliminar etiqueta"
        description={`¿Eliminar la etiqueta "${deleteConfirmTag?.name}"? Se va a quitar de todos los archivos y carpetas que la tengan.`}
      />
    </>
  )
}
