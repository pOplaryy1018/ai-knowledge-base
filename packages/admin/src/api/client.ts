import { createAuthClient } from '@akb/shared'
import type { ApiClientOptions } from '@akb/shared'
let options: ApiClientOptions & { getRefreshToken: () => string | null; onTokenRefreshed: (token: string) => void } = {
  baseURL: '/api', getToken: () => null, onUnauthorized: () => {}, getRefreshToken: () => null, onTokenRefreshed: () => {},
}
const auth = createAuthClient({
  baseURL: '/api', getToken: () => options.getToken(), onUnauthorized: () => options.onUnauthorized(),
  getRefreshToken: () => options.getRefreshToken(), onTokenRefreshed: token => options.onTokenRefreshed(token),
  getGeneration: () => options.getGeneration?.() ?? 0,
})
export function setupApiClient(next: Omit<typeof options, 'baseURL'>) { options = { ...next, baseURL: '/api' } }
export const getApiClient = () => auth.client
export const refreshAccessToken = auth.refreshAccessToken
export const getAccessToken = () => options.getToken()
export const getAuthGeneration = () => options.getGeneration?.() ?? 0
export const handleUnauthorized = () => options.onUnauthorized()
