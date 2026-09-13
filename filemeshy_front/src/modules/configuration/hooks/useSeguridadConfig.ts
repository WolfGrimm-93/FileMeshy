import { useState, useEffect, useCallback } from 'react'
import { toast } from '@/ui/toast/CustomToast'
import { adminConfigurationService } from '../services/admin-configuration.service'
import type { TurnstileConfigUpdate } from '../services/admin-configuration.service'

export interface SeguridadForm {
  turnstileEnabled: boolean
  turnstileSiteKey: string
  turnstileSecretKey: string        // solo escritura, nunca se pre-carga
  turnstileSecretKeyConfigured: boolean
}

const DEFAULT_FORM: SeguridadForm = {
  turnstileEnabled: false,
  turnstileSiteKey: '',
  turnstileSecretKey: '',
  turnstileSecretKeyConfigured: false,
}

export function useSeguridadConfig() {
  const [form, setForm] = useState<SeguridadForm | null>(null)
  const [initial, setInitial] = useState<SeguridadForm | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [isSaving, setIsSaving] = useState(false)

  useEffect(() => {
    const load = async () => {
      try {
        const ts = await adminConfigurationService.getTurnstileConfig()
        const loaded: SeguridadForm = {
          turnstileEnabled: ts.enabled ?? false,
          turnstileSiteKey: ts.site_key || '',
          turnstileSecretKey: '',
          turnstileSecretKeyConfigured: ts.secret_key_configured ?? false,
        }
        setForm(loaded)
        setInitial(loaded)
      } catch {
        setForm(DEFAULT_FORM)
        setInitial(DEFAULT_FORM)
      } finally {
        setIsLoading(false)
      }
    }
    load()
  }, [])

  const isDirty = form !== null && initial !== null && JSON.stringify(form) !== JSON.stringify(initial)

  const saveConfig = useCallback(async () => {
    if (!form) return
    setIsSaving(true)
    try {
      const payload: TurnstileConfigUpdate = {
        enabled: form.turnstileEnabled,
        site_key: form.turnstileSiteKey,
        ...(form.turnstileSecretKey ? { secret_key: form.turnstileSecretKey } : {}),
      }
      await adminConfigurationService.updateTurnstileConfig(payload)
      const clean: SeguridadForm = {
        ...form,
        turnstileSecretKey: '',
        turnstileSecretKeyConfigured: form.turnstileSecretKey ? true : form.turnstileSecretKeyConfigured,
      }
      setForm(clean)
      setInitial(clean)
      localStorage.setItem('filemeshy_config_updated', Date.now().toString())
      toast.success('Configuración guardada correctamente')
    } catch (err: unknown) {
      const detalle = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
        || 'Error al guardar la configuración'
      toast.error(detalle)
    } finally {
      setIsSaving(false)
    }
  }, [form])

  return { form, setForm, isLoading, isSaving, isDirty, saveConfig }
}
