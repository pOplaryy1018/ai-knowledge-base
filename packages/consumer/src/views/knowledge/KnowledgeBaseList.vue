<script setup lang="ts">
/**
 * 知识库列表页 — 卡片网格布局（仿飞书云文档）
 */
import { ref, computed } from 'vue'
import { IconPlusCircle, IconSearch } from '@arco-design/web-vue/es/icon'
import { useKnowledgeBaseList } from '@/composables/useKnowledgeQueries'
import type { KnowledgeBase, KnowledgeBaseCreate, KnowledgeBaseUpdate } from '@akb/shared'
import KnowledgeBaseDialog from './KnowledgeBaseDialog.vue'
import KnowledgeBaseGrid from '@/components/knowledge/KnowledgeBaseGrid.vue'

const {
  page, size, search, items, total, isLoading, isError, refetch,
  createMutation, updateMutation, confirmDelete,
} = useKnowledgeBaseList()

// ── 搜索防抖：输入值 vs 查询值分离 ──
const searchInput = ref('')
let searchTimer: ReturnType<typeof setTimeout>
function onSearchInput() {
  clearTimeout(searchTimer)
  searchTimer = setTimeout(() => {
    search.value = searchInput.value
    page.value = 1
  }, 300)
}

const dialogVisible = ref(false)
const editing = ref<{ id: string; name: string; description: string | null } | null>(null)
const submitting = computed(() => createMutation.isPending.value || updateMutation.isPending.value)

function openCreate() { editing.value = null; dialogVisible.value = true }
function openEdit(kb: KnowledgeBase) {
  editing.value = { id: kb.id, name: kb.name, description: kb.description }
  dialogVisible.value = true
}

async function handleDialogSubmit(data: KnowledgeBaseCreate | KnowledgeBaseUpdate) {
  if (editing.value) {
    await updateMutation.mutateAsync({ id: editing.value.id, body: data as KnowledgeBaseUpdate })
  } else {
    await createMutation.mutateAsync(data as KnowledgeBaseCreate)
  }
  dialogVisible.value = false
}
</script>

<template>
  <div class="list-page">
    <div class="list-header">
      <h2 class="list-title">
        全部知识库
      </h2>
      <a-button
        type="primary"
        @click="openCreate"
      >
        <template #icon>
          <IconPlusCircle />
        </template>
        新建知识库
      </a-button>
    </div>

    <div class="list-toolbar">
      <a-input
        v-model="searchInput"
        placeholder="搜索知识库名称..."
        allow-clear
        style="width:320px"
        @input="onSearchInput"
      >
        <template #prefix>
          <IconSearch />
        </template>
      </a-input>
    </div>

    <KnowledgeBaseGrid
      :items="items"
      :is-loading="isLoading"
      :is-error="isError"
      :on-delete="confirmDelete"
      :on-edit="openEdit"
      :on-create="openCreate"
      :on-retry="() => refetch()"
    />

    <!-- 分页 -->
    <a-pagination
      v-if="total > size"
      v-model:current="page"
      :page-size="size"
      :total="total"
      show-total
      style="margin-top:24px;justify-content:flex-end;"
    />

    <KnowledgeBaseDialog
      :visible="dialogVisible"
      :editing="editing"
      :submitting="submitting"
      @close="dialogVisible = false"
      @submit="handleDialogSubmit"
    />
  </div>
</template>

<style scoped>
.list-page {
  background: var(--color-bg-card);
  border-radius: var(--akb-card-radius, 8px);
  padding: 24px;
}
.list-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}
.list-title {
  margin: 0;
  font-size: 20px;
  font-weight: 600;
  color: var(--color-text-primary);
}
.list-toolbar {
  margin-bottom: 20px;
}
</style>
