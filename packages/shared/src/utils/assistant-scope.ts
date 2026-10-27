import type { Source } from '../types/source'

export interface AssistantScope {
  available: Source[]
  selectedIds: string[]
  requiresSelection: boolean
}

/** The scoped chat endpoint accepts at most 100 distinct published sources. */
export function buildAssistantScope(sources: Source[], requestedIds?: string[]): AssistantScope {
  const available = sources.filter(source => !source.archived_at && Boolean(source.current_revision_id))
  const allowedIds = new Set(available.map(source => source.id))
  const selectedIds = requestedIds === undefined
    ? available.length <= 100 ? available.map(source => source.id) : []
    : [...new Set(requestedIds)].filter(id => allowedIds.has(id))
  if (selectedIds.length > 100) {
    return { available, selectedIds: [], requiresSelection: true }
  }
  return { available, selectedIds, requiresSelection: available.length > 100 && selectedIds.length === 0 }
}

export function scopeChanged(before: string[], after: string[]): boolean {
  if (before.length !== after.length) return true
  const previous = new Set(before)
  return after.some(id => !previous.has(id))
}
