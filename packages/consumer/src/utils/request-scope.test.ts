import { expect, it } from 'vitest'
import { createRequestScope } from './request-scope'
it('late route answer and candidate cannot replace the new route data', async () => {
  const scope = createRequestScope()
  const a = scope.begin('a')
  let release!: (value: string) => void
  const delayed = new Promise<string>((resolve) => {
    release = resolve
  })
  let displayed = ''
  const late = delayed.then((value) =>
    a.apply(() => {
      displayed = value
    }),
  )
  const b = scope.begin('b')
  b.apply(() => {
    displayed = 'answer B'
  })
  release('candidate A')
  await late
  expect(displayed).toBe('answer B')
  expect(a.signal.aborted).toBe(true)
})
it('repeat selection of same source still discards older responses and disposal cancels downloads', () => {
  const scope = createRequestScope()
  const old = scope.begin('source')
  const latest = scope.begin('source')
  expect(
    old.apply(() => {
      throw new Error('stale')
    }),
  ).toBe(false)
  expect(latest.isCurrent()).toBe(true)
  scope.dispose()
  expect(latest.signal.aborted).toBe(true)
  expect(latest.isCurrent()).toBe(false)
})
