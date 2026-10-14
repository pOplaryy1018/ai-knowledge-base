/**
 * 统计面板 — TanStack Query Hooks
 */
import { computed, toValue } from 'vue'
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

import type { MaybeRef, MaybeRefOrGetter } from 'vue'

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
export function useItemsByType(kbId?: MaybeRefOrGetter<string | undefined>, enabled: MaybeRef<boolean> = true) {
  return useQuery({
    queryKey: computed(() => queryKeys.statistics.itemsByType(toValue(kbId))),
    queryFn: () => getItemsByType(toValue(kbId)),
    enabled})
}

// ── 条目增长趋势 ──
export function useItemsTrend(days: MaybeRefOrGetter<number> = 30, kbId?: MaybeRefOrGetter<string | undefined>, enabled: MaybeRef<boolean> = true) {
  return useQuery({
    queryKey: computed(() => queryKeys.statistics.itemsTrend(toValue(days), toValue(kbId))),
    queryFn: () => getItemsTrend(toValue(days), toValue(kbId)),
    enabled})
}

// ── 问答活跃趋势 ──
export function useChatTrend(days: MaybeRefOrGetter<number> = 30, enabled: MaybeRef<boolean> = true) {
  return useQuery({
    queryKey: computed(() => queryKeys.statistics.chatTrend(toValue(days))),
    queryFn: () => getChatTrend(toValue(days)),
    enabled})
}

// ── 热门知识 Top N ──
export function useTopItems(limit: MaybeRefOrGetter<number> = 20, kbId?: MaybeRefOrGetter<string | undefined>, enabled: MaybeRef<boolean> = true) {
  return useQuery({
    queryKey: computed(() => queryKeys.statistics.topItems(toValue(limit), toValue(kbId))),
    queryFn: () => getTopItems(toValue(limit), toValue(kbId)),
    enabled})
}

// ── 标签词云 ──
export function useTagsWordcloud(kbId?: MaybeRefOrGetter<string | undefined>, enabled: MaybeRef<boolean> = true) {
  return useQuery({
    queryKey: computed(() => queryKeys.statistics.tagsWordcloud(toValue(kbId))),
    queryFn: () => getTagsWordcloud(toValue(kbId)),
    enabled})
}
