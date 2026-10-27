<script setup lang="ts">
import { computed, onUnmounted, ref, watch } from 'vue'
import type { Source, SourceGraphRelation, SourceGraphRelations, SourceGraphStatus } from '@akb/shared'
import { downloadOriginal, getSourceGraphRelations } from '@/api/sources'
import { createRequestScope } from '@/utils/request-scope'
import { errorMessage, versionLabel } from '@/utils/review-state'

const props = defineProps<{ source: Source; status?: SourceGraphStatus }>()
const open = ref(false)
const loading = ref(false)
const error = ref('')
const graph = ref<SourceGraphRelations>()
const selected = ref<SourceGraphRelation>()
const requestScope = createRequestScope()
let downloadController: AbortController | undefined
const ready = computed(() => props.status?.status === 'completed'
  && props.status.revision_id === props.source.current_revision_id && !props.source.archived_at)
const graphHeight = computed(() => Math.max(80, (graph.value?.items.length || 0) * 76))
function shorten(value: string, max: number) {
  return value.length > max ? value.slice(0, max - 1) + '…' : value
}
function reset() {
  requestScope.dispose()
  downloadController?.abort()
  open.value = false
  loading.value = false
  error.value = ''
  graph.value = undefined
  selected.value = undefined
}
async function show() {
  if (!ready.value) return
  open.value = true
  loading.value = true
  error.value = ''
  graph.value = undefined
  selected.value = undefined
  const sourceId = props.source.id
  const revisionId = props.source.current_revision_id
  const request = requestScope.begin(`${sourceId}/${revisionId}`)
  try {
    const result = await getSourceGraphRelations(sourceId, request.signal)
    request.apply(() => {
      if (props.source.id !== sourceId || props.source.current_revision_id !== revisionId) return
      if (result.revision_id !== revisionId) {
        error.value = '资料版本已变化，请刷新后重试。'
        return
      }
      graph.value = result
    })
  } catch (caught) {
    request.apply(() => { error.value = errorMessage(caught) })
  } finally {
    request.apply(() => { loading.value = false })
  }
}
async function openOriginal() {
  const relation = selected.value
  if (!relation) return
  downloadController?.abort()
  const own = new AbortController()
  downloadController = own
  try {
    await downloadOriginal(props.source.id, relation.revision_id, '原件', own.signal)
  } catch (caught) {
    if (!own.signal.aborted) error.value = errorMessage(caught)
  }
}
watch(() => [props.source.id, props.source.current_revision_id], reset)
onUnmounted(reset)
</script>

