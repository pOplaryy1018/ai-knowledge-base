/**
 * API 客户端单例 ── 延迟初始化，由 user store 注入 token 和 401 回调
 * 支持自动 token 刷新：401 时尝试用 refresh_token 换取新 access_token 并重试请求
 */
import type { AxiosInstance, AxiosError } from 'axios'
import axios from 'axios'
import { createApiClient } from '@akb/shared'

// ── 注入的依赖 ──
let _getToken: () => string | null = () => null
let _onUnauthorized: () => void = () => {}
let _getRefreshToken: () => string | null = () => null
let _onTokenRefreshed: (token: string) => void = () => {}

// ── 裸 Axios 实例（无拦截器），用于刷新和重试请求 ──
const rawAxios = axios.create({
  baseURL: '/api',
  timeout: 15000,
  headers: { 'Content-Type': 'application/json' }})

// ── 客户端单例 ──
let _client: AxiosInstance | null = null

// ── Token 刷新去重：同一时刻只发送一个刷新请求 ──
let _refreshPromise: Promise<string | null> | null = null

/** 刷新拦截器：捕获 401，尝试刷新 token 并重试原请求 */
function createRefreshInterceptor() {
  return async (error: AxiosError) => {
    if (error.response?.status !== 401) return Promise.reject(error)
    if (!error.config) return Promise.reject(error)

    // 防止对刷新请求自身进行重试
    if (error.config.url === '/auth/refresh') {
      _onUnauthorized()
      return Promise.reject(error)
    }

    const refreshTokenValue = _getRefreshToken()
    if (!refreshTokenValue) {
      _onUnauthorized()
      return Promise.reject(error)
    }

    // 去重：已有刷新在途，等待其结果
    if (!_refreshPromise) {
      _refreshPromise = (async () => {
        try {
          const res = await rawAxios.post('/auth/refresh', {
            refresh_token: refreshTokenValue})
          const newToken: string = res.data.access_token
          _onTokenRefreshed(newToken)
          return newToken
        } catch {
          return null
        }
      })()
    }

    const newToken = await _refreshPromise
    _refreshPromise = null

    if (!newToken) {
      _onUnauthorized()
      return Promise.reject(error)
    }

    // 重试原请求（使用 rawAxios 避免触发自身拦截器）
    error.config.headers.Authorization = `Bearer ${newToken}`
    return rawAxios.request(error.config)
  }
}

/** 由 user store 在 setup 时调用，注入依赖 */
export function setupApiClient(options: {
  getToken: () => string | null
  onUnauthorized: () => void
  getRefreshToken: () => string | null
  onTokenRefreshed: (token: string) => void
}) {
  _getToken = options.getToken
  _onUnauthorized = options.onUnauthorized
  _getRefreshToken = options.getRefreshToken
  _onTokenRefreshed = options.onTokenRefreshed
}

/** 获取 API 客户端单例（首次调用时创建） */
export function getApiClient(): AxiosInstance {
  if (!_client) {
    _client = createApiClient({
      baseURL: '/api',
      getToken: () => _getToken(),
      onUnauthorized: () => _onUnauthorized()})

    // 追加刷新拦截器，利用 LIFO 顺序优先处理 401
    _client.interceptors.response.use(
      (response) => response,
      createRefreshInterceptor(),
    )
  }
  return _client
}
