import { describe, expect, it, vi, afterEach } from 'vitest'
import { answerStatusLabel, canSaveAnswer, sourceSelectable, formatLocator, evidenceStateLabel } from './review-state'
import { scopedChatSSE } from '../api/scoped-chat'
import { getAuthGeneration, refreshAccessToken } from '../api/client'
vi.mock('../api/client', () => ({
  getAccessToken: () => 'token',
  getAuthGeneration: vi.fn(() => 1),
  refreshAccessToken: vi.fn(),
  handleUnauthorized: vi.fn(),
}))
afterEach(() => { vi.unstubAllGlobals(); vi.clearAllMocks(); vi.mocked(getAuthGeneration).mockReturnValue(1) })
describe('review state', () => {
  it('keeps untracked distinct from unchanged', () => {
    expect(answerStatusLabel('untracked')).toBe('未追踪证据')
    expect(answerStatusLabel('unchanged')).toBe('未检测到直接引用变化')
  })
  it('only saves completed server messages', () => {
    expect(canSaveAnswer({ content: 'partial' })).toBe(false)
    expect(canSaveAnswer({ content: 'done', messageId: 'server-id' })).toBe(true)
  })
  it('excludes archived and unpublished sources', () => {
    expect(sourceSelectable({ archived_at: 'today', current_revision_id: 'v1' })).toBe(false)
    expect(sourceSelectable({ archived_at: null, current_revision_id: null })).toBe(false)
  })
})
it('preserves server message id in scoped SSE done', async () => {
  vi.stubGlobal(
    'fetch',
    vi
      .fn()
      .mockResolvedValue(
        new Response(
          'event: meta\ndata: {"conversation_id":"conv"}\n\nevent: done\ndata: {"conversation_id":"conv","message_id":"persisted"}\n\n',
        ),
      ),
  )
  const events = []
  for await (const event of scopedChatSSE('question', ['source'])) events.push(event)
  expect(events[1]).toEqual({
    type: 'done',
    data: { conversation_id: 'conv', message_id: 'persisted' },
  })
})

it('refreshes unauthorized scoped chat once before consuming events', async () => {
  vi.mocked(refreshAccessToken).mockResolvedValue('renewed')
  const fetchMock = vi.fn().mockResolvedValueOnce(new Response('', { status: 401 })).mockResolvedValueOnce(new Response('event: done\ndata: {"conversation_id":"conv","message_id":"persisted"}\n\n'))
  vi.stubGlobal('fetch', fetchMock)
  for await (const event of scopedChatSSE('q', ['source'])) expect(event.type).toBe('done')
  expect(refreshAccessToken).toHaveBeenCalledTimes(1)
  expect(fetchMock).toHaveBeenCalledTimes(2)
})
it('rejects the old account stream before exposing its result', async () => {
  vi.stubGlobal('fetch', vi.fn().mockImplementation(async () => {
    vi.mocked(getAuthGeneration).mockReturnValue(2)
    return new Response('event: done\ndata: {"message_id":"old"}\n\n')
  }))
  const iterator = scopedChatSSE('q', ['source'])
  await expect(iterator.next()).rejects.toMatchObject({ name: 'AbortError' })
})

it('formats document positions without exposing raw locator metadata', () => {
  expect(formatLocator({ page: 3, line_start: 2, line_end: 4, logical_path: 'page/3', char_start: 20 })).toBe('第3页 · 第2–4行')
  expect(formatLocator({ paragraph: 8 })).toBe('第8段')
  expect(formatLocator(null)).toBe('位置不可用')
  expect(evidenceStateLabel('ambiguous')).toBe('无法确认')
})
