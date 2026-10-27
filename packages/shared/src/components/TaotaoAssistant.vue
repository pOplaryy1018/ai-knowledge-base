<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, reactive, ref, watch } from 'vue'
import type { Source, SourceCitation } from '../types/source'
import { buildAssistantScope, scopeChanged } from '../utils/assistant-scope'

type StreamEvent =
  | { type: 'meta'; data: { conversation_id: string } }
  | { type: 'token'; data: { content: string } }
  | { type: 'citations'; data: SourceCitation[] }
  | { type: 'done'; data: { conversation_id: string; message_id: string } }
  | { type: 'warning' | 'progress' | 'error'; data: { message: string } }
  | { type: 'comparison'; data: unknown }

interface Reply {
  question: string
  content: string
  citations: SourceCitation[]
  warning: string
  done: boolean
}

const props = defineProps<{
  generation: number
  getSources: (signal?: AbortSignal) => Promise<Source[]>
  ask: (question: string, sourceIds: string[], conversationId?: string, signal?: AbortSignal) => AsyncIterable<StreamEvent>
  openOriginal: (citation: SourceCitation) => Promise<void>
  sourcesPath: string
  sourcesLabel: string
}>()

const open = ref(false)
const assetReady = ref(false)
const loadingSources = ref(false)
const sourcesLoaded = ref(false)
const sourcesError = ref('')
const sources = ref<Source[]>([])
const selectedIds = ref<string[]>([])
const selecting = ref(false)
const question = ref('')
const inputRef = ref<HTMLInputElement | null>(null)
const replies = ref<Reply[]>([])
const conversationId = ref<string>()
const streaming = ref(false)
const progress = ref('')
const error = ref('')
let listController: AbortController | undefined
let streamController: AbortController | undefined

const scope = computed(() => buildAssistantScope(sources.value, selectedIds.value))
const canSend = computed(() => Boolean(question.value.trim() && selectedIds.value.length && !streaming.value && !loadingSources.value))
const scopeLabel = computed(() => {
  if (!scope.value.available.length) return '暂无已发布资料'
  if (!selectedIds.value.length) return '请先选择资料范围'
  if (selectedIds.value.length === scope.value.available.length) return `全部可访问资料 · ${selectedIds.value.length} 份`
  return `已选择 ${selectedIds.value.length} 份资料`
})

function resetConversation() {
  streamController?.abort()
  streamController = undefined
  replies.value = []
  conversationId.value = undefined
  streaming.value = false
  progress.value = ''
  error.value = ''
}

function resetIdentity() {
  listController?.abort()
  resetConversation()
  sources.value = []
  selectedIds.value = []
  question.value = ''
  open.value = false
  selecting.value = false
  loadingSources.value = false
  sourcesError.value = ''
  sourcesLoaded.value = false
}

async function showAssistant() {
  open.value = true
  void loadSources()
  await nextTick()
  inputRef.value?.focus()
}

async function loadSources() {
  listController?.abort()
  const controller = new AbortController()
  listController = controller
  loadingSources.value = true
  sourcesError.value = ''
  try {
    const next = await props.getSources(controller.signal)
    if (controller.signal.aborted) return
    const previousAvailable = buildAssistantScope(sources.value).available
    const wasAllSelected = sourcesLoaded.value && previousAvailable.length > 0
      && selectedIds.value.length === previousAvailable.length
    const nextScope = buildAssistantScope(next, sourcesLoaded.value && !wasAllSelected ? selectedIds.value : undefined)
    const revisionChanged = selectedIds.value.some(id => {
      const before = sources.value.find(source => source.id === id)?.current_revision_id
      const after = nextScope.available.find(source => source.id === id)?.current_revision_id
      return before !== after
    })
    if (sourcesLoaded.value && (scopeChanged(selectedIds.value, nextScope.selectedIds) || revisionChanged)) resetConversation()
    sources.value = nextScope.available
    selectedIds.value = nextScope.selectedIds
    sourcesLoaded.value = true
  } catch (caught) {
    if (!controller.signal.aborted) sourcesError.value = caught instanceof Error ? caught.message : '资料加载失败，请重试'
  } finally {
    if (listController === controller) loadingSources.value = false
  }
}

