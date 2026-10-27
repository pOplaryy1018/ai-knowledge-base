<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { useUserStore } from '@/stores/user'
import type { SourceCitation } from '@akb/shared'
import { listSources, downloadOriginal } from '@/api/sources'
import { scopedChatSSE } from '@/api/scoped-chat'
import TaotaoAssistant from '../../../shared/src/components/TaotaoAssistant.vue'

const route = useRoute()
const store = useUserStore()
const currentTitle = computed(() => String(route.meta.title || '工作区'))
const groups = [
  { label: '01 / 资料', items: [
    { path: '/workspace/knowledge-bases', title: '知识库', number: '01' },
    { path: '/workspace/sources', title: '资料来源', number: '02' },
  ] },
  { label: '02 / 问答', items: [
    { path: '/workspace/personal-chat', title: '个人资料问答', number: '03' },
    { path: '/workspace/chat', title: 'Agent 问答', number: '04' },
  ] },
  { label: '03 / 成果', items: [
    { path: '/workspace/answers', title: '已保存答案与复核', number: '05' },
    { path: '/workspace/wiki', title: 'Wiki 档案', number: '06' },
  ] },
]
function isActive(path: string) {
  if (path.endsWith('/answers')) return route.path.startsWith('/workspace/answers') || route.path.startsWith('/workspace/reviews')
  return route.path.startsWith(path)
}
function openAssistantOriginal(citation: SourceCitation) {
  return downloadOriginal(citation.source_id, citation.revision_id, '引用原件')
}
</script>

<template>
  <div class="workspace-layout akb-tactical-surface">
    <aside
      class="workspace-sidebar"
      aria-label="用户端导航"
    >
      <router-link
        class="sidebar-brand"
        to="/workspace/knowledge-bases"
      >
        <span
          class="brand-mark"
          aria-hidden="true"
        />
        <span>AKB / ARCHIVE<small>PERSONAL KNOWLEDGE</small></span>
      </router-link>
      <nav
        class="sidebar-nav"
        aria-label="工作区导航"
      >
        <div
          v-for="group in groups"
          :key="group.label"
          class="nav-group"
        >
          <div class="nav-label">
            {{ group.label }}
          </div>
          <router-link
            v-for="item in group.items"
            :key="item.path"
            :to="item.path"
            class="nav-item"
            :class="{ active: isActive(item.path) }"
            :aria-current="isActive(item.path) ? 'page' : undefined"
          >
            <span>{{ item.number }}</span>{{ item.title }}
          </router-link>
        </div>
      </nav>
      <div class="sidebar-footer">
        <div class="assistant-status">
          韬韬 / KNOWLEDGE ASSISTANT
        </div>
        <p>从资料中寻找答案，保留原文版本与位置。</p>
        <button
          type="button"
          class="logout"
          @click="store.logout()"
        >
          退出登录 ↗
        </button>
      </div>
    </aside>
    <div class="workspace-body">
      <header class="workspace-topbar">
        <div class="breadcrumb">
          USER SPACE <span>/</span> WORKSPACE <span>/</span> <strong>{{ currentTitle }}</strong>
        </div>
        <div class="topbar-right">
          <span>{{ store.userInfo?.username || '用户' }}</span><router-link to="/workspace/sources">
            资料来源 ↗
          </router-link>
        </div>
      </header>
      <main class="workspace-main">
        <router-view />
      </main>
    </div>
    <TaotaoAssistant
      :generation="store.generation"
      :get-sources="listSources"
      :ask="scopedChatSSE"
      :open-original="openAssistantOriginal"
      sources-path="/workspace/sources"
      sources-label="前往资料来源"
    />
  </div>
</template>

