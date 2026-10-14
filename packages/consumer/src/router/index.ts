/**
 * 路由配置 ── 消费者端：知识库工作台 + AI 问答
 */

import { createRouter, createWebHistory } from 'vue-router'
import type { RouteRecordRaw } from 'vue-router'
import { useUserStore } from '@/stores/user'

const routes: RouteRecordRaw[] = [
  {
    path: '/login',
    name: 'Login',
    component: () => import('@/views/Login.vue'),
    meta: { title: '登录', guest: true },
  },
  {
    path: '/register',
    name: 'Register',
    component: () => import('@/views/Register.vue'),
    meta: { title: '注册', guest: true },
  },
  {
    path: '/workspace',
    component: () => import('@/views/Layout.vue'),
    redirect: '/workspace/knowledge-bases',
    meta: { requiresAuth: true },
    children: [
      {
        path: 'wiki',
        name: 'WikiWorkbench',
        component: () => import('@/views/wiki/WikiWorkbench.vue'),
        meta: { title: 'LLM Wiki' },
      },
      {
        path: 'wiki/:id',
        name: 'WikiDetail',
        component: () => import('@/views/wiki/WikiDetail.vue'),
        meta: { title: 'Wiki 页面' },
      },
      {
        path: 'knowledge-bases',
        name: 'KnowledgeBaseList',
        component: () => import('@/views/knowledge/KnowledgeBaseList.vue'),
        meta: { title: '知识库' },
      },
      {
        path: 'knowledge-bases/:kbId',
        name: 'KnowledgeBaseDetail',
        component: () => import('@/views/knowledge/KnowledgeBaseDetail.vue'),
        meta: { title: '知识库详情' },
      },
      {
        path: 'chat',
        name: 'Chat',
        component: () => import('@/views/ChatView.vue'),
        meta: { title: 'Agent 问答' },
      },
      {
        path: 'sources',
        name: 'Sources',
        component: () => import('@/views/sources/SourceWorkspace.vue'),
        meta: { title: '资料来源' },
      },
      {
        path: 'personal-chat',
        name: 'PersonalChat',
        component: () => import('@/views/ScopedChatView.vue'),
        meta: { title: '个人资料问答' },
      },
      {
        path: 'answers',
        name: 'SavedAnswers',
        component: () => import('@/views/answers/SavedAnswers.vue'),
        meta: { title: '已保存答案' },
      },
      {
        path: 'answers/:id',
        name: 'AnswerDetail',
        component: () => import('@/views/answers/AnswerDetail.vue'),
        meta: { title: '答案详情' },
      },
      {
        path: 'reviews/:id',
        name: 'ReviewDetail',
        component: () => import('@/views/answers/ReviewDetail.vue'),
        meta: { title: '答案复核' },
      },
    ],
  },
  {
    path: '/',
    redirect: '/workspace/knowledge-bases',
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

router.beforeEach(async (to, _from, next) => {
  const store = useUserStore()

  // token 存在但用户信息未加载 → 恢复会话
  if (store.accessToken && !store.userInfo) {
    await store.fetchUser()
  }

  if (to.meta.guest && store.isLoggedIn) {
    return next('/workspace/knowledge-bases')
  }

  if (to.meta.requiresAuth && !store.isLoggedIn) {
    return next(`/login?redirect=${encodeURIComponent(to.fullPath)}`)
  }

  next()
})

router.afterEach((to) => {
  const title = to.meta.title as string | undefined
  document.title = title ? `${title} — AI 知识助手` : 'AI 知识助手'
})

export default router
