import { Calendar } from 'lucide-react'
import type { DateRangeFieldDef, FilterValues } from '../types'

export interface DateRangeFieldProps {
  field: DateRangeFieldDef
  values: FilterValues
  onChange: (key: string, value: unknown) => void
  autoFocus?: boolean
}

/** "2026-06-01" -> "01/06/2026". Formateo manual (no Intl) para no depender del
 *  idioma del navegador/SO -- el input nativo type="date" muestra su propio
 *  formato según esa configuración (a veces mm/dd/aaaa aunque la página esté en
 *  español), así que acá tapamos su texto con uno propio siempre dd/mm/aaaa. */
function toDisplay(iso: string): string {
  const [y, m, d] = iso.split('-')
  if (!y || !m || !d) return ''
  return `${d}/${m}/${y}`
}

function DateBox({
  id,
  label,
  value,
  onChange,
  autoFocus,
}: {
  id: string
  label: string
  value: string
  onChange: (value: string) => void
  autoFocus?: boolean
}) {
  return (
    <div className="relative flex-1">
      <label htmlFor={id} className="sr-only">
        {label}
      </label>
      {/* Texto visible: siempre dd/mm/aaaa, sin importar el idioma del navegador. */}
      <div className="pointer-events-none flex w-full items-center justify-between rounded-lg border border-input bg-background px-3 py-1.5 text-sm text-foreground">
        {value ? toDisplay(value) : <span className="text-muted-foreground">dd/mm/aaaa</span>}
        <Calendar className="size-3.5 text-muted-foreground" />
      </div>
      {/* Input nativo real, invisible pero clickeable encima -- abre el calendario del navegador
          y es el que de verdad guarda el valor ISO (yyyy-mm-dd) que espera el resto del sistema. */}
      <input
        id={id}
        type="date"
        autoComplete="off"
        autoFocus={autoFocus}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="absolute inset-0 h-full w-full cursor-pointer opacity-0"
      />
    </div>
  )
}

export function DateRangeField({ field, values, onChange, autoFocus }: DateRangeFieldProps) {
  const fromId = `filter-${field.fromKey}`
  const toId = `filter-${field.toKey}`
  const fromValue = (values[field.fromKey] as string | undefined) ?? ''
  const toValue = (values[field.toKey] as string | undefined) ?? ''

  return (
    <div>
      <p className="mb-1.5 text-xs font-medium text-muted-foreground">{field.label}</p>
      <div className="flex items-center gap-2">
        <DateBox
          id={fromId}
          label={`${field.label} — desde`}
          value={fromValue}
          onChange={(v) => onChange(field.fromKey, v || undefined)}
          autoFocus={autoFocus}
        />
        <span className="text-xs text-muted-foreground">—</span>
        <DateBox
          id={toId}
          label={`${field.label} — hasta`}
          value={toValue}
          onChange={(v) => onChange(field.toKey, v || undefined)}
        />
      </div>
    </div>
  )
}
