<script setup lang="ts">
import { computed, onUnmounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import type { Source, WikiLink, WikiPageDetail } from '@akb/shared'
import { listSources } from '@/api/sources'
import { compileWikiPage, exportWikiMarkdown, getWikiPage, listWikiPages, publishWikiPage, updateWikiDraft } from '@/api/wiki'
import { useUserStore } from '@/stores/user'
import { createRequestScope } from '@/utils/request-scope'
import { createWikiWriteGuard, wikiConflictMessage } from '@/utils/wiki'
import { sourceSelectable, errorMessage } from '@/utils/review-state'
import WikiRevisionPanel from './WikiRevisionPanel.vue'

const route = useRoute(), user = useUserStore()
const page = ref<WikiPageDetail>(), links = ref<WikiLink[]>([]), sources = ref<Source[]>([])
const selectedSources = ref<string[]>([]), tab = ref('draft'), historyId = ref('')
const editTitle = ref(''), editContent = ref('')
const error = ref(''), auxiliaryError = ref(''), notice = ref('')
const loading = ref(false), busy = ref(false), actionName = ref('')
const reads = createRequestScope()
const identity = () => `${user.generation}/${String(route.params.id)}`
const writes = createWikiWriteGuard(identity)
const baseRevision = computed(() => page.value?.draft_revision || page.value?.published_revision)
const dirty = computed(() => !!baseRevision.value && (editTitle.value !== baseRevision.value.title || editContent.value !== baseRevision.value.content))
const preview = computed(() => baseRevision.value ? { ...baseRevision.value, title: editTitle.value, content: editContent.value } : null)
const historyRevision = computed(() => page.value?.history.find(item => item.id === historyId.value))
const unavailableSources = computed(() => selectedSources.value.filter(id => !sources.value.some(source => source.id === id)))
const canCompile = computed(() => !!baseRevision.value && !busy.value && !loading.value && !dirty.value && selectedSources.value.length > 0 && selectedSources.value.length <= 100 && !unavailableSources.value.length)

function applyPage(result: WikiPageDetail, resetSources = true) {
  page.value = result
  const revision = result.draft_revision || result.published_revision
  editTitle.value = revision?.title || result.title
  editContent.value = revision?.content || ''
  if (resetSources) selectedSources.value = Object.keys(revision?.source_versions || {})
  if (!result.history.some(item => item.id === historyId.value)) historyId.value = result.history[result.history.length - 1]?.id || ''
}

async function load() {
  if (!user.isLoggedIn) return
  const id = String(route.params.id), request = reads.begin(identity())
  loading.value = true; error.value = ''; auxiliaryError.value = ''; notice.value = ''
  const results = await Promise.allSettled([
    getWikiPage(id, request.signal), listWikiPages('', request.signal), listSources(request.signal),
  ])
  request.apply(() => {
    const [detail, index, materials] = results
    if (detail.status === 'fulfilled' && detail.value.id === id) {
      applyPage(detail.value)
      links.value = detail.value.links
    } else if (detail.status === 'rejected') error.value = errorMessage(detail.reason)
    if (index.status === 'fulfilled') links.value = index.value.map(item => ({ id: item.id, slug: item.slug, title: item.title }))
    else auxiliaryError.value = `Wiki链接目录暂不可用：${errorMessage(index.reason)}`
    if (materials.status === 'fulfilled') sources.value = materials.value.filter(sourceSelectable)
    else auxiliaryError.value += `${auxiliaryError.value ? '；' : ''}来源列表暂不可用：${errorMessage(materials.reason)}`
    loading.value = false
  })
}

async function act<T>(name: string, action: (signal: AbortSignal) => Promise<T>, apply: (value: T) => void) {
  if (busy.value || loading.value || !page.value) return
  const own = identity()
  busy.value = true; actionName.value = name; error.value = ''; notice.value = ''
  try {
    await writes.run(action, apply)
  } catch (e) {
    if (identity() === own) error.value = wikiConflictMessage(e)
  } finally {
    if (identity() === own) { busy.value = false; actionName.value = '' }
  }
}

function save() {
  const current = page.value, base = baseRevision.value
  if (!current || !base || !editTitle.value.trim() || !editContent.value.trim()) return
  const title = editTitle.value.trim(), content = editContent.value
  void act('保存草稿', signal => updateWikiDraft(current.id, base.id, title, content, signal), result => {
    applyPage(result, false); notice.value = '已保存为新的草稿修订，之前的版本仍在历史中。'
  })
}

function compile() {
  const current = page.value, base = baseRevision.value
  if (!current || !base || !canCompile.value) return
  const ids = [...selectedSources.value]
  void act('重新编译', signal => compileWikiPage(current.id, base.id, ids, signal), result => {
    applyPage(result); tab.value = 'draft'; notice.value = '已根据当前资料生成新草稿，请复核内容和引用后发布。'
  })
}

function publish() {
  const current = page.value, draft = current?.draft_revision
  if (!current || !draft || dirty.value) return
  void act('发布草稿', signal => publishWikiPage(current.id, draft.id, signal), result => {
    applyPage(result); tab.value = 'published'; notice.value = '草稿已发布。发布表示已选择此修订，不代表事实正确性已被自动验证。'
  })
}

function exportMarkdown() {
  const id = page.value?.id
  if (!id || !page.value?.published_revision) return
  void act('导出 Markdown', signal => exportWikiMarkdown(id, signal), result => {
    const url = URL.createObjectURL(result.blob), link = document.createElement('a')
    link.href = url; link.download = result.filename; link.click()
    setTimeout(() => URL.revokeObjectURL(url), 1000)
  })
}

watch([() => route.params.id, () => user.generation], () => {
  reads.dispose(); writes.dispose()
  page.value = undefined; sources.value = []; links.value = []; selectedSources.value = []
  editTitle.value = ''; editContent.value = ''; historyId.value = ''; tab.value = 'draft'
  error.value = ''; auxiliaryError.value = ''; notice.value = ''; busy.value = false; loading.value = false; actionName.value = ''
  if (user.isLoggedIn) void load()
}, { immediate: true, flush: 'sync' })
onUnmounted(() => { reads.dispose(); writes.dispose() })
</script>

<template>
  <section class="wiki-detail">
    <router-link to="/workspace/wiki">
      返回 Wiki 工作台
    </router-link>
    <a-alert
      v-if="error"
      type="error"
    >
      {{ error }}
    </a-alert>
    <a-alert
      v-if="auxiliaryError"
      type="warning"
    >
      {{ auxiliaryError }}。可刷新后重试。
    </a-alert>
    <a-alert
      v-if="notice"
      type="success"
    >
      {{ notice }}
    </a-alert>
    <a-spin
      v-if="loading"
      :loading="true"
      class="wiki-loading"
    />
    <a-empty
      v-if="!loading && !page"
      description="Wiki 页面未加载或不可访问"
    >
      <a-button @click="load">
        重试加载
      </a-button>
    </a-empty>
    <template v-if="page">
      <div class="wiki-heading">
        <div>
          <h2>{{ page.title }}</h2><p class="wiki-note">
            [[{{ page.slug }}]] · {{ page.published_revision ? '已发布' : '尚未发布' }}
          </p>
        </div>
        <div class="wiki-actions">
          <a-popconfirm
            v-if="dirty"
            content="刷新会丢弃尚未保存的本地编辑，确认继续？"
            @ok="load"
          >
            <a-button :disabled="busy || loading">
              刷新页面
            </a-button>
          </a-popconfirm>
          <a-button
            v-else
            :disabled="busy || loading"
            @click="load"
          >
            刷新页面
          </a-button>
          <a-button
            :disabled="busy || loading || !page.published_revision"
            @click="exportMarkdown"
          >
            导出已发布 Markdown
          </a-button>
        </div>
      </div>
      <a-alert
        v-if="page.source_changed"
        type="warning"
        class="wiki-review-warning"
      >
        来源变化 · 待复核。页面依据的资料已更新或不可用，请检查草稿与原文；这不表示页面内容已被证明错误。
      </a-alert>
      <p
        v-if="busy"
        role="status"
      >
        正在{{ actionName }}，请稍候…
      </p>
      <div class="wiki-columns">
        <main class="wiki-main">
          <a-tabs v-model:active-key="tab">
            <a-tab-pane
              key="draft"
              :title="page.draft_revision ? '草稿与编辑' : '编辑新草稿'"
            >
              <a-alert>人工编辑沿用已有引用；新增陈述不会自动获得依据。请保存修订、核对引用，再决定发布。</a-alert>
              <template v-if="baseRevision">
                <label class="wiki-label">页面标题</label>
                <a-input
                  v-model="editTitle"
                  :max-length="200"
                  :disabled="busy || loading"
                  placeholder="Wiki 页面标题"
                />
                <label class="wiki-label">Markdown 正文</label>
                <a-textarea
                  v-model="editContent"
                  :textarea-attrs="{ 'aria-label': 'Wiki Markdown正文' }"
                  :auto-size="{ minRows: 12, maxRows: 30 }"
                  :max-length="50000"
                  :disabled="busy || loading"
                  placeholder="编辑正文，可用 [[slug]] 链接自己的其他 Wiki 页面"
                />
                <p class="wiki-note">
                  用 [[slug]] 链接已有同用户页面；未找到的页面链接保留为文字。修改标题不会更改稳定的 slug。
                </p>
                <div class="wiki-actions">
                  <a-button
                    type="primary"
                    :disabled="busy || loading || !editTitle.trim() || !editContent.trim() || (!dirty && !!page.draft_revision)"
                    @click="save"
                  >
                    保存新草稿修订
                  </a-button>
                  <a-popconfirm
                    content="确认已人工复核草稿与引用，并将此修订发布？历史版本会保留。"
                    @ok="publish"
                  >
                    <a-button :disabled="busy || loading || dirty || !page.draft_revision">
                      发布草稿
                    </a-button>
                  </a-popconfirm>
                  <a-button
                    v-if="dirty"
                    :disabled="busy || loading"
                    @click="editTitle = baseRevision.title; editContent = baseRevision.content"
                  >
                    恢复已保存内容
                  </a-button>
                </div>
                <p
                  v-if="dirty"
                  class="wiki-note"
                >
                  有尚未保存的编辑。发布或重新编译前请先保存或恢复。
                </p>
                <h3 class="wiki-section-title">
                  预览与引用
                </h3>
                <WikiRevisionPanel
                  v-if="preview"
                  :revision="preview"
                  :links="links"
                />
              </template>
            </a-tab-pane>
            <a-tab-pane
              key="published"
              title="已发布版本"
            >
              <WikiRevisionPanel
                v-if="page.published_revision"
                :revision="page.published_revision"
                :links="links"
              />
              <a-empty
                v-else
                description="还没有已发布版本，请先人工复核并发布草稿"
              />
            </a-tab-pane>
            <a-tab-pane
              key="history"
              :title="`修订历史（${page.history.length}）`"
            >
              <a-select
                v-model="historyId"
                placeholder="选择历史修订"
                class="wiki-history-select"
              >
                <a-option
                  v-for="revision in page.history"
                  :key="revision.id"
                  :value="revision.id"
                >
                  {{ new Date(revision.created_at).toLocaleString() }} · {{ revision.kind === 'generated' ? 'AI 编译' : '人工编辑' }} · {{ revision.id.slice(0, 8) }}{{ revision.id === page.published_revision_id ? ' · 当前发布' : '' }}{{ revision.id === page.draft_revision_id ? ' · 当前草稿' : '' }}
                </a-option>
              </a-select>
              <h3
                v-if="historyRevision"
                class="wiki-section-title"
              >
                {{ historyRevision.title }}
              </h3>
              <WikiRevisionPanel
                v-if="historyRevision"
                :revision="historyRevision"
                :links="links"
              />
              <a-empty
                v-else
                description="暂无修订历史"
              />
            </a-tab-pane>
          </a-tabs>
        </main>
        <aside class="wiki-side">
          <a-card title="重新编译草稿">
            <p class="wiki-note">
              选择当前已发布资料，生成新修订；现有发布内容和历史保留。
            </p>
            <a-select
              v-model="selectedSources"
              multiple
              :max-tag-count="2"
              :disabled="busy || loading"
              placeholder="选择重新编译的资料"
            >
              <a-option
                v-for="source in sources"
                :key="source.id"
                :value="source.id"
              >
                {{ source.name }}
              </a-option>
            </a-select>
            <a-alert
              v-if="unavailableSources.length"
              type="warning"
            >
              部分原来源已不可用或未发布，请移除对应项并重新选择资料。
            </a-alert>
            <a-button
              type="primary"
              :disabled="!canCompile"
              @click="compile"
            >
              按当前资料重新编译
            </a-button>
            <p
              v-if="!selectedSources.length"
              class="wiki-note"
            >
              至少选择一份已发布资料。
            </p>
          </a-card>
          <a-card title="正向链接">
            <p class="wiki-note">
              当前已保存草稿优先，否则取已发布版本。未保存的编辑不计入。
            </p>
            <ul
              v-if="page.links.length"
              class="wiki-links"
            >
              <li
                v-for="item in page.links"
                :key="item.id"
              >
                <router-link :to="`/workspace/wiki/${item.id}`">
                  {{ item.title }}
                </router-link><small>[[{{ item.slug }}]]</small>
              </li>
            </ul>
            <p
              v-else
              class="wiki-note"
            >
              暂无可解析的页面链接。
            </p>
          </a-card>
          <a-card title="反向链接">
            <p class="wiki-note">
              这些已发布页面链接到当前页面。
            </p>
            <ul
              v-if="page.backlinks.length"
              class="wiki-links"
            >
              <li
                v-for="item in page.backlinks"
                :key="item.id"
              >
                <router-link :to="`/workspace/wiki/${item.id}`">
                  {{ item.title }}
                </router-link><small>[[{{ item.slug }}]]</small>
              </li>
            </ul>
            <p
              v-else
              class="wiki-note"
            >
              暂无已发布页面链接到这里。
            </p>
          </a-card>
        </aside>
      </div>
    </template>
  </section>
</template>

<style scoped>
.wiki-detail { display: grid; gap: 16px; max-width: 1440px; margin: 0 auto; }
.wiki-heading { display: flex; gap: 16px; align-items: flex-start; justify-content: space-between; }
.wiki-heading h2 { overflow-wrap: anywhere; }
.wiki-note { color: var(--color-text-secondary); font-size: 13px; margin: 8px 0; overflow-wrap: anywhere; }
.wiki-actions { display: flex; gap: 10px; flex-wrap: wrap; }
.wiki-columns { display: grid; grid-template-columns: minmax(0, 1fr) 290px; gap: 24px; }
.wiki-main { min-width: 0; }
.wiki-side { display: flex; flex-direction: column; gap: 16px; min-width: 0; }
.wiki-side :deep(.arco-select-view) { margin: 12px 0; }
.wiki-label { display: block; font-weight: 500; margin: 18px 0 8px; }
.wiki-main .wiki-actions { margin-top: 14px; }
.wiki-section-title { margin: 22px 0 14px; }
.wiki-history-select { margin-bottom: 12px; }
.wiki-links { padding-left: 18px; overflow-wrap: anywhere; }
.wiki-links li { margin-top: 10px; }
.wiki-links small { display: block; color: var(--color-text-secondary); }
.wiki-loading { padding: 40px; }
@media (max-width: 960px) { .wiki-columns { grid-template-columns: minmax(0, 1fr); } }
@media (max-width: 640px) { .wiki-heading { flex-direction: column; } .wiki-actions { width: 100%; } }
</style>
