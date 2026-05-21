<script setup lang="ts">
/**
 * 知识库卡片 — 仿飞书云文档风格
 */
import { computed, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import { IconMore, IconEdit, IconDelete, IconFolder } from '@arco-design/web-vue/es/icon'
import type { KnowledgeBase } from '@akb/shared'
import { timeAgo } from '@/utils/timeAgo'

const props = defineProps<{
  kb: KnowledgeBase
  onDelete: (id: string, name: string) => Promise<boolean>
  onEdit: (kb: KnowledgeBase) => void
}>()

const router = useRouter()

// ── 预设渐变色（根据 ID 字符码取模） ──
const GRADIENTS: [string, string][] = [
  ['#122E8A', '#4B3F72'],
  ['#122E8A', '#1A5C8A'],
  ['#122E8A', '#8A4B12'],
  ['#122E8A', '#2D5AA0'],
  ['#0F2570', '#6B3A6B'],
  ['#122E8A', '#3A6B8A'],
  ['#1A3DAA', '#5C4B1A'],
  ['#122E8A', '#7A4B5C'],
]

const gradientStyle = computed(() => {
  const hash = [...props.kb.id].reduce((acc, ch) => acc + ch.charCodeAt(0), 0)
  const [from, to] = GRADIENTS[hash % GRADIENTS.length]
  return { background: `linear-gradient(135deg, ${from}, ${to})` }
})

function handleCardClick() {
  router.push(`/workspace/knowledge-bases/${props.kb.id}`)
}

async function handleSelect(value: string | number | Record<string, any> | undefined) {
  if (value === 'edit') {
    props.onEdit(props.kb)
  } else if (value === 'delete') {
    await nextTick()
    await props.onDelete(props.kb.id, props.kb.name)
  }
}
</script>

<template>
  <div class="kb-card">
    <!-- 封面区域 -->
    <div
      class="kb-card-cover"
      :style="gradientStyle"
      @click="handleCardClick"
    >
      <span class="kb-card-cover-icon">
        <IconFolder :size="36" />
      </span>

      <!-- 更多操作按钮 -->
      <div class="kb-card-more">
        <a-dropdown
          trigger="click"
          @select="handleSelect"
        >
          <a-button
            type="text"
            size="small"
            class="kb-card-more-btn"
            @click.stop
          >
            <template #icon>
              <IconMore />
            </template>
          </a-button>
          <template #content>
            <a-doption value="edit">
              <template #icon>
                <IconEdit />
              </template>
              重命名
            </a-doption>
            <a-doption value="delete">
              <template #icon>
                <IconDelete />
              </template>
              删除
            </a-doption>
          </template>
        </a-dropdown>
      </div>
    </div>

    <!-- 信息区域 -->
    <div
      class="kb-card-body"
      @click="handleCardClick"
    >
      <h3
        class="kb-card-name"
        :title="kb.name"
      >
        {{ kb.name }}
      </h3>
      <p
        v-if="kb.description"
        class="kb-card-desc"
      >
        {{ kb.description }}
      </p>
      <p
        v-else
        class="kb-card-desc kb-card-desc--empty"
      >
&nbsp;
      </p>
      <div class="kb-card-meta">
        <span class="kb-card-time">{{ timeAgo(kb.updated_at) }}</span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.kb-card {
  background: var(--color-bg-card);
  border-radius: 12px;
  cursor: pointer;
  box-shadow: var(--shadow-card);
  transition: transform 0.2s ease, box-shadow 0.2s ease;
}
.kb-card:hover {
  transform: translateY(-2px);
  box-shadow: var(--shadow-card-hover);
}

.kb-card-cover {
  position: relative;
  aspect-ratio: 3 / 2;
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
  border-radius: 12px 12px 0 0;
}
.kb-card-cover-icon {
  color: rgba(255, 255, 255, 0.85);
  display: flex;
}

.kb-card-more {
  position: absolute;
  top: 8px;
  right: 8px;
  z-index: 2;
  opacity: 0;
  transition: opacity 0.15s ease;
}
.kb-card:hover .kb-card-more {
  opacity: 1;
}
.kb-card-more-btn {
  background: rgba(18, 46, 138, 0.2) !important;
  color: #fff !important;
  border-radius: 6px;
  backdrop-filter: blur(4px);
}
.kb-card-more-btn:hover {
  background: rgba(18, 46, 138, 0.35) !important;
}

.kb-card-body {
  padding: 14px 16px;
}
.kb-card-name {
  margin: 0 0 4px;
  font-size: 16px;
  font-weight: 600;
  color: var(--color-text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.kb-card-desc {
  margin: 0 0 10px;
  font-size: 12px;
  color: var(--color-text-tertiary);
  line-height: 1.5;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  min-height: 18px;
}
.kb-card-desc--empty {
  visibility: hidden;
}
.kb-card-meta {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 12px;
  color: var(--color-text-tertiary);
}
.kb-card-files {
  color: var(--color-text-secondary);
}
</style>
