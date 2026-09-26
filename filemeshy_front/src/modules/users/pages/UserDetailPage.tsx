import { useState, useEffect, useCallback, useMemo } from 'react'
import { useNavigate, useParams, useSearchParams } from 'react-router-dom'
import {
  ArrowLeft, Edit, Trash2, Shield, Phone,
  FileText, Calendar, Clock, CheckCircle, XCircle,
  Monitor, Key, LogIn, LogOut, Loader2, Save,
  UserCircle, UserCheck, UserX, Camera,
} from 'lucide-react'
import { Button } from '@/ui/buttons/Button'
import { Badge } from '@/ui/badges/Badge'
import { ConfirmDialog } from '@/ui/modals/ConfirmDialog'
import { toast } from '@/ui/toast/CustomToast'
import { useUserStore } from '@/modules/users/store/userStore'
import { useAuth } from '@/modules/auth/hooks/useAuth'
import {
  userService,
  type User as BackendUser,
  type UserSession,
} from '@/modules/users/services/user.service'
import { rolesService } from '@/modules/access_control/services/roles.service'
import { userPermissionOverridesService } from '@/modules/access_control/services/user-permission-overrides.service'
import type { RoleSummary } from '@/modules/access_control/types/role.types'
import { useAvailablePermissions } from '@/modules/access_control/hooks/useAvailablePermissions'
import { formatDateLong, formatDateTime, isPast } from '@/shared/utils/dates'

// ─── Helpers ───────────────────────────────────────────────────────────────────

function SectionCard({ icon: Icon, title, children, action }: {
  icon: React.ElementType; title: string; children: React.ReactNode; action?: React.ReactNode
}) {
  return (
    <div className="bg-card border border-border rounded-2xl overflow-hidden">
      <div className="flex items-center justify-between gap-2 px-5 py-3 border-b border-border">
        <div className="flex items-center gap-2">
          <Icon className="w-4 h-4 text-brand-500" />
          <h3 className="text-sm font-semibold text-foreground">{title}</h3>
        </div>
        {action}
      </div>
      <div className="p-5">{children}</div>
    </div>
  )
}

function InfoRow({ label, value }: { label: string; value?: string | null }) {
  if (!value) return null
  return (
    <div>
      <p className="text-xs text-muted-foreground mb-0.5">{label}</p>
      <p className="text-sm text-foreground">{value}</p>
    </div>
  )
}

const ROLE_COLORS: Record<string, string> = {
  SUPER_ADMIN: 'bg-purple-100 text-purple-800 dark:bg-purple-900/30 dark:text-purple-300',
  ADMIN:       'bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-300',
  USER:        'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-300',
}

const ROLE_NAMES: Record<string, string> = {
  SUPER_ADMIN: 'Super Administrador',
  ADMIN:       'Administrador',
  USER:        'Usuario',
}

// ─── Page ──────────────────────────────────────────────────────────────────────

