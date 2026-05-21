/**
 * 用户认证状态管理 (Pinia) ── token 持久化、登录/登出
 */
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { UserInfo, LoginResponse } from '@akb/shared'
import { getApiClient, setupApiClient } from '@/api/client'
import router from '@/router'

const TOKEN_KEY = 'akb_access_token'
const REFRESH_KEY = 'akb_refresh_token'

export const useUserStore = defineStore('user', () => {
  const accessToken = ref<string | null>(localStorage.getItem(TOKEN_KEY))
  const refreshTokenValue = ref<string | null>(localStorage.getItem(REFRESH_KEY))
  const userInfo = ref<UserInfo | null>(null)
  const loading = ref(false)

  const isLoggedIn = computed(() => !!accessToken.value)

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

  async function login(username: string, password: string) {
    loading.value = true
    try {
      const { data } = await getApiClient().post<LoginResponse>('/auth/login', { username, password })
      saveTokens(data.access_token, data.refresh_token)
      userInfo.value = data.user
      setupApiClient({
        getToken: () => accessToken.value,
        onUnauthorized: () => { clearAuth(); router.push('/login') },
        getRefreshToken: () => refreshTokenValue.value,
        onTokenRefreshed: (token: string) => {
          accessToken.value = token
          localStorage.setItem(TOKEN_KEY, token)
        }})
      return data
    } finally {
      loading.value = false
    }
  }

  function logout() {
    clearAuth()
    router.push('/login')
  }

  async function fetchUser() {
    if (!accessToken.value) return
    loading.value = true
    try {
      const { data } = await getApiClient().get<UserInfo>('/auth/me')
      userInfo.value = data
    } catch {
      clearAuth()
    } finally {
      loading.value = false
    }
  }

  return {
    accessToken, refreshTokenValue, userInfo, loading,
    isLoggedIn, login, logout, fetchUser, clearAuth}
})
