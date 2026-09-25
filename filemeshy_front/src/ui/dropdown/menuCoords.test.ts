import { computeMenuCoords, MENU_WIDTH_PX, VIEWPORT_MARGIN_PX, MENU_PREFERRED_HEIGHT_PX } from './menuCoords'

// Trigger falso: solo importa getBoundingClientRect
function fakeTrigger(rect: Partial<DOMRect>): HTMLElement {
  const el = document.createElement('button')
  el.getBoundingClientRect = () => ({ top: 0, bottom: 0, left: 0, right: 0, width: 0, height: 0, x: 0, y: 0, toJSON() {}, ...rect }) as DOMRect
  return el
}

function setViewport(width: number, height: number) {
  Object.defineProperty(window, 'innerWidth', { value: width, configurable: true })
  Object.defineProperty(window, 'innerHeight', { value: height, configurable: true })
}

describe('computeMenuCoords', () => {
  beforeEach(() => setViewport(1280, 800))

  it('abre hacia abajo cuando hay espacio suficiente', () => {
    const c = computeMenuCoords(fakeTrigger({ top: 100, bottom: 140, left: 200, right: 300 }), 'left')
    expect(c.top).toBe(148) // bottom + gap
    expect(c.bottom).toBeUndefined()
    expect(c.left).toBe(200)
  })

  it('abre hacia arriba cuando abajo hay < 340px y arriba hay más espacio', () => {
    // spaceBelow = 800 - 700 - 8 - 8 = 84 ; spaceAbove = 660 - 16 = 644
    const c = computeMenuCoords(fakeTrigger({ top: 660, bottom: 700, left: 200, right: 300 }), 'left')
    expect(c.bottom).toBe(800 - 660 + 8)
    expect(c.top).toBeUndefined()
    expect(c.maxHeight).toBe(644)
  })

  it('no abre hacia arriba si arriba tampoco hay más espacio que abajo', () => {
    setViewport(1280, 300)
    // below = 300-140-16 = 144 ; above = 100-16 = 84
    const c = computeMenuCoords(fakeTrigger({ top: 100, bottom: 140, left: 0, right: 100 }), 'left')
    expect(c.top).toBe(148)
    expect(c.bottom).toBeUndefined()
    expect(c.maxHeight).toBe(144)
  })

  it('acota maxHeight al espacio disponible hacia abajo', () => {
    setViewport(1280, 500)
    // below = 500-140-16 = 344 (>= 340: abre abajo)
    const c = computeMenuCoords(fakeTrigger({ top: 100, bottom: 140, left: 0, right: 100 }), 'left')
    expect(c.top).toBe(148)
    expect(c.maxHeight).toBe(344)
    expect(c.maxHeight).toBeGreaterThanOrEqual(MENU_PREFERRED_HEIGHT_PX)
  })

  it('maxHeight nunca es negativo', () => {
    setViewport(1280, 100)
    const c = computeMenuCoords(fakeTrigger({ top: 50, bottom: 95, left: 0, right: 100 }), 'left')
    expect(c.maxHeight).toBeGreaterThanOrEqual(0)
  })

  it('position right ancla el borde derecho del menú al del trigger', () => {
    const c = computeMenuCoords(fakeTrigger({ top: 100, bottom: 140, left: 800, right: 900 }), 'right')
    expect(c.left).toBe(900 - MENU_WIDTH_PX)
  })

  it('clamp horizontal: position left en el borde derecho no se sale de la pantalla', () => {
    const c = computeMenuCoords(fakeTrigger({ top: 100, bottom: 140, left: 1250, right: 1280 }), 'left')
    expect(c.left).toBe(1280 - MENU_WIDTH_PX - VIEWPORT_MARGIN_PX)
  })

  it('clamp horizontal: position right con trigger pegado a la izquierda no da left negativo', () => {
    const c = computeMenuCoords(fakeTrigger({ top: 100, bottom: 140, left: 0, right: 50 }), 'right')
    expect(c.left).toBe(VIEWPORT_MARGIN_PX)
  })

  it('sin espacio ni arriba ni abajo (<= 0): abre hacia abajo con maxHeight 0 (comportamiento documentado)', () => {
    setViewport(1280, 40)
    // below = 40-30-16 = -6 ; above = 10-16 = -6 (no es mayor) -> abajo
    const c = computeMenuCoords(fakeTrigger({ top: 10, bottom: 30, left: 0, right: 100 }), 'left')
    expect(c.top).toBe(38)
    expect(c.bottom).toBeUndefined()
    expect(c.maxHeight).toBe(0)
  })
})
