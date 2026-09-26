import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { parseDate, minutesSince, isPast, formatRelativeShort, formatDateTime } from './dates'

const NOW = new Date('2026-06-15T12:00:00Z')

beforeEach(() => { vi.useFakeTimers(); vi.setSystemTime(NOW) })
afterEach(() => vi.useRealTimers())

describe('parseDate', () => {
  it('un datetime sin zona se interpreta como UTC', () => {
    expect(parseDate('2026-06-15T10:00:00')?.toISOString()).toBe('2026-06-15T10:00:00.000Z')
    expect(parseDate('2026-06-15 10:00:00')?.toISOString()).toBe('2026-06-15T10:00:00.000Z')
  })
  it('basura o vacío da null', () => {
    expect(parseDate('basura')).toBeNull()
    expect(parseDate(null)).toBeNull()
  })
})

describe('minutesSince / isPast', () => {
  it('calcula minutos y null si no parsea', () => {
    expect(minutesSince('2026-06-15T11:30:00Z')).toBe(30)
    expect(minutesSince('basura')).toBeNull()
  })
  it('isPast: pasado true, futuro false, inválido cuenta como vencido', () => {
    expect(isPast('2026-06-15T11:00:00Z')).toBe(true)
    expect(isPast('2026-06-15T13:00:00Z')).toBe(false)
    expect(isPast('basura')).toBe(true)
  })
})

describe('formatRelativeShort', () => {
  it.each([
    ['2026-06-15T11:59:40Z', 'Justo ahora'],
    ['2026-06-15T11:15:00Z', 'Hace 45 min'],
    ['2026-06-15T09:00:00Z', 'Hace 3h'],
    ['2026-06-13T12:00:00Z', 'Hace 2d'],
  ])('%s -> %s', (d, expected) => expect(formatRelativeShort(d)).toBe(expected))
  it('inválida muestra "—", nunca "Invalid Date"', () => {
    expect(formatRelativeShort('basura')).toBe('—')
    expect(formatRelativeShort(undefined)).toBe('—')
  })
  it('pasada una semana usa fecha media', () => {
    expect(formatRelativeShort('2026-01-10T12:00:00Z')).toMatch(/2026/)
  })
})

describe('formatDateTime', () => {
  it('inválida devuelve null', () => expect(formatDateTime('basura')).toBeNull())
})

describe('parseDate: casos base', () => {
  it('fecha pura YYYY-MM-DD se parsea como fecha local (sin desfase UTC)', () => {
    const d = parseDate('2000-03-15')!
    expect([d.getFullYear(), d.getMonth(), d.getDate()]).toEqual([2000, 2, 15])
  })
  it('tolera "+00:00Z" duplicado y respeta zonas explícitas', () => {
    expect(parseDate('2026-06-15T10:00:00+00:00Z')?.toISOString()).toBe('2026-06-15T10:00:00.000Z')
    expect(parseDate('2026-06-15T10:00:00-04:00')?.toISOString()).toBe('2026-06-15T14:00:00.000Z')
  })
  it('microsegundos de 6 dígitos con Z se resuelven al milisegundo exacto', () => {
    const d = parseDate('2026-09-25T11:30:49.842652Z')!
    expect(d.toISOString()).toBe('2026-09-25T11:30:49.842Z')
    expect(d.getTime()).toBe(Date.UTC(2026, 8, 25, 11, 30, 49, 842))
  })
  it('microsegundos sin zona (UTC) y con offset también', () => {
    expect(parseDate('2026-09-25T11:30:49.842652')?.toISOString()).toBe('2026-09-25T11:30:49.842Z')
    expect(parseDate('2026-09-25T11:30:49.842652-04:00')?.toISOString()).toBe('2026-09-25T15:30:49.842Z')
  })
  it('offset explícito +00:00 sin Z sobrante', () => {
    const d = parseDate('2026-09-25T11:30:49+00:00')!
    expect(d.toISOString()).toBe('2026-09-25T11:30:49.000Z')
    expect(d.getTime()).toBe(Date.UTC(2026, 8, 25, 11, 30, 49))
  })
})
