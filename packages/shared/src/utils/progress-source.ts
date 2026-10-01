import type { AxiosInstance } from 'axios'
import { readSSE } from './sse'
/** EventSource-compatible task progress using bearer headers and terminal status recovery. */
export function createProgressSource(taskId: string, client: AxiosInstance, getGeneration: () => number = () => 0) {
  const generation = getGeneration()
  const target = new EventTarget()
  const controller = new AbortController()
  let closed = false
  const source = {
    addEventListener: (type: string, listener: (event: MessageEvent) => void) => target.addEventListener(type, listener as EventListener),
    onerror: null as (() => void) | null,
    close: () => { closed = true; controller.abort() },
  }
  const dispatch = (type: string, data: string) => {
    target.dispatchEvent(new MessageEvent(type, { data }))
    if (type === 'complete' || type === 'error') source.close()
  }
  void (async () => {
    for (let attempt = 0; !closed; attempt++) {
      if (generation !== getGeneration()) { source.close(); return }
      try {
        // Axios authenticates and refreshes before opening a streaming fetch.
        const { data: status, config } = await client.get(`/import/${taskId}/status`, { signal: controller.signal })
        if (closed || generation !== getGeneration()) { source.close(); return }
        if (status.type === 'complete' || status.type === 'error') { dispatch(status.type, JSON.stringify(status)); return }
        const response = await fetch(`${client.defaults.baseURL}/import/${taskId}/progress`, {
          headers: { Authorization: String(config.headers.Authorization || '') }, signal: controller.signal,
        })
        if (!response.ok || !response.body) throw new Error('Progress connection failed')
        for await (const event of readSSE(response.body)) { if (closed || generation !== getGeneration()) { source.close(); return }; dispatch(event.type, event.data) }
      } catch { if (closed || generation !== getGeneration()) { source.close(); return } }
      if (!closed) source.onerror?.()
      if (!closed) await new Promise<void>(resolve => {
        const timer = setTimeout(resolve, Math.min(1000 * (attempt + 1), 3000))
        controller.signal.addEventListener('abort', () => { clearTimeout(timer); resolve() }, { once: true })
      })
    }
  })()
  return source
}
