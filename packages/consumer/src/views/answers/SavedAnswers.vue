<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'
import type { SavedAnswer, ReviewSummary } from '@akb/shared'
import { listAnswers, listReviews } from '@/api/answers'
import { answerStatusLabel, errorMessage } from '@/utils/review-state'
const controller = new AbortController(),
  answers = ref<SavedAnswer[]>([]),
  reviews = ref<ReviewSummary[]>([]),
  page = ref(1),
  error = ref(''),
  busy = ref(false)
async function load(next = page.value) {
  busy.value = true
  error.value = ''
  try {
    const [a, r] = await Promise.all([
      listAnswers(next, controller.signal),
      listReviews(next, controller.signal),
    ])
    answers.value = a
    reviews.value = r
    page.value = next
  } catch (e) {
    if (!controller.signal.aborted) error.value = errorMessage(e)
  } finally {
    busy.value = false
  }
}
onMounted(() => {
  void load()
})
onUnmounted(() => controller.abort())
</script>
<template>
  <a-space
    direction="vertical"
    fill
  >
    <h2>已保存答案</h2>
    <a-alert
      v-if="error"
      type="error"
    >
      {{ error }}
    </a-alert><a-list>
      <a-list-item
        v-for="answer in answers"
        :key="answer.id"
      >
        <a-space>
          <router-link :to="`/workspace/answers/${answer.id}`">
            {{ answer.question }}
          </router-link><a-tag>{{ answerStatusLabel(answer.status) }}</a-tag>
        </a-space>
      </a-list-item>
    </a-list>
    <h3>复核记录</h3>
    <a-list>
      <a-list-item
        v-for="review in reviews"
        :key="review.id"
      >
        <router-link :to="`/workspace/reviews/${review.id}`">
          {{ review.question }} · {{ review.decision }}
        </router-link>
      </a-list-item>
    </a-list><a-space>
      <a-button
        :disabled="page === 1 || busy"
        @click="load(page - 1)"
      >
        上一页
      </a-button><span>第 {{ page }} 页</span><a-button
        :disabled="busy || (answers.length < 20 && reviews.length < 20)"
        @click="load(page + 1)"
      >
        下一页
      </a-button>
    </a-space>
  </a-space>
</template>
