/**
 * API 客户端工厂 ── 创建带拦截器的 Axios 实例
 * 不依赖任何 UI 框架，保持 shared 包纯净性。
 * 401 处理通过回调注入，由调用方（admin/consumer）传入重定向逻辑。
 */

import type { AxiosInstance, AxiosError, InternalAxiosRequestConfig } from 'axios'
import axios from 'axios'

export interface ApiClientOptions {
  baseURL: string
  /** 获取当前 access_token 的函数 */
  getToken: () => string | null
  /** 401 未授权时的处理回调（如跳转登录页） */
  onUnauthorized: () => void
}

export function createApiClient(options: ApiClientOptions): AxiosInstance {
  const instance = axios.create({
    baseURL: options.baseURL,
    timeout: 15000,
    headers: { 'Content-Type': 'application/json' },
  })

  // ── 请求拦截器：自动附加 Authorization 头 ──
  instance.interceptors.request.use((config: InternalAxiosRequestConfig) => {
    const token = options.getToken()
    if (token && config.headers) {
      config.headers.Authorization = `Bearer ${token}`
    }
    return config
  })

  // ── 响应拦截器：统一错误处理 ──
  instance.interceptors.response.use(
    (response) => response,
    (error: AxiosError) => {
      if (error.response?.status === 401) {
        options.onUnauthorized()
      }
      return Promise.reject(error)
    },
  )

  return instance
}
