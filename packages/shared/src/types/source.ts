export interface Source {
  last_sync_manifest?: { dirty?: boolean }
  id: string
  knowledge_base_id: string
  name: string
  kind: 'document' | 'image' | 'git_local' | 'git_public'
  config?: { root_id?: string; relative_path?: string; url?: string; include_paths?: string[] }
  current_revision_id: string | null
  active_task_id: string | null
  archived_at: string | null
}
export interface SourceRevision {
  id: string
  commit?: string | null
  manifest?: {
    image_hash?: string
    ocr_text?: string
    ocr_status?: 'completed' | 'no_text' | 'unavailable'
    manual_description?: string
    ocr_correction?: string
    channel_fingerprints?: Record<string, string>
    image?: { format: string; width: number; height: number; bytes: number }
    needs_description?: boolean
    included_count?: number
    stats?: { candidates: number; included: number; skipped: number; text_bytes: number }
    complete?: boolean
    skipped?: { path: string; reason: string }[]
    dirty?: boolean
    config_fingerprint?: string
  } | null
  raw_hash: string
  state: string
  filename: string
  created_at: string
  published_at: string | null
}
export interface SourceTask {
  id?: string
  source_id: string
  revision_id: string | null
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

export interface SourceDocument {
  id: string
  logical_path: string
  locator: Record<string, unknown>
}
