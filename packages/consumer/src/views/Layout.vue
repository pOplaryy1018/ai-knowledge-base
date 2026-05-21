<script setup lang="ts">
import { useRouter, useRoute } from 'vue-router'
import { useUserStore } from '@/stores/user'

const router = useRouter()
const route = useRoute()
const store = useUserStore()

const isActive = (path: string) => route.path.startsWith(path)

function handleLogout() {
  store.logout()
}
</script>

<template>
  <div class="workspace-layout">
    <aside class="workspace-sidebar">
      <div class="sidebar-brand">
        AI 知识助手
      </div>

      <nav class="sidebar-nav">
        <div
          :class="['nav-item', { active: isActive('/workspace/knowledge-bases') }]"
          @click="router.push('/workspace/knowledge-bases')"
        >
          📚 知识库
        </div>
        <div
          :class="['nav-item', { active: isActive('/workspace/chat') }]"
          @click="router.push('/workspace/chat')"
        >
          💬 AI 问答
        </div>
      </nav>

      <div class="sidebar-footer">
        <a-button
          type="text"
          @click="handleLogout"
        >
          退出登录
        </a-button>
      </div>
    </aside>

    <main class="workspace-main">
      <router-view />
    </main>
  </div>
</template>

<style scoped>
.workspace-layout {
  height: 100vh;
  display: flex;
  background: var(--color-bg);
  overflow: hidden;
}

.workspace-sidebar {
  width: 220px;
  min-width: 220px;
  background: var(--color-bg-card);
  border-right: 1px solid var(--border-color);
  display: flex;
  flex-direction: column;
}

.sidebar-brand {
  padding: 20px 16px;
  font-size: 16px;
  font-weight: 600;
  color: var(--color-text-primary);
  border-bottom: 1px solid var(--color-bg-card-alt);
}

.sidebar-nav {
  flex: 1;
  padding: 12px 8px;
}

.nav-item {
  padding: 10px 12px;
  border-radius: 8px;
  cursor: pointer;
  font-size: 14px;
  color: var(--color-text-secondary);
  transition: all 0.15s;
  margin-bottom: 2px;
  user-select: none;
}

.nav-item:hover {
  background: var(--color-primary-light);
}

.nav-item.active {
  background: var(--color-primary-light);
  color: var(--color-primary);
  font-weight: 500;
}

.sidebar-footer {
  padding: 12px 16px;
  border-top: 1px solid var(--color-bg-card-alt);
}

.workspace-main {
  flex: 1;
  overflow-y: auto;
  padding: 20px;
}
</style>
