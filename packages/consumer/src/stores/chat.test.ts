import { beforeEach, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
const stream = vi.hoisted(() => ({ events: [] as Array<{ type: string; data: unknown }>, wait: null as null | (() => void) }))
vi.mock('./user', () => ({ useUserStore: () => ({ accessToken: 'token', isLoggedIn: true }) }))
vi.mock('@/api/client', () => ({ getApiClient: () => ({ get: vi.fn() }) }))
vi.mock('@arco-design/web-vue', () => ({ Message: { error: vi.fn(), warning: vi.fn() } }))
vi.mock('@/api/chat', () => ({ async *chatSSE(_a: string, _b: string, _c: string, _d: string, signal: AbortSignal) {
  yield { type: 'token', data: 'partial' }
  await new Promise<void>(resolve => { stream.wait = resolve; signal.addEventListener('abort', () => resolve(), { once: true }) })
  yield { type: 'token', data: 'stale' }
} }))
import { useChatStore } from './chat'
beforeEach(() => setActivePinia(createPinia()))
it('aborts generation and keeps the partial assistant answer on stop', async () => {
 const store = useChatStore()
 const request = store.sendMessage('agent', 'question')
 await vi.waitFor(() => expect(store.streamingContent).toBe('partial'))
 store.stopStreaming()
 await request
 expect(store.messages.map(m => m.content)).toEqual(['question', 'partial'])
 expect(store.isStreaming).toBe(false)
})
it('reset aborts and prevents old stream output from restoring cleared messages', async () => {
 const store = useChatStore()
 const request = store.sendMessage('agent', 'question')
 await vi.waitFor(() => expect(store.streamingContent).toBe('partial'))
 store.resetChatState()
 await request
 expect(store.messages).toEqual([])
 expect(store.streamingContent).toBe('')
})


it('preserves partial output on EOF without a done event', async () => {
 const store = useChatStore()
 const request = store.sendMessage('agent', 'question')
 await vi.waitFor(() => expect(store.streamingContent).toBe('partial'))
 stream.wait?.()
 await request
 expect(store.messages.map(m => m.content)).toEqual(['question', 'partialstale'])
 expect(store.streamingContent).toBe('')
 expect(store.isStreaming).toBe(false)
})
