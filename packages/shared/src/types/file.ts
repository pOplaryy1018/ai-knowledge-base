/** 文件状态 */
export type FileStatus = 'processing' | 'completed' | 'failed'

/** 知识库文件记录 */
export interface KnowledgeFile {
  id: string
  knowledge_base_id: string
  user_id: string
  filename: string
  original_filename: string
  file_path: string
  file_type: string
  file_size: number
  status: FileStatus
  error_message: string | null
  chunks_count: number
  created_at: string
  updated_at: string
}

/** 文件列表响应 */
export interface KnowledgeFileListResponse {
  total: number
  page: number
  size: number
  items: KnowledgeFile[]
}

/** 文件上传响应 */
export interface KnowledgeFileUploadResponse {
  file_id: string
  task_id: string
  filename: string
}

/** 文件预览响应 */
export interface KnowledgeFilePreview {
  file_id: string
  filename: string
  file_type: string
  content: string
  content_type: 'text' | 'code' | 'image' | 'unsupported'
  total_chars: number
  preview_chars: number
}

/** 文件列表查询参数 */
export interface FileListQuery {
  page?: number
  size?: number
  search?: string
  status?: FileStatus
  file_type?: string
  sort_by?: string
  sort_order?: string
  kb_id?: string
  user_id?: string
}

/** 重试文件响应 */
export interface FileRetryResponse {
  file_id: string
  task_id: string
  status: string
}
