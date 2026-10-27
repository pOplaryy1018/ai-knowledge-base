<script setup lang="ts">
import { useRoute } from 'vue-router'
import { useAppStore } from '@/stores/app'

const route = useRoute()
const appStore = useAppStore()
const groups = [
  { label: '01 / 总览', items: [{ path: '/admin/dashboard', title: '管理工作台', number: '01' }, { path: '/admin/statistics', title: '统计面板', number: '02' }] },
  { label: '02 / 内容与服务', items: [{ path: '/admin/knowledge-bases', title: '知识库管理', number: '03' }, { path: '/admin/files', title: '文件管理', number: '04' }, { path: '/admin/agents', title: 'Agent 管理', number: '05' }] },
  { label: '03 / 系统', items: [{ path: '/admin/users', title: '用户管理', number: '06' }] },
]
</script>

<template>
  <div
    class="sidebar-menu"
    :class="{ collapsed: appStore.sidebarCollapsed }"
  >
    <router-link
      class="sidebar-logo"
      to="/admin/dashboard"
      :title="appStore.sidebarCollapsed ? 'AKB 管理端' : undefined"
    >
      <span
        class="brand-mark"
        aria-hidden="true"
      />
      <span v-if="!appStore.sidebarCollapsed">AKB / ARCHIVE<small>SYSTEM OPERATIONS</small></span>
    </router-link>
    <nav
      class="sidebar-nav"
      aria-label="管理端导航"
    >
      <section
        v-for="group in groups"
        :key="group.label"
        class="nav-group"
      >
        <div
          v-if="!appStore.sidebarCollapsed"
          class="nav-label"
        >
          {{ group.label }}
        </div>
        <router-link
          v-for="item in group.items"
          :key="item.path"
          :to="item.path"
          class="nav-item"
          :class="{ active: route.path === item.path }"
          :title="appStore.sidebarCollapsed ? item.title : undefined"
          :aria-current="route.path === item.path ? 'page' : undefined"
        >
          <span class="nav-number">{{ item.number }}</span><span v-if="!appStore.sidebarCollapsed">{{ item.title }}</span>
        </router-link>
      </section>
    </nav>
    <div
      v-if="!appStore.sidebarCollapsed"
      class="sidebar-foot"
    >
      ADMIN / CONTROL<br>资料权限仍由服务端核验
    </div>
  </div>
</template>

<style scoped>
.sidebar-menu { height: 100%; display: flex; flex-direction: column; background: var(--akb-sidebar-bg); color: var(--akb-text-secondary); }
.sidebar-logo { height: 72px; display: flex; align-items: center; gap: 12px; padding: 17px; text-decoration: none; color: var(--akb-text); font-size: 13px; font-weight: 800; letter-spacing: .04em; white-space: nowrap; }
.sidebar-logo small { display: block; color: var(--akb-text-muted); font: 11px Consolas, monospace; letter-spacing: .1em; margin-top: 4px; }
.brand-mark { display: block; flex: none; width: 24px; height: 24px; border: 2px solid var(--akb-primary); transform: skew(-14deg); box-shadow: 7px 7px 0 -3px var(--akb-warning); }
.sidebar-nav { padding: 0 11px; overflow: auto; flex: 1; }
.nav-group { border-top: 1px solid #3b3444; padding: 9px 0; }
.nav-label { padding: 5px 10px 9px; color: var(--akb-text-muted); font: 11px Consolas, monospace; letter-spacing: .14em; }
.nav-item { display: flex; align-items: center; gap: 11px; min-height: 43px; padding: 9px 12px; text-decoration: none; color: var(--akb-text-secondary); font-size: 12px; }
.nav-item:hover { background: #292032; color: var(--akb-text); }
.nav-item.active { background: var(--akb-primary); color: #25182e; font-weight: 800; clip-path: polygon(0 0, calc(100% - 10px) 0, 100% 10px, 100% 100%, 0 100%); }
.nav-number { color: #a58bb8; font: 11px Consolas, monospace; }.nav-item.active .nav-number { color: #614778; }
.sidebar-foot { margin: auto 18px 20px; border-top: 1px solid #3b3444; padding-top: 12px; font: 11px Consolas, monospace; line-height: 1.7; color: var(--akb-text-muted); }
.collapsed .sidebar-logo { padding: 17px; }.collapsed .sidebar-nav { padding: 0 6px; }.collapsed .nav-item { justify-content: center; padding: 9px; }
@media (max-width: 760px) {
  .sidebar-logo { height: 52px; padding: 10px 14px; }
  .sidebar-nav { display: flex; gap: 4px; overflow-x: auto; padding: 0 8px; }
  .nav-group { display: flex; align-items: center; border: 0; padding: 0; }
  .nav-label, .sidebar-foot { display: none; }
  .nav-item { white-space: nowrap; }
}
</style>
