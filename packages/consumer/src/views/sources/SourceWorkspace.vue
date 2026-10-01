<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import type { Source, SourceRevision, SourceDocument } from '@akb/shared'
import { getApiClient } from '@/api/client'
import {
  listSources,
  createSource,
  uploadRevision,
  getSourceTask,
  listRevisions,
  archiveSource,
  downloadOriginal,
  listRepoRoots,
  syncSource,
  listRevisionDocuments,
  getRevisionDocument,
  updateSourceScope,
} from '@/api/sources'
import { createRequestScope } from '@/utils/request-scope'
import { errorMessage, versionLabel, repositoryManifest } from '@/utils/review-state'
const controller = new AbortController()
const sources = ref<Source[]>([]),
  revisions = ref<SourceRevision[]>([])
const revisionRows = computed(() =>
  revisions.value.map((revision) => ({
    ...revision,
    scope: repositoryManifest(selected.value?.kind || 'document', revision.manifest),
  })),
)
const bases = ref<{ id: string; name: string }[]>([])
const kind = ref<Source['kind']>('document')
const roots = ref<{ id: string; label: string }[]>([])
const rootId = ref(''),
  relativePath = ref(''),
  publicUrl = ref(''),
  includePaths = ref('')
const documents = ref<SourceDocument[]>([])
const viewedRevision = ref(''),
  viewedContent = ref(''),
  viewedPath = ref('')
