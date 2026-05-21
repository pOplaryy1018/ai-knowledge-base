/** 导入任务响应 */
export interface ImportTaskResponse {
  file_id: string
  task_id: string
  filename: string
  status: string
}

/** SSE 进度事件 */
export interface ImportProgressEvent {
  type: 'progress' | 'complete' | 'error' | 'connected' | 'closed'
  stage?: string
  message?: string
  percent?: number
  total_chunks?: number
  kb_id?: string
  preview?: Array<{ title: string; content_preview: string }>
  error?: string
}
