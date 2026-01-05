import { useEffect, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { getWebSocketUrl } from '../lib/api'

export function useWebSocket() {
  const queryClient = useQueryClient()
  const [isConnected, setIsConnected] = useState(false)

  useEffect(() => {
    const url = getWebSocketUrl()
    const socket = new WebSocket(url)

    socket.onopen = () => {
      console.log('[WS] Connected')
      setIsConnected(true)
    }

    socket.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data)
        if (data.type === 'db_updated') {
          // Invalidate all queries to refetch
          queryClient.invalidateQueries({ queryKey: ['sessions'] })
          queryClient.invalidateQueries({ queryKey: ['conversation'] })
          console.log('[WS] Database updated, invalidating queries')
        }
      } catch (e) {
        console.error('[WS] Failed to parse message:', e)
      }
    }

    socket.onclose = () => {
      console.log('[WS] Disconnected')
      setIsConnected(false)
    }

    socket.onerror = (e) => {
      console.error('[WS] Error:', e)
    }

    return () => {
      socket.close()
    }
  }, [queryClient])

  return { isConnected }
}
