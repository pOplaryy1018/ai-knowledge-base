/**
 * 用户状态管理 (Pinia) ── token 持久化、登录/登出、用户信息
 */

import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { UserInfo } from '@akb/shared'
import { login as loginApi, getMe } from '@/api/auth'
import { setupApiClient } from '@/api/client'
import router from '@/router'
import { queryClient } from '@/queryClient'

const TOKEN_KEY = 'akb_access_token'
const REFRESH_KEY = 'akb_refresh_token'

export const useUserStore = defineStore('user', () => {
  // ── 状态 ──
  const accessToken = ref<string | null>(localStorage.getItem(TOKEN_KEY))
  const refreshTokenValue = ref<string | null>(localStorage.getItem(REFRESH_KEY))
  const userInfo = ref<UserInfo | null>(null)
  const loading = ref(false)
  const generation = ref(0)

  // ── 计算属性 ──
  const isLoggedIn = computed(() => !!accessToken.value)
  const isAdmin = computed(() => userInfo.value?.role === 'super_admin')
  const role = computed(() => userInfo.value?.role || null)

  // ── 初始化客户端依赖 ──
  setupApiClient({
    getGeneration: () => generation.value,
    getToken: () => accessToken.value,
    onUnauthorized: () => {
      clearAuth()
      router.push('/login')
    },
    getRefreshToken: () => refreshTokenValue.value,
    onTokenRefreshed: (token: string) => {
      accessToken.value = token
      localStorage.setItem(TOKEN_KEY, token)
    }})

  // ── 内部方法 ──
  function saveTokens(access: string, refresh: string) {
    clearAuth()
    accessToken.value = access
    refreshTokenValue.value = refresh
    localStorage.setItem(TOKEN_KEY, access)
    localStorage.setItem(REFRESH_KEY, refresh)
  }

  function clearAuth() {
    generation.value++
    void queryClient.cancelQueries()
    queryClient.clear()
    accessToken.value = null
    refreshTokenValue.value = null
    userInfo.value = null
    localStorage.removeItem(TOKEN_KEY)
    localStorage.removeItem(REFRESH_KEY)
  }

  // ── 公开方法 ──

  /** 登录：调用 API，存储 token，拉取用户信息 */
  async function login(username: string, password: string) {
    loading.value = true
    const requestGeneration = generation.value
    try {
      const res = await loginApi({ username, password })
      if (requestGeneration !== generation.value) return
      if (res.user.role !== 'super_admin') throw new Error('此账号没有管理权限')
      saveTokens(res.access_token, res.refresh_token)
      userInfo.value = res.user
      return res
    } finally {
      loading.value = false
    }
  }

  /** 登出：清除 token，跳转登录页 */
  function logout() {
    clearAuth()
    router.push('/login')
  }

  /** 拉取当前用户信息（用于页面刷新后恢复） */
  async function fetchUser() {
    if (!accessToken.value) return
    loading.value = true
    const requestGeneration = generation.value
    try {
      const user = await getMe()
      if (requestGeneration !== generation.value) return
      userInfo.value = user
    } catch {
      // token 失效则清理
      if (requestGeneration === generation.value) clearAuth()
    } finally {
      loading.value = false
    }
  }

  return {
    generation, accessToken,
    refreshTokenValue,
    userInfo,
    loading,
    isLoggedIn,
    isAdmin,
    role,
    login,
    logout,
    fetchUser,
    clearAuth}
})
