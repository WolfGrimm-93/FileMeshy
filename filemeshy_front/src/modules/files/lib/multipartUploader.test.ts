import {
  buildPartRanges,
  uploadPartsWithConcurrency,
  MAX_CONCURRENT_PARTS,
  MAX_PART_RETRIES,
  MultipartUploadPausedError,
  type PartRange,
} from './multipartUploader'

describe('buildPartRanges', () => {
  it('archivo de tamaño exacto múltiplo de la parte', () => {
    const r = buildPartRanges(30, 10)
    expect(r).toHaveLength(3)
    expect(r.map((p) => p.size)).toEqual([10, 10, 10])
    expect(r[2]).toEqual({ partNumber: 3, start: 20, end: 30, size: 10 })
  })
  it('archivo no múltiplo: la última parte es más chica', () => {
    const r = buildPartRanges(25, 10)
    expect(r.map((p) => [p.start, p.end, p.size])).toEqual([[0, 10, 10], [10, 20, 10], [20, 25, 5]])
    expect(r.map((p) => p.partNumber)).toEqual([1, 2, 3])
  })
  it('archivo más chico que una parte -> una sola parte', () => {
    expect(buildPartRanges(4, 10)).toEqual([{ partNumber: 1, start: 0, end: 4, size: 4 }])
  })
  it('archivo vacío -> sin partes', () => {
    expect(buildPartRanges(0, 10)).toEqual([])
  })
  it('las partes cubren el archivo completo sin huecos', () => {
    const r = buildPartRanges(1_000_003, 64_000)
    expect(r.reduce((acc, p) => acc + p.size, 0)).toBe(1_000_003)
  })
})

// XMLHttpRequest falso: cada instancia registra concurrencia y responde según `behavior`
type Behavior = (url: string) => { status: number; etag?: string | null }
let active = 0
let maxActive = 0
let behavior: Behavior = () => ({ status: 200, etag: '"etag"' })
const requestedUrls: string[] = []

class FakeXhr {
  status = 0
  upload: { onprogress: ((e: ProgressEvent) => void) | null } = { onprogress: null }
  onload: (() => void) | null = null
  onerror: (() => void) | null = null
  onabort: (() => void) | null = null
  private url = ''
  private etag: string | null = null
  open(_m: string, url: string) { this.url = url }
  getResponseHeader() { return this.etag }
  abort() { this.onabort?.() }
  send() {
    active++
    maxActive = Math.max(maxActive, active)
    requestedUrls.push(this.url)
    // Respuesta asíncrona (macrotask) para que las partes se solapen
    setTimeout(() => {
      active--
      const r = behavior(this.url)
      this.status = r.status
      this.etag = r.etag ?? null
      this.onload?.()
    }, 10)
  }
}

function makeOptions(parts: PartRange[], overrides: Partial<Parameters<typeof uploadPartsWithConcurrency>[0]> = {}) {
  return {
    file: new File([new Uint8Array(parts.reduce((a, p) => a + p.size, 0))], 'f.bin'),
    parts,
    alreadyConfirmed: new Set<number>(),
    getUrl: (n: number) => `https://minio/part-${n}`,
    refreshUrls: vi.fn(async () => {}),
    concurrency: MAX_CONCURRENT_PARTS,
    maxRetries: MAX_PART_RETRIES,
    signal: new AbortController().signal,
    onPartProgress: vi.fn(),
    onPartConfirmed: vi.fn(),
    ...overrides,
  }
}

describe('uploadPartsWithConcurrency', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    vi.stubGlobal('XMLHttpRequest', FakeXhr)
    active = 0
    maxActive = 0
    requestedUrls.length = 0
    behavior = () => ({ status: 200, etag: '"etag"' })
  })
  afterEach(() => {
    vi.useRealTimers()
    vi.unstubAllGlobals()
  })

  it('nunca supera MAX_CONCURRENT_PARTS partes en simultáneo y confirma todas', async () => {
    const parts = buildPartRanges(10 * 10, 10) // 10 partes
    const opts = makeOptions(parts)
    const p = uploadPartsWithConcurrency(opts)
    await vi.runAllTimersAsync()
    await p
    expect(maxActive).toBe(MAX_CONCURRENT_PARTS)
    expect(opts.onPartConfirmed).toHaveBeenCalledTimes(10)
    // el ETag llega sin comillas
    expect(opts.onPartConfirmed).toHaveBeenCalledWith(1, 'etag')
  })

  it('saltea las partes ya confirmadas (reanudación)', async () => {
    const parts = buildPartRanges(50, 10)
    const opts = makeOptions(parts, { alreadyConfirmed: new Set([1, 2, 3]) })
    const p = uploadPartsWithConcurrency(opts)
    await vi.runAllTimersAsync()
    await p
    expect(opts.onPartConfirmed).toHaveBeenCalledTimes(2)
    expect(requestedUrls).not.toContain('https://minio/part-1')
  })

  it('reintenta una parte que falla y termina bien (backoff con timers falsos)', async () => {
    const parts = buildPartRanges(10, 10)
    let calls = 0
    behavior = () => (++calls < 3 ? { status: 500 } : { status: 200, etag: '"ok"' })
    const opts = makeOptions(parts)
    const p = uploadPartsWithConcurrency(opts)
    await vi.runAllTimersAsync()
    await p
    expect(calls).toBe(3)
    expect(opts.onPartConfirmed).toHaveBeenCalledWith(1, 'ok')
  })

  it('agota los reintentos (1 + MAX_PART_RETRIES intentos) y lanza MultipartUploadPausedError', async () => {
    const parts = buildPartRanges(10, 10)
    let calls = 0
    behavior = () => {
      calls++
      return { status: 500 }
    }
    const opts = makeOptions(parts)
    const p = uploadPartsWithConcurrency(opts)
    const assertion = expect(p).rejects.toBeInstanceOf(MultipartUploadPausedError)
    await vi.runAllTimersAsync()
    await assertion
    expect(calls).toBe(MAX_PART_RETRIES + 1)
    expect(opts.onPartConfirmed).not.toHaveBeenCalled()
  })

  it('403 (URL vencida) pide refreshUrls y reintenta sin gastar un reintento', async () => {
    const parts = buildPartRanges(10, 10)
    let calls = 0
    behavior = () => (++calls === 1 ? { status: 403 } : { status: 200, etag: '"ok"' })
    const opts = makeOptions(parts)
    const p = uploadPartsWithConcurrency(opts)
    await vi.runAllTimersAsync()
    await p
    expect(opts.refreshUrls).toHaveBeenCalledOnce()
    expect(opts.onPartConfirmed).toHaveBeenCalledWith(1, 'ok')
  })
})
