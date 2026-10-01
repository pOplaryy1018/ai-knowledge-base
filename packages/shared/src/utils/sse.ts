export async function* readSSE(body: ReadableStream<Uint8Array>): AsyncGenerator<{ type: string; data: string }> {
  const reader = body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  const parse = (record: string) => {
    let type = 'message'
    const data: string[] = []
    for (const line of record.split(/\r?\n/)) {
      if (line.startsWith('event:')) type = line.slice(6).trim()
      if (line.startsWith('data:')) data.push(line.slice(5).replace(/^ /, ''))
    }
    return data.length ? { type, data: data.join('\n') } : null
  }
  try {
    while (true) {
      const { done, value } = await reader.read()
      buffer += done ? decoder.decode() : decoder.decode(value, { stream: true })
      let match: RegExpExecArray | null
      while ((match = /\r?\n\r?\n/.exec(buffer))) {
        const event = parse(buffer.slice(0, match.index))
        buffer = buffer.slice(match.index + match[0].length)
        if (event) yield event
      }
      if (done) { const event = parse(buffer); if (event) yield event; break }
    }
  } finally { await reader.cancel().catch(() => {}); reader.releaseLock() }
}
