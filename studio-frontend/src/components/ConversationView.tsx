import { useConversation } from '../hooks/useConversation'
import { motion } from 'framer-motion'
import { UserMessage } from './entries/UserMessage'
import { ThinkingBlock } from './entries/ThinkingBlock'
import { ToolUse } from './entries/ToolUse'
import { ToolResult } from './entries/ToolResult'
import { TextBlock } from './entries/TextBlock'

interface Props {
  sessionId: string
}

export function ConversationView({ sessionId }: Props) {
  const { data, isLoading, error } = useConversation(sessionId)

  if (isLoading) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <div className="flex flex-col items-center gap-3">
          <div className="w-8 h-8 border-2 border-accent border-t-transparent rounded-full animate-spin" />
          <span className="text-sm text-text-muted">Loading conversation...</span>
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <div className="text-center">
          <div className="text-deny mb-2">Failed to load conversation</div>
          <div className="text-xs text-text-muted font-mono">{(error as Error).message}</div>
        </div>
      </div>
    )
  }

  if (!data) return null

  return (
    <div className="flex-1 flex flex-col overflow-hidden">
      {/* Header */}
      <header className="px-6 py-4 border-b border-border bg-bg-secondary/50 backdrop-blur-sm">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-sm font-medium text-text-primary">Session</h2>
            <div className="font-mono text-xs text-text-muted mt-0.5">
              {sessionId.slice(0, 20)}...
            </div>
          </div>
          {data.stats && (
            <div className="flex items-center gap-4 text-xs">
              {data.stats.tool_calls !== undefined && (
                <Stat label="Tools" value={data.stats.tool_calls} />
              )}
              {data.stats.tokens_in !== undefined && (
                <Stat label="In" value={`${data.stats.tokens_in}`} />
              )}
              {data.stats.tokens_out !== undefined && (
                <Stat label="Out" value={`${data.stats.tokens_out}`} />
              )}
            </div>
          )}
        </div>
      </header>

      {/* Conversation entries */}
      <div className="flex-1 overflow-y-auto">
        <div className="max-w-4xl mx-auto px-6 py-6 space-y-4">
          {data.entries.map((entry, index) => (
            <motion.div
              key={index}
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: index * 0.02, duration: 0.2 }}
            >
              <EntryRenderer entry={entry} />
            </motion.div>
          ))}
        </div>
      </div>
    </div>
  )
}

function EntryRenderer({ entry }: { entry: import('../lib/api').ConversationEntry }) {
  switch (entry.type) {
    case 'user_message':
      return <UserMessage content={entry.content || ''} />
    case 'thinking':
      return <ThinkingBlock content={entry.content || ''} />
    case 'tool_use':
      return (
        <ToolUse
          name={entry.name || 'Unknown'}
          input={entry.input || {}}
          hooks={entry.hooks}
        />
      )
    case 'tool_result':
      return <ToolResult content={entry.content || ''} />
    case 'text':
      return <TextBlock content={entry.content || ''} />
    default:
      return null
  }
}

function Stat({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="text-right">
      <div className="text-text-muted">{label}</div>
      <div className="font-mono text-text-secondary">{value}</div>
    </div>
  )
}
