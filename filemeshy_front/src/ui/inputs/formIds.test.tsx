import { render, screen, fireEvent } from '@testing-library/react'
import { Input, PasswordInput } from './Input'
import { Select } from './Select'
import { Textarea } from './Textarea'
import { Radio, RadioGroup } from './Radio'

describe('ids únicos por instancia (label repetido)', () => {
  it('PasswordInput: dos instancias sin id tienen ids distintos', () => {
    const { container } = render(
      <div>
        <PasswordInput error="a" />
        <PasswordInput error="b" />
      </div>,
    )
    const [one, two] = Array.from(container.querySelectorAll('input'))
    expect(one.id).not.toBe(two.id)
    expect(one.id).not.toBe('password')
    expect(container.querySelector(`[id="${two.id}-error"]`)).toHaveTextContent('b')
  })

  it('PasswordInput respeta un id explícito', () => {
    const { container } = render(<PasswordInput id="password" />)
    expect(container.querySelector('input')!.id).toBe('password')
  })

  it('Input: click en el label del segundo enfoca el segundo', () => {
    render(<div><Input label="Nombre" /><Input label="Nombre" /></div>)
    const inputs = screen.getAllByLabelText('Nombre')
    expect(inputs).toHaveLength(2)
    // El label del segundo controla SU control (jsdom no emula el foco por click en label)
    expect((screen.getAllByText('Nombre')[1] as HTMLLabelElement).control).toBe(inputs[1])
    expect(inputs[0].id).not.toBe(inputs[1].id)
  })

  it('Select: label repetido apunta a su propio select', () => {
    render(<div><Select label="Tipo" options={[{ value: 'a', label: 'A' }]} /><Select label="Tipo" options={[{ value: 'a', label: 'A' }]} /></div>)
    const selects = screen.getAllByLabelText('Tipo')
    expect(selects).toHaveLength(2)
    // El label del segundo controla SU control (jsdom no emula el foco por click en label)
    expect((screen.getAllByText('Tipo')[1] as HTMLLabelElement).control).toBe(selects[1])
    expect(selects[0].id).not.toBe(selects[1].id)
  })

  it('Textarea: label repetido apunta a su propio textarea', () => {
    render(<div><Textarea label="Notas" /><Textarea label="Notas" /></div>)
    const areas = screen.getAllByLabelText('Notas')
    expect(areas).toHaveLength(2)
    // El label del segundo controla SU control (jsdom no emula el foco por click en label)
    expect((screen.getAllByText('Notas')[1] as HTMLLabelElement).control).toBe(areas[1])
    expect(areas[0].id).not.toBe(areas[1].id)
  })

  it('Radio: ids únicos por opción y el name las agrupa', () => {
    const onChange = vi.fn()
    const { container } = render(
      <div>
        <RadioGroup name="g1" options={[{ value: 'x', label: 'Sí' }, { value: 'y', label: 'No' }]} onChange={onChange} />
        <RadioGroup name="g2" options={[{ value: 'x', label: 'Sí' }, { value: 'y', label: 'No' }]} />
      </div>,
    )
    const radios = Array.from(container.querySelectorAll('input[type="radio"]'))
    expect(new Set(radios.map((r) => r.id)).size).toBe(4)
    expect(radios.slice(0, 2).every((r) => r.getAttribute('name') === 'g1')).toBe(true)
    fireEvent.click(screen.getAllByText('No')[0])
    expect(onChange).toHaveBeenCalledWith('y')
  })

  it('Radio suelto respeta id explícito', () => {
    const { container } = render(<Radio label="A" id="mi-radio" name="n" value="a" readOnly />)
    expect(container.querySelector('input')!.id).toBe('mi-radio')
  })
})
