<script setup lang="ts">
import type { Source, SourcePublication } from '@akb/shared'
import { versionLabel } from '@/utils/review-state'

defineProps<{ source: Source; publications: SourcePublication[]; busy: boolean; loading: boolean; error: string }>()
defineEmits<{ rollback: [revisionId: string]; reload: [] }>()
</script>

<template>
  <section
    class="history-panel"
    aria-label="发布历史"
  >
    <h3 class="akb-subheading">
      发布历史
    </h3>
    <p>重新发布历史版本会保留现有记录，并对受影响的答案发起复核。</p>
    <a-alert
      v-if="error"
      type="error"
    >
      {{ error }} <a-button
        size="mini"
        @click="$emit('reload')"
      >
        重试
      </a-button>
    </a-alert>
    <a-spin v-else-if="loading" />
    <a-empty
      v-else-if="!publications.length"
      description="暂无发布记录"
    />
    <a-list v-else>
      <a-list-item
        v-for="publication in publications"
        :key="publication.id"
      >
        <div class="history-row">
          <div>
            <strong>发布 #{{ publication.sequence }}</strong>
            <span> · {{ versionLabel(publication.revision_id) }} · {{ new Date(publication.created_at).toLocaleString() }}</span>
            <a-tag v-if="publication.id === source.current_publication_id">
              当前发布
            </a-tag>
          </div>
          <a-popconfirm
            v-if="publication.revision_id !== source.current_revision_id && !source.archived_at && source.current_publication_id"
            content="重新发布此历史版本后，受影响的答案将进入复核。"
            ok-text="确认回滚"
            cancel-text="取消"
            @ok="$emit('rollback', publication.revision_id)"
          >
            <a-button
              :disabled="busy || !!source.active_task_id"
              :aria-label="`回滚到发布 #${publication.sequence}`"
            >
              回滚到此版本
            </a-button>
          </a-popconfirm>
        </div>
      </a-list-item>
    </a-list>
  </section>
</template>

<style scoped>
.history-panel { color: var(--akb-text); }
.history-panel > p { color: var(--akb-text-secondary); line-height: 1.6; }
.history-row { width: 100%; display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 12px; }
.history-row span { color: var(--akb-text-secondary); }
.history-row .arco-tag { margin-left: 8px; }
</style>
