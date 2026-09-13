/**
 * LogoPickerField — campo para seleccionar imagen por URL o archivo.
 * Muestra preview, botón de upload y campo de URL alternativo.
 *
 * Uso básico (solo URL, sin upload al servidor):
 *   <LogoPickerField value={url} onChange={setUrl} />
 *
 * Uso con upload al servidor (requiere brandId):
 *   <LogoPickerField value={url} onChange={setUrl} onUpload={handleUpload} onDelete={handleDelete} />
 */

import { useRef, useState } from 'react'
import { Upload, Link2, X, Image as ImageIcon, Loader2 } from 'lucide-react'

interface LogoPickerFieldProps {
  value: string
  onChange: (url: string) => void
  /** Si se provee, se habilita el botón de upload que llama a esta función */
  onUpload?: (file: File) => Promise<string>
  /** Si se provee, se muestra el botón de eliminar */
  onDelete?: () => Promise<void>
  label?: string
  placeholder?: string
}

export function LogoPickerField({
  value,
  onChange,
  onUpload,
  onDelete,
  label = 'Imagen / Logo',
  placeholder = 'https://ejemplo.com/logo.png',
}: LogoPickerFieldProps) {
  const fileInputRef = useRef<HTMLInputElement>(null)
  const [uploading, setUploading] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const [imgError, setImgError] = useState(false)
  const [showUrl, setShowUrl] = useState(false)

  const handleFile = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file || !onUpload) return
    setUploading(true)
    try {
      const url = await onUpload(file)
      onChange(url)
      setImgError(false)
    } finally {
      setUploading(false)
      if (fileInputRef.current) fileInputRef.current.value = ''
    }
  }

  const handleDelete = async () => {
    if (!onDelete) { onChange(''); return }
    setDeleting(true)
    try {
      await onDelete()
      onChange('')
    } finally {
      setDeleting(false)
    }
  }

  const hasImage = !!value && !imgError

  return (
    <div>
      {label && (
        <p className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">{label}</p>
      )}

      <div className="flex items-start gap-4">
        {/* Preview */}
        <div className="w-20 h-20 shrink-0 rounded-xl border-2 border-dashed border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800 flex items-center justify-center overflow-hidden">
          {hasImage ? (
            <img
              src={value}
              alt="preview"
              className="w-full h-full object-contain p-1"
              onError={() => setImgError(true)}
            />
          ) : (
            <ImageIcon className="w-8 h-8 text-gray-300 dark:text-gray-600" />
          )}
        </div>

        {/* Controls */}
        <div className="flex-1 space-y-2">
          <div className="flex flex-wrap gap-2">
            {onUpload && (
              <button
                type="button"
                onClick={() => fileInputRef.current?.click()}
                disabled={uploading}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors disabled:opacity-50"
              >
                {uploading
                  ? <Loader2 className="w-3.5 h-3.5 animate-spin" />
                  : <Upload className="w-3.5 h-3.5" />
                }
                {uploading ? 'Subiendo...' : 'Subir archivo'}
              </button>
            )}
            <button
              type="button"
              onClick={() => setShowUrl(v => !v)}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors"
            >
              <Link2 className="w-3.5 h-3.5" />
              Usar URL
            </button>
            {hasImage && (
              <button
                type="button"
                onClick={handleDelete}
                disabled={deleting}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg border border-red-200 dark:border-red-800 bg-white dark:bg-gray-900 text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-900/20 transition-colors disabled:opacity-50"
              >
                {deleting
                  ? <Loader2 className="w-3.5 h-3.5 animate-spin" />
                  : <X className="w-3.5 h-3.5" />
                }
                Quitar
              </button>
            )}
          </div>

          {showUrl && (
            <div className="flex gap-2">
              <input
                type="url"
                value={value}
                onChange={e => { onChange(e.target.value); setImgError(false) }}
                placeholder={placeholder}
                className="flex-1 px-3 py-1.5 text-xs border border-gray-200 dark:border-gray-700 rounded-lg bg-white dark:bg-gray-900 text-gray-900 dark:text-white focus:ring-2 focus:ring-brand-500 focus:border-transparent"
              />
              <button type="button" onClick={() => setShowUrl(false)} className="p-1.5 text-gray-400 hover:text-gray-600 transition-colors">
                <X className="w-3.5 h-3.5" />
              </button>
            </div>
          )}

          {hasImage && (
            <p className="text-xs text-gray-400 dark:text-gray-500 truncate max-w-xs">{value}</p>
          )}

          <input
            ref={fileInputRef}
            type="file"
            accept="image/*"
            className="hidden"
            onChange={handleFile}
          />
        </div>
      </div>
    </div>
  )
}
