import type { Source, SourceRevision, SourceTask, SourceDocument } from '@akb/shared'
import { getApiClient } from './client'
export async function listSources(signal?: AbortSignal) {
  return (await getApiClient().get<{ items: Source[] }>('/sources', { signal })).data.items
}
export async function createSource(
  name: string,
  knowledgeBaseId: string,
  signal?: AbortSignal,
  options: Pick<Source, 'kind' | 'config'> = { kind: 'document' },
) {
  return (
    await getApiClient().post<Source>(
      '/sources',
      { name, knowledge_base_id: knowledgeBaseId, ...options },
      { signal },
    )
  ).data
}
export async function uploadRevision(id: string, file: File, signal?: AbortSignal) {
  const body = new FormData()
  body.append('file', file)
  return (await getApiClient().post<SourceTask>(`/sources/${id}/revisions`, body, { signal })).data
}
export async function getSourceTask(id: string, signal?: AbortSignal) {
  return (await getApiClient().get<SourceTask>(`/source-tasks/${id}`, { signal })).data
}
export async function listRevisions(id: string, signal?: AbortSignal) {
  return (
    await getApiClient().get<{ items: SourceRevision[] }>(`/sources/${id}/revisions`, { signal })
  ).data.items
}
export async function archiveSource(id: string, signal?: AbortSignal) {
  return (await getApiClient().post<Source>(`/sources/${id}/archive`, {}, { signal })).data
}
export async function downloadOriginal(
  source: string,
  revision: string,
  filename = 'original',
  signal?: AbortSignal,
) {
  const response = await getApiClient().get<Blob>(
    `/sources/${source}/revisions/${revision}/original`,
    { responseType: 'blob', signal },
  )
  if (signal?.aborted) return
  const url = URL.createObjectURL(response.data)
  const link = document.createElement('a')
  link.href = url
  const disposition = String(response.headers['content-disposition'] || '')
  const encoded = /filename\*=UTF-8''([^;]+)/i.exec(disposition)?.[1]
  const plain = /filename="?([^";]+)"?/i.exec(disposition)?.[1]
  let downloadName = plain || filename
  if (encoded) {
    try {
      downloadName = decodeURIComponent(encoded)
    } catch {
      /* use filename fallback */
    }
  }
  link.download = downloadName.replace(/[/\\]/g, '_')
  link.click()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}
export async function listRepoRoots(signal?: AbortSignal) {
  return (
    await getApiClient().get<{ items: { id: string; label: string }[] }>('/source-repo-roots', {
      signal,
    })
  ).data.items
}
export async function syncSource(id: string, signal?: AbortSignal) {
  return (await getApiClient().post<SourceTask>(`/sources/${id}/sync`, {}, { signal })).data
}
export async function listRevisionDocuments(
  source: string,
  revision: string,
  signal?: AbortSignal,
) {
  return (
    await getApiClient().get<{ items: SourceDocument[] }>(
      `/sources/${source}/revisions/${revision}/documents`,
      { signal },
    )
  ).data.items
}
export async function getRevisionDocument(
  source: string,
  revision: string,
  document: string,
  signal?: AbortSignal,
) {
  return (
    await getApiClient().get<{ content: string }>(
      `/sources/${source}/revisions/${revision}/documents/${document}`,
      { signal },
    )
  ).data.content
}
export async function updateSourceScope(id: string, includePaths: string[], signal?: AbortSignal) {
  return (
    await getApiClient().patch<Source>(
      `/sources/${id}/scope`,
      { include_paths: includePaths },
      { signal },
    )
  ).data
}
export async function uploadImageRevision(
  id: string,
  file: File,
  manualDescription = '',
  expectedRevisionId?: string,
  signal?: AbortSignal,
) {
  const body = new FormData()
  body.append('file', file)
  body.append('manual_description', manualDescription)
  if (expectedRevisionId) body.append('expected_revision_id', expectedRevisionId)
  return (await getApiClient().post<SourceTask>(`/sources/${id}/image-revisions`, body, { signal }))
    .data
}
export async function updateImageText(
  id: string,
  expectedRevisionId: string,
  manualDescription: string,
  ocrCorrection: string,
  signal?: AbortSignal,
) {
  return (
    await getApiClient().patch<SourceTask>(
      `/sources/${id}/image-text`,
      {
        expected_revision_id: expectedRevisionId,
        manual_description: manualDescription,
        ocr_correction: ocrCorrection,
      },
      { signal },
    )
  ).data
}
export async function reextractImage(id: string, expectedRevisionId: string, signal?: AbortSignal) {
  return (
    await getApiClient().post<SourceTask>(
      `/sources/${id}/image-reextract`,
      { expected_revision_id: expectedRevisionId },
      { signal },
    )
  ).data
}
export async function getOriginalBlob(source: string, revision: string, signal?: AbortSignal) {
  return (
    await getApiClient().get<Blob>(`/sources/${source}/revisions/${revision}/original`, {
      responseType: 'blob',
      signal,
    })
  ).data
}
