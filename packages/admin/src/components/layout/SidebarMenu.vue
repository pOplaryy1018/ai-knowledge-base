<script setup lang="ts">
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAppStore } from '@/stores/app'
import { IconDashboard, IconFolder, IconRobot, IconBarChart, IconUser, IconBook } from '@arco-design/web-vue/es/icon'

const route = useRoute()
const router = useRouter()
const appStore = useAppStore()

interface MenuItem {
  path: string
  title: string
  icon: string
}

const iconMap: Record<string, any> = {
  Odometer: IconDashboard,
  Collection: IconFolder,
  Service: IconRobot,
  DataAnalysis: IconBarChart,
  FolderOpened: IconFolder,
  User: IconUser}

const menuItems = computed<MenuItem[]>(() => {
  const adminRoute = router.options.routes.find((r) => r.path === '/admin')
  if (!adminRoute || !adminRoute.children) return []

  return adminRoute.children
    .filter((child) => !child.meta?.hidden)
    .map((child) => ({
      path: `/admin/${child.path}`,
      title: (child.meta?.title as string) || child.path,
      icon: (child.meta?.icon as string) || 'Collection'}))
})

const activeMenu = computed(() => route.path)
</script>

<template>
  <div class="sidebar-menu">
    <div class="sidebar-logo">
      <IconBook
        :size="22"
        :stroke-width="2"
        class="logo-icon"
        style="color:#fff"
      />
      <span
        class="logo-text"
        :class="{ collapsed: appStore.sidebarCollapsed }"
      >
        {{ appStore.sidebarCollapsed ? 'AI' : 'AI 知识库' }}
      </span>
    </div>

    <a-menu
      :default-active="activeMenu"
      :collapsed="appStore.sidebarCollapsed"
      background-color="#304156"
      text-color="#bfcbd9"
      active-text-color="#409eff"
      class="sidebar-el-menu"
      @menu-item-click="(key: string) => router.push(key)"
    >
      <a-menu-item
        v-for="item in menuItems"
        :key="item.path"
      >
        <template #icon>
          <component :is="iconMap[item.icon]" />
        </template>
        <span>{{ item.title }}</span>
      </a-menu-item>
    </a-menu>
  </div>
</template>

<style scoped>
.sidebar-menu {
  height: 100%;
  display: flex;
  flex-direction: column;
  background-color: var(--akb-sidebar-bg);
}

.sidebar-logo {
  height: var(--akb-header-height);
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.08);
  flex-shrink: 0;
}

.logo-icon {
  flex-shrink: 0;
}

.logo-text {
  font-size: 20px;
  font-weight: 700;
  color: #fff;
  white-space: nowrap;
  transition: font-size 0.3s;
}

.logo-text.collapsed {
  display: none;
}

.sidebar-el-menu {
  border-right: none;
  flex: 1;
  overflow-y: auto;
}
</style>
