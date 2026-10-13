import type { SourceCitation } from './source'
import type { SourceComparison } from './comparison'
export type AnswerStatus = 'untracked' | 'unchanged' | 'needs_review' | 'unavailable'
export interface EvidenceResult {
  evidence_id: string
  citation_index?: number
  document_id?: string
  source_id: string
  state: string
  old_text: string | null
  old_locator: Record<string, unknown>
  current_text: string | null
  locator: Record<string, unknown> | null
  old_revision_id?: string
  reason?: string
  current_revision_id?: string
}
export interface AnswerVersion {
  citations?: SourceCitation[]
  comparison?: SourceComparison | null
  id: string
  content: string
  kind: string
  source_versions: Record<string, string>
  created_at: string
}
export interface SavedAnswer {
  comparison?: SourceComparison | null
  id: string
  question: string
  source_ids: string[]
  accepted_revision_id: string
  content: string
  source_versions: Record<string, string>
  status: AnswerStatus
  evidence: EvidenceResult[]
  versions: AnswerVersion[]
  created_at: string
}
export interface AnswerCandidate {
  comparison?: SourceComparison | null
  warning?: string | null
  id: string
  content: string
  source_versions: Record<string, string>
  expected_answer_revision_id: string
  citations: SourceCitation[]
}
export interface ReviewSummary {
  id: string
  answer_id: string
  question: string
  decision: string
  note: string | null
  evidence_results: EvidenceResult[]
}
export interface ReviewDetail {
  id: string
  decision: string
  note: string | null
  checked_answer_revision_id: string
  historical_evidence_results: EvidenceResult[]
  answer: SavedAnswer
}
