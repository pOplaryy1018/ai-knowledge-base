<script setup lang="ts">
import { ref, watch, onMounted, onUnmounted } from 'vue'
import { IconLeft, IconClose, IconCopy, IconDownload } from '@arco-design/web-vue/es/icon'
import { Message } from '@arco-design/web-vue'
import { previewFile, getRawFileUrl } from '@/api/import'
import type { KnowledgeFile, KnowledgeFilePreview } from '@akb/shared'
import MarkdownIt from 'markdown-it'
import hljs from 'highlight.js'
import 'highlight.js/styles/github-dark.css'

const props = defineProps<{ visible: boolean; file: KnowledgeFile | null }>()
const emit = defineEmits<{ close: [] }>()

const loading = ref(false)
const error = ref('')
const preview = ref<KnowledgeFilePreview | null>(null)
const copied = ref(false)

const md = new MarkdownIt({
  html: false, linkify: true, breaks: true,
  highlight(str, lang) {
    if (lang && hljs.getLanguage(lang)) {
      try { return hljs.highlight(str, { language: lang, ignoreIllegals: true }).value }
      catch { /* fall through */ }
    }
    return hljs.highlightAuto(str).value
  },
})

const codeExts = ['py', 'ts', 'tsx', 'js', 'jsx', 'java', 'go', 'rs', 'c', 'cpp', 'h']

function renderContent(content: string, fileType: string): string {
  if (fileType === 'md' || fileType === 'markdown') {
    return md.render(content)
  }
  if (codeExts.includes(fileType)) {
    const lang = fileType === 'py' ? 'python' : fileType === 'ts' ? 'typescript' : fileType === 'js' ? 'javascript' : fileType
    try {
      return `<pre><code>${hljs.highlight(content, { language: lang }).value}</code></pre>`
    } catch {
      return `<pre><code>${escapeHtml(content)}</code></pre>`
    }
  }
  return `<pre><code>${escapeHtml(content)}</code></pre>`
}

function escapeHtml(text: string): string {
  return text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
}

function getRawUrl(): string {
  if (!props.file) return ''
  const token = localStorage.getItem('akb_access_token') || ''
  return getRawFileUrl(props.file.knowledge_base_id, props.file.id, token)
}

async function load() {
  if (!props.file) return
  loading.value = true
  error.value = ''
  preview.value = null
  try {
    preview.value = await previewFile(props.file.knowledge_base_id, props.file.id)
  } catch (e: any) {
    error.value = e?.response?.data?.detail || e?.message || '加载失败'
  } finally {
    loading.value = false
  }
}

async function handleCopy() {
  if (!preview.value?.content) return
  try {
    await navigator.clipboard.writeText(preview.value.content)
    copied.value = true
    Message.success('已复制到剪贴板')
    setTimeout(() => { copied.value = false }, 2000)
  } catch {
    Message.error('复制失败')
  }
}

function handleDownload() {
  const token = localStorage.getItem('akb_access_token') || ''
  if (props.file) {
    window.open(getRawFileUrl(props.file.knowledge_base_id, props.file.id, token), '_blank')
  }
}

function handleKeydown(e: KeyboardEvent) {
  if (e.key === 'Escape') emit('close')
}

function handleBackdropClick() {
  emit('close')
}

watch(() => props.visible, (v) => {
  if (v) load()
})

onMounted(() => document.addEventListener('keydown', handleKeydown))
onUnmounted(() => document.removeEventListener('keydown', handleKeydown))
</script>

<template>
  <Teleport to="body">
    <div
      v-if="visible"
      class="preview-overlay"
      @click.self="handleBackdropClick"
    >
      <!-- 顶部工具栏 -->
      <div class="preview-toolbar">
        <button
          class="toolbar-btn"
          @click="emit('close')"
        >
          <IconLeft :size="20" />
          <span>返回</span>
        </button>
        <span class="toolbar-filename">{{ file?.original_filename || '' }}</span>
        <div class="toolbar-actions">
          <button
            v-if="preview?.content"
            class="toolbar-btn"
            @click="handleCopy"
          >
            <IconCopy :size="16" />
            <span>{{ copied ? '已复制' : '复制' }}</span>
          </button>
          <button
            class="toolbar-btn"
            @click="handleDownload"
          >
            <IconDownload :size="16" />
            <span>下载</span>
          </button>
          <button
            class="toolbar-btn toolbar-btn-close"
            @click="emit('close')"
          >
            <IconClose :size="20" />
          </button>
        </div>
      </div>

      <!-- 内容区 -->
      <div class="preview-content">
        <!-- 加载中 -->
        <div
          v-if="loading"
          class="preview-center"
        >
          <a-spin :size="32" />
        </div>

        <!-- 错误 -->
        <div
          v-else-if="error"
          class="preview-center"
        >
          <p class="preview-error">
            {{ error }}
          </p>
          <a-button @click="load">
            重试
          </a-button>
        </div>

        <!-- 图片 -->
        <div
          v-else-if="preview?.content_type === 'image'"
          class="preview-image-wrapper"
        >
          <img
            :src="getRawUrl()"
            :alt="file?.original_filename"
            class="preview-image"
          >
        </div>

        <!-- 不支持 -->
        <div
          v-else-if="preview?.content_type === 'unsupported'"
          class="preview-center"
        >
          <p class="preview-hint">
            该文件类型不支持在线预览
          </p>
          <a-button
            type="primary"
            @click="handleDownload"
          >
            <template #icon>
              <IconDownload />
            </template>
            下载原文件
          </a-button>
        </div>

        <!-- 文本/代码 -->
        <div
          v-else
          class="preview-text-wrapper"
        >
          <div
            v-if="preview?.content"
            class="preview-text-content"
            :class="{ 'markdown-body': file?.file_type === 'md' || file?.file_type === 'markdown' }"
            v-html="renderContent(preview.content, file?.file_type || '')"
          />
          <div
            v-else
            class="preview-center"
          >
            <p class="preview-hint">
              文件内容为空
            </p>
          </div>
          <div
            v-if="preview && preview.total_chars > preview.preview_chars"
            class="preview-truncation"
          >
            预览仅展示前 {{ preview.preview_chars.toLocaleString() }} 字符 / 共 {{ preview.total_chars.toLocaleString() }} 字符
          </div>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.preview-overlay {
  position: fixed;
  inset: 0;
  z-index: 9999;
  display: flex;
  flex-direction: column;
  background: rgba(0, 0, 0, 0.92);
}

