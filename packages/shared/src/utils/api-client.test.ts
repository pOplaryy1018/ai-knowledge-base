import { describe, it, expect, vi } from 'vitest'
import { AxiosError, AxiosHeaders } from 'axios'
import { createApiClient } from './api-client'

describe('authentication recovery', () => {
  it('refreshes before unauthorized and deduplicates concurrent 401 responses', async () => {
    let token = 'old'
    const unauthorized = vi.fn()
    const refresh = vi.fn(async () => { await new Promise(r => setTimeout(r, 10)); token = 'new'; return token })
    const client = createApiClient({ baseURL: '/api', getToken: () => token, onUnauthorized: unauthorized, refreshAccessToken: refresh, getGeneration: () => 1 })
    client.defaults.adapter = async config => {
      if (config.headers.Authorization === 'Bearer old') throw new AxiosError('expired', 'ERR_BAD_REQUEST', config, undefined, { status: 401, statusText: '', headers: {}, config, data: {} })
      return { status: 200, statusText: '', headers: {}, config, data: 'ok' }
    }
    await expect(Promise.all([client.get('/a'), client.get('/b')])).resolves.toHaveLength(2)
    expect(refresh).toHaveBeenCalledTimes(1)
    expect(unauthorized).not.toHaveBeenCalled()
  })
  it('does not refresh auth endpoints', async () => {
    const refresh = vi.fn(async () => 'new')
    const unauthorized = vi.fn()
    const client = createApiClient({ baseURL: '/api', getToken: () => null, onUnauthorized: unauthorized, refreshAccessToken: refresh })
    client.defaults.adapter = async config => { throw new AxiosError('invalid', '', config, undefined, { status: 401, statusText: '', headers: {}, config, data: {} }) }
    await expect(client.post('/auth/login')).rejects.toThrow('invalid')
    expect(refresh).not.toHaveBeenCalled()
    expect(unauthorized).not.toHaveBeenCalled()
  })
  it('rejects a previous account response', async () => {
    let generation = 1
    const client = createApiClient({ baseURL: '/api', getToken: () => 'token', onUnauthorized: vi.fn(), getGeneration: () => generation })
    client.defaults.adapter = async config => { generation++; return { status: 200, statusText: '', headers: new AxiosHeaders(), config, data: 'private' } }
    await expect(client.get('/private')).rejects.toThrow('Account changed')
  })
})
import { createAuthClient } from './api-client'
it('bounds replay to one refresh when new credentials are rejected', async () => {
 const refresh = vi.fn(async () => 'new')
 const unauthorized = vi.fn()
 const client = createApiClient({ baseURL: '/api', getToken: () => 'new', onUnauthorized: unauthorized, refreshAccessToken: refresh })
 client.defaults.adapter = async config => { throw new AxiosError('denied', '', config, undefined, { status: 401, statusText: '', headers: {}, config, data: {} }) }
 await expect(client.get('/private')).rejects.toThrow('denied')
 expect(refresh).toHaveBeenCalledTimes(1)
 expect(unauthorized).toHaveBeenCalledTimes(1)
})
it('does not apply a refresh result after the account changes', async () => {
 let generation = 0
 let resolve!: (value: unknown) => void
 const refreshed = vi.fn()
 // Raw transport is controlled through Axios default adapter for this isolated refresh request.
 const axios = (await import('axios')).default
 const original = axios.defaults.adapter
 axios.defaults.adapter = async config => new Promise(r => { resolve = value => r({ data: value, status: 200, statusText: '', headers: {}, config }) })
 const fresh = createAuthClient({ baseURL: '/api', getToken: () => 'old', getRefreshToken: () => 'refresh', getGeneration: () => generation, onTokenRefreshed: refreshed, onUnauthorized: vi.fn() })
 const request = fresh.refreshAccessToken()
 await vi.waitFor(() => expect(resolve).toBeDefined())
 generation++
 resolve({ access_token: 'old-account-new-token' })
 expect(await request).toBeNull()
 expect(refreshed).not.toHaveBeenCalled()
 axios.defaults.adapter = original
})
