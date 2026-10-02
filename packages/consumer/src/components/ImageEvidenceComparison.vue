<script setup lang="ts">
import { onUnmounted, ref, watch } from 'vue'
import type { EvidenceResult } from '@akb/shared'
import { getEvidence } from '@/api/answers'
import { createImagePreview, imageReasonLabel, loadImageEvidenceSides } from '@/utils/image-source'
import { createRequestScope } from '@/utils/request-scope'
const props = defineProps<{ evidence: EvidenceResult }>()
const oldUrl = ref(''),
  currentUrl = ref(''),
  oldError = ref(''),
  currentError = ref('')
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
    oldError.value = ''; currentError.value = ''
    await loadImageEvidenceSides(evidence, request, {
      old: (source, revision) => oldPreview.load(source, revision),
      current: (source, revision) => currentPreview.load(source, revision),
      lookup: getEvidence,
    }, (side, result) => {
      if (side === 'old') { oldUrl.value = result.url; oldError.value = result.error }
      else { currentUrl.value = result.url; currentError.value = result.error }
    })
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
    <div class="image-comparison">
      <div>
        <a-alert
          v-if="oldError"
          type="error"
        >
          引用时原图预览不可用：{{ oldError }}
        </a-alert>
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
        <a-alert
          v-if="currentError"
          type="error"
        >
          当前原图预览不可用：{{ currentError }}
        </a-alert>
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
