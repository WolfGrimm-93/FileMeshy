/**
 * Editor de permisos granulares para roles
 */
import { useState, useEffect } from 'react'
import { Checkbox } from '@/ui/inputs/Checkbox'
import { Badge } from '@/ui/badges/Badge'
import { ChevronDown, ChevronRight } from 'lucide-react'
import type { RolePermissions } from '../types/role.types'
import { useAvailablePermissions } from '../hooks/useAvailablePermissions'

interface RolePermissionsEditorProps {
  permissions: RolePermissions
  onChange: (permissions: RolePermissions) => void
}

export default function RolePermissionsEditor({
  permissions,
  onChange
}: RolePermissionsEditorProps) {
  const { available, resource_labels, action_labels } = useAvailablePermissions()
  const [expandedResources, setExpandedResources] = useState<Set<string>>(
    new Set(Object.keys(available))
  )

  useEffect(() => {
    setExpandedResources(new Set(Object.keys(available)))
  }, [available])

  const toggleResource = (resource: string) => {
    const newExpanded = new Set(expandedResources)
    if (newExpanded.has(resource)) {
      newExpanded.delete(resource)
    } else {
      newExpanded.add(resource)
    }
    setExpandedResources(newExpanded)
  }

  const toggleAllActionsForResource = (resource: string, checked: boolean) => {
    const newPermissions = { ...permissions }
    if (checked) {
      newPermissions[resource] = [...available[resource]]
    } else {
      delete newPermissions[resource]
    }
    onChange(newPermissions)
  }

  const toggleAction = (resource: string, action: string, checked: boolean) => {
    const newPermissions = { ...permissions }
    const currentActions = newPermissions[resource] || []

    if (checked) {
      newPermissions[resource] = [...currentActions, action]
    } else {
      newPermissions[resource] = currentActions.filter((a) => a !== action)
      if (newPermissions[resource].length === 0) {
        delete newPermissions[resource]
      }
    }

    onChange(newPermissions)
  }

  const isResourceFullySelected = (resource: string) => {
    const availableActions = available[resource]
    const selectedActions = permissions[resource] || []
    return availableActions.length === selectedActions.length && selectedActions.length > 0
  }

  return (
    <div className="space-y-2">
      {Object.entries(available).map(([resource, actions]) => {
        const isExpanded = expandedResources.has(resource)
        const isFullySelected = isResourceFullySelected(resource)
        const selectedCount = (permissions[resource] || []).length

        return (
          <div
            key={resource}
            className="border border-border rounded-lg overflow-hidden"
          >
            {/* Header del recurso */}
            <div className="bg-muted p-3 flex items-center justify-between">
              <div className="flex items-center gap-3 flex-1">
                <button
                  type="button"
                  onClick={() => toggleResource(resource)}
                  className="text-gray-500 hover:text-gray-700 dark:hover:text-gray-300"
                >
                  {isExpanded ? (
                    <ChevronDown className="w-5 h-5" />
                  ) : (
                    <ChevronRight className="w-5 h-5" />
                  )}
                </button>

                <div className="flex items-center gap-2 flex-1">
                  <Checkbox
                    checked={isFullySelected}
                    onChange={(e) => toggleAllActionsForResource(resource, e.target.checked)}
                    label={resource_labels[resource] || resource}
                  />
                  {selectedCount > 0 && (
                    <Badge size="sm">
                      {selectedCount}/{actions.length}
                    </Badge>
                  )}
                </div>
              </div>
            </div>

            {/* Acciones del recurso */}
            {isExpanded && (
              <div className="p-4 grid grid-cols-2 md:grid-cols-3 gap-3 bg-card">
                {actions.map((action) => (
                  <Checkbox
                    key={action}
                    checked={(permissions[resource] || []).includes(action)}
                    onChange={(e) => toggleAction(resource, action, e.target.checked)}
                    label={action_labels[action] || action}
                  />
                ))}
              </div>
            )}
          </div>
        )
      })}

      {/* Resumen */}
      <div className="mt-4 p-3 bg-blue-50 dark:bg-blue-900/20 rounded-lg">
        <p className="text-sm text-blue-800 dark:text-blue-200">
          <strong>Total:</strong> {Object.keys(permissions).length} recursos configurados,{' '}
          {Object.values(permissions).reduce((acc, actions) => acc + (actions?.length || 0), 0)}{' '}
          permisos otorgados
        </p>
      </div>
    </div>
  )
}
