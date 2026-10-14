import { beforeEach, expect, it, vi } from 'vitest'
import { createWikiPage, updateWikiDraft, compileWikiPage, publishWikiPage, exportWikiMarkdown, listWikiPages } from './wiki'

const client = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), patch: vi.fn() }))
vi.mock('./client', () => ({ getApiClient: () => client }))
beforeEach(() => vi.clearAllMocks())

it('sends explicit revision guards and abort signals for every Wiki mutation', async () => {
  const signal = new AbortController().signal
  client.post.mockResolvedValue({ data: { id: 'page' } })
  client.patch.mockResolvedValue({ data: { id: 'page' } })
  await createWikiPage('事务', ['source'], signal)
  expect(client.post).toHaveBeenLastCalledWith('/wiki/pages', { title: '事务', source_ids: ['source'] }, { signal, timeout: 0 })
  await updateWikiDraft('page', 'revision', '事务', '正文', signal)
  expect(client.patch).toHaveBeenLastCalledWith('/wiki/pages/page/draft', { expected_revision_id: 'revision', title: '事务', content: '正文' }, { signal })
  await compileWikiPage('page', 'revision', ['source'], signal)
  expect(client.post).toHaveBeenLastCalledWith('/wiki/pages/page/compile', { expected_revision_id: 'revision', source_ids: ['source'] }, { signal, timeout: 0 })
  await publishWikiPage('page', 'revision', signal)
  expect(client.post).toHaveBeenLastCalledWith('/wiki/pages/page/publish', { expected_revision_id: 'revision' }, { signal })
})

it('keeps search cancellable and exports through the authenticated Blob client', async () => {
  const signal = new AbortController().signal
  client.get.mockResolvedValueOnce({ data: { items: [{ id: 'page' }] } })
  expect(await listWikiPages('事务', signal)).toEqual([{ id: 'page' }])
  expect(client.get).toHaveBeenLastCalledWith('/wiki/pages', { params: { q: '事务' }, signal })
  const blob = new Blob(['# 事务'], { type: 'text/markdown' })
  client.get.mockResolvedValueOnce({ data: blob, headers: { 'content-disposition': 'attachment; filename="wiki-test.md"' } })
  expect(await exportWikiMarkdown('page', signal)).toEqual({ blob, filename: 'wiki-test.md' })
  expect(client.get).toHaveBeenLastCalledWith('/wiki/pages/page/export', { responseType: 'blob', signal })
})
