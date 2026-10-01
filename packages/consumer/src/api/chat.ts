/**
 * 聊天 API ── SSE 流式对话 + REST 接口（对话列表、消息历史、删除）
 */

import { readSSE } from '@akb/shared'
import type {
  ConversationListResponse,
  ChatMessage,
  SSETokenEvent,
  SSEMetaEvent,
  SSEDoneEvent,
  SSEErrorEvent,
  CitationItem} from '@akb/shared'
import { getApiClient, getAccessToken, getAuthGeneration, refreshAccessToken, handleUnauthorized } from './client'

// ── SSE 事件类型 ──

export type SSEEventType = 'token' | 'citations' | 'meta' | 'done' | 'error'

export interface SSEData {
  type: SSEEventType
  data: string | CitationItem[] | { conversation_id: string } | { message: string }
}

/** 解析 SSE 数据字段 */
function parseSSEData(eventType: string, rawData: string): SSEData['data'] {
  try {
    const parsed = JSON.parse(rawData)
    switch (eventType) {
      case 'token':
        return (parsed as SSETokenEvent).content
      case 'citations':
        return parsed as CitationItem[]
      case 'meta':
        return { conversation_id: (parsed as SSEMetaEvent).conversation_id }
      case 'done':
        return { conversation_id: (parsed as SSEDoneEvent).conversation_id }
      case 'error':
        return { message: (parsed as SSEErrorEvent).message }
      default:
        return rawData
    }
  } catch {
    // 非 JSON 数据（如纯文本 token），直接返回
    return rawData
  }
}

/**
 * SSE 流式对话 ── 使用 fetch + ReadableStream 读取流
 * 返回 AsyncGenerator，yield 每个解析后的 SSE 事件
 */
export async function* chatSSE(
  agentId: string,
  message: string,
  conversationId: string | undefined,
  token: string,
  signal?: AbortSignal,
): AsyncGenerator<SSEData> {
  const generation = getAuthGeneration()
  const request = () => fetch(`/api/chat/agents/${agentId}/chat`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${getAccessToken() || token}`},
    body: JSON.stringify({
      message,
      conversation_id: conversationId}),
    signal,
  })
  let response = await request()
  if (response.status === 401 && generation === getAuthGeneration()) {
    const refreshed = await refreshAccessToken()
    if (generation !== getAuthGeneration() || signal?.aborted) throw new DOMException('Aborted', 'AbortError')
    if (refreshed) response = await request()
    if (!refreshed || response.status === 401) handleUnauthorized()
  }
  if (generation !== getAuthGeneration()) throw new DOMException('Account changed', 'AbortError')

  if (!response.ok) {
    const errorBody = await response.text().catch(() => '')
    let errorMessage = `请求失败 (${response.status})`
    try {
      const err = JSON.parse(errorBody)
      errorMessage = err.detail || err.message || errorMessage
    } catch {
      // 非 JSON 响应体，忽略
    }
    throw new Error(errorMessage)
  }

  if (!response.body) {
    throw new Error('浏览器不支持流式读取')
  }

  for await (const event of readSSE(response.body)) {
    if (generation !== getAuthGeneration() || signal?.aborted) throw new DOMException('Aborted', 'AbortError')
    yield { type: event.type as SSEEventType, data: parseSSEData(event.type, event.data) }
  }
}

// ── REST 接口 ──

/** 获取对话列表 */
export async function getConversations(
  agentId: string,
  page = 1,
  size = 20,
): Promise<ConversationListResponse> {
  const { data } = await getApiClient().get<ConversationListResponse>(
    '/chat/conversations',
    { params: { agent_id: agentId, page, size } },
  )
  return data
}

/** 获取对话历史消息 */
export async function getMessages(conversationId: string): Promise<ChatMessage[]> {
  const { data } = await getApiClient().get<ChatMessage[]>(
    `/chat/conversations/${conversationId}/messages`,
  )
  return data
}

/** 删除对话 */
export async function deleteConversation(conversationId: string): Promise<void> {
  await getApiClient().delete(`/chat/conversations/${conversationId}`)
}
