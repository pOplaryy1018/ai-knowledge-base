<script setup lang="ts">
import { onMounted, onUnmounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import type { Source, WikiPageSummary } from '@akb/shared'
import { listSources } from '@/api/sources'
import { createWikiPage, listWikiPages } from '@/api/wiki'
import { useUserStore } from '@/stores/user'
import { createRequestScope } from '@/utils/request-scope'
import { sourceSelectable, errorMessage } from '@/utils/review-state'
import { createWikiWriteGuard } from '@/utils/wiki'

const router = useRouter(), user = useUserStore()
const pages = ref<WikiPageSummary[]>([]), sources = ref<Source[]>([])
const query = ref(''), title = ref(''), sourceIds = ref<string[]>([])
const loading = ref(false), loadingSources = ref(false), creating = ref(false)
const error = ref(''), sourceError = ref('')
const pageScope = createRequestScope(), sourceScope = createRequestScope()
const writes = createWikiWriteGuard(() => String(user.generation))
let searchTimer: ReturnType<typeof setTimeout> | undefined

async function loadPages() {
  if (!user.isLoggedIn) return
  const request = pageScope.begin(`${user.generation}/${query.value}`)
  loading.value = true
  error.value = ''
  try {
    const items = await listWikiPages(query.value.trim(), request.signal)
    request.apply(() => { pages.value = items })
  } catch (e) {
    request.apply(() => { error.value = errorMessage(e) })
  } finally {
    request.apply(() => { loading.value = false })
  }
}

async function loadSources() {
  if (!user.isLoggedIn) return
  const request = sourceScope.begin(String(user.generation))
  loadingSources.value = true
  sourceError.value = ''
  try {
    const items = (await listSources(request.signal)).filter(sourceSelectable)
    request.apply(() => {
      sources.value = items
      sourceIds.value = sourceIds.value.filter(id => items.some(source => source.id === id))
    })
  } catch (e) {
    request.apply(() => { sourceError.value = errorMessage(e) })
  } finally {
    request.apply(() => { loadingSources.value = false })
  }
}

async function create() {
  if (creating.value || !title.value.trim() || !sourceIds.value.length || sourceIds.value.length > 100) return
  const generation = user.generation, topic = title.value.trim(), selected = [...sourceIds.value]
  creating.value = true
  error.value = ''
  try {
    await writes.run(signal => createWikiPage(topic, selected, signal), page => {
      void router.push(`/workspace/wiki/${page.id}`)
    })
  } catch (e) {
    if (generation === user.generation) error.value = errorMessage(e)
  } finally {
    if (generation === user.generation) creating.value = false
  }
}

watch(query, () => {
  // Invalidate before the debounce so a previous search cannot flash into the new query.
  pageScope.dispose()
  clearTimeout(searchTimer)
  if (!user.isLoggedIn) return
  searchTimer = setTimeout(() => { void loadPages() }, 300)
})
watch(() => user.generation, () => {
  pageScope.dispose(); sourceScope.dispose(); writes.dispose()
  clearTimeout(searchTimer)
  pages.value = []; sources.value = []; sourceIds.value = []
  title.value = ''; query.value = ''; error.value = ''; sourceError.value = ''
  creating.value = false; loading.value = false; loadingSources.value = false
}, { flush: 'sync' })
onMounted(() => { void loadPages(); void loadSources() })
onUnmounted(() => {
  pageScope.dispose(); sourceScope.dispose(); writes.dispose()
  clearTimeout(searchTimer)
})
</script>

<template>
  <section class="wiki-workbench">
    <div class="wiki-heading">
      <div><h2>LLM Wiki</h2><p>把已发布资料编译为可编辑、可追溯的知识页面。</p></div>
      <router-link to="/workspace/sources">
        管理资料来源
      </router-link>
    </div>
    <a-alert
      v-if="error"
      type="error"
    >
      {{ error }}
    </a-alert>
    <a-card
      title="从资料生成草稿"
      class="wiki-create"
    >
      <p class="wiki-note">
        AI 生成内容需人工复核后发布。来源变化会提示待复核，不表示页面内容已经错误。
        生成按主题选取相关证据，不保证覆盖所选资料全文。
      </p>
      <label class="wiki-label">主题</label>
      <a-input
        v-model="title"
        placeholder="例如：项目中的事务与并发控制"
        :max-length="200"
        :disabled="creating"
      />
      <label class="wiki-label">使用的已发布资料</label>
      <a-alert
        v-if="sourceError"
        type="error"
      >
        {{ sourceError }}
      </a-alert>
      <a-select
        v-model="sourceIds"
        multiple
        :max-tag-count="3"
        :loading="loadingSources"
        :disabled="creating"
        placeholder="选择资料来源（最多100份）"
      >
        <a-option
          v-for="source in sources"
          :key="source.id"
          :value="source.id"
        >
          {{ source.name }}
        </a-option>
      </a-select>
      <p
        v-if="!loadingSources && !sources.length && !sourceError"
        class="wiki-note"
      >
        还没有已发布资料。请先在“资料来源”创建并发布一份资料。
      </p>
      <div class="wiki-actions">
        <a-button
          type="primary"
          :loading="creating"
          :disabled="creating || !title.trim() || !sourceIds.length || sourceIds.length > 100"
          @click="create"
        >
          生成 Wiki 草稿
        </a-button>
        <a-button
          :disabled="creating || loadingSources"
          @click="loadSources"
        >
          刷新资料
        </a-button>
        <span
          v-if="creating"
          role="status"
        >正在依据所选资料生成草稿，请稍候…</span>
      </div>
    </a-card>
    <div class="wiki-heading">
      <h3>知识页面</h3>
      <a-input
        v-model="query"
        allow-clear
        :max-length="200"
        class="wiki-search"
        placeholder="搜索 Wiki 标题或正文"
      />
    </div>
    <a-spin
      :loading="loading"
      class="wiki-list"
    >
      <a-empty
        v-if="!loading && !pages.length"
        :description="error ? '列表加载失败，请重试' : query.trim() ? '没有匹配的 Wiki 页面' : '还没有 Wiki 页面，选择资料生成第一份草稿'"
      />
      <a-list v-else>
        <a-list-item
          v-for="page in pages"
          :key="page.id"
        >
          <div class="wiki-page-row">
            <div>
              <router-link :to="`/workspace/wiki/${page.id}`">
                {{ page.title }}
              </router-link><p class="wiki-note">
                [[{{ page.slug }}]] · 更新于 {{ new Date(page.updated_at).toLocaleString() }}
              </p>
            </div>
            <div class="wiki-tags">
              <a-tag :color="page.published_revision_id ? 'green' : 'gray'">
                {{ page.published_revision_id ? '已发布' : '尚未发布' }}
              </a-tag><a-tag
                v-if="page.draft_revision_id"
                color="arcoblue"
              >
                有草稿
              </a-tag><a-tag
                v-if="page.source_changed"
                color="orange"
              >
                来源变化 · 待复核
              </a-tag>
            </div>
          </div>
        </a-list-item>
      </a-list>
    </a-spin>
    <a-button
      :disabled="loading"
      @click="loadPages"
    >
      刷新页面列表
    </a-button>
  </section>
</template>

<style scoped>
.wiki-workbench { display: grid; gap: 20px; max-width: 1200px; margin: 0 auto; }
.wiki-heading { display: flex; justify-content: space-between; gap: 16px; align-items: center; }
.wiki-heading p, .wiki-note { color: var(--color-text-secondary); font-size: 13px; margin-top: 6px; overflow-wrap: anywhere; }
.wiki-label { display: block; font-weight: 500; margin: 16px 0 8px; }
.wiki-actions { display: flex; flex-wrap: wrap; gap: 12px; align-items: center; margin-top: 16px; }
.wiki-search { max-width: 340px; }
.wiki-list { width: 100%; }
.wiki-page-row { width: 100%; display: flex; justify-content: space-between; align-items: flex-start; gap: 16px; }
.wiki-page-row a { font-size: 16px; font-weight: 500; overflow-wrap: anywhere; }
.wiki-tags { display: flex; flex-wrap: wrap; gap: 6px; }
@media (max-width: 640px) { .wiki-heading, .wiki-page-row { flex-direction: column; align-items: stretch; } .wiki-search { max-width: none; } }
</style>
