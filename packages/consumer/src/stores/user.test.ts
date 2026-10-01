import { beforeEach, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
const api = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }))
vi.mock('@/api/client', () => ({ getApiClient: () => api, setupApiClient: vi.fn() }))
vi.mock('@/router', () => ({ default: { push: vi.fn() } }))
vi.mock('./chat', () => ({ useChatStore: () => ({ resetChatState: vi.fn() }) }))
import { useUserStore } from './user'
import { queryClient } from '@/queryClient'
beforeEach(() => {
 setActivePinia(createPinia())
 const storage = new Map<string, string>()
 vi.stubGlobal('localStorage', { getItem: (k: string) => storage.get(k) || null, setItem: (k: string, v: string) => storage.set(k, v), removeItem: (k: string) => storage.delete(k) })
 queryClient.clear()
})
it('logout clears cached private data and rejects late user information', async () => {
 const store = useUserStore()
 store.accessToken = 'old'
 let resolve!: (value: unknown) => void
 api.get.mockImplementationOnce(() => new Promise(r => { resolve = r }))
 queryClient.setQueryData(['private'], { secret: true })
 const request = store.fetchUser()
 store.logout()
 expect(queryClient.getQueryData(['private'])).toBeUndefined()
 resolve({ data: { id: 'old-user', role: 'user' } })
 await request
 expect(store.userInfo).toBeNull()
 expect(store.accessToken).toBeNull()
})
