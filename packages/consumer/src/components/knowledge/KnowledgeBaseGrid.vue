<script setup lang="ts">
/**
 * 知识库网格容器 — 骨架屏 + 空状态 + 错误重试 + 新建入口卡片
 */
import KnowledgeBaseCard from './KnowledgeBaseCard.vue'
import type { KnowledgeBase } from '@akb/shared'

defineProps<{
  items: KnowledgeBase[]
  isLoading: boolean
  isError: boolean
  onDelete: (id: string, name: string) => Promise<boolean>
  onEdit: (kb: KnowledgeBase) => void
  onCreate: () => void
  onRetry: () => void
}>()
</script>

<template>
  <div class="kb-grid-wrapper">
    <!-- 骨架屏 -->
    <template v-if="isLoading">
      <div
        v-for="i in 8"
        :key="i"
        class="kb-card kb-card--skeleton"
      >
        <div class="skeleton-cover" />
        <div class="skeleton-body">
          <div class="skeleton-line skeleton-line--title" />
          <div class="skeleton-line skeleton-line--desc" />
          <div class="skeleton-line skeleton-line--meta" />
        </div>
      </div>
    </template>

    <!-- 错误状态 -->
    <div
      v-else-if="isError"
      class="kb-grid-error"
    >
      <a-empty description="加载失败，请检查网络连接">
        <a-button
          type="primary"
          @click="onRetry"
        >
          重试
        </a-button>
      </a-empty>
    </div>

    <!-- 卡片网格 -->
    <template v-else>
      <KnowledgeBaseCard
        v-for="kb in items"
        :key="kb.id"
        :kb="kb"
        :on-delete="onDelete"
        :on-edit="onEdit"
      />

      <!-- 空状态（无数据且不在加载/错误中） -->
      <div
        v-if="items.length === 0"
        class="kb-grid-empty"
      >
        <a-empty description="还没有知识库">
          <a-button
            type="primary"
            @click="onCreate"
          >
            创建第一个知识库
          </a-button>
        </a-empty>
      </div>
    </template>
  </div>
</template>

<style scoped>
.kb-grid-wrapper {
  display: grid;
  grid-template-columns: repeat(6, 1fr);
  gap: 16px;
}

@media (max-width: 1600px) {
  .kb-grid-wrapper { grid-template-columns: repeat(5, 1fr); }
}
@media (max-width: 1280px) {
  .kb-grid-wrapper { grid-template-columns: repeat(4, 1fr); }
}
@media (max-width: 960px) {
  .kb-grid-wrapper { grid-template-columns: repeat(3, 1fr); }
}
@media (max-width: 640px) {
  .kb-grid-wrapper { grid-template-columns: repeat(2, 1fr); }
}

/* 骨架屏 */
.kb-card--skeleton {
  pointer-events: none;
}
.skeleton-cover {
  aspect-ratio: 3 / 2;
  background: linear-gradient(90deg, var(--color-bg) 25%, var(--color-bg-card-alt) 50%, var(--color-bg) 75%);
  background-size: 200% 100%;
  animation: shimmer 1.5s infinite;
}
.skeleton-body {
  padding: 14px 16px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.skeleton-line {
  height: 14px;
  border-radius: 4px;
  background: linear-gradient(90deg, var(--color-bg) 25%, var(--color-bg-card-alt) 50%, var(--color-bg) 75%);
  background-size: 200% 100%;
  animation: shimmer 1.5s infinite;
}
.skeleton-line--title { width: 60%; height: 16px; }
.skeleton-line--desc  { width: 85%; }
.skeleton-line--meta  { width: 40%; }

@keyframes shimmer {
  0%   { background-position: 200% 0; }
  100% { background-position: -200% 0; }
}

/* 错误 / 空状态 */
.kb-grid-error,
.kb-grid-empty {
  grid-column: 1 / -1;
  display: flex;
  justify-content: center;
  padding: 80px 0;
}
</style>
