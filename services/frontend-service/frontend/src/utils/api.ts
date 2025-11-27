import axios, { AxiosResponse } from 'axios';
import {
  BillingAccount,
  Subscription,
  Invoice,
  Payment,
  PaymentMethod,
  Plan,
  BillingOverview,
  CreateSubscriptionRequest,
  CreatePaymentMethodRequest,
  CreateSubscriptionResponse,
  CreatePaymentMethodResponse,
  BillingAccountResponse,
  SubscriptionsResponse,
  InvoicesResponse,
  PaymentsResponse,
  PaymentMethodsResponse,
  PlansResponse,
  PaynowPaymentRequest,
  PaynowPaymentResponse,
  PaynowPaymentStatus,
  TrialEligibilityResponse,
  UpgradeSubscriptionRequest,
  UpgradeSubscriptionResponse,
} from '../types/billing';

// Types
export interface LoginRequest {
  email: string;
  password: string;
  remember_me?: boolean;
}

export interface RegisterRequest {
  first_name: string;
  last_name: string;
  email: string;
  password: string;
  accept_terms: boolean;
  phone?: string;
  company?: string;
  country?: string;
}

export interface RegisterResponse {
  success: boolean;
  message: string;
  customer: {
    id: string;
    email: string;
    first_name: string;
    last_name: string;
    requires_verification: boolean;
  };
  supabase_user?: any;
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
  customer_id: string;
  name: string;
  description: string;
  status: 'creating' | 'starting' | 'running' | 'stopping' | 'stopped' | 'paused' | 'error' | 'terminated';
  billing_status: 'trial' | 'paid' | 'payment_required';
  external_url: string | null;
  internal_url: string | null;
  database_name: string;
  odoo_version: string;
  instance_type: string;
  created_at: string;
  updated_at: string;
  admin_email: string;
  demo_data: boolean;
  subscription_id?: string;
  error_message?: string;
}

export interface CreateInstanceRequest {
  customer_id: string;
  name: string;
  description?: string | null;
  odoo_version: string;
  instance_type: 'development' | 'staging' | 'production';
  cpu_limit: number;
  memory_limit: string;
  storage_limit: string;
  admin_email: string;
  database_name: string;
  subdomain?: string | null;
  demo_data: boolean;
  custom_addons: string[];
}

export interface CreateInstanceWithSubscriptionRequest {
  customer_id: string;
  plan_name?: string;
  name: string;
  description?: string | null;
  admin_email: string;
  subdomain?: string | null;
  database_name: string;
  odoo_version?: string;
  instance_type?: string;
  demo_data?: boolean;
  cpu_limit?: number;
  memory_limit?: string;
  storage_limit?: string;
  custom_addons?: string[];
  phase_type?: string;
  // For reactivating terminated instances
  instance_id?: string;
}

export interface CreateInstanceWithSubscriptionResponse {
  success: boolean;
  subscription_id: string;
  subscription: any;
  invoice?: any;
  message: string;
  instance_config: any;
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

// Configuration management
class ConfigManager {
  private static config: AppConfig | null = null;
  private static initPromise: Promise<void> | null = null;

  static async initialize(): Promise<void> {
    if (this.config) return; // Already initialized
    if (this.initPromise) return this.initPromise; // Already initializing

    this.initPromise = (async () => {
      try {
        // Fetch config from Flask backend using relative URL
        const response = await axios.get('/api/config', {
          timeout: 5000,
        });
        this.config = response.data;
      } catch (error) {
        console.error('Failed to fetch config from backend, using fallback:', error);
        // Fallback: derive from window.location
        const hostname = window.location.hostname;
        const protocol = window.location.protocol;

        let apiBaseUrl: string;
        if (hostname === 'localhost' || hostname === '127.0.0.1') {
          // When accessing via localhost, use port-based access
          apiBaseUrl = `${protocol}//localhost:8003`;
        } else {
          // Extract domain from hostname (e.g., app.example.com -> api.example.com)
          const domain = hostname.replace(/^app\./, '');
          apiBaseUrl = `${protocol}//api.${domain}`;
        }

        this.config = {
          BASE_DOMAIN: hostname.replace(/^app\./, ''),
          ENVIRONMENT: 'development',
          API_BASE_URL: apiBaseUrl,
          VERSION: '1.0.0',
          FEATURES: {
            billing: true,
            analytics: false,
            monitoring: true,
          },
        };
      }
    })();

    return this.initPromise;
  }