<style scoped>
.workspace-layout { min-height: 100vh; height: 100vh; display: grid; grid-template-columns: 226px minmax(0, 1fr); overflow: hidden; }
.workspace-sidebar { display: flex; flex-direction: column; min-width: 0; background: var(--akb-sidebar-bg); border-right: 1px solid var(--akb-line); }
.sidebar-brand { display: flex; align-items: center; gap: 12px; min-height: 72px; padding: 18px; color: var(--akb-text); text-decoration: none; font-size: 14px; font-weight: 800; letter-spacing: .05em; }
.sidebar-brand small { display: block; color: var(--akb-text-muted); font: 11px Consolas, monospace; letter-spacing: .1em; margin-top: 4px; }
.brand-mark { flex: none; width: 24px; height: 24px; border: 2px solid var(--akb-primary); transform: skew(-14deg); box-shadow: 7px 7px 0 -3px var(--akb-warning); }
.sidebar-nav { min-height: 0; overflow: auto; flex: 1; padding: 0 11px; }
.nav-group { border-top: 1px solid #3b3444; padding: 10px 0; }
.nav-label { padding: 5px 10px 8px; color: var(--akb-text-muted); font: 11px Consolas, monospace; letter-spacing: .15em; }
.nav-item { display: flex; align-items: center; gap: 10px; min-height: 42px; margin: 2px 0; padding: 8px 12px; color: var(--akb-text-secondary); text-decoration: none; font-size: 12px; }
.nav-item span { width: 20px; flex: none; color: #a58bb8; font: 11px Consolas, monospace; }
.nav-item:hover { background: #292032; color: var(--akb-text); }
.nav-item.active { background: var(--akb-primary); color: #26182f; font-weight: 800; clip-path: polygon(0 0, calc(100% - 10px) 0, 100% 10px, 100% 100%, 0 100%); }
.nav-item.active span { color: #5d4173; }
.sidebar-footer { margin: auto 17px 18px; border-top: 1px solid #3b3444; padding-top: 16px; color: var(--akb-text-muted); }
.assistant-status { color: #e1d2ee; font: 11px Consolas, monospace; }
.sidebar-footer p { margin: 8px 0 12px; font-size: 12px; line-height: 1.6; }
.logout { border: 0; background: transparent; padding: 0; color: var(--akb-text-secondary); font-size: 12px; }
.logout:hover { color: var(--akb-primary); }
.workspace-body { min-width: 0; display: flex; flex-direction: column; }
.workspace-topbar { height: 60px; flex: none; display: flex; justify-content: space-between; align-items: center; gap: 16px; padding: 0 26px; background: var(--akb-header-bg); border-bottom: 1px solid var(--akb-line); }
.breadcrumb { color: var(--akb-text-secondary); font: 11px Consolas, monospace; letter-spacing: .06em; }
.breadcrumb span { margin: 0 7px; color: #7c6a8c; }.breadcrumb strong { color: var(--akb-text); }
.topbar-right { display: flex; gap: 18px; align-items: center; white-space: nowrap; font-size: 12px; color: var(--akb-text-secondary); }
.topbar-right a { text-decoration: none; }
.workspace-main { min-width: 0; min-height: 0; flex: 1; overflow: auto; padding: 28px; }
:deep(.workspace-main h2) { color: var(--akb-text); font-size: clamp(25px, 3vw, 34px); letter-spacing: -.045em; }
@media (max-width: 760px) { .workspace-layout { display: flex; flex-direction: column; }.workspace-sidebar { flex: none; border-right: 0; border-bottom: 1px solid var(--akb-line); }.sidebar-brand { min-height: 50px; padding: 11px 16px; }.sidebar-nav { display: flex; overflow-x: auto; padding: 0 8px 7px; }.nav-group { display: flex; align-items: center; border: 0; padding: 0; }.nav-label, .sidebar-footer { display: none; }.nav-item { white-space: nowrap; margin: 0 2px; padding: 8px 10px; }.workspace-body { flex: 1; min-height: 0; }.workspace-topbar { height: 44px; padding: 0 12px; }.topbar-right { display: none; }.workspace-main { padding: 16px 12px 76px; } }
</style>
