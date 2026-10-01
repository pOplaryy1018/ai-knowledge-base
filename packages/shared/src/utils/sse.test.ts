import { expect, it } from 'vitest'
import { readSSE } from './sse'
it('parses split CRLF records and multiline data', async () => {
 const encoder = new TextEncoder()
 const stream = new ReadableStream({ start(c) { c.enqueue(encoder.encode('event: progress\r')); c.enqueue(encoder.encode('\ndata: one\r\ndata: two\r\n\r\n')); c.close() } })
 const events = []
 for await (const event of readSSE(stream)) events.push(event)
 expect(events).toEqual([{ type: 'progress', data: 'one\ntwo' }])
})
