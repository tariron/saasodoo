import axios, { AxiosResponse } from 'axios';

// Types
export interface LoginRequest {
  email: string;
  password: string;
  remember_me?: boolean;
}

export interface LoginResponse {
  success: boolean;
  message: string;
  customer: {
    id: string;
    email: string;
    first_name: string;
    last_name: string;
    is_verified: boolean;
  };
  tokens: {
    access_token: string;
    refresh_token?: string;
    token_type: string;
    expires_at: string;
    expires_in?: number;
  };
}

export interface UserProfile {
  id: string;
  email: string;
  first_name: string;
  last_name: string;
  phone?: string;
  company?: string;
  country?: string;
  created_at: string;
  instance_count: number;
  subscription_plan?: string;
  subscription_status?: string;
}

export interface Instance {
  id: string;
  tenant_id: string;
  name: string;
  description: string;
  status: 'creating' | 'starting' | 'running' | 'stopping' | 'stopped' | 'error' | 'terminated';
  external_url: string | null;
  internal_url: string | null;
  database_name: string;
  odoo_version: string;
  instance_type: string;
  created_at: string;
  updated_at: string;
  admin_email: string;
  demo_data: boolean;
}

export interface CreateInstanceRequest {
  tenant_id: string;
  name: string;
  description?: string | null;
  odoo_version: string;
  instance_type: 'development' | 'staging' | 'production';
  cpu_limit: number;
  memory_limit: string;
  storage_limit: string;
  admin_email: string;
  admin_password: string;
  database_name: string;
  subdomain?: string | null;
  demo_data: boolean;
  custom_addons: string[];
}

export interface Tenant {
  id: string;
  customer_id: string;
  name: string;
  status: string;
  created_at: string;
}

export interface TenantWithInstances extends Tenant {
  instances: Instance[];
}

export interface AppConfig {
  BASE_DOMAIN: string;
  ENVIRONMENT: string;
  API_BASE_URL: string;
  VERSION: string;
  FEATURES: {
    billing: boolean;
    analytics: boolean;
    monitoring: boolean;
  };
}

// Token management with security
class TokenManager {
  private static readonly TOKEN_KEY = 'auth_token_data';
  private static readonly REFRESH_KEY = 'refresh_token';

  static setTokens(accessToken: string, expiresAt: string, refreshToken?: string): void {
    const tokenData = {
      access_token: accessToken,
      expires_at: new Date(expiresAt).getTime(),
      created_at: Date.now()
    };
    
    // Use sessionStorage for better security
    sessionStorage.setItem(this.TOKEN_KEY, JSON.stringify(tokenData));
    if (refreshToken) {
      sessionStorage.setItem(this.REFRESH_KEY, refreshToken);
    }
  }

  static getAccessToken(): string | null {
    try {
      const tokenDataStr = sessionStorage.getItem(this.TOKEN_KEY);
      if (!tokenDataStr) return null;

      const tokenData = JSON.parse(tokenDataStr);
      
      // Check if token is expired
      if (Date.now() >= tokenData.expires_at) {
        this.clearTokens();
        return null;
      }

      return tokenData.access_token;
    } catch {
      this.clearTokens();
      return null;
    }
  }

  static getRefreshToken(): string | null {
    return sessionStorage.getItem(this.REFRESH_KEY);
  }

  static clearTokens(): void {
    sessionStorage.removeItem(this.TOKEN_KEY);
    sessionStorage.removeItem(this.REFRESH_KEY);
  }

  static isAuthenticated(): boolean {
    return this.getAccessToken() !== null;
  }
}

