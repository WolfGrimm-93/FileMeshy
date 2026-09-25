import { formatBytes } from './downloadFile'

describe('formatBytes', () => {
  it('0 bytes', () => expect(formatBytes(0)).toBe('0 B'))
  it('1023 queda en B', () => expect(formatBytes(1023)).toBe('1023 B'))
  it('1024 -> 1 KB', () => expect(formatBytes(1024)).toBe('1 KB'))
  it('1536 -> 1.5 KB', () => expect(formatBytes(1536)).toBe('1.5 KB'))
  it('MB y GB', () => {
    expect(formatBytes(5 * 1024 ** 2)).toBe('5 MB')
    expect(formatBytes(2.5 * 1024 ** 3)).toBe('2.5 GB')
  })
  it('>= 1 TB usa TB (antes sizes[4] era undefined -> "1 undefined")', () => {
    expect(formatBytes(1024 ** 4)).toBe('1 TB')
    expect(formatBytes(1.5 * 1024 ** 4)).toBe('1.5 TB')
  })
  it('por encima de TB no se sale del arreglo (acota a TB)', () => {
    expect(formatBytes(1024 ** 5)).toBe('1024 TB')
    expect(formatBytes(1024 ** 5)).not.toContain('undefined')
  })
  it('menos de 1 byte no produce "undefined"', () => {
    expect(formatBytes(0.5)).not.toContain('undefined')
  })
  it('valores no válidos (negativo, NaN, Infinity) devuelven "—"', () => {
    expect(formatBytes(-1)).toBe('—')
    expect(formatBytes(NaN)).toBe('—')
    expect(formatBytes(Infinity)).toBe('—')
  })
  it('el redondeo sube de unidad en vez de mostrar 1024', () => {
    expect(formatBytes(1048575)).toBe('1 MB')
    expect(formatBytes(1073741823)).toBe('1 GB')
  })
  it('bordes exactos de TB y PB', () => {
    expect(formatBytes(1024 ** 4)).toBe('1 TB')
    expect(formatBytes(1024 ** 5)).toBe('1024 TB')
  })
})
