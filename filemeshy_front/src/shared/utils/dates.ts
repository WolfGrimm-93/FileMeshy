/**
 * Utilidades de formateo de fechas — estándar República Dominicana.
 *
 * PROBLEMA UTC:
 *   `new Date("2000-01-01")` se interpreta como UTC medianoche.
 *   En RD (UTC-4) eso equivale al día anterior a las 8pm → la fecha se muestra
 *   incorrecta (día, mes, y a veces año distintos al original).
 *
 * REGLA:
 *   - Strings de fecha pura "YYYY-MM-DD"  → parsear como fecha LOCAL (sin UTC).
 *   - Strings de datetime con hora/zona   → `new Date()` maneja correctamente.
 */

const LOCALE = 'es-DO'

// ─── Parser base ──────────────────────────────────────────────────────────────

/**
 * Convierte un string de fecha a objeto Date respetando el timezone local.
 *
 * - `"2000-03-15"`             → Date local (evita desfase UTC)
 * - `"2000-03-15T10:30:00Z"`   → Date con timezone explícito (correcto)
 * - `"2000-03-15T10:30:00"`    → Date interpretado como local por el motor JS
 */
export function parseDate(dateStr: string | null | undefined): Date | null {
  if (!dateStr) return null

  // Fecha pura "YYYY-MM-DD" (exactamente 10 caracteres, sin componente de hora)
  if (/^\d{4}-\d{2}-\d{2}$/.test(dateStr)) {
    const [year, month, day] = dateStr.split('-').map(Number)
    const d = new Date(year, month - 1, day)
    return isNaN(d.getTime()) ? null : d
  }

  // Datetime con hora — normalizar espacio a T y asumir UTC si no hay zona
  let normalized = dateStr.replace(' ', 'T')
  if (/T\d{2}:\d{2}/.test(normalized) && !/Z$|[+-]\d{2}:\d{2}$/.test(normalized)) {
    normalized += 'Z'
  }
  const d = new Date(normalized)
  return isNaN(d.getTime()) ? null : d
}

// ─── Formateadores de fecha ────────────────────────────────────────────────────

/**
 * Formatea una fecha con opciones personalizadas.
 * Default: "15 de marzo de 2000"
 *
 * @example
 * formatDate("2000-03-15")
 * // → "15 de marzo de 2000"
 *
 * formatDate("2000-03-15", { day: '2-digit', month: '2-digit', year: 'numeric' })
 * // → "15/03/2000"
 */
export function formatDate(
  dateStr: string | null | undefined,
  options: Intl.DateTimeFormatOptions = { day: 'numeric', month: 'long', year: 'numeric' },
): string | null {
  const d = parseDate(dateStr)
  if (!d) return null
  return d.toLocaleDateString(LOCALE, options)
}

/**
 * Formato largo: "15 de marzo de 2000"
 */
export function formatDateLong(dateStr: string | null | undefined): string | null {
  return formatDate(dateStr, { day: 'numeric', month: 'long', year: 'numeric' })
}

/**
 * Formato corto numérico: "15/03/2000"
 */
export function formatDateShort(dateStr: string | null | undefined): string | null {
  return formatDate(dateStr, { day: '2-digit', month: '2-digit', year: 'numeric' })
}

/**
 * Formato medio con mes abreviado: "15 mar. 2000"
 */
export function formatDateMedium(dateStr: string | null | undefined): string | null {
  return formatDate(dateStr, { day: 'numeric', month: 'short', year: 'numeric' })
}

// ─── Formateadores de fecha + hora ────────────────────────────────────────────

/**
 * Fecha y hora: "15 de marzo de 2000, 10:30 a.m."
 */
export function formatDateTime(dateStr: string | null | undefined): string | null {
  const d = parseDate(dateStr)
  if (!d) return null
  return d.toLocaleString(LOCALE, {
    day: 'numeric',
    month: 'long',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    timeZone: 'America/Santo_Domingo',
  })
}

/**
 * Solo la hora: "10:30 a.m."
 */
export function formatTime(dateStr: string | null | undefined): string | null {
  const d = parseDate(dateStr)
  if (!d) return null
  return d.toLocaleTimeString(LOCALE, {
    hour: '2-digit',
    minute: '2-digit',
    timeZone: 'America/Santo_Domingo',
  })
}

// ─── Utilidades ───────────────────────────────────────────────────────────────

/**
 * Retorna la fecha en formato "YYYY-MM-DD" para usar en `<input type="date">`.
 * Usa la fecha LOCAL para evitar el desfase UTC.
 */
export function toDateInputValue(dateStr: string | null | undefined): string {
  const d = parseDate(dateStr)
  if (!d) return ''
  const year  = d.getFullYear()
  const month = String(d.getMonth() + 1).padStart(2, '0')
  const day   = String(d.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

/**
 * Fecha relativa en español: "Hoy", "Ayer", "Hace 3 días", "Hace 2 meses", etc.
 */
export function formatDateRelative(dateStr: string | null | undefined): string | null {
  const d = parseDate(dateStr)
  if (!d) return null

  const diffMs   = Date.now() - d.getTime()
  const diffDays = Math.floor(diffMs / 86_400_000)

  if (diffDays === 0) return 'Hoy'
  if (diffDays === 1) return 'Ayer'
  if (diffDays < 7)  return `Hace ${diffDays} días`
  if (diffDays < 30) return `Hace ${Math.floor(diffDays / 7)} semanas`
  if (diffDays < 365) return `Hace ${Math.floor(diffDays / 30)} meses`
  return `Hace ${Math.floor(diffDays / 365)} años`
}

/**
 * Retorna la fecha de hoy en formato "YYYY-MM-DD" (zona local).
 * Útil para valores por defecto en inputs de fecha.
 */
export function todayInputValue(): string {
  return toDateInputValue(new Date().toISOString())
}