  static getConfig(): AppConfig {
    if (!this.config) {
      throw new Error('ConfigManager not initialized. Call initialize() first.');
    }
    return this.config;
  }

  static getApiBaseUrl(): string {
    return this.getConfig().API_BASE_URL;
  }
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

// Axios instance configuration - Uses dynamic config from backend
// Note: The baseURL will be updated after ConfigManager initializes
const api = axios.create({
  baseURL: '', // Will be set dynamically after config loads
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Update axios baseURL after config is loaded
export const initializeAPI = async (): Promise<void> => {
  await ConfigManager.initialize();
  api.defaults.baseURL = ConfigManager.getApiBaseUrl();
};

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
          // Use dynamic base URL for refresh token endpoint
          const baseURL = ConfigManager.getApiBaseUrl();
          const response = await axios.post(`${baseURL}/user/auth/refresh-token`, {
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
  
  register: (data: RegisterRequest): Promise<AxiosResponse<RegisterResponse>> => 
    api.post('/user/auth/register', data),
  
  verifyEmail: (token: string): Promise<AxiosResponse<{success: boolean, message: string, customer?: any}>> => 
    api.post('/user/auth/verify-email', { token }),
  
  resendVerification: (email: string): Promise<AxiosResponse<{success: boolean, message: string}>> => 
    api.post('/user/auth/resend-verification', { email }),

  requestPasswordReset: (email: string): Promise<AxiosResponse<{success: boolean, message: string}>> =>
    api.post('/user/auth/password-reset', { email }),

  resetPasswordWithToken: (token: string, newPassword: string, confirmPassword: string): Promise<AxiosResponse<{success: boolean, message: string}>> =>
    api.post('/user/auth/password-reset-complete', { token, new_password: newPassword, confirm_password: confirmPassword }),

  changePassword: (currentPassword: string, newPassword: string): Promise<AxiosResponse<{success: boolean, message: string}>> =>
    api.post('/user/auth/password-change', { current_password: currentPassword, new_password: newPassword }),
};


export const instanceAPI = {
  list: (customerId: string): Promise<AxiosResponse<{instances: Instance[], total: number}>> => 
    api.get(`/instance/api/v1/instances/?customer_id=${customerId}`),
  
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
  
  checkSubdomain: (subdomain: string): Promise<AxiosResponse<{subdomain: string, available: boolean, message: string}>> => 
    api.get(`/instance/api/v1/instances/check-subdomain/${subdomain}`),
};

export const billingAPI = {
  // Account management
  getAccount: (customerId: string): Promise<AxiosResponse<BillingAccountResponse>> => 
    api.get(`/billing/api/billing/accounts/${customerId}`),
  
  createAccount: (customerId: string, data: { email: string; name: string; company?: string }): Promise<AxiosResponse<BillingAccountResponse>> => 
    api.post('/billing/api/billing/accounts/', { customer_id: customerId, ...data }),
  
  // Subscriptions
  getSubscriptions: (customerId: string): Promise<AxiosResponse<SubscriptionsResponse>> => 
    api.get(`/billing/api/billing/subscriptions/${customerId}`),
  
  createSubscription: (data: CreateSubscriptionRequest): Promise<AxiosResponse<CreateSubscriptionResponse>> => 
    api.post('/billing/api/billing/subscriptions/', data),
  
  cancelSubscription: (subscriptionId: string, reason?: string): Promise<AxiosResponse<{success: boolean, message: string}>> => 
    api.delete(`/billing/api/billing/subscriptions/${subscriptionId}`, { data: { reason } }),
  
  // Invoices
  getInvoices: (customerId: string, page: number = 1, limit: number = 10): Promise<AxiosResponse<InvoicesResponse>> => 
    api.get(`/billing/api/billing/invoices/${customerId}?page=${page}&limit=${limit}`),
  
  getInvoice: (invoiceId: string): Promise<AxiosResponse<{success: boolean, invoice: Invoice}>> => 
    api.get(`/billing/api/billing/invoices/detail/${invoiceId}`),
  
  downloadInvoice: (invoiceId: string): Promise<AxiosResponse<Blob>> => 
    api.get(`/billing/api/billing/invoices/${invoiceId}/pdf`, { responseType: 'blob' }),
  
  // Payments
  getPayments: (customerId: string, page: number = 1, limit: number = 10): Promise<AxiosResponse<PaymentsResponse>> => 
    api.get(`/billing/api/billing/payments/${customerId}?page=${page}&limit=${limit}`),
  
  makePayment: (invoiceId: string, paymentMethodId?: string): Promise<AxiosResponse<{success: boolean, payment: Payment}>> => 
    api.post('/billing/api/billing/payments/', { invoice_id: invoiceId, payment_method_id: paymentMethodId }),
  
  // Payment Methods
  getPaymentMethods: (customerId: string): Promise<AxiosResponse<PaymentMethodsResponse>> => 
    api.get(`/billing/api/billing/payment-methods/${customerId}`),
  
  addPaymentMethod: (data: CreatePaymentMethodRequest): Promise<AxiosResponse<CreatePaymentMethodResponse>> => 
    api.post('/billing/api/billing/payment-methods/', data),
  
  deletePaymentMethod: (paymentMethodId: string): Promise<AxiosResponse<{success: boolean, message: string}>> => 
    api.delete(`/billing/api/billing/payment-methods/${paymentMethodId}`),
  
  setDefaultPaymentMethod: (paymentMethodId: string): Promise<AxiosResponse<{success: boolean, message: string}>> => 
    api.put(`/billing/api/billing/payment-methods/${paymentMethodId}/default`, {}),
  
  // Plans
  getPlans: (): Promise<AxiosResponse<PlansResponse>> =>
    api.get('/billing/api/billing/plans/'),

  // Trial Eligibility
  getTrialEligibility: (customerId: string): Promise<AxiosResponse<TrialEligibilityResponse>> =>
    api.get(`/billing/api/billing/trial-eligibility/${customerId}`),

  // Billing Overview
  getBillingOverview: (customerId: string): Promise<AxiosResponse<{success: boolean, data: BillingOverview}>> =>
    api.get(`/billing/api/billing/accounts/overview/${customerId}`),
  
  // Instance with Subscription Creation
  createInstanceWithSubscription: (data: CreateInstanceWithSubscriptionRequest): Promise<AxiosResponse<CreateInstanceWithSubscriptionResponse>> =>
    api.post('/billing/api/billing/instances/', data),
  
  // Individual Subscription Management
  getSubscription: (subscriptionId: string): Promise<AxiosResponse<{success: boolean, subscription: any, metadata: any}>> =>
    api.get(`/billing/api/billing/subscriptions/subscription/${subscriptionId}`),
  
  getSubscriptionInvoices: (subscriptionId: string, page: number = 1, limit: number = 10): Promise<AxiosResponse<{success: boolean, invoices: any[], total: number}>> =>
    api.get(`/billing/api/billing/subscriptions/subscription/${subscriptionId}/invoices?page=${page}&limit=${limit}`),
  
  pauseSubscription: (subscriptionId: string): Promise<AxiosResponse<{success: boolean, message: string}>> =>
    api.post(`/billing/api/billing/subscriptions/subscription/${subscriptionId}/pause`),
  
  resumeSubscription: (subscriptionId: string): Promise<AxiosResponse<{success: boolean, message: string}>> =>
    api.post(`/billing/api/billing/subscriptions/subscription/${subscriptionId}/resume`),
  
  cancelSubscriptionById: (subscriptionId: string, reason?: string): Promise<AxiosResponse<{success: boolean, message: string}>> =>
    api.delete(`/billing/api/billing/subscriptions/subscription/${subscriptionId}`, { data: { reason } }),

  upgradeSubscription: (subscriptionId: string, upgradeData: UpgradeSubscriptionRequest): Promise<AxiosResponse<UpgradeSubscriptionResponse>> =>
    api.post(`/billing/api/billing/subscriptions/subscription/${subscriptionId}/upgrade`, upgradeData),

  // Instance reactivation
  reactivateInstance: (data: {customer_id: string, plan_name: string, instance_id: string}): Promise<AxiosResponse<CreateInstanceWithSubscriptionResponse>> =>
    api.post('/billing/api/billing/instances/reactivate', data),

  // ==================== PAYNOW PAYMENTS ====================

  /**
   * Initiate Paynow payment for an invoice
   * Supports mobile money (EcoCash/OneMoney) and card payments
   */
  initiatePaynowPayment: (request: PaynowPaymentRequest): Promise<AxiosResponse<PaynowPaymentResponse>> =>
    api.post('/billing/api/billing/payments/paynow/initiate', request),

  /**
   * Get Paynow payment status
   * Used for polling payment status until completion
   */
  getPaynowPaymentStatus: (paymentId: string): Promise<AxiosResponse<PaynowPaymentStatus>> =>
    api.get(`/billing/api/billing/payments/paynow/status/${paymentId}`),
};

export { TokenManager, ConfigManager };
export default api;