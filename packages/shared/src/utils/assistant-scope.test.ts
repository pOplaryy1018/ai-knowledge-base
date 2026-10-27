import { describe, expect, it } from 'vitest'
import type { Source } from '../types/source'
import { buildAssistantScope, scopeChanged } from './assistant-scope'

const source = (id: string, published = true, archived = false): Source => ({
  id, name: id, knowledge_base_id: 'kb', kind: 'document',
  current_revision_id: published ? `revision-${id}` : null,
  active_task_id: null, archived_at: archived ? '2026-10-26' : null,
})

describe('floating assistant scope', () => {
  it('defaults to only accessible published active sources', () => {
    const scope = buildAssistantScope([source('a'), source('b', false), source('c', true, true)])
    expect(scope.available.map(item => item.id)).toEqual(['a'])
    expect(scope.selectedIds).toEqual(['a'])
    expect(scope.requiresSelection).toBe(false)
  })

  it('does not silently truncate more than 100 sources', () => {
    const scope = buildAssistantScope(Array.from({ length: 101 }, (_, index) => source(String(index))))
    expect(scope.available).toHaveLength(101)
    expect(scope.selectedIds).toEqual([])
    expect(scope.requiresSelection).toBe(true)
  })

  it('removes inaccessible ids and detects a changed source set', () => {
    const scope = buildAssistantScope([source('a'), source('b', false)], ['a', 'b', 'unknown'])
    expect(scope.selectedIds).toEqual(['a'])
    expect(scopeChanged(['a', 'b'], ['b', 'a'])).toBe(false)
    expect(scopeChanged(['a'], ['b'])).toBe(true)
  })
})
