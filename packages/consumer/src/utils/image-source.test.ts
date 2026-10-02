import { expect, it, vi } from 'vitest'
import { uploadImageRevision, updateImageText, reextractImage } from '../api/sources'
import { createImagePreview, imageStatusLabel, imageReasonLabel } from './image-source'
import { formatLocator, sourceSelectable } from './review-state'
const client = vi.hoisted(() => ({
  post: vi.fn(async () => ({ data: { status: 'pending' } })),
  patch: vi.fn(async () => ({ data: {} })),
  get: vi.fn(),
}))
vi.mock('../api/client', () => ({ getApiClient: () => client }))
it('uploads independent description and guards replacements against displayed HEAD', async () => {
  await uploadImageRevision('s', new Blob(['x']) as File, '', 'head')
  const [path, body] = client.post.mock.calls[0] as unknown as [string, FormData]
  expect(path).toBe('/sources/s/image-revisions')
  expect(body.get('manual_description')).toBe('')
  expect(body.get('expected_revision_id')).toBe('head')
  await uploadImageRevision('s', new Blob(['x']) as File, '')
  expect(
    (client.post.mock.calls[1] as unknown as [string, FormData])[1].has('expected_revision_id'),
  ).toBe(false)
})
it('sends both explicitly clearable text channels and guarded OCR extraction', async () => {
  await updateImageText('s', 'head', '', '')
  expect(client.patch).toHaveBeenCalledWith(
    '/sources/s/image-text',
    { expected_revision_id: 'head', manual_description: '', ocr_correction: '' },
    { signal: undefined },
  )
  await reextractImage('s', 'head')
  expect(client.post).toHaveBeenLastCalledWith(
    '/sources/s/image-reextract',
    { expected_revision_id: 'head' },
    { signal: undefined },
  )
})
it('labels image channels and honest empty OCR readiness', () => {
  expect(formatLocator({ origin: 'image_ocr', line_start: 2 })).toBe('图片OCR · 第2行')
  expect(formatLocator({ origin: 'image_ocr_correction' })).toBe('人工OCR校正')
  expect(formatLocator({ origin: 'manual_description' })).toBe('人工描述')
  expect(imageStatusLabel({ ocr_status: 'no_text', needs_description: true })).toContain(
    '未检测到文字',
  )
  expect(imageStatusLabel({ ocr_status: 'unavailable' })).toContain('不可用')
  expect(imageReasonLabel('image_changed')).toBe('原图已变化，请核对')
  expect(sourceSelectable({ archived_at: null, current_revision_id: 'ready-empty' })).toBe(true)
})
it('authenticated preview aborts old request, ignores late blobs and revokes replaced URLs', async () => {
  const resolvers: ((blob: Blob) => void)[] = []
  const loader = vi.fn(
    (_s: string, _r: string, _signal: AbortSignal) =>
      new Promise<Blob>((resolve) => resolvers.push(resolve)),
  )
  const urls = { createObjectURL: vi.fn(() => 'blob:preview'), revokeObjectURL: vi.fn() }
  const preview = createImagePreview(loader, urls)
  const old = preview.load('old', 'r1')
  const next = preview.load('new', 'r2')
  expect(loader.mock.calls[0][2].aborted).toBe(true)
  resolvers[0](new Blob(['old']))
  expect(await old).toBeUndefined()
  resolvers[1](new Blob(['new']))
  expect(await next).toBe('blob:preview')
  preview.dispose()
  expect(urls.revokeObjectURL).toHaveBeenCalledWith('blob:preview')
})
it('fetches originals through the authenticated client as blobs with cancellation', async () => {
  const blob = new Blob(['png'], { type: 'image/png' })
  client.get.mockResolvedValueOnce({ data: blob })
  const { getOriginalBlob } = await import('../api/sources')
  const signal = new AbortController().signal
  expect(await getOriginalBlob('private-source', 'immutable-version', signal)).toBe(blob)
  expect(client.get).toHaveBeenCalledWith(
    '/sources/private-source/revisions/immutable-version/original',
    { responseType: 'blob', signal },
  )
})
it('revokes the displayed version immediately and never retains a late result after unmount', async () => {
  let resolveLate!: (blob: Blob) => void
  const loader = vi
    .fn()
    .mockResolvedValueOnce(new Blob(['first']))
    .mockImplementationOnce(
      () =>
        new Promise<Blob>((resolve) => {
          resolveLate = resolve
        }),
    )
  const urls = { createObjectURL: vi.fn(() => 'blob:first'), revokeObjectURL: vi.fn() }
  const preview = createImagePreview(loader, urls)
  await preview.load('same-source', 'v1')
  const second = preview.load('same-source', 'v2')
  expect(urls.revokeObjectURL).toHaveBeenCalledWith('blob:first')
  preview.dispose()
  resolveLate(new Blob(['late']))
  expect(await second).toBeUndefined()
  expect(urls.createObjectURL).toHaveBeenCalledTimes(1)
})
it('shows the recorded character range without inventing image boxes', () => {
  expect(formatLocator({ origin: 'manual_description', char_start: 0, char_end: 12 })).toBe(
    '人工描述 · 字符 0–12',
  )
})
it('cancels downloads and suppresses navigation-stale errors while preserving current failures', async () => {
  const { createImageDownload } = await import('./image-source')
  let rejectOld!: (reason: Error) => void
  const downloader = vi.fn(
    (_s: string, _r: string, _name: string, _signal: AbortSignal) =>
      new Promise<void>((_resolve, reject) => {
        rejectOld = reject
      }),
  )
  const onError = vi.fn()
  const download = createImageDownload(downloader)
  const old = download.load('s1', 'r1', 'original', onError)
  download.dispose()
  expect(downloader.mock.calls[0][3].aborted).toBe(true)
  rejectOld(new Error('old failure'))
  await old
  expect(onError).not.toHaveBeenCalled()
  const current = download.load('s2', 'r2', 'original', onError)
  rejectOld(new Error('current failure'))
  await current
  expect(onError).toHaveBeenCalledWith('current failure')
})
