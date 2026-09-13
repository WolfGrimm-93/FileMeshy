import { useState, useEffect } from 'react'
import { permissionsService, type AvailablePermissionsData } from '../services/permissions.service'
import { AVAILABLE_PERMISSIONS, RESOURCE_LABELS, ACTION_LABELS } from '../types/role.types'

// Fallback estático en caso de error o mientras carga la primera vez
const FALLBACK: AvailablePermissionsData = {
  available: AVAILABLE_PERMISSIONS,
  resource_labels: RESOURCE_LABELS,
  action_labels: ACTION_LABELS,
}

// Cache en memoria: se carga una sola vez por sesión
let _cache: AvailablePermissionsData | null = null

export function useAvailablePermissions() {
  const [data, setData] = useState<AvailablePermissionsData>(_cache ?? FALLBACK)
  const [isLoading, setIsLoading] = useState(_cache === null)

  useEffect(() => {
    if (_cache !== null) return

    permissionsService
      .getAvailable()
      .then((result) => {
        _cache = result
        setData(result)
      })
      .catch(() => {
        // Fallback silencioso al hardcoded si la API falla
        setData(FALLBACK)
      })
      .finally(() => setIsLoading(false))
  }, [])

  return { ...data, isLoading }
}
