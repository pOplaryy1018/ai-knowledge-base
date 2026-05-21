<script setup lang="ts">
/**
 * 统计面板 — 时间筛选 + 图表 + Top 知识表格
 */
import { ref, computed } from 'vue'
import { IconClockCircle, IconFolder } from '@arco-design/web-vue/es/icon'
import VChart from 'vue-echarts'
import { use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { LineChart, BarChart, PieChart } from 'echarts/charts'
import {
  GridComponent,
  TooltipComponent,
  LegendComponent} from 'echarts/components'
import type { KnowledgeBase } from '@akb/shared'
import { listKnowledgeBases } from '@/api/knowledge'
import {
  useItemsByType,
  useItemsTrend,
  useChatTrend,
  useTopItems,
  useTagsWordcloud} from '@/composables/useStatisticsQueries'

// 注册 ECharts 组件
use([CanvasRenderer, LineChart, BarChart, PieChart, GridComponent, TooltipComponent, LegendComponent])

// ── 筛选条件 ──
const days = ref(30)
const selectedKbId = ref<string | undefined>(undefined)
const kbOptions = ref<{ label: string; value: string }[]>([])

// 加载知识库列表用于下拉筛选
async function loadKbOptions() {
  const res = await listKnowledgeBases(1, 100, '')
  kbOptions.value = (res.items as KnowledgeBase[]).map((kb) => ({
    label: kb.name,
    value: kb.id}))
}
loadKbOptions()

// ── 数据查询 ──
const { data: itemsByType, isLoading: typeLoading } = useItemsByType(selectedKbId.value)
const { data: itemsTrend, isLoading: trendLoading } = useItemsTrend(days.value, selectedKbId.value)
const { data: chatTrend, isLoading: chatLoading } = useChatTrend(days.value)
const { data: topItems, isLoading: topLoading } = useTopItems(20, selectedKbId.value)
// 词云组件待实现，查询结果暂未绑定到视图
useTagsWordcloud(selectedKbId.value)

// ── 条目趋势折线图 ──
const itemsTrendOption = computed(() => ({
  tooltip: { trigger: 'axis' as const },
  grid: { left: '3%', right: '4%', bottom: '3%', containLabel: true },
  xAxis: {
    type: 'category' as const,
    data: itemsTrend.value?.map((p) => p.date) ?? []},
  yAxis: { type: 'value' as const },
  series: [
    {
      name: '新增条目',
      type: 'line',
      data: itemsTrend.value?.map((p) => p.count) ?? [],
      smooth: true,
      lineStyle: { color: '#409eff' },
      areaStyle: { color: 'rgba(64,158,255,0.1)' }},
  ]}))

// ── 问答趋势柱状图 ──
const chatTrendOption = computed(() => ({
  tooltip: { trigger: 'axis' as const },
  grid: { left: '3%', right: '4%', bottom: '3%', containLabel: true },
  xAxis: {
    type: 'category' as const,
    data: chatTrend.value?.map((p) => p.date) ?? []},
  yAxis: { type: 'value' as const },
  series: [
    {
      name: '问答次数',
      type: 'bar',
      data: chatTrend.value?.map((p) => p.count) ?? [],
      itemStyle: { color: '#67c23a', borderRadius: [4, 4, 0, 0] }},
  ]}))

// ── 类型分布饼图 ──
const typePieOption = computed(() => ({
  tooltip: { trigger: 'item' as const },
  legend: { bottom: '0%' },
  series: [
    {
      name: '类型分布',
      type: 'pie',
      radius: ['40%', '70%'],
      data: itemsByType.value?.map((item) => ({
        name: item.type,
        value: item.count})) ?? [],
      emphasis: {
        itemStyle: { shadowBlur: 10, shadowOffsetX: 0, shadowColor: 'rgba(0,0,0,0.5)' }}},
  ]}))

// ── 时间筛选预设 ──
const dayPresets = [
  { label: '近7天', value: 7 },
  { label: '近30天', value: 30 },
  { label: '近90天', value: 90 },
]

function handlePresetChange(val: number | string | boolean | undefined) {
  days.value = Number(val)
}
</script>

<template>
  <div class="statistics-page">
    <!-- 顶部筛选栏 -->
    <a-card class="filter-card">
      <div class="filter-bar">
        <div class="filter-left">
          <IconClockCircle :size="16" />
          <span class="filter-label">时间范围：</span>
          <a-radio-group
            :model-value="days"
            size="medium"
            @change="handlePresetChange"
          >
            <a-radio
              v-for="preset in dayPresets"
              :key="preset.value"
              :value="preset.value"
            >
              {{ preset.label }}
            </a-radio>
          </a-radio-group>
        </div>
        <div class="filter-right">
          <IconFolder :size="16" />
          <span class="filter-label">知识库：</span>
          <a-select
            v-model="selectedKbId"
            placeholder="全部知识库"
            allow-clear
            style="width: 200px"
          >
            <a-option
              v-for="kb in kbOptions"
              :key="kb.value"
              :label="kb.label"
              :value="kb.value"
            />
          </a-select>
        </div>
      </div>
    </a-card>

    <!-- 图表区：折线图 + 柱状图 -->
    <a-row
      :gutter="20"
      class="chart-row"
    >
      <a-col :span="12">
        <a-card>
          <template #header>
            <span class="chart-title">知识条目增长趋势</span>
          </template>
          <a-skeleton
            :loading="trendLoading"
            :animation="true"
          >
            <v-chart
              :option="itemsTrendOption"
              style="height: 320px"
              autoresize
            />
          </a-skeleton>
        </a-card>
      </a-col>
      <a-col :span="12">
        <a-card>
          <template #header>
            <span class="chart-title">问答活跃趋势</span>
          </template>
          <a-skeleton
            :loading="chatLoading"
            :animation="true"
          >
            <v-chart
              :option="chatTrendOption"
              style="height: 320px"
              autoresize
            />
          </a-skeleton>
        </a-card>
      </a-col>
    </a-row>

    <!-- 图表区：饼图 + Top 知识 -->
    <a-row
      :gutter="20"
      class="chart-row"
    >
      <a-col :span="10">
        <a-card>
          <template #header>
            <span class="chart-title">知识类型分布</span>
          </template>
          <a-skeleton
            :loading="typeLoading"
            :animation="true"
          >
            <v-chart
              :option="typePieOption"
              style="height: 320px"
              autoresize
            />
          </a-skeleton>
        </a-card>
      </a-col>
      <a-col :span="14">
        <a-card>
          <template #header>
            <span class="chart-title">热门知识 Top 20</span>
          </template>
          <a-skeleton
            :loading="topLoading"
            :animation="true"
          >
            <a-table
              :data="topItems ?? []"
              :stripe="true"
              style="max-height:320px"
            >
              <template #empty>
                <a-empty description="暂无数据" />
              </template>
              <a-table-column
                title="#"
                :width="50"
              >
                <template #cell="{ rowIndex }">
                  {{ rowIndex + 1 }}
                </template>
              </a-table-column>
              <a-table-column
                data-index="title"
                title="知识标题"
                ellipsis
              />
              <a-table-column
                data-index="count"
                title="引用次数"
                :width="100"
                :sortable="{ sortDirections: ['ascend', 'descend'] }"
              />
            </a-table>
          </a-skeleton>
        </a-card>
      </a-col>
    </a-row>
  </div>
</template>

<style scoped>
.statistics-page {
  max-width: 1400px;
}

.filter-card {
  margin-bottom: 20px;
}

.filter-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.filter-left,
.filter-right {
  display: flex;
  align-items: center;
  gap: 8px;
}

.filter-label {
  font-size: 14px;
  color: var(--akb-text-secondary);
  white-space: nowrap;
}

.chart-row {
  margin-bottom: 20px;
}

.chart-title {
  font-size: 15px;
  font-weight: 600;
  color: var(--akb-text);
}
</style>
