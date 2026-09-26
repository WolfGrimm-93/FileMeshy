import { render, screen, fireEvent } from '@testing-library/react'
import { Modal } from './Modal'

const noop = () => {}

describe('Modal: scroll del body con modales anidados', () => {
  it('cerrar el interno no libera el scroll mientras el externo siga abierto', () => {
    const { rerender } = render(
      <>
        <Modal isOpen onClose={noop} title="Externo">a</Modal>
        <Modal isOpen onClose={noop} title="Interno">b</Modal>
      </>,
    )
    expect(document.body.style.overflow).toBe('hidden')

    rerender(
      <>
        <Modal isOpen onClose={noop} title="Externo">a</Modal>
        <Modal isOpen={false} onClose={noop} title="Interno">b</Modal>
      </>,
    )
    expect(document.body.style.overflow).toBe('hidden')

    rerender(
      <>
        <Modal isOpen={false} onClose={noop} title="Externo">a</Modal>
        <Modal isOpen={false} onClose={noop} title="Interno">b</Modal>
      </>,
    )
    expect(document.body.style.overflow).toBe('')
  })

  it('un modal solo bloquea y al desmontar libera', () => {
    const { unmount } = render(<Modal isOpen onClose={noop} title="Solo">a</Modal>)
    expect(document.body.style.overflow).toBe('hidden')
    unmount()
    expect(document.body.style.overflow).toBe('')
  })

  it('cerrado no toca el scroll', () => {
    document.body.style.overflow = ''
    render(<Modal isOpen={false} onClose={noop} title="Cerrado">a</Modal>)
    expect(document.body.style.overflow).toBe('')
  })

  it('al cerrar el último restaura el overflow ORIGINAL de la página, no "unset"', () => {
    document.body.style.overflow = 'scroll'
    const { unmount } = render(<Modal isOpen onClose={noop} title="A">a</Modal>)
    expect(document.body.style.overflow).toBe('hidden')
    unmount()
    expect(document.body.style.overflow).toBe('scroll')
    document.body.style.overflow = ''
  })

  it('modales anidados tienen aria-labelledby/id de título únicos y consistentes', () => {
    render(
      <>
        <Modal isOpen onClose={noop} title="Externo">a</Modal>
        <Modal isOpen onClose={noop} title="Interno">b</Modal>
      </>,
    )
    const dialogs = screen.getAllByRole('dialog')
    const ids = dialogs.map((d) => d.getAttribute('aria-labelledby')!)
    expect(new Set(ids).size).toBe(2)
    dialogs.forEach((_d, i) => {
      expect(document.getElementById(ids[i])).toHaveTextContent(i === 0 ? 'Externo' : 'Interno')
    })
    expect(screen.getByRole('dialog', { name: 'Interno' })).toBeInTheDocument()
  })

  it('Escape cierra solo el modal más alto (el último abierto)', () => {
    const closeOuter = vi.fn()
    const closeInner = vi.fn()
    render(
      <>
        <Modal isOpen onClose={closeOuter} title="Externo">a</Modal>
        <Modal isOpen onClose={closeInner} title="Interno">b</Modal>
      </>,
    )
    fireEvent.keyDown(document, { key: 'Escape' })
    expect(closeInner).toHaveBeenCalledTimes(1)
    expect(closeOuter).not.toHaveBeenCalled()
  })
})
