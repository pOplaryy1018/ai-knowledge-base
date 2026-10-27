import type { Source, SourceCitation } from '@akb/shared'
import { getApiClient } from './client'

export async function listSources(signal?: AbortSignal): Promise<Source[]> {
  return (await getApiClient().get<{ items: Source[] }>('/sources', { signal })).data.items
}

export async function downloadCitationOriginal(citation: SourceCitation): Promise<void> {
  const response = await getApiClient().get<Blob>(
    `/sources/${citation.source_id}/revisions/${citation.revision_id}/original`,
    { responseType: 'blob' },
  )
  const url = URL.createObjectURL(response.data)
  try {
    const link = document.createElement('a')
    link.href = url
    link.download = '引用原件'
    link.click()
  } finally {
    setTimeout(() => URL.revokeObjectURL(url), 1000)
  }
}
