import { beforeEach, expect, it, vi } from 'vitest'
import { getSourceGraph, retrySourceGraph } from './sources'

const client = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }))
vi.mock('./client', () => ({ getApiClient: () => client }))
beforeEach(() => vi.clearAllMocks())

it('reads graph status and retries only through authenticated source endpoints', async () => {
  const signal = new AbortController().signal
  client.get.mockResolvedValue({ data: { status: 'failed' } })
  client.post.mockResolvedValue({ data: { status: 'pending' } })
  expect(await getSourceGraph('source-1', signal)).toEqual({ status: 'failed' })
  expect(client.get).toHaveBeenCalledWith('/sources/source-1/graph', { signal })
  expect(await retrySourceGraph('source-1', signal)).toEqual({ status: 'pending' })
  expect(client.post).toHaveBeenCalledWith('/sources/source-1/graph/retry', {}, { signal })
})
