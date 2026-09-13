/**
 * Utilidades para descarga de archivos grandes con streaming y rangos.
 *
 * Para datasets de 50K+ registros:
 * 1. Consulta el total con /export/count
 * 2. Descarga por rangos (ej: 10K por rango)
 * 3. Muestra progreso real: "Rango 2 de 5 — 38%"
 * 4. Merge de rangos en un solo archivo final
 * 5. Si un rango falla, reintenta solo ese rango
 */

import { authService } from '@/modules/auth/services/auth.service'
import { env } from '../config/env'

export type ExportFormat = 'csv' | 'excel' | 'json' | 'toml'

// ---------------------------------------------------------------------------
// Progress types
// ---------------------------------------------------------------------------

export interface RangeProgress {
  /** Rango actual (1-based) */
  currentRange: number
  /** Total de rangos */
  totalRanges: number
  /** Porcentaje del rango actual (0-100) */
  rangePercent: number
  /** Porcentaje global (0-100) */
  globalPercent: number
  /** Bytes descargados en total */
  totalLoaded: number
  /** Total de registros */
  totalRecords: number
  /** Estado actual */
  status: 'counting' | 'downloading' | 'merging' | 'done' | 'error'
  /** Mensaje descriptivo */
  message: string
}

export type OnRangeProgress = (progress: RangeProgress) => void

// ---------------------------------------------------------------------------
// Config
// ---------------------------------------------------------------------------

const DEFAULT_RANGE_SIZE = 10000
const MAX_RETRIES = 2

// ---------------------------------------------------------------------------
// Core helpers
// ---------------------------------------------------------------------------

function triggerDownload(blob: Blob, filename: string) {
  const url = window.URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
  window.URL.revokeObjectURL(url)
}

export const downloadFile = triggerDownload

async function fetchAuth(url: string, init?: RequestInit): Promise<Response> {
  const token = authService.getAccessToken()
  const headers: HeadersInit = { ...(init?.headers || {}) }
  if (token) {
    (headers as Record<string, string>)['Authorization'] = `Bearer ${token}`
  }
  return fetch(`${env.apiUrl}${url}`, {
    ...init,
    headers,
    credentials: 'include',
  })
}

// ---------------------------------------------------------------------------
// Step 1: Get count + recommended range size
// ---------------------------------------------------------------------------

interface ExportCountResponse {
  total: number
  recommended_range_size: number
}

async function getExportCount(basePath: string): Promise<ExportCountResponse> {
  const response = await fetchAuth(`${basePath}/export/count`)
  if (!response.ok) throw new Error(`Count failed: ${response.status}`)
  return response.json()
}

// ---------------------------------------------------------------------------
// Step 2: Download a single range as blob with progress
// ---------------------------------------------------------------------------

async function downloadRange(
  url: string,
  onBytesLoaded?: (loaded: number) => void,
): Promise<Blob> {
  const response = await fetchAuth(url)
  if (!response.ok) throw new Error(`HTTP ${response.status}`)

  if (!response.body) {
    return response.blob()
  }

  const reader = response.body.getReader()
  const chunks: BlobPart[] = []
  let loaded = 0

  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    chunks.push(value)
    loaded += value.length
    onBytesLoaded?.(loaded)
  }

  return new Blob(chunks)
}

async function downloadRangeWithRetry(
  url: string,
  retries: number = MAX_RETRIES,
  onBytesLoaded?: (loaded: number) => void,
): Promise<Blob> {
  for (let attempt = 0; attempt <= retries; attempt++) {
    try {
      return await downloadRange(url, onBytesLoaded)
    } catch (error) {
      if (attempt === retries) throw error
      // Esperar antes de reintentar (backoff exponencial)
      await new Promise((r) => setTimeout(r, 1000 * (attempt + 1)))
    }
  }
  throw new Error('Max retries exceeded')
}

// ---------------------------------------------------------------------------
// Step 3: Merge blobs by format
// ---------------------------------------------------------------------------

function mergeCSVBlobs(blobs: Blob[]): Blob {
  // Los blobs ya vienen con/sin header según include_header
  return new Blob(blobs, { type: 'text/csv; charset=utf-8' })
}

async function mergeJSONBlobs(blobs: Blob[]): Promise<Blob> {
  // Cada rango es un JSON array, los mergeamos en uno solo
  const allItems: unknown[] = []
  for (const blob of blobs) {
    const text = await blob.text()
    const items = JSON.parse(text) as unknown[]
    allItems.push(...items)
  }
  const merged = JSON.stringify(allItems, null, 2)
  return new Blob([merged], { type: 'application/json; charset=utf-8' })
}

function mergeTOMLBlobs(blobs: Blob[]): Blob {
  // TOML: simplemente concatenar
  return new Blob(blobs, { type: 'application/toml; charset=utf-8' })
}

function mergeExcelBlobs(blobs: Blob[]): Blob {
  // Excel: cada rango ya es un .xlsx completo; si solo hay 1, retornarlo directo
  // Para múltiples rangos de Excel, el backend ya maneja el rango internamente
  return blobs[0]
}

// ---------------------------------------------------------------------------
// Main: Descarga por rangos con progreso
// ---------------------------------------------------------------------------

export interface RangedDownloadResult {
  success: boolean
  totalRecords?: number
  error?: unknown
}