function toggleSource(id: string) {
  const next = selectedIds.value.includes(id) ? selectedIds.value.filter(item => item !== id) : [...selectedIds.value, id]
  if (next.length > 100) {
    error.value = '一次最多选择 100 份资料'
    return
  }
  if (scopeChanged(selectedIds.value, next)) resetConversation()
  selectedIds.value = next
}

function sourceName(id: string) { return sources.value.find(item => item.id === id)?.name || '资料来源' }
function locatorLabel(locator: Record<string, unknown>) {
  const parts: string[] = []
  if (typeof locator.logical_path === 'string') parts.push(locator.logical_path)
  if (locator.page != null) parts.push(`第 ${locator.page} 页`)
  if (locator.paragraph != null) parts.push(`第 ${locator.paragraph} 段`)
  if (locator.line_start != null) parts.push(`第 ${locator.line_start} 行`)
  return parts.join(' · ') || '原文片段'
}

async function send() {
  if (!canSend.value) return
  const item = reactive<Reply>({ question: question.value.trim(), content: '', citations: [], warning: '', done: false })
  question.value = ''
  replies.value.push(item)
  const controller = new AbortController()
  streamController = controller
  streaming.value = true
  progress.value = '正在检索资料…'
  error.value = ''
  try {
    for await (const event of props.ask(item.question, [...selectedIds.value], conversationId.value, controller.signal)) {
      if (controller.signal.aborted || streamController !== controller) return
      if (event.type === 'meta') conversationId.value = event.data.conversation_id
      if (event.type === 'token') item.content += event.data.content
      if (event.type === 'citations') item.citations = event.data
      if (event.type === 'warning') item.warning = event.data.message
      if (event.type === 'progress') progress.value = event.data.message
      if (event.type === 'done') item.done = true
      if (event.type === 'error') throw new Error(event.data.message)
    }
    if (!item.done && !controller.signal.aborted) error.value = '回答未完成，请重试。'
  } catch (caught) {
    if (!controller.signal.aborted) error.value = caught instanceof Error ? caught.message : '问答失败，请重试'
  } finally {
    if (streamController === controller) {
      streaming.value = false
      progress.value = ''
      streamController = undefined
    }
  }
}

async function openCitation(citation: SourceCitation) {
  try { await props.openOriginal(citation) }
  catch (caught) { error.value = caught instanceof Error ? caught.message : '原件打开失败' }
}

function onKeydown(event: KeyboardEvent) {
  if (event.key === 'Escape' && open.value) {
    open.value = false
    selecting.value = false
  }
}

watch(() => props.generation, resetIdentity)
onMounted(() => {
  const image = new Image()
  image.onload = () => { assetReady.value = true }
  image.src = '/local-theme/taotao-q.png'
  void loadSources()
  document.addEventListener('keydown', onKeydown)
})
onUnmounted(() => {
  listController?.abort()
  streamController?.abort()
  document.removeEventListener('keydown', onKeydown)
})
</script>

