/**
 * Ícono representativo (lucide-react) según mime-type. Generaliza el mapper
 * que antes vivía inline en FileList (ui/file-upload/FileUpload.tsx),
 * limitado a imagen/PDF/genérico -- ahora lo comparten FileList y
 * FileGridView (vistas de íconos del explorador de archivos).
 */
import {
  File,
  FileArchive,
  FileAudio,
  FileCode,
  FileImage,
  FileSpreadsheet,
  FileText,
  FileVideo,
  type LucideIcon,
} from 'lucide-react'

export function getFileTypeIcon(mimeType: string): LucideIcon {
  if (mimeType.startsWith('image/')) return FileImage
  if (mimeType.startsWith('video/')) return FileVideo
  if (mimeType.startsWith('audio/')) return FileAudio
  if (mimeType === 'application/pdf') return FileText
  if (
    mimeType.includes('zip') ||
    mimeType.includes('compressed') ||
    mimeType.includes('tar') ||
    mimeType.includes('rar')
  ) {
    return FileArchive
  }
  if (mimeType.includes('spreadsheet') || mimeType === 'text/csv' || mimeType.includes('excel')) {
    return FileSpreadsheet
  }
  if (
    mimeType.startsWith('text/') ||
    mimeType.includes('json') ||
    mimeType.includes('xml') ||
    mimeType.includes('javascript')
  ) {
    return FileCode
  }
  return File
}
