import type { AnswerStatus } from '@akb/shared'
export function answerStatusLabel(status: AnswerStatus) {
  return {
    untracked: '未追踪证据',
    unchanged: '未检测到直接引用变化',
    needs_review: '需要复核',
    unavailable: '证据不可用',
  }[status]
}
export function canSaveAnswer(answer: { content: string; messageId?: string }) {
  return Boolean(answer.messageId && answer.content.trim())
}
export function sourceSelectable(source: {
  archived_at: string | null
  current_revision_id: string | null
}) {
  return !source.archived_at && Boolean(source.current_revision_id)
}
export function errorMessage(error: unknown): string {
  const e = error as {
    response?: { data?: { detail?: string }; status?: number }
    message?: string
  }
  return e.response?.data?.detail || e.message || '请求失败，请重试'
}

export function evidenceStateLabel(state: string) {
  return (
    (
      {
        unchanged: '未检测到直接引用变化',
        relocated: '位置移动',
        changed: '引用变化',
        missing: '引用缺失',
        ambiguous: '无法确认',
        unavailable: '证据不可用',
      } as Record<string, string>
    )[state] || '待核对'
  )
}
export function formatLocator(locator: Record<string, unknown> | null) {
  if (!locator) return '位置不可用'
  const labels: string[] = []
  if (typeof locator.commit === 'string') {
    labels.push(locator.commit)
    if (typeof locator.logical_path === 'string') labels.push(locator.logical_path)
  }
  if (locator.page != null) labels.push(`第${locator.page}页`)
  if (locator.paragraph != null) labels.push(`第${locator.paragraph}段`)
  if (locator.line_start != null)
    labels.push(
      locator.line_end != null && locator.line_end !== locator.line_start
        ? `第${locator.line_start}–${locator.line_end}行`
        : `第${locator.line_start}行`,
    )
  return labels.join(' · ') || '原件中的引用片段'
}
export function versionLabel(id: string | undefined) {
  return id ? `版本 ${id.slice(0, 8)}` : '无当前版本'
}

export function repositoryManifest(
  kind: string,
  manifest:
    | {
        included_count?: number
        stats?: { included?: number }
        skipped?: { path: string; reason: string }[]
        dirty?: boolean
      }
    | null
    | undefined,
) {
  if (kind !== 'git_local' && kind !== 'git_public') return null
  return {
    included: manifest?.stats?.included ?? manifest?.included_count ?? 0,
    skipped: manifest?.skipped ?? [],
    dirty: manifest?.dirty ?? false,
  }
}
