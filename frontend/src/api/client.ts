import axios from 'axios'
import type { AxiosRequestConfig } from 'axios'
import { useUserStore } from '@/stores/user'

const instance = axios.create({
  baseURL: '/api/v1/travel',
  timeout: 60000,
  headers: {
    'Content-Type': 'application/json',
  },
})

instance.interceptors.request.use((config) => {
  try {
    const userStore = useUserStore()
    config.headers['X-User-Id'] = String(userStore.userId || 1)
  } catch {
    const cached = localStorage.getItem('travel.userId') || '1'
    config.headers['X-User-Id'] = cached
  }
  return config
})

instance.interceptors.response.use(
  (response) => response.data,
  (error) => {
    const message =
      error.response?.data?.message ||
      error.response?.data?.detail ||
      error.message ||
      '网络请求失败'
    return Promise.reject(new Error(message))
  }
)

export const apiClient = {
  get<T = any>(url: string, config?: AxiosRequestConfig): Promise<T> {
    return instance.get(url, config) as unknown as Promise<T>
  },
  post<T = any>(url: string, data?: any, config?: AxiosRequestConfig): Promise<T> {
    return instance.post(url, data, config) as unknown as Promise<T>
  },
  put<T = any>(url: string, data?: any, config?: AxiosRequestConfig): Promise<T> {
    return instance.put(url, data, config) as unknown as Promise<T>
  },
  delete<T = any>(url: string, config?: AxiosRequestConfig): Promise<T> {
    return instance.delete(url, config) as unknown as Promise<T>
  },
}
