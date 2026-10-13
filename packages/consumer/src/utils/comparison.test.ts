import { describe, expect, it } from 'vitest'
import { comparisonReferences, filterComparisonRows, canCompare } from './comparison'
import type { SourceComparison, SourceCitation } from '@akb/shared'
const card: SourceComparison = {
  kind: 'source_comparison',
  sources: [
    { source_id: 'a', name: 'A', revision_id: 'v1' },
    { source_id: 'b', name: 'B', revision_id: 'v2' },
  ],
  rows: [
    {
      dimension: '事务',
      cells: [
        { source_id: 'a', text: '支持', citation_indices: [1] },
        { source_id: 'b', text: '未找到依据', citation_indices: [] },
      ],
    },
    {
      dimension: '索引',
      cells: [
        { source_id: 'a', text: '支持', citation_indices: [1] },
        { source_id: 'b', text: '支持', citation_indices: [2] },
      ],
    },
  ],
}
const citations = [
  { index: 1, source_id: 'a', revision_id: 'v1', document_id: 'd1', content: '原文', locator: {} },
] as SourceCitation[]
describe('comparison presentation', () => {
  it('limits comparisons to 2–4 distinct sources', () => {
    expect(canCompare(['a'])).toBe(false)
    expect(canCompare(['a', 'a'])).toBe(false)
    expect(canCompare(['a', 'b'])).toBe(true)
    expect(canCompare(['a', 'b', 'c', 'd', 'e'])).toBe(false)
  })
  it('filters dimensions without losing evidence indices', () => {
    expect(filterComparisonRows(card, ' 索引 ')).toEqual([card.rows[1]])
    expect(filterComparisonRows(card, '')).toEqual(card.rows)
    expect(filterComparisonRows(card, 'missing')).toEqual([])
  })
  it('resolves only same-source available quotes', () => {
    expect(comparisonReferences(card.rows[0].cells[0], citations)).toEqual(citations)
    expect(
      comparisonReferences({ source_id: 'b', text: 'wrong', citation_indices: [1] }, citations),
    ).toEqual([])
    expect(comparisonReferences(card.rows[1].cells[1], citations)).toEqual([])
  })
})
