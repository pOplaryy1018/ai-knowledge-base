/**
 * 应用全局状态 — 侧边栏折叠、面包屑等
 */
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

export const useAppStore = defineStore('app', () => {
  const sidebarCollapsed = ref(false)

  const sidebarWidth = computed(() => (sidebarCollapsed.value ? '64px' : '220px'))

  function toggleSidebar() {
    sidebarCollapsed.value = !sidebarCollapsed.value
  }

  return {
    sidebarCollapsed,
    sidebarWidth,
    toggleSidebar}
})
