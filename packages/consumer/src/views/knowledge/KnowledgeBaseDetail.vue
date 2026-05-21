<script setup lang="ts">
import { ref, computed, shallowRef } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { IconLeft } from '@arco-design/web-vue/es/icon'
import ImportDocumentDialog from './ImportDocumentDialog.vue'
import ImportProgressToast from './ImportProgressToast.vue'
import FileListTab from './FileListTab.vue'

const route = useRoute()
const router = useRouter()
const kbId = computed(() => route.params.kbId as string)

const importDialogVisible = ref(false)
const fileRefreshTrigger = ref(0)

interface ImportTask { taskId: string; filename: string }
const importTasks = shallowRef<ImportTask[]>([])

function onFileUploaded(taskId: string, filename: string) {
  importTasks.value = [...importTasks.value, { taskId, filename }]
  fileRefreshTrigger.value++
}

function onTaskDone(taskId: string) {
  importTasks.value = importTasks.value.filter(t => t.taskId !== taskId)
  fileRefreshTrigger.value++
}

function onTaskClose(taskId: string) {
  importTasks.value = importTasks.value.filter(t => t.taskId !== taskId)
}

function goBack() { router.push('/workspace/knowledge-bases') }
</script>

<template>
  <div class="detail-page">
    <div class="detail-header">
      <a-button
        type="text"
        @click="goBack"
      >
        <template #icon>
          <IconLeft />
        </template>
        返回知识库列表
      </a-button>
    </div>

    <FileListTab
      :kb-id="kbId"
      :refresh-trigger="fileRefreshTrigger"
      @upload="importDialogVisible = true"
    />

    <ImportDocumentDialog
      :visible="importDialogVisible"
      :kb-id="kbId"
      @close="importDialogVisible = false"
      @uploaded="onFileUploaded"
    />

    <Teleport to="body">
      <div
        v-if="importTasks.length > 0"
        class="import-toast-stack"
      >
        <ImportProgressToast
          v-for="task in importTasks"
          :key="task.taskId"
          :task-id="task.taskId"
          :filename="task.filename"
          @done="onTaskDone(task.taskId)"
          @close="onTaskClose(task.taskId)"
        />
      </div>
    </Teleport>
  </div>
</template>

<style scoped>
.detail-page { background: var(--color-bg-card); border-radius:8px; padding:20px; }
.detail-header { display:flex; justify-content:space-between; align-items:center; margin-bottom:16px; }
</style>

<style>
.import-toast-stack {
  position: fixed;
  right: 24px;
  bottom: 24px;
  z-index: 9999;
  display: flex;
  flex-direction: column;
  gap: 12px;
}
</style>
