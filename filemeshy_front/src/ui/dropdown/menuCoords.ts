// Cálculo de posición del menú desplegable (extraído de Dropdown.tsx para poder testearlo)

// Ancho fijo del menú (coincide con la clase w-56 = 14rem de abajo). Se usa
// para calcular el `left` cuando el menú cuelga del borde derecho del
// trigger, ya que con position:fixed no hay forma de expresar "right-0"
// relativo al trigger sin conocer su ancho de antemano.
export const MENU_WIDTH_PX = 224
export const VIEWPORT_MARGIN_PX = 8

// Alto aproximado de un menú "típico" (9 ítems de 36px + padding). Solo sirve
// para decidir si abrir hacia abajo o hacia arriba; el alto real lo acota
// `maxHeight` (con scroll interno) para que ningún ítem quede inalcanzable.
export const MENU_PREFERRED_HEIGHT_PX = 340
export const TRIGGER_GAP_PX = 8

export interface MenuCoords {
  // Exactamente uno de los dos: hacia abajo se ancla por `top`, hacia arriba
  // por `bottom` (así el menú crece hacia arriba sin conocer su alto real).
  top?: number
  bottom?: number
  left: number
  maxHeight: number
}

// Calcula la posición del menú en coordenadas de viewport (position: fixed)
// a partir del trigger real, con un margen para no pisar los bordes de la
// pantalla. Si abajo no entra un menú típico y arriba hay más lugar, abre
// hacia arriba; en ambos casos acota el alto al espacio disponible.
// Compartido entre Dropdown y SplitButton.
export function computeMenuCoords(triggerEl: HTMLElement, position: 'left' | 'right'): MenuCoords {
  const rect = triggerEl.getBoundingClientRect()
  const rawLeft = position === 'left' ? rect.left : rect.right - MENU_WIDTH_PX
  const maxLeft = window.innerWidth - MENU_WIDTH_PX - VIEWPORT_MARGIN_PX
  const left = Math.min(Math.max(rawLeft, VIEWPORT_MARGIN_PX), Math.max(maxLeft, VIEWPORT_MARGIN_PX))

  const spaceBelow = window.innerHeight - rect.bottom - TRIGGER_GAP_PX - VIEWPORT_MARGIN_PX
  const spaceAbove = rect.top - TRIGGER_GAP_PX - VIEWPORT_MARGIN_PX
  const openUp = spaceBelow < MENU_PREFERRED_HEIGHT_PX && spaceAbove > spaceBelow

  if (openUp) {
    return {
      bottom: window.innerHeight - rect.top + TRIGGER_GAP_PX,
      left,
      maxHeight: Math.max(spaceAbove, 0),
    }
  }
  return { top: rect.bottom + TRIGGER_GAP_PX, left, maxHeight: Math.max(spaceBelow, 0) }
}
