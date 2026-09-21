/**
 * Ronda 6 -- badge chico que indica que un resultado de búsqueda matcheó por
 * el CONTENIDO del archivo (no por su nombre), para no confundir al usuario
 * cuando ve un archivo cuyo nombre no tiene relación aparente con lo que
 * buscó. Mismo criterio visual minimalista que TagChips (rounded-full,
 * texto pequeño), reutilizado por la vista Lista (FilesPage) y la vista
 * Grilla (FileGridView).
 *
 * `matchedBy` es el campo opcional `FileOut.matched_by` -- ausente o `null`
 * cuando no hay búsqueda activa o el backend todavía no lo soporta, en cuyo
 * caso el componente no renderiza nada (degradación segura, contrato en
 * construcción en paralelo).
 */
import { FileSearch } from 'lucide-react'
import type { FileOut } from '../types'

interface ContentMatchBadgeProps {
  matchedBy: FileOut['matched_by'] | null | undefined
  /** Solo se muestra si además hay una búsqueda activa (evita falsos positivos por datos viejos). */
  hasActiveSearch: boolean
  className?: string
}

export default function ContentMatchBadge({ matchedBy, hasActiveSearch, className = '' }: ContentMatchBadgeProps) {
  if (!hasActiveSearch) return null
  if (matchedBy !== 'content' && matchedBy !== 'both') return null

  return (
    <span
      className={`inline-flex shrink-0 items-center gap-1 rounded-full bg-brand-50 px-1.5 py-0.5 text-[10px] font-medium leading-tight text-brand-700 dark:bg-brand-900/30 dark:text-brand-400 ${className}`}
      title="Este resultado coincide por el contenido del archivo, no por su nombre"
    >
      <FileSearch className="size-3" />
      Coincide en el contenido
    </span>
  )
}
