export interface RequestTicket {
  id: string
  signal: AbortSignal
  isCurrent: () => boolean
  apply: (change: () => void) => boolean
}
export function createRequestScope() {
  let generation = 0
  let controller: AbortController | undefined
  return {
    begin(id: string): RequestTicket {
      controller?.abort()
      const own = new AbortController()
      controller = own
      const epoch = ++generation
      const isCurrent = () => epoch === generation && !own.signal.aborted
      return {
        id,
        signal: own.signal,
        isCurrent,
        apply(change) {
          if (!isCurrent()) return false
          change()
          return true
        },
      }
    },
    dispose() {
      ++generation
      controller?.abort()
    },
  }
}
