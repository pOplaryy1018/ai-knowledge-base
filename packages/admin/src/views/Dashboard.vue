<script setup lang="ts">
/**
 * 工作台概览 — 统计卡片 + 快捷入口 + 最近动态
 */
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import StatCard from '@/components/statistics/StatCard.vue'
import { useOverviewStats, useRecentActivities } from '@/composables/useStatisticsQueries'
import { IconFile, IconFolder, IconRobot, IconBarChart } from '@arco-design/web-vue/es/icon'

const router = useRouter()

const { data: overview, isLoading: overviewLoading } = useOverviewStats()
const { data: activities, isLoading: activityLoading } = useRecentActivities(10)

const quickLinks = computed(() => [
  { title: '知识库管理', icon: IconFolder, path: '/admin/knowledge-bases' },
  { title: '导入文档', icon: IconFile, path: '/admin/knowledge-bases' },
  { title: 'Agent 管理', icon: IconRobot, path: '/admin/agents' },
  { title: '统计面板', icon: IconBarChart, path: '/admin/statistics' },
])

const activityTypeMap: Record<string, { color: string; label: string }> = {
  kb_created: { color: 'var(--akb-primary)', label: '知识库' },
  item_created: { color: 'var(--akb-success)', label: '条目' },
  import_done: { color: 'var(--akb-warning)', label: '导入' },
  agent_created: { color: '#909399', label: 'Agent' }}

function navigateTo(path: string) {
  router.push(path)
}
</script>

<template>
  <div class="dashboard">
    <!-- 统计卡片 -->
    <a-row
      :gutter="20"
      class="stat-row"
    >
      <a-col :span="6">
        <StatCard
          title="知识条目总数"
          :value="overview?.total_items ?? 0"
          :trend="overview?.items_growth"
          :icon="IconFile"
          :loading="overviewLoading"
        />
      </a-col>
      <a-col :span="6">
        <StatCard
          title="可用条目数"
          :value="overview?.available_items ?? 0"
          :icon="IconFolder"
          :loading="overviewLoading"
        />
      </a-col>
      <a-col :span="6">
        <StatCard
          title="Agent 总数"
          :value="overview?.total_agents ?? 0"
          :icon="IconRobot"
          :loading="overviewLoading"
        />
      </a-col>
      <a-col :span="6">
        <StatCard
          title="今日问答次数"
          :value="overview?.today_chats ?? 0"
          :trend="overview?.chats_growth"
          :icon="IconRobot"
          :loading="overviewLoading"
        />
      </a-col>
    </a-row>

    <!-- 快捷入口 + 最近动态 -->
    <a-row
      :gutter="20"
      class="bottom-row"
    >
      <a-col :span="8">
        <a-card class="quick-links-card">
          <template #header>
            <span class="card-header-title">快捷入口</span>
          </template>
          <div class="quick-links">
            <a-button
              v-for="link in quickLinks"
              :key="link.path"
              class="quick-link-btn"
              @click="navigateTo(link.path)"
            >
              <template #icon>
                <component :is="link.icon" />
              </template>
              {{ link.title }}
            </a-button>
          </div>
        </a-card>
      </a-col>

      <a-col :span="16">
        <a-card class="timeline-card">
          <template #header>
            <span class="card-header-title">最近动态</span>
          </template>
          <a-skeleton
            :loading="activityLoading"
            :animation="true"
          >
            <template #template>
              <div
                v-for="i in 5"
                :key="i"
                style="padding: 12px 0"
              >
                <a-skeleton-line style="width: 80%" />
              </div>
            </template>
            <template #default>
              <div
                v-if="!activities || activities.length === 0"
                class="empty-state"
              >
                <a-empty description="暂无动态" />
              </div>
              <a-timeline v-else>
                <a-timeline-item
                  v-for="activity in activities"
                  :key="activity.id"
                  :timestamp="new Date(activity.created_at).toLocaleString('zh-CN')"
                  placement="top"
                  :color="activityTypeMap[activity.type]?.color"
                >
                  <span class="activity-text">{{ activity.title }}</span>
                  <a-tag
                    size="small"
                    :color="activityTypeMap[activity.type]?.color"
                    style="color: #fff; border: none; margin-left: 8px"
                  >
                    {{ activityTypeMap[activity.type]?.label }}
                  </a-tag>
                </a-timeline-item>
              </a-timeline>
            </template>
          </a-skeleton>
        </a-card>
      </a-col>
    </a-row>
  </div>
</template>

<style scoped>
.dashboard {
  max-width: 1400px;
}

.stat-row {
  margin-bottom: 20px;
}

.bottom-row {
  margin-bottom: 0;
}

.card-header-title {
  font-size: 16px;
  font-weight: 600;
  color: var(--akb-text);
}

.quick-links {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
}

.quick-link-btn {
  flex: 1;
  min-width: 120px;
  height: 48px;
  font-size: 14px;
}

.timeline-card {
  height: 100%;
}

.activity-text {
  font-size: 14px;
  color: var(--akb-text);
}

.empty-state {
  padding: 40px 0;
}
</style>
