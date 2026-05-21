<script setup lang="ts">
import { useAppStore } from '@/stores/app'
import TopNavbar from '@/components/layout/TopNavbar.vue'
import SidebarMenu from '@/components/layout/SidebarMenu.vue'
import BreadcrumbNav from '@/components/layout/BreadcrumbNav.vue'

const appStore = useAppStore()
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
  </a-layout>
</template>

<style scoped>
.layout-container {
  height: 100vh;
}

.layout-header {
  background: var(--akb-header-bg);
  border-bottom: 1px solid #e6e6e6;
  padding: 0;
  flex-shrink: 0;
}

.layout-body {
  flex: 1;
  overflow: hidden;
}

.layout-aside {
  background-color: var(--akb-sidebar-bg);
  transition: width 0.3s;
  overflow: hidden;
}

.layout-main {
  background-color: var(--akb-bg);
  padding: 20px;
  overflow-y: auto;
}

.layout-breadcrumb {
  margin-bottom: 16px;
}
</style>
