import { create } from 'zustand'
import { persist } from 'zustand/middleware'

export interface AdminUser {
  id: string
  email: string
  name: string
  role: 'operator' | 'admin' | 'super_admin'
}

export interface LoginResponse {
  access_token: string
  refresh_token: string
  token_type: string
  user: AdminUser
}

interface AuthState {
  user: AdminUser | null
  accessToken: string | null
  refreshToken: string | null
  isAuthenticated: boolean
  login: (response: LoginResponse) => void
  logout: () => void
  setUser: (user: AdminUser) => void
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      user: null,
      accessToken: null,
      refreshToken: null,
      isAuthenticated: false,

      login: (response: LoginResponse) => {
        set({
          user: response.user,
          accessToken: response.access_token,
          refreshToken: response.refresh_token,
          isAuthenticated: true,
        })
      },

      logout: () => {
        set({
          user: null,
          accessToken: null,
          refreshToken: null,
          isAuthenticated: false,
        })
      },

      setUser: (user: AdminUser) => {
        set({ user })
      },
    }),
    {
      name: 'admin-auth-storage',
    }
  )
)
