<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useUserStore } from '@/stores/user'
import type { Source, SourceCitation, SourceComparison, ScopedResponseMode } from '@akb/shared'
import { listSources, downloadOriginal } from '@/api/sources'
import { scopedChatSSE } from '@/api/scoped-chat'
import { saveAnswer } from '@/api/answers'
import {
  sourceSelectable,
  canSaveAnswer,
  errorMessage,
  formatLocator,
  versionLabel,
} from '@/utils/review-state'
import ComparisonCard from '@/components/ComparisonCard.vue'
import { canCompare } from '@/utils/comparison'
const mode = ref<ScopedResponseMode>('text')
const progress = ref('')
const canSend = computed(
  () =>
    !!question.value.trim() &&
    !streaming.value &&
    (mode.value === 'comparison' ? canCompare(scope.value) : !!scope.value.length),
)
const store = useUserStore()
const controller = new AbortController()
let streamController: AbortController | undefined
const sources = ref<Source[]>([]),
  scope = ref<string[]>([]),
  question = ref(''),
  conversation = ref<string>(),
  error = ref(''),
  streaming = ref(false)
const messages = ref<
  {
    question: string
    content: string
    citations: SourceCitation[]
    messageId?: string
    saved?: boolean
    comparison?: SourceComparison
    warning?: string
  }[]
>([])
watch(scope, () => {
  streamController?.abort()
  messages.value = []
  conversation.value = undefined
  streaming.value = false
})
watch(
  () => store.generation,
  () => {
    streamController?.abort()
    controller.abort()
    scope.value = []
    sources.value = []
    messages.value = []
    conversation.value = undefined
  },
)
async function send() {
  if (!canSend.value) return
  streamController = new AbortController()
  const signal = streamController.signal
  const item: (typeof messages.value)[number] = {
    question: question.value.trim(),
    content: '',
    citations: [] as SourceCitation[],
    messageId: undefined as string | undefined,
  }
  messages.value.push(item)
  const current = messages.value[messages.value.length - 1]
  question.value = ''
  streaming.value = true
  error.value = ''
  progress.value = mode.value === 'comparison' ? '正在生成资料对比…' : ''
  try {
    for await (const event of scopedChatSSE(
      current.question,
      [...scope.value],
      conversation.value,
      signal,
      mode.value,
    )) {
      if (signal.aborted || streamController?.signal !== signal) break
      if (event.type === 'comparison') current.comparison = event.data
      if (event.type === 'warning') current.warning = event.data.message
      if (event.type === 'progress') progress.value = event.data.message
      if (event.type === 'meta') conversation.value = event.data.conversation_id
      if (event.type === 'token') current.content += event.data.content
      if (event.type === 'citations') current.citations = event.data
      if (event.type === 'done') current.messageId = event.data.message_id
      if (event.type === 'error') throw new Error(event.data.message)
    }
    if (!current.messageId && !signal.aborted) error.value = '回答未完成，不能保存，请重试。'
  } catch (e) {
    if (!signal.aborted) error.value = errorMessage(e)
  } finally {
    if (streamController?.signal === signal) {
      streaming.value = false
      progress.value = ''
    }
  }
}
async function save(item: (typeof messages.value)[number]) {
  if (!canSaveAnswer(item)) return
  try {
    await saveAnswer(item.messageId!, controller.signal)
    item.saved = true
  } catch (e) {
    if (!controller.signal.aborted) error.value = errorMessage(e)
  }
}
async function original(citation: SourceCitation) {
  try {
    await downloadOriginal(citation.source_id, citation.revision_id, '原件', controller.signal)
  } catch (e) {
    error.value = errorMessage(e)
  }
}
onMounted(async () => {
  try {
    sources.value = (await listSources(controller.signal)).filter(sourceSelectable)
  } catch (e) {
    if (!controller.signal.aborted) error.value = errorMessage(e)
  }
})
onUnmounted(() => {
  controller.abort()
  streamController?.abort()
})
</script>
<template>
  <a-space
    direction="vertical"
    fill
  >
    <h2>个人资料问答</h2>
    <a-alert>仅查询所选已发布来源。改变来源会开启新对话并清空当前记录。</a-alert><a-alert
      v-if="error"
      type="error"
    >
      {{ error }}
    </a-alert><a-select
      v-model="scope"
      multiple
      placeholder="选择问题来源"
      :disabled="streaming"
    >
      <a-option
        v-for="source in sources"
        :key="source.id"
        :value="source.id"
      >
        {{ source.name }}
      </a-option>
    </a-select>
    <a-radio-group
      v-model="mode"
      type="button"
      :disabled="streaming"
    >
      <a-radio value="text">
        普通问答
      </a-radio>
      <a-radio value="comparison">
        资料对比
      </a-radio>
    </a-radio-group>
    <a-alert v-if="mode === 'comparison'">
      选择2至4份不同资料，输入要比较的问题或维度。没有证据的单元格会明确标注。
    </a-alert>
    <a-card
      v-for="(item, index) in messages"
      :key="index"
      :title="item.question"
    >
      <a-alert
        v-if="item.warning"
        type="warning"
      >
        {{ item.warning }}
      </a-alert>
      <ComparisonCard
        v-if="item.comparison"
        :comparison="item.comparison"
        :citations="item.citations"
        @original="original"
      />
      <p
        v-else
        style="white-space: pre-wrap"
      >
        {{ item.content }}
      </p>
      <a-collapse>
        <a-collapse-item
          v-for="citation in item.citations"
          :key="citation.index"
          :header="`引用 ${citation.index} · ${versionLabel(citation.revision_id)}`"
        >
          <p>{{ citation.content }}</p>
          <pre>{{ formatLocator(citation.locator) }}</pre>
          <a-button @click="original(citation)">
            下载引用版本原件
          </a-button>
        </a-collapse-item>
      </a-collapse><a-button
        :disabled="!canSaveAnswer(item) || item.saved"
        @click="save(item)"
      >
        {{ item.saved ? '已保存' : '保存答案' }}
      </a-button>
    </a-card><a-textarea
      v-model="question"
      :disabled="streaming"
      :placeholder="
        mode === 'comparison'
          ? '例如：比较这些资料中的事务支持、索引结构和适用场景'
          : '针对所选资料提问'
      "
    />
    <p
      v-if="streaming && progress"
      role="status"
    >
      {{ progress }}
    </p>
    <a-space>
      <a-button
        type="primary"
        :disabled="!canSend"
        @click="send"
      >
        {{ mode === 'comparison' ? '生成对比' : '提问' }}
      </a-button><a-button
        v-if="streaming"
        @click="streamController?.abort()"
      >
        停止生成
      </a-button>
    </a-space>
  </a-space>
</template>
