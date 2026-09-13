/**
 * Cliente HTTP base para todas las peticiones API
 */
import axiosInstance from './axios'
import type { ApiResponse } from './axios'
import type { AxiosRequestConfig } from 'axios'
import { extractErrorMessage } from '@/shared/utils/errors'


class ApiClient {
  /**
   * Extrae el mensaje de error de una respuesta
   * Retorna: "code: message" para errores con código, o solo "message"
   */
  private extractErrorMessage(error: unknown): string {
    return extractErrorMessage(error, 'Error desconocido')
  }

  /**
   * GET request
   */
  async get<T>(url: string, config?: AxiosRequestConfig): Promise<T> {
    try {
      const response = await axiosInstance.get<ApiResponse<T>>(url, config)
      return response.data.data
    } catch (error) {
      throw new Error(this.extractErrorMessage(error))
    }
  }

  /**
   * POST request
   */
  async post<T>(url: string, data?: unknown, config?: AxiosRequestConfig): Promise<T> {
    try {
      const response = await axiosInstance.post<ApiResponse<T>>(url, data, config)
      return response.data.data
    } catch (error) {
      throw new Error(this.extractErrorMessage(error))
    }
  }

  /**
   * PUT request
   */
  async put<T>(url: string, data?: unknown, config?: AxiosRequestConfig): Promise<T> {
    try {
      const response = await axiosInstance.put<ApiResponse<T>>(url, data, config)
      return response.data.data
    } catch (error) {
      throw new Error(this.extractErrorMessage(error))
    }
  }

  /**
   * PATCH request
   */
  async patch<T>(url: string, data?: unknown, config?: AxiosRequestConfig): Promise<T> {
    try {
      const response = await axiosInstance.patch<ApiResponse<T>>(url, data, config)
      return response.data.data
    } catch (error) {
      throw new Error(this.extractErrorMessage(error))
    }
  }

  /**
   * DELETE request
   */
  async delete<T>(url: string, config?: AxiosRequestConfig): Promise<T> {
    try {
      const response = await axiosInstance.delete<ApiResponse<T>>(url, config)
      return response.data.data
    } catch (error) {
      throw new Error(this.extractErrorMessage(error))
    }
  }
}

export const apiClient = new ApiClient()

// Re-exportar axiosInstance para uso directo cuando se necesita (ej: upload de archivos)
export { axiosInstance }
