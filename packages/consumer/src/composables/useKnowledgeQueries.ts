/**
 * 知识库 / 知识条目 — TanStack Query Hooks
 */
import { ref, computed } from 'vue'
import { useQuery, useMutation, keepPreviousData } from '@tanstack/vue-query'
import { Message, Modal } from '@arco-design/web-vue'
import {
  listKnowledgeBases,
  createKnowledgeBase,
  updateKnowledgeBase,
  deleteKnowledgeBase} from '@/api/knowledge'
import type {
  KnowledgeBaseCreate,
  KnowledgeBaseUpdate} from '@akb/shared'
import { queryKeys } from './queryKeys'

// ── 知识库列表 ──
export function useKnowledgeBaseList() {
  const page = ref(1)
  const size = ref(20)
  const search = ref('')

  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: computed(() =>
      queryKeys.knowledgeBases.list(page.value, size.value, search.value),
    ),
    queryFn: () => listKnowledgeBases(page.value, size.value, search.value),
    placeholderData: keepPreviousData})

  const items = computed(() => data.value?.items ?? [])
  const total = computed(() => data.value?.total ?? 0)

  const createMutation = useMutation({
    mutationFn: (body: KnowledgeBaseCreate) => createKnowledgeBase(body),
    onSuccess: () => {
      Message.success('知识库已创建')
      refetch()
    }})

  const updateMutation = useMutation({
    mutationFn: ({ id, body }: { id: string; body: KnowledgeBaseUpdate }) =>
      updateKnowledgeBase(id, body),
    onSuccess: () => {
      Message.success('知识库已更新')
      refetch()
    }})

  function confirmDelete(id: string, name: string): Promise<boolean> {
    return new Promise((resolve) => {
      Modal.confirm({
        content: `确定要删除知识库「${name}」吗？删除后关联的所有条目也将被清除，此操作不可恢复。`,
        title: '删除确认',
        okText: '确认删除',
        cancelText: '取消',
        onOk: async () => {
          await deleteKnowledgeBase(id)
          Message.success('知识库已删除')
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
    search,
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

// 知识条目仅由文件导入流水线自动创建，前端不再提供手动 CRUD 入口
