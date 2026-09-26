import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

const users = vi.hoisted(() => ({ getUser: vi.fn(), updateUser: vi.fn(), uploadAvatar: vi.fn() }))
vi.mock('@/modules/users/services/user.service', () => ({ userService: users }))
let currentUser = { id: 'u1' }
vi.mock('@/modules/auth/hooks/useAuth', () => ({ useAuth: () => ({ user: currentUser }) }))
const toastMock = vi.hoisted(() => ({ error: vi.fn(), success: vi.fn() }))
vi.mock('@/ui/toast/CustomToast', () => ({ toast: toastMock }))

import MiPerfilComponent from './MiPerfilComponent'

const profile = { id: 'u1', first_name: 'Ana', last_name: 'Pérez', email: 'ana@x.com', phone: '809', avatar: '' }

beforeEach(() => {
  vi.clearAllMocks()
  currentUser = { id: 'u1' }
  vi.spyOn(console, 'error').mockImplementation(() => {})
  users.getUser.mockResolvedValue(profile)
  users.updateUser.mockResolvedValue({})
})

describe('MiPerfilComponent', () => {
  it('carga y rellena el formulario', async () => {
    render(<MiPerfilComponent />)
    expect(await screen.findByDisplayValue('Ana')).toBeInTheDocument()
    expect(screen.getByDisplayValue('Pérez')).toBeInTheDocument()
    expect(screen.getByDisplayValue('ana@x.com')).toBeInTheDocument()
    expect(users.getUser).toHaveBeenCalledWith('u1')
    expect(users.getUser).toHaveBeenCalledTimes(1)
  })

  it('guardar llama updateUser y recarga', async () => {
    const onSave = vi.fn()
    const user = userEvent.setup()
    render(<MiPerfilComponent onSave={onSave} />)
    const name = await screen.findByPlaceholderText('Tu nombre')
    await user.clear(name)
    await user.type(name, 'Bea')
    await user.click(screen.getByRole('button', { name: /Guardar/i }))
    await waitFor(() =>
      expect(users.updateUser).toHaveBeenCalledWith('u1', expect.objectContaining({ first_name: 'Bea', last_name: 'Pérez' })),
    )
    await waitFor(() => expect(onSave).toHaveBeenCalled())
    expect(users.getUser).toHaveBeenCalledTimes(2)
  })

  it('error de carga muestra toast', async () => {
    users.getUser.mockRejectedValue(new Error('x'))
    render(<MiPerfilComponent />)
    await waitFor(() => expect(toastMock.error).toHaveBeenCalledWith('Error al cargar tu perfil'))
  })

  it('al cambiar userId muestra loading y luego los datos del nuevo, sin los del anterior', async () => {
    const { rerender } = render(<MiPerfilComponent />)
    expect(await screen.findByDisplayValue('Ana')).toBeInTheDocument()
    let resolve!: (v: unknown) => void
    users.getUser.mockReturnValueOnce(new Promise((r) => { resolve = r }))
    currentUser = { id: 'u2' }
    rerender(<MiPerfilComponent />)
    expect(document.querySelector('.animate-spin')).not.toBeNull()
    expect(screen.queryByDisplayValue('Ana')).toBeNull()
    resolve({ ...profile, id: 'u2', first_name: 'Carlos' })
    expect(await screen.findByDisplayValue('Carlos')).toBeInTheDocument()
    expect(users.getUser).toHaveBeenLastCalledWith('u2')
  })
})

describe('MiPerfilComponent labels asociados', () => {
  it('cada label enfoca/asocia su control', async () => {
    render(<MiPerfilComponent />)
    await screen.findByDisplayValue('Ana')
    expect(screen.getByLabelText('Nombre')).toHaveValue('Ana')
    expect(screen.getByLabelText('Apellido')).toHaveValue('Pérez')
    expect(screen.getByLabelText('Correo Electrónico')).toHaveValue('ana@x.com')
    expect(screen.getByLabelText(/Teléfono/)).toHaveValue('809')
  })
})

describe('MiPerfilComponent avatar', () => {
  const pick = (file: File) => {
    const input = document.querySelector('input[type="file"]') as HTMLInputElement
    fireEvent.change(input, { target: { files: [file] } })
  }

  it('renderiza el avatar con la URL que devuelve el backend', async () => {
    users.getUser.mockResolvedValue({ ...profile, avatar: 'http://localhost:58102/filemeshy-media/avatars/u1.webp' })
    render(<MiPerfilComponent />)
    const img = await screen.findByAltText('Avatar')
    expect(img).toHaveAttribute('src', 'http://localhost:58102/filemeshy-media/avatars/u1.webp')
  })

  it('si la URL del avatar falla al cargar muestra el icono de fallback', async () => {
    users.getUser.mockResolvedValue({ ...profile, avatar: 'http://localhost/roto.webp' })
    render(<MiPerfilComponent />)
    fireEvent.error(await screen.findByAltText('Avatar'))
    expect(screen.queryByAltText('Avatar')).toBeNull()
  })

  it('subir un archivo usa el endpoint multipart y NO manda base64 por PUT', async () => {
    users.uploadAvatar.mockResolvedValue({ ...profile, avatar: 'http://x/media/avatars/new.webp' })
    const user = userEvent.setup()
    render(<MiPerfilComponent />)
    await screen.findByDisplayValue('Ana')
    const file = new File(['abc'], 'a.png', { type: 'image/png' })
    pick(file)
    await waitFor(() => expect(users.uploadAvatar).toHaveBeenCalledWith('u1', file))
    expect((await screen.findByAltText('Avatar'))).toHaveAttribute('src', 'http://x/media/avatars/new.webp')
    await user.click(screen.getByRole('button', { name: /Guardar/i }))
    await waitFor(() => expect(users.updateUser).toHaveBeenCalled())
    const payload = users.updateUser.mock.calls[0][1]
    expect(payload).not.toHaveProperty('avatar')
  })

  it('rechaza archivos que no son imagen o superan 5 MB con mensaje claro', async () => {
    render(<MiPerfilComponent />)
    await screen.findByDisplayValue('Ana')
    pick(new File(['x'], 'a.pdf', { type: 'application/pdf' }))
    expect(toastMock.error).toHaveBeenCalledWith(expect.stringMatching(/JPG, PNG, WEBP o GIF/))
    const big = new File(['x'], 'big.png', { type: 'image/png' })
    Object.defineProperty(big, 'size', { value: 6 * 1024 * 1024 })
    pick(big)
    expect(toastMock.error).toHaveBeenLastCalledWith(expect.stringMatching(/5 ?MB/))
    expect(users.uploadAvatar).not.toHaveBeenCalled()
  })
})
