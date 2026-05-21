/**
 * 聊天 API ── SSE 流式对话 + REST 接口（对话列表、消息历史、删除）
 */

import type {
  ConversationListResponse,
  ChatMessage,
  SSETokenEvent,
  SSEMetaEvent,
  SSEDoneEvent,
  SSEErrorEvent,
  CitationItem} from '@akb/shared'
import { getApiClient } from './client'

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
): AsyncGenerator<SSEData> {
  const response = await fetch(`/api/chat/agents/${agentId}/chat`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token}`},
    body: JSON.stringify({
      message,
      conversation_id: conversationId}),
    // 注意：不传 signal，因为 AbortController signal 在某些浏览器中
    // 会导致 SSE 流式请求立即被中止（ERR_ABORTED）
  })

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

  const reader = response.body.getReader()
  const decoder = new TextDecoder('utf-8')
  let buffer = ''

  try {
    while (true) {
      const { done, value } = await reader.read()
      if (done) break

      buffer += decoder.decode(value, { stream: true })

      // SSE 协议：事件以双换行分隔
      const parts = buffer.split('\n\n')
      // 最后一个可能是不完整的事件，保留在 buffer 中
      buffer = parts.pop() || ''

      for (const part of parts) {
        if (!part.trim()) continue

        const lines = part.split('\n')
        let eventType = ''
        let data = ''

        for (const line of lines) {
          if (line.startsWith('event: ')) {
            eventType = line.slice(7).trim()
          } else if (line.startsWith('data: ')) {
            data = line.slice(6)
          } else if (line.startsWith('data:')) {
            data = line.slice(5)
          }
        }

        if (eventType && data !== undefined) {
          yield {
            type: eventType as SSEEventType,
            data: parseSSEData(eventType, data)}
        }
      }
    }

    // 处理缓冲区中剩余的数据
    if (buffer.trim()) {
      const lines = buffer.split('\n')
      let eventType = ''
      let data = ''

      for (const line of lines) {
        if (line.startsWith('event: ')) {
          eventType = line.slice(7).trim()
        } else if (line.startsWith('data: ')) {
          data = line.slice(6)
        } else if (line.startsWith('data:')) {
          data = line.slice(5)
        }
      }

      if (eventType && data !== undefined) {
        yield {
          type: eventType as SSEEventType,
          data: parseSSEData(eventType, data)}
      }
    }
  } finally {
    reader.releaseLock()
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