<template>
  <section
    class="graph-panel"
    aria-label="知识图谱"
  >
    <div class="graph-heading">
      <div>
        <h3 class="akb-subheading">
          知识图谱
        </h3>
        <p>以下关系由资料自动抽取，请结合原文核对。</p>
      </div>
      <a-button
        v-if="!open"
        :disabled="!ready"
        @click="show"
      >
        查看知识图谱
      </a-button>
      <a-button
        v-else
        @click="reset"
      >
        收起知识图谱
      </a-button>
    </div>
    <template v-if="open">
      <a-spin v-if="loading" />
      <a-alert
        v-else-if="error"
        type="error"
      >
        {{ error }}
        <a-button
          size="mini"
          @click="show"
        >
          重试
        </a-button>
      </a-alert>
      <template v-else-if="graph">
        <a-alert
          v-if="graph.truncated"
          type="warning"
        >
          关系较多，仅显示前 50 条。
        </a-alert>
        <a-empty
          v-if="!graph.items.length"
          :description="graph.truncated ? '当前范围没有可展示的关系，结果已截断' : '当前版本没有可展示的关系'"
        />
        <template v-else>
          <div
            class="graph-canvas"
            aria-hidden="true"
          >
            <svg
              :viewBox="`0 0 760 ${graphHeight}`"
              :height="graphHeight"
              width="760"
            >
              <defs>
                <marker
                  id="graph-arrow"
                  viewBox="0 0 10 10"
                  refX="9"
                  refY="5"
                  markerWidth="6"
                  markerHeight="6"
                  orient="auto-start-reverse"
                >
                  <path
                    d="M 0 0 L 10 5 L 0 10 z"
                    fill="#c5a8ee"
                  />
                </marker>
              </defs>
              <g
                v-for="(relation, index) in graph.items"
                :key="relation.id"
                :transform="`translate(0 ${index * 76})`"
              >
                <rect
                  x="16"
                  y="13"
                  width="222"
                  height="48"
                  rx="3"
                  class="graph-node"
                />
                <text
                  x="127"
                  y="42"
                  text-anchor="middle"
                >{{ shorten(relation.subject, 18) }}</text>
                <line
                  x1="248"
                  y1="37"
                  x2="510"
                  y2="37"
                  stroke="#c5a8ee"
                  stroke-width="2"
                  marker-end="url(#graph-arrow)"
                />
                <rect
                  x="312"
                  y="21"
                  width="142"
                  height="31"
                  rx="3"
                  class="graph-label"
                />
                <text
                  x="383"
                  y="42"
                  text-anchor="middle"
                >{{ shorten(relation.predicate, 11) }}</text>
                <rect
                  x="522"
                  y="13"
                  width="222"
                  height="48"
                  rx="3"
                  class="graph-node"
                />
                <text
                  x="633"
                  y="42"
                  text-anchor="middle"
                >{{ shorten(relation.object, 18) }}</text>
              </g>
            </svg>
          </div>
          <p>选择一条关系查看原文；同名提及分别展示。</p>
          <ol class="graph-list">
            <li
              v-for="relation in graph.items"
              :key="relation.id"
            >
              <button
                type="button"
                :aria-label="`${relation.subject} ${relation.predicate} ${relation.object}`"
                :class="{ active: selected?.id === relation.id }"
                @click="selected = relation"
              >
                {{ relation.subject }} · {{ relation.predicate }} · {{ relation.object }}
              </button>
            </li>
          </ol>
          <div
            v-if="selected"
            class="graph-evidence"
          >
            <strong>关系候选的原文</strong>
            <p>{{ selected.quote }}</p>
            <small>{{ versionLabel(selected.revision_id) }} · {{ selected.locator.logical_path }}
              <template v-if="selected.locator.line_start"> · 第 {{ selected.locator.line_start }} 行</template>
            </small>
            <a-button
              size="small"
              @click="openOriginal"
            >
              下载原件
            </a-button>
          </div>
        </template>
      </template>
    </template>
  </section>
</template>

<style scoped>
.graph-panel { color: var(--akb-text); border-top: 1px solid var(--akb-line); padding-top: 12px; }
.graph-heading { display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 12px; }
.graph-heading p, .graph-panel > p { color: var(--akb-text-secondary); }
.graph-canvas { max-height: 320px; overflow: auto; border: 1px solid var(--akb-line); background: #100d16; }
.graph-canvas svg { display: block; }
.graph-canvas text { fill: var(--akb-text); font-size: 14px; }
.graph-node { fill: #30243b; stroke: #9d82b5; }
.graph-label { fill: #21182c; stroke: #665477; }
.graph-list { max-height: 180px; overflow: auto; margin: 10px 0; padding-left: 24px; }
.graph-list button { border: 1px solid transparent; background: transparent; color: var(--akb-text-secondary); padding: 8px; text-align: left; cursor: pointer; }
.graph-list button:hover, .graph-list button.active { color: var(--akb-text); background: #352943; border-color: #9d82b5; }
.graph-evidence { display: grid; gap: 9px; padding: 14px; border-left: 3px solid var(--akb-primary); background: #21182c; }
.graph-evidence p { margin: 0; white-space: pre-wrap; overflow-wrap: anywhere; }
.graph-evidence small { color: var(--akb-text-secondary); overflow-wrap: anywhere; }
.graph-evidence .arco-btn { justify-self: start; }
</style>
