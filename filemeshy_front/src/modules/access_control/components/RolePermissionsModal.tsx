/**
 * Modal para ver permisos de un rol
 */
import { Modal } from '@/ui/modals/Modal'
import { Badge } from '@/ui/badges/Badge'
import { Lock } from 'lucide-react'
import type { RoleResponse } from '../types/role.types'
import { RESOURCE_LABELS, ACTION_LABELS } from '../types/role.types'

interface RolePermissionsModalProps {
  role: RoleResponse
  onClose: () => void
}

export default function RolePermissionsModal({ role, onClose }: RolePermissionsModalProps) {
  const permissionEntries = Object.entries(role.permissions || {})

  return (
    <Modal
      isOpen={true}
      onClose={onClose}
      title={`Permisos: ${role.display_name}`}
      size="xl"
    >
      <div className="space-y-6">
        {/* Info del rol */}
        <div className="bg-muted rounded-lg p-4">
          <div className="grid grid-cols-2 gap-4 text-sm">
            <div>
              <span className="text-gray-500">Nombre:</span>
              <span className="ml-2 font-mono font-medium">{role.name}</span>
            </div>
            <div>
              <span className="text-gray-500">Tipo:</span>
              <span className="ml-2">
                <Badge>
                  {role.is_system ? 'Sistema' : 'Personalizado'}
                </Badge>
              </span>
            </div>
            <div>
              <span className="text-gray-500">Usuarios:</span>
              <span className="ml-2">{role.users_count || 0}</span>
            </div>
            <div>
              <span className="text-gray-500">Estado:</span>
              <span className="ml-2">
                <Badge>
                  {role.is_active ? 'Activo' : 'Inactivo'}
                </Badge>
              </span>
            </div>
          </div>
          {role.description && (
            <div className="mt-3 pt-3 border-t border-border">
              <p className="text-sm text-muted-foreground">{role.description}</p>
            </div>
          )}
        </div>

        {/* Lista de permisos */}
        {permissionEntries.length === 0 ? (
          <div className="text-center py-8 text-gray-500">
            <Lock className="w-12 h-12 mx-auto mb-2 opacity-50" />
            <p>Este rol no tiene permisos asignados</p>
          </div>
        ) : (
          <div className="space-y-4">
            {permissionEntries.map(([resource, actions]) => (
              <div
                key={resource}
                className="border border-border rounded-lg p-4"
              >
                <div className="flex items-center gap-2 mb-3">
                  <Lock className="w-4 h-4 text-gray-400" />
                  <h4 className="font-semibold text-foreground">
                    {RESOURCE_LABELS[resource] || resource}
                  </h4>
                  <Badge size="sm">
                    {actions?.length || 0} {(actions?.length || 0) === 1 ? 'permiso' : 'permisos'}
                  </Badge>
                </div>
                <div className="flex flex-wrap gap-2">
                  {(actions || []).map((action) => (
                    <Badge
                      key={action}
                      size="sm"
                    >
                      {ACTION_LABELS[action] || action}
                    </Badge>
                  ))}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </Modal>
  )
}
