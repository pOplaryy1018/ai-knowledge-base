<script setup lang="ts">
/**
 * 文档导入弹窗 — 选择文件后直接上传，进度展示交给右下角 Toast
 */
import { ref, watch } from 'vue'
import { Message } from '@arco-design/web-vue'
import { IconUpload } from '@arco-design/web-vue/es/icon'
import { uploadFile } from '@/api/import'

const props = defineProps<{
  visible: boolean
  kbId: string
}>()

const emit = defineEmits<{
  close: []
  uploaded: [taskId: string, filename: string]
}>()

// 每次弹窗打开时递增 key，强制重建 upload 组件以清除上次上传的内部状态
const uploadKey = ref(0)
watch(() => props.visible, (v) => {
  if (v) uploadKey.value++
})

const allowed = [
  '.pdf', '.docx', '.doc', '.md', '.markdown', '.txt', '.text',
  '.png', '.jpg', '.jpeg', '.gif', '.bmp', '.webp',
  '.py', '.ts', '.tsx', '.js', '.jsx', '.java', '.go', '.rs',
  '.c', '.cpp', '.h', '.json', '.yaml', '.yml', '.xml', '.toml',
]

function beforeUpload(file: File) {
  const suffix = '.' + file.name.split('.').pop()?.toLowerCase()
  if (!allowed.includes(suffix)) {
    Message.error(`不支持的文件格式: ${suffix}`)
    return false
  }
  if (file.size > 50 * 1024 * 1024) {
    Message.error('文件大小不能超过 50MB')
    return false
  }
  return true
}

function handleUpload(option: any) {
  const file = option.fileItem?.file || option.file
  if (!file) {
    Message.error('文件对象无效')
    option.onError?.(new Error('文件对象无效'))
    return { abort: () => {} }
  }
  // 立即关闭弹窗，上传在后台进行，进度由右下角 Toast 展示
  emit('close')
  uploadFile(props.kbId, file)
    .then((res) => {
      option.onSuccess?.(res)
      emit('uploaded', res.task_id, file.name)
    })
    .catch((e: any) => {
      option.onError?.(e)
      Message.error(e?.response?.data?.detail || '上传失败，请重试')
    })
  return { abort: () => {} }
}
</script>

<template>
  <a-modal
    :visible="visible"
    title="导入文档"
    :width="520"
    :mask-closable="false"
    :footer="false"
    @cancel="emit('close')"
  >
    <a-upload
      :key="uploadKey"
      draggable
      :show-file-list="false"
      :before-upload="beforeUpload"
      :custom-request="handleUpload"
      :limit="1"
    >
      <template #upload-button>
        <div class="upload-area">
          <IconUpload
            :size="48"
            class="upload-icon"
          />
          <div class="upload-text">
            <p class="upload-primary">
              将文件拖拽到此处，或 <em>点击选择</em>
            </p>
            <p class="upload-hint">
              支持 PDF、Word、Markdown、TXT、图片（PNG/JPG）、代码文件（Python/TS/JS/Java/Go 等），单文件不超过 50MB
            </p>
          </div>
        </div>
      </template>
    </a-upload>
  </a-modal>
</template>

<style scoped>
.upload-area {
  padding: 24px 0;
  text-align: center;
}
.upload-icon {
  color: var(--color-text-tertiary);
  margin-bottom: 8px;
}
.upload-primary {
  font-size: 16px;
  color: var(--color-text-secondary);
  margin: 8px 0;
}
.upload-primary em {
  color: var(--akb-primary, #122E8A);
  font-style: normal;
}
.upload-hint {
  font-size: 12px;
  color: var(--color-text-tertiary);
  margin: 4px 0;
}
</style>
