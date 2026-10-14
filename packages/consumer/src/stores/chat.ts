/**
 * 聊天状态管理 (Pinia Setup Store) ── 对话列表、消息流、SSE 流控制
 */

import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { Message } from '@arco-design/web-vue'
import type { ChatMessage, Agent, CitationItem } from '@akb/shared'
import { getApiClient } from '@/api/client'
import { chatSSE } from '@/api/chat'
import type { SSEData } from '@/api/chat'
import { useUserStore } from './user'

export const useChatStore = defineStore('chat', () => {
  const user = useUserStore()
  // ── 状态 ──
  const agent = ref<Agent | null>(null)
  const currentConversationId = ref<string | null>(null)
  const messages = ref<ChatMessage[]>([])
  const isLoading = ref(false)
  const isStreaming = ref(false)
  const streamingContent = ref('')
  const streamingCitations = ref<CitationItem[] | null>(null)

  /** SSE 流控制器，用于手动停止生成 */
  let controller: AbortController | null = null
  let agentController: AbortController | null = null
  let requestId = 0

  // ── 计算属性 ──
  const isLoggedIn = computed(() => user.isLoggedIn)

  // ── 状态清空 ──

  function resetChatState() {
    stopStreaming()
    agentController?.abort()
    agentController = null
    agent.value = null
    currentConversationId.value = null
    messages.value = []
    streamingContent.value = ''
    streamingCitations.value = null
    isStreaming.value = false
    isLoading.value = false
  }

  // ── Actions ──

  /** 分享链接选择指定 Agent；未指定时保留默认助手入口。 */
  async function fetchDefaultAgent(agentId?: string) {
    resetChatState()
    const id = requestId
    const ownController = new AbortController()
    agentController = ownController
    isLoading.value = true
    try {
      const selected = agentId
        ? (await getApiClient().get<Agent>(`/agents/${encodeURIComponent(agentId)}`, { signal: ownController.signal })).data
        : (await getApiClient().get<{ items: Agent[] }>('/agents', {
          params: { page: 1, size: 1 }, signal: ownController.signal })).data.items?.[0]
      if (id !== requestId) return null
      agent.value = selected || null
      return agent.value
    } catch (error) {
      if (id !== requestId) return null
      throw error
    } finally {
      if (id === requestId) { isLoading.value = false; agentController = null }
    }
  }

  /** 停止当前 SSE 流 */
  function stopStreaming() {
    requestId++
    controller?.abort()
    controller = null
    if (streamingContent.value) handleSSEEvent({ type: 'done', data: { conversation_id: currentConversationId.value || '' } })
    isStreaming.value = false
  }

  /** 发送消息并处理 SSE 流 */
  async function sendMessage(agentId: string, content: string) {
    if (!content.trim() || isStreaming.value) return

    // 将用户消息添加到本地列表
    const userMessage: ChatMessage = {
      id: `temp-${Date.now()}`,
      conversation_id: currentConversationId.value || '',
      role: 'user',
      content: content.trim(),
      citations: null,
      created_at: new Date().toISOString()}
    messages.value = [...messages.value, userMessage]

    // 开始流式响应
    isStreaming.value = true
    streamingContent.value = ''
    streamingCitations.value = null

    // 重置停止标志
    const id = ++requestId
    controller = new AbortController()
    let completed = false

    try {
      for await (const event of chatSSE(
        agentId,
        content.trim(),
        currentConversationId.value || undefined,
        user.accessToken || '',
        controller.signal,
      )) {
        // 如果用户点击了停止，退出循环
        if (id !== requestId) break

        if (event.type === 'done') completed = true
        handleSSEEvent(event)
      }
    } catch (err: any) {
      // AbortError 不视为错误
      if (id === requestId && err?.name !== 'AbortError') {
        if (streamingContent.value) handleSSEEvent({ type: 'done', data: { conversation_id: currentConversationId.value || '' } })
        const errorMessage: ChatMessage = {
          id: `error-${Date.now()}`,
          conversation_id: currentConversationId.value || '',
          role: 'assistant',
          content: `抱歉，请求失败：${err.message || '未知错误'}`,
          citations: null,
          created_at: new Date().toISOString()}
        messages.value = [...messages.value, errorMessage]

        Message.error(err.message || '请求失败，请重试')
      }
    } finally {
      if (id === requestId) {
        if (streamingContent.value) {
          handleSSEEvent({ type: 'done', data: { conversation_id: currentConversationId.value || '' } })
          if (!completed) Message.warning('连接已中断，已保留部分回答，请重试')
        }
        isStreaming.value = false; controller = null
      }
    }
  }

  /** 处理单个 SSE 事件 */
  function handleSSEEvent(event: SSEData) {
    switch (event.type) {
      case 'meta': {
        const metaData = event.data as { conversation_id: string }
        if (metaData.conversation_id) {
          currentConversationId.value = metaData.conversation_id
          // 更新用户消息的 conversation_id
          if (messages.value.length > 0) {
            const lastMsg = messages.value[messages.value.length - 1]
            if (lastMsg.role === 'user' && lastMsg.id.startsWith('temp-')) {
              lastMsg.conversation_id = metaData.conversation_id
            }
          }
          // 对话创建成功，后续消息将关联到此对话
        }
        break
      }
      case 'token': {
        streamingContent.value += event.data as string
        break
      }
      case 'citations': {
        streamingCitations.value = event.data as CitationItem[]
        break
      }
      case 'done': {
        // 流式完成，将当前内容保存为最终消息
        if (streamingContent.value) {
          const doneData = event.data as { conversation_id: string }
          const assistantMessage: ChatMessage = {
            id: `msg-${Date.now()}`,
            conversation_id: doneData.conversation_id || currentConversationId.value || '',
            role: 'assistant',
            content: streamingContent.value,
            citations: streamingCitations.value,
            created_at: new Date().toISOString()}
          messages.value = [...messages.value, assistantMessage]
          streamingContent.value = ''
          streamingCitations.value = null
        }
        break
      }
      case 'error': {
        const errData = event.data as { message: string }
        throw new Error(errData.message || '服务器返回错误')
      }
    }
  }

  return {
    // 状态
    agent,
    currentConversationId,
    messages,
    isLoading,
    isStreaming,
    streamingContent,
    streamingCitations,
    // 计算
    isLoggedIn,
    // 方法
    fetchDefaultAgent,
    sendMessage,
    stopStreaming,
    resetChatState}
})
