import { describe, expect, it, vi } from 'vitest'
import { wikiMarkdown, wikiConflictMessage, createWikiWriteGuard, wikiExportFilename } from './wiki'

describe('Wiki navigation and publication boundaries', () => {
  const links = [{ id: 'page/id', slug: '事务', title: '事务介绍' }]
  it('links only server-resolved pages and leaves unknown slugs as literal text', () => {
    expect(wikiMarkdown('阅读 [[事务]] 和 [[不存在]]。', links)).toBe(
      '阅读 [事务](/workspace/wiki/page%2Fid) 和 [[不存在]]。',
    )
    expect(wikiMarkdown('[[javascript:alert(1)]]', links)).toBe('[[javascript:alert(1)]]')
  })
  it('preserves fenced and inline code instead of creating navigation inside examples', () => {
    const code = '`[[事务]]`\n```md\n[[事务]]\n```\n~~~\n[[事务]]\n~~~\n[[事务]]'
    expect(wikiMarkdown(code, links)).toBe(
      '`[[事务]]`\n```md\n[[事务]]\n```\n~~~\n[[事务]]\n~~~\n[事务](/workspace/wiki/page%2Fid)',
    )
  })
  it('respects CommonMark indented code, unclosed fences and multiline code spans', () => {
    expect(wikiMarkdown('    [[事务]]\n\n[[事务]]', links)).toBe('    [[事务]]\n\n[事务](/workspace/wiki/page%2Fid)')
    expect(wikiMarkdown('```md\n[[事务]]', links)).toBe('```md\n[[事务]]')
    expect(wikiMarkdown('``code `\n[[事务]]``', links)).toBe('``code `\n[[事务]]``')
    expect(wikiMarkdown('\\[[事务]]', links)).toBe('\\[[事务]]')
  })
  it('keeps conflict explanations actionable without describing evidence changes as factual errors', () => {
    expect(wikiConflictMessage({ response: { status: 409, data: { detail: '资料版本已变化，请重新编译并复核草稿' } } })).toContain('重新编译')
    expect(wikiConflictMessage({ response: { status: 409, data: { detail: 'Wiki草稿或发布版本已变化，请刷新后重试' } } })).toContain('刷新')
    expect(wikiConflictMessage(new Error('连接失败'))).toBe('连接失败')
  })
  it('bounds export names to a plain Markdown filename', () => {
    expect(wikiExportFilename("attachment; filename*=UTF-8''%E4%BA%8B%E5%8A%A1.md", 'wiki')).toBe('事务.md')
    expect(wikiExportFilename('attachment; filename="../private.md"', 'wiki')).toBe('.._private.md')
    expect(wikiExportFilename("attachment; filename*=UTF-8''%ZZ", 'wiki')).toBe('wiki.md')
  })
})

it('allows only one write and discards completion after a route or account changes', async () => {
  let identity = 'account-a/page-a'
  const guard = createWikiWriteGuard(() => identity)
  let finish!: (value: string) => void
  const apply = vi.fn()
  const first = guard.run(() => new Promise<string>(resolve => { finish = resolve }), apply)
  const duplicate = vi.fn(async () => 'duplicate')
  expect(await guard.run(duplicate, apply)).toBe(false)
  expect(duplicate).not.toHaveBeenCalled()
  identity = 'account-b/page-b'
  guard.dispose()
  finish('old-page')
  expect(await first).toBe(false)
  expect(apply).not.toHaveBeenCalled()
  await guard.run(async () => 'new-page', apply)
  expect(apply).toHaveBeenCalledWith('new-page')
})

it('releases a failed write for retry and suppresses an aborted previous identity failure', async () => {
  const guard = createWikiWriteGuard(() => 'page')
  const apply = vi.fn()
  await expect(guard.run(async () => { throw new Error('current failure') }, apply)).rejects.toThrow('current failure')
  expect(await guard.run(async () => 'retry', apply)).toBe(true)
  let reject!: (reason: Error) => void
  let signal!: AbortSignal
  const old = guard.run(abort => { signal = abort; return new Promise((_resolve, rejectPromise) => { reject = rejectPromise }) }, apply)
  guard.dispose()
  expect(signal.aborted).toBe(true)
  reject(new Error('late failure'))
  expect(await old).toBe(false)
})
