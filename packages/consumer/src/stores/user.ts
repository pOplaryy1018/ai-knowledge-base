/**
 * 用户认证状态管理 (Pinia) ── token 持久化、登录/登出
 */
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { UserInfo, LoginResponse } from '@akb/shared'
import { getApiClient, setupApiClient } from '@/api/client'
import router from '@/router'
import { queryClient } from '@/queryClient'
import { useChatStore } from './chat'

const TOKEN_KEY = 'akb_access_token'
const REFRESH_KEY = 'akb_refresh_token'

export const useUserStore = defineStore('user', () => {
  const accessToken = ref<string | null>(localStorage.getItem(TOKEN_KEY))
  const refreshTokenValue = ref<string | null>(localStorage.getItem(REFRESH_KEY))
  const userInfo = ref<UserInfo | null>(null)
  const loading = ref(false)
  const generation = ref(0)

  const isLoggedIn = computed(() => !!accessToken.value)

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
    useChatStore().resetChatState()
    accessToken.value = null
    refreshTokenValue.value = null
    userInfo.value = null
    localStorage.removeItem(TOKEN_KEY)
    localStorage.removeItem(REFRESH_KEY)
  }

  async function login(username: string, password: string) {
    loading.value = true
    const requestGeneration = generation.value
    try {
      const { data } = await getApiClient().post<LoginResponse>('/auth/login', { username, password })
      if (requestGeneration !== generation.value) return
      saveTokens(data.access_token, data.refresh_token)
      userInfo.value = data.user
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
    const requestGeneration = generation.value
    try {
      const { data } = await getApiClient().get<UserInfo>('/auth/me')
      if (requestGeneration !== generation.value) return
      userInfo.value = data
    } catch {
      if (requestGeneration === generation.value) clearAuth()
    } finally {
      loading.value = false
    }
  }

  return {
    generation, accessToken, refreshTokenValue, userInfo, loading,
    isLoggedIn, login, logout, fetchUser, clearAuth}
})
