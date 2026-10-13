import type { ComparisonCell, SourceCitation, SourceComparison } from '@akb/shared'
export function canCompare(sourceIds: string[]): boolean {
  const count = new Set(sourceIds).size
  return count === sourceIds.length && count >= 2 && count <= 4
}
export function filterComparisonRows(comparison: SourceComparison, query: string) {
  const normalized = query.trim().toLocaleLowerCase()
  return comparison.rows.filter((row) => row.dimension.toLocaleLowerCase().includes(normalized))
}
export function comparisonReferences(cell: ComparisonCell, citations: SourceCitation[]) {
  return citations.filter(
    (citation) =>
      cell.citation_indices.includes(citation.index) &&
      citation.source_id === cell.source_id &&
      typeof citation.content === 'string' &&
      citation.content.length > 0,
  )
}
