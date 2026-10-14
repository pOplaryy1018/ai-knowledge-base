import type { WikiPageDetail, WikiPageSummary } from '@akb/shared'
import { getApiClient } from './client'
import { wikiExportFilename } from '@/utils/wiki'

export async function listWikiPages(q = '', signal?: AbortSignal) {
  return (await getApiClient().get<{ items: WikiPageSummary[] }>('/wiki/pages', { params: { q }, signal })).data.items
}

export async function getWikiPage(id: string, signal?: AbortSignal) {
  return (await getApiClient().get<WikiPageDetail>(`/wiki/pages/${id}`, { signal })).data
}

export async function createWikiPage(title: string, sourceIds: string[], signal?: AbortSignal) {
  return (await getApiClient().post<WikiPageDetail>('/wiki/pages', { title, source_ids: sourceIds }, { signal, timeout: 0 })).data
}

export async function updateWikiDraft(id: string, expectedRevisionId: string, title: string, content: string, signal?: AbortSignal) {
  return (await getApiClient().patch<WikiPageDetail>(`/wiki/pages/${id}/draft`, {
    expected_revision_id: expectedRevisionId, title, content,
  }, { signal })).data
}

export async function compileWikiPage(id: string, expectedRevisionId: string, sourceIds: string[], signal?: AbortSignal) {
  return (await getApiClient().post<WikiPageDetail>(`/wiki/pages/${id}/compile`, {
    expected_revision_id: expectedRevisionId, source_ids: sourceIds,
  }, { signal, timeout: 0 })).data
}

export async function publishWikiPage(id: string, expectedRevisionId: string, signal?: AbortSignal) {
  return (await getApiClient().post<WikiPageDetail>(`/wiki/pages/${id}/publish`, {
    expected_revision_id: expectedRevisionId,
  }, { signal })).data
}

export async function exportWikiMarkdown(id: string, signal?: AbortSignal) {
  const response = await getApiClient().get<Blob>(`/wiki/pages/${id}/export`, { responseType: 'blob', signal })
  return { blob: response.data, filename: wikiExportFilename(String(response.headers['content-disposition'] || ''), `wiki-${id}`) }
}
