import type { SourceCitation } from './source'
export type AnswerStatus = 'untracked' | 'unchanged' | 'needs_review' | 'unavailable'
export interface EvidenceResult {
  evidence_id: string
  source_id: string
  state: string
  old_text: string | null
  old_locator: Record<string, unknown>
  current_text: string | null
  locator: Record<string, unknown> | null
  current_revision_id?: string
}
export interface AnswerVersion {
  id: string
  content: string
  kind: string
  source_versions: Record<string, string>
  created_at: string
}
export interface SavedAnswer {
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
