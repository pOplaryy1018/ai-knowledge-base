<script setup lang="ts">
import { computed, onUnmounted, ref, watch } from 'vue'
import ComparisonCard from '@/components/ComparisonCard.vue'
import ImageEvidenceComparison from '@/components/ImageEvidenceComparison.vue'
import { useRoute } from 'vue-router'
import type { SavedAnswer, AnswerCandidate, EvidenceResult, SourceCitation } from '@akb/shared'
import { getAnswer, generateCandidate, acceptCandidate, getEvidence } from '@/api/answers'
import { downloadOriginal } from '@/api/sources'
import {
  answerStatusLabel,
  errorMessage,
  evidenceStateLabel,
  formatLocator,
  versionLabel,
} from '@/utils/review-state'
import { createRequestScope } from '@/utils/request-scope'
import type { RequestTicket } from '@/utils/request-scope'
const route = useRoute(),
  scope = createRequestScope(),
  answer = ref<SavedAnswer>(),
  candidate = ref<AnswerCandidate>(),
  error = ref(''),
  busy = ref(false)
const note = ref('')
const currentCitations = computed<SourceCitation[]>(() =>
  (answer.value?.evidence || [])
    .filter(
      (item) =>
        item.citation_index !== undefined &&
        !!item.old_text &&
        !!item.old_revision_id &&
        !!item.document_id,
    )
    .map((item) => ({
      index: item.citation_index!,
      source_id: item.source_id,
      revision_id: item.old_revision_id!,
      document_id: item.document_id!,
      content: item.old_text!,
      locator: item.old_locator,
    })),
)
async function cardOriginal(citation: SourceCitation, request: RequestTicket) {
  await downloadOriginal(citation.source_id, citation.revision_id, '引用原件', request.signal)
}
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
  const result = await getAnswer(request.id, request.signal)
  if (result.id === request.id)
    request.apply(() => {
      answer.value = result
    })
}
function changeRoute() {
  ticket = scope.begin(String(route.params.id))
  answer.value = undefined
  candidate.value = undefined
  error.value = ''
  busy.value = false
  note.value = ''
  void act(load)
}
async function generate(request: RequestTicket) {
  const id = answer.value?.id
  if (!id) return
  const result = await generateCandidate(id, request.signal)
  request.apply(() => {
    candidate.value = result
  })
}
async function adopt(request: RequestTicket) {
  const id = answer.value?.id,
    chosen = candidate.value
  if (!id || !chosen) return
  const result = await acceptCandidate(id, chosen, request.signal)
  if (result.id !== id || !request.isCurrent()) return
  request.apply(() => {
    answer.value = result
  })
  request.apply(() => {
    candidate.value = undefined
  })
}
async function original(evidence: EvidenceResult, request: RequestTicket) {
  const result = await getEvidence(evidence.evidence_id, request.signal)
  if (request.isCurrent())
    await downloadOriginal(result.source_id, result.revision_id, '引用原件', request.signal)
}
watch(() => route.params.id, changeRoute, { immediate: true })
onUnmounted(() => scope.dispose())
</script>
<template>
  <a-space
    direction="vertical"
    fill
  >
    <h2>{{ answer?.question || '答案详情' }}</h2>
    <a-alert
      v-if="error"
      type="error"
    >
      {{ error }}
    </a-alert><template v-if="answer">
      <a-tag>{{ answerStatusLabel(answer.status) }}</a-tag><a-card title="当前采纳答案">
        <ComparisonCard
          v-if="answer.comparison"
          :comparison="answer.comparison"
          :citations="currentCitations"
          @original="(citation) => act((request) => cardOriginal(citation, request))"
        />
        <p
          v-else
          style="white-space: pre-wrap"
        >
          {{ answer.content }}
        </p>
        <p>本答案依据 {{ Object.keys(answer.source_versions).length }} 个资料版本。</p>
      </a-card>
      <h3>引用证据 · 当前比对</h3>
      <a-card
        v-for="(evidence, evidenceIndex) in answer.evidence"
        :key="evidence.evidence_id"
        :title="`引用证据 ${evidenceIndex + 1} · ${evidenceStateLabel(evidence.state)}`"
      >
        <a-space
          direction="vertical"
          fill
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
          <strong>引用时原文</strong>
          <p>{{ evidence.old_text || '不可用' }}</p>
          <pre>{{ formatLocator(evidence.old_locator) }}</pre>
          <strong>当前原文 · {{ versionLabel(evidence.current_revision_id) }}</strong>
          <p>{{ evidence.current_text || '无可确认匹配' }}</p>
          <pre>{{ formatLocator(evidence.locator) }}</pre>
          <a-button @click="act((request) => original(evidence, request))">
            下载引用时原件
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
            下载当前原件
          </a-button>
        </a-space>
      </a-card><a-alert v-if="!answer.evidence.length">
        此答案没有可追踪引用，不能据此判断资料是否变化。
      </a-alert><a-button
        :disabled="busy"
        @click="act(generate)"
      >
        按当前资料生成候选答案
      </a-button><a-card
        v-if="candidate"
        title="候选答案（尚未采纳）"
      >
        <a-alert
          v-if="candidate.warning"
          type="warning"
        >
          {{ candidate.warning }}
        </a-alert>
        <ComparisonCard
          v-if="candidate.comparison"
          :comparison="candidate.comparison"
          :citations="candidate.citations"
          @original="(citation) => act((request) => cardOriginal(citation, request))"
        />
        <p
          v-else
          style="white-space: pre-wrap"
        >
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
      </a-card><a-collapse>
        <a-collapse-item
          v-for="(version, versionIndex) in answer.versions"
          :key="version.id"
          :header="`第 ${versionIndex + 1} 版 · ${version.kind === 'candidate' ? '候选' : '保存'} · ${new Date(version.created_at).toLocaleString()}`"
        >
          <ComparisonCard
            v-if="version.comparison"
            :comparison="version.comparison"
            :citations="version.citations"
            @original="(citation) => act((request) => cardOriginal(citation, request))"
          />
          <p
            v-else
            style="white-space: pre-wrap"
          >
            {{ version.content }}
          </p>
          <p>依据 {{ Object.keys(version.source_versions).length }} 个资料版本。</p>
        </a-collapse-item>
      </a-collapse>
    </template>
  </a-space>
</template>
