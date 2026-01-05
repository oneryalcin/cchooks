import { useQuery } from '@tanstack/react-query'
import { fetchApi } from '../lib/api'
import type { Session } from '../lib/api'

export function useSessions() {
  return useQuery({
    queryKey: ['sessions'],
    queryFn: () => fetchApi<Session[]>('/api/sessions'),
  })
}
