<script setup lang="ts">
import { ref, watch, onMounted } from 'vue'
import { Message, Modal } from '@arco-design/web-vue'
import { IconDelete } from '@arco-design/web-vue/es/icon'
import { adminListFiles, deleteFile } from '@/api/import'
import type { KnowledgeFile } from '@akb/shared'

const files = ref<KnowledgeFile[]>([])
const total = ref(0)
const page = ref(1)
const size = ref(20)
const search = ref('')
const statusFilter = ref('')
const typeFilter = ref('')
const kbIdFilter = ref('')
const userIdFilter = ref('')
const loading = ref(false)

const statusLabels: Record<string, string> = {
  pending: '等待中', processing: '处理中', completed: '已完成', failed: '失败',
}

async function fetchFiles() {
  loading.value = true
  try {
    const res = await adminListFiles({
      page: page.value, size: size.value,
      search: search.value || undefined,
      status: statusFilter.value || undefined,
      file_type: typeFilter.value || undefined,
      kb_id: kbIdFilter.value || undefined,
      user_id: userIdFilter.value || undefined})
    files.value = res.items
    total.value = res.total
  } finally {
    loading.value = false
  }
}

function handleDelete(file: KnowledgeFile) {
  Modal.confirm({
    content: '确认删除？关联的知识片段将被同步删除',
    title: '删除文件',
    onOk: async () => {
      await deleteFile(file.knowledge_base_id, file.id)
      Message.success('已删除')
      fetchFiles()
    },
    onCancel: () => {},
  })
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

watch([page], () => fetchFiles())
watch([statusFilter, typeFilter, kbIdFilter, userIdFilter], () => { page.value = 1; fetchFiles() })
onMounted(() => fetchFiles())
</script>

<template>
  <div class="file-mgmt">
    <div class="file-toolbar">
      <a-input
        v-model="search"
        placeholder="搜索文件名..."
        allow-clear
        style="width:200px"
        @change="page=1;fetchFiles()"
      />
      <a-input
        v-model="kbIdFilter"
        placeholder="知识库 ID..."
        allow-clear
        style="width:200px"
        @change="page=1;fetchFiles()"
      />
      <a-input
        v-model="userIdFilter"
        placeholder="用户 ID..."
        allow-clear
        style="width:200px"
        @change="page=1;fetchFiles()"
      />
      <a-select
        v-model="statusFilter"
        placeholder="状态筛选"
        allow-clear
        style="width:120px"
        @change="page=1;fetchFiles()"
      >
        <a-option
          label="等待中"
          value="pending"
        />
        <a-option
          label="处理中"
          value="processing"
        />
        <a-option
          label="已完成"
          value="completed"
        />
        <a-option
          label="失败"
          value="failed"
        />
      </a-select>
      <a-select
        v-model="typeFilter"
        placeholder="类型筛选"
        allow-clear
        style="width:120px"
        @change="page=1;fetchFiles()"
      >
        <a-option
          label="PDF"
          value="pdf"
        />
        <a-option
          label="Word"
          value="docx"
        />
        <a-option
          label="Markdown"
          value="md"
        />
        <a-option
          label="纯文本"
          value="txt"
        />
        <a-option
          label="图片"
          value="png"
        />
        <a-option
          label="Python"
          value="py"
        />
      </a-select>
    </div>

    <a-table
      :data="files"
      :loading="loading"
      :stripe="true"
      :pagination="false"
    >
      <a-table-column
        data-index="original_filename"
        title="文件名"
        :width="200"
        ellipsis
      />
      <a-table-column
        data-index="knowledge_base_id"
        title="知识库"
        :width="280"
        ellipsis
      />
      <a-table-column
        data-index="user_id"
        title="上传者"
        :width="280"
        ellipsis
      />
      <a-table-column
        title="类型"
        :width="80"
      >
        <template #cell="{ record }">
          <a-tag size="small">
            {{ record.file_type }}
          </a-tag>
        </template>
      </a-table-column>
      <a-table-column
        title="大小"
        :width="90"
      >
        <template #cell="{ record }">
          {{ formatSize(record.file_size) }}
        </template>
      </a-table-column>
      <a-table-column
        title="状态"
        :width="100"
      >
        <template #cell="{ record }">
          <a-tag
            :color="record.status === 'completed' ? 'green' : record.status === 'failed' ? 'red' : record.status === 'processing' ? 'orangered' : 'gray'"
            size="small"
          >
            {{ statusLabels[record.status] || record.status }}
          </a-tag>
        </template>
      </a-table-column>
      <a-table-column
        data-index="chunks_count"
        title="片段"
        :width="70"
      />
      <a-table-column
        title="时间"
        :width="170"
      >
        <template #cell="{ record }">
          {{ new Date(record.created_at).toLocaleString('zh-CN') }}
        </template>
      </a-table-column>
      <a-table-column
        title="操作"
        :width="80"
      >
        <template #cell="{ record }">
          <a-button
            size="small"
            status="danger"
            @click="handleDelete(record)"
          >
            <template #icon>
              <IconDelete />
            </template>
            删除
          </a-button>
        </template>
      </a-table-column>
    </a-table>

    <a-pagination
      v-if="total > size"
      v-model:current="page"
      :page-size="size"
      :total="total"
      show-total
      style="margin-top:16px;justify-content:flex-end;"
    />
  </div>
</template>

<style scoped>
.file-toolbar { display:flex; gap:12px; margin-bottom:16px; flex-wrap:wrap; align-items:center; }
</style>
