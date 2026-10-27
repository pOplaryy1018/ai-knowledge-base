<script setup lang="ts">
import { useAppStore } from '@/stores/app'
import TopNavbar from '@/components/layout/TopNavbar.vue'
import SidebarMenu from '@/components/layout/SidebarMenu.vue'
import BreadcrumbNav from '@/components/layout/BreadcrumbNav.vue'
import { useUserStore } from '@/stores/user'
import { listSources, downloadCitationOriginal } from '@/api/sources'
import { scopedChatSSE } from '@/api/scoped-chat'
import TaotaoAssistant from '../../../shared/src/components/TaotaoAssistant.vue'

const appStore = useAppStore()
const userStore = useUserStore()
</script>

<template>
  <a-layout class="layout-container">
    <!-- 顶部导航 -->
    <a-layout-header
      height="60px"
      class="layout-header"
    >
      <TopNavbar />
    </a-layout-header>

    <a-layout class="layout-body">
      <!-- 侧边栏 -->
      <a-layout-sider
        :width="appStore.sidebarCollapsed ? 64 : 220"
        class="layout-aside"
      >
        <SidebarMenu />
      </a-layout-sider>

      <!-- 内容区 -->
      <a-layout-content class="layout-main">
        <BreadcrumbNav class="layout-breadcrumb" />
        <router-view v-slot="{ Component }">
          <transition
            name="page-fade"
            mode="out-in"
          >
            <component :is="Component" />
          </transition>
        </router-view>
      </a-layout-content>
    </a-layout>
    <TaotaoAssistant
      :generation="userStore.generation"
      :get-sources="listSources"
      :ask="scopedChatSSE"
      :open-original="downloadCitationOriginal"
      sources-path="/admin/knowledge-bases"
      sources-label="前往知识库管理"
    />
  </a-layout>
</template>

<style scoped>
.layout-container {
  height: 100vh;
  background: var(--akb-bg);
}

.layout-header {
  background: var(--akb-header-bg);
  border-bottom: 1px solid var(--akb-line);
  padding: 0;
  flex-shrink: 0;
}

.layout-body {
  flex: 1;
  overflow: hidden;
}

.layout-aside {
  background-color: var(--akb-sidebar-bg);
  border-right: 1px solid var(--akb-line);
  transition: width 0.3s;
  overflow: hidden;
}

.layout-main {
  background-color: var(--akb-bg);
  background-image: linear-gradient(#a28ab009 1px, transparent 1px), linear-gradient(90deg, #a28ab009 1px, transparent 1px);
  background-size: 40px 40px;
  padding: 28px;
  overflow-y: auto;
}

.layout-breadcrumb {
  margin-bottom: 22px;
}
@media (max-width: 760px) {
  .layout-body { flex-direction: column; }
  .layout-aside { width: 100% !important; flex: none !important; height: 112px; border-right: 0; border-bottom: 1px solid var(--akb-line); }
  .layout-main { padding: 16px 12px 76px; }
}
</style>
