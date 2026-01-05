import { useQuery } from '@tanstack/react-query'
import { fetchApi } from '../lib/api'
import type { ConversationResponse } from '../lib/api'

export function useConversation(sessionId: string | null) {
  return useQuery({
    queryKey: ['conversation', sessionId],
    queryFn: () => fetchApi<ConversationResponse>(`/api/sessions/${sessionId}/conversation`),
    enabled: !!sessionId,
  })
}
