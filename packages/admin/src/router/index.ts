/**
 * 路由配置 — Layout 作为父路由包裹管理页面，Login 保持独立
 */
import { createRouter, createWebHistory } from 'vue-router'
import type { RouteRecordRaw } from 'vue-router'
import { useUserStore } from '@/stores/user'

const routes: RouteRecordRaw[] = [
  // ── 登录页（独立，无 Layout 外壳）──
  {
    path: '/login',
    name: 'Login',
    component: () => import('@/views/Login.vue'),
    meta: { title: '登录', guest: true }},

  // ── 管理后台（Layout 父路由）──
  {
    path: '/admin',
    component: () => import('@/views/Layout.vue'),
    redirect: '/admin/dashboard',
    meta: { requiresAuth: true, roles: ['super_admin'] },
    children: [
      {
        path: 'dashboard',
        name: 'Dashboard',
        component: () => import('@/views/Dashboard.vue'),
        meta: { title: '工作台', icon: 'Odometer' }},
      {
        path: 'users',
        name: 'UserList',
        component: () => import('@/views/UserList.vue'),
        meta: { title: '用户管理', icon: 'User' }},
      {
        path: 'knowledge-bases',
        name: 'KnowledgeBaseList',
        component: () => import('@/views/knowledge/KnowledgeBaseList.vue'),
        meta: { title: '知识库管理', icon: 'Collection' }},
      {
        path: 'agents',
        name: 'AgentList',
        component: () => import('@/views/agent/AgentList.vue'),
        meta: { title: 'Agent 管理', icon: 'Service' }},
      {
        path: 'files',
        name: 'FileManagement',
        component: () => import('@/views/knowledge/FileManagement.vue'),
        meta: { title: '文件管理', icon: 'FolderOpened' }},
      {
        path: 'statistics',
        name: 'Statistics',
        component: () => import('@/views/Statistics.vue'),
        meta: { title: '统计面板', icon: 'DataAnalysis' }},
    ]},

  // ── 根路径重定向 ──
  {
    path: '/',
    redirect: '/admin/dashboard'},
]

const router = createRouter({
  history: createWebHistory(),
  routes})

// ── 全局前置守卫 ──
router.beforeEach(async (to, _from, next) => {
  const userStore = useUserStore()

  // ① token 存在但用户信息未加载 → 拉取用户信息
  if (userStore.accessToken && !userStore.userInfo) {
    await userStore.fetchUser()
  }

  // ② 已登录访问登录页 → 重定向到管理后台
  if (to.meta.guest && userStore.isLoggedIn) {
    return next('/admin/dashboard')
  }

  // ③ 未登录访问受保护页面 → 重定向到登录页
  if (to.meta.requiresAuth && !userStore.isLoggedIn) {
    return next('/login')
  }

  // ④ 角色不匹配 → 重定向到工作台
  if (to.meta.roles && userStore.role) {
    const allowed = to.meta.roles as string[]
    if (!allowed.includes(userStore.role)) {
      return next('/admin/dashboard')
    }
  }

  next()
})

// ── 页面标题更新 ──
router.afterEach((to) => {
  const title = to.meta.title as string | undefined
  document.title = title ? `${title} — AI 知识库` : 'AI 知识库管理平台'
})

export default router
