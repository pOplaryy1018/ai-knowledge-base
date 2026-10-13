import { afterEach, expect, it, vi } from 'vitest'
import { scopedChatSSE } from './scoped-chat'
vi.mock('./client', () => ({
  getAccessToken: () => 'token',
  getAuthGeneration: () => 1,
  refreshAccessToken: vi.fn(),
  handleUnauthorized: vi.fn(),
}))
afterEach(() => vi.unstubAllGlobals())
it('sends comparison mode and consumes comparison and warning events', async () => {
  const card = { kind: 'source_comparison', sources: [], rows: [] }
  const request = vi
    .fn()
    .mockResolvedValue(
      new Response(
        'event: comparison\ndata: ' +
          JSON.stringify(card) +
          '\n\nevent: warning\ndata: {"message":"已回退"}\n\nevent: done\ndata: {"conversation_id":"c","message_id":"m"}\n\n',
      ),
    )
  vi.stubGlobal('fetch', request)
  const events = []
  for await (const event of scopedChatSSE('比较', ['a', 'b'], undefined, undefined, 'comparison'))
    events.push(event)
  expect(JSON.parse(request.mock.calls[0][1].body).response_mode).toBe('comparison')
  expect(events.map((event) => event.type)).toEqual(['comparison', 'warning', 'done'])
})
