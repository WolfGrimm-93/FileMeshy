import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { useState } from 'react'

let hookValue: {
  available: Record<string, string[]>
  resource_labels: Record<string, string>
  action_labels: Record<string, string>
}
vi.mock('../hooks/useAvailablePermissions', () => ({ useAvailablePermissions: () => hookValue }))

import RolePermissionsEditor from './RolePermissionsEditor'
import type { RolePermissions } from '../types/role.types'

const labels = { view: 'Ver' }
const make = (resources: string[]) => ({
  available: Object.fromEntries(resources.map((r) => [r, ['view']])),
  resource_labels: Object.fromEntries(resources.map((r) => [r, r.toUpperCase()])),
  action_labels: labels,
})

describe('RolePermissionsEditor', () => {
  it('expande todos los recursos cuando llega un nuevo `available`', () => {
    hookValue = make(['a'])
    const { rerender } = render(<RolePermissionsEditor permissions={{}} onChange={() => {}} />)
    expect(screen.getAllByText('Ver')).toHaveLength(1)
    hookValue = make(['a', 'b', 'c'])
    rerender(<RolePermissionsEditor permissions={{}} onChange={() => {}} />)
    expect(screen.getAllByText('Ver')).toHaveLength(3)
  })

  it('colapsar un recurso sigue funcionando y no se re-expande en re-renders sin cambio de available', () => {
    hookValue = make(['a', 'b'])
    const { rerender } = render(<RolePermissionsEditor permissions={{}} onChange={() => {}} />)
    fireEvent.click(screen.getAllByRole('button')[0])
    expect(screen.getAllByText('Ver')).toHaveLength(1)
    rerender(<RolePermissionsEditor permissions={{}} onChange={() => {}} />)
    expect(screen.getAllByText('Ver')).toHaveLength(1)
  })

  it('BUG ids repetidos: clic en el TEXTO "Ver" del tercer recurso togglea solo ese', () => {
    hookValue = make(['dashboard', 'files', 'folders'])
    const seen: RolePermissions[] = []
    const Host = () => {
      const [p, setP] = useState<RolePermissions>({})
      return <RolePermissionsEditor permissions={p} onChange={(n) => { seen.push(n); setP(n) }} />
    }
    render(<Host />)
    fireEvent.click(screen.getAllByText('Ver')[2])
    expect(seen).toEqual([{ folders: ['view'] }])
    // ids únicos en el documento
    const ids = Array.from(document.querySelectorAll('input[type="checkbox"]')).map((i) => i.id)
    expect(new Set(ids).size).toBe(ids.length)
  })
})
