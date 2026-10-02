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
import { computed, ref, watch } from 'vue'
import type { Ref } from 'vue'
import type { Source, EvidenceResult } from '@akb/shared'
import type { RequestTicket } from './request-scope'
export function createImageEditorSession(
  source: () => Pick<Source, 'id' | 'current_revision_id'>,
  selectedRevision: Ref<string>,
  revision: () => Pick<SourceRevision, 'id' | 'manifest'> | undefined,
) {
  const scope = createRequestScope(),
    pending = ref(false),
    description = ref(''),
    correction = ref('')
  const identity = computed(() =>
    JSON.stringify([source().id, source().current_revision_id, selectedRevision.value]),
  )
  let hydrated = false
  const stopIdentity = watch(
    identity,
    () => {
      scope.dispose()
      pending.value = false
      hydrated = false
      description.value = ''
      correction.value = ''
    },
    { flush: 'sync' },
  )
  const stopHydrate = watch(
    () => [identity.value, revision()],
    () => {
      const item = revision()
      if (hydrated || !item || item.id !== selectedRevision.value) return
      description.value = item.manifest?.manual_description || ''
      correction.value = item.manifest?.ocr_correction || ''
      hydrated = true
    },
    { immediate: true, flush: 'sync' },
  )
  return {
    pending,
    description,
    correction,
    async run<T>(
      action: (signal: AbortSignal) => Promise<T>,
      onSuccess: (value: T) => void,
      onError: (message: string) => void,
    ) {
      const request = scope.begin(identity.value)
      pending.value = true
      try {
        const result = await action(request.signal)
        request.apply(() => onSuccess(result))
      } catch (e) {
        request.apply(() => onError(errorMessage(e)))
      } finally {
        request.apply(() => {
          pending.value = false
        })
      }
    },
    dispose() {
      stopIdentity()
      stopHydrate()
      scope.dispose()
      pending.value = false
    },
  }
}
export async function loadImageEvidenceSides(
  evidence: EvidenceResult,
  request: RequestTicket,
  loaders: {
    old: (source: string, revision: string) => Promise<string | undefined>
    current: (source: string, revision: string) => Promise<string | undefined>
    lookup: (id: string, signal: AbortSignal) => Promise<{ source_id: string; revision_id: string }>
  },
  update: (side: 'old' | 'current', result: { url: string; error: string }) => void,
) {
  if (evidence.state === 'unavailable' || !evidence.source_id) return
  async function loadSide(side: 'old' | 'current') {
    try {
      let revision = side === 'old' ? evidence.old_revision_id : evidence.current_revision_id
      if (side === 'old' && !revision) {
        const original = await loaders.lookup(evidence.evidence_id, request.signal)
        if (!request.isCurrent()) return
        if (original.source_id !== evidence.source_id) throw new Error('引用原件来源不匹配')
        revision = original.revision_id
      }
      if (!revision || !request.isCurrent()) return
      const url = await loaders[side](evidence.source_id, revision)
      request.apply(() => update(side, { url: url || '', error: '' }))
    } catch (e) {
      request.apply(() => update(side, { url: '', error: errorMessage(e) }))
    }
  }
  await Promise.allSettled([loadSide('old'), loadSide('current')])
}
