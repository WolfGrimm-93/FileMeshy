/**
 * PÁGINA: GESTIÓN DE PERMISOS
 *
 * Asigna permisos del catálogo (tabla `permissions`) a cada rol (tabla nueva
 * role_permissions). Reemplaza al viejo editor de Role.permissions (JSONB) que
 * no tenía ningún efecto real -- acá el cambio se aplica de inmediato a todos
 * los usuarios de ese rol (ver PUT /roles/{id}/permissions en el backend).
 *
 * Reusa RolePermissionsEditor (el checklist por recurso/acción ya existía,
 * conectado al lugar equivocado) en vez de construir un checklist nuevo.
 */
import { useState, useEffect, useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import { ArrowLeft, ShieldCheck, Save, Loader2 } from 'lucide-react'
import { toast } from 'sonner'
import { Button } from '@/ui/buttons/Button'
import { Badge } from '@/ui/badges/Badge'
import { EmptyState } from '@/ui/empty-states/EmptyState'
import RolePermissionsEditor from '../components/RolePermissionsEditor'
import { rolesService } from '../services/roles.service'
import {
  permissionsAssignmentService,
  idsToPermissionsDict,
  permissionsDictToIds,
  type PermissionCatalogItem,
} from '../services/permissions-assignment.service'
import type { RoleResponse, RolePermissions } from '../types/role.types'
import { useAuth } from '@/modules/auth/hooks/useAuth'

export default function PermissionsManagementPage() {
  const navigate = useNavigate()
  const { user: authUser } = useAuth()
  const canManage = authUser?.role === 'SUPER_ADMIN'

  const [roles, setRoles] = useState<RoleResponse[]>([])
  const [selectedRoleId, setSelectedRoleId] = useState<string | null>(null)
  const [catalog, setCatalog] = useState<PermissionCatalogItem[]>([])
  const [assignedDict, setAssignedDict] = useState<RolePermissions>({})
  const [isLoadingRoles, setIsLoadingRoles] = useState(true)
  // Rol cuyos permisos ya terminaron de cargarse (con éxito o error): `loading` se
  // deriva de compararlo con el rol seleccionado, sin setState síncrono en el efecto
  const [attempt, setAttempt] = useState(0)
  const [loadState, setLoadState] = useState<{ roleId: string; ok: boolean } | null>(null)
  const isLoadingPermissions = selectedRoleId !== null && loadState?.roleId !== selectedRoleId
  // La carga del rol seleccionado falló: no se muestran permisos ajenos ni se permite guardar
  const loadFailed = selectedRoleId !== null && loadState?.roleId === selectedRoleId && !loadState.ok
  const [isSaving, setIsSaving] = useState(false)

  useEffect(() => {
    rolesService
      .list({ skip: 0, limit: 100, include_system: true })
      .then((res) => {
        setRoles(res.items)
        if (res.items.length > 0) setSelectedRoleId(res.items[0].id)
      })
      .catch(() => toast.error('No se pudieron cargar los roles'))
      .finally(() => setIsLoadingRoles(false))
  }, [])

  useEffect(() => {
    if (!selectedRoleId) return
    let cancelled = false
    permissionsAssignmentService
      .getForRole(selectedRoleId)
      .then((res) => {
        if (cancelled) return
        setCatalog(res.catalog)
        setAssignedDict(idsToPermissionsDict(res.assigned_permission_ids, res.catalog))
        setLoadState({ roleId: selectedRoleId, ok: true })
      })
      .catch(() => {
        if (cancelled) return
        // Limpiar lo del rol anterior para no mostrarlo ni guardarlo bajo este rol
        setCatalog([])
        setAssignedDict({})
        setLoadState({ roleId: selectedRoleId, ok: false })
        toast.error('No se pudieron cargar los permisos de este rol')
      })
    return () => {
      cancelled = true
      // Al cambiar de rol se invalida lo cargado: volver a un rol previo recarga con spinner
      setLoadState(null)
    }
  }, [selectedRoleId, attempt])

  const selectedRole = useMemo(() => roles.find((r) => r.id === selectedRoleId), [roles, selectedRoleId])

  const handleSave = async () => {
    if (!selectedRoleId) return
    setIsSaving(true)
    try {
      const ids = permissionsDictToIds(assignedDict, catalog)
      await permissionsAssignmentService.updateForRole(selectedRoleId, ids)
      toast.success(`Permisos de "${selectedRole?.display_name}" actualizados`)
    } catch {
      toast.error('No se pudieron guardar los permisos')
    } finally {
      setIsSaving(false)
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3 mb-2">
        <Button variant="ghost" size="sm" leftIcon={<ArrowLeft className="size-4" />} onClick={() => navigate('/usuarios')}>
          Volver
        </Button>
        <div className="w-px h-8 bg-border" />
        <div>
          <h1 className="text-3xl font-bold text-foreground">Gestión de Permisos</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Asigná permisos del catálogo a cada rol. El cambio aplica de inmediato a todos los usuarios de ese rol.
          </p>
        </div>
      </div>

      {!canManage && (
        <div className="p-4 rounded-lg border border-border bg-muted text-sm text-muted-foreground">
          Podés ver los permisos asignados, pero solo Super Administrador puede modificarlos.
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-4 gap-6">
        {/* Selector de rol */}
        <div className="md:col-span-1 border border-border rounded-lg overflow-hidden">
          <div className="bg-muted px-4 py-3 font-medium text-sm">Roles</div>
          {isLoadingRoles ? (
            <div className="p-4 flex justify-center">
              <Loader2 className="w-5 h-5 animate-spin text-muted-foreground" />
            </div>
          ) : (
            <ul>
              {roles.map((role) => (
                <li key={role.id}>
                  <button
                    type="button"
                    onClick={() => setSelectedRoleId(role.id)}
                    className={`w-full text-left px-4 py-3 border-b border-border last:border-b-0 transition-colors ${
                      selectedRoleId === role.id ? 'bg-primary/10 text-primary font-medium' : 'hover:bg-muted'
                    }`}
                  >
                    <div className="flex items-center justify-between gap-2">
                      <span>{role.display_name}</span>
                      {role.is_system && <Badge size="sm" variant="gray">Sistema</Badge>}
                    </div>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>

        {/* Editor de permisos del rol seleccionado */}
        <div className="md:col-span-3">
          {!selectedRoleId ? (
            <EmptyState
              icon={<ShieldCheck className="w-12 h-12" />}
              title="Elegí un rol"
              description="Seleccioná un rol de la lista para ver y editar sus permisos."
            />
          ) : isLoadingPermissions ? (
            <div className="p-8 flex justify-center">
              <Loader2 className="w-6 h-6 animate-spin text-muted-foreground" />
            </div>
          ) : loadFailed ? (
            <div className="p-4 rounded-lg border border-red-200 bg-red-50 dark:bg-red-900/20 text-sm text-red-700 dark:text-red-300">
              No se pudieron cargar los permisos de este rol. Selecciona otro rol o vuelve a intentarlo.
              <div className="mt-3">
                <Button variant="secondary" size="sm" onClick={() => { setLoadState(null); setAttempt((n) => n + 1) }}>
                  Reintentar
                </Button>
              </div>
            </div>
          ) : (
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <h2 className="text-lg font-semibold">{selectedRole?.display_name}</h2>
                {canManage && (
                  <Button
                    variant="primary"
                    leftIcon={isSaving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
                    onClick={handleSave}
                    disabled={isSaving}
                  >
                    Guardar cambios
                  </Button>
                )}
              </div>

              <fieldset disabled={!canManage} className={!canManage ? 'opacity-70' : ''}>
                <RolePermissionsEditor permissions={assignedDict} onChange={setAssignedDict} />
              </fieldset>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
