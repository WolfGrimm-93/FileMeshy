import { useState, useEffect } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { ArrowLeft, Save, Shield, Eye, EyeOff } from 'lucide-react'
import { Button } from '../../../ui/buttons'
import { Input } from '../../../ui/inputs'
import { useUserStore } from '../store/userStore'
import { rolesService } from '@/modules/access_control/services/roles.service'
import type { RoleSummary } from '@/modules/access_control/types/role.types'
import type { UserFormData } from '../types'

export default function UserEditPage() {
  const navigate = useNavigate()
  const { id } = useParams()
  const { fetchUser, updateUser, isLoading } = useUserStore()
  const [showPassword, setShowPassword] = useState(false)
  const [showConfirmPassword, setShowConfirmPassword] = useState(false)
  const [cambiarPassword, setCambiarPassword] = useState(false)
  const [availableRoles, setAvailableRoles] = useState<RoleSummary[]>([])
  const [loadingRoles, setLoadingRoles] = useState(true)

  const [formData, setFormData] = useState<UserFormData>({
    first_name: '',
    last_name: '',
    email: '',
    phone: '',
    role: '',
    role_id: '',
    is_active: true,
    password: '',
    confirmarPassword: '',
  })

  // Load available roles on mount
  useEffect(() => {
    const loadRoles = async () => {
      try {
        setLoadingRoles(true)
        const roles = await rolesService.getSummary(true) // Only active roles
        setAvailableRoles(roles)
      } catch (error) {
        console.error('Error loading roles:', error)
      } finally {
        setLoadingRoles(false)
      }
    }
    
    loadRoles()
  }, [])

  // Cargar datos del usuario
  useEffect(() => {
    const loadUser = async () => {
      if (id) {
        const user = await fetchUser(id)
        if (user) {
          setFormData({
            first_name: user.first_name,
            last_name: user.last_name,
            email: user.email,
            phone: user.phone || '',
            role: user.role,
            role_id: user.role_id || '',
            is_active: user.is_active,
            password: '',
            confirmarPassword: ''
          })
        }
      }
    }
    loadUser()
  }, [id, fetchUser])

  const handleChange = (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>) => {
    const { name, value } = e.target
    if (name === 'role_id') {
      const role = availableRoles.find(r => r.id === value)
      setFormData(prev => ({ ...prev, role_id: value, role: role?.name ?? prev.role }))
      return
    }
    setFormData(prev => ({ ...prev, [name]: value }))
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()

    // Validaciones solo si está cambiando la contraseña
    if (cambiarPassword) {
      if (formData.password !== formData.confirmarPassword) {
        alert('Las contraseñas no coinciden')
        return
      }

      if (!formData.password || formData.password.length < 8) {
        alert('La contraseña debe tener al menos 8 caracteres')
        return
      }
    }

    // Preparar datos de actualización
    const updateData: any = {
      email: formData.email,
      first_name: formData.first_name,
      last_name: formData.last_name,
      phone: formData.phone,
      is_active: formData.is_active,
      role: formData.role,
      role_id: formData.role_id,
    }

    // Agregar contraseña solo si se está cambiando
    if (cambiarPassword && formData.password) {
      updateData.password = formData.password
    }

    // Actualizar usuario
    const updated = await updateUser(id!, updateData)

    if (updated) {
      navigate('/usuarios')
    }
  }

  return (
    <div className="w-full">
      {/* Header */}
      <div className="mb-6">
        <div className="flex items-center gap-3">
          <Button variant="ghost" size="sm" leftIcon={<ArrowLeft className="size-4" />} onClick={() => navigate('/usuarios')}>
            Volver
          </Button>
          <div className="w-px h-8 bg-border" />
          <div className="w-12 h-12 bg-linear-to-br from-brand-400 to-brand-600 rounded-xl flex items-center justify-center">
            <Shield className="text-white" size={24} />
          </div>
          <div>
            <h1 className="text-3xl font-bold text-foreground">Editar Usuario</h1>
            <p className="text-muted-foreground">Modifica la información del usuario</p>
          </div>
        </div>
      </div>

      {/* Formulario */}
      <form onSubmit={handleSubmit} className="space-y-6">
        {/* Información Personal */}
        <div className="bg-muted rounded-xl shadow-xs border border-border p-6">
          <h2 className="text-lg font-semibold text-foreground mb-4 flex items-center gap-2">
            <Shield size={20} className="text-brand-600" />
            Información Personal
          </h2>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-foreground/80 mb-2">
                Nombre *
              </label>
              <Input
                name="first_name"
                value={formData.first_name}
                onChange={handleChange}
                required
                placeholder="Ej: Juan"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-foreground/80 mb-2">
                Apellido *
              </label>
              <Input
                name="last_name"
                value={formData.last_name}
                onChange={handleChange}
                required
                placeholder="Ej: Pérez"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-foreground/80 mb-2">
                Email *
              </label>
              <Input
                type="email"
                name="email"
                value={formData.email}
                onChange={handleChange}
                required
                placeholder="usuario@dominio.com"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-foreground/80 mb-2">
                Teléfono
              </label>
              <Input
                name="phone"
                value={formData.phone}
                onChange={handleChange}
                placeholder="809-555-0101"
              />
            </div>
          </div>
        </div>

        {/* Rol y Permisos */}
        <div className="bg-muted rounded-xl shadow-xs border border-border p-6">
          <h2 className="text-lg font-semibold text-foreground mb-4">Rol y Permisos</h2>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-foreground/80 mb-2">
                Rol *
              </label>
              <select
                name="role_id"
                value={formData.role_id}
                onChange={handleChange}
                required
                disabled={loadingRoles}
                className="w-full px-4 py-2.5 border border-input rounded-lg bg-muted text-foreground focus:ring-2 focus:ring-brand-500 focus:border-transparent disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {loadingRoles ? (
                  <option value="">Cargando roles...</option>
                ) : availableRoles.length === 0 ? (
                  <option value="">No hay roles disponibles</option>
                ) : (
                  availableRoles.map(role => (
                    <option key={role.id} value={role.id}>
                      {role.display_name}
                    </option>
                  ))
                )}
              </select>
              {!loadingRoles && availableRoles.length > 0 && (
                <p className="text-xs text-muted-foreground mt-1">
                  {availableRoles.find(r => r.id === formData.role_id)?.description || 'Selecciona un rol para el usuario'}
                </p>
              )}
            </div>

            <div>
              <label className="block text-sm font-medium text-foreground/80 mb-2">
                Estado *
              </label>
              <select
                name="is_active"
                value={formData.is_active ? 'true' : 'false'}
                onChange={(e) => setFormData({ ...formData, is_active: e.target.value === 'true' })}
                required
                className="w-full px-4 py-2.5 border border-input rounded-lg bg-muted text-foreground focus:ring-2 focus:ring-brand-500 focus:border-transparent"
              >
                <option value="true">Activo</option>
                <option value="false">Inactivo</option>
              </select>
            </div>
          </div>
        </div>

        {/* Cambiar Contraseña */}
        <div className="bg-muted rounded-xl shadow-xs border border-border p-6">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-semibold text-foreground">Cambiar Contraseña</h2>
            <label className="flex items-center gap-2 cursor-pointer">
              <input
                type="checkbox"
                checked={cambiarPassword}
                onChange={(e) => setCambiarPassword(e.target.checked)}
                className="w-4 h-4 text-brand-600 border-gray-300 rounded-sm focus:ring-2 focus:ring-brand-500"
              />
              <span className="text-sm text-foreground/80">Modificar contraseña</span>
            </label>
          </div>

          {cambiarPassword && (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-foreground/80 mb-2">
                  Nueva Contraseña *
                </label>
                <div className="relative">
                  <Input
                    type={showPassword ? 'text' : 'password'}
                    name="password"
                    value={formData.password}
                    onChange={handleChange}
                    required={cambiarPassword}
                    placeholder="Mínimo 8 caracteres"
                  />
                  <button
                    type="button"
                    onClick={() => setShowPassword(!showPassword)}
                    className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-foreground"
                  >
                    {showPassword ? <EyeOff size={18} /> : <Eye size={18} />}
                  </button>
                </div>
                <p className="text-xs text-muted-foreground mt-1">
                  Debe incluir mayúsculas, minúsculas y números
                </p>
              </div>

              <div>
                <label className="block text-sm font-medium text-foreground/80 mb-2">
                  Confirmar Contraseña *
                </label>
                <div className="relative">
                  <Input
                    type={showConfirmPassword ? 'text' : 'password'}
                    name="confirmarPassword"
                    value={formData.confirmarPassword}
                    onChange={handleChange}
                    required={cambiarPassword}
                    placeholder="Repite la contraseña"
                  />
                  <button
                    type="button"
                    onClick={() => setShowConfirmPassword(!showConfirmPassword)}
                    className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-foreground"
                  >
                    {showConfirmPassword ? <EyeOff size={18} /> : <Eye size={18} />}
                  </button>
                </div>
              </div>
            </div>
          )}

          {!cambiarPassword && (
            <p className="text-sm text-muted-foreground">
              Deja la contraseña sin cambios si no deseas modificarla
            </p>
          )}
        </div>

        {/* Botones */}
        <div className="flex items-center justify-end gap-3">
          <Button
            type="button"
            variant="secondary"
            onClick={() => navigate('/usuarios')}
            disabled={isLoading}
          >
            Cancelar
          </Button>
          <Button type="submit" variant="primary" leftIcon={<Save size={18} />} isLoading={isLoading}>
            Guardar Cambios
          </Button>
        </div>
      </form>
    </div>
  )
}
