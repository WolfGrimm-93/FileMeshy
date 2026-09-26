import { useState } from 'react'
import { render, screen, fireEvent } from '@testing-library/react'
import { FilterModal } from './FilterModal'
import type { FilterGroup, FilterValues } from './types'

const groups: FilterGroup[] = [
  { fields: [{ key: 'activo', type: 'boolean', label: 'Solo activos' }] },
]

function Harness({ onApply, values }: { onApply: (v: FilterValues) => void; values: FilterValues }) {
  const [open, setOpen] = useState(true)
  return (
    <>
      <button onClick={() => setOpen(true)}>abrir</button>
      <FilterModal isOpen={open} onClose={() => setOpen(false)} groups={groups} values={values} onApply={onApply} />
    </>
  )
}

const sw = () => screen.getByRole('switch')

describe('FilterModal', () => {
  it('abre mostrando values, descarta el borrador al cerrar y reabre con values', () => {
    render(<Harness onApply={vi.fn()} values={{ activo: true }} />)
    expect(sw()).toHaveAttribute('aria-checked', 'true')

    fireEvent.click(sw()) // edita el borrador
    expect(sw()).toHaveAttribute('aria-checked', 'false')
    fireEvent.click(screen.getByText('Cancelar'))
    expect(screen.queryByRole('switch')).not.toBeInTheDocument()

    fireEvent.click(screen.getByText('abrir'))
    expect(sw()).toHaveAttribute('aria-checked', 'true')
  })

  it('Aplicar llama onApply con el borrador', () => {
    const onApply = vi.fn()
    render(<Harness onApply={onApply} values={{}} />)
    fireEvent.click(sw())
    fireEvent.click(screen.getByText('Aplicar'))
    expect(onApply).toHaveBeenCalledWith({ activo: true })
  })
})
