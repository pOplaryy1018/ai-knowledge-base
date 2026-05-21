/**
 * 统计面板 — TanStack Query Hooks
 */
import { computed } from 'vue'
import { useQuery } from '@tanstack/vue-query'
import {
  getOverviewStats,
  getRecentActivities,
  getItemsByType,
  getItemsTrend,
  getChatTrend,
  getTopItems,
  getTagsWordcloud} from '@/api/statistics'
import { queryKeys } from './queryKeys'

import type { MaybeRef } from 'vue'

// ── 概览统计 ──
export function useOverviewStats(enabled: MaybeRef<boolean> = true) {
  return useQuery({
    queryKey: queryKeys.statistics.overview,
    queryFn: getOverviewStats,
    staleTime: 1000 * 60,
    enabled})
}

// ── 最近动态 ──
export function useRecentActivities(limit = 10, enabled: MaybeRef<boolean> = true) {
  return useQuery({
    queryKey: queryKeys.statistics.recentActivities,
    queryFn: () => getRecentActivities(limit),
    enabled})
}

// ── 条目类型分布 ──
export function useItemsByType(kbId?: string, enabled: MaybeRef<boolean> = true) {
  return useQuery({
    queryKey: computed(() => queryKeys.statistics.itemsByType(kbId)),
    queryFn: () => getItemsByType(kbId),
    enabled})
}

// ── 条目增长趋势 ──
export function useItemsTrend(days = 30, kbId?: string, enabled: MaybeRef<boolean> = true) {
  return useQuery({
    queryKey: computed(() => queryKeys.statistics.itemsTrend(days, kbId)),
    queryFn: () => getItemsTrend(days, kbId),
    enabled})
}

// ── 问答活跃趋势 ──
export function useChatTrend(days = 30, enabled: MaybeRef<boolean> = true) {
  return useQuery({
    queryKey: computed(() => queryKeys.statistics.chatTrend(days)),
    queryFn: () => getChatTrend(days),
    enabled})
}

// ── 热门知识 Top N ──
export function useTopItems(limit = 20, kbId?: string, enabled: MaybeRef<boolean> = true) {
  return useQuery({
    queryKey: computed(() => queryKeys.statistics.topItems(limit, kbId)),
    queryFn: () => getTopItems(limit, kbId),
    enabled})
}

// ── 标签词云 ──
export function useTagsWordcloud(kbId?: string, enabled: MaybeRef<boolean> = true) {
  return useQuery({
    queryKey: computed(() => queryKeys.statistics.tagsWordcloud(kbId)),
    queryFn: () => getTagsWordcloud(kbId),
    enabled})
}
