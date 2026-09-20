/**
 * Chips de etiquetas -- reutilizado por la vista Lista (FilesPage) y la vista
 * Grilla (FileGridView) para no duplicar el mismo estilo en los dos lugares.
 * Sin color propio => gris neutro (mismo criterio que el fallback de TagsModal).
 */
import type { TagOut } from '../types'

interface TagChipsProps {
  tags: TagOut[]
  className?: string
}

export default function TagChips({ tags, className = '' }: TagChipsProps) {
  if (tags.length === 0) return null

  return (
    <div className={`flex flex-wrap gap-1 ${className}`}>
      {tags.map((tag) => (
        <span
          key={tag.id}
          className="inline-flex max-w-40 items-center truncate rounded-full px-1.5 py-0.5 text-[10px] font-medium leading-tight text-white"
          style={{ backgroundColor: tag.color ?? '#9ca3af' }}
          title={tag.name}
        >
          {tag.name}
        </span>
      ))}
    </div>
  )
}
