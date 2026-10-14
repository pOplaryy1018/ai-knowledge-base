import { beforeEach, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
const stream = vi.hoisted(() => ({ events: [] as Array<{ type: string; data: unknown }>, wait: null as null | (() => void) }))
const client = vi.hoisted(() => ({ get: vi.fn() }))
vi.mock('./user', () => ({ useUserStore: () => ({ accessToken: 'token', isLoggedIn: true }) }))
vi.mock('@/api/client', () => ({ getApiClient: () => client }))
vi.mock('@arco-design/web-vue', () => ({ Message: { error: vi.fn(), warning: vi.fn() } }))
vi.mock('@/api/chat', () => ({ async *chatSSE(_a: string, _b: string, _c: string, _d: string, signal: AbortSignal) {
  yield { type: 'token', data: 'partial' }
  await new Promise<void>(resolve => { stream.wait = resolve; signal.addEventListener('abort', () => resolve(), { once: true }) })
  yield { type: 'token', data: 'stale' }
} }))
import { useChatStore } from './chat'
beforeEach(() => { setActivePinia(createPinia()); client.get.mockReset() })
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

it('selects the shared Agent exactly and does not fall back on an inaccessible id', async () => {
 const store = useChatStore()
 client.get.mockResolvedValueOnce({ data: { id: 'shared', name: 'Shared assistant' } })
 await store.fetchDefaultAgent('shared')
 expect(client.get.mock.calls[0][0]).toBe('/agents/shared')
 expect(store.agent?.id).toBe('shared')
 client.get.mockRejectedValueOnce(new Error('Forbidden'))
 await expect(store.fetchDefaultAgent('private')).rejects.toThrow('Forbidden')
 expect(store.agent).toBeNull()
 expect(client.get).toHaveBeenCalledTimes(2)
})

it('switching Agent aborts old detail and stream, and rejects late detail completion', async () => {
 const store = useChatStore()
 let release!: (value: unknown) => void
 client.get.mockImplementationOnce(() => new Promise(resolve => { release = resolve }))
 const oldDetail = store.fetchDefaultAgent('old')
 const signal = client.get.mock.calls[0][1].signal as AbortSignal
 client.get.mockResolvedValueOnce({ data: { id: 'next', name: 'Next' } })
 await store.fetchDefaultAgent('next')
 release({ data: { id: 'old', name: 'Old' } })
 await oldDetail
 expect(signal?.aborted).toBe(true)
 expect(store.agent?.id).toBe('next')
 const streaming = store.sendMessage('next', 'question')
 await vi.waitFor(() => expect(store.streamingContent).toBe('partial'))
 client.get.mockResolvedValueOnce({ data: { id: 'last', name: 'Last' } })
 await store.fetchDefaultAgent('last')
 await streaming
 expect(store.agent?.id).toBe('last')
 expect(store.currentConversationId).toBeNull()
 expect(store.messages).toEqual([])
 expect(store.streamingContent).toBe('')
})
