import { expect, it, vi } from 'vitest'
import axios from 'axios'
import { createProgressSource } from './progress-source'
it('replays a terminal snapshot without putting tokens into a URL', async () => {
 const client = axios.create({ baseURL: '/api' })
 client.defaults.adapter = async config => ({ status: 200, statusText: '', config, headers: {}, data: { type: 'complete', total_chunks: 3 } })
 const fetchSpy = vi.spyOn(globalThis, 'fetch')
 const source = createProgressSource('task', client)
 const event = await new Promise<MessageEvent>(resolve => source.addEventListener('complete', resolve))
 expect(JSON.parse(event.data)).toEqual({ type: 'complete', total_chunks: 3 })
 expect(fetchSpy).not.toHaveBeenCalled()
 fetchSpy.mockRestore()
})
it('closes an in-flight progress connection with its AbortSignal', async () => {
 const client = axios.create({ baseURL: '/api' })
 client.defaults.adapter = async config => ({ status: 200, statusText: '', config, headers: {}, data: { type: 'progress' } })
 let signal: AbortSignal | undefined
 const fetchSpy = vi.spyOn(globalThis, 'fetch').mockImplementation(async (_url, options) => {
   signal = options?.signal as AbortSignal
   return new Promise((_resolve, reject) => signal?.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError'))))
 })
 const source = createProgressSource('task', client)
 await vi.waitFor(() => expect(signal).toBeDefined())
 source.close()
 expect(signal?.aborted).toBe(true)
 expect(fetchSpy.mock.calls[0][0]).toBe('/api/import/task/progress')
 fetchSpy.mockRestore()
})
it('discards terminal progress from a previous account', async () => {
 let generation = 0
 let resolve!: (data: unknown) => void
 const client = axios.create({ baseURL: '/api' })
 client.defaults.adapter = async config => new Promise(r => { resolve = data => r({ data, status: 200, statusText: '', headers: {}, config }) })
 const source = createProgressSource('task', client, () => generation)
 const complete = vi.fn()
 source.addEventListener('complete', complete)
 await vi.waitFor(() => expect(resolve).toBeDefined())
 generation++
 resolve({ type: 'complete', total_chunks: 3 })
 await new Promise(r => setTimeout(r, 20))
 expect(complete).not.toHaveBeenCalled()
 source.close()
})
it('discards stream records and aborts after an account switch', async () => {
 let generation = 0
 const client = axios.create({ baseURL: '/api' })
 client.defaults.adapter = async config => ({ status: 200, statusText: '', headers: {}, config, data: { type: 'progress' } })
 let enqueue!: (data: string) => void
 let signal: AbortSignal | undefined
 const body = new ReadableStream<Uint8Array>({ start(c) { enqueue = data => c.enqueue(new TextEncoder().encode(data)) } })
 const fetchSpy = vi.spyOn(globalThis, 'fetch').mockImplementation(async (_url, options) => { signal = options?.signal as AbortSignal; return new Response(body) })
 const source = createProgressSource('task', client, () => generation)
 const progress = vi.fn()
 source.addEventListener('progress', progress)
 await vi.waitFor(() => expect(signal).toBeDefined())
 generation++
 enqueue('event: progress\ndata: {"percent":10}\n\n')
 await vi.waitFor(() => expect(signal?.aborted).toBe(true))
 expect(progress).not.toHaveBeenCalled()
 source.close()
 fetchSpy.mockRestore()
})