<template>
  <div class="taotao-root">
    <button
      v-if="!open"
      type="button"
      class="taotao-trigger"
      aria-label="打开韬韬知识助手"
      @click="showAssistant"
    >
      <span
        v-if="assetReady"
        class="taotao-sprite"
        aria-hidden="true"
      />
      <span
        v-else
        class="taotao-fallback"
        aria-hidden="true"
      >韬</span>
      <span class="taotao-trigger-label">ASK / 韬韬 ↗</span>
    </button>
    <section
      v-else
      class="taotao-panel"
      role="dialog"
      aria-label="韬韬知识助手"
      aria-modal="false"
    >
      <header class="taotao-header">
        <span
          v-if="assetReady"
          class="taotao-sprite small"
          aria-hidden="true"
        />
        <span
          v-else
          class="taotao-fallback small"
          aria-hidden="true"
        >韬</span>
        <span><strong>韬韬 · 知识助手</strong><small>TRACEABLE / KNOWLEDGE CHAT</small></span>
        <button
          type="button"
          class="taotao-close"
          aria-label="收起韬韬助手"
          @click="open = false; selecting = false"
        >
          ×
        </button>
      </header>
      <div class="taotao-scope">
        <span>{{ scopeLabel }}</span>
        <button
          type="button"
          :aria-expanded="selecting"
          @click="selecting = !selecting"
        >
          更改范围 ▾
        </button>
      </div>
      <div
        v-if="selecting"
        class="taotao-source-list"
        aria-label="选择资料范围"
      >
        <p>更改范围会开启新对话。最多选择 100 份已发布资料。</p>
        <label
          v-for="source in scope.available"
          :key="source.id"
        ><input
          type="checkbox"
          :checked="selectedIds.includes(source.id)"
          @change="toggleSource(source.id)"
        >{{ source.name }}</label>
        <p v-if="!scope.available.length">
          没有可选择的已发布资料。
        </p>
      </div>
      <div
        class="taotao-messages"
        aria-live="polite"
      >
        <div
          v-if="loadingSources"
          class="taotao-hint"
        >
          正在载入资料范围…
        </div>
        <div
          v-else-if="sourcesError"
          class="taotao-hint error"
        >
          {{ sourcesError }} <button
            type="button"
            @click="loadSources"
          >
            重试
          </button>
        </div>
        <div
          v-else-if="scope.requiresSelection"
          class="taotao-hint"
        >
          可访问资料超过 100 份，请先选择提问范围。
        </div>
        <div
          v-else-if="!scope.available.length"
          class="taotao-hint"
        >
          暂无已发布资料。<a :href="sourcesPath">{{ sourcesLabel }} ↗</a>
        </div>
        <div
          v-else-if="!replies.length"
          class="taotao-hint"
        >
          我在这里。选择资料后提问，回答会显示来源版本与原文位置。
        </div>
        <div
          v-for="(reply, index) in replies"
          :key="index"
          class="taotao-turn"
        >
          <div class="taotao-question">
            {{ reply.question }}
          </div>
          <div class="taotao-answer">
            {{ reply.content || (streaming ? '正在整理依据…' : '暂无回答内容') }}
          </div>
          <div
            v-if="reply.warning"
            class="taotao-warning"
          >
            {{ reply.warning }}
          </div>
          <div
            v-if="reply.done && !reply.citations.length && !reply.warning"
            class="taotao-no-evidence"
          >
            此回答没有可核验的原文引用，请谨慎使用。
          </div>
          <button
            v-for="citation in reply.citations"
            :key="`${citation.source_id}-${citation.revision_id}-${citation.index}`"
            type="button"
            class="taotao-citation"
            @click="openCitation(citation)"
          >
            ↗ {{ sourceName(citation.source_id) }} · 版本 {{ citation.revision_id.slice(0, 8) }} · {{ locatorLabel(citation.locator) }}
            <small>{{ citation.content }}</small>
          </button>
        </div>
      </div>
      <div
        v-if="progress && streaming"
        class="taotao-progress"
      >
        {{ progress }}
      </div>
      <div
        v-if="error"
        class="taotao-error"
        role="alert"
      >
        {{ error }}
      </div>
      <form
        class="taotao-compose"
        @submit.prevent="send"
      >
        <input
          ref="inputRef"
          v-model="question"
          aria-label="向韬韬提问"
          :disabled="!selectedIds.length || streaming"
          placeholder="问问知识库里的资料……"
        >
        <button
          type="submit"
          :disabled="!canSend"
        >
          发送 ↗
        </button>
        <small>仅查询有权限的已发布资料 · 普通聊天不会自动保存答案</small>
      </form>
    </section>
  </div>
</template>

