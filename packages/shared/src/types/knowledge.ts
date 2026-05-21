/** 知识库 */
export interface KnowledgeBase {
  id: string
  name: string
  description: string | null
  user_id: string
  created_at: string
  updated_at: string
}

/** 知识条目 */
export interface KnowledgeItem {
  id: string
  knowledge_base_id: string
  file_id: string | null
  title: string
  content: string
  type: string
  status: string
  tags: string[] | null
  source: string
  source_metadata: Record<string, any>
  created_at: string
  updated_at: string
}

/** 分页响应 */
export interface PaginatedResponse<T> {
  total: number
  page: number
  size: number
  items: T[]
}

/** 创建知识库表单 */
export interface KnowledgeBaseCreate {
  name: string
  description?: string
}

/** 更新知识库表单 */
export interface KnowledgeBaseUpdate {
  name?: string
  description?: string
}

/** 创建知识条目表单 */
export interface KnowledgeItemCreate {
  title: string
  content: string
  type?: string
  tags?: string[]
}

/** 更新知识条目表单 */
export interface KnowledgeItemUpdate {
  title?: string
  content?: string
  type?: string
  tags?: string[]
}

/** 切换条目状态 */
export interface KnowledgeItemStatusUpdate {
  status: 'available' | 'unavailable'
}

/** 列表查询参数 */
export interface KnowledgeItemQuery {
  page?: number
  size?: number
  search?: string
  status?: string
  tag?: string
}
