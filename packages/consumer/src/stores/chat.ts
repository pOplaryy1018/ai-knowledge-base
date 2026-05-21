/**
 * 聊天状态管理 (Pinia Setup Store) ── 对话列表、消息流、SSE 流控制
 */

import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { Message } from '@arco-design/web-vue'
import type { ChatMessage, Agent, CitationItem } from '@akb/shared'
import { setupApiClient, getApiClient } from '@/api/client'
import { chatSSE } from '@/api/chat'
import type { SSEData } from '@/api/chat'
import router from '@/router'

const TOKEN_KEY = 'akb_access_token'
const REFRESH_KEY = 'akb_refresh_token'

export const useChatStore = defineStore('chat', () => {
  // ── Token 管理 ──
  const accessToken = ref<string | null>(localStorage.getItem(TOKEN_KEY))
  const refreshTokenValue = ref<string | null>(localStorage.getItem(REFRESH_KEY))

  // ── 注入 API 客户端依赖 ──
  setupApiClient({
    getToken: () => accessToken.value,
    onUnauthorized: () => {
      clearAuth()
      router.push('/login')
    },
    getRefreshToken: () => refreshTokenValue.value,
    onTokenRefreshed: (token: string) => {
      accessToken.value = token
      localStorage.setItem(TOKEN_KEY, token)
    }})

  function saveToken(access: string, refresh: string) {
    accessToken.value = access
    refreshTokenValue.value = refresh
    localStorage.setItem(TOKEN_KEY, access)
    localStorage.setItem(REFRESH_KEY, refresh)
    // 重置客户端以使用新 token
    setupApiClient({
      getToken: () => accessToken.value,
      onUnauthorized: () => {
        clearAuth()
        router.push('/login')
      },
      getRefreshToken: () => refreshTokenValue.value,
      onTokenRefreshed: (token: string) => {
        accessToken.value = token
        localStorage.setItem(TOKEN_KEY, token)
      }})
  }

  function clearAuth() {
    accessToken.value = null
    refreshTokenValue.value = null
    localStorage.removeItem(TOKEN_KEY)
    localStorage.removeItem(REFRESH_KEY)
  }

  // ── 状态 ──
  const agent = ref<Agent | null>(null)
  const currentConversationId = ref<string | null>(null)
  const messages = ref<ChatMessage[]>([])
  const isLoading = ref(false)
  const isStreaming = ref(false)
  const streamingContent = ref('')
  const streamingCitations = ref<CitationItem[] | null>(null)

  /** SSE 流控制器，用于手动停止生成 */
  let stopRequested = false

  // ── 计算属性 ──
  const isLoggedIn = computed(() => !!accessToken.value)

  // ── 状态清空 ──

  function resetChatState() {
    currentConversationId.value = null
    messages.value = []
    streamingContent.value = ''
    streamingCitations.value = null
    isStreaming.value = false
  }

  // ── Actions ──

  /** 获取第一个（唯一）Agent 并自动进入问答 */
  async function fetchDefaultAgent() {
    isLoading.value = true
    try {
      const { data } = await getApiClient().get<{ items: Agent[] }>('/agents', {
        params: { page: 1, size: 1 }})
      if (data.items && data.items.length > 0) {
        agent.value = data.items[0]
        return data.items[0]
      }
      return null
    } finally {
      isLoading.value = false
    }
  }

  /** 停止当前 SSE 流 */
  function stopStreaming() {
    stopRequested = true
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
    stopRequested = false

    try {
      for await (const event of chatSSE(
        agentId,
        content.trim(),
        currentConversationId.value || undefined,
        accessToken.value || '',
      )) {
        // 如果用户点击了停止，退出循环
        if (stopRequested) break

        handleSSEEvent(event)
      }
    } catch (err: any) {
      // AbortError 不视为错误
      if (err?.name !== 'AbortError') {
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
      isStreaming.value = false
      stopRequested = false
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
    accessToken,
    refreshTokenValue,
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
    saveToken,
    clearAuth,
    fetchDefaultAgent,
    sendMessage,
    stopStreaming,
    resetChatState}
})
