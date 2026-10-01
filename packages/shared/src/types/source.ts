export interface Source {
  id: string
  knowledge_base_id: string
  name: string
  kind: string
  current_revision_id: string | null
  active_task_id: string | null
  archived_at: string | null
}
export interface SourceRevision {
  id: string
  raw_hash: string
  state: string
  filename: string
  created_at: string
  published_at: string | null
}
export interface SourceTask {
  id?: string
  source_id: string
  revision_id: string
  task_id?: string | null
  status: string
  stage?: string
  error?: string | null
}
export interface SourceCitation {
  index: number
  source_id: string
  revision_id: string
  document_id: string
  content: string
  locator: Record<string, unknown>
}
