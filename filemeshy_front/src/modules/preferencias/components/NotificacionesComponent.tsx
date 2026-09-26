/**
 * COMPONENTE - NOTIFICACIONES
 * Gestiona preferencias de notificaciones por email, sistema y resúmenes
 */
import { useState, useEffect, useCallback } from 'react'
import { Bell, Mail, Monitor, CheckCircle2, Save, Loader2 } from 'lucide-react'
import { toast } from '@/ui/toast/CustomToast'
import { userPreferencesService } from '@/modules/configuration/services/user-preferences.service'
import type { UserPreferences, UserPreferencesUpdate } from '../types'
import { useAuth } from '@/modules/auth/hooks/useAuth'

interface NotificacionesProps {
  onSave?: () => void
}

// Interruptor: definido a nivel de módulo (no dentro del render) para no remontarse en cada render
function Toggle({ checked, onChange }: { checked: boolean; onChange: () => void }) {
  return (
    <button
      type="button"
      onClick={onChange}
      className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${
        checked ? 'bg-brand-600' : 'bg-gray-300 dark:bg-gray-600'
      }`}
    >
      <span
        className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
          checked ? 'translate-x-6' : 'translate-x-1'
        }`}
      />
    </button>
  )
}

export default function NotificacionesComponent({ onSave }: NotificacionesProps) {
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [, setPreferences] = useState<UserPreferences | null>(null)
  const { user } = useAuth()
  const userEmail = user?.email
  const [formData, setFormData] = useState<UserPreferencesUpdate>({
    email_notifications: false,
    system_notifications: false
  })


  // Núcleo del fetch (sin setState síncrono; `loading` arranca en true)
  const fetchPreferences = useCallback(
    () =>
      userPreferencesService
        .getMyPreferences()
        .then((data) => {
          setPreferences(data as unknown as UserPreferences)
          setFormData({
            email_notifications: data.email_notifications,
            system_notifications: data.system_notifications
          })
        })
        .catch((error) => {
          console.error('Error cargando preferencias:', error)
          toast.error('Error al cargar preferencias de notificaciones')
        })
        .finally(() => setLoading(false)),
    []
  )

  // Recarga explícita (tras guardar): vuelve a mostrar el spinner
  const loadPreferences = async () => {
    setLoading(true)
    await fetchPreferences()
  }

  useEffect(() => {
    fetchPreferences()
  }, [fetchPreferences])

  const handleToggle = (field: keyof UserPreferencesUpdate) => {
    setFormData(prev => ({ ...prev, [field]: !prev[field] }))
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    
    try {
      setSaving(true)
      await userPreferencesService.updateMyPreferences(formData)
      toast.success('Preferencias de notificaciones actualizadas')
      await loadPreferences()
      onSave?.()
    } catch (error) {
      console.error('Error actualizando preferencias:', error)
      toast.error('Error al actualizar las preferencias')
    } finally {
      setSaving(false)
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12">
        <Loader2 className="w-8 h-8 animate-spin text-brand-600" />
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h3 className="text-xl font-semibold text-foreground mb-2">
          Notificaciones
        </h3>
        <p className="text-sm text-muted-foreground">
          Configura cómo y cuándo quieres recibir notificaciones
        </p>
      </div>

      <form onSubmit={handleSubmit} className="space-y-6">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {/* Notificaciones por Email */}
          <div className="bg-muted rounded-xl border border-border p-5">
            <div className="flex items-center space-x-3 mb-4">
              <div className="bg-blue-600 text-white p-2 rounded-lg">
                <Mail size={18} />
              </div>
              <div className="flex-1">
                <h4 className="font-semibold text-foreground text-sm">
                  Notificaciones por Email
                </h4>
                <p className="text-xs text-muted-foreground">
                  Recibe actualizaciones en tu correo
                </p>
              </div>
            </div>

            <div className="flex items-center justify-between p-3 bg-card rounded-lg">
              <div className="flex items-center space-x-2">
                <Mail className="text-muted-foreground" size={18} />
                <span className="font-medium text-sm text-foreground">
                  Activar notificaciones
                </span>
              </div>
              <Toggle
                checked={formData.email_notifications || false}
                onChange={() => handleToggle('email_notifications')}
              />
            </div>

            {formData.email_notifications && userEmail && (
              <div className="mt-3 bg-blue-50 dark:bg-blue-900/20 rounded-lg p-3 border border-blue-200 dark:border-blue-800">
                <div className="flex items-start space-x-2">
                  <CheckCircle2 className="text-blue-600 mt-0.5 shrink-0" size={16} />
                  <div className="text-xs text-foreground/80">
                    <p className="font-medium mb-0.5">Recibirás notificaciones en:</p>
                    <p className="text-blue-600">{userEmail}</p>
                  </div>
                </div>
              </div>
            )}
          </div>

          {/* Notificaciones del Sistema */}
          <div className="bg-muted rounded-xl border border-border p-5">
            <div className="flex items-center space-x-3 mb-4">
              <div className="bg-purple-600 text-white p-2 rounded-lg">
                <Monitor size={18} />
              </div>
              <div className="flex-1">
                <h4 className="font-semibold text-foreground text-sm">
                  Notificaciones del Sistema
                </h4>
                <p className="text-xs text-muted-foreground">
                  Alertas dentro de la aplicación
                </p>
              </div>
            </div>

            <div className="flex items-center justify-between p-3 bg-card rounded-lg">
              <div className="flex items-center space-x-2">
                <Bell className="text-muted-foreground" size={18} />
                <span className="font-medium text-sm text-foreground">
                  Alertas en tiempo real
                </span>
              </div>
              <Toggle
                checked={formData.system_notifications || false}
                onChange={() => handleToggle('system_notifications')}
              />
            </div>

            {formData.system_notifications && (
              <div className="mt-3 p-3 bg-card rounded-lg border border-border text-center">
                <p className="text-xs text-muted-foreground">
                  Todavía no hay categorías para elegir. Vas a poder configurarlas por evento
                  cuando existan notificaciones reales del dominio de archivos (ej. archivo
                  compartido, cuota de almacenamiento al límite).
                </p>
              </div>
            )}
          </div>
        </div>

        {/* Nota Informativa */}
        <div className="bg-brand-50 dark:bg-brand-900/20 rounded-lg p-4 border border-brand-200 dark:border-brand-800">
          <div className="flex items-start space-x-3">
            <Bell className="text-brand-600 mt-0.5 shrink-0" size={18} />
            <div className="text-sm text-foreground/80">
              <p className="font-medium mb-1">Sobre las notificaciones</p>
              <p>
                Las notificaciones te ayudan a mantenerte informado. Puedes personalizar qué tipo de notificaciones deseas recibir en cualquier momento.
              </p>
            </div>
          </div>
        </div>

        {/* Botón Guardar */}
        <div className="flex justify-end pt-4 border-t border-border">
          <button
            type="submit"
            disabled={saving}
            className="px-6 py-2.5 bg-brand-600 text-white rounded-lg hover:bg-brand-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center space-x-2"
          >
            {saving ? (
              <>
                <Loader2 className="w-4 h-4 animate-spin" />
                <span>Guardando...</span>
              </>
            ) : (
              <>
                <Save size={16} />
                <span>Guardar Preferencias</span>
              </>
            )}
          </button>
        </div>
      </form>
    </div>
  )
}
