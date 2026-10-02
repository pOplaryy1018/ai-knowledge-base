<script setup lang="ts">
import { computed, onUnmounted, ref, watch } from 'vue'
import type { Source, SourceRevision, SourceTask } from '@akb/shared'
import {
  uploadImageRevision,
  updateImageText,
  reextractImage,
} from '@/api/sources'
import { createImageDownload, createImageEditorSession, createImagePreview, imageStatusLabel } from '@/utils/image-source'
import { createRequestScope } from '@/utils/request-scope'
import { errorMessage, versionLabel } from '@/utils/review-state'
const props = defineProps<{ source: Source; revisions: SourceRevision[]; busy: boolean }>()
const emit = defineEmits<{ task: [task: SourceTask]; refresh: [] }>()
const revisionId = ref(''),
  uploadDescription = ref('')
const file = ref<File>(),
  previewUrl = ref(''),
  error = ref(''),
  uploadInput = ref<HTMLInputElement>()
const preview = createImagePreview(),
  imageDownload = createImageDownload(),
  previewScope = createRequestScope()
const revision = computed(() => props.revisions.find((item) => item.id === revisionId.value))
const editor = createImageEditorSession(() => props.source, revisionId, () => revision.value)
const { pending, description, correction } = editor
const historical = computed(() => revisionId.value !== props.source.current_revision_id)
const disabled = computed(
  () => props.busy || pending.value || !!props.source.archived_at || !!props.source.active_task_id,
)
watch(
  () => JSON.stringify([props.source.id, props.source.current_revision_id]),
  () => {
    error.value = ''
    file.value = undefined
    uploadDescription.value = ''
    revisionId.value = props.source.current_revision_id || ''
  },
  { immediate: true },
)
watch(
  () => JSON.stringify([props.source.id, revisionId.value]),
  async () => {
    const request = previewScope.begin(`${props.source.id}/${revisionId.value}`)
    imageDownload.dispose()
    preview.dispose()
    previewUrl.value = ''
    error.value = ''
    if (!revisionId.value) return
    try {
      const url = await preview.load(props.source.id, revisionId.value)
      request.apply(() => {
        previewUrl.value = url || ''
      })
    } catch (e) {
      request.apply(() => {
        error.value = errorMessage(e)
      })
    }
  },
  { immediate: true },
)
function choose(event: Event) {
  file.value = (event.target as HTMLInputElement).files?.[0]
  uploadDescription.value = ''
}
async function mutate(action: (signal: AbortSignal) => Promise<SourceTask>) {
  if (disabled.value) return
  error.value = ''
  await editor.run(action, task => {
    file.value = undefined
    if (uploadInput.value) uploadInput.value.value = ''
    uploadDescription.value = ''
    emit('task', task)
  }, message => { error.value = message })
}

function upload() {
  const selectedFile = file.value,
    source = props.source
  if (!selectedFile) return
  const head = source.current_revision_id || undefined,
    caption = uploadDescription.value
  void mutate((signal) => uploadImageRevision(source.id, selectedFile, caption, head, signal))
}
function save() {
  const id = revisionId.value,
    source = props.source.id,
    caption = description.value,
    text = correction.value
  if (!id || historical.value) return
  void mutate((signal) => updateImageText(source, id, caption, text, signal))
}
function reextract() {
  const id = revisionId.value,
    source = props.source.id
  if (!id || historical.value) return
  void mutate((signal) => reextractImage(source, id, signal))
}
onUnmounted(() => {
  imageDownload.dispose()
  preview.dispose()
  editor.dispose()
  previewScope.dispose()
})
</script>
<template>
  <a-space
    direction="vertical"
    fill
  >
    <a-alert
      v-if="error"
      type="error"
    >
      {{ error }}。可刷新资料后重试。
    </a-alert>
    <a-button
      :disabled="pending"
      @click="emit('refresh')"
    >
      刷新图片资料
    </a-button>
    <a-card title="上传图片新版">
      <p>PNG / JPEG / WebP · 单帧 · 最多 10 MiB、2000 万像素。新图片的文字不会继承旧版。</p>
      <input
        ref="uploadInput"
        :key="source.id"
        type="file"
        accept="image/png,image/jpeg,image/webp,.png,.jpg,.jpeg,.webp"
        :disabled="disabled"
        @change="choose"
      >
      <a-textarea
        v-model="uploadDescription"
        :textarea-attrs="{ 'aria-label': '新图片描述' }"
        placeholder="新图片描述（可留空）"
        :disabled="disabled"
      />
      <a-button
        :disabled="disabled || !file"
        @click="upload"
      >
        上传图片新版
      </a-button>
    </a-card>
    <a-space wrap>
      <a-button
        v-for="item in revisions"
        :key="item.id"
        :disabled="pending"
        @click="revisionId = item.id"
      >
        查看图片版本 {{ item.id }}
      </a-button>
    </a-space>
    <a-card
      v-if="revisionId"
      :title="`${versionLabel(revisionId)}${historical ? ' · 历史版本（只读）' : ' · 当前版本'}`"
    >
      <img
        v-if="previewUrl"
        :src="previewUrl"
        alt="图片原件"
        style="max-width: 100%; max-height: 480px; object-fit: contain"
      >
      <p v-else>
        图片原件暂不可用
      </p>
      <a-button
        @click="
          imageDownload.load(source.id, revisionId, revision?.filename || '图片原件', message => error = message)
        "
      >
        下载图片原件 {{ revisionId }}
      </a-button>
      <a-alert>{{ imageStatusLabel(revision?.manifest) }}</a-alert>
      <p v-if="revision?.manifest?.image">
        {{ revision.manifest.image.width }} × {{ revision.manifest.image.height }} ·
        {{ revision.manifest.image.format }}
      </p>
      <h4>机器OCR（只读）</h4>
      <pre style="white-space: pre-wrap">{{ revision?.manifest?.ocr_text || '无机器OCR文字' }}</pre>
      <h4>人工描述</h4>
      <a-textarea
        v-model="description"
        :textarea-attrs="{ 'aria-label': '人工描述' }"
        :disabled="disabled || historical"
      />
      <h4>人工OCR校正</h4>
      <a-textarea
        v-model="correction"
        :textarea-attrs="{ 'aria-label': '人工OCR校正' }"
        :disabled="disabled || historical"
      />
      <p>人工文字可清空；保存会发布新版本。OCR文字定位按行或字符，不提供图片区域框。</p>
      <a-space>
        <a-button
          :disabled="disabled || historical || !revision"
          @click="save"
        >
          保存图片文字
        </a-button><a-button
          :disabled="disabled || historical || !revision"
          @click="reextract"
        >
          重新提取图片文字
        </a-button>
      </a-space>
    </a-card>
  </a-space>
</template>
