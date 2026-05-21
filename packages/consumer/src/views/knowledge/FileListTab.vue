<script setup lang="ts">
import { ref, watch, onMounted } from 'vue'
import { Message, Modal } from '@arco-design/web-vue'
import { IconDelete, IconSync, IconUpload, IconEye } from '@arco-design/web-vue/es/icon'
import { listFiles, deleteFile, retryFile } from '@/api/import'
import FilePreviewOverlay from './FilePreviewOverlay.vue'
import type { KnowledgeFile } from '@akb/shared'
import type { TableColumnData } from '@arco-design/web-vue'

const props = defineProps<{ kbId: string; refreshTrigger: number }>()
const emit = defineEmits<{ upload: [] }>()

const files = ref<KnowledgeFile[]>([])
const total = ref(0)
const page = ref(1)
const size = ref(20)
const search = ref('')
const loading = ref(false)
const deleting = ref<string | null>(null)
const retrying = ref<string | null>(null)
const previewVisible = ref(false)
const previewFileData = ref<KnowledgeFile | null>(null)

function handlePreview(file: KnowledgeFile) {
  previewFileData.value = file
  previewVisible.value = true
}

const statusLabels: Record<string, string> = {
  pending: '等待中', processing: '处理中',
  completed: '已完成', failed: '失败',
}

const columns: TableColumnData[] = [
  { slotName: 'filename', title: '文件名', width: 200, ellipsis: true },
  { slotName: 'type', title: '类型', width: 80 },
  { slotName: 'size', title: '大小', width: 90 },
  { slotName: 'status', title: '状态', width: 100 },
  { dataIndex: 'chunks_count', title: '片段数', width: 80 },
  { slotName: 'created_at', title: '上传时间', width: 170 },
  { slotName: 'actions', title: '操作', width: 120 },
]

async function fetchFiles() {
  loading.value = true
  try {
    const res = await listFiles(props.kbId, {
      page: page.value, size: size.value,
      search: search.value || undefined,
    })
    files.value = res.items ?? []
    total.value = res.total ?? 0
  } catch {
    files.value = []
    total.value = 0
  } finally {
    loading.value = false
  }
}

let searchTimer: ReturnType<typeof setTimeout>
function onSearchChange() {
  clearTimeout(searchTimer)
  searchTimer = setTimeout(() => { page.value = 1; fetchFiles() }, 300)
}

function handleDelete(file: KnowledgeFile) {
  const msg = file.status === 'completed'
    ? `将同步删除该文件生成的 ${file.chunks_count} 个知识片段，确认删除？`
    : '确认删除该文件？'
  Modal.confirm({
    content: msg,
    title: '删除文件',
    onOk: async () => {
      deleting.value = file.id
      await deleteFile(props.kbId, file.id)
      Message.success('文件已删除')
      await fetchFiles()
      deleting.value = null
    },
    onCancel: () => {},
  })
}

async function handleRetry(file: KnowledgeFile) {
  retrying.value = file.id
  try {
    const res = await retryFile(props.kbId, file.id)
    Message.success(`已重新入队，任务 ID: ${res.task_id}`)
    await fetchFiles()
  } catch (e: any) {
    Message.error(e?.response?.data?.detail || '重试失败')
  } finally {
    retrying.value = null
  }
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

watch([page], () => fetchFiles())
watch(() => props.refreshTrigger, () => { page.value = 1; fetchFiles() })
onMounted(() => fetchFiles())
</script>

<template>
  <div class="file-list-tab">
    <div class="file-toolbar">
      <a-input
        v-model="search"
        placeholder="搜索文件名..."
        allow-clear
        style="width:280px"
        @input="onSearchChange"
      />
      <a-button
        type="primary"
        @click="emit('upload')"
      >
        <template #icon>
          <IconUpload />
        </template>
        上传文件
      </a-button>
    </div>

    <a-table
      :data="files"
      :columns="columns"
      :loading="loading"
      :stripe="true"
      :pagination="false"
    >
      <template #filename="{ record }">
        <span
          class="filename-link"
          :class="{ disabled: (record as KnowledgeFile).status !== 'completed' }"
          @click="(record as KnowledgeFile).status === 'completed' && handlePreview(record as KnowledgeFile)"
        >
          {{ (record as KnowledgeFile).original_filename }}
        </span>
      </template>
      <template #type="{ record }">
        <a-tag size="small">
          {{ (record as KnowledgeFile).file_type }}
        </a-tag>
      </template>
      <template #size="{ record }">
        {{ formatSize((record as KnowledgeFile).file_size) }}
      </template>
      <template #status="{ record }">
        <a-tag
          :color="(record as KnowledgeFile).status === 'completed' ? 'green' : (record as KnowledgeFile).status === 'failed' ? 'red' : (record as KnowledgeFile).status === 'processing' ? 'orangered' : 'gray'"
          size="small"
        >
          {{ statusLabels[(record as KnowledgeFile).status] || (record as KnowledgeFile).status }}
        </a-tag>
      </template>
      <template #created_at="{ record }">
        {{ new Date((record as KnowledgeFile).created_at).toLocaleString('zh-CN') }}
      </template>
      <template #actions="{ record }">
        <a-button
          size="small"
          :disabled="(record as KnowledgeFile).status !== 'completed'"
          @click="handlePreview(record as KnowledgeFile)"
        >
          <template #icon>
            <IconEye />
          </template>
          预览
        </a-button>
        <a-button
          v-if="(record as KnowledgeFile).status === 'failed'"
          size="small"
          status="warning"
          :loading="retrying === (record as KnowledgeFile).id"
          @click="handleRetry(record as KnowledgeFile)"
        >
          <template #icon>
            <IconSync />
          </template>
          重试
        </a-button>
        <a-button
          size="small"
          status="danger"
          :loading="deleting === (record as KnowledgeFile).id"
          @click="handleDelete(record as KnowledgeFile)"
        >
          <template #icon>
            <IconDelete />
          </template>
          删除
        </a-button>
      </template>
    </a-table>

    <a-pagination
      v-if="total > size"
      v-model:current="page"
      :page-size="size"
      :total="total"
      show-total
      style="margin-top:16px;justify-content:flex-end;"
    />

    <a-empty
      v-if="!loading && files.length === 0"
      description="暂无文件，上传第一个文档开始构建知识库"
    >
      <a-button
        type="primary"
        @click="emit('upload')"
      >
        <template #icon>
          <IconUpload />
        </template>
        上传文件
      </a-button>
    </a-empty>

    <FilePreviewOverlay
      :visible="previewVisible"
      :file="previewFileData"
      @close="previewVisible = false"
    />
  </div>
</template>

<style scoped>
.file-toolbar { display:flex; gap:12px; margin-bottom:16px; align-items:center; }

.filename-link {
  color: var(--color-primary, #165dff);
  cursor: pointer;
}

.filename-link:hover {
  text-decoration: underline;
}

.filename-link.disabled {
  color: var(--color-text-secondary, #86909c);
  cursor: default;
}

.filename-link.disabled:hover {
  text-decoration: none;
}
</style>
