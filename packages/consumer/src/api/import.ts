/** 文档导入 API */
import axios from 'axios'
import type { ImportTaskResponse } from '@akb/shared'
import { getApiClient } from './client'

const uploadClient = axios.create({
  baseURL: '/api',
  timeout: 30000,
  // 不设置 Content-Type，让浏览器自动附上 boundary
})

// 请求拦截器：附加 token
uploadClient.interceptors.request.use((config) => {
  const token = localStorage.getItem('akb_access_token')
  if (token && config.headers) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

export async function uploadFile(kbId: string, file: File): Promise<ImportTaskResponse> {
  const formData = new FormData()
  formData.append('file', file)
  const { data } = await uploadClient.post<ImportTaskResponse>(
    '/import/upload',
    formData,
    { params: { kb_id: kbId } },
  )
  return data
}

/** 创建 SSE EventSource 连接以监听导入进度 */
export function createProgressEventSource(taskId: string): EventSource {
  const token = localStorage.getItem('akb_access_token') || ''
  return new EventSource(
    `/api/import/${taskId}/progress?token=${encodeURIComponent(token)}`,
  )
}

// ── 文件管理 ──

import type { KnowledgeFile, KnowledgeFilePreview, FileRetryResponse } from '@akb/shared'

export async function previewFile(kbId: string, fileId: string): Promise<KnowledgeFilePreview> {
  const { data } = await getApiClient().get<KnowledgeFilePreview>(
    `/knowledge-bases/${kbId}/files/${fileId}/preview`,
  )
  return data
}

export function getRawFileUrl(kbId: string, fileId: string, token: string): string {
  return `/api/knowledge-bases/${kbId}/files/${fileId}/raw?token=${encodeURIComponent(token)}`
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
