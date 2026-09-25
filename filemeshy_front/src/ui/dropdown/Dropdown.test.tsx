import { render, screen, fireEvent } from '@testing-library/react'
import { Dropdown } from './Dropdown'

describe('Dropdown (menú portaleado)', () => {
  const originalHeight = window.innerHeight

  afterEach(() => {
    Object.defineProperty(window, 'innerHeight', { value: originalHeight, configurable: true })
    vi.restoreAllMocks()
  })

  function mockTriggerRect(rect: Partial<DOMRect>) {
    vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockReturnValue(
      { top: 0, bottom: 0, left: 0, right: 0, width: 0, height: 0, x: 0, y: 0, toJSON() {}, ...rect } as DOMRect,
    )
  }

  it('renderiza el menú en document.body (portal) hacia abajo cuando hay espacio', () => {
    Object.defineProperty(window, 'innerHeight', { value: 800, configurable: true })
    mockTriggerRect({ top: 100, bottom: 140, left: 200, right: 300 })
    const { container } = render(<Dropdown trigger="Acciones" items={[{ label: 'Editar' }, { label: 'Borrar', danger: true }]} position="left" />)

    expect(screen.queryByRole('menu')).not.toBeInTheDocument()
    fireEvent.click(screen.getByText('Acciones'))

    const menu = screen.getByRole('menu')
    expect(container.contains(menu)).toBe(false) // vive fuera del árbol del componente
    expect(document.body.contains(menu)).toBe(true)
    expect(menu.style.top).toBe('148px')
    expect(menu.style.bottom).toBe('')
    expect(screen.getAllByRole('menuitem')).toHaveLength(2)
  })

  it('abre hacia arriba (bottom, sin top) en una ventana baja', () => {
    Object.defineProperty(window, 'innerHeight', { value: 800, configurable: true })
    mockTriggerRect({ top: 660, bottom: 700, left: 200, right: 300 })
    render(<Dropdown trigger="Acciones" items={[{ label: 'Editar' }]} />)
    fireEvent.click(screen.getByText('Acciones'))

    const menu = screen.getByRole('menu')
    expect(menu.style.bottom).toBe('148px')
    expect(menu.style.top).toBe('')
    expect(menu.style.maxHeight).toBe('644px')
  })

  it('click en un ítem ejecuta onClick y cierra el menú', () => {
    Object.defineProperty(window, 'innerHeight', { value: 800, configurable: true })
    mockTriggerRect({ top: 100, bottom: 140, left: 200, right: 300 })
    const onClick = vi.fn()
    render(<Dropdown trigger="Acciones" items={[{ label: 'Editar', onClick }]} />)
    fireEvent.click(screen.getByText('Acciones'))
    fireEvent.click(screen.getByText('Editar'))
    expect(onClick).toHaveBeenCalledOnce()
    expect(screen.queryByRole('menu')).not.toBeInTheDocument()
  })
})
