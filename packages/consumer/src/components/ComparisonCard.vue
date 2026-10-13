<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import type { SourceComparison, SourceCitation, ComparisonCell } from '@akb/shared'
import { comparisonReferences, filterComparisonRows } from '@/utils/comparison'
import { formatLocator, versionLabel } from '@/utils/review-state'
const props = withDefaults(
  defineProps<{ comparison: SourceComparison; citations?: SourceCitation[] }>(),
  { citations: () => [] },
)
defineEmits<{ original: [citation: SourceCitation] }>()
const filter = ref('')
const selected = ref<SourceCitation>()
watch(
  () => props.comparison,
  () => {
    selected.value = undefined
    filter.value = ''
  },
)
const rows = computed(() => filterComparisonRows(props.comparison, filter.value))
function cell(row: (typeof rows.value)[number], sourceId: string): ComparisonCell {
  return (
    row.cells.find((item) => item.source_id === sourceId) || {
      source_id: sourceId,
      text: '未找到依据',
      citation_indices: [],
    }
  )
}
</script>
<template>
  <section
    class="comparison"
    aria-label="带引用的资料对比"
  >
    <div class="comparison-toolbar">
      <div>
        <strong>资料对比</strong>
        <p>结论仅依据本轮资料。未找到依据不代表资料明确否认。</p>
      </div>
      <a-input
        v-model="filter"
        allow-clear
        placeholder="筛选比较维度"
        aria-label="筛选比较维度"
      />
    </div>
    <div class="comparison-scroll">
      <table>
        <caption class="sr-only">
          所选资料按维度对比，点击引用查看原文
        </caption>
        <thead>
          <tr>
            <th scope="col">
              比较维度
            </th>
            <th
              v-for="source in comparison.sources"
              :key="source.source_id"
              scope="col"
            >
              {{ source.name }}<small>{{ versionLabel(source.revision_id) }}</small>
            </th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="row in rows"
            :key="row.dimension"
          >
            <th scope="row">
              {{ row.dimension }}
            </th>
            <td
              v-for="source in comparison.sources"
              :key="source.source_id"
            >
              <p :class="{ missing: !cell(row, source.source_id).citation_indices.length }">
                {{ cell(row, source.source_id).text }}
              </p>
              <button
                v-for="index in cell(row, source.source_id).citation_indices"
                :key="index"
                class="citation-button"
                :disabled="
                  !comparisonReferences(cell(row, source.source_id), citations).some(
                    (item) => item.index === index,
                  )
                "
                :aria-label="`查看 ${source.name} 的引用 ${index}`"
                @click="
                  selected = comparisonReferences(cell(row, source.source_id), citations).find(
                    (item) => item.index === index,
                  )
                "
              >
                [{{ index }}]
              </button>
              <small
                v-if="
                  cell(row, source.source_id).citation_indices.length &&
                    !comparisonReferences(cell(row, source.source_id), citations).length
                "
              >引用原文不可用</small>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
    <p
      v-if="!rows.length"
      role="status"
    >
      没有匹配的比较维度。
    </p>
    <section
      v-if="selected"
      class="comparison-evidence"
      aria-label="引用原文"
    >
      <div>
        <strong>引用 {{ selected.index }} · {{ versionLabel(selected.revision_id) }}</strong><a-button
          size="small"
          @click="selected = undefined"
        >
          收起引用
        </a-button>
      </div>
      <p>{{ selected.content }}</p>
      <pre>{{ formatLocator(selected.locator) }}</pre>
      <a-button @click="$emit('original', selected!)">
        下载引用版本原件
      </a-button>
    </section>
  </section>
</template>
<style scoped>
.comparison {
  border: 1px solid var(--color-border-2);
  border-radius: 8px;
  padding: 16px;
}
.comparison-toolbar {
  display: flex;
  align-items: flex-start;
  gap: 16px;
  justify-content: space-between;
  margin-bottom: 12px;
}
.comparison-toolbar p {
  margin: 6px 0 0;
  font-size: 12px;
  color: var(--color-text-3);
}
.comparison-toolbar .arco-input-wrapper {
  max-width: 220px;
}
.comparison-scroll {
  overflow-x: auto;
}
table {
  width: 100%;
  border-collapse: collapse;
  table-layout: fixed;
  min-width: 560px;
}
th,
td {
  padding: 12px;
  border-bottom: 1px solid var(--color-border-2);
  vertical-align: top;
  text-align: left;
  overflow-wrap: anywhere;
}
thead th {
  background: var(--color-fill-2);
}
th:first-child {
  width: 110px;
}
td p {
  margin: 0 0 8px;
  white-space: pre-wrap;
}
small {
  display: block;
  color: var(--color-text-3);
  font-weight: normal;
  margin-top: 4px;
}
.missing {
  color: var(--color-text-3);
}
.citation-button {
  border: 0;
  background: var(--color-fill-2);
  color: rgb(var(--primary-6));
  cursor: pointer;
  padding: 4px 8px;
  border-radius: 4px;
  margin-right: 6px;
}
.citation-button:disabled {
  color: var(--color-text-4);
  cursor: default;
}
.comparison-evidence {
  margin-top: 16px;
  padding-top: 12px;
  border-top: 1px solid var(--color-border-2);
}
.comparison-evidence > div {
  display: flex;
  justify-content: space-between;
}
.comparison-evidence p {
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}
pre {
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}
.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
}
@media (max-width: 600px) {
  .comparison-toolbar {
    flex-direction: column;
  }
  .comparison-toolbar .arco-input-wrapper {
    max-width: 100%;
  }
  .comparison {
    padding: 10px;
  }
}
</style>
