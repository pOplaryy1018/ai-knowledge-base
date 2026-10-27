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
  useTopItems} from '@/composables/useStatisticsQueries'

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
const { data: itemsByType, isLoading: typeLoading } = useItemsByType(selectedKbId)
const { data: itemsTrend, isLoading: trendLoading } = useItemsTrend(days, selectedKbId)
const { data: chatTrend, isLoading: chatLoading } = useChatTrend(days)
const { data: topItems, isLoading: topLoading } = useTopItems(20, selectedKbId)

// ── 条目趋势折线图 ──
const itemsTrendOption = computed(() => ({
  backgroundColor: 'transparent',
  tooltip: { trigger: 'axis' as const, backgroundColor: '#231c2c', borderColor: '#705f80', textStyle: { color: '#f3f3f5' } },
  grid: { left: '3%', right: '4%', bottom: '3%', containLabel: true },
  xAxis: {
    type: 'category' as const,
    axisLabel: { color: '#bdc0c8' }, axisLine: { lineStyle: { color: '#50465a' } },
    data: itemsTrend.value?.map((p) => p.date) ?? []},
  yAxis: { type: 'value' as const, axisLabel: { color: '#bdc0c8' }, splitLine: { lineStyle: { color: '#3e3549' } } },
  series: [
    {
      name: '新增条目',
      type: 'line',
      data: itemsTrend.value?.map((p) => p.count) ?? [],
      smooth: true,
      lineStyle: { color: '#c5a8ee' },
      areaStyle: { color: 'rgba(197,168,238,0.13)' }},
  ]}))

// ── 问答趋势柱状图 ──
const chatTrendOption = computed(() => ({
  backgroundColor: 'transparent',
  tooltip: { trigger: 'axis' as const, backgroundColor: '#231c2c', borderColor: '#705f80', textStyle: { color: '#f3f3f5' } },
  grid: { left: '3%', right: '4%', bottom: '3%', containLabel: true },
  xAxis: {
    type: 'category' as const,
    axisLabel: { color: '#bdc0c8' }, axisLine: { lineStyle: { color: '#50465a' } },
    data: chatTrend.value?.map((p) => p.date) ?? []},
  yAxis: { type: 'value' as const, axisLabel: { color: '#bdc0c8' }, splitLine: { lineStyle: { color: '#3e3549' } } },
  series: [
    {
      name: '问答次数',
      type: 'bar',
      data: chatTrend.value?.map((p) => p.count) ?? [],
      itemStyle: { color: '#eeb275', borderRadius: [2, 2, 0, 0] }},
  ]}))

// ── 类型分布饼图 ──
const typePieOption = computed(() => ({
  backgroundColor: 'transparent',
  color: ['#c5a8ee', '#eeb275', '#9982be', '#bdc0c8', '#e698aa'],
  tooltip: { trigger: 'item' as const, backgroundColor: '#231c2c', borderColor: '#705f80', textStyle: { color: '#f3f3f5' } },
  legend: { bottom: '0%', textStyle: { color: '#bdc0c8' } },
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
    <header class="akb-section-heading">
      <span class="akb-kicker">COMMAND / METRICS</span><h2>统计分析</h2><p>查看资料与问答活动的运行趋势。</p>
    </header>
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
            <a-skeleton-line :rows="6" />
            <template #content>
              <v-chart
                :option="itemsTrendOption"
                style="height: 320px"
                autoresize
              />
            </template>
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
            <a-skeleton-line :rows="6" />
            <template #content>
              <v-chart
                :option="chatTrendOption"
                style="height: 320px"
                autoresize
              />
            </template>
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
            <a-skeleton-line :rows="6" />
            <template #content>
              <v-chart
                :option="typePieOption"
                style="height: 320px"
                autoresize
              />
            </template>
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
            <a-skeleton-line :rows="6" />
            <template #content>
              <a-table
                :data="topItems ?? []"
                :stripe="true"
                style="max-height:320px"
              >
                <template #empty>
                  <a-empty description="暂无数据" />
                </template>
                <template #columns>
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
                </template>
              </a-table>
            </template>
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