<style scoped>
.taotao-root { position: fixed; right: 22px; bottom: 20px; z-index: 900; font-family: Inter, "Noto Sans SC", sans-serif; }
.taotao-trigger { display: flex; flex-direction: column; align-items: center; width: 118px; min-height: 139px; padding: 0; border: 0; background: transparent; filter: drop-shadow(0 12px 14px #000a); }
.taotao-sprite { display: block; flex: none; width: 112px; height: 121px; background: url('/local-theme/taotao-q.png') 0 0 / 800% 1100% no-repeat; }
.taotao-sprite.small { width: 50px; height: 54px; }
.taotao-fallback { display: grid; place-items: center; flex: none; width: 92px; height: 92px; border: 2px solid #c5a8ee; border-radius: 22px 22px 18px 18px; background: linear-gradient(140deg, #573f68, #21182d); color: #f7f0ff; font-size: 39px; font-weight: 900; }
.taotao-fallback.small { width: 45px; height: 45px; border-radius: 9px; font-size: 19px; }
.taotao-trigger-label { margin-top: -2px; padding: 5px 10px; background: var(--akb-primary); color: #24162e; font: 10px Consolas, monospace; transform: skew(-8deg); }
.taotao-panel { width: min(420px, calc(100vw - 28px)); height: min(620px, calc(100vh - 40px)); display: flex; flex-direction: column; background: #1b1524; border: 1px solid #a17fbd; box-shadow: 0 18px 60px #000b; color: var(--akb-text); }
.taotao-header { display: flex; align-items: center; gap: 10px; flex: none; min-height: 70px; padding: 8px 14px; background: #2a1e37; border-bottom: 1px solid #685175; }
.taotao-header strong { font-size: 14px; }.taotao-header small { display: block; margin-top: 5px; color: #bec0c8; font: 9px Consolas, monospace; }
.taotao-close { margin-left: auto; width: 33px; height: 33px; border: 1px solid #6b557d; background: #1d1727; color: var(--akb-text); font-size: 21px; }
.taotao-scope { display: flex; justify-content: space-between; align-items: center; gap: 8px; min-height: 43px; padding: 7px 13px; border-bottom: 1px solid #51435e; color: var(--akb-text-secondary); font-size: 11px; }
.taotao-scope button { flex: none; border: 1px solid #72598a; padding: 5px 8px; background: #31233e; color: #e5d9ef; font-size: 10px; }
.taotao-source-list { max-height: 170px; overflow: auto; flex: none; padding: 8px 13px; background: #261c31; border-bottom: 1px solid #5b496a; }
.taotao-source-list p { margin: 3px 0 9px; font-size: 10px; color: #b8bac2; }.taotao-source-list label { display: flex; align-items: center; gap: 8px; padding: 6px 0; font-size: 11px; color: #e9e7ed; }
.taotao-source-list input { accent-color: var(--akb-primary); }
.taotao-messages { min-height: 0; flex: 1; overflow: auto; padding: 16px 13px; }
.taotao-hint { border: 1px solid #5b486c; padding: 12px; background: #2a2035; color: #e6e3eb; font-size: 12px; line-height: 1.7; }.taotao-hint a { display: block; margin-top: 8px; }
.taotao-hint.error { border-color: #a45c6c; }.taotao-hint button { border: 0; background: transparent; color: var(--akb-primary); }
.taotao-turn { margin-bottom: 16px; }.taotao-question { margin-left: 16%; margin-bottom: 9px; padding: 10px; background: #533d67; color: #f7f5fa; font-size: 12px; line-height: 1.6; }.taotao-answer { border: 1px solid #584668; padding: 11px; background: #2a2035; color: #f1eff4; font-size: 12px; line-height: 1.7; white-space: pre-wrap; overflow-wrap: anywhere; }
.taotao-warning, .taotao-no-evidence { margin-top: 7px; color: #efc18c; font-size: 11px; line-height: 1.6; }
.taotao-citation { display: block; width: 100%; margin-top: 8px; border: 1px solid #675277; padding: 8px 9px; text-align: left; background: #30243d; color: #e4d4f0; font-size: 10px; line-height: 1.5; }.taotao-citation small { display: block; margin-top: 5px; color: #c1c2c9; white-space: pre-wrap; overflow-wrap: anywhere; }
.taotao-progress, .taotao-error { padding: 5px 12px; color: #d6c1e9; font-size: 10px; }.taotao-error { color: #f3a4b4; }
.taotao-compose { flex: none; display: flex; flex-wrap: wrap; gap: 7px; padding: 11px; border-top: 1px solid #5b4968; background: #221a2c; }.taotao-compose input { min-width: 0; flex: 1; border: 1px solid #715a81; background: #120e19; padding: 9px 10px; color: #f3f3f5; font-size: 12px; }.taotao-compose button { border: 0; padding: 9px 12px; background: var(--akb-primary); color: #25192e; font-weight: 800; }.taotao-compose button:disabled { opacity: .55; cursor: not-allowed; }.taotao-compose small { width: 100%; color: #aaaeb7; font-size: 10px; }
@media (max-width: 640px) { .taotao-root { right: 8px; bottom: 8px; }.taotao-panel { width: 100vw; height: min(680px, 92vh); border-left: 0; border-right: 0; }.taotao-root:has(.taotao-panel) { right: 0; bottom: 0; } }
</style>
