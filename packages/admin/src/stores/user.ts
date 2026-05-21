/**
 * 用户状态管理 (Pinia) ── token 持久化、登录/登出、用户信息
 */

import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { UserInfo } from '@akb/shared'
import { login as loginApi, getMe } from '@/api/auth'
import { setupApiClient } from '@/api/client'
import router from '@/router'

const TOKEN_KEY = 'akb_access_token'
const REFRESH_KEY = 'akb_refresh_token'

export const useUserStore = defineStore('user', () => {
  // ── 状态 ──
  const accessToken = ref<string | null>(localStorage.getItem(TOKEN_KEY))
  const refreshTokenValue = ref<string | null>(localStorage.getItem(REFRESH_KEY))
  const userInfo = ref<UserInfo | null>(null)
  const loading = ref(false)

  // ── 计算属性 ──
  const isLoggedIn = computed(() => !!accessToken.value)
  const isAdmin = computed(() => userInfo.value?.role === 'super_admin')
  const role = computed(() => userInfo.value?.role || null)

  // ── 初始化客户端依赖 ──
  setupApiClient({
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
    accessToken.value = access
    refreshTokenValue.value = refresh
    localStorage.setItem(TOKEN_KEY, access)
    localStorage.setItem(REFRESH_KEY, refresh)
  }

  function clearAuth() {
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
    try {
      const res = await loginApi({ username, password })
      saveTokens(res.access_token, res.refresh_token)
      userInfo.value = res.user
      // 登录后立即让客户端获取新 token
      setupApiClient({
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
    try {
      const user = await getMe()
      userInfo.value = user
    } catch {
      // token 失效则清理
      clearAuth()
    } finally {
      loading.value = false
    }
  }

  return {
    accessToken,
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
