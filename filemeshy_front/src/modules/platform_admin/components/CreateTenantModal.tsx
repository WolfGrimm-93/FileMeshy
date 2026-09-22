/**
 * Modal de alta de tenant nuevo.
 *
 * Validación client-side de slug/schema_name replica los mismos patterns
 * que exige el backend (`SLUG_PATTERN`/`SCHEMA_NAME_PATTERN` en
 * `app/platform/schemas.py`) -- solo para feedback temprano, la validación
 * real la sigue haciendo el backend igual (400 con `{detail}` si falla).
 */
import { useState, type FormEvent } from 'react'
import { Modal } from '@/ui/modals/Modal'
import { Button } from '@/ui/buttons/Button'
import { Input } from '@/ui/inputs/Input'
import type { TenantCreatePayload } from '../services/tenants.service'

// Mismos patrones que el backend (app/platform/schemas.py) -- ver comentario
// de arriba.
const SLUG_PATTERN = /^[a-z][a-z0-9-]{1,62}$/
const SCHEMA_NAME_PATTERN = /^[a-z][a-z0-9_]{2,62}$/

interface CreateTenantModalProps {
  isOpen: boolean
  onClose: () => void
  onSubmit: (payload: TenantCreatePayload) => Promise<void>
}

interface FormState {
  slug: string
  schema_name: string
  company_name: string
  plan: string
}

const EMPTY_FORM: FormState = { slug: '', schema_name: '', company_name: '', plan: '' }

export function CreateTenantModal({ isOpen, onClose, onSubmit }: CreateTenantModalProps) {
  const [form, setForm] = useState<FormState>(EMPTY_FORM)
  const [errors, setErrors] = useState<Partial<Record<keyof FormState, string>>>({})
  const [isSubmitting, setIsSubmitting] = useState(false)

  const handleClose = () => {
    if (isSubmitting) return
    setForm(EMPTY_FORM)
    setErrors({})
    onClose()
  }

  const validate = (): boolean => {
    const nextErrors: Partial<Record<keyof FormState, string>> = {}

    if (!SLUG_PATTERN.test(form.slug)) {
      nextErrors.slug = 'Minúsculas, números y guiones -- debe empezar con una letra (ej. acme-corp).'
    }
    if (!SCHEMA_NAME_PATTERN.test(form.schema_name)) {
      nextErrors.schema_name = 'Minúsculas, números y guion bajo -- debe empezar con una letra (ej. tenant_acme_corp).'
    }
    if (!form.company_name.trim()) {
      nextErrors.company_name = 'La razón social es obligatoria.'
    }

    setErrors(nextErrors)
    return Object.keys(nextErrors).length === 0
  }

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault()
    if (!validate() || isSubmitting) return

    setIsSubmitting(true)
    try {
      await onSubmit({
        slug: form.slug.trim(),
        schema_name: form.schema_name.trim(),
        company_name: form.company_name.trim(),
        plan: form.plan.trim() || undefined,
      })
      setForm(EMPTY_FORM)
      setErrors({})
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <Modal isOpen={isOpen} onClose={handleClose} title="Crear tenant" size="md">
      <form onSubmit={handleSubmit} className="space-y-4">
        <Input
          label="Slug"
          placeholder="acme-corp"
          value={form.slug}
          onChange={(e) => setForm((f) => ({ ...f, slug: e.target.value }))}
          error={errors.slug}
          helperText="Identificador público (URLs/headers)."
          disabled={isSubmitting}
          autoFocus
        />

        <Input
          label="Schema (Postgres)"
          placeholder="tenant_acme_corp"
          value={form.schema_name}
          onChange={(e) => setForm((f) => ({ ...f, schema_name: e.target.value }))}
          error={errors.schema_name}
          helperText="Nombre del schema de Postgres para este tenant."
          disabled={isSubmitting}
        />

        <Input
          label="Empresa"
          placeholder="Acme Corp S.A."
          value={form.company_name}
          onChange={(e) => setForm((f) => ({ ...f, company_name: e.target.value }))}
          error={errors.company_name}
          helperText="Razón social / nombre comercial."
          disabled={isSubmitting}
        />

        <Input
          label="Plan"
          placeholder="standard"
          value={form.plan}
          onChange={(e) => setForm((f) => ({ ...f, plan: e.target.value }))}
          helperText="Opcional -- por defecto 'standard'."
          disabled={isSubmitting}
        />

        <div className="flex justify-end gap-2 pt-2">
          <Button type="button" variant="secondary" onClick={handleClose} disabled={isSubmitting}>
            Cancelar
          </Button>
          <Button type="submit" variant="primary" isLoading={isSubmitting} loadingText="Creando...">
            Crear tenant
          </Button>
        </div>
      </form>
    </Modal>
  )
}
