<script setup lang="ts">
import { onUnmounted, ref, watch } from 'vue'
import ImageEvidenceComparison from '@/components/ImageEvidenceComparison.vue'
import { useRoute } from 'vue-router'
import type { ReviewDetail, AnswerCandidate, EvidenceResult } from '@akb/shared'
import {
  getReview,
  retainReview,
  generateCandidate,
  acceptCandidate,
  getEvidence,
} from '@/api/answers'
import { downloadOriginal } from '@/api/sources'
import { errorMessage, evidenceStateLabel, formatLocator, versionLabel } from '@/utils/review-state'
import { createRequestScope } from '@/utils/request-scope'
import type { RequestTicket } from '@/utils/request-scope'
const route = useRoute(),
  scope = createRequestScope(),
  review = ref<ReviewDetail>(),
  candidate = ref<AnswerCandidate>(),
  error = ref(''),
  busy = ref(false)
const note = ref('')
let ticket: RequestTicket
async function act(action: (request: RequestTicket) => Promise<void>) {
  const request = ticket
  if (!request?.isCurrent()) return
  error.value = ''
  busy.value = true
  try {
    await action(request)
  } catch (e) {
    request.apply(() => {
      error.value = errorMessage(e)
    })
  } finally {
    request.apply(() => {
      busy.value = false
    })
  }
}
async function load(request: RequestTicket) {
  const result = await getReview(request.id, request.signal)
  if (result.id === request.id)
    request.apply(() => {
      review.value = result
      note.value = result.note || ''
    })
}
function changeRoute() {
  ticket = scope.begin(String(route.params.id))
  review.value = undefined
  candidate.value = undefined
  error.value = ''
  busy.value = false
  note.value = ''
  void act(load)
}
async function generate(request: RequestTicket) {
  const id = review.value?.answer.id
  if (!id) return
  const result = await generateCandidate(id, request.signal)
  request.apply(() => {
    candidate.value = result
  })
}
async function adopt(request: RequestTicket) {
  const id = review.value?.answer.id,
    chosen = candidate.value
  if (!id || !chosen) return
  const result = await acceptCandidate(id, chosen, request.signal)
  if (result.id !== id || !request.isCurrent()) return
  await load(request)
  request.apply(() => {
    candidate.value = undefined
  })
}
async function original(evidence: EvidenceResult, request: RequestTicket) {
  const result = await getEvidence(evidence.evidence_id, request.signal)
  if (request.isCurrent())
    await downloadOriginal(result.source_id, result.revision_id, '引用原件', request.signal)
}
async function retain(request: RequestTicket) {
  const id = review.value?.id,
    reason = note.value.trim()
  if (!id || !reason) return
  await retainReview(id, reason, request.signal)
  if (request.isCurrent()) await load(request)
}
watch(() => route.params.id, changeRoute, { immediate: true })
onUnmounted(() => scope.dispose())
</script>
<template>
  <a-space
    direction="vertical"
    fill
  >
    <h2>答案复核</h2>
    <a-alert
      v-if="error"
      type="error"
    >
      {{ error }}
    </a-alert><template v-if="review">
      <h3>{{ review.answer.question }}</h3>
      <a-alert>复核决定：{{ review.decision }}。证据变化需要人工判断，不代表答案必然错误。</a-alert><router-link :to="`/workspace/answers/${review.answer.id}`">
        查看答案与完整历史
      </router-link><a-card title="当前采纳答案">
        <p style="white-space: pre-wrap">
          {{ review.answer.content }}
        </p>
      </a-card>
      <h3>当前实时证据比对</h3>
      <a-card
        v-for="(evidence, evidenceIndex) in review.answer.evidence"
        :key="evidence.evidence_id"
        :title="`引用证据 ${evidenceIndex + 1} · ${evidenceStateLabel(evidence.state)}`"
      >
        <ImageEvidenceComparison
          v-if="
            evidence.old_locator?.image_hash ||
              String(evidence.old_locator?.origin || '').startsWith('image_') ||
              evidence.old_locator?.origin === 'manual_description' ||
              evidence.reason?.startsWith('image_')
          "
          :evidence="evidence"
        />
        <strong>引用时文字</strong>
        <p>{{ evidence.old_text || '不可用' }}</p>
        <pre>{{ formatLocator(evidence.old_locator) }}</pre>
        <strong>当前文字 · {{ versionLabel(evidence.current_revision_id) }}</strong>
        <p>{{ evidence.current_text || '无可确认匹配' }}</p>
        <pre>{{ formatLocator(evidence.locator) }}</pre>
        <a-space>
          <a-button @click="act((request) => original(evidence, request))">
            引用时原件
          </a-button><a-button
            v-if="evidence.current_revision_id"
            @click="
              act((request) =>
                downloadOriginal(
                  evidence.source_id,
                  evidence.current_revision_id!,
                  '当前原件',
                  request.signal,
                ),
              )
            "
          >
            当前原件
          </a-button>
        </a-space>
      </a-card><a-collapse>
        <a-collapse-item header="事件发生时的历史比对快照（不是实时结果）">
          <a-card
            v-for="(evidence, index) in review.historical_evidence_results"
            :key="index"
            :title="evidenceStateLabel(evidence.state)"
          >
            <p>原文：{{ evidence.old_text }}</p>
            <pre>{{ formatLocator(evidence.old_locator) }}</pre>
            <p>当时文字：{{ evidence.current_text || '无匹配' }}</p>
            <pre>{{ formatLocator(evidence.locator) }}</pre>
          </a-card>
        </a-collapse-item>
      </a-collapse><a-textarea
        v-model="note"
        placeholder="保留原答案的理由（必填）"
        :max-length="2000"
      /><a-space>
        <a-button
          :disabled="!note.trim() || busy"
          @click="act(retain)"
        >
          保留原答案并记录理由
        </a-button><a-button
          :disabled="busy"
          @click="act(generate)"
        >
          生成候选答案
        </a-button>
      </a-space><a-card
        v-if="candidate"
        title="候选答案（尚未采纳）"
      >
        <p style="white-space: pre-wrap">
          {{ candidate.content }}
        </p>
        <a-collapse>
          <a-collapse-item
            v-for="citation in candidate.citations"
            :key="citation.index"
            :header="`引用 ${citation.index} · ${versionLabel(citation.revision_id)}`"
          >
            <p>{{ citation.content }}</p>
            <pre>{{ formatLocator(citation.locator) }}</pre>
          </a-collapse-item>
        </a-collapse><a-button
          :disabled="busy"
          @click="act(adopt)"
        >
          采纳候选
        </a-button>
      </a-card>
    </template>
  </a-space>
</template>
