/** 文档导入 API */
import { createProgressSource } from '@akb/shared'
import type { ImportTaskResponse } from '@akb/shared'
import { getApiClient, getAuthGeneration } from './client'

export async function uploadFile(kbId: string, file: File): Promise<ImportTaskResponse> {
  const formData = new FormData()
  formData.append('file', file)
  const { data } = await getApiClient().post<ImportTaskResponse>(
    '/import/upload',
    formData,
    { params: { kb_id: kbId } },
  )
  return data
}

/** 创建 SSE EventSource 连接以监听导入进度 */
export function createProgressEventSource(taskId: string) {
  return createProgressSource(taskId, getApiClient(), getAuthGeneration)
}

// ── 文件管理 ──

import type { KnowledgeFile, KnowledgeFilePreview, FileRetryResponse } from '@akb/shared'

export async function previewFile(kbId: string, fileId: string, signal?: AbortSignal): Promise<KnowledgeFilePreview> {
  const { data } = await getApiClient().get<KnowledgeFilePreview>(
    `/knowledge-bases/${kbId}/files/${fileId}/preview`,
    { signal },
  )
  return data
}

export async function getRawFile(kbId: string, fileId: string, signal?: AbortSignal): Promise<Blob> {
  const { data } = await getApiClient().get<Blob>(
    `/knowledge-bases/${kbId}/files/${fileId}/raw`,
    { responseType: 'blob', signal },
  )
  return data
}

export async function listFiles(kbId: string, params: Record<string, any> = {}) {
  const { data: res } = await getApiClient().get<{
    total: number; page: number; size: number; items: KnowledgeFile[]
  }>(`/knowledge-bases/${kbId}/files`, { params })
  return res
}

export async function deleteFile(kbId: string, fileId: string) {
  await getApiClient().delete(`/knowledge-bases/${kbId}/files/${fileId}`)
}

export async function retryFile(kbId: string, fileId: string) {
  const { data: res } = await getApiClient().post<FileRetryResponse>(
    `/knowledge-bases/${kbId}/files/${fileId}/retry`,
  )
  return res
}
