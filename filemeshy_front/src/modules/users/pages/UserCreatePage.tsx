import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { ArrowLeft, Save, UserPlus, Eye, EyeOff, Shield } from 'lucide-react'
import { Button } from '../../../ui/buttons'
import { Input } from '../../../ui/inputs'
import { useUserStore } from '../store/userStore'
import { rolesService } from '@/modules/access_control/services/roles.service'
import type { RoleSummary } from '@/modules/access_control/types/role.types'
import type { UserFormData } from '../types'

export default function UserCreatePage() {
  const navigate = useNavigate()
  const { createUser, isLoading } = useUserStore()
  const [showPassword, setShowPassword] = useState(false)
  const [showConfirmPassword, setShowConfirmPassword] = useState(false)
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
        
        // Set default role_id to first available role
        if (roles.length > 0) {
          setFormData(prev => ({ ...prev, role_id: roles[0].id }))
        }
      } catch (error) {
        console.error('Error loading roles:', error)
      } finally {
        setLoadingRoles(false)
      }
    }
    
    loadRoles()
  }, [])

  const handleChange = (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>) => {
    const { name, value } = e.target
    setFormData((prev) => ({
      ...prev,
      [name]: value,
    }))
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()

    // Validaciones
    if (formData.password !== formData.confirmarPassword) {
      alert('Las contraseñas no coinciden')
      return
    }

    if (!formData.password || formData.password.length < 8) {
      alert('La contraseña debe tener al menos 8 caracteres')
      return
    }

    // Crear usuario
    const newUser = await createUser({
      email: formData.email,
      first_name: formData.first_name,
      last_name: formData.last_name,
      phone: formData.phone,
      password: formData.password,
      is_active: formData.is_active,
      role_id: formData.role_id,
    })

    if (newUser) {
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
            <UserPlus className="text-white" size={24} />
          </div>
          <div>
            <h1 className="text-3xl font-bold text-foreground">Nuevo Usuario</h1>
            <p className="text-muted-foreground">Crea un nuevo usuario del sistema</p>
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
              <label className="block text-sm font-medium text-foreground/80 mb-2" htmlFor="user-create-1">
                Nombre *
              </label>
              <Input id="user-create-1"
                name="first_name"
                value={formData.first_name}
                onChange={handleChange}
                required
                placeholder="Ej: Juan"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-foreground/80 mb-2" htmlFor="user-create-2">
                Apellido *
              </label>
              <Input id="user-create-2"
                name="last_name"
                value={formData.last_name}
                onChange={handleChange}
                required
                placeholder="Ej: Pérez"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-foreground/80 mb-2" htmlFor="user-create-3">
                Email *
              </label>
              <Input id="user-create-3"
                type="email"
                name="email"
                value={formData.email}
                onChange={handleChange}
                required
                placeholder="usuario@dominio.com"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-foreground/80 mb-2" htmlFor="user-create-4">
                Teléfono
              </label>
              <Input id="user-create-4"
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
              <label className="block text-sm font-medium text-foreground/80 mb-2" htmlFor="user-create-5">
                Rol *
              </label>
              <select id="user-create-5"
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
              <label className="block text-sm font-medium text-foreground/80 mb-2" htmlFor="user-create-6">
                Estado *
              </label>
              <select id="user-create-6"
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

        {/* Credenciales de Acceso */}
        <div className="bg-muted rounded-xl shadow-xs border border-border p-6">
          <h2 className="text-lg font-semibold text-foreground mb-4">Credenciales de Acceso</h2>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-foreground/80 mb-2" htmlFor="user-create-7">
                Contraseña *
              </label>
              <div className="relative">
                <Input id="user-create-7"
                  type={showPassword ? 'text' : 'password'}
                  name="password"
                  value={formData.password}
                  onChange={handleChange}
                  required
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
              <label className="block text-sm font-medium text-foreground/80 mb-2" htmlFor="user-create-8">
                Confirmar Contraseña *
              </label>
              <div className="relative">
                <Input id="user-create-8"
                  type={showConfirmPassword ? 'text' : 'password'}
                  name="confirmarPassword"
                  value={formData.confirmarPassword}
                  onChange={handleChange}
                  required
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
            Guardar Usuario
          </Button>
        </div>
      </form>
    </div>
  )
}
