import { QueryClient } from '@tanstack/vue-query'
export const queryClient = new QueryClient({ defaultOptions: { queries: { staleTime: 120000, retry: 1, refetchOnWindowFocus: false } } })
