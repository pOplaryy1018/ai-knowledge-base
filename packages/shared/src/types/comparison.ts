export type ScopedResponseMode = 'text' | 'comparison'
export interface ComparisonCell {
  source_id: string
  text: string
  citation_indices: number[]
}
export interface ComparisonRow {
  dimension: string
  cells: ComparisonCell[]
}
export interface SourceComparison {
  kind: 'source_comparison'
  sources: { source_id: string; name: string; revision_id: string }[]
  rows: ComparisonRow[]
}
