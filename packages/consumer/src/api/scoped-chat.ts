import { readSSE } from '@akb/shared'
import type { SourceCitation, SourceComparison, ScopedResponseMode } from '@akb/shared'
import { getAccessToken, getAuthGeneration, refreshAccessToken, handleUnauthorized } from './client'
export type ScopedEvent =
  | { type: 'comparison'; data: SourceComparison }
  | { type: 'warning' | 'progress'; data: { message: string } }
  | { type: 'meta'; data: { conversation_id: string } }
  | { type: 'token'; data: { content: string } }
  | { type: 'citations'; data: SourceCitation[] }
  | { type: 'done'; data: { conversation_id: string; message_id: string } }
  | { type: 'error'; data: { message: string } }
export async function* scopedChatSSE(
  question: string,
  sourceIds: string[],
  conversationId?: string,
  signal?: AbortSignal,
  responseMode: ScopedResponseMode = 'text',
): AsyncGenerator<ScopedEvent> {
  const generation = getAuthGeneration()
  const assertActive = () => {
    if (signal?.aborted || generation !== getAuthGeneration())
      throw new DOMException('会话已取消', 'AbortError')
  }
  const request = () =>
    fetch('/api/chat/scoped', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${getAccessToken() || ''}`,
      },
      body: JSON.stringify({
        question,
        source_ids: sourceIds,
        conversation_id: conversationId,
        response_mode: responseMode,
      }),
      signal,
    })
  assertActive()
  let response = await request()
  assertActive()
  if (response.status === 401) {
    const refreshed = await refreshAccessToken()
    assertActive()
    if (refreshed) response = await request()
    assertActive()
    if (!refreshed || response.status === 401) handleUnauthorized()
  }
  if (!response.ok) {
    const body = await response.json().catch(() => ({}))
    throw new Error(body.detail || `请求失败 (${response.status})`)
  }
  if (!response.body) throw new Error('浏览器不支持流式读取')
  for await (const event of readSSE(response.body)) {
    assertActive()
    if (
      ['meta', 'token', 'citations', 'done', 'error', 'comparison', 'warning', 'progress'].includes(
        event.type,
      )
    )
      yield { type: event.type, data: JSON.parse(event.data) } as ScopedEvent
  }
}
