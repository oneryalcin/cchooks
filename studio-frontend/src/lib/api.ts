const API_BASE = import.meta.env.DEV ? '' : window.location.origin

export async function fetchApi<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`)
  if (!res.ok) {
    throw new Error(`API error: ${res.status} ${res.statusText}`)
  }
  return res.json()
}

export function getWebSocketUrl(): string {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  const host = import.meta.env.DEV ? 'localhost:5556' : window.location.host
  return `${protocol}//${host}/ws`
}

// Types matching backend responses
export interface Session {
  session_id: string
  hook_count: number
  event_count: number
  first_seen: number  // Unix epoch
  last_seen: number   // Unix epoch
  transcript_path?: string
}

export interface Handler {
  name: string
  decision: string | null
  duration_ms: number | null
  reason: string | null
}

export interface HookData {
  hook_id: string
  hook_event_name: string
  total_duration_ms: number
  handlers: Handler[]
  input_preview?: string
}

export interface ConversationEntry {
  type: 'user_message' | 'thinking' | 'tool_use' | 'tool_result' | 'text'
  content?: string
  id?: string
  name?: string
  input?: Record<string, unknown>
  hooks?: HookData
  tool_use_id?: string
}

export interface ConversationResponse {
  session_id: string
  entries: ConversationEntry[]
  stats: {
    tokens_in?: number
    tokens_out?: number
    messages?: number
    turns?: number
    tool_calls?: number
  }
}
