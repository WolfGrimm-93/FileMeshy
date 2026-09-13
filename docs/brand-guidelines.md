# Guía de Marca — FileMeshy

Ver también [README.md](../README.md#documentación) para el resto de la documentación del
proyecto.

Estado: colores e íconos aplicados en `filemeshy_front`; tipografía aplicada solo en `/login`
(ver "Tipografía" más abajo). Ver "Pendiente" al final.

## Referencia rápida

| Elemento | Valor |
|---|---|
| Color primario | `#3A64D9` (azul) |
| Color secundario/acento | `#6552E0` (violeta) |
| Acento vívido (superficies oscuras) | `#22D3EE` (cian) |
| Tono base oscuro | `#0B1638` (navy/ink) |
| Tipografía de títulos | Space Grotesk |
| Tipografía de cuerpo | DM Sans |
| Voz | Directa, técnica sin ser fría, confiable |

## Origen: el ícono

Toda la paleta se extrajo programáticamente (cuantización de color real, no a ojo) del
ícono de marca (`icono-filemeshy.png`, provisto por el equipo): una nube-red (mesh) tejida
con documentos incrustados, en gradiente navy → índigo → azul → cian. El concepto conecta
tres ideas del producto directamente — **mesh** (red/tejido), **archivos** (los documentos
dentro de la nube), **cloud storage** (la forma de nube) — sin ser un ícono genérico de
carpeta u disco.

## Paleta de colores

### Primarios

| Nombre | Hex | HSL | Uso |
|---|---|---|---|
| Primary (azul) | `#3A64D9` | `224 68% 54%` | Botones primarios, links, focus ring |
| Primary hover/pressed | `#254EC1` | — | Estado hover del primario |
| Accent (violeta) | `#6552E0` | `248 70% 60%` | CTAs secundarios, highlights, badges |
| Ink (navy oscuro) | `#0B1638` | `225 67% 13%` | Fondo dark mode, superficies oscuras |

### Acento vívido — uso restringido

| Nombre | Hex | Uso permitido | Uso prohibido |
|---|---|---|---|
| Cyan | `#22D3EE` | Sobre fondos oscuros (9.8:1 contra `#0B1638`), íconos, gradientes decorativos, gráficos de datos | **Nunca** como fondo sólido con texto blanco encima (1.8:1 — no pasa WCAG AA) |

### Semánticos

| Estado | Hex | Uso |
|---|---|---|
| Success | `#10B981` | Confirmaciones, estados positivos |
| Error | `#EF4444` | Errores, acciones destructivas |
| Info | mismo que Primary | Mensajes informativos |

### Accesibilidad — verificado, no asumido

Contraste real calculado (fórmula WCAG de luminancia relativa), no estimado:

| Par | Ratio | Resultado |
|---|---|---|
| Primary `#3A64D9` + texto blanco | 5.31:1 | ✅ AA (normal), no AAA |
| Primary `#3A64D9` sobre fondo claro `#F8FAFC` | 5.08:1 | ✅ AA |
| Accent `#6552E0` + texto blanco | 5.47:1 | ✅ AA |
| Cyan `#22D3EE` + texto blanco | 1.81:1 | ❌ Falla — no usar así |
| Cyan `#22D3EE` sobre Ink `#0B1638` | 9.80:1 | ✅ AAA |
| Ink `#0B1638` sobre blanco | 17.71:1 | ✅ AAA |

### Dónde vive esto en código

- `filemeshy_front/src/assets/index.css` — variables CSS semánticas (`--primary`, `--accent`,
  etc.) en formato HSL, modo claro y oscuro.
- `filemeshy_front/src/assets/index.css` (bloque `@theme`) — escala `--color-brand-50..900`
  contiene los valores de azul de marca (`bg-brand-500`, `text-brand-600`, etc. en todo el
  proyecto); `primary.accent` es el violeta.
- `filemeshy_front/src/assets/styles/utilities.css` — gradientes de marca (`.gradient-primary`,
  `.text-gradient`) usan navy → índigo → azul → cian, el mismo gradiente del ícono.

## Tipografía

Recomendación generada con la skill `ui-ux-pro-max` (base de datos de pairings, no elegido a
ojo) para "SaaS de almacenamiento en la nube, tono moderno/tech distintivo":

```css
--font-heading: 'Space Grotesk', system-ui, sans-serif;
--font-body: 'DM Sans', system-ui, sans-serif;
```

- **Space Grotesk** (títulos): geométrica, con carácter técnico/futurista sin caer en
  "genérico de IA" — coincide con el mood tech/startup/SaaS del producto.
- **DM Sans** (cuerpo): muy legible en UI densa (tablas, formularios), misma familia de
  sensación que Space Grotesk, para que ambas convivan sin fricción visual.

**Google Fonts:**
```
https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;700&family=Space+Grotesk:wght@400;500;600;700&display=swap
```

**Estado: aplicado solo en `/login`.** `filemeshy_front/src/modules/auth/login.css` carga
las dos fuentes vía `@import` (Google Fonts) y las aplica con la clase `.filemeshy-login-scope`
(a propósito, para no filtrarse al resto de la app). El resto de `filemeshy_front` sigue en
`system-ui, Avenir, Helvetica, Arial, sans-serif` (ver `src/assets/index.css`). Extender esto a
toda la app está pendiente (ver "Pendiente" al final de este documento).

## Uso del ícono/logo

Hoy FileMeshy tiene **ícono, no logotipo** (no hay una versión con el texto "FileMeshy"
integrado a la imagen) — en todos lados donde se muestra la marca, el ícono va solo y el
texto "FileMeshy" se renderiza aparte (tipografía del sistema), nunca en la misma imagen.
Esto ya es consistente en el código (`LoginForm.tsx`, `SidebarHeader.tsx`,
`AuthProvider.tsx`).

### Dónde vive

| Archivo | Uso |
|---|---|
| `filemeshy_front/public/icon-16x16.png`, `icon-32x32.png` | Favicon |
| `filemeshy_front/public/apple-touch-icon.png` | iOS home screen (fondo blanco opaco — iOS rellena de negro si hay transparencia) |
| `filemeshy_front/public/icon-192x192.png`, `icon-512x512.png` | PWA manifest, `purpose: maskable` (con margen extra de seguridad para el recorte circular de Android) |
| `filemeshy_front/src/assets/logo-icon.png` | Ícono en el header del sidebar |
| `filemeshy_front/src/assets/images/logo-filemeshy-color.png` | Login, splash de restauración de sesión, About (renombrado desde un nombre de archivo heredado de un proyecto anterior — el contenido ya era 100% el ícono de FileMeshy, solo quedaba mal nombrado) |

### Qué NO tocar

- `filemeshy_front/src/assets/images/logo-dtslabs-*.png` — es el logo de **DTS Labs**, la
  empresa que desarrolla el producto (crédito real en el About page), no es branding de
  FileMeshy. No reemplazar.

### Reglas de uso

- Espacio libre mínimo alrededor del ícono: igual a 1/4 de su ancho.
- Tamaño mínimo digital: 24px (por debajo de eso el detalle interno de la red/documentos se
  pierde).
- No rotar, no aplicar distorsión de aspecto, no recolorear manualmente (usar solo las
  variantes ya generadas).
- Sobre fondo oscuro: usar tal cual, el ícono ya tiene contraste interno propio.
- Sobre fondo muy claro/blanco: usar tal cual (el contorno navy oscuro del ícono ya aporta
  el contraste necesario).

## Voz y personalidad

| Rasgo | Somos | No somos |
|---|---|---|
| **Directo** | Explicamos qué hace algo en la menor cantidad de palabras posible | Verborrágicos, marketing vacío |
| **Técnico sin ser frío** | Usamos el término correcto, explicamos el porqué cuando importa | Jerga innecesaria para sonar "pro" |
| **Confiable** | Hablamos de seguridad/permisos con precisión (es literalmente el producto) | Alarmistas o vagos sobre qué pasa con los archivos del usuario |
| **Con personalidad, no genérico** | El ícono ya lo dice: mesh/red, no "otra nube azul con una carpeta" | Plantillas de SaaS clonadas sin identidad |

### Términos a evitar

| Evitar | Por qué |
|---|---|
| "Revolucionario", "disruptivo" | Sobreusado, no dice nada del producto |
| "Seamless" / "sin fricción" | Sobreusado |
| "Sincronización mágica" | FileMeshy es sobre control y permisos, no "magia" — la precisión es la promesa |

## Pendiente (no aplicado en esta pasada)

- Tipografía fuera de `/login` (ver "Tipografía" más arriba).
- DTS Labs: si algún día se quiere una CIP separada de la de FileMeshy, es un ejercicio aparte
  (no hay pedido de esto todavía).
