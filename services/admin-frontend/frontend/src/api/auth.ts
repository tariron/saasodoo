import { apiClient } from './client'
import { LoginResponse } from '@/stores/authStore'

export interface LoginCredentials {
  email: string
  password: string
}

export const authApi = {
  login: async (credentials: LoginCredentials): Promise<LoginResponse> => {
    const response = await apiClient.post<LoginResponse>('/admin/auth/login', credentials)
    return response.data
  },

  logout: async (): Promise<void> => {
    await apiClient.post('/admin/auth/logout')
  },

  getMe: async () => {
    const response = await apiClient.get('/admin/auth/me')
    return response.data
  },
}