// Axios instance configuration - Direct calls to microservices
const api = axios.create({
  baseURL: 'https://api.saasodoo.local', // Direct to microservices via Traefik
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Request interceptor - add auth token
api.interceptors.request.use(
  (config) => {
    const token = TokenManager.getAccessToken();
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => Promise.reject(error)
);

// Response interceptor - handle auth errors
api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config;

    // Handle 401 errors
    if (error.response?.status === 401 && !originalRequest._retry) {
      originalRequest._retry = true;

      // Try to refresh token
      const refreshToken = TokenManager.getRefreshToken();
      if (refreshToken) {
        try {
          const response = await axios.post('https://api.saasodoo.local/user/auth/refresh-token', {
            refresh_token: refreshToken
          });
          
          const { tokens } = response.data;
          TokenManager.setTokens(
            tokens.access_token, 
            tokens.refresh_token, 
            tokens.expires_in
          );

          // Retry original request
          originalRequest.headers.Authorization = `Bearer ${tokens.access_token}`;
          return api(originalRequest);
        } catch (refreshError) {
          // Refresh failed, redirect to login only if not already there
          TokenManager.clearTokens();
          if (window.location.pathname !== '/login') {
            window.location.href = '/login';
          }
          return Promise.reject(refreshError);
        }
      } else {
        // No refresh token, redirect to login only if not already there
        TokenManager.clearTokens();
        if (window.location.pathname !== '/login') {
          window.location.href = '/login';
        }
      }
    }

    return Promise.reject(error);
  }
);

// API functions - Direct calls to microservices via Traefik
export const configAPI = {
  getConfig: (): Promise<AxiosResponse<AppConfig>> => 
    axios.get('/api/config'), // Get config from Flask backend
};

export const authAPI = {
  login: (data: LoginRequest): Promise<AxiosResponse<LoginResponse>> => 
    api.post('/user/auth/login', data),
  
  logout: (): Promise<AxiosResponse<{success: boolean}>> => 
    api.post('/user/auth/logout'),
  
  getProfile: (): Promise<AxiosResponse<UserProfile>> => 
    api.get('/user/auth/me'),
  
  refreshToken: (refreshToken: string): Promise<AxiosResponse<{tokens: any}>> => 
    api.post('/user/auth/refresh-token', { refresh_token: refreshToken }),
};

export const tenantAPI = {
  list: (customerId: string): Promise<AxiosResponse<{tenants: Tenant[], total: number}>> => 
    api.get(`/tenant/api/v1/tenants/?customer_id=${customerId}`),
  
  create: (data: {name: string; description: string; customer_id: string}): Promise<AxiosResponse<Tenant>> => {
    // Backend doesn't expect description field, so we exclude it
    const { description, ...backendData } = data;
    return api.post('/tenant/api/v1/tenants/', backendData);
  },
  
  get: (id: string): Promise<AxiosResponse<Tenant>> => 
    api.get(`/tenant/api/v1/tenants/${id}`),
};

export const instanceAPI = {
  list: (tenantId: string): Promise<AxiosResponse<{instances: Instance[], total: number}>> => 
    api.get(`/instance/api/v1/instances/?tenant_id=${tenantId}`),
  
  get: (id: string): Promise<AxiosResponse<Instance>> => 
    api.get(`/instance/api/v1/instances/${id}`),
  
  create: (data: CreateInstanceRequest): Promise<AxiosResponse<Instance>> => 
    api.post('/instance/api/v1/instances/', data),
  
  update: (id: string, data: Partial<Instance>): Promise<AxiosResponse<Instance>> => 
    api.put(`/instance/api/v1/instances/${id}`, data),
  
  delete: (id: string): Promise<AxiosResponse<{message: string}>> => 
    api.delete(`/instance/api/v1/instances/${id}`),
  
  action: (id: string, action: string, parameters?: any): Promise<AxiosResponse<any>> => 
    api.post(`/instance/api/v1/instances/${id}/actions`, { action, parameters }),
  
  backups: (id: string): Promise<AxiosResponse<any>> => 
    api.get(`/instance/api/v1/instances/${id}/backups`),
  
  status: (id: string): Promise<AxiosResponse<any>> => 
    api.get(`/instance/api/v1/instances/${id}/status`),
};

export { TokenManager };
export default api;