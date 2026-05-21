<script setup lang="ts">
/**
 * 右下角导入进度卡片 — 接收 task_id，连 SSE 显示异步处理进度
 */
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { createProgressEventSource } from '@/api/import'

const props = defineProps<{
  taskId: string
  filename: string
}>()

const emit = defineEmits<{
  done: []
  close: []
}>()

const stage = ref('')
const message = ref('等待处理...')
const rawPercent = ref(0)
const percent = computed(() => rawPercent.value > 1 ? rawPercent.value / 100 : rawPercent.value)
const completed = ref(false)
const failed = ref(false)
const errorMsg = ref('')
const totalChunks = ref(0)

let eventSource: EventSource | null = null

function connectSSE() {
  eventSource = createProgressEventSource(props.taskId)

  eventSource.addEventListener('progress', (e: MessageEvent) => {
    const data = JSON.parse(e.data)
    stage.value = data.stage || ''
    message.value = data.message || ''
    rawPercent.value = data.percent || 0
  })

  eventSource.addEventListener('complete', (e: MessageEvent) => {
    const data = JSON.parse(e.data)
    completed.value = true
    totalChunks.value = data.total_chunks || 0
    closeSSE()
    emit('done')
  })

  eventSource.addEventListener('error', (e: MessageEvent) => {
    try {
      const data = JSON.parse(e.data)
      errorMsg.value = data.error || '处理失败'
    } catch {
      errorMsg.value = '连接中断'
    }
    failed.value = true
    closeSSE()
    emit('done')
  })

  eventSource.onerror = () => {
    if (!completed.value && !failed.value) {
      errorMsg.value = '连接中断'
      failed.value = true
    }
    closeSSE()
    emit('done')
  }
}

function closeSSE() {
  if (eventSource) {
    eventSource.close()
    eventSource = null
  }
}

const stageLabels: Record<string, string> = {
  parsing: '解析中', chunking: '切分中',
  vectorizing: '向量化', storing: '入库中'}

onMounted(() => connectSSE())
onUnmounted(() => closeSSE())
</script>

<template>
  <div
    class="import-toast"
    :class="{ completed, failed }"
  >
    <div class="toast-header">
      <span class="toast-title">{{ completed ? '导入完成' : failed ? '导入失败' : '文件导入' }}</span>
      <a-button
        type="text"
        size="small"
        class="toast-close"
        @click="emit('close')"
      >
        ✕
      </a-button>
    </div>

    <p class="toast-filename">
      {{ filename }}
    </p>

    <template v-if="!completed && !failed">
      <a-progress
        :percent="percent"
        :stroke-width="6"
        :show-text="false"
      />
      <p class="toast-stage">
        {{ stageLabels[stage] || message }}
      </p>
    </template>

    <template v-if="completed">
      <p class="toast-result success">
        共生成 {{ totalChunks }} 个知识片段
      </p>
    </template>

    <template v-if="failed">
      <p class="toast-result error">
        {{ errorMsg }}
      </p>
    </template>
  </div>
</template>

<style scoped>
.import-toast {
  width: 320px;
  background: var(--color-bg-card);
  border-radius: 10px;
  box-shadow: 0 6px 30px rgba(0, 0, 0, 0.15);
  padding: 16px 18px;
  font-size: 13px;
  border-left: 4px solid var(--color-primary);
  transition: border-color 0.3s;
}

.import-toast.completed {
  border-left-color: var(--color-success);
}

.import-toast.failed {
  border-left-color: var(--color-danger);
}

.toast-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 4px;
}

.toast-title {
  font-weight: 600;
  font-size: 14px;
  color: var(--color-text-primary);
}

.toast-close {
  padding: 2px;
  font-size: 14px;
  color: var(--color-text-tertiary);
}

.toast-filename {
  color: var(--color-text-secondary);
  margin: 4px 0 12px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.toast-stage {
  color: var(--color-text-tertiary);
  margin: 8px 0 0;
  font-size: 12px;
}

.toast-result {
  margin: 12px 0 0;
  font-size: 13px;
}

.toast-result.success {
  color: var(--color-success);
}

.toast-result.error {
  color: var(--color-danger);
}
</style>
