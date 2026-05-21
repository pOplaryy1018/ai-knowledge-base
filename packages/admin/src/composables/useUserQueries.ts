/**
 * 用户管理 — TanStack Query Hooks
 */
import { ref, computed } from 'vue'
import { useQuery, useMutation, keepPreviousData } from '@tanstack/vue-query'
import { Message } from '@arco-design/web-vue'
import { queryKeys } from './queryKeys'
import { getRoles } from '@/api/auth'

// ── 占位 API 函数（用户列表 API 需在 Step 9 补充后端）──
async function fetchUsers() {
  const { getApiClient } = await import('@/api/client')
  const { data } = await getApiClient().get('/auth/users')
  return data
}

async function createUserApi(params: {
  username: string
  password: string
  role: string
}) {
  const { getApiClient } = await import('@/api/client')
  const { data } = await getApiClient().post('/auth/users', null, { params })
  return data
}

export function useUserList() {
  const page = ref(1)
  const size = ref(20)

  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: computed(() => [...queryKeys.users.list(), { page: page.value, size: size.value }]),
    queryFn: () => fetchUsers(),
    placeholderData: keepPreviousData})

  const users = computed(() => data.value ?? [])

  const createMutation = useMutation({
    mutationFn: createUserApi,
    onSuccess: () => {
      Message.success('用户创建成功')
      refetch()
    }})

  const updateMutation = useMutation({
    mutationFn: async (params: { userId: string; role: string }) => {
      const { getApiClient } = await import('@/api/client')
      const { data } = await getApiClient().put(`/auth/users/${params.userId}`, { role: params.role })
      return data
    },
    onSuccess: () => {
      Message.success('用户角色更新成功')
      refetch()
    },
    onError: (err: any) => {
      Message.error(err?.response?.data?.detail || '更新失败')
    }})

  const deleteMutation = useMutation({
    mutationFn: async (userId: string) => {
      const { getApiClient } = await import('@/api/client')
      await getApiClient().delete(`/auth/users/${userId}`)
    },
    onSuccess: () => {
      Message.success('用户已删除')
      refetch()
    },
    onError: (err: any) => {
      Message.error(err?.response?.data?.detail || '删除失败')
    }})

  return {
    page,
    size,
    users,
    isLoading,
    isError,
    error,
    refetch,
    createMutation,
    updateMutation,
    deleteMutation}
}

export function useRoleList() {
  return useQuery({
    queryKey: queryKeys.users.roles,
    queryFn: () => getRoles(),
    staleTime: 1000 * 60 * 5})
}
