<script setup lang="ts">
/**
 * 用户管理页 ── 列表 + 新建 + 编辑角色 + 删除
 */
import { ref, computed } from 'vue'
import { IconPlusCircle, IconDelete } from '@arco-design/web-vue/es/icon'
import { Message, Modal } from '@arco-design/web-vue'
import { useUserList } from '@/composables/useUserQueries'
import type { UserInfo } from '@akb/shared'

const { users, isLoading, createMutation, updateMutation, deleteMutation } = useUserList()

const creating = computed(() => createMutation.isPending.value)

// ── 新建用户对话框 ──
const createVisible = ref(false)
const createForm = ref({ username: '', password: '', role: 'user' })

async function handleCreate() {
  if (!createForm.value.username || !createForm.value.password) {
    Message.warning('请填写用户名和密码')
    return
  }
  await createMutation.mutateAsync(createForm.value)
  createVisible.value = false
  createForm.value = { username: '', password: '', role: 'user' }
}

// ── 编辑角色 ──
async function handleRoleChange(user: UserInfo, newRole: string) {
  await updateMutation.mutateAsync({ userId: user.id, role: newRole })
}

// ── 删除 ──
function handleDelete(user: UserInfo) {
  Modal.confirm({
    content: `确定删除用户「${user.username}」？其知识库将被一并删除。`,
    title: '删除确认',
    okText: '确定删除',
    cancelText: '取消',
    onOk: () => deleteMutation.mutateAsync(user.id),
    onCancel: () => {},
  })
}

</script>

<template>
  <div class="list-page">
    <div class="list-header">
      <h2>用户管理</h2>
      <a-button
        type="primary"
        @click="createVisible = true"
      >
        <template #icon>
          <IconPlusCircle />
        </template>
        新建用户
      </a-button>
    </div>

    <a-table
      :loading="isLoading"
      :data="users"
      stripe
    >
      <a-table-column
        data-index="username"
        title="用户名"
        :width="160"
      />
      <a-table-column
        title="角色"
        :width="160"
      >
        <template #cell="{ record }">
          <a-select
            :model-value="record.role"
            :disabled="record.username === 'admin'"
            size="small"
            @change="(val) => handleRoleChange(record, val as string)"
          >
            <a-option
              label="超级管理员"
              value="super_admin"
            />
            <a-option
              label="普通用户"
              value="user"
            />
          </a-select>
        </template>
      </a-table-column>
      <a-table-column
        title="注册时间"
        :width="180"
      >
        <template #cell="{ record }">
          {{ new Date(record.created_at).toLocaleString('zh-CN') }}
        </template>
      </a-table-column>
      <a-table-column
        title="操作"
        :width="100"
        fixed="right"
      >
        <template #cell="{ record }">
          <a-button
            size="small"
            status="danger"
            :disabled="record.username === 'admin'"
            @click="handleDelete(record)"
          >
            <template #icon>
              <IconDelete />
            </template>
            删除
          </a-button>
        </template>
      </a-table-column>
    </a-table>

    <!-- 新建用户弹窗 -->
    <a-modal
      :visible="createVisible"
      title="新建用户"
      :width="420"
      @cancel="createVisible = false"
    >
      <a-form
        :model="createForm"
        label-width="80px"
      >
        <a-form-item label="用户名">
          <a-input
            v-model="createForm.username"
            placeholder="3-100 字符"
          />
        </a-form-item>
        <a-form-item label="密码">
          <a-input
            v-model="createForm.password"
            type="password"
            placeholder="至少 6 位"
          />
        </a-form-item>
        <a-form-item label="角色">
          <a-select v-model="createForm.role">
            <a-option
              label="普通用户"
              value="user"
            />
            <a-option
              label="超级管理员"
              value="super_admin"
            />
          </a-select>
        </a-form-item>
      </a-form>
      <template #footer>
        <a-button @click="createVisible = false">
          取消
        </a-button>
        <a-button
          type="primary"
          :loading="creating"
          @click="handleCreate"
        >
          创建
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

.list-header h2 {
  margin: 0;
  font-size: 18px;
  font-weight: 600;
}
</style>
