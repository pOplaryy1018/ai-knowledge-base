/**
 * Agent 管理 — TanStack Query Hooks
 */
import { ref, computed } from 'vue'
import { useQuery, useMutation, keepPreviousData } from '@tanstack/vue-query'
import { Message, Modal } from '@arco-design/web-vue'
import {
  listAgents,
  createAgent,
  updateAgent,
  deleteAgent} from '@/api/agent'
import type { AgentCreate, AgentUpdate } from '@akb/shared'
import { queryKeys } from './queryKeys'

export function useAgentList() {
  const page = ref(1)
  const size = ref(20)

  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: computed(() => queryKeys.agents.list(page.value, size.value)),
    queryFn: () => listAgents(page.value, size.value),
    placeholderData: keepPreviousData})

  const items = computed(() => data.value?.items ?? [])
  const total = computed(() => data.value?.total ?? 0)

  const createMutation = useMutation({
    mutationFn: (body: AgentCreate) => createAgent(body),
    onSuccess: () => {
      Message.success('Agent 已创建')
      refetch()
    }})

  const updateMutation = useMutation({
    mutationFn: ({ id, body }: { id: string; body: AgentUpdate }) =>
      updateAgent(id, body),
    onSuccess: () => {
      Message.success('Agent 已更新')
      refetch()
    }})

  function confirmDelete(id: string, name: string): Promise<boolean> {
    return new Promise((resolve) => {
      Modal.confirm({
        content: `确定要删除 Agent「${name}」吗？此操作不可恢复。`,
        title: '删除确认',
        okText: '确认删除',
        cancelText: '取消',
        onOk: async () => {
          await deleteAgent(id)
          Message.success('Agent 已删除')
          refetch()
          resolve(true)
        },
        onCancel: () => {
          resolve(false)
        },
      })
    })
  }

  return {
    page,
    size,
    items,
    total,
    isLoading,
    isError,
    error,
    refetch,
    createMutation,
    updateMutation,
    confirmDelete}
}
