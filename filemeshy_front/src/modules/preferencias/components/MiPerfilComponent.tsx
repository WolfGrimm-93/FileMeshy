/**
 * COMPONENTE - MI PERFIL
 * Gestiona la información personal del usuario: nombre, email, teléfono, foto de perfil
 */
import { useState, useEffect, useRef, useCallback } from 'react'
import { User as UserIcon, Mail, Phone, Save, Loader2, Camera } from 'lucide-react'
import { toast } from '@/ui/toast/CustomToast'
import { useAuth } from '@/modules/auth/hooks/useAuth'
import { useAuthStore } from '@/modules/auth/store/authStore'
import { extractErrorMessage } from '@/shared/utils/errors'
import { userService } from '@/modules/users/services/user.service'
import type { User, UserUpdate } from '@/modules/users/services/user.service'
import { formatDateMedium } from '@/shared/utils/dates'

const AVATAR_TYPES = ['image/jpeg', 'image/png', 'image/webp', 'image/gif']
const AVATAR_MAX_BYTES = 5 * 1024 * 1024

interface MiPerfilProps {
  onSave?: () => void
}

export default function MiPerfilComponent({ onSave }: MiPerfilProps) {
  const { user: authUser } = useAuth()
  // `loading` se deriva: recarga explícita en curso, o aún no cargado para el usuario actual
  const [reloading, setReloading] = useState(false)
  const [loadedFor, setLoadedFor] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const [uploadingAvatar, setUploadingAvatar] = useState(false)
  const [profile, setProfile] = useState<User | null>(null)
  const [previewAvatar, setPreviewAvatar] = useState<string | null>(null)
  const [failedAvatar, setFailedAvatar] = useState<string | null>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const [formData, setFormData] = useState<UserUpdate>({
    first_name: '',
    last_name: '',
    phone: '',
    email: ''
  })


  const userId = authUser?.id
  const loading = reloading || !userId || loadedFor !== userId

  // Núcleo del fetch (sin setState síncrono). `isStale` descarta respuestas de un usuario anterior
  const fetchProfile = useCallback((isStale: () => boolean = () => false) => {
    if (!userId) return Promise.resolve()
    return userService
      .getUser(userId)
      .then((data) => {
        if (isStale()) return
        setProfile(data)
        setFormData({
          first_name: data.first_name,
          last_name: data.last_name,
          phone: data.phone || '',
          email: data.email
        })
        setPreviewAvatar(data.avatar || null)
      })
      .catch((error) => {
        if (isStale()) return
        console.error('Error cargando perfil:', error)
        toast.error('Error al cargar tu perfil')
      })
      .finally(() => {
        if (isStale()) return
        setLoadedFor(userId)
        setReloading(false)
      })
  }, [userId])

  // Recarga explícita (tras guardar): vuelve a mostrar el spinner
  const loadProfile = async () => {
    if (!userId) return
    setReloading(true)
    await fetchProfile()
  }

  useEffect(() => {
    let cancelled = false
    fetchProfile(() => cancelled)
    return () => {
      cancelled = true
    }
  }, [fetchProfile])

  const handleInputChange = (field: keyof UserUpdate, value: string) => {
    setFormData(prev => ({ ...prev, [field]: value }))
  }

  const handleAvatarClick = () => {
    fileInputRef.current?.click()
  }

  // El avatar se sube SOLO por el endpoint multipart (POST /users/{id}/avatar); el backend
  // lo guarda en MinIO y devuelve el usuario con la URL pública en `avatar`.
  const handleAvatarChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    // Permitir volver a elegir el mismo archivo
    e.target.value = ''
    if (!file || !authUser) return

    if (!AVATAR_TYPES.includes(file.type)) {
      toast.error('Solo se permiten imágenes JPG, PNG, WEBP o GIF')
      return
    }
    if (file.size > AVATAR_MAX_BYTES) {
      toast.error('La imagen no debe superar 5 MB')
      return
    }

    try {
      setUploadingAvatar(true)
      const updated = await userService.uploadAvatar(authUser.id, file)
      setPreviewAvatar(updated.avatar || null)
      // Reflejar la nueva URL en el usuario de sesión (Navbar y demás)
      useAuthStore.getState().login({ ...authUser, avatar: updated.avatar || undefined })
      toast.success('Foto de perfil actualizada')
    } catch (error) {
      console.error('Error subiendo avatar:', error)
      toast.error(extractErrorMessage(error, 'No se pudo subir la foto de perfil'))
    } finally {
      setUploadingAvatar(false)
    }
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!authUser) return

    try {
      setSaving(true)
      await userService.updateUser(authUser.id, formData)
      toast.success('Perfil actualizado exitosamente')
      await loadProfile()
      onSave?.()
    } catch (error) {
      console.error('Error actualizando perfil:', error)
      toast.error('Error al actualizar tu perfil')
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
          Mi Perfil
        </h3>
        <p className="text-sm text-muted-foreground">
          Actualiza tu información personal
        </p>
      </div>

      {/* Formulario */}
      <form onSubmit={handleSubmit} className="space-y-6">
        <div className="flex flex-col md:flex-row gap-6">
          {/* Sección Izquierda: Avatar */}
          <div className="md:w-64 flex flex-col items-center space-y-4">
            {/* Avatar */}
            <div className="relative group">
              <div className="w-40 h-40 rounded-full overflow-hidden bg-gray-200 dark:bg-gray-700 border-4 border-white dark:border-gray-800 shadow-lg">
                {previewAvatar && failedAvatar !== previewAvatar ? (
                  <img
                    src={previewAvatar}
                    alt="Avatar"
                    onError={() => setFailedAvatar(previewAvatar)}
                    className="w-full h-full object-cover"
                  />
                ) : (
                  <div className="w-full h-full flex items-center justify-center bg-linear-to-br from-brand-400 to-brand-600">
                    <UserIcon className="w-20 h-20 text-white" />
                  </div>
                )}
              </div>
              
              {/* Botón de cambiar foto */}
              <button
                type="button"
                onClick={handleAvatarClick}
                disabled={uploadingAvatar}
                className="absolute bottom-0 right-0 bg-brand-600 text-white p-3 rounded-full shadow-lg hover:bg-brand-700 transition-colors group-hover:scale-110"
              >
                <Camera size={20} />
              </button>
              
              <input
                ref={fileInputRef}
                type="file"
                accept="image/*"
                onChange={handleAvatarChange}
                className="hidden"
              />
            </div>

            {/* Info del archivo */}
            <div className="text-center">
              <p className="text-xs text-muted-foreground">
                Máximo 5 MB
              </p>
              <p className="text-xs text-muted-foreground">
                JPG, PNG, WEBP o GIF
              </p>
            </div>

            {/* Información de la cuenta */}
            {profile && (
              <div className="w-full bg-brand-50 dark:bg-brand-900/20 rounded-xl p-4 border border-brand-200 dark:border-brand-800">
                <div className="space-y-2 text-sm">
                  <div>
                    <span className="text-muted-foreground">Rol:</span>
                    <span className="ml-2 font-medium text-foreground">
                      {profile.role}
                    </span>
                  </div>
                  <div>
                    <span className="text-muted-foreground">Estado:</span>
                    <span className={`ml-2 font-medium ${profile.is_active ? 'text-green-600' : 'text-red-600'}`}>
                      {profile.is_active ? 'Activo' : 'Inactivo'}
                    </span>
                  </div>
                  {profile.created_at && (
                    <div>
                      <span className="text-muted-foreground">Miembro desde:</span>
                      <span className="ml-2 font-medium text-foreground block">
                        {formatDateMedium(profile.created_at) ?? ''}
                      </span>
                    </div>
                  )}
                </div>
              </div>
            )}
          </div>

          {/* Sección Derecha: Formulario */}
          <div className="flex-1 space-y-6">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {/* Nombre */}
              <div className="space-y-2">
                <label className="block text-sm font-medium text-foreground/80" htmlFor="mi-perfil-1">
                  Nombre
                </label>
                <div className="relative">
                  <UserIcon className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" size={18} />
                  <input id="mi-perfil-1"
                    type="text"
                    value={formData.first_name}
                    onChange={(e) => handleInputChange('first_name', e.target.value)}
                    className="w-full pl-10 pr-4 py-2.5 bg-muted border border-input rounded-lg focus:ring-2 focus:ring-brand-500 focus:border-transparent text-foreground"
                    placeholder="Tu nombre"
                    required
                  />
                </div>
              </div>

              {/* Apellido */}
              <div className="space-y-2">
                <label className="block text-sm font-medium text-foreground/80" htmlFor="mi-perfil-2">
                  Apellido
                </label>
                <div className="relative">
                  <UserIcon className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" size={18} />
                  <input id="mi-perfil-2"
                    type="text"
                    value={formData.last_name}
                    onChange={(e) => handleInputChange('last_name', e.target.value)}
                    className="w-full pl-10 pr-4 py-2.5 bg-muted border border-input rounded-lg focus:ring-2 focus:ring-brand-500 focus:border-transparent text-foreground"
                    placeholder="Tu apellido"
                    required
                  />
                </div>
              </div>
            </div>

            {/* Email */}
            <div className="space-y-2">
              <label className="block text-sm font-medium text-foreground/80" htmlFor="mi-perfil-3">
                Correo Electrónico
              </label>
              <div className="relative">
                <Mail className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" size={18} />
                <input id="mi-perfil-3"
                  type="email"
                  value={formData.email}
                  onChange={(e) => handleInputChange('email', e.target.value)}
                  className="w-full pl-10 pr-4 py-2.5 bg-muted border border-input rounded-lg focus:ring-2 focus:ring-brand-500 focus:border-transparent text-foreground"
                  placeholder="tu@email.com"
                  required
                />
              </div>
            </div>

            {/* Teléfono */}
            <div className="space-y-2">
              <label className="block text-sm font-medium text-foreground/80" htmlFor="mi-perfil-4">
                Teléfono <span className="text-gray-400">(opcional)</span>
              </label>
              <div className="relative">
                <Phone className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" size={18} />
                <input id="mi-perfil-4"
                  type="tel"
                  value={formData.phone}
                  onChange={(e) => handleInputChange('phone', e.target.value)}
                  className="w-full pl-10 pr-4 py-2.5 bg-muted border border-input rounded-lg focus:ring-2 focus:ring-brand-500 focus:border-transparent text-foreground"
                  placeholder="(809) 000-0000"
                />
              </div>
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
                <span>Guardar Cambios</span>
              </>
            )}
          </button>
        </div>
      </form>
    </div>
  )
}
