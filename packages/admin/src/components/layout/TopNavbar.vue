<script setup lang="ts">
import { IconUp, IconDown, IconSwap } from '@arco-design/web-vue/es/icon'
import { useAppStore } from '@/stores/app'
import { useUserStore } from '@/stores/user'

const appStore = useAppStore()
const userStore = useUserStore()

function handleLogout() {
  userStore.logout()
}
</script>

<template>
  <div class="top-navbar">
    <div class="top-navbar-left">
      <IconUp
        v-if="appStore.sidebarCollapsed"
        class="collapse-btn"
        :size="20"
        @click="appStore.toggleSidebar"
      />
      <IconDown
        v-else
        class="collapse-btn"
        :size="20"
        @click="appStore.toggleSidebar"
      />
    </div>

    <div class="top-navbar-right">
      <a-dropdown trigger="click">
        <span class="user-info">
          <a-avatar :size="32">
            <template #icon><IconSwap /></template>
          </a-avatar>
          <span class="user-name">{{ userStore.userInfo?.username || '管理员' }}</span>
          <IconDown class="dropdown-icon" />
        </span>
        <template #content>
          <a-doption @click="handleLogout">
            <template #icon>
              <IconSwap />
            </template>
            退出登录
          </a-doption>
        </template>
      </a-dropdown>
    </div>
  </div>
</template>

<style scoped>
.top-navbar {
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 20px;
}

.collapse-btn {
  cursor: pointer;
  color: var(--akb-text);
  transition: color 0.2s;
}

.collapse-btn:hover {
  color: var(--akb-primary);
}

.top-navbar-right {
  display: flex;
  align-items: center;
}

.user-info {
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
  padding: 4px 8px;
  border-radius: var(--akb-btn-radius);
  transition: background 0.2s;
}

.user-info:hover {
  background: #f0f2f5;
}

.user-name {
  font-size: 14px;
  color: var(--akb-text);
  max-width: 160px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.dropdown-icon {
  color: var(--akb-text-secondary);
  font-size: 12px;
}
</style>
