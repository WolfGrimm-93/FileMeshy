import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { EditQuotaModal } from './EditQuotaModal'
import type { StorageQuotaItem } from '../services/storage-quota.service'

const GB = 1024 ** 3
const quota = (id: string, limit: number | null): StorageQuotaItem => ({
  user_id: id, email: `${id}@x.com`, first_name: 'Nom', last_name: id, limit_bytes: limit, bytes_used: 0,
})
const field = () => screen.getByLabelText('Límite de almacenamiento (GB)') as HTMLInputElement

describe('EditQuotaModal', () => {
  it('precarga el límite en GB y vacío cuando no hay límite', () => {
    const { rerender } = render(<EditQuotaModal isOpen onClose={() => {}} quota={quota('u1', 5 * GB)} onSave={vi.fn()} />)
    expect(field().value).toBe('5')
    rerender(<EditQuotaModal isOpen onClose={() => {}} quota={quota('u2', null)} onSave={vi.fn()} />)
    expect(field().value).toBe('')
  })

  it('reabrir (cierra y abre) descarta la edición anterior', () => {
    const q = quota('u1', 5 * GB)
    const { rerender } = render(<EditQuotaModal isOpen onClose={() => {}} quota={q} onSave={vi.fn()} />)
    fireEvent.change(field(), { target: { value: '9' } })
    rerender(<EditQuotaModal isOpen={false} onClose={() => {}} quota={null} onSave={vi.fn()} />)
    rerender(<EditQuotaModal isOpen onClose={() => {}} quota={q} onSave={vi.fn()} />)
    expect(field().value).toBe('5')
  })

  it('guardar vacío envía null', async () => {
    const onSave = vi.fn().mockResolvedValue(undefined)
    const onClose = vi.fn()
    render(<EditQuotaModal isOpen onClose={onClose} quota={quota('u1', 5 * GB)} onSave={onSave} />)
    fireEvent.change(field(), { target: { value: '' } })
    fireEvent.click(screen.getByText('Guardar'))
    await waitFor(() => expect(onSave).toHaveBeenCalledWith('u1', null))
    await waitFor(() => expect(onClose).toHaveBeenCalled())
  })

  it('guardar "2.5" envía Math.round(2.5 * GB)', async () => {
    const onSave = vi.fn().mockResolvedValue(undefined)
    render(<EditQuotaModal isOpen onClose={() => {}} quota={quota('u1', null)} onSave={onSave} />)
    fireEvent.change(field(), { target: { value: '2.5' } })
    fireEvent.click(screen.getByText('Guardar'))
    await waitFor(() => expect(onSave).toHaveBeenCalledWith('u1', Math.round(2.5 * GB)))
  })

  it('un límite inválido (0) no llama a onSave', () => {
    const onSave = vi.fn()
    render(<EditQuotaModal isOpen onClose={() => {}} quota={quota('u1', null)} onSave={onSave} />)
    fireEvent.change(field(), { target: { value: '0' } })
    fireEvent.click(screen.getByText('Guardar'))
    expect(onSave).not.toHaveBeenCalled()
  })
})
