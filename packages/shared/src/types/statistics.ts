/** 统计相关类型 */

export interface OverviewStats {
  total_items: number
  available_items: number
  total_agents: number
  today_chats: number
  items_growth: number
  chats_growth: number
}

export interface RecentActivity {
  id: string
  type: 'kb_created' | 'item_created' | 'import_done' | 'agent_created'
  title: string
  created_at: string
}

export interface ItemsByType {
  type: string
  count: number
}

export interface TrendPoint {
  date: string
  count: number
}

export interface TopItem {
  title: string
  count: number
}

export interface TagFrequency {
  tag: string
  count: number
}
