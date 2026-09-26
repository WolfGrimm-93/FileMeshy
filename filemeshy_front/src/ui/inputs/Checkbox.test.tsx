import { render, screen, fireEvent } from '@testing-library/react'
import { Checkbox } from './Checkbox'

describe('Checkbox', () => {
  it('BUG: con el mismo label repetido, click en el texto del segundo togglea el segundo', () => {
    const onA = vi.fn()
    const onB = vi.fn()
    const { container } = render(
      <div>
        <Checkbox label="Ver" checked={false} onChange={onA} />
        <Checkbox label="Ver" checked={false} onChange={onB} />
      </div>,
    )
    const inputs = container.querySelectorAll('input')
    expect(inputs[0].id).not.toBe(inputs[1].id)

    fireEvent.click(screen.getAllByText('Ver')[1])
    expect(onB).toHaveBeenCalledOnce()
    expect(onA).not.toHaveBeenCalled()
  })

  it('respeta un id explícito', () => {
    const { container } = render(<Checkbox label="Ver" id="mi-id" error="mal" onChange={() => {}} />)
    expect(container.querySelector('input')!.id).toBe('mi-id')
    expect(container.querySelector('#mi-id-error')).toBeInTheDocument()
  })
})
