<script setup lang="ts">
/**
 * Agent 管理页 — TanStack Query + 骨架屏
 */
import { ref } from 'vue'
import { Message } from '@arco-design/web-vue'
import { useAgentList } from '@/composables/useAgentQueries'
import type { Agent, AgentCreate } from '@akb/shared'
import SkeletonTable from '@/components/common/SkeletonTable.vue'
import { IconPlusCircle, IconEdit, IconDelete, IconLink, IconMessage, IconSearch } from '@arco-design/web-vue/es/icon'

const {
  page,
  size,
  items,
  total,
  isLoading,
  createMutation,
  updateMutation,
  confirmDelete} = useAgentList()

// ── 搜索 ──
const searchText = ref('')
// 暂不支持后端搜索，仅前端过滤
const filteredItems = computed(() => {
  if (!searchText.value.trim()) return items.value
  const keyword = searchText.value.toLowerCase()
  return items.value.filter(
    (a) =>
      a.name.toLowerCase().includes(keyword) ||
      (a.description && a.description.toLowerCase().includes(keyword)),
  )
})

import { computed } from 'vue'

// ── 创建/编辑对话框 ──
const dialogVisible = ref(false)
const editingAgent = ref<Agent | null>(null)
const formData = ref<AgentCreate>({
  name: '',
  description: '',
  knowledge_ids: [],
  prompt_template: ''})
const formLoading = ref(false)

function openCreate() {
  editingAgent.value = null
  formData.value = {
    name: '',
    description: '',
    knowledge_ids: [],
    prompt_template: ''}
  dialogVisible.value = true
}

function openEdit(agent: Agent) {
  editingAgent.value = agent
  formData.value = {
    name: agent.name,
    description: agent.description || '',
    knowledge_ids: [...agent.knowledge_ids],
    prompt_template: agent.prompt_template || ''}
  dialogVisible.value = true
}

async function handleSubmit() {
  if (!formData.value.name.trim()) {
    Message.warning('请输入 Agent 名称')
    return
  }
  if (formData.value.knowledge_ids.length === 0) {
    Message.warning('请至少添加一个知识条目')
    return
  }
  formLoading.value = true
  try {
    if (editingAgent.value) {
      await updateMutation.mutateAsync({
        id: editingAgent.value.id,
        body: formData.value})
    } else {
      await createMutation.mutateAsync(formData.value)
    }
    dialogVisible.value = false
  } finally {
    formLoading.value = false
  }
}

// ── 分享链接复制 ──
function copyShareLink(agentId: string) {
  const link = `http://localhost:5174/chat/${agentId}`
  navigator.clipboard.writeText(link).then(
    () => Message.success('分享链接已复制到剪贴板'),
    () => Message.info(link),
  )
}

// ── 对话测试 ──
function goChat(agentId: string) {
  window.open(`http://localhost:5174/chat/${agentId}`, '_blank')
}

// ── 知识条目 ID 输入 ──
const newId = ref('')
function addKnowledgeId() {
  const trimmed = newId.value.trim()
  if (trimmed && !formData.value.knowledge_ids.includes(trimmed)) {
    formData.value.knowledge_ids.push(trimmed)
  }
  newId.value = ''
}
function removeKnowledgeId(index: number) {
  formData.value.knowledge_ids.splice(index, 1)
}
</script>

<template>
  <div class="list-page">
    <!-- 页面头部 -->
    <div class="list-header">
      <h2 class="list-title">
        Agent 管理
      </h2>
      <a-button
        type="primary"
        @click="openCreate"
      >
        <template #icon>
          <IconPlusCircle />
        </template>
        创建 Agent
      </a-button>
    </div>

    <!-- 搜索栏 -->
    <div class="list-toolbar">
      <a-input
        v-model="searchText"
        placeholder="搜索 Agent 名称..."
        allow-clear
        style="width: 320px"
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
        :cols="5"
      />
      <template v-else>
        <a-table
          v-if="filteredItems.length > 0"
          :data="filteredItems"
          :stripe="true"
        >
          <a-table-column
            data-index="name"
            title="名称"
            :width="150"
          />
          <a-table-column
            data-index="description"
            title="描述"
            :width="200"
            ellipsis
          >
            <template #cell="{ record }">
              {{ record.description || '暂无描述' }}
            </template>
          </a-table-column>
          <a-table-column
            title="关联条目"
            :width="120"
            align="center"
          >
            <template #cell="{ record }">
              <a-tag
                size="small"
                color="arcoblue"
              >
                {{ record.knowledge_ids.length }} 条
              </a-tag>
            </template>
          </a-table-column>
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
            :width="300"
            fixed="right"
          >
            <template #cell="{ record }">
              <a-button
                size="small"
                @click="copyShareLink(record.id)"
              >
                <template #icon>
                  <IconLink />
                </template>
                复制链接
              </a-button>
              <a-button
                size="small"
                @click="goChat(record.id)"
              >
                <template #icon>
                  <IconMessage />
                </template>
                对话测试
              </a-button>
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
          description="暂无 Agent"
        >
          <a-button
            type="primary"
            @click="openCreate"
          >
            <template #icon>
              <IconPlusCircle />
            </template>
            创建第一个 Agent
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
      layout="total, prev, pager, next"
      class="list-pagination"
    />

    <!-- 创建/编辑对话框 -->
    <a-modal
      :visible="dialogVisible"
      :title="editingAgent ? '编辑 Agent' : '创建 Agent'"
      :width="560"
      @cancel="dialogVisible = false"
    >
      <a-form layout="vertical" :model="formData">
        <a-form-item
          label="Agent 名称"
          required
        >
          <a-input
            v-model="formData.name"
            placeholder="例如：客服助手"
            :max-length="255"
          />
        </a-form-item>
        <a-form-item label="描述">
          <a-textarea
            v-model="formData.description"
            :rows="2"
            placeholder="简要描述 Agent 的用途"
          />
        </a-form-item>
        <a-form-item
          label="关联知识条目 ID"
          required
        >
          <div class="id-input-row">
            <a-input
              v-model="newId"
              placeholder="输入 knowledge_item 的 UUID"
              @keyup.enter="addKnowledgeId"
            />
            <a-button @click="addKnowledgeId">
              添加
            </a-button>
          </div>
          <div
            v-if="formData.knowledge_ids.length > 0"
            class="id-tags"
          >
            <a-tag
              v-for="(id, idx) in formData.knowledge_ids"
              :key="id"
              closable
              @close="removeKnowledgeId(idx)"
            >
              {{ id.slice(0, 8) }}...
            </a-tag>
          </div>
          <div
            v-else
            class="id-hint"
          >
            尚未添加任何知识条目
          </div>
        </a-form-item>
        <a-form-item label="系统提示词（可选）">
          <a-textarea
            v-model="formData.prompt_template"
            :rows="4"
            placeholder="留空则自动生成。可使用 {context} 占位符"
          />
        </a-form-item>
      </a-form>
      <template #footer>
        <a-button @click="dialogVisible = false">
          取消
        </a-button>
        <a-button
          type="primary"
          :loading="formLoading"
          @click="handleSubmit"
        >
          {{ editingAgent ? '保存' : '创建' }}
        </a-button>
      </template>
    </a-modal>
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

.id-input-row {
  display: flex;
  gap: 8px;
  margin-bottom: 8px;
}

.id-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.id-hint {
  color: var(--akb-text-secondary);
  font-size: 13px;
}
</style>