export default function UserDetailPage() {
  const navigate = useNavigate()
  const { id } = useParams()
  const [searchParams, setSearchParams] = useSearchParams()
  const activeTab = searchParams.get('tab') ?? 'info'
  const setActiveTab = useCallback(
    (tab: string) => setSearchParams({ tab }, { replace: true }),
    [setSearchParams]
  )

  const { fetchUser, deleteUser, updateUser } = useUserStore()
  const { user: authUser, logout } = useAuth()
  const { available: AVAILABLE_PERMISSIONS, resource_labels: RESOURCE_LABELS, action_labels: ACTION_LABELS } = useAvailablePermissions()

  const [usuario, setUsuario] = useState<BackendUser | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false)
  const [isToggling, setIsToggling] = useState(false)
  const [imgError, setImgError] = useState(false)
  const [uploadingAvatar, setUploadingAvatar] = useState(false)

  // Sesiones
  const [sessions, setSessions] = useState<UserSession[]>([])
  // Id del usuario cuyas sesiones ya se cargaron: `loading` se deriva (ver más abajo)
  const [sessionsFor, setSessionsFor] = useState<string | null>(null)

  // Rol inline
  const [availableRoles, setAvailableRoles] = useState<RoleSummary[]>([])
  const [editingRole, setEditingRole] = useState(false)
  const [selectedRoleId, setSelectedRoleId] = useState<string>('')
  const [savingRole, setSavingRole] = useState(false)

  // Permisos inline
  const [editingPerms, setEditingPerms] = useState(false)
  const [selectedPerms, setSelectedPerms] = useState<Set<string>>(new Set())
  const [savingPerms, setSavingPerms] = useState(false)
  // Excepciones individuales: base de permisos que da el rol actual (para poder
  // calcular, al guardar, cuáles de los cambios son "agregados" y cuáles "quitados"
  // respecto de esa base -- ver handleSavePerms)
  const [roleBaseCodes, setRoleBaseCodes] = useState<Set<string>>(new Set())
  const [permCodeToId, setPermCodeToId] = useState<Map<string, string>>(new Map())
  // Clave (`id:role`) de los overrides ya cargados: `overridesLoaded` se deriva de compararla
  const [overridesKey, setOverridesKey] = useState<string | null>(null)
  const canManagePerms = authUser?.role === 'SUPER_ADMIN'

  const TABS = useMemo(() => [
    { id: 'info', label: 'Información', icon: FileText },
    { id: 'rol', label: 'Rol y Permisos', icon: Shield },
    { id: 'sessions', label: 'Sesiones', icon: Monitor },
  ], [])

  useEffect(() => {
    const load = async () => {
      if (!id) return
      const user = await fetchUser(id)
      if (user) {
        setUsuario(user)
        setSelectedRoleId(user.role_id ?? '')
        setSelectedPerms(new Set(user.permissions))
      }
      setIsLoading(false)
    }
    load()
  }, [id, fetchUser])

  useEffect(() => {
    rolesService.getSummary(true).then(setAvailableRoles).catch(() => {})
  }, [])

  const usuarioId = usuario?.id
  const usuarioRole = usuario?.role
  const currentOverridesKey = usuarioId ? `${usuarioId}:${usuarioRole}` : null
  const overridesLoaded = currentOverridesKey !== null && overridesKey === currentOverridesKey

  useEffect(() => {
    if (!usuarioId || !canManagePerms || usuarioRole === 'SUPER_ADMIN') return
    let cancelled = false
    const key = `${usuarioId}:${usuarioRole}`
    userPermissionOverridesService.getForUser(usuarioId)
      .then(res => {
        if (cancelled) return
        const byId = new Map(res.catalog.map(p => [p.id, p.permission_code]))
        setRoleBaseCodes(new Set(res.role_permission_ids.map(id => byId.get(id)).filter((c): c is string => !!c)))
        setPermCodeToId(new Map(res.catalog.map(p => [p.permission_code, p.id])))
        setOverridesKey(key)
      })
      .catch(() => {})
    return () => { cancelled = true }
  }, [usuarioId, usuarioRole, canManagePerms])

  // Las sesiones se consideran "cargando" mientras no coincida el usuario cargado con el actual
  const loadingSessions = activeTab === 'sessions' && !!id && sessionsFor !== id

  useEffect(() => {
    if (activeTab !== 'sessions' || !id) return
    let cancelled = false
    userService.getUserSessions(id)
      .then(r => { if (!cancelled) setSessions(r.items) })
      .catch(() => {})
      .finally(() => { if (!cancelled) setSessionsFor(id) })
    return () => {
      cancelled = true
      // Al salir de la pestaña (o cambiar de usuario) se descarta lo cargado: al volver se ve el spinner
      setSessionsFor(null)
    }
  }, [activeTab, id])

  const handleToggleActive = async () => {
    if (!usuario) return
    setIsToggling(true)
    try {
      const updated = await updateUser(usuario.id, { is_active: !usuario.is_active })
      if (updated) {
        setUsuario(updated)
        toast.success(usuario.is_active ? 'Usuario desactivado' : 'Usuario activado')
      }
    } catch {
      toast.error('Error al cambiar el estado')
    } finally {
      setIsToggling(false)
    }
  }


  const handleDelete = async () => {
    if (!usuario) return
    const success = await deleteUser(usuario.id)
    if (success) navigate('/usuarios')
  }

  const handleSaveRole = async () => {
    if (!usuario) return
    const role = availableRoles.find(r => r.id === selectedRoleId)
    if (!role) return
    setSavingRole(true)
    try {
      const updated = await updateUser(usuario.id, {
        role_id: role.id,
        role: role.name,
      })
      if (updated) {
        setUsuario(updated)
        setEditingRole(false)
        // El rol cambió por debajo -- si "Editar permisos" seguía abierto, su
        // `selectedPerms` quedó calculado contra el rol viejo. Se cierra en vez de
        // dejarlo abierto con una base stale: guardar en ese estado generaría
        // excepciones individuales que no reflejan lo que el admin tildó.
        if (editingPerms) {
          setEditingPerms(false)
          toast.info('El rol cambió — revisá los permisos adicionales de nuevo antes de editarlos')
        }
        toast.success('Rol actualizado exitosamente')
      }
    } catch {
      toast.error('Error al actualizar el rol')
    } finally {
      setSavingRole(false)
    }
  }

  const handleSavePerms = async () => {
    if (!usuario) return
    if (!overridesLoaded) {
      // Guardar antes de que resuelva el fetch de la base del rol tomaría
      // roleBaseCodes vacío -- el diff marcaría TODOS los permisos actuales como
      // "agregados" a mano, incluidos los que el usuario ya tenía solo por su rol.
      toast.error('Todavía se están cargando los permisos del rol, esperá un segundo')
      return
    }
    setSavingPerms(true)
    try {
      // Se guarda como excepciones (agregado/quitado) respecto de la base del rol,
      // no como un reemplazo directo de la lista completa -- así una edición
      // posterior de los permisos del rol no borra esta excepción individual
      // (ver filemeshy_back/app/crud/user_permission_override.py).
      const grantIds: string[] = []
      const revokeIds: string[] = []
      for (const code of selectedPerms) {
        if (!roleBaseCodes.has(code)) {
          const permId = permCodeToId.get(code)
          if (permId) grantIds.push(permId)
        }
      }
      for (const code of roleBaseCodes) {
        if (!selectedPerms.has(code)) {
          const permId = permCodeToId.get(code)
          if (permId) revokeIds.push(permId)
        }
      }
      await userPermissionOverridesService.updateForUser(usuario.id, grantIds, revokeIds)
      const updated = await fetchUser(usuario.id)
      if (updated) setUsuario(updated)
      setEditingPerms(false)
      toast.success('Permisos actualizados exitosamente')
    } catch {
      toast.error('Error al actualizar los permisos')
    } finally {
      setSavingPerms(false)
    }
  }

  const handleAvatarUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file || !usuario) return
    setUploadingAvatar(true)
    try {
      const updated = await userService.uploadAvatar(usuario.id, file)
      setUsuario(updated)
      setImgError(false)
      toast.success('Foto actualizada')
    } catch {
      toast.error('Error al subir la foto')
    } finally {
      setUploadingAvatar(false)
      e.target.value = ''
    }
  }

  const togglePerm = (perm: string) => {
    setSelectedPerms(prev => {
      const next = new Set(prev)
      if (next.has(perm)) next.delete(perm)
      else next.add(perm)
      return next
    })
  }

  const handleRevokeSession = async (sessionId: string) => {
    if (!id) return
    try {
      await userService.revokeUserSession(id, sessionId)
      const isOwn = authUser?.id === id
      if (isOwn) { await logout(); navigate('/login', { replace: true }); return }
      const r = await userService.getUserSessions(id)
      setSessions(r.items)
    } catch {
      toast.error('Error al cerrar la sesión')
    }
  }

  const handleRevokeAllSessions = async () => {
    if (!id) return
    try {
      await userService.revokeAllUserSessions(id)
      const isOwn = authUser?.id === id
      if (isOwn) { await logout(); navigate('/login', { replace: true }); return }
      const r = await userService.getUserSessions(id)
      setSessions(r.items)
    } catch {
      toast.error('Error al cerrar las sesiones')
    }
  }

  if (isLoading) {
    return (
      <div className="flex items-center justify-center min-h-[400px]">
        <div className="text-center">
          <div className="w-12 h-12 border-4 border-brand-500 border-t-transparent rounded-full animate-spin mx-auto mb-3" />
          <p className="text-muted-foreground text-sm">Cargando usuario...</p>
        </div>
      </div>
    )
  }

  if (!usuario) return null

  const roleName = ROLE_NAMES[usuario.role] ?? usuario.role
  const roleColor = ROLE_COLORS[usuario.role] ?? ROLE_COLORS.USER
  const activeSessions = sessions.filter(s => s.is_active && !isPast(s.expires_at)).length

  return (
    <div className="pb-16">
      <div className="space-y-5">

        {/* ── Breadcrumb + acciones ── */}
        <div className="flex items-center justify-between gap-4">
          <Button variant="ghost" size="sm" leftIcon={<ArrowLeft className="size-4" />} onClick={() => navigate('/usuarios')}>
            Volver
          </Button>
          <div className="flex items-center gap-2">
            <Button
              variant="secondary"
              onClick={handleToggleActive}
              disabled={isToggling}
              leftIcon={usuario.is_active
                ? <UserX className="w-4 h-4" />
                : <UserCheck className="w-4 h-4" />}
            >
              {usuario.is_active ? 'Desactivar' : 'Activar'}
            </Button>
            <Button
              variant="secondary"
              onClick={() => navigate(`/usuarios/${usuario.id}/editar`)}
              leftIcon={<Edit className="w-4 h-4" />}
            >
              Editar
            </Button>
            <Button
              variant="danger"
              onClick={() => setDeleteDialogOpen(true)}
              leftIcon={<Trash2 className="w-4 h-4" />}
            >
              Eliminar
            </Button>
          </div>
        </div>

        {/* ── Layout principal: dos columnas ── */}
        <div className="flex flex-col lg:flex-row gap-5 lg:items-start">

          {/* ── Columna izquierda (sticky) ── */}
          <div className="lg:w-96 shrink-0 lg:sticky lg:top-6 space-y-4">
            <div className="bg-card border border-border rounded-2xl overflow-hidden">

              {/* Foto de perfil — clickeable para cambiar */}
              <label className="relative block aspect-square bg-muted cursor-pointer group overflow-hidden">
                <input
                  type="file"
                  accept="image/*"
                  className="hidden"
                  onChange={handleAvatarUpload}
                  disabled={uploadingAvatar}
                />
                {usuario.avatar && !imgError ? (
                  <img
                    src={usuario.avatar}
                    alt={`${usuario.first_name} ${usuario.last_name}`}
                    className="w-full h-full object-cover"
                    onError={() => setImgError(true)}
                  />
                ) : (
                  <div className="w-full h-full bg-linear-to-br from-brand-400 to-brand-600 flex items-center justify-center">
                    <span className="text-7xl font-bold text-white select-none">
                      {usuario.first_name.charAt(0).toUpperCase()}
                    </span>
                  </div>
                )}
                {/* Overlay cámara */}
                <div className="absolute inset-0 bg-black/40 flex flex-col items-center justify-center gap-2 opacity-0 group-hover:opacity-100 transition-opacity">
                  {uploadingAvatar
                    ? <Loader2 className="w-8 h-8 text-white animate-spin" />
                    : <Camera className="w-8 h-8 text-white" />}
                  <span className="text-white text-xs font-medium">Cambiar foto</span>
                </div>
              </label>

              {/* Info principal */}
              <div className="p-5 space-y-4">
                {/* Badges + nombre + email */}
                <div>
                  <div className="flex flex-wrap gap-1.5 mb-2">
                    <Badge variant={usuario.is_active ? 'success' : 'danger'}>
                      {usuario.is_active ? 'Activo' : 'Inactivo'}
                    </Badge>
                    <span className={`inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-medium ${roleColor}`}>
                      <Shield className="w-3 h-3" />
                      {roleName}
                    </span>
                  </div>
                  <h1 className="text-lg font-bold text-foreground leading-snug">
                    {usuario.first_name} {usuario.last_name}
                  </h1>
                  <p className="text-xs text-muted-foreground mt-1">{usuario.email}</p>
                </div>

                {/* Stats 2x2 */}
                <div className="grid grid-cols-2 gap-2">
                  <div className="bg-muted rounded-xl p-3">
                    <p className="text-[10px] text-muted-foreground uppercase tracking-wide mb-0.5">Miembro desde</p>
                    <p className="text-xs font-semibold text-foreground">{formatDateLong(usuario.created_at) ?? '—'}</p>
                  </div>
                  <div className="bg-muted rounded-xl p-3">
                    <p className="text-[10px] text-muted-foreground uppercase tracking-wide mb-0.5">Último acceso</p>
                    <p className="text-xs font-semibold text-foreground">
                      {usuario.last_login ? formatDateTime(usuario.last_login) ?? '—' : 'Nunca'}
                    </p>
                  </div>
                  <div className="bg-muted rounded-xl p-3">
                    <p className="text-[10px] text-muted-foreground uppercase tracking-wide mb-0.5">Permisos</p>
                    <p className="text-xs font-semibold text-foreground">{usuario.permissions.length} activos</p>
                  </div>
                  <div className="bg-muted rounded-xl p-3">
                    <p className="text-[10px] text-muted-foreground uppercase tracking-wide mb-0.5">Teléfono</p>
                    <p className="text-xs font-semibold text-foreground">{usuario.phone || '—'}</p>
                  </div>
                </div>
              </div>
            </div>
          </div>

          {/* ── Columna derecha (tabs) ── */}
          <div className="flex-1 min-w-0 bg-card border border-border rounded-2xl overflow-hidden">

            {/* Tab bar */}
            <div className="flex items-center gap-0 border-b border-border overflow-x-auto overflow-y-hidden scrollbar-hide px-2">
              {TABS.map(tab => {
                const Icon = tab.icon
                const active = activeTab === tab.id
                return (
                  <button
                    key={tab.id}
                    onClick={() => setActiveTab(tab.id)}
                    className={`flex items-center gap-1.5 px-3 py-3.5 text-sm font-medium whitespace-nowrap border-b-2 transition-colors -mb-px ${
                      active
                        ? 'border-brand-500 text-primary'
                        : 'border-transparent text-muted-foreground hover:text-foreground'
                    }`}
                  >
                    <Icon className="w-3.5 h-3.5" />
                    {tab.label}
                  </button>
                )
              })}
            </div>

            {/* Contenido del tab */}
            <div className="p-5 space-y-4">

            {/* ── Tab: Información ── */}
            {activeTab === 'info' && (
              <div className="space-y-4">
                <SectionCard icon={UserCircle} title="Información Personal">
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                    <InfoRow label="Nombre" value={usuario.first_name} />
                    <InfoRow label="Apellido" value={usuario.last_name} />
                    <InfoRow label="Email" value={usuario.email} />
                    <InfoRow label="Teléfono" value={usuario.phone || '—'} />
                    <InfoRow label="Estado" value={usuario.is_active ? 'Activo' : 'Inactivo'} />
                    <InfoRow label="Tema" value={usuario.theme ?? 'Auto'} />
                  </div>
                </SectionCard>

                <SectionCard icon={Calendar} title="Fechas">
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                    <InfoRow label="Fecha de creación" value={formatDateTime(usuario.created_at) ?? '—'} />
                    <InfoRow label="Última actualización" value={usuario.updated_at ? formatDateTime(usuario.updated_at) ?? '—' : '—'} />
                    <InfoRow label="Último inicio de sesión" value={usuario.last_login ? formatDateTime(usuario.last_login) ?? '—' : 'Nunca'} />
                  </div>
                </SectionCard>
              </div>
            )}

            {/* ── Tab: Rol y Permisos ── */}
            {activeTab === 'rol' && (
              <div className="space-y-4">
                <SectionCard
                  icon={Shield}
                  title="Rol Asignado"
                  action={
                    !editingRole ? (
                      <button
                        onClick={() => { setEditingRole(true); setSelectedRoleId(usuario.role_id ?? '') }}
                        className="flex items-center gap-1 text-xs text-brand-500 hover:text-brand-600 font-medium transition-colors"
                      >
                        <Edit className="w-3 h-3" />
                        Cambiar rol
                      </button>
                    ) : (
                      <div className="flex items-center gap-2">
                        <button
                          onClick={() => setEditingRole(false)}
                          className="text-xs text-muted-foreground hover:text-foreground transition-colors"
                        >
                          Cancelar
                        </button>
                        <Button
                          variant="primary"
                          size="sm"
                          onClick={handleSaveRole}
                          disabled={savingRole}
                          leftIcon={savingRole ? <Loader2 className="w-3 h-3 animate-spin" /> : <Save className="w-3 h-3" />}
                        >
                          Guardar
                        </Button>
                      </div>
                    )
                  }
                >
                  {!editingRole ? (
                    <div className="flex items-center gap-4">
                      <div className={`w-12 h-12 rounded-xl flex items-center justify-center ${roleColor}`}>
                        <Shield className="w-6 h-6" />
                      </div>
                      <div>
                        <p className="font-semibold text-foreground">{roleName}</p>
                        <p className="text-xs text-muted-foreground mt-0.5">
                          {availableRoles.find(r => r.id === usuario.role_id)?.description ?? ''}
                        </p>
                      </div>
                    </div>
                  ) : (
                    <div className="space-y-3">
                      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                        {availableRoles.map(role => {
                          const isSelected = selectedRoleId === role.id
                          return (
                            <button
                              key={role.id}
                              onClick={() => setSelectedRoleId(role.id)}
                              className={`flex items-start gap-3 p-3 rounded-xl border-2 text-left transition-all ${
                                isSelected
                                  ? 'border-brand-500 bg-brand-50 dark:bg-brand-900/20'
                                  : 'border-border bg-muted hover:border-brand-300'
                              }`}
                            >
                              <div className={`w-8 h-8 rounded-lg flex items-center justify-center shrink-0 ${ROLE_COLORS[role.name] ?? ROLE_COLORS.USER}`}>
                                <Shield className="w-4 h-4" />
                              </div>
                              <div className="min-w-0">
                                <p className={`text-sm font-semibold truncate ${isSelected ? 'text-brand-700 dark:text-brand-300' : 'text-foreground'}`}>
                                  {role.display_name}
                                </p>
                                {role.description && (
                                  <p className="text-xs text-muted-foreground mt-0.5 line-clamp-2">{role.description}</p>
                                )}
                              </div>
                              {isSelected && <CheckCircle className="w-4 h-4 text-brand-500 shrink-0 mt-0.5 ml-auto" />}
                            </button>
                          )
                        })}
                      </div>
                    </div>
                  )}
                </SectionCard>

                <SectionCard
                  icon={Key}
                  title={`Permisos (${usuario.permissions.length})`}
                  action={
                    usuario.role !== 'SUPER_ADMIN' && canManagePerms && (
                      !editingPerms ? (
                        <button
                          onClick={() => { setEditingPerms(true); setSelectedPerms(new Set(usuario.permissions)) }}
                          disabled={!overridesLoaded}
                          className="flex items-center gap-1 text-xs text-brand-500 hover:text-brand-600 font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                        >
                          {overridesLoaded ? <Edit className="w-3 h-3" /> : <Loader2 className="w-3 h-3 animate-spin" />}
                          Editar permisos
                        </button>
                      ) : (
                        <div className="flex items-center gap-2">
                          <button
                            onClick={() => setEditingPerms(false)}
                            className="text-xs text-muted-foreground hover:text-foreground transition-colors"
                          >
                            Cancelar
                          </button>
                          <Button
                            variant="primary"
                            size="sm"
                            onClick={handleSavePerms}
                            disabled={savingPerms || !overridesLoaded}
                            leftIcon={savingPerms ? <Loader2 className="w-3 h-3 animate-spin" /> : <Save className="w-3 h-3" />}
                          >
                            Guardar
                          </Button>
                        </div>
                      )
                    )
                  }
                >
                  {editingPerms && (
                    <p className="text-xs text-muted-foreground mb-3 -mt-1">
                      Los que vienen del rol <strong>{roleName}</strong> aparecen tildados. Destildar uno de esos lo
                      quita solo para este usuario; tildar uno que el rol no da lo agrega solo para este usuario
                      (los cambios de este rol no afectan a nadie más).
                    </p>
                  )}
                  {usuario.role === 'SUPER_ADMIN' ? (
                    <div className="flex items-start gap-3 p-3 bg-purple-50 dark:bg-purple-900/20 rounded-xl border border-purple-200 dark:border-purple-800">
                      <Shield className="w-5 h-5 text-purple-600 dark:text-purple-400 mt-0.5 shrink-0" />
                      <div>
                        <p className="font-medium text-purple-900 dark:text-purple-300 text-sm">Super Administrador</p>
                        <p className="text-xs text-purple-700 dark:text-purple-400 mt-0.5">
                          Acceso completo a todo el sistema sin restricciones.
                        </p>
                      </div>
                    </div>
                  ) : (
                    <div className="space-y-4">
                      {Object.entries(AVAILABLE_PERMISSIONS).map(([resource, actions]) => {
                        const allChecked = actions.every(a => (editingPerms ? selectedPerms : new Set(usuario.permissions)).has(`${resource}.${a}`))
                        const someChecked = actions.some(a => (editingPerms ? selectedPerms : new Set(usuario.permissions)).has(`${resource}.${a}`))
                        return (
                          <div key={resource} className="bg-muted rounded-xl p-3">
                            <div className="flex items-center justify-between mb-2.5">
                              <div className="flex items-center gap-2">
                                {editingPerms && (
                                  <input
                                    type="checkbox"
                                    checked={allChecked}
                                    ref={el => { if (el) el.indeterminate = someChecked && !allChecked }}
                                    onChange={() => {
                                      setSelectedPerms(prev => {
                                        const next = new Set(prev)
                                        if (allChecked) actions.forEach(a => next.delete(`${resource}.${a}`))
                                        else actions.forEach(a => next.add(`${resource}.${a}`))
                                        return next
                                      })
                                    }}
                                    className="w-4 h-4 accent-brand-500 rounded-sm"
                                  />
                                )}
                                <p className="text-xs font-bold text-foreground uppercase tracking-wide">
                                  {RESOURCE_LABELS[resource] ?? resource}
                                </p>
                              </div>
                              {!editingPerms && someChecked && (
                                <span className="text-xs text-muted-foreground">
                                  {actions.filter(a => usuario.permissions.includes(`${resource}.${a}`)).length}/{actions.length}
                                </span>
                              )}
                            </div>
                            <div className="flex flex-wrap gap-2">
                              {actions.map(action => {
                                const key = `${resource}.${action}`
                                const active = (editingPerms ? selectedPerms : new Set(usuario.permissions)).has(key)
                                const fromRole = roleBaseCodes.has(key)
                                return editingPerms ? (
                                  <label key={action} className={`flex items-center gap-1.5 px-2.5 py-1 rounded-lg border cursor-pointer text-xs font-medium transition-all select-none ${
                                    active
                                      ? 'bg-brand-50 dark:bg-brand-900/20 border-brand-300 dark:border-brand-700 text-brand-700 dark:text-brand-300'
                                      : 'bg-card border-border text-muted-foreground hover:border-brand-300'
                                  }`}>
                                    <input
                                      type="checkbox"
                                      checked={active}
                                      onChange={() => togglePerm(key)}
                                      className="w-3 h-3 accent-brand-500"
                                    />
                                    {ACTION_LABELS[action] ?? action}
                                    {active && !fromRole && (
                                      <span title={`Agregado para este usuario -- el rol ${roleName} no lo da`} className="text-brand-500 font-bold">+</span>
                                    )}
                                    {!active && fromRole && (
                                      <span title={`Quitado para este usuario -- el rol ${roleName} sí lo da`} className="text-red-500 font-bold">−</span>
                                    )}
                                  </label>
                                ) : (
                                  <span key={action} className={`px-2.5 py-1 rounded-lg text-xs font-medium ${
                                    active
                                      ? 'bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800 text-green-700 dark:text-green-300'
                                      : 'bg-card border border-border text-muted-foreground opacity-50'
                                  }`}>
                                    {ACTION_LABELS[action] ?? action}
                                  </span>
                                )
                              })}
                            </div>
                          </div>
                        )
                      })}
                    </div>
                  )}
                </SectionCard>
              </div>
            )}

            {/* ── Tab: Sesiones ── */}
            {activeTab === 'sessions' && (
              <SectionCard
                icon={Monitor}
                title={`Sesiones Activas (${activeSessions})`}
                action={
                  activeSessions > 0 ? (
                    <Button
                      variant="danger"
                      size="sm"
                      leftIcon={<LogOut className="w-3.5 h-3.5" />}
                      onClick={handleRevokeAllSessions}
                    >
                      Cerrar todas
                    </Button>
                  ) : undefined
                }
              >
                {loadingSessions ? (
                  <div className="flex items-center justify-center py-10">
                    <Loader2 className="w-8 h-8 animate-spin text-brand-500" />
                  </div>
                ) : sessions.length === 0 ? (
                  <div className="text-center py-10">
                    <Monitor className="w-10 h-10 mx-auto text-muted-foreground/30 mb-2" />
                    <p className="text-sm text-muted-foreground">No hay sesiones para este usuario</p>
                  </div>
                ) : (
                  <div className="space-y-3">
                    {sessions.map(session => {
                      const isExpired = isPast(session.expires_at)
                      const isActive = session.is_active && !isExpired
                      const ua = session.user_agent || ''
                      const isMobile = /Mobile|Android|iPhone/i.test(ua)
                      const browser = ua.match(/Chrome|Safari|Firefox|Edge/)?.[0] ?? 'Navegador'
                      const os = ua.match(/Windows|Mac|Linux|Android|iOS/)?.[0] ?? 'Sistema'
                      // Preferir el nombre de dispositivo que arma el backend; parseo local como respaldo
                      const deviceLabel = session.device_name || `${browser} en ${os}`

                      return (
                        <div
                          key={session.id}
                          className={`p-4 rounded-xl border ${
                            isActive
                              ? 'bg-green-50 dark:bg-green-900/20 border-green-200 dark:border-green-800'
                              : 'bg-muted border-border'
                          }`}
                        >
                          <div className="flex items-start justify-between gap-3">
                            <div className="flex items-start gap-3 flex-1 min-w-0">
                              <div className={`w-9 h-9 rounded-lg flex items-center justify-center shrink-0 ${
                                isActive ? 'bg-green-100 dark:bg-green-900/40' : 'bg-muted'
                              }`}>
                                {isMobile
                                  ? <Phone className={`w-4 h-4 ${isActive ? 'text-green-600 dark:text-green-400' : 'text-muted-foreground'}`} />
                                  : <Monitor className={`w-4 h-4 ${isActive ? 'text-green-600 dark:text-green-400' : 'text-muted-foreground'}`} />
                                }
                              </div>
                              <div className="flex-1 min-w-0">
                                <div className="flex items-center gap-2 mb-1 flex-wrap">
                                  <p className="text-sm font-medium text-foreground">{deviceLabel}</p>
                                  {isActive
                                    ? <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded-full text-xs font-medium bg-green-100 text-green-800 dark:bg-green-900/40 dark:text-green-300">
                                        <CheckCircle className="w-3 h-3" /> Activa
                                      </span>
                                    : <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded-full text-xs font-medium bg-muted text-muted-foreground">
                                        <XCircle className="w-3 h-3" /> Cerrada
                                      </span>
                                  }
                                </div>
                                {session.ip_address && (
                                  <p className="text-xs text-muted-foreground mb-1">IP: {session.ip_address}</p>
                                )}
                                <div className="flex flex-wrap gap-x-3 gap-y-0.5 text-xs text-muted-foreground">
                                  <span className="flex items-center gap-1">
                                    <LogIn className="w-3 h-3" />
                                    {formatDateTime(session.created_at) ?? ''}
                                  </span>
                                  <span className="flex items-center gap-1">
                                    <Clock className="w-3 h-3" />
                                    {formatDateTime(session.last_activity) ?? ''}
                                  </span>
                                </div>
                              </div>
                            </div>
                            {isActive && (
                              <Button
                                variant="ghost"
                                size="sm"
                                leftIcon={<LogOut className="w-3.5 h-3.5" />}
                                onClick={() => handleRevokeSession(session.id)}
                              >
                                Cerrar
                              </Button>
                            )}
                          </div>
                        </div>
                      )
                    })}
                  </div>
                )}
              </SectionCard>
            )}

            </div>{/* fin p-5 */}
          </div>
        </div>
      </div>

      <ConfirmDialog
        isOpen={deleteDialogOpen}
        onClose={() => setDeleteDialogOpen(false)}
        onConfirm={handleDelete}
        title="Eliminar Usuario"
        message={`¿Estás seguro de eliminar a ${usuario.first_name} ${usuario.last_name}? Esta acción no se puede deshacer.`}
        confirmText="Eliminar"
        variant="danger"
      />
    </div>
  )
}
