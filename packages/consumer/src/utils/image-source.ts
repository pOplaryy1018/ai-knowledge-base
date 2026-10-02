import type { SourceRevision } from '@akb/shared'
import { errorMessage } from './review-state'
import { downloadOriginal, getOriginalBlob } from '@/api/sources'
import { createRequestScope } from './request-scope'
export function imageStatusLabel(manifest: SourceRevision['manifest']) {
  const status = manifest?.ocr_status
  return `${status === 'completed' ? '图片OCR已完成' : status === 'no_text' ? '图片OCR未检测到文字' : '图片OCR不可用'}${manifest?.needs_description ? '；请补充人工描述' : ''}`
}
export function imageReasonLabel(reason?: string) {
  return reason === 'image_changed'
    ? '原图已变化，请核对'
    : reason === 'image_untracked'
      ? '原图变化未追踪，请核对'
      : ''
}
export function createImagePreview(
  loader: (
    source: string,
    revision: string,
    signal: AbortSignal,
  ) => Promise<Blob> = getOriginalBlob,
  urls: Pick<typeof URL, 'createObjectURL' | 'revokeObjectURL'> = URL,
) {
  const scope = createRequestScope()
  let url: string | undefined
  function clear() {
    if (url) urls.revokeObjectURL(url)
    url = undefined
  }
  return {
    async load(source: string, revision: string) {
      const ticket = scope.begin(`${source}/${revision}`)
      clear()
      const blob = await loader(source, revision, ticket.signal)
      if (!ticket.isCurrent()) return undefined
      url = urls.createObjectURL(blob)
      return url
    },
    dispose() {
      scope.dispose()
      clear()
    },
  }
}

export function createImageDownload(
  downloader: (
    source: string,
    revision: string,
    filename: string,
    signal: AbortSignal,
  ) => Promise<void> = downloadOriginal,
) {
  const scope = createRequestScope()
  return {
    async load(
      source: string,
      revision: string,
      filename: string,
      onError: (message: string) => void,
    ) {
      const ticket = scope.begin(`${source}/${revision}`)
      try {
        await downloader(source, revision, filename, ticket.signal)
      } catch (e) {
        ticket.apply(() => onError(errorMessage(e)))
      }
    },
    dispose() {
      scope.dispose()
    },
  }
}