const documentScope = createRequestScope()
const scopeEditRequest = createRequestScope()
const scopePaths = ref('')
const validCreation = computed(
  () =>
    name.value.trim() &&
    kb.value &&
    (kind.value === 'document' ||
      (kind.value === 'git_local'
        ? rootId.value && relativePath.value.trim()
        : /^https:\/\/github\.com\/[^/]+\/[^/]+\/?$/.test(publicUrl.value.trim()))),
)
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
  scopeEditRequest.begin(source.id)
  scopePaths.value = (source.config?.include_paths || []).join(', ')
  selected.value = source
  revisions.value = []
  status.value = ''
  documentScope.begin(source.id)
  documents.value = []
  viewedContent.value = ''
  viewedRevision.value = ''
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
    if (selected.value?.id === source.id) status.value = syncLabel(task.status)
    if (task.task_id) {
      const existing = timers.get(task.task_id)
      if (existing) clearTimeout(existing)
      await poll(task.task_id)
    } else await refresh()
  })
  input.value = ''
}
async function browse(revision: SourceRevision) {
  const source = selected.value
  if (!source) return
  const request = documentScope.begin(`${source.id}/${revision.id}`)
  viewedRevision.value = revision.id
  documents.value = []
  viewedContent.value = ''
  try {
    const items = await listRevisionDocuments(source.id, revision.id, request.signal)
    request.apply(() => {
      documents.value = items
    })
  } catch (e) {
    request.apply(() => {
      error.value = errorMessage(e)
    })
  }
}
async function viewDocument(document: SourceDocument) {
  const source = selected.value,
    revision = viewedRevision.value
  if (!source || !revision) return
  const request = documentScope.begin(`${source.id}/${revision}/${document.id}`)
  viewedContent.value = ''
  try {
    const content = await getRevisionDocument(source.id, revision, document.id, request.signal)
    request.apply(() => {
      viewedContent.value = content
      viewedPath.value = document.logical_path
    })
  } catch (e) {
    request.apply(() => {
      error.value = errorMessage(e)
    })
  }
}
async function create() {
  await act(async () => {
    const config =
      kind.value === 'git_local'
        ? { root_id: rootId.value, relative_path: relativePath.value.trim() }
        : kind.value === 'git_public'
          ? { url: publicUrl.value.trim() }
          : undefined
    if (config)
      Object.assign(config, {
        include_paths: includePaths.value
          .split(/[\n,]/)
          .map((path) => path.trim())
          .filter(Boolean),
      })
    const source = await createSource(name.value.trim(), kb.value, signal, {
      kind: kind.value,
      config,
    })
    name.value = ''
    await load()
    await select(source)
  })
}
async function saveScope() {
  const source = selected.value
  if (!source) return
  const request = scopeEditRequest.begin(source.id)
  const paths = scopePaths.value.split(/[\n,]/).map(path => path.trim()).filter(Boolean)
  await act(async () => {
    try {
      await updateSourceScope(source.id, paths, request.signal)
      if (!request.isCurrent()) return
      const items = await listSources(request.signal)
      request.apply(() => {
        if (selected.value?.id !== source.id) return
        sources.value = items
        selected.value = items.find(item => item.id === source.id) || source
        scopePaths.value = (selected.value.config?.include_paths || []).join(', ')
        status.value = '采集范围已保存，需手动同步后发布新版本。'
      })
    } catch (e) {
      request.apply(() => { error.value = errorMessage(e) })
    }
  })
}
async function manualSync() {
  const source = selected.value
  if (!source) return
  await act(async () => {
    const task = await syncSource(source.id, signal)
    if (task.task_id) {
      source.active_task_id = task.task_id
      const listed = sources.value.find((item) => item.id === source.id)
      if (listed) listed.active_task_id = task.task_id
    }
    if (selected.value?.id === source.id) status.value = syncLabel(task.status)
    if (task.task_id) await poll(task.task_id)
    else await refresh()
  })
}
onMounted(() => {
  void act(async () => {
    await load()
    try {
      roots.value = await listRepoRoots(signal)
    } catch (e) {
      if (!signal.aborted) error.value = errorMessage(e)
    }
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
  documentScope.dispose()
  scopeEditRequest.dispose()
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
      </a-select>
      <a-select
        v-model="kind"
        style="width: 180px"
      >
        <a-option value="document">
          文档
        </a-option><a-option value="git_local">
          本地仓库
        </a-option><a-option value="git_public">
          公开 GitHub 仓库
        </a-option>
      </a-select>
      <a-select
        v-if="kind === 'git_local'"
        v-model="rootId"
        placeholder="授权目录"
        style="width: 180px"
      >
        <a-option
          v-for="root in roots"
          :key="root.id"
          :value="root.id"
        >
          {{ root.label }}
        </a-option>
      </a-select>
      <a-input
        v-if="kind === 'git_local'"
        v-model="relativePath"
        placeholder="根目录内相对路径（根仓库填 .）"
      />
      <a-input
        v-if="kind === 'git_public'"
        v-model="publicUrl"
        placeholder="https://github.com/owner/repo"
      />
      <a-input
        v-if="kind !== 'document'"
        v-model="includePaths"
        placeholder="可选：限定路径，以逗号分隔"
      />
      <a-button
        :disabled="!validCreation || busy"
        @click="create"
      >
        创建来源
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
        <p>
          {{
            selected.kind === 'document'
              ? '文档'
              : selected.kind === 'git_local'
                ? '本地仓库'
                : '公开仓库'
          }}
          · {{ selected.config?.relative_path || selected.config?.url || '' }}
        </p>
        <a-alert
          v-if="selected.kind !== 'document' && selected.last_sync_manifest?.dirty"
          type="warning"
        >
          最近同步检测到未提交修改；采集只包含已提交内容。
        </a-alert>
        <a-space v-if="selected.kind !== 'document'">
          <a-input
            v-model="scopePaths"
            placeholder="调整采集范围，逗号分隔；留空采集整个仓库"
            :disabled="busy || !!selected.active_task_id || !!selected.archived_at"
          />
          <a-button
            :disabled="busy || !!selected.active_task_id || !!selected.archived_at"
            @click="saveScope"
          >
            保存采集范围
          </a-button>
        </a-space>
        <a-space>
          <input
            v-if="selected.kind === 'document'"
            type="file"
            accept=".md,.markdown,.txt,.text,.pdf,.docx,.doc"
            :disabled="!!selected.archived_at || busy"
            @change="upload"
          >
          <a-button
            v-if="selected.kind !== 'document'"
            :disabled="!!selected.archived_at || busy || !!selected.active_task_id"
            @click="manualSync"
          >
            手动同步
          </a-button>
          <a-popconfirm
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
        <a-alert
          v-if="selected.kind !== 'document' && selected.last_sync_manifest?.dirty"
          type="warning"
        >
          最近一次同步检测到未提交修改；已发布版本只包含已提交内容。
        </a-alert>
        <a-list>
          <a-list-item
            v-for="revision in revisionRows"
            :key="revision.id"
          >
            <a-space>
              <span>{{ revision.commit || revision.filename }} · {{ syncLabel(revision.state) }} ·
                {{ new Date(revision.created_at).toLocaleString() }}</span><a-button
                  v-if="selected.kind === 'document'"
                  @click="
                    act(() => downloadOriginal(selected!.id, revision.id, revision.filename, signal))
                  "
                >
                  下载原件
                </a-button>
              <a-button
                v-if="selected.kind !== 'document'"
                @click="act(() => browse(revision))"
              >
                查看版本文件
              </a-button>
            </a-space>
            <div v-if="revision.scope">
              <p>
                实际采集
                {{ revision.scope.included }}
                个文件 · 跳过 {{ revision.scope.skipped.length }} 个文件
              </p>
              <a-alert
                v-if="revision.scope.dirty"
                type="warning"
              >
                工作区存在未提交修改；此版本只包含已提交内容。
              </a-alert>
              <details v-if="revision.scope.skipped.length">
                <summary>查看跳过范围</summary>
                <p
                  v-for="(item, index) in revision.scope.skipped"
                  :key="index"
                >
                  {{ item.path }} · {{ item.reason }}
                </p>
              </details>
            </div>
          </a-list-item>
        </a-list>
        <a-card
          v-if="viewedRevision"
          :title="`版本文件 · ${viewedRevision.slice(0, 8)}`"
        >
          <a-button
            v-for="document in documents"
            :key="document.id"
            type="text"
            @click="act(() => viewDocument(document))"
          >
            {{ document.logical_path }}
          </a-button>
          <p v-if="!documents.length">
            此版本没有可查看的文本文件。
          </p>
          <p v-if="viewedContent">
            {{ viewedPath }}
          </p>
          <pre
            v-if="viewedContent"
            style="white-space: pre; overflow: auto; max-height: 600px"
          >{{
            viewedContent
          }}</pre>
        </a-card>
      </a-space>
    </a-card>
  </a-space>
</template>