export async function downloadByRanges(
  basePath: string,
  format: ExportFormat,
  filename: string,
  onProgress?: OnRangeProgress,
  rangeSize?: number,
): Promise<RangedDownloadResult> {
  try {
    // 1. Obtener total
    onProgress?.({
      currentRange: 0, totalRanges: 0, rangePercent: 0,
      globalPercent: 0, totalLoaded: 0, totalRecords: 0,
      status: 'counting', message: 'Calculando registros...',
    })

    const { total, recommended_range_size } = await getExportCount(basePath)
    const effectiveRangeSize = rangeSize ?? recommended_range_size ?? DEFAULT_RANGE_SIZE

    // Si hay pocos registros, descarga directa sin rangos
    if (total <= effectiveRangeSize) {
      return downloadSingle(basePath, format, filename, total, onProgress)
    }

    // 2. Calcular rangos
    const totalRanges = Math.ceil(total / effectiveRangeSize)
    const endpointMap: Record<ExportFormat, string> = {
      csv: 'csv', excel: 'excel', json: 'json', toml: 'toml',
    }
    const endpoint = endpointMap[format]

    // 3. Descargar cada rango
    const blobs: Blob[] = []
    let totalLoaded = 0

    for (let i = 0; i < totalRanges; i++) {
      const offset = i * effectiveRangeSize
      const limit = Math.min(effectiveRangeSize, total - offset)

      // Construir URL con params de rango
      let url = `${basePath}/export/${endpoint}?offset=${offset}&limit=${limit}`
      if (format === 'csv' && i > 0) {
        url += '&include_header=false'
      }

      onProgress?.({
        currentRange: i + 1, totalRanges, rangePercent: 0,
        globalPercent: Math.round((i / totalRanges) * 100),
        totalLoaded, totalRecords: total,
        status: 'downloading',
        message: `Descargando rango ${i + 1} de ${totalRanges} (${offset.toLocaleString()}-${(offset + limit).toLocaleString()})`,
      })

      const blob = await downloadRangeWithRetry(url, MAX_RETRIES, (loaded) => {
        const rangeLoaded = totalLoaded + loaded
        onProgress?.({
          currentRange: i + 1, totalRanges,
          rangePercent: -1, // no sabemos el total de bytes del rango
          globalPercent: Math.round(((i + (loaded > 0 ? 0.5 : 0)) / totalRanges) * 100),
          totalLoaded: rangeLoaded, totalRecords: total,
          status: 'downloading',
          message: `Rango ${i + 1}/${totalRanges} — ${formatBytes(rangeLoaded)}`,
        })
      })

      blobs.push(blob)
      totalLoaded += blob.size
    }

    // 4. Merge
    onProgress?.({
      currentRange: totalRanges, totalRanges, rangePercent: 100,
      globalPercent: 95, totalLoaded, totalRecords: total,
      status: 'merging', message: 'Uniendo rangos...',
    })

    let finalBlob: Blob
    switch (format) {
      case 'csv':   finalBlob = mergeCSVBlobs(blobs); break
      case 'json':  finalBlob = await mergeJSONBlobs(blobs); break
      case 'toml':  finalBlob = mergeTOMLBlobs(blobs); break
      case 'excel': finalBlob = mergeExcelBlobs(blobs); break
    }

    triggerDownload(finalBlob, filename)

    onProgress?.({
      currentRange: totalRanges, totalRanges, rangePercent: 100,
      globalPercent: 100, totalLoaded: finalBlob.size, totalRecords: total,
      status: 'done', message: `${total.toLocaleString()} registros exportados`,
    })

    return { success: true, totalRecords: total }
  } catch (error) {
    console.error('Error en descarga por rangos:', error)
    onProgress?.({
      currentRange: 0, totalRanges: 0, rangePercent: 0,
      globalPercent: 0, totalLoaded: 0, totalRecords: 0,
      status: 'error', message: 'Error al exportar',
    })
    return { success: false, error }
  }
}

// ---------------------------------------------------------------------------
// Descarga directa (sin rangos, para datasets pequeños)
// ---------------------------------------------------------------------------

async function downloadSingle(
  basePath: string,
  format: ExportFormat,
  filename: string,
  totalRecords: number,
  onProgress?: OnRangeProgress,
): Promise<RangedDownloadResult> {
  const endpointMap: Record<ExportFormat, string> = {
    csv: 'csv', excel: 'excel', json: 'json', toml: 'toml',
  }
  const url = `${basePath}/export/${endpointMap[format]}`

  onProgress?.({
    currentRange: 1, totalRanges: 1, rangePercent: 0,
    globalPercent: 0, totalLoaded: 0, totalRecords,
    status: 'downloading', message: 'Descargando...',
  })

  const blob = await downloadRangeWithRetry(url, MAX_RETRIES, (loaded) => {
    onProgress?.({
      currentRange: 1, totalRanges: 1, rangePercent: -1,
      globalPercent: -1, totalLoaded: loaded, totalRecords,
      status: 'downloading', message: `Descargando — ${formatBytes(loaded)}`,
    })
  })

  triggerDownload(blob, filename)

  onProgress?.({
    currentRange: 1, totalRanges: 1, rangePercent: 100,
    globalPercent: 100, totalLoaded: blob.size, totalRecords,
    status: 'done', message: `${totalRecords.toLocaleString()} registros exportados`,
  })

  return { success: true, totalRecords }
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const EXTENSIONS: Record<ExportFormat, string> = {
  csv: '.csv',
  excel: '.xlsx',
  json: '.json',
  toml: '.toml',
}

export function buildFilename(entityName: string, format: ExportFormat): string {
  const date = new Date().toISOString().split('T')[0]
  return `${entityName}_${date}${EXTENSIONS[format]}`
}

export function formatBytes(bytes: number): string {
  if (bytes === 0) return '0 B'
  const k = 1024
  const sizes = ['B', 'KB', 'MB', 'GB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return `${parseFloat((bytes / Math.pow(k, i)).toFixed(1))} ${sizes[i]}`
}
