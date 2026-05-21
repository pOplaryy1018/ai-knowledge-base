<script setup lang="ts">
/**
 * AI 问答界面 ── 全屏简洁版
 * 自动获取唯一 Agent，支持 SSE 流式输出、Markdown 渲染、引用标注
 */

import { ref, watch, nextTick, onMounted, computed } from 'vue'
import { Message } from '@arco-design/web-vue'
import { useChatStore } from '@/stores/chat'
import MarkdownIt from 'markdown-it'
import hljs from 'highlight.js'
import 'highlight.js/styles/github.css'
import type { ChatMessage } from '@akb/shared'

const store = useChatStore()

// ── Markdown 渲染器 ──
const md = new MarkdownIt({
  html: false,
  linkify: true,
  breaks: true,
  highlight(str, lang) {
    if (lang && hljs.getLanguage(lang)) {
      try {
        return `<pre class="hljs"><code>${hljs.highlight(str, { language: lang, ignoreIllegals: true }).value}</code></pre>`
      } catch {
        // 高亮失败，使用自动检测
      }
    }
    return `<pre class="hljs"><code>${hljs.highlightAuto(str).value}</code></pre>`
  }})

function renderMarkdown(content: string): string {
  let html = md.render(content)
  html = html.replace(/\[(\d+)\]/g, (_match, num) => {
    return `<sup class="citation-tag" data-citation-index="${num}">[${num}]</sup>`
  })
  return html
}

// ── 本地状态 ──
const inputText = ref('')
const messagesContainer = ref<HTMLElement | null>(null)
const inputTextarea = ref<HTMLTextAreaElement | null>(null)
const expandedCitations = ref<Set<number>>(new Set())

// ── 生成中的消息列表（包含流式内容） ──
const displayMessages = computed(() => {
  if (!store.isStreaming || !store.streamingContent) {
    return store.messages
  }
  const streamMsg: ChatMessage = {
    id: 'streaming',
    conversation_id: store.currentConversationId || '',
    role: 'assistant',
    content: store.streamingContent,
    citations: store.streamingCitations,
    created_at: new Date().toISOString()}
  return [...store.messages, streamMsg]
})

// ── 滚动到底部 ──
async function scrollToBottom() {
  await nextTick()
  if (messagesContainer.value) {
    messagesContainer.value.scrollTo({
      top: messagesContainer.value.scrollHeight,
      behavior: 'smooth'})
  }
}

watch(
  () => [store.messages.length, store.streamingContent],
  () => { scrollToBottom() },
  { deep: false },
)

// ── 引用相关 ──
function toggleCitation(index: number) {
  const newSet = new Set(expandedCitations.value)
  if (newSet.has(index)) {
    newSet.delete(index)
  } else {
    newSet.add(index)
  }
  expandedCitations.value = newSet
}

// ── 消息发送 ──
async function handleSend() {
  const text = inputText.value.trim()
  if (!text || store.isStreaming || !store.agent) return

  inputText.value = ''
  if (inputTextarea.value) {
    inputTextarea.value.style.height = 'auto'
  }
  await store.sendMessage(store.agent.id, text)
}

function handleKeydown(e: KeyboardEvent) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    handleSend()
  }
}

function handleInput() {
  if (inputTextarea.value) {
    inputTextarea.value.style.height = 'auto'
    inputTextarea.value.style.height = Math.min(inputTextarea.value.scrollHeight, 150) + 'px'
  }
}

function handleStop() {
  store.stopStreaming()
}

function handleCitationClick(e: MouseEvent) {
  const target = e.target as HTMLElement
  if (target.classList.contains('citation-tag')) {
    const index = parseInt(target.dataset.citationIndex || '0')
    if (index > 0) {
      toggleCitation(index)
    }
  }
}

// ── 格式化时间 ──
function formatTime(dateStr: string): string {
  const date = new Date(dateStr)
  const now = new Date()
  const diff = now.getTime() - date.getTime()

  if (diff < 60000) return '刚刚'
  if (diff < 3600000) return `${Math.floor(diff / 60000)} 分钟前`
  if (diff < 86400000) return `${Math.floor(diff / 3600000)} 小时前`

  return date.toLocaleDateString('zh-CN', {
    month: 'short',
    day: 'numeric'})
}

// ── 生命周期 ──
onMounted(async () => {
  store.resetChatState()
  try {
    const agent = await store.fetchDefaultAgent()
    if (!agent) {
      Message.warning('暂无可用的 AI 助手，请联系管理员配置')
    }
  } catch {
    Message.error('加载 AI 助手失败')
  }
})
</script>

