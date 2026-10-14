import type { WikiLink } from '@akb/shared'
import MarkdownIt from 'markdown-it'
import { errorMessage } from './review-state'

const markdown = new MarkdownIt({ html: false })

/** Resolve Wiki syntax only through the current user's server-provided page index. */
export function wikiMarkdown(content: string, links: WikiLink[]): string {
  const pages = new Map(links.map(link => [link.slug, link.id]))
  function prose(text: string) {
    let result = '', index = 0
    while (index < text.length) {
      if (text[index] === '\\') { result += text.slice(index, index + 2); index += 2; continue }
      if (text[index] === '`') {
        const run = /^`+/.exec(text.slice(index))![0]
        const closing = /`+/g
        closing.lastIndex = index + run.length
        let match: RegExpExecArray | null, end = index + run.length
        while ((match = closing.exec(text))) {
          if (match[0].length === run.length) { end = match.index + run.length; break }
        }
        result += text.slice(index, end); index = end; continue
      }
      const match = text.startsWith('[[', index) ? /^\[\[([^[\]\n]+)\]\]/.exec(text.slice(index)) : null
      const id = match && pages.get(match[1])
      if (match && id) {
        const label = match[1].replace(/[\\`*{}[\]()#+.!_<>]/g, '\\$&')
        result += `[${label}](/workspace/wiki/${encodeURIComponent(id)})`
        index += match[0].length
      } else { result += text[index]; index++ }
    }
    return result
  }
  // CommonMark supplies exact line ranges, including indented and unclosed code blocks.
  const offsets = [0]
  for (const newline of content.matchAll(/\n/g)) offsets.push(newline.index! + 1)
  let result = '', cursor = 0
  for (const token of markdown.parse(content, {})) {
    if (!['fence', 'code_block'].includes(token.type) || !token.map) continue
    const start = offsets[token.map[0]] ?? content.length, end = offsets[token.map[1]] ?? content.length
    result += prose(content.slice(cursor, start)) + content.slice(start, end)
    cursor = end
  }
  return result + prose(content.slice(cursor))
}

export function wikiConflictMessage(error: unknown): string {
  const response = (error as { response?: { status?: number } })?.response
  const message = errorMessage(error)
  return response?.status === 409 ? `${message}。本地未保存的编辑已保留。` : message
}

export function wikiExportFilename(disposition: string, fallback: string): string {
  const encoded = /filename\*=UTF-8''([^;]+)/i.exec(disposition)?.[1]
  const plain = /filename="?([^";]+)"?/i.exec(disposition)?.[1]
  let name = plain || `${fallback}.md`
  if (encoded) {
    try { name = decodeURIComponent(encoded) } catch { name = `${fallback}.md` }
  }
  name = Array.from(name, character => character.charCodeAt(0) < 32 || character.charCodeAt(0) === 127 || /[/\\]/.test(character) ? '_' : character).join('').trim()
  return name || `${fallback}.md`
}

/** A cancelled identity can start a new write while late completion is discarded. */
export function createWikiWriteGuard(identity: () => string) {
  let active: { controller: AbortController; identity: string } | undefined
  return {
    async run<T>(action: (signal: AbortSignal) => Promise<T>, apply: (value: T) => void): Promise<boolean> {
      if (active) return false
      const own = { controller: new AbortController(), identity: identity() }
      active = own
      const current = () => active === own && !own.controller.signal.aborted && identity() === own.identity
      try {
        const result = await action(own.controller.signal)
        if (!current()) return false
        apply(result)
        return true
      } catch (error) {
        if (current()) throw error
        return false
      } finally {
        if (active === own) active = undefined
      }
    },
    dispose() {
      active?.controller.abort()
      active = undefined
    },
  }
}
