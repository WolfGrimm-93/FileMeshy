import { render, screen, fireEvent } from '@testing-library/react'
import { DataTable } from './DataTable'

interface Row { id: string; name: string }
const data: Row[] = [{ id: 'a', name: 'Uno' }, { id: 'b', name: 'Dos' }]
const columns = [{ key: 'name' as const, label: 'Nombre' }]

describe('DataTable selección', () => {
  it('seleccionar todo emite el Set con todos los ids', () => {
    const onSelectionChange = vi.fn()
    render(<DataTable<Row> columns={columns} data={data} selectedIds={new Set()} onSelectionChange={onSelectionChange} />)
    const boxes = screen.getAllByRole('checkbox')
    fireEvent.click(boxes[0])
    expect(onSelectionChange).toHaveBeenCalledWith(new Set(['a', 'b']))
  })

  it('seleccionar una fila agrega solo esa fila a la selección existente', () => {
    const onSelectionChange = vi.fn()
    render(<DataTable<Row> columns={columns} data={data} selectedIds={new Set(['a'])} onSelectionChange={onSelectionChange} />)
    fireEvent.click(screen.getAllByRole('checkbox')[2])
    expect(onSelectionChange).toHaveBeenCalledWith(new Set(['a', 'b']))
  })

  it('compat selectedRows: marca las filas y deselecciona una', () => {
    const onSelectionChange = vi.fn()
    render(<DataTable<Row> columns={columns} data={data} selectedRows={['a']} onSelectionChange={onSelectionChange} />)
    const boxes = screen.getAllByRole('checkbox')
    expect(boxes[1]).toBeChecked()
    expect(boxes[2]).not.toBeChecked()
    fireEvent.click(boxes[1])
    expect(onSelectionChange).toHaveBeenCalledWith(new Set())
  })
})
