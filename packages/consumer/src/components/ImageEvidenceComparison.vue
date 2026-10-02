<script setup lang="ts">
import { onUnmounted, ref, watch } from 'vue'
import type { EvidenceResult } from '@akb/shared'
import { getEvidence } from '@/api/answers'
import { createImagePreview, imageReasonLabel } from '@/utils/image-source'
import { createRequestScope } from '@/utils/request-scope'
import { errorMessage } from '@/utils/review-state'
const props = defineProps<{ evidence: EvidenceResult }>()
const oldUrl = ref(''),
  currentUrl = ref(''),
  error = ref('')
const oldPreview = createImagePreview(),
  currentPreview = createImagePreview(),
  scope = createRequestScope()
watch(
  () => props.evidence,
  async (evidence) => {
    const request = scope.begin(evidence.evidence_id)
    oldPreview.dispose()
    currentPreview.dispose()
    oldUrl.value = ''
    currentUrl.value = ''
    error.value = ''
    if (evidence.state === 'unavailable' || !evidence.source_id) return
    try {
      let oldRevision = evidence.old_revision_id
      if (!oldRevision) {
        const original = await getEvidence(evidence.evidence_id, request.signal)
        if (!request.isCurrent() || original.source_id !== evidence.source_id) return
        oldRevision = original.revision_id
      }
      if (!request.isCurrent()) return
      const urls = await Promise.all([
        oldRevision ? oldPreview.load(evidence.source_id, oldRevision) : undefined,
        evidence.current_revision_id
          ? currentPreview.load(evidence.source_id, evidence.current_revision_id)
          : undefined,
      ])
      request.apply(() => {
        oldUrl.value = urls[0] || ''
        currentUrl.value = urls[1] || ''
      })
    } catch (e) {
      request.apply(() => {
        error.value = errorMessage(e)
      })
    }
  },
  { immediate: true },
)
onUnmounted(() => {
  scope.dispose()
  oldPreview.dispose()
  currentPreview.dispose()
})
</script>
<template>
  <a-space
    direction="vertical"
    fill
  >
    <a-alert
      v-if="imageReasonLabel(evidence.reason)"
      type="warning"
    >
      {{ imageReasonLabel(evidence.reason) }}。请人工查看原图与引用文字。
    </a-alert>
    <a-alert
      v-if="error"
      type="error"
    >
      原图预览不可用：{{ error }}
    </a-alert>
    <div class="image-comparison">
      <div>
        <strong>引用时原图</strong><img
          v-if="oldUrl"
          :src="oldUrl"
          alt="引用时原图"
        >
        <p v-else>
          引用时原图不可用
        </p>
      </div>
      <div>
        <strong>当前原图</strong><img
          v-if="currentUrl"
          :src="currentUrl"
          alt="当前原图"
        >
        <p v-else>
          当前原图不可用
        </p>
      </div>
    </div>
  </a-space>
</template>
<style scoped>
.image-comparison {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
}
.image-comparison img {
  display: block;
  max-width: 100%;
  max-height: 420px;
  object-fit: contain;
}
</style>
