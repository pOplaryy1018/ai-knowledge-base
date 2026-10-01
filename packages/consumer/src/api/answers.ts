import type { SavedAnswer, AnswerCandidate, ReviewSummary, ReviewDetail } from '@akb/shared'
import { getApiClient } from './client'
export async function listAnswers(page = 1, signal?: AbortSignal) {
  return (
    await getApiClient().get<{ items: SavedAnswer[] }>('/answers', {
      params: { page, size: 20 },
      signal,
    })
  ).data.items
}
export async function getAnswer(id: string, signal?: AbortSignal) {
  return (await getApiClient().get<SavedAnswer>(`/answers/${id}`, { signal })).data
}
export async function saveAnswer(messageId: string, signal?: AbortSignal) {
  return (await getApiClient().post<SavedAnswer>('/answers', { message_id: messageId }, { signal }))
    .data
}
export async function generateCandidate(id: string, signal?: AbortSignal) {
  return (await getApiClient().post<AnswerCandidate>(`/answers/${id}/candidates`, {}, { signal }))
    .data
}
export async function acceptCandidate(
  id: string,
  candidate: AnswerCandidate,
  signal?: AbortSignal,
) {
  return (
    await getApiClient().post<SavedAnswer>(
      `/answers/${id}/accept`,
      {
        candidate_id: candidate.id,
        expected_answer_revision_id: candidate.expected_answer_revision_id,
        expected_source_versions: candidate.source_versions,
      },
      { signal },
    )
  ).data
}
export async function listReviews(page = 1, signal?: AbortSignal) {
  return (
    await getApiClient().get<{ items: ReviewSummary[] }>('/reviews', {
      params: { page, size: 20 },
      signal,
    })
  ).data.items
}
export async function getReview(id: string, signal?: AbortSignal) {
  return (await getApiClient().get<ReviewDetail>(`/reviews/${id}`, { signal })).data
}
export async function retainReview(id: string, note: string, signal?: AbortSignal) {
  return (
    await getApiClient().post(`/reviews/${id}/decision`, { decision: 'retain', note }, { signal })
  ).data
}
export async function getEvidence(id: string, signal?: AbortSignal) {
  return (
    await getApiClient().get<{
      content: string
      source_id: string
      revision_id: string
      locator: Record<string, unknown>
    }>(`/evidence/${id}`, { signal })
  ).data
}
