/**
 * TanStack Vue Query — Query Key 常量
 */

export const queryKeys = {
  // ── 知识库 ──
  knowledgeBases: {
    all: ['knowledge-bases'] as const,
    list: (page: number, size: number, search: string) =>
      [...queryKeys.knowledgeBases.all, 'list', { page, size, search }] as const},

  // ── Agent ──
  agents: {
    all: ['agents'] as const,
    list: (page: number, size: number) =>
      [...queryKeys.agents.all, 'list', { page, size }] as const,
    detail: (id: string) => [...queryKeys.agents.all, 'detail', id] as const},

  // ── 统计 ──
  statistics: {
    overview: ['statistics', 'overview'] as const,
    recentActivities: ['statistics', 'recent-activities'] as const,
    itemsByType: (kbId?: string) => ['statistics', 'items-by-type', kbId] as const,
    itemsTrend: (days: number, kbId?: string) =>
      ['statistics', 'items-trend', { days, kbId }] as const,
    chatTrend: (days: number) => ['statistics', 'chat-trend', { days }] as const,
    topItems: (limit: number, kbId?: string) =>
      ['statistics', 'top-items', { limit, kbId }] as const,
    tagsWordcloud: (kbId?: string) => ['statistics', 'tags-wordcloud', kbId] as const},

  // ── 用户管理 ──
  users: {
    all: ['users'] as const,
    list: () => [...queryKeys.users.all, 'list'] as const,
    roles: ['users', 'roles'] as const}} as const
