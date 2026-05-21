<script setup lang="ts">
/**
 * 知识库列表页 — TanStack Query + 骨架屏
 */
import { ref } from 'vue'
import { IconPlusCircle, IconEdit, IconDelete, IconSearch } from '@arco-design/web-vue/es/icon'
import { useKnowledgeBaseList } from '@/composables/useKnowledgeQueries'
import type { KnowledgeBase, KnowledgeBaseCreate, KnowledgeBaseUpdate } from '@akb/shared'
import KnowledgeBaseDialog from './KnowledgeBaseDialog.vue'
import SkeletonTable from '@/components/common/SkeletonTable.vue'

const {
  page,
  size,
  search,
  items,
  total,
  isLoading,
  createMutation,
  updateMutation,
  confirmDelete} = useKnowledgeBaseList()

// ── 搜索 ──
let searchTimer: ReturnType<typeof setTimeout>
function onSearchChange() {
  clearTimeout(searchTimer)
  searchTimer = setTimeout(() => {
    page.value = 1
  }, 300)
}

// ── 对话框 ──
const dialogVisible = ref(false)
const editing = ref<{ id: string; name: string; description: string | null } | null>(null)

function openCreate() {
  editing.value = null
  dialogVisible.value = true
}

function openEdit(row: KnowledgeBase) {
  editing.value = { id: row.id, name: row.name, description: row.description }
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
    <!-- 页面头部 -->
    <div class="list-header">
      <h2 class="list-title">
        知识库管理
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

    <!-- 搜索栏 -->
    <div class="list-toolbar">
      <a-input
        v-model="search"
        placeholder="搜索知识库名称..."
        allow-clear
        style="width: 320px"
        @input="onSearchChange"
      >
        <template #prefix>
          <IconSearch />
        </template>
      </a-input>
    </div>

    <!-- 表格 -->
    <div class="list-table">
      <SkeletonTable
        v-if="isLoading"
        :rows="5"
        :cols="4"
      />
      <template v-else>
        <a-table
          v-if="items.length > 0"
          :data="items"
          :stripe="true"
        >
          <a-table-column
            data-index="name"
            title="名称"
            :width="200"
          />
          <a-table-column
            data-index="description"
            title="描述"
            :width="250"
            ellipsis
          >
            <template #cell="{ record }">
              {{ record.description || '暂无描述' }}
            </template>
          </a-table-column>
          <a-table-column
            data-index="user_id"
            title="所属用户"
            :width="280"
            ellipsis
          />
          <a-table-column
            title="创建时间"
            :width="180"
          >
            <template #cell="{ record }">
              {{ new Date(record.created_at).toLocaleString('zh-CN') }}
            </template>
          </a-table-column>
          <a-table-column
            title="操作"
            :width="160"
            fixed="right"
          >
            <template #cell="{ record }">
              <a-button
                size="small"
                @click="openEdit(record)"
              >
                <template #icon>
                  <IconEdit />
                </template>
                编辑
              </a-button>
              <a-button
                size="small"
                status="danger"
                @click="confirmDelete(record.id, record.name)"
              >
                <template #icon>
                  <IconDelete />
                </template>
                删除
              </a-button>
            </template>
          </a-table-column>
        </a-table>
        <a-empty
          v-else
          description="暂无知识库"
        >
          <a-button
            type="primary"
            @click="openCreate"
          >
            <template #icon>
              <IconPlusCircle />
            </template>
            创建第一个知识库
          </a-button>
        </a-empty>
      </template>
    </div>

    <!-- 分页 -->
    <a-pagination
      v-if="total > size"
      v-model:current="page"
      :page-size="size"
      :total="total"
      show-total
      style="margin-top:16px;justify-content:flex-end;"
    />

    <!-- 对话框 -->
    <KnowledgeBaseDialog
      :visible="dialogVisible"
      :editing="editing"
      @cancel="dialogVisible = false"
      @submit="handleDialogSubmit"
    />
  </div>
</template>

<style scoped>
.list-page {
  background: #fff;
  border-radius: var(--akb-card-radius);
  padding: 20px;
}

.list-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}

.list-title {
  margin: 0;
  font-size: 18px;
  font-weight: 600;
  color: var(--akb-text);
}

.list-toolbar {
  margin-bottom: 16px;
}

.list-pagination {
  margin-top: 16px;
  justify-content: flex-end;
}
</style>
