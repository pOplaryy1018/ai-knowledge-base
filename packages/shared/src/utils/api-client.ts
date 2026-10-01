import axios, { CanceledError } from 'axios'
import type { AxiosInstance, AxiosError, InternalAxiosRequestConfig } from 'axios'

export interface ApiClientOptions {
  baseURL: string
  getToken: () => string | null
  onUnauthorized: () => void
  refreshAccessToken?: () => Promise<string | null>
  getGeneration?: () => number
}
type AuthConfig = InternalAxiosRequestConfig & { authGeneration?: number; authRetried?: boolean }
const isAuthEndpoint = (url = '') => /\/auth\/(login|register|refresh)(?:$|\?)/.test(url)

export function createApiClient(options: ApiClientOptions): AxiosInstance {
  const instance = axios.create({ baseURL: options.baseURL, timeout: 15000 })
  const generation = () => options.getGeneration?.() ?? 0
  let refreshing: { generation: number; promise: Promise<string | null> } | null = null
  instance.interceptors.request.use((config: AuthConfig) => {
    if (config.authGeneration !== undefined && config.authGeneration !== generation()) throw new CanceledError('Account changed')
    config.authGeneration = generation()
    const token = options.getToken()
    if (token && !isAuthEndpoint(config.url)) config.headers.Authorization = `Bearer ${token}`
    else delete config.headers.Authorization
    return config
  })
  instance.interceptors.response.use(response => {
    if ((response.config as AuthConfig).authGeneration !== generation()) throw new CanceledError('Account changed')
    return response
  }, async (error: AxiosError) => {
    const config = error.config as AuthConfig | undefined
    if (!config || isAuthEndpoint(config.url) || error.response?.status !== 401) throw error
    const requestGeneration = config.authGeneration
    if (requestGeneration !== generation()) throw new CanceledError('Account changed')
    if (!config.authRetried && options.refreshAccessToken) {
      if (!refreshing || refreshing.generation !== requestGeneration) {
        const pending = { generation: generation(), promise: options.refreshAccessToken().catch(() => null) }
        refreshing = pending
        void pending.promise.finally(() => { if (refreshing === pending) refreshing = null })
      }
      const token = await refreshing.promise
      if (requestGeneration !== generation()) throw new CanceledError('Account changed')
      if (token) { config.authRetried = true; return instance.request(config) }
    }
    options.onUnauthorized()
    throw error
  })
  return instance
}

/** One refresh flight per identity, also shared with fetch-based streams. */
export function createAuthClient(options: ApiClientOptions & {
  getRefreshToken: () => string | null
  onTokenRefreshed: (token: string) => void
}) {
  const raw = axios.create({ baseURL: options.baseURL, timeout: 15000 })
  let pending: { generation: number; promise: Promise<string | null> } | null = null
  const refreshAccessToken = (): Promise<string | null> => {
    const generation = options.getGeneration?.() ?? 0
    if (pending?.generation === generation) return pending.promise
    const refresh = options.getRefreshToken()
    if (!refresh) return Promise.resolve(null)
    const flight = { generation, promise: raw.post('/auth/refresh', { refresh_token: refresh }).then(res => {
      if ((options.getGeneration?.() ?? 0) !== generation) return null
      const token: string = res.data.access_token
      options.onTokenRefreshed(token)
      return token
    }).catch(() => null) }
    pending = flight
    void flight.promise.finally(() => { if (pending === flight) pending = null })
    return flight.promise
  }
  return { client: createApiClient({ ...options, refreshAccessToken }), refreshAccessToken }
}
