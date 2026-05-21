// ── Agent ──

export interface Agent {
  id: string
  name: string
  description: string | null
  knowledge_ids: string[]
  prompt_template: string | null
  created_at: string
  updated_at: string
}

export interface AgentCreate {
  name: string
  description?: string
  knowledge_ids: string[]
  prompt_template?: string
}

export interface AgentUpdate {
  name?: string
  description?: string
  knowledge_ids?: string[]
  prompt_template?: string
}

export interface AgentListResponse {
  total: number
  items: Agent[]
}

// ── 对话 ──

export interface Conversation {
  id: string
  agent_id: string
  user_id: string
  title: string | null
  created_at: string
  updated_at: string
}

export interface ConversationListResponse {
  total: number
  items: Conversation[]
}

// ── 消息 ──

export interface CitationItem {
  index: number
  content: string
  knowledge_title: string
  score: number
}

export interface ChatMessage {
  id: string
  conversation_id: string
  role: 'user' | 'assistant'
  content: string
  citations: CitationItem[] | null
  created_at: string
}

// ── 对话请求 ──

export interface ChatRequest {
  message: string
  conversation_id?: string
}

// ── SSE 事件 ──

export interface SSETokenEvent {
  content: string
}

export interface SSEMetaEvent {
  conversation_id: string
}

export interface SSEDoneEvent {
  conversation_id: string
}

export interface SSEErrorEvent {
  message: string
}