<template>
  <div class="chat-fullpage">
    <header class="chat-topbar">
      <h3>{{ store.agent?.name || 'AI 问答' }}</h3>
      <span
        v-if="store.isStreaming"
        class="streaming-indicator"
      >
        <span class="typing-dot" />
        正在生成...
      </span>
    </header>

    <div
      ref="messagesContainer"
      class="messages-container"
      @click="handleCitationClick"
    >
      <!-- 加载中骨架 -->
      <div
        v-if="store.isLoading && store.messages.length === 0"
        class="loading-placeholder"
      >
        <div
          v-for="i in 4"
          :key="i"
          class="skeleton-line"
          :style="{ width: (80 - i * 15) + '%' }"
        />
      </div>

      <!-- 空状态引导 -->
      <div
        v-else-if="!store.isLoading && store.messages.length === 0 && !store.isStreaming"
        class="empty-state"
      >
        <p class="empty-text">
          向 AI 助手提问，基于您的知识库获取答案
        </p>
      </div>

      <!-- 消息列表 -->
      <template v-else>
        <div
          v-for="msg in displayMessages"
          :key="msg.id"
          :class="['message-wrapper', msg.role]"
        >
          <!-- 用户消息 -->
          <div
            v-if="msg.role === 'user'"
            class="message-bubble user-bubble"
          >
            <div class="message-content">
              {{ msg.content }}
            </div>
            <div class="message-time">
              {{ formatTime(msg.created_at) }}
            </div>
          </div>

          <!-- AI 消息 -->
          <div
            v-else
            class="message-bubble ai-bubble"
          >
            <div
              class="message-content markdown-body"
              v-html="renderMarkdown(msg.content)"
            />

            <!-- 引用标注列表 -->
            <div
              v-if="msg.citations && msg.citations.length > 0"
              class="citations-list"
            >
              <div
                v-for="cit in msg.citations"
                :key="cit.index"
                :class="['citation-card', { expanded: expandedCitations.has(cit.index) }]"
                @click="toggleCitation(cit.index)"
              >
                <div class="citation-header">
                  <span class="citation-index">[{{ cit.index }}]</span>
                  <span class="citation-title">{{ cit.knowledge_title }}</span>
                  <span class="citation-score">{{ (cit.score * 100).toFixed(1) }}%</span>
                </div>
                <div
                  v-if="expandedCitations.has(cit.index)"
                  class="citation-detail"
                >
                  <p class="citation-content">
                    {{ cit.content }}
                  </p>
                </div>
              </div>
            </div>

            <div class="message-time">
              {{ msg.id !== 'streaming' ? formatTime(msg.created_at) : '' }}
            </div>
          </div>
        </div>
      </template>
    </div>

    <div class="chat-input-area">
      <div class="input-wrapper">
        <textarea
          ref="inputTextarea"
          v-model="inputText"
          class="input-textarea"
          placeholder="输入您的问题，按 Enter 发送，Shift+Enter 换行"
          :disabled="store.isStreaming"
          rows="1"
          @keydown="handleKeydown"
          @input="handleInput"
        />

        <a-button
          v-if="!store.isStreaming"
          type="primary"
          class="send-btn"
          :disabled="!inputText.trim()"
          @click="handleSend"
        >
          发送
        </a-button>
        <a-button
          v-else
          status="danger"
          class="send-btn"
          @click="handleStop"
        >
          停止
        </a-button>
      </div>
    </div>
  </div>
</template>

<style scoped>
/* ── 全屏布局 ── */
.chat-fullpage {
  height: 100%;
  display: flex;
  flex-direction: column;
  background: var(--color-bg);
  overflow: hidden;
}

/* ── 顶部栏 ── */
.chat-topbar {
  height: 56px;
  padding: 0 24px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  background: var(--color-bg-card);
  border-bottom: 1px solid var(--border-color);
  flex-shrink: 0;
}

.chat-topbar h3 {
  font-size: 16px;
  font-weight: 500;
  color: var(--color-text-primary);
  margin: 0;
}

.streaming-indicator {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  color: var(--color-primary);
}

.typing-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--color-primary);
  animation: typing-pulse 1s infinite;
}

@keyframes typing-pulse {
  0%, 100% { opacity: 0.4; }
  50% { opacity: 1; }
}

/* ── 消息列表 ── */
.messages-container {
  flex: 1;
  overflow-y: auto;
  padding: 24px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.message-wrapper {
  display: flex;
  max-width: 100%;
}

.message-wrapper.user {
  justify-content: flex-end;
}

.message-wrapper.assistant {
  justify-content: flex-start;
}

/* 消息气泡 */
.message-bubble {
  max-width: 80%;
  padding: 12px 16px;
  border-radius: 12px;
  font-size: 14px;
  line-height: 1.6;
  position: relative;
}

.user-bubble {
  background: var(--color-bg-card);
  color: var(--color-text-primary);
  border-bottom-right-radius: 4px;
}

.ai-bubble {
  background: var(--color-primary-light);
  color: var(--color-text-primary);
  border-bottom-left-radius: 4px;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.06);
  border: 1px solid var(--border-color);
}

.message-content {
  word-break: break-word;
}

