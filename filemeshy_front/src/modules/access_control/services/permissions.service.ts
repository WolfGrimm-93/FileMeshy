import axiosInstance from '@/shared/config/axios'

export interface AvailablePermissionsData {
  available: Record<string, string[]>
  resource_labels: Record<string, string>
  action_labels: Record<string, string>
}

export const permissionsService = {
  async getAvailable(): Promise<AvailablePermissionsData> {
    const resp = await axiosInstance.get('/permissions/available')
    return resp.data.data
  },
}
