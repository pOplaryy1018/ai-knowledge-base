<script setup lang="ts">
/**
 * Markdown 预览组件 — markdown-it + highlight.js 渲染
 */
import { computed } from 'vue'
import MarkdownIt from 'markdown-it'
import hljs from 'highlight.js'
import 'highlight.js/styles/github.css'

const props = withDefaults(
  defineProps<{
    content: string
    maxHeight?: string
  }>(),
  {
    maxHeight: '500px'},
)

const md = new MarkdownIt({
  html: false,
  linkify: true,
  typographer: true,
  highlight(str: string, lang: string) {
    if (lang && hljs.getLanguage(lang)) {
      try {
        return hljs.highlight(str, { language: lang }).value
      } catch {
        /* fall through */
      }
    }
    return ''
  }})

const renderedHtml = computed(() => md.render(props.content))
</script>

<template>
  <div
    class="markdown-preview"
    :style="{ maxHeight }"
  >
    <div
      class="markdown-body"
      v-html="renderedHtml"
    />
  </div>
</template>

<style scoped>
.markdown-preview {
  overflow-y: auto;
  padding: 12px 16px;
  background: var(--color-bg-card-alt);
  border: 1px solid var(--border-color);
  border-radius: var(--akb-btn-radius);
}

.markdown-body :deep(h1),
.markdown-body :deep(h2),
.markdown-body :deep(h3) {
  margin: 16px 0 8px;
  color: var(--akb-text);
}

.markdown-body :deep(h1) {
  font-size: 20px;
}

.markdown-body :deep(h2) {
  font-size: 18px;
}

.markdown-body :deep(h3) {
  font-size: 16px;
}

.markdown-body :deep(p) {
  margin: 8px 0;
  line-height: 1.7;
  color: var(--akb-text);
}

.markdown-body :deep(pre) {
  background: var(--color-bg);
  border-radius: var(--akb-btn-radius);
  padding: 12px 16px;
  overflow-x: auto;
  margin: 8px 0;
}

.markdown-body :deep(code) {
  font-family: 'Fira Code', 'Consolas', monospace;
  font-size: 13px;
}

.markdown-body :deep(blockquote) {
  border-left: 4px solid var(--akb-primary);
  padding: 8px 16px;
  margin: 8px 0;
  background: var(--color-primary-light);
  color: var(--akb-text-secondary);
}

.markdown-body :deep(ul),
.markdown-body :deep(ol) {
  padding-left: 24px;
  margin: 8px 0;
}

.markdown-body :deep(table) {
  border-collapse: collapse;
  width: 100%;
  margin: 8px 0;
}

.markdown-body :deep(th),
.markdown-body :deep(td) {
  border: 1px solid var(--border-color);
  padding: 8px 12px;
  text-align: left;
}

.markdown-body :deep(th) {
  background: var(--color-bg);
  font-weight: 600;
}
</style>