/* Markdown 内容样式 */
.markdown-body :deep(p) {
  margin: 0 0 8px;
}

.markdown-body :deep(p:last-child) {
  margin-bottom: 0;
}

.markdown-body :deep(pre) {
  background: var(--color-bg-card-alt);
  border-radius: 6px;
  padding: 12px 16px;
  overflow-x: auto;
  margin: 8px 0;
  font-size: 13px;
}

.markdown-body :deep(code) {
  font-family: 'SFMono-Regular', Consolas, 'Liberation Mono', Menlo, monospace;
  font-size: 13px;
  background: var(--color-bg-card-alt);
  padding: 2px 4px;
  border-radius: 3px;
}

.markdown-body :deep(pre code) {
  background: none;
  padding: 0;
}

.markdown-body :deep(ul),
.markdown-body :deep(ol) {
  padding-left: 20px;
  margin: 4px 0;
}

.markdown-body :deep(blockquote) {
  border-left: 3px solid var(--color-primary);
  margin: 8px 0;
  padding: 4px 12px;
  color: var(--color-text-secondary);
  background: var(--color-bg-card-alt);
}

.markdown-body :deep(table) {
  border-collapse: collapse;
  width: 100%;
  margin: 8px 0;
}

.markdown-body :deep(th),
.markdown-body :deep(td) {
  border: 1px solid var(--border-color);
  padding: 6px 12px;
  text-align: left;
}

.markdown-body :deep(th) {
  background: var(--color-bg-card-alt);
  font-weight: 500;
}

/* 引用标注 */
:deep(.citation-tag) {
  color: var(--color-primary);
  font-weight: 600;
  cursor: pointer;
  font-size: 12px;
  padding: 0 1px;
  vertical-align: super;
}

:deep(.citation-tag:hover) {
  text-decoration: underline;
  color: var(--color-primary-hover);
}

/* 引用卡片列表 */
.citations-list {
  margin-top: 12px;
  border-top: 1px solid var(--color-bg-card-alt);
  padding-top: 8px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.citation-card {
  background: var(--color-bg-card-alt);
  border-radius: 6px;
  padding: 8px 10px;
  cursor: pointer;
  transition: background 0.15s;
}

.citation-card:hover {
  background: var(--color-bg-card-alt);
}

.citation-card.expanded {
  background: var(--color-primary-light);
  border: 1px solid var(--border-color);
}

.citation-header {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
}

.citation-index {
  color: var(--color-primary);
  font-weight: 600;
  font-size: 12px;
  flex-shrink: 0;
}

.citation-title {
  color: var(--color-text-primary);
  font-weight: 500;
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.citation-score {
  color: var(--color-text-tertiary);
  font-size: 12px;
  flex-shrink: 0;
}

.citation-detail {
  margin-top: 8px;
  padding-top: 8px;
  border-top: 1px dashed var(--border-color);
}

.citation-content {
  font-size: 13px;
  color: var(--color-text-secondary);
  line-height: 1.6;
  margin: 0;
  white-space: pre-wrap;
  word-break: break-word;
}

/* 消息时间标记 */
.message-time {
  font-size: 11px;
  color: #bfbfbf;
  margin-top: 4px;
  text-align: right;
}

.user-bubble .message-time {
  color: rgba(255, 255, 255, 0.6);
}

/* ── 加载状态 ── */
.loading-placeholder {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 40px;
}

.skeleton-line {
  height: 16px;
  background: linear-gradient(90deg, var(--color-bg-card-alt) 25%, var(--border-color) 50%, var(--color-bg-card-alt) 75%);
  background-size: 200% 100%;
  animation: skeleton-loading 1.5s infinite;
  border-radius: 4px;
}

@keyframes skeleton-loading {
  0% { background-position: 200% 0; }
  100% { background-position: -200% 0; }
}

/* ── 空状态 ── */
.empty-state {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
}

.empty-text {
  font-size: 16px;
  color: var(--color-text-tertiary);
}

/* ── 输入区 ── */
.chat-input-area {
  padding: 16px 24px;
  background: var(--color-bg-card);
  border-top: 1px solid var(--border-color);
  flex-shrink: 0;
}

.input-wrapper {
  display: flex;
  align-items: flex-end;
  gap: 12px;
  background: var(--color-bg);
  border-radius: 12px;
  padding: 10px 14px;
  border: 1px solid var(--border-color);
  transition: border-color 0.2s;
}

.input-wrapper:focus-within {
  border-color: var(--color-primary);
}

.input-textarea {
  flex: 1;
  border: none;
  outline: none;
  background: transparent;
  font-size: 14px;
  line-height: 1.6;
  color: var(--color-text-primary);
  resize: none;
  min-height: 24px;
  max-height: 150px;
  font-family: inherit;
}

.input-textarea::placeholder {
  color: #bfbfbf;
}

.send-btn {
  flex-shrink: 0;
  height: 36px;
  min-width: 72px;
}
</style>
