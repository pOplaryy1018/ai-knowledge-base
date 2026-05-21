/**
 * 统计 API ── 概览、趋势、热门、词云
 */
import type {
  OverviewStats,
  RecentActivity,
  ItemsByType,
  TrendPoint,
  TopItem,
  TagFrequency} from '@akb/shared'
import { getApiClient } from './client'

export async function getOverviewStats(): Promise<OverviewStats> {
  const { data } = await getApiClient().get<OverviewStats>('/statistics/overview')
  return data
}

export async function getRecentActivities(
  limit = 10,
): Promise<RecentActivity[]> {
  const { data } = await getApiClient().get<RecentActivity[]>(
    '/statistics/recent-activities',
    { params: { limit } },
  )
  return data
}

export async function getItemsByType(kbId?: string): Promise<ItemsByType[]> {
  const { data } = await getApiClient().get<ItemsByType[]>(
    '/statistics/items-by-type',
    { params: { kb_id: kbId } },
  )
  return data
}

export async function getItemsTrend(
  days = 30,
  kbId?: string,
): Promise<TrendPoint[]> {
  const { data } = await getApiClient().get<TrendPoint[]>(
    '/statistics/items-trend',
    { params: { days, kb_id: kbId } },
  )
  return data
}

export async function getChatTrend(days = 30): Promise<TrendPoint[]> {
  const { data } = await getApiClient().get<TrendPoint[]>(
    '/statistics/chat-trend',
    { params: { days } },
  )
  return data
}

export async function getTopItems(
  limit = 20,
  kbId?: string,
): Promise<TopItem[]> {
  const { data } = await getApiClient().get<TopItem[]>(
    '/statistics/top-items',
    { params: { limit, kb_id: kbId } },
  )
  return data
}

export async function getTagsWordcloud(kbId?: string): Promise<TagFrequency[]> {
  const { data } = await getApiClient().get<TagFrequency[]>(
    '/statistics/tags-wordcloud',
    { params: { kb_id: kbId } },
  )
  return data
}
