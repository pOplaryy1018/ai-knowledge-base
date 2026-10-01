<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'
import type { Source, SourceRevision } from '@akb/shared'
import { getApiClient } from '@/api/client'
import {
  listSources,
  createSource,
  uploadRevision,
  getSourceTask,
  listRevisions,
  archiveSource,
  downloadOriginal,
} from '@/api/sources'
import { createRequestScope } from '@/utils/request-scope'
import { errorMessage, versionLabel } from '@/utils/review-state'
const controller = new AbortController()
const sources = ref<Source[]>([]),
  revisions = ref<SourceRevision[]>([])
const bases = ref<{ id: string; name: string }[]>([])
const name = ref(''),
  kb = ref(''),
  selected = ref<Source>(),
  error = ref(''),
  status = ref(''),
  busy = ref(false)
const timers = new Map<string, ReturnType<typeof setTimeout>>()
const signal = controller.signal
const selectionScope = createRequestScope()
function syncLabel(state: string) {
  return (
    (
      {
        pending: '等待同步',
        processing: '同步中',
        completed: '同步完成',
        failed: '同步失败',
        ready: '已发布',
        staging: '处理中',
      } as Record<string, string>
    )[state] || '等待处理'
  )
}
async function load() {
  sources.value = await listSources(signal)
}
async function act(action: () => Promise<void>) {
  error.value = ''
  busy.value = true
  try {
    await action()
  } catch (e) {
    if (!signal.aborted) error.value = errorMessage(e)
  } finally {
    busy.value = false
  }
}
async function select(source: Source) {
  const request = selectionScope.begin(source.id)
  selected.value = source
  revisions.value = []
  status.value = ''
  try {
    const items = await listRevisions(source.id, request.signal)
    if (selected.value?.id === request.id)
      request.apply(() => {
        revisions.value = items
      })
  } catch (e) {
    request.apply(() => {
      error.value = errorMessage(e)
    })
  }
}
async function refresh() {
  await load()
  if (selected.value) {
    const current = sources.value.find((s) => s.id === selected.value?.id)
    if (current) await select(current)
  }
}
async function poll(id: string) {
  try {
    const task = await getSourceTask(id, signal)
    if (selected.value?.id === task.source_id)
      status.value = `${syncLabel(task.status)} ${task.error || ''}`
    if (task.status === 'completed' || task.status === 'failed') {
      timers.delete(id)
      await refresh()
      if (selected.value?.id === task.source_id)
        status.value = `${syncLabel(task.status)} ${task.error || ''}`
      return
    }
    if (signal.aborted) return
    timers.set(
      id,
      setTimeout(() => {
        void poll(id)
      }, 1000),
    )
  } catch (e) {
    if (!signal.aborted) error.value = errorMessage(e)
  }
}
async function upload(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  const source = selected.value
  if (!file || !source) return
  await act(async () => {
    const task = await uploadRevision(source.id, file, signal)
    status.value = syncLabel(task.status)
    if (task.task_id) {
      const existing = timers.get(task.task_id)
      if (existing) clearTimeout(existing)
      await poll(task.task_id)
    } else await refresh()
  })
  input.value = ''
}
onMounted(() => {
  void act(async () => {
    await load()
    bases.value = (
      await getApiClient().get<{ items: { id: string; name: string }[] }>('/knowledge-bases', {
        signal,
        params: { size: 100 },
      })
    ).data.items
    for (const source of sources.value)
      if (source.active_task_id) {
        await poll(source.active_task_id)
      }
  })
})
onUnmounted(() => {
  controller.abort()
  selectionScope.dispose()
  for (const timer of timers.values()) clearTimeout(timer)
  timers.clear()
})
</script>
<template>
  <a-space
    direction="vertical"
    fill
  >
    <h2>资料来源</h2>
    <a-alert
      v-if="error"
      type="error"
    >
      {{ error }}
    </a-alert>
    <a-space>
      <a-input
        v-model="name"
        placeholder="来源名称"
      /><a-select
        v-model="kb"
        placeholder="选择知识库"
        style="width: 220px"
      >
        <a-option
          v-for="base in bases"
          :key="base.id"
          :value="base.id"
        >
          {{ base.name }}
        </a-option>
      </a-select><a-button
        :disabled="!name.trim() || !kb || busy"
        @click="
          act(async () => {
            await createSource(name.trim(), kb, signal)
            name = ''
            await load()
          })
        "
      >
        创建文档来源
      </a-button>
    </a-space>
    <a-list>
      <a-list-item
        v-for="source in sources"
        :key="source.id"
      >
        <a-space>
          <a-button
            type="text"
            @click="act(() => select(source))"
          >
            {{ source.name }}
          </a-button><a-tag>
            {{
              source.archived_at ? '已归档' : source.current_revision_id ? '已发布' : '尚未发布'
            }}
          </a-tag><span>{{
            source.current_revision_id ? versionLabel(source.current_revision_id) : '尚未发布'
          }}</span>
        </a-space>
      </a-list-item>
    </a-list>
    <a-card
      v-if="selected"
      :title="selected.name"
    >
      <a-space
        direction="vertical"
        fill
      >
        <a-space>
          <input
            type="file"
            accept=".md,.markdown,.txt,.text,.pdf,.docx,.doc"
            :disabled="!!selected.archived_at || busy"
            @change="upload"
          ><a-popconfirm
            content="归档后无法作为新问题来源，已有引用仍可复核。"
            @ok="
              act(async () => {
                await archiveSource(selected!.id, signal)
                await refresh()
              })
            "
          >
            <a-button :disabled="!!selected.archived_at || busy">
              归档
            </a-button>
          </a-popconfirm>
        </a-space><a-alert v-if="status">
          同步状态：{{ status }}
        </a-alert>
        <a-list>
          <a-list-item
            v-for="revision in revisions"
            :key="revision.id"
          >
            <a-space>
              <span>{{ revision.filename }} · {{ syncLabel(revision.state) }} ·
                {{ new Date(revision.created_at).toLocaleString() }}</span><a-button
                @click="
                  act(() => downloadOriginal(selected!.id, revision.id, revision.filename, signal))
                "
              >
                下载原件
              </a-button>
            </a-space>
          </a-list-item>
        </a-list>
      </a-space>
    </a-card>
  </a-space>
</template>
