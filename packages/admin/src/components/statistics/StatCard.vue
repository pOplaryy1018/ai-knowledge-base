<script setup lang="ts">
/**
 * 统计卡片 — a-statistic + 环比趋势箭头
 */
import { computed } from 'vue'
import { IconToTop, IconToBottom } from '@arco-design/web-vue/es/icon'
import type { Component } from 'vue'

const props = defineProps<{
  title: string
  value: number | string
  trend?: number
  icon?: Component
  loading?: boolean
}>()

const displayValue = computed(() => {
  if (typeof props.value === 'number') return props.value
  return parseFloat(props.value) || 0
})

const trendColor = computed(() => {
  if (!props.trend) return ''
  return props.trend > 0 ? 'var(--akb-success)' : 'var(--akb-danger)'
})

const trendText = computed(() => {
  if (!props.trend) return ''
  const sign = props.trend > 0 ? '+' : ''
  return `${sign}${props.trend}%`
})
</script>

<template>
  <a-card
    shadow="hover"
    class="stat-card"
  >
    <a-skeleton
      :loading="loading"
      :animation="true"
    >
      <template #template>
        <div class="skeleton-stat">
          <a-skeleton-line style="width: 60%" />
          <a-skeleton-line style="width: 40%; margin-top: 8px" />
        </div>
      </template>
      <template #default>
        <div class="stat-content">
          <div class="stat-info">
            <span class="stat-title">{{ title }}</span>
            <a-statistic
              :value="displayValue"
              class="stat-value"
            />
            <span
              v-if="trendText"
              class="stat-trend"
              :style="{ color: trendColor }"
            >
              <IconToTop
                v-if="trend && trend > 0"
                :size="14"
              />
              <IconToBottom
                v-else
                :size="14"
              />
              {{ trendText }}
              <span class="trend-label">较昨日</span>
            </span>
          </div>
          <div
            v-if="icon"
            class="stat-icon"
          >
            <component
              :is="icon"
              :size="36"
              style="color: var(--akb-primary)"
            />
          </div>
        </div>
      </template>
    </a-skeleton>
  </a-card>
</template>

<style scoped>
.stat-card {
  border-radius: var(--akb-card-radius);
}

.stat-content {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.stat-info {
  flex: 1;
}

.stat-title {
  font-size: 14px;
  color: var(--akb-text-secondary);
}

.stat-value {
  margin-top: 4px;
}

.stat-trend {
  display: inline-flex;
  align-items: center;
  gap: 2px;
  font-size: 13px;
  font-weight: 500;
  margin-top: 6px;
}

.trend-label {
  color: var(--akb-text-secondary);
  font-weight: 400;
  margin-left: 2px;
}

.stat-icon {
  flex-shrink: 0;
  margin-left: 16px;
  width: 56px;
  height: 56px;
  border-radius: 12px;
  background: rgba(64, 158, 255, 0.08);
  display: flex;
  align-items: center;
  justify-content: center;
}

.skeleton-stat {
  padding: 8px 0;
}
</style>
