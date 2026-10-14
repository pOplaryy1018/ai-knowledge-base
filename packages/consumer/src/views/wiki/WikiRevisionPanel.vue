<script setup lang="ts">
import { onUnmounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import type { WikiLink, WikiRevision, WikiCitation } from '@akb/shared'
import MarkdownPreview from '@/components/common/MarkdownPreview.vue'
import { downloadOriginal } from '@/api/sources'
import { useUserStore } from '@/stores/user'
import { formatLocator, versionLabel } from '@/utils/review-state'
import { createWikiWriteGuard, wikiMarkdown, wikiConflictMessage } from '@/utils/wiki'

const props = defineProps<{ revision: WikiRevision; links: WikiLink[] }>()
const router = useRouter(), user = useUserStore()
const error = ref(''), downloading = ref(false)
const downloads = createWikiWriteGuard(() => `${user.generation}/${props.revision.id}`)
function navigate(event: MouseEvent) {
  if (event.button !== 0 || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return
  const link = (event.target as Element)?.closest('a')
  const href = link?.getAttribute('href')
  if (href && /^\/workspace\/wiki\/[^?#]+$/.test(href)) { event.preventDefault(); void router.push(href) }
}
async function original(citation: WikiCitation) {
  if (downloading.value || citation.unavailable) return
  const identity = `${user.generation}/${props.revision.id}`
  downloading.value = true; error.value = ''
  try {
    await downloads.run(signal => downloadOriginal(citation.source_id, citation.revision_id, 'Wiki引用原件', signal), () => {})
  } catch (e) {
    if (identity === `${user.generation}/${props.revision.id}`) error.value = wikiConflictMessage(e)
  } finally {
    if (identity === `${user.generation}/${props.revision.id}`) downloading.value = false
  }
}
watch(() => `${user.generation}/${props.revision.id}`, () => { downloads.dispose(); error.value = ''; downloading.value = false }, { flush: 'sync' })
onUnmounted(() => downloads.dispose())
</script>

<template>
  <div class="wiki-revision">
    <p class="wiki-meta">
      修订 {{ revision.id.slice(0, 8) }} · {{ revision.kind === 'generated' ? 'AI 编译' : '人工编辑' }} · {{ new Date(revision.created_at).toLocaleString() }}
    </p>
    <div @click="navigate">
      <MarkdownPreview
        :content="wikiMarkdown(revision.content, links)"
        max-height="none"
      />
    </div>
    <a-alert
      v-if="error"
      type="error"
    >
      {{ error }}
    </a-alert>
    <h4>引用证据 · {{ revision.citations.length }} 条</h4>
    <p
      v-if="!revision.citations.length"
      class="wiki-meta"
    >
      此修订没有可查看的引用。请核对资料与陈述的依据。
    </p>
    <a-collapse v-else>
      <a-collapse-item
        v-for="citation in revision.citations"
        :key="citation.index"
        :header="`引用 [${citation.index}] · ${citation.knowledge_title || '资料'} · ${versionLabel(citation.revision_id)}`"
      >
        <a-alert
          v-if="citation.unavailable"
          type="warning"
        >
          此引用的原文或资料访问权限已不可用，不能据此核验当前陈述。
        </a-alert>
        <template v-else>
          <p class="wiki-quote">
            {{ citation.quote || citation.content || '原文暂不可用' }}
          </p>
          <p class="wiki-meta">
            {{ formatLocator(citation.locator) }}
          </p>
          <a-button
            :disabled="downloading"
            @click="original(citation)"
          >
            下载引用版本原件
          </a-button>
        </template>
      </a-collapse-item>
    </a-collapse>
    <details class="wiki-versions">
      <summary>查看修订依据的资料版本</summary><p
        v-for="(revisionId, sourceId) in revision.source_versions"
        :key="sourceId"
        class="wiki-meta"
      >
        来源 {{ sourceId }} · {{ versionLabel(revisionId) }}
      </p>
    </details>
  </div>
</template>

<style scoped>
.wiki-revision { display: grid; gap: 14px; min-width: 0; }
.wiki-meta { font-size: 12px; color: var(--color-text-secondary); overflow-wrap: anywhere; }
.wiki-quote { white-space: pre-wrap; overflow-wrap: anywhere; margin-bottom: 10px; }
.wiki-versions summary { cursor: pointer; font-size: 13px; }
.wiki-versions p { margin-top: 8px; }
</style>
