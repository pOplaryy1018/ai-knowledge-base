/** 知识库 API 封装 */
import type {
  KnowledgeBase,
  KnowledgeBaseCreate,
  KnowledgeBaseUpdate,
  PaginatedResponse} from '@akb/shared'
import { getApiClient } from './client'

// ── 知识库 ──

export async function createKnowledgeBase(data: KnowledgeBaseCreate) {
  const { data: res } = await getApiClient().post<KnowledgeBase>('/knowledge-bases', data)
  return res
}

export async function listKnowledgeBases(page = 1, size = 20, search = '') {
  const { data: res } = await getApiClient().get<PaginatedResponse<KnowledgeBase>>(
    '/knowledge-bases',
    { params: { page, size, search } },
  )
  return res
}

export async function updateKnowledgeBase(id: string, data: KnowledgeBaseUpdate) {
  const { data: res } = await getApiClient().put<KnowledgeBase>(
    `/knowledge-bases/${id}`,
    data,
  )
  return res
}

export async function deleteKnowledgeBase(id: string) {
  await getApiClient().delete(`/knowledge-bases/${id}`)
}
