import { useEffect, useState } from 'react'
import { Modal } from '@/ui/modals/Modal'
import { Button } from '@/ui/buttons/Button'
import type { FilterGroup, FilterValues } from './types'
import { renderFilterField } from './inputs'

export interface FilterModalProps {
  isOpen: boolean
  onClose: () => void
  title?: string
  groups: FilterGroup[]
  /** Valores realmente aplicados (los del store de la vista). Solo se leen al abrir. */
  values: FilterValues
  onApply: (values: FilterValues) => void
  /** Llamado además de onApply(vacío) cuando se presiona "Limpiar todo". */
  onClear?: () => void
  size?: 'sm' | 'md' | 'lg' | 'xl' | '2xl' | '3xl' | '4xl'
}

/**
 * Modal genérico de filtros: la vista declara `groups` (qué campos mostrar y
 * de qué tipo) y le pasa sus `values`/`onApply` actuales -- no conoce
 * Zustand ni Axios, solo maneja el borrador local del formulario.
 *
 * Estado en borrador: los cambios de campo solo tocan `draft`, nunca llaman a
 * `onApply` directamente. Recién al presionar "Aplicar" se escribe al estado
 * real de la vista. Cancelar / Escape / clic en overlay descartan `draft` sin
 * efecto -- corrige el bug que existe hoy en AccountsPayableTab/
 * AccountsReceivableTab, donde cada cambio escribe directo al store y
 * "Cancelar" no revierte nada.
 */
export function FilterModal({
  isOpen,
  onClose,
  title = 'Filtrar por',
  groups,
  values,
  onApply,
  onClear,
  size = 'lg',
}: FilterModalProps) {
  const [draft, setDraft] = useState<FilterValues>(values)

  // Re-sincronizar el borrador con el estado real cada vez que se abre --
  // así el modal siempre refleja los filtros ya aplicados, no un borrador viejo.
  useEffect(() => {
    if (isOpen) setDraft(values)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isOpen])

  const handleFieldChange = (key: string, value: unknown) => {
    setDraft((prev) => ({ ...prev, [key]: value }))
  }

  const handleApply = () => {
    onApply(draft)
    onClose()
  }

  const handleClearAll = () => {
    const empty: FilterValues = {}
    setDraft(empty)
    onClear?.()
    onApply(empty)
    onClose()
  }

  const allFields = groups.flatMap((g) => g.fields)
  const firstFieldKey = allFields[0]?.key

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title={title}
      size={size}
      footer={
        <div className="flex items-center justify-between gap-2">
          <Button variant="ghost" size="sm" onClick={handleClearAll}>
            Limpiar todo
          </Button>
          <div className="flex gap-2">
            <Button variant="ghost" onClick={onClose}>
              Cancelar
            </Button>
            <Button variant="primary" onClick={handleApply}>
              Aplicar
            </Button>
          </div>
        </div>
      }
    >
      <div className="space-y-5">
        {groups.map((group, gi) => (
          <div key={group.title ?? gi} className="space-y-3">
            {group.title && (
              <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                {group.title}
              </p>
            )}
            <div className="space-y-4">
              {group.fields.map((field) => (
                <div key={field.key}>
                  {renderFilterField(field, draft, handleFieldChange, field.key === firstFieldKey)}
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>
    </Modal>
  )
}
