/** 文档导入 API 封装 */
import axios from 'axios'
import type { ImportTaskResponse } from '@akb/shared'
import { getApiClient } from './client'

const uploadClient = axios.create({
  baseURL: '/api',
  timeout: 30000,
})

uploadClient.interceptors.request.use((config) => {
  const token = localStorage.getItem('akb_access_token')
  if (token && config.headers) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

/** 上传文件，返回异步任务信息 */
export async function uploadFile(kbId: string, file: File): Promise<ImportTaskResponse> {
  const form = new FormData()
  form.append('file', file)
  const { data } = await uploadClient.post<ImportTaskResponse>(
    '/import/upload',
    form,
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

import type { KnowledgeFile, FileRetryResponse } from '@akb/shared'

export async function adminListFiles(params: Record<string, any> = {}) {
  const { data: res } = await getApiClient().get<{
    total: number; page: number; size: number; items: KnowledgeFile[]
  }>('/admin/files', { params })
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