/* ── 工具栏 ── */
.preview-toolbar {
  height: 56px;
  padding: 0 16px;
  display: flex;
  align-items: center;
  gap: 16px;
  background: rgba(30, 30, 30, 0.95);
  border-bottom: 1px solid rgba(255, 255, 255, 0.08);
  flex-shrink: 0;
}

.toolbar-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  background: none;
  border: none;
  color: #ccc;
  font-size: 14px;
  cursor: pointer;
  padding: 6px 12px;
  border-radius: 6px;
  transition: all 0.15s;
}

.toolbar-btn:hover {
  color: #fff;
  background: rgba(255, 255, 255, 0.1);
}

.toolbar-btn-close {
  padding: 6px;
  margin-left: 8px;
}

.toolbar-filename {
  flex: 1;
  color: #e0e0e0;
  font-size: 14px;
  font-weight: 500;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.toolbar-actions {
  display: flex;
  align-items: center;
  gap: 4px;
}

/* ── 内容区 ── */
.preview-content {
  flex: 1;
  overflow: auto;
  display: flex;
}

.preview-center {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 16px;
  padding: 40px;
}

.preview-error {
  color: #e57373;
  font-size: 16px;
  margin: 0;
}

.preview-hint {
  color: #9e9e9e;
  font-size: 16px;
  margin: 0;
}

/* ── 图片 ── */
.preview-image-wrapper {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
}

.preview-image {
  max-width: 100%;
  max-height: calc(100vh - 104px);
  object-fit: contain;
}

/* ── 文本/代码 ── */
.preview-text-wrapper {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 32px 16px 16px;
  overflow: auto;
}

.preview-text-content {
  width: 100%;
  max-width: 900px;
  background: #1e1e1e;
  border-radius: 8px;
  padding: 24px 32px;
  overflow: auto;
  color: #d4d4d4;
  font-size: 14px;
  line-height: 1.7;
}

.preview-text-content :deep(pre) {
  margin: 0;
  white-space: pre-wrap;
  word-break: break-word;
  font-family: 'SFMono-Regular', 'Fira Code', 'Consolas', monospace;
  font-size: 13.5px;
}

.preview-text-content :deep(code) {
  font-family: 'SFMono-Regular', 'Fira Code', 'Consolas', monospace;
}

.preview-text-content.markdown-body :deep(h1),
.preview-text-content.markdown-body :deep(h2),
.preview-text-content.markdown-body :deep(h3) {
  color: #e0e0e0;
  margin: 16px 0 8px;
}

.preview-text-content.markdown-body :deep(p) {
  margin: 8px 0;
  color: #d4d4d4;
}

.preview-text-content.markdown-body :deep(ul),
.preview-text-content.markdown-body :deep(ol) {
  padding-left: 24px;
  color: #d4d4d4;
}

.preview-text-content.markdown-body :deep(blockquote) {
  border-left: 3px solid #555;
  padding-left: 12px;
  color: #999;
  margin: 8px 0;
}

.preview-text-content.markdown-body :deep(code) {
  background: #2d2d2d;
  padding: 2px 6px;
  border-radius: 3px;
  font-size: 13px;
}

.preview-text-content.markdown-body :deep(pre code) {
  background: none;
  padding: 0;
}

.preview-text-content.markdown-body :deep(table) {
  border-collapse: collapse;
  width: 100%;
}

.preview-text-content.markdown-body :deep(th),
.preview-text-content.markdown-body :deep(td) {
  border: 1px solid #444;
  padding: 6px 12px;
}

/* ── 截断提示 ── */
.preview-truncation {
  max-width: 900px;
  width: 100%;
  margin-top: 12px;
  padding: 10px 16px;
  background: rgba(255, 193, 7, 0.1);
  border: 1px solid rgba(255, 193, 7, 0.3);
  border-radius: 6px;
  color: #ffc107;
  font-size: 13px;
  text-align: center;
}
</style>
