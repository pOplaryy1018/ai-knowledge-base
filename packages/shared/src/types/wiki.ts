export interface WikiCitation {
  index: number
  source_id: string
  revision_id: string
  document_id: string
  knowledge_title: string
  content: string | null
  quote: string | null
  locator: Record<string, unknown>
  unavailable: boolean
}

export interface WikiLink {
  id: string
  slug: string
  title: string
}

export interface WikiRevision {
  id: string
  title: string
  content: string
  source_versions: Record<string, string>
  citations: WikiCitation[]
  kind: 'generated' | 'edited'
  created_at: string
}

export interface WikiPageSummary {
  id: string
  slug: string
  title: string
  status: 'draft' | 'published'
  published_revision_id: string | null
  draft_revision_id: string | null
  source_changed: boolean
  created_at: string
  updated_at: string
}

export interface WikiPageDetail extends WikiPageSummary {
  published_revision: WikiRevision | null
  draft_revision: WikiRevision | null
  history: WikiRevision[]
  links: WikiLink[]
  backlinks: WikiLink[]
}
