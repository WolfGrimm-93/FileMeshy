import axiosInstance from '@/shared/config/axios'
import { filesService } from './files.service'
import { foldersService } from './folders.service'

vi.mock('@/shared/config/axios', () => ({ default: { post: vi.fn().mockResolvedValue({ data: {} }) } }))

const post = vi.mocked(axiosInstance.post)
beforeEach(() => post.mockClear())

describe('copy: destino inequívoco', () => {
  it('sin destino manda body vacío (el backend copia en la misma carpeta)', async () => {
    await filesService.copy('f1')
    expect(post).toHaveBeenCalledWith('/files/f1/copy', {})
    await foldersService.copy('d1')
    expect(post).toHaveBeenLastCalledWith('/folders/d1/copy', {})
  })

  it('a una carpeta X manda folder_id X', async () => {
    await filesService.copy('f1', 'X')
    expect(post).toHaveBeenCalledWith('/files/f1/copy', { folder_id: 'X' })
    await foldersService.copy('d1', 'X')
    expect(post).toHaveBeenLastCalledWith('/folders/d1/copy', { folder_id: 'X' })
  })

  it('a la raíz manda folder_id null explícito', async () => {
    await filesService.copy('f1', null)
    expect(post).toHaveBeenCalledWith('/files/f1/copy', { folder_id: null })
    await foldersService.copy('d1', null)
    expect(post).toHaveBeenLastCalledWith('/folders/d1/copy', { folder_id: null })
  })
})
